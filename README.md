# Libreta

> A self-hosted wiki where the source of truth is a directory of plain markdown files in a git repository — with a Confluence-grade WYSIWYG editor and first-class diagrams.net integration on top.

**Status**: 🟡 Pre-alpha. Architecture defined, implementation not started. See [`docs/PROGRESS.md`](./docs/PROGRESS.md).

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

> ⚠️ Not yet implemented. The commands below are the *intended* user experience; track [`docs/PROGRESS.md`](./docs/PROGRESS.md) for current state.

```bash
# Clone the project
git clone https://github.com/<you>/libreta.git
cd libreta

# Initialise your content repository (this is your wiki)
mkdir -p ./data/content
git -C ./data/content init

# Start it
docker compose up -d

# Open http://localhost:8080
```

Your wiki content lives in `./data/content` — a normal git repository of markdown files. You can clone it elsewhere, edit it in any editor, push it to GitHub or a private Forgejo, and Libreta will pick up changes.

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
