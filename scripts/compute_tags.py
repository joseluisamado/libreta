"""Compute tags for every page that doesn't already have them.

Walks a repo's ``pages/`` directory (pass ``--repo /path/to/clone``). For each
``.md`` file with no ``tags`` (or empty ``tags``) in frontmatter, derives 3–5
tags by scoring terms via TF-IDF across the corpus and writes them back.
Idempotent: pages that already have tags are left alone.

Run via:

    cd backend && uv run python ../scripts/compute_tags.py --repo <clone> [--dry-run] [--force]

Flags:
    --repo      Path to a git source clone (its ``pages/`` subdir is scanned). Required.
    --dry-run   Print the computed tags without writing.
    --force     Overwrite existing tags (default: skip pages that already have any).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure libreta is importable when running as a standalone script.
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from libreta.tagging import (  # noqa: E402
    MIN_TAGS,
    build_corpus_df,
    good_term,
    heading_terms,
    score_page,
    strip_markup,
    title_terms,
    tokenize,
)

HEADING_BOOST = 3
TITLE_BOOST = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Path to a git source clone; its pages/ subdir is scanned.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing tags (default: skip pages that have any)",
    )
    args = parser.parse_args()

    repo_root: Path = args.repo.resolve()
    pages_dir = repo_root / "pages"
    if not pages_dir.is_dir():
        print(f"pages dir not found: {pages_dir}", file=sys.stderr)
        return 2

    files = list(sorted(pages_dir.rglob("*.md")))
    if not files:
        print("no pages found")
        return 0

    # Build document-frequency corpus
    df, n_docs = build_corpus_df(repo_root)

    written = 0
    skipped = 0
    for f in files:
        try:
            post = frontmatter.load(f)
        except Exception as e:  # noqa: BLE001
            print(
                f"  warn: failed to parse {f.relative_to(pages_dir)}: {e}",
                file=sys.stderr,
            )
            continue

        existing = post.metadata.get("tags") or []
        is_placeholder = isinstance(existing, list) and set(existing) <= {"imported"}
        if existing and not is_placeholder and not args.force:
            skipped += 1
            continue

        # Tokenize this page
        body = strip_markup(post.content)
        bag: list[str] = []
        bag.extend(t for t in tokenize(body) if good_term(t))
        for t in heading_terms(post.content):
            if good_term(t):
                bag.extend([t] * HEADING_BOOST)
        for t in title_terms(post.metadata):
            if good_term(t):
                bag.extend([t] * TITLE_BOOST)
        tf = Counter(bag)

        chosen = score_page(tf, df, n_docs)
        if len(chosen) < MIN_TAGS:
            print(f"  skip (too few terms): {f.relative_to(pages_dir)}")
            continue

        rel = f.relative_to(pages_dir)
        print(f"  {rel}  →  {chosen}")

        if not args.dry_run:
            post.metadata["tags"] = chosen
            f.write_bytes(frontmatter.dumps(post).encode("utf-8") + b"\n")
        written += 1

    total = written + skipped
    print(f"\nprocessed {total} pages: {written} tagged, {skipped} skipped (had tags)")
    if args.dry_run:
        print("(dry run — no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
