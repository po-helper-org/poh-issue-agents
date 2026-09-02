# Layer A operator commands. Run `make setup` once, then up → dry-run → go-live.
.PHONY: help setup up up-local up-full logs ps dry-run backfill-one go-live dry-again down test consolidate deploy-check deploy-check-stack

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
# Адрес Temporal сторожу выкладки. Makefile не грузит .env целиком (см. REPO
# выше — там та же ручная выемка), а без адреса сторож ушёл бы на localhost:7233
# и на внешнем кластере молча докладывал бы «недоступен».
#
# Пустое значение НЕ подставляется: `TEMPORAL_ADDRESS=` хуже отсутствия строки —
# `os.environ.get(..., "localhost:7233")` вернёт пустую строку, а не дефолт, и
# соединение уйдёт по пустому адресу (та же ловушка, что у MODEL_CLASSIFY,
# описанная в docs/DEPLOY-DOKPLOY.md).
TEMPORAL := $(strip $(shell grep -E '^TEMPORAL_ADDRESS=' .env 2>/dev/null | cut -d= -f2-))
GUARD := $(if $(TEMPORAL),TEMPORAL_ADDRESS=$(TEMPORAL) )$(PY) scripts/deploy_guard.py

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
	@echo "make deploy-check how many live workflows a rebuild would hit (ARGS=--replay for details)"
	@echo "make deploy-check-stack  same check from inside the worker (full stack: 7233 not published)"
	@echo "make down         stop everything"

setup:
	bash scripts/setup.sh

# Незакрытые прогоны считаются ПЕРЕД пересборкой: воркфлоу живут неделями, и
# выкладка, меняющая порядок активностей, их убивает (#263). Гейт, который
# останавливает, — эта цель: код возврата 1, когда под ударом есть прогоны.
# Цели сборки ниже зовут тот же сторож с `--warn-only`: цифра печатается,
# сборка не блокируется — решать выкладывать или нет должен человек.
deploy-check:
	$(GUARD) $(ARGS)

# Та же проверка ИЗНУТРИ контейнера. Нужна для конфигурации full: там 7233
# намеренно не публикуется наружу (`expose`, а не `ports` в
# docker-compose.full.yml), и с хоста сторожу до Temporal не дотянуться —
# он честно отвечал бы «недоступен», приучая не читать его вывод.
# Тот же приём, что у scripts/diag.py: запускать там, где живёт сервис.
deploy-check-stack:
	docker compose $(FULL) exec -T worker python scripts/deploy_guard.py $(ARGS)

up:
	-@$(GUARD) --warn-only
	docker compose up --build -d $(CORE)

# Локальная разработка: полный стек со встроенным Temporal.
# .env для Temporal править не нужно — адрес/namespace заданы в файле.
up-local:
	-@$(GUARD) --warn-only
	docker compose $(LOCAL) up --build -d
	@echo "Temporal UI: http://localhost:8080"

# Полный прод-стек со встроенным Temporal (обычно поднимается через Dokploy;
# цель нужна для локальной проверки прод-конфига). Требует POSTGRES_PASSWORD.
# Сторожа выкладки здесь НЕТ намеренно: 7233 в этой конфигурации наружу не
# публикуется, и проверка с хоста всегда отвечала бы «недоступен». Считать
# прогоны перед пересборкой этого стека — `make deploy-check-stack`.
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
