# DEPLOY.md — bootstrapping Libreta from scratch

This guide takes you from "empty server" to a running Libreta on your own
hardware. It covers a single-host Docker Compose deployment — the simplest
shape that makes sense for v0.x, where Libreta is a single-user wiki.

> The prerequisites assume Linux (Ubuntu / Debian / Fedora) but anything that
> runs Docker will do. Adjust paths and package names accordingly.

---

## Architecture overview (new model)

In this version, **all wiki content lives in git repositories that Libreta
clones and manages**. There is no `data/content/` wiki directory to initialise
manually. Instead, you:

1. Create (or already have) a git repo containing your wiki pages.
2. Tell Libreta about it via the Admin UI (`/-/admin` → Git Sources).
3. Libreta clones it locally, reads/writes pages into it, and pushes commits
   back to the remote asynchronously.

Docker volumes (not bind mounts) hold the cloned repos and SSH keys so they
survive container restarts and upgrades.

---

## 1. Prerequisites

- A host with at least 1 vCPU, 1 GB RAM, 5 GB free disk.
- Docker Engine 24+ and the `docker compose` plugin.
- Git ≥ 2.40 (on the host, for checking out the project).
- A git repository for your wiki content (GitHub, Gitea, Forgejo, or a bare
  repo on another server). The repo should have at least one commit and a
  `pages/` directory (or be empty — Libreta will create `pages/` on first
  save).
- An SSH key pair with read/write access to that repo, if it is private.
- A domain name pointed at the host (optional but recommended for TLS).

Check:

```bash
docker --version
docker compose version
```

---

## 2. Get the source

```bash
git clone https://github.com/<you>/libreta.git /opt/libreta
cd /opt/libreta
```

Pin to a released version rather than `main` for production:

```bash
git checkout v0.2.0          # whatever the latest released tag is
```

---

## 3. Build the production images

Libreta currently builds images locally; there is no public registry yet.

```bash
make build-prod
```

This produces:

```
libreta-api:0.2.0       libreta-api:latest
libreta-frontend:0.2.0  libreta-frontend:latest
```

---

## 4. Configure the runtime

Create `.env` next to the compose files:

```bash
cat > .env <<'EOF'
# Version tag that matches what `make build-prod` just produced.
VERSION=0.2.0

# Public HTTP port — what users hit in the browser.
# Front this with Caddy / Nginx / Traefik for TLS.
LIBRETA_HTTP_PORT=8080
EOF
```

> **Do not commit `.env`** — it's already in `.gitignore`.

---

## 5. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

That brings up three containers:

| Service         | Image                           | Port (host)            | Purpose                                        |
| --------------- | ------------------------------- | ---------------------- | ---------------------------------------------- |
| `api`           | `libreta-api:${VERSION}`        | 8092 (debug only)      | FastAPI backend, git source manager            |
| `frontend-prod` | `libreta-frontend:${VERSION}`   | `${LIBRETA_HTTP_PORT}` | Nginx serving the SPA + reverse-proxy to `api` |
| `drawio`        | `jgraph/drawio:latest`          | 8093                   | Diagram editor sidecar                         |

Smoke-test:

```bash
curl -sf http://localhost:${LIBRETA_HTTP_PORT:-8080}/  | head -1
curl -sf http://localhost:${LIBRETA_HTTP_PORT:-8080}/api/v1/info
```

You should see the SPA's `index.html` and a JSON `info` payload.

---

## 6. Add your wiki git source (via the Admin UI)

Open `http://<your-host>:${LIBRETA_HTTP_PORT}` in a browser, then navigate to
**`/-/admin`**.

### 6a. Add an SSH key (private repos only)

If your wiki repo is private:

1. On **Admin → SSH Keys**, click **Add key**.
2. Paste the **private key** PEM (e.g. `cat ~/.ssh/id_ed25519`).
3. Give it a label and save. The fingerprint is shown for verification.

The key is stored inside the `libreta-data` Docker volume at
`/var/lib/libreta/ssh_keys/`. It never touches the project source tree.

### 6b. Add a Git Source

1. On **Admin → Git Sources**, click **Add source**.
2. Fill in:

   | Field           | Example                              |
   | --------------- | ------------------------------------ |
   | ID (slug)       | `my-wiki`                            |
   | Label           | `My Wiki`                            |
   | Remote URL      | `git@github.com:you/wiki-private.git`|
   | Branch          | `main`                               |
   | Sync interval   | `15` (minutes)                       |
   | SSH key         | select the key you added in 6a       |

3. Click **Add source**. Libreta immediately begins cloning in the background.
   The sidebar shows a grey dot while cloning; it turns green once synced.

The wiki pages appear in the sidebar as soon as the clone finishes. Creating
or editing a page commits to the local clone and pushes to the remote
asynchronously — you don't wait for the push.

---

## 7. Front with TLS (Caddy)

The repo ships a ready-to-use Caddy overlay (`docker-compose.caddy.yml` +
`Caddyfile.example`) that runs Caddy as a sidecar container, terminates TLS
with Let's Encrypt, and proxies to the frontend nginx. This is the
recommended production setup — no separate Caddy install on the host.

### 7a. Configure

```bash
cp Caddyfile.example Caddyfile
# Edit: replace `wiki.example.com` with your domain and `you@example.com`
# with an address you read (used for ACME expiry notices).
$EDITOR Caddyfile
```

Make sure:

- The domain's A/AAAA record points at this host.
- Ports **80** and **443** are open on the firewall (and **443/udp** if you
  want HTTP/3).
- Nothing else is bound to those ports on the host.

### 7b. Start with the overlay

```bash
VERSION=$(cat VERSION) docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    -f docker-compose.caddy.yml \
    up -d
```

The overlay:

- Drops the public port from `frontend-prod` (only Caddy is reachable from
  outside).
- Adds a `caddy` container that mounts `./Caddyfile` read-only.
- Persists the issued certificate + ACME account in the `caddy-data` named
  volume so restarts don't re-issue.

Caddy obtains the certificate on the first HTTPS request to your domain.
Watch progress with:

```bash
docker compose logs -f caddy
```

### 7c. Renewals and reloads

Renewal is automatic (Caddy checks twice daily). To apply a Caddyfile edit
without restarting:

```bash
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### 7d. Using a different reverse proxy

If you already run Nginx or Traefik on the host, skip the Caddy overlay
and bring up only `docker-compose.yml` + `docker-compose.prod.yml`. Point
your existing proxy at `localhost:${LIBRETA_HTTP_PORT}` (default `8080`).

---

## 8. Backups

> See [`BACKUP.md`](./BACKUP.md) for the full backup & restore guide
> (single-page restore, lost-volume recovery, lost-host recovery,
> verification, scheduling). The summary below is the tl;dr.

The entire state of Libreta lives in **one Docker named volume**: `libreta_libreta-data`
(Docker Compose prefixes the volume name with the project name, which defaults
to the directory name — `/opt/libreta` → project `libreta`).

```bash
# Verify the volume name first
docker volume ls | grep libreta-data

# Back up to a tar file (adjust the volume name if different)
docker run --rm \
  -v libreta_libreta-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/libreta-data-$(date +%Y%m%d).tar.gz -C /data .
```

That archive contains:

- `/data/repos/<source-id>/` — the local git working trees (including `.git/`)
- `/data/ssh_keys/` — SSH private key material
- `/data/meta/_meta/` — sources.json, watched.json

The local clone *is* the backup for the wiki content, because it is a full git
repo. If you lose the volume but still have the remote, just re-add the source
in the Admin UI — Libreta will re-clone.

If you use the Caddy overlay, also back up the `libreta_caddy-data` volume — it
holds the issued certificate and ACME account key. Without it, Caddy will
re-issue on restore (rate-limited by Let's Encrypt).

### Restoring a backup into an existing instance

Use this when you have a running Libreta (local dev, staging, another
production host) and you want to restore a snapshot from a different
instance — for migration testing, disaster-recovery rehearsal, or
duplicating a setup.

The target must already have the `libreta_libreta-data` volume and the stack
running at least once (the volume is auto-created by `docker compose up`).

```bash
# On the target host — stop the stack so the volume isn't in use
cd /opt/libreta
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Extract the backup into the existing volume (overwrites what's there)
docker run --rm \
  -v libreta_libreta-data:/data \
  -v /path/to/backups:/backup:ro \
  alpine sh -c 'rm -rf /data/* /data/.[!.]* /data/..?* && cd /data && tar xzf /backup/libreta-data-YYYYMMDD.tar.gz'

# Bring the stack back up — the API detects the restored sources and
# begins syncing each repo
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> **SSH key caveat**: the backup includes private SSH keys. If the target
> host is less trusted than the source (e.g., a personal laptop vs. a
> production VM), rotate the keys after the test.

If you use the Caddy overlay and your target has a **different domain**,
skip the `caddy-data` restore — the certificate won't match. Let Caddy
issue a fresh one on the target.

---

## 8b. Cutting a release (maintainers)

The `VERSION` file is the single source of truth. The version bump and the
`CHANGELOG.md` update both happen in **one step** (`scripts/changelog.py`,
wrapped by `make changelog`), driven from [Conventional Commit](https://www.conventionalcommits.org)
subjects. `make release` no longer bumps the version — it ships whatever
`VERSION` currently says.

Run each step by hand, in order:

```bash
# 1. Commit your code changes (Conventional Commits — feat:, fix:, refactor!:, …).

# 2. Cut the version: bump VERSION + package.json, write the CHANGELOG section
#    from the commits since the last tag.
make changelog LEVEL=minor          # or patch | major
#    Review CHANGELOG.md; hand-edit the new section if a commit subject needs
#    polishing. (Dry run first: python scripts/changelog.py --level minor --dry-run)

# 3. Build images, commit VERSION+CHANGELOG, tag, deploy.
make release                        # commits "chore(release): vX.Y.Z", tags vX.Y.Z

# 4. Publish.
git push --follow-tags
```

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/). Only
user-facing commit types appear (`feat`→Added, `fix`→Fixed, `perf`/`refactor`→
Changed, `docs`→Documentation, breaking `!` →BREAKING CHANGES); `chore`, `test`,
`ci`, `build`, and `style` are dropped. A version with no user-facing commits
renders `_No user-facing changes._`. To reseed the whole file from tags:
`make changelog-backfill`.

---

## 9. Upgrades

```bash
cd /opt/libreta
git fetch --tags
git checkout v0.3.0          # whatever the new release tag is
make build-prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`up -d` recreates only the containers whose image changed. The `libreta-data`
volume is untouched.

If a release introduces a content-repo migration, the release notes will say
so explicitly and ship a migration script under `scripts/`.

---

## 10. Operational notes

- **Logs**: `docker compose logs -f api`. The API logs sync events, push
  successes, and push errors at INFO/WARNING level.
- **Sync errors**: visible in the sidebar (orange dot) and in the Admin page
  under each source. Fix the underlying issue (bad SSH key, remote down) and
  click **Sync** to retry immediately.
- **Healthchecks**: `/api/v1/healthz` returns 200 when the API is ready.
- **Resource limits**: the default stack has no limits. On a small host,
  consider `mem_limit: 512m` on `api`.

---

## 11. Tearing it down

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Add `-v` to also remove the named volumes:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
# ★ This deletes all cloned repos and SSH keys — make sure remote copies exist.
```

---

## Troubleshooting

**Sidebar shows orange dot / "Sync error"**: check the Admin page for the
error message. Common causes:
- Wrong SSH key (key not added to the remote's allowed keys).
- Incorrect remote URL (typo, HTTPS URL used instead of SSH for a private
  repo).
- Remote unreachable from the server.

Fix the cause, then click **Sync** or wait for the next periodic sync.

**Clone never finishes**: run `docker compose logs api` and look for the source
id. The clone is done in a FastAPI background task — if the container restarted
mid-clone the working tree may be partial. Delete the partial clone directory
from inside the volume and re-add the source:

```bash
docker run --rm -v libreta-data:/data alpine \
  rm -rf /data/repos/<source-id>
```

Then re-add the source in the Admin UI.

**Pages appear in git but not in the sidebar**: the tree is read from
`pages/` inside the cloned repo. Ensure your pages are in a `pages/`
subdirectory in the repo root, and end with `.md`.

**`502 Bad Gateway`**: the API container isn't healthy yet.
`docker compose logs api` for the cause.
