"""Tests for SSH-key label editing (rename).

Key material is write-only; only the label is mutable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from libreta.errors import SshKeyNotFoundError
from libreta.storage import ssh as store

# A minimal but plausible PEM body (>= 64 chars; passes _validate_key).
_PEM = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + "a" * 80 + "\n-----END OPENSSH PRIVATE KEY-----\n"


def test_rename_changes_label_only(tmp_path: Path) -> None:
    key = store.add_key_sync(tmp_path, "old label", _PEM)
    updated = store.update_key_label_sync(tmp_path, key.id, "new label")
    assert updated.label == "new label"
    # id and fingerprint are stable across a rename.
    assert updated.id == key.id
    assert updated.fingerprint == key.fingerprint

    listed = store.list_keys_sync(tmp_path)
    assert [(k.id, k.label) for k in listed] == [(key.id, "new label")]
    # Key material is untouched and still loadable.
    assert store.load_private_key_sync(tmp_path, key.id) == _PEM


def test_rename_missing_key_raises(tmp_path: Path) -> None:
    with pytest.raises(SshKeyNotFoundError):
        store.update_key_label_sync(tmp_path, "nope", "x")


def test_ssh_credentials_dispatch_on_allowed_types(tmp_path: Path) -> None:
    """The SSH credentials callback must honor allowed_types.

    libgit2 may probe for the username first (USERNAME in allowed_types)
    before asking for the key (SSH_KEY). Returning a Keypair during the
    username phase raises "invalid credential type" against some remotes —
    so the username phase must return a Username instead. Regression guard.
    """
    import pygit2

    key = store.add_key_sync(tmp_path, "deploy", _PEM)
    cb = store.make_callbacks(tmp_path, key.id)

    # Username phase: must hand back a Username (not a Keypair).
    cred = cb.credentials(
        "ssh://git@example.com/repo.git",
        None,
        int(pygit2.enums.CredentialType.USERNAME),
    )
    assert isinstance(cred, pygit2.Username)

    # Key phase: must hand back the Keypair.
    cred = cb.credentials(
        "ssh://git@example.com/repo.git",
        "git",
        int(pygit2.enums.CredentialType.SSH_KEY),
    )
    assert isinstance(cred, pygit2.Keypair)


def test_ssh_credentials_rejects_non_ssh_transport(tmp_path: Path) -> None:
    """An ssh_key_id against an https:// remote fails with a clear error.

    libgit2's HTTP transport offers neither USERNAME nor SSH_KEY in
    allowed_types; without this guard the user sees a bare "invalid
    credential type". Guard against the scheme/auth mismatch instead.
    """
    import pygit2

    from libreta.errors import SshKeyInvalidError

    key = store.add_key_sync(tmp_path, "deploy", _PEM)
    cb = store.make_callbacks(tmp_path, key.id)

    with pytest.raises(SshKeyInvalidError, match="SSH URL"):
        cb.credentials(
            "https://example.com/repo.git",
            None,
            int(pygit2.enums.CredentialType.USERPASS_PLAINTEXT),
        )


def test_ssh_credentials_username_from_url_preferred(tmp_path: Path) -> None:
    """During the username phase, the URL's username wins over the 'git' default."""
    import pygit2

    key = store.add_key_sync(tmp_path, "deploy", _PEM)
    cb = store.make_callbacks(tmp_path, key.id)

    cred = cb.credentials(
        "ssh://deploy@example.com/repo.git",
        "deploy",
        int(pygit2.enums.CredentialType.USERNAME),
    )
    assert isinstance(cred, pygit2.Username)
