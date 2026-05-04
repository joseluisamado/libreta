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
    """Resolve a normalized page path to its on-disk ``<page>.md`` file.

    When the page path already starts with ``pages/`` (source repos that have
    a top-level pages directory) we resolve from *content_dir* directly.
    Otherwise, if *content_dir* contains a ``pages/`` subdirectory the path is
    rooted there. Flat repos use *content_dir* itself.
    """
    page_str = str(page)
    pages_dir = content_dir / "pages"
    if page_str.startswith("pages/"):
        return content_dir.joinpath(*page.parts).with_suffix(".md")
    if pages_dir.is_dir():
        return pages_dir.joinpath(*page.parts).with_suffix(".md")
    return content_dir.joinpath(*page.parts).with_suffix(".md")
