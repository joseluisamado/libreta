---
title: 'FAQ'
---

# Frequently asked questions

## Storage and content

### Where is my data?

In two places:

1. **Authoritative**: the git remote you configured in Admin → Git Sources.
   That's where every page save eventually lands. If you lose Libreta but
   still have the remote, your wiki is intact.
2. **Local clone**: inside the `libreta-data` Docker volume at
   `/var/lib/libreta/repos/<source-id>/`. This is what Libreta reads from
   and writes into. It's a regular git working tree.

### Can I edit pages outside Libreta?

Yes. Clone the same git repo on another machine, edit, commit, push.
Libreta picks up your changes on the next sync (or when you click **Sync**
in the sidebar). This works in both directions: edit in Libreta, pull on
the server; edit on the server with `vim`, push, see it in Libreta.

### Why git instead of a database?

Three reasons:

1. **Portability.** Your content survives Libreta. If the project dies,
   you still have a directory of markdown files and a full edit history.
2. **Backup.** `git push` is the entire backup story.
3. **Tooling.** `git log`, `git blame`, `git diff`, `grep -r`, every
   editor in existence — all work on a Libreta wiki without any
   adapters.

The trade-off is concurrent editing: git can't merge two simultaneous
edits to the same line of the same page. v1.0 is single-user, so this
isn't a problem yet.

### Can I host multiple wikis?

A single Libreta instance can have multiple **sources** — each is a
separate git repo, listed independently in the sidebar. So one Libreta
can present a "personal" wiki, a "work" wiki, and an "ops runbook" wiki
side by side, each backed by its own remote.

What you can't do (by design) is have one source serve multiple users
with different visibility — that's M6.

## Editing

### What does the editor support?

CommonMark + GFM:

- Headings, lists (bulleted, numbered, task lists), block quotes.
- Bold, italic, strikethrough, inline code.
- Code blocks with syntax highlighting.
- Tables (insert/delete rows/columns; column resize landed in M3).
- Links, images, file attachments.
- Math via KaTeX (`$inline$`, `$$block$$`).
- Mermaid diagrams in fenced code blocks (` ```mermaid `).
- diagrams.net diagrams via the toolbar.

Plus the standard editing affordances: undo/redo, find/replace, paste-as-text.

### What about raw HTML in markdown?

Stripped at render time (and at save). Libreta deliberately doesn't
allow user content to execute JavaScript in another user's browser
session. If you need a callout or admonition, use GitHub's
`> [!NOTE]` syntax (recognised by the renderer); don't reach for
`<div class="warning">`.

### Can I customise the editor's appearance?

Reading width has a toggle in the toolbar (standard / wide). The
syntax theme is GitHub-light. There isn't a dark mode toggle yet —
the system theme isn't followed either. Open an issue if you want it.

### What does "save" actually do?

Each save:

1. Serialises the editor content back to markdown (round-trip is
   byte-identical for the supported feature set).
2. Writes the file to disk in the local clone.
3. Creates a git commit.
4. Updates the SQLite FTS5 index.
5. Schedules a push to the remote (returns immediately — you don't
   block on the network).

If the push fails (remote down, expired credential), the commit stays
local and is retried on the next sync. The sidebar shows an orange dot
on sources with pending or failing pushes.

### How are simultaneous edits handled?

v1.0 is single-user. If you somehow do edit the same page from two
Libreta instances against the same remote, you'll get a git push
rejection on the second one — the first writer wins, and the second
writer needs to manually resolve. M9 may add an in-app warning for
this; for now: don't.

## Search

### How fast is search?

Smoke-tested at ~6 ms median on a ~200-page corpus. The target is
< 500 ms on a 1000-page corpus, with comfortable headroom.
See [`PERFORMANCE.md`](../PERFORMANCE.md).

### Search returned weird results / nothing

The full-text index is a SQLite FTS5 table at
`/var/lib/libreta/meta/_meta/search.db`. If it's out of sync with the
filesystem (e.g. you bulk-imported pages by writing files into the
clone instead of via the API), rebuild it:

```bash
docker compose exec api libreta reindex
```

Reindexing scans every `.md` file across every source and rebuilds the
table. On the corpus sizes Libreta targets, it takes seconds.

## Deployment

### Can I run Libreta on a Raspberry Pi?

Yes. The performance targets in `PROJECT.md` are calibrated to a Pi 4.
Libreta runs comfortably under 100 MB resident on a small instance. The
docker images are amd64 + arm64 (same Dockerfiles, multi-arch build
when wired up).

### Do I need HTTPS?

For anything reachable beyond `localhost`, yes. The recommended setup
is the bundled Caddy overlay (`docker-compose.caddy.yml` +
`Caddyfile.example`), which terminates TLS with Let's Encrypt
automatically. See [`DEPLOY.md`](../DEPLOY.md).

### Does Libreta have authentication?

Not in v1.0. Front it with a reverse proxy that adds auth (Caddy +
basic auth, oauth2-proxy, etc.) or restrict access at the network
level. Native auth lands in M6.

### Can I expose Libreta to the public internet without auth?

Technically yes, structurally no. The whole API is unauthenticated —
anyone who can reach it can write to your wiki. Don't.

### How do I back up?

The git remote is the primary backup; periodic snapshots of the
`libreta-data` volume cover SSH keys and local state. Full procedure:
[`BACKUP.md`](../BACKUP.md).

## Migration

### Can I import from Apple Notes?

Yes — there's a first-party importer that reads Apple's
`NoteStore.sqlite` directly. See
[`MIGRATION-APPLE-NOTES.md`](../MIGRATION-APPLE-NOTES.md).

### What about Notion / Obsidian / BookStack / Wiki.js?

No first-party importer for v1.0. Notion's HTML/markdown export and
Obsidian's vault format are both close enough to Libreta's storage
that a manual `cp` works for most pages — adjust frontmatter if you
care, then commit and push. Open an issue (or a PR) if you'd like a
packaged importer.

## Operations

### How do I update Libreta?

```bash
cd /opt/libreta              # wherever you cloned
git fetch --tags
git checkout v1.1.0          # or the new tag
make build-prod
VERSION=$(cat VERSION) docker compose -f docker-compose.yml \
    -f docker-compose.prod.yml up -d
```

`up -d` recreates only the containers whose image changed; the
`libreta-data` volume is untouched.

### How do I tail the logs?

```bash
docker compose logs -f api
```

Look for `git remote host=...` (each git op), `push` / `sync` events,
and `last_sync_status` updates.

### Where are the OpenAPI docs?

The API is documented at `/api/v1/docs` (Swagger UI) and
`/api/v1/redoc` on whatever host:port you exposed.

## Philosophy

### Why no plugin marketplace?

Plugin marketplaces optimise for surface area, not robustness. Every
plugin is a future security review, a future support load, a future
"I installed a thing and now my wiki is broken." Libreta's design rule
is "the markdown file is the contract" — anything that needs to live
outside that contract eventually breaks portability. M10 may expose a
stable extension API for power users to add features without forking,
but it won't ship with a store.

### Why no custom block syntax?

Same reason. The moment you write `:::tip` in a page, that page only
renders correctly inside Libreta. Stick to GFM and your content
survives any markdown viewer.

### Will you add feature X?

Maybe. The roadmap (`docs/ROADMAP.md`) lists what's planned. Anything
on "Things we will not do" is hard-no by design — see
[`PROJECT.md`](../PROJECT.md) "Non-goals" for the rationale. Everything
else is fair game; open an issue.
