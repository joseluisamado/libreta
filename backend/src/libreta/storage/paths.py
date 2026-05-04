from pathlib import Path, PurePosixPath

from libreta.errors import InvalidPathError


def normalize_page_path(raw: str) -> PurePosixPath:
    """Validate and normalize a page path coming from the API.

    Rules: relative, no traversal, no hidden segments, no empty segments,
    no extension (the .md is added by the storage layer).
    """
    if not raw or raw.startswith("/"):
        raise InvalidPathError(f"page path must be relative and non-empty: {raw!r}")
    parts = raw.split("/")
    for p in parts:
        if not p or p in {".", ".."} or p.startswith("."):
            raise InvalidPathError(f"invalid path segment {p!r} in {raw!r}")
        if "\x00" in p:
            raise InvalidPathError("null byte in path")
    if raw.endswith(".md"):
        raise InvalidPathError("do not include the .md extension in page paths")
    return PurePosixPath(*parts)


def page_to_file(content_dir: Path, page: PurePosixPath) -> Path:
    """Resolve a normalized page path to its on-disk ``<page>.md`` file."""
    pages_root = content_dir / "pages"
    return pages_root.joinpath(*page.parts).with_suffix(".md")
