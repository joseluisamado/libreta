from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from libreta.errors import AssetNotFoundError, InvalidPathError, PageNotFoundError
from libreta.storage import pagefile
from libreta.storage.paths import normalize_page_path, page_to_file

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def resolve_asset(content_dir: Path, raw: str) -> Path:
    """Resolve a raw asset path under the content dir.

    The path must stay strictly inside ``content_dir`` after symlink resolution.
    """
    pagefile.validate_path_segments(raw)
    if raw.endswith(".md"):
        raise InvalidPathError("markdown pages are served via /pages, not /assets")
    base = content_dir.resolve()
    candidate = (content_dir / raw).resolve()
    if base not in candidate.parents and candidate != base:
        raise InvalidPathError("asset path escapes content directory")
    if not candidate.is_file():
        raise AssetNotFoundError(raw)
    return candidate


# ── upload ──────────────────────────────────────────────────────────────


_FILENAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_filename(raw: str, *, allow_markdown: bool = False) -> str:
    """Reduce an arbitrary upload filename to a safe, path-local name.

    Strips any directory components, replaces unsafe runs with ``-``, drops
    leading dots, lowercases the extension. By default refuses ``.md``: a
    markdown file is a *page*, not an embeddable asset. Pass
    ``allow_markdown=True`` for folder uploads, where any file type is
    accepted as a first-class sibling file.
    """
    name = PurePosixPath(raw).name
    name = name.lstrip(".")
    if not name:
        raise InvalidPathError("empty filename after sanitization")
    cleaned = _FILENAME_SAFE.sub("-", name).strip("-")
    if not cleaned:
        raise InvalidPathError(f"filename {raw!r} contains no usable characters")
    if not allow_markdown and cleaned.lower().endswith(".md"):
        raise InvalidPathError("cannot upload markdown files as assets")
    if "\x00" in cleaned:
        raise InvalidPathError("null byte in filename")
    return cleaned


def _sidecar_dir(content_dir: Path, page: PurePosixPath) -> Path:
    """Return the sidecar directory for a page: ``<parent>/.<pagename>.md/``."""
    md_file = page_to_file(content_dir, page)
    sidecar_name = f".{md_file.name}"
    return md_file.parent / sidecar_name


def page_directory(content_dir: Path, raw_path: str) -> Path:
    """Return the sidecar directory that owns the page's attachments.

    Every page has a hidden sidecar directory (``.saml.md/`` for ``saml.md``)
    where its attachments live.  For synthesised directory pages (a folder
    with children but no ``.md`` file) the sidecar is derived from the
    hypothetical ``<dirname>.md`` path.
    """
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)
    if not file.exists():
        # Allow attachments for a synthesised directory page
        if str(page).startswith("pages/"):
            dir_path = content_dir / Path(*page.parts)
        else:
            dir_path = content_dir / "pages" / Path(*page.parts)
        if dir_path.is_dir():
            return _sidecar_dir(content_dir, page)
        raise PageNotFoundError(raw_path)
    return _sidecar_dir(content_dir, page)


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
    # Sidecar prefix for embedding in markdown: .<pagename>.md/
    sidecar_prefix = f"{directory.name}/"

    directory.mkdir(parents=True, exist_ok=True)

    # Dedupe: if any existing file in this sidecar has identical bytes,
    # reuse that filename rather than writing a new copy.
    for existing in directory.iterdir():
        if not existing.is_file() or existing.suffix == ".md":
            continue
        if existing.stat().st_size != len(data):
            continue
        if hashlib.sha256(existing.read_bytes()).hexdigest() == sha:
            rel = str(existing.relative_to(content_dir))
            return UploadResult(
                filename=sidecar_prefix + existing.name,
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
        filename=sidecar_prefix + final_name,
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


def _replace_asset_sync(
    content_dir: Path,
    raw_page: str,
    raw_filename: str,
    data: bytes,
    content_type: str | None,
) -> UploadResult:
    """Overwrite (or create) the file at ``<page-sidecar>/<raw_filename>``.

    Unlike ``store_asset`` this does not auto-uniquify the name — the caller is
    explicitly targeting an existing or chosen filename. Used by the diagram
    save flow, where a re-saved diagram must replace the bytes of the file
    whose name is already embedded in the markdown.
    """
    directory = page_directory(content_dir, raw_page)
    name = sanitize_filename(raw_filename)
    sha = hashlib.sha256(data).hexdigest()
    sidecar_prefix = f"{directory.name}/"

    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name

    if target.is_file() and target.read_bytes() == data:
        rel = str(target.relative_to(content_dir))
        return UploadResult(
            filename=sidecar_prefix + name,
            size=len(data),
            sha256=sha,
            kind=_kind_for(content_type, name),
            rel_path=rel,
            deduped=True,
        )

    target.write_bytes(data)
    rel = str(target.relative_to(content_dir))
    return UploadResult(
        filename=sidecar_prefix + name,
        size=len(data),
        sha256=sha,
        kind=_kind_for(content_type, name),
        rel_path=rel,
        deduped=False,
    )


async def replace_asset(
    content_dir: Path,
    raw_page: str,
    raw_filename: str,
    data: bytes,
    content_type: str | None,
) -> UploadResult:
    return await asyncio.to_thread(
        _replace_asset_sync, content_dir, raw_page, raw_filename, data, content_type
    )


# ── folder uploads ──────────────────────────────────────────────────────
#
# Unlike ``store_asset`` (page-scoped sidecar attachments), a folder upload
# writes the raw file as a *sibling* inside a folder — e.g. dropping
# ``report.pdf`` into ``Docs/`` lands it at ``pages/Docs/report.pdf`` where it
# shows up in the folder listing as a first-class file. There is no size cap:
# the file is streamed to disk in chunks so memory stays constant regardless of
# upload size (the >50MB warning is a client-side courtesy, not a server gate).


def _resolve_upload_dir(base_dir: Path, folder: str) -> Path:
    """Resolve and validate the on-disk folder that an upload targets.

    *folder* is a path relative to *base_dir* ("" means the repo root). The
    resolved directory must exist and stay strictly inside *base_dir*.
    """
    pagefile.validate_path_segments(folder)
    base = base_dir.resolve()
    target = (base_dir / folder).resolve() if folder else base
    if base != target and base not in target.parents:
        raise InvalidPathError("folder path escapes content directory")
    if not target.is_dir():
        raise PageNotFoundError(folder or "/")
    return target


async def store_folder_file(
    base_dir: Path,
    folder: str,
    raw_filename: str,
    read_chunk: Callable[[int], Awaitable[bytes]],
    *,
    repo_root: Path | None = None,
    chunk_size: int = 1024 * 1024,
) -> UploadResult:
    """Stream an uploaded file into *folder* as a sibling file.

    *base_dir* is the directory ``folder`` resolves against (``pages/`` for the
    main content repo, the repo root for a git source). *read_chunk* pumps the
    upload one chunk at a time so arbitrarily large files never sit fully in
    memory. ``rel_path`` on the result is relative to *repo_root* (defaulting to
    *base_dir*) so it's ready to hand to the git index.
    """
    root = repo_root if repo_root is not None else base_dir
    directory = await asyncio.to_thread(_resolve_upload_dir, base_dir, folder)
    name = sanitize_filename(raw_filename, allow_markdown=True)

    def _open() -> tuple[Path, object]:
        final_name = _unique_filename(directory, name)
        target = directory / final_name
        return target, target.open("wb")

    target, handle = await asyncio.to_thread(_open)
    hasher = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = await read_chunk(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
            await asyncio.to_thread(handle.write, chunk)  # type: ignore[attr-defined]
    except BaseException:
        await asyncio.to_thread(handle.close)  # type: ignore[attr-defined]
        target.unlink(missing_ok=True)
        raise
    await asyncio.to_thread(handle.close)  # type: ignore[attr-defined]

    if size == 0:
        target.unlink(missing_ok=True)
        raise InvalidPathError("empty upload")

    rel = str(target.relative_to(root))
    return UploadResult(
        filename=target.name,
        size=size,
        sha256=hasher.hexdigest(),
        kind=_kind_for(None, target.name),
        rel_path=rel,
        deduped=False,
    )
