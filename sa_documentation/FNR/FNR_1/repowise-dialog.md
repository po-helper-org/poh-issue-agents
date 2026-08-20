# Итог

## Архитектура пайплайнов BFT и FNR

### BFT Pipeline (Глубокий режим)
- **7 стадий**: `index`, `context`, `problem`, `concept`, `debate`, `draft`, `validate` ([`shared/bft.py:93`](worker/activities.py:93))
- **Точка входа**: [`worker/activities.py::run_bft_stage`](worker/activities.py:2732-2774)
- **Контроль прямых вызовов**: [`bft.direct_stages()`](shared/bft.py:366-372) читает `BFT_DIRECT_STAGES` из окружения

### FNR Pipeline (Анализ)
- **Точка входа**: [`worker/activities.py::run_fnr_stage`](worker/activities.py:1266-1321)
- **Инфраструктуры прямых вызовов нет** — все стадии идут через `_run_claude`

## Пути выполнения

### Путь через `claude -p` (дёшево, дорого по памяти)
- [`_run_claude()`](worker/activities.py:943-988) запускает `subprocess.run(["claude", "-p", prompt, ...])`
- **356 МБ RSS** на процесс — подтверждено замерами ([комментарий в коде](worker/activities.py:2752-2754))
- Креды: [`_claude_anthropic_creds()`](worker/activities.py:926-940) трансформирует `ZAI_*` → `ANTHROPIC_*`
- Протокол: Anthropic (not OpenAI), эндпоинт `/api/anthropic`

### Путь прямого вызова (уже реализовано для `draft`)
- [`_bft_direct_draft()`](worker/activities.py:2639-2725) — двухфазовая реализация
- Фаза 1: сбор каскада требований и якорей (JSON)
- Фаза 2: рендер документа из каскада
- Модель: `BFT_DIRECT_MODEL` (default "glm-4.6")
- Проверка полноты: [`cascade_gaps()`](shared/bft.py:389-443) между фазами
- **Выбор пути**: строка 2751 — `if stage_name in bft.direct_stages()`

## Креды и API

- **Единый ключ** `ZAI_API_KEY` для Python-стадий и `claude -p`
- **Трансформация**: `ZAI_BASE_URL` (OpenAI-формат) → `ANTHROPIC_BASE_URL` (Anthropic-формат)
- **Проксирование**: `claude -p` ходит в `api.z.ai/api/anthropic`, а не напрямую в Anthropic

## Существующая инфраструктура для прямых вызовов

1. **Переключатель**: `BFT_DIRECT_STAGES` env var → [`bft.direct_stages()`](shared/bft.py:366-372)
2. **Реализация**: [`_bft_direct_draft()`](worker/activities.py:2639-2725) для стадии `draft`
3. **LLM-клиент**: [`llm.complete()`](worker/llm.py:56) (обёртка над Anthropic SDK)
4. **Проверки качества**: [`CASCADE_FLOOR`](shared/bft.py:354), [`ANCHOR_FLOOR`](shared/bft.py:355), [`cascade_gaps()`](shared/bft.py:389-443)

## Кандидаты на прямой вызов (по описанию задачи)

**Оставить с агентом** (исследуют репозиторий):
- `index`, `context` — читают файлы по своему выбору

**Перевести на прямой вызов** (получают готовый вход):
- `problem`, `concept`, `debate`, `draft`, `validate`

## Состояние на сегодня

- Только `draft` имеет реализацию прямого вызова
- FNR полностью на `claude -p`
- Критерий приёмки описан в задаче, но не автоматизирован

# Открытые вопросы

Нет открытых вопросов — индекс ответил на все запросы.

# Диалог

## Ход 1: Обзор репозитория
**Инструмент**: `get_overview(poh-issue-agents)`
**Результат**: Получен обзор репозитория — 323 файла, основная логика в `worker/activities.py`, BFT-логика в `shared/bft.py`. Репозиторий часть workspace с соседями `poh-bft-writer`, `poh-pr-agents` и др.

## Ход 2: Поиск BFT-стадий
**Инструмент**: `search_codebase("bft-problem bft-concept...")`
**Результат**: Найдены ключевые файлы — `shared/bft.py` (определения стадий), `worker/activities.py` (исполнение), символ `run_bft_stage`.

## Ход 3: Обзор poh-bft-writer
**Инструмент**: `get_overview(poh-bft-writer)`
**Результат**: 54 файла, здоровое состояние. BFT-команды реализованы как скиллы в `.claude/skills/`. Основная логика пайплайна в `poh-issue-agents`, этот репозиторий — скиллы.

## Ход 4: Контекст run_bft_stage
**Инструмент**: `get_context(["run_bft_stage", "shared/bft.py"])`
**Результат**: Обнаружено:
- 7 стадий в `DEEP_STAGE_NAMES`
- Функция `direct_stages()` с env var `BFT_DIRECT_STAGES`
- Скелет `run_bft_stage` с условием на строке 2751

## Ход 5: Полное тело run_bft_stage
**Инструмент**: `get_symbol("worker/activities.py::run_bft_stage")`
**Результат**: Полный код функции. Подтверждено:
- Строка 2751: проверка `if stage_name in bft.direct_stages()`
- При true → `_bft_direct_draft`, иначе → `_run_claude`
- Комментарий 2752-2754 явно упоминает 356 МБ RSS

## Ход 6: Поиск _run_claude и _bft_direct_draft
**Инструмент**: `get_answer("Where are _bft_direct_draft and _run_claude...")`
**Результат**: Получены полные тела обеих функций:
- `_run_claude`: subprocess `claude -p` с трансформацией кредов
- `_bft_direct_draft`: двухфазовая реализация с `llm.complete()`

## Ход 7: Состояние FNR
**Инструмент**: `get_answer("Is there similar infrastructure for FNR...")`
**Результат**: `run_fnr_stage` не имеет инфраструктуры прямых вызовов — все стадии через `_run_claude`. Обнаружена логика degradation для Repowise-стадии.

## Ход 8: Детали кредов
**Инструмент**: `get_symbol("worker/activities.py::_claude_anthropic_creds")`
**Результат**: Полная логика трансформации `ZAI_*` → `ANTHROPIC_*` с парсингом URL эндпоинта.


---
session: rw-analysis-po-helper-org__poh-issue-agents-77
workspace: contour
turns: 11
started: 2026-08-20T19:11:31Z
finished: 2026-08-20T19:12:12Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 32 мин |

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

## Ход 2 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "bft-writer pipeline stages claude -p",
  "mode": "concept",
  "repo": "poh-bft-writer",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: install.sh",
      "page_type": "infra_page",
      "snippet": "BLUE='\\033[0;34m'; YELLOW='\\033[1;33m'; NC='\\033[0m'\nREPO_URL=\"https://github.com/po-helper-org/poh-bft-writer.git\"\n\n# Источник: если запущено из клона — текущая папка; если через curl — клонируем\nif",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "install.sh",
      "confidence_score": 1.0
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "c7fe9bd7d1b2",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "install.sh"
    }
  ]
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "mode": "concept",
  "query": "bft-problem bft-concept bft-debate bft-draft bft-validate",
  "repo": "poh-bft-writer"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Repository Overview: poh-bft-writer",
      "page_type": "repo_overview",
      "snippet": "# Repository Overview: poh-bft-writer\n\n**Files:** 54 | **Lines:** 15621\n\n## Project Summary\n\n\n`poh-bft-writer` is a markdown codebase of 54 files.\n\n\n\n\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank ov",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "poh-bft-writer",
      "confidence_score": 1.0
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "c7fe9bd7d1b2",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 4 · `get_overview` · contour

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

## Ход 5 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "mode": "concept",
  "query": "claude -p bft validate draft problem concept debate"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "# shared/bft.py\n\n## Overview\n\nБФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: worker/consolidation_activities.py",
      "page_type": "file_page",
      "snippet": "ef synthesize_unifying_issue(increment: Increment, profiles: list[SolutionProfile]) -> UnifyingIssueDraft |\n| `fetch_open_issues` | function | def fetch_open_issues(cfg: ConsolidationInput) -> list[Is",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "worker/consolidation_activities.py",
      "confidence_score": 0.98
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "and: str, ok: bool) -> None |\n| `classify_issue` | function | def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult |\n| `FOLLOWUP_THREAD_COMMENTS` | constant | FOL",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "Architecture Scripts",
      "page_type": "module_page",
      "snippet": "# Architecture Scripts\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascri",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts",
      "confidence_score": 0.94
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
      "confidence_score": 0.93
    },
    {
      "title": "Utility Shared",
      "page_type": "module_page",
      "snippet": "аёт вебхук, а тот же разбор нужен воркеру — чтобы исключить сами команды из треда, уходя\n\n- `shared/bft.py`: БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария. Модуль намеренно",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "shared",
      "confidence_score": 0.91
    },
    {
      "title": "Symbol: worker.activities.decompose_issue",
      "page_type": "symbol_spotlight",
      "snippet": "ivities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::decompose_issue",
      "file": "worker/activities.py",
      "confidence_score": 0.9
    },
    {
      "title": "Symbol: worker.activities.run_bft_stage",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) -> d",
      "relevance_score": 2.687,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_stage",
      "file": "worker/activities.py",
      "confidence_score": 0.89
    },
    {
      "title": "File: shared/workflow_types.py",
      "page_type": "file_page",
      "snippet": "PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `Es",
      "relevance_score": 2.677,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py",
      "confidence_score": 0.88
    },
    {
      "title": "File: shared/commands.py",
      "page_type": "file_page",
      "target_path": "shared/commands.py",
      "snippet": "Разбор slash-команд из комментариев Issue и сборка входа аналитики.",
      "relevance_score": 2.051,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.68
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
      "path": "shared/bft.py"
    },
    {
      "path": "worker/consolidation_activities.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "scripts/e2e_live.py"
    },
    {
      "path": "shared/decomposition.py"
    },
    {
      "path": "worker/consolidation_workflow.py"
    },
    {
      "path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
    },
    {
      "path": ".claude/skills/architecture/scripts/generate_taxonomy.py"
    }
  ]
}

## Ход 6 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/activities.py::run_bft_stage",
    "shared/bft.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/activities.py::run_bft_stage": {
      "target": "worker/activities.py::run_bft_stage",
      "type": "symbol",
      "docs": {
        "name": "run_bft_stage",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.run_bft_stage",
        "signature": "async def run_bft_stage(req: BftRequest, stage_name: str) -> dict",
        "docstring": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.\n\n    Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной\n    активностью весь пайплайн был бы одним баром в Event History на десятки\n    минут, и застрявшая стадия не называла бы себя.",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_followups.py",
          "tests/test_e2e_issue_lifecycle.py",
          "tests/test_fnr_partial_resume.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 20,
        "last_fix_days_ago": 0,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 5780,
        "full_tokens": 33526,
        "pct_of_full": 17.2,
        "bodies_kept": [],
        "text": "[repowise#a64651acfa50: 748 lines omitted (~5780 tokens); restore: repowise expand a64651acfa50]",
        "verified": true,
        "of_file": "worker/activities.py",
        "symbol_hint": "Skeleton of the file defining 'run_bft_stage'. For that symbol's full body call get_symbol('worker/activities.py::run_bft_stage').",
        "omitted": true
      },
      "episodes": 20
    },
    "shared/bft.py": {
      "target": "shared/bft.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/bft.py",
        "summary": "БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария."
      },
      "hotspot": true,
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
        "tokens": 2096,
        "full_tokens": 6049,
        "pct_of_full": 34.7,
        "bodies_kept": [
          "epic_slug",
          "deep_stages",
          "stage_artifacts",
          "_table",
          "statement_path"
        ],
        "text": "\"\"\"БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py`. Формат комментария и перечень стадий проверяются напрямую, без\nпрогона воркфлоу и без обращения к модели.\n\nПочему БФТ, а не прежний advisor-ответ\n--------------------------------------\nКлассификация отвечала свободным текстом «Ситуация / Ограничение / Варианты\nрешения / Оценка сложности». В нём нет сценария приёмки, нет границ и нет\nсписка открытых вопросов с владельцами, зато есть «варианты решения» — то есть\nпроектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)\nдаёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`\n→ `Границы` → `Документация` плюс таблицу требований на цитатах.\n\nДва режима, две цены\n--------------------\n`fast` — один вызов модели по тексту Issue и треду: секунды, комментарий в Issue.\n`deep` — канонический пайплайн `bft-writer` внутри клона репозитория: минуты,\nартефакты в ветке. Первый идёт сам на триаже, второй — только по явной команде:\nдорогую стадию запускает человек, а не догадка агента.\n\"\"\"\n\nimport json\nimport os\nimport re\n\nFAST = \"fast\"\nDEEP = \"deep\"\nMODES = (FAST, DEEP)\n\n# Ветка артефактов глубокого прогона. Отдельная от `research/issue-N` (цепочка\n# FNR): у документов разные авторы и разная судьба, и складывать их в одну ветку\n# значило бы, что повторный прогон одного затирает историю другого.\nBRANCH_PREFIX = \"bft-research\"\n\n# Корень документации bft-writer внутри воркспейса — дефолт `docs_path` из\n# `bft-config.md`. Задан здесь явно, чтобы публикация знала, что забирать, не\n# угадывая по маске.\nDOCS_ROOT = \".bft/documentation\"\n\n\ndef epic_slug(issue_number: int) -> str:\n    \"\"\"Имя эпика для пайплайна — от НОМЕРА Issue, а не от заголовка.\n\n    Заголовок редактируют, и slug из него менял бы каталог артефактов между\n    прогонами: второй `/bft-deep` писал бы рядом с первым, а не поверх, и\n    «документ с дополнительными требованиями» превращался бы во второй документ.\n    \"\"\"\n    return f\"issue-{issue_number}\"\n\n\ndef branch(issue_number: int) -> str:\n    return f\"{BRANCH_PREFIX}/{epic_slug(issue_number)}\"\n\n\ndef epic_dir(issue_number: int) -> str:\n    return f\"{DOCS_ROOT}/{epic_slug(issue_number)}\"\n\n\ndef artefacts_dir(issue_number: int) -> str:\n    return f\"{epic_dir(issue_number)}/artefacts\"\n\n\ndef statement_path(issue_number: int) -> str:\n    \"\"\"Постановка от заказчика — файл, который пайплайн читает вместо JIRA.\n\n    В контуре Issue трекера нет: `/bft-context-gen` штатно тянет эпик из JIRA, а\n    здесь его роль играет сам Issue вместе с тредом и уточнениями из команды.\n    ... 4 lines (70-73)\n\n\ndef document_path(issue_number: int) -> str:\n    \"\"\"Главный документ БФТ — то, что открывает человек.\"\"\"\n    ... 9 lines (78-86)\nDEEP_STAGE_NAMES: tuple[str, ...] = (\n    \"index\", \"context\", \"problem\", \"concept\", \"debate\", \"draft\", \"validate\",\n)\n\n\ndef deep_stages(issue_number: int) -> list[tuple[str, str, str | None, str | None]]:\n    \"\"\"(имя, промпт, ожидаемый артефакт, требуемый вход) для каждой стадии.\n\n    Промпт — `/<команда> <аргументы>` и ничего больше: `claude -p` разворачивает\n    команду только тогда, когда она стоит первой, а произвольный текст после\n    аргументов команда прочитает как ещё один аргумент.\n\n    `index` и `debate` ожидаемого файла не имеют: первый строит каталог\n    `.bft/index/`, второй дописывает вердикт в конец `concept.md`.\n    ... 20 lines (101-120)\n\n\ndef deep_stage(name: str, issue_number: int) -> tuple[str, str | None, str | None]:\n    \"\"\"(промпт, ожидаемый артефакт, требуемый вход) стадии по имени.\"\"\"\n    ... 10 lines (125-134)\nDEEP_HINT = (\n    \"Если задача касается больших изменений — запустите команду `/bft-deep` \"\n    \"и ответьте на ряд этих уточняющих вопросов:\"\n)\n\nDEEP_HINT_NO_QUESTIONS = (\n    \"Если задача касается больших изменений — запустите команду `/bft-deep` \"\n    \"(можно с уточнениями в том же комментарии): она соберёт полный БФТ по \"\n    \"канону и приложит артефакты веткой.\"\n)\n\n\ndef _bullets(items: list[str]) -> str:\n    return \"\\n\".join(f\"* {item.strip()}\" for item in items if item and item.strip())\n\n\ndef _numbered(items: list[str]) -> str:\n    kept = [item.strip() for item in items if item and item.strip()]\n    return \"\\n\".join(f\"{i}. {item}\" for i, item in enumerate(kept, 1))\n\n\ndef _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:\n    \"\"\"Markdown-таблица из строк-словарей. Пустой список строк → пустая строка.\n\n    В `/bft-fast` требования уезжают вложением csv. В Issue вложений нет, и\n    таблица — единственная форма, в которой они и читаются глазами, и остаются\n    ... 12 lines (161-172)\n\n\ndef render_letter(\n    *,\n    goal: str,\n    how_to_demo: list[str],\n    open_questions: list[str],\n    scope: str,\n    documentation: list[str],\n    requirements: list[dict],\n    personas: list[dict],\n    revision: int = 1,\n) -> str:\n    \"\"\"Комментарий fast-режима: письмо `/bft-fast` плюс приписка про `/bft-deep`.\n... 54 lines (187-240)\n\n\ndef render_statement(\n    *,\n    title: str,\n    body: str,\n    thread: str,\n    instructions: str,\n    issue_number: int,\n    repo: str,\n) -> str:\n    \"\"\"Постановка для глубокого прогона — единственный вход задачи в пайплайн.\n... 29 lines (253-281)\n\n\ndef render_config() -> str:\n    \"\"\"`bft-config.md` для клона — конфигурация пайплайна на этот прогон.\n... 20 lines (286-305)\n\n\ndef render_deep_summary(repo: str, issue_number: int, files: list[str]) -> str:\n    \"\"\"Сводка глубокого прогона: где лежит документ и что ещё появилось.\"\"\"\n    ... 40 lines (310-349)\nCASCADE_FLOOR: dict[str, int] = {\"БТ\": 4, \"ПТ\": 5, \"ИТ\": 6, \"ФТ\": 10, \"НФТ\": 4}\nANCHOR_FLOOR = 24\n\nCASCADE_SCHEMA = \"\"\"{\n  ... 8 lines (354-361)\n\n\ndef direct_stages() -> set[str]:\n    \"\"\"Стадии, которые идут прямыми вызовами вместо `claude -p`.\n... 7 lines (366-372)\n\n\ndef parse_cascade(text: str) -> dict:\n    \"\"\"JSON каскада из ответа модели.\n... 8 lines (377-384)\n\n\ndef cascade_gaps(cascade: dict, line_counts: dict[str, int]) -> list[str]:\n    \"\"\"Чего каскаду не хватает — претензиями на языке добора.\n... 55 lines (389-443)\ndef stage_artifacts(issue_number: int) -> dict[str, str]:\n    \"\"\"Стадия → путь её артефакта. Только стадии, у которых он есть.\n\n    `index` строит каталог `.bft/index/`, `debate` дописывает вердикт в конец\n    `concept.md` — по файлу их «сделанность» не определить, поэтому в карте их\n    ... 5 lines (449-453)\n\n\ndef done_stages(issue_number: int, exists) -> list[str]:\n    \"\"\"Стадии, чей артефакт уже лежит в рабочем каталоге.\n... 6 lines (458-463)\n\n\ndef remaining_stages(issue_number: int, done: list[str]) -> list[str]:\n    \"\"\"Стадии, которые осталось прогнать — в каноническом порядке.\"\"\"\n    return [name for name in DEEP_STAGE_NAMES if name not in done]\n\n\ndef render_partial_summary(repo: str, issue_number: int, files: list[str],\n                           done: list[str], reason: str) -> str:\n    \"\"\"Комментарий о прогоне, оборванном на середине.\n... 39 lines (474-512)\nDIALOG_LOG = \"dialog-log.md\"\n\n\ndef dialog_log_path(issue_number: int) -> str:\n    return f\"{artefacts_dir(issue_number)}/{DIALOG_LOG}\"\n\n\ndef render_dialog_entry(*, stage: str, actor: str, step: str, outcome: str,\n                        detail: str = \"\", tokens: str = \"\",\n                        elapsed: float | None = None) -> str:\n    \"\"\"Одна запись журнала — строка таблицы.\n... 9 lines (524-532)\n\n\nDIALOG_LOG_HEADER = (\n    \"# Журнал прогона БФТ\\n\\n\"\n    \"Что делал пайплайн и чем это кончилось. Пишется по ходу, поэтому уцелевает\\n\"\n    \"и у оборванного прогона — по нему видно, на чём именно остановились.\\n\\n\"\n    \"| Стадия | Исполнитель | Шаг | Исход | Время | Токены | Подробности |\\n\"\n    \"|---|---|---|---|---|---|---|\\n\"\n)\n... 14 lines (542-555)\nENTIRE_BRANCH_PREFIX = \"entire/\"\n\n\ndef parse_session_id(text: str) -> str:\n    \"\"\"Id сессии entire из вывода `entire session list`.\n... 9 lines (561-569)\n\n\ndef parse_session_branch(text: str) -> str:\n    \"\"\"Ветка чекпоинтов из вывода `git branch` или `git for-each-ref`.\"\"\"\n    ... 5 lines (574-578)\n\n\ndef render_session_hint(repo: str, session_id: str, session_branch: str) -> str:\n    \"\"\"Блок про сессию для комментария: где диалог и чем продолжить.\n... 15 lines (583-597)\n\n\ndef split_session_arg(instructions: str) -> tuple[str, str]:\n    \"\"\"(id сессии, остальные инструкции) из хвоста `/bft-deep`.\n... 12 lines (602-613)\n",
        "verified": true
      }
    }
  },
  "_meta": {
    "timing_ms": 393.6,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "a64651acfa50",
        "dd429360a5de"
      ],
      "tokens": 5824,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {},
  "omission_marker": "[repowise#dd429360a5de: 5 lines omitted (~44 tokens); restore: repowise expand dd429360a5de]"
}

## Ход 7 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::run_bft_stage"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::run_bft_stage",
  "file": "worker/activities.py",
  "name": "run_bft_stage",
  "kind": "function",
  "qualified_name": "worker.activities.run_bft_stage",
  "signature": "async def run_bft_stage(req: BftRequest, stage_name: str) -> dict",
  "language": "python",
  "start_line": 2732,
  "end_line": 2774,
  "symbol_start_line": 2732,
  "symbol_end_line": 2774,
  "source": "  2732\tasync def run_bft_stage(req: BftRequest, stage_name: str) -> dict:\n  2733\t    \"\"\"Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.\n  2734\t\n  2735\t    Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной\n  2736\t    активностью весь пайплайн был бы одним баром в Event History на десятки\n  2737\t    минут, и застрявшая стадия не называла бы себя.\n  2738\t    \"\"\"\n  2739\t    prompt, expected, requires = bft.deep_stage(stage_name, req.issue_number)\n  2740\t    clone_dir = _require_bft_workspace(req, requires)\n  2741\t    if expected:\n  2742\t        done = Path(clone_dir) / expected\n  2743\t        if done.is_file() and done.stat().st_size > 0:\n  2744\t            # Артефакт приехал с веткой прошлого прогона: стадия уже сделана, и\n  2745\t            # повторять её — платить второй раз за тот же документ. Так `/bft-deep`\n  2746\t            # после срыва продолжает с места обрыва, а не начинает заново.\n  2747\t            logger.info(\"БФТ %s#%s: стадия %s уже сделана — пропускаю\",\n  2748\t                        req.repo, req.issue_number, stage_name)\n  2749\t            return {\"stage\": stage_name, \"artifact\": expected,\n  2750\t                    \"bytes\": done.stat().st_size, \"skipped\": True}\n  2751\t    if stage_name in bft.direct_stages() and expected:\n  2752\t        # Стадия без исследования репозитория: вход готов, выход — один файл.\n  2753\t        # Агент здесь стоит 356 МБ RSS и ничего не добавляет, кроме способности\n  2754\t        # дочитать файл, который мы и так подаём (#77).\n  2755\t        document = await _run_with_heartbeat(\n  2756\t            _bft_direct_draft, req, clone_dir, label=f\"bft:{stage_name}\")\n  2757\t        path = Path(clone_dir) / expected\n  2758\t        path.parent.mkdir(parents=True, exist_ok=True)\n  2759\t        path.write_text(document, encoding=\"utf-8\")\n  2760\t    else:\n  2761\t        # Диалог этой стадии пишет entire: у `claude -p` есть сессия, за которую\n  2762\t        # он цепляется хуками. Дублировать её журналом значит вести две записи\n  2763\t        # одного и того же и обе поддерживать.\n  2764\t        await _run_with_heartbeat(_run_claude, prompt, clone_dir,\n  2765\t                                  label=f\"bft:{stage_name}\")\n  2766\t    artifact: str | None = None\n  2767\t    size = 0\n  2768\t    if expected:\n  2769\t        path = Path(clone_dir) / expected\n  2770\t        if not path.exists():\n  2771\t            raise RuntimeError(f\"стадия {stage_name}: артефакт {expected} не создан\")\n  2772\t        artifact = expected\n  2773\t        size = path.stat().st_size\n  2774\t    return {\"stage\": stage_name, \"artifact\": artifact, \"bytes\": size}",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 19.39,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "mode": "symbol",
  "query": "_bft_direct_draft _run_claude"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueBft::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2088,
      "end_line": 2169,
      "signature": "async def run(self, req: BftRequest) -> bool",
      "qualified_name": "worker.workflows.IssueBft.run",
      "language": "python",
      "score": 52.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueEstimation::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2218,
      "end_line": 2274,
      "signature": "async def run(self, req: EstimateRequest) -> None",
      "qualified_name": "worker.workflows.IssueEstimation.run",
      "language": "python",
      "score": 46.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/smoke_temporal.py::SmokeWorkflow::run",
      "name": "run",
      "kind": "method",
      "file": "scripts/smoke_temporal.py",
      "start_line": 47,
      "end_line": 50,
      "signature": "async def run(self, x: str) -> str",
      "qualified_name": "scripts.smoke_temporal.SmokeWorkflow.run",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::BFT",
      "name": "BFT",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 24,
      "end_line": 24,
      "signature": "BFT = \"bft\"",
      "qualified_name": "shared.commands.BFT",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/consolidation_workflow.py::ConsolidationWorkflow::run",
      "name": "run",
      "kind": "method",
      "file": "worker/consolidation_workflow.py",
      "start_line": 15,
      "end_line": 64,
      "signature": "async def run(self, cfg: ConsolidationInput)",
      "qualified_name": "worker.consolidation_workflow.ConsolidationWorkflow.run",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
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
      "path": "worker/workflows.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "worker/consolidation_workflow.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches '_bft_direct_draft _run_claude'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 9 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Where are _bft_direct_draft and _run_claude functions defined in worker/activities.py and what do they do?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `_run_claude`, `_bft_direct_draft`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    "worker/worker.py",
    "worker/activities.py::run_bft_stage",
    "worker/activities.py::run_fnr_stage",
    "worker/activities.py::DuplicateExtraction"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "worker/activities.py",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 103 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) -> None |\n| `close_as_spam` | function | def close_as_spam(issue: IssueI",
      "score": 4.25,
      "key_symbols": [
        {
          "name": "WORKSPACE_DIR",
          "kind": "constant",
          "signature": "WORKSPACE_DIR = Path(\"/app/workspace\")",
          "docstring": "",
          "start_line": 70,
          "end_line": 70,
          "source_excerpt": "WORKSPACE_DIR = Path(\"/app/workspace\")"
        },
        {
          "name": "CLAUDE_STAGE_TIMEOUT_SEC",
          "kind": "constant",
          "signature": "CLAUDE_STAGE_TIMEOUT_SEC = 900",
          "docstring": "",
          "start_line": 752,
          "end_line": 752,
          "source_excerpt": "CLAUDE_STAGE_TIMEOUT_SEC = 900"
        },
        {
          "name": "_workspace_dir",
          "kind": "function",
          "signature": "def _workspace_dir(analyze: AnalyzeInput) -> Path:",
          "docstring": "Детерминированный рабочий каталог прогона (переживает activity в пределах\n    жизни контейнера). База — ANALYSIS_WORKSPACE_ROOT или системный temp.",
          "start_line": 815,
          "end_line": 820
        },
        {
          "name": "_build_workspace",
          "kind": "function",
          "signature": "def _build_workspace(analyze: AnalyzeInput) -> str:",
          "docstring": "Свежий каталог: снести остаток прежнего прогона, clone, repomix.\n\n    Ветка артефактов забирается, если уже есть: повторный `/analyze` после\n    обрыва — это продолжение, а не второй анализ рядом. Стадия с готовым\n    артефактом тогда пропускается, и прогон не платит второй раз за уже\n    написанный документ. Без этого пропуск не сработал бы вовсе: в свежем\n    клоне дефолтной ветки прошлых артефактов нет.",
          "start_line": 841,
          "end_line": 862
        },
        {
          "name": "_require_workspace",
          "kind": "function",
          "signature": "def _require_workspace(analyze: AnalyzeInput, requires: str | None) -> str:",
          "docstring": "Guard стадии: каталог+repomix на месте? требуемый вход на месте? Иначе\n    fail-fast (без пере-клона — он дал бы свежий репозиторий без артефактов).",
          "start_line": 865,
          "end_line": 875
        },
        {
          "name": "_claude_anthropic_creds",
          "kind": "function",
          "signature": "def _claude_anthropic_creds() -> tuple[str, str]:",
          "docstring": "Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n    не нужно, но если заданы — приоритетнее (явный override).",
          "start_line": 926,
          "end_line": 940
        },
        {
          "name": "_run_claude",
          "kind": "function",
          "signature": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:",
          "docstring": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.",
          "start_line": 943,
          "end_line": 988,
          "source_excerpt": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:\n    \"\"\"Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.\n    \"\"\"\n    token, base = _claude_anthropic_creds()\n    # Понятная ошибка вместо голого \"exit 1\", если z.ai не сконфигурирован:\n    # без креды claude-code уходит на дефолтный Anthropic API и падает.\n    if not token or not base:\n        raise RuntimeError(\n            \"claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL \"\n            \"(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера.\"\n        )\n    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера\n    # работает от root, а тот флаг под root запрещён самим claude-code\n    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).\n    command = [\"claude\", \"-p\", prompt, \"--permission-mode\", \"acceptEdits\"]\n    if mcp_config:\n        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы\n        # затесаться серверы из окружения образа, и стадия ходила бы не туда,\n        # куда её послали.\n        #\n        # --allowedTools по имени сервера: без него вызов инструмента ждёт\n        # подтверждения, которого в неинтерактивном режиме не будет, и диалог\n        # молча не состоится.\n        command += [\"--mcp-config\", mcp_config, \"--strict-mcp-config\",\n                    \"--allowedTools\", f\"mcp__{repowise.SERVER_NAME}\"]\n    result = subprocess.run(\n        command,\n        cwd=cwd, capture_output=True, text=True,\n        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,\n        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.\n        env={**os.environ, \"ANTHROPIC_AUTH_TOKEN\": token, \"ANTHROPIC_BASE_URL\": base},\n    )\n    if result.returncode != 0:\n        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба\n        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.\n        detail = result.stderr.strip() or result.stdout.strip() or \"(пустой вывод)\"\n        raise RuntimeError(f\"claude -p exit {result.returncode}: {detail[-1500:]}\")"
        },
        {
          "name": "prepare_workspace",
          "kind": "function",
          "signature": "async def prepare_workspace(analyze: AnalyzeInput) -> None:",
          "docstring": "Стадия 0 пайплайна /analyze: свежий clone + repomix в детерминированный\n    каталог. Идемпотентна (сносит остаток и строит заново).",
          "start_line": 1163,
          "end_line": 1166
        },
        {
          "name": "cleanup_workspace",
          "kind": "function",
          "signature": "async def cleanup_workspace(analyze: AnalyzeInput) -> None:",
          "docstring": "Best-effort снос рабочего каталога прогона.",
          "start_line": 1390,
          "end_line": 1392
        },
        {
          "name": "_bft_direct_draft",
          "kind": "function",
          "signature": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:",
          "docstring": "Стадия `draft` двумя вызовами модели вместо агента.\n\n    Первый вызов собирает каскад требований и якоря структурой, второй рендерит\n    из них документ. Между ними — программная проверка полноты и якорей: ради\n    неё разбиение и сделано, одним ответом проверять нечего.",
          "start_line": 2639,
          "end_line": 2725,
          "source_excerpt": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:\n    \"\"\"Стадия `draft` двумя вызовами модели вместо агента.\n\n    Первый вызов собирает каскад требований и якоря структурой, второй рендерит\n    из них документ. Между ними — программная проверка полноты и якорей: ради\n    неё разбиение и сделано, одним ответом проверять нечего.\n    \"\"\"\n    model = os.environ.get(\"BFT_DIRECT_MODEL\", \"glm-4.6\")\n    sources = _bft_sources(clone_dir)\n    line_counts = {rel: len(body.splitlines()) for rel, body in sources.items()}\n    inputs = _bft_stage_inputs(clone_dir, req.issue_number, sources)\n    issue = req.issue_number\n\n    system = _bft_stage_system(\n        \"draft\", \"СЕЙЧАС ты собираешь ТОЛЬКО каскад требований и таблицу якорей. \"\n                 \"Документ не пишешь — его соберёт следующий шаг.\")\n    cascade_task = (\n        f\"{inputs}\\n\\n---\\n\\n# Задание\\n\\n\"\n        f\"Собери каскад требований БФТ для эпика issue-{issue} и таблицу якорей.\\n\\n\"\n        \"Разворачивай, а не сворачивай: каждый пункт TOBE из problem.md, каждое \"\n        \"уточнение постановки, каждая ветка сценария демонстрации, каждый экран \"\n        \"актора, каждая измеримая характеристика — отдельное требование.\\n\\n\"\n        \"Якоря: As-Is-факт → `файл:строки` из исходников выше (ранг R1, тип \"\n        \"«Код»); требование постановки → `po-statement.md:N` (R2, «Постановка»); \"\n        \"решение концепта → `concept.md` (R2, «Решение»). To-Be на код НЕ \"\n        \"якорится.\\n\\n\"\n        \"Нижняя граница: \"\n        + \", \".join(f\"{k} ≥ {v}\" for k, v in bft.CASCADE_FLOOR.items())\n        + f\", якорей ≥ {bft.ANCHOR_FLOOR}.\\n\\n\"\n        f\"Верни ТОЛЬКО JSON по схеме:\\n{bft.CASCADE_SCHEMA}\")\n\n    started = time.monotonic()\n    cascade = bft.parse_cascade(llm.complete(system, cascade_task, model=model))\n    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"каскад требований\",\n        outcome=\"готово\", elapsed=time.monotonic() - started,\n        detail=f\"требований {len(cascade.get('requirements') or [])}, \"\n               f\"якорей {len(cascade.get('anchors') or [])}\"))\n    for _ in range(BFT_TOP_UP_ATTEMPTS):\n        gaps = bft.cascade_gaps(cascade, line_counts)\n        if not gaps:\n            break\n        logger.info(\"БФТ %s#%s: добор каскада — %s\", req.repo, issue, \"; \".join(gaps))\n        _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n            stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"добор каскада\",\n            outcome=\"добор\", detail=\"; \".join(gaps)))\n        top_up = (f\"{inputs}\\n\\n---\\n\\n# Уже собрано\\n\\n```json\\n\"\n                  + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n                  \"# Чего не хватает\\n\\n- \" + \"\\n- \".join(gaps) + \"\\n\\n\"\n                  \"Верни ПОЛНЫЙ JSON той же схемы: собранное дословно плюс \"\n                  \"недостающее. Ничего не удаляй и не переформулируй.\")\n        cascade = bft.parse_cascade(llm.complete(system, top_up, model=model))\n\n    left = bft.cascade_gaps(cascade, line_counts)\n    if left:\n        # Не падаем: неполный каскад — это плохой документ, а не сорванный\n        # прогон, и человеку полезнее увидеть его с честной пометкой в логе,\n        # чем не увидеть ничего. Полнота проверяется стадией `validate`.\n        logger.warning(\"БФТ %s#%s: каскад неполон после добора — %s\",\n                       req.repo, issue, \"; \".join(left))\n\n    system2 = _bft_stage_system(\n        \"draft\", \"СЕЙЧАС ты рендеришь документ из УТВЕРЖДЁННОГО каскада. \"\n                 \"Требования и якоря уже собраны: переносишь их все, ничего не \"\n                 \"теряя и не добавляя новых идентификаторов.\")\n    render_task = (\n        f\"{inputs}\\n\\n---\\n\\n# Утверждённый каскад\\n\\n```json\\n\"\n        + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n        f\"# Задание\\n\\nСобери чистовик БФТ issue-{issue} по корп-шаблону. Все \"\n        \"требования каскада обязаны попасть в свои разделы, все якоря — в раздел \"\n        \"«Якоря истины» таблицей `Факт | Источник | Ранг | Тип`.\\n\\n\"\n        \"Файловых инструментов нет: ты не записываешь файл, а выводишь его \"\n        \"содержимое целиком.\\n\\n\"\n        f\"YAML-шапка ровно такая:\\n```\\n---\\nEpic: issue-{issue}\\n\"\n        \"Название: <название>\\nСтатус: Черновик\\nДата: <сегодня>\\n\"\n        \"Автор: bft-draft\\nВерсия: 1.0\\n---\\n```\\n\\n\"\n        \"Заголовки разделов — только `##`. Ответ начинается со строки `---` и \"\n        \"заканчивается последней строкой таблицы якорей, без обрамляющих \"\n        \"```-блоков и без фраз до или после.\")\n\n    started = time.monotonic()\n    document = llm.complete(system2, render_task, model=model)\n    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"рендер документа\",\n        outcome=\"готово\", elapsed=time.monotonic() - started,\n        detail=f\"{len(document)} символов\"))\n    return document"
        }
      ]
    },
    {
      "path": "worker/worker.py",
      "title": "File: worker/worker.py",
      "summary": "`worker/worker.py` is a python source file in the Application layer.",
      "snippet": "`worker/worker.py` is a python source file in the Application layer.",
      "excerpt": "# worker/worker.py\n\n## Overview\n\n`worker/worker.py` is a python source file in the Application layer.\n\nIt exposes 1 public symbol and depends on 7 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `worker/activities.py`\n- `worker/consolidation_activities.py`\n- `worker/consolidation_workflow.py`\n- `shared/__init__.py`\n- `shared/sentry_setup.py`\n- `shared/temporal_client.py`\n- `worker/workflows.py`\n\n## Used by\n\nImported by 23 files in this repository.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bft_workflow.py`\n- `tests/test_clarify_after_analysis.py`\n- `tests/test_comment_ack.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_duplicate_phase_transitions.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_fnr3_workflow.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_loop.py`\n- `tests/test_park_deadline_absolute.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_workflow_analysis.py`\n- `tests/test_workflow_batch.py`\n- `tests/test_workflow_closed_by_merge.py`\n- `tests/test_workflow_estimation.py`\n- `tests/test_workflow_issue_closed.py`\n- `tests/test_workflow_lifecycle_stage.py`\n- `tests/test_workflow_protocol.py`\n\n## Usage Notes\n\n**Layer:** Application | **Role:** edge_connector\n\n## Questions this page answers\n\n- What does `",
      "score": 2.975,
      "key_symbols": [
        {
          "name": "main",
          "kind": "function",
          "signature": "async def main() -> None:",
          "docstring": "",
          "start_line": 34,
          "end_line": 121
        }
      ]
    },
    {
      "path": "worker/activities.py::run_bft_stage",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.run_bft_stage",
      "summary": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.",
      "snippet": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) -> d",
      "excerpt": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) -> dict\n```\n\n## Overview\n\nОдна стадия канонического пайплайна БФТ — отдельный `claude -p`.\n\nРазложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной\nактивностью весь пайплайн был бы одним баром в Event History на десятки\nминут, и застрявшая стадия не называла бы себя.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n31 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_followups.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_phases.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_closing.py`\n- `tests/test_protocol_state.py`\n- `tests/test_ready_for_dev.py`\n- `t",
      "score": 2.25
    },
    {
      "path": "worker/activities.py::run_fnr_stage",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.run_fnr_stage",
      "summary": "Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога, затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.",
      "snippet": "# worker.activities.run_fnr_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str",
      "excerpt": "# worker.activities.run_fnr_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict\n```\n\n## Overview\n\nОдна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\nзатем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\nотчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n31 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_followups.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_phases.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_closing.py`\n- `tests/test_protocol_state.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_repowise_develop.py`\n\n_and 6 mor",
      "score": 2.177
    },
    {
      "path": "worker/activities.py::DuplicateExtraction",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.DuplicateExtraction",
      "summary": "`DuplicateExtraction` is a class defined in `worker/activities.py`. It carries no docstring.",
      "snippet": "# worker.activities.DuplicateExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass DuplicateExtraction\n```\n\n## Overview\n\n`DuplicateExtraction` i",
      "excerpt": "# worker.activities.DuplicateExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass DuplicateExtraction\n```\n\n## Overview\n\n`DuplicateExtraction` is a class defined in `worker/activities.py`. It carries no docstring.\n\n## Where it is used\n\n31 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_followups.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_phases.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_closing.py`\n- `tests/test_protocol_state.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_repowise_develop.py`\n\n_and 6 more._\n\n## Implementation\n\n```\nclass DuplicateExtraction(BaseModel):\n    candidates: list[DuplicateCandidate]\n```\n\n## Questions this page answers\n\n- Where is `DuplicateExtraction` defined?\n- What is `worker.activities.Duplica",
      "score": 2.143
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements function _run_claude.",
      "score": 4.25
    },
    {
      "file": "worker/worker.py",
      "why_relevant": "`worker/worker.py` is a python source file in the Application layer..",
      "score": 2.975
    },
    {
      "file": "worker/activities.py",
      "why_relevant": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`..",
      "score": 2.25
    }
  ],
  "code_rationale": [
    {
      "path": "worker/worker.py",
      "lines": [
        104,
        108
      ],
      "comment": "The activities are now SYNC defs doing BLOCKING LLM/HTTP + CPU-heavy pydantic parsing. Running them in a ThreadPoolExecutor keeps the blocking work OFF the workflow event-loop thread, so under a backfill burst the loop stays free to process workflow tasks (no task-timeout churn) and up to `max_workers` activities run truly concurrently.",
      "matched_terms": [
        "activities",
        "worker"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "_run_claude",
      "lines": [
        943,
        988
      ],
      "source": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:\n    \"\"\"Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.\n    \"\"\"\n    token, base = _claude_anthropic_creds()\n    # Понятная ошибка вместо голого \"exit 1\", если z.ai не сконфигурирован:\n    # без креды claude-code уходит на дефолтный Anthropic API и падает.\n    if not token or not base:\n        raise RuntimeError(\n            \"claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL \"\n            \"(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера.\"\n        )\n    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера\n    # работает от root, а тот флаг под root запрещён самим claude-code\n    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).\n    command = [\"claude\", \"-p\", prompt, \"--permission-mode\", \"acceptEdits\"]\n    if mcp_config:\n        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы\n        # затесаться серверы из окружения образа, и стадия ходила бы не туда,\n        # куда её послали.\n        #\n        # --allowedTools по имени сервера: без него вызов инструмента ждёт\n        # подтверждения, которого в неинтерактивном режиме не будет, и диалог\n        # молча не состоится.\n        command += [\"--mcp-config\", mcp_config, \"--strict-mcp-config\",\n                    \"--allowedTools\", f\"mcp__{repowise.SERVER_NAME}\"]\n    result = subprocess.run(\n        command,\n        cwd=cwd, capture_output=True, text=True,\n        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,\n        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.\n        env={**os.environ, \"ANTHROPIC_AUTH_TOKEN\": token, \"ANTHROPIC_BASE_URL\": base},\n    )\n    if result.returncode != 0:\n        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба\n        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.\n        detail = result.stderr.strip() or result.stdout.strip() or \"(пустой вывод)\"\n        raise RuntimeError(f\"claude -p exit {result.returncode}: {detail[-1500:]}\")"
    },
    {
      "path": "worker/activities.py",
      "name": "_bft_direct_draft",
      "lines": [
        2639,
        2725
      ],
      "source": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:\n    \"\"\"Стадия `draft` двумя вызовами модели вместо агента.\n\n    Первый вызов собирает каскад требований и якоря структурой, второй рендерит\n    из них документ. Между ними — программная проверка полноты и якорей: ради\n    неё разбиение и сделано, одним ответом проверять нечего.\n    \"\"\"\n    model = os.environ.get(\"BFT_DIRECT_MODEL\", \"glm-4.6\")\n    sources = _bft_sources(clone_dir)\n    line_counts = {rel: len(body.splitlines()) for rel, body in sources.items()}\n    inputs = _bft_stage_inputs(clone_dir, req.issue_number, sources)\n    issue = req.issue_number\n\n    system = _bft_stage_system(\n        \"draft\", \"СЕЙЧАС ты собираешь ТОЛЬКО каскад требований и таблицу якорей. \"\n                 \"Документ не пишешь — его соберёт следующий шаг.\")\n    cascade_task = (\n        f\"{inputs}\\n\\n---\\n\\n# Задание\\n\\n\"\n        f\"Собери каскад требований БФТ для эпика issue-{issue} и таблицу якорей.\\n\\n\"\n        \"Разворачивай, а не сворачивай: каждый пункт TOBE из problem.md, каждое \"\n        \"уточнение постановки, каждая ветка сценария демонстрации, каждый экран \"\n        \"актора, каждая измеримая характеристика — отдельное требование.\\n\\n\"\n        \"Якоря: As-Is-факт → `файл:строки` из исходников выше (ранг R1, тип \"\n        \"«Код»); требование постановки → `po-statement.md:N` (R2, «Постановка»); \"\n        \"решение концепта → `concept.md` (R2, «Решение»). To-Be на код НЕ \"\n        \"якорится.\\n\\n\"\n        \"Нижняя граница: \"\n        + \", \".join(f\"{k} ≥ {v}\" for k, v in bft.CASCADE_FLOOR.items())\n        + f\", якорей ≥ {bft.ANCHOR_FLOOR}.\\n\\n\"\n        f\"Верни ТОЛЬКО JSON по схеме:\\n{bft.CASCADE_SCHEMA}\")\n\n    started = time.monotonic()\n    cascade = bft.parse_cascade(llm.complete(system, cascade_task, model=model))\n    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"каскад требований\",\n        outcome=\"готово\", elapsed=time.monotonic() - started,\n        detail=f\"требований {len(cascade.get('requirements') or [])}, \"\n               f\"якорей {len(cascade.get('anchors') or [])}\"))\n    for _ in range(BFT_TOP_UP_ATTEMPTS):\n        gaps = bft.cascade_gaps(cascade, line_counts)\n        if not gaps:\n            break\n        logger.info(\"БФТ %s#%s: добор каскада — %s\", req.repo, issue, \"; \".join(gaps))\n        _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n            stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"добор каскада\",\n            outcome=\"добор\", detail=\"; \".join(gaps)))\n        top_up = (f\"{inputs}\\n\\n---\\n\\n# Уже собрано\\n\\n```json\\n\"\n                  + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n                  \"# Чего не хватает\\n\\n- \" + \"\\n- \".join(gaps) + \"\\n\\n\"\n                  \"Верни ПОЛНЫЙ JSON той же схемы: собранное дословно плюс \"\n                  \"недостающее. Ничего не удаляй и не переформулируй.\")\n        cascade = bft.parse_cascade(llm.complete(system, top_up, model=model))\n\n    left = bft.cascade_gaps(cascade, line_counts)\n    if left:\n        # Не падаем: неполный каскад — это плохой документ, а не сорванный\n        # прогон, и человеку полезнее увидеть его с честной пометкой в логе,\n        # чем не увидеть ничего. Полнота проверяется стадией `validate`.\n        logger.warning(\"БФТ %s#%s: каскад неполон после добора — %s\",\n                       req.repo, issue, \"; \".join(left))\n\n    system2 = _bft_stage_system(\n        \"draft\", \"СЕЙЧАС ты рендеришь документ из УТВЕРЖДЁННОГО каскада. \"\n                 \"Требования и якоря уже собраны: переносишь их все, ничего не \"\n                 \"теряя и не добавляя новых идентификаторов.\")\n    render_task = (\n        f\"{inputs}\\n\\n---\\n\\n# Утверждённый каскад\\n\\n```json\\n\"\n        + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n        f\"# Задание\\n\\nСобери чистовик БФТ issue-{issue} по корп-шаблону. Все \"\n        \"требования каскада обязаны попасть в свои разделы, все якоря — в раздел \"\n        \"«Якоря истины» таблицей `Факт | Источник | Ранг | Тип`.\\n\\n\"\n        \"Файловых инструментов нет: ты не записываешь файл, а выводишь его \"\n        \"содержимое целиком.\\n\\n\"\n        f\"YAML-шапка ровно такая:\\n```\\n---\\nEpic: issue-{issue}\\n\"\n        \"Название: <название>\\nСтатус: Черновик\\nДата: <сегодня>\\n\"\n        \"Автор: bft-draft\\nВерсия: 1.0\\n---\\n```\\n\\n\"\n        \"Заголовки разделов — только `##`. Ответ начинается со строки `---` и \"\n        \"заканчивается последней строкой таблицы якорей, без обрамляющих \"\n        \"```-блоков и без фраз до или после.\")\n\n    started = time.monotonic()\n    document = llm.complete(system2, render_task, model=model)\n    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"рендер документа\",\n        outcome=\"готово\", elapsed=time.monotonic() - started,\n        detail=f\"{len(document)} символов\"))\n    return document"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the _run_claude body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 1065.0,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "70-2725",
      "defines": "_run_claude:943, _bft_direct_draft:2639, GateExtraction:79, ClassificationExtraction:84, DuplicateCandidate:89, DuplicateExtraction:95"
    },
    {
      "path": "worker/worker.py",
      "lines": "34-121",
      "defines": "main:34"
    }
  ]
}

## Ход 10 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Is there similar infrastructure for direct calls (not claude -p) in the FNR pipeline? Look for run_fnr_stage and any direct call variants."
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `run_fnr_stage`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
    "onboarding/how_it_works",
    ".claude/skills/brainstorming/scripts/stop-server.sh",
    ".claude/skills/architecture/scripts"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "worker/activities.py",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 103 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) -> None |\n| `close_as_spam` | function | def close_as_spam(issue: IssueI",
      "score": 5.822,
      "key_symbols": [
        {
          "name": "CLAUDE_STAGE_TIMEOUT_SEC",
          "kind": "constant",
          "signature": "CLAUDE_STAGE_TIMEOUT_SEC = 900",
          "docstring": "",
          "start_line": 752,
          "end_line": 752,
          "source_excerpt": "CLAUDE_STAGE_TIMEOUT_SEC = 900"
        },
        {
          "name": "_claude_anthropic_creds",
          "kind": "function",
          "signature": "def _claude_anthropic_creds() -> tuple[str, str]:",
          "docstring": "Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n    не нужно, но если заданы — приоритетнее (явный override).",
          "start_line": 926,
          "end_line": 940,
          "source_excerpt": "def _claude_anthropic_creds() -> tuple[str, str]:\n    \"\"\"Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n    не нужно, но если заданы — приоритетнее (явный override).\"\"\"\n    token = os.environ.get(\"ANTHROPIC_AUTH_TOKEN\") or os.environ.get(\"ZAI_API_KEY\", \"\")\n    base = os.environ.get(\"ANTHROPIC_BASE_URL\", \"\")\n    if not base:\n        zai = os.environ.get(\"ZAI_BASE_URL\", \"\")\n        if zai:\n            from urllib.parse import urlsplit\n            p = urlsplit(zai)\n            base = f\"{p.scheme}://{p.netloc}/api/anthropic\"\n    return token, base"
        },
        {
          "name": "_run_claude",
          "kind": "function",
          "signature": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:",
          "docstring": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.",
          "start_line": 943,
          "end_line": 988
        },
        {
          "name": "_run_with_heartbeat",
          "kind": "function",
          "signature": "async def _run_with_heartbeat(fn, *args, label: str):",
          "docstring": "Гоняет блокирующий fn в потоке и шлёт heartbeat каждые\n    HEARTBEAT_INTERVAL_SEC, пока он не завершится.\n\n    Heartbeat только между стадиями недостаточен: одна стадия claude -p идёт\n    до CLAUDE_STAGE_TIMEOUT_SEC (900с), а heartbeat_timeout воркфлоу — 300с;\n    без периодического сигнала внутри стадии сервер счёл бы activity мёртвой и\n    (при maximum_attempts=1) уронил бы весь прогон. to_thread освобождает event\n    loop, но сам по себе не бьёт — поэтому бьём здесь, пока поток занят.",
          "start_line": 1039,
          "end_line": 1065
        },
        {
          "name": "run_fnr_stage",
          "kind": "function",
          "signature": "async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:",
          "docstring": "Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\n    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\n    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.",
          "start_line": 1266,
          "end_line": 1321,
          "source_excerpt": "async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:\n    \"\"\"Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\n    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\n    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.\"\"\"\n    # Бриф с обсуждением и связанными PR нужен ровно стадии `task`: только её\n    # промпт несёт описание задачи, остальные ссылаются на уже готовые артефакты.\n    # Регрессия, из-за которой это место и появилось: при переходе на\n    # пер-стадийные activity обогащение осталось в монолите, и `/analyze`\n    # уезжал в модель с одними title+body — агент переоткрывал вопросы,\n    # закрытые в комментариях.\n    description = (\n        await asyncio.to_thread(_build_task_context, analyze)\n        if stage_name == \"task\"\n        else f\"{analyze.title}\\n\\n{analyze.body}\"\n    )\n    prompt, expected, requires = _fnr_stage(stage_name, description)\n    clone_dir = _require_workspace(analyze, requires)\n    if expected:\n        ready = Path(clone_dir) / expected\n        if ready.is_file() and ready.stat().st_size > 0:\n            # Артефакт приехал с веткой прошлого прогона: стадия сделана, и\n            # повторять её — платить второй раз за тот же документ.\n            logger.info(\"FNR %s#%s: стадия %s уже сделана — пропускаю\",\n                        analyze.repo, analyze.issue_number, stage_name)\n            return {\"stage\": stage_name, \"artifact\": expected,\n                    \"bytes\": ready.stat().st_size, \"outcome\": \"skipped\"}\n    mcp_config = _write_repowise_config(analyze, clone_dir)\n    if stage_name == REPOWISE_STAGE:\n        degraded = await asyncio.to_thread(_degrade_repowise_stage, analyze, clone_dir, expected)\n        if degraded is not None:\n            return degraded\n    # Конфигурация MCP передаётся ТОЛЬКО стадии сбора контекста: остальным\n    # стадиям индекс не нужен, а лишние инструменты в сессии — лишние соблазны\n    # и лишние деньги.\n    await _run_with_heartbeat(\n        _run_claude, prompt, clone_dir,\n        mcp_config if stage_name == REPOWISE_STAGE else None,\n        label=stage_name)\n\n    outcome = \"ok\"\n    if stage_name == REPOWISE_STAGE and expected:\n        # Артефакт дописывается транскриптом из журнала прокси и потому не\n        # зависит от того, вспомнила ли модель его записать.\n        outcome = await asyncio.to_thread(\n            _ensure_dialog_artifact, analyze, clone_dir, expected)\n\n    artifact: str | None = None\n    size = 0\n    if expected:\n        path = Path(clone_dir) / expected\n        if not path.exists():\n            raise RuntimeError(f\"стадия {stage_name}: артефакт {expected} не создан\")\n        artifact = expected\n        size = path.stat().st_size\n    return {\"stage\": stage_name, \"artifact\": artifact, \"bytes\": size,\n            \"outcome\": outcome}"
        },
        {
          "name": "run_bug_pipeline",
          "kind": "function",
          "signature": "def run_bug_pipeline(issue: IssueInput) -> None:",
          "docstring": "TODO: перенести содержимое bug-pipeline.yml аналогично.",
          "start_line": 1398,
          "end_line": 1400
        },
        {
          "name": "run_bft_fast",
          "kind": "function",
          "signature": "async def run_bft_fast(req: BftRequest) -> str:",
          "docstring": "Быстрый проход: письмо БФТ комментарием в Issue.\n\n    Один вызов модели, без клона и без claude-code: формат `/bft-fast` — это\n    структурирование уже сказанного, а не исследование кода. Клонировать\n    репозиторий ради него значило бы платить минутами за то, что нужно секундами.\n\n    Возвращает опубликованный текст — он же уходит в историю Temporal, поэтому\n    разбор «что именно агент отписал» не требует лезть в GitHub.",
          "start_line": 2286,
          "end_line": 2316
        },
        {
          "name": "CLAUDE_HOME",
          "kind": "constant",
          "signature": "CLAUDE_HOME = Path(os.environ.get(\"CLAUDE_HOME\", \"/root/.claude\"))",
          "docstring": "",
          "start_line": 2429,
          "end_line": 2429
        },
        {
          "name": "_bft_stage_system",
          "kind": "function",
          "signature": "def _bft_stage_system(stage_name: str, role_tail: str) -> str:",
          "docstring": "Системный промпт стадии — та же инструкция, что читает `claude -p`.",
          "start_line": 2457,
          "end_line": 2476
        },
        {
          "name": "_bft_direct_draft",
          "kind": "function",
          "signature": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:",
          "docstring": "Стадия `draft` двумя вызовами модели вместо агента.\n\n    Первый вызов собирает каскад требований и якоря структурой, второй рендерит\n    из них документ. Между ними — программная проверка полноты и якорей: ради\n    неё разбиение и сделано, одним ответом проверять нечего.",
          "start_line": 2639,
          "end_line": 2725
        }
      ]
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "summary": "`.claude/skills/subagent-driven-development/scripts/sdd-workspace` is an infrastructure file (shell). Its behaviour is not derivable from structure, so the source is reproduced in full.",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/sdd-workspace` is an infrastructur",
      "excerpt": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/sdd-workspace` is an infrastructure file (shell). Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Resolve and ensure the working-tree directory SDD uses for its short-lived\n# artifacts: task briefs, implementer reports, review packages, and the\n# progress ledger. Print the directory's absolute path.\n#\n# The workspace lives in the working tree (not under .git/) because Claude Code\n# treats .git/ as a protected path and denies agent writes there — which blocks\n# an implementer subagent from writing its report file. A self-ignoring\n# .gitignore keeps the workspace out of `git status` and out of accidental\n# commits without modifying any tracked file.\n#\n# Single source of truth for the workspace location, so task-brief and\n# review-package cannot drift to different directories.\n#\n# Usage: sdd-workspace\nset -euo pipefail\n\nroot=$(git rev-parse --show-toplevel)\ndir=\"$root/.superpowers/sdd\"\nmkdir -p \"$dir\"\nprintf '*\\n' > \"$dir/.gitignore\"\ncd \"$dir\" && pwd\n\n```\n\n---\n\n*Built from the code itself: parsed symbols, the import graph, git history and\nthe knowledge graph. Every statement here is checked against the source rather\nthan written about it.*",
      "score": 3.822
    },
    {
      "path": "onboarding/how_it_works",
      "title": "How It Works",
      "summary": "Traced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.",
      "snippet": "outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-issue",
      "excerpt": "# How It Works\n\nTraced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-issue-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Traced flows\n\n\n\n\n### From `worker/workflows.py::IssueLifecycle::run`\n\n\n\n1. `worker/workflows.py::IssueLifecycle::run`\n\n2. `worker/workflows.py::IssueLifecycle::_run_phase_loop`\n\n3. `worker/workflows.py::IssueLifecycle::_phase_await_build`\n\n4. `worker/workflows.py::IssueLifecycle::_park`\n\n5. `shared/awaiting.py::Awaiting`\n\n\n\n\n\n\n### From `webhook/main.py::github_webhook`\n\n\n\n1. `webhook/main.py::github_webhook`\n\n2. `shared/agent_launcher.py::request_analysis`\n\n3. `shared/workflow_ids.py::issue_workflow_id`\n\n\n\n\n\n\n### From `worker/workflows.py::IssueAnalysis::run`\n\n\n\n1. `worker/workflows.py::IssueAnalysis::run`\n\n2. `worker/workflows.py::_run_staged_analysis`\n\n3. `worker/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. README.md. Start here for the end-to-end picture before diving into the code.\n   - `README.md`\n\n\n2. main.py. An entry point — execution and imports fan out from here.\n   - `webhook/main.py`\n\n\n3. workflow_types.py. Directly used by the entry points above; a core collab",
      "score": 3.197
    },
    {
      "path": ".claude/skills/brainstorming/scripts/stop-server.sh",
      "title": "Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh",
      "summary": "`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructure file (shell). It declares 5 named targets, listed below. Its behaviour is not derivable from structure, so the source is reproduced in full.",
      "snippet": "# Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh\n\n**Type:** shell | **Declared targets:** 5\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructur",
      "excerpt": "# Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh\n\n**Type:** shell | **Declared targets:** 5\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructure file (shell). It declares 5 named targets, listed below. Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n## Declared targets\n\n- `mark_stopped`\n\n- `read_expected_server_id`\n\n- `command_line_for_pid`\n\n- `command_has_server_id`\n\n- `is_brainstorm_server`\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Stop the brainstorm server and clean up\n# Usage: stop-server.sh <session_dir>\n#\n# Kills the server process. Only deletes session directory if it's\n# under /tmp (ephemeral). Persistent directories (.superpowers/) are\n# kept so mockups can be reviewed later.\n\nSESSION_DIR=\"$1\"\n\nif [[ -z \"$SESSION_DIR\" ]]; then\n  echo '{\"error\": \"Usage: stop-server.sh <session_dir>\"}'\n  exit 1\nfi\n\nSTATE_DIR=\"${SESSION_DIR}/state\"\nPID_FILE=\"${STATE_DIR}/server.pid\"\nSERVER_ID_FILE=\"${STATE_DIR}/server-instance-id\"\n\nmark_stopped() {\n  local reason=\"$1\"\n  rm -f \"${STATE_DIR}/server-info\"\n  printf '{\"reason\":\"%s\",\"timestamp\":%s}\\n' \"$reason\" \"$(date +%s)\" > \"${STATE_DIR}/server-stopped\"\n}\n\nread_expected_server_id() {\n  [[ -f \"$SERVER_ID_FILE\" ]] || return 1\n  local id\n  id=\"$(tr -d '\\r\\n' < \"$SERVER_ID_FILE\" 2>/dev/null || true)\"\n  [[ \"$id\" =~ ^[A-Za-z0-9_-]{32,64}$ ]] || return 1\n  printf '%s\\n' \"$id\"\n}\n\ncommand_line_for_pid() {\n  local pid=\"$1\"\n  if [[ -r \"/proc/$pid/cmdli",
      "score": 3.185
    },
    {
      "path": ".claude/skills/architecture/scripts",
      "title": "Architecture Scripts",
      "summary": "`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`",
      "snippet": "# Architecture Scripts\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascri",
      "excerpt": "# Architecture Scripts\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascript | **Files:** 5 | **Public symbols:** 78 / 83\n\n\nCovers the 5 source files in 4 directories under .claude/skills. Does not cover code outside those directories, which is documented on its own pages.\n\n\n\n\n## Overview\n\nArchitecture Scripts covers 5 javascript files across 4 directories, exposing 78 public symbols. It hosts 1 entry point into this subsystem.\n\n\n## Entry Points\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `.claude/skills/architecture/scripts/generate_taxonomy.py`: `.claude/skills/architecture/scripts/generate_taxonomy.py` is a python source file in the Config layer. It exposes 1 public symbol.\n\n- `.claude/skills/brainstorming/scripts/helper.js`: `.claude/skills/brainstorming/scripts/helper.js` is a javascript source file in the Config layer. It exposes 8 public symbols.\n\n- `.claude/skills/brainstorming/scripts/server.cjs` *(entry point)*: `.claude/skills/brainstorming/scripts/server.cjs` is a javascript entry-point source file in the Config layer. It exposes 66 public symbols.\n\n- `.claude/skills/systematic-debugging/condition-based-waiting-example.ts`: `.claude/skills/systematic-debugging/condition-based-waiting-example.ts` is a typescript source file in the Config layer. It exposes 3 public sy",
      "score": 3.047
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements function run_fnr_stage.",
      "score": 5.822
    },
    {
      "file": ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "why_relevant": "`.claude/skills/subagent-driven-development/scripts/sdd-workspace` is an infrastructure file (shell).",
      "score": 3.822
    }
  ],
  "code_rationale": [
    {
      "path": "worker/activities.py",
      "lines": [
        791,
        796
      ],
      "comment": "Входной артефакт каждой стадии — что уже должно лежать в рабочем каталоге, чтобы стадия имела смысл (используется guard'ом _require_workspace). У `task` вход — артефакт диалога: пропустить сбор контекста незаметно нельзя. Артефакт создаётся и при недоступном Repowise (деградация, см. run_fnr_stage), поэтому guard не превращает сервис в обязательную зависимость конвейера.",
      "matched_terms": [
        "fnr",
        "run_fnr_stage"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        879,
        890
      ],
      "comment": "Shallow-клон целевого репозитория: артефакты FNR обязаны опираться на реальный код (`файл:строка`), одного текста Issue недостаточно. `branch` — ветка вместо дефолтной; её просят два вызывающих по разным причинам. Круг правок работает поверх ветки PR, иначе правки ложились бы не на то, что видел ревьюер. Повторный прогон БФТ забирает ветку прошлого прогона, потому что дорабатывает уже лежащий там документ, а не пишет второй рядом. Пусто — ветка по умолчанию, как для анализа и разработки. Вызывающий обязан убедиться, что ветка существует: клон несуществующей падает внутри git, а падать это должно на понятной проверке. Токен идёт через credential.helper в env, а НЕ вклеен в URL: argv команды целиком рендерится в текст subprocess.CalledProcessError/TimeoutExpired, и без этого любой сбой клон…",
      "matched_terms": [
        "call",
        "fnr"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        944,
        954
      ],
      "comment": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом. Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно. `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам. Положить файл в каталог прогона и надеяться — ровно то, что провалилось на первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов не увидела и артефакта не создала.",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        963,
        965
      ],
      "comment": "acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера работает от root, а тот флаг под root запрещён самим claude-code (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).",
      "matched_terms": [
        "call",
        "claude"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        2733,
        2738
      ],
      "comment": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`. Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной активностью весь пайплайн был бы одним баром в Event History на десятки минут, и застрявшая стадия не называла бы себя.",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "run_fnr_stage",
      "lines": [
        1266,
        1321
      ],
      "source": "async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:\n    \"\"\"Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\n    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\n    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.\"\"\"\n    # Бриф с обсуждением и связанными PR нужен ровно стадии `task`: только её\n    # промпт несёт описание задачи, остальные ссылаются на уже готовые артефакты.\n    # Регрессия, из-за которой это место и появилось: при переходе на\n    # пер-стадийные activity обогащение осталось в монолите, и `/analyze`\n    # уезжал в модель с одними title+body — агент переоткрывал вопросы,\n    # закрытые в комментариях.\n    description = (\n        await asyncio.to_thread(_build_task_context, analyze)\n        if stage_name == \"task\"\n        else f\"{analyze.title}\\n\\n{analyze.body}\"\n    )\n    prompt, expected, requires = _fnr_stage(stage_name, description)\n    clone_dir = _require_workspace(analyze, requires)\n    if expected:\n        ready = Path(clone_dir) / expected\n        if ready.is_file() and ready.stat().st_size > 0:\n            # Артефакт приехал с веткой прошлого прогона: стадия сделана, и\n            # повторять её — платить второй раз за тот же документ.\n            logger.info(\"FNR %s#%s: стадия %s уже сделана — пропускаю\",\n                        analyze.repo, analyze.issue_number, stage_name)\n            return {\"stage\": stage_name, \"artifact\": expected,\n                    \"bytes\": ready.stat().st_size, \"outcome\": \"skipped\"}\n    mcp_config = _write_repowise_config(analyze, clone_dir)\n    if stage_name == REPOWISE_STAGE:\n        degraded = await asyncio.to_thread(_degrade_repowise_stage, analyze, clone_dir, expected)\n        if degraded is not None:\n            return degraded\n    # Конфигурация MCP передаётся ТОЛЬКО стадии сбора контекста: остальным\n    # стадиям индекс не нужен, а лишние инструменты в сессии — лишние соблазны\n    # и лишние деньги.\n    await _run_with_heartbeat(\n        _run_claude, prompt, clone_dir,\n        mcp_config if stage_name == REPOWISE_STAGE else None,\n        label=stage_name)\n\n    outcome = \"ok\"\n    if stage_name == REPOWISE_STAGE and expected:\n        # Артефакт дописывается транскриптом из журнала прокси и потому не\n        # зависит от того, вспомнила ли модель его записать.\n        outcome = await asyncio.to_thread(\n            _ensure_dialog_artifact, analyze, clone_dir, expected)\n\n    artifact: str | None = None\n    size = 0\n    if expected:\n        path = Path(clone_dir) / expected\n        if not path.exists():\n            raise RuntimeError(f\"стадия {stage_name}: артефакт {expected} не создан\")\n        artifact = expected\n        size = path.stat().st_size\n    return {\"stage\": stage_name, \"artifact\": artifact, \"bytes\": size,\n            \"outcome\": outcome}"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the run_fnr_stage body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 607.4,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "752-2725",
      "defines": "run_fnr_stage:1266, GateExtraction:79, ClassificationExtraction:84, DuplicateCandidate:89, DuplicateExtraction:95, PriorityExtraction:99"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/stop-server.sh",
      "defines": "mark_stopped:20, read_expected_server_id:26, command_line_for_pid:34, command_has_server_id:43, is_brainstorm_server:65"
    },
    {
      "path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
    },
    {
      "path": "worker/llm.py",
      "defines": "get_client:25, extract:41, complete:56, MODEL_GATE:19, MODEL_CLASSIFY:20"
    }
  ]
}

## Ход 11 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_claude_anthropic_creds"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_claude_anthropic_creds",
  "file": "worker/activities.py",
  "name": "_claude_anthropic_creds",
  "kind": "function",
  "qualified_name": "worker.activities._claude_anthropic_creds",
  "signature": "def _claude_anthropic_creds() -> tuple[str, str]",
  "language": "python",
  "start_line": 926,
  "end_line": 940,
  "symbol_start_line": 926,
  "symbol_end_line": 940,
  "source": "   926\tdef _claude_anthropic_creds() -> tuple[str, str]:\n   927\t    \"\"\"Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n   928\t    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n   929\t    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n   930\t    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n   931\t    не нужно, но если заданы — приоритетнее (явный override).\"\"\"\n   932\t    token = os.environ.get(\"ANTHROPIC_AUTH_TOKEN\") or os.environ.get(\"ZAI_API_KEY\", \"\")\n   933\t    base = os.environ.get(\"ANTHROPIC_BASE_URL\", \"\")\n   934\t    if not base:\n   935\t        zai = os.environ.get(\"ZAI_BASE_URL\", \"\")\n   936\t        if zai:\n   937\t            from urllib.parse import urlsplit\n   938\t            p = urlsplit(zai)\n   939\t            base = f\"{p.scheme}://{p.netloc}/api/anthropic\"\n   940\t    return token, base",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 26.69,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}
