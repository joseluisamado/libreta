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


# ── folder uploads (sibling files, not page sidecars) ────────────────────


PDF = b"%PDF-1.4\nfake-pdf-bytes\n%%EOF"


def test_upload_folder_file_writes_sibling(client: TestClient, content_dir: Path) -> None:
    r = client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "report.pdf"
    assert body["size"] == len(PDF)
    # Lands directly in the folder, NOT in a hidden sidecar.
    assert (content_dir / "pages" / "recipes" / "report.pdf").read_bytes() == PDF


def test_upload_folder_file_to_root(client: TestClient, content_dir: Path) -> None:
    r = client.post(
        "/api/v1/pages/files",
        files={"file": ("top.bin", b"\x00\x01\x02", "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "top.bin"
    assert (content_dir / "pages" / "top.bin").read_bytes() == b"\x00\x01\x02"


def test_upload_folder_file_uniquifies_on_collision(client: TestClient, content_dir: Path) -> None:
    client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("doc.txt", b"first", "text/plain")},
    )
    r = client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("doc.txt", b"second", "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["filename"] == "doc-2.txt"
    assert (content_dir / "pages" / "recipes" / "doc-2.txt").read_bytes() == b"second"


def test_upload_folder_file_creates_commit(client: TestClient, content_dir: Path) -> None:
    import pygit2

    repo = pygit2.Repository(str(content_dir))
    n_before = sum(1 for _ in repo.walk(repo.head.target)) if not repo.is_empty else 0
    client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    n_after = sum(1 for _ in repo.walk(repo.head.target))
    assert n_after == n_before + 1
    head = repo[repo.head.target]
    assert head.message.startswith("upload pages/recipes/report.pdf")


def test_upload_folder_file_unknown_folder_404(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/does/not/exist/files",
        files={"file": ("x.bin", b"x", "application/octet-stream")},
    )
    assert r.status_code == 404


def test_upload_folder_file_rejects_empty(client: TestClient) -> None:
    r = client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("empty.bin", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_folder_file_rejects_markdown(client: TestClient) -> None:
    # Sibling .md would collide with the page model — assets layer refuses it.
    r = client.post(
        "/api/v1/pages/recipes/files",
        files={"file": ("notes.md", b"# hi\n", "text/markdown")},
    )
    assert r.status_code == 400


# ── store_folder_file storage helper (shared by all three repo kinds) ─────


async def _chunks(*parts: bytes):
    """A read_chunk-style callable that yields fixed parts then EOF."""
    queue = list(parts)

    async def read(_n: int) -> bytes:
        return queue.pop(0) if queue else b""

    return read


def test_store_folder_file_streams_to_disk(tmp_path: Path) -> None:
    import asyncio

    from libreta.storage.assets import store_folder_file

    base = tmp_path / "repo"
    (base / "sub").mkdir(parents=True)

    async def run() -> None:
        read = await _chunks(b"hello ", b"world")
        result = await store_folder_file(base, "sub", "greeting.txt", read)
        assert result.filename == "greeting.txt"
        assert result.size == len(b"hello world")
        assert result.rel_path == "sub/greeting.txt"
        assert (base / "sub" / "greeting.txt").read_bytes() == b"hello world"

    asyncio.run(run())


def test_store_folder_file_repo_root_rel_path(tmp_path: Path) -> None:
    import asyncio

    from libreta.storage.assets import store_folder_file

    # base_dir is pages/, repo_root is the parent → rel_path keeps the prefix.
    repo_root = tmp_path / "content"
    base = repo_root / "pages"
    (base / "docs").mkdir(parents=True)

    async def run() -> None:
        read = await _chunks(b"data")
        result = await store_folder_file(base, "docs", "f.bin", read, repo_root=repo_root)
        assert result.rel_path == "pages/docs/f.bin"

    asyncio.run(run())


def test_store_folder_file_escape_blocked(tmp_path: Path) -> None:
    import asyncio

    from libreta.errors import InvalidPathError
    from libreta.storage.assets import store_folder_file

    base = tmp_path / "repo"
    base.mkdir()

    async def run() -> None:
        read = await _chunks(b"x")
        try:
            await store_folder_file(base, "../escape", "f.bin", read)
        except InvalidPathError:
            return
        raise AssertionError("expected InvalidPathError for traversal")

    asyncio.run(run())
