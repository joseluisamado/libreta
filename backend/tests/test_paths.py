import pytest

from libreta.errors import InvalidPathError
from libreta.storage.paths import normalize_page_path


def test_simple_path() -> None:
    assert str(normalize_page_path("recipes/pizza-dough")) == "recipes/pizza-dough"


def test_single_segment() -> None:
    assert str(normalize_page_path("index")) == "index"


@pytest.mark.parametrize(
    "bad",
    ["", "/abs/path", "../escape", "foo/../bar", "foo//bar", ".hidden/x", "x/.git", "page.md"],
)
def test_invalid_paths(bad: str) -> None:
    with pytest.raises(InvalidPathError):
        normalize_page_path(bad)
