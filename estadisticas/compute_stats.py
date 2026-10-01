"""Calcula estadisticas globales del repositorio (palabras distintas y su
frecuencia) leyendo todos los documentos de texto plano en paralelo.

Uso: python estadisticas/compute_stats.py
Salida: estadisticas/word_counter.pkl (Counter completo, para reusar sin
recalcular) y estadisticas/resumen.json (numeros para el documento).
"""
from __future__ import annotations

import json
import pickle
import re
import sqlite3
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "crawl.db"
_REPO_DIR = _ROOT / "repo"
_OUT_DIR = Path(__file__).resolve().parent

# Misma definicion de "palabra" que usa common/extract.py al calcular topic_hits,
# para que las cifras sean consistentes con el resto del proyecto.
_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.I)

_CHUNK_SIZE = 500


def _count_file(path_str: str) -> Counter:
    try:
        text = Path(path_str).read_text(encoding="utf-8")
    except OSError:
        return Counter()
    return Counter(_WORD_RE.findall(text.lower()))


def main() -> None:
    conn = sqlite3.connect(_DB_PATH)
    paths = [str(_REPO_DIR / row[0]) for row in conn.execute("SELECT path FROM documents")]
    total_docs = len(paths)
    conn.close()

    print(f"Procesando {total_docs:,} documentos...", flush=True)
    started = time.time()
    global_counter: Counter[str] = Counter()
    processed = 0

    with Pool() as pool:
        for chunk_counter in pool.imap_unordered(_count_file, paths, chunksize=_CHUNK_SIZE):
            global_counter.update(chunk_counter)
            processed += 1
            if processed % 50_000 == 0:
                elapsed = time.time() - started
                rate = processed / elapsed
                eta = (total_docs - processed) / rate
                print(f"  {processed:,}/{total_docs:,} docs "
                      f"({rate:.0f} docs/s, ETA {eta / 60:.1f} min)", flush=True)

    _OUT_DIR.mkdir(exist_ok=True)
    with open(_OUT_DIR / "word_counter.pkl", "wb") as f:
        pickle.dump(global_counter, f)

    total_words = sum(global_counter.values())
    distinct_words = len(global_counter)
    summary = {
        "documentos": total_docs,
        "palabras_totales": total_words,
        "palabras_distintas": distinct_words,
        "top_50": global_counter.most_common(50),
    }
    with open(_OUT_DIR / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - started
    print(f"\nListo en {elapsed / 60:.1f} min.")
    print(f"Palabras totales: {total_words:,}")
    print(f"Palabras distintas: {distinct_words:,}")


if __name__ == "__main__":
    main()
