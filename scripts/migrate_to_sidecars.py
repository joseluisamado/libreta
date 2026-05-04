#!/usr/bin/env python3
"""Migrate a Libreta content directory from the old ``index.md`` model to the
new sidecar-directory model.

Before::

    pages/
    ├── index.md                     # home page
    ├── about/index.md               # /about (index page)
    ├── devel/concepts/saml/
    │   ├── index.md                 # /devel/concepts/saml
    │   ├── 20260314-202736.png      # attachment
    │   └── 20260314-202805.png
    └── recipes/
        ├── pizza-dough.md           # leaf page
        └── pizza-dough.jpg          # attachment

After::

    pages/
    ├── index.md                     # /index (regular page)
    ├── .index.md/                   # sidecar (empty if no refs)
    ├── about.md                     # was about/index.md
    ├── .about.md/                   # sidecar for about.md
    ├── devel/concepts/saml.md       # was saml/index.md
    ├── devel/concepts/.saml.md/     # sidecar for saml.md
    │   ├── 20260314-202736.png
    │   └── 20260314-202805.png
    └── recipes/
        ├── pizza-dough.md
        └── .pizza-dough.md/         # sidecar for pizza-dough.md
            └── pizza-dough.jpg

Usage::

    python scripts/migrate_to_sidecars.py /path/to/repo-root [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def find_refs(body: str) -> set[str]:
    """Find all relative file references in a markdown body.

    Matches ``![](file)`` images and ``[text](file)`` links, but skips
    absolute URLs and anchors.
    """
    refs: set[str] = set()
    for m in re.finditer(r"!\[.*?\]\(([^)]+)\)", body):
        href = m.group(1)
        if _is_relative(href):
            refs.add(href.split("#")[0].split("?")[0])
    for m in re.finditer(r"(?<!\!)\[.*?\]\(([^)]+)\)", body):
        href = m.group(1)
        if _is_relative(href):
            refs.add(href.split("#")[0].split("?")[0])
    return refs


def _is_relative(href: str) -> bool:
    if href.startswith(("http://", "https://", "//", "/", "#", "data:", "mailto:")):
        return False
    return True


def is_attachment(name: str) -> bool:
    return not name.endswith(".md") and not name.startswith(".")


def relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def migrate(root: Path, dry_run: bool = False) -> int:
    pages_root = root / "pages"
    if not pages_root.is_dir():
        pages_root = root

    print(f"Migrating: {pages_root}")
    if dry_run:
        print("  (dry-run — no changes will be made)")

    promotions = 0
    moved_attachments = 0
    removed_dirs = 0

    # ── Phase 1: promote index.md → ../<dirname>.md & move attachments ──
    # Process deepest first so nested index.md are handled before their parents
    for index_file in sorted(
        pages_root.rglob("index.md"), key=lambda p: len(p.parts), reverse=True
    ):
        parent = index_file.parent
        if parent == pages_root:
            # Top-level index.md stays as a regular page
            continue

        # The new path: foo/bar/index.md → foo/bar.md
        target = parent.parent / f"{parent.name}.md"
        if target.exists():
            print(f"  CONFLICT: {index_file} → {target} (target exists, skipping)")
            continue

        # Sidecar is named after the directory: foo/.bar.md/
        sidecar = parent.parent / f".{parent.name}.md"

        # Find refs in the index.md body and move matching attachments
        body = index_file.read_text(encoding="utf-8")
        refs = find_refs(body)
        for candidate in sorted(parent.iterdir()):
            if not candidate.is_file():
                continue
            if candidate.name == "index.md":
                continue
            if candidate.name.startswith("."):
                continue
            if candidate.name in refs:
                sidecar.mkdir(parents=True, exist_ok=True)
                dest = sidecar / candidate.name
                print(
                    f"  attach: {relative(candidate, pages_root)} → {relative(dest, pages_root)}"
                )
                if not dry_run:
                    shutil.move(str(candidate), str(dest))
                moved_attachments += 1

        # Promote index.md → target
        print(
            f"  promote: {relative(index_file, pages_root)} → {relative(target, pages_root)}"
        )
        if not dry_run:
            target.write_text(body, encoding="utf-8")
            index_file.unlink()
        promotions += 1

    # ── Phase 2: handle remaining leaf .md files ──────────────────────────
    for md_file in sorted(pages_root.rglob("*.md")):
        if not md_file.is_file():
            continue
        if md_file.name == "index.md":
            continue  # already handled or top-level

        sidecar = md_file.parent / f".{md_file.name}"
        body = md_file.read_text(encoding="utf-8")
        refs = find_refs(body)
        md_dir = md_file.parent

        for candidate in sorted(md_dir.iterdir()):
            if not candidate.is_file():
                continue
            if candidate.name == md_file.name:
                continue
            if not is_attachment(candidate.name):
                continue
            if candidate.name in refs:
                sidecar.mkdir(parents=True, exist_ok=True)
                dest = sidecar / candidate.name
                print(
                    f"  attach: {relative(candidate, pages_root)} → {relative(dest, pages_root)}"
                )
                if not dry_run:
                    shutil.move(str(candidate), str(dest))
                moved_attachments += 1

    # ── Phase 3: move orphan attachments ─────────────────────────────────
    for md_file in sorted(pages_root.rglob("*.md")):
        if not md_file.is_file():
            continue
        md_dir = md_file.parent
        sidecar = md_dir / f".{md_file.name}"

        # Count other .md files in this directory
        other_mds = [
            p
            for p in md_dir.iterdir()
            if p.suffix == ".md" and p.is_file() and p != md_file
        ]

        for candidate in sorted(md_dir.iterdir()):
            if not candidate.is_file():
                continue
            if not is_attachment(candidate.name):
                continue
            if candidate.name == md_file.name:
                continue
            if not other_mds:
                # Sole .md file owns all orphans
                sidecar.mkdir(parents=True, exist_ok=True)
                dest = sidecar / candidate.name
                print(
                    f"  orphan: {relative(candidate, pages_root)} → {relative(dest, pages_root)}"
                )
                if not dry_run:
                    shutil.move(str(candidate), str(dest))
                moved_attachments += 1
            else:
                print(f"  SKIP orphan (ambiguous): {relative(candidate, pages_root)}")
                break  # Only print once per directory

    # ── Phase 4: remove empty directories ─────────────────────────────────
    # First pass: remove leftover .index.md directories (empty sidecars from
    # Phase 1 that ended up inside the old directory after a previous run).
    for dir_path in sorted(
        pages_root.rglob(".index.md"), key=lambda p: len(p.parts), reverse=True
    ):
        if dir_path.is_dir() and not any(
            p for p in dir_path.iterdir() if not p.name.startswith(".")
        ):
            for f in dir_path.iterdir():
                f.unlink()
            print(f"  rmdir (artifact): {relative(dir_path, pages_root)}")
            if not dry_run:
                dir_path.rmdir()
            removed_dirs += 1

    # Second pass: remove non-hidden empty directories.
    for dir_path in sorted(
        pages_root.rglob("*"), key=lambda p: len(p.parts), reverse=True
    ):
        if not dir_path.is_dir():
            continue
        if dir_path.name.startswith("."):
            continue  # preserve sidecars
        if dir_path == pages_root:
            continue
        try:
            if not any(dir_path.iterdir()):
                print(f"  rmdir: {relative(dir_path, pages_root)}")
                if not dry_run:
                    dir_path.rmdir()
                removed_dirs += 1
        except OSError:
            pass

    # ── Summary ───────────────────────────────────────────────────────────
    print(
        f"\nDone: {promotions} index→page promotions, {moved_attachments} attachments moved, {removed_dirs} directories removed"
    )
    if dry_run:
        print("  (no changes were made — re-run without --dry-run to apply)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Libreta content to sidecar model"
    )
    parser.add_argument(
        "repo_root", type=Path, help="Path to the repo root (or pages/ parent)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without applying"
    )
    args = parser.parse_args()
    return migrate(args.repo_root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
