from collections.abc import Iterator
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    # Initialize a git repo so save/commit operations work
    pygit2.init_repository(str(tmp_path))

    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "index.md").write_text(
        '---\ntitle: "Home"\n---\n\n# Home\n\nWelcome.\n',
        encoding="utf-8",
    )
    (pages / "recipes.md").write_text(
        '---\ntitle: "Recipes"\n---\n\n# Recipes\n',
        encoding="utf-8",
    )
    (pages / "recipes").mkdir()
    (pages / "recipes" / "pizza-dough.md").write_text(
        '---\ntitle: "Pizza Dough"\ntags: [food, pizza]\n---\n\n# Pizza Dough\n\nFlour, water, salt, yeast.\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(content_dir: Path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(content_dir=content_dir)
    with TestClient(app) as c:
        yield c
