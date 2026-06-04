"""Unit tests for non-page file classification (_classify_other)."""

import pytest

from libreta.storage.pagefile import _classify_other


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
