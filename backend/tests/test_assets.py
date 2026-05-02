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
