from pathlib import Path

from fastapi.testclient import TestClient


def test_get_asset_serves_image(client: TestClient, content_dir: Path) -> None:
    img_dir = content_dir / "pages" / "recipes" / "images"
    img_dir.mkdir(parents=True)
    payload = b"\x89PNG\r\n\x1a\nfake"
    (img_dir / "foo.png").write_bytes(payload)

    r = client.get("/api/v1/assets/pages/recipes/images/foo.png")
    assert r.status_code == 200
    assert r.content == payload


def test_get_asset_missing(client: TestClient) -> None:
    r = client.get("/api/v1/assets/pages/recipes/nope.png")
    assert r.status_code == 404


def test_get_asset_traversal_blocked(client: TestClient) -> None:
    r = client.get("/api/v1/assets/../etc/passwd")
    assert r.status_code in (400, 404)


def test_get_asset_rejects_markdown(client: TestClient) -> None:
    r = client.get("/api/v1/assets/pages/index.md")
    assert r.status_code == 400


# ── upload ──────────────────────────────────────────────────────────────


PNG = b"\x89PNG\r\n\x1a\nfake-png-bytes"


def test_upload_asset_to_page_writes_into_sidecar(client: TestClient, content_dir: Path) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # filename now includes the sidecar prefix for direct embedding in markdown
    assert body["filename"] == ".pizza-dough.md/photo.png"
    assert body["kind"] == "image"
    assert body["size"] == len(PNG)
    assert body["deduped"] is False
    # File landed in the sidecar: pages/recipes/.pizza-dough.md/photo.png
    assert (content_dir / "pages" / "recipes" / ".pizza-dough.md" / "photo.png").read_bytes() == PNG
    # Servable through the sidecar path
    r2 = client.get("/api/v1/assets/pages/recipes/.pizza-dough.md/photo.png")
    assert r2.status_code == 200
    assert r2.content == PNG


def test_upload_asset_to_canonical_page_uses_sidecar(client: TestClient, content_dir: Path) -> None:
    # "recipes" page is at pages/recipes.md → sidecar is pages/.recipes.md/
    r = client.post(
        "/api/v1/pages/recipes/assets",
        files={"file": ("hero.png", PNG, "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["filename"] == ".recipes.md/hero.png"
    assert (content_dir / "pages" / ".recipes.md" / "hero.png").read_bytes() == PNG


def test_upload_dedupes_identical_bytes(client: TestClient, content_dir: Path) -> None:
    r1 = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo-renamed.png", PNG, "image/png")},
    )
    assert r2.status_code == 200
    assert r2.json()["deduped"] is True
    # The deduper returns the existing file's name with sidecar prefix
    assert r2.json()["filename"] == ".pizza-dough.md/photo.png"
    assert not (
        content_dir / "pages" / "recipes" / ".pizza-dough.md" / "photo-renamed.png"
    ).exists()


def test_upload_collision_with_different_bytes_gets_suffix(
    client: TestClient, content_dir: Path
) -> None:
    r1 = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r1.json()["filename"] == ".pizza-dough.md/photo.png"
    r2 = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG + b"more", "image/png")},
    )
    assert r2.status_code == 200
    assert r2.json()["filename"] == ".pizza-dough.md/photo-2.png"
    assert r2.json()["deduped"] is False


def test_upload_unknown_page_returns_404(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/does/not/exist/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r.status_code == 404


def test_upload_rejects_md_files(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("notes.md", b"# hi\n", "text/markdown")},
    )
    assert r.status_code == 400


def test_upload_rejects_empty(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert r.status_code == 400


def test_upload_sanitizes_unsafe_filename(client: TestClient, content_dir: Path) -> None:
    r = client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("../../weird name with spaces!.PNG", PNG, "image/png")},
    )
    assert r.status_code == 200
    full = r.json()["filename"]
    assert full.startswith(".pizza-dough.md/")
    # The sidecar prefix contains a slash; the filename part must be safe
    name = full.split("/", 1)[1]
    assert ".." not in name and " " not in name
    assert name.endswith(".PNG")
    assert (content_dir / "pages" / "recipes" / ".pizza-dough.md" / name).read_bytes() == PNG


def test_upload_creates_commit(client: TestClient, content_dir: Path) -> None:
    import pygit2

    repo = pygit2.Repository(str(content_dir))
    n_before = sum(1 for _ in repo.walk(repo.head.target)) if not repo.is_empty else 0
    client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    n_after = sum(1 for _ in repo.walk(repo.head.target))
    assert n_after == n_before + 1
    head = repo[repo.head.target]
    assert head.message.startswith("attach pages/recipes/.pizza-dough.md/photo.png")


def test_dedupe_does_not_create_extra_commit(client: TestClient, content_dir: Path) -> None:
    import pygit2

    client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    repo = pygit2.Repository(str(content_dir))
    n_after_first = sum(1 for _ in repo.walk(repo.head.target))
    client.post(
        "/api/v1/pages/recipes/pizza-dough/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    n_after_second = sum(1 for _ in repo.walk(repo.head.target))
    assert n_after_second == n_after_first
