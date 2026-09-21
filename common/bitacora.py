from __future__ import annotations

import json
import threading
import time


class Bitacora:
    """Registro JSONL de cada URL visitada: evidencia del recorrido de la araña.

    La usan ambos arañadores (propio y Scrapy), cada uno con su propio archivo
    (`logs/bitacora.jsonl` y `logs/bitacora_scrapy.jsonl`).
    """

    def __init__(self, path, buffer_size: int = 64):
        self._file = open(path, "a", encoding="utf-8", buffering=1 << 16)
        self._lock = threading.Lock()
        self._buffer_size = buffer_size
        self._since_flush = 0

    def write(self, **entry) -> None:
        line = json.dumps({"ts": round(time.time(), 3), **entry}, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._since_flush += 1
            if self._since_flush >= self._buffer_size:
                self._file.flush()
                self._since_flush = 0

    def close(self) -> None:
        with self._lock:
            self._file.flush()
            self._file.close()


def human_bytes(size: float) -> str:
    if size < 1024**2:
        return f"{size / 1024:.0f}KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f}MB"
    return f"{size / 1024**3:.2f}GB"


def hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
