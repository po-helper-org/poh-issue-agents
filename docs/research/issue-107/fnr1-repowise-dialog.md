# Итог

## Собранные факты

### 1. Текущая структура конфигурации агентов (`.claude/`)
- **poh-issue-agents**: `.claude/skills/` (архитектурные навыки, brainstorming, systematic-debugging, writing-skills), `.claude/commands/` (bft-*, fnr-*, repowise-context)
- **poh-bft-writer**: отдельный репозиторий с вынесенными навыками БФТ (`skills/bft-fast`, `skills/bft-writer`, `skills/bft-deep-swarm`), `commands/` (bft-concept, bft-context-gen, bft-debate, bft-deep, bft-deliver)
- **Формат**: frontmatter (description) + детальные инструкции для LLM, структурированные по этапам/шагам
- **Пример**: `.claude/commands/bft-context-gen.md` — 170 строк, 13 заголовков, явная инструкция для LLM с разделением факт/вывод

### 2. Механизмы share контента между репозиториями
- **Cross-repo связи**: только behavioural (co-change count: 76), structural (package) зависимостей нет
- **Top connections**: poh-bft-writer ↔ poh-issue-agents (50), poh-issue-agents ↔ poh-pr-agents (10), poh-helper ↔ poh-issue-agents (7)
- **Вывод**: репозитории развиваются независимо но меняются согласованно; нет механизма git submodule/tree/vendoring

### 3. Пример структурированного индекса (`.bft/index/`)
- **Схема** [`.claude/skills/bft-indexer/resources/index_schema.md`](.claude/skills/bft-indexer/resources/index_schema.md:1):
  - `MANIFEST.md` — карта покрытия (источник | тип | статус | дата | охват)
  - `architecture.md` — компоненты, сервисы, интеграции с якорями
  - `domain-rules.md` — бизнес-правила с якорями
  - `decisions.md` — ADR и решения
  - `regulatory.md` — compliance/регуляторика
  - `glossary.md` — термины с якорями
  - `stakeholders.md` — роли/команды/владельцы
  - `sources.md` — реестр якорей (id → полный источник)
- **Принцип**: пусто ≠ «нет данных» — UNAVAILABLE помечается явно

### 4. MCP как механизм подключения контента
- **[`shared/repowise.py`](shared/repowise.py:1)**: клиент MCP-прокси для доступа к индексу кода
  - Прокси между агентами и MCP-эндпоинтами
  - Маршрутизация по workspace (`contour` vs `product`)
  - Токен и идентификатор сессии
  - Журналирование каждого обмена
  - Артефакт диалога (транскрипт) рендерится прокси — полота свойство построения
  - Деградация штатна при недоступности: [`unavailable_artifact()`](shared/repowise.py:189)

### 5. Workspace-архитектура
- **9 репозиториев**: poh-issue-agents (default), poh-bft-writer, poh-cortex, poh-helper, poh-infra, poh-memory-engine, poh-pr-agents, poh-scheduller, poh-sprint-agents
- **Workspace root**: `/workspaces/contour`
- **Cross-repo contract links**: 23 контракта (HTTP: 12, data: 11)

### 6. Hotspot файла (для risk assessment)
- **poh-issue-agents**: `worker/workflows.py` (score: 1.0), 24 hotspots (high-churn + high-complexity)
- **poh-bft-writer**: `commands/bft-fast.md` (score: 6.5), 9 hotspots
- **poh-helper**: `sa_documentation/validate_ground.py` (score: 3.51)

### 7. Git health
- **poh-issue-agents**: 39 hotspots, churn trend: increasing, avg bus factor: 0.6, 108 файлов с bus factor 1
- **poh-bft-writer**: 9 hotspots, avg bus factor: 0.5, 27 файлов с bus factor 1
- **poh-helper**: 5 hotspots, churn trend: decreasing, avg bus factor: 1.0

## Открытые вопросы

1. **PR #97/#105**: индекс не содержит информации об упомянутых architectural inconsistency (обход декларативных паттернов хардкодом)
2. **Issue #70 (poh-sysreq-agent)**: прямых упоминаний нет; идея вынесения общего контента подтверждается существованием poh-bft-writer
3. **MetaReviewer #92**: прямых упоминаний нет; механизм self-improvement контура не найден в индексе
4. **Механизм локального уточнения**: не найдены примеры локальных файлов, расширяющих/переопределяющих центральные правила
5. **Валидация контента**: не найдены примеры ревью человеком или автоматической проверки правил на противоречия/двусмысленность
6. **Git submodule/tree/vendoring**: не найдены примеры использования в воркспейсе

## Диалог

### Ход 1: Overview + List repos
**Инструмент**: `get_overview()`, `list_repos()`
**Результат**: Обзор poh-issue-agents (323 файла, 80733 строк, 1 цикл импорта), список 9 репозиториев в workspace, cross-repo связи (co-change: 76)

### Ход 2: Структура `.claude/`
**Инструмент**: `search_codebase(".claude skills commands settings configuration")`
**Результат**: Найдены `.claude/skills/architecture/scripts`, `.claude/commands`, `.claude/skills` с множеством навыков

### Ход 3: Контекст `.claude/` и `.bft/index/`
**Инструмент**: `get_context([".claude", ".claude/skills", ".claude/commands"])`
**Результат**: `.claude/commands` найден, `.bft/index` не найден напрямую (предложения: `.claude/commands/bft-index.md`, `.claude/skills/bft-indexer/SKILL.md`)

### Ход 4: Схема индекса `.bft/index/`
**Инструмент**: `get_context([".claude/skills/bft-indexer/resources/index_schema.md"])`
**Результат**: Получена схема индекса (MANIFEST, architecture, domain-rules, decisions, regulatory, glossary, stakeholders, sources)

### Ход 5: Поиск issue #70, MetaReviewer #92
**Инструмент**: `search_codebase("issue 70 poh-sysreq-agent")`, `search_codebase("MetaReviewer 92 self-improvement validation")`
**Результат**: Прямых упоминаний нет; найдены `shared/repos.py` (список репозиториев), `worker/estimation.py::EstimationFacts`, `shared/bft.py`

### Ход 6: Overview соседних репозиториев
**Инструмент**: `get_overview(repo="poh-bft-writer")`, `get_overview(repo="poh-helper")`
**Результат**: poh-bft-writer (54 файла, 15621 строк, healthy), poh-helper (548 файлов, 172065 строк, healthy); подтверждена cross-repo топология

### Ход 7: Blast radius для cross-repo связей
**Инструмент**: `get_blast_radius(["poh-issue-agents"], max_depth=2)`
**Результат**: 6 downstream services impacted через co-change только; structural зависимостей нет

### Ход 8: Структура poh-bft-writer skills/commands
**Инструмент**: `get_context(["skills", "commands"], repo="poh-bft-writer")`
**Результат**: Найдены `commands/bft-context-gen.md`, `skills/bft-deep-swarm/SKILL.md`; формат команд с frontmatter

### Ход 9: Детали команды bft-context-gen
**Инструмент**: `get_context(["commands/bft-context-gen.md"], repo="poh-bft-writer")`
**Результат**: Полный формат команды (170 строк): frontmatter + использование + примеры + инструкция для LLM (6 этапов)

### Ход 10: Поиск CLAUDE.md и git submodule
**Инструмент**: `search_codebase("CLAUDE.md system prompt context injection")`, `search_codebase("git submodule subtree vendor dependency")`
**Результат**: Найдены `worker/activities.py` (PROMPTS_DIR, CONFIG_DIR), `.claude/skills/architecture/scripts/generate_taxonomy.py` (vendor-папки); submodule не найден

### Ход 11: Поиск MCP серверов
**Инструмент**: `search_codebase("MCP server tool validation review content check")`
**Результат**: Найден `shared/repowise.py` — клиент MCP-прокси

### Ход 12: Детали repowise.py
**Инструмент**: `get_context(["shared/repowise.py"], include=["skeleton"])`
**Результат**: Получена структура MCP-клиента: прокси, маршрутизация по workspace, токен/сессия, журналирование, деградация

---

**Источник**: индекс Repowise (commit: a41f569f0381, 2026-08-21)
**Репозиторий**: poh-issue-agents (workspace: contour)
**Ходов**: 12 из 12


---
session: rw-analysis-po-helper-org__poh-issue-agents-107
workspace: contour
turns: 18
started: 2026-08-21T08:15:47Z
finished: 2026-08-21T08:16:37Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 33 мин |
| `poh-helper` | `18512c1e7ce9` | 33 мин |
| `poh-issue-agents` | `a41f569f0381` | 33 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
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
    "average_health": 8.36,
    "band": "healthy",
    "hotspot_health": 5.11,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 445,
    "file_count": 344,
    "distribution": {
      "total_files": 344,
      "total_nloc": 48406,
      "bands": {
        "healthy": {
          "files": 307,
          "nloc": 36317,
          "pct": 75.0
        },
        "warning": {
          "files": 33,
          "nloc": 7070,
          "pct": 14.6
        },
        "alert": {
          "files": 4,
          "nloc": 5019,
          "pct": 10.4
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
    "files_git_attributed": 347,
    "hotspot_count": 39,
    "avg_bus_factor": 0.6,
    "files_with_bus_factor_1": 108,
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
        "percentage": 23.6
      },
      {
        "name": "kibarik",
        "files_owned": 69,
        "percentage": 19.9
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
      "size": 13
    },
    {
      "id": 1,
      "label": "tests (37)",
      "size": 8
    },
    {
      "id": 2,
      "label": "server",
      "size": 7
    },
    {
      "id": 3,
      "label": "tests (23)",
      "size": 7
    },
    {
      "id": 4,
      "label": "worker",
      "size": 4
    },
    {
      "id": 5,
      "label": "external:~/threads",
      "size": 3
    },
    {
      "id": 6,
      "label": "tests (5)",
      "size": 3
    },
    {
      "id": 7,
      "label": "claude",
      "size": 1
    },
    {
      "id": 8,
      "label": "installed_skills",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands",
      "size": 1
    }
  ],
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-issue-agents",
      "title": "Repository Overview: poh-issue-agents"
    },
    "total_pages": 251,
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
        "descendants": 101
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
        "file_count": 53
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
        "file_count": 94
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
    "indexed_commit": "a41f569f0381",
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

## Ход 2 · `list_repos` · contour

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
      "last_commit_at_index": "ac430395f64957e82c685eea7ffbc5986b6882bd"
    },
    {
      "alias": "poh-issue-agents",
      "path": "poh-issue-agents",
      "absolute_path": "/workspaces/contour/poh-issue-agents",
      "is_default": true,
      "indexed_at": "2026-08-19T16:06:57.382649+00:00",
      "last_commit_at_index": "a41f569f038188e9f0b3c9731990ef5efe59d014"
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

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": ".claude skills commands settings configuration",
  "repo": "poh-issue-agents",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Repository Overview: poh-issue-agents",
      "page_type": "repo_overview",
      "snippet": "`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.\n\n\n\n\n## Entry Points\nStart here when reading the cod",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "poh-issue-agents",
      "confidence_score": 1.0
    },
    {
      "title": "Architecture Scripts",
      "page_type": "module_page",
      "snippet": "# Architecture Scripts\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascri",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/technical-documentation/scripts/find_sql_queries.sh` is an infrastru",
      "relevance_score": 2.918,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "confidence_score": 0.97
    },
    {
      "title": "File: .claude/skills/architecture/scripts/generate_taxonomy.py",
      "page_type": "file_page",
      "snippet": "# .claude/skills/architecture/scripts/generate_taxonomy.py\n\n## Overview\n\n`.claude/skills/architecture/scripts/generate_taxonomy.py` is a python source file in the Config layer.\n\nIt exposes 1 public sy",
      "relevance_score": 2.872,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts/generate_taxonomy.py",
      "confidence_score": 0.96
    },
    {
      "title": "File: .claude/skills/writing-skills/render-graphs.js",
      "page_type": "file_page",
      "snippet": "# .claude/skills/writing-skills/render-graphs.js\n\n## Overview\n\n`.claude/skills/writing-skills/render-graphs.js` is a javascript source file in the Config layer.\n\n## Usage Notes\n\n**Layer:** Config | **",
      "relevance_score": 2.828,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/writing-skills/render-graphs.js",
      "confidence_score": 0.94
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/sdd-workspace` is an infrastructur",
      "relevance_score": 2.784,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "confidence_score": 0.93
    },
    {
      "title": "Infrastructure: worker/Dockerfile",
      "page_type": "infra_page",
      "snippet": "ce.com/setup_22.x | bash - \\\n    && apt-get install -y nodejs \\\n    && npm install -g @anthropic-ai/claude-code repomix \\\n    && rm -rf /var/lib/apt/lists/*\n\n# Только КЛИЕНТ Docker (`docker-ce-cli`),",
      "relevance_score": 2.757,
      "sources": [
        "fts"
      ],
      "target_path": "worker/Dockerfile",
      "confidence_score": 0.92
    },
    {
      "title": "File: .claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "page_type": "file_page",
      "snippet": "# .claude/skills/systematic-debugging/condition-based-waiting-example.ts\n\n## Overview\n\n`.claude/skills/systematic-debugging/condition-based-waiting-example.ts` is a typescript source file in the Confi",
      "relevance_score": 2.702,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "confidence_score": 0.9
    },
    {
      "title": "File: .claude/skills/brainstorming/scripts/helper.js",
      "page_type": "file_page",
      "snippet": "# .claude/skills/brainstorming/scripts/helper.js\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/helper.js` is a javascript source file in the Config layer.\n\nIt exposes 8 public symbols.\n\n## Publi",
      "relevance_score": 2.662,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/brainstorming/scripts/helper.js",
      "confidence_score": 0.89
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/task-brief",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/task-brief\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/task-brief` is an infrastructure file",
      "relevance_score": 2.624,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/task-brief",
      "confidence_score": 0.87
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
    },
    {
      "path": ".claude/skills/architecture/scripts/generate_taxonomy.py"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
    },
    {
      "path": "worker/Dockerfile"
    },
    {
      "path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/helper.js"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/task-brief"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    },
    {
      "path": ".claude/skills/systematic-debugging/find-polluter.sh"
    }
  ]
}

## Ход 4 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    ".claude",
    ".claude/skills",
    ".claude/commands"
  ],
  "repo": "poh-issue-agents",
  "include": [
    "skeleton",
    "ownership",
    "metrics"
  ]
}
```

**Ответ:**

{
  "targets": {
    ".claude": {
      "target": ".claude",
      "type": "module",
      "parent_page": {
        "title": "Repository Overview: poh-issue-agents",
        "target_path": "poh-issue-agents",
        "section": null
      },
      "docs": {
        "title": "Architecture Scripts",
        "summary": "`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`",
        "section": "4",
        "files": [
          {
            "path": ".claude/skills/architecture/scripts/generate_taxonomy.py",
            "description": "`.claude/skills/architecture/scripts/generate_taxonomy.py` is a python source file in the Config layer.",
            "confidence_score": 1.0
          }
        ]
      },
      "hotspot": false,
      "ownership": {
        "primary_owner": null,
        "owner_pct": null,
        "contributor_count": 0,
        "bus_factor": 0
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "metrics": null,
      "skeleton": {
        "error": "skeleton requires a file target; pass the file path."
      }
    },
    ".claude/skills": {
      "target": ".claude/skills",
      "type": "module",
      "parent_page": {
        "title": "Repository Overview: poh-issue-agents",
        "target_path": "poh-issue-agents",
        "section": null
      },
      "docs": {
        "title": "Architecture Scripts",
        "summary": "`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`",
        "section": "4",
        "files": [
          {
            "path": ".claude/skills/architecture/scripts/generate_taxonomy.py",
            "description": "`.claude/skills/architecture/scripts/generate_taxonomy.py` is a python source file in the Config layer.",
            "confidence_score": 1.0
          }
        ]
      },
      "hotspot": false,
      "ownership": {
        "primary_owner": null,
        "owner_pct": null,
        "contributor_count": 0,
        "bus_factor": 0
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "metrics": null,
      "skeleton": {
        "error": "skeleton requires a file target; pass the file path."
      }
    },
    ".claude/commands": {
      "target": ".claude/commands",
      "error": "Target not found: '.claude/commands'",
      "suggestions": [
        ".claude/commands/arch-gen.md",
        ".claude/commands/bft-concept.md",
        ".claude/commands/bft-context-gen.md",
        ".claude/commands/bft-debate.md",
        ".claude/commands/bft-deep.md"
      ]
    }
  },
  "_meta": {
    "timing_ms": 110.9,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 5 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    ".bft/index"
  ],
  "repo": "poh-issue-agents",
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    ".bft/index": {
      "target": ".bft/index",
      "error": "Target not found: '.bft/index'",
      "suggestions": [
        ".claude/commands/bft-index.md",
        ".claude/skills/bft-indexer/SKILL.md",
        ".claude/skills/bft-indexer/resources/index_schema.md"
      ]
    }
  },
  "_meta": {
    "timing_ms": 45.65,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 6 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    ".claude/skills/bft-indexer/resources/index_schema.md"
  ],
  "repo": "poh-issue-agents",
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    ".claude/skills/bft-indexer/resources/index_schema.md": {
      "target": ".claude/skills/bft-indexer/resources/index_schema.md",
      "type": "file",
      "docs": {
        "summary": "index_schema.md: 35-line document, 9 headings, no indexed symbols.",
        "file_preview": {
          "lines": 35,
          "chars": 1621,
          "headings": [
            "# Схема индекса `.bft/index/`",
            "## MANIFEST.md",
            "## architecture.md  (роль C1)",
            "## domain-rules.md  (роль C2)",
            "## decisions.md  (роль C5)",
            "## regulatory.md  (роль C3, опц.)",
            "## glossary.md",
            "## stakeholders.md  (реестр владельцев по ролям)",
            "## sources.md"
          ],
          "note": "This file has no indexed symbols, so there is no structural card for it. The fields above are counts and verbatim excerpts. Read the file for its full content."
        }
      },
      "hotspot": false,
      "freshness": {
        "confidence_score": null,
        "freshness_status": null,
        "is_stale": null
      },
      "architectural_layer": {
        "name": "Config",
        "description": "",
        "role": "entry_point"
      },
      "skeleton": {
        "mode": "raw",
        "tokens": 405,
        "full_tokens": 405,
        "pct_of_full": 100.0,
        "bodies_kept": [],
        "text": "# Схема индекса `.bft/index/`\n\nСамо-генерируемый контекст воркспейса. Аналог централизованной справочной базы знаний, но\nсобирается локально из доступных источников. Правило: пусто ≠ «нет данных» — недоступный источник помечается\nUNAVAILABLE в MANIFEST, вывод из него → `[УТОЧНИТЬ]`.\n\n## MANIFEST.md\nКарта покрытия. Таблица: Источник | Тип (docs/code/tracker) | Статус (INDEXED/UNAVAILABLE) |\nДата | Охват (файлов/страниц). Плюс строка «Индекс собран: <дата>».\n\n## architecture.md  (роль C1)\nКомпоненты, сервисы, интеграции воркспейса. Из кода (serena: модули/пакеты/точки входа) +\nдоков-описаний. Каждый компонент: назначение + якорь `[источник: path:line | doc.md]`.\n\n## domain-rules.md  (роль C2)\nБизнес-правила предметной области. Из доков/спек/существующих БФТ. Правило + якорь.\n\n## decisions.md  (роль C5)\nADR и зафиксированные решения. Из `**/ADR*.md`, `**/decisions/**`, комментов трекера.\nРешение + дата + якорь.\n\n## regulatory.md  (роль C3, опц.)\nCompliance/регуляторика (ПДн, отраслевое). Если в источниках нет — файл создаётся с\nпометкой «Регуляторных источников не найдено — заполнить вручную при необходимости».\n\n## glossary.md\nТермины домена: термин → определение → якорь. Из доков + частотного анализа.\n\n## stakeholders.md  (реестр владельцев по ролям)\nРоли/команды/владельцы. Из CODEOWNERS, git-истории (частые авторы по областям),\nдоков-контактов, трекера (assignee/reporter). Роль → зона ответственности → якорь.\n\n## sources.md\nПлоский реестр всех использованных якорей: id якоря → полный источник (path:line /\nJIRA-key / Confluence-URL / doc). На него ссылаются пакеты и финальный раздел «Якоря» БФТ.\n",
        "verified": true,
        "note": "No usable symbol bounds for this file — returned source as-is."
      }
    }
  },
  "_meta": {
    "timing_ms": 75.91,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
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
  "query": "PR 97 105 architecture pattern hardcode",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: .claude/skills/systematic-debugging/find-polluter.sh",
      "page_type": "infra_page",
      "snippet": "s an infrastructure file (shell). Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Bisection script to find which test",
      "relevance_score": 3.015,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/systematic-debugging/find-polluter.sh",
      "confidence_score": 1.0
    },
    {
      "title": "File: .claude/skills/architecture/scripts/generate_taxonomy.py",
      "page_type": "file_page",
      "snippet": "# .claude/skills/architecture/scripts/generate_taxonomy.py\n\n## Overview\n\n`.claude/skills/architecture/scripts/generate_taxonomy.py` is a python source file in the Config layer.\n\nIt exposes 1 public sy",
      "relevance_score": 2.966,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts/generate_taxonomy.py",
      "confidence_score": 0.98
    },
    {
      "title": "Architecture Scripts",
      "page_type": "module_page",
      "snippet": "# Architecture Scripts\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascri",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts",
      "confidence_score": 0.96
    },
    {
      "title": "Symbol: worker.activities.prefilter_bot_and_security",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.prefilter_bot_and_security\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef prefilter_bot_and_security(issue: IssueInput, origin_",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::prefilter_bot_and_security",
      "file": "worker/activities.py",
      "confidence_score": 0.95
    },
    {
      "title": "Infrastructure: worker/Dockerfile",
      "page_type": "infra_page",
      "snippet": "res 1 named target, listed below. Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n## Declared targets\n\n- `cmd`\n\n\n\n\n## Source\n\n```dockerfile\nFROM python:3.12-slim",
      "relevance_score": 2.842,
      "sources": [
        "fts"
      ],
      "target_path": "worker/Dockerfile",
      "confidence_score": 0.94
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/systematic-debugging/find-polluter.sh"
    },
    {
      "path": ".claude/skills/architecture/scripts/generate_taxonomy.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/Dockerfile"
    },
    {
      "path": "shared/pr_closing.py"
    }
  ]
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "issue 70 poh-sysreq-agent",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Repository Overview: poh-issue-agents",
      "page_type": "repo_overview",
      "snippet": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `web",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "poh-issue-agents",
      "confidence_score": 1.0
    },
    {
      "title": "File: scripts/smoke_temporal.py",
      "page_type": "file_page",
      "snippet": "scribe_namespace — namespace существует и REGISTERED\n  3) поднимает временный worker на task-queue `poh-smoke-test`, запускает\n     тривиальный workflow (activity возвращает pong) и ждёт результат —",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/smoke_temporal.py",
      "confidence_score": 0.99
    },
    {
      "title": "Active Landscape",
      "page_type": "onboarding",
      "snippet": "# Active Landscape\n\nWhere `poh-issue-agents` has actually been changing. 501 commits touched 129 files in the last 90 days.\n\n\n## Files under active change\n\n| File | Commits (90d) | Owner | Hotspot | A",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/active_landscape",
      "confidence_score": 0.97
    },
    {
      "title": "File: shared/repos.py",
      "page_type": "file_page",
      "snippet": "# shared/repos.py\n\n## Overview\n\nСписок отслеживаемых репозиториев (ISSUE_AGENT_REPOS).\n\nАналог RELIABILITY_REPOS в poh-pr-agents. Чистые функции: разбор спецификаций\nи проверка допуска репозитория. Се",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "shared/repos.py",
      "confidence_score": 0.96
    },
    {
      "title": "Key Concepts",
      "page_type": "onboarding",
      "snippet": "# Key Concepts\n\nThe types and functions the rest of `poh-issue-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanati",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/key_concepts",
      "confidence_score": 0.94
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "shared/repos.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "shared/lifecycle.py"
    }
  ]
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "MetaReviewer 92 self-improvement validation",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: .claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "page_type": "file_page",
      "snippet": "OL_CALL Complete implementation of condition-based waiting utilities From: Lace test infrastructure improvements (2025-10-03) Context: Fixed 15 flaky tests by replacing arbitrary timeouts Usage exampl",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "type": "page"
    },
    {
      "title": "Symbol: worker.estimation.EstimationFacts",
      "page_type": "symbol_spotlight",
      "snippet": "| new_development | enhancement | deployment\")\n    artifact_type: str = Field(description=\"bugfix | validation | subtask | new_module\")\n    scaffolding_hours: float = Field(description=\"Часы на каркас",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/estimation.py::EstimationFacts",
      "file": "worker/estimation.py",
      "type": "page"
    },
    {
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "`FAST` defined?\n- What imports `shared/bft.py`?\n\n## In the code\n\nslug pack problem concept document validation kept head sep body cells goal how_to_demo how demo open_questions open questions scope do",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "type": "page"
    },
    {
      "title": "Symbol: tests.test_estimate_activities.FakeGitHub",
      "page_type": "symbol_spotlight",
      "snippet": "irmed call sites.\n\n- `tests/conftest.py`\n\n## Implementation\n\n```\nclass FakeGitHub:\n    def __init__(self, issue=None, comments=None, branches=(), files=None):\n        self.issue = issue or {\"title\": \"",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_activities.py::FakeGitHub",
      "file": "tests/test_estimate_activities.py",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_pr_closing.py::test_exhausted_comment_blames_the_code_not_the_reviewer",
      "name": "test_exhausted_comment_blames_the_code_not_the_reviewer",
      "kind": "function",
      "file": "tests/test_pr_closing.py",
      "start_line": 141,
      "end_line": 145,
      "signature": "def test_exhausted_comment_blames_the_code_not_the_reviewer()",
      "qualified_name": "tests.test_pr_closing.test_exhausted_comment_blames_the_code_not_the_reviewer",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts"
    },
    {
      "path": "worker/estimation.py"
    },
    {
      "path": "shared/bft.py"
    },
    {
      "path": "tests/test_estimate_activities.py"
    },
    {
      "path": "tests/test_pr_closing.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'MetaReviewer'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 10 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "poh-bft-writer"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-bft-writer",
  "content_md": "# Repository Overview: poh-bft-writer\n\n**Files:** 54 | **Lines:** 15621",
  "code_health": {
    "average_health": 9.34,
    "band": "healthy",
    "hotspot_health": 9.38,
    "worst_performer_path": "commands/bft-fast.md",
    "worst_performer_score": 6.5,
    "open_findings": 42,
    "file_count": 57,
    "distribution": {
      "total_files": 57,
      "total_nloc": 5041,
      "bands": {
        "healthy": {
          "files": 52,
          "nloc": 4269,
          "pct": 84.7
        },
        "warning": {
          "files": 5,
          "nloc": 772,
          "pct": 15.3
        },
        "alert": {
          "files": 0,
          "nloc": 0,
          "pct": 0.0
        }
      }
    }
  },
  "key_modules": [],
  "entry_points": [],
  "git_health": {
    "files_git_attributed": 56,
    "hotspot_count": 9,
    "avg_bus_factor": 0.5,
    "files_with_bus_factor_1": 27,
    "churn_trend": "increasing",
    "top_churn_modules": [
      "skills/bft-fast",
      "skills/bft-writer",
      "skills/bft-deep-swarm",
      "docs/superpowers",
      "commands/bft-fast.md"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "ALeks ishmanov",
        "files_owned": 28,
        "percentage": 50.0
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "claude",
      "size": 1
    },
    {
      "id": 1,
      "label": ".mcp",
      "size": 1
    },
    {
      "id": 2,
      "label": "readme",
      "size": 1
    },
    {
      "id": 3,
      "label": "config",
      "size": 1
    },
    {
      "id": 4,
      "label": "commands",
      "size": 1
    },
    {
      "id": 5,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 6,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 7,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 8,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands (1)",
      "size": 1
    }
  ],
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-bft-writer",
      "title": "Repository Overview: poh-bft-writer"
    },
    "total_pages": 8,
    "sections": [
      {
        "section": "1",
        "page_id": "onboarding:onboarding/how_it_works",
        "title": "How It Works",
        "page_type": "onboarding",
        "target_path": "onboarding/how_it_works"
      },
      {
        "section": "2",
        "page_id": "infra_page:install.sh",
        "title": "Infrastructure: install.sh",
        "page_type": "infra_page",
        "target_path": "install.sh"
      },
      {
        "section": "3",
        "page_id": "file_page:skills/bft-writer/scripts/bft-lint.py",
        "title": "File: skills/bft-writer/scripts/bft-lint.py",
        "page_type": "file_page",
        "target_path": "skills/bft-writer/scripts/bft-lint.py",
        "descendants": 4
      }
    ]
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "CLI",
        "description": "",
        "file_count": 10
      },
      {
        "name": "Application",
        "description": "",
        "file_count": 27
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 1
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 19
      }
    ],
    "tour_available": true,
    "tour_step_count": 2
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-bft-writer",
      "page_id": "repo_overview:poh-bft-writer",
      "target_path": "poh-bft-writer",
      "section": null
    },
    {
      "order": 2,
      "slot": "how_it_works",
      "title": "How It Works",
      "page_id": "onboarding:onboarding/how_it_works",
      "target_path": "onboarding/how_it_works",
      "section": "1"
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
      "title": "bft-config.template.md",
      "kind": "code",
      "reason": "The walk's anchor — its imports fan out the widest in a repo with no single entry point.",
      "target_path": "bft-config.template.md",
      "page_id": "file_page:bft-config.template.md",
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
    "indexed_commit": "c7fe9bd7d1b2",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 11 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "poh-helper"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-helper",
  "content_md": "# Repository Overview: poh-helper\n\n**Files:** 548 | **Lines:** 172065 | **Import cycles:** 1",
  "code_health": {
    "average_health": 9.93,
    "band": "healthy",
    "hotspot_health": 6.24,
    "worst_performer_path": "sa_documentation/validate_ground.py",
    "worst_performer_score": 3.51,
    "open_findings": 66,
    "file_count": 548,
    "distribution": {
      "total_files": 548,
      "total_nloc": 69911,
      "bands": {
        "healthy": {
          "files": 542,
          "nloc": 69175,
          "pct": 98.9
        },
        "warning": {
          "files": 5,
          "nloc": 545,
          "pct": 0.8
        },
        "alert": {
          "files": 1,
          "nloc": 191,
          "pct": 0.3
        }
      }
    }
  },
  "key_modules": [
    {
      "name": "Resources Engine",
      "path": ".claude/skills/okr-planner/resources/engine",
      "description": "`.claude/skills/okr-planner/resources/engine` · `.claude/workflows`\n\n**Language:** python | **Files:** 13 | **Public symbols:** 44 / 97\n\n\nCovers the 13 source files in 2 directories under .claude…",
      "page_id": "module_page:.claude/skills/okr-planner/resources/engine",
      "section": "4",
      "parent_page_id": "repo_overview:poh-helper"
    },
    {
      "name": "Sa Documentation",
      "path": "sa_documentation",
      "description": "`sa_documentation`\n\n**Language:** python | **Files:** 4 | **Public symbols:** 9 / 15\n\n\nCovers the 4 source files in sa_documentation. Does not cover code outside those directories, which is…",
      "page_id": "module_page:sa_documentation",
      "section": "5",
      "parent_page_id": "repo_overview:poh-helper"
    }
  ],
  "entry_points": [],
  "git_health": {
    "files_git_attributed": 38,
    "hotspot_count": 5,
    "avg_bus_factor": 1.0,
    "files_with_bus_factor_1": 38,
    "churn_trend": "decreasing",
    "top_churn_modules": [
      ".claude/skills",
      "install.sh",
      "sa_documentation/tests",
      "sa_documentation/validate_ground.py",
      "sa_documentation/lint_graph.py"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "ALeks ishmanov",
        "files_owned": 38,
        "percentage": 100.0
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "skills/okr-planner (6)",
      "size": 3
    },
    {
      "id": 1,
      "label": "skills/okr-planner (6)",
      "size": 3
    },
    {
      "id": 2,
      "label": "skills/okr-planner",
      "size": 3
    },
    {
      "id": 3,
      "label": "skills/okr-planner (3)",
      "size": 2
    },
    {
      "id": 4,
      "label": "agents",
      "size": 1
    },
    {
      "id": 5,
      "label": "commands",
      "size": 1
    },
    {
      "id": 6,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 7,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 8,
      "label": "commands (1)",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands (1)",
      "size": 1
    }
  ],
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-helper",
      "title": "Repository Overview: poh-helper"
    },
    "total_pages": 39,
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
        "page_id": "module_page:.claude/skills/okr-planner/resources/engine",
        "title": "Resources Engine",
        "page_type": "module_page",
        "target_path": ".claude/skills/okr-planner/resources/engine",
        "descendants": 27
      },
      {
        "section": "5",
        "page_id": "module_page:sa_documentation",
        "title": "Sa Documentation",
        "page_type": "module_page",
        "target_path": "sa_documentation",
        "descendants": 3
      },
      {
        "section": "6",
        "page_id": "scc_page:scc-89d616a7255c",
        "title": "Circular Dependency: Engine Tests",
        "page_type": "scc_page",
        "target_path": "scc-89d616a7255c"
      },
      {
        "section": "7",
        "page_id": "infra_page:deploy/pr-agent/cron/review-open-prs.sh",
        "title": "Infrastructure: deploy/pr-agent/cron/review-open-prs.sh",
        "page_type": "infra_page",
        "target_path": "deploy/pr-agent/cron/review-open-prs.sh"
      },
      {
        "section": "8",
        "page_id": "infra_page:install.sh",
        "title": "Infrastructure: install.sh",
        "page_type": "infra_page",
        "target_path": "install.sh"
      }
    ]
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 43
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 233
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 252
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 20
      }
    ],
    "tour_available": true,
    "tour_step_count": 7,
    "layer_order": [
      "Application",
      "Config"
    ]
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-helper",
      "page_id": "repo_overview:poh-helper",
      "target_path": "poh-helper",
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
      "title": "validate_ground.py",
      "kind": "code",
      "reason": "The walk's anchor — its imports fan out the widest in a repo with no single entry point.",
      "target_path": "sa_documentation/validate_ground.py",
      "page_id": "file_page:sa_documentation/validate_ground.py",
      "section": "5.3"
    },
    {
      "order": 3,
      "title": "cindex_ids.py",
      "kind": "code",
      "reason": "Off the import paths walked above — a standalone or supporting file.",
      "target_path": "sa_documentation/cindex_ids.py",
      "page_id": "file_page:sa_documentation/cindex_ids.py",
      "section": "5.1"
    },
    {
      "order": 6,
      "title": "install.sh",
      "kind": "code",
      "reason": "A top churn hotspot — one of the most frequently changed files in the repo; worth understanding early.",
      "target_path": "install.sh",
      "page_id": "file_page:install.sh",
      "section": null
    },
    {
      "order": 7,
      "title": "conftest.py",
      "kind": "code",
      "reason": "The test suite — how the system's behavior is verified.",
      "target_path": ".claude/skills/okr-planner/resources/engine/tests/conftest.py",
      "page_id": "file_page:.claude/skills/okr-planner/resources/engine/tests/conftest.py",
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
    "indexed_commit": "18512c1e7ce9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 12 · `get_blast_radius` · contour

**Запрос:**

```json
{
  "targets": [
    "poh-issue-agents"
  ],
  "max_depth": 2,
  "include_behavioral": true
}
```

**Ответ:**

{
  "targets": [
    "poh-issue-agents"
  ],
  "target_repos": [
    "poh-issue-agents"
  ],
  "impacted": [
    {
      "id": "poh-pr-agents",
      "repo": "poh-pr-agents",
      "name": "poh-pr-agents",
      "kind": "service",
      "distance": 1,
      "score": 0.1947,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    },
    {
      "id": "poh-bft-writer",
      "repo": "poh-bft-writer",
      "name": "poh-bft-writer",
      "kind": "service",
      "distance": 1,
      "score": 0.1902,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    },
    {
      "id": "poh-memory-engine",
      "repo": "poh-memory-engine",
      "name": "poh-memory-engine",
      "kind": "service",
      "distance": 1,
      "score": 0.1875,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    },
    {
      "id": "poh-helper",
      "repo": "poh-helper",
      "name": "poh-helper",
      "kind": "service",
      "distance": 1,
      "score": 0.186,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    },
    {
      "id": "poh-infra",
      "repo": "poh-infra",
      "name": "poh-infra",
      "kind": "service",
      "distance": 1,
      "score": 0.1503,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    },
    {
      "id": "poh-issue-agents::worker",
      "repo": "poh-issue-agents",
      "name": "worker",
      "kind": "service",
      "distance": 2,
      "score": 0.0379,
      "structural": false,
      "edge_kinds": [
        "co_change"
      ]
    }
  ],
  "impacted_truncated": 0,
  "impacted_repos": [
    "poh-bft-writer",
    "poh-helper",
    "poh-infra",
    "poh-memory-engine",
    "poh-pr-agents"
  ],
  "structural_count": 0,
  "behavioral_count": 6,
  "max_distance": 2,
  "total_impacted": 6,
  "unresolved_targets": [],
  "summary": "Changing 1 service(s) impacts 6 downstream service(s) across 5 other repo(s): 0 via a real dependency, 6 via co-change only.",
  "_meta": {
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 13 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-bft-writer",
  "targets": [
    "skills",
    "commands"
  ]
}
```

**Ответ:**

{
  "targets": {
    "skills": {
      "target": "skills",
      "error": "Target not found: 'skills'",
      "suggestions": [
        "skills/bft-deep-swarm/SKILL.md",
        "skills/bft-deep-swarm/examples/golden_deep_document.md",
        "skills/bft-deep-swarm/examples/golden_deep_eval_verdict.md",
        "skills/bft-deep-swarm/examples/golden_deep_gold.md",
        "skills/bft-deep-swarm/examples/golden_deep_summary.md"
      ]
    },
    "commands": {
      "target": "commands",
      "error": "Target not found: 'commands'",
      "suggestions": [
        "commands/bft-concept.md",
        "commands/bft-context-gen.md",
        "commands/bft-debate.md",
        "commands/bft-deep.md",
        "commands/bft-deliver.md"
      ]
    }
  },
  "_meta": {
    "timing_ms": 82.31,
    "index_age_days": 0,
    "indexed_commit": "c7fe9bd7d1b2",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 14 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-bft-writer",
  "targets": [
    "commands/bft-context-gen.md"
  ]
}
```

**Ответ:**

{
  "targets": {
    "commands/bft-context-gen.md": {
      "target": "commands/bft-context-gen.md",
      "type": "file",
      "docs": {
        "summary": "bft-context-gen.md: 170-line document, 13 headings, no indexed symbols.",
        "file_preview": {
          "lines": 170,
          "chars": 7886,
          "headings": [
            "## Использование",
            "## Примеры",
            "## Важно",
            "## На выходе",
            "## Инструкция для LLM",
            "### Этап 0: Подготовка",
            "### Этап 1: `.bft/index/` — читаем локальный фон (без сетевых запросов)",
            "### Этап 2: JIRA базовый (один запрос на эпик)",
            "### Этап 3: LLM-синтез на основе индекса + JIRA",
            "### Этап 4: Матрица покрытия",
            "### Этап 5: Сборка pack",
            "### Этап 6: Отчёт",
            "## Жёсткие правила"
          ],
          "note": "This file has no indexed symbols, so there is no structural card for it. The fields above are counts and verbatim excerpts. Read the file for its full content."
        }
      },
      "hotspot": false,
      "freshness": {
        "confidence_score": null,
        "freshness_status": null,
        "is_stale": null
      },
      "architectural_layer": {
        "name": "CLI",
        "description": "",
        "role": "entry_point"
      },
      "skeleton": {
        "mode": "raw",
        "tokens": 1971,
        "full_tokens": 1971,
        "pct_of_full": 100.0,
        "bodies_kept": [],
        "text": "---\ndescription: Быстрый контекст-пак для БФТ — индекс `.bft/index/` + базовый JIRA + LLM-синтез. Готов за 1-2 минуты. Индекс неполон — перезапусти /bft-index\n---\n\n## Использование\n\n```\n/bft-context-gen <epic_code> <jira_key>\n```\n\n**Параметры:**\n- `<epic_code>` — короткий код БФТ (напр. `EPIC-10`).\n- `<jira_key>` — эпик JIRA (напр. `PROJ-101`).\n\n## Примеры\n\n```\n/bft-context-gen EPIC-10 PROJ-101\n/bft-context-gen EPIC-PROC PROJ-103\n```\n\n## Важно\n\n**Режим:** контекст-пак из `.bft/index/` (см. `/bft-index`) + один запрос к JIRA, далее LLM синтезирует вероятную картину домена. Неизвестное — честно помечает `[УТОЧНИТЬ]`. Индекс неполон (см. `MANIFEST.md` — источники со статусом `UNAVAILABLE`) — перезапусти `/bft-index` для полного покрытия перед `/bft-problem`.\n\n**Когда достаточно текущего индекса:**\n- `MANIFEST.md` показывает `INDEXED` по релевантным источникам\n- Нужно быстро войти в контекст перед встречей с PO\n- Первый черновик для ориентира перед перестройкой индекса\n- JIRA/Confluence временно недоступны (VPN)\n\n**Когда сначала перезапустить `/bft-index`:**\n- Новый/незнакомый эпик, индекс собирался давно или не собирался\n- В `MANIFEST.md` много `UNAVAILABLE` по релевантным источникам\n- Требуется полная доказательная база для БФТ без дыр\n\n## На выходе\n\n```\n.bft/documentation/<epic>/artefacts/\n└── bft-context-pack.md   ← pack: .bft/index/ + базовый JIRA + LLM-синтез + матрица покрытия\n```\n\n**Иные файлы не создавать.** Pack — единственный артефакт, который читает `/bft-problem`. Кладётся в `artefacts/` (служебная папка пайплайна); финальный БФТ `<epic>.md` появится в корне папки эпика на стадии `/bft-draft`.\n---\n\n## Инструкция для LLM\n\n### Этап 0: Подготовка\n\n1. Создай папку `.bft/documentation/<epic>/artefacts/`.\n2. Зафиксируй `epic_code` и `jira_key`.\n3. Прочитай `.bft/index/MANIFEST.md` — зафиксируй покрытие (INDEXED/UNAVAILABLE по источникам).\n4. В шапке pack сразу пометь: `Режим: контекст-пак из .bft/index/. Индекс неполон — /bft-index.`\n\n### Этап 1: `.bft/index/` — читаем локальный фон (без сетевых запросов)\n\nПрочитай из индекса только релевантное по теме эпика:\n\n- **Архитектура** (`.bft/index/architecture.md`) — границы, потоки, сервисы.\n- **Регуляторика** (`.bft/index/regulatory.md`) — применимые законы.\n- **Бизнес-правила** (`.bft/index/domain-rules.md`) — релевантные правила домена.\n- **Решения** (`.bft/index/decisions.md`) — известные ADR и PO-решения.\n- **Глоссарий** (`.bft/index/glossary.md`) — термины домена.\n- **Стейкхолдеры** (`.bft/index/stakeholders.md`) — владельцы/роли по зонам ответственности.\n- **Смежные БФТ** (`.bft/documentation/*/`) — есть ли уже готовый документ по этому домену?\n\nФиксируй: что нашёл / чего нет (→ `[УТОЧНИТЬ: нет в индексе]`). Источник со статусом `UNAVAILABLE` в `MANIFEST.md` — не «пусто», а прямой сигнал перезапустить `/bft-index`.\n\n### Этап 2: JIRA базовый (один запрос на эпик)\n\n1. `mcp__atlassian__jira_get_issue(<jira_key>)` — описание, статус, приоритет, labels, assignee, components.\n2. Из описания эпика выдели: цель, scope, связанные компоненты, упомянутые зависимости.\n3. **Дочерние задачи не запрашиваем** — только эпик.\n4. Если JIRA недоступен → `[УТОЧНИТЬ: JIRA недоступна (VPN?)]`, продолжай по индексу.\n\n### Этап 3: LLM-синтез на основе индекса + JIRA\n\nНа основе прочитанного — рассуждай как опытный аналитик домена. **Явно разделяй факт и вывод:**\n\n- **Факт** (из индекса / трекера) — помечай источником: `(architecture.md)`, `(JIRA)`, `(domain-rules.md)`, `(decisions.md)`\n- **Вывод LLM** — помечай: `[вывод LLM, требует проверки]`\n- **Неизвестное** — помечай: `[УТОЧНИТЬ у {кого}]`\n\nСинтезируй по блокам:\n\n**A. Домен и контекст**\n- Что делает эпик (своими словами, 2-3 предложения)\n- К какому домену относится (термины и команды из `.bft/index/glossary.md`)\n- Какие сервисы и БД затрагивает (из `architecture.md` + JIRA)\n\n**B. As-Is (вероятная текущая ситуация)**\n- Как эта область работает сейчас (из `architecture.md`, смежных БФТ в `.bft/documentation/`)\n- Где источник истины (системы из `architecture.md` / `.bft/index/sources.md`)\n- Что считается болью/проблемой (из JIRA description + индекса)\n\n**C. Стейкхолдеры (вывод LLM)**\n- Кто владелец домена (из `stakeholders.md`)\n- Кого затрагивают изменения (смежные команды/системы из `architecture.md`)\n- Кто согласует (PO / архитектор / юристы по `regulatory.md`)\n- Пометь весь блок: `[вывод LLM — проверить с PO]`\n\n**D. Зависимости (вывод LLM)**\n- Какие смежные системы/команды вовлечены (из `architecture.md`)\n- Какие интеграции затрагивает\n- Известные блокеры или зависимые эпики (из JIRA description)\n- Пометь: `[вывод LLM — статус согласования неизвестен, уточнить]`\n\n**E. Регуляторика и риски (из `regulatory.md`)**\n- Применимые законы/требования из `.bft/index/regulatory.md`\n- Если `regulatory.md` не покрывает тему → `[УТОЧНИТЬ: регуляторика для данного домена]`\n\n**F. Открытые вопросы**\n- Всё неизвестное из блоков выше — сводный список `[УТОЧНИТЬ у {кого}]`\n\n### Этап 4: Матрица покрытия\n\n| Раздел БФТ | Источник | Режим | Статус |\n|---|---|---|---|\n| Домен и контекст | JIRA + architecture.md | факт | ✅/[УТОЧНИТЬ] |\n| As-Is | architecture.md + смежные БФТ | факт | ✅/[УТОЧНИТЬ] |\n| Стейкхолдеры | stakeholders.md + LLM-вывод | вывод | ⚠️ проверить |\n| БТ (ценность) | JIRA description | факт+вывод | ✅/[УТОЧНИТЬ] |\n| ПТ/ФТ | LLM-вывод | вывод | ⚠️ проверить |\n| НФТ (нагрузка/SLA) | architecture.md + LLM | вывод | ⚠️ /bft-index (перестроить индекс) |\n| Negative flows | LLM-вывод | вывод | ⚠️ /bft-index (перестроить индекс) |\n| Риски/Compliance | regulatory.md + LLM | факт+вывод | ✅/[УТОЧНИТЬ] |\n| Зависимости | architecture.md + LLM | вывод | ⚠️ проверить |\n| Дочерние задачи | — | не собрано | ➡️ /bft-index (расширить охват трекера) |\n\n### Этап 5: Сборка pack\n\nСобери `.bft/documentation/<epic>/artefacts/bft-context-pack.md`:\n\n1. **Шапка:** epic, jira_key, дата, покрытие индекса (из `MANIFEST.md`).\n2. **Выдержки из индекса** (architecture/domain-rules/decisions/regulatory/glossary/stakeholders) — только релевантное.\n3. **JIRA-факты** — что взято из эпика.\n4. **LLM-синтез** (блоки A–F) с явными пометками факт / вывод LLM.\n5. **Матрица покрытия**.\n6. **Требует уточнения** — сводный список всех `[УТОЧНИТЬ]`.\n7. **Рекомендация:** если >3 блоков помечены `⚠️ вывод LLM` в критичных разделах (НФТ, Negative flows, Зависимости) или в `MANIFEST.md` много `UNAVAILABLE` по релевантным источникам → предложи перезапустить `/bft-index` перед `/bft-problem`.\n\n### Этап 6: Отчёт\n\n```\nКонтекст-пак собран: .bft/documentation/<epic>/artefacts/bft-context-pack.md\n\nИсточники: .bft/index/ (architecture/domain-rules/decisions/regulatory/glossary/stakeholders) + JIRA basic.\nФакты: <X> из JIRA/индекса.\nВыводы LLM (требуют проверки): <Y> блоков.\nОткрытые вопросы: <Z> [УТОЧНИТЬ].\n\n<если индекс неполон или много выводов LLM>\n⚠️ Рекомендую: перезапусти /bft-index для полного покрытия перед /bft-problem.\n</если>\n\n── СТОП ── PO/СА: проверьте pack, особенно блоки ⚠️ (вывод LLM).\nДальше:\n• /bft-index                          ← перестроить/дополнить индекс (если неполон)\n• /bft-problem <epic_code>            ← диагноз As-Is/Gap (если контекста достаточно)\n```\n\n## Жёсткие правила\n\n1. **Явная метка покрытия.** Pack ссылается на `MANIFEST.md` — читатель видит, где вывод LLM, а где индекс неполон.\n2. **Факт vs вывод** — всегда разделять. Не смешивать.\n3. **Нет выдумок.** Вывод LLM ≠ факт. Вывод помечается явно.\n4. **JIRA — только эпик.** Без дочерних задач и поиска по Confluence.\n5. **Честно про недоступность** — VPN/MCP проблемы и `UNAVAILABLE` в `MANIFEST.md` помечать явно.\n6. **Стиль pack** — по `skills/bft-writer/resources/writing_style.md`. Pack — это отчёт пайплайна (не БФТ): деловая проза без AI-стоп-слов («позволяет», «обеспечивает», «представляет собой»); эмодзи только семантические (статус источника в матрице покрытия: `✅`/`⚠️`/`➡️`); декоративных эмодзи в шапке режима не ставить — режим текстом.\n",
        "verified": true,
        "note": "No usable symbol bounds for this file — returned source as-is."
      }
    }
  },
  "_meta": {
    "timing_ms": 53.55,
    "index_age_days": 0,
    "indexed_commit": "c7fe9bd7d1b2",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "CLAUDE.md system prompt context injection",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: worker/consolidation_activities.py",
      "page_type": "file_page",
      "snippet": "and depends on 3 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `ProfileExtraction` | class | class",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "worker/consolidation_activities.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: worker/llm.py",
      "page_type": "file_page",
      "snippet": "о ручного json.loads()+try/except, как было в исходной версии на\nActions.\n\nДля po-helper/SA-helper (Claude Code skills) используется ДРУГОЙ путь —\nAnthropic-совместимый эндпоинт z.ai через переменные",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "worker/llm.py",
      "confidence_score": 0.98
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "| Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DI",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "Symbol: worker.activities.run_bft_fast",
      "page_type": "symbol_spotlight",
      "snippet": "## Overview\n\nБыстрый проход: письмо БФТ комментарием в Issue.\n\nОдин вызов модели, без клона и без claude-code: формат `/bft-fast` — это\nструктурирование уже сказанного, а не исследование кода. Клони",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_fast",
      "file": "worker/activities.py",
      "confidence_score": 0.94
    },
    {
      "title": "Symbol: worker.activities.decompose_issue",
      "page_type": "symbol_spotlight",
      "snippet": "- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_d",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::decompose_issue",
      "file": "worker/activities.py",
      "confidence_score": 0.93
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/consolidation_activities.py"
    },
    {
      "path": "worker/llm.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js"
    },
    {
      "path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts"
    }
  ]
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "MCP server tool validation review content check",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/repowise.py",
      "page_type": "file_page",
      "snippet": "# shared/repowise.py\n\n## Overview\n\nКлиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.\n\nПрокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по\nworkspace, треб",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/repowise.py",
      "confidence_score": 1.0
    },
    {
      "title": "Repository Overview: poh-issue-agents",
      "page_type": "repo_overview",
      "snippet": "codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `webhook/main.py`\n\n- `.cl",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "poh-issue-agents",
      "confidence_score": 0.97
    },
    {
      "title": "File: .claude/skills/brainstorming/scripts/server.cjs",
      "page_type": "file_page",
      "snippet": "# .claude/skills/brainstorming/scripts/server.cjs\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/server.cjs` is a javascript entry-point source file in the Config layer.\n\nIt exposes 66 public sym",
      "relevance_score": 2.918,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/brainstorming/scripts/server.cjs",
      "confidence_score": 0.96
    },
    {
      "title": "Architecture Scripts",
      "page_type": "module_page",
      "snippet": "hosts 1 entry point into this subsystem.\n\n\n## Entry Points\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `.claude/skills/archi",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts",
      "confidence_score": 0.94
    },
    {
      "title": "Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh\n\n**Type:** shell | **Declared targets:** 5\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructur",
      "relevance_score": 2.828,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/brainstorming/scripts/stop-server.sh",
      "confidence_score": 0.93
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/repowise.py"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/server.cjs"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/stop-server.sh"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/start-server.sh"
    },
    {
      "path": "scripts/demo_e2e.py"
    }
  ]
}

## Ход 17 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "git submodule subtree vendor dependency",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: .claude/skills/architecture/scripts/generate_taxonomy.py",
      "page_type": "file_page",
      "snippet": "( node_modules __pycache__ dist Анализ структуры папок для определения доменов Пропускаем скрытые и vendor-папки Определяем домен по имени папки (универсальная эвристика) Поиск упоминаний внешних прот",
      "relevance_score": 3.015,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts/generate_taxonomy.py",
      "confidence_score": 1.0
    },
    {
      "title": "Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "page_type": "infra_page",
      "snippet": "ECT, INSERT, UPDATE, DELETE внутри PHP файлов\ngrep -rEi \"SELECT|INSERT|UPDATE|DELETE\" $1 | grep -v \"vendor\"\n```\n\n---\n\n*Built from the code itself: parsed symbols, the import graph, git history and\nthe",
      "relevance_score": 2.966,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "confidence_score": 0.98
    },
    {
      "title": "Circular Dependency: Tests",
      "page_type": "scc_page",
      "snippet": "# Circular Dependency: Tests\n\n4 files import each other in a loop, directly or transitively. Nothing in this group can be loaded, tested or extracted without the rest of it.\n\n**Cycle id:** `scc-37580",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "scc-37580294ed84",
      "confidence_score": 0.96
    },
    {
      "title": "Key Concepts",
      "page_type": "onboarding",
      "snippet": "py` · Application · used from 2 other files\n\n_No docstring._\n\n\n\n\n\n\n## Vocabulary from the clusters\n\nDependency analysis named these groups. Their names are usually the codebase's own words for its par",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/key_concepts",
      "confidence_score": 0.95
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/architecture/scripts/generate_taxonomy.py"
    },
    {
      "path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
    }
  ]
}

## Ход 18 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/repowise.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/repowise.py": {
      "target": "shared/repowise.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/repowise.py",
        "summary": "Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода."
      },
      "hotspot": false,
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
        "tokens": 1199,
        "full_tokens": 1901,
        "pct_of_full": 63.1,
        "bodies_kept": [
          "workspace_for",
          "session_id",
          "enabled",
          "max_turns",
          "claude_mcp_config"
        ],
        "text": "\"\"\"Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.\n\nПрокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по\nworkspace, требует токен и идентификатор сессии, журналирует каждый обмен и\nрендерит из журнала артефакт диалога.\n\nПочему транскрипт забирается у прокси, а не пишется агентом. Guard стадии\n(`worker/activities.py`, проверка ожидаемого артефакта в `run_fnr_stage`) умеет\nпроверить только существование файла и его размер; отличить полный транскрипт\nот правдоподобного пересказа ему не с чем. Журнал на стороне прокси делает\nполноту свойством построения, а не добросовестности модели.\n\nМодуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и\n`shared/agent_events.py`. Он вызывается и из воркера, и из подготовки каталога\nразработки; лишний импорт втащил бы клиент GitHub вместе с токеном туда, где\nего быть не должно.\n\"\"\"\n\nfrom __future__ import annotations\n\nimport os\nimport urllib.error\nimport urllib.parse\nimport urllib.request\n\nfrom shared import repos\n\n# --- Виды агентов ---\n#\n# Попадают в идентификатор сессии: аналитика и разработка по одному Issue —\n# два разных диалога, и слить их в один журнал значило бы потерять оба.\nANALYSIS = \"analysis\"\nDEVELOP = \"openhands\"\n... 5 lines (34-38)\nCONTOUR = \"contour\"\nPRODUCT = \"product\"\n\nDEFAULT_MAX_TURNS = 12\nPROBE_TIMEOUT_SEC = 5.0\nTRANSCRIPT_TIMEOUT_SEC = 30.0\n\n# Имя сервера в конфигурации MCP. Фиксировано: на него ссылается промпт стадии.\nSERVER_NAME = \"repowise\"\n\n\ndef proxy_base() -> str:\n    return os.environ.get(\"REPOWISE_PROXY_URL\", \"\").rstrip(\"/\")\n\n\ndef agent_token() -> str:\n    return os.environ.get(\"REPOWISE_AGENT_TOKEN\", \"\")\n\n\ndef enabled() -> bool:\n    \"\"\"Интеграция включена только при заданном адресе прокси.\n\n    Пустой адрес — не отказ, а выключенная интеграция: стадия деградирует\n    штатно (см. `unavailable_artifact`), конвейер идёт дальше.\n    \"\"\"\n    return bool(proxy_base())\n\n\ndef max_turns() -> int:\n    \"\"\"Потолок ходов диалога.\n\n    Мусор в переменной не снимает потолок вовсе: стадия живёт внутри активности\n    с потолком времени, и неограниченный цикл вопросов — это и расход средств,\n    и зависший прогон.\n    \"\"\"\n    raw = os.environ.get(\"REPOWISE_MAX_TURNS\", \"\").strip()\n    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_MAX_TURNS\n\n\ndef workspace_for(repo: str) -> str:\n    \"\"\"`contour` для репозиториев из REPOWISE_CONTOUR_REPOS, иначе `product`.\n\n    Guard на пустой список обязателен: `repos.is_allowed` трактует пустоту как\n    «разрешено всё», а здесь это означало бы, что каждый репозиторий попал в\n    `contour`, — ровно наоборот.\n    \"\"\"\n    specs = [s for s in os.environ.get(\"REPOWISE_CONTOUR_REPOS\", \"\").split(\",\") if s.strip()]\n    if not specs:\n        return PRODUCT\n    return CONTOUR if repos.is_allowed(repo, specs) else PRODUCT\n\n\ndef session_id(repo: str, issue_number: int, agent: str) -> str:\n    \"\"\"Детерминированный идентификатор сессии.\n\n    Детерминированный по той же причине, что и идентификаторы прогонов\n    (`shared/workflow_ids.py`): повторный запуск по тому же Issue должен\n    попадать в ту же сессию, а не плодить осиротевшие журналы.\n\n    Слэш в имени репозитория заменяется на `__` — идентификатор уезжает в\n    query-параметр, и кодировать его на каждой стороне незачем. Тот же приём\n    применяется для каталога прогона (`worker/activities.py`, `_workspace_dir`).\n    \"\"\"\n    return f\"rw-{agent}-{repo.replace('/', '__')}-{issue_number}\"\n\n\ndef mcp_url(workspace: str, session: str) -> str:\n    query = urllib.parse.urlencode({\"workspace\": workspace, \"session\": session})\n    return f\"{proxy_base()}/mcp?{query}\"\n\n\ndef _headers() -> dict:\n    return {\"Authorization\": f\"Bearer {agent_token()}\"}\n\n\ndef claude_mcp_config(repo: str, issue_number: int, agent: str) -> dict:\n    \"\"\"Содержимое `.mcp.json` в рабочем каталоге прогона `claude -p`.\"\"\"\n    session = session_id(repo, issue_number, agent)\n    return {\n        \"mcpServers\": {\n            SERVER_NAME: {\n                \"type\": \"http\",\n                \"url\": mcp_url(workspace_for(repo), session),\n                \"headers\": _headers(),\n            }\n        }\n    }\n\n\ndef openhands_mcp_config(repo: str, issue_number: int, agent: str) -> dict:\n    \"\"\"Содержимое `~/.openhands/mcp.json` одноразового контейнера разработки.\n... 16 lines (130-145)\n\n\ndef available(timeout: float = PROBE_TIMEOUT_SEC) -> bool:\n    \"\"\"Отвечает ли прокси. Исключений не поднимает — недоступность не отказ.\n... 16 lines (150-165)\n\n\ndef transcript(session: str) -> str | None:\n    \"\"\"Отрендеренный транскрипт сессии либо None, если получить не удалось.\n... 15 lines (170-184)\n\n\ndef unavailable_artifact(repo: str, issue_number: int, agent: str, reason: str) -> str:\n    \"\"\"Артефакт диалога для случая, когда источник недоступен.\n... 35 lines (189-223)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 63.1% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 45.55,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
