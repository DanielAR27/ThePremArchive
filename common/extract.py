from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment

from .config import TOPIC_KEYWORDS

_PARSER = "lxml" if importlib.util.find_spec("lxml") else "html.parser"
_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe",
              "nav", "header", "footer", "aside", "form", "button")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")
_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.I)
_DATE_META = (
    {"property": "article:published_time"},
    {"property": "article:modified_time"},
    {"name": "pubdate"},
    {"name": "date"},
    {"itemprop": "datePublished"},
)


@dataclass(slots=True)
class Page:
    title: str
    text: str
    published_at: str | None
    links: list[str]
    words: list[str]
    topic_hits: int


def parse(html: str) -> Page:
    soup = BeautifulSoup(html, _PARSER)

    links = [a["href"] for a in soup.find_all("a", href=True)]

    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = _clean(soup.get_text("\n"))
    words = _WORD_RE.findall(text.lower())

    return Page(
        title=title[:300],
        text=text,
        published_at=_published_at(soup),
        links=links,
        words=words,
        topic_hits=len(TOPIC_KEYWORDS & set(words)),
    )


def _clean(text: str) -> str:
    lines = (_WS_RE.sub(" ", line).strip() for line in text.splitlines())
    return _BLANK_RE.sub("\n\n", "\n".join(line for line in lines if line))


def _published_at(soup: BeautifulSoup) -> str | None:
    for attrs in _DATE_META:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"][:40]

    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        return time_tag["datetime"][:40]

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("datePublished"):
                return str(node["datePublished"])[:40]
    return None
