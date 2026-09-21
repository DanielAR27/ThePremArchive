from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

from .config import BINARY_SUFFIXES, NOISE_SUBDOMAINS, OFF_TOPIC_TOKENS

_MULTI_LABEL_SUFFIXES = frozenset(
    {"co.uk", "com.au", "co.za", "com.br", "co.jp", "com.mx", "co.nz", "org.uk"}
)
_TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_cid", "mc_eid", "icid", "ito", "cmp")
_HOST_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
_YEAR_RE = re.compile(r"/(19\d{2}|20\d{2})(?:[/-]\d{1,2})?(?:/|-|$)")
_FRESH_TOKENS = ("/news", "/report", "/match", "/fixture", "/result", "/transfer",
                 "/live", "/preview", "/analysis", "/interview", "/blog")


def registrable_domain(host: str) -> str:
    """Dominio registrable: news.bbc.co.uk -> bbc.co.uk."""
    host = host.lower().split(":")[0].removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_LABEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def normalize(url: str, base: str | None = None) -> str | None:
    """Canonicaliza una URL. Devuelve None si no es arañable."""
    try:
        if base:
            url = urljoin(base, url)
        url, _ = urldefrag(url.strip())
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        host = parts.hostname.lower()
        port = parts.port
    except ValueError:  # href malformado (puerto invalido, IPv6 roto, etc.)
        return None

    if not _HOST_RE.fullmatch(host):
        return None

    netloc = host if port in (None, 80, 443) else f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = "&".join(
        p for p in parts.query.split("&")
        if p and not p.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def is_crawlable(url: str, allowed_domains: frozenset[str]) -> bool:
    """Politica 1 (dominios permitidos) + politica 3 (descarte temprano por URL)."""
    parts = urlsplit(url)
    host = parts.netloc.split(":")[0].lower()
    if registrable_domain(host) not in allowed_domains:
        return False
    if host.split(".")[0] in NOISE_SUBDOMAINS:
        return False
    path = parts.path.lower()
    if any(path.endswith(suffix) for suffix in BINARY_SUFFIXES):
        return False
    segments = {s for s in re.split(r"[/_.-]+", path) if s}
    return not (segments & OFF_TOPIC_TOKENS)


def priority(url: str, depth: int) -> float:
    """Politica 2: puntaje de recencia estimado a partir de la URL y la profundidad.

    Se evalua antes de descargar, por lo que usa señales del path (seccion de
    noticias, año embebido) en lugar de la fecha real de publicacion.
    """
    path = urlsplit(url).path.lower()
    score = 10.0 - 1.5 * depth

    if any(token in path for token in _FRESH_TOKENS):
        score += 3.0

    match = _YEAR_RE.search(path)
    if match:
        year, current = int(match.group(1)), datetime.now(timezone.utc).year
        score += 3.0 if year >= current - 1 else max(-4.0, -0.4 * (current - year))

    depth_in_path = path.count("/")
    if depth_in_path > 7:
        score -= 1.0
    return score
