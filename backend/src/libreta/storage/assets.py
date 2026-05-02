from __future__ import annotations

from pathlib import Path

from libreta.errors import AssetNotFoundError, InvalidPathError


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
