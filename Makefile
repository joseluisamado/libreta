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
        build-prod build-prod-frontend release release-current

BACKEND   := backend
FRONTEND  := frontend

# Single source of truth for the project version. Release targets bump it
# and propagate to backend/pyproject.toml and frontend/package.json.
VERSION := $(shell cat VERSION 2>/dev/null)

# SSH target for `make release` image deployment. Override on the command
# line if needed: `make release LEVEL=patch DEPLOY_HOST=user@homelab`.
DEPLOY_HOST := example.com

# Compose invocation: dev stacks layer docker-compose.dev.yml on top of the
# base file so the api service gets a source bind-mount and uvicorn --reload.
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev

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
	cd $(BACKEND) && LIBRETA_CONTENT_DIR=../data/content uv run uvicorn libreta.main:app --reload --host 0.0.0.0 --port 8092

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

compute-tags: ## Compute frontmatter tags for any untagged pages
	cd $(BACKEND) && uv run python ../scripts/compute_tags.py $(if $(FORCE),--force)

compute-tags-dry: ## Dry-run tag computation (no files written)
	cd $(BACKEND) && uv run python ../scripts/compute_tags.py --dry-run $(if $(FORCE),--force)

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

release: ## Bump VERSION (LEVEL=patch|minor|major), build images, tag git, deploy to DEPLOY_HOST
	@if [ -z "$(LEVEL)" ]; then echo "usage: make release LEVEL=patch|minor|major" && exit 2; fi
	$(MAKE) version-bump LEVEL=$(LEVEL)
	$(MAKE) release-current

release-current: ## Release the CURRENT VERSION as-is (no bump): build images, tag git, deploy to DEPLOY_HOST
	$(MAKE) build-prod
	@new=$$(cat VERSION); \
	echo "→ tagging git as v$$new"; \
	git tag -a "v$$new" -m "release v$$new" || echo "  (skipped: already tagged?)"
	@new=$$(cat VERSION); \
	echo "→ deploying images to $(DEPLOY_HOST) via ssh"; \
	docker save libreta-api:$$new libreta-api:latest libreta-frontend:$$new libreta-frontend:latest \
	  | ssh $(DEPLOY_HOST) docker load
	@echo ""
	@echo "Release v$$(cat VERSION) built locally and loaded into docker on $(DEPLOY_HOST)."
	@echo "Run: git push --tags"
