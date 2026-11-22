"""Base de datos de uso (SQLite): quién buscó qué, qué abrió y qué marcó como relevante. De aquí salen las
métricas y las estadísticas de uso del documento."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS consultas (
    id           INTEGER PRIMARY KEY,
    sesion       TEXT NOT NULL,
    texto        TEXT NOT NULL,
    modo         TEXT NOT NULL,          -- 'search' (solo buscar) o 'evaluate' (marcar relevancia)
    motor        TEXT,                   -- 'lucene' o 'manual'
    terminos     TEXT,                   -- cómo quedó la consulta después de normalizarla
    tiempo_ms    REAL,
    n_resultados INTEGER,
    creado       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clics (
    id           INTEGER PRIMARY KEY,
    consulta_id  INTEGER NOT NULL REFERENCES consultas(id),
    hash         TEXT NOT NULL,
    puesto       INTEGER NOT NULL,
    creado       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS juicios (
    id           INTEGER PRIMARY KEY,
    consulta_id  INTEGER NOT NULL REFERENCES consultas(id),
    sesion       TEXT NOT NULL,
    hash         TEXT NOT NULL,
    puesto       INTEGER NOT NULL,
    relevante    INTEGER NOT NULL,       -- 1 = relevante, 0 = no, -1 = no pudo decidirlo
    creado       TEXT NOT NULL,
    UNIQUE (consulta_id, hash)
);
CREATE TABLE IF NOT EXISTS mostrados (
    consulta_id  INTEGER NOT NULL REFERENCES consultas(id),
    puesto       INTEGER NOT NULL,
    hash         TEXT NOT NULL,
    PRIMARY KEY (consulta_id, hash)
);
CREATE TABLE IF NOT EXISTS satisfaccion (
    consulta_id  INTEGER PRIMARY KEY REFERENCES consultas(id),
    valor        INTEGER NOT NULL,       -- 2 = sí cubrió lo que buscaba, 1 = en parte, 0 = no
    creado       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consultas_sesion ON consultas(sesion);
CREATE INDEX IF NOT EXISTS idx_juicios_consulta ON juicios(consulta_id);
"""


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def conexion():
    config.USO_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.USO_DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conexion() as con:
        con.executescript(ESQUEMA)


def registrar_consulta(sesion: str, texto: str, modo: str, motor: str, terminos, tiempo_ms: float, n: int) -> int:
    with conexion() as con:
        cur = con.execute(
            "INSERT INTO consultas (sesion, texto, modo, motor, terminos, tiempo_ms, n_resultados, creado) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (sesion, texto, modo, motor, " ".join(terminos), tiempo_ms, n, ahora()))
        return cur.lastrowid


def registrar_clic(consulta_id: int, hash_doc: str, puesto: int):
    with conexion() as con:
        con.execute("INSERT INTO clics (consulta_id, hash, puesto, creado) VALUES (?,?,?,?)",
                    (consulta_id, hash_doc, puesto, ahora()))


def registrar_mostrados(consulta_id: int, resultados):
    """Guarda qué documentos se le mostraron a la persona en una consulta de evaluación: [(puesto, hash)]."""
    with conexion() as con:
        con.executemany("INSERT OR IGNORE INTO mostrados (consulta_id, puesto, hash) VALUES (?,?,?)",
                        [(consulta_id, puesto, h) for puesto, h in resultados])


def consulta_de(sesion: str, consulta_id: int):
    """La consulta de evaluación si existe y es de esta sesión; si no, None."""
    with conexion() as con:
        return con.execute("SELECT * FROM consultas WHERE id=? AND sesion=? AND modo='evaluate'",
                           (consulta_id, sesion)).fetchone()


def guardar_juicios(consulta_id: int, sesion: str, marcas: dict) -> int:
    """marcas: {hash: 1 | 0 | -1}. Solo se aceptan documentos que se le mostraron. Devuelve cuántos se guardaron."""
    with conexion() as con:
        mostrados = {fila["hash"]: fila["puesto"] for fila in
                     con.execute("SELECT hash, puesto FROM mostrados WHERE consulta_id=?", (consulta_id,))}
        guardados = 0
        for h, valor in marcas.items():
            if h in mostrados and valor in (1, 0, -1):
                con.execute("INSERT INTO juicios (consulta_id, sesion, hash, puesto, relevante, creado) VALUES (?,?,?,?,?,?) "
                            "ON CONFLICT(consulta_id, hash) DO UPDATE SET relevante=excluded.relevante, creado=excluded.creado",
                            (consulta_id, sesion, h, mostrados[h], valor, ahora()))
                guardados += 1
        return guardados


def guardar_satisfaccion(consulta_id: int, valor: int):
    if valor in (0, 1, 2):
        with conexion() as con:
            con.execute("INSERT INTO satisfaccion (consulta_id, valor, creado) VALUES (?,?,?) "
                        "ON CONFLICT(consulta_id) DO UPDATE SET valor=excluded.valor, creado=excluded.creado",
                        (consulta_id, valor, ahora()))


def contar_evaluadas(sesion: str) -> int:
    """Consultas distintas que esta sesión ya evaluó (con al menos una marca)."""
    with conexion() as con:
        return con.execute("SELECT COUNT(DISTINCT consulta_id) FROM juicios WHERE sesion=?", (sesion,)).fetchone()[0]
