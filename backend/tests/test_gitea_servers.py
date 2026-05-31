"""Tests for the Gitea-server credential store.

Mirrors the SSH-key store: metadata in index.json, the token in a 0600
sibling file, never returned over the API surface.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from libreta.errors import GiteaServerAlreadyExistsError, GiteaServerNotFoundError
from libreta.storage import gitea_servers as store


def test_add_then_list_omits_token(tmp_path: Path) -> None:
    resp = store.add_server_sync(tmp_path, "Work", "https://git.example.com", "alice", "tok-123")
    assert resp.label == "Work"
    assert resp.base_url == "https://git.example.com"
    assert resp.username == "alice"
    # The response model has no token field at all.
    assert not hasattr(resp, "token")

    listed = store.list_servers_sync(tmp_path)
    assert [s.id for s in listed] == [resp.id]
    assert listed[0].base_url == "https://git.example.com"


def test_token_file_is_owner_only(tmp_path: Path) -> None:
    resp = store.add_server_sync(tmp_path, "Work", "https://git.example.com", "alice", "tok-123")
    token_file = tmp_path / resp.id
    assert token_file.read_text() == "tok-123"
    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_base_url_normalised(tmp_path: Path) -> None:
    # Trailing slash and a trailing /api are stripped so either paste works.
    a = store.add_server_sync(tmp_path, "A", "https://git.example.com/", "alice", "t")
    assert a.base_url == "https://git.example.com"
    b = store.add_server_sync(tmp_path, "B", "https://git.example.com/api", "bob", "t")
    assert b.base_url == "https://git.example.com"


def test_duplicate_same_url_and_user_rejected(tmp_path: Path) -> None:
    store.add_server_sync(tmp_path, "Work", "https://git.example.com", "alice", "t")
    with pytest.raises(GiteaServerAlreadyExistsError):
        store.add_server_sync(tmp_path, "Work2", "https://git.example.com", "alice", "t2")
    # A different user on the same server is allowed.
    store.add_server_sync(tmp_path, "WorkBob", "https://git.example.com", "bob", "t3")


def test_load_credentials_roundtrip(tmp_path: Path) -> None:
    resp = store.add_server_sync(tmp_path, "Work", "https://git.example.com", "alice", "secret")
    username, token = store.load_credentials_sync(tmp_path, resp.id)
    assert (username, token) == ("alice", "secret")


def test_remove_deletes_token_file(tmp_path: Path) -> None:
    resp = store.add_server_sync(tmp_path, "Work", "https://git.example.com", "alice", "t")
    token_file = tmp_path / resp.id
    assert token_file.exists()
    store.remove_server_sync(tmp_path, resp.id)
    assert not token_file.exists()
    assert store.list_servers_sync(tmp_path) == []


def test_missing_server_raises(tmp_path: Path) -> None:
    with pytest.raises(GiteaServerNotFoundError):
        store.remove_server_sync(tmp_path, "nope")
    with pytest.raises(GiteaServerNotFoundError):
        store.load_credentials_sync(tmp_path, "nope")
