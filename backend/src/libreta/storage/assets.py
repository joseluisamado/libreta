from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path, PurePosixPath

from libreta.errors import AssetNotFoundError, InvalidPathError, PageNotFoundError
from libreta.storage.paths import normalize_page_path, page_to_file


def _validate_segments(raw: str) -> list[str]:
    if not raw or raw.startswith("/"):
        raise InvalidPathError(f"asset path must be relative and non-empty: {raw!r}")
    parts = raw.split("/")
    for p in parts:
        if not p or p in {".", ".."} or p.startswith("."):
            raise InvalidPathError(f"invalid asset segment {p!r} in {raw!r}")
        if "\x00" in p:
            raise InvalidPathError("null byte in path")
    if raw.endswith(".md"):
        raise InvalidPathError("markdown pages are served via /pages, not /assets")
    return parts


def resolve_asset(content_dir: Path, raw: str) -> Path:
    """Resolve a raw asset path under the content dir.

    The path must stay strictly inside ``content_dir`` after symlink resolution.
    """
    parts = _validate_segments(raw)
    base = content_dir.resolve()
    candidate = (content_dir.joinpath(*parts)).resolve()
    if base not in candidate.parents and candidate != base:
        raise InvalidPathError("asset path escapes content directory")
    if not candidate.is_file():
        raise AssetNotFoundError(raw)
    return candidate


# ── upload ──────────────────────────────────────────────────────────────


_FILENAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_filename(raw: str) -> str:
    """Reduce an arbitrary upload filename to a safe page-local asset name.

    Strips any directory components, replaces unsafe runs with ``-``, drops
    leading dots, lowercases the extension. Refuses ``.md`` outright.
    """
    name = PurePosixPath(raw).name
    name = name.lstrip(".")
    if not name:
        raise InvalidPathError("empty filename after sanitization")
    cleaned = _FILENAME_SAFE.sub("-", name).strip("-")
    if not cleaned:
        raise InvalidPathError(f"filename {raw!r} contains no usable characters")
    if cleaned.lower().endswith(".md"):
        raise InvalidPathError("cannot upload markdown files as assets")
    if "\x00" in cleaned:
        raise InvalidPathError("null byte in filename")
    return cleaned


def page_directory(content_dir: Path, raw_path: str) -> Path:
    """Return the directory that owns the page's attachments.

    For an index page (``foo/index.md``) the directory is ``foo/``.
    For a leaf page (``foo.md``) the directory is the parent folder.
    Raises ``PageNotFoundError`` if the page does not yet exist on disk.
    """
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)
    if not file.exists():
        # Allow attachments next to a synthesised directory page (a folder
        # with children but no index.md) — use the directory itself.
        dir_path = content_dir / "pages" / Path(*page.parts)
        if dir_path.is_dir():
            return dir_path
        raise PageNotFoundError(raw_path)
    return file.parent


def _unique_filename(directory: Path, base_name: str) -> str:
    """Return a filename in *directory* that doesn't collide with anything there.

    If ``photo.jpg`` is taken, returns ``photo-2.jpg``, then ``photo-3.jpg``, etc.
    """
    if not (directory / base_name).exists():
        return base_name
    stem = PurePosixPath(base_name).stem
    suffix = PurePosixPath(base_name).suffix
    n = 2
    while (directory / f"{stem}-{n}{suffix}").exists():
        n += 1
    return f"{stem}-{n}{suffix}"


def _kind_for(content_type: str | None, filename: str) -> str:
    if content_type and content_type.startswith("image/"):
        return "image"
    ext = PurePosixPath(filename).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}:
        return "image"
    return "file"


class UploadResult:
    __slots__ = ("deduped", "filename", "kind", "rel_path", "sha256", "size")

    def __init__(
        self,
        *,
        filename: str,
        size: int,
        sha256: str,
        kind: str,
        rel_path: str,
        deduped: bool,
    ) -> None:
        self.filename = filename
        self.size = size
        self.sha256 = sha256
        self.kind = kind
        self.rel_path = rel_path
        self.deduped = deduped


def _store_asset_sync(
    content_dir: Path,
    raw_page: str,
    raw_filename: str,
    data: bytes,
    content_type: str | None,
) -> UploadResult:
    directory = page_directory(content_dir, raw_page)
    name = sanitize_filename(raw_filename)
    sha = hashlib.sha256(data).hexdigest()

    # Dedupe: if any existing file in this directory has identical bytes,
    # reuse that filename rather than writing a new copy.
    for existing in directory.iterdir():
        if not existing.is_file() or existing.suffix == ".md":
            continue
        if existing.stat().st_size != len(data):
            continue
        if hashlib.sha256(existing.read_bytes()).hexdigest() == sha:
            rel = str(existing.relative_to(content_dir))
            return UploadResult(
                filename=existing.name,
                size=len(data),
                sha256=sha,
                kind=_kind_for(content_type, existing.name),
                rel_path=rel,
                deduped=True,
            )

    final_name = _unique_filename(directory, name)
    target = directory / final_name
    target.write_bytes(data)
    rel = str(target.relative_to(content_dir))
    return UploadResult(
        filename=final_name,
        size=len(data),
        sha256=sha,
        kind=_kind_for(content_type, final_name),
        rel_path=rel,
        deduped=False,
    )


async def store_asset(
    content_dir: Path,
    raw_page: str,
    raw_filename: str,
    data: bytes,
    content_type: str | None,
) -> UploadResult:
    return await asyncio.to_thread(
        _store_asset_sync, content_dir, raw_page, raw_filename, data, content_type
    )
