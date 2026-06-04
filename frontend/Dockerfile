# Dev image for the Vite frontend.
#
# Shares its dependency-install step with the prod build (Dockerfile.prod):
# both do `pnpm install --frozen-lockfile` against the same lockfile, so the
# node_modules artifact is produced the same way in dev and prod. The dev
# overlay (docker-compose.dev.yml) bind-mounts only the *source* (src/,
# public/, index.html, configs) on top of this image — never node_modules —
# so host edits hot-reload while the image's installed deps stay
# authoritative. A lockfile change therefore requires an image rebuild
# (`make rebuild-dev`), exactly like the backend.
#
# Mirror of backend/Dockerfile's role: build-time install = the artifact;
# bind-mount = convenience for editing source.

FROM node:22-alpine

RUN corepack enable

WORKDIR /app

# Install deps as their own layer so source edits don't bust the cache.
# --frozen-lockfile (no fallback): if the lockfile is out of sync with
# package.json the build fails loudly rather than silently drifting.
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

# Bake a full copy too, so the image runs standalone (no bind-mount needed,
# e.g. CI). The dev overlay shadows src/public/etc. with the host tree.
COPY . .

EXPOSE 5173
# `pnpm dev` already binds --host 0.0.0.0 (see package.json), so the server is
# reachable from outside the container.
CMD ["pnpm", "dev"]
