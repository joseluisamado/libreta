# PROGRESS.md — Libreta

Living document. Update as work progresses. Latest at the top.

> Convention: each session/work-block adds a dated entry. Keep entries short — link to commits/PRs for detail. The "Status" line at the top must always reflect reality.

---

## Status

**Current milestone**: M0.5 — Read-experience polish (in progress)
**Phase**: All eight M0.5 features landed; tag-on-save spec deferred to M2 implementation
**Next action**: Last sweep on remaining feedback, then start M2

## At a glance

| Milestone | Status |
|---|---|
| M0 — Foundations | 🟢 Done |
| M1 — Read-only wiki | 🟢 Done |
| M0.5 — Read-experience polish | 🟢 Done (M2 hand-off pending) |
| M2 — Editing & commits | ⚪ Not started |
| M3 — Tables, attachments, search | ⚪ Not started |
| M4 — Diagrams.net integration | ⚪ Not started |
| M5 — v1.0 release | ⚪ Not started |

Legend: ⚪ not started · 🟡 in progress · 🟢 done · 🔴 blocked

---

## Log

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
