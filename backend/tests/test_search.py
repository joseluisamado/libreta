from pathlib import Path

from fastapi.testclient import TestClient


def _seed_index(client: TestClient) -> None:
    """Trigger indexing by saving the existing pages through the API."""
    for path in ("index", "recipes", "recipes/pizza-dough"):
        r = client.get(f"/api/v1/pages/{path}")
        if r.status_code == 200:
            body = r.json()
            client.put(
                f"/api/v1/pages/{path}",
                json={"body": body["body"]},
            )


def test_search_returns_results(client: TestClient) -> None:
    _seed_index(client)
    r = client.get("/api/v1/search", params={"q": "pizza"})
    assert r.status_code == 200
    results = r.json()
    assert any(
        "pizza" in res["title"].lower() or "pizza" in res["snippet"].lower() for res in results
    )


def test_search_empty_query_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/search", params={"q": ""})
    assert r.status_code == 422


def test_search_bad_fts_syntax_returns_empty(client: TestClient) -> None:
    # Unclosed quote is invalid FTS5 syntax — should return [] not 500.
    r = client.get("/api/v1/search", params={"q": '"unclosed'})
    assert r.status_code == 200
    assert r.json() == []


def test_search_tag_filter_rewritten(client: TestClient) -> None:
    _seed_index(client)
    # pizza-dough.md has tags: [food, pizza]
    r = client.get("/api/v1/search", params={"q": "tag:food"})
    assert r.status_code == 200
    results = r.json()
    assert any("pizza" in res["path"] for res in results)


def test_search_missing_q_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/search")
    assert r.status_code == 422


def test_full_reindex_cli(content_dir: Path) -> None:
    from libreta.storage.search import _full_reindex_sync, db_path

    n = _full_reindex_sync(content_dir)
    assert n >= 3  # index.md + recipes/index.md + recipes/pizza-dough.md
    assert db_path(content_dir).exists()


def test_incremental_reindex_skips_unchanged(content_dir: Path) -> None:
    from libreta.storage.search import _full_reindex_sync, _incremental_reindex_sync

    _full_reindex_sync(content_dir)
    # Second incremental pass should update nothing (files unchanged).
    n = _incremental_reindex_sync(content_dir)
    assert n == 0


def test_page_removed_from_index_on_delete(client: TestClient, content_dir: Path) -> None:
    from libreta.storage.search import _full_reindex_sync, _search_sync

    _full_reindex_sync(content_dir)
    results_before = _search_sync(content_dir, "flour", 10)
    assert any("pizza" in r["path"] for r in results_before)

    client.delete("/api/v1/pages/recipes/pizza-dough")

    # BackgroundTasks run synchronously in TestClient
    results_after = _search_sync(content_dir, "flour", 10)
    assert not any("pizza" in r["path"] for r in results_after)
