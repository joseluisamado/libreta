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
        ("movie.mp4", "binary"),
    ],
)
def test_classify_other(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


def test_images_are_children_not_other_files(tmp_path: Path) -> None:
    """Images (and .drawio.svg) are first-class child nodes, not other_files —
    they have a viewer and a thumbnail, so they belong in the listing."""
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (tmp_path / "chart.drawio.svg").write_text("<svg/>")
    (tmp_path / "notes.txt").write_text("hi")
    (tmp_path / "archive.zip").write_bytes(b"PK")

    nodes, other = walk_children(tmp_path, "")

    kinds = {n.filename: n.kind for n in nodes}
    assert kinds["photo.png"] == "image"
    assert kinds["chart.drawio.svg"] == "drawio"
    assert "page.md" in kinds  # the markdown page is still a node

    other_names = {o.name for o in other}
    assert other_names == {"notes.txt", "archive.zip"}
    assert "photo.png" not in other_names
