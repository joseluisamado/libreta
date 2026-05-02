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
    assert r.status_code in (400, 404)  # FastAPI may normalize before our handler sees it


def test_get_page_synthesises_bare_directory(client: TestClient, content_dir) -> None:  # type: ignore[no-untyped-def]
    # Create a directory with content but no <dir>.md or index.md.
    bare = content_dir / "pages" / "devel" / "bash"
    bare.mkdir(parents=True)
    (bare / "heredoc.md").write_text('---\ntitle: "Heredoc"\n---\n\nbody\n', encoding="utf-8")
    r = client.get("/api/v1/pages/devel/bash")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "devel/bash"
    assert body["meta"]["title"] == "Bash"
    assert body["body"] == ""
    assert body["is_index"] is True


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
    # The body is embedded in the file after the frontmatter separator.
    # frontmatter.dumps may adjust trailing whitespace, so check containment.
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
    # created should be auto-set for new pages
    assert body["meta"]["created"] is not None

    # Verify file on disk
    file = content_dir / "pages" / "recipes" / "tiramisu.md"
    assert file.exists()

    # Verify git commit uses verb "create"
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
    """A new page with no tags should get tags derived from its body."""
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
    # We expect at least 2 tags to be derived from the deployment-heavy body
    assert len(tags) >= 2
    # Common terms like "server", "deployment", "configuration" should be in the top
    expected = {"server", "deployment", "configuration", "guide", "setup", "production", "steps"}
    assert len(set(tags) & expected) >= 1


def test_put_page_does_not_derive_tags_on_update(client: TestClient) -> None:
    """An existing page with tags should keep its original tags on update."""
    # Pizza Dough already has tags: [food, pizza]
    r = client.put(
        "/api/v1/pages/recipes/pizza-dough",
        json={"body": "# A completely different topic\n\npython async server"},
    )
    assert r.status_code == 200
    body = r.json()
    # Original tags must be preserved
    assert "food" in body["meta"]["tags"]
    assert "pizza" in body["meta"]["tags"]


# ── DELETE tests ───────────────────────────────────────────────────────


def test_delete_page(client: TestClient, content_dir: Path) -> None:
    # Create a page first
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nA classic.\n"},
    )
    r = client.delete("/api/v1/pages/recipes/tiramisu")
    assert r.status_code == 204
    assert r.text == ""  # no content

    # Verify file is gone
    file = content_dir / "pages" / "recipes" / "tiramisu.md"
    assert not file.exists()

    # Verify git commit
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


def test_delete_page_index_file(client: TestClient, content_dir: Path) -> None:
    # Create a directory page first (empty, just index.md)
    client.put(
        "/api/v1/pages/devel",
        json={"body": "# Devel\n\nTips.\n", "is_index": True},
    )
    index_file = content_dir / "pages" / "devel" / "index.md"
    assert index_file.exists()

    r = client.delete("/api/v1/pages/devel")
    assert r.status_code == 204

    # Both index.md and the now-empty directory are gone
    assert not index_file.exists()
    assert not (content_dir / "pages" / "devel").exists()


def test_delete_page_index_file_with_children(client: TestClient, content_dir: Path) -> None:
    # Create a directory page with a child page inside
    client.put(
        "/api/v1/pages/devel",
        json={"body": "# Devel\n\nTips.\n", "is_index": True},
    )
    client.put(
        "/api/v1/pages/devel/bash",
        json={"body": "# Bash\n\nScripts.\n"},
    )

    # Refused: folder is not empty
    r = client.delete("/api/v1/pages/devel")
    assert r.status_code == 409

    # Both index.md and the child remain intact
    assert (content_dir / "pages" / "devel" / "index.md").exists()
    assert (content_dir / "pages" / "devel" / "bash.md").exists()


def test_delete_bare_directory(client: TestClient, content_dir: Path) -> None:
    # Create an empty bare directory (no .md file at all)
    bare = content_dir / "pages" / "empty-folder"
    bare.mkdir(parents=True)

    r = client.delete("/api/v1/pages/empty-folder")
    assert r.status_code == 204
    assert not bare.exists()


def test_delete_bare_directory_not_empty(client: TestClient, content_dir: Path) -> None:
    # Create a bare directory with a child file
    bare = content_dir / "pages" / "stuff"
    bare.mkdir(parents=True)
    (bare / "notes.md").write_text("some notes", encoding="utf-8")

    r = client.delete("/api/v1/pages/stuff")
    assert r.status_code == 409


# ── MOVE tests ─────────────────────────────────────────────────────────


def test_move_page(client: TestClient, content_dir: Path) -> None:
    # Create a page first
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

    # Old path should 404
    assert client.get("/api/v1/pages/recipes/tiramisu").status_code == 404

    # New path should be accessible
    new = client.get("/api/v1/pages/recipes/tiramisu-classic")
    assert new.status_code == 200
    assert "A classic" in new.json()["body"]

    # Verify git commit
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


def test_move_directory_page(client: TestClient, content_dir: Path) -> None:
    # Create a directory page with a child
    client.put(
        "/api/v1/pages/devel",
        json={"body": "# Devel\n\nTips.\n", "is_index": True},
    )
    client.put(
        "/api/v1/pages/devel/bash",
        json={"body": "# Bash\n\nScripts.\n"},
    )

    r = client.post(
        "/api/v1/pages/devel/move",
        json={"new_path": "development"},
    )
    assert r.status_code == 200

    # Old paths should 404
    assert client.get("/api/v1/pages/devel").status_code == 404
    assert client.get("/api/v1/pages/devel/bash").status_code == 404

    # Both pages accessible at new location
    d = client.get("/api/v1/pages/development")
    assert d.status_code == 200
    assert "Tips" in d.json()["body"]

    b = client.get("/api/v1/pages/development/bash")
    assert b.status_code == 200
    assert "Scripts" in b.json()["body"]


# ── is_index tests ─────────────────────────────────────────────────────


def test_put_page_as_index(client: TestClient, content_dir: Path) -> None:
    r = client.put(
        "/api/v1/pages/guides",
        json={"body": "# Guides\n\nTutorials.\n", "is_index": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_index"] is True

    # Verify file was created as <path>/index.md, not <path>.md
    assert (content_dir / "pages" / "guides" / "index.md").exists()
    assert not (content_dir / "pages" / "guides.md").exists()
