from pathlib import Path

import pygit2
from fastapi.testclient import TestClient


def test_get_tree(client: TestClient) -> None:
    r = client.get("/api/v1/pages/tree")
    assert r.status_code == 200
    nodes = r.json()
    paths = {n["path"] for n in nodes}
    assert "index" in paths
    assert "recipes" in paths
    # When both recipes.md and recipes/ exist, they merge into one directory
    # node that carries the page's title and the directory's children.
    recipes = next(n for n in nodes if n["path"] == "recipes")
    assert recipes["is_directory"] is True
    child_paths = {c["path"] for c in recipes["children"]}
    assert "recipes/pizza-dough" in child_paths


def test_get_page_index(client: TestClient) -> None:
    r = client.get("/api/v1/pages/index")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Home"
    assert "Welcome." in body["body"]


def test_get_page_nested(client: TestClient) -> None:
    r = client.get("/api/v1/pages/recipes/pizza-dough")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Pizza Dough"
    assert "food" in body["meta"]["tags"]


def test_get_page_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/pages/does-not-exist")
    assert r.status_code == 404


def test_get_page_traversal_blocked(client: TestClient) -> None:
    r = client.get("/api/v1/pages/../etc/passwd")
    assert r.status_code in (400, 404)


def test_get_page_synthesises_bare_directory(client: TestClient, content_dir) -> None:  # type: ignore[no-untyped-def]
    # Create a directory with content but no <dir>.md.
    bare = content_dir / "pages" / "devel" / "bash"
    bare.mkdir(parents=True)
    (bare / "heredoc.md").write_text('---\ntitle: "Heredoc"\n---\n\nbody\n', encoding="utf-8")
    r = client.get("/api/v1/pages/devel/bash")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "devel/bash"
    assert body["meta"]["title"] == "Bash"
    assert body["body"] == ""


# ── PUT tests ──────────────────────────────────────────────────────────


def test_put_page_update(client: TestClient, content_dir: Path) -> None:
    r = client.put(
        "/api/v1/pages/recipes/pizza-dough",
        json={"body": "# Updated Pizza\n\nNew recipe.\n"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["body"] == "# Updated Pizza\n\nNew recipe.\n"
    assert body["meta"]["title"] == "Pizza Dough"
    assert "food" in body["meta"]["tags"]
    assert body["meta"]["updated"] is not None

    # Verify file on disk
    file = content_dir / "pages" / "recipes" / "pizza-dough.md"
    raw = file.read_text(encoding="utf-8")
    assert "# Updated Pizza" in raw
    assert "New recipe" in raw

    # Verify git commit was created
    repo = pygit2.Repository(str(content_dir))
    head = repo.head
    commit = repo[head.target]
    assert "update" in commit.message.lower()


def test_put_page_create(client: TestClient, content_dir: Path) -> None:
    r = client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nA classic.\n"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["body"] == "# Tiramisu\n\nA classic.\n"
    assert body["meta"]["title"] == "Tiramisu"
    assert body["meta"]["created"] is not None

    file = content_dir / "pages" / "recipes" / "tiramisu.md"
    assert file.exists()

    repo = pygit2.Repository(str(content_dir))
    head = repo.head
    commit = repo[head.target]
    assert "create" in commit.message.lower()


def test_put_page_traversal_blocked(client: TestClient) -> None:
    r = client.put(
        "/api/v1/pages/../etc/passwd",
        json={"body": "exploit"},
    )
    assert r.status_code in (400, 404)


def test_put_page_preserves_frontmatter(client: TestClient) -> None:
    r = client.put(
        "/api/v1/pages/recipes/pizza-dough",
        json={"body": "# Just the body\n"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["title"] == "Pizza Dough"
    assert "food" in body["meta"]["tags"]
    assert body["meta"]["created"] is not None


# ── Tag derivation tests ────────────────────────────────────────────────


def test_put_page_derives_tags_on_create(client: TestClient) -> None:
    r = client.put(
        "/api/v1/pages/guides/deployment",
        json={
            "body": (
                "# Deployment Guide\n\n"
                "This guide covers server deployment and configuration.\n\n"
                "## Server Setup\n\n"
                "Setting up the server requires careful configuration.\n\n"
                "## Deployment Steps\n\n"
                "Follow the deployment steps for production.\n"
            )
        },
    )
    assert r.status_code == 200
    body = r.json()
    tags = body["meta"]["tags"]
    assert isinstance(tags, list)
    assert len(tags) >= 2
    expected = {"server", "deployment", "configuration", "guide", "setup", "production", "steps"}
    assert len(set(tags) & expected) >= 1


def test_put_page_does_not_derive_tags_on_update(client: TestClient) -> None:
    r = client.put(
        "/api/v1/pages/recipes/pizza-dough",
        json={"body": "# A completely different topic\n\npython async server"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "food" in body["meta"]["tags"]
    assert "pizza" in body["meta"]["tags"]


# ── DELETE tests ───────────────────────────────────────────────────────


def test_delete_page(client: TestClient, content_dir: Path) -> None:
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nA classic.\n"},
    )
    r = client.delete("/api/v1/pages/recipes/tiramisu")
    assert r.status_code == 204
    assert r.text == ""

    file = content_dir / "pages" / "recipes" / "tiramisu.md"
    assert not file.exists()

    repo = pygit2.Repository(str(content_dir))
    head = repo.head
    commit = repo[head.target]
    assert "delete" in commit.message.lower()


def test_delete_page_not_found(client: TestClient) -> None:
    r = client.delete("/api/v1/pages/does-not-exist")
    assert r.status_code == 404


def test_delete_page_invalid_path(client: TestClient) -> None:
    r = client.delete("/api/v1/pages/../etc/passwd")
    assert r.status_code in (400, 404)


def test_delete_page_in_directory_with_siblings(client: TestClient, content_dir: Path) -> None:
    # Create a page inside recipes/ alongside pizza-dough.md
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nA classic.\n"},
    )
    r = client.delete("/api/v1/pages/recipes/tiramisu")
    assert r.status_code == 204
    # pizza-dough.md should still exist
    assert (content_dir / "pages" / "recipes" / "pizza-dough.md").exists()
    assert not (content_dir / "pages" / "recipes" / "tiramisu.md").exists()


def test_delete_bare_directory(client: TestClient, content_dir: Path) -> None:
    bare = content_dir / "pages" / "empty-folder"
    bare.mkdir(parents=True)

    r = client.delete("/api/v1/pages/empty-folder")
    assert r.status_code == 204
    assert not bare.exists()


def test_delete_bare_directory_not_empty(client: TestClient, content_dir: Path) -> None:
    bare = content_dir / "pages" / "stuff"
    bare.mkdir(parents=True)
    (bare / "notes.md").write_text("some notes", encoding="utf-8")

    r = client.delete("/api/v1/pages/stuff")
    assert r.status_code == 409


# ── MOVE tests ─────────────────────────────────────────────────────────


def test_move_page(client: TestClient, content_dir: Path) -> None:
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nA classic.\n"},
    )
    r = client.post(
        "/api/v1/pages/recipes/tiramisu/move",
        json={"new_path": "recipes/tiramisu-classic"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "recipes/tiramisu-classic"
    assert "A classic" in body["body"]

    assert client.get("/api/v1/pages/recipes/tiramisu").status_code == 404

    new = client.get("/api/v1/pages/recipes/tiramisu-classic")
    assert new.status_code == 200
    assert "A classic" in new.json()["body"]

    repo = pygit2.Repository(str(content_dir))
    head = repo.head
    commit = repo[head.target]
    assert "rename" in commit.message.lower()


def test_move_page_not_found(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/does-not-exist/move",
        json={"new_path": "somewhere-else"},
    )
    assert r.status_code == 404


def test_move_page_target_exists(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/move",
        json={"new_path": "index"},
    )
    assert r.status_code == 409


def test_move_page_invalid_path(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/move",
        json={"new_path": "../etc/passwd"},
    )
    assert r.status_code in (400, 404)
