"""Integration test for the /mcp endpoint.

Drives the mounted MCP streamable-HTTP server with a real MCP client over a
loopback uvicorn (so the app's lifespan — and thus the session manager — runs),
then exercises the full tool set: list_sources, list_pages, read_page, the
create + edit halves of write_page, and attach_file (base64 binary → page
sidecar). The write/attach paths assert the change lands on disk and is
committed, matching Libreta's save lifecycle (R3).
"""

from __future__ import annotations

import asyncio
import base64
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pygit2
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.main import create_app
from libreta.storage.sources import save_sources_sync

from .conftest import make_source

# Smallest valid PNG (1x1 transparent) — real image bytes so _kind_for
# classifies the attachment as "image" and the round-trip is honest.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def mcp_url(meta_dir: Path, repos_dir: Path) -> Iterator[str]:
    """Run the app under uvicorn on a loopback port; yield the /mcp URL."""
    make_source(repos_dir, "wiki", {"notes/ideas.md": "# Ideas\n\noriginal body\n"})
    # Register the source in the meta registry so list_sources sees it (the
    # working tree alone is not enough — list_sources reads sources.json).
    save_sources_sync(
        meta_dir,
        [
            {
                "id": "wiki",
                "label": "My Wiki",
                "remote_url": "git@example.com:wiki.git",
                "branch": "main",
                "ssh_key_id": None,
                "http_username": None,
                "http_password": None,
                "gitea_server_id": None,
                "sync_interval_minutes": 15,
                "last_synced_at": None,
                "last_sync_error": None,
            }
        ],
    )

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        meta_dir=meta_dir, repos_dir=repos_dir
    )

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for startup (lifespan complete) before handing back the URL.
    while not server.started:  # set True after lifespan startup
        if not thread.is_alive():  # pragma: no cover - startup crash
            raise RuntimeError("uvicorn failed to start")

    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def _drive(url: str, repos_dir: Path) -> None:
    async with (
        streamablehttp_client(url) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        names = {t.name for t in (await session.list_tools()).tools}
        assert names == {
            "list_sources",
            "list_pages",
            "read_page",
            "write_page",
            "attach_file",
        }

        sources = (await session.call_tool("list_sources", {})).structuredContent
        assert sources is not None
        ids = {s["id"] for s in sources["result"]}
        assert "wiki" in ids

        pages = (await session.call_tool("list_pages", {"source": "wiki"})).structuredContent
        assert pages is not None
        # Libreta addresses pages without the .md extension.
        paths = {p["path"] for p in pages["result"]}
        assert "notes/ideas" in paths

        # Dict-returning tools surface the dict directly (no "result" wrap).
        read_result = (
            await session.call_tool("read_page", {"source": "wiki", "path": "notes/ideas"})
        ).structuredContent
        assert read_result is not None
        assert "original body" in read_result["body"]

        # Edit existing page (read -> modify -> write).
        await session.call_tool(
            "write_page",
            {
                "source": "wiki",
                "path": "notes/ideas",
                "body": "# Ideas\n\nedited via mcp\n",
            },
        )
        # Create a new page, setting a sidebar weight via the meta channel.
        create_res = (
            await session.call_tool(
                "write_page",
                {
                    "source": "wiki",
                    "path": "fresh",
                    "body": "# Fresh\n\nnew page\n",
                    "meta": {"weight": 20},
                },
            )
        ).structuredContent
        assert create_res is not None
        assert create_res["meta"]["weight"] == 20

        # Attach a binary file (base64 over the JSON transport) to a page, then
        # reference it in the body — the two-step image flow the tools expose.
        png = base64.b64encode(_TINY_PNG).decode("ascii")
        attach_res = (
            await session.call_tool(
                "attach_file",
                {
                    "source": "wiki",
                    "page": "notes/ideas",
                    "filename": "diagram.png",
                    "content_base64": png,
                },
            )
        ).structuredContent
        assert attach_res is not None
        # Sidecar-relative path, ready to embed as markdown.
        assert attach_res["filename"] == ".ideas.md/diagram.png"
        assert attach_res["kind"] == "image"
        assert attach_res["deduped"] is False

        # Re-attaching identical bytes dedupes rather than writing a copy.
        redo = (
            await session.call_tool(
                "attach_file",
                {
                    "source": "wiki",
                    "page": "notes/ideas",
                    "filename": "diagram.png",
                    "content_base64": png,
                },
            )
        ).structuredContent
        assert redo is not None
        assert redo["deduped"] is True
        assert redo["filename"] == ".ideas.md/diagram.png"

        # Non-base64 payload is a caller error, not a 500.
        bad = await session.call_tool(
            "attach_file",
            {
                "source": "wiki",
                "page": "notes/ideas",
                "filename": "x.png",
                "content_base64": "not base64!!!",
            },
        )
        assert bad.isError, "invalid base64 should error"

        # A body containing a frontmatter fence is a caller mistake: it must be
        # rejected, not persisted as page content.
        fence_res = await session.call_tool(
            "write_page",
            {
                "source": "wiki",
                "path": "notes/ideas",
                "body": "---\nweight: 99\n---\n\n# Ideas\n",
            },
        )
        assert fence_res.isError, "frontmatter-in-body write should error"

    # The writes hit the real working tree and were committed. Libreta manages
    # frontmatter on save, so assert the body content rather than byte-exact.
    edited = (repos_dir / "wiki" / "notes" / "ideas.md").read_text()
    assert "edited via mcp" in edited
    # The rejected frontmatter-in-body write must not have touched the page.
    assert "weight: 99" not in edited
    created = (repos_dir / "wiki" / "fresh.md").read_text()
    assert "new page" in created
    # The weight set via meta landed in frontmatter (parsed as YAML, not body).
    assert "weight: 20" in created
    assert "# Fresh" in created

    # The attachment landed in the page's hidden sidecar with the real bytes.
    asset = repos_dir / "wiki" / "notes" / ".ideas.md" / "diagram.png"
    assert asset.read_bytes() == _TINY_PNG

    repo = pygit2.Repository(str(repos_dir / "wiki"))
    messages = [c.message for c in repo.walk(repo.head.target)]
    # Both writes were committed (R3): the new page and the attachment.
    assert any("fresh.md" in m for m in messages)
    assert any("diagram.png" in m for m in messages)


def test_mcp_endpoint_round_trip(mcp_url: str, repos_dir: Path) -> None:
    asyncio.run(_drive(mcp_url, repos_dir))


def test_mcp_accepts_foreign_host_header(mcp_url: str) -> None:
    """A non-localhost Host header must not be rejected.

    The streamable-HTTP transport enables DNS-rebinding protection by default,
    which 421s any Host not on an (empty by default) allowlist — breaking access
    via mybox.lan, a Tailscale name, the raw IP, etc. We disable it in
    build_mcp(); this guards against it silently coming back.
    """
    # mcp_url is the /mcp mount; POST to the trailing-slash transition target so
    # we exercise the transport, not the 307 redirect. Any non-localhost Host
    # exercises the DNS-rebinding check; an arbitrary LAN-style name suffices.
    resp = httpx.post(
        mcp_url + "/",
        headers={
            "Host": "wiki.lan:8091",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0"},
            },
        },
        timeout=10,
    )
    # Pre-fix this returned 421 Misdirected Request ("Invalid Host header").
    assert resp.status_code != 421, resp.text
    assert resp.status_code == 200, resp.text
