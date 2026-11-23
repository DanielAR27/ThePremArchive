"""Búsqueda con los dos indexadores: Lucene (por el servicio HTTP en Java) o el índice propio (en este mismo proceso).
Los dos devuelven lo mismo: términos, total de aciertos y los mejores resultados (host, hash y puntaje), con los mismos
filtros (sitio y fechas) y los mismos órdenes (relevancia, más recientes primero, relevancia con frescura)."""
import functools
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date

import numpy as np

from . import config

sys.path.insert(0, str(config.RAIZ))

MAX_PROPIOS_EN_MEMORIA = 2   # cada índice propio carga su diccionario completo; se guardan los últimos usados
BASE_DIAS = date(2000, 1, 1)
VIDA_MEDIA_DIAS = 180.0      # cada cuántos días baja a la mitad el peso de un documento en el orden "recent"
FRESCURA_SIN_FECHA = 0.5     # factor de un documento sin fecha: ni premiado ni castigado del todo
ORDENES = ("relevance", "newest", "recent")


class MotorNoDisponible(Exception):
    pass


def dia_de(iso: str) -> int:
    """AAAA-MM-DD -> días desde 2000-01-01 más 1 (como en fechas.bin). Lanza ValueError si no es una fecha."""
    return (date.fromisoformat(iso) - BASE_DIAS).days + 1


def iso_de(dia: int) -> str:
    return date.fromordinal(BASE_DIAS.toordinal() + dia - 1).isoformat()


class TablaDeFechas:
    """El día de publicación de cada documento, buscado por los primeros 8 bytes de su hash (ver preparar_fechas.py)."""

    def __init__(self):
        crudo = config.FECHAS_BIN.read_bytes()
        if crudo[:4] != b"PFEC":
            raise ValueError(f"{config.FECHAS_BIN} no es un archivo de fechas")
        n = int(np.frombuffer(crudo, dtype="<u4", count=1, offset=8)[0])
        datos = np.frombuffer(crudo, dtype=np.dtype([("p", "<i8"), ("d", "<u2")]), count=n, offset=12)
        self.claves = datos["p"].copy()
        self.dias = datos["d"].copy()
        self.mas_reciente = int(self.dias.max())

    def para(self, prefijos):
        """Días de los documentos con esos prefijos de hash (0 = sin fecha conocida)."""
        pos = np.searchsorted(self.claves, prefijos)
        pos[pos == len(self.claves)] = 0
        return np.where(self.claves[pos] == prefijos, self.dias[pos], 0).astype(np.int32)


class Buscador:
    def __init__(self):
        self._propios = OrderedDict()        # política -> (Indice, Normalizador, días de cada documento)
        self._cerrojo = threading.Lock()
        self._sitios = None
        self._fechas = None

    # --- fechas ------------------------------------------------------------------------------------
    def fechas(self):
        """La tabla de fechas, o None si no se ha preparado (python -m web_app.preparar_fechas)."""
        if self._fechas is None and config.FECHAS_BIN.exists():
            self._fechas = TablaDeFechas()
        return self._fechas

    def info_fechas(self):
        """{'minima', 'maxima', 'conFecha'} de la colección indexada, o None si no hay fechas."""
        tabla = self.fechas()
        if tabla is None:
            return None
        try:
            meta = json.loads(config.FECHAS_META.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if "indexados_con_fecha" not in meta:
            try:
                indice, _, dias = self._propio_cargado(config.POLITICA_POR_OMISION)
                con_fecha = float(np.count_nonzero(dias)) / len(dias)
                activas = dias[dias > 0]
                meta.update({"indexados_con_fecha": round(con_fecha, 4), "minima_indexados": iso_de(int(activas.min())),
                             "maxima_indexados": iso_de(int(activas.max()))})
                config.FECHAS_META.write_text(json.dumps(meta, indent=1), encoding="utf-8")
            except MotorNoDisponible:
                pass
        return {"minima": meta.get("minima_indexados", meta.get("minima")),
                "maxima": meta.get("maxima_indexados", meta.get("maxima")),
                "conFecha": meta.get("indexados_con_fecha")}

    # --- Lucene -----------------------------------------------------------------------------------
    def politicas_lucene(self):
        """Políticas que el servicio de Lucene tiene cargadas, o [] si no está corriendo."""
        try:
            with urllib.request.urlopen(f"{config.LUCENE_URL}/salud", timeout=2) as respuesta:
                datos = json.load(respuesta)
            return list(datos.get("politicas", [])) if datos.get("ok") else []
        except (urllib.error.URLError, OSError, ValueError):
            return []

    def _lucene(self, consulta, politica, sitio, k, desde, hasta, orden):
        parametros = {"q": consulta, "k": k, "policy": politica}
        if sitio:
            parametros["site"] = sitio
        if desde:
            parametros["from"] = desde
        if hasta:
            parametros["to"] = hasta
        if orden != "relevance":
            parametros["sort"] = orden
        url = f"{config.LUCENE_URL}/buscar?" + urllib.parse.urlencode(parametros)
        try:
            with urllib.request.urlopen(url, timeout=120) as respuesta:
                datos = json.load(respuesta)
        except urllib.error.HTTPError as error:
            raise MotorNoDisponible(f"The Lucene search service rejected the request ({error.code}).") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise MotorNoDisponible("The Lucene search service is not responding.") from error
        return {"terms": datos["terminos"], "total": datos["total"], "undated": datos.get("sin_fecha", 0),
                "tookMs": datos["tiempo_ms"],
                "results": [{"host": r["host"], "doc": r["hash"], "score": r["puntaje"]} for r in datos["resultados"]]}

    # --- Índice propio ----------------------------------------------------------------------------
    def _propio_cargado(self, politica):
        with self._cerrojo:
            if politica in self._propios:
                self._propios.move_to_end(politica)
                return self._propios[politica]
        from indexacion.indexador_manual.buscar import Indice
        from indexacion.indexador_manual.config import cargar
        from indexacion.indexador_manual.normalizacion import Normalizador
        conf = cargar(config.CONFIG_DIR / f"politica_{politica}.conf")
        if not conf.salida or not os.path.exists(conf.salida):
            raise MotorNoDisponible(f"The own index for policy {politica} has not been built.")
        indice = Indice(str(conf.salida))
        tabla = self.fechas()
        dias = tabla.para(indice.prefijos_hash()) if tabla is not None else np.zeros(indice.n_docs, dtype=np.int32)
        cargado = (indice, Normalizador(conf), dias)
        with self._cerrojo:
            self._propios[politica] = cargado
            while len(self._propios) > MAX_PROPIOS_EN_MEMORIA:
                _, (viejo, _, _) = self._propios.popitem(last=False)
                viejo.cerrar()
        return cargado

    @functools.lru_cache(maxsize=1)
    def politicas_propio(self):
        from indexacion.indexador_manual.config import cargar
        disponibles = []
        for p in config.POLITICAS:
            archivo = config.CONFIG_DIR / f"politica_{p}.conf"
            if archivo.exists() and os.path.exists(cargar(archivo).salida):
                disponibles.append(p)
        return disponibles

    def _propio(self, consulta, politica, sitio, k, desde, hasta, orden):
        indice, normalizador, dias = self._propio_cargado(politica)
        t0 = time.perf_counter()
        terminos = normalizador(consulta)
        vacio = {"terms": terminos, "total": 0, "undated": 0, "results": [],
                 "tookMs": (time.perf_counter() - t0) * 1000}
        puntaje = indice.puntajes(terminos)
        if puntaje is None:
            return vacio
        apto = puntaje > 0
        if sitio:
            if sitio not in indice.hosts:
                return vacio
            apto &= indice.docs["host"] == indice.hosts.index(sitio)
        sin_fecha = 0
        if desde or hasta:
            sin_fecha = int(np.count_nonzero(apto & (dias == 0)))
            apto &= (dias >= (dia_de(desde) if desde else 1)) & (dias <= (dia_de(hasta) if hasta else 65535)) & (dias > 0)
        posiciones = np.flatnonzero(apto)
        total = len(posiciones)
        if total:
            if orden == "newest":
                clave = dias[posiciones] + np.minimum(puntaje[posiciones], 999) / 10000.0
            elif orden == "recent":
                referencia = self.fechas().mas_reciente
                edad = np.maximum(0, referencia - dias[posiciones])
                frescura = np.where(dias[posiciones] == 0, FRESCURA_SIN_FECHA, 0.3 + 0.7 * 2.0 ** (-edad / VIDA_MEDIA_DIAS))
                clave = puntaje[posiciones] * frescura
            else:
                clave = puntaje[posiciones]
            k = min(k, total)
            mejores = np.argpartition(-clave, k - 1)[:k]
            mejores = posiciones[mejores[np.argsort(-clave[mejores])]]
        else:
            mejores = []
        return {"terms": terminos, "total": total, "undated": sin_fecha,
                "tookMs": (time.perf_counter() - t0) * 1000,
                "results": [{"host": indice.hosts[int(indice.docs[d]["host"])], "doc": indice.hash_hex(int(d)),
                             "score": float(puntaje[d])} for d in mejores]}

    # --- Sitios que tiene la colección ------------------------------------------------------------
    def sitios(self):
        """Los sitios web de la colección indexada (se guardan en un archivo para no leer el índice cada vez)."""
        if self._sitios is None:
            try:
                self._sitios = json.loads(config.CACHE_SITIOS.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                indice, _, _ = self._propio_cargado(config.POLITICA_POR_OMISION)
                self._sitios = sorted(indice.hosts)
                config.CACHE_SITIOS.parent.mkdir(parents=True, exist_ok=True)
                config.CACHE_SITIOS.write_text(json.dumps(self._sitios), encoding="utf-8")
        return self._sitios

    # --- Interfaz pública -------------------------------------------------------------------------
    def buscar(self, consulta, motor, politica, sitio="", k=10, desde="", hasta="", orden="relevance"):
        """{'terms', 'total', 'undated', 'tookMs', 'results': [{host, doc, score}]}.
        Lanza MotorNoDisponible si el motor no puede responder y ValueError si una fecha o el orden no son válidos."""
        consulta = " ".join(consulta.split())
        k = max(1, min(k, config.MAX_K))
        if orden not in ORDENES:
            raise ValueError(f"sort must be one of {', '.join(ORDENES)}.")
        for texto in (desde, hasta):
            if texto:
                dia_de(texto)                                 # ValueError si no es AAAA-MM-DD
        if (desde or hasta or orden != "relevance") and self.fechas() is None:
            raise MotorNoDisponible("Publication dates are not prepared. Run: python -m web_app.preparar_fechas")
        if not consulta:
            return {"terms": [], "total": 0, "undated": 0, "tookMs": 0.0, "results": []}
        if motor == "lucene":
            return self._lucene(consulta, politica, sitio, k, desde, hasta, orden)
        if motor == "manual":
            return self._propio(consulta, politica, sitio, k, desde, hasta, orden)
        raise MotorNoDisponible(f"Unknown engine: {motor}")
