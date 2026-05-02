from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_history_single_commit(client: TestClient, content_dir: Path) -> None:
    # Create a page first so there is at least one commit
    client.put(
        "/api/v1/pages/test-one",
        json={"body": "# Test\n\nBody.\n"},
    )
    r = client.get("/api/v1/pages/test-one/history")
    assert r.status_code == 200
    entries = r.json()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    entry = entries[0]
    assert "sha" in entry
    assert len(entry["sha"]) == 7
    assert "message" in entry
    assert "author" in entry
    assert "timestamp" in entry


def test_history_multi_commit(client: TestClient) -> None:
    # Create two updates to generate multiple commits
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nV1.\n"},
    )
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nV2.\n"},
    )

    r = client.get("/api/v1/pages/recipes/tiramisu/history")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 2


def test_history_nonexistent_page_returns_empty(client: TestClient) -> None:
    r = client.get("/api/v1/pages/does/not/exist/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_ordering(client: TestClient) -> None:
    # Create two updates
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nOldest.\n"},
    )
    client.put(
        "/api/v1/pages/recipes/tiramisu",
        json={"body": "# Tiramisu\n\nNewest.\n"},
    )

    r = client.get("/api/v1/pages/recipes/tiramisu/history")
    entries = r.json()
    assert len(entries) >= 2
    # Most recent first
    timestamps = [e["timestamp"] for e in entries]
    assert timestamps == sorted(timestamps, reverse=True)
