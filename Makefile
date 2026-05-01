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
        up up-dev down logs ps \
        clean clean-backend clean-frontend

BACKEND   := backend
FRONTEND  := frontend

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

dev: ## Run the dev stack via docker compose (api + frontend + drawio)
	docker compose --profile dev up

dev-backend: ## Run only the backend with reload (no docker)
	cd $(BACKEND) && LIBRETA_CONTENT_DIR=../data/content uv run uvicorn libreta.main:app --reload --host 0.0.0.0 --port 8080

dev-frontend: ## Run only the frontend Vite dev server (no docker)
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
	docker compose --profile dev up -d

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
