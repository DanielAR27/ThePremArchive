from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scrapy import signals
from scrapy.exceptions import NotConfigured
from twisted.internet import task

from common.bitacora import hms, human_bytes
from common.config import Config
from common.store import Store

_CHECK_INTERVAL = 15.0


class TargetSizeExtension:
    """Imprime el progreso del repositorio combinado (propio + Scrapy) cada
    15s y detiene el spider al llegar a TARGET_GB, revisando la misma base
    de datos compartida que usa `python -m vanilla_spider_premierleague crawl
    --target-gb`. Sin esto la terminal de Scrapy no muestra nada porque el
    log va a `logs/scrapy.log` (LOG_FILE).
    """

    def __init__(self, crawler):
        self.crawler = crawler
        target_gb = crawler.settings.getfloat("TARGET_GB", 0)
        if not target_gb:
            raise NotConfigured
        self.target_bytes = target_gb * 1024**3

        cfg = Config(repo_dir=_REPO_ROOT / "repo", db_path=_REPO_ROOT / "data" / "crawl.db")
        self.store = Store(cfg)
        self.loop = task.LoopingCall(self._tick)

        self._started = time.monotonic()
        self._last_docs = 0
        self._last_time = self._started

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_opened(self, spider) -> None:
        docs, _ = self.store.totals()
        self._last_docs = docs
        self.loop.start(_CHECK_INTERVAL, now=False)

    def spider_closed(self, spider) -> None:
        if self.loop.running:
            self.loop.stop()

    def _tick(self) -> None:
        now = time.monotonic()
        docs, total_bytes = self.store.totals()
        rate = (docs - self._last_docs) / max(now - self._last_time, 1e-6)
        self._last_docs, self._last_time = docs, now

        remaining = max(0.0, self.target_bytes - total_bytes)
        print(f"[{hms(now - self._started)}] combinado: docs={docs:,} "
              f"texto={human_bytes(total_bytes)} ({rate:.1f} doc/s) "
              f"faltan={human_bytes(remaining)}", flush=True)

        if total_bytes >= self.target_bytes:
            self.crawler.engine.close_spider(
                self.crawler.spider,
                f"meta combinada de {self.target_bytes / 1024**3:.0f}GB alcanzada",
            )
