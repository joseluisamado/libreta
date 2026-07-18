"""MCP endpoint exposing Libreta pages to MCP clients (e.g. Claude Desktop).

This mounts a Model Context Protocol server *inside* the FastAPI app, served
over the streamable-HTTP transport at ``/mcp``. Unlike a stdio sidecar, it ships
and deploys with the backend container — Claude Desktop connects to the URL,
nothing is installed per-machine.

The tools call the storage layer directly (in-process, no HTTP self-call) and
go through the same save lifecycle as the REST handlers: ``write_page`` commits
to the source repo via ``write_source_page`` and then enqueues an async push,
exactly like ``PUT /api/v1/sources/{id}/pages/{path}``. ``attach_file`` mirrors
``POST /api/v1/sources/{id}/pages/{path}/assets`` — it stores a binary asset in
the page's hidden sidecar directory (``.<pagename>.md/``), commits it, and
enqueues a push. There is no save-without-commit path.

Binary attachments cross the MCP boundary as base64 text (the transport carries
JSON, not raw bytes). ``attach_file`` decodes the payload, hands the bytes to
the same ``store_asset`` the upload endpoint uses (so dedup, unique-naming, and
sidecar placement are identical), and returns the sidecar-relative ``filename``
(``.<pagename>.md/photo.png``) ready to drop into markdown as
``![](.<pagename>.md/photo.png)`` via a follow-up ``write_page``.

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

import base64
import binascii
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import InvalidPathError
from libreta.services.sync import enqueue_push
from libreta.storage import sources as src_store
from libreta.storage.assets import store_asset
from libreta.storage.repo import commit_page, open_repo


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
    # The streamable-HTTP transport enables DNS-rebinding protection by default,
    # which 421s any request whose Host header isn't on an allowlist (empty by
    # default → only localhost works). Libreta is a self-hosted LAN appliance
    # reached by arbitrary names/IPs (mybox.lan, a Tailscale name, the raw IP),
    # so that check only breaks legitimate access. The protection guards browser
    # origins; /mcp is already LAN/no-auth and not a browser surface, so disable
    # it rather than maintain an unknowable host allowlist.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp = FastMCP(
        "libreta",
        streamable_http_path="/",
        transport_security=security,
    )

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
    async def write_page(
        source: str,
        path: str,
        body: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or edit a page (upsert). ``body`` is the page's markdown *body only*.

        Do NOT put a ``---`` YAML frontmatter block in ``body`` — it would be
        stored as visible page content, and a body that opens with a frontmatter
        fence is rejected. Set frontmatter through the ``meta`` argument instead.

        ``meta`` is an optional dict of frontmatter fields to set, merged over the
        page's existing frontmatter (unlisted keys are preserved). Settable keys:

        - ``weight`` (int): sidebar ordering hint; lower sorts first. Convention
          is to leave gaps (10, 20, 30) so pages can be inserted later. Pass
          ``null`` to clear it. Malformed values are treated as cleared.
        - ``tags`` (list of str)
        - ``title`` (str)

        ``created``/``updated`` are managed by Libreta and cannot be set here.

        This overwrites the entire file, so when editing an existing page, first
        ``read_page`` it, apply your changes to the returned body, then pass the
        complete revised body here (plus any ``meta`` changes). A ``path`` ending
        in ``.md`` is created if it does not exist. Each write commits to the
        source repo and queues a push.

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
            meta=meta,
        )
        enqueue_push(source)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def attach_file(
        source: str,
        page: str,
        filename: str,
        content_base64: str,
    ) -> dict[str, Any]:
        """Attach an image or binary file to a page, storing it in the page's sidecar.

        Use this to add an image (or any binary: PDF, diagram, etc.) that a page
        embeds or links to. The bytes are stored in the page's hidden sidecar
        directory (``.<pagename>.md/``) — the same place Libreta's web uploader
        puts attachments — committed to the source repo, and queued for push.

        Arguments:

        - ``source``: a source id from ``list_sources``.
        - ``page``: the page path this file belongs to (e.g. ``notes/ideas`` or
          ``notes/ideas.md``). The page must already exist — create it with
          ``write_page`` first if needed. The sidecar is derived from this path.
        - ``filename``: the desired file name (e.g. ``diagram.png``). It is
          sanitized (directory components stripped, unsafe characters replaced)
          and de-collided against existing attachments, so the stored name may
          differ from what you pass — always use the returned ``filename``.
          ``.md`` names are rejected: a markdown file is a page, not an asset.
        - ``content_base64``: the file's raw bytes, base64-encoded. The MCP
          transport is JSON/text, so binary payloads must be base64.

        Returns ``{filename, size, sha256, kind, deduped}`` where ``filename`` is
        the sidecar-relative path (``.notes.md/diagram.png``) — embed it verbatim
        in the page body as ``![](.notes.md/diagram.png)`` (for ``kind ==
        "image"``) or a link (for ``kind == "file"``) via a follow-up
        ``write_page``. ``deduped`` is true when identical bytes already existed
        and the stored copy was reused.

        Storing the file does NOT edit the page body — call ``write_page`` after
        this to reference the returned ``filename`` in the markdown.
        """
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidPathError(f"content_base64 is not valid base64: {exc}") from exc
        if not data:
            raise InvalidPathError("empty file")

        settings = settings_provider()
        # _local_path enforces the source-id shape, so a crafted `source`
        # can't escape repos_dir; store_asset validates the page path.
        local = src_store._local_path(settings.repos_dir, source).resolve()
        result = await store_asset(local, page, filename, data, None)
        if not result.deduped:
            repo = open_repo(local)
            await commit_page(repo, result.rel_path, "attach")
            enqueue_push(source)
        return {
            "filename": result.filename,
            "size": result.size,
            "sha256": result.sha256,
            "kind": result.kind,
            "deduped": result.deduped,
        }

    return mcp
