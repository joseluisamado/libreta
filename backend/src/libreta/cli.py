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

    an = sub.add_parser(
        "import-apple-notes",
        help="Import Apple Notes (NoteStore.sqlite) into a git working tree",
    )
    an.add_argument(
        "--notestore",
        type=Path,
        default=Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite",
        help="Path to NoteStore.sqlite (default: standard macOS location).",
    )
    an.add_argument("--repo", type=Path, required=True, help="Target git working tree.")
    an.add_argument(
        "--dest",
        type=str,
        default="apple-notes",
        help="Destination subpath inside --repo (default: apple-notes).",
    )
    an.add_argument("--account", type=str, default=None)
    an.add_argument("--folder", type=str, default=None)
    an.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "reindex":
        _run_reindex(args.content_dir)
    elif args.command == "gc":
        _run_gc(args.source, args.repo, args.delete)
    elif args.command == "import-apple-notes":
        _run_import_apple_notes(args)


def _run_import_apple_notes(args: argparse.Namespace) -> None:
    # Reuse the standalone script as a library, so the CLI and `python
    # scripts/import_apple_notes.py` share one implementation.
    import importlib.util

    script = Path(__file__).resolve().parents[3] / "scripts" / "import_apple_notes.py"
    spec = importlib.util.spec_from_file_location("_libreta_apple_notes", script)
    if spec is None or spec.loader is None:
        print(f"error: could not load {script}", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    stats = mod.import_notes(
        notestore=args.notestore.expanduser(),
        repo=args.repo.expanduser().resolve(),
        dest_subpath=args.dest,
        dry_run=args.dry_run,
        account_filter=args.account,
        folder_filter=args.folder,
    )
    print(
        f"Done. Seen {stats.notes_seen}, wrote {stats.notes_written}, "
        f"locked-skipped {stats.notes_skipped_locked}.",
        file=sys.stderr,
    )


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
