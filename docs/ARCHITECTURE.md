# Libreta — Architecture

## Contents

1. [Overview](#overview)
2. [System diagram](#system-diagram)
3. [Components](#components)
4. [Technology choices](#technology-choices)
5. [Data model](#data-model)
6. [Storage layer](#storage-layer)
7. [HTTP API](#http-api)
8. [Frontend](#frontend)
9. [Editor and markdown roundtrip](#editor-and-markdown-roundtrip)
10. [Diagrams.net integration](#diagramsnet-integration)
11. [Asset handling](#asset-handling)
12. [Search](#search)
13. [Authentication (forward-looking)](#authentication-forward-looking)
14. [Deployment topology](#deployment-topology)
15. [Key decisions](#key-decisions)
16. [Open questions](#open-questions)

## Overview

Libreta is a thin Python/FastAPI application that turns a git-managed directory of markdown files into a navigable, editable wiki. The filesystem is the source of truth. Auxiliary state (search index, cache) is rebuildable from the filesystem alone.

Three containers in development; two in production.

**Development** (`docker compose --profile dev up`):

- **api** — FastAPI app, serves REST API and asset files. In dev, does *not* serve the frontend bundle.
- **frontend** — Vite dev server with HMR, proxies `/api` and `/assets` to the api container.
- **drawio** — `jgraph/drawio` Docker image, embedded via iframe by the editor.

**Production** (default profile):

- **api** — FastAPI app, serves the *built* Vue SPA from `/`, plus REST API and asset files. The frontend container is not used.
- **drawio** — same as in dev.

In both modes, wiki content lives in **git source clones** under the `libreta-data` Docker named volume. The api process clones, reads, commits, and pushes via libgit2. There is no host bind-mount for wiki content.

## System diagram

```mermaid
flowchart TB
    Browser[User browser]

    subgraph Libreta[Docker Compose stack]
        API[api: FastAPI + SPA in prod]
        Frontend[frontend: Vite dev server, dev profile only]
        Drawio[drawio: jgraph/drawio]
        subgraph Volume[libreta-data volume]
            Repos[repos/&lt;source-id&gt;/ git working trees]
            SSHKeys[ssh_keys/ private key material]
            Meta[meta/_meta/ sources.json, watched.json]
            Index[(search.db: SQLite FTS5)]
        end
    end

    Remote[Remote git repos — GitHub, Gitea, etc.]

    Browser -- HTTP --> API
    Browser -. dev only .-> Frontend
    Frontend -- proxy /api, /assets --> API
    Browser -- iframe + postMessage --> Drawio
    API -- libgit2 read/write/commit --> Repos
    API -- async push / periodic fetch --> Remote
    API -- query/index --> Index
```

## Components

### `api` — backend

A FastAPI application that:

- Serves the compiled Vue SPA from `/` (production only)
- Exposes a versioned REST API at `/api/v1/...`
- Serves uploaded assets at `/assets/...`
- Manages one or more **git sources**: clones remote repos, reads/writes pages into local working trees, commits every save, and pushes asynchronously
- Runs a background sync loop that fast-forwards each source clone on a configurable interval
- Maintains a SQLite-based search index in the background

### `frontend` — Vite dev server (development only)

A Node container running `pnpm dev`. Provides hot module reload during development. Proxies `/api/v1/*` and `/assets/*` to the `api` container. **Not used in production** — production builds the SPA into a static bundle that the api container serves.

### `drawio` — diagram editor

The official `jgraph/drawio` image, run as a sidecar container. Loaded in a sandboxed iframe from the SPA. Communicates via the documented `postMessage` protocol. No state persists in this container — diagrams are saved by the api process to the source repo.

### `libreta-data` — named Docker volume

A single Docker named volume at `/var/lib/libreta/` inside the container, containing three subdirectories:

| Path | Contents |
|---|---|
| `repos/<source-id>/` | Full git working tree for each configured source (`.git/` + `pages/`) |
| `ssh_keys/` | Private SSH key files + `index.json` manifest. Mode 0600. Never committed anywhere. |
| `meta/_meta/` | `sources.json` (source config), `watched.json` (watched-folder config) |

This is the only stateful volume that matters for backups. The search index lives here too but is fully regenerable.

## Technology choices

| Layer                | Choice                                  | Why                                                                                                        |
| -------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Language             | Python 3.12+                            | User preference; rich ecosystem for markdown, git, search.                                                 |
| Web framework        | FastAPI                                 | Async, OpenAPI out of the box, good DX.                                                                    |
| ASGI server          | Uvicorn (with uvloop)                   | Standard pairing for FastAPI.                                                                              |
| Git library          | pygit2 (libgit2 bindings)               | In-process, fast, no shell-out. Avoids the subprocess fragility seen in Wiki.js.                           |
| Markdown parser      | markdown-it-py                          | CommonMark compliant, extensible, mirrors the JS markdown-it the editor uses (consistent rendering both sides). |
| Frontmatter          | python-frontmatter                      | YAML metadata in `.md` files.                                                                              |
| Validation           | Pydantic v2                             | First-class FastAPI integration.                                                                           |
| Search               | SQLite FTS5                             | Zero infra, embedded, sufficient for personal-scale corpora. Upgrade path: tantivy or Meilisearch sidecar. |
| Image processing     | Pillow                                  | Thumbnails, format conversion.                                                                             |
| Filesystem watcher   | watchdog                                | Detects external edits (e.g. user `vim`'d a file) and triggers reindex.                                    |
| Frontend framework   | Vue 3 + TypeScript                      | Familiar territory (Wiki.js too), excellent TipTap bindings.                                               |
| Build tool           | Vite                                    | Fast dev loop, simple config.                                                                              |
| State management     | Pinia                                   | Vue 3 standard.                                                                                            |
| Editor               | TipTap (ProseMirror)                    | Modern, extensible, good Vue integration. Used in production wikis like Docmost.                           |
| Markdown ↔ HTML      | tiptap-markdown + custom serializers    | See [editor section](#editor-and-markdown-roundtrip).                                                      |
| Source-mode editor   | CodeMirror 6                            | Lightweight, modern, good markdown support.                                                                |
| Styling              | Tailwind CSS                            | Solo-dev productive, mobile-first.                                                                         |
| Syntax highlighting  | Shiki (build-time) / highlight.js (run) | TBD per perf testing.                                                                                      |
| Container runtime    | Docker / Docker Compose v2              | Universal.                                                                                                 |

### Decisions deliberately deferred

- **Reverse proxy** (Caddy/Traefik) — not bundled in v1; users add their own. Keeps the compose file small.
- **Job queue** (Celery/RQ/arq) — not needed at v1 scale. Use FastAPI `BackgroundTasks` for git commits and indexing.
- **Migrations framework** — no DB schema beyond search index, which is rebuildable from filesystem.

## Data model

### Git source configuration

Git sources are configured via the Admin UI (`/-/admin`) and persisted to
`<meta>/_meta/sources.json` (inside the `libreta-data` volume):

```json
[
  {
    "id": "my-wiki",
    "label": "My Wiki",
    "remote_url": "git@github.com:you/wiki.git",
    "branch": "main",
    "ssh_key_id": "uuid-of-key-or-null",
    "sync_interval_minutes": 15,
    "last_synced_at": "2026-05-03T10:00:00Z",
    "last_sync_error": null
  }
]
```

SSH private keys are stored as individual files under `ssh_keys/<uuid>` (mode
0600) with a manifest at `ssh_keys/index.json`. Key material never leaves the
volume and is never committed to any git repository.

### Filesystem layout (per source)

Each git source is cloned to `repos/<source-id>/`:

```
repos/my-wiki/                    # git working tree for source "my-wiki"
├── .git/
└── pages/
    ├── index.md                  # page at /index
    ├── .index.md/                # sidecar: attachments for index.md
    ├── projects.md               # page at /projects
    ├── .projects.md/             # sidecar: attachments for projects.md
    ├── projects/                 # sub-pages container
    │   ├── libreta.md            # /projects/libreta
    │   ├── .libreta.md/          # sidecar: attachments for libreta.md
    │   │   ├── architecture.png
    │   │   └── budget.xlsx
    │   ├── libreta/              # sub-pages of /projects/libreta
    │   │   ├── notes.md
    │   │   └── .notes.md/
    │   └── other.md
    └── recipes/
        ├── pizza-dough.md
        └── .pizza-dough.md/      # sidecar: attachments for pizza-dough.md
            └── pizza-dough.jpg
```

A few rules:

- A page at URL path `/foo/bar` lives at `pages/foo/bar.md`.
- Every ``.md`` file is a page. There is no special ``index.md`` concept — a page at ``pages/index.md`` has URL ``/index``.
- ``foo.md`` and ``foo/`` can coexist as siblings: the ``.md`` file is the page, the directory holds its sub-pages.
- **Attachments live in a hidden sidecar directory** named ``.<page-name>.md/`` next to the page. A page at ``pages/recipes/pizza-dough.md`` with ``![](pizza-dough.jpg)`` resolves to ``pages/recipes/.pizza-dough.md/pizza-dough.jpg``.
- Asset paths in markdown are **relative** to the page (`![](photo.jpg)`, `[budget](budget.xlsx)`). Root-anchored URLs (`/assets/...`) are not used.
- The `pages/` tree carries the entire wiki — both pages and their attachments. There is no separate `assets/` tree.
- Sidecar directories start with ``.`` so they are hidden from file listings and tree walks.

**Why sidecar directories**: a page owns its attachments unambiguously. Moving or renaming a page is a single unit: rename the ``.md`` file, its ``.<name>.md/`` sidecar, and optionally its ``<name>/`` sub-pages container. The trade-off is that an attachment used by two pages is duplicated; we accept that at solo-user scale.

**Diagrams** (per the diagrams.net integration below) follow the same rule: a `.drawio.svg` lives next to the page that embeds it.

### Page format

````markdown
---
title: "Libreta Architecture"
created: 2026-05-01T10:23:00Z
updated: 2026-05-01T14:55:00Z
tags: [libreta, architecture, docs]
---

# Libreta Architecture

The body of the page in standard CommonMark / GFM markdown.

![Auth flow](auth-flow.drawio.svg)

```python
def hello() -> str:
    return "world"
```
````

Frontmatter schema (Pydantic):

```python
class PageMeta(BaseModel):
    title: str
    created: datetime
    updated: datetime
    tags: list[str] = []
    # extension point for future fields
```

Unknown frontmatter keys are preserved on roundtrip — Libreta reads what it knows and leaves the rest alone.

## Storage layer

### Git source lifecycle

At **startup**, the api clones any configured sources that don't have a local clone yet, and fast-forwards those that do. Startup work runs as background tasks inside the FastAPI lifespan so the HTTP server becomes responsive immediately. Concurrent syncs are capped at 2 via a shared semaphore — fanning out one fetch per source on a low-core host (libgit2's pack resolution is single-threaded and CPU-bound) just pegs every core through contention.

A **background push worker** (asyncio task) drains a queue of pending pushes. Every local commit enqueues a push. The worker retries up to 3 times with exponential backoff (5 s, 10 s, 20 s). On final failure the error is written to `sources.json` and surfaced in the UI. Push assumes whatever is in `HEAD` is what should be shipped — Libreta commits on every page write, so the push path does not auto-stage external modifications. Files edited outside Libreta are the user's responsibility to commit.

A **periodic sync loop** (asyncio task) checks every 60 seconds which sources are due for a pull (based on their `sync_interval_minutes`). To avoid double-fetching what `startup_sync` already did, every known source is seeded with `next_sync = startup_time + interval` before the loop's first tick. Each due source goes through the same 2-permit semaphore as startup. The fast-forward itself uses `pygit2`'s `SAFE` checkout strategy: libgit2 refuses the FF if any file in the diff has uncommitted local changes, so there is no pre-flight working-tree scan (that scan used to hash the whole repo every call when the index stat cache was stale, e.g. right after a `rsync`-style migration).

### Cadence summary

Concrete numbers in one place so callers don't have to read the source:

| Event | Cadence | Notes |
| --- | --- | --- |
| Push after local commit | Immediate | `enqueue_push(source_id)` runs synchronously after every page or asset commit. The worker dequeues and pushes within ~1 s in the happy path. |
| Push retry on failure | 5 s, then 10 s, then 20 s | Exponential backoff. After three failed attempts the error is recorded in `sources.json` and shown in the Admin UI / sidebar. |
| Periodic pull check | Every 60 s (loop tick) | Each source is then pulled if `now >= last_synced_at + sync_interval_minutes`. |
| Per-source pull interval | `sync_interval_minutes`, default **15 min** | Configurable per source in the Admin UI. |
| Frontend `/sources` poll | 3 s when any source is pending, else 30 s | Drives the sidebar's status dot and `↑N` indicator. Adaptive: tightens during a push window so the indicator drains within ~3 s of the worker finishing, and relaxes at rest so we don't hammer the API. Paused while the tab is hidden; forced immediately on tab refocus and after every successful page save. |

### Pending-changes indicator

`GitSourceResponse.pending_count` reports how many local commits are ahead of `origin/<branch>` (computed via `pygit2.Repository.ahead_behind` on every `/sources` GET — cheap, no caching). The frontend uses this to color the per-source status dot:

- **green** — clean, no local changes ahead.
- **amber** — `pending_count > 0`. The sidebar also renders a `↑N` button next to the source label that opens a small popover listing the changed pages, grouped by page path with the underlying commits underneath.
- **red** — last push attempt failed (`last_sync_error` is set).

The popover is backed by `GET /api/v1/sources/{id}/pending`, which returns each pending commit's sha, message, author, timestamp, and the `.md` page paths it touched.

### Write path (per-page save)

1. Validate the incoming markdown (parses cleanly, frontmatter valid).
2. Acquire the per-source asyncio write lock (one git operation at a time per source).
3. Write the file to the local working tree clone.
4. Stage and commit using pygit2 with a structured message (see below).
5. Enqueue a push to the remote (async, handled by the push worker with retry).
6. Notify the indexer to reindex the changed file.
7. Release the lock and return the saved `PageRead`.

The HTTP response returns as soon as the local commit is done. The push happens in the background — the user is not blocked waiting for the remote.

### Commit message format

```
<verb> <path>

Optional body with a brief change summary.
```

Verbs: `create`, `update`, `delete`, `rename`, `attach`, `draw`. Examples:

```
update pages/projects/libreta.md
create pages/recipes/pizza-dough.md
attach pages/recipes/pizza-dough.jpg
draw   pages/projects/libreta/auth-flow.drawio.svg
```

This makes `git log --oneline` immediately scannable.

### Read path

- Lists and trees: `os.scandir` from the local working tree clone (cheap; the kernel caches it).
- Page content: read the file. No object-DB lookup.
- History: pygit2 walk of commits touching the path.
- Specific revision: pygit2 blob lookup at the given OID.

### External edits and remote changes

A user may edit files directly in the remote git repository (via GitHub UI, VS Code + git push, etc.). The periodic sync loop will fetch and fast-forward those changes into the local clone on the next sync cycle. The search index is updated after each sync. The UI shows the last sync time and any errors in the sidebar panel for each source.

## HTTP API

All routes prefixed with `/api/v1`. JSON throughout. OpenAPI at `/api/v1/docs`.

### Pages & Assets

Pages and their attachments are **always** scoped to a git source (`/sources/{id}/...`)
or a watched folder (`/watch/{label}/...`). There is no top-level `/pages` or `/assets`
namespace — those belonged to the retired single-content-repo model (see *Decisions*).
See the **Git Sources** and **Watch** sections below for the page/asset routes.

Diagrams travel through the **same** asset routes — a `.drawio.svg` is just an SVG file
with embedded mxfile XML. POST creates, PUT-by-filename overwrites. There is no separate
`/diagrams` endpoint.

### Client config

| Method | Path        | Description                                                                                  |
| ------ | ----------- | -------------------------------------------------------------------------------------------- |
| GET    | `/config`   | Returns runtime configuration the SPA needs at boot. Currently `{ drawio_url }`.             |

### Git Sources

| Method | Path                                   | Description                                                       |
| ------ | -------------------------------------- | ----------------------------------------------------------------- |
| GET    | `/sources`                             | List all configured git sources with sync status                  |
| POST   | `/sources`                             | Add a new git source (clone starts in background)                 |
| PUT    | `/sources/{id}`                        | Update label, branch, SSH key, or sync interval                   |
| DELETE | `/sources/{id}`                        | Remove source from config (local clone not deleted)               |
| POST   | `/sources/{id}/sync`                   | Trigger an immediate fetch+fast-forward for a source              |
| GET    | `/sources/{id}/pending`                | List local commits ahead of `origin/<branch>` (each with sha, message, author, timestamp, and the `.md` paths it touched). Drives the sidebar's `↑N` popover. |
| GET    | `/sources/{id}/tree`                   | Page tree for a specific source                                   |
| GET    | `/sources/{id}/children/{path:path}`   | Lazy-load one directory's children (shallow tree expansion)       |
| GET    | `/sources/{id}/pages/{path:path}`      | Read a page from a source                                         |
| PUT    | `/sources/{id}/pages/{path:path}`      | Write a page (commits locally + enqueues push)                    |
| DELETE | `/sources/{id}/pages/{path:path}`      | Delete a page (commits locally + enqueues push)                   |
| POST   | `/sources/{id}/pages/{path:path}/move` | Move/rename a page                                                 |
| POST   | `/sources/{id}/pages/{path:path}/assets`            | Upload an attachment into the page's sidecar dir. Auto-uniquifies, commits. |
| PUT    | `/sources/{id}/pages/{path:path}/assets/{filename}` | Replace an existing sidecar asset's bytes (diagram re-save).                 |
| GET    | `/sources/{id}/assets/{path:path}`     | Serve an asset file from the source working tree                  |
| POST   | `/sources/{id}/files`, `/sources/{id}/folders/{folder}/files` | Upload a sibling file into the repo root or a folder |

### SSH Keys

| Method | Path                     | Description                                              |
| ------ | ------------------------ | -------------------------------------------------------- |
| GET    | `/sources/keys`          | List SSH keys (label + fingerprint; no private key)      |
| POST   | `/sources/keys`          | Upload a private key PEM; returns fingerprint            |
| DELETE | `/sources/keys/{key_id}` | Remove an SSH key                                        |

### Search

| Method | Path                       | Description                                  |
| ------ | -------------------------- | -------------------------------------------- |
| GET    | `/search?q=...&limit=20`   | Full-text search; ranked hits with snippets  |

### System

| Method | Path        | Description                                      |
| ------ | ----------- | ------------------------------------------------ |
| GET    | `/healthz`  | Liveness                                         |
| GET    | `/readyz`   | Readiness (repo accessible, index loaded)        |
| GET    | `/info`     | Version, build, and `meta_dir` metadata          |

## Frontend

### Routes (Vue Router)

| Route                          | View               | Notes                                         |
| ------------------------------ | ------------------ | --------------------------------------------- |
| `/`                            | DashboardView      | Home / search entry                           |
| `/search`                      | SearchView         |                                               |
| `/source/:sourceId/:path*`     | SourcePageView     | Read page from a git source                   |
| `/edit-source/:sourceId/:path*`| SourceEditorView   | Edit page in a git source                     |
| `/watch/:label/:path*`         | WatchedPageView    | Read page from a watched local folder         |
| `/edit-watch/:label/:path*`    | WatchedEditorView  | Edit page in a watched local folder           |
| `/-/admin`                     | AdminView          | Git sources + SSH key management              |

### State

Pinia stores:

- `sourcesStore` — git source list, per-source trees, SSH key list
- `watchedStore` — watched-folder list, per-folder trees
- `uiStore` — theme, sidebar width, breakpoint

### Component tree (high level)

```
App.vue                            # sidebar (stacked panels) + main RouterView
├── SourceSidebarPanel.vue         # one per git source — sync status dot, expand/collapse
│   └── PageTree.vue
├── WatchedSidebarContent.vue      # collapsible section for watched local folders
│   └── PageTree.vue
└── <RouterView>
    ├── DashboardView.vue
    ├── SourcePageView.vue
    ├── SourceEditorView.vue
    │   └── Editor.vue             # TipTap instance
    │       └── EditorToolbar.vue
    ├── WatchedPageView.vue
    ├── WatchedEditorView.vue
    ├── SearchView.vue
    └── AdminView.vue              # git sources + SSH keys CRUD
```

## Editor and markdown roundtrip

This is the trickiest part of the system. We must:

1. Load `.md` from disk → render in TipTap (HTML / ProseMirror).
2. On save, produce `.md` bytes that are stable: re-saving an unchanged document must produce identical bytes.

### Approach

- **Parser:** a single canonical markdown-it instance, configured identically in Python (markdown-it-py) and TS (markdown-it). Same plugins, same options. This guarantees the api's server-rendered HTML matches the editor's view.
- **Serializer:** the editor exports TipTap state to markdown using `tiptap-markdown` for common nodes, with custom serializers for non-trivial nodes (tables, diagram embed, callout).
- **Stability tests:** the test suite includes a corpus of representative `.md` files. Each is parsed → serialized and compared byte-for-byte. Any drift is a bug.

#### Table-shape guard (2026-06-11)

`tiptap-markdown` only serializes a table that has the canonical GFM shape: the first row is all `tableHeader` cells, every later row is all `tableCell`s, and **each cell holds exactly one block**. Any violation makes it emit the literal placeholder `[table]`, silently destroying the table on save (an R1 violation). All three violations are one edit away — deleting the header row, inserting a row above the header, or pressing **Enter inside a cell** (which creates a second paragraph in that cell).

A ProseMirror `appendTransaction` guard (`TableHeaderGuard` in `Editor.vue`) normalizes every table after any doc change: it fixes cell types to match row position, and collapses any multi-block cell into a single paragraph, preserving the breaks between former blocks as `hardBreak`s. A custom `MarkdownHardBreak` serializes an in-cell hardBreak as a literal `<br>` (the GFM in-cell line-break idiom).

Because `<br>` must parse *back* into a hardBreak on reload (otherwise it re-escapes to `&lt;br&gt;` and breaks the round-trip), the editor's `tiptap-markdown` parser runs with `html: true`. This affects only the editor's **client-side** parser; R6's protection is render-time DOMPurify sanitization, which is unchanged (markdown-page saves already write the body verbatim — there is no save-time HTML scrub to weaken). The `tables-cell-linebreak.md` fixture pins the `<br>`-in-cell round-trip.

The read-only viewer (`markdown.ts`, client-side markdown-it with `html: false`) would otherwise escape that `<br>` to text. A narrow custom `text` render rule renders **only** the literal `<br>` / `<br/>` / `<br />` as a real line break and leaves every other raw HTML tag escaped — `<br>` is the single raw-HTML construct we render. It is inert (no script, no attributes, no handlers), so this does not relax R6; a tag with attributes (e.g. `<b onmouseover=…>`) still escapes. This is the only place the viewer interprets raw HTML.

### Supported markdown features

- CommonMark core
- GFM tables, task lists, strikethrough, autolinks
- Fenced code blocks with language hints
- Inline HTML (preserved verbatim, not edited via WYSIWYG)
- YAML frontmatter (treated as metadata, not body)
- Wiki-style links: `[[Page Title]]` (custom plugin)
- Drawio embed: `![alt](path/to/file.drawio.svg)` — detected by extension
- Mermaid: ` ```mermaid ` fenced blocks — rendered as SVG diagrams in view mode. In the editor, mermaid blocks are edited as source text with the `mermaid` language selected from the code-block language dropdown. A visual mermaid editor (live preview while editing) is tracked in the roadmap under "Beyond v1."
- Callouts: `> [!NOTE]` / `> [!WARNING]` style (GitHub-compatible)

### Source mode

The editor toggles between WYSIWYG and a CodeMirror 6 markdown source view. The source view is the canonical view; WYSIWYG is a projection of it. Toggling source → wysiwyg → source must be idempotent.

## Diagrams.net integration

### Storage format

Diagrams are saved as `.drawio.svg` — SVG with the original drawio XML embedded in a `<mxGraphModel>` element. This format:

- Renders as a regular image when displayed inline (no JS required).
- Is editable in any drawio install (web, desktop, VS Code extension).
- Is a single file, gits cleanly, diffs readably.

Diagrams are addressed in markdown as ordinary images:

```markdown
![Auth flow](auth-flow.drawio.svg)
```

The editor recognizes the `.drawio.svg` suffix and switches the rendered image into an "edit" affordance.

### Edit flow

1. User clicks "Insert diagram" in the toolbar (new) or **double-clicks** an existing `.drawio.svg` image (edit).
2. The SPA opens a modal containing an iframe pointing to `<drawio_url>/?embed=1&proto=json&spin=1&saveAndExit=1&ui=atlas`. The `drawio_url` is read from `GET /api/v1/config` at editor mount time, so the host is configurable per deploy.
3. The drawio iframe sends `init` via `postMessage`; the SPA replies with `{action:'load', xml}` — `xml` is empty for a new diagram or the mxfile string extracted from the existing SVG's `content="…"` attribute.
4. User edits and presses Save. Drawio sends `{event:'save'}`; the SPA responds with `{action:'export', format:'xmlsvg'}` to request an SVG that embeds the editable XML.
5. Drawio replies with `{event:'export', data:<dataURI>}`; the SPA decodes the base64 SVG payload.
6. The SPA writes the SVG via the existing asset routes:
   - **New diagram** → `POST /api/v1/sources/{id}/pages/{path}/assets` with a generated `diagram-YYYYMMDD-HHMMSS.drawio.svg` filename. The backend auto-uniquifies, commits, and returns the relative filename.
   - **Re-save** → `PUT /api/v1/sources/{id}/pages/{path}/assets/{filename}` — replaces the existing file's bytes in place, keeping the same path embedded in the markdown so the document doesn't need rewriting.
7. The editor inserts a new image node (new diagram) or refreshes the cached image (re-save).

The drawio container runs `jgraph/drawio:latest` and publishes its embed UI on a host port (8093 by default). Because the iframe is loaded by the user's browser — not proxied through the api container — `LIBRETA_DRAWIO_URL` must be a **browser-reachable** URL (e.g. `http://localhost:8093` for local dev, or `https://draw.example.com` behind a reverse proxy in production). Pointing it at `https://embed.diagrams.net` is supported but disables offline operation (R5) and is documented as opt-in only.

### Why not Mermaid only?

Mermaid is great for code-defined diagrams in CI workflows. It is not great for the kind of free-form architecture and box-and-line drawings users actually make in Confluence-like tools. Libreta supports both: Mermaid in fenced code blocks for code-as-diagram, drawio for hand-authored diagrams.

## Asset handling

- Uploads are scoped to a page. The upload endpoint takes the owning page path; the asset is written to that page's directory (see "Filesystem layout" — for an `index.md` page, the directory is the page's own folder; for a leaf page, it is the parent folder of the `.md` file).
- Uploads pass through size and MIME validation.
- Images: Pillow generates a thumbnail (max 1200 px wide, JPEG q85) saved alongside the original. (Deferred until image-handling proves it earns its weight — original-only upload is acceptable for v1.)
- All assets are committed to git. Trade-off: repo size grows. Acceptable at personal scale; LFS is a v2+ option.
- Deduplication: content-hash (SHA-256) is checked at upload time, **scoped to the owning page's directory**. Identical bytes already present in that directory → existing filename returned without a new commit. Bytes shared across two pages are duplicated (one copy per page); we accept that.
- Filename collisions with non-identical bytes get a numeric suffix: `photo.jpg` → `photo-2.jpg`, etc.
- **Orphans are kept, not garbage-collected on save.** If a user removes an image or link from a page, the underlying file stays in the page's directory. Rationale: every save is already a commit (R3), so removed assets are still reachable via git history — but a file the user *might* want back next minute should not vanish from the working tree on a reflexive edit. A future `libreta gc` CLI may surface and optionally remove orphan files; until then the policy is "the filesystem is append-only on the asset axis, modulo git rewrites." Deciding orphan status correctly requires scanning *all* sibling `.md` files in the directory (a leaf page and its index page share a directory and may both reference the same file), which is straightforward but deferred.

## Search

### v1: SQLite FTS5

- Background indexer subscribes to filesystem change events.
- Per-page row in `documents` virtual table: `(path, title, body, tags, updated)`.
- Query syntax surfaced minimally: phrase search, prefix search, tag filter (`tag:foo`).
- Snippets via FTS5's built-in `snippet()` function.

### Schema

```sql
CREATE VIRTUAL TABLE documents USING fts5(
    path UNINDEXED,
    title,
    body,
    tags,
    updated UNINDEXED,
    tokenize = 'porter unicode61 remove_diacritics 2'
);
```

### Reindex

The startup reindex is commit-aware. A `sources_meta(source_id, indexed_head)` row records the git HEAD each source was last indexed at:

- If a source's current HEAD equals `indexed_head`, the source is skipped entirely — no file I/O at all.
- If HEAD moved, the diff between old and new HEAD is asked of `pygit2`; only the changed `.md` files are reindexed, and files removed in the new tree are deleted from the index.
- If `indexed_head` is missing (first run after upgrade, or DB rebuild), the old mtime-based walk runs as a fallback and then records HEAD for next time.

On every commit, the affected paths are reindexed inline (single-page `index_page` call). A full rebuild is available via the CLI: `libreta reindex`. The startup reindex also runs as a background task — it does not block the HTTP server.

## Authentication (forward-looking)

Out of scope for v1. The API is designed to accept an authenticating principal middleware later without restructuring:

- All routes already accept (currently ignored) authorization headers.
- A `Principal` Pydantic model with a single `local-admin` instance is injected via FastAPI dependency.
- Future: replace dependency with a real auth resolver (session cookie, OIDC).

When multi-user lands:

- Local accounts via Argon2id password hashing, stored in SQLite.
- OIDC via Authlib (Authentik, Keycloak, Google).
- Per-tree ACLs stored in `.libreta-permissions.yaml` files inside `pages/` (versioned with the content).

## Deployment topology

### docker-compose.yml shape

```yaml
services:
  api:
    build: ./backend
    image: libreta-api:${VERSION:-latest}
    restart: unless-stopped
    environment:
      LIBRETA_META_DIR: /var/lib/libreta/meta   # sources.json, watched.json, search index
      LIBRETA_REPOS_DIR: /var/lib/libreta/repos    # cloned git source working trees
      LIBRETA_SSH_KEYS_DIR: /var/lib/libreta/ssh_keys
      LIBRETA_DRAWIO_URL: http://drawio:8080
    volumes:
      - libreta-data:/var/lib/libreta
    ports:
      - "8092:8080"                   # api: host 8092 → container 8080
    depends_on:
      - drawio

  frontend:
    profiles: ["dev"]                 # dev only — production serves SPA from api
    build: ./frontend
    environment:
      VITE_API_BASE: http://api:8080
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - pnpm-store:/pnpm-store
    ports:
      - "8091:5173"                   # frontend: host 8091 → container 5173
    depends_on:
      - api

  drawio:
    image: jgraph/drawio:latest
    restart: unless-stopped
    ports:
      - "8093:8080"                   # drawio: host 8093 → container 8080

volumes:
  libreta-data:    # repos + ssh_keys + meta — the only volume you need to back up
  pnpm-store:
```

### Production hardening (user responsibility)

- Place behind a reverse proxy (Caddy, Traefik, nginx) for TLS.
- Configure remote git push via SSH key mounted into the api container.
- Schedule offsite backups of `./content`.

## Key decisions

The following are decisions worth pinning down explicitly. Each is revisitable but should not be revisited casually.

### D-01 — Filesystem is the source of truth

Not the database. Not git objects. The working tree.

**Why:** it is what the user can read with any tool, on any system, with no Libreta dependency. It is the data-portability promise.

**Consequence:** every API write goes through the same filesystem-then-commit code path. There is no path that updates state without producing a `.md` file.

### D-02 — pygit2, not subprocess git

**Why:** pygit2 wraps libgit2 in-process. No subprocess overhead, no shell-quoting bugs, atomic operations, no race with concurrent git commands.

**Consequence:** adds a non-trivial native dependency. We accept this cost; it is paid by `pip install` and the docker image build.

### D-03 — TipTap, not Toast UI / Milkdown / a custom editor

**Why:** largest extension ecosystem of the modern markdown WYSIWYG editors. Solid Vue integration. Battle-tested in production wikis (Docmost, others).

**Consequence:** markdown roundtrip is our responsibility (TipTap is HTML-native). Mitigated by stability tests.

### D-04 — Vue 3, not React or Svelte

**Why:** familiar, mature, less ceremony than React for solo development; richer editor ecosystem than Svelte.

**Consequence:** smaller hiring pool than React if this ever becomes a team project; acceptable.

### D-05 — drawio as a sidecar, not bundled

**Why:** upstream image is well-maintained; we get updates for free. Bundling drawio's JS into our app would be a maintenance tax.

**Consequence:** two containers in the compose file instead of one. Worth it.

### D-06 — Single-instance, single-writer model

**Why:** avoids merge conflicts entirely. A shared editor across multiple servers is a v3+ problem, not a v1 problem.

**Consequence:** external edits via `git pull` are supported (we re-read), but two Libreta instances pointed at the same remote will fight. Don't do that.

### D-07 — Git as version control, not as content store

We do not read content from git objects on the hot path. We read from the working tree. Git is for history and remote sync.

**Why:** performance (file reads vs. object lookups), simplicity, and the working tree's role as the user-facing artifact.

### D-08 — No realtime collaboration in v1

**Why:** Y.js / Hocuspocus-grade collaboration is a project of its own. v1 is a personal wiki; collaboration is v3.

### D-09 — Git sources replace the fixed content bind-mount (2026-05-03)

The original design had a single bind-mounted `./data/content` directory that Libreta owned. This is replaced by **dynamically-configured git sources**: each source is a remote git repository that Libreta clones to a Docker named volume, writes into with local commits, and pushes asynchronously.

**Why:** The user's actual wiki content already lives in a remote git repository. A fixed bind-mount requires manual initialisation and makes deployment fragile (the server needs a clone of the content repo in exactly the right place before Libreta can start). Git sources let the deployment be stateless beyond the `libreta-data` volume: add a source in the Admin UI, Libreta clones it, done.

**Consequence:** `LIBRETA_CONTENT_DIR` (later renamed — see D-11) is now used only for configuration files (`sources.json`, `watched.json`) and the search index — it no longer holds wiki content. The `libreta-data` named Docker volume is the single backup target. A two-Libreta-instances-on-the-same-remote scenario is still a conflict risk (D-06 still applies).

### D-11 — Remove the legacy main wiki; rename `content_dir` → `meta_dir` (2026-06-03)

D-09 left the single-content-repo code in place (the `/pages` API, the `/w/...` and
`/edit/...` routes, `PageView`/`EditorView`/`HistoryView`/`DiffView`, the `/assets/{path}`
server, and `storage/pages.py`) even though the bind-mount no longer held content. That
"main wiki" surfaced as an empty, confusing entity (e.g. a stray "Main wiki" option in the
editor's link picker). It is now **fully removed** from backend and frontend.

**Consequence:** With no content repo left, `content_dir` was a misnomer — it only ever
holds Libreta's own metadata. The setting and env var are renamed `meta_dir` /
`LIBRETA_META_DIR` (default `./data/meta`; the deployed volume path `/var/lib/libreta/meta`
is unchanged). Search is now sources-only (the `content_dir/pages` index fallback is gone).
Inline image/diagram attachments require editing inside a git source; the watched-folder
editor no longer routes attachment uploads through the (deleted) main-wiki asset endpoint.

### D-10 — Local commit first, async push (2026-05-03)

Every page save commits to the local clone immediately and returns. A background push worker then pushes to the remote with up to 3 retries (exponential backoff). Push errors are surfaced in the Admin page and sidebar but do not block editing.

**Why:** Remote git operations (especially over SSH) can take seconds and can fail transiently. Blocking the user's save on a push would degrade the editing experience significantly. The local commit provides immediate durability (the data is safe in the volume) and git history; the push is a best-effort sync. Losing the volume without a recent push means losing the commits since the last push — acceptable for a personal wiki, not acceptable to silently ignore.

## Open questions

- **Wiki-link resolution:** `[[Pizza Dough]]` — fuzzy match on title, or strict path? (Leaning: title fuzzy with a disambiguation UI when ambiguous.)
- **Rename strategy:** `git mv` plus a link-fixup pass across the corpus, or break links and notify? (Leaning: rewrite links in a single commit, surfaced in the diff.)
- **Soft delete vs. hard delete:** the file leaves the working tree; git history retains it regardless. (Leaning: hard delete from working tree.)
- **Asset garbage collection:** orphaned uploads — periodic sweep or never? (Leaning: weekly sweep with a quarantine period.)
- **Default branch and remote semantics:** opinionated to `main` and a single configured remote.
- **CRDT layer for offline edits:** out of scope until v3, but the data model should not preclude it.
