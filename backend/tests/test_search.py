from pathlib import Path

from fastapi.testclient import TestClient

from libreta.storage.search import _full_reindex_sync, _search_sync, db_path

from .conftest import make_source

_PAGES = {
    "index.md": '---\ntitle: "Home"\n---\n\n# Home\n\nWelcome.\n',
    "recipes/pizza-dough.md": (
        '---\ntitle: "Pizza Dough"\ntags: [food, pizza]\n---\n\n'
        "# Pizza Dough\n\nFlour, water, salt, yeast.\n"
    ),
}


def _seed_source(repos_dir: Path, meta_dir: Path) -> None:
    """Create a git source and build the search index from it."""
    make_source(repos_dir, "work", _PAGES)
    _full_reindex_sync(meta_dir, repos_dir)


def test_search_returns_results(client: TestClient, repos_dir: Path, meta_dir: Path) -> None:
    _seed_source(repos_dir, meta_dir)
    r = client.get("/api/v1/search", params={"q": "pizza"})
    assert r.status_code == 200
    results = r.json()
    assert any(
        "pizza" in res["title"].lower() or "pizza" in res["snippet"].lower() for res in results
    )
    # Results are attributed to the source they came from.
    assert any(res["source_id"] == "work" for res in results)


def test_search_empty_query_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/search", params={"q": ""})
    assert r.status_code == 422


def test_search_bad_fts_syntax_returns_empty(client: TestClient) -> None:
    # Unclosed quote is invalid FTS5 syntax — should return [] not 500.
    r = client.get("/api/v1/search", params={"q": '"unclosed'})
    assert r.status_code == 200
    assert r.json() == []


def test_search_tag_filter_rewritten(client: TestClient, repos_dir: Path, meta_dir: Path) -> None:
    _seed_source(repos_dir, meta_dir)
    # pizza-dough.md has tags: [food, pizza]
    r = client.get("/api/v1/search", params={"q": "tag:food"})
    assert r.status_code == 200
    results = r.json()
    assert any("pizza" in res["path"] for res in results)


def test_search_missing_q_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/search")
    assert r.status_code == 422


def test_full_reindex_indexes_sources(repos_dir: Path, meta_dir: Path) -> None:
    make_source(repos_dir, "work", _PAGES)
    n = _full_reindex_sync(meta_dir, repos_dir)
    assert n >= 2  # index.md + recipes/pizza-dough.md
    assert db_path(meta_dir).exists()


def test_incremental_reindex_skips_unchanged(repos_dir: Path, meta_dir: Path) -> None:
    from libreta.storage.search import _incremental_reindex_sync

    make_source(repos_dir, "work", _PAGES)
    _full_reindex_sync(meta_dir, repos_dir)
    # Second incremental pass should update nothing (HEAD unchanged).
    n = _incremental_reindex_sync(meta_dir, repos_dir)
    assert n == 0


def test_search_finds_body_text(repos_dir: Path, meta_dir: Path) -> None:
    _seed_source(repos_dir, meta_dir)
    results = _search_sync(meta_dir, "flour", 10)
    assert any("pizza" in r["path"] for r in results)
