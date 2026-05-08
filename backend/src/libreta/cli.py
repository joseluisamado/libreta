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

    gc = sub.add_parser(
        "gc",
        help="List (or delete) sidecar assets that no page references",
    )
    gc_target = gc.add_mutually_exclusive_group()
    gc_target.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run on the given git source id (under LIBRETA_REPOS_DIR/<id>)",
    )
    gc_target.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Run on an arbitrary repo path (overrides --source and LIBRETA_CONTENT_DIR)",
    )
    gc.add_argument(
        "--delete",
        action="store_true",
        help="Delete orphans and commit per page. Default is dry-run (list only).",
    )

    args = parser.parse_args()

    if args.command == "reindex":
        _run_reindex(args.content_dir)
    elif args.command == "gc":
        _run_gc(args.source, args.repo, args.delete)


def _run_reindex(content_dir: Path | None) -> None:
    from libreta.config import Settings
    from libreta.storage.search import full_reindex

    settings = Settings(content_dir=content_dir) if content_dir else Settings()

    if not settings.content_dir.is_dir():
        print(f"error: content directory not found: {settings.content_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Reindexing {settings.content_dir} …", flush=True)
    n = asyncio.run(full_reindex(settings.content_dir, settings.repos_dir))
    print(f"Done — indexed {n} page(s).")


def _run_gc(source: str | None, repo: Path | None, delete: bool) -> None:
    from libreta.config import Settings
    from libreta.storage.gc import commit_orphan_removal, find_orphans

    settings = Settings()
    if repo is not None:
        repo_root = repo
    elif source is not None:
        repo_root = settings.repos_dir / source
    else:
        repo_root = settings.content_dir

    if not repo_root.is_dir():
        print(f"error: repo not found: {repo_root}", file=sys.stderr)
        sys.exit(1)

    results = find_orphans(repo_root)
    if not results:
        print(f"No orphan assets in {repo_root}.")
        return

    total_files = sum(len(orphs) for _, orphs in results)
    action = "Deleting" if delete else "Found"
    print(f"{action} {total_files} orphan asset(s) across {len(results)} page(s) in {repo_root}:")
    for md_file, orphans in results:
        rel_md = md_file.relative_to(repo_root)
        print(f"\n  {rel_md}")
        for o in orphans:
            print(f"    - {o.relative_to(repo_root)}")
        if delete:
            commit_orphan_removal(repo_root, md_file, orphans)

    if not delete:
        print("\n(dry run — re-run with --delete to remove and commit.)")


if __name__ == "__main__":
    main()
