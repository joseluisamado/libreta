from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from libreta.errors import (
    PageNotFoundError,
    WatchedFileOutsideRootError,
    WatchedFolderNotAccessibleError,
    WatchedLabelNotFoundError,
)
from libreta.models import OtherFile, PageNode, PageRead
from libreta.storage import pagefile

logger = logging.getLogger(__name__)

WATCHED_CONFIG_FILENAME = ".meta/watched.json"


# ---------------------------------------------------------------------------
# Config persistence (watched-specific)
# ---------------------------------------------------------------------------


def load_watched_config_sync(content_dir: Path) -> list[dict[str, Any]]:
    config_path = content_dir / WATCHED_CONFIG_FILENAME
    if not config_path.exists():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict) and "label" in e and "path" in e]
    except (json.JSONDecodeError, OSError):
        logger.warning("watched config corrupt, treating as empty", exc_info=True)
        return []


async def load_watched_config(content_dir: Path) -> list[dict[str, Any]]:
    return await asyncio.to_thread(load_watched_config_sync, content_dir)


def save_watched_config_sync(content_dir: Path, folders: list[dict[str, Any]]) -> None:
    config_path = content_dir / WATCHED_CONFIG_FILENAME
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(folders, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


async def save_watched_config(content_dir: Path, folders: list[dict[str, Any]]) -> None:
    return await asyncio.to_thread(save_watched_config_sync, content_dir, folders)


# ---------------------------------------------------------------------------
# Path resolution & validation (watched-specific)
# ---------------------------------------------------------------------------


def resolve_watched_file_sync(content_dir: Path, label: str, raw_path: str) -> tuple[Path, Path]:
    """Return (watched_root, resolved_file_path) after validating containment."""
    config = load_watched_config_sync(content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        raise WatchedLabelNotFoundError(label)

    watched_root = Path(entry["path"]).expanduser().resolve()
    try:
        root_exists = watched_root.exists()
    except OSError as exc:
        raise WatchedFolderNotAccessibleError(str(watched_root)) from exc
    if not root_exists:
        raise WatchedFolderNotAccessibleError(str(watched_root))

    # Validate the raw path segments (empty path = root). Sidecar dirs like
    # ".page.md/" must remain reachable; pagefile.validate_path_segments allows
    # them and blocks only well-known sensitive prefixes (.git, .ssh, .libreta).
    if raw_path:
        pagefile.validate_path_segments(raw_path)

    candidate = (watched_root / raw_path).resolve() if raw_path else watched_root

    try:
        candidate.relative_to(watched_root)
    except ValueError as exc:
        raise WatchedFileOutsideRootError(raw_path) from exc

    return watched_root, candidate


async def resolve_watched_file(content_dir: Path, label: str, raw_path: str) -> tuple[Path, Path]:
    return await asyncio.to_thread(resolve_watched_file_sync, content_dir, label, raw_path)


# ---------------------------------------------------------------------------
# Tree walk (delegates to pagefile)
# ---------------------------------------------------------------------------


async def walk_watched_tree(
    watched_root: Path,
    max_depth: int | None = None,
) -> list[PageNode]:
    return await asyncio.to_thread(pagefile.walk_tree, watched_root, max_depth)


async def walk_watched_children(
    watched_root: Path, raw_path: str
) -> tuple[list[PageNode], list[OtherFile]]:
    return await asyncio.to_thread(pagefile.walk_children, watched_root, raw_path)


# ---------------------------------------------------------------------------
# Read & write (delegates to pagefile)
# ---------------------------------------------------------------------------


async def read_watched_page(watched_root: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(pagefile.read_page_file, watched_root, raw_path)


async def write_watched_page(watched_root: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    return await asyncio.to_thread(pagefile.write_page_file, watched_root, raw_path, body)


# ---------------------------------------------------------------------------
# Folder & page lifecycle (watched-specific: no git)
# ---------------------------------------------------------------------------


def _create_watched_folder_sync(watched_root: Path, raw_path: str) -> None:
    dir_path = (watched_root / raw_path).resolve()
    try:
        dir_path.relative_to(watched_root)
    except ValueError:
        raise WatchedFileOutsideRootError(raw_path)
    if dir_path.exists():
        raise FileExistsError(str(dir_path))
    dir_path.mkdir(parents=True)
    (dir_path / ".gitkeep").write_text("")


async def create_watched_folder(watched_root: Path, raw_path: str) -> None:
    await asyncio.to_thread(_create_watched_folder_sync, watched_root, raw_path)


def _delete_watched_page_sync(watched_root: Path, raw_path: str) -> None:
    raw_target = watched_root / raw_path
    suffix = Path(raw_path).suffix.lower()
    md_file = raw_target if suffix == ".md" else raw_target.with_suffix(".md")
    dir_path = watched_root / raw_path

    try:
        raw_target.resolve().relative_to(watched_root.resolve())
    except ValueError:
        raise WatchedFileOutsideRootError(raw_path)

    if suffix and suffix != ".md" and raw_target.is_file():
        raw_target.unlink()
        return

    if md_file.is_file():
        sidecar = md_file.parent / f".{md_file.name}"
        md_file.unlink()
        if sidecar.is_dir():
            for f in sidecar.rglob("*"):
                if f.is_file():
                    f.unlink()
            sidecar.rmdir()
    elif dir_path.is_dir():
        gitkeep = dir_path / ".gitkeep"
        if gitkeep.is_file():
            gitkeep.unlink()
        contents = [p for p in dir_path.iterdir() if not p.name.startswith(".")]
        if contents:
            raise OSError(f"Directory not empty: {raw_path}")
        for p in dir_path.iterdir():
            if p.is_file():
                p.unlink()
        dir_path.rmdir()
    else:
        raise PageNotFoundError(raw_path)


async def delete_watched_page(watched_root: Path, raw_path: str) -> None:
    await asyncio.to_thread(_delete_watched_page_sync, watched_root, raw_path)
