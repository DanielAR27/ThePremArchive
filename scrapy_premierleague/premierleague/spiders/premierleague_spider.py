from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import scrapy
from scrapy.http import TextResponse

from common import dedup, extract, urls
from common.bitacora import Bitacora
from common.config import Config

from ..items import DocumentItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MAX_LINKS_PER_PAGE = 300


def _load_seeds() -> list[str]:
    path = _REPO_ROOT / "seeds.txt"
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


class PremierLeagueSpider(scrapy.Spider):
    """Arañador con biblioteca (Scrapy) para la misma necesidad de informacion
    que vanilla_spider_premierleague/crawler.py (el arañador propio). Reusa
    los modulos compartidos de politicas en common/ (urls, extract, dedup)
    para que la unica diferencia real entre ambas implementaciones sea el
    motor de arañado.
    """

    name = "premierleague"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rutas ancladas a la raiz del repo, no a la CWD desde donde se
        # invoque `scrapy crawl` (ver nota en pipelines.py).
        self.cfg = Config(
            repo_dir=_REPO_ROOT / "repo",
            db_path=_REPO_ROOT / "data" / "crawl.db",
            log_path=_REPO_ROOT / "logs" / "bitacora.jsonl",
        )
        self.cfg.ensure_dirs()

        seed_urls = [u for u in (urls.normalize(s) for s in _load_seeds()) if u]
        self.start_urls = seed_urls
        # Politica 1: dominios permitidos = los de las semillas (igual que __main__.py).
        self.allowed_domains = sorted({
            urls.registrable_domain(urlsplit(u).netloc) for u in seed_urls
        })
        self._allowed_set = frozenset(self.allowed_domains)

        self.bitacora = Bitacora(_REPO_ROOT / "logs" / "bitacora_scrapy.jsonl")

    def closed(self, reason: str) -> None:
        self.bitacora.close()

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse,
                                 priority=int(urls.priority(url, 0)))

    def parse(self, response: scrapy.http.Response):
        if not isinstance(response, TextResponse):
            self.bitacora.write(url=response.url, outcome="content_type")
            return

        depth = response.meta.get("depth", 0)
        page = extract.parse(response.text)
        on_topic = page.topic_hits >= self.cfg.min_topic_hits

        # Politica 1: los hubs (semillas y primer nivel) se expanden aunque su
        # texto propio sea pobre, porque su valor esta en los enlaces que ofrecen.
        if on_topic or depth <= 1:
            yield from self._follow_links(response, page.links, depth)

        if not on_topic or len(page.text) < self.cfg.min_text_chars:
            self.bitacora.write(url=response.url, depth=depth, outcome="off_topic",
                                topic_hits=page.topic_hits, chars=len(page.text))
            return

        item = DocumentItem()
        item["url"] = response.url
        item["host"] = urlsplit(response.url).netloc
        item["title"] = page.title
        item["published_at"] = page.published_at
        item["fetched_at"] = time.time()
        item["depth"] = depth
        referer = response.request.headers.get("Referer")
        item["source_url"] = referer.decode() if referer else None
        item["http_status"] = response.status
        item["elapsed_ms"] = int(response.meta.get("download_latency", 0.0) * 1000)
        item["raw_bytes"] = len(response.body)
        item["text_bytes"] = len(page.text.encode("utf-8"))
        item["word_count"] = len(page.words)
        item["topic_hits"] = page.topic_hits
        item["sha256"] = dedup.content_hash(page.text)
        item["text"] = page.text
        item["simhash_value"] = dedup.simhash(page.words)
        yield item

    def _follow_links(self, response: scrapy.http.Response, links: list[str], depth: int):
        if depth >= self.cfg.max_depth:
            return
        child_depth = depth + 1
        seen: set[str] = set()
        for href in links[:_MAX_LINKS_PER_PAGE]:
            url = urls.normalize(href, response.url)
            if not url or url in seen:
                continue
            seen.add(url)
            if not urls.is_crawlable(url, self._allowed_set):
                continue
            yield response.follow(url, callback=self.parse,
                                  priority=int(urls.priority(url, child_depth)))
