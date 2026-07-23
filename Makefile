# Layer A operator commands. Run `make setup` once, then up → dry-run → go-live.
.PHONY: help setup up up-local up-full logs ps dry-run backfill-one go-live dry-again down test consolidate

# Три конфигурации compose:
#   main (docker-compose.yml)       — только приложение, внешний Temporal из .env
#   local (docker-compose.local.yml) — полный стек для локальной разработки
#   full (docker-compose.full.yml)   — полный стек для прода со встроенным Temporal
# Layer A — только worker (webhook нужен позже, для Layer B).
CORE  := worker
LOCAL := -f docker-compose.local.yml
FULL  := -f docker-compose.full.yml
REPO := $(shell grep -E '^GITHUB_REPOSITORY=' .env 2>/dev/null | cut -d= -f2-)
PY   := .venv/bin/python

help:
	@echo "make setup        interactive onboarding (preflight, venv, .env)"
	@echo "make up           main: worker only, external Temporal from .env"
	@echo "make up-local     local: full stack + local Temporal (offline dev)"
	@echo "make up-full      full: full stack + bundled Temporal (prod-style)"
	@echo "make logs         follow worker logs"
	@echo "make dry-run      triage ALL open issues (DRY_RUN — no mutations)"
	@echo "make backfill-one issue=N   triage a single issue (smoke test)"
	@echo "make go-live      turn DRY_RUN off, restart worker, run for real"
	@echo "make consolidate  cluster open backlog & open PR (DRY_RUN-guarded)"
	@echo "make down         stop everything"

setup:
	bash scripts/setup.sh

up:
	docker compose up --build -d $(CORE)

# Локальная разработка: полный стек со встроенным Temporal.
# .env для Temporal править не нужно — адрес/namespace заданы в файле.
up-local:
	docker compose $(LOCAL) up --build -d
	@echo "Temporal UI: http://localhost:8080"

# Полный прод-стек со встроенным Temporal (обычно поднимается через Dokploy;
# цель нужна для локальной проверки прод-конфига). Требует POSTGRES_PASSWORD.
up-full:
	docker compose $(FULL) up --build -d

logs:
	docker compose logs -f worker

ps:
	docker compose ps

dry-run:
	@test -n "$(REPO)" || { echo "no GITHUB_REPOSITORY in .env — run 'make setup'"; exit 1; }
	GITHUB_REPOSITORY=$(REPO) $(PY) scripts/backfill.py

backfill-one:
	@test -n "$(issue)" || { echo "usage: make backfill-one issue=<N>"; exit 1; }
	GITHUB_REPOSITORY=$(REPO) $(PY) scripts/backfill.py --issue $(issue)

# Flip DRY_RUN off in .env, reload the worker, then run for real.
go-live:
	@grep -q '^DRY_RUN=$$' .env && { echo "DRY_RUN already off (live)."; } || true
	@printf "\033[31mThis will post real comments/labels and may CLOSE issues on %s.\033[0m\n" "$(REPO)"
	@read -r -p "Type 'live' to proceed: " ans; [ "$$ans" = "live" ] || { echo "aborted."; exit 1; }
	@grep -v '^DRY_RUN=' .env > .env.tmp && echo 'DRY_RUN=' >> .env.tmp && mv .env.tmp .env && chmod 600 .env
	@echo "DRY_RUN off. Reloading worker..."
	docker compose up -d worker
	@sleep 3
	GITHUB_REPOSITORY=$(REPO) $(PY) scripts/backfill.py

down:
	docker compose $(LOCAL) down

consolidate:
	@test -n "$(REPO)" || { echo "no GITHUB_REPOSITORY in .env"; exit 1; }
	GITHUB_REPOSITORY=$(REPO) $(PY) scripts/consolidate.py

test:
	.venv/bin/pytest -q
