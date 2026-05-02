from __future__ import annotations

from fastapi.testclient import TestClient


def _shas(client: TestClient, page: str) -> list[str]:
    r = client.get(f"/api/v1/pages/{page}/history")
    assert r.status_code == 200
    return [e["sha"] for e in r.json()]


def test_diff_between_two_revisions(client: TestClient) -> None:
    client.put("/api/v1/pages/recipes/tiramisu", json={"body": "# Tiramisu\n\nV1.\n"})
    client.put("/api/v1/pages/recipes/tiramisu", json={"body": "# Tiramisu\n\nV2 — better.\n"})

    shas = _shas(client, "recipes/tiramisu")
    assert len(shas) >= 2
    new_sha, old_sha = shas[0], shas[1]

    r = client.get(f"/api/v1/pages/recipes/tiramisu/diff?a={old_sha}&b={new_sha}")
    assert r.status_code == 200
    body = r.json()
    assert body["old_sha"] == old_sha
    assert body["new_sha"] == new_sha
    assert body["old_path"] == "pages/recipes/tiramisu.md"
    assert body["new_path"] == "pages/recipes/tiramisu.md"
    assert "-V1." in body["patch"]
    assert "+V2 — better." in body["patch"]


def test_diff_identical_revisions_returns_empty_patch(client: TestClient) -> None:
    client.put("/api/v1/pages/recipes/tiramisu", json={"body": "# Tiramisu\n\nSame.\n"})
    shas = _shas(client, "recipes/tiramisu")
    sha = shas[0]
    r = client.get(f"/api/v1/pages/recipes/tiramisu/diff?a={sha}&b={sha}")
    assert r.status_code == 200
    assert r.json()["patch"] == ""


def test_diff_creation_shows_added_lines(client: TestClient) -> None:
    # Establish a baseline commit in which "new-page" does not exist yet.
    client.put("/api/v1/pages/baseline", json={"body": "# Baseline\n"})
    baseline_sha = _shas(client, "baseline")[0]

    # Now create new-page in a subsequent commit.
    client.put("/api/v1/pages/new-page", json={"body": "# New\n\nHello.\n"})
    creation_sha = _shas(client, "new-page")[0]

    r = client.get(f"/api/v1/pages/new-page/diff?a={baseline_sha}&b={creation_sha}")
    assert r.status_code == 200
    body = r.json()
    assert body["old_path"] is None  # didn't exist in baseline
    assert body["new_path"] == "pages/new-page.md"
    assert "+# New" in body["patch"]


def test_diff_unknown_revision_returns_404(client: TestClient) -> None:
    client.put("/api/v1/pages/recipes/tiramisu", json={"body": "# T\n"})
    shas = _shas(client, "recipes/tiramisu")
    r = client.get(f"/api/v1/pages/recipes/tiramisu/diff?a=deadbee&b={shas[0]}")
    assert r.status_code == 404
