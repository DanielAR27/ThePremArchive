"""Evalúa la calidad de las políticas con consultas de prueba, por el método del pool (Manning et al., cap. 8).

Paso 1:  python indexacion/herramientas/evaluar.py pool
    Corre cada consulta de indexacion/config/datos/consultas.txt en los índices manual_A..F y en los de Lucene
    (lucene_A..F, columnas LA..LF; hay que compilar el .jar antes) y junta los primeros K resultados de todas las
    políticas, sin repetir, en estadisticas/evaluacion/pool_juzgado.csv. Si el archivo ya existía, conserva las
    marcas hechas y solo deja en blanco los documentos nuevos. Guarda además los resultados de cada motor en
    estadisticas/evaluacion/resultados_busqueda.json, para compararlos.

Paso 2 (a mano): llenar en pool_juzgado.csv la columna "relevante" de cada fila con
    1 = el documento trata realmente de lo que pide la consulta, 0 = no.
    Cada documento se juzga una sola vez, aunque lo hayan devuelto varias políticas.

Paso 3:  python indexacion/herramientas/evaluar.py resultados
    Calcula la precisión en los primeros K resultados (P@K) de cada política y consulta, y el promedio, para
    cada indexador, y cuánto se parecen los K primeros resultados de uno y otro.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from indexacion.indexador_manual.buscar import Indice  # noqa: E402
from indexacion.indexador_manual.config import cargar  # noqa: E402
from indexacion.indexador_manual.normalizacion import Normalizador  # noqa: E402

POLITICAS = "ABCDEF"
CONSULTAS = RAIZ / "indexacion" / "config" / "datos" / "consultas.txt"
JUZGADO = RAIZ / "estadisticas" / "evaluacion" / "pool_juzgado.csv"  # el pool con la columna "relevante" llena
BUSQUEDAS = RAIZ / "estadisticas" / "evaluacion" / "resultados_busqueda.json"  # top-K de cada motor y política
JAR = RAIZ / "indexacion" / "indexador_lucene" / "target" / "indexador-lucene.jar"


def leer_consultas():
    consultas = []
    for linea in CONSULTAS.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            qid, texto, nota = [c.strip() for c in linea.split("|")]
            consultas.append((qid, texto, nota))
    return consultas


def extracto(ruta: str):
    with open(ruta, encoding="utf-8", errors="replace") as f:
        titulo = f.readline().strip()
        cuerpo = " ".join(f.read(900).split())
    return titulo, cuerpo[:260]


def buscar_lucene(conf: Path, k: int):
    """{consulta: [(host, hash)]} del índice Lucene de esa política, con el comando `consultas` del .jar."""
    if not JAR.exists():
        raise SystemExit(f"Falta {JAR}: compilar con  cd indexacion/indexador_lucene && mvn -q package")
    entorno = dict(os.environ, JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8")
    salida = subprocess.run(["java", "-jar", str(JAR), "consultas", "--config", str(conf), "-k", str(k), str(CONSULTAS)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno,
                            check=True).stdout
    resultado = {}
    for linea in salida.splitlines():
        campos = linea.split("\t")
        if len(campos) == 5:   # id, puesto, host, hash, puntaje (el resto es ruido de Lucene en la salida)
            resultado.setdefault(campos[0], []).append((campos[2], campos[3]))
    return resultado


def pool(k: int):
    consultas = leer_consultas()
    filas = {}
    busquedas = {"manual": {}, "lucene": {}}   # motor -> política -> consulta -> [hash]

    def agregar(qid, texto, hx, host, ruta, columna, rango):
        fila = filas.get((qid, hx))
        if fila is None:
            titulo, cuerpo = extracto(ruta)
            fila = filas[(qid, hx)] = {"consulta": qid, "texto": texto, "doc": hx, "host": host,
                                       "titulo": titulo, "extracto": cuerpo, "rangos": {}, "relevante": ""}
        fila["rangos"][columna] = rango

    for p in POLITICAS:
        conf = RAIZ / "indexacion" / "config" / f"politica_{p}.conf"
        politica = cargar(conf)
        norm, indice = Normalizador(politica), Indice(politica.salida)
        busquedas["manual"][p] = {}
        for qid, texto, _ in consultas:
            hashes = []
            for rango, (doc_id, _) in enumerate(indice.buscar(norm(texto), k), 1):
                hx = indice.hash_hex(doc_id)
                hashes.append(hx)
                agregar(qid, texto, hx, indice.hosts[int(indice.docs[doc_id]["host"])],
                        indice.ruta_documento(doc_id, politica.repo), p, rango)
            busquedas["manual"][p][qid] = hashes
        indice.cerrar()
        print(f"política {p} (manual) lista", flush=True)
        busquedas["lucene"][p] = {}
        textos = {qid: texto for qid, texto, _ in consultas}
        for qid, resultados in buscar_lucene(conf, k).items():
            busquedas["lucene"][p][qid] = [hx for _, hx in resultados]
            for rango, (host, hx) in enumerate(resultados, 1):
                agregar(qid, textos[qid], hx, host, Path(politica.repo) / host / hx[:2] / f"{hx}.txt", "L" + p, rango)
        print(f"política {p} (Lucene) lista", flush=True)
    BUSQUEDAS.parent.mkdir(parents=True, exist_ok=True)
    BUSQUEDAS.write_text(json.dumps(busquedas, indent=1), encoding="utf-8")
    JUZGADO.parent.mkdir(parents=True, exist_ok=True)
    previas = {}   # marcas que ya existían, para no volver a juzgar lo mismo
    if JUZGADO.exists():
        with open(JUZGADO, encoding="utf-8-sig", newline="") as f:
            previas = {(r["consulta"], r["doc"]): r for r in csv.DictReader(f)}
    campos = ["consulta", "texto", "doc", "host", "titulo", "extracto", "rangos", "relevante", "dudoso",
              "revisado_por_humano"]
    nuevos = 0
    try:
        with open(JUZGADO, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(campos)
            for (qid, hx), fila in sorted(filas.items()):
                antes = previas.get((qid, hx), {})
                if not antes.get("relevante", "").strip():
                    nuevos += 1
                rangos = " ".join(f"{p}:{r}" for p, r in sorted(fila["rangos"].items()))
                w.writerow([qid, fila["texto"], hx, fila["host"], fila["titulo"], fila["extracto"], rangos,
                            antes.get("relevante", ""), antes.get("dudoso", ""), antes.get("revisado_por_humano", "")])
    except PermissionError:
        raise SystemExit(f"No se pudo escribir {JUZGADO}: ciérralo en Excel y vuelve a ejecutar.")
    print(f"{len(filas)} documentos en {JUZGADO.name}; {nuevos} sin juzgar todavía.")


def tabla_p(aciertos, columnas, consultas, k):
    print(f"| Consulta | " + " | ".join(columnas) + " |")
    print("|---|" + "---|" * len(columnas))
    for qid, texto, _ in consultas:
        print(f"| {qid} {texto} | " + " | ".join(f"{aciertos.get((qid, c), 0) / k:.1f}" for c in columnas) + " |")
    print("| **Promedio P@%d** | " % k + " | ".join(
        f"**{sum(aciertos.get((q[0], c), 0) for q in consultas) / (k * len(consultas)):.2f}**" for c in columnas) + " |")


def resultados(k: int):
    aciertos = {}   # (consulta, columna) -> relevantes entre los K primeros; columna "A" = manual, "LA" = Lucene
    sin_juzgar = 0
    hay_lucene = False
    with open(JUZGADO, encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            hay_lucene = hay_lucene or "L" in fila["rangos"]
            if fila["relevante"].strip() not in ("0", "1"):
                sin_juzgar += 1
                continue
            for par in fila["rangos"].split():
                c, r = par.split(":")
                if int(r) <= k:
                    aciertos[(fila["consulta"], c)] = aciertos.get((fila["consulta"], c), 0) + int(fila["relevante"])
    if sin_juzgar:
        print(f"AVISO: {sin_juzgar} documentos sin juzgar; los resultados están incompletos.", file=sys.stderr)
    consultas = leer_consultas()
    print("Indexador propio\n")
    tabla_p(aciertos, list(POLITICAS), consultas, k)
    if not (hay_lucene and BUSQUEDAS.exists()):
        return
    print("\nLucene\n")
    tabla_p(aciertos, ["L" + p for p in POLITICAS], consultas, k)

    busquedas = json.loads(BUSQUEDAS.read_text(encoding="utf-8"))
    print(f"\nParecido entre los {k} primeros resultados del propio y de Lucene\n")
    print("| Política | P@%d propio | P@%d Lucene | Documentos en común (media) | Consultas con el mismo documento en el 1.er puesto |" % (k, k))
    print("|---|:---:|:---:|:---:|:---:|")
    for p in POLITICAS:
        pm = sum(aciertos.get((q[0], p), 0) for q in consultas) / (k * len(consultas))
        pl = sum(aciertos.get((q[0], "L" + p), 0) for q in consultas) / (k * len(consultas))
        comunes, mismo, n = 0.0, 0, 0
        for qid, _, _ in consultas:
            a = busquedas["manual"][p].get(qid, [])[:k]
            b = busquedas["lucene"][p].get(qid, [])[:k]
            if not a and not b:
                continue
            n += 1
            comunes += len(set(a) & set(b)) / k
            mismo += bool(a and b and a[0] == b[0])
        print(f"| {p} | {pm:.2f} | {pl:.2f} | {comunes / n * 100:.0f} % | {mismo} de {n} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paso", choices=["pool", "resultados"])
    ap.add_argument("-k", type=int, default=10)
    args = ap.parse_args()
    pool(args.k) if args.paso == "pool" else resultados(args.k)
