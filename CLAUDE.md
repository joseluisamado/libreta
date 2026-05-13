# CLAUDE.md — Operating manual for Claude Code

You are working on **Libreta**, a self-hosted wiki built around the principle that a git repository of markdown files is the source of truth.

Read [`docs/PROJECT.md`](./docs/PROJECT.md) and [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) before making non-trivial changes. The "Principles" section of `docs/PROJECT.md` is not aspirational — it states decision rules that override stylistic or convenience considerations.

This file is your operating manual: project orientation, conventions, the things that must not break, and the pre-flight checks before declaring work done.

---

## 1. Orientation

**Layout**:

```
libreta/
├── backend/                  Python 3.12 + FastAPI service (managed with uv)
├── frontend/                 Vue 3 + Vite SPA (managed with pnpm)
├── docker-compose.yml        Orchestrates backend + frontend(dev) + drawio
├── data/content/             ★ The user's wiki. A git repo of .md files.
├── docs/
│   ├── PROJECT.md            Vision, principles, non-goals
│   ├── ARCHITECTURE.md       Tech stack, components, data model, APIs
│   ├── ROADMAP.md            Milestones M0 → M5 (and M6+ "beyond v1")
│   └── PROGRESS.md           Update this when you finish something
├── README.md
└── CLAUDE.md                 You are here.
```

**Mental model**: Libreta is a thin layer over a git repository. It reads markdown files, presents them in a nice editor, and writes commits back. The user's data lives in `data/content/`. The backend's job is to mediate between HTTP requests and that directory.

---

## 2. Inviolable rules

Breaking any of these is a regression, regardless of test coverage. Treat as if they were enforced by a build gate.

### R1. The markdown round-trip is sacred.

`docs/PROJECT.md` P3. Any change that breaks the byte-identical round-trip on the fixture corpus (read → editor → save → assert identical) is rejected. If a feature would require breaking it, the feature does not ship as designed — redesign or drop.

### R2. The filesystem is the source of truth.

`docs/PROJECT.md` P1. Never add a feature that stores user content only in SQLite, only in memory, or only in some other store. If a metadata bit needs to persist, it lives in:
- frontmatter of the relevant page, OR
- a sidecar file in the wiki repo (e.g., `.meta/foo.yaml`), OR
- nowhere, and it gets recomputed on demand.

The SQLite index is **never** authoritative. Anything in it must be regenerable from the filesystem by a single CLI command.

### R3. Every save is a commit.

`docs/PROJECT.md` P2. There is no "save without commit" code path. If you find yourself writing one to avoid noisy git history, push back: maybe debounce in the UI before saving, but never skip the commit on a server-side save.

### R4. No custom markdown syntax.

`docs/PROJECT.md` P4. CommonMark + GFM (tables, task lists, strikethrough, autolinks). No `{% widget %}`, no `:::admonition`, no proprietary block extensions. Diagrams are referenced as standard images; their drawio-ness is a property of the file, not of a special markdown directive.

### R5. No reliance on public services at runtime.

`docs/PROJECT.md` P5. The wiki must work fully offline. The drawio editor is the self-hosted `jgraph/drawio` container. Don't introduce a feature that fetches from a CDN or a public API at user-action time.

### R6. Server-rendered HTML never executes user-supplied JS.

Markdown allows raw HTML. We strip `<script>` and event-handler attributes at save and at render. If a feature would require relaxing this, escalate before implementing.

---

## 3. Working in the backend

Path: `backend/`. Python 3.12. Managed with [`uv`](https://github.com/astral-sh/uv).

### 3.1 Set up

```bash
cd backend
uv sync                       # creates .venv, installs deps, respects uv.lock
```

### 3.2 Run

```bash
# Dev server with reload:
uv run uvicorn libreta.main:app --reload --host 0.0.0.0 --port 8080

# Or via docker compose:
docker compose --profile dev up backend
```

### 3.3 Pre-flight checks (run before declaring work done)

```bash
uv run ruff format .          # format
uv run ruff check . --fix     # lint + autofix
uv run mypy src               # types (strict mode)
uv run pytest                 # tests
```

CI runs all four. If any of them are red, work isn't done.

### 3.4 Conventions

- **Async-first**: handlers, storage methods, anything that touches I/O. Use `asyncio.to_thread()` for unavoidably-sync libs.
- **pygit2, not GitPython**: the project uses libgit2 bindings for performance and correctness. Don't introduce GitPython.
- **Pydantic v2** for all request/response models. Models live in `src/libreta/models.py` (small project) or near their handlers (when modules grow).
- **Type hints everywhere**, including private helpers. `mypy --strict` must pass.
- **Errors are explicit**: raise typed exceptions defined in `src/libreta/errors.py`; FastAPI handlers translate them to HTTP responses centrally. Don't `raise HTTPException` from deep storage code.
- **Logging**: structured (`structlog` if added), one logger per module via `logging.getLogger(__name__)`.
- **No globals.** Pass dependencies via FastAPI's `Depends`, including the page store, repo handle, and config.
- **Tests**: `tests/` mirrors `src/libreta/`. New code without tests gets bounced.

### 3.5 Filesystem operations

When writing/reading the content directory:
- **Always validate paths** through the helper in `storage/paths.py`. Never trust path segments from the API.
- **Use `pathlib.Path`**, not string concatenation.
- **Acquire the repo write lock** before any operation that touches the working tree. See `storage/repo.py`.

---

## 4. Working in the frontend

Path: `frontend/`. Vue 3 + Vite + TypeScript. Managed with [`pnpm`](https://pnpm.io/).

### 4.1 Set up

```bash
cd frontend
pnpm install
```

### 4.2 Run

```bash
pnpm dev                      # vite dev server with HMR
pnpm build                    # production bundle
pnpm preview                  # serve the production bundle locally
```

### 4.3 Pre-flight checks

```bash
pnpm lint                     # eslint
pnpm format                   # prettier
pnpm typecheck                # vue-tsc --noEmit
pnpm test                     # vitest
pnpm test:e2e                 # playwright (slower; run before merging)
```

### 4.4 Conventions

- **`<script setup lang="ts">`** for all components. No Options API.
- **TypeScript strict** (`strict: true`, `noImplicitAny: true`). Use `unknown` over `any`.
- **No untyped fetch calls**. All API calls go through `src/api/client.ts`, which has typed wrappers generated from (or manually mirroring) the OpenAPI schema.
- **Tiptap extensions**: live in `src/components/Editor/extensions/`. Each extension has a unit test that round-trips through markdown.
- **Tailwind**: prefer utility classes; if a class string crosses ~6 utilities, extract a component. Don't reach for `@apply` except in the design tokens layer.
- **Pinia stores**: keep them dumb (state + getters + simple setters). Business logic lives in the API layer or in composables.
- **No CSS-in-JS, no styled-components.** Tailwind + scoped `<style>` is enough.

### 4.5 The editor — extra care

Anything touching the Tiptap editor or the markdown serializer needs:

1. A **round-trip test** added to `tests/round-trip/fixtures/` for the new feature
2. A check that all *existing* fixtures still round-trip
3. A note in the PR description confirming both

The round-trip test corpus is the contract. Treat it like a public API.

---

## 5. Working with the docker stack

```bash
docker compose --profile dev up        # everything: backend, frontend, drawio
docker compose --profile dev up -d     # detached
docker compose logs -f backend         # tail logs
docker compose down                    # stop everything
docker compose down -v                 # ★ careful: removes volumes
```

The wiki content volume is bind-mounted from `./data/content`. **Do not put committed files there** — that directory is the user's wiki, separate from the project repo. Add it to `.gitignore` of the project repo.

The drawio container is a vanilla `jgraph/drawio:latest`. We do not fork or modify it. Configuration is via env vars per its upstream docs.

---

## 6. Commits and branches

### 6.1 Branches

- `main` — protected, always green CI
- `feat/<short-name>` — feature work
- `fix/<short-name>` — bugfix
- `refactor/<short-name>` — non-functional change
- `docs/<short-name>` — docs only

### 6.2 Commit messages

Conventional Commits, lowercase scope:

```
feat(backend): add page move endpoint
fix(editor): drawio iframe loses focus on save
refactor(storage): extract path validation
docs(architecture): clarify save lifecycle
chore(deps): bump pygit2 to 1.15
test(round-trip): add fixture for nested task lists
```

Body wrapped at 72 cols. Reference issues with `Closes #N` or `Refs #N`.

**Do not include "co-authored-by: Claude" or similar lines.** Commits are authored by the human running you.

### 6.3 Two distinct git contexts

There are **two repositories** at play. Don't confuse them.

| | Project repo | Content repo |
|---|---|---|
| Path | the project root | `./data/content/` |
| Contains | source code, this CLAUDE.md, etc. | the user's wiki: `.md` files, attachments |
| Who commits | developers (humans + Claude Code) | Libreta itself, on every page save |
| Author | conventional commits | "Libreta <libreta@localhost>" (until M6 auth) |

When a user says "commit your work", they almost always mean the project repo. When they say "save the page", that goes through Libreta's save lifecycle and produces a commit in the content repo. If unclear, ask.

---

## 7. Updating project documents

Several docs in this repo are living documents. Keep them current:

- **`docs/PROGRESS.md`** — update at the end of any non-trivial chunk of work. Status block at the top, dated log entry, decisions if any.
- **`docs/ROADMAP.md`** — only update with explicit user agreement. Don't reorder or add milestones unilaterally.
- **`docs/ARCHITECTURE.md`** — update when an architectural choice changes. The "Open questions" section shrinks as decisions land — move resolved items into the relevant section above with a date stamp.
- **`docs/PROJECT.md`** — rarely changes. Treat the principles section as constitutional; propose changes, don't make them silently.
- **`README.md`** — update when the user-facing quickstart changes.
- **`CLAUDE.md`** (this file) — update when conventions change or when you find yourself repeatedly correcting the same thing.

---

## 8. When to stop and ask

Default to action for routine work. Stop and ask the user when:

- A task implies relaxing one of the **Inviolable rules** in §2.
- A task requires a new top-level dependency (a new framework, a new database, a new container in the stack). Confirm before adding.
- A task crosses the project / content repo boundary in a non-obvious way.
- The architecture document doesn't cover the case and the choice has long-term implications. Bias toward asking; cheap to clarify, expensive to refactor.
- A test would need to be deleted or weakened to make a change pass. Almost always indicates the change is wrong, not the test.

---

## 9. Things that look fine but aren't

A short collection of recurring traps, accumulated over time. Add to it.

- **"Just store this in SQLite for now"**: no. R2. If it needs to persist, find a file home for it.
- **"Skip the commit, it's a tiny change"**: no. R3. Save = commit, always.
- **"Pre-render the markdown to HTML and cache it"**: only if you also handle invalidation correctly when a `.md` file changes externally. Usually not worth the complexity for the perf gain.
- **"Add a `<script>` rendering capability for trusted users"**: no. R6. Even with auth, even for admins.
- **"Use a custom `:::tip` block syntax"**: no. R4. Stick to GFM. If we need callouts, they're rendered from a recognised pattern (e.g., GitHub's `> [!NOTE]`) — never a new syntax.
- **"Hold the diagram XML in the database for fast access"**: no. R2 + R5. The `.drawio.svg` file *is* the diagram, including its editable XML.
- **"Run `repo.status()` to check if the working tree is dirty before fetching/pulling"**: it's an O(working-tree-bytes) operation that hashes every untracked file (and every tracked file when the index stat cache is stale, e.g. right after a `rsync`-style migration). On low-spec hardware with hundreds of MB of attachments this pegs a core for minutes per call. Let `pygit2.CheckoutStrategy.SAFE` be the dirty-check during checkout — it scopes the work to files that would actually change.
- **"Auto-stage external modifications on push"**: tempting but wrong. Libreta commits on every write, so an auto-stage on push only ever catches edits made outside Libreta. Those are explicitly the user's responsibility to commit (`PROJECT.md` P1: the filesystem is the source of truth, including for users who edit it directly). Doing the scan costs a full-tree hash per push.
- **"Block FastAPI lifespan on startup sync/reindex"**: don't await heavy work in `lifespan` — launch it as `asyncio.create_task` instead. Even when the work is cheap on dev hardware, blocking lifespan makes the API unresponsive for the duration on the target box, which looks like "Libreta is broken" to a user reloading the tab.
- **"`location /api/` in nginx is enough to proxy the API"**: only as long as no API URL ends in a static-asset extension. A regex `location ~*` block for `*.svg|*.png|…` matches before plain prefix locations and will intercept `/api/v1/.../foo.drawio.svg`. Use `location ^~ /api/` so the prefix beats regex matches.

---

## 10. Quick reference

| | Backend | Frontend |
|---|---|---|
| Language | Python 3.12 | TypeScript (strict) |
| Pkg manager | `uv` | `pnpm` |
| Format | `ruff format` | `prettier` |
| Lint | `ruff check` | `eslint` |
| Types | `mypy --strict` | `vue-tsc --noEmit` |
| Test | `pytest` | `vitest`, `playwright` |
| Run dev | `uv run uvicorn ...` | `pnpm dev` |

When in doubt: re-read the "Principles" section of [`docs/PROJECT.md`](./docs/PROJECT.md), then the "Overview" and "Components" sections of [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md). Most questions are answered there.
