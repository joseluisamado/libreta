from __future__ import annotations

import logging
import os
import plistlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml
from frontmatter import Post

from libreta.errors import FrontmatterInBodyError, InvalidPathError, PageNotFoundError
from libreta.models import OtherFile, PageMeta, PageNode, PageRead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared data transforms
# ---------------------------------------------------------------------------


def parse_meta(raw: dict[str, Any], fallback_title: str) -> PageMeta:
    title = raw.get("title") or fallback_title
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return PageMeta(
        title=str(title),
        created=_as_datetime(raw.get("created")),
        updated=_as_datetime(raw.get("updated")),
        tags=[str(t) for t in tags],
        weight=_as_weight(raw.get("weight")),
    )


def _as_weight(value: Any) -> int | None:
    """Coerce a frontmatter ``weight`` to an int, or ``None`` if unusable.

    Bad input (non-integer, non-numeric string, ``None``) is treated as absent
    rather than raising, so a malformed weight never breaks a page load or
    reorders unrelated pages — the page just falls back to filename sort. Bools
    are rejected explicitly (YAML ``true``/``false`` are ``int`` subclasses in
    Python but are not meaningful weights). Negative values are allowed: they
    sort ahead of positive ones, which is a legitimate "pin to top" use.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# Managed frontmatter keys a caller may set through the write ``meta`` channel.
# ``created``/``updated`` are deliberately excluded — the writer owns those
# timestamps; letting a request set them would let a client rewrite history.
_SETTABLE_META_KEYS = frozenset({"title", "tags", "weight"})


def sanitize_page_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Validate/coerce a caller-supplied ``meta`` dict for :func:`write_page_file`.

    Only the keys in :data:`_SETTABLE_META_KEYS` pass through; unknown keys and
    the writer-owned timestamps are dropped silently (a caller can't stomp
    ``created``/``updated``). Values are coerced to their canonical shapes:

    - ``weight`` → int via :func:`_as_weight`; malformed → ``None``, which
      *clears* an existing weight (an explicit ``weight: null`` request).
    - ``tags`` → list of strings.
    - ``title`` → non-empty string, else dropped (fall back to existing/derived).

    Returns a dict safe to pass as ``extra_meta``. Never raises on bad values —
    frontmatter is best-effort, not a validation gate.
    """
    if not meta:
        return {}
    out: dict[str, Any] = {}
    if "weight" in meta:
        # Present-but-unset (weight: null / "") clears; otherwise coerce.
        out["weight"] = _as_weight(meta["weight"])
    if "tags" in meta:
        tags = meta["tags"]
        if not isinstance(tags, list):
            tags = [tags] if tags not in (None, "") else []
        out["tags"] = [str(t) for t in tags]
    if "title" in meta:
        title = meta["title"]
        if isinstance(title, str) and title.strip():
            out["title"] = title
    return out


def _body_looks_like_frontmatter(body: str) -> bool:
    """True if *body* opens with what looks like a YAML frontmatter block.

    Distinguishes a stray frontmatter fence (a caller mistake) from a legitimate
    leading thematic break (``---`` horizontal rule). A frontmatter block is an
    opening ``---`` line *followed by a closing ``---`` fence* later in the text;
    a lone ``---`` with no closing fence is a horizontal rule and is allowed.
    Leading blank lines before the opening fence are tolerated.
    """
    lines = body.splitlines()
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines) or lines[idx].strip() != "---":
        return False
    # An opening fence: is there a closing fence on a later line?
    return any(line.strip() in {"---", "..."} for line in lines[idx + 1 :])


def beautify_stem(stem: str) -> str:
    """Turn a filename stem into a human-readable label for sidebar / listings.

    Hyphens and underscores become spaces; case is preserved (NOT title-cased,
    since title-casing mangles acronyms like ``APT`` → ``Apt``). Strips runs
    of whitespace so ``foo---bar`` reads as ``foo bar``, not ``foo   bar``.
    """
    out = stem.replace("-", " ").replace("_", " ")
    return " ".join(out.split())


def read_page_head(file: Path, fallback_title: str) -> tuple[int | None, str]:
    """Read a markdown file's sidebar metadata in a single pass: ``(weight, title)``.

    The tree walk needs two things per page — its ``weight`` (frontmatter) and
    its sidebar label (first body H1, else *fallback_title*). Both live in the
    head of the file, so this reads it **once** and stops at the first content
    line, rather than calling ``frontmatter.load`` twice (which each slurp and
    parse the *whole* file). This is the hot path for large folders.

    Parsing mirrors ``read_weight`` + ``read_h1_or_fallback``: only ``weight`` is
    pulled from the YAML block (via :func:`_as_weight`, so malformed → ``None``),
    and the title is the first ATX ``# `` heading, giving up at the first
    non-blank non-H1 line. Any read/parse error degrades to ``(None, fallback)``.
    """
    weight: int | None = None
    try:
        with file.open("r", encoding="utf-8") as fh:
            it = iter(fh)
            # Skip leading blank lines (matches the tolerant frontmatter/H1
            # behaviour) to find the first significant line.
            first = _next_nonblank(it)
            if first is not None and first.strip() == "---":
                # Collect the YAML block *verbatim* (including any blank lines
                # inside it) up to the closing fence, then parse just that small
                # block rather than the whole file.
                fm_lines: list[str] = []
                for line in it:
                    if line.strip() in {"---", "..."}:
                        break
                    fm_lines.append(line)
                weight = _weight_from_yaml_block("".join(fm_lines))
                first = _next_nonblank(it)  # advance to first body content line
            # *first* now holds the first non-blank body line (or None). The H1
            # must be that first content line; anything else means "no title".
            title = fallback_title
            if first is not None:
                stripped = first.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    title = stripped[2:].strip() or fallback_title
            return weight, title
    except OSError:
        return None, fallback_title


def _next_nonblank(it: Any) -> str | None:
    """Return the next non-blank line from *it*, or ``None`` at end of file."""
    for raw in it:
        if raw.strip():
            return str(raw)
    return None


# One line of the trivial subset the fast path handles: blank, a whole-line
# comment, ``key: value`` at column 0, or an indented ``- item`` sequence entry.
#
# The key is restricted to word characters (so no quoting, no ``?`` explicit
# key, no flow indicator) and the ``:`` must be followed by a space or end of
# line — YAML reads ``title:5.5`` as the single scalar ``"title:5.5"``, not a
# mapping, which is exactly the kind of line that makes a *whole block* fail to
# parse. Values and sequence items rule out every construct whose meaning spans
# lines or needs real parsing: quotes, anchors/aliases/merge keys (``&`` ``*``),
# block scalars (``|`` ``>``), flow collections (``[`` ``{``) and ``#``.
#
# Sequence entries are allowed because ``tags:``/``aliases:`` lists are by far
# the most common frontmatter shape in a real wiki; they cannot introduce a
# top-level ``weight``, so they are irrelevant to the scan but must not force
# every tagged page down the slow path.
_VALUE = r"[^\s&*|>\[\]{}#'\"][^#\t\n]*?"
# A fully-quoted scalar on one line, e.g. ``title: "Locking: Optimistic"``. These
# are everywhere in real frontmatter (any title containing a colon needs them)
# and are inert for the scan, but only when the quote actually closes on the same
# line — an unterminated quote runs into the following lines and changes how the
# whole block parses, so it must not match here. Escapes are excluded rather than
# handled: rare enough to be worth a trip through the parser.
_QUOTED = r"\"[^\"\\\n]*\"|'[^'\\\n]*'"
# An anchored or aliased scalar on some *other* key, e.g. the
# ``created: &id001 <ts>`` / ``updated: *id001`` pair PyYAML emits for a repeated
# timestamp. These cannot define or redirect a top-level ``weight`` — a merge key
# (``<<:``) could, and is excluded by the key pattern below — so a block carrying
# them is still safe to scan, as long as its own ``weight`` line is a plain int.
_ANCHOR_VALUE = rf"[&*][\w.-]+(?: +{_VALUE})?"
# The anchor (``&name``) or alias (``*name``) marker in such a value.
_ANCHOR_REF_RE = re.compile(r": *([&*])([\w.-]+)")
_SIMPLE_LINE_RE = re.compile(
    rf" *(?:#.*)?"
    rf"| *- +(?:{_QUOTED}|{_VALUE}) *(?:#.*)?"
    rf"|\w[\w.-]*:(?: +(?:{_QUOTED}|{_VALUE}|{_ANCHOR_VALUE}))? *(?:#.*)?"
)
# A ``weight: <int>`` line at column 0: a bare integer, optional trailing
# comment. A float, a quoted value or anything else falls through to the parser.
_WEIGHT_LINE_RE = re.compile(r"^weight: +([+-]?\d+) *(?:#.*)?$", re.MULTILINE)
# Any ``weight`` key at column 0, used only to tell "no weight here" from "a
# weight the fast path could not read".
_WEIGHT_KEY_RE = re.compile(r"^weight:", re.MULTILINE)


def _is_simple_block(block: str) -> bool:
    """True when *block* is entirely blank/comment/``key: value``/``- item`` lines.

    This is the precondition for reading ``weight`` line-wise. It is deliberately
    whole-block rather than per-line: one malformed line (``title:5.5``) makes
    ``yaml.safe_load`` return a string instead of a dict, so the reference result
    for the *whole* block is ``None`` — and a fast path that read ``weight`` from
    a neighbouring well-formed line would disagree.

    Sequence entries must also keep a consistent indent within one run, since
    YAML rejects a block whose items step in and out, and such a block likewise
    parses to ``None`` rather than to its well-formed lines.
    """
    seq_indent: int | None = None
    anchors: set[str] = set()
    aliases: set[str] = set()
    for line in block.splitlines():
        if _SIMPLE_LINE_RE.fullmatch(line) is None:
            return False
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            indent = len(line) - len(stripped)
            if seq_indent is None:
                seq_indent = indent
            elif indent != seq_indent:
                return False
        elif stripped and not stripped.startswith("#"):
            # A mapping key ends the current sequence run.
            seq_indent = None
        marker = _ANCHOR_REF_RE.search(line)
        if marker is not None:
            (anchors if marker.group(1) == "&" else aliases).add(marker.group(2))
    # An alias with no anchor to resolve makes the whole document fail to parse,
    # which the scan cannot tell from a well-formed block; hand those to YAML.
    return aliases <= anchors


def _weight_from_yaml_block(block: str) -> int | None:
    """Extract ``weight`` from a small YAML frontmatter block. Never raises.

    ``yaml.safe_load`` is the authority here, but it is also, by a wide margin,
    the single most expensive thing the tree walk does: on a 1100-page wiki it
    was ~3.0s of a ~3.8s full walk (78%), spent building a throwaway document
    tree for every page just to read one integer.

    So try a line-wise fast path first, and fall back to the real parser the
    moment the block looks like anything other than plain ``key: value`` lines.
    The fast path only ever *skips* YAML when it has found a top-level
    ``weight: <int>``, or proved there is no top-level ``weight`` key at all, in
    a block with no multi-document/anchor syntax — so the fallback, not the
    regex, remains responsible for correctness on anything unusual.
    """
    if not block.strip():
        return None
    if _is_simple_block(block):
        keys = _WEIGHT_KEY_RE.findall(block)
        if not keys:
            # No ``weight`` key: nothing for the parser to find.
            return None
        # A duplicate key is legal YAML and the *last* one wins. Only trust the
        # scan when every ``weight`` line parsed as an integer, so a trailing
        # ``weight:`` (null) or ``weight: '5'`` still reaches the real parser.
        matches = _WEIGHT_LINE_RE.findall(block)
        if len(matches) == len(keys):
            return _as_weight(matches[-1])
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return _as_weight(data.get("weight"))


def read_weight(file: Path) -> int | None:
    """Read the ``weight`` frontmatter key from a markdown file, if any.

    Thin wrapper over :func:`read_page_head` (single-pass reader). Returns the
    parsed integer weight, or ``None`` when absent, malformed, or unreadable.
    """
    weight, _ = read_page_head(file, "")
    return weight


def sidebar_sort_key(weight: int | None, name: str) -> tuple[bool, int, str]:
    """Ordering key for a folder's children in the sidebar / tree.

    Weighted children come first, in ascending weight; ties (equal or absent
    weight) break by case-folded filename. Concretely the key is
    ``(weight is None, weight or 0, name.casefold())``:

    - ``weight is None`` is ``False`` (0) for weighted pages and ``True`` (1)
      for unweighted, so *any* weighted page sorts ahead of *every* unweighted
      one — the documented mixed-folder rule.
    - among weighted pages, lower ``weight`` wins; equal weights fall through
      to the filename tie-break, so duplicate weights are stable, not an error.
    - among unweighted pages the weight fields are equal, so they order purely
      by filename — identical to the pre-weight behaviour.
    """
    return (weight is None, weight or 0, name.casefold())


def read_h1_or_fallback(file: Path, fallback: str) -> str:
    """Sidebar / tree label for a markdown file.

    Reads the first H1 (``# `` heading) from the body. If absent or the file
    is unreadable, returns *fallback*. Frontmatter ``title:`` is deliberately
    NOT consulted here — the sidebar should reflect what the user sees when
    they open the file, which is the body's H1.

    Thin wrapper over :func:`read_page_head` so there is a single head-parsing
    implementation; the tree walk calls ``read_page_head`` directly to get the
    weight and title from one file read.
    """
    _, title = read_page_head(file, fallback)
    return title


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


_FORBIDDEN_HIDDEN_PREFIXES = (".git", ".ssh", ".libreta")


def validate_path_segments(raw_path: str) -> None:
    if not raw_path:
        return
    for part in raw_path.split("/"):
        if not part or part in {".", ".."}:
            raise InvalidPathError(f"invalid path segment {part!r} in {raw_path!r}")
        if "\x00" in part:
            raise InvalidPathError("null byte in path")
        # Sidecar dirs start with '.' (e.g. '.page.md/') and must remain
        # accessible. Block well-known sensitive hidden segments instead.
        lower = part.lower()
        if any(lower.startswith(prefix) for prefix in _FORBIDDEN_HIDDEN_PREFIXES):
            raise InvalidPathError(f"forbidden path segment {part!r}")


# ---------------------------------------------------------------------------
# Read & write page files
# ---------------------------------------------------------------------------


def resolve_page_source_file(root: Path, raw_path: str) -> Path:
    """Resolve a page path to its on-disk source file, for raw download.

    Mirrors :func:`read_page_file`'s resolution (``.md`` is implied when the
    path has no suffix) but returns the *file itself* so it can be streamed
    byte-identically. Refuses directories and missing pages. The returned path
    is guaranteed to stay strictly inside *root*.
    """
    validate_path_segments(raw_path)
    base = root.resolve()
    file = (root / raw_path).resolve()
    actual = file.with_suffix(".md") if not file.suffix else file
    if base not in actual.parents:
        raise InvalidPathError("page path escapes content directory")
    if not actual.is_file():
        raise PageNotFoundError(raw_path)
    return actual


def read_page_file(root: Path, raw_path: str) -> PageRead:
    """Read a page from *root* at *raw_path*.

    - ``.md`` / ``.html`` / ``.txt`` → parsed with frontmatter
    - binary files (PDF, images, etc.) → stub PageRead with empty body
    - directory → synthesized empty directory page
    - missing → ``PageNotFoundError``
    """
    file = root / raw_path
    fallback_title = file.name.replace("-", " ").replace("_", " ").title()

    actual = file.with_suffix(".md") if not file.suffix else file
    if actual.exists():
        if actual.is_dir():
            return PageRead(
                path=raw_path,
                meta=PageMeta(title=fallback_title),
                body="",
            )
        suffix = actual.suffix.lower()
        if suffix in {".md", ".html", ".txt"}:
            post = frontmatter.load(actual)
            return PageRead(
                path=raw_path,
                meta=parse_meta(post.metadata, fallback_title),
                body=post.content,
            )
        # Binary or unsupported — stub for viewer routing
        return PageRead(
            path=raw_path,
            meta=PageMeta(title=fallback_title),
            body="",
        )

    if file.is_dir():
        return PageRead(
            path=raw_path,
            meta=PageMeta(title=fallback_title),
            body="",
        )

    raise PageNotFoundError(raw_path)


def write_page_file(
    root: Path, raw_path: str, body: str, extra_meta: dict[str, Any] | None = None
) -> tuple[PageRead, str]:
    """Write a page at *root* / *raw_path*.

    Preserves existing frontmatter (all keys) and sets updated=now. *extra_meta*
    is merged on top of preserved metadata so callers can set managed fields
    (e.g. ``weight``, ``tags``) — this is the *only* channel for frontmatter.
    Frontmatter must never be embedded in *body*: a body opening with a ``---``
    fence raises :class:`FrontmatterInBodyError` rather than being persisted as
    visible page content.

    Returns ``(PageRead, verb)`` where *verb* is ``"create"`` or ``"update"``.
    """
    if _body_looks_like_frontmatter(body):
        raise FrontmatterInBodyError(
            "page body starts with a '---' frontmatter fence; set frontmatter "
            "via the meta channel, not in the body"
        )

    file = root / raw_path
    fallback_title = file.name.replace("-", " ").replace("_", " ").title()

    existing = file.with_suffix(".md") if not file.suffix else file
    existed = existing.exists()

    existing_meta: dict[str, Any] = {}
    if existed:
        try:
            post = frontmatter.load(existing)
            existing_meta = dict(post.metadata)
        except (OSError, ValueError):
            pass

    now = datetime.now(UTC)
    # Preserve every existing frontmatter key (ARCHITECTURE.md: "Unknown
    # frontmatter keys are preserved on roundtrip — Libreta reads what it knows
    # and leaves the rest alone"). Only the keys Libreta actively manages are
    # overridden below; anything the user or another tool put in the frontmatter
    # (e.g. ``weight`` for sidebar ordering) survives untouched.
    metadata: dict[str, Any] = dict(existing_meta)
    metadata["title"] = existing_meta.get("title", fallback_title)
    metadata["updated"] = now
    if "created" not in existing_meta:
        metadata["created"] = now

    if extra_meta:
        metadata.update(extra_meta)

    existing.parent.mkdir(parents=True, exist_ok=True)
    post = Post(body, **metadata)
    existing.write_text(frontmatter.dumps(post), encoding="utf-8")

    verb = "update" if existed else "create"

    result = PageRead(
        path=raw_path,
        meta=PageMeta(
            title=str(metadata["title"]),
            created=metadata["created"] if isinstance(metadata["created"], datetime) else now,
            updated=now,
            tags=list(metadata.get("tags", [])),
            weight=_as_weight(metadata.get("weight")),
        ),
        body=body,
    )
    return result, verb


def patch_page_meta(root: Path, raw_path: str, extra_meta: dict[str, Any]) -> tuple[PageRead, str]:
    """Set managed frontmatter on an existing page without touching its body.

    Reads the page's current body, then rewrites it via :func:`write_page_file`
    with *extra_meta* merged over the preserved frontmatter. This is the
    body-safe channel for edits that only change metadata (e.g. adjusting
    ``weight`` from the folder listing): the caller doesn't need — and shouldn't
    have to round-trip — the page body just to set a frontmatter key.

    *extra_meta* is caller-supplied and must already be sanitized (see
    :func:`sanitize_page_meta`). Only markdown pages carry frontmatter; a
    non-``.md`` target (or a missing file) raises :class:`PageNotFoundError`.
    Returns ``(PageRead, verb)`` like :func:`write_page_file` (always
    ``"update"`` here — the page must already exist).
    """
    file = root / raw_path
    actual = file.with_suffix(".md") if not file.suffix else file
    if not actual.is_file() or actual.suffix.lower() != ".md":
        raise PageNotFoundError(raw_path)
    post = frontmatter.load(actual)
    return write_page_file(root, raw_path, post.content, extra_meta)


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


_NOEXT_TEXT_NAMES = {
    "version",
    "license",
    "licence",
    "makefile",
    "dockerfile",
    "changelog",
    "contributors",
    "authors",
    "readme",
    "copying",
    "news",
    "todo",
    "install",
    "gemfile",
    "rakefile",
    "procfile",
    "vagrantfile",
    "caddyfile",
    "crontab",
    "flake.lock",
}

# Non-page kinds that have a dedicated viewer and a preview thumbnail, so they
# are listed as first-class children ("in this folder") rather than in the
# "other files" bucket. "binary" is the only non-previewable _classify_other
# result and stays in other_files.
_PREVIEWABLE_KINDS = frozenset({"image", "drawio", "text", "html", "video", "ebook"})

# E-book / e-reader formats rendered client-side by foliate-js (see the
# frontend EbookView): EPUB, MOBI, Kindle KF8/AZW, FictionBook, and comic-book
# archives. All map to a single ``kind="ebook"``; foliate sniffs the concrete
# format itself, so the backend doesn't need to distinguish them.
_EBOOK_EXTS = (
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".kf8",
    ".prc",
    ".fb2",
    ".fbz",
    ".fb2.zip",
    ".cbz",
)


def _classify_other(name: str) -> str:
    """Classify a non-page file by extension."""
    lower = name.lower()
    if lower.endswith((".drawio.svg", ".drawio.png", ".drawio")):
        return "drawio"
    if lower.endswith(_EBOOK_EXTS):
        return "ebook"
    if lower.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".heic", ".heif")
    ):
        # HEIC/HEIF render natively only in Safari; other browsers show a
        # broken image (same as any unsupported asset). We don't decode them.
        return "image"
    # Video plays via the browser's native <video> element (no library).
    # Codec support is the browser's call; broadly mp4/webm/ogg work.
    if lower.endswith((".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v")):
        return "video"
    # macOS .webloc bookmark: a plist pointing at a URL. No viewer/thumbnail —
    # clicking it just opens the target URL (resolved in _read_webloc_url).
    if lower.endswith(".webloc"):
        return "weblink"
    # HTML is rendered (JS-stripped) in its own viewer, distinct from the
    # raw-source text viewer — see the frontend html viewer / R6.
    if lower.endswith((".html", ".htm")):
        return "html"
    if lower in _NOEXT_TEXT_NAMES:
        return "text"
    if lower.endswith(
        (
            ".txt",
            ".css",
            ".js",
            ".ts",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".log",
            ".xml",
            ".csv",
            ".py",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".h",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".tmpl",
            ".example",
            ".tsbuildinfo",
            ".plist",
            ".swift",
            ".entitlements",
            ".pbxproj",
            ".nix",
        )
    ):
        return "text"
    return "binary"


def _read_webloc_url(path: Path) -> str | None:
    """Extract the target URL from a macOS ``.webloc`` bookmark.

    A ``.webloc`` is a plist (XML or binary) with a top-level ``URL`` key.
    Returns the URL string, or ``None`` if the file is unreadable, malformed,
    or the URL isn't a safe http(s) link (we don't surface ``file:``/``javascript:``
    targets as clickable links).
    """
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        logger.warning("cannot read webloc %s", path)
        return None
    url = data.get("URL") if isinstance(data, dict) else None
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    return url


def _dir_has_renderable_child(dir_path: Path) -> bool:
    """Whether *dir_path* contains at least one entry the tree would render.

    Mirrors the child-classification in :func:`_build_tree`: a subdirectory,
    a ``.md`` page, a ``.pdf``, a previewable file, or a ``.webloc`` bookmark
    counts. Plain "other" files (binaries etc.) do *not* become tree nodes, so
    a folder holding only those reads as empty in the sidebar.

    Used at the depth-limit boundary to distinguish a *confirmed-empty* folder
    (emit ``children=[], has_more=False``) from a truncation stub (``has_more``)
    without recursing — one short-circuited ``scandir`` per boundary folder.
    """
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        return True
                except OSError:
                    continue
                lower = entry.name.lower()
                if lower.endswith(".md") or lower.endswith(".pdf"):
                    return True
                kind = _classify_other(entry.name)
                if kind == "weblink" or kind in _PREVIEWABLE_KINDS:
                    return True
    except OSError:
        logger.warning("cannot scan directory %s", dir_path)
    return False


# Node budget for the adaptive tree walk. A repo whose renderable-entry count
# fits in this many nodes is served whole (``max_depth=None``); anything larger
# falls back to a depth-limited walk with truncation stubs.
#
# Calibrated by measurement, not taste: a full walk costs ~0.11 ms and ~205
# bytes of JSON per node, both linear in node count. 4000 nodes is therefore
# ~440 ms and ~800 KiB on dev hardware — and the target box (a NanoPi) is
# several times slower, which is why this sits well below the point where a
# full walk stops being a win. For scale: a 1100-page wiki counts ~1100 and is
# served whole; a 75k-page one counts out in ~7 ms and stays lazy.
TREE_FULL_BUDGET = 4000


def count_renderable_entries(root: Path, budget: int) -> int:
    """Count renderable entries under *root*, abandoning the walk past *budget*.

    Used to decide whether a repo is small enough to serve as one complete tree.
    Deliberately much cheaper than :func:`walk_tree`: ``os.scandir`` only, with
    no file reads, no frontmatter parsing and no ``PageNode`` construction — the
    three things that make the real walk expensive. Counts directories and
    ``.md`` files, which is a close enough proxy for node count to size the
    decision (non-page leaf kinds are a small minority and only ever make the
    estimate conservative in the safe direction).

    Returns as soon as the running count exceeds *budget*, so the cost is
    bounded by the budget rather than by the size of the tree: a huge repo is
    rejected in milliseconds instead of being fully counted.
    """
    seen = 0
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir():
                            stack.append(Path(entry.path))
                            seen += 1
                        elif entry.name.lower().endswith(".md"):
                            seen += 1
                    except OSError:
                        continue
        except OSError:
            logger.warning("cannot scan directory %s", current)
            continue
        if seen > budget:
            return seen
    return seen


def _build_tree(
    dir_path: Path,
    url_prefix: str,
    max_depth: int | None = None,
    depth: int = 0,
) -> tuple[list[PageNode], list[OtherFile]]:
    """Recursive helper for ``walk_tree`` and ``walk_children``.

    Returns ``(nodes, other_files)`` where *nodes* are the children of
    *dir_path* and *other_files* are the non-page files in *dir_path*.
    """
    nodes: list[PageNode] = []
    other_entries: list[Path] = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
    except OSError:
        logger.warning("cannot list directory %s", dir_path)
        return nodes, []

    md_names: dict[str, Path] = {}
    dir_names: dict[str, Path] = {}
    pdf_files: list[Path] = []
    # Non-page files that have a dedicated viewer AND a thumbnail are
    # first-class children: they belong in the listing alongside pages/PDFs,
    # not in "other files". The kind comes from _classify_other. Everything
    # else (binary, etc.) stays in other_files.
    previewable_files: list[Path] = []
    # .webloc bookmarks: first-class clickable children, but with no thumbnail
    # or viewer (the click opens the target URL), so they're kept apart from
    # previewable_files.
    weblink_files: list[Path] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                dir_names[entry.name] = entry
            elif entry.suffix == ".md":
                md_names[entry.stem] = entry
            elif entry.suffix.lower() == ".pdf":
                pdf_files.append(entry)
            elif _classify_other(entry.name) == "weblink":
                weblink_files.append(entry)
            elif _classify_other(entry.name) in _PREVIEWABLE_KINDS:
                previewable_files.append(entry)
            else:
                other_entries.append(entry)
        except OSError:
            continue

    all_names: set[str] = set()
    all_names.update(md_names.keys())
    all_names.update(dir_names.keys())

    # A child's ``weight`` and sidebar title both come from the head of its
    # ``.md`` file. Read each file **once** here (weight + H1 title together) so
    # the sort key and the emitted PageNodes agree and we don't parse every file
    # twice. A directory without a matching ``.md`` (a plain folder) has no head
    # to read: weight ``None`` (filename order), title from the beautified stem.
    heads: dict[str, tuple[int | None, str]] = {
        name: (
            read_page_head(md_names[name], beautify_stem(name))
            if name in md_names
            else (None, beautify_stem(name))
        )
        for name in all_names
    }

    hit_max = max_depth is not None and depth >= max_depth

    for name in sorted(all_names, key=lambda n: sidebar_sort_key(heads[n][0], n)):
        md_file = md_names.get(name)
        sub_dir = dir_names.get(name)
        weight, head_title = heads[name]
        child_url = f"{url_prefix}/{name}" if url_prefix else name
        humanised = beautify_stem(name)
        md_filename = md_file.name if md_file else f"{name}.md"

        if hit_max and sub_dir:
            title = head_title if md_file else humanised
            # At the depth boundary we don't recurse, but a single cheap scan
            # tells us whether the folder is empty. A confirmed-empty folder is
            # emitted as a fully-loaded node (has_more=False) so the sidebar can
            # render it as empty; a folder with content stays a truncation stub.
            has_children = _dir_has_renderable_child(sub_dir)
            nodes.append(
                PageNode(
                    path=child_url,
                    title=title,
                    filename=md_filename if md_file else name,
                    is_directory=True,
                    children=[],
                    has_more=has_children,
                    weight=weight,
                )
            )
        else:
            children: list[PageNode] = []
            sub_other: list[OtherFile] = []
            if sub_dir:
                children, sub_other = _build_tree(sub_dir, child_url, max_depth, depth + 1)
            if md_file:
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=head_title,
                        filename=md_filename,
                        is_directory=bool(sub_dir),
                        children=children,
                        other_files=sub_other,
                        weight=weight,
                    )
                )
            else:
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=humanised,
                        filename=name,
                        is_directory=True,
                        children=children,
                        other_files=sub_other,
                        weight=weight,
                    )
                )

    for pdf in sorted(pdf_files, key=lambda p: p.name.casefold()):
        child_url = f"{url_prefix}/{pdf.name}" if url_prefix else pdf.name
        nodes.append(
            PageNode(
                path=child_url,
                title=beautify_stem(pdf.stem),
                filename=pdf.name,
                is_directory=False,
                children=[],
                kind="pdf",
            )
        )

    for pv in sorted(previewable_files, key=lambda p: p.name.casefold()):
        child_url = f"{url_prefix}/{pv.name}" if url_prefix else pv.name
        nodes.append(
            PageNode(
                path=child_url,
                title=beautify_stem(pv.stem),
                filename=pv.name,
                is_directory=False,
                children=[],
                kind=_classify_other(pv.name),  # image|drawio|text|html|video|ebook
            )
        )

    for wl in sorted(weblink_files, key=lambda p: p.name.casefold()):
        child_url = f"{url_prefix}/{wl.name}" if url_prefix else wl.name
        nodes.append(
            PageNode(
                path=child_url,
                title=beautify_stem(wl.stem),
                filename=wl.name,
                is_directory=False,
                children=[],
                kind="weblink",
                target=_read_webloc_url(wl),
            )
        )

    other = [
        OtherFile(
            name=entry.name,
            path=f"{url_prefix}/{entry.name}" if url_prefix else entry.name,
            kind=_classify_other(entry.name),
        )
        for entry in sorted(other_entries, key=lambda p: p.name.casefold())
    ]
    return nodes, other


def walk_tree(root: Path, max_depth: int | None = None) -> list[PageNode]:
    """Recursive tree walk from *root*. Returns a list of ``PageNode``.

    - ``.md`` files become page nodes (title from frontmatter)
    - directories become folder nodes with children
    - ``.pdf`` files become leaf nodes with ``kind="pdf"``
    - other files populate ``other_files`` on directory nodes
    - ``max_depth`` controls depth; truncated subtrees get ``has_more=True``
    """
    try:
        if not root.exists():
            return []
    except OSError:
        logger.warning("cannot access root %s", root)
        return []

    nodes, root_other = _build_tree(root, "", max_depth)
    # Attach root-level other files to a root directory node (e.g. "index")
    # so they appear when viewing the content root.
    if root_other:
        for node in nodes:
            if node.is_directory:
                node.other_files = root_other
                break
    return nodes


def resolve_tree_depth(
    root: Path, requested: int | None, budget: int = TREE_FULL_BUDGET
) -> int | None:
    """Pick the depth to walk *root* at: ``None`` (whole tree) or *requested*.

    A depth-limited tree is not free for the client: every folder the user has
    expanded past the cutoff arrives as a truncation stub and costs one extra
    HTTP round-trip to fill. Restoring a fully-expanded sidebar that way meant
    ~200 requests funnelled through the browser's 6-connection HTTP/1.1 limit —
    measurably more total work than simply serving the tree whole.

    So: probe the repo cheaply (:func:`count_renderable_entries`, bounded by
    *budget*) and, when it fits, walk it complete so the client needs no
    follow-up fetches at all. Large repos keep the depth limit, where lazy
    filling genuinely pays — a full walk there is seconds and tens of MiB.

    *requested* ``None`` already means "everything", so it short-circuits, and a
    *budget* of 0 or less disables the whole-tree path (always depth-limit).
    """
    if requested is None:
        return None
    if budget <= 0:
        return requested
    try:
        if not root.exists():
            return requested
    except OSError:
        return requested
    if count_renderable_entries(root, budget) <= budget:
        return None
    return requested


def walk_children(root: Path, raw_path: str) -> tuple[list[PageNode], list[OtherFile]]:
    """Return immediate children of *raw_path* within *root* (max_depth=1).

    Children are returned with full paths (rooted at the source/watched
    repo), matching the convention used by ``walk_tree`` so the frontend can
    merge them into the existing tree without any path rewriting.

    Also returns any non-page files in the directory so the caller can
    populate ``other_files`` on the parent node.
    """
    child_dir = (root / raw_path).resolve()
    try:
        child_dir.relative_to(root)
    except ValueError:
        return [], []
    if not child_dir.is_dir():
        return [], []
    return _build_tree(child_dir, raw_path, max_depth=1)


# ---------------------------------------------------------------------------
# Asset resolution
# ---------------------------------------------------------------------------


def resolve_asset(root: Path, raw_path: str) -> Path:
    """Resolve an asset file path within *root*.

    Validates containment, rejects ``.md`` files and path traversal.
    Returns the absolute ``Path`` to the asset.

    Asset references embedded in markdown are *page-relative* — a page-scoped
    attachment is ``.note.md/photo.png`` (the sidecar dir next to the page),
    with no ``pages/`` prefix, so the markdown stays portable. But a source
    repo with a top-level ``pages/`` directory stores that page (and its
    sidecar) under ``pages/`` on disk. Mirror :func:`page_to_file`: when the
    bare path doesn't resolve and *root* has a ``pages/`` subdir, retry there.
    """
    validate_path_segments(raw_path)
    suffix = Path(raw_path).suffix.lower()
    if suffix == ".md":
        raise InvalidPathError("markdown pages are not served via /assets")

    def _candidate(base: Path) -> Path | None:
        c = (base / raw_path).resolve()
        if root not in c.parents and c != root:
            raise InvalidPathError("asset path escapes root directory")
        return c if c.is_file() else None

    candidate = _candidate(root)
    if candidate is None:
        pages_dir = root / "pages"
        if not raw_path.startswith("pages/") and pages_dir.is_dir():
            candidate = _candidate(pages_dir)
    if candidate is None:
        raise PageNotFoundError(raw_path)
    return candidate
