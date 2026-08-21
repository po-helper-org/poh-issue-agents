# Итог

## Кодовая база poh-issue-agents

**Репозиторий**: 323 файла, 80k строк кода. Основные модули:
- `webhook/main.py` — единственная точка входа для GitHub вебхуков
- `worker/workflows.py` — Temporal воркфлоу (IssueLifecycle, IssueAnalysis, IssueBft, IssueEstimation)
- `shared/` — общие типы, контракты, lifecycle модель
- `scripts/` — smoke-тесты (Temporal, estimation)
- `.claude/skills/` — навыки агента

**Entry points**: `webhook/main.py::github_webhook`, `worker/workflows.py::IssueLifecycle::run`

## Жизненный цикл Issue — сегодня и завтра

**Реализованные фазы** (в `worker/workflows.py`):
1. `created` (triage) — классификация и триаж
2. `classified` (await_decision) — ожидание решения человека
3. `business-analysis` — цепочка FNR
4. `system-requirements` (handoff) — передача разработчику
5. `ready-for-dev` (await_build) — ожидание взятия в разработку
6. `pr-review` — ревью PR

**Фазы определены в модели** (`shared/lifecycle.py`), но не реализованы:
- `MERGED` — PR влит
- `TESTING` — выкатка на стенд
- `RELEASED` — попадание в прод

**Workflow останавливается на `pr-review`** — нет кода для фаз после слияния (#42).

## Вебхуки и внешние события

**Обрабатываемые события** (`webhook/main.py`):
- `issues.opened` → старт нового IssueLifecycle
- `issue_comment.created` → команды (`/analyze`, `/estimate`, `/bft`, `/bft-deep`)
- `issues.labeled` → `run:<command>` метки
- `/agent-event` → факты от внешних агентов (#38)

**НЕ обрабатываются**:
- `pull_request` события — не подписаны, фазы после мержа нет

## Контракт внешних агентов (H3 протокол)

**Endpoint**: `POST /agent-event` с HMAC-подписью (`X-Agent-Signature-256`)

**Payload** (`shared/agent_events.py`):
```python
{
    repo: str,
    agent: str,         # "pr-agent", "pr-closer", etc.
    phase: str,         # из lifecycle.TRANSITIONS
    status: str,        # STARTED | SUCCEEDED | FAILED | BLOCKED
    ref: str,           # branch, PR number, etc.
    root_issue: int?,   # явное указание Issue
    detail: str,        # дополнительный контекст
    revision: str?      # идемпотентность
}
```

**Корреляция с Issue** (по убыванию надёжности):
1. Явное поле `root_issue`
2. `Closes #N` в detail body
3. Конвенция ветки (`research/issue-N`, `bug/issue-N`)

**Почему HTTP, не Temporal**: `poh-pr-agents` не использует Temporal вообще — избегаем связности SDK, workflow IDs, сетевого доступа.

## poh-pr-agents — агент PR

**Назначение**: анализ PR (`/describe`, `/review`), chunking/mapreduce для больших PR

**Интеграция** (`poh-pr-agents/self-hosted/reliability/agent_event.py`):
- Отправляет события фазы `pr-review` со статусами `started`/`failed`
- Корреляция через `Closes #N` в теле PR
- Best-effort: никогда не роняет обработку PR при ошибке отправки

**Сопротивление сбоям**: circuit breaker, rate limiter, failover по пулу провайдеров (`gateway.py`)

## Временная модель Temporal

**IssueLifecycle** — один workflow на Issue (ID = `issue-<repo>-<n>`):
- Сигналы: `human_decision`, `user_comment`, `issue_closed`, `analyze_requested`, `agent_event`, `bft_requested`, `estimate_requested`
- Queries: `stage`, `phase`, `generation`, `awaiting`, `handles_agents`
- Continue-as-new при истории >800 событий

**Child workflows**: IssueAnalysis, IssueBft, IssueEstimation

## Мониторинг и верификация

**Sentry** (`shared/sentry_setup.py`):
- Теги: service/repo/issue/stage
- Ссылки на события публикуются комментариями в GitHub
- Фильтрует внешние сбои (RateLimitError, APITimeoutError) как `warning`
- Scrubs секреты из кадров стека

**Smoke-тесты**:
- `scripts/smoke_temporal.py` — Temporal коннект, namespace, queue roundtrip
- `scripts/estimate.py` — IssueEstimation workflow
- Ручной E2E через скрипты

**Чего нет**:
- Метрик, дашбордов
- Smoke-набора против живого стенда
- Автоматической проверки после выкатки
- Зафиксированного определения "система стабильна"

## Ручной деплой

**Сегодня**: Dokploy, docker compose, автодеплой не настроен
- Выкладка = правка `ISSUE_AGENT_CONTEXT` в `.env` + `docker compose build && up -d`
- События `deployment_status` в GitHub не приходят
- Отсутствует API для "отгрузить в прод"

## Воркспейс контура

**Репозитории**:
- `poh-issue-agents` (целевой)
- `poh-bft-writer` (50 связей)
- `poh-pr-agents` (10 связей)
- `poh-helper` (7 связей)
- `poh-memory-engine` (5 связей)
- `poh-cortex`, `poh-infra`, `poh-scheduller`, `poh-sprint-agents`

**НЕ найден**: `poh-sysreq-agent` (указан как precedent #70) — открытый вопрос

# Открытые вопросы

1. **poh-sysreq-agent (#70)**: упомянут как прецедент выноса агента в отдельный репозиторий, но отсутствует в воркспейсе. Где его код и как он интегрируется?

2. **Фазы MERGED → TESTING → RELEASED**: модель определена в `lifecycle.py`, но код обработки отсутствует. Какой агент отвечает за эти фазы? КакTemporal workflow должен продолжаться?

3. **Корреляция кросс-репозиторных релизов**: как Delivery-Agent будет определять порядок отгрузки при связях между репозиториями (#43)?

4. **Проверка стабильности**: что конкретно означает "система ведёт себя стабильно"? Как превратить HowToDemo из БФТ в исполняемый чек-лист?

5. **Откат docker compose выкладки**: как именно откатиться и как убедиться, что откат состоялся?

6. **GitHub Release vs GitHub Issues**: Delivery-Agent создаёт GitHub Release, но сегодня релизов нет. Какие метаданные нужны?

7. **Дочерние воркфлоу в Temporal (#73)**: ReleaseWorkflow объединяет несколько Issue — как это ложится на модель дочерних воркфлоу?

8. **CI порог покрытия 83%**: как Delivery-Agent будет подтверждать зелёный CI перед включением PR в релиз?

# Диалог

## Ход 1: Framework (get_overview)
**Инструмент**: `mcp__repowise__get_overview`
**Репозиторий**: poh-issue-agents
**Результат**: 323 файла, entry points в webhook/main.py и worker/workflows.py, workspace с 8 другими репо. Горячие точки: worker/activities.py, worker/workflows.py.

## Ход 2: Webhook events
**Инструмент**: `mcp__repowise__get_context` на webhook/main.py
**Результат**: Подтверждено — обрабатываются только `issues` и `issue_comment`. Никаких `pull_request` событий. Есть `/agent-event` эндпоинт для фактов от внешних агентов (#38).

## Ход 3: Workflow structure
**Инструмент**: `mcp__repowise__get_context` на worker/workflows.py
**Результат**: IssueLifecycle имеет фазы до `pr-review`. Каждая фаза — отдельный метод (`_phase_*`). Signals для агентских событий. Child workflows для аналитики/БФТ/оценки. Код после `pr-review` отсутствует.

## Ход 4: External agent contract
**Инструмент**: `mcp__repowise__get_context` на shared/agent_events.py
**Результат**: Контракт определён: POST /agent-event с подписью, корреляция по root_issue/Closes/branch convention. Почему HTTP — не втаскивать Temporal в соседние сервисы.

## Ход 5: Workspace check
**Инструмент**: `mcp__repowise__list_repos`
**Результат**: 9 репо в воркспейсе, но `poh-sysreq-agent` отсутствует. Открытый вопрос.

## Ход 6: poh-pr-agents overview
**Инструмент**: `mcp__repowise__get_overview` на poh-pr-agents
**Результат**: Python сервис для PR reliability. Entry point в self-hosted/reliability/app.py. 87 файлов.

## Ход 7: poh-pr-agents integration
**Инструмент**: `mcp__repowise__get_context` на poh-pr-agents/self-hosted/reliability/agent_event.py
**Результат**: poh-pr-agents отправляет события фазы `pr-review` в poh-issue-agents через тот же контракт. Корреляция через `Closes #N`. Best-effort отправка.

## Ход 8: Monitoring infrastructure
**Инструмент**: `mcp__repowise__get_context` на shared/sentry_setup.py и scripts/smoke_temporal.py
**Результат**: Sentry для сбоев с тегами и ссылками. Smoke-тесты для Temporal. Нет метрик, дашбордов, автоматической проверки выкладки.

## Ход 9: Lifecycle phases
**Инструмент**: `mcp__repowise__get_symbol` на repowise#9a8693ecf93c (lifecycle.py omission)
**Результат**: Полный путь фаз: CREATED → ... → PR_REVIEW → MERGED → TESTING → RELEASED. Боковые состояния: SPAM, DUPLICATE, ANSWERED, SKIPPED, ESCALATED, FAILED, CANCELLED. Модель определена, код для фаз после PR_REVIEW отсутствует.

## Ход 10: Awaiting states
**Инструмент**: `mcp__repowise__get_context` на shared/awaiting.py
**Результат**: Виды ожидания: HUMAN_DECISION, APPROVAL, TESTING, EXTERNAL_AGENT, FAILURE_RECOVERY с дефолтными сроками. KIND_BY_PHASE маппинг показывает TESTING фазу ожидает TESTING вид.

## Ход 11: Deployment search
**Инструмент**: `mcp__repowise__search_codebase` — deployment/docker/compose
**Результат**: Пусто — подтверждает ручной деплой без автоматизации в коде.

## Ход 12: Final synthesis
**Инструмент**: анализ полученных фактов
**Результат**: Собрана полная картина: вебхуки, воркфлоу, контракты, мониторинг,.lifecycle модель, внешние агенты. Выявлены разрывы: фазы после PR_REVIEW не реализованы, деплой ручной, проверка стабильности не определена.


---
session: rw-analysis-po-helper-org__poh-issue-agents-111
workspace: contour
turns: 16
started: 2026-08-21T10:52:27Z
finished: 2026-08-21T10:53:48Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `d54073370859` | 9 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 9 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "include": [
    "content"
  ]
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Primary Execution Flows\n\n- `worker/workflows.py::IssueLifecycle::run` (5 steps)\n\n- `webhook/main.py::github_webhook` (3 steps)\n\n- `worker/workflows.py::IssueAnalysis::run` (3 steps)\n\n- `webhook/main.py::agent_event` (3 steps)\n\n- `worker/github_client.py::dispatch_workflow` (6 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `tests/conftest.py` (0.0634)\n\n- `shared/workflow_types.py` (0.0442)\n\n- `worker/estimation.py` (0.0293)\n\n- `shared/__init__.py` (0.0190)\n\n- `worker/activities.py` (0.0170)\n\n- `tests/test_estimate_activities.py` (0.0155)\n\n- `tests/test_estimate_report.py` (0.0155)\n\n- `tests/test_estimation_compute.py` (0.0155)\n\n- `worker/github_client.py` (0.0125)\n\n- `shared/lifecycle.py` (0.0109)\n\n- `shared/workflow_ids.py` (0.0108)\n\n- `worker/worker.py` (0.0106)\n\n- `worker/workflows.py` (0.0099)\n\n- `shared/labels.py` (0.0095)\n\n- `worker/consolidation_activities.py` (0.0093)\n\n- `webhook/main.py` (0.0090)\n\n- `shared/agent_comment.py` (0.0089)\n\n- `shared/temporal_client.py` (0.0084)\n\n- `shared/commands.py` (0.0082)\n\n- `shared/bft.py` (0.0072)\n\n\n\n\n\n\n\n\n\n## Codebase health signals\n- **Hotspots:** 24 files are both high-churn and high-complexity\n- **Stable core:** 0 files unchanged in 90+ days\n- **Most changed (90d):** `worker/activities.py`, `worker/workflows.py`, `worker/worker.py`\n- **Oldest file:** `shared/__init__.py` (38 days)\n\n\n---\n\n*Built from the code's structure. It states what is there, not why it is that\nway. Add an API key and run `repowise generate` to have that written.*\n\n## Architecture map\n\n```mermaid\nflowchart LR\n  subgraph layer_application[\"Application\"]\n    direction TB\n    module_application[\"Application\"]\n  end\n  subgraph layer_config[\"Config\"]\n    direction TB\n    module_claude_skills[\".claude/skills\"]\n    module_claude_commands[\".claude/commands\"]\n  end\n  subgraph layer_utility[\"Utility\"]\n    direction TB\n    module_shared[\"shared\"]\n  end\n  subgraph layer_docs_tooling[\"Docs & Tooling\"]\n    direction TB\n    module_docs_tooling[\"Docs & Tooling\"]\n  end\n  subgraph layer_test[\"Test\"]\n    direction TB\n    module_test[\"Test\"]\n  end\n\n  module_application -->|\"39\"| module_shared\n  module_docs_tooling -->|\"14\"| module_shared\n```\n",
  "code_health": {
    "average_health": 8.33,
    "band": "healthy",
    "hotspot_health": 5.01,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 459,
    "file_count": 348,
    "distribution": {
      "total_files": 348,
      "total_nloc": 49462,
      "bands": {
        "healthy": {
          "files": 310,
          "nloc": 36736,
          "pct": 74.3
        },
        "warning": {
          "files": 34,
          "nloc": 7615,
          "pct": 15.4
        },
        "alert": {
          "files": 4,
          "nloc": 5111,
          "pct": 10.3
        }
      }
    }
  },
  "key_modules": [
    {
      "name": "Architecture Scripts",
      "path": ".claude/skills/architecture/scripts",
      "description": "`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascript | **Files:** 5 |…",
      "page_id": "module_page:.claude/skills/architecture/scripts",
      "section": "4",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Docs Tooling Scripts",
      "path": "scripts",
      "description": "`scripts`\n\n**Language:** python | **Files:** 8 | **Public symbols:** 49 / 51\n\n\nCovers the 8 source files in scripts. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:scripts",
      "section": "5",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Utility Shared",
      "path": "shared",
      "description": "`shared`\n\n**Language:** python | **Files:** 18 | **Public symbols:** 236 / 256\n\n\nCovers the 18 source files in shared. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:shared",
      "section": "6",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Application Webhook",
      "path": "webhook",
      "description": "`webhook`\n\n**Language:** python | **Files:** 1 | **Public symbols:** 9 / 21\n\n\nCovers the 1 source files in webhook. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:webhook",
      "section": "7",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Application Worker",
      "path": "worker",
      "description": "`worker`\n\n**Language:** python | **Files:** 9 | **Public symbols:** 190 / 294\n\n\nCovers the 9 source files in worker. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:worker",
      "section": "8",
      "parent_page_id": "repo_overview:poh-issue-agents"
    }
  ],
  "entry_points": [
    "webhook/main.py",
    ".claude/skills/brainstorming/scripts/server.cjs"
  ],
  "git_health": {
    "files_git_attributed": 351,
    "hotspot_count": 39,
    "avg_bus_factor": 0.6,
    "files_with_bus_factor_1": 110,
    "churn_trend": "increasing",
    "top_churn_modules": [
      ".claude/skills",
      "worker/activities.py",
      "worker/workflows.py",
      "README.md",
      "worker/worker.py"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 82,
        "percentage": 23.4
      },
      {
        "name": "kibarik",
        "files_owned": 69,
        "percentage": 19.7
      },
      {
        "name": "Claude",
        "files_owned": 6,
        "percentage": 1.7
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "tests",
      "size": 12
    },
    {
      "id": 1,
      "label": "tests (46)",
      "size": 12
    },
    {
      "id": 2,
      "label": "worker",
      "size": 8
    },
    {
      "id": 3,
      "label": "server",
      "size": 7
    },
    {
      "id": 4,
      "label": "external:~/threads",
      "size": 3
    },
    {
      "id": 5,
      "label": "tests (5)",
      "size": 3
    },
    {
      "id": 6,
      "label": "claude",
      "size": 1
    },
    {
      "id": 7,
      "label": "installed_skills",
      "size": 1
    },
    {
      "id": 8,
      "label": "commands",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands (1)",
      "size": 1
    }
  ],
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-issue-agents",
      "title": "Repository Overview: poh-issue-agents"
    },
    "total_pages": 252,
    "sections": [
      {
        "section": "1",
        "page_id": "onboarding:onboarding/key_concepts",
        "title": "Key Concepts",
        "page_type": "onboarding",
        "target_path": "onboarding/key_concepts"
      },
      {
        "section": "2",
        "page_id": "onboarding:onboarding/how_it_works",
        "title": "How It Works",
        "page_type": "onboarding",
        "target_path": "onboarding/how_it_works"
      },
      {
        "section": "3",
        "page_id": "onboarding:onboarding/active_landscape",
        "title": "Active Landscape",
        "page_type": "onboarding",
        "target_path": "onboarding/active_landscape"
      },
      {
        "section": "4",
        "page_id": "module_page:.claude/skills/architecture/scripts",
        "title": "Architecture Scripts",
        "page_type": "module_page",
        "target_path": ".claude/skills/architecture/scripts",
        "descendants": 5
      },
      {
        "section": "5",
        "page_id": "module_page:scripts",
        "title": "Docs Tooling Scripts",
        "page_type": "module_page",
        "target_path": "scripts",
        "descendants": 8
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 45
      },
      {
        "section": "7",
        "page_id": "module_page:webhook",
        "title": "Application Webhook",
        "page_type": "module_page",
        "target_path": "webhook",
        "descendants": 2
      },
      {
        "section": "8",
        "page_id": "module_page:worker",
        "title": "Application Worker",
        "page_type": "module_page",
        "target_path": "worker",
        "descendants": 102
      },
      {
        "section": "9",
        "page_id": "scc_page:scc-37580294ed84",
        "title": "Circular Dependency: Tests",
        "page_type": "scc_page",
        "target_path": "scc-37580294ed84"
      },
      {
        "section": "10",
        "page_id": "infra_page:.claude/skills/brainstorming/scripts/start-server.sh",
        "title": "Infrastructure: .claude/skills/brainstorming/scripts/start-server.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/brainstorming/scripts/start-server.sh"
      },
      {
        "section": "11",
        "page_id": "infra_page:.claude/skills/brainstorming/scripts/stop-server.sh",
        "title": "Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/brainstorming/scripts/stop-server.sh"
      },
      {
        "section": "12",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/review-package",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/review-package"
      },
      {
        "section": "13",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/sdd-workspace",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
      },
      {
        "section": "14",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/task-brief",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/task-brief",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/task-brief"
      },
      {
        "section": "15",
        "page_id": "infra_page:.claude/skills/systematic-debugging/find-polluter.sh",
        "title": "Infrastructure: .claude/skills/systematic-debugging/find-polluter.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/systematic-debugging/find-polluter.sh"
      },
      {
        "section": "16",
        "page_id": "infra_page:.claude/skills/technical-documentation/scripts/find_sql_queries.sh",
        "title": "Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
      },
      {
        "section": "17",
        "page_id": "infra_page:Makefile",
        "title": "Infrastructure: Makefile",
        "page_type": "infra_page",
        "target_path": "Makefile"
      },
      {
        "section": "18",
        "page_id": "infra_page:openhands/Dockerfile",
        "title": "Infrastructure: openhands/Dockerfile",
        "page_type": "infra_page",
        "target_path": "openhands/Dockerfile"
      },
      {
        "section": "19",
        "page_id": "symbol_spotlight:tests/conftest.py::ROOT",
        "title": "Symbol: tests.conftest.ROOT",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::ROOT"
      },
      {
        "section": "20",
        "page_id": "symbol_spotlight:tests/conftest.py::RULES_PATH",
        "title": "Symbol: tests.conftest.RULES_PATH",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::RULES_PATH"
      },
      {
        "section": "21",
        "page_id": "symbol_spotlight:tests/conftest.py::rules",
        "title": "Symbol: tests.conftest.rules",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::rules"
      },
      {
        "section": "22",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::FakeGitHub",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::FakeGitHub"
      },
      {
        "section": "23",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::__init__",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.__init__",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::__init__"
      },
      {
        "section": "24",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_label",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_label",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_label"
      },
      {
        "section": "25",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_reaction",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_reaction",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_reaction"
      },
      {
        "section": "26",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::branch_exists",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.branch_exists",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::branch_exists"
      },
      {
        "section": "27",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::comment",
        "title": "Symbol: tests.test_estimate_activities.comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::comment"
      },
      {
        "section": "28",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::fake",
        "title": "Symbol: tests.test_estimate_activities.fake",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::fake"
      },
      {
        "section": "29",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_file",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_file",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_file"
      },
      {
        "section": "30",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_issue",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_issue",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_issue"
      },
      {
        "section": "31",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::list_comments",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.list_comments",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::list_comments"
      },
      {
        "section": "32",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::post_comment",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.post_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::post_comment"
      },
      {
        "section": "33",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment",
        "title": "Symbol: tests.test_estimate_activities.test_ack_puts_eyes_on_the_command_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment"
      },
      {
        "section": "34",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread",
        "title": "Symbol: tests.test_estimate_activities.test_bot_comments_and_commands_are_excluded_from_the_thread",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread"
      },
      {
        "section": "35",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch",
        "title": "Symbol: tests.test_estimate_activities.test_bug_branch_is_used_when_there_is_no_research_branch",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch"
      },
      {
        "section": "36",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown",
        "title": "Symbol: tests.test_estimate_activities.test_compute_activity_returns_rendered_markdown",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown"
      },
      {
        "section": "37",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_context_carries_title_body_and_labels",
        "title": "Symbol: tests.test_estimate_activities.test_context_carries_title_body_and_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_context_carries_title_body_and_labels"
      },
      {
        "section": "38",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts",
        "title": "Symbol: tests.test_estimate_activities.test_error_reports_the_stage_and_reacts",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts"
      },
      {
        "section": "39",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_no_branch_means_no_artifacts_and_is_not_an_error",
        "title": "Symbol: tests.test_estimate_activities.test_no_branch_means_no_artifacts_and_is_not_an_error",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_no_branch_means_no_artifacts_and_is_not_an_error"
      },
      {
        "section": "40",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_oversized_artifact_is_truncated",
        "title": "Symbol: tests.test_estimate_activities.test_oversized_artifact_is_truncated",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_oversized_artifact_is_truncated"
      }
    ],
    "sections_total": 89,
    "sections_truncated": true
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 54
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 139
      },
      {
        "name": "Utility",
        "description": "",
        "file_count": 19
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 39
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 97
      }
    ],
    "tour_available": true,
    "tour_step_count": 12,
    "layer_order": [
      "Application",
      "Config",
      "Utility",
      "Docs & Tooling"
    ]
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-issue-agents",
      "page_id": "repo_overview:poh-issue-agents",
      "target_path": "poh-issue-agents",
      "section": null
    },
    {
      "order": 2,
      "slot": "key_concepts",
      "title": "Key Concepts",
      "page_id": "onboarding:onboarding/key_concepts",
      "target_path": "onboarding/key_concepts",
      "section": "1"
    },
    {
      "order": 3,
      "slot": "how_it_works",
      "title": "How It Works",
      "page_id": "onboarding:onboarding/how_it_works",
      "target_path": "onboarding/how_it_works",
      "section": "2"
    },
    {
      "order": 4,
      "slot": "active_landscape",
      "title": "Active Landscape",
      "page_id": "onboarding:onboarding/active_landscape",
      "target_path": "onboarding/active_landscape",
      "section": "3"
    }
  ],
  "reading_order_hint": "Canonical onboarding sequence — read these page_ids in order via get_context/get_symbol to understand the repo the way a new contributor would.",
  "guided_tour": [
    {
      "order": 1,
      "title": "README.md",
      "kind": "overview",
      "reason": "Start here for the end-to-end picture before diving into the code.",
      "target_path": "README.md",
      "page_id": "repo_overview:README.md",
      "section": null
    },
    {
      "order": 2,
      "title": "main.py",
      "kind": "code",
      "reason": "An entry point — execution and imports fan out from here.",
      "target_path": "webhook/main.py",
      "page_id": "file_page:webhook/main.py",
      "section": "7.2"
    },
    {
      "order": 3,
      "title": "workflow_types.py",
      "kind": "code",
      "reason": "Directly used by the entry points above; a core collaborator.",
      "target_path": "shared/workflow_types.py",
      "page_id": "file_page:shared/workflow_types.py",
      "section": "6.18"
    },
    {
      "order": 9,
      "title": "backfill.py",
      "kind": "code",
      "reason": "The Docs & Tooling layer's anchor — its most depended-on file.",
      "target_path": "scripts/backfill.py",
      "page_id": "file_page:scripts/backfill.py",
      "section": "5.2"
    },
    {
      "order": 10,
      "title": "estimation-rules.toml",
      "kind": "code",
      "reason": "The Config layer's anchor — its most depended-on file.",
      "target_path": "config/estimation-rules.toml",
      "page_id": "file_page:config/estimation-rules.toml",
      "section": null
    },
    {
      "order": 11,
      "title": "activities.py",
      "kind": "code",
      "reason": "A top churn hotspot — one of the most frequently changed files in the repo; worth understanding early.",
      "target_path": "worker/activities.py",
      "page_id": "file_page:worker/activities.py",
      "section": "8.2"
    },
    {
      "order": 12,
      "title": "conftest.py",
      "kind": "code",
      "reason": "The test suite — how the system's behavior is verified.",
      "target_path": "tests/conftest.py",
      "page_id": "file_page:tests/conftest.py",
      "section": null
    }
  ],
  "guided_tour_hint": "Topology-ordered walk of the codebase: read these page_ids in order — entry points first, then the files they import, with infrastructure last. Each step builds on the previous.",
  "workspace": {
    "workspace_root": "/workspaces/contour",
    "default_repo": "poh-issue-agents",
    "other_repos": [
      "poh-bft-writer",
      "poh-cortex",
      "poh-helper",
      "poh-infra",
      "poh-memory-engine",
      "poh-pr-agents",
      "poh-scheduller",
      "poh-sprint-agents"
    ],
    "hint": "This repo is part of a workspace. Other repos: poh-bft-writer, poh-cortex, poh-helper, poh-infra, poh-memory-engine, poh-pr-agents, poh-scheduller, poh-sprint-agents. Use repo='<alias>' to query another repo, or repo='all' for workspace-wide results.",
    "cross_repo": {
      "co_change_count": 76,
      "package_dep_count": 0,
      "top_connections": [
        {
          "repos": [
            "poh-bft-writer",
            "poh-issue-agents"
          ],
          "edge_count": 50
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-pr-agents"
          ],
          "edge_count": 10
        },
        {
          "repos": [
            "poh-helper",
            "poh-issue-agents"
          ],
          "edge_count": 7
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-memory-engine"
          ],
          "edge_count": 5
        },
        {
          "repos": [
            "poh-bft-writer",
            "poh-memory-engine"
          ],
          "edge_count": 2
        }
      ]
    },
    "contract_links": {
      "total_contracts": 23,
      "total_links": 0,
      "by_type": {
        "http": 12,
        "data": 11
      }
    }
  },
  "tool_guide": {
    "first_call": "get_answer for any how/where/why question; trust confidence=high directly (it is content-grounded).",
    "reading_code": "get_context(include=[\"skeleton\"]) for a whole file verified, or just Read it. get_symbol only for an id a response already gave you — never file-by-signature.",
    "recipes": [
      "get_answer low confidence → Read best_guesses[0].file",
      "get_context hotspot: true → get_risk before editing",
      "get_context decision_records → get_why(targets=[...]) for rationale",
      "PR review → get_risk(targets, changed_files) and read directive first",
      "search_codebase(query) auto-routes: identifier → symbol hits (pipe symbol_id into get_symbol), path → files (get_context), prose → wiki search. Force with mode=symbol|path|concept|hybrid."
    ],
    "reread_triggers": "Only re-read source on bounds: approximate, stale_warning in _meta, or a search hit whose sources are [fts] only (keyword match, no semantic agreement)."
  },
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "4b14af6bd067"
      ],
      "tokens": 1960,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "omission_marker": "[repowise#4b14af6bd067: 53 lines omitted (~1960 tokens); restore: repowise expand 4b14af6bd067]"
}

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "webhook/main.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "webhook/main.py": {
      "target": "webhook/main.py",
      "type": "file",
      "parent_page": {
        "title": "Application Webhook",
        "target_path": "webhook",
        "section": "7"
      },
      "docs": {
        "title": "File: webhook/main.py",
        "summary": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:"
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 4,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 2046,
        "full_tokens": 6855,
        "pct_of_full": 29.8,
        "bodies_kept": [
          "_client_disconnect",
          "_log_effective_config",
          "verify_agent_signature",
          "_report_orphan",
          "_lifecycle_args_for"
        ],
        "text": "\"\"\"\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и\n                               через signal-with-start поднимает цикл-владелец\n                               состояния, `/estimate` — IssueEstimation,\n                               `/bft` и `/bft-deep` — IssueBft (хвост команды\n                               уезжает в прогон как замечания/уточнения); любой\n                               другой комментарий — сигнал уже идущему workflow\n                               (используется циклом уточнений)\n- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и\n                               команда в комментарии (run:analyze ->\n                               IssueAnalysis, run:estimate -> IssueEstimation,\n                               run:bft / run:bft-deep -> IssueBft);\n                               точки решения человека (research-me / bug-me /\n                               build-me) идут через signal-with-start: воркфлоу\n                               триажа может не существовать, тогда он\n                               поднимается тем же вызовом\n\nНичего из бизнес-логики здесь нет — это чистый транспортный слой.\n\"\"\"\nimport hashlib\nimport hmac\nimport logging\nimport os\nfrom fastapi import FastAPI, Header, HTTPException, Request, Response\nfrom starlette.requests import ClientDisconnect\nfrom temporalio.client import Client\nfrom temporalio.exceptions import WorkflowAlreadyStartedError\nfrom shared import sentry_setup\nfrom shared.commands import (\n    ... 10 lines (36-45)\nfrom shared.agent_comment import is_agent_comment\nfrom shared.agent_launcher import request_analysis, request_bft, request_estimate\nfrom shared.authz import may_trigger, trigger_allowlist\nfrom shared.labels import parse_root_issue\nfrom shared.repos import allowed_specs, is_allowed\nfrom shared.temporal_client import connect_temporal\nfrom shared.workflow_ids import (\n    ... 9 lines (53-61)\n_log = logging.getLogger(\"webhook\")\n\napp = FastAPI()\n\n\n@app.exception_handler(ClientDisconnect)\nasync def _client_disconnect(request: Request, exc: ClientDisconnect):\n    \"\"\"Отправитель ушёл, не дослав тело.\n\n    Отвечать 500 некому: соединения уже нет, а событие уезжает в Sentry как\n    сбой вебхука (ISSUE-AGENT-8, пять штук за один разрыв связи с прокси).\n    Доставка не потеряна — GitHub ретраит её сам, так что здесь нечего чинить\n    и не о чем будить. 204 закрывает запрос тихо и оставляет след в логе.\n    \"\"\"\n    _log.info(\"отправитель разорвал соединение до конца тела (%s) — доставка будет повторена\",\n              request.headers.get(\"x-github-delivery\", \"без id\"))\n    return Response(status_code=204)\n\n\nHUMAN_DECISION_LABELS = {\"research-me\", \"bug-me\", \"build-me\", \"not-duplicate\", \"confirm-duplicate\"}\n\n\ndef _log_effective_config() -> None:\n    \"\"\"Один раз на старте — какой конфиг реально действует.\n\n    Секреты не логируются: только режим авторизации. Полная картина —\n    `scripts/diag.py` внутри контейнера; эта строка нужна, чтобы после\n    передеплоя не гадать, подхватились ли переменные.\n    \"\"\"\n    specs = [s for s in allowed_specs() if s.strip()]\n    if os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\"):\n        auth = \"PAT (перебивает GitHub App)\" if os.environ.get(\"GITHUB_APP_ID\") else \"PAT\"\n    elif os.environ.get(\"GITHUB_APP_ID\"):\n        auth = \"GitHub App\"\n    else:\n        auth = \"НЕ НАСТРОЕНА\"\n    _log.info(\n        \"effective config: ISSUE_AGENT_REPOS=%s auth=%s temporal=%s/%s\",\n        specs or [\"(пусто — любой репозиторий)\"], auth,\n        os.environ.get(\"TEMPORAL_ADDRESS\", \"localhost:7233\"),\n        os.environ.get(\"TEMPORAL_NAMESPACE\", \"default\"),\n    )\n\n\n_log_effective_config()\n\n_temporal_client: Client | None = None\n\n\nasync def get_temporal_client() -> Client:\n    ... 4 lines (112-115)\n\n\ndef verify_signature(body: bytes, signature_header: str | None) -> None:\n    ... 6 lines (119-124)\n\n\n# Формат ID живёт в shared/workflow_ids.py: его же собирают скрипты прямого\n# запуска, и разъехавшись, они потеряли бы идемпотентность.\nworkflow_id_for = issue_workflow_id\nestimate_workflow_id_for = estimate_workflow_id\n\n\ndef _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None:\n    \"\"\"Сквозной ключ цепочки в Temporal: `RootIssue` и `Repo`.\n... 20 lines (135-154)\n\n\ndef _issue_input(payload: dict, *, interactive: bool):\n    \"\"\"`IssueInput` из полезной нагрузки вебхука.\n... 16 lines (159-174)\n\n\ndef _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:\n    \"\"\"Гейт на запуск дорогой стадии + аудит того, кто её запустил.\n... 21 lines (179-199)\n\n\nasync def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None,\n                                  repo: str, specs: list[str]) -> None:\n    \"\"\"След в Temporal UI для события, отброшенного по allowlist.\n... 33 lines (205-237)\n\n\nasync def _ack_comment_seen(client, repo: str, issue_number: int,\n                            comment_id: int) -> None:\n    \"\"\"Реакция `eyes` на принятый комментарий — отдельным прогоном.\n... 23 lines (243-265)\n\n\ndef verify_agent_signature(body: bytes, signature_header: str | None) -> None:\n    \"\"\"Подпись входящего события агента — своим секретом, не гитхабовским.\n\n    Сигнал, двигающий фазу Issue, не может приходить анонимно. Секрет отдельный:\n    у соседних сервисов свои права, и утечка одного не должна открывать второй\n    канал. Без переменной эндпоинт закрыт (503, а не «пропускаем всех») —\n    молчаливо открытый приём фазовых событий хуже, чем выключенный.\n    \"\"\"\n    secret = os.environ.get(\"AGENT_EVENT_SECRET\", \"\")\n    if not secret:\n        raise HTTPException(status_code=503, detail=\"AGENT_EVENT_SECRET не задан\")\n    if not signature_header or not signature_header.startswith(\"sha256=\"):\n        raise HTTPException(status_code=401, detail=\"Missing signature\")\n    expected = \"sha256=\" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()\n    if not hmac.compare_digest(expected, signature_header):\n        raise HTTPException(status_code=401, detail=\"Invalid signature\")\n\n\nasync def _report_orphan(client, event, reason: str) -> None:\n    \"\"\"Событие, которое не удалось связать с Issue, не пропадает молча.\n\n    Опознать работу не получилось — значит, ни одна фаза не сдвинется, и\n    единственное, что мы можем, — сделать это видимым. Тишина здесь означала бы\n    ровно тот обрыв трассировки, ради которого задача и ставилась.\n    \"\"\"\n    from shared.workflow_types import OrphanEventInput\n\n    try:\n        await client.start_workflow(\n            \"OrphanAgentEvent\",\n            OrphanEventInput(repo=event.repo, agent=event.agent, phase=event.phase,\n                             status=event.status, ref=event.ref, reason=reason,\n                             detail=event.detail[:2000]),\n            ... 8 lines (301-308)\n\n\n@app.post(\"/agent-event\")\nasync def agent_event(\n    request: Request,\n    x_agent_signature_256: str | None = Header(None),\n):\n    \"\"\"Приём фактов от внешних агентов контура (#38).\n... 37 lines (317-353)\n\n\ndef _lifecycle_args_for(event, issue_number: int) -> list:\n    \"\"\"Аргументы старта цикла для события агента.\n\n    Цикла может не быть: Issue завели до установки App, либо его прогон уже\n    закрылся по сроку. Поднимать его обычным путём нельзя — триаж пошёл бы по\n    пустым заголовку и телу, задал бы человеку уточняющий вопрос и потратил\n    вызовы модели на задачу, которая давно в разработке.\n\n    Поэтому цикл поднимается СРАЗУ в той фазе, о которой доложил агент, через\n    тот же снимок состояния, что используется для continue-as-new (#36).\n    Триажу тут делать нечего: работа уже в PR.\n    \"\"\"\n    from shared.agent_events import target_phase\n    from shared.workflow_types import IssueInput, LifecycleState\n\n    ... 10 lines (371-380)\n\n\n@app.post(\"/webhook\")\nasync def github_webhook(\n    request: Request,\n    x_github_event: str = Header(...),\n    x_hub_signature_256: str | None = Header(None),\n    x_github_delivery: str | None = Header(None),\n):\n    ... 223 lines (390-612)\n",
        "verified": true
      },
      "episodes": 4
    }
  },
  "_meta": {
    "timing_ms": 76.25,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 3 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/workflows.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/workflows.py": {
      "target": "worker/workflows.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/workflows.py",
        "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 14,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 3102,
        "full_tokens": 28921,
        "pct_of_full": 10.7,
        "bodies_kept": [],
        "text": "\"\"\"\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\"\"\"\n\nimport asyncio\nfrom datetime import datetime, timedelta, timezone\n\nfrom temporalio import workflow\nfrom temporalio.common import RetryPolicy\nfrom temporalio.exceptions import WorkflowAlreadyStartedError\nfrom temporalio.workflow import ParentClosePolicy\n\nwith workflow.unsafe.imports_passed_through():\n    from shared import bft, labels, lifecycle\n    from shared.commands import ANALYZE, BFT, BFT_DEEP, ESTIMATE\n    from shared.workflow_ids import (\n        analysis_workflow_id,\n        bft_workflow_id,\n        estimate_workflow_id,\n    )\n    from shared import agent_events, awaiting as awaiting_mod\n    from shared.agent_events import AgentEvent\n    from shared.awaiting import Awaiting\n    from shared.workflow_types import (\n        AnalyzeInput,\n        BftRequest,\n        ClassificationResult,\n        CommentAckInput,\n        Deadlines,\n        EstimateRequest,\n        EstimateResult,\n        IssueInput,\n        LifecycleState,\n        OrphanEventInput,\n        UserComment,\n        WebhookAuditInput,\n    )\n\n    import activities\n\n# Прогон БФТ, запущенный самим триажем, а не человеком. Отличается тем, что не\n# трогает метки команды: помечать `run:bft` нечего — команды не было, а метка\n# вернулась бы вебхуком как новая.\nBFT_TRIAGE = \"triage\"\n\nMAX_CLARIFICATION_ROUNDS = 2\n... 7 lines (61-67)\nMAX_ANALYSIS_CLARIFY_ROUNDS = 2\n\n# Запрос на прогон аналитики, доставленный в общую очередь сигналов. Та же\n# схема, что у реплики человека (`UserComment`): одна очередь, разные виды\n# событий, и обработчик фазы решает, что с ними делать.\nAGENT_ANALYZE = \"__agent__:analyze\"\n\n# Issue закрыт на GitHub. Тот же приём: сигнал будит парковку, а решение\n# принимает цикл — иначе обработчику каждой фазы пришлось бы знать про закрытие.\nCLOSED = \"__closed__\"\n\n# Сколько ключей событий помнить ради идемпотентности. Цикл живёт месяцами, а\n# событий по одному Issue — десятки: список без потолка рос бы вместе с\n# историей, ровно тем объёмом, который continue-as-new и призван обрывать.\nSEEN_EVENTS_KEPT = 50\n\n# Порог длины истории для continue-as-new. Ниже потолка, на котором уже\n# спотыкалась консолидация (~990 событий): реплей должен укладываться в\n# workflow-task timeout с запасом, а не впритык.\nHISTORY_EVENT_THRESHOLD = 800\n\n\ndef _failure_reason(e: BaseException) -> str:\n    \"\"\"\"ExcType: message\" из ПЕРВОПРИЧИНЫ для тегов/группировки Sentry.\n... 16 lines (92-107)\n\n\nasync def _run_staged_analysis(analyze: AnalyzeInput) -> bool:\n    \"\"\"Пер-стадийный прогон FNR — общий для обоих входов в аналитику.\n... 92 lines (112-203)\n\n\nasync def _agents_off(repo: str, issue_number: int, what: str) -> bool:\n    \"\"\"R4: человек забрал Issue себе — прогон не стартует.\n... 20 lines (208-227)\n\n\nasync def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:\n    \"\"\"Обратный ход меток команды — один вызов на все терминальные ветки.\n... 11 lines (232-242)\n\n\n@workflow.defn(name=\"WebhookAudit\")\nclass WebhookAudit:\n    \"\"\"Надгробие для доставки, отброшенной по конфигу.\n... 11 lines (248-258)\n    async def run(self, audit: WebhookAuditInput) -> str:\n        ... 6 lines (260-265)\n\n\n@workflow.defn(name=\"OrphanAgentEvent\")\nclass OrphanAgentEvent:\n    \"\"\"Надгробие для события агента, не связанного ни с одним Issue.\n... 9 lines (271-279)\n    async def run(self, orphan: OrphanEventInput) -> str:\n        ... 6 lines (281-286)\n\n\n@workflow.defn(name=\"CommentAck\")\nclass CommentAck:\n    \"\"\"Подтверждение приёма комментария — отдельным прогоном, до всего остального.\n... 11 lines (292-302)\n    async def run(self, ack: CommentAckInput) -> None:\n        ... 6 lines (304-309)\n\n\n@workflow.defn(name=\"IssueLifecycle\")\nclass IssueLifecycle:\n    def __init__(self) -> None:\n        ... 60 lines (315-374)\n\n    @workflow.query\n    def stage(self) -> str:\n        \"\"\"Текущая стадия прогона — для Temporal UI (вкладка Queries).\n... 10 lines (379-388)\n\n    @workflow.query\n    def phase(self) -> str:\n        \"\"\"Фаза жизненного цикла — единый словарь на весь контур (#35).\n... 9 lines (393-401)\n\n    @workflow.query\n    def generation(self) -> int:\n        \"\"\"Сколько раз цикл перезапускался через continue-as-new.\n... 7 lines (406-412)\n\n    @workflow.query\n    def awaiting(self) -> Awaiting | None:\n        \"\"\"Чего Issue ждёт: вид, адресат, с какого момента и до какого срока (#39).\n... 6 lines (417-422)\n\n    @workflow.query\n    def handles_agents(self) -> bool:\n        \"\"\"Ведёт ли этот прогон агентов дочерними воркфлоу (#37).\n... 10 lines (427-436)\n\n    @workflow.signal\n    async def human_decision(self, label: str) -> None:\n        await self._signal_queue.put(label)\n\n    @workflow.signal\n    async def user_comment(self, text: str, comment_id: int | None = None) -> None:\n        \"\"\"Реплика человека в Issue.\n... 6 lines (445-450)\n\n    @workflow.signal\n    async def issue_closed(self, who: str | None = None) -> None:\n        \"\"\"Issue закрыт на GitHub — цикл обязан завершиться.\n... 12 lines (455-466)\n\n    @workflow.signal\n    async def analyze_requested(self, comment_id: int | None) -> None:\n        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n... 53 lines (471-523)\n\n    @workflow.signal\n    async def agent_event(self, event: AgentEvent) -> None:\n        \"\"\"Факт от внешнего агента контура: PR открыт, ревью взято, CI упал (#38).\n... 23 lines (528-550)\n\n    @workflow.signal\n    async def bft_requested(self, req: BftRequest) -> None:\n        \"\"\"По Issue запрошен БФТ — командой `/bft`/`/bft-deep` или меткой `run:*`.\n... 21 lines (555-575)\n\n    async def _start_bft(self, req: BftRequest) -> bool:\n        \"\"\"Прогон БФТ по команде — дочерним воркфлоу, без ожидания результата.\n... 23 lines (579-601)\n\n    @workflow.signal\n    async def estimate_requested(self, comment_id: int | None) -> None:\n        \"\"\"По Issue запрошена оценка трудоёмкости.\n... 29 lines (606-634)\n\n    async def _wait_for_signal(\n            self, timeout: timedelta | None = None) -> str | AgentEvent | UserComment | None:\n        ... 13 lines (638-650)\n\n    @workflow.run\n    async def run(self, issue: IssueInput,\n                  carried: LifecycleState | None = None) -> None:\n        \"\"\"Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n        ... 50 lines (656-705)\n\n    # --- Фазовый цикл ---\n\n    def _snapshot(self) -> LifecycleState:\n        \"\"\"Компактное состояние для continue-as-new: фаза и то немногое, что\n        ... 17 lines (711-727)\n\n    def _history_is_long(self) -> bool:\n        \"\"\"Порог по длине истории, а не по числу итераций: цена реплея зависит\n        от событий, а одна фаза может стоить и трёх событий, и трёхсот.\"\"\"\n        return workflow.info().get_current_history_length() >= HISTORY_EVENT_THRESHOLD\n\n    async def _park(self, kind: str, who: str, reason: str, hours: int) -> timedelta:\n        \"\"\"Встать в ожидание: описать его и вернуть срок таймера.\n... 14 lines (736-749)\n\n    async def _publish_awaiting(self) -> None:\n        \"\"\"Отражение ожидания в GitHub: очередь к людям должна быть полной.\n... 22 lines (753-774)\n\n    async def _stop_awaiting(self) -> None:\n        \"\"\"Ожидание снято: описание очищается, метка уходит.\"\"\"\n        ... 4 lines (778-781)\n\n    def _park_timeout(self, hours: int) -> timedelta:\n        \"\"\"Сколько ещё ждать в этой фазе — остаток от срока, а не полный срок.\n... 17 lines (785-801)\n\n    async def _phase_on_close(self) -> tuple[str, str]:\n        \"\"\"Чем закончился путь Issue: слиянием или снятием с обработки.\n... 22 lines (805-826)\n\n    async def _enter(self, phase: str, stage: str, *, write_label: bool = True) -> None:\n        \"\"\"Переход в фазу: проверка допустимости, стадия, метка.\n... 35 lines (830-864)\n\n    async def _run_analysis_child(self, issue: IssueInput,\n                                  trigger: str | None = None) -> bool:\n        \"\"\"Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n... 47 lines (869-915)\n\n    async def _agent_event(self, event: AgentEvent) -> tuple:\n        \"\"\"Факт внешнего агента — переход по той же таблице, что и у своих.\n... 35 lines (919-953)\n\n    async def _analysis_requested(self, issue: IssueInput) -> tuple:\n        \"\"\"Куда ведёт запрос аналитики из ТЕКУЩЕЙ фазы.\n... 19 lines (957-975)\n\n    async def _run_phase_loop(self, issue: IssueInput) -> None:\n        ... 78 lines (978-1055)\n\n    async def _phase_triage(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `created`: тот же триаж, что и раньше, но его исход — фаза.\n... 178 lines (1059-1236)\n\n    async def _bft_on_triage(self, issue: IssueInput) -> None:\n        \"\"\"БФТ как ответ триажа на запрос функционала.\n... 35 lines (1240-1274)\n\n    async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `classified`: ждём решения человека о тяжёлой стадии.\n... 77 lines (1278-1354)\n\n    async def _phase_analysis(self, issue: IssueInput) -> tuple | None:\n        \"\"\"Фаза `business-analysis`: цепочка FNR дочерним прогоном.\n... 10 lines (1358-1367)\n\n    async def _phase_handoff(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `system-requirements`: декомпозиция и передача разработчику (H1).\n... 72 lines (1371-1442)\n\n    async def _clarify_open_questions(self, issue: IssueInput, deadlines,\n                                      branch: str) -> tuple | None:\n        \"\"\"Спросить и подождать. `None` — идти дальше, передавать задачу.\n... 57 lines (1447-1503)\n\n    async def _answer_followup(self, issue: IssueInput, comment: UserComment) -> tuple:\n        \"\"\"Ответить на реплику человека, оставшись в той же фазе.\n... 41 lines (1507-1547)\n\n    async def _phase_await_build(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `ready-for-dev`: ждём, возьмут ли задачу в разработку.\n... 54 lines (1551-1604)\n\n    async def _start_development(self, issue: IssueInput) -> tuple:\n        \"\"\"Активность Develop: передать задачу агенту разработки.\n... 49 lines (1608-1656)\n\n    async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `pr-review`: довести PR по замечаниям, пока они по делу.\n... 57 lines (1660-1716)\n\n    async def _phase_park(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Боковые фазы и фазы внешних агентов.\n... 71 lines (1720-1790)\n\n    async def _run_linear(self, issue: IssueInput) -> None:\n        \"\"\"Прежний линейный сценарий — БЕЗ ИЗМЕНЕНИЙ.\n... 269 lines (1794-2062)\n\n\n@workflow.defn(name=\"IssueAnalysis\")\nclass IssueAnalysis:\n    \"\"\"Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.\n... 11 lines (2068-2078)\n    async def run(self, analyze: AnalyzeInput) -> bool:\n        \"\"\"Возвращает, опубликованы ли артефакты.\n... 14 lines (2081-2094)\n\n\n@workflow.defn(name=\"IssueBft\")\nclass IssueBft:\n    \"\"\"БФТ по Issue: быстрый проход (`/bft`) и глубокая проработка (`/bft-deep`).\n... 11 lines (2100-2110)\n    def __init__(self) -> None:\n        self._stage = \"accepted\"\n        self._mode = bft.FAST\n\n    @workflow.query\n    def stage(self) -> str:\n        \"\"\"Стадия прогона — для Temporal UI (вкладка Queries).\n... 6 lines (2118-2123)\n\n    @workflow.query\n    def mode(self) -> str:\n        return self._mode\n\n    @workflow.run\n    async def run(self, req: BftRequest) -> bool:\n        \"\"\"Возвращает, опубликован ли БФТ.\n... 80 lines (2132-2211)\n\n    async def _run_deep(self, req: BftRequest) -> None:\n        \"\"\"Канонический пайплайн bft-writer — стадия за стадией.\n... 31 lines (2215-2245)\n\n\n@workflow.defn(name=\"IssueEstimation\")\nclass IssueEstimation:\n    \"\"\"Оценка трудоёмкости по команде /estimate.\n... 9 lines (2251-2259)\n    async def run(self, req: EstimateRequest) -> None:\n        ... 56 lines (2261-2316)\n",
        "verified": true
      },
      "episodes": 14
    }
  },
  "_meta": {
    "timing_ms": 80.7,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "sysreq-agent external agent integration",
  "limit": 5
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/lifecycle.py",
      "page_type": "file_page",
      "snippet": "| `FAILED` | constant | FAILED = \"failed\" |\n| `CANCELLED` | constant | CANCELLED = \"cancelled\" |\n| `AGENT` | constant | AGENT = \"agent\" |\n| `HUMAN` | constant | HUMAN = \"human\" |\n| `EXTERNAL` | consta",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/lifecycle.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: shared/sentry_setup.py",
      "page_type": "file_page",
      "snippet": "e request dsn try environment release traces_sample_rate traces sample rate before_send before send integrations event_level event level _configured configured org url message github_private_key_b64 k",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "shared/sentry_setup.py",
      "confidence_score": 0.98
    },
    {
      "title": "File: shared/awaiting.py",
      "page_type": "file_page",
      "snippet": "| `APPROVAL` | constant | APPROVAL = \"approval\" |\n| `TESTING` | constant | TESTING = \"testing\" |\n| `EXTERNAL_AGENT` | constant | EXTERNAL_AGENT = \"external-agent\" |\n| `FAILURE_RECOVERY` | constant | F",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "shared/awaiting.py",
      "confidence_score": 0.97
    },
    {
      "title": "File: worker/estimation.py",
      "page_type": "file_page",
      "snippet": "rationale work_type work type artifact_type artifact scaffolding_hours scaffolding work_units units integration_hours integration fp_count count fp_hours_per_point per point data_sufficiency data suff",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "worker/estimation.py",
      "confidence_score": 0.95
    },
    {
      "title": "Symbol: tests.test_estimate_report.facts",
      "page_type": "symbol_spotlight",
      "snippet": "s=4.0,\n        work_units=[WorkUnit(name=\"эндпоинт\", hours=4.0, rationale=\"один маршрут\")],\n        integration_hours=2.0,\n        fp_count=2.0,\n        fp_hours_per_point=5.5,\n        data_sufficienc",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_report.py::facts",
      "file": "tests/test_estimate_report.py",
      "confidence_score": 0.93
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "shared/sentry_setup.py"
    },
    {
      "path": "shared/awaiting.py"
    },
    {
      "path": "worker/estimation.py"
    },
    {
      "path": "tests/test_estimate_report.py"
    }
  ]
}

## Ход 5 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/lifecycle.py",
    "shared/agent_events.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/lifecycle.py": {
      "target": "shared/lifecycle.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/lifecycle.py",
        "summary": "Модель фаз жизненного цикла Issue — единственный источник правды."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 2,
        "last_fix_days_ago": 1
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1463,
        "full_tokens": 3502,
        "pct_of_full": 41.8,
        "bodies_kept": [
          "InvalidTransition",
          "transition",
          "TRANSITIONS",
          "STAGE_TO_PHASE",
          "phase_from_labels"
        ],
        "text": "[repowise#9a8693ecf93c: 154 lines omitted (~1463 tokens); restore: repowise expand 9a8693ecf93c]",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 41.8% of the full file — a direct Read costs little more.",
        "omitted": true
      },
      "episodes": 2
    },
    "shared/agent_events.py": {
      "target": "shared/agent_events.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/agent_events.py",
        "summary": "Контракт «событие внешнего агента → факт в жизни Issue»."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 2
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1275,
        "full_tokens": 2001,
        "pct_of_full": 63.7,
        "bodies_kept": [
          "parse_closes",
          "parse_event",
          "key",
          "correlate",
          "issue_from_branch"
        ],
        "text": "\"\"\"Контракт «событие внешнего агента → факт в жизни Issue».\n\nПубличный интерфейс для соседних сервисов контура (PR-Agent, PR-Closer, CI).\nЭто не общая шина и не общий код: у них свой релизный цикл и своя\nответственность, а здесь — один типизированный конверт и одно правило\nкорреляции.\n\nПочему HTTP, а не прямая сигнализация по Temporal-handle. `poh-pr-agents` —\nсервис поверх GitHub App, Temporal он не использует вовсе. Общий namespace\nпотребовал бы втащить в него SDK, сетевой доступ к кластеру и знание наших\nworkflow id; это ровно та связность, ради ухода от которой задача и ставилась.\nHTTP с подписью — транспорт, на котором соседний сервис уже говорит.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub. Разбор и корреляция\nпроверяются напрямую, как в `shared/lifecycle.py` и `worker/estimation.py`.\n\"\"\"\n\nimport re\nfrom dataclasses import dataclass, field\n\nfrom shared import lifecycle\n\n# --- Статусы события. Фазу называет агент, статус уточняет её исход ---\n\nSTARTED = \"started\"      # работа началась: PR открыт, ревью взято в работу\nSUCCEEDED = \"succeeded\"  # шаг закрыт успешно: PR влит, тесты зелёные\nFAILED = \"failed\"        # шаг не удался: CI красный, доведение не получилось\nBLOCKED = \"blocked\"      # нужен человек: ревью запросило решение\n\nSTATUSES = frozenset({STARTED, SUCCEEDED, FAILED, BLOCKED})\n\n\nclass InvalidAgentEvent(ValueError):\n    \"\"\"Событие не соответствует контракту.\n... 5 lines (35-39)\n\n\n@dataclass\nclass AgentEvent:\n    \"\"\"Факт, о котором внешний агент докладывает циклу Issue.\n... 30 lines (45-74)\n    def key(self) -> str:\n        \"\"\"Ключ идемпотентности: один факт — один переход.\n\n        Фаза входит в ключ, хотя постановка называла пару `(ref, status)`. Без\n        неё `pr-open/started` и `pr-review/started` по одному PR — один ключ, и\n        начало ревью потерялось бы как «повторная доставка открытия». Статуса\n        мало: `started` сопровождает каждый шаг пути.\n        \"\"\"\n        base = f\"{self.ref}:{self.phase}:{self.status}\"\n        return f\"{base}:{self.revision}\" if self.revision else base\n\n\ndef parse_event(payload: dict) -> AgentEvent:\n    \"\"\"Разбор конверта с проверками, которые дешевле сделать на входе.\n\n    Проверяем ровно то, от чего зависит дальнейшая обработка: фаза обязана быть\n    из словаря, статус — из перечня. Всё остальное (кто агент, что в detail)\n    контур не интерпретирует и потому не валидирует: лишняя строгость на\n    публичном контракте ломает соседей на каждой их правке.\n    \"\"\"\n    if not isinstance(payload, dict):\n        raise InvalidAgentEvent(\"ожидается объект\")\n\n    missing = [f for f in (\"repo\", \"agent\", \"phase\", \"status\", \"ref\")\n               if not str(payload.get(f) or \"\").strip()]\n    if missing:\n        raise InvalidAgentEvent(f\"не заполнено: {', '.join(missing)}\")\n\n    phase = str(payload[\"phase\"]).strip()\n    if phase not in lifecycle.TRANSITIONS:\n        raise InvalidAgentEvent(\n            f\"фаза {phase!r} не из словаря; допустимо: {', '.join(lifecycle.PHASES)}\")\n\n    status = str(payload[\"status\"]).strip()\n    if status not in STATUSES:\n        raise InvalidAgentEvent(\n            f\"статус {status!r} не из перечня; допустимо: {', '.join(sorted(STATUSES))}\")\n\n    root = payload.get(\"root_issue\")\n    if root is not None:\n        try:\n            ... 23 lines (116-138)\n_CLOSES_RE = re.compile(\n    r\"\\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\\s*:?\\s*#(\\d+)\", re.IGNORECASE)\n\n# Конвенция веток артефактов — та же, что у аналитики и багфикса.\n_BRANCH_RE = re.compile(r\"\\b(?:research|bug)/issue-(\\d+)\\b\")\n\n\ndef parse_closes(text: str | None) -> list[int]:\n    \"\"\"Все номера, которые текст объявляет закрываемыми.\"\"\"\n    if not text:\n        return []\n    seen: list[int] = []\n    for raw in _CLOSES_RE.findall(text):\n        number = int(raw)\n        if number not in seen:\n            seen.append(number)\n    return seen\n\n\ndef issue_from_branch(ref: str | None) -> int | None:\n    \"\"\"Номер Issue из имени ветки артефактов, иначе None.\"\"\"\n    if not ref:\n        return None\n    match = _BRANCH_RE.search(ref)\n    return int(match.group(1)) if match else None\n\n\ndef correlate(event: AgentEvent) -> tuple[int | None, str]:\n    \"\"\"Какому Issue принадлежит работа. Возвращает (номер, чем опознали).\n\n    Источники по убыванию надёжности: явное поле → `Closes #N` в теле →\n    конвенция имени ветки. Первый сработавший выигрывает: смешивать их\n    голосованием нельзя, у них разная достоверность.\n\n    Неоднозначность НЕ разрешается догадкой. Если тело объявляет закрываемыми\n    несколько Issue, выбирать «первый попавшийся» значит молча привязать работу\n    не к той задаче — а именно на этой связи держится вся трассировка. Такой\n    случай уходит человеку.\n    \"\"\"\n    if event.root_issue is not None:\n        return event.root_issue, \"поле root_issue\"\n\n    closes = parse_closes(event.detail)\n    if len(closes) == 1:\n        return closes[0], \"Closes #N в теле\"\n    if len(closes) > 1:\n        ... 8 lines (185-192)\n\n\n# --- Отображение события в переход фазы ---\n\ndef target_phase(event: AgentEvent) -> str:\n    \"\"\"В какую фазу событие переводит Issue.\n... 11 lines (199-209)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 63.7% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 71.91,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "9a8693ecf93c"
      ],
      "tokens": 1463,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {}
}

## Ход 6 · `list_repos` · contour

**Запрос:**

```json
{}
```

**Ответ:**

{
  "workspace": true,
  "workspace_root": "/workspaces/contour",
  "default_repo": "poh-issue-agents",
  "repos": [
    {
      "alias": "poh-bft-writer",
      "path": "poh-bft-writer",
      "absolute_path": "/workspaces/contour/poh-bft-writer",
      "is_default": false,
      "indexed_at": "2026-08-19T16:03:52.461252+00:00",
      "last_commit_at_index": "c7fe9bd7d1b2daab398ea838ee9b6fbf3a273555"
    },
    {
      "alias": "poh-cortex",
      "path": "poh-cortex",
      "absolute_path": "/workspaces/contour/poh-cortex",
      "is_default": false,
      "indexed_at": "2026-08-19T16:03:55.713541+00:00",
      "last_commit_at_index": "3c3e1a3a9e83725ddb2792da665fc180a2ed81b1"
    },
    {
      "alias": "poh-helper",
      "path": "poh-helper",
      "absolute_path": "/workspaces/contour/poh-helper",
      "is_default": false,
      "indexed_at": "2026-08-19T16:06:36.007619+00:00",
      "last_commit_at_index": "18512c1e7ce999e3fed9f009f443a51aa7e9d9e4"
    },
    {
      "alias": "poh-infra",
      "path": "poh-infra",
      "absolute_path": "/workspaces/contour/poh-infra",
      "is_default": false,
      "indexed_at": "2026-08-19T16:06:38.913538+00:00",
      "last_commit_at_index": "a1db4f02f10c0d144bc2a8222b3865a6eecb9dc4"
    },
    {
      "alias": "poh-issue-agents",
      "path": "poh-issue-agents",
      "absolute_path": "/workspaces/contour/poh-issue-agents",
      "is_default": true,
      "indexed_at": "2026-08-19T16:06:57.382649+00:00",
      "last_commit_at_index": "d54073370859527533c3269472dead49cca252b9"
    },
    {
      "alias": "poh-memory-engine",
      "path": "poh-memory-engine",
      "absolute_path": "/workspaces/contour/poh-memory-engine",
      "is_default": false,
      "indexed_at": "2026-08-19T16:07:08.084545+00:00",
      "last_commit_at_index": "194e39319b3fa91f62971c91d919dff98f6b9833"
    },
    {
      "alias": "poh-pr-agents",
      "path": "poh-pr-agents",
      "absolute_path": "/workspaces/contour/poh-pr-agents",
      "is_default": false,
      "indexed_at": "2026-08-19T16:07:58.727530+00:00",
      "last_commit_at_index": "9f15ada9e4e90cb8a8e6ea7a091f672eeb948e1e"
    },
    {
      "alias": "poh-scheduller",
      "path": "poh-scheduller",
      "absolute_path": "/workspaces/contour/poh-scheduller",
      "is_default": false,
      "indexed_at": "2026-08-19T16:08:00.946992+00:00",
      "last_commit_at_index": "04cc3f47aff9726fc09d913a4e20a1723f3fea68"
    },
    {
      "alias": "poh-sprint-agents",
      "path": "poh-sprint-agents",
      "absolute_path": "/workspaces/contour/poh-sprint-agents",
      "is_default": false,
      "indexed_at": "2026-08-19T16:08:07.097100+00:00",
      "last_commit_at_index": "c41cb5b2ce182e15312f0fe906f4a1bdb561d8f3"
    }
  ],
  "hint": "Use repo='<alias>' on tools that accept a repo parameter.",
  "_meta": {
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "mode": "path",
  "query": "deployment deploy CI CD docker compose"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "Sentry health endpoint monitoring verification smoke test"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Docs Tooling Scripts",
      "page_type": "module_page",
      "snippet": "y`: Живой E2E: проверка контура на настоящем репозитории, Temporal и модели. Внутрипроцессный E2E (`tests/test_e2e_issue_lifecycle.py`) замыкает сеть на заглушки и потому не может ответить на вопросы,",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "scripts",
      "confidence_score": 1.0
    },
    {
      "title": "File: scripts/estimate.py",
      "page_type": "file_page",
      "snippet": "# scripts/estimate.py\n\n## Overview\n\nSmoke harness: start one IssueEstimation workflow without the webhook.\n\n`/estimate` normally arrives as an `issue_comment.created` webhook, which\nneeds Layer B (Git",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/estimate.py",
      "confidence_score": 0.99
    },
    {
      "title": "Application Webhook",
      "page_type": "module_page",
      "snippet": "- `shared/authz.py`\n\n- `shared/commands.py`\n\n- `shared/labels.py`\n\n- `shared/repos.py`\n\n- `shared/sentry_setup.py`\n\n- `shared/temporal_client.py`\n\n- `shared/workflow_ids.py`\n\n- `shared/workflow_type",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "webhook",
      "confidence_score": 0.97
    },
    {
      "title": "Utility Shared",
      "page_type": "module_page",
      "snippet": "и Temporal, ни GitHub, как `lifecycle.py` и `estimation.py`. Формат комментария и перече\n\n- `shared/sentry_setup.py`: Отправка ключевых сбоёв в Sentry (парно к логам в stdout). Зачем: логи воркера/веб",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "shared",
      "confidence_score": 0.95
    },
    {
      "title": "File: scripts/smoke_temporal.py",
      "page_type": "file_page",
      "snippet": "# scripts/smoke_temporal.py\n\n## Overview\n\nEnd-to-end проверка централизованного Temporal: коннект, namespace и очередь.\n\nЗапускать С ХОСТА, где реально крутится worker (у него есть сетевой доступ к\nкл",
      "relevance_score": 2.842,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/smoke_temporal.py",
      "confidence_score": 0.95
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "scripts/estimate.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "webhook/main.py"
    },
    {
      "path": "worker/worker.py"
    },
    {
      "path": "shared/sentry_setup.py"
    }
  ]
}

## Ход 9 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "targets": [
    "shared/sentry_setup.py",
    "scripts/smoke_temporal.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/sentry_setup.py": {
      "target": "shared/sentry_setup.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/sentry_setup.py",
        "summary": "Отправка ключевых сбоёв в Sentry (парно к логам в stdout)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 1
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1340,
        "full_tokens": 2536,
        "pct_of_full": 52.8,
        "bodies_kept": [
          "event_url",
          "_scrub_mapping",
          "_classify_external",
          "_EXTERNAL_FAILURES",
          "_scrub_event"
        ],
        "text": "\"\"\"Отправка ключевых сбоёв в Sentry (парно к логам в stdout).\n\nЗачем: логи воркера/вебхука живут в stdout контейнера Dokploy и никого не\nбудят. Главный класс сбоя этого стека — не падение процесса, а *пойманный*\nсбой: workflow триажа упал и оставил лейбл `advisor:error` (workflows.py), а\n`/estimate` упал на стадии и поставил реакцию `confused`. Оба видны только как\nкоммент в issue и строка лога. Sentry делает из них адресуемое событие с\nтегами service/repo/issue/stage.\n\n`configure()` идемпотентна и НЕОБЯЗАТЕЛЬНА: без SENTRY_DSN — no-op, стек ведёт\nсебя ровно как до интеграции (это же и процедура отката — убрать переменную из\n.env и перезапустить).\n\n⚠️ ГРАНИЦА С TEMPORAL: этот модуль зовётся ТОЛЬКО из entrypoint'ов (worker.py,\nwebhook/main.py) и из activities. Никогда — из workflow-кода (workflows.py,\nconsolidation_workflow.py): там сетевой вызов недетерминирован и сломает replay.\n\n⚠️ Скраббер (`_scrub_event`): в кадры стека sentry-sdk кладёт значения локальных\nпеременных, а по этому коду ходят ZAI_API_KEY, GitHub-токен, GITHUB_PRIVATE_KEY_B64\nи тела issue/PR. Денилист имён вырезает значения ДО отправки на sentry.io —\nтрогать его без нужды нельзя.\n\"\"\"\nfrom __future__ import annotations\n\nimport logging\nimport os\nimport re\nfrom typing import Optional\n\nlogger = logging.getLogger(__name__)\n\n_configured = False\n\n# Ключи, значения которых не должны покидать периметр. Сопоставляется по\n# ПОДСТРОКЕ имени в нижнем регистре: \"github_private_key_b64\" ловится по \"key\",\n# \"X-Hub-Signature-256\" — по \"signature\", \"ZAI_API_KEY\" — по \"key\".\n_SECRET_KEY = re.compile(\n    r\"token|key|secret|password|passwd|private|authorization|auth|cookie|\"\n    r\"signature|dsn|credential\",\n    re.IGNORECASE,\n)\n_FILTERED = \"[Filtered]\"\n_MAX_VALUE_LEN = 2048  # длинные значения (тела ответов) режем, а не шлём целиком\n\n\ndef _scrub_mapping(d) -> None:\n    \"\"\"Заменить значения секретных ключей на [Filtered], длинные — обрезать. In-place.\"\"\"\n    if not isinstance(d, dict):\n        return\n    for k, v in list(d.items()):\n        if isinstance(k, str) and _SECRET_KEY.search(k):\n            d[k] = _FILTERED\n        elif isinstance(v, dict):\n            _scrub_mapping(v)\n        elif isinstance(v, str) and len(v) > _MAX_VALUE_LEN:\n            d[k] = v[:_MAX_VALUE_LEN] + \"…[truncated]\"\n... 11 lines (57-67)\n_EXTERNAL_FAILURES = {\n    \"RateLimitError\",       # 429 от z.ai — один ключ на все стадии контура\n    \"APITimeoutError\",      # провайдер не ответил в срок\n    \"APIConnectionError\",   # до провайдера не дошли\n    \"InternalServerError\",  # 5xx и 524 от шлюза\n    \"ClientDisconnect\",     # отправитель вебхука ушёл, не дослав тело\n}\n\n\ndef _classify_external(event: dict) -> None:\n    \"\"\"Пометить отказ чужой стороны: level=warning и общий fingerprint.\"\"\"\n    values = (event.get(\"exception\") or {}).get(\"values\") or []\n    if not values:\n        return\n    exc_type = values[-1].get(\"type\")\n    if exc_type in _EXTERNAL_FAILURES:\n        event[\"level\"] = \"warning\"\n        event[\"fingerprint\"] = [\"external_failure\", exc_type]\n        event.setdefault(\"tags\", {})[\"failure_side\"] = \"external\"\n\n\ndef _scrub_event(event: dict, hint=None) -> Optional[dict]:\n    \"\"\"before_send: вычистить секреты из кадров стека, request и extra.\"\"\"\n    _classify_external(event)\n    for value in (event.get(\"exception\") or {}).get(\"values\") or []:\n        for frame in (value.get(\"stacktrace\") or {}).get(\"frames\") or []:\n            _scrub_mapping(frame.get(\"vars\"))\n    request = event.get(\"request\")\n    if isinstance(request, dict):\n        _scrub_mapping(request.get(\"headers\"))\n        _scrub_mapping(request.get(\"cookies\"))\n        _scrub_mapping(request.get(\"env\"))\n        request.pop(\"data\", None)  # тело webhook'а = payload GitHub, наружу не нужно\n    _scrub_mapping(event.get(\"extra\"))\n    _scrub_mapping(event.get(\"contexts\"))\n    return event\n\n\ndef configure(service: str) -> bool:\n    \"\"\"Инициализировать Sentry для процесса `service` (webhook|worker).\n... 33 lines (108-140)\n\n\ndef event_url(event_id: Optional[str]) -> Optional[str]:\n    \"\"\"Ссылка на конкретное событие в Sentry — по id и слагу организации.\n\n    Слаг из DSN не выводится (там только числовой id организации), поэтому\n    берётся из `SENTRY_ORG`. Без него ссылки нет — остаётся сам id события,\n    по которому оно ищется в UI руками.\n    \"\"\"\n    org = os.environ.get(\"SENTRY_ORG\", \"\").strip()\n    if not event_id or not org:\n        return None\n    # Поиск по id события в списке issue: Sentry разворачивает его в само\n    # событие. Прямой ссылки на событие без известного issue_id у API нет.\n    return f\"https://{org}.sentry.io/issues/?query={event_id}\"\n\n\ndef debug_reference(event_id: Optional[str]) -> str:\n    \"\"\"Строка для комментария в Issue: куда смотреть, чтобы разобрать сбой.\n... 11 lines (160-170)\n\n\ndef capture_pipeline_failure(issue, exc_type: str, message: str) -> Optional[str]:\n    \"\"\"Workflow триажа (IssueLifecycle) поймал исключение и поставил лейбл\n    ... 21 lines (175-195)\n\n\ndef capture_analysis_failure(analyze, exc_type: str, message: str) -> Optional[str]:\n    \"\"\"Workflow `/analyze` (IssueAnalysis) не довёл прогон до артефактов.\n... 19 lines (200-218)\n\n\ndef capture_estimate_failure(req, stage: str, exc_type: str,\n                             message: str) -> Optional[str]:\n    \"\"\"Workflow /estimate (IssueEstimation) упал на стадии `stage`.\n... 19 lines (224-242)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 52.8% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    },
    "scripts/smoke_temporal.py": {
      "target": "scripts/smoke_temporal.py",
      "type": "file",
      "parent_page": {
        "title": "Docs Tooling Scripts",
        "target_path": "scripts",
        "section": "5"
      },
      "docs": {
        "title": "File: scripts/smoke_temporal.py",
        "summary": "End-to-end проверка централизованного Temporal: коннект, namespace и очередь."
      },
      "hotspot": false,
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Docs & Tooling",
        "description": "",
        "role": "entry_point"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 685,
        "full_tokens": 709,
        "pct_of_full": 96.6,
        "bodies_kept": [
          "main"
        ],
        "text": "#!/usr/bin/env python3\n\"\"\"End-to-end проверка централизованного Temporal: коннект, namespace и очередь.\n\nЗапускать С ХОСТА, где реально крутится worker (у него есть сетевой доступ к\nкластеру). Не с локальной машины — публичный эндпоинт может быть за allowlist.\n\n    set -a; . .env; set +a          # подхватить TEMPORAL_ADDRESS/NAMESPACE\n    python scripts/smoke_temporal.py\n\nЧто делает:\n  1) Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)\n  2) describe_namespace — namespace существует и REGISTERED\n  3) поднимает временный worker на task-queue `poh-smoke-test`, запускает\n     тривиальный workflow (activity возвращает pong) и ждёт результат —\n     это доказывает, что очередь принимает задачи и worker их исполняет.\n\nНичего в целевом репозитории не трогает — отдельная task-queue и workflow.\n\"\"\"\nimport asyncio\nimport os\nimport sys\nimport time\nfrom datetime import timedelta\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n\nfrom temporalio import activity, workflow\nfrom temporalio.api.workflowservice.v1 import DescribeNamespaceRequest\nfrom temporalio.worker import UnsandboxedWorkflowRunner, Worker\n\nfrom shared.temporal_client import connect_temporal\n\nADDR = os.environ.get(\"TEMPORAL_ADDRESS\", \"localhost:7233\")\nNS = os.environ.get(\"TEMPORAL_NAMESPACE\", \"default\")\nTQ = \"poh-smoke-test\"\n\n\n@activity.defn\nasync def echo(x: str) -> str:\n    return f\"pong:{x}\"\n\n\n@workflow.defn\nclass SmokeWorkflow:\n    @workflow.run\n    async def run(self, x: str) -> str:\n        ... 3 lines (48-50)\n\n\nasync def main() -> None:\n    print(f\"target: {ADDR}  namespace: {NS}\")\n    try:\n        client = await connect_temporal()\n    except Exception as e:  # noqa: BLE001 — диагностика, печатаем как есть\n        print(f\"CONNECT_FAIL: {type(e).__name__}: {e}\")\n        sys.exit(1)\n    print(\"[1/3] CONNECT_OK\")\n\n    desc = await client.workflow_service.describe_namespace(\n        DescribeNamespaceRequest(namespace=NS)\n    )\n    print(f\"[2/3] NAMESPACE_OK: name={desc.namespace_info.name!r} \"\n          f\"state={desc.namespace_info.state}\")\n\n    wf_id = f\"poh-smoke-{int(time.time())}\"\n    async with Worker(\n        client,\n        task_queue=TQ,\n        workflows=[SmokeWorkflow],\n        activities=[echo],\n        workflow_runner=UnsandboxedWorkflowRunner(),\n    ):\n        result = await asyncio.wait_for(\n            client.execute_workflow(\n                SmokeWorkflow.run, \"hello\", id=wf_id, task_queue=TQ\n            ),\n            timeout=60,\n        )\n    ok = result == \"pong:hello\"\n    print(f\"[3/3] QUEUE_ROUNDTRIP {'OK' if ok else 'MISMATCH'}: \"\n          f\"result={result!r} (id={wf_id} tq={TQ})\")\n    sys.exit(0 if ok else 2)\n\n\nif __name__ == \"__main__\":\n    asyncio.run(main())\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 96.6% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 96.68,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 10 · `get_overview` · contour

**Запрос:**

```json
{
  "include": [
    "content"
  ],
  "repo": "poh-pr-agents"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-pr-agents",
  "content_md": "# Repository Overview: poh-pr-agents\n\n**Files:** 87 | **Lines:** 15233 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-pr-agents` is a python codebase of 87 files. Execution starts at `self-hosted/reliability/app.py`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `self-hosted/reliability/app.py`\n\n\n\n\n## Primary Execution Flows\n\n- `self-hosted/reliability/worker.py::main` (7 steps)\n\n- `self-hosted/reliability/app.py::webhook` (4 steps)\n\n- `self-hosted/reliability/worker.py::handle_lease` (4 steps)\n\n- `self-hosted/reliability/mapreduce_worker.py::route_and_fanout` (4 steps)\n\n- `self-hosted/reliability/sweeper.py::sweep` (3 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `self-hosted/reliability/state.py` (0.0929)\n\n- `self-hosted/reliability/sizing.py` (0.0501)\n\n- `self-hosted/reliability/chunk_review.py` (0.0338)\n\n- `self-hosted/reliability/__init__.py` (0.0305)\n\n- `self-hosted/reliability/metrics.py` (0.0243)\n\n- `self-hosted/reliability/chunking.py` (0.0215)\n\n- `self-hosted/reliability/reduce.py` (0.0201)\n\n- `self-hosted/reliability/queue.py` (0.0184)\n\n- `self-hosted/reliability/webhook.py` (0.0177)\n\n- `self-hosted/reliability/token.py` (0.0173)\n\n- `self-hosted/reliability/sweeper.py` (0.0172)\n\n- `self-hosted/reliability/security.py` (0.0171)\n\n- `self-hosted/reliability/quality_eval.py` (0.0168)\n\n- `self-hosted/reliability/github_client.py` (0.0158)\n\n- `self-hosted/reliability/notifier.py` (0.0150)\n\n- `self-hosted/reliability/gateway.py` (0.0143)\n\n- `self-hosted/reliability/sentry_setup.py` (0.0140)\n\n- `self-hosted/reliability/worker.py` (0.0131)\n\n- `self-hosted/reliability/mapreduce.py` (0.0130)\n\n- `self-hosted/reliability/analyze_adapter.py` (0.0126)\n\n\n\n\n\n\n\n\n\n## Codebase health signals\n- **Hotspots:** 14 files are both high-churn and high-complexity\n- **Stable core:** 0 files unchanged in 90+ days\n- **Most changed (90d):** `self-hosted/reliability/worker.py`, `self-hosted/reliability/tests/test_worker.py`, `self-hosted/reliability/github_client.py`\n- **Oldest file:** `self-hosted/finish-registration.sh` (39 days)\n\n\n---\n\n*Built from the code's structure. It states what is there, not why it is that\nway. Add an API key and run `repowise generate` to have that written.*\n\n## Architecture map\n\n```mermaid\nflowchart LR\n  subgraph layer_application[\"Application\"]\n    direction TB\n    module_application[\"Application\"]\n  end\n  subgraph layer_test[\"Test\"]\n    direction TB\n    module_self_hosted_reliability_tests[\"reliability/tests\"]\n  end\n\n```\n",
  "code_health": {
    "average_health": 8.64,
    "band": "healthy",
    "hotspot_health": 6.95,
    "worst_performer_path": "self-hosted/reliability/worker.py",
    "worst_performer_score": 4.55,
    "open_findings": 219,
    "file_count": 87,
    "distribution": {
      "total_files": 87,
      "total_nloc": 8327,
      "bands": {
        "healthy": {
          "files": 72,
          "nloc": 6210,
          "pct": 74.6
        },
        "warning": {
          "files": 15,
          "nloc": 2117,
          "pct": 25.4
        },
        "alert": {
          "files": 0,
          "nloc": 0,
          "pct": 0.0
        }
      }
    }
  },
  "key_modules": [
    {
      "name": "Self Hosted Reliability",
      "path": "self-hosted/reliability",
      "description": "`self-hosted/reliability`\n\n**Language:** python | **Files:** 30 | **Public symbols:** 223 / 275\n\n\nCovers the 30 source files in self-hosted/reliability. Does not cover code outside those directories…",
      "page_id": "module_page:self-hosted/reliability",
      "section": "4",
      "parent_page_id": "repo_overview:poh-pr-agents"
    },
    {
      "name": "Reliability Eval",
      "path": "self-hosted/reliability/eval",
      "description": "`self-hosted/reliability/eval` · `self-hosted/reliability/loadtest`\n\n**Language:** python | **Files:** 2 | **Public symbols:** 20 / 23\n\n\nCovers the 2 source files in 2 directories under…",
      "page_id": "module_page:self-hosted/reliability/eval",
      "section": "5",
      "parent_page_id": "repo_overview:poh-pr-agents"
    }
  ],
  "entry_points": [
    "self-hosted/reliability/app.py"
  ],
  "git_health": {
    "files_git_attributed": 64,
    "hotspot_count": 14,
    "avg_bus_factor": 1.1,
    "files_with_bus_factor_1": 60,
    "churn_trend": "stable",
    "top_churn_modules": [
      "self-hosted/reliability",
      "self-hosted/finish-registration.sh",
      "self-hosted/reliability-entrypoint.sh",
      "self-hosted/scripts"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "Claude",
        "files_owned": 59,
        "percentage": 92.2
      },
      {
        "name": "ALeks ishmanov",
        "files_owned": 3,
        "percentage": 4.7
      },
      {
        "name": "kibarik",
        "files_owned": 2,
        "percentage": 3.1
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "tests",
      "size": 10
    },
    {
      "id": 1,
      "label": "agent_event",
      "size": 7
    },
    {
      "id": 2,
      "label": "tests (16)",
      "size": 6
    },
    {
      "id": 3,
      "label": "tests (11)",
      "size": 6
    },
    {
      "id": 4,
      "label": "tests (5)",
      "size": 3
    },
    {
      "id": 5,
      "label": ".mcp",
      "size": 1
    },
    {
      "id": 6,
      "label": "agents",
      "size": 1
    },
    {
      "id": 7,
      "label": "readme",
      "size": 1
    },
    {
      "id": 8,
      "label": ".pr_agent",
      "size": 1
    },
    {
      "id": 9,
      "label": "architecture",
      "size": 1
    }
  ],
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-pr-agents",
      "title": "Repository Overview: poh-pr-agents"
    },
    "total_pages": 110,
    "sections": [
      {
        "section": "1",
        "page_id": "onboarding:onboarding/key_concepts",
        "title": "Key Concepts",
        "page_type": "onboarding",
        "target_path": "onboarding/key_concepts"
      },
      {
        "section": "2",
        "page_id": "onboarding:onboarding/how_it_works",
        "title": "How It Works",
        "page_type": "onboarding",
        "target_path": "onboarding/how_it_works"
      },
      {
        "section": "3",
        "page_id": "onboarding:onboarding/active_landscape",
        "title": "Active Landscape",
        "page_type": "onboarding",
        "target_path": "onboarding/active_landscape"
      },
      {
        "section": "4",
        "page_id": "module_page:self-hosted/reliability",
        "title": "Self Hosted Reliability",
        "page_type": "module_page",
        "target_path": "self-hosted/reliability",
        "descendants": 98
      },
      {
        "section": "5",
        "page_id": "module_page:self-hosted/reliability/eval",
        "title": "Reliability Eval",
        "page_type": "module_page",
        "target_path": "self-hosted/reliability/eval",
        "descendants": 2
      },
      {
        "section": "6",
        "page_id": "scc_page:scc-710476d31bcf",
        "title": "Circular Dependency: Self Hosted Reliability",
        "page_type": "scc_page",
        "target_path": "scc-710476d31bcf"
      },
      {
        "section": "7",
        "page_id": "infra_page:self-hosted/finish-registration.sh",
        "title": "Infrastructure: self-hosted/finish-registration.sh",
        "page_type": "infra_page",
        "target_path": "self-hosted/finish-registration.sh"
      },
      {
        "section": "8",
        "page_id": "infra_page:self-hosted/reliability-entrypoint.sh",
        "title": "Infrastructure: self-hosted/reliability-entrypoint.sh",
        "page_type": "infra_page",
        "target_path": "self-hosted/reliability-entrypoint.sh"
      },
      {
        "section": "9",
        "page_id": "infra_page:self-hosted/scripts/smoke.sh",
        "title": "Infrastructure: self-hosted/scripts/smoke.sh",
        "page_type": "infra_page",
        "target_path": "self-hosted/scripts/smoke.sh"
      }
    ]
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 56
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 1
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 1
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 29
      }
    ],
    "tour_available": true,
    "tour_step_count": 12,
    "layer_order": [
      "Application"
    ]
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-pr-agents",
      "page_id": "repo_overview:poh-pr-agents",
      "target_path": "poh-pr-agents",
      "section": null
    },
    {
      "order": 2,
      "slot": "key_concepts",
      "title": "Key Concepts",
      "page_id": "onboarding:onboarding/key_concepts",
      "target_path": "onboarding/key_concepts",
      "section": "1"
    },
    {
      "order": 3,
      "slot": "how_it_works",
      "title": "How It Works",
      "page_id": "onboarding:onboarding/how_it_works",
      "target_path": "onboarding/how_it_works",
      "section": "2"
    },
    {
      "order": 4,
      "slot": "active_landscape",
      "title": "Active Landscape",
      "page_id": "onboarding:onboarding/active_landscape",
      "target_path": "onboarding/active_landscape",
      "section": "3"
    }
  ],
  "reading_order_hint": "Canonical onboarding sequence — read these page_ids in order via get_context/get_symbol to understand the repo the way a new contributor would.",
  "guided_tour": [
    {
      "order": 1,
      "title": "README.md",
      "kind": "overview",
      "reason": "Start here for the end-to-end picture before diving into the code.",
      "target_path": "README.md",
      "page_id": "repo_overview:README.md",
      "section": null
    },
    {
      "order": 2,
      "title": "app.py",
      "kind": "code",
      "reason": "An entry point — execution and imports fan out from here.",
      "target_path": "self-hosted/reliability/app.py",
      "page_id": "file_page:self-hosted/reliability/app.py",
      "section": "4.4"
    },
    {
      "order": 3,
      "title": "state.py",
      "kind": "code",
      "reason": "Directly used by the entry points above; a core collaborator.",
      "target_path": "self-hosted/reliability/state.py",
      "page_id": "file_page:self-hosted/reliability/state.py",
      "section": "4.22"
    },
    {
      "order": 11,
      "title": "worker.py",
      "kind": "code",
      "reason": "A top churn hotspot — one of the most frequently changed files in the repo; worth understanding early.",
      "target_path": "self-hosted/reliability/worker.py",
      "page_id": "file_page:self-hosted/reliability/worker.py",
      "section": "4.29"
    },
    {
      "order": 12,
      "title": "__init__.py",
      "kind": "code",
      "reason": "The test suite — how the system's behavior is verified.",
      "target_path": "self-hosted/reliability/tests/__init__.py",
      "page_id": "file_page:self-hosted/reliability/tests/__init__.py",
      "section": null
    }
  ],
  "guided_tour_hint": "Topology-ordered walk of the codebase: read these page_ids in order — entry points first, then the files they import, with infrastructure last. Each step builds on the previous.",
  "workspace": {
    "workspace_root": "/workspaces/contour",
    "default_repo": "poh-issue-agents",
    "other_repos": [
      "poh-bft-writer",
      "poh-cortex",
      "poh-helper",
      "poh-infra",
      "poh-memory-engine",
      "poh-pr-agents",
      "poh-scheduller",
      "poh-sprint-agents"
    ],
    "hint": "This repo is part of a workspace. Other repos: poh-bft-writer, poh-cortex, poh-helper, poh-infra, poh-memory-engine, poh-pr-agents, poh-scheduller, poh-sprint-agents. Use repo='<alias>' to query another repo, or repo='all' for workspace-wide results.",
    "cross_repo": {
      "co_change_count": 76,
      "package_dep_count": 0,
      "top_connections": [
        {
          "repos": [
            "poh-bft-writer",
            "poh-issue-agents"
          ],
          "edge_count": 50
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-pr-agents"
          ],
          "edge_count": 10
        },
        {
          "repos": [
            "poh-helper",
            "poh-issue-agents"
          ],
          "edge_count": 7
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-memory-engine"
          ],
          "edge_count": 5
        },
        {
          "repos": [
            "poh-bft-writer",
            "poh-memory-engine"
          ],
          "edge_count": 2
        }
      ]
    },
    "contract_links": {
      "total_contracts": 23,
      "total_links": 0,
      "by_type": {
        "http": 12,
        "data": 11
      }
    }
  },
  "tool_guide": {
    "first_call": "get_answer for any how/where/why question; trust confidence=high directly (it is content-grounded).",
    "reading_code": "get_context(include=[\"skeleton\"]) for a whole file verified, or just Read it. get_symbol only for an id a response already gave you — never file-by-signature.",
    "recipes": [
      "get_answer low confidence → Read best_guesses[0].file",
      "get_context hotspot: true → get_risk before editing",
      "get_context decision_records → get_why(targets=[...]) for rationale",
      "PR review → get_risk(targets, changed_files) and read directive first",
      "search_codebase(query) auto-routes: identifier → symbol hits (pipe symbol_id into get_symbol), path → files (get_context), prose → wiki search. Force with mode=symbol|path|concept|hybrid."
    ],
    "reread_triggers": "Only re-read source on bounds: approximate, stale_warning in _meta, or a search hit whose sources are [fts] only (keyword match, no semantic agreement)."
  },
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 11 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-pr-agents",
  "targets": [
    "self-hosted/reliability/webhook.py",
    "self-hosted/reliability/gateway.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "self-hosted/reliability/webhook.py": {
      "target": "self-hosted/reliability/webhook.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/webhook.py",
        "summary": "Разбор webhook GitHub → список Event (СТ-8)."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 2,
        "last_fix_days_ago": 34
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1145,
        "full_tokens": 1279,
        "pct_of_full": 89.5,
        "bodies_kept": [
          "parse_events",
          "stop_labels_present",
          "enrich_events"
        ],
        "text": "\"\"\"Разбор webhook GitHub → список Event (СТ-8).\n\nОдна доставка PR-события может породить несколько команд (describe+review) —\nдля каждой формируется отдельный Event с уникальным ключом идемпотентности\n`{delivery_id}:{command}` (чтобы dedup и PK работали покомандно).\n\"\"\"\nfrom __future__ import annotations\n\nimport logging\nfrom dataclasses import replace\nfrom typing import Callable\n\nfrom reliability.state import Event\n\nlogger = logging.getLogger(__name__)\n\nDEFAULT_PR_COMMANDS = (\"/describe\", \"/review\")\n... 8 lines (18-25)\nSTOP_LABELS = frozenset({\"pr-closer:closed\", \"agents:off\"})\n\n\ndef stop_labels_present(payload: dict) -> frozenset[str]:\n    \"\"\"Стоп-метки из payload события.\n\n    Читаем и pull_request, и issue: у issue_comment PR приходит под ключом\n    `issue`, и метки лежат там же.\n    \"\"\"\n    names: set[str] = set()\n    for key in (\"pull_request\", \"issue\"):\n        for label in (payload.get(key) or {}).get(\"labels\") or []:\n            name = label.get(\"name\") if isinstance(label, dict) else label\n            if name:\n                names.add(str(name))\n    return frozenset(names & STOP_LABELS)\n\n# (repo, number) -> head_sha (\"\" если issue не является PR / API недоступен)\nFetchHeadSha = Callable[[str, int], str]\n\n\ndef enrich_events(events: list[Event], fetch_head_sha: FetchHeadSha) -> list[Event]:\n    \"\"\"Дозаполнить head_sha для событий без него (issue_comment: в payload sha нет).\n\n    Ключ идемпотентности (business_key) зависит от head_sha, поэтому обогащение\n    ОБЯЗАНО выполняться до record_received/enqueue — иначе строка сохранится с\n    пустым sha и reconcile/дедуп по push сломаются. События, для которых sha так и\n    не получен (issue — не PR, либо API молчит), отбрасываются: ревьюить нечего,\n    а неполный ключ хуже отсутствия события. PR-события уже несут sha → проходят\n    без обращения к API.\n    \"\"\"\n    out: list[Event] = []\n    for e in events:\n        if e.head_sha:\n            out.append(e)\n            continue\n        try:\n            sha = fetch_head_sha(e.repo, e.number)\n        except Exception:\n            # транзиентная ошибка GitHub-API трактуется как 404 (см. модульный\n            # docstring ingress: 500 + бесконечные ретраи доставки — риск против\n            # К-1). Событие отбрасываем; свипер добэкстопит настроенные команды на\n            # открытых PR. Один сбойный fetch не рушит весь батч.\n            ... 4 lines (69-72)\nPR_TRIGGER_ACTIONS = frozenset({\"opened\", \"reopened\", \"ready_for_review\", \"synchronize\"})\n\n\ndef parse_events(event_type: str, delivery_id: str, payload: dict,\n                 pr_commands=DEFAULT_PR_COMMANDS) -> list[Event]:\n    stopped = stop_labels_present(payload)\n    if stopped:\n        # Снятие метки — осознанное действие человека, и оно возвращает PR\n        # в оборот. Пока метка стоит, не запускается ничего, включая явную\n        # команду в комментарии: иначе рубильник переставал бы быть рубильником.\n        logger.info(\"событие пропущено: на PR стоит %s (event=%s delivery=%s)\",\n                    \", \".join(sorted(stopped)), event_type, delivery_id)\n        return []\n\n    if event_type == \"pull_request\":\n        if payload.get(\"action\") not in PR_TRIGGER_ACTIONS:\n            return []\n        pr = payload.get(\"pull_request\") or {}\n        repo = (payload.get(\"repository\") or {}).get(\"full_name\")\n        number = pr.get(\"number\")\n        head_sha = (pr.get(\"head\") or {}).get(\"sha\")\n        if not (repo and number is not None and head_sha):\n            return []  # неполный payload — не выдумываем событие\n        return [\n            Event(delivery_id=f\"{delivery_id}:{cmd}\", repo=repo, number=number,\n                  head_sha=head_sha, command=cmd, event_type=event_type)\n            for cmd in pr_commands\n        ]\n\n    if event_type == \"issue_comment\":\n        if payload.get(\"action\") != \"created\":\n            return []\n        body = ((payload.get(\"comment\") or {}).get(\"body\") or \"\").strip()\n        if not body.startswith(\"/\"):\n            return []\n        cmd = body.split()[0]\n        repo = (payload.get(\"repository\") or {}).get(\"full_name\")\n        number = (payload.get(\"issue\") or {}).get(\"number\")\n        if not (repo and number is not None):\n            return []\n        # head_sha из payload issue_comment недоступен напрямую — обогащается на\n        # следующем шаге (запрос PR по номеру); пока пусто (см. issue #1).\n        head_sha = payload.get(\"_head_sha\", \"\")\n        return [Event(delivery_id=f\"{delivery_id}:{cmd}\", repo=repo, number=number,\n                      head_sha=head_sha, command=cmd, event_type=event_type)]\n\n    return []\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 89.5% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    },
    "self-hosted/reliability/gateway.py": {
      "target": "self-hosted/reliability/gateway.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/gateway.py",
        "summary": "LLM Gateway (СТ-19..24): единая защищённая точка вызова анализа/LLM."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 2,
        "last_fix_days_ago": 29
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1693,
        "full_tokens": 2769,
        "pct_of_full": 61.1,
        "bodies_kept": [
          "GatewayCircuitOpen",
          "record_failure",
          "build_tiered_gateway",
          "try_acquire",
          "__init__"
        ],
        "text": "\"\"\"LLM Gateway (СТ-19..24): единая защищённая точка вызова анализа/LLM.\n\nСтоит между воркером и pr-agent (который ходит в Z.AI). Даёт:\n- **circuit breaker на провайдера** (СТ-22): после N подряд сбоев/таймаутов цепь\n  размыкается → последующие вызовы отказывают МГНОВЕННО (GatewayCircuitOpen), не\n  вися по таймауту. Это backpressure: воркер ОТКЛАДЫВАЕТ PR до восстановления\n  провайдера, а не дедлетерит его провал-комментом (системный простой ≠ дефект PR;\n  иначе один аутейдж Z.AI спамит провалами весь org-wide бэклог). К-3 (не жжём\n  worker-секунды на мёртвый Z.AI) сохраняется; «не молчать» на затяжной простой —\n  эскалация свипера после max_cycles.\n- **token-bucket rate limit** (СТ-20): держим поток запросов под лимитом провайдера;\n  переполнение → backpressure (`RateLimited`), очередь разложит во времени.\n- **failover по пулу провайдеров** (СТ-19/21): пробуем следующий на сбое. Один ключ\n  Z.AI = вырожденный пул из одного провайдера, но seam для добавления ключей готов.\n- **таймаут на попытку** (СТ-14): зависший вызов = сбой цепи, а не вечное ожидание.\n\nРазделение слоёв ретрая (важно, чтобы не было двойного ретрая): gateway делает\nfailover ВШИРЬ (по провайдерам за один вызов), очередь+воркер — ретрай ВГЛУБЬ\n(во времени, backoff/DLQ). Часы/сон/таймаут инъектируются → тесты без реального\nвремени и потоков.\n\n⚠️ Состояние breaker/limiter — ПРОЦЕССНОЕ (in-memory). При N репликах воркера у\nкаждой свой bucket → эффективный RPS ≈ N×rate: на масштабе задавать rate = лимит\nZ.AI / N (или вынести общий limiter в Redis за тем же интерфейсом, как и очередь).\nBreaker тоже per-process — «быстрый отказ» срабатывает независимо на каждой реплике;\nдля одного узла Dokploy (где и SQLite-очередь одноузловая) это приемлемо.\n\"\"\"\nfrom __future__ import annotations\n\nimport enum\nfrom dataclasses import dataclass, field\nfrom typing import Callable, Optional\n\nfrom reliability import metrics, sentry_setup\nfrom reliability.state import Backpressure, Event\n\nInvoke = Callable[[Event], None]  # реальный вызов провайдера; бросает при сбое\n\n\nclass GatewayUnavailable(Exception):\n    \"\"\"Провайдеров РЕАЛЬНО звали (≥1 попытка за этот вызов), но все сбоили. Воркер\n    → nack (ретрай/DLQ+коммент): это «не молчать» для настоящего сбоя попытки.\"\"\"\n\n\nclass GatewayCircuitOpen(Backpressure):\n    \"\"\"Все цепи провайдеров разомкнуты — звонков в этот раз НЕ было (системный\n    простой, уже подтверждённый circuit breaker'ом). Backpressure: воркер ОТЛОЖИТ\n    без счёта к DLQ и без провал-коммента — PR ни при чём. Держим до восстановления\n    провайдера; затяжной простой закрывает эскалация свипера (max_cycles), а не спам\n    провалов на весь бэклог при первом же аутейдже Z.AI.\"\"\"\n\n\nclass RateLimited(Backpressure):\n    \"\"\"Превышен локальный лимит запросов — backpressure: воркер отложит без счёта\n    к DLQ и без ложного коммента о провале (не сбой, а сдерживание потока).\"\"\"\n\n\nclass Circuit(str, enum.Enum):\n    ... 3 lines (59-61)\n\n\nclass CircuitBreaker:\n    \"\"\"Размыкается после `failure_threshold` подряд сбоев; через `reset_timeout`\n    ... 3 lines (66-68)\n    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0,\n                 clock: Callable[[], float] = None):\n        import time\n        self._threshold = failure_threshold\n        self._reset = reset_timeout\n        self._clock = clock or time.monotonic\n        self._failures = 0\n        self._state = Circuit.CLOSED\n        self._opened_at = 0.0\n\n    @property\n    def state(self) -> Circuit:\n        ... 4 lines (81-84)\n\n    def allow(self) -> bool:\n        return self.state != Circuit.OPEN  # CLOSED и HALF_OPEN пропускают\n\n    def record_success(self) -> None:\n        self._failures = 0\n        self._state = Circuit.CLOSED\n\n    def record_failure(self) -> None:\n        # сбой пробы в HALF_OPEN → сразу назад в OPEN (не ждём порога)\n        if self.state == Circuit.HALF_OPEN:\n            self._state = Circuit.OPEN\n            self._opened_at = self._clock()\n            return\n        self._failures += 1\n        if self._failures >= self._threshold:\n            self._state = Circuit.OPEN\n            self._opened_at = self._clock()\n\n\nclass TokenBucket:\n    \"\"\"Классический token-bucket: `rate` токенов/сек, ёмкость `capacity`.\n    `try_acquire()` неблокирующий — вернёт False, если токенов нет (backpressure).\"\"\"\n\n    def __init__(self, rate: float, capacity: float,\n                 clock: Callable[[], float] = None):\n        ... 6 lines (111-116)\n\n    def _refill(self) -> None:\n        ... 3 lines (119-121)\n\n    def try_acquire(self, cost: float = 1.0) -> bool:\n        self._refill()\n        if self._tokens >= cost:\n            self._tokens -= cost\n            return True\n        return False\n\n\n@dataclass\nclass Provider:\n    ... 3 lines (133-135)\n\n\n# Механизм таймаута попытки инъектируется (как в worker) → тесты без потоков.\ndef _default_run_fn(fn: Callable, timeout: float):  # pragma: no cover - реальные потоки\n    from reliability.worker import run_with_timeout\n    return run_with_timeout(fn, timeout)\n\n\nclass Gateway:\n    def __init__(self, providers: list[Provider], *, limiter: Optional[TokenBucket] = None,\n                 attempt_timeout: float = 75.0, run_fn: Callable = _default_run_fn):\n        ... 6 lines (147-152)\n\n    def run(self, event: Event) -> None:\n        \"\"\"analyze-совместимый вход: провести анализ через защищённый пул.\n        ... 44 lines (156-199)\n\n\nclass TieredGateway:\n    \"\"\"Тиринг моделей (ФТ-APRP-10 / СТ-24): маршрутизация вызова к УРОВНЮ модели.\n... 6 lines (204-209)\n    def __init__(self, tiers: dict):\n        ... 3 lines (211-213)\n\n    def run(self, event: Event, tier: str = \"deep\") -> None:\n        ... 4 lines (216-219)\n\n    def tiers(self) -> list:\n        return list(self._tiers)\n\n\ndef build_tiered_gateway(specs: list, *, run_fn: Callable = _default_run_fn) -> TieredGateway:\n    \"\"\"Собрать TieredGateway из data-driven спецификаций уровней (M5).\n\n    spec: {tier, name, invoke, attempt_timeout, rate?, burst?, cb_threshold?, cb_reset?}.\n    Пример: [{tier:'deep', name:'glm-5', invoke:..., attempt_timeout:200},\n             {tier:'cheap', name:'glm-4.7', invoke:..., attempt_timeout:40}].\"\"\"\n    tiers: dict = {}\n    for s in specs:\n        breaker = CircuitBreaker(failure_threshold=s.get(\"cb_threshold\", 5),\n                                 reset_timeout=s.get(\"cb_reset\", 30.0))\n        limiter = (TokenBucket(rate=s[\"rate\"], capacity=s.get(\"burst\", s[\"rate\"]))\n                   if s.get(\"rate\") else None)\n        tiers[s[\"tier\"]] = Gateway([Provider(s[\"name\"], s[\"invoke\"], breaker=breaker)],\n                                   limiter=limiter,\n                                   attempt_timeout=s.get(\"attempt_timeout\", 75.0),\n                                   run_fn=run_fn)\n    return TieredGateway(tiers)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 61.1% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 66.78,
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 12 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "agent_event delivery poh-issue-agents webhook report back",
  "repo": "poh-pr-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Repository Overview: poh-pr-agents",
      "page_type": "repo_overview",
      "snippet": "# Repository Overview: poh-pr-agents\n\n**Files:** 87 | **Lines:** 15233 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-pr-agents` is a python codebase of 87 files. Execution starts at `self-hosted/r",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "poh-pr-agents",
      "type": "page"
    },
    {
      "title": "File: self-hosted/reliability/webhook.py",
      "page_type": "file_page",
      "snippet": "# self-hosted/reliability/webhook.py\n\n## Overview\n\nРазбор webhook GitHub → список Event (СТ-8).\n\nОдна доставка PR-события может породить несколько команд (describe+review) —\nдля каждой формируется отд",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "self-hosted/reliability/webhook.py",
      "type": "page"
    },
    {
      "title": "Key Concepts",
      "page_type": "onboarding",
      "snippet": "# Key Concepts\n\nThe types and functions the rest of `poh-pr-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanation",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/key_concepts",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "self-hosted/reliability/agent_event.py::AGENT",
      "name": "AGENT",
      "kind": "constant",
      "file": "self-hosted/reliability/agent_event.py",
      "start_line": 37,
      "end_line": 37,
      "signature": "AGENT = \"pr-agent\"",
      "qualified_name": "self-hosted.reliability.agent_event.AGENT",
      "language": "python",
      "score": 100.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "self-hosted/reliability/agent_event.py::build_payload",
      "name": "build_payload",
      "kind": "function",
      "file": "self-hosted/reliability/agent_event.py",
      "start_line": 72,
      "end_line": 86,
      "signature": "def build_payload(repo: str, pr_number: int, status: str, *,\n                  root_issue: Optional[int] = None, detail: str = \"\") -> dict",
      "qualified_name": "self-hosted.reliability.agent_event.build_payload",
      "language": "python",
      "score": 60.05,
      "next": "get_symbol"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "self-hosted/reliability/webhook.py"
    },
    {
      "path": "self-hosted/reliability/agent_event.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'agent_event'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 13 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-pr-agents",
  "targets": [
    "self-hosted/reliability/agent_event.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "self-hosted/reliability/agent_event.py": {
      "target": "self-hosted/reliability/agent_event.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/agent_event.py",
        "summary": "Доклад PR-Agent в цикл Issue (точка передачи H3 протокола агентов)."
      },
      "hotspot": false,
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1141,
        "full_tokens": 1216,
        "pct_of_full": 93.8,
        "bodies_kept": [
          "build_payload",
          "parse_root_issue",
          "report"
        ],
        "text": "\"\"\"Доклад PR-Agent в цикл Issue (точка передачи H3 протокола агентов).\n\nIssue-Agent держит задачу живым Temporal-workflow и после открытия PR ждёт в\nфазе `pr-open`. Без доклада отсюда он там и остаётся: своих вебхуков по PR он не\nслушает намеренно — фазу двигает тот, кто выполнил работу, а не тот, кто мимо\nпроходил.\n\nКонтракт узкий и односторонний: `POST /agent-event` с HMAC-подписью, конверт\n`{repo, agent, phase, status, ref, root_issue?, detail?}`. Temporal сюда не\nвтаскивается — у этого сервиса свой релизный цикл, и знание чужих workflow id\nбыло бы ровно той связностью, ради ухода от которой контракт и заводился.\n\nДоклад — вспомогательный канал, и он НИКОГДА не роняет обработку. Ревью уже\nопубликовано; уронить его из-за недоступного соседа значило бы обменять\nсделанную работу на несделанный доклад.\n\nСекрет и адрес берутся из окружения. Не задан любой из двух — канал выключен\nцеликом: это и есть процедура отката.\n\"\"\"\nfrom __future__ import annotations\n\nimport hashlib\nimport hmac\nimport json\nimport logging\nimport os\nimport re\nimport urllib.request\nfrom typing import Callable, Optional\n\nlogger = logging.getLogger(\"reliability.agent_event\")\n\n# (method, url, data, headers) -> (status, body) — тот же Transport, что и в\n# github_client: модуль тестируется без сети.\nTransport = Callable[[str, str, \"Optional[bytes]\", dict], \"tuple[int, bytes]\"]\n\nAGENT = \"pr-agent\"\n\n# Фаза, о которой докладывает именно этот сервис. Другие фазы пути (`merged`,\n# `testing`) ведут соседи, и присваивать их себе означало бы врать таймлайну.\nPHASE = \"pr-review\"\n\nSTARTED = \"started\"\nFAILED = \"failed\"\n\n# Формы, которые GitHub считает закрывающими. Держим их же: расхождение означало\n# бы, что PR закрывает Issue, а контур этого не видит.\n_CLOSES_RE = re.compile(\n    r\"\\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\\s*:?\\s*#(\\d+)\", re.IGNORECASE)\n\n\ndef _urllib_transport(method: str, url: str, data, headers):  # pragma: no cover\n    ... 3 lines (53-55)\n\n\ndef parse_root_issue(pr_body: str | None) -> Optional[int]:\n    \"\"\"Номер задачи из `Closes #N` в теле PR, иначе None.\n\n    Несколько закрываемых Issue — НЕ повод выбрать первый: привязать работу не к\n    той задаче значит испортить трассировку сразу двум. Такой случай уходит без\n    ключа, и Issue-Agent разберётся сам (у него та же развилка) либо запишет\n    сироту.\n    \"\"\"\n    if not pr_body:\n        return None\n    found = {int(n) for n in _CLOSES_RE.findall(pr_body)}\n    return found.pop() if len(found) == 1 else None\n\n\ndef build_payload(repo: str, pr_number: int, status: str, *,\n                  root_issue: Optional[int] = None, detail: str = \"\") -> dict:\n    payload = {\n        \"repo\": repo,\n        \"agent\": AGENT,\n        \"phase\": PHASE,\n        \"status\": status,\n        # `ref` — то, о чём событие. Номер PR: он же половина ключа\n        # идемпотентности на стороне цикла, поэтому строкой и без префикса.\n        \"ref\": str(pr_number),\n        \"detail\": detail,\n    }\n    if root_issue is not None:\n        payload[\"root_issue\"] = root_issue\n    return payload\n\n\ndef sign(secret: str, body: bytes) -> str:\n    return \"sha256=\" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()\n\n\ndef configured(env=None) -> bool:\n    ... 3 lines (94-96)\n\n\ndef report(repo: str, pr_number: int, status: str, *, root_issue: Optional[int] = None,\n           detail: str = \"\", env=None, transport: Transport = _urllib_transport) -> bool:\n    \"\"\"Отправляет событие. Возвращает, дошло ли. Не поднимает исключений.\n\n    Ошибку логируем предупреждением, а не роняем воркер: сосед мог быть\n    недоступен, а ревью в PR уже лежит и от нашего доклада не зависит.\n    \"\"\"\n    env = env if env is not None else os.environ\n    if not configured(env):\n        return False\n\n    url = env[\"ISSUE_AGENT_URL\"].strip().rstrip(\"/\") + \"/agent-event\"\n    body = json.dumps(build_payload(repo, pr_number, status,\n                                    root_issue=root_issue, detail=detail)).encode()\n    headers = {\n        \"Content-Type\": \"application/json\",\n        \"X-Agent-Signature-256\": sign(env[\"AGENT_EVENT_SECRET\"].strip(), body),\n        \"User-Agent\": \"pr-agent-reliability\",\n    }\n    try:\n        code, resp = transport(\"POST\", url, body, headers)\n    except Exception as exc:\n        logger.warning(\"доклад в цикл Issue не ушёл (%s#%s, %s): %s\",\n                       repo, pr_number, status, exc)\n        return False\n    if code >= 300:\n        logger.warning(\"цикл Issue отклонил доклад (%s#%s, %s): %s %r\",\n                       repo, pr_number, status, code, resp[:200])\n        return False\n    return True\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 93.8% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 35.63,
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "id": "repowise#9a8693ecf93c",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "repowise#9a8693ecf93c",
  "ref": "9a8693ecf93c",
  "kind": "omission",
  "source": "mcp:get_context",
  "original_tokens": 1463,
  "content": "\"\"\"Модель фаз жизненного цикла Issue — единственный источник правды.\n\nСегодня состояние Issue размазано по четырём независимым представлениям (метки,\nпеременные воркфлоу, комментарии, Event History), и ни одно не покрывает путь\nдальше приоритизации. Этот модуль вводит один перечень фаз и одну таблицу\nпереходов; из них выводятся значения query, метки в GitHub, search attribute и\nстроки таймлайна. Иначе каждая подзадача эпика заведёт свои названия, и\nтрассировка будет собирать таймлайн из несовместимых кусков.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как `estimation.py`.\nЛогика состояний проверяется напрямую, а не через прогон воркфлоу.\n\nИменование согласовано с уже внедрёнными словарями: namespace через двоеточие,\nкак `needs-human:*` и `run:*`/`done:*` (протокол агентов v1, задачи #30 и #33).\nФаза в GitHub — метка `phase:<имя>`.\n\"\"\"\n\nfrom dataclasses import dataclass\n\n# --- Основной путь: от создания до прода ---\n\nCREATED = \"created\"\nCLASSIFIED = \"classified\"\nBUSINESS_ANALYSIS = \"business-analysis\"\nSYSTEM_REQUIREMENTS = \"system-requirements\"\nGROOMED = \"groomed\"\nREADY_FOR_DEV = \"ready-for-dev\"\nIN_DEVELOPMENT = \"in-development\"\nPR_OPEN = \"pr-open\"\nPR_REVIEW = \"pr-review\"\nMERGED = \"merged\"\nTESTING = \"testing\"\nRELEASED = \"released\"\n\n# --- Боковые состояния: сегодня существуют де-факто, но нигде не названы ---\n\nSPAM = \"spam\"                # intake gate распознал спам, issue закрыт\nDUPLICATE = \"duplicate\"      # дубликат: решение о закрытии за человеком\nANSWERED = \"answered\"        # классификация закрыла содержательным ответом\nSKIPPED = \"skipped\"          # предфильтр: бот или security-sensitive\nESCALATED = \"escalated\"      # ушло человеку (needs-human:*)\nFAILED = \"failed\"            # стадия сорвалась, нужен разбор\nCANCELLED = \"cancelled\"      # снято с обработки решением человека\n\n# Кто инициирует переход. Различать обязательно: «ждём агента» и «ждём человека» —\n# это разные состояния для того, кто смотрит на очередь.\nAGENT = \"agent\"        # сам Issue-Agent по завершении своей стадии\nHUMAN = \"human\"        # метка или команда человека\nEXTERNAL = \"external\"  # PR-Agent, PR-Closer, CI — внешняя система контура\n\n\n@dataclass(frozen=True)\nclass Transition:\n    ... 8 lines (54-61)\nTERMINAL = frozenset({RELEASED, CANCELLED})\n... 7 lines (63-69)\nTRANSITIONS: dict[str, tuple[Transition, ...]] = {\n    CREATED: (\n        Transition(CLASSIFIED, AGENT, \"триаж завершён\"),\n        Transition(SKIPPED, AGENT, \"предфильтр: бот или security-sensitive\"),\n        Transition(SPAM, AGENT, \"intake gate: спам\"),\n        # Дедуп и advisor-ответ — шаги ВНУТРИ триажа, поэтому их исход виден из\n        # `created`, а не только из `classified`: до конца триажа Issue ещё не\n        # классифицирован формально.\n        Transition(DUPLICATE, AGENT, \"duplicate-check\"),\n        Transition(ANSWERED, AGENT, \"advisor:consultation / existing-functionality\"),\n        Transition(ESCALATED, AGENT, \"не удалось сузить запрос\"),\n        Transition(FAILED, AGENT, \"сбой стадии\"),\n        ... 129 lines (82-210)\n\nPHASES: tuple[str, ...] = tuple(TRANSITIONS)\n\n# Метка фазы в GitHub. Инвариант: одна фаза — ровно одна метка `phase:*`, при\n# переходе предыдущая снимается. Без этого по меткам нельзя восстановить\n# состояние: два `phase:*` на Issue означали бы противоречие, а не историю.\nPHASE_PREFIX = \"phase:\"\n\n# Мост от значений query `stage` (#29) к фазам. Нужен на время перехода: пока\n# `IssueLifecycle` линейный (#36 ещё не сделана), стадия — единственное, что\n# воркфлоу знает о себе.\nSTAGE_TO_PHASE: dict[str, str] = {\n    \"intake\": CREATED,\n    \"classify\": CREATED,\n    \"duplicate-check\": CLASSIFIED,\n    \"priority\": CLASSIFIED,\n    \"awaiting-human-decision\": CLASSIFIED,\n    \"analysis\": BUSINESS_ANALYSIS,\n    \"bug\": READY_FOR_DEV,\n    \"awaiting-build-decision\": READY_FOR_DEV,\n    \"done\": READY_FOR_DEV,\n    \"skipped\": SKIPPED,\n    \"spam\": SPAM,\n    ... 17 lines (234-250)\n\n\nclass InvalidTransition(ValueError):\n    \"\"\"Недопустимый переход — ошибка, а не молчаливая перезапись фазы.\n\n    Молчаливая запись любой фазы поверх любой означала бы, что модель ничего не\n    гарантирует: Issue оказывался бы в состоянии, из которого не выводится ни\n    предыстория, ни следующий шаг.\n    \"\"\"\n\n\ndef phase_label(phase: str) -> str:\n    return f\"{PHASE_PREFIX}{phase}\"\n\n\ndef phase_from_labels(labels: list[str]) -> str | None:\n    \"\"\"Фаза по набору меток Issue, иначе None.\n\n    Инвариант «одна фаза — одна метка» проверяется здесь же: две метки `phase:*`\n    означают противоречие, и мы отказываемся угадывать, какая из них настоящая.\n    \"\"\"\n    found = [name[len(PHASE_PREFIX):].lower() for name in labels\n             if name.lower().startswith(PHASE_PREFIX)]\n    known = [name for name in found if name in TRANSITIONS]\n    if len(known) != 1:\n        return None\n    return known[0]\n\n\ndef is_terminal(phase: str) -> bool:\n    return phase in TERMINAL\n\n\ndef allowed(phase: str) -> tuple[Transition, ...]:\n    \"\"\"Переходы, возможные из фазы. Неизвестная фаза — ошибка модели.\"\"\"\n    ... 3 lines (286-288)\n\n\ndef can(source: str, target: str) -> bool:\n    return any(t.to == target for t in allowed(source))\n\n\ndef transition(source: str, target: str) -> Transition:\n    \"\"\"Переход или InvalidTransition с перечнем допустимых — сообщение должно\n    само говорить, что было возможно вместо этого.\"\"\"\n    for candidate in allowed(source):\n        if candidate.to == target:\n            return candidate\n    options = \", \".join(t.to for t in allowed(source)) or \"—\"\n    raise InvalidTransition(\n        f\"переход {source} → {target} не предусмотрен; допустимо: {options}\")\n\n\ndef initiator(source: str, target: str) -> str:\n    return transition(source, target).initiator\n\n\ndef reachable_from(start: str = CREATED) -> set[str]:\n    \"\"\"Фазы, достижимые из start. Используется тестом полноты: фаза, до которой\n    ... 10 lines (312-321)\n",
  "_meta": {
    "timing_ms": 6.88,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "created_at": "2026-08-21T10:52:59.465501+00:00"
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "mode": "symbol",
  "query": "PR_REVIEW MERGED TESTING RELEASED transition"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::transition",
      "name": "transition",
      "kind": "function",
      "file": "shared/lifecycle.py",
      "start_line": 295,
      "end_line": 303,
      "signature": "def transition(source: str, target: str) -> Transition",
      "qualified_name": "shared.lifecycle.transition",
      "language": "python",
      "score": 45.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::Transition",
      "name": "Transition",
      "kind": "class",
      "file": "shared/lifecycle.py",
      "start_line": 53,
      "end_line": 56,
      "signature": "class Transition",
      "qualified_name": "shared.lifecycle.Transition",
      "language": "python",
      "score": 45.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/awaiting.py::TESTING",
      "name": "TESTING",
      "kind": "constant",
      "file": "shared/awaiting.py",
      "start_line": 25,
      "end_line": 25,
      "signature": "TESTING = \"testing\"",
      "qualified_name": "shared.awaiting.TESTING",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::MERGED",
      "name": "MERGED",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "MERGED = \"merged\"",
      "qualified_name": "shared.lifecycle.MERGED",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::RELEASED",
      "name": "RELEASED",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 33,
      "end_line": 33,
      "signature": "RELEASED = \"released\"",
      "qualified_name": "shared.lifecycle.RELEASED",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "shared/awaiting.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'PR_REVIEW MERGED TESTING RELEASED transition'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 16 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "targets": [
    "shared/awaiting.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/awaiting.py": {
      "target": "shared/awaiting.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/awaiting.py",
        "summary": "Ожидание как первоклассное состояние: кого ждём, с какого момента, до какого срока."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 2
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1214,
        "full_tokens": 2254,
        "pct_of_full": 53.9,
        "bodies_kept": [
          "InvalidAwaiting",
          "deadline_hours",
          "describe",
          "DEFAULT_DEADLINE_HOURS",
          "__post_init__"
        ],
        "text": "\"\"\"Ожидание как первоклассное состояние: кого ждём, с какого момента, до какого срока.\n\nСегодня все ожидания выглядят одинаково — как их отсутствие. Прогон,\nприпаркованный до решения человека, в Temporal UI просто `Running`; на Issue\nвидна метка приоритета, из которой не следует, что ход за человеком; а сбой\nвообще не был ожиданием — он вешал метку и закрывал прогон.\n\nФаза (#35) отвечает на вопрос «где Issue», это состояние работы. `Awaiting`\nотвечает на другой — «почему он там стоит и кто его сдвинет». Одна фаза может\nждать разного: `failed` ждёт решения человека о перезапуске, `pr-review` — что\nвнешний агент доведёт ревью. Мешать это в одну ось значило бы либо плодить\nфазы под каждую причину, либо терять причину.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub.\n\"\"\"\n\nfrom dataclasses import dataclass\n\nfrom shared import lifecycle\n\n# --- Виды ожидания ---\n\nHUMAN_DECISION = \"human-decision\"        # ждём метку/команду человека\nAPPROVAL = \"approval\"                    # ждём приёмку сделанного\nTESTING = \"testing\"                      # ждём прогон на стенде\nEXTERNAL_AGENT = \"external-agent\"        # ждём соседний сервис контура\nFAILURE_RECOVERY = \"failure-recovery\"    # шаг сорвался, ждём решения человека\n\nKINDS: tuple[str, ...] = (HUMAN_DECISION, APPROVAL, TESTING,\n                          EXTERNAL_AGENT, FAILURE_RECOVERY)\n... 5 lines (31-35)\nBLOCKED_ON_HUMAN: frozenset[str] = frozenset({HUMAN_DECISION, APPROVAL, FAILURE_RECOVERY})\n... 10 lines (37-46)\nDEFAULT_DEADLINE_HOURS: dict[str, int] = {\n    HUMAN_DECISION: 72,      # решение о тяжёлой стадии: рабочие сутки плюс выходные\n    APPROVAL: 72,            # приёмка — то же ожидание человека, что и решение\n    TESTING: 48,             # прогон на стенде: дольше суток означает, что он завис\n    EXTERNAL_AGENT: 24,      # сосед либо отвечает быстро, либо не отвечает вовсе\n    FAILURE_RECOVERY: 168,   # разбор сбоя реже срочный; неделя — чтобы не потерялся\n}\n\n\nclass InvalidAwaiting(ValueError):\n    \"\"\"Ожидание описано некорректно.\n\n    Отдельный тип: фаза ожидания без заполненного `Awaiting` — ошибка, а не\n    пустое поле. Молчаливое «ждём неизвестно чего» и есть то состояние, ради\n    ухода от которого задача ставилась.\n    \"\"\"\n\n\n@dataclass\nclass Awaiting:\n    \"\"\"Чего ждёт Issue прямо сейчас.\n... 16 lines (68-83)\n    def __post_init__(self) -> None:\n        if self.kind not in KINDS:\n            raise InvalidAwaiting(\n                f\"вид ожидания {self.kind!r} не из перечня; допустимо: {', '.join(KINDS)}\")\n        if not str(self.reason).strip():\n            raise InvalidAwaiting(\"ожидание без причины: человек не поймёт, чего от него ждут\")\n        if not str(self.who).strip():\n            raise InvalidAwaiting(\"ожидание без адресата: непонятно, кто его снимет\")\n\n    @property\n    def blocks_on_human(self) -> bool:\n        return self.kind in BLOCKED_ON_HUMAN\n\n    def waited_hours(self, now_epoch: float) -> float:\n        return max(0.0, (now_epoch - self.since_epoch) / 3600)\n\n    def remaining_hours(self, now_epoch: float) -> float | None:\n        \"\"\"Сколько ещё ждать. None — ожидание без срока.\"\"\"\n        ... 3 lines (102-104)\n\n    def expired(self, now_epoch: float) -> bool:\n        return bool(self.deadline_epoch) and now_epoch >= self.deadline_epoch\n\n    def describe(self, now_epoch: float) -> str:\n        \"\"\"Строка для человека: чего ждём, от кого, сколько уже и сколько осталось.\"\"\"\n        parts = [self.reason, f\"ждём: {self.who}\", f\"уже {self.waited_hours(now_epoch):.0f} ч\"]\n        left = self.remaining_hours(now_epoch)\n        parts.append(\"без срока\" if left is None else f\"осталось {left:.0f} ч\")\n        return \"; \".join(parts)\n\n\ndef deadline_hours(kind: str, override: int | None = None) -> int:\n    \"\"\"Срок ожидания: переопределение сильнее таблицы по умолчанию.\n\n    Переопределение нужно там, где срок уже настраивается оператором\n    (`PARK_*_HOURS`): две независимые ручки на один таймер разъехались бы при\n    первой же правке одной из них.\n    \"\"\"\n    if override is not None and override > 0:\n        return override\n    if kind not in DEFAULT_DEADLINE_HOURS:\n        raise InvalidAwaiting(f\"нет срока по умолчанию для вида {kind!r}\")\n    return DEFAULT_DEADLINE_HOURS[kind]\n... 10 lines (129-138)\nKIND_BY_PHASE: dict[str, str] = {\n    ... 28 lines (140-167)\nWORKED_BY_AGENT: frozenset[str] = frozenset({\n    lifecycle.CREATED, lifecycle.BUSINESS_ANALYSIS, lifecycle.SYSTEM_REQUIREMENTS,\n})\n\nWHO_BY_KIND: dict[str, str] = {\n    ... 6 lines (173-178)\n\nREASON_BY_PHASE: dict[str, str] = {\n    ... 16 lines (181-196)\n\n\ndef kind_for_phase(phase: str) -> str:\n    return KIND_BY_PHASE.get(phase, HUMAN_DECISION)\n\n\ndef who_for_phase(phase: str) -> str:\n    return WHO_BY_KIND[kind_for_phase(phase)]\n\n\ndef reason_for_phase(phase: str) -> str:\n    return REASON_BY_PHASE.get(phase, f\"событие, двигающее фазу `{phase}`\")\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 53.9% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 33.07,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
