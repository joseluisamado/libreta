from __future__ import annotations

import logging
import plistlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
from frontmatter import Post

from libreta.errors import InvalidPathError, PageNotFoundError
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
    )


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def beautify_stem(stem: str) -> str:
    """Turn a filename stem into a human-readable label for sidebar / listings.

    Hyphens and underscores become spaces; case is preserved (NOT title-cased,
    since title-casing mangles acronyms like ``APT`` → ``Apt``). Strips runs
    of whitespace so ``foo---bar`` reads as ``foo bar``, not ``foo   bar``.
    """
    out = stem.replace("-", " ").replace("_", " ")
    return " ".join(out.split())


def read_h1_or_fallback(file: Path, fallback: str) -> str:
    """Sidebar / tree label for a markdown file.

    Reads the first H1 (``# `` heading) from the body. If absent or the file
    is unreadable, returns *fallback*. Frontmatter ``title:`` is deliberately
    NOT consulted here — the sidebar should reflect what the user sees when
    they open the file, which is the body's H1.
    """
    try:
        post = frontmatter.load(file)
        body = post.content or ""
    except (OSError, ValueError):
        return fallback
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Match ATX H1: "# Heading" (one leading hash, then space, then text).
        # H2+ are skipped; setext headings (=== underline) are uncommon in
        # this codebase and the cost of supporting them isn't worth it.
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip() or fallback
        # Stop at first non-blank, non-H1 line — if the doc doesn't open
        # with an H1, treat it as having no title.
        return fallback
    return fallback


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

    Preserves existing frontmatter (title, created, tags) and sets updated=now.
    *extra_meta* is merged on top of preserved metadata so callers can inject
    auto-derived fields (e.g. tags on first save).

    Returns ``(PageRead, verb)`` where *verb* is ``"create"`` or ``"update"``.
    """
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
    metadata: dict[str, Any] = {
        "title": existing_meta.get("title", fallback_title),
        "updated": now,
    }
    if "created" in existing_meta:
        metadata["created"] = existing_meta["created"]
    else:
        metadata["created"] = now
    if "tags" in existing_meta:
        metadata["tags"] = existing_meta["tags"]

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
        ),
        body=body,
    )
    return result, verb


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
            "nix",
            "flake",
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

    hit_max = max_depth is not None and depth >= max_depth

    for name in sorted(all_names):
        md_file = md_names.get(name)
        sub_dir = dir_names.get(name)
        child_url = f"{url_prefix}/{name}" if url_prefix else name
        humanised = beautify_stem(name)
        md_filename = md_file.name if md_file else f"{name}.md"

        if hit_max and sub_dir:
            title = read_h1_or_fallback(md_file, humanised) if md_file else humanised
            nodes.append(
                PageNode(
                    path=child_url,
                    title=title,
                    filename=md_filename if md_file else name,
                    is_directory=True,
                    children=[],
                    has_more=True,
                )
            )
        else:
            children: list[PageNode] = []
            sub_other: list[OtherFile] = []
            if sub_dir:
                children, sub_other = _build_tree(sub_dir, child_url, max_depth, depth + 1)
            if md_file:
                title = read_h1_or_fallback(md_file, humanised)
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=title,
                        filename=md_filename,
                        is_directory=bool(sub_dir),
                        children=children,
                        other_files=sub_other,
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
