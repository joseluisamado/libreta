# ROADMAP.md — Libreta

A milestone-based plan, not a calendar. Each milestone is a coherent slice of value that can be released and used. We finish each one before starting the next.

> Dates are deliberately omitted. This is a side project; pace will vary.

---

## M0 — Foundations

**Goal**: Make the project ready to be developed in.

- [x] Repo initialised with this set of project documents
- [x] `backend/` skeleton: FastAPI app boots, `/healthz` returns 200
- [x] `frontend/` skeleton: Vue 3 + Vite "hello world" loads in the browser (Tiptap deferred to M2)
- [x] `docker-compose.yml` brings backend + frontend (dev profile) up together
- [x] CI pipeline (Gitea Actions / GitHub Actions): lint + type-check + tests run on every push
- [x] `pre-commit` hooks: ruff format/check, mypy, eslint, prettier
- [x] Pinned dependency versions and reproducible builds (`uv.lock`, `pnpm-lock.yaml`)

**Exit criteria**: A new contributor can `git clone`, `docker compose --profile dev up`, and see the empty editor in their browser.

---

## M1 — Read-only wiki

**Goal**: Libreta can render an existing git repo of markdown files as a navigable wiki. No editing yet.

- [x] Filesystem walker: discover all `.md` pages and produce the page tree
- [x] Page reader: parse frontmatter + body, surface metadata
- [x] `GET /api/v1/pages/{path}` returns markdown + parsed frontmatter
- [x] `GET /api/v1/pages/tree` returns the full page hierarchy
- [x] Frontend: page tree sidebar, markdown rendering (read-only)
- [x] Frontend: breadcrumbs
- [x] Frontend: tables, code blocks with syntax highlighting, task lists, links rendered correctly
- [x] Image attachments rendered (regular images, not yet drawio)
- [x] Mobile-responsive shell (basic flex layout exists; needs collapse/drawer for narrow viewports)

**Exit criteria**: Point Libreta at a hand-written git repo of markdown files and read them in the browser as you would on GitHub. No editing surface visible.

---

## M0.5 — Read-experience polish

**Goal**: Tighten the read-only wiki before starting M2. Real content (DokuWiki import) surfaced rough edges that are cheap to fix now and expensive to fix later once editing layers on top.

- [x] Synthesised directory pages: when `<dir>/` has no `index.md` or `<dir>.md`, the API returns a generated stub so the frontend can still render breadcrumbs and a folder listing (e.g. `/w/devel/bash` shows `heredoc` as a child).
- [x] Generic asset link rewriting: `<a href="foo.pdf">` (and other relative links to non-page files) resolve through `/api/v1/assets/...`, same as images. Fixes broken PDF/zip downloads.
- [x] Sidebar: folders visually distinct from pages; folders are collapsible (state persisted in localStorage); icon + lighter weight signals "open me to expand."
- [x] GitHub-style markdown rendering: prose width, type scale, code-block chrome (background, border-radius, language label), syntax-colour theme matching GitHub light. Theme toggle deferred.
- [x] Math blocks: render LaTeX inside `$...$` (inline) and `$$...$$` (block) with KaTeX. No DSL; pure math passthrough.
- [x] Reading-width toggle: upper-right button switches between "standard" (3xl prose) and "wide" (full viewport). Persisted in localStorage. Default: standard.
- [x] Back-to-top floating button: appears once the page has scrolled past one viewport; smooth-scrolls to top on click.
- [x] One-shot tag computation: a CLI / Make target walks every page, derives tags from titles + body, writes them into frontmatter only when tags are missing or empty. Idempotent.
- [x] M2 hand-off: in M2's save lifecycle, when a page is saved for the first time and has no tags, derive and persist them. Spec lives here, implementation lands with the editor.

**Exit criteria**: navigating the imported corpus feels like reading a polished wiki — no broken links, every folder is browsable, code looks like GitHub, math renders, reading width is ergonomic.

---

## M2 — Editing & git commits

**Goal**: WYSIWYG editor with markdown round-trip, every save is a commit.

- [x] Tiptap editor with the v1 extension set: headings, lists, links, code, blockquote, hard-break, history
- [x] Markdown serializer round-trips a fixture corpus byte-identically (the invariant from `ARCHITECTURE.md` "Editor and markdown roundtrip")
- [x] `PUT /api/pages/{path}` writes file + git commit via pygit2
- [x] `DELETE /api/pages/{path}` and `POST /api/pages/{path}/move` (rename)
- [x] Auto-set `updated` frontmatter on save; preserve `created`
- [x] Page history view: read git log for a file, render commit list
- [x] Diff view: side-by-side or inline diff between two revisions
- [x] External-edit watcher: not needed — every page request reads from disk, so editing a `.md` file in another tool surfaces on next reload (no watcher process required until the SQLite index lands in M3)

**Exit criteria**: Daily-driver-able for a single user editing markdown. Round-trip tests passing for ≥ 50 fixtures.

---

## M3 — Tables, attachments, search

**Goal**: Confluence-grade table editing, file uploads, full-text search.

- [ ] Tiptap table extension with column resize, header row, cell background colour
- [ ] Tables round-trip through GFM markdown without information loss
- [ ] Image upload: drag & drop, paste from clipboard, "insert image" button
- [ ] Arbitrary file upload as attachment (PDFs, zips, etc.) with download links
- [ ] Attachment storage layout per `ARCHITECTURE.md` "Filesystem layout" (`assets/` partitioned by upload date)
- [ ] SQLite FTS5 index built and updated on save
- [ ] `GET /api/search?q=...` returns ranked results
- [ ] Search UI in the frontend, with snippets and keyboard navigation
- [ ] `libreta reindex` CLI subcommand to force a full rebuild

**Exit criteria**: All non-diagram editing features feel "done." Search finds anything in under 300 ms.

---

## M4 — Diagrams.net integration

**Goal**: First-class diagrams.net editing, end to end.

- [ ] `jgraph/drawio` container in the Compose stack
- [ ] Custom `DrawioImage` Tiptap extension (per `ARCHITECTURE.md` "Diagrams.net integration")
- [ ] "Insert diagram" toolbar button → opens drawio in a modal
- [ ] postMessage protocol implemented for load/save/exit
- [ ] Saved diagrams stored as `.drawio.svg` under `assets/diagrams/YYYY/MM/`
- [ ] Editing an existing diagram (double-click → reopens with current content)
- [ ] Diagrams render in markdown view as plain images (because they are SVGs)
- [ ] Diagrams export with the wiki: cloning the content repo elsewhere preserves all editable diagrams
- [ ] Documentation: how to point Libreta at the public diagrams.net instead of self-hosted (for users who prefer it)

**Exit criteria**: All v1 features from `PROJECT.md` "Goals → Must have (v1.0)" and "Functional requirements" are implemented. Libreta is a viable BookStack/Wiki.js alternative for solo users.

---

## M5 — v1.0 release

**Goal**: Ship it.

- [ ] Production Docker Compose example with Caddy reverse proxy and TLS
- [ ] Backup & restore guide (it's just `git push` of the content repo, but document it)
- [ ] Migration guide: importing from BookStack / Wiki.js / Notion exports / Obsidian vaults
- [ ] User-facing docs site (built with Libreta itself, dogfooded)
- [ ] Performance benchmarks against the targets in `PROJECT.md` "Non-functional requirements"
- [ ] Security review: path traversal, sanitisation, dependency audit
- [ ] License finalised (likely AGPL-3.0)
- [ ] First public release tag: `v1.0.0`

**Exit criteria**: First external user installs Libreta and uses it for a week without filing critical bugs.

---

## Beyond v1: planned but not committed

These are tracked here so the v1 architecture doesn't accidentally foreclose them.

### M6 — Multi-user & auth

The first big architectural extension. Likely requires:

- A users table (in SQLite or a separate users.db)
- Session management (cookie-based for the web UI, optional API tokens)
- Per-user commit attribution (`git commit --author` from the logged-in user)
- A simple ACL model: read/write/admin per wiki, with future room for per-tree ACLs stored alongside content (see `ARCHITECTURE.md` "Authentication" for the proposed `.libreta-permissions.yaml` layout)
- Pluggable auth: local password, OIDC, optionally LDAP

This is a large change. Will be designed in its own `AUTH-DESIGN.md` before implementation.

### M7 — Backlinks, tags, graph view

Wiki-grade navigation:
- Auto-discovered backlinks (which pages link to this one)
- Tag pages (auto-generated index of all pages with a tag)
- Optional Obsidian-style graph view

Stored in the SQLite index, rebuildable from files.

### M8 — Templates & snippets

User-defined page templates. Stored as markdown files in `_meta/templates/`. Inserted via a "New from template" UI.

### M9 — Real-time-ish collaboration (maybe)

The hardest item, deliberately last. Not real-time CRDT collab — just optimistic locking with a "someone else is editing this" indicator and a server-side merge offer if conflicting commits land. May never ship if it doesn't earn its complexity.

### M10 — Plugin / extension API

A typed extension API for client-side editor extensions and server-side render hooks. **Not a plugin marketplace.** Just a stable surface for power users to add features without forking.

---

## What we will not do

Restating from `PROJECT.md` "Non-goals" because roadmap docs are where scope creep gets introduced:

- ❌ Custom widget DSL or block syntax beyond CommonMark + GFM
- ❌ Embedded spreadsheets / kanban / forms
- ❌ Native mobile apps
- ❌ Plugin marketplace
- ❌ A built-in real-time editor
- ❌ Multi-wiki within a single instance (run multiple instances instead)

If a future user request runs into this list, the answer is "no, by design."
