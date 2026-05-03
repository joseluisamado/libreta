from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="libreta", description="Libreta CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ri = sub.add_parser("reindex", help="Rebuild the full-text search index from scratch")
    ri.add_argument(
        "--content-dir",
        type=Path,
        default=None,
        help="Path to the content repo (default: LIBRETA_CONTENT_DIR env var or ./data/content)",
    )

    args = parser.parse_args()

    if args.command == "reindex":
        _run_reindex(args.content_dir)


def _run_reindex(content_dir: Path | None) -> None:
    from libreta.config import Settings
    from libreta.storage.search import full_reindex

    settings = Settings(content_dir=content_dir) if content_dir else Settings()

    if not settings.content_dir.is_dir():
        print(f"error: content directory not found: {settings.content_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Reindexing {settings.content_dir} …", flush=True)
    n = asyncio.run(full_reindex(settings.content_dir))
    print(f"Done — indexed {n} page(s).")
