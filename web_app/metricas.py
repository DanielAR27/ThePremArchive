"""Métricas de evaluación y estadísticas de uso.

Las métricas siguen las definiciones de Manning, Raghavan y Schütze (2008, cap. 8) y son las mismas de
interfaz/src/lib/metricas.js: se calculan sobre los 10 primeros resultados, los documentos sin juicio cuentan como no
relevantes y "unsure" cuenta como juzgado pero no relevante. Para cada motor y política se usan los 10 primeros
resultados de las 12 consultas de prueba (los del Proyecto 2) y los juicios de relevancia, que valen para cualquier
motor porque se juzga el documento y no el motor (método del pool).
"""
import csv
import functools
import json
import math
import statistics
from collections import Counter, defaultdict

from . import config, db

CORTE = 10
BASE_P2 = "Project 2 pool"


# --- datos de referencia ---------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def consultas_de_prueba() -> list:
    """[{'id': 'q01', 'text': 'haaland goals'}] de indexacion/config/datos/consultas.txt."""
    salida = []
    for linea in (config.CONFIG_DIR / "datos" / "consultas.txt").read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            campos = [c.strip() for c in linea.split("|")]
            salida.append({"id": campos[0], "text": campos[1]})
    return salida


@functools.lru_cache(maxsize=1)
def rankings_p2() -> dict:
    """{'lucene:C': {'q01': [hash, ...]}}: los 10 primeros de cada motor y política en el Proyecto 2."""
    datos = json.loads(config.RANKINGS_P2.read_text(encoding="utf-8"))
    return {f"{motor}:{politica}": consultas
            for motor, politicas in datos.items() for politica, consultas in politicas.items()}


@functools.lru_cache(maxsize=1)
def juicios_p2() -> list:
    """Los juicios de relevancia del pool del Proyecto 2, en el formato de la API."""
    salida = []
    with open(config.JUICIOS_P2, encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["relevante"].strip() in ("0", "1"):
                salida.append({"queryId": fila["consulta"], "doc": fila["doc"], "evaluator": BASE_P2,
                               "judgment": "relevant" if fila["relevante"].strip() == "1" else "not_relevant"})
    return salida


# --- una lista de resultados -----------------------------------------------------------------------------------
def _media(valores):
    valores = list(valores)
    return sum(valores) / len(valores) if valores else 0.0


def puntuar(rel, relevantes_conocidos):
    """rel: 1 / 0 / None por posición. Devuelve P@5, P@10, RR, AP, nDCG@10 y cuántos tenían juicio."""
    top = rel[:CORTE]
    acierto = [1 if r == 1 else 0 for r in top]
    p_en = lambda k: sum(acierto[:k]) / k

    primero = acierto.index(1) if 1 in acierto else -1
    rr = 0.0 if primero == -1 else 1 / (primero + 1)

    encontrados, suma = 0, 0.0
    for i, h in enumerate(acierto):
        if h:
            encontrados += 1
            suma += encontrados / (i + 1)
    ap = suma / min(relevantes_conocidos, CORTE) if relevantes_conocidos else 0.0

    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(acierto))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(relevantes_conocidos, CORTE)))
    ndcg = dcg / ideal if ideal else 0.0
    return {"p5": p_en(5), "p10": p_en(10), "rr": rr, "ap": ap, "ndcg10": ndcg,
            "judged": sum(1 for r in top if r is not None)}


def calcular_metricas(motor: str, politica: str, incluir_p2: bool = True) -> dict:
    """Lo que devuelve GET /api/metrics."""
    vivos = [j for j in db.listar_juicios() if j["queryId"]]
    juicios = (juicios_p2() if incluir_p2 else []) + vivos
    relevancia = {}                                  # (consulta, documento) -> el último juicio
    for j in juicios:
        relevancia[(j["queryId"], j["doc"])] = j["judgment"]
    conocidos = Counter(q for (q, _), v in relevancia.items() if v == "relevant")

    consultas, rankings = consultas_de_prueba(), rankings_p2()

    def puntuar_config(clave):
        filas = []
        for q in consultas:
            docs = rankings.get(clave, {}).get(q["id"], [])
            rel = []
            for d in docs[:CORTE]:
                v = relevancia.get((q["id"], d))
                rel.append(None if v is None else (1 if v == "relevant" else 0))
            filas.append({"id": q["id"], "text": q["text"], "relevantAtRank": rel,
                          **puntuar(rel, conocidos.get(q["id"], 0))})
        return filas

    def resumir(filas):
        return {"p5": _media(f["p5"] for f in filas), "p10": _media(f["p10"] for f in filas),
                "mrr": _media(f["rr"] for f in filas), "map": _media(f["ap"] for f in filas),
                "ndcg10": _media(f["ndcg10"] for f in filas)}

    por_consulta = puntuar_config(f"{motor}:{politica}")
    por_config = []
    for clave in sorted(rankings):
        m, p = clave.split(":")
        por_config.append({"engine": m, "policy": p, **resumir(puntuar_config(clave))})

    por_dia = Counter(j["judgedAt"][:10] for j in vivos if j.get("judgedAt"))
    return {
        "engine": motor, "policy": politica,
        "summary": {"queries": len(consultas), "judged": len(relevancia),
                    "evaluators": len({j["evaluator"] for j in juicios}), **resumir(por_consulta)},
        "perQuery": por_consulta,
        "byConfig": por_config,
        "activity": [{"date": d, "judgments": n} for d, n in sorted(por_dia.items())],
        "baseline": ({"label": BASE_P2, "judgments": len(juicios_p2()),
                      "relevant": sum(1 for j in juicios_p2() if j["judgment"] == "relevant"),
                      "date": config.FECHA_P2} if incluir_p2 else None),
    }


# --- uso -------------------------------------------------------------------------------------------------------
def percentil(valores, q):
    if not valores:
        return None
    valores = sorted(valores)
    return valores[min(len(valores) - 1, int(round(q * (len(valores) - 1))))]


def estadisticas_de_uso() -> dict:
    """Búsquedas, personas y tiempos, para la sección de estadísticas de uso del documento."""
    with db.conexion() as con:
        busquedas = [dict(f) for f in con.execute("SELECT * FROM searches")]
        juicios = [dict(f) for f in con.execute("SELECT evaluator, judged_at FROM judgments")]
    tiempos = [b["took_ms"] for b in busquedas]
    por_dia = defaultdict(int)
    for b in busquedas:
        por_dia[b["created_at"][:10]] += 1
    por_config = defaultdict(list)
    for b in busquedas:
        por_config[f"{b['engine']}:{b['policy']}"].append(b["took_ms"])
    return {
        "searches": len(busquedas),
        "people": len({b["session"] for b in busquedas if b["session"]}),
        "evaluators": len({j["evaluator"] for j in juicios}),
        "judgments": len(juicios),
        "withoutResults": sum(1 for b in busquedas if b["total"] == 0),
        "withSiteFilter": sum(1 for b in busquedas if b["site"]),
        "withDateFilter": sum(1 for b in busquedas if b.get("date_from") or b.get("date_to")),
        "bySort": dict(Counter(b.get("sort") or "relevance" for b in busquedas)),
        "tookMs": {"median": statistics.median(tiempos) if tiempos else None, "p95": percentil(tiempos, 0.95),
                   "max": max(tiempos) if tiempos else None},
        "byConfig": [{"config": c, "searches": len(v), "medianMs": statistics.median(v)} for c, v in sorted(por_config.items())],
        "perDay": [{"date": d, "searches": n} for d, n in sorted(por_dia.items())],
        "topQueries": [{"query": q, "times": n} for q, n in
                       Counter(db.normalizar(b["query"]) for b in busquedas).most_common(10)],
    }


def exportar_csv(que: str) -> str:
    """Los datos en bruto, para analizarlos aparte (por ejemplo, para las conclusiones del documento)."""
    import io
    tablas = {"judgments": "SELECT * FROM judgments ORDER BY id", "searches": "SELECT * FROM searches ORDER BY id"}
    if que not in tablas:
        raise KeyError(que)
    with db.conexion() as con:
        cursor = con.execute(tablas[que])
        salida = io.StringIO()
        escritor = csv.writer(salida)
        escritor.writerow([d[0] for d in cursor.description])
        escritor.writerows(cursor.fetchall())
    return salida.getvalue()
