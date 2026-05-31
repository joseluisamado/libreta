"""API tests for Gitea server CRUD, discovery, and bulk import.

The discovery service is patched at the api module boundary so these tests
exercise the endpoints without any network or real Gitea.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pygit2
import pytest
from fastapi.testclient import TestClient

from libreta.api import sources as sources_api
from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app
from libreta.models import GiteaRepo


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    pygit2.init_repository(str(content_dir))
    settings = Settings(
        content_dir=content_dir,
        repos_dir=tmp_path / "repos",
        ssh_keys_dir=tmp_path / "ssh",
        gitea_servers_dir=tmp_path / "gitea",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


def _add_server(client: TestClient) -> str:
    r = client.post(
        "/api/v1/sources/gitea-servers",
        json={
            "label": "Work",
            "base_url": "https://git.example.com",
            "username": "alice",
            "token": "tok-123",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" not in body
    return str(body["id"])


def test_server_crud(client: TestClient) -> None:
    server_id = _add_server(client)
    listed = client.get("/api/v1/sources/gitea-servers").json()
    assert [s["id"] for s in listed] == [server_id]
    assert listed[0]["base_url"] == "https://git.example.com"
    assert "token" not in listed[0]

    assert client.delete(f"/api/v1/sources/gitea-servers/{server_id}").status_code == 204
    assert client.get("/api/v1/sources/gitea-servers").json() == []


def _patch_discovery(monkeypatch: pytest.MonkeyPatch, repos: list[GiteaRepo]) -> list[str]:
    """Patch the api module's discover_repos; capture the tokens it was called with."""
    seen_tokens: list[str] = []

    async def fake(base_url: str, owner: str, token: str) -> list[GiteaRepo]:
        seen_tokens.append(token)
        assert base_url == "https://git.example.com"
        assert owner == "team"
        return repos

    monkeypatch.setattr(sources_api, "discover_repos", fake)
    return seen_tokens


def test_discover_flags_already_added(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    server_id = _add_server(client)
    repos = [
        GiteaRepo(
            name="handbook",
            full_name="team/handbook",
            clone_url="https://git.example.com/team/handbook.git",
        ),
        GiteaRepo(
            name="runbooks",
            full_name="team/runbooks",
            clone_url="https://git.example.com/team/runbooks.git",
        ),
    ]
    seen = _patch_discovery(monkeypatch, repos)

    # Pre-add a source pointing at the handbook clone_url.
    client.post(
        "/api/v1/sources",
        json={
            "id": "team-handbook",
            "label": "team/handbook",
            "remote_url": "https://git.example.com/team/handbook.git",
        },
    )

    r = client.post(
        f"/api/v1/sources/gitea-servers/{server_id}/discover",
        json={"owner": "team"},
    )
    assert r.status_code == 200, r.text
    result = {x["full_name"]: x["already_added"] for x in r.json()}
    assert result == {"team/handbook": True, "team/runbooks": False}
    # The stored token (not anything client-supplied) was used for discovery.
    assert seen == ["tok-123"]


def test_import_creates_sources_referencing_server(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = _add_server(client)
    repos = [
        GiteaRepo(
            name="handbook",
            full_name="team/handbook",
            clone_url="https://git.example.com/team/handbook.git",
        ),
        GiteaRepo(
            name="runbooks",
            full_name="team/runbooks",
            clone_url="https://git.example.com/team/runbooks.git",
        ),
    ]
    _patch_discovery(monkeypatch, repos)

    r = client.post(
        f"/api/v1/sources/gitea-servers/{server_id}/import",
        json={"owner": "team", "repos": ["team/handbook", "team/runbooks"]},
    )
    assert r.status_code == 200, r.text
    created = r.json()
    assert {c["label"] for c in created} == {"team/handbook", "team/runbooks"}
    # Every created source references the server, carries no per-source secret.
    for c in created:
        assert c["gitea_server_id"] == server_id
        assert c["http_username"] is None

    # They now appear in the source list.
    listed = client.get("/api/v1/sources").json()
    assert {s["label"] for s in listed} >= {"team/handbook", "team/runbooks"}


def test_import_is_idempotent_on_clone_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = _add_server(client)
    repos = [
        GiteaRepo(
            name="handbook",
            full_name="team/handbook",
            clone_url="https://git.example.com/team/handbook.git",
        ),
    ]
    _patch_discovery(monkeypatch, repos)
    payload = {"owner": "team", "repos": ["team/handbook"]}
    first = client.post(f"/api/v1/sources/gitea-servers/{server_id}/import", json=payload).json()
    assert len(first) == 1
    # Re-importing the same repo creates nothing new.
    second = client.post(f"/api/v1/sources/gitea-servers/{server_id}/import", json=payload).json()
    assert second == []
    labels = [s["label"] for s in client.get("/api/v1/sources").json()]
    assert labels.count("team/handbook") == 1
