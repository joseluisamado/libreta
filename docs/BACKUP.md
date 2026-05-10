# BACKUP.md — backing up and restoring Libreta

Libreta's content model makes backups simple: **the canonical copy of your
wiki lives in the git remote you configured under Admin → Git Sources.**
Everything Libreta keeps locally is either a clone of that remote, derived
data (search index), or operator state (SSH keys, TLS certs).

This guide covers what to back up, how, and how to restore — from a single
deleted page to a lost server.

---

## What state exists

| Where | What | Authoritative? | Backup priority |
|---|---|---|---|
| Your **git remote** (GitHub / Gitea / Forgejo / bare repo) | Pages, attachments, drawio diagrams, frontmatter | ✅ Yes — source of truth | n/a, the remote is the backup |
| `libreta-data` Docker volume → `/var/lib/libreta/repos/<id>/` | Local clone of each git source (working tree + `.git`) | ❌ Mirrors the remote | Optional — re-cloneable |
| `libreta-data` → `/var/lib/libreta/ssh_keys/` | Private SSH keys for git remotes | ✅ Yes — only copy on this host | **High** |
| `libreta-data` → `/var/lib/libreta/meta/_meta/` | `sources.json`, `watched.json`, FTS5 search index | Mixed — config is, index is regenerable | **High** for config, low for index |
| `caddy-data` Docker volume (if using the Caddy overlay) | TLS certificates, ACME account key | Reissuable but rate-limited | Medium |
| Project repo (`/opt/libreta`) | Source code, compose files, `Caddyfile`, `.env`, `VERSION` | ✅ For your local edits (Caddyfile, .env) | **High** for `.env` and `Caddyfile` |

The wiki itself (markdown + attachments) is *not* in this table because it
is not stored on the Libreta host in any authoritative way — it lives in
your git remote. Push works on every save; if a save's commit reached the
remote, that page is backed up.

---

## Strategy: lean on git for content, snapshot the rest

The recommended setup uses two complementary mechanisms:

1. **Git push to a remote** (already configured) covers all wiki content
   automatically. Verify this is healthy: a green dot in the sidebar next
   to each source means the last push succeeded.
2. **Periodic tar snapshots** of the two named volumes (and the `.env` /
   `Caddyfile`) cover everything else.

You almost never need to restore (1) from a snapshot — you re-add the
source in the Admin UI and Libreta re-clones from the remote. Snapshots
exist for the things that *aren't* in the remote: SSH keys, config, certs.

---

## Backing up

### Quick: one-shot snapshot

```bash
cd /opt/libreta
mkdir -p ./backups
DATE=$(date +%Y%m%d-%H%M%S)

# Volumes
docker run --rm \
  -v libreta-data:/data:ro \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf "/backup/libreta-data-${DATE}.tar.gz" -C /data .

docker run --rm \
  -v caddy-data:/data:ro \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf "/backup/caddy-data-${DATE}.tar.gz" -C /data .

# Local config (project repo)
tar czf "./backups/libreta-config-${DATE}.tar.gz" \
  .env Caddyfile VERSION docker-compose*.yml
```

The two volume archives are **safe to take while Libreta is running** —
git working trees and SQLite-WAL are tolerant of being read concurrently
for a tar. If you want a fully consistent snapshot, stop the stack first
(`docker compose ... down`).

### Scheduled: cron + offsite copy

```cron
# /etc/cron.d/libreta-backup — runs nightly at 03:30
30 3 * * * root cd /opt/libreta && ./scripts/backup.sh >> /var/log/libreta-backup.log 2>&1
```

A skeleton `scripts/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/libreta
DATE=$(date +%Y%m%d)
DEST=./backups
mkdir -p "$DEST"

docker run --rm -v libreta-data:/data:ro -v "$PWD/$DEST:/b" \
  alpine tar czf "/b/libreta-data-$DATE.tar.gz" -C /data .
docker run --rm -v caddy-data:/data:ro -v "$PWD/$DEST:/b" \
  alpine tar czf "/b/caddy-data-$DATE.tar.gz" -C /data .
tar czf "$DEST/libreta-config-$DATE.tar.gz" \
  .env Caddyfile VERSION docker-compose*.yml

# Keep 14 days locally
find "$DEST" -name '*.tar.gz' -mtime +14 -delete

# Push offsite (rclone, rsync, restic — pick one)
# rclone copy "$DEST" b2:my-bucket/libreta/
```

The script doesn't ship in the repo by default — copy this into
`scripts/backup.sh`, make it executable, and adapt the offsite step to
your storage.

### What you can skip

- `pnpm-store` volume — pnpm cache, only present in dev mode.
- The FTS5 search index inside `meta/_meta/` — regenerable in seconds
  with `libreta reindex`. Backing it up does no harm; restoring without
  it just costs one rebuild.

---

## Restoring

Three scenarios, in increasing order of severity.

### Scenario A: a single page was deleted or corrupted

The wiki repo is a normal git repo. Use git.

From the host:

```bash
docker compose exec api sh -lc \
  'cd /var/lib/libreta/repos/<source-id> && git log -- pages/path/to/page.md'
```

Find the commit before the bad change, then restore it through the UI
(create a new revision pasting the previous content) or directly:

```bash
docker compose exec api sh -lc '
  cd /var/lib/libreta/repos/<source-id> &&
  git checkout <good-sha> -- pages/path/to/page.md &&
  git commit -m "restore page from <good-sha>" &&
  git push
'
```

The next periodic sync — or a manual **Sync** click in the sidebar —
brings the rest of the world in line.

### Scenario B: the `libreta-data` volume is lost

You still have the project repo, the `.env`, and your git remotes.

```bash
cd /opt/libreta

# 1. Re-create the volume by bringing the stack up
VERSION=$(cat VERSION) docker compose \
  -f docker-compose.yml -f docker-compose.prod.yml up -d
# (add -f docker-compose.caddy.yml if you use it)

# 2. Restore SSH keys + sources.json from the most recent snapshot
docker run --rm \
  -v libreta-data:/data \
  -v "$(pwd)/backups:/backup:ro" \
  alpine sh -c 'cd /data && tar xzf /backup/libreta-data-YYYYMMDD.tar.gz'

# 3. Restart so the API re-reads sources.json and re-clones each source
docker compose restart api
```

If you don't have a snapshot, the manual path is:

1. Re-add each SSH key in the Admin UI (paste the private key from
   wherever you keep them — password manager, another host, etc.).
2. Re-add each git source. Libreta clones from the remote.
3. Run `libreta reindex` once the clones finish, to rebuild search.

### Scenario C: the entire host is gone

On a fresh server:

```bash
# 1. Install Docker + docker compose
# 2. Clone the project repo
git clone https://github.com/<you>/libreta.git /opt/libreta
cd /opt/libreta
git checkout v1.0.0          # the version you were running

# 3. Restore config
tar xzf /path/to/backups/libreta-config-YYYYMMDD.tar.gz

# 4. Build images at the matching version
make build-prod

# 5. Restore volumes (creates them if missing)
docker volume create libreta-data
docker volume create caddy-data

docker run --rm -v libreta-data:/data -v /path/to/backups:/b:ro \
  alpine sh -c 'cd /data && tar xzf /b/libreta-data-YYYYMMDD.tar.gz'
docker run --rm -v caddy-data:/data -v /path/to/backups:/b:ro \
  alpine sh -c 'cd /data && tar xzf /b/caddy-data-YYYYMMDD.tar.gz'

# 6. Bring it up
VERSION=$(cat VERSION) docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.caddy.yml \
  up -d
```

Restoring `caddy-data` reuses your existing Let's Encrypt certificate, so
there's no rate-limit risk and no certificate-rotation event for clients
pinning the chain.

If you skip the `caddy-data` restore, Caddy issues a fresh certificate on
the first HTTPS request — fine, just observable.

---

## Verification

After any restore, sanity-check:

```bash
# API up
curl -sf https://wiki.example.com/api/v1/healthz

# Sources synced
curl -sf https://wiki.example.com/api/v1/sources | jq '.[] | {id, last_sync_status}'

# Search index has content
curl -sf 'https://wiki.example.com/api/v1/search?q=the' | jq '.results | length'
```

A non-zero search-result count and `"last_sync_status": "ok"` on each
source means content + sync are healthy. If search is empty but pages
render, run `docker compose exec api libreta reindex`.

---

## Verify that pushes are actually reaching the remote

Backups are only worth what they back up. The "push to remote" half of
the strategy is silent when it works — make sure it works.

```bash
# On the host: tail the API for push events
docker compose logs --since=24h api | grep -E 'push|sync'

# From the remote side: check most recent commit
git ls-remote <remote-url> refs/heads/main
```

A healthy install has at least one push log line per save. If you see
"sync error" in the sidebar and ignore it, you are not backed up.

---

## What this document doesn't cover

- **Encrypted backups.** Use `restic` or `borgbackup` if you need at-rest
  encryption — wrap the tar step or back up the volume directly.
- **Point-in-time restore of the search index.** It's not worth the
  complexity; rebuild from files instead.
- **Cross-version restore.** Restore against the same Libreta version
  you backed up from. If you must cross versions, restore first, then
  upgrade — never the other way around.
