from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from . import dedup
from .config import Config

PENDING, INFLIGHT, DONE, FAILED, SKIPPED = 0, 1, 2, 3, 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier (
    url         TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    depth       INTEGER NOT NULL,
    priority    REAL NOT NULL,
    status      INTEGER NOT NULL DEFAULT 0,
    source_url  TEXT,
    discovered  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_frontier_claim ON frontier(status, host, priority DESC);

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL UNIQUE,
    path          TEXT NOT NULL,
    host          TEXT NOT NULL,
    title         TEXT,
    published_at  TEXT,
    fetched_at    REAL NOT NULL,
    depth         INTEGER NOT NULL,
    source_url    TEXT,
    http_status   INTEGER,
    elapsed_ms    INTEGER,
    raw_bytes     INTEGER,
    text_bytes    INTEGER,
    word_count    INTEGER,
    topic_hits    INTEGER,
    sha256        TEXT NOT NULL UNIQUE,
    simhash       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_documents_host ON documents(host);

CREATE TABLE IF NOT EXISTS simhash_bands (
    band    INTEGER NOT NULL,
    value   INTEGER NOT NULL,
    doc_id  INTEGER NOT NULL,
    PRIMARY KEY (band, value, doc_id)
) WITHOUT ROWID;
"""


class DuplicateError(Exception):
    """El contenido ya existe en el repositorio (politica 5)."""


class Store:
    """Metadatos y frontera en SQLite; documentos como texto plano en disco."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._local = threading.local()
        self._write_lock = threading.Lock()
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.cfg.db_path, timeout=60, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA cache_size=-64000")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = self._connect()
        return conn

    # frontera

    def add_urls(self, rows: list[tuple[str, str, int, float, str | None]]) -> int:
        """INSERT OR IGNORE: el PRIMARY KEY sobre url es el filtro de URLs ya vistas."""
        if not rows:
            return 0
        now = time.time()
        with self._write_lock:
            cursor = self.conn.executemany(
                "INSERT OR IGNORE INTO frontier"
                " (url, host, depth, priority, source_url, discovered)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [(*row, now) for row in rows],
            )
        return cursor.rowcount

    def claim(self, host_limit: int) -> list[tuple[str, str, int, float]]:
        """Reclama un lote balanceado por host y lo marca INFLIGHT.

        El balanceo por host materializa la cortesia a nivel de planificacion:
        ningun sitio domina la cola aunque tenga mas URLs pendientes.
        """
        with self._write_lock:
            conn = self.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                hosts = [r[0] for r in conn.execute(
                    "SELECT DISTINCT host FROM frontier WHERE status = ?", (PENDING,)
                )]
                batch: list[tuple[str, str, int, float]] = []
                for host in hosts:
                    batch.extend(conn.execute(
                        "SELECT url, host, depth, priority FROM frontier"
                        " WHERE status = ? AND host = ?"
                        " ORDER BY priority DESC LIMIT ?",
                        (PENDING, host, host_limit),
                    ))
                if batch:
                    conn.executemany(
                        "UPDATE frontier SET status = ? WHERE url = ?",
                        [(INFLIGHT, row[0]) for row in batch],
                    )
                conn.execute("COMMIT")
                return batch
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def finish(self, url: str, status: int) -> None:
        with self._write_lock:
            self.conn.execute("UPDATE frontier SET status = ? WHERE url = ?", (status, url))

    def requeue_inflight(self) -> int:
        """Al reanudar, las URLs que quedaron en vuelo vuelven a la cola."""
        with self._write_lock:
            cursor = self.conn.execute(
                "UPDATE frontier SET status = ? WHERE status = ?", (PENDING, INFLIGHT)
            )
        return cursor.rowcount

    def pending_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM frontier WHERE status = ?", (PENDING,)
        ).fetchone()[0]

    # documentos

    def is_near_duplicate(self, value: int) -> bool:
        """Politica 5: candidatos por banda + verificacion por distancia Hamming."""
        if not value:
            return False
        seen: set[int] = set()
        for band, band_value in dedup.bands(value):
            for (doc_simhash,) in self.conn.execute(
                "SELECT d.simhash FROM simhash_bands b"
                " JOIN documents d ON d.id = b.doc_id"
                " WHERE b.band = ? AND b.value = ? LIMIT 200",
                (band, band_value),
            ):
                stored = dedup.from_signed(doc_simhash)
                if stored in seen:
                    continue
                seen.add(stored)
                if dedup.hamming(stored, value) <= self.cfg.near_dup_distance:
                    return True
        return False

    def save(self, meta: dict, text: str, simhash_value: int) -> int:
        """Escribe el .txt y registra sus metadatos de forma atomica."""
        sha = meta["sha256"]
        rel_path = Path(meta["host"]) / sha[:2] / f"{sha}.txt"
        target = self.cfg.repo_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        signed = dedup.to_signed(simhash_value)
        with self._write_lock:
            conn = self.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "INSERT INTO documents (url, path, host, title, published_at,"
                    " fetched_at, depth, source_url, http_status, elapsed_ms, raw_bytes,"
                    " text_bytes, word_count, topic_hits, sha256, simhash)"
                    " VALUES (:url, :path, :host, :title, :published_at, :fetched_at,"
                    " :depth, :source_url, :http_status, :elapsed_ms, :raw_bytes,"
                    " :text_bytes, :word_count, :topic_hits, :sha256, :simhash)",
                    {**meta, "path": str(rel_path), "simhash": signed},
                )
                doc_id = cursor.lastrowid
                if simhash_value:
                    conn.executemany(
                        "INSERT OR IGNORE INTO simhash_bands (band, value, doc_id)"
                        " VALUES (?, ?, ?)",
                        [(band, value, doc_id) for band, value in dedup.bands(simhash_value)],
                    )
                conn.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK")
                raise DuplicateError(str(exc)) from exc
            except Exception:
                conn.execute("ROLLBACK")
                raise

        target.write_text(text, encoding="utf-8")
        return doc_id

    def totals(self) -> tuple[int, int]:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(text_bytes), 0) FROM documents"
        ).fetchone()
        return row[0], row[1]

    def per_host_counts(self) -> list[tuple[str, int, int]]:
        return list(self.conn.execute(
            "SELECT host, COUNT(*), COALESCE(SUM(text_bytes), 0) FROM documents"
            " GROUP BY host ORDER BY 2 DESC"
        ))
