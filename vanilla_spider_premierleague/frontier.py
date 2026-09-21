from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from common.config import Config
from common.store import Store

_REFILL_PER_HOST = 200


@dataclass(slots=True)
class Task:
    url: str
    host: str
    depth: int
    priority: float


class Frontier:
    """Planificador de la cola de arañado.

    Mantiene una cola por host en memoria (respaldada por SQLite) y entrega
    tareas solo cuando el host cumple su delay de cortesia y no excede el
    maximo de descargas concurrentes permitidas para ese host.
    """

    def __init__(self, store: Store, cfg: Config, delay_for):
        self._store = store
        self._cfg = cfg
        self._delay_for = delay_for

        self._cv = threading.Condition()
        self._refill_lock = threading.Lock()
        self._queues: dict[str, deque[Task]] = {}
        self._ready_at: dict[str, float] = {}
        self._inflight: dict[str, int] = {}
        self._delays: dict[str, float] = {}
        self._buffered = 0
        self._active = 0
        self._closed = False

    # entrada

    def add(self, rows: list[tuple[str, str, int, float, str | None]]) -> int:
        added = self._store.add_urls(rows)
        if added:
            with self._cv:
                self._cv.notify_all()
        return added

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    # salida

    def next(self) -> Task | None:
        """Bloquea hasta que haya una tarea lista, o devuelve None al terminar."""
        while True:
            with self._cv:
                if self._closed:
                    return None
                task = self._pick()
                if task is not None:
                    return task
                empty = self._buffered == 0
                wait = self._time_to_ready()

            if empty:
                if self._refill():
                    continue
                with self._cv:
                    if self._buffered == 0 and self._active == 0 and not self._closed:
                        self._closed = True
                        self._cv.notify_all()
                        return None

            with self._cv:
                self._cv.wait(timeout=min(wait, 0.5))

    def complete(self, task: Task) -> None:
        with self._cv:
            self._active -= 1
            self._inflight[task.host] -= 1
            self._cv.notify_all()

    # internas

    def _pick(self) -> Task | None:
        """Requiere self._cv. Elige el host listo con la tarea de mayor prioridad."""
        now = time.monotonic()
        best_host, best_priority = None, float("-inf")

        for host, queue in self._queues.items():
            if not queue:
                continue
            if self._inflight.get(host, 0) >= self._cfg.per_domain_concurrency:
                continue
            if self._ready_at.get(host, 0.0) > now:
                continue
            if queue[0].priority > best_priority:
                best_host, best_priority = host, queue[0].priority

        if best_host is None:
            return None

        task = self._queues[best_host].popleft()
        self._buffered -= 1
        self._active += 1
        self._inflight[best_host] = self._inflight.get(best_host, 0) + 1
        self._ready_at[best_host] = now + self._delays.get(
            best_host, self._cfg.per_domain_delay
        )
        return task

    def _time_to_ready(self) -> float:
        """Requiere self._cv. Segundos hasta que algun host vuelva a estar listo."""
        now = time.monotonic()
        waits = [
            self._ready_at[host] - now
            for host, queue in self._queues.items()
            if queue and self._ready_at.get(host, 0.0) > now
        ]
        return max(0.0, min(waits)) if waits else 0.5

    def _refill(self) -> int:
        """Trae de SQLite un lote balanceado por host. Serializado entre hilos."""
        with self._refill_lock:
            with self._cv:
                if self._buffered > 0:
                    return self._buffered
            batch = self._store.claim(_REFILL_PER_HOST)
            if not batch:
                return 0

            by_host: dict[str, list[Task]] = {}
            for url, host, depth, priority in batch:
                by_host.setdefault(host, []).append(Task(url, host, depth, priority))

            # El delay de robots.txt se resuelve aqui (fuera del lock de la cola)
            # porque implica una peticion de red la primera vez que se ve el host.
            for host, tasks in by_host.items():
                if host not in self._delays:
                    self._delays[host] = self._delay_for(tasks[0].url)

            with self._cv:
                for host, tasks in by_host.items():
                    tasks.sort(key=lambda t: t.priority, reverse=True)
                    self._queues.setdefault(host, deque()).extend(tasks)
                self._buffered += len(batch)
                self._cv.notify_all()
            return len(batch)
