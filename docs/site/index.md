---
title: 'Libreta'
---

# Libreta

A self-hosted wiki where the source of truth is a git repository of plain
markdown files — with a Confluence-grade WYSIWYG editor and first-class
diagrams.net integration on top.

## What it is

- **A wiki you can run on your own hardware.** Single Docker Compose
  stack. No SaaS, no telemetry, no plugins to install.
- **Git as the storage layer.** Pages are `.md` files in a git repository
  you control (GitHub, Gitea, Forgejo, or a bare repo on another box).
  Every save is a commit. The repo is the entire backup.
- **Editing that doesn't fight the format.** Tiptap-powered WYSIWYG that
  round-trips through CommonMark + GFM byte-identically. No proprietary
  block syntax. No DSL.
- **Diagrams that survive the wiki.** First-class diagrams.net
  integration — saved as `.drawio.svg` next to the page, openable in
  github.com or VS Code's drawio extension without Libreta.
- **Search that scales to a personal corpus.** SQLite FTS5, regenerable
  from the file tree at any time.

## What it isn't (yet)

- **Multi-user.** v1.0 is single-user; auth, ACLs, and per-user commit
  attribution come in M6.
- **A real-time collaborative editor.** Optimistic locking + a
  "someone-else-is-editing" indicator may land later; CRDT-style live
  collab is unlikely.
- **A plugin marketplace.** A typed extension API may come; a plugin
  store will not.

## Where to go next

| If you want to… | Go to |
|---|---|
| Get a wiki running on your machine in five minutes | [Getting started](./getting-started.md) |
| Deploy to a server with HTTPS | [`DEPLOY.md`](../DEPLOY.md) |
| Move pages out of Apple Notes | [`MIGRATION-APPLE-NOTES.md`](../MIGRATION-APPLE-NOTES.md) |
| Understand the architecture | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Back up or restore | [`BACKUP.md`](../BACKUP.md) |
| Read the security posture | [`SECURITY-REVIEW.md`](../SECURITY-REVIEW.md) |
| Find the answer to a common question | [FAQ](./faq.md) |
| Diagnose something that's broken | [Troubleshooting](./troubleshooting.md) |
