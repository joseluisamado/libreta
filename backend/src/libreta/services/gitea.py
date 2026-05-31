"""Gitea repo discovery.

Lists the repositories under an org or user on a Gitea server, so they can be
bulk-imported as git sources. This is the only place Libreta talks to the
Gitea HTTP API; cloning afterwards goes through the normal pygit2 path.

R5: this runs only on an explicit admin discover/import action, never at
page-render time, and targets the user's own self-hosted Gitea.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from libreta.errors import GiteaDiscoveryError
from libreta.models import GiteaRepo

logger = logging.getLogger(__name__)

# Gitea caps limit at 50 by default; paginate until a short page comes back.
_PAGE_SIZE = 50
# Hard cap so a misconfigured server can't make us loop forever.
_MAX_PAGES = 200
_TIMEOUT = httpx.Timeout(15.0)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/json"}


def _to_repo(raw: dict[str, Any]) -> GiteaRepo:
    return GiteaRepo(
        name=raw.get("name", ""),
        full_name=raw.get("full_name", ""),
        clone_url=raw.get("clone_url", ""),
        description=raw.get("description") or "",
        empty=bool(raw.get("empty", False)),
    )


def _gitea_message(resp: httpx.Response) -> str:
    """Best-effort extraction of Gitea's JSON `message` field for an error."""
    try:
        body = resp.json()
    except (ValueError, httpx.HTTPError):
        return ""
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, str):
            return msg
    return ""


async def _fetch_all(client: httpx.AsyncClient, url: str, token: str) -> list[dict[str, Any]]:
    """Fetch every page of a Gitea list endpoint. Raises on the first error."""
    out: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        resp = await client.get(
            url,
            headers=_headers(token),
            params={"page": page, "limit": _PAGE_SIZE},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list):
            raise GiteaDiscoveryError(f"unexpected response shape from {url}")
        out.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
    return out


# Status codes on the org endpoint that mean "try the user endpoint instead":
#   404 — owner is genuinely not an org.
#   403 — the token can reach the instance but lacks `read:organization`
#         scope. A user-owned account returns 403 here (the org check is
#         scope-gated and runs before the not-an-org decision), yet the user
#         endpoint needs no org scope and succeeds. Falling through lets a
#         repo-scoped token list a user's repos without `read:organization`.
_ORG_FALLBACK_CODES = frozenset({403, 404})


def _status_error(owner: str, exc: httpx.HTTPStatusError) -> GiteaDiscoveryError:
    code = exc.response.status_code
    detail = _gitea_message(exc.response)
    suffix = f": {detail}" if detail else ""
    return GiteaDiscoveryError(f"gitea returned {code} for {owner!r}{suffix}")


async def discover_repos(base_url: str, owner: str, token: str) -> list[GiteaRepo]:
    """List repos under *owner*, trying the org endpoint then the user one.

    Gitea exposes org repos at ``/api/v1/orgs/{owner}/repos`` and user repos
    at ``/api/v1/users/{owner}/repos``. We don't know which *owner* is, so we
    try the org endpoint first and fall back to the user endpoint when the org
    attempt returns a code in ``_ORG_FALLBACK_CODES``.
    """
    base = base_url.rstrip("/")
    org_url = f"{base}/api/v1/orgs/{owner}/repos"
    user_url = f"{base}/api/v1/users/{owner}/repos"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            raw = await _fetch_all(client, org_url, token)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _ORG_FALLBACK_CODES:
                raise _status_error(owner, exc) from exc
            # Not an org, or no org scope — try the user endpoint.
            try:
                raw = await _fetch_all(client, user_url, token)
            except httpx.HTTPStatusError as exc2:
                raise _status_error(owner, exc2) from exc2
            except httpx.HTTPError as exc2:
                raise GiteaDiscoveryError(f"cannot reach gitea: {exc2}") from exc2
        except httpx.HTTPError as exc:
            raise GiteaDiscoveryError(f"cannot reach gitea: {exc}") from exc

    return [_to_repo(r) for r in raw]
