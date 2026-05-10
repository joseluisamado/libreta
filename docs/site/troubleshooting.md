---
title: 'Troubleshooting'
---

# Troubleshooting

The fastest debug loop is `docker compose logs -f api`. The backend logs
every git operation, every sync, every save. When something is wrong,
the answer is usually one tail away.

This page covers symptoms that aren't self-explanatory from the logs.

## Source / sync

### Sidebar shows an orange dot next to a source

Sync error. Click into the source — under each, there's a
`last_sync_error` field. Common causes:

| Error | Cause |
|---|---|
| `authentication required` | No SSH key bound, or a private repo accessed with a public-key-less callbacks |
| `Permission denied (publickey)` | The SSH key isn't in the remote's allowed list |
| `repository not found` | Typo in the URL, or the repo was deleted |
| `connection refused` / `timed out` | Remote unreachable from the host |
| `non-fast-forward` | Local has commits the remote doesn't (rare; see below) |

Fix the cause, then click **Sync** in the sidebar to retry immediately.

### `non-fast-forward` push errors

Someone (you, on another machine, or another tool) pushed to the remote
and Libreta's local clone now diverges. Resolve by editing the working
tree directly:

```bash
docker compose exec api sh -lc '
  cd /var/lib/libreta/repos/<source-id>
  git fetch
  git rebase origin/main
  git push
'
```

If the rebase has conflicts, you'll need to resolve them by hand. This
should be rare — Libreta's normal sync path pulls before pushing.

### Clone never finishes

Run `docker compose logs api` and look for the source id around the
clone time. If the container restarted mid-clone, the working tree may
be partial. Delete it from inside the volume and re-add the source:

```bash
docker run --rm -v libreta-data:/data alpine \
  rm -rf /data/repos/<source-id>
```

Then re-add the source in the Admin UI — it'll re-clone from the
remote.

### Pages exist in the repo but not in the sidebar

Two possibilities:

1. **Tree-walk hasn't picked them up.** This happens if the files were
   added by a tool other than Libreta and the sidebar wasn't refreshed.
   Click on a different source then click back — the tree re-fetches.
2. **The files aren't where Libreta looks.** Libreta supports both flat
   repos (markdown in the root) and `pages/`-rooted repos. If your repo
   has both `README.md` at the root **and** a `pages/` subdirectory, the
   `pages/` subdirectory wins — the root files are ignored. Move them
   under `pages/` or remove the directory.

## Editor

### Save shows "Conflict" / "page changed on disk"

Another tool wrote to the same file between your last load and your
save. Reload the page (you'll lose the in-flight edit), then redo the
change.

### `Round-trip mismatch` warning when saving

The serializer can't reproduce some construct from the editor state
byte-identically. Save anyway — your content will be fine, but the
exact whitespace or quoting may differ. If you see this on a feature
that's supposed to round-trip (lists, tables, code), open an issue
with the source markdown attached.

### Diagram saves but doesn't appear

Two known shapes:

- **Browser blocked the drawio iframe.** The iframe URL is the
  `LIBRETA_DRAWIO_URL` value (default `http://localhost:8093`). If your
  browser is on a different host than the Docker host, point this env
  var at a URL the browser can reach.
- **The save round-tripped but the markdown reload didn't pick up the
  new SVG.** Hard-reload the page (Ctrl/Cmd-Shift-R).

### Mermaid block shows source instead of diagram

The mermaid library lazy-loads. Wait a beat — if it still doesn't
render, check the browser console for a `mermaid` parse error (your
diagram syntax may be wrong). The textual source is what's stored in
the markdown; Libreta isn't dropping it.

## Search

### Search returns no results

Run `docker compose exec api libreta reindex`. If the repo was
populated outside Libreta (bulk import, manual `cp`), the FTS5 index
won't know about the new files until you rebuild.

### Search returns stale results after a delete

The index removes entries on save and on delete via the API. If you
deleted a file by writing to the working tree directly, the entry
lingers until the next reindex.

## Deployment

### `502 Bad Gateway`

The API container isn't healthy. Common causes:

- It's still starting. The first request after `docker compose up` can
  take a few seconds while pygit2 opens the existing clones.
- Port collision. If `8080` was already taken, `frontend-prod` may have
  failed to bind. Check `docker compose ps`.
- The API crashed. `docker compose logs api` will show the traceback.

### Caddy says `no certificate available`

In order, check:

1. Your domain's A/AAAA record actually points at the host.
2. Ports 80 **and** 443 are reachable from the public internet (not
   just on the LAN — Let's Encrypt validates from the outside).
3. The `Caddyfile` has the right domain and an email you actually read.
4. `docker compose logs caddy` for the actual ACME error.

If you're behind a NAT or a CDN, you may need DNS-01 validation
instead of HTTP-01. See Caddy's docs.

### High memory usage

Libreta is comfortable in 100 MB at idle. If you see it climbing into
hundreds of megabytes:

- A pathological page (multi-megabyte markdown with thousands of
  inline images) can spike during render. Page load is async; this
  shouldn't persist.
- A FTS5 reindex on a huge corpus uses memory proportional to the
  index size. If you're hitting an OOM there, give the container
  more RAM (`mem_limit: 1g` in the compose override) — or chunk the
  reindex by source.

If neither applies and memory grows monotonically over days, that's a
leak. Open an issue with logs and a `docker stats` snapshot.

## Backup / restore

### Backup tar fails with "permission denied"

The `libreta-data` volume contains files owned by the API container's
user. The backup snippet in [`BACKUP.md`](../BACKUP.md) uses
`docker run -v libreta-data:/data alpine tar ...` precisely so it runs
inside a container that can read the volume. Don't try to tar the
volume's host-side directory directly.

### Restore: "fatal: not a git repository"

You restored the volume but the API can't see the working trees.
Verify:

```bash
docker run --rm -v libreta-data:/data alpine \
  ls /data/repos
```

You should see one directory per source. If not, the tar was either
empty or extracted into the wrong path. Re-extract with `cd /data &&
tar xzf ...` (no leading slash — relative paths inside the archive).

### Restore: search shows nothing

Expected if you restored without `meta/_meta/search.db`. Run
`docker compose exec api libreta reindex`.

## Performance

See [`PERFORMANCE.md`](../PERFORMANCE.md) for measured numbers. If
something feels slow:

```bash
bash scripts/smoke_bench.sh
```

Compare to the numbers in `PERFORMANCE.md`. A regression of >2× without
an obvious cause is worth digging into.

## When all else fails

1. `docker compose down && docker compose -f ... up -d` — surprising
   how often "have you tried turning it off and on again" works.
2. `docker compose logs api > /tmp/log.txt` — attach this to any bug
   report.
3. Check the [project repo issues](https://github.com/<you>/libreta/issues)
   for someone with the same symptom.
