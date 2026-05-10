# MIGRATION-APPLE-NOTES.md — moving Apple Notes into Libreta

Libreta ships an importer that reads `NoteStore.sqlite` directly and writes
one markdown file per note into a clone of your wiki repository. You then
review the result, commit, and push.

This is the only first-party migration path for v1.0. Other systems
(Notion, Obsidian, BookStack, Wiki.js, …) are deferred until a real user
needs them — Apple Notes is the one we use ourselves.

---

## What gets migrated

✅ **Faithfully:**

- Note title → `# Heading` and frontmatter `title`.
- Plain text, paragraphs, line breaks.
- Bold, italic, monospaced, strikethrough.
- Apple's three heading levels (Title / Heading / Subheading) → H1 / H2 / H3.
- Bulleted, dashed, and numbered lists, including indentation.
- Checklists → GFM task lists (`- [ ]` / `- [x]`).
- Block quotes.
- Inline links.
- Image attachments (PNG, JPG, HEIC, etc.) — copied to a sidecar dir and
  referenced inline.
- Other file attachments (PDFs, audio, …) — copied as-is, referenced as
  download links.
- Created / updated timestamps → frontmatter.
- Folder structure → directory hierarchy.

⚠️ **Best-effort or lossy:**

- Apple Notes tables: rendered as GFM tables; cells with anything other
  than plain text (images, checklists) emit a warning.
- Highlight colours, font sizes, custom indents beyond list nesting.
- Drawings and scribbles: kept as PNG/SVG attachments where possible, but
  layered ink data is not editable afterwards.

❌ **Skipped, with a warning:**

- **Locked / encrypted notes.** The importer can't decrypt them. Unlock
  in Notes.app first if you want them migrated.
- **Smart Folders.** They're queries, not content — they don't import.
- **Recently Deleted.** Not touched.

---

## Prerequisites

1. A Mac running macOS 12+ with the Notes you want to migrate.
2. **Full Disk Access** for your terminal: System Settings → Privacy &
   Security → Full Disk Access → add your terminal app (Terminal, iTerm2,
   etc.). Without this, opening `NoteStore.sqlite` returns
   `unable to open database file`.
3. A clone of your Libreta wiki git source on the same Mac. This can be:
   - The same repo that's configured in your live Libreta instance, or
   - A fresh empty repo if you're seeding a new wiki.

   The importer writes files into your local clone — it does not touch
   the running Libreta instance directly. You commit and push when you're
   satisfied with the result.

4. Quit Notes.app first. macOS doesn't lock the database, but a quiet
   Notes app keeps the snapshot consistent.

---

## Step-by-step

### 1. Locate your clone

```bash
cd ~/wikis/my-wiki         # or wherever your clone lives
git status                  # confirm it's a clean working tree
git pull                    # get the latest from the remote
```

### 2. Dry-run the import

```bash
make import-apple-notes-dry REPO=$PWD
```

or, equivalently:

```bash
cd /path/to/libreta
uv run --project backend python scripts/import_apple_notes.py \
    --repo ~/wikis/my-wiki \
    --dest apple-notes \
    --dry-run
```

The dry-run prints one line per note that *would* be written, plus a
summary of locked/empty/missing-attachment counts. Read the warnings —
they tell you which notes won't survive the trip cleanly.

### 3. Narrow the scope (optional)

If you only want one folder or one account:

```bash
make import-apple-notes-dry REPO=$PWD \
    ACCOUNT="iCloud" \
    FOLDER="Recipes"
```

`ACCOUNT` matches Notes account names exactly (`iCloud`, `On My Mac`,
`Gmail`, …). `FOLDER` matches folder titles, again exactly.

### 4. Run for real

```bash
make import-apple-notes REPO=$PWD
```

The importer writes:

```
~/wikis/my-wiki/
└── apple-notes/
    ├── recipes/
    │   ├── pulled-pork.md
    │   ├── .pulled-pork.md/      ← sidecar dir
    │   │   └── IMG_4231.heic
    │   └── …
    ├── work/
    │   └── q4-okrs.md
    └── _inbox/                   ← notes with no folder
        └── todo-list.md
```

Frontmatter on every imported page:

```yaml
---
title: 'Pulled pork'
created: 2024-08-12T14:22:09Z
updated: 2025-11-04T09:18:50Z
apple_notes_account: 'iCloud'
apple_notes_folder: 'Recipes'
apple_notes_uuid: 0F2A...-...-...
---
```

The `apple_notes_uuid` field lets you re-run the importer later and
correlate notes by identity — useful if you want to do a second pass after
fixing some notes manually.

### 5. Review and commit

```bash
cd ~/wikis/my-wiki
git status
git diff -- apple-notes/      # spot-check a few pages
```

For a large import, render a sample in Libreta first by pushing a small
subset and pointing the running instance at the source. Iterate on the
folder structure or on individual notes that didn't render well, then
push the rest:

```bash
git add apple-notes
git commit -m "import apple notes ($(date +%Y-%m-%d))"
git push
```

Libreta's running instance picks up the new content on the next sync
(usually within a minute) — or you can hit **Sync** in the sidebar.

---

## What if I want to keep using Apple Notes too?

Don't. The importer is a one-way migration: there's no syncing back. If
you want to keep both systems in step, you'll end up with diverging
copies and a manual reconciliation problem.

If you genuinely want a one-shot migration that you might re-run after
adding more notes, the `apple_notes_uuid` frontmatter field lets a future
importer detect "this note has already been migrated, skip it" — but no
such re-run mode is implemented yet. File a request when you need it.

---

## Troubleshooting

**`error: NoteStore.sqlite not found at …`**

Pass `--notestore` explicitly:

```bash
uv run --project backend python scripts/import_apple_notes.py \
    --notestore "/Users/$USER/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite" \
    --repo …
```

**`sqlite3.OperationalError: unable to open database file`**

You don't have Full Disk Access. Grant it to your terminal in System
Settings → Privacy & Security → Full Disk Access, then **fully quit and
relaunch the terminal** (the permission only applies to newly-spawned
processes).

**Notes import as empty / single-line / garbled**

The protobuf decoder targets the most common note format. If a particular
note imports empty:

1. Open it in Notes.app and copy/paste its contents to make Notes
   re-serialise the body. Save, quit Notes, re-run the importer.
2. If it still fails, fall back to copy/paste into a new `.md` file by
   hand. Open an issue with the (anonymised) note structure if you'd
   like the importer to learn it.

**Attachment files missing**

The importer reports `attachment file missing for <note>: <uuid>` when a
note references an attachment whose file isn't on disk. Common causes:
- The attachment is iCloud-only and hasn't been downloaded locally. In
  Notes.app, scroll to the attachment to force a download, then re-run.
- The attachment is a Notes-internal type (live drawing, scanned doc) we
  don't unpack. The note text imports; the attachment doesn't.

**Tables look wrong**

Apple Notes tables don't map cleanly to GFM. Tables with multi-line cells
or embedded attachments are flagged by warnings. Fix them by hand after
import.

---

## Reference: what the script actually does

For the curious, the migration is roughly:

1. Open `NoteStore.sqlite` read-only.
2. Join `ZICCLOUDSYNCINGOBJECT` (notes + folders + accounts) with
   `ZICNOTEDATA` (the gzip'd protobuf body).
3. For each non-deleted, non-locked note: gunzip + decode the protobuf to
   recover plain text + per-run style metadata.
4. Walk the runs to emit GFM markdown, applying inline marks
   (bold/italic/...) and paragraph styles (heading/list/todo/...).
5. Resolve attachment UUIDs to files under `Media/<uuid>/`, copy them
   into a sidecar directory, rewrite inline references.
6. Write the `.md` file with frontmatter capturing identity, folder, and
   timestamps.
7. Print a summary + warnings to stderr.

No third-party dependencies — the protobuf reader is hand-rolled because
we only need a handful of fields and a `protobuf` dep would dwarf the
script.

Source: [`scripts/import_apple_notes.py`](../scripts/import_apple_notes.py).
