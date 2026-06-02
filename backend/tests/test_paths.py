from pathlib import Path

import pytest

from libreta.errors import InvalidPathError, PageNotFoundError
from libreta.storage.pagefile import resolve_page_source_file
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


def test_resolve_page_source_file_implies_md(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    target = tmp_path / "notes" / "todo.md"
    target.write_text("# todo\n", encoding="utf-8")
    assert resolve_page_source_file(tmp_path, "notes/todo") == target


def test_resolve_page_source_file_missing(tmp_path: Path) -> None:
    with pytest.raises(PageNotFoundError):
        resolve_page_source_file(tmp_path, "nope")


def test_resolve_page_source_file_directory(tmp_path: Path) -> None:
    (tmp_path / "adir").mkdir()
    with pytest.raises(PageNotFoundError):
        resolve_page_source_file(tmp_path, "adir")


def test_resolve_page_source_file_traversal(tmp_path: Path) -> None:
    with pytest.raises(InvalidPathError):
        resolve_page_source_file(tmp_path, "../escape")
