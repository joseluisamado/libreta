# Libreta — task runner
#
# Most targets are thin wrappers over `uv` (backend) or `pnpm` (frontend) plus
# `docker compose`. Run `make help` for the menu.

.DEFAULT_GOAL := help
.PHONY: help \
        install install-backend install-frontend \
        dev dev-backend dev-frontend dev-stack \
        check check-backend check-frontend \
        format format-backend format-frontend \
        lint lint-backend lint-frontend \
        typecheck typecheck-backend typecheck-frontend \
        test test-backend test-frontend \
        build build-frontend \
        up up-dev rebuild rebuild-dev down logs ps \
        clean clean-backend clean-frontend \
        import-dokuwiki import-dokuwiki-dry \
        import-apple-notes import-apple-notes-dry \
        compute-tags compute-tags-dry \
        version version-bump version-set sync-version \
        changelog changelog-backfill \
        build-prod build-prod-frontend release release-current _tag-and-deploy \
        setup-tls _tls-require-hostname _tls-precheck _tls-ensure-leaf

BACKEND   := backend
FRONTEND  := frontend

# Local, machine-specific overrides (DEPLOY_HOST, etc.). Gitignored; optional.
# The leading `-` makes a missing file a no-op. Values here win over the `?=`
# defaults below, but the command line still wins over everything
# (`make release DEPLOY_HOST=...`).
-include local.mk

# Single source of truth for the project version. Release targets bump it
# and propagate to backend/pyproject.toml and frontend/package.json.
VERSION := $(shell cat VERSION 2>/dev/null)

# SSH target for `make release` image deployment. Override on the command
# line if needed: `make release LEVEL=patch DEPLOY_HOST=user@homelab`.
DEPLOY_HOST ?= user@homelab

# Directory on DEPLOY_HOST that holds the prod compose files + .env. The deploy
# step runs `docker compose up -d` there to recreate containers from the image
# just loaded (otherwise the host keeps running the previous container).
DEPLOY_PATH ?= /home/user

# Hostname for the LAN HTTPS cert that releases generate with mkcert (e.g.
# wiki.lan). Must match the URL clients use
# (https://$(TLS_HOSTNAME):$(LIBRETA_HTTPS_PORT)/). Empty by default — set it in
# local.mk or on the command line (`make release TLS_HOSTNAME=wiki.lan`) to opt
# into HTTPS. When unset, releases deploy plain HTTP and skip the TLS steps.
TLS_HOSTNAME ?=

# Host port Caddy serves HTTPS on. Defaults to 8091 — the same port the plain
# frontend used — so enabling TLS doesn't change the URL's port. Must match the
# port in Caddyfile.mkcert's site address and LIBRETA_HTTPS_PORT in the overlay.
LIBRETA_HTTPS_PORT ?= 8091

# Compose invocation: dev stacks layer docker-compose.dev.yml on top of the
# base file so the api service gets a source bind-mount and uvicorn --reload.
# docker-compose.dev.local.yml is an optional, untracked, per-developer overlay
# (machine-specific paths); include it only when it exists.
LOCAL_OVERLAY := $(wildcard docker-compose.dev.local.yml)
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml $(if $(LOCAL_OVERLAY),-f $(LOCAL_OVERLAY),) --profile dev

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} \
	      /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---------- install ----------

install: install-backend install-frontend ## Install backend + frontend dependencies

install-backend: ## uv sync
	cd $(BACKEND) && uv sync

install-frontend: ## pnpm install
	cd $(FRONTEND) && pnpm install

# ---------- dev ----------

dev: ## Run the dev stack via docker compose (api + frontend + drawio, with hot-reload)
	$(COMPOSE_DEV) up

dev-backend: ## Run only the backend with reload (host port 8092, no docker)
	cd $(BACKEND) && LIBRETA_META_DIR=../data/meta uv run uvicorn libreta.main:app --reload --host 0.0.0.0 --port 8092

dev-frontend: ## Run only the frontend Vite dev server (host port 8091, no docker)
	cd $(FRONTEND) && pnpm dev

dev-stack: dev ## Alias for `dev`

# ---------- pre-flight checks ----------

check: check-backend check-frontend ## Run all pre-flight checks (format + lint + types + tests)

check-backend: format-backend lint-backend typecheck-backend test-backend ## Backend pre-flight (per CLAUDE.md §3.3)

check-frontend: lint-frontend typecheck-frontend test-frontend ## Frontend pre-flight (per CLAUDE.md §4.3)

# ---------- format ----------

format: format-backend format-frontend ## Format backend + frontend

format-backend:
	cd $(BACKEND) && uv run ruff format .

format-frontend:
	cd $(FRONTEND) && pnpm format

# ---------- lint ----------

lint: lint-backend lint-frontend ## Lint backend + frontend

lint-backend:
	cd $(BACKEND) && uv run ruff check . --fix

lint-frontend:
	cd $(FRONTEND) && pnpm lint

# ---------- typecheck ----------

typecheck: typecheck-backend typecheck-frontend ## Type-check backend + frontend

typecheck-backend:
	cd $(BACKEND) && uv run mypy src

typecheck-frontend:
	cd $(FRONTEND) && pnpm typecheck

# ---------- test ----------

test: test-backend test-frontend ## Run all tests

test-backend:
	cd $(BACKEND) && uv run pytest

test-frontend:
	cd $(FRONTEND) && pnpm test

# ---------- build ----------

build: build-frontend ## Build production artifacts

build-frontend:
	cd $(FRONTEND) && pnpm build

# ---------- docker compose lifecycle ----------

up: ## Start the prod-style stack (no frontend dev container)
	docker compose up -d

up-dev: ## Start the dev stack, detached
	$(COMPOSE_DEV) up -d

rebuild: ## Rebuild images and start the prod-style stack, detached
	docker compose up -d --build

rebuild-dev: ## Rebuild images and start the dev stack, detached (run this after changing deps)
	$(COMPOSE_DEV) up -d --build

down: ## Stop the stack
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

ps: ## Show running services
	docker compose ps

# ---------- clean ----------

clean: clean-backend clean-frontend ## Remove caches and build outputs

clean-backend:
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -type d -name __pycache__ -exec rm -rf {} +

clean-frontend:
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/dist $(FRONTEND)/.vite

# ---------- import ----------

import-dokuwiki: ## Import a DokuWiki installation into pages/ (override SOURCE=...)
	cd $(BACKEND) && uv run python ../scripts/import_dokuwiki.py $(if $(SOURCE),--source $(SOURCE))

import-dokuwiki-dry: ## Dry-run the DokuWiki importer (override SOURCE=...)
	cd $(BACKEND) && uv run python ../scripts/import_dokuwiki.py --dry-run $(if $(SOURCE),--source $(SOURCE))

import-apple-notes: ## Import Apple Notes into REPO=<git working tree> [DEST=apple-notes]
	@test -n "$(REPO)" || (echo "error: pass REPO=/path/to/wiki-clone" >&2; exit 1)
	cd $(BACKEND) && uv run python ../scripts/import_apple_notes.py \
		--repo $(REPO) $(if $(DEST),--dest $(DEST)) $(if $(ACCOUNT),--account "$(ACCOUNT)") $(if $(FOLDER),--folder "$(FOLDER)")

import-apple-notes-dry: ## Dry-run Apple Notes import
	@test -n "$(REPO)" || (echo "error: pass REPO=/path/to/wiki-clone" >&2; exit 1)
	cd $(BACKEND) && uv run python ../scripts/import_apple_notes.py \
		--repo $(REPO) --dry-run $(if $(DEST),--dest $(DEST)) $(if $(ACCOUNT),--account "$(ACCOUNT)") $(if $(FOLDER),--folder "$(FOLDER)")

compute-tags: ## Compute frontmatter tags for untagged pages in REPO=<git source clone>
	@test -n "$(REPO)" || (echo "error: pass REPO=/path/to/source-clone" >&2; exit 1)
	cd $(BACKEND) && uv run python ../scripts/compute_tags.py --repo $(REPO) $(if $(FORCE),--force)

compute-tags-dry: ## Dry-run tag computation (REPO=<git source clone>, no files written)
	@test -n "$(REPO)" || (echo "error: pass REPO=/path/to/source-clone" >&2; exit 1)
	cd $(BACKEND) && uv run python ../scripts/compute_tags.py --repo $(REPO) --dry-run $(if $(FORCE),--force)

# ---------- versioning + release ----------

version: ## Print the current project version
	@cd $(BACKEND) && uv run python ../scripts/sync_version.py --print

sync-version: ## Propagate the VERSION file into pyproject.toml + package.json
	cd $(BACKEND) && uv run python ../scripts/sync_version.py

version-bump: ## Bump the VERSION (LEVEL=patch|minor|major) and propagate
	@if [ -z "$(LEVEL)" ]; then echo "usage: make version-bump LEVEL=patch|minor|major" && exit 2; fi
	cd $(BACKEND) && uv run python ../scripts/sync_version.py --bump $(LEVEL)

version-set: ## Set the VERSION (NEW=X.Y.Z) and propagate
	@if [ -z "$(NEW)" ]; then echo "usage: make version-set NEW=1.2.3" && exit 2; fi
	cd $(BACKEND) && uv run python ../scripts/sync_version.py --set $(NEW)

build-prod: build-prod-frontend ## Build prod images tagged :VERSION and :latest (no bump)
	@echo "→ building libreta-api:$(VERSION)"
	docker build -f $(BACKEND)/Dockerfile -t libreta-api:$(VERSION) -t libreta-api:latest .
	@echo "→ images:"
	@docker images libreta-api --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})"
	@docker images libreta-frontend --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})"

build-prod-frontend: ## Build the frontend static bundle into a runnable image
	@echo "→ building libreta-frontend:$(VERSION)"
	docker build -f $(FRONTEND)/Dockerfile.prod -t libreta-frontend:$(VERSION) -t libreta-frontend:latest $(FRONTEND)

changelog: ## Bump VERSION + write CHANGELOG from commits, without releasing (prompts, or LEVEL=)
	cd $(BACKEND) && uv run python ../scripts/changelog.py $(if $(LEVEL),--level $(LEVEL),)

changelog-backfill: ## Reseed CHANGELOG.md from every git tag (one-off)
	cd $(BACKEND) && uv run python ../scripts/changelog.py --backfill

# One-command release. Run it after committing your code changes; it drives the
# whole cut:
#   1. abort if there are no commits since the last tag
#   2. prompt for the bump LEVEL, then write VERSION + CHANGELOG
#      (pass LEVEL=patch|minor|major to skip the prompt, e.g. CI)
#   3. build the prod images — if the build fails, revert VERSION/CHANGELOG
#   4. commit VERSION+CHANGELOG, tag vX.Y.Z, deploy to DEPLOY_HOST
# Then publish manually:  git push --follow-tags
release: ## Cut a release: check commits → prompt LEVEL → build → commit+tag+deploy
	@# Fail fast on TLS prerequisites BEFORE any irreversible work (build, version
	@# bump, commit). When TLS_HOSTNAME is set, the local mkcert CA must exist.
	@if [ -n "$(TLS_HOSTNAME)" ]; then $(MAKE) _tls-precheck; fi
	@CL="cd $(BACKEND) && uv run python ../scripts/changelog.py"; \
	echo "→ checking for unreleased commits"; \
	if ! sh -c "$$CL --check"; then exit 0; fi; \
	echo "→ cutting version"; \
	sh -c "$$CL $(if $(LEVEL),--level $(LEVEL),)" || { echo "release aborted"; exit 1; }; \
	new=$$(cat VERSION); \
	echo "→ building prod images for v$$new"; \
	if ! $(MAKE) build-prod; then \
	  echo "✗ build failed — reverting VERSION + CHANGELOG"; \
	  sh -c "$$CL --revert"; \
	  exit 1; \
	fi; \
	echo "→ committing VERSION + CHANGELOG for v$$new"; \
	git add VERSION CHANGELOG.md frontend/package.json; \
	git commit -m "chore(release): v$$new" >/dev/null; \
	$(MAKE) _tag-and-deploy

# Blindly (re)release whatever VERSION currently says: build, tag, deploy. No
# commit check, no bump, no changelog, no commit — for re-shipping a version or
# deploying to a fresh host.
release-current: ## Re-release the CURRENT VERSION as-is: build, tag, deploy (no bump/commit)
	@if [ -n "$(TLS_HOSTNAME)" ]; then $(MAKE) _tls-precheck; fi
	$(MAKE) build-prod
	$(MAKE) _tag-and-deploy

setup-tls: _tls-require-hostname _tls-ensure-leaf ## Provision the LAN HTTPS cert on DEPLOY_HOST (set TLS_HOSTNAME), no deploy
	@echo "TLS material is in place on $(DEPLOY_HOST). A release will serve https://$(TLS_HOSTNAME):$(LIBRETA_HTTPS_PORT)/."

# HTTPS is opt-in: it requires TLS_HOSTNAME. Targets that touch certs depend on
# this so they fail loudly (not silently with a wrong hostname) when it's unset.
_tls-require-hostname:
	@if [ -z "$(TLS_HOSTNAME)" ]; then \
	  echo "✗ TLS_HOSTNAME is not set. Set it to your LAN hostname to enable HTTPS,"; \
	  echo "  e.g. in local.mk:   TLS_HOSTNAME := wiki.lan"; \
	  echo "  or on the command line:   make setup-tls TLS_HOSTNAME=wiki.lan"; \
	  exit 1; \
	fi

# Verify this machine has mkcert AND its CA installed. The leaf must be signed by
# the CA that clients already trust, so the CA living here (not on the host) is
# what lets the host be rebuilt/replaced without re-trusting on clients. Stops
# with instructions rather than guessing.
_tls-precheck: _tls-require-hostname
	@if ! command -v mkcert >/dev/null; then \
	  echo "✗ mkcert not found on this machine. To enable HTTPS for $(TLS_HOSTNAME):"; \
	  echo "    brew install mkcert      # (or your platform's package)"; \
	  echo "    mkcert -install          # trust the CA in your system + browsers"; \
	  echo "  then re-run. See docs/site/claude-desktop.md."; \
	  exit 1; \
	fi
	@if [ ! -f "$$(mkcert -CAROOT)/rootCA.pem" ]; then \
	  echo "✗ mkcert CA not generated yet. Run once on this machine:"; \
	  echo "    mkcert -install"; \
	  echo "  then re-run. (This is the CA your clients will trust.)"; \
	  exit 1; \
	fi

# Ensure DEPLOY_HOST has a valid leaf for TLS_HOSTNAME. Regenerate + install when
# the cert is missing, expired (within 24h), or doesn't cover the hostname.
# Always (re)installs the Caddyfile + overlay so the host config matches the repo.
_tls-ensure-leaf: _tls-precheck
	@echo "→ checking $(DEPLOY_HOST) for a valid leaf cert for $(TLS_HOSTNAME)"
	@need=1; \
	if ssh $(DEPLOY_HOST) "test -f $(DEPLOY_PATH)/certs/cert.pem" 2>/dev/null; then \
	  if ssh $(DEPLOY_HOST) "openssl x509 -in $(DEPLOY_PATH)/certs/cert.pem -checkend 86400 -noout && openssl x509 -in $(DEPLOY_PATH)/certs/cert.pem -noout -checkhost $(TLS_HOSTNAME)" >/dev/null 2>&1; then \
	    echo "  ✓ valid cert already present — keeping it"; need=0; \
	  else \
	    echo "  cert present but expired or wrong hostname — regenerating"; \
	  fi; \
	else \
	  echo "  no cert on host — generating"; \
	fi; \
	if [ "$$need" = 1 ]; then \
	  tmp=$$(mktemp -d); \
	  mkcert -cert-file "$$tmp/cert.pem" -key-file "$$tmp/key.pem" "$(TLS_HOSTNAME)"; \
	  ssh $(DEPLOY_HOST) "mkdir -p $(DEPLOY_PATH)/certs"; \
	  scp -q "$$tmp/cert.pem" "$$tmp/key.pem" "$(DEPLOY_HOST):$(DEPLOY_PATH)/certs/"; \
	  rm -rf "$$tmp"; \
	  echo "  ✓ leaf generated (your CA) and installed"; \
	fi
	@# Fill the Caddyfile template's tokens from TLS_HOSTNAME / LIBRETA_HTTPS_PORT
	@# and push it; keeps host config in sync with the repo every time, cheaply.
	@sed -e 's/__TLS_HOSTNAME__/$(TLS_HOSTNAME)/g' -e 's/__HTTPS_PORT__/$(LIBRETA_HTTPS_PORT)/g' Caddyfile.mkcert.example \
	  | ssh $(DEPLOY_HOST) "cat > $(DEPLOY_PATH)/Caddyfile.mkcert"
	@scp -q docker-compose.mkcert.yml "$(DEPLOY_HOST):$(DEPLOY_PATH)/"

# Shared tail: tag the current VERSION, ship the images to DEPLOY_HOST, and
# recreate the running containers. When TLS_HOSTNAME is set, ensure the cert is
# present and deploy with the mkcert + Caddy overlay (HTTPS); otherwise deploy
# plain HTTP as before.
_tag-and-deploy:
	@if [ -n "$(TLS_HOSTNAME)" ]; then $(MAKE) _tls-ensure-leaf; fi
	@new=$$(cat VERSION); \
	echo "→ tagging git as v$$new"; \
	git tag -a "v$$new" -m "release v$$new" || echo "  (skipped: already tagged?)"
	@new=$$(cat VERSION); \
	echo "→ deploying images to $(DEPLOY_HOST) via ssh"; \
	docker save libreta-api:$$new libreta-api:latest libreta-frontend:$$new libreta-frontend:latest \
	  | ssh $(DEPLOY_HOST) docker load
	@if [ -n "$(TLS_HOSTNAME)" ]; then \
	  echo "→ recreating containers on $(DEPLOY_HOST) ($(DEPLOY_PATH)) with HTTPS overlay"; \
	  ssh $(DEPLOY_HOST) "cd $(DEPLOY_PATH) && LIBRETA_HTTPS_PORT=$(LIBRETA_HTTPS_PORT) docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.mkcert.yml up -d"; \
	else \
	  echo "→ recreating containers on $(DEPLOY_HOST) ($(DEPLOY_PATH))"; \
	  ssh $(DEPLOY_HOST) "cd $(DEPLOY_PATH) && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"; \
	fi
	@echo ""
	@if [ -n "$(TLS_HOSTNAME)" ]; then \
	  echo "Release v$$(cat VERSION) deployed and live: https://$(TLS_HOSTNAME):$(LIBRETA_HTTPS_PORT)/"; \
	  echo "MCP endpoint: https://$(TLS_HOSTNAME):$(LIBRETA_HTTPS_PORT)/mcp"; \
	else \
	  echo "Release v$$(cat VERSION) deployed and live on $(DEPLOY_HOST)."; \
	fi
	@echo "Run: git push --follow-tags"
