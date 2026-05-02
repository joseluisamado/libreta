# Libreta

> A self-hosted wiki where the source of truth is a directory of plain markdown files in a git repository — with a Confluence-grade WYSIWYG editor and first-class diagrams.net integration on top.

**Status**: 🟡 Pre-alpha. Read-only wiki works end-to-end (M0 + M1 done). Editing, search, and diagrams still ahead. See [`docs/PROGRESS.md`](./docs/PROGRESS.md).

## Why this exists

Self-hosted wiki tools today force a tradeoff:

| Tool | Markdown files on disk | Git versioned | Native diagrams.net | Confluence-style WYSIWYG |
|---|---|---|---|---|
| Wiki.js | ⚠️ DB is source of truth, git is sync | ⚠️ via sync module | ❌ DIY sidecar | ✅ |
| BookStack | ❌ HTML in MariaDB | ❌ | ✅ | ✅ |
| Docmost | ❌ DB | ❌ | ✅ | ✅ |
| Wikmd | ✅ | ✅ | ❌ | ❌ |
| **Libreta** | ✅ | ✅ | ✅ | ✅ |

Libreta aims to combine the portability and grep-ability of file-based wikis with the editing experience of database-backed ones.

See [`docs/PROJECT.md`](./docs/PROJECT.md) for full motivation, principles, and non-goals.

## Quickstart

```bash
# Clone the project
git clone https://github.com/<you>/libreta.git
cd libreta

# Initialise your content repository (this is your wiki)
mkdir -p ./data/content
git -C ./data/content init

# Start it (dev stack: api + Vite frontend + drawio, all hot-reloading)
make dev

# Open http://localhost:8091  — Vite dev server (with HMR)
#      http://localhost:8092  — API directly (FastAPI / OpenAPI at /api/v1/docs)
#      http://localhost:8093  — drawio sidecar
```

Your wiki content lives in `./data/content` — a normal git repository of markdown files. You can clone it elsewhere, edit it in any editor, push it to GitHub or a private Forgejo, and Libreta will pick up changes.

### Dev vs prod

The Compose layout has two modes. Pick based on what you're doing:

| | Dev (`make dev` / `make up-dev` / `make rebuild-dev`) | Prod (`make up` / `make rebuild`) |
|---|---|---|
| Compose files | `docker-compose.yml` + `docker-compose.dev.yml` | `docker-compose.yml` only |
| Backend source | bind-mounted from `./backend/src`; uvicorn `--reload` picks up edits live | baked into the image at build time; no reloader |
| Frontend | Vite dev server with HMR (port 8091) | not served by Compose — build `frontend/dist` and put it behind your reverse proxy of choice (Caddy/Nginx) |
| When to rebuild | only when dependencies change (`pyproject.toml`, `pnpm-lock.yaml`, `Dockerfile`) | every code change before deploy |

The Makefile wraps both modes; you rarely need to type the raw `docker compose` command. Run `make help` for the full menu.

### Useful targets

```bash
make help                  # Show all available targets
make check                 # Run all pre-flight checks (lint + types + tests)
make import-dokuwiki-dry   # Preview a DokuWiki import without writing
make import-dokuwiki       # Import a DokuWiki installation into your wiki
                           #   override: SOURCE=/path/to/dokuwiki/storage/data make import-dokuwiki
```

## Features (target for v1)

- 📝 **Pages stored as markdown files** with YAML frontmatter — your content is portable, greppable, and survives Libreta.
- 🔀 **Git as the source of truth** — every save is a commit. Optional remote push to GitHub / Gitea / Forgejo.
- ✨ **WYSIWYG editor** with markdown round-trip via Tiptap.
- 🎨 **diagrams.net integrated** — toolbar button opens the editor inline, diagrams saved as `.drawio.svg`.
- 🖼️ **Image and arbitrary file uploads** — stored in `_attachments/` next to pages.
- 📊 **Confluence-style tables** — resizable columns, header rows, cell colours.
- 🔍 **Full-text search** — SQLite FTS5 index, regenerable from the file tree at any time.
- 📱 **Responsive** — works on mobile and desktop.
- 🐳 **One-command deploy** via Docker Compose.

See [`docs/ROADMAP.md`](./docs/ROADMAP.md) for what's planned beyond v1 (auth, multi-user, plugins, etc.).

## Project documents

| File | Purpose |
|---|---|
| [`docs/PROJECT.md`](./docs/PROJECT.md) | Motivation, principles, non-goals, success criteria |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Components, data model, tech stack, deployment topology |
| [`docs/ROADMAP.md`](./docs/ROADMAP.md) | Milestones M0 → M5 |
| [`docs/PROGRESS.md`](./docs/PROGRESS.md) | Current state of execution |
| [`CLAUDE.md`](./CLAUDE.md) | Conventions and guardrails for Claude Code agents working on this repo |

## License

TBD — likely AGPL-3.0 to match the wiki ecosystem norm and ensure forks remain open. Confirm before first public release.
