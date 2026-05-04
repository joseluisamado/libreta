"""Tests for the watched folder feature."""

import json
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app


@pytest.fixture
def client_with_watchers(content_dir: Path) -> TestClient:
    """Test client with a content_dir already set up as a git repo."""
    pygit2.init_repository(str(content_dir))
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(content_dir=content_dir)
    return TestClient(app)


@pytest.fixture
def watched_fixture(tmp_path: Path) -> Path:
    """Create a temporary directory with some markdown files for watching."""
    root = tmp_path / "ext-wiki"
    root.mkdir()
    (root / "readme.md").write_text(
        '---\ntitle: "Readme"\n---\n\n# Readme\n\nHello world.\n', encoding="utf-8"
    )
    sub = root / "notes"
    sub.mkdir()
    (sub / "todo.md").write_text(
        '---\ntitle: "Todo"\ntags: [chore]\n---\n\n# Todo\n\n- [ ] thing\n', encoding="utf-8"
    )
    (sub / "journal.md").write_text(
        '---\ntitle: "Journal"\ntags: [personal]\n---\n\n# Journal\n\nToday was good.\n',
        encoding="utf-8",
    )
    # A file without frontmatter
    (root / "plain.md").write_text("# Plain\n\nNo frontmatter here.\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Folder list / add / remove
# ---------------------------------------------------------------------------


def test_list_folders_empty(client_with_watchers: TestClient) -> None:
    r = client_with_watchers.get("/api/v1/watch/folders")
    assert r.status_code == 200
    assert r.json() == []


def test_add_and_list_folders(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    r = client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "mywiki"
    assert body["exists"] is True

    r2 = client_with_watchers.get("/api/v1/watch/folders")
    assert r2.status_code == 200
    folders = r2.json()
    assert len(folders) == 1
    assert folders[0]["label"] == "mywiki"


def test_add_folder_invalid_label(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    r = client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "bad label!", "path": str(watched_fixture)},
    )
    assert r.status_code == 422


def test_add_folder_nonexistent_path(client_with_watchers: TestClient) -> None:
    r = client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "ghost", "path": "/does/not/exist/anywhere"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "ghost"
    assert body["exists"] is False


def test_add_duplicate_label(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    assert r.status_code == 409


def test_remove_folder(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.delete("/api/v1/watch/folders/mywiki")
    assert r.status_code == 204

    r2 = client_with_watchers.get("/api/v1/watch/folders")
    assert r2.json() == []


def test_remove_nonexistent_label(client_with_watchers: TestClient) -> None:
    r = client_with_watchers.delete("/api/v1/watch/folders/nope")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


def test_get_watched_tree(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/tree")
    assert r.status_code == 200
    nodes = r.json()
    paths = {n["path"] for n in nodes}
    assert "readme" in paths
    assert "plain" in paths
    assert "notes" in paths
    notes = next(n for n in nodes if n["path"] == "notes")
    assert notes["is_directory"] is True
    child_paths = {c["path"] for c in notes["children"]}
    assert "notes/todo" in child_paths
    assert "notes/journal" in child_paths


def test_watched_tree_skips_hidden(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    (watched_fixture / ".hidden.md").write_text("# secret\n", encoding="utf-8")
    (watched_fixture / ".hidden_dir").mkdir()
    (watched_fixture / ".hidden_dir" / "file.md").write_text("# nope\n", encoding="utf-8")

    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/tree")
    assert r.status_code == 200
    paths = {n["path"] for n in r.json()}
    assert ".hidden" not in paths
    assert ".hidden_dir" not in paths


def test_watched_tree_skips_non_md(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    (watched_fixture / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/tree")
    assert r.status_code == 200
    paths = {n["path"] for n in r.json()}
    assert "image" not in paths  # .png is not .md


# ---------------------------------------------------------------------------
# Read page
# ---------------------------------------------------------------------------


def test_read_watched_page_with_frontmatter(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/readme")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Readme"
    assert "Hello world." in body["body"]


def test_read_watched_page_without_frontmatter(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/plain")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Plain"
    assert "No frontmatter here." in body["body"]


def test_read_watched_page_not_found(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/does-not-exist")
    assert r.status_code == 404


def test_read_watched_page_label_not_found(client_with_watchers: TestClient) -> None:
    r = client_with_watchers.get("/api/v1/watch/nolabel/anything")
    assert r.status_code == 404


def test_read_watched_page_traversal_blocked(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.get("/api/v1/watch/mywiki/../../../etc/passwd")
    assert r.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Write page
# ---------------------------------------------------------------------------


def test_write_watched_new_page(client_with_watchers: TestClient, watched_fixture: Path) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.put(
        "/api/v1/watch/mywiki/newfile",
        json={"body": "# New\n\nFresh content."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Newfile"
    assert "Fresh content." in body["body"]

    # Verify on disk
    written = watched_fixture / "newfile.md"
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "Fresh content." in content
    assert "title: Newfile" in content


def test_write_watched_update_existing(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.put(
        "/api/v1/watch/mywiki/readme",
        json={"body": "# Updated\n\nChanged."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Readme"  # preserved from existing frontmatter

    written = watched_fixture / "readme.md"
    content = written.read_text(encoding="utf-8")
    assert "Changed." in content
    assert "title: Readme" in content


def test_write_watched_preserves_frontmatter(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.put(
        "/api/v1/watch/mywiki/notes/todo",
        json={"body": "# Todo\n\n- [x] thing"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "chore" in body["meta"]["tags"]

    written = watched_fixture / "notes" / "todo.md"
    content = written.read_text(encoding="utf-8")
    assert "tags:" in content
    assert "chore" in content


def test_write_watched_no_frontmatter_file(
    client_with_watchers: TestClient, watched_fixture: Path
) -> None:
    """Updating a file with no existing frontmatter adds title/created/updated."""
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    r = client_with_watchers.put(
        "/api/v1/watch/mywiki/plain",
        json={"body": "# Plain\n\nUpdated content."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Plain"
    assert body["meta"]["created"] is not None
    assert body["meta"]["updated"] is not None

    written = watched_fixture / "plain.md"
    content = written.read_text(encoding="utf-8")
    assert "title: Plain" in content


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def test_config_persisted_to_disk(
    client_with_watchers: TestClient, content_dir: Path, watched_fixture: Path
) -> None:
    client_with_watchers.post(
        "/api/v1/watch/folders",
        json={"label": "mywiki", "path": str(watched_fixture)},
    )
    config_path = content_dir / ".meta" / "watched.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["label"] == "mywiki"

    # Remove and verify config updated
    client_with_watchers.delete("/api/v1/watch/folders/mywiki")
    data2 = json.loads(config_path.read_text(encoding="utf-8"))
    assert data2 == []
