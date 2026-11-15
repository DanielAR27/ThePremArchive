"""Mide cuánto tardan los dos indexadores en abrir un índice y en responder las consultas de prueba.

    python indexacion/herramientas/medir_consultas.py            # las seis políticas
    python indexacion/herramientas/medir_consultas.py B C -n 7   # solo algunas, con 7 repeticiones

Para cada política y cada indexador se mide:
  - apertura: tiempo de abrir el índice (en el propio incluye leer el diccionario completo a memoria);
  - consulta: tiempo de normalizar la consulta, buscar los 10 mejores y leer su hash, con el índice ya abierto.
Cada consulta de consultas.txt se repite N veces después de una pasada de calentamiento y se toma la mediana.
Necesita los índices construidos y el .jar de Lucene compilado. Deja los resultados en
estadisticas/rendimiento_consultas.json e imprime la tabla del documento.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from indexacion.indexador_manual.buscar import Indice  # noqa: E402
from indexacion.indexador_manual.config import cargar  # noqa: E402
from indexacion.indexador_manual.normalizacion import Normalizador  # noqa: E402

CONSULTAS = RAIZ / "indexacion" / "config" / "datos" / "consultas.txt"
JAR = RAIZ / "indexacion" / "indexador_lucene" / "target" / "indexador-lucene.jar"
SALIDA = RAIZ / "estadisticas" / "rendimiento_consultas.json"


def leer_consultas():
    out = []
    for linea in CONSULTAS.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            campos = [c.strip() for c in linea.split("|")]
            out.append((campos[0], campos[1]))
    return out


def medir_propio(conf: Path, repeticiones: int, k: int = 10):
    politica = cargar(conf)
    norm = Normalizador(politica)
    consultas = leer_consultas()
    apertura = 0.0
    indice = None
    for vez in range(2):   # se informa la segunda apertura, con el archivo ya en la caché del sistema
        t0 = time.perf_counter()
        indice = Indice(politica.salida)
        apertura = (time.perf_counter() - t0) * 1000
        if vez == 0:
            indice.cerrar()
    medidas = {qid: [] for qid, _ in consultas}
    for pasada in range(-1, repeticiones):   # la pasada -1 es de calentamiento
        for qid, texto in consultas:
            t0 = time.perf_counter()
            for doc_id, _ in indice.buscar(norm(texto), k):
                indice.hash_hex(doc_id)
            if pasada >= 0:
                medidas[qid].append((time.perf_counter() - t0) * 1000)
    indice.cerrar()
    return apertura, {qid: statistics.median(v) for qid, v in medidas.items()}


def medir_lucene(conf: Path, repeticiones: int, k: int = 10):
    if not JAR.exists():
        raise SystemExit(f"Falta {JAR}: compilar con  cd indexacion/indexador_lucene && mvn -q package")
    entorno = dict(os.environ, JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8")
    salida = subprocess.run(["java", "-jar", str(JAR), "tiempos", "--config", str(conf), "-k", str(k),
                             "--repeticiones", str(repeticiones), str(CONSULTAS)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno,
                            check=True).stdout
    apertura, consultas = 0.0, {}
    for linea in salida.splitlines():
        campos = linea.split("\t")
        if len(campos) == 2 and campos[0] == "apertura_ms":
            apertura = float(campos[1])
        elif len(campos) == 2 and campos[0].startswith("q"):
            consultas[campos[0]] = float(campos[1])
    return apertura, consultas


def formato(ms: float) -> str:
    return f"{ms / 1000:.1f} s" if ms >= 1000 else (f"{ms:.0f} ms" if ms >= 10 else f"{ms:.1f} ms")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("politicas", nargs="*", default=list("ABCDEF"))
    ap.add_argument("-n", "--repeticiones", type=int, default=7)
    args = ap.parse_args()
    resultados = {}
    for p in args.politicas:
        conf = RAIZ / "indexacion" / "config" / f"politica_{p}.conf"
        resultados[p] = {}
        for motor, medir in (("propio", medir_propio), ("lucene", medir_lucene)):
            apertura, consultas = medir(conf, args.repeticiones)
            resultados[p][motor] = {"apertura_ms": apertura, "consultas_ms": consultas,
                                    "mediana_ms": statistics.median(consultas.values()),
                                    "maximo_ms": max(consultas.values())}
        print(f"política {p} lista", flush=True)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resultados, indent=1), encoding="utf-8")

    print("\n| Política | Apertura propio | Apertura Lucene | Consulta propio (mediana / máxima) "
          "| Consulta Lucene (mediana / máxima) |")
    print("|---|---|---|---|---|")
    for p, r in resultados.items():
        a, b = r["propio"], r["lucene"]
        print(f"| {p} | {formato(a['apertura_ms'])} | {formato(b['apertura_ms'])} "
              f"| {formato(a['mediana_ms'])} / {formato(a['maximo_ms'])} "
              f"| {formato(b['mediana_ms'])} / {formato(b['maximo_ms'])} |")


if __name__ == "__main__":
    main()
