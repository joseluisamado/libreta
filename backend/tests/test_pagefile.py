"""Unit tests for non-page file classification (_classify_other)."""

from pathlib import Path

import pytest

from libreta.storage.pagefile import _classify_other, _read_webloc_url, walk_children

_WEBLOC_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n'
    "<dict><key>URL</key><string>{url}</string></dict>\n"
    "</plist>\n"
)


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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bookmark.webloc", "weblink"),
        ("Bookmark.WEBLOC", "weblink"),
        # A generic .plist is still text, not a weblink.
        ("settings.plist", "text"),
    ],
)
def test_classify_weblink(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


def test_read_webloc_url_xml(tmp_path: Path) -> None:
    f = tmp_path / "link.webloc"
    f.write_text(_WEBLOC_XML.format(url="https://example.com/page"))
    assert _read_webloc_url(f) == "https://example.com/page"


def test_read_webloc_url_binary(tmp_path: Path) -> None:
    import plistlib

    f = tmp_path / "link.webloc"
    f.write_bytes(plistlib.dumps({"URL": "https://example.org"}, fmt=plistlib.FMT_BINARY))
    assert _read_webloc_url(f) == "https://example.org"


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "ftp://host/x", ""],
)
def test_read_webloc_url_rejects_unsafe(tmp_path: Path, url: str) -> None:
    f = tmp_path / "link.webloc"
    f.write_text(_WEBLOC_XML.format(url=url))
    assert _read_webloc_url(f) is None


def test_read_webloc_url_malformed(tmp_path: Path) -> None:
    f = tmp_path / "broken.webloc"
    f.write_text("not a plist at all")
    assert _read_webloc_url(f) is None


def test_weblink_is_first_class_child_with_target(tmp_path: Path) -> None:
    """A .webloc is a clickable child node carrying its resolved target URL,
    not a thumbnail-bearing previewable and not an other_file."""
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "site.webloc").write_text(_WEBLOC_XML.format(url="https://example.com"))

    nodes, other = walk_children(tmp_path, "")

    by_name = {n.filename: n for n in nodes}
    assert by_name["site.webloc"].kind == "weblink"
    assert by_name["site.webloc"].target == "https://example.com"
    assert "site.webloc" not in {o.name for o in other}


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
