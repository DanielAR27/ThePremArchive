"""Genera interfaz/src/mock/datos.json a partir de los resultados reales de la entrega 2.

Fuentes (todas versionadas en el repositorio):
  - estadisticas/evaluacion/resultados_busqueda.json  -> top 10 de cada motor y política
  - estadisticas/evaluacion/pool_juzgado.csv          -> título, sitio, extracto y juicio de cada documento
  - estadisticas/rendimiento_consultas.json           -> tiempo de cada consulta
  - estadisticas/estadisticas_extra.json              -> tamaño de la colección por política
  - indexacion/config/datos/consultas.txt             -> las 12 consultas de prueba

Uso (desde la raíz del repositorio o desde interfaz/):
    python interfaz/herramientas/generar_mock.py
"""
import csv
import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "interfaz" / "src" / "mock" / "datos.json"

POLITICAS = {
    "A": ("Minimal", "Tokenization and lowercase only. The baseline."),
    "B": ("Intermediate", "Possessives, accents, stopwords, dates and numbers."),
    "C": ("Full", "B plus lemmatization, synonyms and known entities (clubs, competitions)."),
    "D": ("Stopwords only", "A plus stopword removal."),
    "E": ("Full, stemmed", "Same as C, with Porter stemming instead of lemmatization."),
    "F": ("Synonyms", "B plus football-domain synonyms."),
}
MOTORES = {"manual": "Own index", "lucene": "Apache Lucene"}


def leer_consultas():
    consultas = []
    for linea in (RAIZ / "indexacion/config/datos/consultas.txt").read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.startswith("#"):
            continue
        qid, texto, _proposito = (p.strip() for p in linea.split("|"))
        consultas.append({"id": qid, "text": texto})
    return consultas


def fecha_pool():
    """Fecha del último commit del pool juzgado (YYYY-MM-DD), o None fuera de git."""
    try:
        salida = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", "estadisticas/evaluacion/pool_juzgado.csv"],
            cwd=RAIZ, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return salida or None
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    resultados = json.loads((RAIZ / "estadisticas/evaluacion/resultados_busqueda.json").read_text(encoding="utf-8"))
    tiempos = json.loads((RAIZ / "estadisticas/rendimiento_consultas.json").read_text(encoding="utf-8"))
    extra = json.loads((RAIZ / "estadisticas/estadisticas_extra.json").read_text(encoding="utf-8"))

    docs, juicios = {}, []
    with open(RAIZ / "estadisticas/evaluacion/pool_juzgado.csv", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            docs[fila["doc"]] = {
                "host": fila["host"],
                "title": fila["titulo"].strip(),
                "snippet": " ".join(fila["extracto"].split()),
            }
            juicios.append({
                "queryId": fila["consulta"],
                "doc": fila["doc"],
                "judgment": "relevant" if fila["relevante"] == "1" else "not_relevant",
                "evaluator": "Project 2 pool",
            })

    rankings = {}
    for motor, por_politica in resultados.items():
        for politica, por_consulta in por_politica.items():
            rankings[f"{motor}:{politica}"] = {
                qid: [d for d in lista if d in docs] for qid, lista in por_consulta.items()
            }

    clave_tiempo = {"manual": "propio", "lucene": "lucene"}
    timings = {}
    for politica, por_motor in tiempos.items():
        for motor, clave in clave_tiempo.items():
            if clave in por_motor:
                timings[f"{motor}:{politica}"] = {
                    q: round(ms, 1) for q, ms in por_motor[clave]["consultas_ms"].items()
                }

    datos = {
        "note": "Generated from project 2 results. Mock data until the search server exists.",
        "collection": {
            "documents": extra["A"]["documentos"],
            "crawled": 1440556,
            "hosts": sorted({d["host"] for d in docs.values()}),
            "termsByPolicy": {p: extra[p]["terminos"] for p in POLITICAS if p in extra},
        },
        "engines": [{"id": k, "label": v} for k, v in MOTORES.items()],
        "policies": [{"id": k, "label": v[0], "description": v[1]} for k, v in POLITICAS.items()],
        "default": {"engine": "lucene", "policy": "C"},
        "queries": leer_consultas(),
        "docs": docs,
        "rankings": rankings,
        "timings": timings,
        "baselineJudgments": juicios,
        "baselineDate": fecha_pool(),
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{SALIDA.relative_to(RAIZ)}: {len(docs)} documentos, {len(juicios)} juicios, {len(rankings)} rankings")


if __name__ == "__main__":
    main()
