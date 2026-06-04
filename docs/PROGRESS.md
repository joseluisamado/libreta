# PROGRESS.md — Libreta

Living document. Update as work progresses. Latest at the top.

> Convention: each session/work-block adds a dated entry. Keep entries short — link to commits/PRs for detail. The "Status" line at the top must always reflect reality.

---

## Status

**Current milestone**: M5 — v1.0 release ✅ (post-1.0 hardening pass shipped 2026-05-13)
**Next milestone**: post-1.0 hardening / M6 (multi-user & auth)
**Next action**: try the Gitea bulk-import against the homelab Gitea, then push tags.

---

## 2026-06-04 — Tooling: CHANGELOG.md + commit-driven release cut

**What**: added `CHANGELOG.md` (Keep a Changelog format) and a release mechanism
that ties the version bump to the changelog update.

- New `scripts/changelog.py`: parses Conventional Commit subjects since the last
  tag into grouped sections (feat→Added, fix→Fixed, perf/refactor→Changed,
  docs→Documentation, breaking `!`→BREAKING CHANGES; chore/test/ci/build/style
  dropped), bumps `VERSION` (`--level`/`--set`, reusing `sync_version`'s
  semver + package.json propagation), and prepends the new dated section.
  `--backfill` seeds from every tag; `--dry-run` prints without writing.
- Backfilled the changelog from all 18 tags (1.0.0 → 2.0.0); hand-polished the
  2.0.0 (the big refactor) and 1.0.0 (genesis) entries.
- **Release responsibility moved**: the version bump now lives in
  `scripts/changelog.py`, not `make release`. New `make changelog` /
  `changelog-backfill` targets; `make release` ships the current VERSION and
  auto-commits VERSION+CHANGELOG (`chore(release): vX.Y.Z`) before tagging.
  Procedure documented in DEPLOY.md §8b: commit → `make changelog LEVEL=…` →
  `make release` → `git push --follow-tags`.

---

## 2026-06-04 — Fix: scanned (JBIG2) PDFs rendered blank + preview-tile polish

**What**: scanned/image-only PDFs (e.g. CAE practice sheets — one JBIG2 image per
page) showed the right page count but every page was blank, in both the full viewer
and the new preview thumbnails. Root cause: pdf.js 5.x decodes JBIG2/JPEG2000/ICC via
separate wasm modules in `pdfjs-dist/wasm/` and fetches each by its literal filename
from a configured `wasmUrl`; we never set `wasmUrl`, so decoding failed with
"JBig2 failed to initialize". Vector/text PDFs need no wasm, hence the file-specific
symptom.

**Fix**: centralised pdf.js setup in `src/lib/pdf.ts` (worker + shared
`PDF_DOC_OPTIONS` with `wasmUrl: '/pdf-wasm/'`), consumed by both `PdfView` and
`PreviewTile` so they can't drift. A small inline Vite plugin (`pdfjs-wasm-assets` in
`vite.config.ts`) copies the wasm dir verbatim — *unhashed* names, which pdf.js
requires — to `/pdf-wasm/`: emitted into `dist/` for prod (nginx 1.27 serves
`application/wasm` from its stock mime.types) and served from node_modules via dev
middleware. Verified: dev serves `/pdf-wasm/jbig2.wasm` as `application/wasm` with the
`\0asm` magic; build emits `dist/pdf-wasm/*.wasm` with original names. No new npm dep.

**Also** (preview-tile feedback): strip YAML frontmatter before rendering markdown
thumbnails (so the body shows, not `created/…` meta — matches the editor); cache PDF
first-page thumbnails as data URLs keyed by raw URL (module-scope, session-shared) to
skip re-parsing on re-entry/resize/view-toggle; bumped default tile size 200 → 240;
replaced the native range thumb (rendered "funky" at non-integer DPR) with an
explicit cross-browser styled slider.

**Checks**: frontend typecheck, lint (0 errors), 63 tests, production build all green.

---

## 2026-06-04 — Feature: preview/grid view mode for the folder listing

**What**: added a second view mode to the directory listing (`DirListing.vue`). A
selector at the top-right of the "In this folder" section toggles between the existing
**list** view and a new **preview** grid of icons with embedded content previews; a size
slider (120–360 px, shown only in preview mode) scales the tiles. Both choices persist in
`localStorage` (`libreta.dirView` / `libreta.dirTileSize`) so they stick while browsing.

**Frontend**: new `components/PreviewTile.vue` renders one tile — text snippet fetched from
the raw endpoint for markdown/text (`page`/`text` kinds, first 1200 chars), the image itself
for `image`, a non-interactive `<embed>` for `pdf`, a folder glyph for directories, and a
coloured kind badge as fallback (binary/drawio/fetch error). Tiles route via RouterLink
(internal) or `<a download>` (external assets), mirroring the list view's link logic, and
carry the same rename/delete row actions for owned children. `DirListing` grew a
`getChildRawUrl` prop; both `SourcePageView` and `WatchedPageView` supply it (pointing at
the existing `/pages/{path}/raw` and `/watch/{label}/raw/{path}` endpoints, which already
serve any suffixed file byte-for-byte). No backend changes.

**Checks**: `pnpm typecheck`, `lint`, `format`, `test` (63 pass) all green. No new round-trip
surface (read-only previews; the markdown round-trip is untouched).

---

## 2026-06-03 — Removal: legacy "main wiki" + `content_dir` → `meta_dir` rename

**What**: removed the original single-content-repo "main wiki" entirely (it no longer
held content after the git-sources migration, D-09) and renamed the now-misnamed
`content_dir` setting to `meta_dir`. See ARCHITECTURE.md **D-11**.

**Backend**: deleted `api/pages.py`, `api/assets.py`, `storage/pages.py`, and the
`resolve_asset`/single-page-index helpers; unhooked the `pages` + `assets` routers in
`main.py`. `storage/assets.py` (source/watched uploads) kept — only its main-wiki
`resolve_asset` removed; its `content_dir` params renamed `repo_root`. Search is
sources-only now (dropped the `content_dir/pages` reindex fallback). Renamed the setting
+ env var → `meta_dir` / `LIBRETA_META_DIR` (default `./data/meta`); `/info` now reports
`meta_dir`/`meta_dir_exists`; `cli reindex` flag `--content-dir` → `--meta-dir`; `cli gc`
now requires `--source`/`--repo`.

**Frontend**: deleted `PageView`/`EditorView`/`HistoryView`/`DiffView` and `stores/tree.ts`;
removed the `/w/ /edit/ /pdf/ /text/ /history/ /diff/` routes (the `-source`/`-watch`
variants stay); pruned the main-wiki client fns (`getTree`, `getPage`, `savePage`, … ,
`uploadAsset`, `upsertAsset`). The editor link picker is now git-sources-only (no more
"Main wiki" option). The editor's inline attachment/diagram features require a git source.

**Tests**: removed `test_pages/history/diff/assets` (backend) and the matching frontend
specs; reworked `conftest.py` (a `meta_dir` + `repos_dir` fixture and a `make_source`
helper) and `test_search.py` to seed a real git source. Backend 94 pass; frontend 63 pass;
ruff/mypy/eslint/tsc/build all green.

---

## 2026-06-02 — Feature: download markdown pages

**What**: a download button (mirroring the PDF/text viewers) now appears when
viewing a non-directory markdown page, fetching the **byte-identical** on-disk
`.md` (frontmatter included), not the parsed body — R1-safe.

**Backend**: new `resolve_page_source_file` in `storage/pagefile.py` resolves a
page path to its on-disk source file (implies `.md`, refuses dirs/missing/
traversal). Three thin `FileResponse` endpoints serve it as an attachment:
`GET /pages/{path}/raw`, `GET /sources/{id}/pages/{path}/raw`,
`GET /watch/{label}/raw/{path}`. Each registered before its greedy
`/{path:path}` sibling so the literal suffix wins.

**Frontend**: `PageView`, `SourcePageView`, `WatchedPageView` gain a download
`<a download>` at `right-[156px]`, shown only when `page && !isDirectory`.

**Tests**: byte-identity + not-found + dir-404 + traversal across pages/watch
HTTP endpoints and the `resolve_page_source_file` helper.

---

## 2026-06-02 — Feature: upload arbitrary files into a folder; repo-root navigation

**What**: the "In this folder" panel gains an **Upload files** button. Selected
files are written as *sibling* files in the folder (e.g. `pages/Docs/report.pdf`)
— not in the page sidecar — so they appear in the folder listing as first-class
files. Files ≥ 50 MB trigger an in-dialog confirmation before upload; there is no
hard size cap.

**Backend**:
- New `store_folder_file` in `storage/assets.py` streams the upload to disk in
  1 MB chunks (constant memory, any file size) and returns a `rel_path` ready for
  the git index. Repo-agnostic via `base_dir`/`repo_root`.
- Endpoints: `POST /pages/{path}/files` + `POST /pages/files` (root) commit per
  R3; `POST /sources/{id}/folders/{path}/files` + `/sources/{id}/files` commit &
  enqueue push; `POST /watch/{label}/folders/{path}/files` + `/watch/{label}/files`
  write to disk (watched dirs aren't git). No `MAX_UPLOAD_BYTES` cap on these
  (existing page-sidecar uploads keep their 25 MB cap).

**Frontend**:
- `DirListing.vue` owns the upload button, file picker, and the >50 MB warning;
  emits `upload` for the parent to perform. Wired into `PageView` (migrated off
  its bespoke inline listing onto the shared `DirListing`), `SourcePageView`,
  `WatchedPageView`.
- **Root navigation**: `SourcePageView`/`WatchedPageView` now render the folder
  listing at the repo root (`path === ""`) via the children endpoint, so files
  can be uploaded to the root. `Breadcrumbs` shows a clickable repo-root crumb
  (e.g. `Home / my-org:homeops / Docs`) linking to `/source/<id>/` — the
  sidebar entry still only expands/collapses.
- Source labels display `owner/repo` as `owner:repo` (new `utils/sourceLabel.ts`)
  in both the sidebar and breadcrumbs, reserving `/` for path separators.

Tests: `store_folder_file` unit tests + folder-upload API tests in
`tests/test_assets.py` (sibling placement, root, uniquify, commit, traversal,
empty/markdown rejection).

---

## 2026-05-31 — Fix: private-repo clone over authenticated HTTP left repo empty

**Symptom**: a private Gitea repo imported as a source showed "synced" in the
sidebar but had no content; only a `.git` husk (unborn HEAD, zero refs) on disk.
A public repo from the same server cloned fine.

**Root cause**: two compounding bugs.
1. `pygit2.clone_repository(..., checkout_branch="main")` against an
   *authenticated* Gitea over smart-HTTP fails the fetch outright
   (`could not read from remote repository`) and leaves an empty repo. A plain
   clone (no `checkout_branch`, taking the remote default HEAD) works.
   Confirmed empirically: WITH_main → GitError; NO_checkout_branch → 3 refs, OK.
2. The failure was invisible. `clone_source_sync` skipped anything with a
   `.git` dir as "already cloned", and `fetch_and_ff_sync` returned cleanly when
   the remote-tracking ref was missing — so every later sync reported success on
   an empty repo and `last_sync_error` stayed null.

**Fix** (`storage/sources.py`):
- Clone WITHOUT `checkout_branch`; afterwards `_checkout_branch_if_needed`
  moves HEAD to the configured branch only when it differs from the default
  (and raises if that branch is absent on the remote).
- `_is_incomplete_clone` detects a husk (`.git` present but unborn HEAD / no
  `origin/<branch>` ref). `clone_source_sync` removes such a husk and re-clones;
  `fetch_and_ff_sync` treats it as needing a re-clone — so a stuck-empty source
  self-heals on the next sync. A failed clone now cleans up after itself.
- A missing remote branch after a real fetch now raises `GitSourceSyncError`
  (recorded in `last_sync_error`) instead of silently reporting "synced".

**Tests**: husk self-heal + clone-lands-on-non-default-branch. Backend 130 green.
Verified live: the stuck `work` repo healed on a sync — HEAD on main, 3 refs,
content present, `last_sync_error` null.

---

## 2026-05-31 — Fix: new-source tree refresh + remove repos from browse panel

Two follow-ups to the Gitea/sources admin work:

- **Sidebar content appeared only after a manual refresh.** A freshly-added
  source clones in the background; the sidebar panel's first tree fetch hit a
  still-empty working tree, cached `[]`, and its `!trees[id]` guard then blocked
  any reload. Added a watcher on the source's `cloned` flag (flipped false→true
  by the App-level sources poll) that reloads the tree when the clone lands, so
  content shows without a refresh. (`SourceSidebarPanel.vue`)
- **Imported repos couldn't be removed from the browse-repos list.** They showed
  greyed-out with no action. The list now renders a Remove button on
  already-added rows (matched to their source by clone_url == remote_url);
  removing flips the row back to importable in place. Backend already supported
  the delete — this is UI only. (`AdminView.vue`)

Verified live against the homelab Gitea: import → already_added=true → remove →
already_added=false. Frontend 65 green, typecheck clean.

---

## 2026-05-31 — Feat: edit support across admin components + repo select-all

**Admin edit affordances**: every admin component is now editable in place,
not just add/delete.
- **Git sources**: inline edit of label / branch / sync interval (id and
  remote_url are identity/clone-target, so they stay remove+re-add). Reuses
  the existing `PUT /sources/{id}`.
- **Gitea servers**: new `PUT /sources/gitea-servers/{id}`. The token field is
  optional on edit — blank keeps the stored token, a value rotates it (the
  token is never returned, so the form can't pre-fill it; blank must mean
  unchanged). Uniqueness (base_url, username) re-checked on edit.
- **Watched folders**: new `PUT /watch/folders/{label}` supporting both label
  and path. The label is the config key, so a rename re-keys the entry and is
  rejected on collision with another folder.
- **SSH keys**: new `PUT /sources/keys/{id}` — label-only (key material is
  write-only/immutable).

**Repo picker**: select-all / deselect-all toggle plus an "N of M selected"
count in the Gitea browse-repos panel; "all selected" ignores already-added
rows.

**Tests**: store-level (gitea update keep/rotate/collision/missing, ssh rename),
API-level (gitea server PUT keeps vs rotates token, watched PUT path+label,
label collision → 409, missing → 404). Backend 128 green, frontend 65 green.
Verified live against the homelab Gitea: server rename kept the token (discover
still worked).

---

## 2026-05-31 — Feat: Gitea servers + bulk repo import

**Motivation**: adding sources one-at-a-time from the same Gitea server was
tedious. You can now store a Gitea server's credentials once and bulk-import
every repo under an org or user.

**Model**: a *Gitea server* is a remembered credential group (label, base URL,
username, token), stored exactly like SSH keys — metadata in
`<gitea_servers_dir>/index.json`, the token in a sibling `0600` file, never
returned over the API (R2: filesystem is the source of truth; the token never
lives only in memory). Imported sources carry a `gitea_server_id` and resolve
the token at clone/fetch/push time, so rotating the token in one place updates
every source from that server.

**Backend**:
- `storage/gitea_servers.py` — the credential store (mirrors `storage/ssh.py`).
- `services/gitea.py` — repo discovery via the Gitea API
  (`/api/v1/orgs/{owner}/repos`, falling back to `/users/{owner}/repos`),
  paginated, using the existing `httpx` dep. Only talks to Gitea on an explicit
  admin action (R5).
- `config.gitea_servers_dir` (default `/var/lib/libreta/gitea_servers`).
- New endpoints under `/sources`: `gitea-servers` CRUD,
  `gitea-servers/{id}/discover`, `gitea-servers/{id}/import`.
- The three git ops (`clone_source`/`fetch_and_ff`/`push`) now take a
  `gitea_servers_dir` and resolve HTTPS auth from the server store when a source
  references one. Threaded through the sync service and lifespan.

**Frontend**: a "Gitea Servers" section in the Admin view — add a server, then
"Browse repos" → enter org/user → checkbox picker (already-added rows disabled,
empty repos flagged) → "Import N selected".

**Tests**: `test_gitea_servers.py` (store: token perms, dedupe, roundtrip),
`test_gitea_discovery.py` (org/user paths, pagination, auth/unreachable errors,
httpx mocked), `test_gitea_api.py` (server CRUD, discover `already_added`
flagging, import creates server-referencing sources, idempotent re-import).
Existing `test_sources_sync.py` updated for the new signature. Backend 115
green, frontend 65 green (round-trip corpus intact).

---

## 2026-05-29 — Fix: fast-forward silently dropped newly-added files

**Symptom**: a user added `.md` files upstream, clicked "sync", and the new
files never appeared in Libreta — no error; `last_sync_error` stayed null.

**Root cause**: a regression introduced by the 2026-05-13 SAFE-checkout change.
`fetch_and_ff_sync` did `local_ref.set_target(remote_commit.id)` (advance the
branch ref) **before** `repo.checkout_head(strategy=SAFE)`. With the ref already
moved, `checkout_head` diffs the *new* HEAD against the working tree; for
purely-added paths that comparison can resolve to "nothing to do", so the new
files were left out of both the index and the working tree while the ref still
pointed at the commit that contained them. Result: files present in HEAD's tree
but `git status: INDEX_DELETED`, invisible to the listing API (which reads the
working tree per R2). Worse, once a repo was in that state it could not
self-heal: a plain SAFE checkout treats the missing-from-workdir paths as
deliberate local deletions and skips restoring them, so every later sync stayed
stuck.

**Fix** (`storage/sources.py` `fetch_and_ff_sync`):
- Check out the explicit target tree (`checkout_tree(remote_commit.tree, …)`)
  and advance the ref only afterwards, so the working tree + index always
  reflect the new commit before HEAD moves.
- Use `SAFE | RECREATE_MISSING`. RECREATE_MISSING makes the fast-forward restore
  tracked files that are missing from the working tree (healing any repo already
  left in the INDEX_DELETED state), while SAFE still aborts on genuine
  uncommitted *modifications* to existing files — same protection as before.

**Live repair**: the deployed `work` repo was stuck in the INDEX_DELETED state;
its index was resynced to HEAD and the tree force-checked-out. Working tree now
clean; the 5 missing files (incl. the `Ch2/Ch4/Ch7 … — Summary & Gotchas.md`
set) are back and visible via the API.

**Tests**: new `backend/tests/test_sources_sync.py` (3 cases) — pure-add FF
materialises files on disk + index (reproduces the original bug; fails without
the fix), self-heal from an INDEX_DELETED repo, and "uncommitted local edit
blocks the FF without moving the ref". Full suite 98/98, ruff + mypy clean.

**Note**: this is unrelated to the case-sensitivity red herring — the user's URL
used `EPSO Books` but the on-disk dir is `EPSO books`; the backend correctly
404s the wrong case and the sidebar always links the real on-disk name.

---

## 2026-05-13 — Homelab deploy hardening

**What changed**: first real-hardware deploy (NanoPi-class ARM SBC, 4 cores / 2 GB RAM, ~2 GB content across two git sources) surfaced a string of latency and footprint issues. None of them showed on the dev Mac. All fixed in this pass; detailed list in `docs/PERFORMANCE.md` "Low-spec / homelab notes".

**Pieces**:
- **Backend image: 586 MB → 206 MB.** `backend/Dockerfile` rewritten as a multi-stage build. The builder installs deps into `/opt/venv`; the runtime image copies only that venv and the source. `libgit2-dev` and `build-essential` are no longer in the runtime — pygit2's manylinux wheel statically bundles libgit2, openssl, libssh2, and pcre. `uv` is dropped from the runtime entirely (the prebuilt `ghcr.io/astral-sh/uv` binary is only used in the builder stage). Only `ca-certificates` is added at runtime for HTTPS git remotes.
- **Sync click: ~60 s → a few seconds.** `fetch_and_ff_sync` no longer runs a pre-flight working-tree scan. The FF uses `pygit2.CheckoutStrategy.SAFE` so libgit2 refuses the FF if any file in the diff has uncommitted local changes; on conflict the ref is rolled back and a warning logged. After an `rsync`-style migration the index stat cache was invalidated, and `index.diff_to_workdir()` was hashing the full 1.2 GB working tree every call (73 s on `libreta-data`, 47 s on `work`). The new path only hashes files that would actually change. Same semantics as `git pull`.
- **Push: no more auto-stage.** `push_sync` no longer calls `repo.status()` to auto-commit external changes before pushing. Libreta commits on every page write, so the auto-stage only caught modifications made outside Libreta — explicitly the user's responsibility now. Eliminates a per-push working-tree hash.
- **Startup reindex is commit-aware.** New `sources_meta(source_id, indexed_head)` table records the git HEAD each source was last indexed at. If HEAD hasn't moved, the source is skipped entirely (no file I/O). If HEAD moved, only the `.md` files in the git diff are reindexed; removed files are deleted from the index. First run / missing row falls back to the old mtime walk and then records HEAD. On a quiet repo, startup reindex now consumes <0.1 s of CPU.
- **Startup is non-blocking.** `incremental_reindex` and `startup_sync` are launched with `asyncio.create_task` from `lifespan` instead of being awaited there. The HTTP server accepts requests within ~30 s (Python startup) instead of waiting minutes for sync work to drain.
- **Sync parallelism cap.** `startup_sync` and `periodic_sync_loop` share a 2-permit semaphore (`_bounded_sync_one`). libgit2's pack resolution is CPU-bound and single-threaded per call; fanning out one fetch per source on a 4-core ARM box pegged every core through contention. The periodic loop also seeds `next_sync = startup_time + interval` for every known source before its first tick, so the t≈60 s tick doesn't re-fetch what `startup_sync` just handled.
- **Production frontend nginx: API assets with image extensions.** `frontend/nginx.prod.conf`'s `/api/` location was a plain prefix and lost precedence to the regex location matching `\.(svg|png|jpg|…)$`. Any asset URL like `/api/v1/sources/<id>/assets/foo.drawio.svg` was matched by the static-asset block, which had no `proxy_pass`, and returned 404 from nginx instead of reaching the backend. Promoted the API location to `location ^~ /api/` so it wins over regex matches. Drawio diagrams and images embedded in markdown pages now load on the production frontend image. Dev was unaffected (Vite handles its own proxy).
- **`make release` deploys to the homelab.** New `DEPLOY_HOST` constant in the Makefile; the `release` target now pipes `docker save … | ssh $(DEPLOY_HOST) docker load` for both api and frontend images (each with `:VERSION` and `:latest` tags). Override at the command line: `make release LEVEL=patch DEPLOY_HOST=other`.

**Measured impact on the home server**:
- Cold restart CPU: ~170 s of total CPU in the first 3 min (≈90 % across cores) → 0.09 s in the first 2 min. Restart pressure is gone.
- Sync-click CPU: full core for ~1 min → near-instant on a clean tree. Confirmed by an isolated timing harness: pre-flight 73 s + 47 s → 0 s; fetch ~1 s; push ~3 s.
- Image pull on the SBC went from 586 MB → 206 MB.

**Docs**: `ARCHITECTURE.md` "Git source lifecycle" + "Reindex" updated to match. `PERFORMANCE.md` gained a "Low-spec / homelab notes" section enumerating the wins.

**Pre-flight (each step)**: backend ruff clean (5 pre-existing housekeeping items unchanged), mypy 0 errors, pytest 95/95. No frontend code changed; nginx config diff is a 1-character addition.

---

## 2026-05-09 — M5 release pass (v1.0.0)

**What changed**: shipped all M5 items in one pass, ending with the
v1.0.0 tag.

**Pieces**:
- **Production deploy**: `docker-compose.caddy.yml` + `Caddyfile.example`
  add Caddy on :80/:443 with auto-Let's-Encrypt; HTTP/3 enabled, certs
  persisted in `caddy-data` volume. `DEPLOY.md` §7 rewritten with the
  full recipe.
- **Backup & restore**: new `docs/BACKUP.md` covering state inventory
  (authoritative vs derived), one-shot + cron strategies, three restore
  scenarios (single page, lost volume, lost host).
- **Apple Notes migration**: `scripts/import_apple_notes.py` reads
  `NoteStore.sqlite` directly via stdlib `sqlite3` + a hand-rolled
  protobuf decoder (no new deps). Renders to GFM with sidecar
  attachments, frontmatter captures `apple_notes_uuid` for future
  re-runs. Wired as `libreta import-apple-notes` and
  `make import-apple-notes REPO=...`. Migration guide:
  `docs/MIGRATION-APPLE-NOTES.md`.
- **Security review**: `docs/SECURITY-REVIEW.md` — threat model + 7
  findings. Fixes landed in the same pass:
  - **P1** XSS via mermaid fence content (`md.utils.escapeHtml`).
  - **P1** Hidden-file disclosure: `validate_path_segments` now blocks
    `.git*` / `.ssh*` / `.libreta*` prefixes; sidecar dirs unaffected.
  - **P1** Source-id traversal: `_local_path` regex-validates.
  - **P1 partially mitigated** SSH `certificate_check` now logs host on
    every git op; full TOFU/known-hosts deferred to M6.
  - **P3** SSH key tempfile leak fixed via `weakref.finalize` cleanup.
  - **Info**: `pip-audit` clean; 2 dev-only `pnpm audit` advisories
    (vite/esbuild dev server) noted, not shipped to prod.
- **Performance**: `scripts/smoke_bench.sh` + `docs/PERFORMANCE.md`.
  Measured on dev stack with 197 pages: tree 9.5 ms, search 6.2 ms,
  page read 2.2 ms, idle memory 81 MiB — all an order of magnitude
  under target. Pi 4 + 1000-page corpus not yet measured.
- **User-facing docs**: `docs/site/` — landing, getting-started, FAQ,
  troubleshooting. README quickstart rewritten to reflect the
  git-source model (the old `mkdir data/content` path was stale since
  M3.5).
- **License**: AGPL-3.0-only — canonical text in `LICENSE`, SPDX in
  `pyproject.toml` and `package.json`, README license section rewritten
  with rationale.

**Pre-flight**: backend pytest 95/95, mypy strict clean. Ruff has 5
pre-existing housekeeping items (B904, RUF005, SIM117) unrelated to
this work. Frontend vitest 65/65, vue-tsc clean.

---

## 2026-05-09 — Other files in directory listing

**What changed**: Directory pages now show non-page files (images, diagrams, text files, binaries) in a separate "Other files" section below the existing "In this folder" listing. The sidebar tree remains unchanged — only folders, `.md`, and `.pdf` files appear there.

**How it works**:
- **Backend**: New `OtherFile` model (name, path, kind) and `DirChildren` response model. `PageNode` gained an `other_files` field. The `_build_tree` helper in `pagefile.py` collects non-hidden, non-md, non-pdf files in each directory and attaches them to the directory node. File kind is classified by extension (image, drawio, text, binary). The `/children/{path}` endpoints now return `DirChildren` so lazy-loaded trees also get `other_files`.
- **Frontend**: `DirListing.vue` gained optional `otherFiles` / `getOtherFileUrl` props and renders a "Other files" section with type badges (IMG/DRAW/TXT/BIN) linking to the asset serving endpoint. `PageView.vue` has the same section inline. Both sections are sorted alphabetically, separate from the main page listing.
- **Common code**: All changes are in `pagefile.walk_tree` / `_build_tree`, so the feature applies automatically to the main wiki, git sources, and watched folders.

**Pre-flight**: backend mypy clean, ruff clean, pytest 95/95. Frontend vue-tsc clean, eslint clean (pre-existing v-html warnings only), prettier clean, vitest 65/65.

---

## 2026-05-08 — Pending-changes indicator (M4 follow-up)

**What changed**: The sidebar now shows when local commits haven't been pushed to the remote yet. Each git source's status dot turns amber on `pending_count > 0`; an `↑N` button next to the source label opens a popover listing the changed pages (grouped by path with the underlying commits underneath).

**How it works**:
- **Backend**: `GitSourceResponse` gained a `pending_count` field, computed via `pygit2.Repository.ahead_behind(HEAD, refs/remotes/origin/<branch>)` on each `/sources` GET. New `GET /api/v1/sources/{id}/pending` returns the detailed commit list (sha, message, author, timestamp, changed `.md` paths) — used by the popover only, so the per-list overhead stays minimal.
- **Frontend**: `App.vue` polls `/sources` every 15 s while the tab is visible, refreshes immediately on tab refocus, and the editor calls `loadSources()` after each successful save so the `↑N` reflects the new commit without waiting for the next tick. New `PendingChangesPopover.vue` component rendered inline beneath the source label when expanded.

**Docs**: ARCHITECTURE.md gained a "Cadence summary" table (push: immediate; push retry: 5/10/20s; periodic pull check: 60s; per-source pull: 15min default; frontend poll: 15s) plus a "Pending-changes indicator" subsection. The git-sources API table now lists the new `/pending` endpoint.

**Pre-flight**: backend mypy clean, pytest 95/95. Frontend vue-tsc clean, vitest 65/65.

---

## 2026-05-08 — M4: Diagrams.net integration

**What changed**: Diagrams.net editing is wired end-to-end. New diagrams come in through the toolbar's "Insert diagram" button; existing `.drawio.svg` images are reopened by double-clicking them in the editor. Diagrams travel with the content repo as a single `.drawio.svg` file per diagram, stored page-locally next to images.

**How it works**:
- **Backend**: new `GET /api/v1/config` returns `{drawio_url}` so the SPA learns where the iframe lives without baking it into the bundle. New `PUT /api/v1/pages/{path}/assets/{filename}` (and the source variant) replaces the bytes of an existing sidecar asset in place — used by the diagram editor on re-save so the markdown's image reference doesn't need to change. Backed by a new `replace_asset` storage helper that mirrors `store_asset` but skips the auto-uniquify step.
- **Frontend — modal**: `DrawioModal.vue` mounts an iframe at `<drawio_url>/?embed=1&proto=json&spin=1&saveAndExit=1&ui=atlas`, implements the documented postMessage protocol (`init` → `load`, `save` → `export xmlsvg`, `export` → resolve SVG data URI, `exit` → close).
- **Frontend — editor**: `PageScopedImage` flags any `src` matching `/\.drawio\.svg$/i` with `data-drawio-src` and a "double-click to edit" tooltip. `editorProps.handleDoubleClickOn` intercepts double-clicks on these nodes and reopens the modal with the existing XML extracted from the SVG's `content="…"` attribute. New diagrams get a generated `diagram-YYYYMMDD-HHMMSS.drawio.svg` filename via `POST /assets`; re-saves go to `PUT /assets/{filename}` so the document keeps the same `![](…)` reference.
- **View mode**: no changes needed — `.drawio.svg` is just an SVG, and `markdown.ts`'s existing image rule routes the relative ref through `/api/v1/assets/...`. Browsers render it inline; double-click affordance is editor-only.
- **R5/offline**: drawio container is the existing `jgraph/drawio:latest` already in `docker-compose.yml`; default URL `http://drawio:8080` keeps everything on the internal network. `LIBRETA_DRAWIO_URL` env var lets a deploy point at the public embed if they explicitly want to (documented opt-out).

**Docs**: ARCHITECTURE.md "Assets" table updated to reflect the unified asset routes (the previously-speculative `/diagrams` endpoint is gone — diagrams use the same routes as any other asset). New "Client config" section. "Diagrams.net integration → Edit flow" rewritten to match the actual postMessage exchange.

**Hardening during smoke-testing**: live testing surfaced a "Applying a mismatched transaction" RangeError from ProseMirror when inserting a saved diagram. Root cause: `editor.commands.focus()` synchronously dispatched a selection transaction whose `onUpdate` re-emitted to the parent, which re-bound `props.content`, which entered the watcher's `setContent` — racing with the `insertContent` transaction still being applied. Fix: drop the explicit `focus()`, gate `onUpdate` and the `props.content` watcher with an `internalUpdateInFlight` flag during the insertContent + post-tick window, and emit a single coalesced `update` after the doc settles. The `LIBRETA_DRAWIO_URL` default also moved from the container-internal `http://drawio:8080` to the host-facing `http://localhost:8093` since the iframe is loaded by the user's browser, not proxied through the api.

**`libreta gc` (bonus)**: shipped the orphan-asset CLI tool that was on the "anytime" backlog. Diagram saves can leave files on disk if the editor's insert step fails, so a cleanup affordance was overdue. `libreta gc --source <id>` lists; `--delete` removes and commits one batch per page. New module `storage/gc.py` plus 8 unit tests.

**Pre-flight**: backend mypy clean (27 files), pytest 95/95 (8 new gc tests). Frontend vue-tsc clean, vitest 65/65, eslint 0 errors (6 pre-existing v-html warnings).

---

## 2026-05-04 — Mermaid code blocks

**What changed**: Added mermaid diagram support via fenced code blocks. Mermaid blocks (` ```mermaid `) are rendered as SVG diagrams in view mode using the mermaid library. In the editor, mermaid is available as a language option in the code block dropdown — users edit the mermaid source text directly.

**How it works**:
- **Rendering**: `markdown.ts` overrides the markdown-it fence renderer for `mermaid` language blocks, emitting `<pre class="mermaid">` instead of syntax-highlighted HTML. After the view components render via `v-html`, a watcher calls `mermaid.run()` scoped to the content container to transform those elements into SVG diagrams.
- **Security**: mermaid initialised with `securityLevel: 'antiscript'` which strips `<script>` tags from node labels (R6-compliant). No external resources are fetched at render time (R5-compliant).
- **Editor**: `mermaid` added to `CODE_LANGS` in `Editor.vue`. Mermaid blocks are standard GFM fenced code blocks — no custom markdown syntax (R4-compliant). The round-trip is byte-identical (R1 — new fixture `mermaid.md` added to the test corpus).
- **No backend changes**: mermaid blocks are just fenced code blocks with `language=mermaid`. The backend stores and returns raw markdown; rendering happens entirely in the frontend.

**Future**: A visual mermaid editor (live preview in the editor as you type) is tracked in `ROADMAP.md` under "Beyond v1." The current implementation follows the architecture doc's plan: render in view mode, source-only editing in v1.

**Pre-flight**: frontend 65/65 tests pass, vue-tsc clean, eslint 0 errors (6 pre-existing v-html warnings).

**Files touched**: `package.json`, `markdown.ts`, `Editor.vue`, `PageView.vue`, `SourcePageView.vue`, `WatchedPageView.vue`, `tests/round-trip/fixtures/mermaid.md`, `tests/round-trip/roundtrip.test.ts`.

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
