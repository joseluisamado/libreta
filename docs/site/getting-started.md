---
title: 'Getting started'
---

# Getting started

Five minutes from "nothing installed" to "my first wiki page is live and
committed to a git repo."

## What you need

- A machine with **Docker Engine 24+** and the `docker compose` plugin.
  Linux, macOS, or Windows with WSL2 — anything that runs Docker.
- A **git repository** for your wiki. This can be:
  - A brand new empty repo on GitHub, Gitea, Forgejo, or self-hosted.
  - An existing repo of markdown files you want to import.
  - A bare repo on another machine that you reach via SSH.
- An **SSH key** with read/write access to that repo (only needed if
  the repo is private).

## Install

```bash
git clone https://github.com/<you>/libreta.git
cd libreta
make build-prod
```

That builds two local Docker images: `libreta-api` and `libreta-frontend`.
No public registry yet, so the build runs on your machine.

## Start

```bash
VERSION=$(cat VERSION) docker compose \
    -f docker-compose.yml -f docker-compose.prod.yml up -d
```

This starts three containers:

| Container | Purpose |
|---|---|
| `libreta-api` | FastAPI backend — reads/writes pages, runs git, indexes search |
| `libreta-frontend` | nginx serving the SPA bundle, proxies `/api/` to the backend |
| `libreta-drawio` | diagrams.net editor (separate process, talks to your browser) |

Open `http://localhost:8080` — you'll see the empty Libreta shell with no
sources configured yet.

## Add your wiki

Click the gear icon (top right) or visit `http://localhost:8080/-/admin`.

### If your wiki repo is private

1. Go to **SSH keys** → **Add key**.
2. Paste the private key (e.g. `cat ~/.ssh/id_ed25519`). Give it a label.
3. Save. Libreta stores the key inside its data volume at mode `0600`;
   it never lands in a project file.

### Add the source

1. Go to **Git sources** → **Add source**.
2. Fill in:
   - **ID** — a slug like `my-wiki`. Used in URLs.
   - **Label** — display name in the sidebar.
   - **Remote URL** — `git@github.com:you/wiki.git` for SSH, or
     `https://github.com/you/wiki.git` for public HTTPS.
   - **Branch** — usually `main`.
   - **Sync interval** — how often Libreta pulls from the remote
     (15 minutes is a sane default).
   - **SSH key** — pick the one you added, if private.
3. Save.

A grey dot appears next to the source — that's the clone in progress.
When it turns green, you're synced. The page tree appears in the
sidebar; if the repo was empty, you'll just see an empty source.

## Your first page

Click **New page** in the sidebar (or hit `Ctrl/Cmd-N`). Type a path
like `welcome` and hit enter. The editor opens.

Type something. Save with `Ctrl/Cmd-S` or by clicking **Save** in the
toolbar.

Behind the scenes:

1. Libreta writes `welcome.md` (with YAML frontmatter) into the local
   clone.
2. Creates a git commit authored as `Libreta <libreta@localhost>`.
3. Schedules a push to your remote (you don't wait for it).
4. Updates the SQLite full-text index.

Verify by checking the remote — you'll see the commit there within a
second or two.

## What's in a page

Pages are markdown files with YAML frontmatter:

```markdown
---
title: 'Welcome'
created: 2026-05-09T12:00:00Z
updated: 2026-05-09T12:00:00Z
tags: [intro]
---

# Welcome

Your content here.
```

Libreta sets `created` on first save, `updated` on every save, and
preserves anything you put in frontmatter manually. It doesn't strip
fields it doesn't recognise — drop your own metadata in there freely.

## Diagrams

In the editor toolbar, click the diagram icon. The drawio editor opens
in a modal. Build your diagram, click **Save**.

The diagram is saved as `<page-name>.drawio.svg` in the page's sidecar
directory and embedded in the page as a regular markdown image. Open
the page elsewhere — github.com, VS Code's drawio extension, even just
a static markdown viewer — and the diagram still renders, because it's
an SVG.

Double-click an existing diagram to edit it.

## Attachments

Drag and drop a file into the editor, or paste an image from the
clipboard. Libreta:

1. Stores the file in the page's sidecar directory (`<page-name>.md/`
   if the page is `<page-name>.md`).
2. Embeds an image or download link in the markdown.
3. Commits and pushes.

Attachment paths are page-relative, so the page is portable: clone the
repo elsewhere and the images keep resolving.

## Editing from outside Libreta

Because the storage is just a git repo, you can clone it on another
machine, edit a page in VS Code or whatever, commit, push. Libreta
picks up the change on its next sync (or click **Sync** in the
sidebar to force it now).

This means: Libreta on your phone via the responsive web UI, VS Code on
your laptop, plain `vim` on the server — all editing the same wiki.

## Where to go from here

- [Front Libreta with HTTPS using Caddy](../DEPLOY.md)
- [Back up your wiki](../BACKUP.md)
- [Import from Apple Notes](../MIGRATION-APPLE-NOTES.md)
- [FAQ](./faq.md)
- [Troubleshooting](./troubleshooting.md)
