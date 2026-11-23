"""Prepara las fechas de publicación para la búsqueda por fecha:  python -m web_app.preparar_fechas

Las páginas guardan su fecha en formatos muy distintos ('2026-09-21T05:00:00Z', '20 Sept 2026', 'Monday 21st September
2026 7:44 PM', ...). Este programa las lee de data/crawl.db, las convierte a un número de día y las deja en
web_app/datos/fechas.bin, ordenadas por hash, para que Lucene y el índice propio puedan filtrar y ordenar por fecha sin
consultar la base de datos en cada búsqueda. Se hace una sola vez (tarda un par de minutos) y la aplicación lo corre
sola si el archivo no existe.

Formato de fechas.bin (little-endian):  "PFEC" | versión (uint32) | N (uint32) | N x ( prefijo del hash (int64) | día (uint16) )
  - prefijo: los primeros 8 bytes del sha256 del documento, leídos como int64 con signo; las entradas van ordenadas por él.
  - día: días desde el 2000-01-01, más 1 (0 significaría "sin fecha" y no se guarda).
Una fecha se descarta si es anterior al año 2000 o posterior al día en que se bajó la página (más 2 días), porque entonces
es la fecha de un evento futuro y no de publicación.
"""
import json
import re
import sqlite3
import struct
import sys
import time
from datetime import date, datetime, timezone

from dateutil import parser as parser_fechas

from . import config

BASE = date(2000, 1, 1)
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
FORMATO_VERSION = 1


def fecha_de_texto(crudo: str):
    """La fecha (datetime.date) de un texto como los que guardan las páginas, o None. Las fechas ISO (AAAA-MM-DD) se leen
    tal cual: darle prioridad al día sobre el mes, como en '10/02/2026', las daría vuelta ('2026-02-10' -> 10 de febrero)."""
    m = _ISO.match(crudo)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        return parser_fechas.parse(crudo, fuzzy=True, dayfirst=True, default=datetime(1900, 1, 1)).date()
    except (ValueError, OverflowError):
        return None


def preparar() -> dict:
    t0 = time.time()
    con = sqlite3.connect(f"file:{config.CRAWL_DB.as_posix()}?mode=ro", uri=True)
    entradas, vistas = [], set()
    total = descartadas = 0
    for sha, publicado, bajado in con.execute("SELECT sha256, published_at, fetched_at FROM documents"):
        total += 1
        if not publicado:
            continue
        f = fecha_de_texto(publicado)
        limite = datetime.fromtimestamp(bajado, timezone.utc).date().toordinal() + 2 if bajado else None
        if f is None or f.year < 2000 or (limite and f.toordinal() > limite):
            descartadas += 1
            continue
        prefijo = struct.unpack(">q", bytes.fromhex(sha)[:8])[0]
        if prefijo in vistas:          # dos hashes con el mismo prefijo de 8 bytes: prácticamente imposible
            continue
        vistas.add(prefijo)
        entradas.append((prefijo, (f - BASE).days + 1))
    entradas.sort()
    config.FECHAS_BIN.parent.mkdir(parents=True, exist_ok=True)
    with open(config.FECHAS_BIN, "wb") as f:
        f.write(b"PFEC" + struct.pack("<II", FORMATO_VERSION, len(entradas)))
        for prefijo, dia in entradas:
            f.write(struct.pack("<qH", prefijo, dia))
    dias = [d for _, d in entradas]
    meta = {"con_fecha": len(entradas), "documentos": total, "descartadas": descartadas,
            "minima": (BASE.fromordinal(BASE.toordinal() + min(dias) - 1)).isoformat() if dias else None,
            "maxima": (BASE.fromordinal(BASE.toordinal() + max(dias) - 1)).isoformat() if dias else None,
            "segundos": round(time.time() - t0, 1)}
    config.FECHAS_META.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


if __name__ == "__main__":
    print(json.dumps(preparar(), indent=1))
    sys.exit(0)
