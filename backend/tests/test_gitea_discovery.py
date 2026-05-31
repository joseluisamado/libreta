"""Tests for the Gitea repo-discovery service.

httpx is mocked with a MockTransport so no network is touched. We patch the
AsyncClient constructor used inside the service to inject the transport.
"""

from __future__ import annotations

import functools
import json

import httpx
import pytest

from libreta.errors import GiteaDiscoveryError
from libreta.services import gitea


def _repo(name: str, owner: str = "team") -> dict[str, object]:
    return {
        "name": name,
        "full_name": f"{owner}/{name}",
        "clone_url": f"https://git.example.com/{owner}/{name}.git",
        "description": f"the {name} repo",
        "empty": False,
    }


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    real_client = httpx.AsyncClient

    @functools.wraps(real_client)
    def _factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", _factory)


async def test_discover_org_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/orgs/team/repos"
        assert request.headers["Authorization"] == "token tok"
        return httpx.Response(200, json=[_repo("handbook"), _repo("runbooks")])

    _install_transport(monkeypatch, handler)
    repos = await gitea.discover_repos("https://git.example.com", "team", "tok")
    assert [r.full_name for r in repos] == ["team/handbook", "team/runbooks"]
    assert repos[0].clone_url == "https://git.example.com/team/handbook.git"


async def test_falls_back_to_user_endpoint_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orgs/alice/repos":
            return httpx.Response(404, json={"message": "not an org"})
        assert request.url.path == "/api/v1/users/alice/repos"
        return httpx.Response(200, json=[_repo("notes", owner="alice")])

    _install_transport(monkeypatch, handler)
    repos = await gitea.discover_repos("https://git.example.com", "alice", "tok")
    assert [r.full_name for r in repos] == ["alice/notes"]


async def test_pagination_concatenates_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    # First page returns a full _PAGE_SIZE batch -> service asks for page 2.
    page1 = [_repo(f"r{i}") for i in range(gitea._PAGE_SIZE)]
    page2 = [_repo("last")]

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        return httpx.Response(200, json=page1 if page == "1" else page2)

    _install_transport(monkeypatch, handler)
    repos = await gitea.discover_repos("https://git.example.com", "team", "tok")
    assert len(repos) == gitea._PAGE_SIZE + 1
    assert repos[-1].name == "last"


async def test_auth_failure_raises_discovery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    _install_transport(monkeypatch, handler)
    with pytest.raises(GiteaDiscoveryError):
        await gitea.discover_repos("https://git.example.com", "team", "bad")


async def test_unreachable_host_raises_discovery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    _install_transport(monkeypatch, handler)
    with pytest.raises(GiteaDiscoveryError):
        await gitea.discover_repos("https://git.example.com", "team", "tok")


async def test_non_list_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"oops": True}))

    _install_transport(monkeypatch, handler)
    with pytest.raises(GiteaDiscoveryError):
        await gitea.discover_repos("https://git.example.com", "team", "tok")
