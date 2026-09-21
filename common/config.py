from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

GB = 1024**3

USER_AGENT = (
    "ThePremArchive/1.0 (+crawler academico IC8060 TEC; contacto: copperdar27@gmail.com)"
)

# Politica 3: vocabulario del dominio. Un documento se conserva solo si supera
# `min_topic_hits` terminos distintos de este conjunto.
TOPIC_KEYWORDS = frozenset(
    """
    premier league epl matchweek gameweek fixture fixtures kickoff kick-off
    anfield emirates etihad stamford bridge old trafford villa park goodison
    arsenal aston villa bournemouth brentford brighton burnley chelsea
    crystal palace everton fulham liverpool luton manchester city united
    newcastle nottingham forest sheffield tottenham hotspur west ham wolves
    wolverhampton leeds leicester southampton ipswich
    goal goals assist assists penalty offside var referee lineup lineups
    manager transfer signing loan injury suspension clean sheet
    standings table relegation champions league europa fa cup carabao
    """.split()
)

# Politica 3: descarte temprano por URL (no se llega a descargar la pagina).
OFF_TOPIC_TOKENS = frozenset(
    """
    rugby cricket nfl nba mlb nhl tennis golf f1 formula1 boxing ufc darts
    cycling athletics olympics netball snooker horse-racing racing gaa
    la-liga serie-a bundesliga ligue1 ligue-1 mls eredivisie
    politics business culture lifestyle travel weather money tv-radio
    shop store tickets hospitality careers jobs privacy cookie terms
    """.split()
)

# Politica 3: subdominios de servicio (no editoriales) que no aportan al tema
# aunque el dominio principal si este permitido, p.ej. holidays.theguardian.com
# o fantasy.espn.com.
NOISE_SUBDOMAINS = frozenset(
    """
    jobs careers workwithus shop store holidays travel members account
    accounts login signin subscribe subscription help support ads cdn
    static assets img images mail id auth checkout tickets hospitality
    fantasy global africa espndeportes
    """.split()
)

BINARY_SUFFIXES = frozenset(
    """
    .jpg .jpeg .png .gif .webp .svg .ico .bmp .tiff .mp4 .m4v .mov .avi .webm
    .mp3 .m4a .wav .ogg .pdf .doc .docx .xls .xlsx .ppt .pptx .zip .gz .tar
    .rar .7z .css .js .json .xml .rss .atom .woff .woff2 .ttf .eot .apk .exe
    """.split()
)


@dataclass(slots=True)
class Config:
    seeds: Path = Path("seeds.txt")
    repo_dir: Path = Path("repo")
    db_path: Path = Path("data/crawl.db")
    log_path: Path = Path("logs/bitacora.jsonl")

    # Concurrencia (requisito de la rubrica: hilos + descarga concurrente).
    workers: int = 24

    # Politica 1: expansion de la frontera.
    max_depth: int = 6

    # Politica 4: cortesia.
    per_domain_delay: float = 1.5
    per_domain_concurrency: int = 2
    timeout: float = 15.0
    obey_robots: bool = True

    # Politica 3: filtrado tematico.
    min_topic_hits: int = 3
    min_text_chars: int = 500

    # Politica 5: deduplicacion.
    near_dup_distance: int = 3

    # Limites del repositorio.
    target_bytes: int = 10 * GB
    max_page_bytes: int = 4 * 1024**2

    allowed_domains: frozenset[str] = field(default_factory=frozenset)

    def ensure_dirs(self) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
