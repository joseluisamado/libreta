# DEPLOY.md — bootstrapping a Libreta from scratch

This guide takes you from "empty server" to a running Libreta on your own
hardware. It covers a single-host Docker Compose deployment — the simplest
shape that makes sense for v0.x, where Libreta is a single-user wiki.

> The prerequisites assume Linux (Ubuntu / Debian / Fedora) but anything that
> runs Docker will do. Adjust paths and package names accordingly.

---

## 1. Prerequisites

- A host with at least 1 vCPU, 1 GB RAM, 5 GB free disk for the wiki itself
  (more if you'll attach lots of media).
- Docker Engine 24+ and the `docker compose` plugin.
- Git ≥ 2.40.
- A domain name pointed at the host (optional but recommended; without it
  you can serve over plain HTTP on a LAN).
- Outbound HTTPS for pulling base images on first deploy.

Check:

```bash
docker --version
docker compose version
git --version
```

---

## 2. Get the source

```bash
git clone https://github.com/<you>/libreta.git /opt/libreta
cd /opt/libreta
```

Pin to a released version rather than `main` for production:

```bash
git checkout v0.1.0          # whatever the latest released tag is
cat VERSION                  # sanity-check that the project's VERSION matches
```

---

## 3. Initialise the content repository

The wiki content lives in `./data/content/` as its own git repository,
**separate from the project repo** (this is enforced by the project's
`.gitignore`).

```bash
mkdir -p ./data/content/pages
git -C ./data/content init
git -C ./data/content commit --allow-empty -m "init libreta content"

# A starter home page so you can verify the install:
cat > ./data/content/pages/index.md <<'EOF'
---
title: Home
---

# Welcome to Libreta

This is the home page. Edit me!
EOF
git -C ./data/content add pages/index.md
git -C ./data/content commit -m "seed home page"
```

If you have an existing wiki to migrate (DokuWiki, OtterWiki, etc.) see the
import scripts under `scripts/` — `make import-dokuwiki SOURCE=/path/to/data`
is the supported one today.

If you want the content repo to live elsewhere on disk, set
`LIBRETA_CONTENT_DIR` in the environment (see step 5).

---

## 4. Build the production images

Libreta currently builds images locally; there is no public registry yet.

```bash
make build-prod
```

This produces:

```
libreta-api:0.1.0       libreta-api:latest
libreta-frontend:0.1.0  libreta-frontend:latest
```

The `:latest` aliases are convenient for compose; the version-pinned tags are
what you should reference in production so a careless `make build-prod` on
top doesn't replace the running version mid-day.

---

## 5. Configure the runtime

Create `.env` next to the compose files:

```bash
cat > .env <<'EOF'
# Which version's images to run. Defaults to "latest" if unset, but pinning
# is strongly recommended in prod.
VERSION=0.1.0

# Public HTTP port — what users hit in the browser. Front this with a real
# reverse proxy (Caddy / Nginx / Traefik) for TLS; nginx in the frontend
# image only speaks HTTP.
LIBRETA_HTTP_PORT=8080
EOF
```

> **Do not commit `.env`** — it's already in `.gitignore`.

---

## 6. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

That brings up three containers:

| Service        | Image                          | Port (host)           | Purpose                                |
|----------------|--------------------------------|-----------------------|----------------------------------------|
| `api`          | `libreta-api:${VERSION}`       | 8092 (debug only)     | FastAPI backend                        |
| `frontend-prod`| `libreta-frontend:${VERSION}`  | `${LIBRETA_HTTP_PORT}`| Nginx serving the SPA + reverse-proxying `/api/` to `api` |
| `drawio`       | `jgraph/drawio:latest`         | 8093                  | Diagram editor sidecar (optional, used in M4) |

Smoke-test:

```bash
curl -sf http://localhost:${LIBRETA_HTTP_PORT:-8080}/  | head -1
curl -sf http://localhost:${LIBRETA_HTTP_PORT:-8080}/api/v1/info
```

You should see the SPA's `index.html` and a JSON `info` payload respectively.

---

## 7. Front with TLS (Caddy example)

The simplest reliable path on a public host is to put **Caddy** in front of
the Libreta nginx. Caddy obtains and renews Let's Encrypt certificates
automatically.

`/etc/caddy/Caddyfile`:

```
wiki.example.com {
    reverse_proxy localhost:8080
}
```

Open ports 80 and 443; close everything else. Caddy will issue the cert on
first request. If you can't run on the standard ports (e.g. behind another
proxy), tell Caddy to listen elsewhere and adjust your upstream.

---

## 8. Backups

The wiki content is a normal git repository. Backup is `git push`:

```bash
git -C /opt/libreta/data/content remote add origin git@github.com:<you>/<wiki-private>.git
git -C /opt/libreta/data/content push -u origin main
```

Schedule a periodic push (cron, systemd timer, or a `post-receive`-style
hook). Restoring is `git clone` of the same repo back into `data/content/`.

The SQLite indexes that ship in M3+ live under `data/index/` and are
regenerable from the filesystem at any time, so they are **not** part of
the backup contract — `make rebuild-index` in v0.x.

---

## 9. Upgrades

```bash
cd /opt/libreta
git fetch --tags
git checkout v0.2.0          # whatever the new release tag is
make build-prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`up -d` recreates only the containers whose image changed.

If a release introduces a content-repo migration, the release notes will say
so explicitly and ship a migration script under `scripts/`.

---

## 10. Operational notes

- **Logs**: `docker compose logs -f api frontend-prod`. Structured log
  shipping is not built-in; run something like `vector` / `promtail` / your
  cloud's log agent if you want centralisation.
- **Healthchecks**: the API's `/api/v1/healthz` returns 200 when ready;
  hook it into your monitoring of choice.
- **Resource limits**: the default Compose stack runs without limits. On a
  small host, consider `mem_limit: 512m` on `api` and `cpu_count: 1`.
- **Local-network-only**: omit step 7, set `LIBRETA_HTTP_PORT=80` (needs
  root or Docker rootless), and reach the wiki at `http://wiki.lan/`.

---

## 11. Tearing it down

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Add `-v` to also remove the named volumes (`pnpm-store`). `data/content/` is
a bind mount — `down -v` will not touch it. To wipe the whole installation:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
rm -rf /opt/libreta/data/content   # ★ destroys your wiki — make sure backups are good
```

---

## Troubleshooting

**`pull access denied for libreta-api`**: you didn't run `make build-prod`
on this host, or the version in `.env` doesn't match a tag that exists.
`docker images libreta-api` should list whatever tags are available.

**`502 Bad Gateway` from nginx**: the API container isn't healthy yet.
`docker compose logs api` — the typical cause is `data/content/` doesn't
exist or isn't a git repo.

**Pages render but assets 404**: the asset URL probably points outside
`data/content/`. Asset paths must be relative; the renderer rewrites them
through `/api/v1/assets/pages/...`. Check the page's markdown source.

**Content edits don't appear after `git pull` in `data/content`**: the API
caches nothing; just reload the page. If a file appears in `git status` but
not in the wiki, ensure the filename ends in `.md` and lives under
`pages/`.
