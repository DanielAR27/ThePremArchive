from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

from common.bitacora import human_bytes
from common.config import GB, Config
from common.store import Store
from common.urls import normalize, registrable_domain

from .crawler import Crawler


def _load_seeds(path: Path) -> list[str]:
    if not path.exists():
        sys.exit(f"No existe el archivo de semillas: {path}")
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _build_config(args: argparse.Namespace, seeds: list[str]) -> Config:
    allowed = {registrable_domain(urlsplit(normalize(s) or s).netloc) for s in seeds}
    allowed.update(args.allow or [])
    cfg = Config(
        seeds=args.seeds,
        repo_dir=args.repo,
        db_path=args.db,
        log_path=args.log,
        allowed_domains=frozenset(d for d in allowed if d),
    )
    for field in ("workers", "max_depth", "per_domain_delay", "per_domain_concurrency",
                  "min_topic_hits", "obey_robots"):
        value = getattr(args, field, None)
        if value is not None:
            setattr(cfg, field, value)
    if getattr(args, "target_gb", None):
        cfg.target_bytes = int(args.target_gb * GB)
    return cfg


def cmd_crawl(args: argparse.Namespace) -> None:
    seeds = _load_seeds(args.seeds)
    cfg = _build_config(args, seeds)

    print(f"Dominios permitidos: {', '.join(sorted(cfg.allowed_domains))}")
    print(f"Hilos: {cfg.workers} | profundidad max: {cfg.max_depth} | "
          f"delay/sitio: {cfg.per_domain_delay}s | "
          f"meta: {cfg.target_bytes / 1024**2:,.0f}MB\n")

    crawler = Crawler(cfg)
    added = crawler.seed(seeds)
    print(f"Semillas encoladas: {added} nuevas de {len(seeds)}\n")
    crawler.run()


def cmd_status(args: argparse.Namespace) -> None:
    cfg = Config(db_path=args.db, repo_dir=args.repo)
    if not cfg.db_path.exists():
        sys.exit(f"No existe la base de datos: {cfg.db_path}")

    store = Store(cfg)
    docs, text_bytes = store.totals()
    print(f"Documentos: {docs:,}")
    print(f"Texto:      {human_bytes(text_bytes)}")
    print(f"Pendientes: {store.pending_count():,}\n")
    for host, count, size in store.per_host_counts():
        print(f"  {host:<34} {count:>8,} docs  {size / 1024**2:>9.1f} MB")


def cmd_reset(args: argparse.Namespace) -> None:
    cfg = Config(db_path=args.db)
    if not cfg.db_path.exists():
        sys.exit(f"No existe la base de datos: {cfg.db_path}")
    print(f"{Store(cfg).requeue_inflight()} URLs en vuelo devueltas a la cola")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m vanilla_spider_premierleague",
        description="Arañador propio para el repositorio Premier League.",
    )
    parser.add_argument("--db", type=Path, default=Path("data/crawl.db"))
    parser.add_argument("--repo", type=Path, default=Path("repo"))
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="arranca o reanuda el arañado")
    crawl.add_argument("--seeds", type=Path, default=Path("seeds.txt"))
    crawl.add_argument("--log", type=Path, default=Path("logs/bitacora.jsonl"))
    crawl.add_argument("-w", "--workers", type=int, help="hilos de descarga (def. 24)")
    crawl.add_argument("-d", "--max-depth", type=int, help="profundidad maxima (def. 6)")
    crawl.add_argument("--delay", dest="per_domain_delay", type=float,
                       help="segundos entre peticiones al mismo sitio (def. 1.5)")
    crawl.add_argument("--per-domain", dest="per_domain_concurrency", type=int,
                       help="descargas simultaneas por sitio (def. 2)")
    crawl.add_argument("--min-topic-hits", type=int,
                       help="terminos del tema requeridos para conservar (def. 3)")
    crawl.add_argument("--target-gb", type=float, help="tamaño objetivo (def. 10)")
    crawl.add_argument("--allow", action="append", metavar="DOMINIO",
                       help="dominio extra permitido (repetible)")
    crawl.add_argument("--ignore-robots", dest="obey_robots", action="store_false",
                       default=None, help=argparse.SUPPRESS)
    crawl.set_defaults(func=cmd_crawl)

    status = sub.add_parser("status", help="estadisticas del repositorio y la cola")
    status.set_defaults(func=cmd_status)

    reset = sub.add_parser("reset", help="devuelve a la cola las URLs en vuelo")
    reset.set_defaults(func=cmd_reset)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
