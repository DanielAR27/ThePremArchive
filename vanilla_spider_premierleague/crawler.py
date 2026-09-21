from __future__ import annotations

import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from common import dedup, extract, urls
from common.bitacora import Bitacora, hms, human_bytes
from common.config import Config
from common.store import DONE, FAILED, SKIPPED, DuplicateError, Store

from .frontier import Frontier, Task
from .net import Net

_MAX_LINKS_PER_PAGE = 300


class Crawler:
    def __init__(self, cfg: Config):
        cfg.ensure_dirs()
        self.cfg = cfg
        self.store = Store(cfg)
        self.net = Net(cfg)
        self.frontier = Frontier(self.store, cfg, self.net.crawl_delay)
        self.bitacora = Bitacora(cfg.log_path)

        self.stop = threading.Event()
        self._counters = Counter()
        self._counter_lock = threading.Lock()

        docs, text_bytes = self.store.totals()
        self._stored_bytes = text_bytes
        self._stored_docs = docs

    # arranque

    def seed(self, seed_urls: list[str]) -> int:
        rows = []
        for raw in seed_urls:
            url = urls.normalize(raw)
            if url:
                rows.append((url, urlsplit(url).netloc, 0, urls.priority(url, 0), None))
        return self.frontier.add(rows)

    def run(self) -> None:
        requeued = self.store.requeue_inflight()
        if requeued:
            print(f"[frontera] {requeued} URLs en vuelo reencoladas")

        monitor = threading.Thread(target=self._monitor, daemon=True)
        monitor.start()

        with ThreadPoolExecutor(max_workers=self.cfg.workers) as pool:
            workers = [pool.submit(self._worker) for _ in range(self.cfg.workers)]
            try:
                for worker in workers:
                    worker.result()
            except KeyboardInterrupt:
                self.request_stop("interrupcion del usuario (Ctrl+C)")
            finally:
                self.stop.set()
                self.frontier.close()

        self.bitacora.close()
        self._print_summary()

    def request_stop(self, reason: str) -> None:
        if not self.stop.is_set():
            print(f"\n[parando] {reason}; los hilos terminan su descarga actual")
            self.stop.set()
            self.frontier.close()

    #  hilos

    def _worker(self) -> None:
        while not self.stop.is_set():
            task = self.frontier.next()
            if task is None:
                return
            try:
                status = self._process(task)
            except Exception as exc:  # una pagina rota no debe matar al hilo
                status = FAILED
                self.bitacora.write(url=task.url, outcome="error",
                                    error=f"{type(exc).__name__}: {exc}")
                self._bump("error")
            finally:
                self.frontier.complete(task)
            self.store.finish(task.url, status)

    def _process(self, task: Task) -> int:
        # Politica 4: robots.txt antes de cualquier descarga.
        if not self.net.allowed(task.url):
            self.bitacora.write(url=task.url, depth=task.depth, outcome="robots_denied")
            self._bump("robots_denied")
            return SKIPPED

        result = self.net.fetch(task.url)
        if result.html is None:
            self.bitacora.write(url=task.url, depth=task.depth, outcome="fetch_skipped",
                                status=result.status, error=result.error,
                                ms=result.elapsed_ms)
            self._bump(result.error or "fetch_failed")
            return FAILED if result.status == 0 else SKIPPED

        # Una redireccion puede sacarnos del conjunto de dominios permitidos.
        if not urls.is_crawlable(result.url, self.cfg.allowed_domains):
            self.bitacora.write(url=result.url, depth=task.depth, outcome="redirect_out")
            self._bump("redirect_out")
            return SKIPPED

        page = extract.parse(result.html)
        on_topic = page.topic_hits >= self.cfg.min_topic_hits

        # Politica 1: los hubs (semillas y primer nivel) se expanden aunque su
        # texto propio sea pobre, porque su valor esta en los enlaces que ofrecen.
        if on_topic or task.depth <= 1:
            self._enqueue_links(page.links, result.url, task.depth)

        if not on_topic or len(page.text) < self.cfg.min_text_chars:
            self.bitacora.write(url=result.url, depth=task.depth, outcome="off_topic",
                                topic_hits=page.topic_hits, chars=len(page.text),
                                ms=result.elapsed_ms)
            self._bump("off_topic")
            return SKIPPED

        # Politica 5: duplicado exacto y casi-duplicado.
        simhash_value = dedup.simhash(page.words)
        if self.store.is_near_duplicate(simhash_value):
            self.bitacora.write(url=result.url, depth=task.depth, outcome="near_duplicate",
                                ms=result.elapsed_ms)
            self._bump("near_duplicate")
            return SKIPPED

        host = urlsplit(result.url).netloc
        meta = {
            "url": result.url,
            "host": host,
            "title": page.title,
            "published_at": page.published_at,
            "fetched_at": time.time(),
            "depth": task.depth,
            "source_url": task.url if task.url != result.url else None,
            "http_status": result.status,
            "elapsed_ms": result.elapsed_ms,
            "raw_bytes": result.raw_bytes,
            "text_bytes": len(page.text.encode("utf-8")),
            "word_count": len(page.words),
            "topic_hits": page.topic_hits,
            "sha256": dedup.content_hash(page.text),
        }
        try:
            self.store.save(meta, page.text, simhash_value)
        except DuplicateError:
            self.bitacora.write(url=result.url, depth=task.depth, outcome="exact_duplicate")
            self._bump("exact_duplicate")
            return SKIPPED

        with self._counter_lock:
            self._counters["stored"] += 1
            self._stored_docs += 1
            self._stored_bytes += meta["text_bytes"]

        self.bitacora.write(url=result.url, host=host, depth=task.depth, outcome="stored",
                            source=task.url, words=meta["word_count"],
                            bytes=meta["text_bytes"], published_at=page.published_at,
                            ms=result.elapsed_ms)
        return DONE

    def _enqueue_links(self, links: list[str], base: str, depth: int) -> None:
        if depth >= self.cfg.max_depth:
            return
        child_depth = depth + 1
        rows, seen = [], set()
        for href in links[:_MAX_LINKS_PER_PAGE]:
            url = urls.normalize(href, base)
            if not url or url in seen:
                continue
            seen.add(url)
            if not urls.is_crawlable(url, self.cfg.allowed_domains):
                continue
            rows.append((url, urlsplit(url).netloc, child_depth,
                         urls.priority(url, child_depth), base))
        if rows:
            self._bump("discovered", self.frontier.add(rows))

    # reporte

    def _bump(self, key: str, amount: int = 1) -> None:
        with self._counter_lock:
            self._counters[key] += amount

    def _monitor(self) -> None:
        started = time.monotonic()
        last_docs, last_time = self._stored_docs, started

        while not self.stop.wait(5.0):
            now = time.monotonic()
            with self._counter_lock:
                docs, total_bytes = self._stored_docs, self._stored_bytes
            rate = (docs - last_docs) / max(now - last_time, 1e-6)
            last_docs, last_time = docs, now

            print(f"[{hms(now - started)}] docs={docs:,} texto={human_bytes(total_bytes)} "
                  f"({rate:.1f} doc/s) cola={self.store.pending_count():,}", flush=True)

            if total_bytes >= self.cfg.target_bytes:
                self.request_stop(f"meta de {self.cfg.target_bytes / 1024**2:.0f}MB alcanzada")
                return

    def _print_summary(self) -> None:
        docs, total_bytes = self.store.totals()
        print(f"\nDocumentos: {docs:,}   Texto: {human_bytes(total_bytes)}")
        print("Contadores:", dict(sorted(self._counters.items())))
        print("\nDistribucion por sitio (politica de cortesia):")
        for host, count, size in self.store.per_host_counts():
            print(f"  {host:<34} {count:>8,} docs  {size / 1024**2:>9.1f} MB")
