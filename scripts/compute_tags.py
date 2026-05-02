"""Compute tags for every page that doesn't already have them.

Walks ``data/content/pages/``. For each ``.md`` file with no ``tags`` (or empty
``tags``) in frontmatter, derives 3–5 tags by scoring terms via TF-IDF across
the corpus and writes them back. Idempotent: pages that already have tags are
left alone.

Run via:

    uv run python scripts/compute_tags.py [--dry-run] [--force]

Flags:
    --dry-run   Print the computed tags without writing.
    --force     Overwrite existing tags (default: skip pages that already have any).
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAGES = PROJECT_ROOT / "data" / "content" / "pages"

MAX_TAGS = 5
MIN_TAGS = 2
MIN_TERM_LEN = 3
MAX_TERM_LEN = 24

# Common English + DokuWiki/markdown noise. Keep small; let TF-IDF do most of
# the work. Anything truly common will get penalised by document frequency.
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy",
    "did", "its", "let", "put", "say", "she", "too", "use", "any", "this",
    "that", "with", "from", "have", "more", "your", "they", "them", "what",
    "when", "will", "into", "than", "then", "some", "just", "like", "also",
    "only", "very", "most", "such", "even", "much", "each", "many", "make",
    "made", "over", "back", "down", "still", "after", "before", "where",
    "while", "which", "would", "could", "should", "their", "there", "these",
    "those", "other", "about", "between", "because", "through", "during",
    "https", "http", "www", "com", "org", "net", "html", "png", "jpg", "jpeg",
    "gif", "svg", "pdf", "zip", "txt", "doc", "code", "block", "image",
    "imported", "page", "pages", "title", "tags", "created", "updated",
    "wiki", "doku", "see", "etc", "via", "per", "yes", "let", "lets",
    "using", "used", "uses", "use", "thing", "things", "stuff", "really",
}

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9_-]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def strip_markup(text: str) -> str:
    """Remove fenced code, inline code, and link/image markup so they don't dominate."""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)  # images
    text = re.sub(r"\[[^\]]*\]\([^)]+\)", " ", text)  # links
    text = re.sub(r"https?://\S+", " ", text)
    return text


def heading_terms(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            out.extend(tokenize(stripped.lstrip("#").strip()))
    return out


def title_terms(meta: dict[str, object]) -> list[str]:
    title = meta.get("title")
    if not title:
        return []
    return tokenize(str(title))


def good_term(t: str) -> bool:
    if t in STOPWORDS:
        return False
    if len(t) < MIN_TERM_LEN or len(t) > MAX_TERM_LEN:
        return False
    if t.isdigit():
        return False
    return True


def iter_md_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.md")):
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing tags (default: skip pages that have any)")
    args = parser.parse_args()

    pages_dir: Path = args.pages.resolve()
    if not pages_dir.is_dir():
        print(f"pages dir not found: {pages_dir}", file=sys.stderr)
        return 2

    files = list(iter_md_files(pages_dir))
    if not files:
        print("no pages found")
        return 0

    # Pass 1: tokenize each page (with boosting for headings + title).
    # Boost = duplicate the term in the bag so its TF goes up.
    HEADING_BOOST = 3
    TITLE_BOOST = 4

    docs: list[tuple[Path, frontmatter.Post, Counter[str]]] = []
    df: Counter[str] = Counter()  # document frequency

    for f in files:
        try:
            post = frontmatter.load(f)
        except Exception as e:  # noqa: BLE001 — keep going on bad pages
            print(f"  warn: failed to parse {f.relative_to(pages_dir)}: {e}", file=sys.stderr)
            continue

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
        docs.append((f, post, tf))
        for term in tf:
            df[term] += 1

    n_docs = len(docs)
    if n_docs == 0:
        print("no readable pages")
        return 0

    # Pass 2: score and write.
    written = 0
    skipped = 0
    for f, post, tf in docs:
        existing = post.metadata.get("tags") or []
        # Treat the lone "imported" placeholder (added by the DokuWiki importer)
        # as if no real tags exist yet — overwrite without --force.
        is_placeholder = isinstance(existing, list) and set(existing) <= {"imported"}
        if existing and not is_placeholder and not args.force:
            skipped += 1
            continue

        # TF-IDF: score term = tf * log(N / df)
        scores: list[tuple[str, float]] = []
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df[term] + 1)) + 1
            scores.append((term, count * idf))
        scores.sort(key=lambda x: (-x[1], x[0]))

        chosen: list[str] = []
        seen_stems: set[str] = set()
        for term, _ in scores:
            # de-dup near-stems (e.g. "python" vs "pythons")
            stem = term.rstrip("s")
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            chosen.append(term)
            if len(chosen) >= MAX_TAGS:
                break

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
