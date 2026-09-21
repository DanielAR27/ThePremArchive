"""Configuracion del arañador con biblioteca (Scrapy).

Reusa los mismos valores por defecto que common/config.py (compartidos con
el arañador propio) para que la comparacion entre ambas implementaciones sea
justa: misma politica de cortesia, misma profundidad, mismo user-agent.

Se puede invocar `scrapy crawl premierleague` desde cualquier carpeta; las
rutas de salida (repo/, data/, logs/) se resuelven en pipelines.py y en el
spider ancladas a la raiz del repo, no a la CWD.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permite `from common import ...` sin importar desde donde se invoque scrapy.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import USER_AGENT as _USER_AGENT  # noqa: E402
from common.config import Config  # noqa: E402

_defaults = Config()

BOT_NAME = "premierleague"
SPIDER_MODULES = ["premierleague.spiders"]
NEWSPIDER_MODULE = "premierleague.spiders"

USER_AGENT = _USER_AGENT

# Politica 4: cortesia (mismos valores que el arañador propio).
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = 48
CONCURRENT_REQUESTS_PER_DOMAIN = _defaults.per_domain_concurrency
DOWNLOAD_DELAY = _defaults.per_domain_delay
RANDOMIZE_DOWNLOAD_DELAY = False
DOWNLOAD_TIMEOUT = _defaults.timeout
DOWNLOAD_MAXSIZE = _defaults.max_page_bytes
DOWNLOAD_WARNSIZE = _defaults.max_page_bytes
AUTOTHROTTLE_ENABLED = False

# Politica 1: expansion (misma profundidad maxima que el propio).
DEPTH_LIMIT = _defaults.max_depth
DEPTH_STATS_VERBOSE = True

RETRY_TIMES = 2
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

ITEM_PIPELINES = {
    "premierleague.pipelines.StoragePipeline": 300,
}

# Se detiene solo cuando el repositorio combinado (propio + Scrapy) llega a
# esta meta; override en la linea de comandos con -s TARGET_GB=<numero>.
EXTENSIONS = {
    "premierleague.extensions.TargetSizeExtension": 500,
}
TARGET_GB = 10

LOG_LEVEL = "INFO"
LOG_FILE = str(Path(__file__).resolve().parents[2] / "logs" / "scrapy.log")

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
