#!/usr/bin/env python3
"""Rewrite markdown references in .md files to include sidecar paths.

After migrating to the sidecar model, markdown files still contain bare
relative references (``![](photo.png)``).  This script rewrites them to
include the sidecar prefix so the files render correctly on GitHub, Gitea,
or any other markdown viewer — no Libreta-specific URL rewriting needed.

Example::

    saml.md:  ![](20260314-202736.png)  →  ![](.saml.md/20260314-202736.png)

Usage::

    python scripts/rewrite_sidecar_refs.py /path/to/repo-root [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def rewrite_body(body: str, sidecar_name: str, sidecar: Path) -> tuple[str, int]:
    """Rewrite relative image/link refs in *body* to include *sidecar_name*.

    Returns (new_body, rewrites_count).
    """
    ref_extractor = re.compile(r"(!?\[.*?\])\(([^)]+)\)")

    def replacer(m: re.Match[str]) -> str:
        prefix = m.group(1)  # ![alt] or [text]
        href = m.group(2)

        # Skip absolute URLs, anchors, data URIs
        if href.startswith(("http://", "https://", "//", "/", "#", "data:", "mailto:")):
            return m.group(0)

        # Skip if already contains sidecar prefix
        if href.startswith(f"{sidecar_name}/") or href.startswith(f"./{sidecar_name}/"):
            return m.group(0)

        # Strip fragment / query for filesystem check
        bare = href.split("#")[0].split("?")[0]

        # Only rewrite if the referenced file actually exists in the sidecar
        if sidecar.is_dir() and (sidecar / bare).is_file():
            return f"{prefix}({sidecar_name}/{href})"

        return m.group(0)

    new_body, n = ref_extractor.subn(replacer, body)
    return new_body, n


def relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def rewrite(root: Path, dry_run: bool = False) -> int:
    pages_root = root / "pages"
    if not pages_root.is_dir():
        pages_root = root

    print(f"Rewriting refs in: {pages_root}")
    if dry_run:
        print("  (dry-run)")

    total_rewrites = 0

    for md_file in sorted(pages_root.rglob("*.md")):
        if not md_file.is_file():
            continue

        sidecar = md_file.parent / f".{md_file.name}"
        sidecar_name = sidecar.name  # .name.md

        body = md_file.read_text(encoding="utf-8")
        new_body, n = rewrite_body(body, sidecar_name, sidecar)

        if n > 0:
            rel = relative(md_file, pages_root)
            print(f"  {rel}: {n} refs rewritten")
            if not dry_run:
                md_file.write_text(new_body, encoding="utf-8")
            total_rewrites += n

    print(f"\nDone: {total_rewrites} references rewritten across all files")
    if dry_run:
        print("  (no changes were made — re-run without --dry-run to apply)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite markdown references to include sidecar paths"
    )
    parser.add_argument("repo_root", type=Path, help="Path to the repo root")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without applying"
    )
    args = parser.parse_args()
    return rewrite(args.repo_root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
