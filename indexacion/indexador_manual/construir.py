"""Construcción del índice: bloques por proceso (SPIMI), mezcla y ensamblado del archivo final.

Fase 1 (paralela): cada tarea normaliza un rango de documentos y escribe un bloque ordenado
    por término. Fase 2: se mezclan los bloques de a `MAX_ABIERTOS`, en pasadas, hasta que quedan
    pocos; la mezcla final escribe diccionario y postings y calcula las normas de los documentos.
Fase 3: se ensambla el archivo (cabecera, metadatos, hosts, documentos, diccionario, postings).

Reanudable: todo lo que se escribe va primero a un archivo `.part` y se renombra al terminar, y el
avance queda en `<salida>.tmp/estado.json`. Si el proceso se corta, al volver a ejecutar el mismo comando
se salta lo ya hecho (bloques de la fase 1, mezclas de la fase 2). Si cambia algo que afecta el resultado
(política, listas de datos, código de normalización, documentos) el avance se descarta y se empieza de cero.
"""
import hashlib
import heapq
import json
import math
import mmap
import multiprocessing
import os
import re
import shutil
import struct
import time
from collections import Counter
from types import SimpleNamespace

import numpy as np

from . import formato as fmt
from .config import Politica, cargar
from .normalizacion import Normalizador

MAX_ABIERTOS = 32
ESQUEMA = 1  # versión del formato de los archivos temporales
_norm = None  # Normalizador del proceso trabajador


# --- listado de documentos ----------------------------------------------------------------

def listar_documentos(repo: str, limite: int = 0):
    """[(host, hash_hex, ruta)] ordenado; con `limite`, una muestra equiespaciada."""
    docs = []
    for host in sorted(os.listdir(repo)):
        dir_host = os.path.join(repo, host)
        if not os.path.isdir(dir_host):
            continue
        for raiz, _, archivos in os.walk(dir_host):
            for nombre in archivos:
                base, ext = os.path.splitext(nombre)
                if ext == ".txt" and len(base) == 64:
                    docs.append((host, base, os.path.join(raiz, nombre)))
    docs.sort(key=lambda d: (d[0], d[1]))
    if limite and len(docs) > limite:
        paso = len(docs) / limite
        docs = [docs[int(i * paso)] for i in range(limite)]
    return docs


def _cargar_reglas_depuracion(ruta: str):
    hosts, urls, titulos, pagina_tema, sin_pagina_tema = set(), [], [], None, set()
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            clave, _, valor = linea.partition("=")
            clave, valor = clave.strip(), valor.strip()
            if clave == "host":
                hosts.add(valor)
            elif clave == "url":
                urls.append(valor)
            elif clave == "titulo":
                titulos.append(valor)
            elif clave == "titulo_hits":  # "<min_hits> :: <regex>"
                minimo, _, regex = valor.partition("::")
                pagina_tema = (int(minimo), re.compile(regex.strip(), re.I))
            elif clave == "titulo_hits_excluir_host":
                sin_pagina_tema.add(valor)
            else:
                raise ValueError(f"{ruta}: regla desconocida {clave!r}")
    union = lambda partes: re.compile("|".join(f"(?:{p})" for p in partes), re.I) if partes else None
    return hosts, union(urls), union(titulos), pagina_tema, sin_pagina_tema


def depurar(docs, base_datos: str, ruta_reglas: str):
    """Conserva los documentos que cumplen alguna regla de `ruta_reglas` (host, URL o título).

    Los metadatos salen de data/crawl.db, donde la araña los dejó para cada documento.
    """
    import sqlite3
    if not base_datos or not os.path.exists(base_datos) or not ruta_reglas:
        raise SystemExit(f"depuracion requiere base_datos y reglas_depuracion: {base_datos} {ruta_reglas}")
    hosts, re_url, re_titulo, pagina_tema, sin_pagina_tema = _cargar_reglas_depuracion(ruta_reglas)
    pedidos = {d[1] for d in docs}
    con = sqlite3.connect(f"file:{base_datos}?mode=ro", uri=True)
    aceptados = set()
    for sha, host, url, titulo, hits in con.execute(
            "SELECT sha256, host, url, title, topic_hits FROM documents"):
        if sha not in pedidos:
            continue
        if (host in hosts or (re_url and re_url.search(url or ""))
                or (re_titulo and re_titulo.search(titulo or ""))
                or (pagina_tema and host not in sin_pagina_tema and hits >= pagina_tema[0]
                    and pagina_tema[1].search(titulo or ""))):
            aceptados.add(sha)
    con.close()
    return [d for d in docs if d[1] in aceptados]


def filtrar_por_tema(docs, base_datos: str, min_hits: int):
    """Descarta los documentos con menos de `min_hits` palabras clave del dominio (topic_hits).

    `topic_hits` lo calculó la araña (common/extract.py) y quedó en data/crawl.db.
    """
    import sqlite3
    if not base_datos or not os.path.exists(base_datos):
        raise SystemExit(f"tema_min_hits requiere la base de datos de la araña: {base_datos}")
    con = sqlite3.connect(f"file:{base_datos}?mode=ro", uri=True)
    hits = dict(con.execute("SELECT sha256, topic_hits FROM documents"))
    con.close()
    return [d for d in docs if hits.get(d[1], 0) >= min_hits]


# --- archivos atómicos y estado -----------------------------------------------------------

def _publicar(ruta_part: str, ruta: str):
    """Renombra de forma atómica un archivo `.part` ya cerrado a su nombre definitivo."""
    with open(ruta_part, "r+b") as f:  # r+b: en Windows fsync no funciona sobre un archivo solo de lectura
        os.fsync(f.fileno())
    os.replace(ruta_part, ruta)


def _escribir_json(ruta: str, datos: dict):
    with open(ruta + ".part", "w", encoding="utf-8") as f:
        json.dump(datos, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(ruta + ".part", ruta)


def _firma(politica: Politica, limite: int, docs) -> str:
    """Huella de todo lo que afecta al contenido de los bloques; si cambia, no se puede reanudar."""
    from . import normalizacion
    h = hashlib.sha256()
    conf = "\n".join(l for l in politica.texto_conf.splitlines() if not l.strip().startswith("procesos"))
    h.update(f"{ESQUEMA}|{fmt.VERSION}|{limite}|{len(docs)}|{conf}".encode())
    for ruta in (politica.stopwords, politica.lemas, politica.sinonimos, politica.entidades,
                 politica.reglas_depuracion if politica.depuracion else None, normalizacion.__file__):
        if ruta and os.path.exists(ruta):
            with open(ruta, "rb") as f:
                h.update(f.read())
    for d in docs:
        h.update(d[1].encode())
    return h.hexdigest()


def _preparar_temporal(dir_tmp: str, firma: str) -> dict:
    """Devuelve el estado guardado si corresponde a este mismo trabajo; si no, empieza limpio."""
    ruta_estado = os.path.join(dir_tmp, "estado.json")
    estado = None
    if os.path.exists(ruta_estado):
        try:
            with open(ruta_estado, encoding="utf-8") as f:
                estado = json.load(f)
        except (OSError, ValueError):
            estado = None
    if estado and estado.get("firma") == firma:
        for nombre in os.listdir(dir_tmp):  # restos de escrituras interrumpidas
            if nombre.endswith(".part"):
                os.remove(os.path.join(dir_tmp, nombre))
        estado["ejecuciones"] = estado.get("ejecuciones", 1) + 1
        _escribir_json(ruta_estado, estado)
        print(f"Reanudando un trabajo anterior (ejecución n.º {estado['ejecuciones']}).", flush=True)
        return estado
    if os.path.isdir(dir_tmp) and os.listdir(dir_tmp):
        print("Hay archivos temporales de otra configuración; se descartan y se empieza de cero.", flush=True)
    shutil.rmtree(dir_tmp, ignore_errors=True)
    os.makedirs(dir_tmp)
    estado = {"firma": firma, "ejecuciones": 1, "seg": {}, "fase1_ok": False, "final_ok": False}
    _escribir_json(ruta_estado, estado)
    return estado


class _Cronometro:
    """Suma al estado el tiempo de una fase, aunque se interrumpa, para que el total sea real.

    Además de guardar al salir, `guardar()` deja el tiempo acumulado cada pocos segundos, de modo que
    si el proceso muere de golpe (corte de luz, kill) solo se pierden esos segundos.
    """

    def __init__(self, estado, dir_tmp, clave, cada=5.0):
        self.estado, self.ruta, self.clave, self.cada = estado, os.path.join(dir_tmp, "estado.json"), clave, cada

    def __enter__(self):
        self.t = self.ultimo = time.time()
        self.base = self.estado["seg"].get(self.clave, 0.0)
        return self

    def guardar(self, forzar=False):
        ahora = time.time()
        if forzar or ahora - self.ultimo >= self.cada:
            self.estado["seg"][self.clave] = self.base + (ahora - self.t)
            _escribir_json(self.ruta, self.estado)
            self.ultimo = ahora

    def __exit__(self, *_):
        self.guardar(forzar=True)


# --- fase 1: bloques ----------------------------------------------------------------------

def _iniciar_trabajador(ruta_conf):
    global _norm
    _norm = Normalizador(cargar(ruta_conf))


def _payload(pares) -> bytes:
    out = bytearray()
    previo = 0
    for i in range(0, len(pares), 2):
        doc, tf = pares[i], pares[i + 1]
        for v in (doc - previo, tf):
            while v > 0x7F:
                out.append((v & 0x7F) | 0x80)
                v >>= 7
            out.append(v)
        previo = doc
    return bytes(out)


def _entrada_bloque(termino: bytes, n: int, ultimo: int, payload: bytes) -> bytes:
    cv = fmt.codificar_varint
    return b"".join((cv(len(termino)), termino, cv(n), cv(ultimo), cv(len(payload)), payload))


def _ruta_bloque0(dir_bloques, idx):
    return os.path.join(dir_bloques, f"bloque_0_{idx:06d}.bin")


def _ruta_lens(dir_bloques, idx):
    return os.path.join(dir_bloques, f"lens_{idx:06d}.npy")


def _tarea_bloque(args):
    """Normaliza un rango de documentos y deja su bloque y sus longitudes. La tarea está completa
    cuando existe el archivo de longitudes, que se escribe al final."""
    idx, docs, dir_bloques = args
    postings = {}
    longitudes = []
    for doc_id, ruta in docs:
        with open(ruta, "rb") as f:
            texto = f.read().decode("utf-8", errors="replace")
        terminos = _norm(texto)
        longitudes.append(len(terminos))
        for termino, tf in Counter(terminos).items():
            lista = postings.get(termino)
            if lista is None:
                postings[termino] = [doc_id, tf]
            else:
                lista.append(doc_id)
                lista.append(tf)
    if postings:
        ruta_bloque = _ruta_bloque0(dir_bloques, idx)
        with open(ruta_bloque + ".part", "wb") as f:
            for termino in sorted(postings):
                pares = postings[termino]
                f.write(_entrada_bloque(termino.encode("utf-8"), len(pares) // 2, pares[-2],
                                        _payload(pares)))
        _publicar(ruta_bloque + ".part", ruta_bloque)
    ruta_lens = _ruta_lens(dir_bloques, idx)
    with open(ruta_lens + ".part", "wb") as f:
        np.save(f, np.array(longitudes, dtype=np.int64))
    _publicar(ruta_lens + ".part", ruta_lens)
    return idx, len(docs)


# --- fase 2: mezcla -----------------------------------------------------------------------

def _entradas(ruta: str, orden: int):
    """Genera (término, orden, n, último_doc, payload) de un bloque, vía mmap."""
    with open(ruta, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        pos, fin = 0, len(mm)
        while pos < fin:
            ltermino, pos = fmt.leer_varint(mm, pos)
            termino = bytes(mm[pos:pos + ltermino])
            pos += ltermino
            n, pos = fmt.leer_varint(mm, pos)
            ultimo, pos = fmt.leer_varint(mm, pos)
            lpayload, pos = fmt.leer_varint(mm, pos)
            yield termino, orden, n, ultimo, bytes(mm[pos:pos + lpayload])
            pos += lpayload


def _mezclar(rutas, emitir):
    """Mezcla bloques ordenados (en orden de doc_id) y llama emitir(término, n, último, payload)."""
    flujos = [_entradas(r, i) for i, r in enumerate(rutas)]
    actual = None
    for termino, _, n, ultimo, payload in heapq.merge(*flujos):
        if termino == actual:
            salto, p = fmt.leer_varint(payload, 0)
            tf, p = fmt.leer_varint(payload, p)
            trozos.append(fmt.codificar_varint(salto - ult_acum) + fmt.codificar_varint(tf))
            trozos.append(payload[p:])
            total += n
            ult_acum = ultimo
        else:
            if actual is not None:
                emitir(actual, total, ult_acum, b"".join(trozos))
            actual, total, ult_acum, trozos = termino, n, ultimo, [payload]
    if actual is not None:
        emitir(actual, total, ult_acum, b"".join(trozos))


def _mezcla_intermedia(rutas, destino):
    with open(destino + ".part", "wb") as f:
        _mezclar(rutas, lambda t, n, u, p: f.write(_entrada_bloque(t, n, u, p)))
    _publicar(destino + ".part", destino)


# --- fase 3: archivo final ----------------------------------------------------------------

class _EscritorFinal:
    """Recibe los términos ya mezclados: escribe diccionario y postings y acumula las normas."""

    def __init__(self, ruta_dict, ruta_post, n_docs, al_paso=None):
        self.al_paso = al_paso
        self.rutas = (ruta_dict, ruta_post)
        self.f_dict = open(ruta_dict + ".part", "wb")
        self.f_post = open(ruta_post + ".part", "wb")
        self.n_docs = n_docs
        self.norma2 = np.zeros(n_docs, dtype=np.float64)
        self.n_terminos = 0
        self.n_postings = 0

    def __call__(self, termino, df, _ultimo, payload):
        cv = fmt.codificar_varint
        self.f_dict.write(b"".join((bytes((len(termino),)), termino, cv(df), cv(len(payload)))))
        self.f_post.write(payload)
        self.n_terminos += 1
        self.n_postings += df
        if self.al_paso and self.n_terminos % 5000 == 0:
            self.al_paso()
        valores = fmt.decodificar_varints(payload)
        docs = np.cumsum(valores[0::2])
        peso = (1.0 + np.log10(valores[1::2])) * math.log10(self.n_docs / df)
        self.norma2[docs] += peso * peso  # los doc_id de un término son únicos

    def cerrar(self):
        self.f_dict.close()
        self.f_post.close()
        for ruta in self.rutas:
            _publicar(ruta + ".part", ruta)


def _copiar(destino, ruta):
    with open(ruta, "rb") as f:
        shutil.copyfileobj(f, destino, 1 << 20)


def _ensamblar(politica, docs, longitudes, resultado, ruta_dict, ruta_post):
    hosts = sorted({d[0] for d in docs})
    if len(hosts) > 0xFFFF:
        raise ValueError("demasiados hosts para u16")
    id_host = {h: i for i, h in enumerate(hosts)}

    meta = politica.texto_conf.encode("utf-8")
    seccion_meta = struct.pack(">I", len(meta)) + meta
    seccion_hosts = struct.pack(">I", len(hosts)) + b"".join(
        struct.pack(">H", len(h.encode())) + h.encode() for h in hosts)

    tabla = np.zeros(len(docs), dtype=fmt.DOC_DTYPE)
    tabla["hash"] = [bytes.fromhex(d[1]) for d in docs]
    tabla["host"] = [id_host[d[0]] for d in docs]
    tabla["n_tokens"] = longitudes
    norma = np.sqrt(resultado.norma2)
    tabla["norma"] = np.where(norma > 0, norma, 1.0)
    seccion_docs = tabla.tobytes()

    off_meta = fmt.HEADER_SIZE
    off_hosts = off_meta + len(seccion_meta)
    off_docs = off_hosts + len(seccion_hosts)
    off_dict = off_docs + len(seccion_docs)
    off_post = off_dict + os.path.getsize(ruta_dict)
    tam = off_post + os.path.getsize(ruta_post)
    cabecera = fmt.empaquetar_cabecera(
        len(docs), resultado.n_terminos, resultado.n_postings, int(np.sum(longitudes)),
        off_meta, off_hosts, off_docs, off_dict, off_post, tam)

    with open(politica.salida + ".part", "wb") as out:
        out.write(cabecera)
        out.write(seccion_meta)
        out.write(seccion_hosts)
        out.write(seccion_docs)
        _copiar(out, ruta_dict)
        _copiar(out, ruta_post)
    _publicar(politica.salida + ".part", politica.salida)  # el .idx nunca queda a medias
    return tam


# --- orquestación -------------------------------------------------------------------------

def construir(ruta_conf: str, limite: int = 0, procesos: int = 0, desde_cero: bool = False) -> dict:
    politica = cargar(ruta_conf)
    procesos = procesos or politica.procesos
    t0 = time.time()
    print(f"Listando documentos en {politica.repo} ...", flush=True)
    docs = listar_documentos(politica.repo, limite)
    docs_sin_depurar = len(docs)
    if politica.depuracion:
        docs = depurar(docs, politica.base_datos, politica.reglas_depuracion)
        print(f"Depuración: {len(docs):,} de {docs_sin_depurar:,} documentos "
              f"({len(docs) / docs_sin_depurar:.0%})", flush=True)
    if politica.tema_min_hits:
        antes = len(docs)
        docs = filtrar_por_tema(docs, politica.base_datos, politica.tema_min_hits)
        print(f"Filtro temático (topic_hits >= {politica.tema_min_hits}): {len(docs):,} de {antes:,} documentos",
              flush=True)
    if not docs:
        raise SystemExit("No se encontraron documentos .txt en el repo")
    print(f"{len(docs):,} documentos ({time.time() - t0:.1f} s). Procesos: {procesos}", flush=True)

    os.makedirs(os.path.dirname(politica.salida), exist_ok=True)
    dir_tmp = politica.salida + ".tmp"
    if desde_cero:
        shutil.rmtree(dir_tmp, ignore_errors=True)
    estado = _preparar_temporal(dir_tmp, _firma(politica, limite, docs))
    estado["seg"].setdefault("listado", time.time() - t0)

    try:
        longitudes, escritor, tam_archivo = _trabajar(politica, docs, dir_tmp, estado, procesos)
    except KeyboardInterrupt:
        print("\nInterrumpido. Lo ya terminado quedó guardado: vuelve a ejecutar el mismo comando para continuar.")
        raise SystemExit(130)

    seg = estado["seg"]
    stats = {
        "politica": os.path.basename(ruta_conf),
        "documentos": len(docs),
        "terminos": escritor.n_terminos,
        "postings": escritor.n_postings,
        "tokens_totales": int(longitudes.sum()),
        "tamano_bytes": tam_archivo,
        "segundos_normalizacion_y_bloques": round(seg.get("fase1", 0.0), 2),
        "segundos_mezcla": round(seg.get("fase2", 0.0), 2),
        "segundos_ensamblado": round(seg.get("fase3", 0.0), 2),
        "segundos_total": round(sum(seg.values()), 2),
        "ejecuciones": estado["ejecuciones"],
        "procesos": procesos,
        "limite": limite,
        "tema_min_hits": politica.tema_min_hits,
        "depuracion": politica.depuracion,
        "documentos_antes_de_depurar": docs_sin_depurar,
    }
    _escribir_json(politica.salida + ".stats.json", stats)
    shutil.rmtree(dir_tmp, ignore_errors=True)
    print(f"Índice: {politica.salida} ({tam_archivo / 1e6:.1f} MB, {stats['terminos']:,} términos, "
          f"{stats['segundos_total']} s)")
    return stats


def _trabajar(politica, docs, dir_tmp, estado, procesos):
    ruta_estado = os.path.join(dir_tmp, "estado.json")
    tam = politica.docs_por_bloque
    n_tareas = (len(docs) + tam - 1) // tam

    # fase 1: normalizar y escribir bloques (solo las tareas que faltan)
    if not estado["fase1_ok"]:
        pendientes = [(i, [(j, docs[j][2]) for j in range(i * tam, min((i + 1) * tam, len(docs)))], dir_tmp)
                      for i in range(n_tareas) if not os.path.exists(_ruta_lens(dir_tmp, i))]
        previos = n_tareas - len(pendientes)
        if previos:
            print(f"  fase 1: {previos} de {n_tareas} bloques ya estaban hechos", flush=True)
        hechos = len(docs) - sum(len(t[1]) for t in pendientes)
        with _Cronometro(estado, dir_tmp, "fase1") as reloj:
            t1 = time.time()
            hechos_aqui = 0
            if pendientes:
                with multiprocessing.Pool(procesos, _iniciar_trabajador, (politica.ruta_conf,)) as pool:
                    for _, n in pool.imap_unordered(_tarea_bloque, pendientes):
                        hechos += n
                        hechos_aqui += n
                        reloj.guardar()
                        print(f"\r  normalización: {hechos:,}/{len(docs):,} docs "
                              f"({hechos_aqui / (time.time() - t1):.0f} docs/s)", end="", flush=True)
                print()
        estado["fase1_ok"] = True
        estado["nivel0"] = [os.path.basename(_ruta_bloque0(dir_tmp, i)) for i in range(n_tareas)
                            if os.path.exists(_ruta_bloque0(dir_tmp, i))]
        _escribir_json(ruta_estado, estado)

    longitudes = np.zeros(len(docs), dtype=np.int64)
    for i in range(n_tareas):
        arr = np.load(_ruta_lens(dir_tmp, i))
        longitudes[i * tam:i * tam + len(arr)] = arr

    # fase 2: mezclas intermedias y mezcla final
    ruta_dict = os.path.join(dir_tmp, "diccionario.bin")
    ruta_post = os.path.join(dir_tmp, "postings.bin")
    ruta_norma = os.path.join(dir_tmp, "norma2.npy")
    if not estado["final_ok"]:
        with _Cronometro(estado, dir_tmp, "fase2") as reloj:
            rutas = [os.path.join(dir_tmp, n) for n in estado["nivel0"]]
            nivel = 1
            while len(rutas) > MAX_ABIERTOS:
                nuevas = []
                for g in range(0, len(rutas), MAX_ABIERTOS):
                    grupo = rutas[g:g + MAX_ABIERTOS]
                    destino = os.path.join(dir_tmp, f"bloque_{nivel}_{g // MAX_ABIERTOS:06d}.bin")
                    if not os.path.exists(destino):
                        _mezcla_intermedia(grupo, destino)
                    for r in grupo:  # las entradas se borran solo cuando el destino ya está completo
                        if os.path.exists(r):
                            os.remove(r)
                    nuevas.append(destino)
                    reloj.guardar()
                rutas = nuevas
                nivel += 1
                print(f"  mezcla nivel {nivel - 1}: {len(rutas)} bloques", flush=True)
            escritor = _EscritorFinal(ruta_dict, ruta_post, len(docs), reloj.guardar)
            _mezclar(rutas, escritor)
            escritor.cerrar()
            with open(ruta_norma + ".part", "wb") as f:
                np.save(f, escritor.norma2)
            _publicar(ruta_norma + ".part", ruta_norma)
        estado.update(final_ok=True, n_terminos=escritor.n_terminos, n_postings=escritor.n_postings)
        _escribir_json(ruta_estado, estado)
    resultado = SimpleNamespace(norma2=np.load(ruta_norma), n_terminos=estado["n_terminos"],
                                n_postings=estado["n_postings"])

    # fase 3: ensamblado
    with _Cronometro(estado, dir_tmp, "fase3"):
        tam_archivo = _ensamblar(politica, docs, longitudes, resultado, ruta_dict, ruta_post)
    return longitudes, resultado, tam_archivo
