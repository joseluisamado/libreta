# PROGRESS.md — Libreta

Living document. Update as work progresses. Latest at the top.

> Convention: each session/work-block adds a dated entry. Keep entries short — link to commits/PRs for detail. The "Status" line at the top must always reflect reality.

---

## Status

**Current milestone**: M2 — Editing & git commits (done)
**Phase**: Diff view between two revisions landed; external-edit watcher resolved as not-needed at this stage
**Next action**: Start M3 — Tables, attachments, search

## At a glance

| Milestone | Status |
|---|---|
| M0 — Foundations | 🟢 Done |
| M1 — Read-only wiki | 🟢 Done |
| M0.5 — Read-experience polish | 🟢 Done |
| M2 — Editing & commits | 🟢 Done |
| M3 — Tables, attachments, search | ⚪ Not started |
| M4 — Diagrams.net integration | ⚪ Not started |
| M5 — v1.0 release | ⚪ Not started |

Legend: ⚪ not started · 🟡 in progress · 🟢 done · 🔴 blocked

---

## Log

### 2026-05-02 — M2 Diff view + external-edit watcher closed out

Closed the last two M2 items. The diff view lets users compare any two revisions of a page; the external-edit watcher turned out to be unnecessary at this stage.

- **`DiffEntry` model** added to [models.py](../backend/src/libreta/models.py): `{ old_sha, new_sha, old_path, new_path, patch }`. `patch` is unified-diff text; empty string when contents are identical. `old_path` / `new_path` are null when the file didn't exist on that side (creation / deletion).
- **`storage/repo.py`**: `_resolve_commit()` peels any object (tag → commit) via `revparse_single`, raising `PageNotFoundError` for unknown SHAs. `_blob_text_at()` reads the blob at a path in a commit's tree. `_get_file_diff_sync()` builds a unified diff with `difflib.unified_diff`. Async wrapper `get_file_diff()` runs it on a thread.
- **`api/pages.py`**: `GET /pages/{path}/diff?a=<sha>&b=<sha>` — query params instead of path params so short SHAs don't tangle with the greedy `:path` matcher.
- **Frontend**: `DiffEntry` type + `getPageDiff()` client function. New [DiffView.vue](../frontend/src/views/DiffView.vue) at `/diff/:path*?a=...&b=...` renders the unified diff line-by-line with green/red/blue tinting (add/del/hunk). [HistoryView.vue](../frontend/src/views/HistoryView.vue) gained two radio columns ("A" older / "B" newer) and a Compare button — pre-selects the two newest commits — plus a per-row "diff vs prev" shortcut.
- **External-edit watcher**: marked done in the roadmap with a note. The read path already re-reads the file on every GET, so external edits surface on browser reload. The watchdog described in `ARCHITECTURE.md` is only useful once the SQLite search index lands (M3); it can be added then if cache invalidation actually needs it.
- **Tests**: backend `test_diff.py` (4: round-trip, identical, creation, unknown SHA → 404). Frontend `DiffView.spec.ts` (4: empty patch, add/del/hunk classes, missing query params, API failure). All HistoryView tests still pass against the new layout.

**Pre-flight**: backend 50/50 tests pass, ruff/mypy clean. Frontend 57/57 tests pass, vue-tsc clean, eslint clean (1 pre-existing `v-html` warning), prettier clean, build succeeds.

### 2026-05-02 — M2 Delete, move, new page / new folder

Implemented the remaining M2 CRUD operations: page deletion, page rename/move, and UI for creating new pages and folders from directory pages.

- **`PageAlreadyExistsError`** (409) added to `errors.py` for move-target conflicts.
- **`PageMove` model** (`new_path: str`) and `is_index: bool` field on `PageWrite` for distinguishing bare `.md` pages from directory `index.md` pages.
- **`storage/pages.py`**: added `delete_page()` (unlinks the `.md` file), `move_page()` (renames files; moves the entire directory tree for `index.md`-backed pages), and plumbed `prefer_index` through `_determine_write_file` / `write_page` so the frontend can create `<dir>/index.md` pages for folders.
- **`storage/repo.py`**: added `delete_commit()` (`index.remove` + commit with `"delete"` message) and `move_commit()` (handles single-file and directory-tree moves, removing old paths and staging new ones; commit message `"rename old -> new"`). All share the same asyncio lock.
- **`api/pages.py`**: `DELETE /{path}` returns 204; `POST /{path}/move` returns the `PageRead` at the new location. PUT now passes `is_index` through to the storage layer.
- **Frontend API**: `deletePage()`, `movePage()` added alongside a `requestNoContent()` helper for 204 responses. `PageWrite.is_index` and `PageMove` types added.
- **PageView.vue**: "In this folder" section now renders for all directory pages (not just those with children). Two buttons — "+ New page" and "+ New folder" — prompt for a name, slugify it, create the page via the existing PUT endpoint (`is_index: true` for folders), refresh the tree, and navigate to the editor.
- **Tests**: backend +10 tests (4 delete, 5 move, 1 is_index creation). All 37 backend tests pass; all 48 frontend tests pass.

**Pre-flight**: backend 37/37 tests pass, ruff/mypy clean. Frontend 48/48 tests pass, vue-tsc clean, eslint clean (1 pre-existing `v-html` warning).

### 2026-05-02 — M2 Save endpoint + git commit on save

Wired the full save lifecycle: PUT endpoint → write file → git commit via pygit2 → frontend Save button. This is the core loop that makes Libreta an editing tool.

- **`PageWrite` model** (`backend/src/libreta/models.py`): body-only request model. Frontmatter is preserved from existing file; `updated` is auto-set server-side.
- **`storage/repo.py`**: new module for git operations. `open_repo()` wraps `pygit2.Repository`, `commit_page_sync()` stages + commits with HEAD parent (handles empty repo), `commit_page()` wraps it with asyncio lock serialization. Commit author: `Libreta <libreta@localhost>` per CLAUDE.md §6.3.
- **`storage/pages.py`**: added `_write_page_sync` + `write_page()` wrapper. Preserves existing `title`, `created`, `tags`; sets `updated` to `datetime.now(UTC)`; determines verb (`create` vs `update`) from whether the file existed.
- **`api/pages.py`**: added `PUT /pages/{path:path}`. Resolves the on-disk file path, calls `write_page` + `commit_page`, returns `PageRead`.
- **Frontend API layer**: `PageWrite` type added; `request()` generalized with optional `RequestInit`; `savePage()` added.
- **EditorView.vue**: Save button now has three states — muted/disabled (not dirty), blue/clickable (dirty), spinner + "Saving…" (in flight). Error text shown on failure. On success, `isDirty` resets and the page ref updates with the server response.
- **Tests**: conftest inits a git repo via `pygit2.init_repository` before populating pages. 4 new PUT tests: update existing, create new, traversal blocked, frontmatter preserved. Frontend EditorView save tests (4): button rendering, disabled state, loading state, error display.

**Pre-flight**: backend 27/27 tests pass, ruff/mypy clean. Frontend 47/47 tests pass, eslint clean (1 pre-existing `v-html` warning), vue-tsc clean, build succeeds.

### 2026-05-02 — M2 Tiptap editor integration (first element)

Wired the WYSIWYG editor — loading page content into a functional Tiptap instance
with toolbar and a Cancel back to read mode. No save/commit wiring yet.

- **Dependencies**: added `@tiptap/vue-3`, `@tiptap/starter-kit`, `@tiptap/pm`, `@tiptap/extension-task-list`, `@tiptap/extension-task-item`, `@tiptap/extension-link`, `@tiptap/core`, `tiptap-markdown`, `@types/node` (dev).
- **Editor.vue** (`src/components/Editor/Editor.vue`): Tiptap wrapper with StarterKit (headings 1–3, bold, italic, strike, code, code-block, blockquote, bullet/ordered lists, hard-break, hr, history, dropcursor, gapcursor) + TaskList + TaskItem + Link + Markdown (html: false). Exposes `getMarkdown()` and the editor instance; emits `update` with dirty tracking via `hasBeenSet` flag.
- **EditorToolbar.vue** (`src/components/Editor/EditorToolbar.vue`): 15-button toolbar grouped into undo/redo, inline formatting (B/I/S/code/link), headings (H1/H2/H3), and block elements (blockquote, bullet/ordered/task lists, hr). Each button has inline SVG, tooltip with shortcut, and `is-active` styling.
- **EditorView.vue** (`src/views/EditorView.vue`): Route component at `/edit/:path*`. Loads page via API, renders toolbar + editor, top bar with Cancel (router-link back to `/w/:path`) and disabled Save placeholder (next M2 step). Handles loading, error, and loaded states.
- **Router** (`src/router.ts`): added `/edit/:path(.*)*` route with lazy-loaded `EditorView.vue`.
- **PageView.vue**: added an Edit button (pencil SVG, RouterLink to `/edit/${page.path}`) positioned next to the PageToolbar buttons. Only shown when page is loaded.
- **Round-trip test infrastructure** (`tests/round-trip/`): 10 canonical fixture files covering all v1 extensions + `roundtrip.test.ts` with 20 tests (stability: pass → pass identical; byte-identical: canonical fixture matches pass-1 output). Fixtures auto-canonicalized via `UPDATE_FIXTURES=true` env var. Known tiptap-markdown normalization: soft breaks → spaces, blockquote continuations → single line (nested blockquotes are an edge case), task list items get blank line separators, `$$` math blocks become single-line with escaped underscores.
- **Helper** (`src/markdownStorage.ts`): typed accessor for `editor.storage.markdown.getMarkdown()` to work around tiptap-markdown's type augmentation not propagating through vue-tsc.

**Pre-flight**: backend 23/23 tests pass (no changes). Frontend 43/43 tests pass (15 existing + 8 Editor.vue + 20 round-trip). ESLint clean (1 pre-existing `v-html` warning), prettier clean, vue-tsc clean, build succeeds.

### 2026-05-02 — M0.5 polish + DokuWiki import

After importing a real DokuWiki corpus (96 pages / 74 media), several rough edges
surfaced. Captured them as M0.5 in the roadmap and worked through in one pass.

- **Synthesized directory pages**: backend returns an empty-body stub when a path resolves to a directory with no `<dir>.md` or `<dir>/index.md`, so the frontend can still render breadcrumbs + a folder listing (e.g. `/w/devel/bash`). Test in `backend/tests/test_pages.py`.
- **Generic asset links**: markdown renderer now rewrites `<a href="foo.pdf">` (and other recognised non-page extensions) through `/api/v1/assets/...`, the same way images already work. Fixes broken PDF/zip/etc downloads in imported pages.
- **KaTeX math**: small inline plugin renders `$x$` (avoiding `$5 and $10` false positives) and `$$ ... $$`. KaTeX CSS bundled.
- **GitHub-style prose**: rewrote `.prose` styling top-to-bottom against the GitHub light palette; switched code blocks to `<pre class="hljs">` with the `highlight.js/styles/github.css` theme and a subtle language label.
- **Sidebar**: folders get a chevron toggle, slightly heavier label weight, and a collapsed-by-default-no-but-persisted open state in localStorage. Pages and folders both navigate; the toggle controls just the subtree.
- **Reading-width toggle + back-to-top**: floating buttons at the page upper-right. Width pref (`standard` / `wide`) persisted to localStorage. Back-to-top appears once the main pane has scrolled past one viewport.
- **Tag computation**: `scripts/compute_tags.py` walks `pages/`, scores terms with TF-IDF (heading/title-boosted), writes 3–5 tags into frontmatter for any page that has none — or whose only tag is the `imported` placeholder. `make compute-tags` / `make compute-tags-dry`. 92 pages tagged on first run.
- **M2 hand-off**: roadmap entry only — when the editor lands, save-for-the-first-time will trigger the same tag computation if the page has no tags.

Bonus fix found mid-stream: the dev compose overlay needed `PYTHONPATH=/app/src` because `pip install` at image-build time copies the source into `site-packages`, which Python then prefers over the bind-mounted `/app/src`. Without this, uvicorn `--reload` would notice file changes but still execute the baked-in copy. Documented inline in [docker-compose.dev.yml](../docker-compose.dev.yml).

**Pre-flight**: backend 23/23 tests pass, ruff/mypy clean. Frontend 15/15 tests pass, vue-tsc clean, eslint clean (one expected `v-html` warning), build succeeds.

### 2026-05-02 — Close out M0 + M1

Wrapped the deferred M0 items and the remaining M1 polish.

- **CI** (`.gitea/workflows/ci.yml`, mirrored to `.github/workflows/ci.yml`): two jobs, backend (ruff format/check, mypy --strict, pytest) and frontend (prettier, eslint, vue-tsc, vitest, vite build). Workflow uses only actions Gitea's `act_runner` ships with by default (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `pnpm/action-setup@v4`) so it runs unmodified on either host.
- **Pre-commit** (`.pre-commit-config.yaml`): ruff format/check, mypy (scoped to `backend/src/`), prettier and eslint via local hooks that shell into `frontend/`.
- **Frontend breadcrumbs**: `Breadcrumbs.vue` walks the page path against the tree store to look up titles, falling back to humanised segments. Wired into `PageView`.
- **Image attachments**: new `/api/v1/assets/{path}` endpoint serves any non-`.md` file inside the content dir with strict path validation (rejects traversal, hidden segments, `.md`). The markdown renderer rewrites relative `![](images/foo.png)` to `/api/v1/assets/pages/<dir>/images/foo.png`; absolute and `data:` URLs pass through.
- **Mobile shell**: `App.vue` now renders a top bar with a hamburger toggle below `md`; the sidebar becomes a slide-in drawer with backdrop, auto-closes on navigation. `md+` viewports render the original two-column layout.
- **ESLint flat config** added (`frontend/eslint.config.js`) so `pnpm lint` actually runs under ESLint 9.

**Pre-flight**: backend 22/22 tests pass, ruff/mypy clean. Frontend 8/8 tests pass, typecheck clean, eslint clean (one unrelated `v-html` warning suppressed by design — markdown HTML is sanitised by markdown-it with `html: false`), prettier clean, build succeeds.

### 2026-05-01 — M0/M1 scaffold

Initial code lands. Backend and frontend both boot; the read path works end-to-end on the seed corpus.

- `backend/`: FastAPI app, `uv`-managed, with `/api/v1/{healthz,readyz,info,pages/tree,pages/{path}}`. Path validation in `storage/paths.py`; page reading + tree walking in `storage/pages.py`. Strict typed errors; `LibretaError` → JSON via central handler. **18 pytest tests pass; `ruff check` clean; `mypy --strict` clean.**
- `frontend/`: Vue 3 + Vite + TS + Tailwind + Pinia + Vue Router. `PageTree` sidebar, `PageView` route, typed API client. Markdown rendered via `markdown-it` + GFM-style plugins + highlight.js. Raw HTML disabled at render (P4/R6). **5 vitest tests pass; `vue-tsc --noEmit` clean; `pnpm build` succeeds.**
- `docker-compose.yml`: three services (`api`, `frontend` under `dev` profile, `drawio`). Bind-mounts `./data/content`.
- `data/content/`: seeded with `pages/index.md` and a couple of recipe pages, initialised as its own git repo with one commit (per CLAUDE.md §6.3).
- Architecture doc updated to describe the three-service dev / two-service prod layout.

Deferred from M0: CI, pre-commit hooks. Will land in a follow-up.

### 2026-05-01 — Project kickoff

Created foundational documents:
- `README.md`
- `PROJECT.md` — vision, principles, non-goals
- `ARCHITECTURE.md` — full technical architecture
- `ROADMAP.md` — milestones M0 → M5+
- `PROGRESS.md` — this file
- `CLAUDE.md` — conventions for Claude Code

Stack decisions locked in:
- Backend: Python 3.12 + FastAPI + pygit2 + SQLite FTS5, managed with uv
- Frontend: Vue 3 + Vite + Tiptap + Tailwind, managed with pnpm
- Diagrams: jgraph/drawio sidecar, integration via iframe + postMessage
- Storage: filesystem-first git repo at `./data/content`; auxiliary search index lives in a separate Docker volume, regenerable from the filesystem

Open questions logged in `ARCHITECTURE.md` "Open questions" section.

**Next session**: M0 kickoff — initialise the repo, create both skeletons, get `docker compose --profile dev up` working end-to-end.

---

## Backlog (unscheduled)

Things noted along the way that don't yet have a milestone home:

- _(empty)_

---

## Decisions log

Significant architectural or product decisions that are worth remembering. Format: date · short description · rationale.

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-01 | Build from scratch rather than fork Wiki.js or wrap BookStack | No existing tool combines markdown-on-disk + git-canonical + drawio + WYSIWYG. Forking either inherits architectural mismatches. |
| 2026-05-01 | Python / FastAPI for the backend | Stated user preference; fits the lightweight async API shape. |
| 2026-05-01 | pygit2 over GitPython | libgit2 bindings are faster and have stricter, well-defined semantics. |
| 2026-05-01 | Diagrams as `.drawio.svg` (not `.drawio` + separate render) | Single file, renders as image anywhere, editable in drawio. Best portability story. |
| 2026-05-01 | SQLite FTS5 for search; no separate search service | Adequate for 10k pages; no extra container; regenerable from filesystem. |
| 2026-05-01 | "Libreta" as working name | Placeholder; rename via find-replace before first public release if desired. |
| 2026-05-01 | Defer auth to M6 | Single-user-first per `PROJECT.md` P6. Multi-user is a large design problem that benefits from real usage before being designed. |

---

## How to update this file

When you finish a chunk of work:

1. Update the **Status** block at the top.
2. Update the **At a glance** milestone table if a milestone moved.
3. Add a dated entry to **Log** describing what changed, in 3-8 bullet points.
4. If a non-trivial decision was made, append to the **Decisions log**.
5. Move any "I noticed but didn't fix" items into **Backlog**.

Commit this file alongside the work it documents.
