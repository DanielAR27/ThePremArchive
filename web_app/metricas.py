"""Métricas a partir de lo que hicieron las personas (uso.db): calidad de la búsqueda (precisión, MRR, nDCG, necesidad
de información cubierta), uso (consultas, clics) y rendimiento (tiempo de respuesta). Todas se calculan al pedirlas,
así que la página siempre muestra los datos al día."""
import csv
import io
import math
import statistics
from collections import Counter, defaultdict

from . import config, db


# --- medidas de una consulta evaluada ------------------------------------------------------------------------
def _medidas(marcas):
    """marcas: [(puesto, relevante)] solo con 1 o 0, de los resultados que la persona pudo juzgar."""
    marcas = sorted(marcas)
    if not marcas:
        return None
    relevantes = [rel for _, rel in marcas]
    precision = sum(relevantes) / len(relevantes)
    primero = next((puesto for puesto, rel in marcas if rel == 1), None)
    mrr = 1.0 / primero if primero else 0.0
    dcg = sum(rel / math.log2(puesto + 1) for puesto, rel in marcas)
    ideal = sum(1 / math.log2(i + 2) for i in range(sum(relevantes)))
    ndcg = dcg / ideal if ideal else 0.0
    return {"p10": precision, "mrr": mrr, "ndcg": ndcg, "juzgados": len(marcas), "relevantes": sum(relevantes)}


def _media(valores):
    valores = list(valores)
    return sum(valores) / len(valores) if valores else None


def _percentil(valores, q):
    if not valores:
        return None
    valores = sorted(valores)
    return valores[min(len(valores) - 1, int(round(q * (len(valores) - 1))))]


def _kappa(pares):
    """Acuerdo entre dos personas que juzgaron lo mismo: porcentaje de acuerdo y kappa de Cohen."""
    n = len(pares)
    if n == 0:
        return None, None
    acuerdo = sum(1 for a, b in pares if a == b) / n
    pa = sum(a for a, _ in pares) / n
    pb = sum(b for _, b in pares) / n
    esperado = pa * pb + (1 - pa) * (1 - pb)
    kappa = (acuerdo - esperado) / (1 - esperado) if esperado < 1 else None
    return acuerdo, kappa


def calcular() -> dict:
    with db.conexion() as con:
        consultas = [dict(f) for f in con.execute("SELECT * FROM consultas")]
        juicios = [dict(f) for f in con.execute("SELECT * FROM juicios")]
        clics = [dict(f) for f in con.execute("SELECT * FROM clics")]
        satisfaccion = {f["consulta_id"]: f["valor"] for f in con.execute("SELECT * FROM satisfaccion")}

    por_id = {c["id"]: c for c in consultas}
    busquedas = [c for c in consultas if c["modo"] == "search"]
    evaluaciones = [c for c in consultas if c["modo"] == "evaluate"]

    # --- calidad -------------------------------------------------------------------------------------------
    marcas_por_consulta = defaultdict(list)
    for j in juicios:
        if j["relevante"] in (0, 1):
            marcas_por_consulta[j["consulta_id"]].append((j["puesto"], j["relevante"]))
    medidas = {cid: m for cid, marcas in marcas_por_consulta.items() if (m := _medidas(marcas))}

    precision_por_puesto = []
    for puesto in range(1, config.K_EVALUACION + 1):
        valores = [rel for marcas in marcas_por_consulta.values() for p, rel in marcas if p == puesto]
        precision_por_puesto.append({"puesto": puesto, "valor": _media(valores), "n": len(valores)})

    sat = Counter(satisfaccion.values())
    sat_total = sum(sat.values())

    # por texto de consulta (varias personas pueden calificar la misma)
    por_texto = defaultdict(list)
    for cid, m in medidas.items():
        por_texto[por_id[cid]["texto"].lower()].append((cid, m))
    tabla_consultas = []
    for texto, lista in por_texto.items():
        tabla_consultas.append({
            "consulta": texto, "evaluaciones": len(lista),
            "p10": _media(m["p10"] for _, m in lista), "mrr": _media(m["mrr"] for _, m in lista),
            "ndcg": _media(m["ndcg"] for _, m in lista),
            "satisfechas": _media(1.0 if satisfaccion.get(cid) == 2 else 0.0 for cid, _ in lista if cid in satisfaccion),
        })
    tabla_consultas.sort(key=lambda f: (-f["evaluaciones"], f["consulta"]))

    # --- acuerdo entre quienes juzgaron lo mismo -------------------------------------------------------------
    grupos = defaultdict(dict)   # (consulta en minúsculas, documento) -> {sesión: marca}
    for j in juicios:
        if j["relevante"] in (0, 1):
            grupos[(por_id[j["consulta_id"]]["texto"].lower(), j["hash"])].setdefault(j["sesion"], j["relevante"])
    pares = [tuple(list(v.values())[:2]) for v in grupos.values() if len(v) >= 2]
    acuerdo, kappa = _kappa(pares)

    # --- uso ---------------------------------------------------------------------------------------------------
    clics_busqueda = [c for c in clics if por_id.get(c["consulta_id"], {}).get("modo") == "search"]
    con_clic = {c["consulta_id"] for c in clics_busqueda}
    por_dia = defaultdict(lambda: {"search": 0, "evaluate": 0})
    for c in consultas:
        por_dia[c["creado"][:10]][c["modo"]] += 1
    clics_por_puesto = Counter(c["puesto"] for c in clics_busqueda if 1 <= c["puesto"] <= config.K_BUSQUEDA)
    mas_buscadas = Counter(c["texto"].lower() for c in consultas).most_common(10)
    sin_resultados = sum(1 for c in consultas if c["n_resultados"] == 0)

    # --- rendimiento ---------------------------------------------------------------------------------------------
    tiempos = [c["tiempo_ms"] for c in consultas if c["tiempo_ms"] is not None]
    por_motor = {m: [c["tiempo_ms"] for c in consultas if c["motor"] == m and c["tiempo_ms"] is not None]
                 for m in sorted({c["motor"] for c in consultas if c["motor"]})}

    return {
        "resumen": {
            "sesiones": len({c["sesion"] for c in consultas}),
            "busquedas": len(busquedas), "evaluaciones": len(evaluaciones),
            "consultas_evaluadas": len(medidas), "juicios": len(juicios),
            "juicios_relevantes": sum(1 for j in juicios if j["relevante"] == 1),
            "juicios_no_relevantes": sum(1 for j in juicios if j["relevante"] == 0),
            "juicios_indecisos": sum(1 for j in juicios if j["relevante"] == -1),
            "clics": len(clics_busqueda),
        },
        "calidad": {
            "p10": _media(m["p10"] for m in medidas.values()),
            "mrr": _media(m["mrr"] for m in medidas.values()),
            "ndcg": _media(m["ndcg"] for m in medidas.values()),
            "sin_relevantes": sum(1 for m in medidas.values() if m["relevantes"] == 0),
            "precision_por_puesto": precision_por_puesto,
            "satisfaccion": {"si": sat.get(2, 0), "parcial": sat.get(1, 0), "no": sat.get(0, 0), "total": sat_total},
            "necesidad_cubierta": (sat.get(2, 0) + 0.5 * sat.get(1, 0)) / sat_total if sat_total else None,
            "consultas": tabla_consultas,
            "acuerdo": {"pares": len(pares), "porcentaje": acuerdo, "kappa": kappa},
        },
        "uso": {
            "ctr": len(con_clic & {c["id"] for c in busquedas}) / len(busquedas) if busquedas else None,
            "puesto_medio_clic": _media(c["puesto"] for c in clics_busqueda if c["puesto"] > 0),
            "clics_por_puesto": [{"puesto": p, "clics": clics_por_puesto.get(p, 0)} for p in range(1, 11)],
            "por_dia": [{"dia": d, **v} for d, v in sorted(por_dia.items())],
            "mas_buscadas": [{"consulta": t, "veces": n} for t, n in mas_buscadas],
            "sin_resultados": sin_resultados,
        },
        "rendimiento": {
            "mediana": statistics.median(tiempos) if tiempos else None,
            "p95": _percentil(tiempos, 0.95), "maximo": max(tiempos) if tiempos else None,
            "por_motor": {m: {"n": len(v), "mediana": statistics.median(v)} for m, v in por_motor.items() if v},
        },
    }


def exportar_csv(que: str) -> str:
    """Los datos en bruto, para analizarlos aparte (por ejemplo para las conclusiones del documento)."""
    tablas = {"juicios": "SELECT * FROM juicios ORDER BY id", "consultas": "SELECT * FROM consultas ORDER BY id",
              "clics": "SELECT * FROM clics ORDER BY id"}
    if que not in tablas:
        raise KeyError(que)
    with db.conexion() as con:
        cursor = con.execute(tablas[que])
        salida = io.StringIO()
        escritor = csv.writer(salida)
        escritor.writerow([d[0] for d in cursor.description])
        escritor.writerows(cursor.fetchall())
    return salida.getvalue()
