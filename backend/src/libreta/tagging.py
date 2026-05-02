"""Reusable TF-IDF tag derivation for wiki pages.

Extracted from ``scripts/compute_tags.py`` so the save lifecycle can also call it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

# ── constants ───────────────────────────────────────────────────────────

MAX_TAGS = 5
MIN_TAGS = 2
MIN_TERM_LEN = 3
MAX_TERM_LEN = 24

HEADING_BOOST = 3
TITLE_BOOST = 4

# Common English + DokuWiki/markdown noise. Keep small; let TF-IDF do most of
# the work. Anything truly common will get penalised by document frequency.
STOPWORDS: set[str] = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "had",
    "her",
    "was",
    "one",
    "our",
    "out",
    "day",
    "get",
    "has",
    "him",
    "his",
    "how",
    "man",
    "new",
    "now",
    "old",
    "see",
    "two",
    "way",
    "who",
    "boy",
    "did",
    "its",
    "let",
    "put",
    "say",
    "she",
    "too",
    "use",
    "any",
    "this",
    "that",
    "with",
    "from",
    "have",
    "more",
    "your",
    "they",
    "them",
    "what",
    "when",
    "will",
    "into",
    "than",
    "then",
    "some",
    "just",
    "like",
    "also",
    "only",
    "very",
    "most",
    "such",
    "even",
    "much",
    "each",
    "many",
    "make",
    "made",
    "over",
    "back",
    "down",
    "still",
    "after",
    "before",
    "where",
    "while",
    "which",
    "would",
    "could",
    "should",
    "their",
    "there",
    "these",
    "those",
    "other",
    "about",
    "between",
    "because",
    "through",
    "during",
    "https",
    "http",
    "www",
    "com",
    "org",
    "net",
    "html",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "pdf",
    "zip",
    "txt",
    "doc",
    "code",
    "block",
    "image",
    "imported",
    "page",
    "pages",
    "title",
    "tags",
    "created",
    "updated",
    "wiki",
    "doku",
    "etc",
    "via",
    "per",
    "yes",
    "lets",
    "using",
    "used",
    "uses",
    "thing",
    "things",
    "stuff",
    "really",
}

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9_-]{2,}")


# ── tokenisation ────────────────────────────────────────────────────────


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def strip_markup(text: str) -> str:
    """Remove fenced code, inline code, and link/image markup."""
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
    return not t.isdigit()


# ── corpus + scoring ────────────────────────────────────────────────────


def build_corpus_df(content_dir: Path) -> tuple[Counter[str], int]:
    """Walk all .md files in the content directory, build a document-frequency counter.

    Returns (df_counter, n_docs).
    """
    from frontmatter import load as fm_load

    pages_dir = content_dir / "pages"
    df: Counter[str] = Counter()
    n_docs = 0

    for f in sorted(pages_dir.rglob("*.md")):
        try:
            post = fm_load(f)
        except Exception:
            continue

        body = strip_markup(post.content)
        tf = Counter(t for t in tokenize(body) if good_term(t))
        for t in heading_terms(post.content):
            if good_term(t):
                tf[t] += HEADING_BOOST
        for t in title_terms(post.metadata):
            if good_term(t):
                tf[t] += TITLE_BOOST

        for term in tf:
            df[term] += 1
        n_docs += 1

    return df, n_docs


def score_page(
    tf: Counter[str],
    df: Counter[str],
    n_docs: int,
) -> list[str]:
    """Score terms for a single page via TF-IDF and return the top tags."""
    scores: list[tuple[str, float]] = []
    for term, count in tf.items():
        idf = math.log((n_docs + 1) / (df[term] + 1)) + 1
        scores.append((term, count * idf))
    scores.sort(key=lambda x: (-x[1], x[0]))

    chosen: list[str] = []
    seen_stems: set[str] = set()
    for term, _ in scores:
        stem = term.rstrip("s")
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        chosen.append(term)
        if len(chosen) >= MAX_TAGS:
            break

    if len(chosen) < MIN_TAGS:
        return []

    return chosen
