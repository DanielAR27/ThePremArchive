"""Verifica que el indexador Lucene normaliza igual que el indexador propio.

Toma una muestra de documentos, los normaliza con las dos implementaciones (Python: Normalizador;
Java: comando "terminos" del jar de Lucene) y compara la lista de términos de cada documento, en orden.

Uso (desde la raíz del repo):
    python indexacion/herramientas/comparar_normalizacion.py --config indexacion/config/politica_C.conf --muestra 500
    python indexacion/herramientas/comparar_normalizacion.py --config indexacion/config/politica_C.conf archivo1.txt ...
"""
import argparse
import difflib
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from indexacion.indexador_manual.config import cargar
from indexacion.indexador_manual.construir import listar_documentos
from indexacion.indexador_manual.normalizacion import Normalizador

JAR = os.path.join(os.path.dirname(__file__), "..", "indexador_lucene", "target", "indexador-lucene.jar")
POR_LLAMADA = 100  # archivos por ejecución de java (límite de largo de la línea de comandos en Windows)


def terminos_lucene(jar, conf, rutas):
    out = {}
    for i in range(0, len(rutas), POR_LLAMADA):
        r = subprocess.run(["java", "-jar", jar, "terminos", "--config", conf, *rutas[i:i + POR_LLAMADA]],
                           capture_output=True, check=True)
        for linea in r.stdout.decode("utf-8").splitlines():
            ruta, _, terminos = linea.partition("\t")
            out[ruta] = terminos.split(" ") if terminos else []
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--muestra", type=int, default=300)
    ap.add_argument("--jar", default=JAR)
    ap.add_argument("--mostrar", type=int, default=5, help="cuántas diferencias mostrar")
    ap.add_argument("archivos", nargs="*")
    a = ap.parse_args()

    politica = cargar(a.config)
    rutas = a.archivos or [d[2] for d in listar_documentos(politica.repo, a.muestra)]
    norm = Normalizador(politica)
    lucene = terminos_lucene(a.jar, a.config, rutas)

    iguales, terminos, distintos = 0, 0, Counter()
    mostradas = 0
    for ruta in rutas:
        with open(ruta, "rb") as f:
            py = norm(f.read().decode("utf-8", errors="replace"))
        jv = lucene.get(ruta)
        terminos += len(py)
        if py == jv:
            iguales += 1
            continue
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, py, jv or [], autojunk=False).get_opcodes():
            if op != "equal":
                distintos[(" ".join(py[i1:i2]), " ".join((jv or [])[j1:j2]))] += 1
        if mostradas < a.mostrar:
            mostradas += 1
            print(f"\nDiferencia en {ruta}:")
            for linea in list(difflib.unified_diff(py, jv or [], "python", "lucene", lineterm="", n=2))[2:40]:
                print("   ", linea)

    print(f"\n{iguales:,} de {len(rutas):,} documentos con exactamente los mismos términos "
          f"({100 * iguales / len(rutas):.2f} %), {terminos:,} términos revisados.")
    if distintos:
        print("Diferencias más frecuentes (python -> lucene):")
        for (py, jv), n in distintos.most_common(20):
            print(f"  {n:6,}  {py!r} -> {jv!r}")
    sys.exit(0 if not distintos else 1)


if __name__ == "__main__":
    main()
