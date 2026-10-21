"""Evalúa la calidad de las políticas con consultas de prueba, por el método del pool (Manning et al., cap. 8).

Paso 1:  python indexacion/herramientas/evaluar.py pool
    Corre cada consulta de indexacion/config/datos/consultas.txt en los índices manual_A..F y junta los
    primeros K resultados de todas las políticas, sin repetir, en estadisticas/evaluacion/pool_juzgado.csv.
    Si el archivo ya existía, conserva las marcas hechas y solo deja en blanco los documentos nuevos.

Paso 2 (a mano): llenar en pool_juzgado.csv la columna "relevante" de cada fila con
    1 = el documento trata realmente de lo que pide la consulta, 0 = no.
    Cada documento se juzga una sola vez, aunque lo hayan devuelto varias políticas.

Paso 3:  python indexacion/herramientas/evaluar.py resultados
    Calcula la precisión en los primeros K resultados (P@K) de cada política y consulta, y el promedio.
"""
import argparse
import csv
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


def pool(k: int):
    consultas = leer_consultas()
    filas = {}
    for p in POLITICAS:
        politica = cargar(RAIZ / "indexacion" / "config" / f"politica_{p}.conf")
        norm, indice = Normalizador(politica), Indice(politica.salida)
        for qid, texto, _ in consultas:
            for rango, (doc_id, _) in enumerate(indice.buscar(norm(texto), k), 1):
                hx = indice.hash_hex(doc_id)
                fila = filas.get((qid, hx))
                if fila is None:
                    titulo, cuerpo = extracto(indice.ruta_documento(doc_id, politica.repo))
                    host = indice.hosts[int(indice.docs[doc_id]["host"])]
                    fila = filas[(qid, hx)] = {"consulta": qid, "texto": texto, "doc": hx, "host": host,
                                               "titulo": titulo, "extracto": cuerpo, "rangos": {}, "relevante": ""}
                fila["rangos"][p] = rango
        indice.cerrar()
        print(f"política {p} lista", flush=True)
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


def resultados(k: int):
    aciertos = {}   # (consulta, política) -> relevantes entre los K primeros
    sin_juzgar = 0
    with open(JUZGADO, encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["relevante"].strip() not in ("0", "1"):
                sin_juzgar += 1
                continue
            for par in fila["rangos"].split():
                p, r = par.split(":")
                if int(r) <= k:
                    aciertos[(fila["consulta"], p)] = aciertos.get((fila["consulta"], p), 0) + int(fila["relevante"])
    if sin_juzgar:
        print(f"AVISO: {sin_juzgar} documentos sin juzgar; los resultados están incompletos.", file=sys.stderr)
    consultas = leer_consultas()
    print(f"| Consulta | " + " | ".join(POLITICAS) + " |")
    print("|---|" + "---|" * len(POLITICAS))
    for qid, texto, _ in consultas:
        print(f"| {qid} {texto} | " + " | ".join(f"{aciertos.get((qid, p), 0) / k:.1f}" for p in POLITICAS) + " |")
    print("| **Promedio P@%d** | " % k + " | ".join(
        f"**{sum(aciertos.get((q[0], p), 0) for q in consultas) / (k * len(consultas)):.2f}**" for p in POLITICAS) + " |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paso", choices=["pool", "resultados"])
    ap.add_argument("-k", type=int, default=10)
    args = ap.parse_args()
    pool(args.k) if args.paso == "pool" else resultados(args.k)
