import scrapy


class DocumentItem(scrapy.Item):
    """Espejo de las columnas de la tabla `documents` en common/store.py."""

    url = scrapy.Field()
    host = scrapy.Field()
    title = scrapy.Field()
    published_at = scrapy.Field()
    fetched_at = scrapy.Field()
    depth = scrapy.Field()
    source_url = scrapy.Field()
    http_status = scrapy.Field()
    elapsed_ms = scrapy.Field()
    raw_bytes = scrapy.Field()
    text_bytes = scrapy.Field()
    word_count = scrapy.Field()
    topic_hits = scrapy.Field()
    sha256 = scrapy.Field()

    # Se descartan del dict antes de Store.save(); no son columnas de la BD.
    text = scrapy.Field()
    simhash_value = scrapy.Field()
