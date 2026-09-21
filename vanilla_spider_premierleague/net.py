from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common.config import USER_AGENT, Config

_CHARSET_RE = re.compile(rb'charset=["\']?\s*([\w-]+)', re.I)
_HTML_TYPES = ("text/html", "application/xhtml", "text/plain")


@dataclass(slots=True)
class Fetched:
    url: str
    status: int
    elapsed_ms: int
    raw_bytes: int
    content_type: str
    html: str | None
    error: str | None = None


class Net:
    """Capa de red con cortesia (politica 4): robots.txt, retries y sesiones por hilo."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._local = threading.local()
        self._robots: dict[str, tuple[RobotFileParser | None, float | None]] = {}
        self._robots_lock = threading.Lock()

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en-GB,en;q=0.9,es;q=0.6",
                "Accept-Encoding": "gzip, deflate",
            })
            retry = Retry(
                total=2,
                backoff_factor=0.8,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
                respect_retry_after_header=True,
            )
            adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._local.session = session
        return session

    def _robots_for(self, url: str) -> tuple[RobotFileParser | None, float | None]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            cached = self._robots.get(origin)
        if cached is not None:
            return cached

        parser: RobotFileParser | None = None
        delay: float | None = None
        try:
            response = self.session.get(f"{origin}/robots.txt", timeout=10)
            if response.status_code == 200 and response.text:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                raw_delay = parser.crawl_delay(USER_AGENT)
                delay = float(raw_delay) if raw_delay else None
        except requests.RequestException:
            parser = None

        entry = (parser, delay)
        with self._robots_lock:
            self._robots.setdefault(origin, entry)
        return entry

    def allowed(self, url: str) -> bool:
        if not self.cfg.obey_robots:
            return True
        parser, _ = self._robots_for(url)
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def crawl_delay(self, url: str) -> float:
        """Delay efectivo: el mayor entre el configurado y el declarado en robots.txt."""
        _, delay = self._robots_for(url)
        return max(self.cfg.per_domain_delay, delay or 0.0)

    def fetch(self, url: str) -> Fetched:
        started = time.perf_counter()
        try:
            response = self.session.get(
                url, timeout=(5.0, self.cfg.timeout), stream=True, allow_redirects=True
            )
        except requests.RequestException as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return Fetched(url, 0, elapsed, 0, "", None, type(exc).__name__)

        with response:
            content_type = response.headers.get("Content-Type", "").lower()
            final_url = response.url

            if response.status_code != 200:
                elapsed = int((time.perf_counter() - started) * 1000)
                return Fetched(final_url, response.status_code, elapsed, 0,
                               content_type, None, "http_status")

            if not any(t in content_type for t in _HTML_TYPES):
                elapsed = int((time.perf_counter() - started) * 1000)
                return Fetched(final_url, 200, elapsed, 0, content_type, None,
                               "content_type")

            chunks, total = [], 0
            for chunk in response.iter_content(64 * 1024):
                chunks.append(chunk)
                total += len(chunk)
                if total >= self.cfg.max_page_bytes:
                    break

        raw = b"".join(chunks)
        elapsed = int((time.perf_counter() - started) * 1000)
        return Fetched(final_url, 200, elapsed, len(raw), content_type,
                       _decode(raw, content_type))


def _decode(raw: bytes, content_type: str) -> str:
    encoding = "utf-8"
    if "charset=" in content_type:
        encoding = content_type.split("charset=", 1)[1].split(";")[0].strip()
    else:
        match = _CHARSET_RE.search(raw[:4096])
        if match:
            encoding = match.group(1).decode("ascii", "ignore")
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, ValueError):
        return raw.decode("utf-8", errors="replace")
