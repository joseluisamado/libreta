# PROGRESS.md — Libreta

Living document. Update as work progresses. Latest at the top.

> Convention: each session/work-block adds a dated entry. Keep entries short — link to commits/PRs for detail. The "Status" line at the top must always reflect reality.

---

## Status

**Current milestone**: M3.5 — complete ✅
**Next milestone**: M4 — Diagrams.net integration
**Next action**: Start M4 — `DrawioImage` Tiptap extension, postMessage protocol, toolbar button.

---

## 2026-05-04 — Sidecar attachment model

**What changed**: Replaced the `index.md`-based directory model with a sidecar-directory model for attachments.

**Before**: Pages could be `foo.md` (leaf) or `foo/index.md` (index). Attachments went in the parent directory for leaf pages, or the same directory for index pages. The `is_index` flag propagated through the entire stack.

**After**: Every `.md` file is a standalone page. Attachments live in a hidden sidecar: `.<pagename>.md/`. A page at `saml.md` has its images in `.saml.md/`. `foo.md` and `foo/` coexist — the `.md` is the page, the directory holds sub-pages.

**Why**: Unambiguous attachment ownership, compatible with existing flat repos, simpler data model (no `is_index` flag anywhere).

**Migration**: `scripts/migrate_to_sidecars.py` converts old repos. Ran against the `libreta-data` source: 31 index→page promotions, 73 attachments moved.

**Also**: Removed underscore-prefix hiding — `_plan materials/` and `_meta/`-style directories are now visible in the tree.

**Files touched**: `models.py`, `paths.py`, `pages.py`, `assets.py`, `sources.py`, `watched.py`, `repo.py`, `api/pages.py`, `api/sources.py`, `api/assets.py`, `types.ts`, `markdown.ts`, `Editor.vue`, 5+ views, all test files, `ARCHITECTURE.md`, `import_dokuwiki.py`.

## At a glance

| Milestone | Status |
|---|---|
| M0 — Foundations | 🟢 Done |
| M1 — Read-only wiki | 🟢 Done |
| M0.5 — Read-experience polish | 🟢 Done |
| M2 — Editing & commits | 🟢 Done |
| M3 — Tables, attachments, search | 🟢 Done |
| M3.5 — Git sources & remote deploy | 🟢 Done |
| M4 — Diagrams.net integration | ⚪ Not started |
| M5 — v1.0 release | ⚪ Not started |

Legend: ⚪ not started · 🟡 in progress · 🟢 done · 🔴 blocked

---

## Log

### 2026-05-03 — M3.5 Git sources & first remote deployment

Replaced the fixed `data/content` bind-mount with a fully dynamic git-source model. All wiki content now lives in remotely-configured git repositories that Libreta clones, writes into, and keeps in sync automatically.

- **`storage/sources.py`** (new): clone, fetch+fast-forward, push via `pygit2.KeypairFromMemory` (in-process SSH, no subprocess). Per-source asyncio write lock. Detects diverged branches (doesn't force-push; logs a warning). Page tree walk, read, and write all mirror the watched-folder layer but commit into git on every write.
- **`storage/ssh.py`** (new): SSH key store backed by the Docker volume. Keys stored at mode 0600, fingerprint computed from the PEM, index in `ssh_keys/index.json`. `make_callbacks()` produces a `RemoteCallbacks` subclass that injects `KeypairFromMemory` at authentication time.
- **`services/sync.py`** (new): two background asyncio tasks wired into FastAPI `lifespan`:
  1. **Push worker** — drains a queue of pending pushes after each local commit. Retries ×3 with exponential back-off (5 s → 10 s → 20 s). Records `last_sync_error` in `sources.json` on final failure.
  2. **Periodic sync loop** — checks every 60 s which sources are due for a pull (based on `sync_interval_minutes`). Runs fetch+fast-forward; skips if working tree is dirty.
- **`api/sources.py`** (new): full CRUD for git sources and SSH keys. Clone triggered as a FastAPI `BackgroundTask` on source creation so the HTTP response returns immediately. Manual sync endpoint available.
- **`docker-compose.yml`**: `libreta-data` named volume at `/var/lib/libreta/` replaces the `./data/content` bind-mount. Three env vars: `LIBRETA_CONTENT_DIR` (meta/config only), `LIBRETA_REPOS_DIR`, `LIBRETA_SSH_KEYS_DIR`.
- **Frontend — Admin page** (`/-/admin`): add/remove git sources (ID slug, label, remote URL, branch, sync interval, SSH key); add/remove SSH keys (paste PEM, see fingerprint). Sync errors shown per source.
- **Frontend — sidebar**: stacked collapsible panels replace the Content/Watched tab bar. Each git source is a panel with a green/amber/grey sync-status dot and a manual sync button. Watched folders demoted to a collapsible section at the bottom.
- **`SourcePageView` + `SourceEditorView`**: read/edit pages from any git source. Routes: `/source/:sourceId/:path*` and `/edit-source/:sourceId/:path*`.
- **VS Code workspace**: `libreta (content)` folder entry removed — content no longer lives on the host filesystem.
- **`DEPLOY.md`**: completely rewritten for the new model. No `git init data/content` step. Fresh deploy = `docker compose up -d`, then add a source in the UI.
- **`ARCHITECTURE.md`**: updated system diagram, storage layer (write path, sync lifecycle), HTTP API table (new `/sources` and `/sources/keys` routes), frontend routes and component tree, deployment topology, and new key decisions D-09 and D-10.
- **`ROADMAP.md`**: new M3.5 milestone added and marked complete.

**Pre-flight**: backend ruff clean, mypy clean (26 files). Frontend vue-tsc clean, eslint 0 errors (6 pre-existing v-html warnings).

**Decision**: local commit first, async push (D-10). Blocking the user's save on a remote git push would add seconds of latency and introduce transient failure modes. The local commit provides immediate durability; push is best-effort with observable error state.

### 2026-05-03 — M3 Search (FTS5 index, API, UI, CLI)

All four remaining M3 items landed together.

- **Index**: SQLite FTS5 at `content/.libreta/search.db` (gitignored; rebuildable). Schema exactly as specified in ARCHITECTURE: `documents(path UNINDEXED, title, body, tags, updated UNINDEXED)` + shadow `pages_meta(path, mtime)` for incremental reindex. Porter stemmer + unicode61 tokenizer.
- **On-save hook**: `put_page` adds an `index_page` `BackgroundTask` after each commit. `delete_page` adds `remove_page_from_index`. No blocking on the response.
- **Startup reindex**: FastAPI `lifespan` context manager runs an incremental reindex on startup (skips pages whose mtime hasn't changed). Errors are logged and swallowed — the API still starts.
- **`GET /api/v1/search?q=&limit=`**: returns ranked results with FTS5 `snippet()` highlights wrapped in `<mark>` tags. `tag:foo` queries are rewritten to `tags:foo` before being passed to FTS5. Bad FTS5 syntax returns `[]` rather than 500.
- **`libreta reindex` CLI**: entry point in `pyproject.toml` (`libreta.cli:main`). Drops and rebuilds the full index. Supports `--content-dir` override.
- **Search UI** (`/search`): full-page search view with debounced input (250 ms), spinner, snippets with highlighted `<mark>` terms, tag chips, keyboard navigation (↑/↓ to move, Enter to open, Escape to clear). URL synced to `?q=` so searches are bookmarkable/shareable. "Search" link added to the sidebar in App.vue.
- **8 backend tests**: results, empty-query 422, bad-syntax empty, tag filter, missing-q 422, full reindex count, incremental reindex skips unchanged, delete removes from index.

**Pre-flight**: backend 68/68 tests pass, ruff clean, mypy clean. Frontend 63/63 tests pass, vue-tsc clean, eslint clean (2 pre-existing v-html warnings).

### 2026-05-03 — Decision: orphan assets are not garbage-collected on save

When an image or link is removed from a page during editing, the underlying asset file stays in the page directory. Considered automatic cleanup on save; rejected for now.

**Reasoning**:
- R3 already gives recoverability — every save is a commit, so removed assets remain in git history.
- Reflex deletions during an editing session shouldn't make files vanish from the working tree the user might want back two clicks later.
- Doing it correctly is non-trivial: a leaf page and its index page share a directory, so an asset is orphaned only if NO sibling `.md` references it. That's a real piece of work that doesn't earn its complexity in the auto-on-save path.

**Plan**: a future `libreta gc` CLI surfaces orphan candidates and optionally removes them with one commit per page. Tracked under "Beyond v1" in [ROADMAP.md](./ROADMAP.md). [ARCHITECTURE.md](./ARCHITECTURE.md) "Asset handling" updated to state the policy explicitly so future-me doesn't accidentally implement auto-cleanup as a "small fix."

### 2026-05-03 — M3 Arbitrary file attachments

Generalised the upload path: any file (PDF, zip, xlsx, etc.) can now be attached, on top of the image work that landed earlier today.

- **No backend changes needed** — `POST /api/v1/pages/{path}/assets` already accepted any non-`.md` file. The image work just happened to be the first consumer.
- **Frontend dispatch**: `Editor.uploadAndInsert(file)` now branches on the response's `kind` field. `image` → inserts a Tiptap Image node (`![alt](filename)` on save). `file` → inserts the filename as plain text with a `link` mark (`[filename](filename)` on save). Both round-trip through the existing reader (M0.5's `looksLikeAssetHref` already routes `.pdf`/`.zip`/`.xlsx`/etc. relative links to the assets API).
- **Toolbar**: new "Attach file" paperclip button next to the "Insert image" button. Two hidden file inputs — one with `accept="image/*"` for the image picker (better OS-picker UX), one with no filter for general files. Both emit a single `upload-files` event up to `EditorView`.
- **Drag/drop** on the editor surface accepts any file now (used to be image-only). Clipboard paste remains image-only — pasting binary blobs from the clipboard is rare and usually unintended.
- **Round-trip fixture**: [tests/round-trip/fixtures/file-attachments.md](../frontend/tests/round-trip/fixtures/file-attachments.md) — three link-style attachments (`xlsx`, `pdf`, `zip`). Byte-identical without seeding.

**Pre-flight**: 63/63 frontend tests pass, vue-tsc clean, eslint clean. Backend untouched (60/60 still pass).

### 2026-05-03 — M3 Image upload + page-local attachment layout

Image upload landed end-to-end. Pre-emptively chose a layout convention that covers all future attachments (PDF, zip, etc.) and updated [ARCHITECTURE.md](./ARCHITECTURE.md) to match.

- **Layout decision (page-local)**: attachments live in the same directory as the page that uses them. A leaf page `pages/recipes/pizza-dough.md` with `![](photo.jpg)` reads `pages/recipes/photo.jpg`; an index page `pages/projects/libreta/index.md` with `![](architecture.png)` reads `pages/projects/libreta/architecture.png`. Markdown refs are relative. There is no separate `assets/` tree. The previous spec (`/assets/images/YYYY/MM/`) is dropped — this matches the imported corpus and what M0.5 already does on the read side.
- **Rationale**: attachments stay with their content. Renaming/moving a page moves its attachments with it (existing `move_page` already moves the directory tree). Cloning a subdirectory still has working images. The trade-off — duplication when two pages share an asset — is acceptable at solo scale.
- **Backend**: `POST /api/v1/pages/{path}/assets` (multipart `file`) writes into the page's directory and commits with verb `attach`. SHA-256 dedupe scoped to that directory: identical bytes → existing filename returned, no new commit. Filename collisions with different bytes get `-2`, `-3`, etc. Filename sanitisation strips path components, replaces unsafe runs with `-`, refuses `.md`. Helpers: [storage/assets.py](../backend/src/libreta/storage/assets.py) (`sanitize_filename`, `page_directory`, `store_asset`); route in [api/pages.py](../backend/src/libreta/api/pages.py).
- **Backend tests**: 11 new (leaf page, index page, dedupe, collision-suffix, unknown-page 404, .md rejection, empty rejection, filename sanitization, commit creation, commit-skipped on dedupe, plus existing GET tests). 60/60 backend tests pass.
- **Dependency**: `python-multipart` added (`UploadFile` requires it).
- **Frontend**: `@tiptap/extension-image` 3.22.5, configured `inline: true` so an image inside a paragraph round-trips as a paragraph. Custom `PageScopedImage` extension keeps `src` in markdown as the bare filename (e.g. `photo.jpg`) but rewrites to `/api/v1/assets/pages/<dir>/<file>` for the editor preview only — `resolveAssetUrl` in [markdown.ts](../frontend/src/markdown.ts) was made an exported helper to share that logic with the editor. Markdown round-trips byte-identically.
- **Upload UX**: three entry points all funnel through `Editor.uploadAndInsert(file)`:
  1. Toolbar "Insert image" button → hidden `<input type=file accept="image/*" multiple>` → `EditorToolbar.vue` emits `image-files` → `EditorView.vue` calls into the editor ref.
  2. Drag/drop onto the editor surface → `editorProps.handleDrop` filters `image/*` files.
  3. Paste from clipboard → `editorProps.handlePaste` filters `image/*` items.
  Upload errors surface as a small banner above the editor.
- **Round-trip fixture**: [tests/round-trip/fixtures/images.md](../frontend/tests/round-trip/fixtures/images.md) covers page-local image, inline-in-paragraph, and missing-alt cases. Fixture matches tiptap-markdown's canonical output without seeding.
- **`is_index` plumbed** from `PageRead` through `EditorView.vue` to `Editor.vue` so the asset URL preview resolves correctly for index pages.

**Pre-flight**: backend 60/60 tests pass, ruff clean, mypy clean. Frontend 61/61 tests pass, vue-tsc clean, eslint clean (1 pre-existing v-html warning), prettier clean.

**Open**: arbitrary-file upload (PDF/zip/etc.) is essentially "the same endpoint without the image MIME filter on the frontend." The backend already accepts any non-`.md` file. Next.

### 2026-05-02 — M3 Tables in the editor with GFM round-trip

First two M3 items: Tiptap table editing wired in, plus byte-identical round-trip through GFM markdown.

- **Extensions**: `@tiptap/extension-table` 3.22.5 (umbrella package, named exports for `Table`, `TableRow`, `TableHeader`, `TableCell`). Registered in [Editor.vue](../frontend/src/components/Editor/Editor.vue) with `resizable: false` — no `colwidth` attrs to leak through serialization. The `tiptap-markdown` 0.9.0 serializer already handles GFM table emit; no custom serializer needed.
- **Toolbar**: insert table (3×2 with header row), add column / add row / delete column / delete row / delete table. Non-insert buttons disabled outside a table. Lives in a new section after the lists/HR group in [EditorToolbar.vue](../frontend/src/components/Editor/EditorToolbar.vue).
- **Round-trip fixture**: [tests/round-trip/fixtures/tables.md](../frontend/tests/round-trip/fixtures/tables.md) — three cases (simple table, inline formatting in cells incl. bold/italic/code/link/strike, single column). Wired into the fixture array; both stability and byte-identical assertions pass.
- **Editor styles**: borders, header background, table wrapper overflow-x, ProseMirror `selectedCell` highlight.

**GFM constraints surfaced** (not handled in this slice — to address before closing M3):
1. **Cell background colour** (called out in the M3 roadmap line) cannot survive GFM round-trip without raw HTML in cells or sidecar metadata. R1 says it has to be redesigned or dropped — open question.
2. **Per-column alignment** (`:---`, `:---:`, `---:`) is GFM-expressible but the bundled serializer always emits plain `---`. Currently a no-op information loss that nobody loses sleep over, but worth recording.
3. **Column resize** (also in the M3 line) — `resizable: false` for now, since widths can't round-trip. Could be revisited as a per-session presentational hint that's discarded on save (no information loss in the file).

**Pre-flight**: frontend 59/59 tests pass (11 new round-trip assertions across the table fixture), vue-tsc clean, eslint clean (1 pre-existing `v-html` warning), prettier clean.

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
| 2026-05-03 | Git sources replace fixed content bind-mount | Content already lived in a remote git repo; dynamic sources make the deploy model cleaner and remove manual `git init` steps. D-09 in ARCHITECTURE.md. |
| 2026-05-03 | Local commit first, async push | Blocking the user save on SSH push adds latency and failure modes. Local clone provides durability; push is observable best-effort. D-10 in ARCHITECTURE.md. |

---

## How to update this file

When you finish a chunk of work:

1. Update the **Status** block at the top.
2. Update the **At a glance** milestone table if a milestone moved.
3. Add a dated entry to **Log** describing what changed, in 3-8 bullet points.
4. If a non-trivial decision was made, append to the **Decisions log**.
5. Move any "I noticed but didn't fix" items into **Backlog**.

Commit this file alongside the work it documents.
