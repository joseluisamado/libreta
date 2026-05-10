from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
import stat
import uuid
from pathlib import Path
from typing import Any

import pygit2

from libreta.errors import SshKeyAlreadyExistsError, SshKeyInvalidError, SshKeyNotFoundError
from libreta.models import SshKeyResponse

logger = logging.getLogger(__name__)

_INDEX_FILENAME = "index.json"


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------


def _index_path(keys_dir: Path) -> Path:
    return keys_dir / _INDEX_FILENAME


def _load_index_sync(keys_dir: Path) -> list[dict[str, Any]]:
    path = _index_path(keys_dir)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except (json.JSONDecodeError, OSError):
        logger.warning("ssh key index corrupt", exc_info=True)
    return []


def _save_index_sync(keys_dir: Path, entries: list[dict[str, Any]]) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    _index_path(keys_dir).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _key_file(keys_dir: Path, key_id: str) -> Path:
    return keys_dir / key_id


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _fingerprint(private_key_pem: str) -> str:
    """Return a SHA-256 fingerprint of the raw key bytes (hex, 16 chars)."""
    digest = hashlib.sha256(private_key_pem.encode()).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Public API (sync, wrapped async below)
# ---------------------------------------------------------------------------


def list_keys_sync(keys_dir: Path) -> list[SshKeyResponse]:
    return [
        SshKeyResponse(id=e["id"], label=e["label"], fingerprint=e["fingerprint"])
        for e in _load_index_sync(keys_dir)
    ]


def add_key_sync(keys_dir: Path, label: str, private_key_pem: str) -> SshKeyResponse:
    _validate_key(private_key_pem)
    index = _load_index_sync(keys_dir)
    fingerprint = _fingerprint(private_key_pem)
    if any(e["fingerprint"] == fingerprint for e in index):
        raise SshKeyAlreadyExistsError(f"key with fingerprint {fingerprint} already exists")

    key_id = str(uuid.uuid4())
    key_file = _key_file(keys_dir, key_id)
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_file.write_text(private_key_pem, encoding="utf-8")
    # Restrict permissions — key material should not be world-readable
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)

    entry = {"id": key_id, "label": label, "fingerprint": fingerprint}
    index.append(entry)
    _save_index_sync(keys_dir, index)
    return SshKeyResponse(id=key_id, label=label, fingerprint=fingerprint)


def remove_key_sync(keys_dir: Path, key_id: str) -> None:
    index = _load_index_sync(keys_dir)
    if not any(e["id"] == key_id for e in index):
        raise SshKeyNotFoundError(key_id)
    key_file = _key_file(keys_dir, key_id)
    if key_file.exists():
        key_file.unlink()
    _save_index_sync(keys_dir, [e for e in index if e["id"] != key_id])


def load_private_key_sync(keys_dir: Path, key_id: str) -> str:
    index = _load_index_sync(keys_dir)
    if not any(e["id"] == key_id for e in index):
        raise SshKeyNotFoundError(key_id)
    key_file = _key_file(keys_dir, key_id)
    if not key_file.exists():
        raise SshKeyNotFoundError(f"key file missing for {key_id}")
    return key_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# pygit2 RemoteCallbacks factory
# ---------------------------------------------------------------------------


def make_callbacks(
    keys_dir: Path,
    key_id: str | None,
    http_username: str | None = None,
    http_password: str | None = None,
) -> pygit2.RemoteCallbacks:
    """Return a RemoteCallbacks for SSH key or HTTP basic auth."""
    if http_username and http_password:
        userpass = pygit2.UserPass(http_username, http_password)

        class _HttpCallbacks(pygit2.RemoteCallbacks):
            def credentials(
                self,
                url: str,
                username_from_url: str | None,
                allowed_types: int,
            ) -> pygit2.UserPass:
                return userpass

            def certificate_check(
                self,
                certificate: object,
                valid: bool,
                host: bytes | str,
            ) -> bool:
                # v1 caveat: no known-hosts pinning yet. We log the host so
                # operators can spot unexpected changes; multi-user mode
                # (M6) will introduce proper TOFU/known-hosts. See
                # docs/SECURITY-REVIEW.md "Known limitations".
                logger.info("git remote host=%r certificate.valid=%s", host, valid)
                return True

        return _HttpCallbacks()

    if key_id is None:
        return pygit2.RemoteCallbacks()

    private_key_pem = load_private_key_sync(keys_dir, key_id)

    import stat as _stat
    import tempfile
    import weakref

    # Write key to a temp file; pygit2.Keypair requires a file path.
    # delete=False because the file must outlive this function scope; we
    # register a finalizer on the callbacks instance so the tempfile is
    # cleaned up when the operation finishes.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".key")
    with os.fdopen(tmp_fd, "w") as f:
        f.write(private_key_pem)
    os.chmod(tmp_path, _stat.S_IRUSR | _stat.S_IWUSR)
    keypair = pygit2.Keypair("git", None, tmp_path, "")

    def _cleanup(path: str = tmp_path) -> None:
        with contextlib.suppress(OSError):
            os.unlink(path)

    class _SshCallbacks(pygit2.RemoteCallbacks):
        def credentials(
            self,
            url: str,
            username_from_url: str | None,
            allowed_types: int,
        ) -> pygit2.Keypair:
            return keypair

        def certificate_check(
            self,
            certificate: object,
            valid: bool,
            host: bytes | str,
        ) -> bool:
            # v1 caveat: no known-hosts pinning yet. We log the host so
            # operators can spot unexpected changes; multi-user mode (M6)
            # will introduce proper TOFU/known-hosts. See
            # docs/SECURITY-REVIEW.md "Known limitations".
            logger.info("git remote host=%r certificate.valid=%s", host, valid)
            return True

    cb = _SshCallbacks()
    weakref.finalize(cb, _cleanup)
    return cb


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------


async def list_keys(keys_dir: Path) -> list[SshKeyResponse]:
    return await asyncio.to_thread(list_keys_sync, keys_dir)


async def add_key(keys_dir: Path, label: str, private_key_pem: str) -> SshKeyResponse:
    return await asyncio.to_thread(add_key_sync, keys_dir, label, private_key_pem)


async def remove_key(keys_dir: Path, key_id: str) -> None:
    return await asyncio.to_thread(remove_key_sync, keys_dir, key_id)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_key(pem: str) -> None:
    stripped = pem.strip()
    if not (stripped.startswith("-----BEGIN") or stripped.startswith("-----")):
        # Accept raw base64 too — but require it to be non-trivial
        try:
            base64.b64decode(stripped, validate=True)
        except Exception as exc:
            raise SshKeyInvalidError("private key does not look like PEM or base64") from exc
    if len(stripped) < 64:
        raise SshKeyInvalidError("private key too short")
