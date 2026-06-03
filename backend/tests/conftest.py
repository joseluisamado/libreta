from collections.abc import Iterator
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app


@pytest.fixture
def meta_dir(tmp_path: Path) -> Path:
    """Libreta's metadata dir: holds the sources registry, watched config, and
    the search index DB. Git-initialised so storage layers that open it as a
    repo (watched config commits) work."""
    root = tmp_path / "meta"
    root.mkdir()
    pygit2.init_repository(str(root))
    return root


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    """Where git sources are cloned. Empty by default; tests that need a source
    create one with :func:`make_source`."""
    d = tmp_path / "repos"
    d.mkdir()
    return d


def make_source(repos_dir: Path, source_id: str, files: dict[str, str]) -> Path:
    """Create a git source working tree under *repos_dir* with one commit.

    *files* maps repo-relative paths (e.g. ``"recipes/pizza.md"``) to contents.
    Returns the source's local path (``repos_dir/source_id``).
    """
    local = repos_dir / source_id
    repo = pygit2.init_repository(str(local), initial_head="main")
    for rel, content in files.items():
        p = local / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    repo.index.add_all()
    repo.index.write()
    tree = repo.index.write_tree()
    sig = pygit2.Signature("Tester", "tester@example.com")
    repo.create_commit("HEAD", sig, sig, "initial", tree, [])
    return local


@pytest.fixture
def client(meta_dir: Path, repos_dir: Path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        meta_dir=meta_dir, repos_dir=repos_dir
    )
    with TestClient(app) as c:
        yield c
