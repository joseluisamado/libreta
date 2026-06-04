"""Unit tests for non-page file classification (_classify_other)."""

from pathlib import Path

import pytest

from libreta.storage.pagefile import _classify_other, walk_children


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("photo.png", "image"),
        ("PHOTO.JPG", "image"),
        ("diagram.drawio.svg", "drawio"),
        ("diagram.drawio.png", "drawio"),
        # HTML gets its own kind: it is rendered (JS-stripped) in a dedicated
        # viewer, not shown as raw source like other text. See R6.
        ("index.html", "html"),
        ("page.HTM", "html"),
        ("notes.txt", "text"),
        ("style.css", "text"),
        ("Dockerfile", "text"),
        ("archive.zip", "binary"),
        ("data.bin", "binary"),
    ],
)
def test_classify_other(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("clip.mp4", "video"),
        ("clip.webm", "video"),
        ("clip.MOV", "video"),
        ("photo.heic", "image"),  # rendered by Safari; broken elsewhere (no decode)
        ("photo.HEIF", "image"),
    ],
)
def test_classify_video_and_heic(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # All e-reader formats map to a single "ebook" kind; foliate-js sniffs
        # the concrete format client-side.
        ("book.epub", "ebook"),
        ("BOOK.EPUB", "ebook"),
        ("classic.mobi", "ebook"),
        ("kindle.azw3", "ebook"),
        ("kindle.azw", "ebook"),
        ("old.prc", "ebook"),
        ("story.fb2", "ebook"),
        ("story.fb2.zip", "ebook"),
        ("story.fbz", "ebook"),
        ("comic.cbz", "ebook"),
        # Not e-books: a plain zip stays binary.
        ("archive.zip", "binary"),
    ],
)
def test_classify_ebook(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


def test_previewable_files_are_children_not_other_files(tmp_path: Path) -> None:
    """Files with a viewer + thumbnail (image, drawio, text, html, video) are
    first-class child nodes; only non-previewable binaries land in other_files."""
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (tmp_path / "chart.drawio.svg").write_text("<svg/>")
    (tmp_path / "notes.txt").write_text("hi")
    (tmp_path / "report.html").write_text("<p>x</p>")
    (tmp_path / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
    (tmp_path / "novel.epub").write_bytes(b"PK\x03\x04")
    (tmp_path / "comic.cbz").write_bytes(b"PK\x03\x04")
    (tmp_path / "archive.zip").write_bytes(b"PK")

    nodes, other = walk_children(tmp_path, "")

    kinds = {n.filename: n.kind for n in nodes}
    assert kinds["photo.png"] == "image"
    assert kinds["chart.drawio.svg"] == "drawio"
    assert kinds["notes.txt"] == "text"
    assert kinds["report.html"] == "html"
    assert kinds["clip.mp4"] == "video"
    assert kinds["novel.epub"] == "ebook"
    assert kinds["comic.cbz"] == "ebook"
    assert "page.md" in kinds  # the markdown page is still a node

    # Only the genuinely non-previewable binary remains in other_files.
    assert {o.name for o in other} == {"archive.zip"}
