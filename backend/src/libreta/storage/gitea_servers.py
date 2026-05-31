"""Gitea-server credential store.

A "Gitea server" is a remembered credential group: a base URL, a username,
and a personal access token. Sources imported from the server reference it by
id and resolve the token at git-op time, so rotating the token in one place
updates every source.

Storage mirrors the SSH-key store (``storage/ssh.py``):

- ``<gitea_servers_dir>/index.json`` holds the non-secret metadata.
- ``<gitea_servers_dir>/<id>`` holds the raw token, chmod 0600.

The token is never returned over the API — callers that need it use
``load_token`` / ``load_token_sync`` on the backend only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from libreta.errors import GiteaServerAlreadyExistsError, GiteaServerNotFoundError
from libreta.models import GiteaServerResponse

logger = logging.getLogger(__name__)

_INDEX_FILENAME = "index.json"


def _index_path(servers_dir: Path) -> Path:
    return servers_dir / _INDEX_FILENAME


def _load_index_sync(servers_dir: Path) -> list[dict[str, Any]]:
    path = _index_path(servers_dir)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except (json.JSONDecodeError, OSError):
        logger.warning("gitea server index corrupt", exc_info=True)
    return []


def _save_index_sync(servers_dir: Path, entries: list[dict[str, Any]]) -> None:
    servers_dir.mkdir(parents=True, exist_ok=True)
    _index_path(servers_dir).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _token_file(servers_dir: Path, server_id: str) -> Path:
    return servers_dir / server_id


def _normalize_base_url(base_url: str) -> str:
    # Strip a trailing slash and any trailing /api so callers can paste either
    # the dashboard URL or an API URL.
    url = base_url.strip().rstrip("/")
    if url.endswith("/api"):
        url = url[: -len("/api")]
    return url


# ---------------------------------------------------------------------------
# Public API (sync, wrapped async below)
# ---------------------------------------------------------------------------


def list_servers_sync(servers_dir: Path) -> list[GiteaServerResponse]:
    return [
        GiteaServerResponse(
            id=e["id"],
            label=e["label"],
            base_url=e["base_url"],
            username=e["username"],
        )
        for e in _load_index_sync(servers_dir)
    ]


def add_server_sync(
    servers_dir: Path,
    label: str,
    base_url: str,
    username: str,
    token: str,
) -> GiteaServerResponse:
    base_url = _normalize_base_url(base_url)
    index = _load_index_sync(servers_dir)
    if any(e["base_url"] == base_url and e["username"] == username for e in index):
        raise GiteaServerAlreadyExistsError(
            f"server {base_url} for user {username!r} already exists"
        )

    server_id = str(uuid.uuid4())
    token_file = _token_file(servers_dir, server_id)
    servers_dir.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    # Token material must not be world-readable.
    os.chmod(token_file, stat.S_IRUSR | stat.S_IWUSR)

    entry = {"id": server_id, "label": label, "base_url": base_url, "username": username}
    index.append(entry)
    _save_index_sync(servers_dir, index)
    return GiteaServerResponse(id=server_id, label=label, base_url=base_url, username=username)


def remove_server_sync(servers_dir: Path, server_id: str) -> None:
    index = _load_index_sync(servers_dir)
    if not any(e["id"] == server_id for e in index):
        raise GiteaServerNotFoundError(server_id)
    token_file = _token_file(servers_dir, server_id)
    if token_file.exists():
        token_file.unlink()
    _save_index_sync(servers_dir, [e for e in index if e["id"] != server_id])


def get_server_sync(servers_dir: Path, server_id: str) -> dict[str, Any]:
    index = _load_index_sync(servers_dir)
    entry = next((e for e in index if e["id"] == server_id), None)
    if entry is None:
        raise GiteaServerNotFoundError(server_id)
    return entry


def load_token_sync(servers_dir: Path, server_id: str) -> str:
    if not any(e["id"] == server_id for e in _load_index_sync(servers_dir)):
        raise GiteaServerNotFoundError(server_id)
    token_file = _token_file(servers_dir, server_id)
    if not token_file.exists():
        raise GiteaServerNotFoundError(f"token file missing for {server_id}")
    return token_file.read_text(encoding="utf-8")


def load_credentials_sync(servers_dir: Path, server_id: str) -> tuple[str, str]:
    """Return (username, token) for *server_id*. Used to build clone auth."""
    entry = get_server_sync(servers_dir, server_id)
    token = load_token_sync(servers_dir, server_id)
    return entry["username"], token


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------


async def list_servers(servers_dir: Path) -> list[GiteaServerResponse]:
    return await asyncio.to_thread(list_servers_sync, servers_dir)


async def add_server(
    servers_dir: Path,
    label: str,
    base_url: str,
    username: str,
    token: str,
) -> GiteaServerResponse:
    return await asyncio.to_thread(add_server_sync, servers_dir, label, base_url, username, token)


async def remove_server(servers_dir: Path, server_id: str) -> None:
    return await asyncio.to_thread(remove_server_sync, servers_dir, server_id)


async def get_server(servers_dir: Path, server_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(get_server_sync, servers_dir, server_id)


async def load_credentials(servers_dir: Path, server_id: str) -> tuple[str, str]:
    return await asyncio.to_thread(load_credentials_sync, servers_dir, server_id)
