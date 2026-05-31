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
