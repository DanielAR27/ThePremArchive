"""Base de datos de la aplicación (SQLite): los juicios de relevancia que dan las personas y las búsquedas que hacen.
De aquí salen las métricas y las estadísticas de uso del documento."""
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    id         INTEGER PRIMARY KEY,
    grupo      TEXT NOT NULL,        -- id de la consulta de prueba, o 'libre:<consulta normalizada>' si no es de prueba
    query_id   TEXT,                 -- 'q01'... o NULL
    query      TEXT NOT NULL,
    doc        TEXT NOT NULL,        -- hash del documento
    engine     TEXT NOT NULL,        -- motor con el que se vio el resultado
    policy     TEXT NOT NULL,
    rank       INTEGER NOT NULL,
    judgment   TEXT NOT NULL CHECK (judgment IN ('relevant', 'not_relevant', 'unsure')),
    evaluator  TEXT NOT NULL,
    judged_at  TEXT NOT NULL,
    UNIQUE (grupo, doc, evaluator)   -- juzgar de nuevo lo mismo actualiza el registro en vez de duplicarlo
);
CREATE INDEX IF NOT EXISTS idx_judgments_evaluator ON judgments(evaluator);
CREATE TABLE IF NOT EXISTS searches (
    id         INTEGER PRIMARY KEY,
    session    TEXT,
    query      TEXT NOT NULL,
    engine     TEXT NOT NULL,
    policy     TEXT NOT NULL,
    site       TEXT,
    date_from  TEXT,
    date_to    TEXT,
    sort       TEXT,
    page       INTEGER NOT NULL,
    total      INTEGER NOT NULL,
    took_ms    REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_session ON searches(session);
"""


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.lower()).strip()


@contextmanager
def conexion():
    config.USO_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.USO_DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conexion() as con:
        con.executescript(ESQUEMA)
        columnas = {f["name"] for f in con.execute("PRAGMA table_info(searches)")}
        for nombre in ("date_from", "date_to", "sort"):      # bases creadas antes de la búsqueda por fecha
            if nombre not in columnas:
                con.execute(f"ALTER TABLE searches ADD COLUMN {nombre} TEXT")


# --- juicios --------------------------------------------------------------------------------------------------
def _juicio_json(f) -> dict:
    return {"id": f["id"], "queryId": f["query_id"], "query": f["query"], "doc": f["doc"], "engine": f["engine"],
            "policy": f["policy"], "rank": f["rank"], "judgment": f["judgment"], "evaluator": f["evaluator"],
            "judgedAt": f["judged_at"]}


def guardar_juicio(j: dict) -> dict:
    grupo = j["queryId"] or "libre:" + normalizar(j["query"])
    with conexion() as con:
        con.execute(
            "INSERT INTO judgments (grupo, query_id, query, doc, engine, policy, rank, judgment, evaluator, judged_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(grupo, doc, evaluator) DO UPDATE SET "
            "engine=excluded.engine, policy=excluded.policy, rank=excluded.rank, judgment=excluded.judgment, "
            "judged_at=excluded.judged_at",
            (grupo, j["queryId"], j["query"], j["doc"], j["engine"], j["policy"], j["rank"], j["judgment"],
             j["evaluator"], ahora()))
        fila = con.execute("SELECT * FROM judgments WHERE grupo=? AND doc=? AND evaluator=?",
                           (grupo, j["doc"], j["evaluator"])).fetchone()
        return _juicio_json(fila)


def listar_juicios(query_id=None, evaluador=None) -> list:
    sql, args = "SELECT * FROM judgments WHERE 1=1", []
    if query_id:
        sql += " AND query_id=?"
        args.append(query_id)
    if evaluador:
        sql += " AND evaluator=?"
        args.append(evaluador)
    with conexion() as con:
        return [_juicio_json(f) for f in con.execute(sql + " ORDER BY judged_at, id", args)]


def borrar_juicios(evaluador: str) -> int:
    with conexion() as con:
        return con.execute("DELETE FROM judgments WHERE evaluator=?", (evaluador,)).rowcount


# --- búsquedas ------------------------------------------------------------------------------------------------
def registrar_busqueda(sesion, consulta, motor, politica, sitio, pagina, total, tiempo_ms, desde="", hasta="",
                       orden="relevance"):
    with conexion() as con:
        con.execute("INSERT INTO searches (session, query, engine, policy, site, date_from, date_to, sort, page, total, "
                    "took_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sesion, consulta, motor, politica, sitio or None, desde or None, hasta or None, orden, pagina,
                     total, tiempo_ms, ahora()))
