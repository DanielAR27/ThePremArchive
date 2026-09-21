from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scrapy.exceptions import DropItem

from common.config import Config
from common.store import DuplicateError, Store


class StoragePipeline:
    """Guarda cada item en el mismo repositorio/BD que el arañador propio.

    Al compartir `data/crawl.db` y `repo/`, la deduplicacion (politica 5) opera
    a traves de ambas implementaciones: si el arañador propio ya guardo una
    noticia, este pipeline la detecta como duplicado exacto o casi-duplicado
    y la descarta, sin necesidad de un paso de fusion manual despues.
    """

    def open_spider(self, spider) -> None:
        # Rutas ancladas a la raiz del repo (no a la CWD): Scrapy siempre se
        # invoca desde scrapy_premierleague/, pero el repositorio final es
        # compartido con el arañador propio en la raiz del proyecto.
        cfg = Config(
            repo_dir=_REPO_ROOT / "repo",
            db_path=_REPO_ROOT / "data" / "crawl.db",
            log_path=_REPO_ROOT / "logs" / "bitacora.jsonl",
        )
        cfg.ensure_dirs()
        self.store = Store(cfg)

    def process_item(self, item: dict, spider) -> dict:
        text = item.pop("text")
        simhash_value = item.pop("simhash_value")

        if self.store.is_near_duplicate(simhash_value):
            spider.bitacora.write(url=item["url"], depth=item["depth"],
                                  outcome="near_duplicate")
            raise DropItem(f"casi-duplicado: {item['url']}")

        try:
            self.store.save(dict(item), text, simhash_value)
        except DuplicateError:
            spider.bitacora.write(url=item["url"], depth=item["depth"],
                                  outcome="exact_duplicate")
            raise DropItem(f"duplicado exacto: {item['url']}")

        spider.bitacora.write(url=item["url"], host=item["host"], depth=item["depth"],
                              outcome="stored", source=item["source_url"],
                              words=item["word_count"], bytes=item["text_bytes"],
                              published_at=item["published_at"])
        return item
