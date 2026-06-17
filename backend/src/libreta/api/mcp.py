"""MCP endpoint exposing Libreta pages to MCP clients (e.g. Claude Desktop).

This mounts a Model Context Protocol server *inside* the FastAPI app, served
over the streamable-HTTP transport at ``/mcp``. Unlike a stdio sidecar, it ships
and deploys with the backend container — Claude Desktop connects to the URL,
nothing is installed per-machine.

The tools call the storage layer directly (in-process, no HTTP self-call) and
go through the same save lifecycle as the REST handlers: ``write_page`` commits
to the source repo via ``write_source_page`` and then enqueues an async push,
exactly like ``PUT /api/v1/sources/{id}/pages/{path}``. There is no
save-without-commit path.

Scope: assumes a LAN/no-auth Libreta (its current pre-M6 state). The MCP
transport is unauthenticated; do not expose ``/mcp`` to an untrusted network
without putting auth in front of the backend.

Concurrency: page writes are last-writer-wins (``PageWrite`` carries only the
body, no revision/ETag). ``read_page`` lets the model edit current content
rather than overwrite blindly; it is not a lock.

``build_mcp()`` returns a *fresh* server each call. The streamable-HTTP
transport's session manager can only be run once per instance, so each
``create_app()`` (notably one per test) must get its own — never share a
module-level singleton.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.services.sync import enqueue_push
from libreta.storage import sources as src_store


def _flatten_pages(nodes: list[Any], acc: list[dict[str, str]]) -> None:
    """Walk the page tree, collecting leaf pages (kind == "page") as {path, title}."""
    for node in nodes:
        if node.is_directory:
            _flatten_pages(node.children, acc)
            continue
        if node.kind == "page":
            acc.append({"path": node.path, "title": node.title})


def build_mcp(settings_provider: Callable[[], Settings] = get_settings) -> FastMCP:
    """Construct a fresh MCP server with Libreta's page tools registered.

    A new instance per call: its session manager is single-use (see module
    docstring). ``streamable_http_path="/"`` so that, mounted at ``/mcp``, the
    endpoint is exactly ``/mcp`` rather than ``/mcp/mcp``.

    ``settings_provider`` resolves the active :class:`Settings`. It defaults to
    the cached :func:`get_settings`; ``create_app`` passes a closure that honors
    FastAPI's ``dependency_overrides`` so tests can point the tools at temp dirs
    (the tools call storage directly, not via ``Depends``, so they would
    otherwise miss the override).
    """
    mcp = FastMCP("libreta", streamable_http_path="/")

    @mcp.tool()
    async def list_sources() -> list[dict[str, str]]:
        """List the git sources (wikis) configured in Libreta.

        Returns each source's ``id`` (use it as the ``source`` argument to the
        other tools), human ``label``, and whether it is ``cloned`` and ready to
        write to.
        """
        settings = settings_provider()
        sources = await src_store.list_sources(settings.meta_dir, settings.repos_dir)
        return [{"id": s.id, "label": s.label, "cloned": str(bool(s.cloned))} for s in sources]

    @mcp.tool()
    async def list_pages(source: str) -> list[dict[str, str]]:
        """List the markdown pages in a source, flattened to a list of paths.

        ``source`` is a source id from ``list_sources``. Each entry has the page
        ``path`` (pass it to ``read_page`` / ``write_page``) and its ``title``.
        Non-page files (images, diagrams, PDFs) are omitted.
        """
        settings = settings_provider()
        tree = await src_store.walk_source_tree(settings.repos_dir, source, max_depth=None)
        pages: list[dict[str, str]] = []
        _flatten_pages(tree, pages)
        return pages

    @mcp.tool()
    async def read_page(source: str, path: str) -> dict[str, Any]:
        """Read a page's current markdown body and frontmatter.

        Always call this before editing an existing page so you modify the real
        current content rather than overwriting blindly. ``source`` is a source
        id; ``path`` is a page path from ``list_pages`` (e.g. ``notes/ideas.md``).
        Returns ``{path, meta, body}`` where ``body`` is the raw markdown.
        """
        settings = settings_provider()
        page = await src_store.read_source_page(settings.repos_dir, source, path)
        return page.model_dump(mode="json")

    @mcp.tool()
    async def write_page(source: str, path: str, body: str) -> dict[str, Any]:
        """Create or edit a page (upsert). Writes ``body`` as the page's full markdown.

        This overwrites the entire file, so when editing an existing page, first
        ``read_page`` it, apply your changes to the returned body, then pass the
        complete revised markdown here. A ``path`` ending in ``.md`` is created
        if it does not exist. Each write commits to the source repo and queues a
        push.

        NOTE: last-writer-wins — there is no revision check. If a human may be
        editing the same page in Libreta's web editor concurrently, coordinate.
        """
        settings = settings_provider()
        result = await src_store.write_source_page(
            settings.repos_dir,
            settings.ssh_keys_dir,
            settings.meta_dir,
            source,
            path,
            body,
        )
        enqueue_push(source)
        return result.model_dump(mode="json")

    return mcp
