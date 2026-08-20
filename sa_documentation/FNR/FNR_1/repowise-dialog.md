# Итог

## Текущее состояние Develop (OpenHands)

1. **Единая активность** `trigger_openhands_resolver` в `worker/activities.py:1213-1260`
   - Декоратор `@activity.defn`, вызывается через `workflow.execute_activity` из `_start_development` (`worker/workflows.py:1596`)
   - Retry-политика: `maximum_attempts=1` (весь прогон повторяется целиком при любой ошибке на любом шаге)

2. **Внутренние функции (не activities)**
   - `_dev_prepare` (lines 1056-1089): клон репо + сборка постановки из артефактов
   - `_dev_run_agent` (lines 1142-1169): прогон контейнера OpenHands
   - `_dev_tests` (lines 1172-1188): прогон проверок (`DEVELOP_TEST_COMMAND`)
   - `_dev_publish` (lines 1191-1210): коммит, пуш, создание PR
   - Все обёрнуты `_run_with_heartbeat` для долгих операций
   - `_dev_announce` (lines 1318-1357): best-effort метка/комментарий (с защитой от дублей по метке `in-development`)

3. **Дедупликация сейчас**
   - Ручная проверка в `_dev_announce` по метке `in-development` (lines 1332-1338)
   - При повторном входе — молчаливый return, второй комментарий не ставится

## Шаблон child workflow (IssueAnalysis)

1. **Класс-воркфлоу** `IssueAnalysis` (`worker/workflows.py:2024-2052`)
   - Декоратор `@workflow.run` на методе `run`
   - Вызывается из родителя через `workflow.execute_child_workflow` (`_run_analysis_child`, line 894)

2. **Параметры запуска child**
   - `id=analysis_workflow_id(issue.repo, issue.issue_number)` — фиксированный id для дедупликации
   - `parent_close_policy=ParentClosePolicy.ABANDON` — дочерний переживает завершение родителя
   - `retry_policy=RetryPolicy(maximum_attempts=1)` — недетерминированный, дорогой прогон

3. **Обработка WorkflowAlreadyStartedError**
   - Ловится в `_run_analysis_child` (line 905): при идущем прогоне — второй не запускается
   - Возвращает `False` — родитель понимает, что результат не будет

## Workflow ID patterns

1. **`shared/workflow_ids.py`** — централизованные генераторы id:
   - `analysis_workflow_id(repo, issue_number)` → `analysis-{repo}-{n}`
   - `estimate_workflow_id(repo, issue_number, comment_id)` → `estimate-{repo}-{n}-{marker}`
   - `issue_workflow_id(repo, issue_number, suffix="")` → `issue-{repo}-{n}`

2. **Для Develop нужен**: `develop_workflow_id(repo, issue_number)` → `develop-{repo}-{n}`

## Вызов из родителя сейчас

1. **`_start_development`** (`worker/workflows.py:1588-1638`)
   - `workflow.execute_activity(activities.trigger_openhands_resolver, issue, ...)` (line 1596)
   - Timeout: 3600s (heartbeat каждые 300s)
   - Retry: `maximum_attempts=1` (комментарий lines 1604-1614 объясняет почему)

2. **При ошибке**
   - Ловится `Exception` (line 1616)
   - Постится метка `phase:failed` через `post_error_label` (line 1624)
   - Возврат `(lifecycle.FAILED, "failed", True)`

## Режим dispatch

1. **`develop.DISPATCH`** — прогон уезжает в GitHub Actions (lines 1234-1241)
   - `github_client.dispatch_workflow` — запуск workflow в репе клиента
   - Результат придёт событием `pr-open`
   - Активность возвращает `None` → фаза `in-development`

## Что НЕ переводить в child

1. **Comment/label-активности** — уже видны в истории родителя, оверхед не оправдан
2. **`_dev_announce`** — best-effort,seconds, одноразовые побочные эффекты
3. **PR-ревью** — ведёт соседний сервис `pr-agent`, связь через `agent_event`-сигнал

## Связанные репозитории

1. **`poh-pr-agents`** — сервис PR-ревью, свой Temporal не поднимает
2. **`poh-helper`** — основной репозиторий контура (в co-change топе)

# Открытые вопросы

Нет — индекс дал полную картину для постановки задачи.

# Диалог

## Ход 1: Repository overview
**Инструмент**: `get_overview`
**Результат**: Получен обзор репозитория `poh-issue-agents` (323 файла, 80733 строк). Основные модули: `worker` (воркер и workflows), `shared` (типы и утилиты), `webhook` (точка входа). Ключевые файлы: `worker/workflows.py`, `worker/activities.py`, `shared/workflow_types.py`.

## Ход 2: Поиск Develop активности
**Инструмент**: `get_symbol(trigger_openhands_resolver)`
**Результат**: Найдена функция `trigger_openhands_resolver` (lines 1708-1759), но смещение строк оказалось неверным из-за индекса. Реальное положение — lines 1213-1260 (проверено Read).

## Ход 3: Поиск шаблона child workflow
**Инструмент**: `search_codebase(IssueAnalysis child workflow)`
**Результат**: Найден класс `IssueAnalysis` (`worker/workflows.py:2024-2052`) и метод `_run_analysis_child` (`worker/workflows.py:866-915`) — шаблон для child workflow с дедупликацией через `WorkflowAlreadyStartedError`.

## Ход 4: Структура вызова Develop
**Инструмент**: `get_symbol(_start_development)`
**Результат**: Получена функция `_start_development` (lines 1588-1638) — точка вызова Develop активности через `workflow.execute_activity` с timeout 3600s и retry `maximum_attempts=1`.

## Ход 5: Workflow ID patterns
**Инструмент**: `get_context(shared/workflow_ids.py)`
**Результат**: Файл содержит генераторы id для workflows: `analysis_workflow_id`, `estimate_workflow_id`, `issue_workflow_id`. Для Develop нужен аналогичный `develop_workflow_id`.

## Ход 6: Внутренние функции Develop
**Инструмент**: `Read(activities.py, lines 1050-1360)`
**Результат**: Найдены все функции, составляющие Develop:
- `_dev_paths` (lines 1050-1053): пути рабочего каталога
- `_dev_prepare` (lines 1056-1089): клон + постановка
- `_handover_to_runner` (lines 1108-1126): передача прав раннеру
- `_reap_runner` (lines 1129-1139): очистка контейнера
- `_dev_run_agent` (lines 1142-1169): прогон агента
- `_dev_tests` (lines 1172-1188): проверки
- `_dev_publish` (lines 1191-1210): публикация PR
- `trigger_openhands_resolver` (lines 1213-1260): основная активность
- `collect_dev_followups` (lines 1263-1315): обработка находок
- `_dev_announce` (lines 1318-1357): объявление о начале работы

## Ход 7: Imports и структура workflows
**Инструмент**: `Read(workflows.py, lines 1-100)`
**Результат**: Получены импорты и константы. В workflow-код импортируется через `with workflow.unsafe.imports_passed_through()`. Используются `RetryPolicy`, `ParentClosePolicy`, `WorkflowAlreadyStartedError`.

## Ход 8: Проверка develop_workflow_id
**Инструмент**: `search_codebase(develop_workflow_id)`
**Результат**: Функция не существует — её нужно создать при переводе Develop в child workflow.

## Ход 9: Анализ IssueEstimation
**Инструмент**: `get_symbol(IssueEstimation)`
**Результат**: Класс `IssueEstimation` (lines 2207-2274) — ещё один пример child workflow с аналогичной структурой: staged execution с отдельными retry-политиками на каждую стадию.

## Ход 10: Проверка _run_with_heartbeat
**Инструмент**: `search_codebase(_run_with_heartbeat)`
**Результат**: Найдена функция `_run_with_heartbeat` (lines 1039-1065) — обёртка для долгих activitiy с heartbeat для предотвращения таймаута.

## Достаточность контекста
После 10 ходов получена полная картина:
- Текущая структура Develop как единой активности
- Шаблон child workflow (IssueAnalysis, IssueEstimation)
- Workflow ID patterns
- Все внутренние функции Develop
- Точка вызова из родителя
- Режим dispatch и его обработка

Контекст достаточен для постановки задачи на перевод Develop в child workflow.


---
session: rw-analysis-po-helper-org__poh-issue-agents-73
workspace: contour
turns: 16
started: 2026-08-20T19:16:25Z
finished: 2026-08-20T19:16:55Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `a41f569f0381` | 37 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "null",
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

## Ход 2 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::trigger_openhands_resolver",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::trigger_openhands_resolver",
  "file": "worker/activities.py",
  "name": "trigger_openhands_resolver",
  "kind": "function",
  "qualified_name": "worker.activities.trigger_openhands_resolver",
  "signature": "async def trigger_openhands_resolver(issue: IssueInput) -> int | None",
  "language": "python",
  "start_line": 1708,
  "end_line": 1759,
  "symbol_start_line": 1708,
  "symbol_end_line": 1759,
  "source": "  1708\tasync def trigger_openhands_resolver(issue: IssueInput) -> int | None:\n  1709\t    \"\"\"Активность Develop: разработка по подготовленному Issue.\n  1710\t\n  1711\t    Два режима (`shared/develop.py`). `local` — прогон одноразовым контейнером\n  1712\t    на своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\n  1713\t    в GitHub Actions, для репозиториев без стенда.\n  1714\t\n  1715\t    Возвращает номер PR (режим `local`) либо None (`dispatch`: результат\n  1716\t    придёт событием `pr-open`, прогон идёт на чужой стороне).\n  1717\t    \"\"\"\n  1718\t    if not develop.enabled():\n  1719\t        raise RuntimeError(\n  1720\t            \"DEVELOP_ENABLED выключен — задача остаётся в очереди к разработчику\")\n  1721\t\n  1722\t    branch = f\"research/issue-{issue.issue_number}\"\n  1723\t    if not await asyncio.to_thread(github_client.branch_exists, issue.repo, branch):\n  1724\t        # Путь бага: аналитики не было, и ветки с артефактами тоже. Штатно —\n  1725\t        # агент работает от тела Issue, но знать об этом должен явно.\n  1726\t        branch = \"\"\n  1727\t\n  1728\t    if develop.mode() == develop.DISPATCH:\n  1729\t        await asyncio.to_thread(\n  1730\t            github_client.dispatch_workflow,\n  1731\t            issue.repo, develop.workflow_file(), develop.workflow_ref(),\n  1732\t            develop.dispatch_inputs(issue.issue_number, branch=branch),\n  1733\t        )\n  1734\t        await _dev_announce(issue, branch, where=\"запустил OpenHands Resolver в GitHub Actions\")\n  1735\t        return None\n  1736\t\n  1737\t    # Порядок не косметический: сначала клон и постановка — они единственные\n  1738\t    # могут не состояться до того, как что-либо сказано человеку.\n  1739\t    task = await _run_with_heartbeat(_dev_prepare, issue, branch, label=\"dev:prepare\")\n  1740\t    logger.info(\"Develop %s#%s: постановка (%d симв.)\\n%s\",\n  1741\t                issue.repo, issue.issue_number, len(task), task[:2000])\n  1742\t    await _dev_announce(issue, branch, where=\"запустил OpenHands на своём сервере\")\n  1743\t\n  1744\t    try:\n  1745\t        await _run_with_heartbeat(_dev_run_agent, issue, label=\"dev:agent\")\n  1746\t    finally:\n  1747\t        # В finally, а не после: диалог полезнее всего при разборе упавшего\n  1748\t        # прогона, и терять его ровно в этом случае было бы худшим из исходов.\n  1749\t        await asyncio.to_thread(_publish_dev_dialog_sync, issue, branch)\n  1750\t    # Находки собираются ДО тестов и публикации: файл находок обязан исчезнуть\n  1751\t    # из рабочего дерева раньше коммита, иначе он уедет в PR — в ревью как мусор,\n  1752\t    # а на следующем круге правок агент прочитает свои прошлые находки как новые.\n  1753\t    await collect_dev_followups(issue)\n  1754\t    await _run_with_heartbeat(_dev_tests, issue, label=\"dev:tests\")\n  1755\t    number = await _run_with_heartbeat(_dev_publish, issue, branch, label=\"dev:publish\")\n  1756\t\n  1757\t    if number is None:\n  1758\t        raise RuntimeError(\"агент не изменил ни одного файла — открывать нечего\")\n  1759\t    return number",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 35.09,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "IssueAnalysis child workflow",
  "repo": "poh-issue-agents",
  "limit": 5
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis",
      "name": "IssueAnalysis",
      "kind": "class",
      "file": "worker/workflows.py",
      "start_line": 2024,
      "end_line": 2052,
      "signature": "class IssueAnalysis",
      "qualified_name": "worker.workflows.IssueAnalysis",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2037,
      "end_line": 2052,
      "signature": "async def run(self, analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows.IssueAnalysis.run",
      "language": "python",
      "score": 60.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/repowise.py::ANALYSIS",
      "name": "ANALYSIS",
      "kind": "constant",
      "file": "shared/repowise.py",
      "start_line": 32,
      "end_line": 32,
      "signature": "ANALYSIS = \"analysis\"",
      "qualified_name": "shared.repowise.ANALYSIS",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueAnalysis",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueAnalysis\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueAnalysis\n```\n\n## Overview\n\nАналитика по запросу (Слой C) — воркф",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueAnalysis",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "# shared/agent_launcher.py\n\n## Overview\n\nЕдиная точка запуска агента: child при живом цикле, root — иначе.\n\nТребование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.\nДо этого воз",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "type": "page"
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
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/repowise.py"
    },
    {
      "path": "shared/agent_launcher.py"
    }
  ],
  "exact_match": true
}

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "_run_analysis_child child workflow",
  "repo": "poh-issue-agents",
  "limit": 5
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_run_analysis_child",
      "name": "_run_analysis_child",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 866,
      "end_line": 915,
      "signature": "async def _run_analysis_child(self, issue: IssueInput,\n                                  trigger: str | None = None) -> bool",
      "qualified_name": "worker.workflows.IssueLifecycle._run_analysis_child",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2037,
      "end_line": 2052,
      "signature": "async def run(self, analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows.IssueAnalysis.run",
      "language": "python",
      "score": 60.01,
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
      "score": 50.02,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: shared.workflow_types.Taxonomy",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.Taxonomy\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass Taxonomy\n```\n\n## Overview\n\n`Taxonomy` is a class defined in `sha",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::Taxonomy",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.ClusterSet",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.ClusterSet\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass ClusterSet\n```\n\n## Overview\n\n`ClusterSet` is a class defined i",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClusterSet",
      "file": "shared/workflow_types.py",
      "type": "page"
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
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/workflow_types.py"
    }
  ],
  "exact_match": true
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::IssueLifecycle::_run_analysis_child",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::_run_analysis_child",
  "file": "worker/workflows.py",
  "name": "_run_analysis_child",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle._run_analysis_child",
  "signature": "async def _run_analysis_child(self, issue: IssueInput,\n                                  trigger: str | None = None) -> bool",
  "language": "python",
  "start_line": 866,
  "end_line": 915,
  "symbol_start_line": 866,
  "symbol_end_line": 915,
  "source": "   866\t    async def _run_analysis_child(self, issue: IssueInput,\n   867\t                                  trigger: str | None = None) -> bool:\n   868\t        \"\"\"Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n   869\t\n   870\t        Один код на оба режима (#37): в Temporal UI прогон виден как child\n   871\t        цикла, а id остаётся прежним (`analysis-<repo>-<n>`), поэтому повторная\n   872\t        команда по-прежнему упирается в `WorkflowAlreadyStarted`, а не тратит\n   873\t        деньги второй раз.\n   874\t        \"\"\"\n   875\t        analyze = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,\n   876\t                               title=issue.title, body=issue.body,\n   877\t                               comment_id=self._analyze_comment_id,\n   878\t                               trigger=trigger)\n   879\t        # Запрос израсходован — но снимается он ПОСЛЕ прогона, а не до.\n   880\t        #\n   881\t        # Пока прогон идёт, `ack_command` вешает на Issue метку `run:analyze`.\n   882\t        # Вебхук видит `issues.labeled` и шлёт `analyze_requested` обратно в\n   883\t        # цикл: наша собственная метка возвращается как новая команда. Со\n   884\t        # снятым флагом она вставала в очередь, и по завершении прогона цикл\n   885\t        # запускал второй — на живом стенде это дало три прогона аналитики\n   886\t        # подряд по одному Issue. Идентификатор занятого прогона от этого не\n   887\t        # спасает: к моменту обработки очереди первый уже завершён, и id\n   888\t        # свободен.\n   889\t        #\n   890\t        # Команда, пришедшая ВО ВРЕМЯ прогона, — эхо своей метки либо повторный\n   891\t        # клик человека. Ни то, ни другое не стоит второго дорогого прогона.\n   892\t        self._analysis_running = True\n   893\t        try:\n   894\t            return await workflow.execute_child_workflow(\n   895\t                IssueAnalysis.run, analyze,\n   896\t                id=analysis_workflow_id(issue.repo, issue.issue_number),\n   897\t                # Цепочка FNR идёт до 4500 с. Ни continue-as-new родителя, ни\n   898\t                # его завершение не должны её убивать — иначе дорогой прогон\n   899\t                # обрывается на середине по причине, к нему не относящейся.\n   900\t                parent_close_policy=ParentClosePolicy.ABANDON,\n   901\t                # Прогон недетерминирован, мутирует файлы и стоит денег:\n   902\t                # повтор инициирует человек, а не политика ретраев.\n   903\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   904\t            )\n   905\t        except WorkflowAlreadyStartedError:\n   906\t            # Прогон по этому Issue уже идёт — второй дорогой не нужен.\n   907\t            # Результата отсюда не видно (это чужой прогон), поэтому фазу\n   908\t            # дальше не двигаем: её сдвинет тот, кто анализ и запускал.\n   909\t            workflow.logger.info(\"analysis already running for %s#%s\",\n   910\t                                 issue.repo, issue.issue_number)\n   911\t            return False\n   912\t        finally:\n   913\t            self._analyze_comment_id = None\n   914\t            self._analyze_pending = False\n   915\t            self._analysis_running = False",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 16.96,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::IssueAnalysis",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueAnalysis",
  "file": "worker/workflows.py",
  "name": "IssueAnalysis",
  "kind": "class",
  "qualified_name": "worker.workflows.IssueAnalysis",
  "signature": "class IssueAnalysis",
  "language": "python",
  "start_line": 2024,
  "end_line": 2052,
  "symbol_start_line": 2024,
  "symbol_end_line": 2052,
  "source": "  2024\tclass IssueAnalysis:\n  2025\t    \"\"\"Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.\n  2026\t\n  2027\t    Работает в двух режимах (#37): дочерним прогоном `IssueLifecycle`, когда\n  2028\t    цикл жив, и самостоятельным — при автономном запуске (скрипт, прогон\n  2029\t    прежнего поколения). Код один и тот же; отличается только родитель.\n  2030\t\n  2031\t    Фиксированный id `analysis-<repo>-<n>` даёт идемпотентность в обоих\n  2032\t    режимах: повторный `/analyze` упрётся в WorkflowAlreadyStarted, а не\n  2033\t    запустит второй дорогой прогон.\n  2034\t    \"\"\"\n  2035\t\n  2036\t    @workflow.run\n  2037\t    async def run(self, analyze: AnalyzeInput) -> bool:\n  2038\t        \"\"\"Возвращает, опубликованы ли артефакты.\n  2039\t\n  2040\t        Родителю этот ответ нужен, чтобы решить, можно ли передавать задачу\n  2041\t        разработчику: без аналитики передавать нечего. Автономный запуск\n  2042\t        результат просто игнорирует.\n  2043\t        \"\"\"\n  2044\t        if await _agents_off(analyze.repo, analyze.issue_number, \"/analyze\"):\n  2045\t            return False\n  2046\t        await workflow.execute_activity(\n  2047\t            activities.ack_command,\n  2048\t            analyze,\n  2049\t            start_to_close_timeout=timedelta(seconds=60),\n  2050\t            retry_policy=RetryPolicy(maximum_attempts=3),\n  2051\t        )\n  2052\t        return await _run_staged_analysis(analyze)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 17.88,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "_start_development workflow",
  "repo": "poh-issue-agents",
  "limit": 3
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_start_development",
      "name": "_start_development",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 1588,
      "end_line": 1638,
      "signature": "async def _start_development(self, issue: IssueInput) -> tuple",
      "qualified_name": "worker.workflows.IssueLifecycle._start_development",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::test_subissue_of_a_plan_does_not_start_its_own_development",
      "name": "test_subissue_of_a_plan_does_not_start_its_own_development",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 327,
      "end_line": 372,
      "signature": "async def test_subissue_of_a_plan_does_not_start_its_own_development()",
      "qualified_name": "tests.test_develop_autostart.test_subissue_of_a_plan_does_not_start_its_own_development",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "title": "File: shared/workflow_ids.py",
      "page_type": "file_page",
      "snippet": "# shared/workflow_ids.py\n\n## Overview\n\nИдентификаторы Temporal-workflow — в одном месте.\n\nID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный\n`issues.opened` идемпотентным, `",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_ids.py",
      "type": "page"
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
      "path": "worker/workflows.py"
    },
    {
      "path": "tests/test_develop_autostart.py"
    },
    {
      "path": "shared/workflow_ids.py"
    }
  ],
  "exact_match": true
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueLifecycle::_start_development"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::_start_development",
  "file": "worker/workflows.py",
  "name": "_start_development",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle._start_development",
  "signature": "async def _start_development(self, issue: IssueInput) -> tuple",
  "language": "python",
  "start_line": 1588,
  "end_line": 1638,
  "symbol_start_line": 1588,
  "symbol_end_line": 1638,
  "source": "  1588\t    async def _start_development(self, issue: IssueInput) -> tuple:\n  1589\t        \"\"\"Активность Develop: передать задачу агенту разработки.\n  1590\t\n  1591\t        Одна точка на оба входа — решение человека `build-me` и автостарт. Две\n  1592\t        копии этого вызова разъехались бы на первой же правке ретраев, и один из\n  1593\t        входов молча остался бы со старым поведением.\n  1594\t        \"\"\"\n  1595\t        try:\n  1596\t            pr_number = await workflow.execute_activity(\n  1597\t                activities.trigger_openhands_resolver,\n  1598\t                issue,\n  1599\t                # Прогон агента идёт десятками минут, поэтому потолок общий на\n  1600\t                # весь шаг, а живость сообщается heartbeat'ом: без него сервер\n  1601\t                # счёл бы активность мёртвой на первой же долгой стадии.\n  1602\t                start_to_close_timeout=timedelta(seconds=3600),\n  1603\t                heartbeat_timeout=timedelta(seconds=300),\n  1604\t                # ОДНА попытка, как у круга правок: активность недетерминирована,\n  1605\t                # идёт десятками минут и стоит денег, а её побочные эффекты\n  1606\t                # видны человеку — комментарий о передаче, ветка, PR.\n  1607\t                #\n  1608\t                # Три попытки выглядели дешёвой страховкой от сетевого сбоя, но\n  1609\t                # ретрай повторяет активность ЦЕЛИКОМ, включая прогон агента.\n  1610\t                # На живом прогоне #39 пуш падал на последнем шаге — уже после\n  1611\t                # работы агента, — и контур трижды объявил о передаче задачи и\n  1612\t                # трижды прогнал агента заново. Сбой сети на фоне такой цены\n  1613\t                # ничтожен: повтор инициирует человек, а не политика ретраев.\n  1614\t                retry_policy=RetryPolicy(maximum_attempts=1),\n  1615\t            )\n  1616\t        except Exception as e:\n  1617\t            # Раньше NotImplementedError отсюда ронял весь воркфлоу: цикл\n  1618\t            # исчезал, и Issue терял владельца состояния.\n  1619\t            reason = _failure_reason(e)\n  1620\t            workflow.logger.warning(\"передача в разработку не выполнена: %s\", reason)\n  1621\t            # Отчёт человеку, а не только метка фазы: до этого срыв передачи был\n  1622\t            # виден лишь как `phase:failed` в списке — отличить его от «ещё\n  1623\t            # работает» можно было только чтением логов контейнера.\n  1624\t            await workflow.execute_activity(\n  1625\t                activities.post_error_label,\n  1626\t                args=[issue, reason],\n  1627\t                start_to_close_timeout=timedelta(seconds=30),\n  1628\t                retry_policy=RetryPolicy(maximum_attempts=5),\n  1629\t            )\n  1630\t            return (lifecycle.FAILED, \"failed\", True)\n  1631\t        if pr_number is None:\n  1632\t            # Режим `dispatch`: работа идёт на чужой стороне, и о её исходе\n  1633\t            # придёт событие `pr-open`. Ждём в `in-development`.\n  1634\t            return (lifecycle.IN_DEVELOPMENT, \"in-development\", True)\n  1635\t        # Режим `local`: PR открыт прямо сейчас, ждать доклада не о чем — фаза\n  1636\t        # двигается сразу. Ревью доложит о себе само, уже из `pr-open`.\n  1637\t        self._pr_number = pr_number\n  1638\t        return (lifecycle.PR_OPEN, \"pr-open\", True)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 21.45,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 9 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/workflow_ids.py"
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
    "shared/workflow_ids.py": {
      "target": "shared/workflow_ids.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/workflow_ids.py",
        "summary": "Идентификаторы Temporal-workflow — в одном месте."
      },
      "hotspot": false,
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
        "tokens": 450,
        "full_tokens": 619,
        "pct_of_full": 72.7,
        "bodies_kept": [
          "estimate_workflow_id",
          "bft_workflow_id"
        ],
        "text": "\"\"\"\nИдентификаторы Temporal-workflow — в одном месте.\n\nID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный\n`issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делает\nидемпотентной повторную доставку вебхука с командой. Формат собирают и вебхук,\nи скрипты прямого запуска; разъехавшись, они молча потеряли бы именно эту\nидемпотентность — поэтому строка живёт здесь одна.\n\"\"\"\n\n\ndef issue_workflow_id(repo_full_name: str, issue_number: int, suffix: str = \"\") -> str:\n    ... 4 lines (13-16)\n\n\ndef estimate_workflow_id(repo_full_name: str, issue_number: int,\n                         comment_id: int | None = None) -> str:\n    # comment_id=None — запуск меткой `run:estimate`: комментария-триггера нет,\n    # различителем служит \"label\". Повторная доставка того же события упирается\n    # в WorkflowAlreadyStarted, а метка, поставленная заново после завершённого\n    # прогона, — честно новый прогон (прошлый закрыт, id свободен).\n    marker = \"label\" if comment_id is None else comment_id\n    return f\"estimate-{repo_full_name}-{issue_number}-{marker}\"\n\n\ndef bft_workflow_id(repo_full_name: str, issue_number: int, mode: str) -> str:\n    # Режим входит в id, а лишних различителей нет. Два режима — разные прогоны,\n    # и глубокий не должен упираться в идущий быстрый. Внутри режима id\n    # фиксирован: повторная команда при идущем прогоне упирается в\n    # WorkflowAlreadyStarted вместо второго прогона, а после завершения id\n    # свободен — и следующая команда с новыми уточнениями честно новый прогон.\n    return f\"bft-{mode}-{repo_full_name}-{issue_number}\"\n\n\ndef comment_ack_workflow_id(repo_full_name: str, comment_id: int) -> str:\n    ... 4 lines (39-42)\n\n\ndef analysis_workflow_id(repo_full_name: str, issue_number: int) -> str:\n    ... 3 lines (46-48)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 72.7% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 55.17,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 10 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "_dev_prepare _dev_run_agent _dev_tests _dev_publish",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 173,
      "end_line": 173,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_ready_for_dev.prepare",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::publish",
      "name": "publish",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 177,
      "end_line": 178,
      "signature": "async def publish(analyze: AnalyzeInput) -> str",
      "qualified_name": "tests.test_ready_for_dev.publish",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::OrphanAgentEvent::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 280,
      "end_line": 286,
      "signature": "async def run(self, orphan: OrphanEventInput) -> str",
      "qualified_name": "worker.workflows.OrphanAgentEvent.run",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "# могут не состояться до того, как что-либо сказано человеку.\n    task = await _run_with_heartbeat(_dev_prepare, issue, branch, label=\"dev:prepare\")\n    logger.info(\"Develop %s#%s: постановка (%d сим",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на Gi",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "type": "page"
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
      "path": "tests/test_ready_for_dev.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "worker/activities.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches '_dev_prepare', '_dev_run_agent', '_dev_tests'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 11 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "develop_workflow_id",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/repowise.py::DEVELOP",
      "name": "DEVELOP",
      "kind": "constant",
      "file": "shared/repowise.py",
      "start_line": 33,
      "end_line": 33,
      "signature": "DEVELOP = \"openhands\"",
      "qualified_name": "shared.repowise.DEVELOP",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_clarify_after_analysis.py::develop",
      "name": "develop",
      "kind": "function",
      "file": "tests/test_clarify_after_analysis.py",
      "start_line": 137,
      "end_line": 139,
      "signature": "async def develop(issue: IssueInput) -> int | None",
      "qualified_name": "tests.test_clarify_after_analysis.develop",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::develop",
      "name": "develop",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 140,
      "end_line": 141,
      "signature": "async def develop(issue: IssueInput) -> None",
      "qualified_name": "tests.test_develop_autostart.develop",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_ids.py::issue_workflow_id",
      "name": "issue_workflow_id",
      "kind": "function",
      "file": "shared/workflow_ids.py",
      "start_line": 12,
      "end_line": 16,
      "signature": "def issue_workflow_id(repo_full_name: str, issue_number: int, suffix: str = \"\") -> str",
      "qualified_name": "shared.workflow_ids.issue_workflow_id",
      "language": "python",
      "score": 20.06,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_ids.py::analysis_workflow_id",
      "name": "analysis_workflow_id",
      "kind": "function",
      "file": "shared/workflow_ids.py",
      "start_line": 45,
      "end_line": 48,
      "signature": "def analysis_workflow_id(repo_full_name: str, issue_number: int) -> str",
      "qualified_name": "shared.workflow_ids.analysis_workflow_id",
      "language": "python",
      "score": 20.05,
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
      "path": "shared/repowise.py"
    },
    {
      "path": "tests/test_clarify_after_analysis.py"
    },
    {
      "path": "tests/test_develop_autostart.py"
    },
    {
      "path": "shared/workflow_ids.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'develop_workflow_id'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueEstimation"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueEstimation",
  "file": "worker/workflows.py",
  "name": "IssueEstimation",
  "kind": "class",
  "qualified_name": "worker.workflows.IssueEstimation",
  "signature": "class IssueEstimation",
  "language": "python",
  "start_line": 2207,
  "end_line": 2274,
  "symbol_start_line": 2207,
  "symbol_end_line": 2274,
  "source": "  2207\tclass IssueEstimation:\n  2208\t    \"\"\"Оценка трудоёмкости по команде /estimate.\n  2209\t\n  2210\t    Отдельный workflow, а не сигнал в IssueLifecycle: тот завершается после\n  2211\t    приоритизации (а на спаме и дубликате — раньше), и через неделю сигналить\n  2212\t    было бы некуда. ID включает comment_id, поэтому повторная доставка того же\n  2213\t    вебхука не запускает вторую оценку, а новая команда — это честно новый\n  2214\t    прогон со своей историей в Temporal UI.\n  2215\t    \"\"\"\n  2216\t\n  2217\t    @workflow.run\n  2218\t    async def run(self, req: EstimateRequest) -> None:\n  2219\t        default_retry = RetryPolicy(maximum_attempts=3)\n  2220\t        # Стадия нужна, чтобы человек в комментарии увидел, ЧТО именно\n  2221\t        # сломалось, а не абстрактное «ошибка обработки».\n  2222\t        if await _agents_off(req.repo, req.issue_number, \"/estimate\"):\n  2223\t            return\n  2224\t        stage = \"подтверждение команды\"\n  2225\t        try:\n  2226\t            await workflow.execute_activity(\n  2227\t                activities.ack_estimate_command,\n  2228\t                req,\n  2229\t                start_to_close_timeout=timedelta(seconds=30),\n  2230\t                retry_policy=default_retry,\n  2231\t            )\n  2232\t\n  2233\t            stage = \"сбор контекста\"\n  2234\t            context = await workflow.execute_activity(\n  2235\t                activities.collect_estimation_context,\n  2236\t                req,\n  2237\t                start_to_close_timeout=timedelta(seconds=120),\n  2238\t                retry_policy=default_retry,\n  2239\t            )\n  2240\t\n  2241\t            stage = \"извлечение фактов\"\n  2242\t            facts = await workflow.execute_activity(\n  2243\t                activities.extract_estimation_facts,\n  2244\t                context,\n  2245\t                start_to_close_timeout=timedelta(seconds=180),\n  2246\t                retry_policy=default_retry,\n  2247\t            )\n  2248\t\n  2249\t            stage = \"расчёт\"\n  2250\t            result: EstimateResult = await workflow.execute_activity(\n  2251\t                activities.compute_estimate,\n  2252\t                args=[facts, context],\n  2253\t                start_to_close_timeout=timedelta(seconds=30),\n  2254\t                # Расчёт детерминирован и не ходит в сеть: повтор дал бы\n  2255\t                # ровно тот же результат, ретрай тут бессмыслен.\n  2256\t                retry_policy=RetryPolicy(maximum_attempts=1),\n  2257\t            )\n  2258\t\n  2259\t            stage = \"публикация\"\n  2260\t            await workflow.execute_activity(\n  2261\t                activities.post_estimate_comment,\n  2262\t                args=[req, result],\n  2263\t                start_to_close_timeout=timedelta(seconds=30),\n  2264\t                retry_policy=default_retry,\n  2265\t            )\n  2266\t            await _finish_labels(req.repo, req.issue_number, ESTIMATE, ok=True)\n  2267\t        except Exception as e:\n  2268\t            await workflow.execute_activity(\n  2269\t                activities.post_estimate_error,\n  2270\t                args=[req, stage, _failure_reason(e)],\n  2271\t                start_to_close_timeout=timedelta(seconds=30),\n  2272\t                retry_policy=RetryPolicy(maximum_attempts=5),\n  2273\t            )\n  2274\t            await _finish_labels(req.repo, req.issue_number, ESTIMATE, ok=False)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 18.58,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 13 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "def _dev_prepare",
  "repo": "poh-issue-agents",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 173,
      "end_line": 173,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_ready_for_dev.prepare",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_agents_as_children.py",
      "start_line": 115,
      "end_line": 115,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_agents_as_children.prepare",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_clarify_after_analysis.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_clarify_after_analysis.py",
      "start_line": 108,
      "end_line": 108,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_clarify_after_analysis.prepare",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 113,
      "end_line": 113,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_develop_autostart.prepare",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_lifecycle_loop.py::prepare",
      "name": "prepare",
      "kind": "function",
      "file": "tests/test_lifecycle_loop.py",
      "start_line": 134,
      "end_line": 134,
      "signature": "async def prepare(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_lifecycle_loop.prepare",
      "language": "python",
      "score": 45.01,
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
      "path": "tests/test_ready_for_dev.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_clarify_after_analysis.py"
    },
    {
      "path": "tests/test_develop_autostart.py"
    },
    {
      "path": "tests/test_lifecycle_loop.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'def _dev_prepare'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 14 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "def _dev_announce",
  "repo": "poh-issue-agents",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_dev_announce",
      "name": "_dev_announce",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 1817,
      "end_line": 1856,
      "signature": "async def _dev_announce(issue: IssueInput, branch: str, *, where: str) -> None",
      "qualified_name": "worker.activities._dev_announce",
      "language": "python",
      "score": 20.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_dev_handoff_once.py::test_announce_is_skipped_when_already_in_development",
      "name": "test_announce_is_skipped_when_already_in_development",
      "kind": "function",
      "file": "tests/test_dev_handoff_once.py",
      "start_line": 26,
      "end_line": 36,
      "signature": "def test_announce_is_skipped_when_already_in_development(monkeypatch)",
      "qualified_name": "tests.test_dev_handoff_once.test_announce_is_skipped_when_already_in_development",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_dev_handoff_once.py::test_announce_posts_on_the_first_handoff",
      "name": "test_announce_posts_on_the_first_handoff",
      "kind": "function",
      "file": "tests/test_dev_handoff_once.py",
      "start_line": 39,
      "end_line": 49,
      "signature": "def test_announce_posts_on_the_first_handoff(monkeypatch)",
      "qualified_name": "tests.test_dev_handoff_once.test_announce_posts_on_the_first_handoff",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_dev_handoff_once.py::test_announce_speaks_up_when_labels_are_unreadable",
      "name": "test_announce_speaks_up_when_labels_are_unreadable",
      "kind": "function",
      "file": "tests/test_dev_handoff_once.py",
      "start_line": 52,
      "end_line": 66,
      "signature": "def test_announce_speaks_up_when_labels_are_unreadable(monkeypatch)",
      "qualified_name": "tests.test_dev_handoff_once.test_announce_speaks_up_when_labels_are_unreadable",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_dev_paths",
      "name": "_dev_paths",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 1441,
      "end_line": 1449,
      "signature": "def _dev_paths(issue: IssueInput) -> tuple[Path, Path]",
      "qualified_name": "worker.activities._dev_paths",
      "language": "python",
      "score": 10.07,
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
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_dev_handoff_once.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'def _dev_announce'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "_run_with_heartbeat",
  "repo": "poh-issue-agents",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_run_with_heartbeat",
      "name": "_run_with_heartbeat",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 1039,
      "end_line": 1065,
      "signature": "async def _run_with_heartbeat(fn, *args, label: str)",
      "qualified_name": "worker.activities._run_with_heartbeat",
      "language": "python",
      "score": 160.1,
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
      "score": 50.02,
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
      "score": 50.01,
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
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::CommentAck::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 303,
      "end_line": 309,
      "signature": "async def run(self, ack: CommentAckInput) -> None",
      "qualified_name": "worker.workflows.CommentAck.run",
      "language": "python",
      "score": 50.01,
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
      "path": "worker/activities.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "worker/consolidation_workflow.py"
    }
  ],
  "exact_match": true
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "_dev_prepare _dev_run_agent _dev_tests _dev_publish worker/activities.py",
  "repo": "poh-issue-agents",
  "mode": "concept"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def trigger_openhands_resolver(issue: Issue",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на Gi",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.99
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
      "path": "worker/activities.py"
    }
  ]
}
