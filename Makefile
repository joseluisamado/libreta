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
        build-prod build-prod-frontend release release-current _tag-and-deploy

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

# Compose invocation: dev stacks layer docker-compose.dev.yml on top of the
# base file so the api service gets a source bind-mount and uvicorn --reload.
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml  -f docker-compose.dev.local.yml --profile dev

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

rebuild-dev: ## Rebuild images and start the dev stack, detached
	$(COMPOSE_DEV) up -d --build

sync-frontend-deps: ## Sync host pnpm changes into the running dev frontend container
	docker exec -e CI=true libreta-frontend-1 pnpm install
	$(COMPOSE_DEV) restart frontend

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
	$(MAKE) build-prod
	$(MAKE) _tag-and-deploy

# Shared tail: tag the current VERSION and ship the images to DEPLOY_HOST.
_tag-and-deploy:
	@new=$$(cat VERSION); \
	echo "→ tagging git as v$$new"; \
	git tag -a "v$$new" -m "release v$$new" || echo "  (skipped: already tagged?)"
	@new=$$(cat VERSION); \
	echo "→ deploying images to $(DEPLOY_HOST) via ssh"; \
	docker save libreta-api:$$new libreta-api:latest libreta-frontend:$$new libreta-frontend:latest \
	  | ssh $(DEPLOY_HOST) docker load
	@echo ""
	@echo "Release v$$(cat VERSION) built locally and loaded into docker on $(DEPLOY_HOST)."
	@echo "Run: git push --follow-tags"
