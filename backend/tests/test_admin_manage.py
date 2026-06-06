"""Tests for admin-panel management features:

* archive-on-delete for git sources (rename clone in place, ``purge`` to
  delete outright; archived dirs ignored by the source-id scan)
* drag-reorder for git sources, Gitea servers, and watched folders
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app
from libreta.storage import sources as src_store
from libreta.storage.search import _list_source_ids


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    pygit2.init_repository(str(meta_dir))
    settings = Settings(
        meta_dir=meta_dir,
        repos_dir=tmp_path / "repos",
        ssh_keys_dir=tmp_path / "ssh",
        gitea_servers_dir=tmp_path / "gitea",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


def _make_clone(repos_dir: Path, source_id: str) -> Path:
    """Create a minimal cloned working tree with one committed file."""
    local = repos_dir / source_id
    local.mkdir(parents=True)
    repo = pygit2.init_repository(str(local), initial_head="main")
    (local / "page.md").write_text("# Hi\n", encoding="utf-8")
    repo.index.add_all()
    repo.index.write()
    tree = repo.index.write_tree()
    sig = pygit2.Signature("T", "t@example.com")
    repo.create_commit("HEAD", sig, sig, "init", tree, [])
    return local


# ---------------------------------------------------------------------------
# Archive-on-delete
# ---------------------------------------------------------------------------


def _register(meta_dir: Path, *ids: str) -> None:
    src_store.save_sources_sync(
        meta_dir, [{"id": i, "remote_url": f"http://x/{i}.git", "branch": "main"} for i in ids]
    )


def test_remove_source_archives_clone(tmp_path: Path) -> None:
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    _register(meta_dir, "work")
    _make_clone(repos_dir, "work")

    src_store.remove_source_sync(meta_dir, repos_dir, "work")

    assert not (repos_dir / "work").exists()
    archives = [d for d in repos_dir.iterdir() if d.name.startswith(".work_")]
    assert len(archives) == 1, "clone should be renamed to a dotted archive"
    assert (archives[0] / "page.md").read_text() == "# Hi\n", "content preserved"
    assert src_store.load_sources_sync(meta_dir) == []


def test_remove_source_purge_deletes_clone(tmp_path: Path) -> None:
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    _register(meta_dir, "work")
    _make_clone(repos_dir, "work")

    src_store.remove_source_sync(meta_dir, repos_dir, "work", purge=True)

    assert not (repos_dir / "work").exists()
    assert list(repos_dir.iterdir()) == [], "purge leaves nothing behind"


def test_remove_source_tolerates_missing_clone(tmp_path: Path) -> None:
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    _register(meta_dir, "orphan")  # registered but never cloned

    src_store.remove_source_sync(meta_dir, repos_dir, "orphan")  # must not raise
    assert src_store.load_sources_sync(meta_dir) == []


def test_archived_clone_not_seen_as_source(tmp_path: Path) -> None:
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    _make_clone(repos_dir, "live")
    _make_clone(repos_dir, ".work_20260606T101112Z")  # an archive shape

    assert _list_source_ids(repos_dir) == ["live"]


def test_delete_endpoint_purge_flag(client: TestClient, tmp_path: Path) -> None:
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    _make_clone(repos_dir, "work")
    src_store.save_sources_sync(
        tmp_path / "meta",
        [{"id": "work", "label": "Work", "remote_url": "http://x/work.git", "branch": "main"}],
    )

    assert client.delete("/api/v1/sources/work?purge=true").status_code == 204
    assert list(repos_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------


def test_reorder_sources(client: TestClient, tmp_path: Path) -> None:
    src_store.save_sources_sync(
        tmp_path / "meta",
        [
            {"id": "a", "label": "A", "remote_url": "http://x/a.git", "branch": "main"},
            {"id": "b", "label": "B", "remote_url": "http://x/b.git", "branch": "main"},
            {"id": "c", "label": "C", "remote_url": "http://x/c.git", "branch": "main"},
        ],
    )
    r = client.put("/api/v1/sources/order", json={"order": ["c", "a", "b"]})
    assert r.status_code == 204, r.text
    assert [s["id"] for s in client.get("/api/v1/sources").json()] == ["c", "a", "b"]


def test_reorder_sources_rejects_non_permutation(client: TestClient, tmp_path: Path) -> None:
    src_store.save_sources_sync(
        tmp_path / "meta",
        [{"id": "a", "label": "A", "remote_url": "http://x/a.git", "branch": "main"}],
    )
    assert client.put("/api/v1/sources/order", json={"order": ["a", "ghost"]}).status_code == 400


def _add_server(client: TestClient, label: str) -> str:
    r = client.post(
        "/api/v1/sources/gitea-servers",
        json={
            "label": label,
            "base_url": f"https://{label.lower()}.example.com",
            "username": "alice",
            "token": "tok",
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_reorder_gitea_servers(client: TestClient) -> None:
    s1 = _add_server(client, "One")
    s2 = _add_server(client, "Two")
    r = client.put("/api/v1/sources/gitea-servers/order", json={"order": [s2, s1]})
    assert r.status_code == 204, r.text
    assert [s["id"] for s in client.get("/api/v1/sources/gitea-servers").json()] == [s2, s1]


def test_reorder_watched_folders(client: TestClient, tmp_path: Path) -> None:
    for lbl in ("alpha", "beta"):
        d = tmp_path / lbl
        d.mkdir()
        assert (
            client.post("/api/v1/watch/folders", json={"label": lbl, "path": str(d)}).status_code
            == 201
        )
    r = client.put("/api/v1/watch/folders/order", json={"order": ["beta", "alpha"]})
    assert r.status_code == 204, r.text
    assert [f["label"] for f in client.get("/api/v1/watch/folders").json()] == ["beta", "alpha"]
