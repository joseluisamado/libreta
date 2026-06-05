"""Page-scoped attachment upload + fetch round-trip.

Regression coverage for the bug where an image uploaded into a source whose
repo has a top-level ``pages/`` directory landed at ``pages/.note.md/photo.png``
on disk, but the API returned a page-relative ``filename`` (``.note.md/...``).
The editor embedded that into the markdown and fetched it back via
``/assets/.note.md/photo.png`` — which resolved against the repo root, missed
the ``pages/`` prefix, and 404'd. Net effect: image upload looked broken.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import make_source

# Smallest valid 1x1 PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _upload(client: TestClient, src: str, page: str) -> str:
    r = client.post(
        f"/api/v1/sources/{src}/pages/{page}/assets",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "image"
    return str(body["filename"])


def test_upload_into_pages_repo_is_fetchable(client: TestClient, repos_dir: Path) -> None:
    make_source(repos_dir, "src1", {"pages/note.md": "# hi\n"})
    filename = _upload(client, "src1", "note")
    # filename is page-relative (no pages/ prefix), so the markdown round-trips.
    assert filename == ".note.md/photo.png"

    g = client.get(f"/api/v1/sources/src1/assets/{filename}")
    assert g.status_code == 200, g.text
    assert g.content == PNG


def test_upload_into_flat_repo_is_fetchable(client: TestClient, repos_dir: Path) -> None:
    # A source without a pages/ dir stores the page at the repo root.
    make_source(repos_dir, "flat", {"note.md": "# hi\n"})
    filename = _upload(client, "flat", "note")
    assert filename == ".note.md/photo.png"

    g = client.get(f"/api/v1/sources/flat/assets/{filename}")
    assert g.status_code == 200, g.text
    assert g.content == PNG


def test_heic_uploads_and_classifies_as_image(client: TestClient, repos_dir: Path) -> None:
    # HEIC can't render in most browsers, but it must still upload and be
    # embedded as an image (![]()), not misclassified as a download link.
    make_source(repos_dir, "src1", {"pages/note.md": "# hi\n"})
    r = client.post(
        "/api/v1/sources/src1/pages/note/assets",
        files={"file": ("DDR4-3200.HEIC", b"\x00\x00\x00\x18ftypheic", "")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "image"
    assert body["filename"] == ".note.md/DDR4-3200.HEIC"

    g = client.get(f"/api/v1/sources/src1/assets/{body['filename']}")
    assert g.status_code == 200, g.text


def test_asset_fetch_rejects_traversal(client: TestClient, repos_dir: Path) -> None:
    make_source(repos_dir, "src1", {"pages/note.md": "# hi\n"})
    g = client.get("/api/v1/sources/src1/assets/..%2f..%2fetc%2fpasswd")
    assert g.status_code in (400, 404), g.text
