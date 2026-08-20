# Итог

1. **Классификация Issue** находится в `worker/activities.py::classify_issue` (строки 517-555). Использует промпт `system_advisor.md` из `/app/prompts/` и `capabilities.md`. Возвращает `ClassificationResult` с `label` из 4 категорий:
   - EXISTING → `advisor:existing-functionality`
   - CONSULTATION → `advisor:consultation`
   - BUG → `advisor:bug`
   - FEATURE → `advisor:feature-request`

2. **Схема извлечения** `ClassificationExtraction` (строки 84-86) — Pydantic модель с полями `category: str` (4 варианта) и `answer: str`. Для добавления пятой категории нужно изменить Field description и `label_map` в `classify_issue`.

3. **Схема меток команд** определена в `shared/commands.py`:
   - `done_label(command) = "done:{command}"`
   - `failed_label(command) = "failed:{command}"`
   - `running_labels(command) = (run_label(command),) + legacy`
   - Префиксы: `DONE_PREFIX`, `FAILED_PREFIX`, `RUN_PREFIX`

4. **Цепочка FNR** (анализ) реализована в `worker/workflows.py::_run_staged_analysis` (строки 110-203). Стадии: `FNR_STAGE_NAMES = (REPOWISE_STAGE, "task", "concept", "debate", "sysreq", "validate")`. Каждая стадия — отдельная activity `run_fnr_stage`, затем `publish_analysis` с артефактами.

5. **Модель фаз жизненного цикла** в `shared/lifecycle.py` — единственный источник правды. Основной путь: CREATED → CLASSIFIED → BUSINESS_ANALYSIS → SYSTEM_REQUIREMENTS → ... → RELEASED. Боковые состояния: SPAM, DUPLICATE, ANSWERED, ESCALATED, FAILED, CANCELLED. Таблица `TRANSITIONS` определяет допустимые переходы.

6. **Workflow IssueLifecycle** (строки 314+) — один Temporal-workflow на один issue. Имеет сигналы:
   - `human_decision(label)` — кладёт label в `_signal_queue`
   - `user_comment(text, comment_id)` — реплика человека
   - `agent_event(event)` — факт от внешнего агента
   - `analyze_requested(comment_id)` — кладёт `AGENT_ANALYZE` в очередь
   - `bft_requested(req)`, `estimate_requested(comment_id)`

7. **Механизм обработки сигналов** — `_run_phase_loop` (строки 978-1055) обрабатывает очередь `_signal_queue` через `_wait_for_signal()`. В зависимости от текущей фазы вызывает соответствующий обработчик (`_analysis_requested`, `_agent_event`, и т.д.).

8. **Запуск дочерних workflows** — `_run_analysis_child` (строки 869-915) запускает `IssueAnalysis` дочерним прогоном через `workflow.start_workflow`. Фиксированный id: `analysis-<repo>-<n>` даёт идемпотентность.

9. **Константа сигнала** `AGENT_ANALYZE = "__agent__:analyze"` (строка 73) используется для запросов аналитики из очереди сигналов.

10. **Фаза анализа** (`_phase_analysis`, строки 1358-1367) соответствует `BUSINESS_ANALYSIS` в lifecycle и запускает `_run_analysis_child`.

# Открытые вопросы

- Промпт `/app/prompts/system_advisor.md` не индексирован — точный формат категорий не виден
- Не определён процесс продуктового исследования (какие стадии, PRD, обход нексусов) — это отдельная задача проектирования
- Не найдено точное место обработки сигналов в `_run_phase_loop` — skeleton показал только структуру

# Диалог

**Ход 1:** Получен обзор репозитория `poh-issue-agents` через `get_overview`. Репозиторий 323 файла, 80K строк. Ключевые модули: `worker/workflows.py` (workflows IssueLifecycle, IssueAnalysis), `shared/lifecycle.py` (модель фаз), `worker/activities.py` (hotspot, классификация), `shared/commands.py` (команды и метки).

**Ход 2:** Поиск `classify_issue` через `search_codebase` — найдена функция в `worker/activities.py:517-555`. Использует промпт `system_advisor.md` и возвращает `ClassificationResult` с 4 категориями.

**Ход 3:** Получена `ClassificationExtraction` (строки 84-86) — Pydantic модель с `category: str = Field(description="EXISTING | CONSULTATION | BUG | FEATURE")` и `answer: str`. Промпт не найден в индексе (`/app/prompts/` не индексируется).

**Ход 4:** Поиск `IssueAnalysis` и `finish_command_labels` — найдена функция работы с метками (строки 487-511) использующая `done_label`, `failed_label`, `running_labels` из `shared/commands.py`.

**Ход 5:** Получены функции меток: `done_label(command) = f"{DONE_PREFIX}{command}"`, `failed_label` аналогично, `running_labels` включает legacy. Получен `_run_staged_analysis` (строки 110-203) — цепочка FNR через `FNR_STAGE_NAMES` → `run_fnr_stage` → `publish_analysis`.

**Ход 6:** Найдены `FNR_STAGE_NAMES = (REPOWISE_STAGE, "task", "concept", "debate", "sysreq", "validate")` и полный `shared/lifecycle.py` с моделью фаз и переходов. `analysis` → `BUSINESS_ANALYSIS`.

**Ход 7:** Получена `IssueLifecycle::analyze_requested` (строки 469-523) — кладёт `AGENT_ANALYZE` в `_signal_queue` после проверок идемпотентности.

**Ход 8:** Получена `IssueLifecycle::agent_event` (строки 526-550) — кладёт события в `_signal_queue` с идемпотентностью по `event.key()`.

**Ход 9:** Получен `IssueLifecycle::run` (строки 653-705) — вызывает `_run_phase_loop(issue)` для нового поколения.

**Ход 10:** Получен skeleton `worker/workflows.py` — структура с сигналами, фазами, `_run_analysis_child`, `_analysis_requested`, `_run_phase_loop`. Найдена константа `AGENT_ANALYZE = "__agent__:analyze"`.

**Ход 11:** Попытка найти `_run_phase_loop` через symbol search не удалась — skeleton показал структуру, но не полную реализацию обработки очереди сигналов.

**Ход 12:** Создан артефакт с собранным контекстом в `sa_documentation/FNR/FNR_1/repowise-dialog.md`.


---
session: rw-analysis-po-helper-org__poh-issue-agents-64
workspace: contour
turns: 32
started: 2026-08-20T19:08:50Z
finished: 2026-08-20T19:10:07Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `a41f569f0381` | 30 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "po-helper-org__poh-issue-agents-64",
  "include": [
    "content"
  ]
}
```

**Ответ:**

{
  "error": "Unknown repo 'po-helper-org__poh-issue-agents-64'. Available: ['poh-bft-writer', 'poh-cortex', 'poh-helper', 'poh-infra', 'poh-issue-agents', 'poh-memory-engine', 'poh-pr-agents', 'poh-scheduller', 'poh-sprint-agents']",
  "remedy": "Call list_repos to see the valid repo aliases, or omit the 'repo' argument to use the default repository."
}

## Ход 2 · `get_overview` · contour

**Запрос:**

```json
{
  "include": [
    "content"
  ],
  "repo": "poh-issue-agents"
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

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "classify_issue advisor:feature-request advisor:bug classification",
  "repo": "poh-issue-agents",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::classify_issue",
      "name": "classify_issue",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 517,
      "end_line": 555,
      "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
      "qualified_name": "worker.activities.classify_issue",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_bft_workflow.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_bft_workflow.ISSUE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::classify",
      "name": "classify",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 81,
      "end_line": 82,
      "signature": "async def classify(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
      "qualified_name": "tests.test_develop_autostart.classify",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_park_deadlines.py::classify",
      "name": "classify",
      "kind": "function",
      "file": "tests/test_park_deadlines.py",
      "start_line": 114,
      "end_line": 115,
      "signature": "async def classify(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
      "qualified_name": "tests.test_park_deadlines.classify",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.classify_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef classify_issue(issue: IssueInput, bft_on_triage: bool = False) ->",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.ClassificationResult",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.ClassificationResult\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationResult\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClassificationResult",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: tests.test_estimate_report.context",
      "page_type": "symbol_spotlight",
      "snippet": "ationContext:\n    base = dict(\n        title=\"Заголовок\",\n        body=\"Описание\",\n        labels=[\"advisor:feature-request\"],\n        thread=[],\n        branch=None,\n        artifacts={},\n        tru",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_report.py::context",
      "file": "tests/test_estimate_report.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.ClassificationExtraction",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.ClassificationExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationExtraction\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::ClassificationExtraction",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: tests.test_estimate_activities.test_context_carries_title_body_and_labels",
      "page_type": "symbol_spotlight",
      "snippet": "ries_title_body_and_labels(fake):\n    fake.issue = {\"title\": \"Т\", \"body\": \"О\", \"labels\": [{\"name\": \"advisor:bug\"}]}\n    context = activities.collect_estimation_context(REQ)\n    assert context.title ==",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_activities.py::test_context_carries_title_body_and_labels",
      "file": "tests/test_estimate_activities.py",
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
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_bft_workflow.py"
    },
    {
      "path": "tests/test_develop_autostart.py"
    },
    {
      "path": "tests/test_park_deadlines.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "tests/test_estimate_report.py"
    },
    {
      "path": "tests/test_estimate_activities.py"
    }
  ],
  "exact_match": true
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::classify_issue",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::classify_issue",
  "file": "worker/activities.py",
  "name": "classify_issue",
  "kind": "function",
  "qualified_name": "worker.activities.classify_issue",
  "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
  "language": "python",
  "start_line": 517,
  "end_line": 555,
  "symbol_start_line": 517,
  "symbol_end_line": 555,
  "source": "   517\tdef classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:\n   518\t    \"\"\"Тип запроса плюс ответ advisor комментарием.\n   519\t\n   520\t    `bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:\n   521\t    на него отвечает БФТ, и два комментария подряд означали бы, что первый\n   522\t    неактуален уже в момент публикации. Для бага, консультации и «уже\n   523\t    реализовано» ответ публикуется как прежде — БФТ по ним не собирается, и\n   524\t    молчание оставило бы Issue вообще без содержательного комментария.\n   525\t\n   526\t    Решение принимается ЗДЕСЬ, а не отдельной активностью публикации, потому что\n   527\t    зависит от категории — а категорию знает только эта активность. Развести их\n   528\t    значило бы гонять текст ответа через воркфлоу ради условия, которое здесь\n   529\t    уже вычислено.\n   530\t\n   531\t    Аргумент со значением по умолчанию, а не новая activity: прогоны прежнего\n   532\t    поколения зовут её одним аргументом и обязаны получить прежнее поведение.\n   533\t    \"\"\"\n   534\t    capabilities = (WORKSPACE_DIR / \"capabilities.md\").read_text(encoding=\"utf-8\") \\\n   535\t        if (WORKSPACE_DIR / \"capabilities.md\").exists() else \"(пусто)\"\n   536\t    user_message = f\"Заголовок: {issue.title}\\n\\nОписание:\\n{issue.body}\\n\\nИзвестный функционал:\\n{capabilities}\"\n   537\t    result = llm.extract(\n   538\t        _load_prompt(\"system_advisor.md\"), user_message, ClassificationExtraction, model=llm.MODEL_CLASSIFY,\n   539\t    )\n   540\t    label_map = {\n   541\t        \"EXISTING\": \"advisor:existing-functionality\",\n   542\t        \"CONSULTATION\": \"advisor:consultation\",\n   543\t        \"BUG\": \"advisor:bug\",\n   544\t        \"FEATURE\": \"advisor:feature-request\",\n   545\t    }\n   546\t    label = label_map.get(result.category, \"advisor:answered\")\n   547\t    # The advisor prompt still asks the model to prefix its answer with a\n   548\t    # legacy [[MARKER]] (from the pre-Instructor text-parsing era). The\n   549\t    # category is now carried structurally, so strip that marker line before\n   550\t    # posting — it must not appear in the user-facing comment.\n   551\t    answer = re.sub(r\"^\\s*\\[\\[[^\\]]+\\]\\]\\s*\", \"\", result.answer)\n   552\t    if not (bft_on_triage and label == \"advisor:feature-request\"):\n   553\t        github_client.post_comment(issue.repo, issue.issue_number, answer)\n   554\t    github_client.add_label(issue.repo, issue.issue_number, label)\n   555\t    return ClassificationResult(label=label, answer=answer)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 25.29,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 5 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "system_advisor.md ClassificationExtraction",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::ClassificationExtraction",
      "name": "ClassificationExtraction",
      "kind": "class",
      "file": "worker/activities.py",
      "start_line": 84,
      "end_line": 86,
      "signature": "class ClassificationExtraction",
      "qualified_name": "worker.activities.ClassificationExtraction",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::ClassificationResult",
      "name": "ClassificationResult",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 203,
      "end_line": 205,
      "signature": "class ClassificationResult",
      "qualified_name": "shared.workflow_types.ClassificationResult",
      "language": "python",
      "score": 7.743,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/consolidation_activities.py::AssignExtraction",
      "name": "AssignExtraction",
      "kind": "class",
      "file": "worker/consolidation_activities.py",
      "start_line": 136,
      "end_line": 138,
      "signature": "class AssignExtraction",
      "qualified_name": "worker.consolidation_activities.AssignExtraction",
      "language": "python",
      "score": 7.519,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "том и обязаны получить прежнее поведение.\n    \"\"\"\n    capabilities = (WORKSPACE_DIR / \"capabilities.md\").read_text(encoding=\"utf-8\") \\\n        if (WORKSPACE_DIR / \"capabilities.md\").exists() else \"(пу",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.ClassificationExtraction",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.ClassificationExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationExtraction\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::ClassificationExtraction",
      "file": "worker/activities.py",
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
      "path": "worker/activities.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "worker/consolidation_activities.py"
    }
  ],
  "exact_match": true
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/activities.py::ClassificationExtraction"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::ClassificationExtraction",
  "file": "worker/activities.py",
  "name": "ClassificationExtraction",
  "kind": "class",
  "qualified_name": "worker.activities.ClassificationExtraction",
  "signature": "class ClassificationExtraction",
  "language": "python",
  "start_line": 84,
  "end_line": 86,
  "symbol_start_line": 84,
  "symbol_end_line": 86,
  "source": "    84\tclass ClassificationExtraction(BaseModel):\n    85\t    category: str = Field(description=\"EXISTING | CONSULTATION | BUG | FEATURE\")\n    86\t    answer: str",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.73,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "prompts/system_advisor.md advisor prompt",
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
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/consolidation_activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "nput, bft_on_triage: bool = False) -> ClassificationResult\n```\n\n## Overview\n\nТип запроса плюс ответ advisor комментарием.\n\n`bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Application Worker",
      "page_type": "module_page",
      "snippet": "ры считаются зде\n\n- `worker/activities.py`: Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (верси",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_bft_stage_system",
      "name": "_bft_stage_system",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 2457,
      "end_line": 2476,
      "signature": "def _bft_stage_system(stage_name: str, role_tail: str) -> str",
      "qualified_name": "worker.activities._bft_stage_system",
      "language": "python",
      "score": 15.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::SYSTEM_REQUIREMENTS",
      "name": "SYSTEM_REQUIREMENTS",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 25,
      "end_line": 25,
      "signature": "SYSTEM_REQUIREMENTS = \"system-requirements\"",
      "qualified_name": "shared.lifecycle.SYSTEM_REQUIREMENTS",
      "language": "python",
      "score": 15.01,
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
      "path": "worker/consolidation_activities.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/lifecycle.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'system_advisor'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "*.md prompts advisor",
  "repo": "poh-issue-agents",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "_load_prompt PROMPTS_DIR prompts directory",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_load_prompt",
      "name": "_load_prompt",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 73,
      "end_line": 74,
      "signature": "def _load_prompt(name: str) -> str",
      "qualified_name": "worker.activities._load_prompt",
      "language": "python",
      "score": 15.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/consolidation_activities.py::_load_prompt",
      "name": "_load_prompt",
      "kind": "function",
      "file": "worker/consolidation_activities.py",
      "start_line": 18,
      "end_line": 19,
      "signature": "def _load_prompt(name: str) -> str",
      "qualified_name": "worker.consolidation_activities._load_prompt",
      "language": "python",
      "score": 15.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::PROMPTS_DIR",
      "name": "PROMPTS_DIR",
      "kind": "constant",
      "file": "worker/activities.py",
      "start_line": 68,
      "end_line": 68,
      "signature": "PROMPTS_DIR = Path(\"/app/prompts\")",
      "qualified_name": "worker.activities.PROMPTS_DIR",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/consolidation_activities.py::PROMPTS_DIR",
      "name": "PROMPTS_DIR",
      "kind": "constant",
      "file": "worker/consolidation_activities.py",
      "start_line": 15,
      "end_line": 15,
      "signature": "PROMPTS_DIR = Path(\"/app/prompts\")",
      "qualified_name": "worker.consolidation_activities.PROMPTS_DIR",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/estimation.py::load_rules",
      "name": "load_rules",
      "kind": "function",
      "file": "worker/estimation.py",
      "start_line": 129,
      "end_line": 131,
      "signature": "def load_rules(path: Path = RULES_PATH) -> dict",
      "qualified_name": "worker.estimation.load_rules",
      "language": "python",
      "score": 7.629,
      "next": "get_symbol"
    },
    {
      "title": "Application Worker",
      "page_type": "module_page",
      "snippet": "is documented on its own pages.\n\n\n\n\n## Overview\n\nApplication Worker covers 9 python files across 1 directory, exposing 190 public symbols. It sits centrally in the import graph (mean PageRank 0.0116)",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker",
      "type": "page"
    },
    {
      "title": "Infrastructure: worker/Dockerfile",
      "page_type": "infra_page",
      "snippet": "позитория очищается при\n# автодеплое, и bind-монтирование из него оставило бы воркер без файлов —\n# _load_prompt упал бы на FileNotFoundError уже на первой стадии.\n# Локальный docker-compose.yml всё е",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/Dockerfile",
      "type": "page"
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "page_type": "infra_page",
      "snippet": "produced in full.\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Resolve and ensure the working-tree directory SDD uses for its short-lived\n# artifacts: task briefs, implementer reports, review package",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "type": "page"
    },
    {
      "title": "File: .claude/skills/writing-skills/render-graphs.js",
      "page_type": "file_page",
      "snippet": "p(line => + line).join( dot -Tsvg utf-8 Error running dot: --combine Usage: render-graphs.js <skill-directory> [--combine] Options: --combine    Combine all diagrams into one SVG Example: ./render-gra",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/writing-skills/render-graphs.js",
      "type": "page"
    },
    {
      "title": "Active Landscape",
      "page_type": "onboarding",
      "snippet": "x. Those are the ones where changes are most likely to go wrong.\n\n\n\n## Areas under active change\n\n| Directory | Commits (90d) | Files | Hotspots |\n| --- | --- | --- | --- |\n| `tests` | 228 | 83 | 14 |",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/active_landscape",
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
      "path": "worker/activities.py"
    },
    {
      "path": "worker/consolidation_activities.py"
    },
    {
      "path": "worker/estimation.py"
    },
    {
      "path": "worker/Dockerfile"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js"
    }
  ],
  "exact_match": true
}

## Ход 10 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/activities.py::_load_prompt"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_load_prompt",
  "file": "worker/activities.py",
  "name": "_load_prompt",
  "kind": "function",
  "qualified_name": "worker.activities._load_prompt",
  "signature": "def _load_prompt(name: str) -> str",
  "language": "python",
  "start_line": 73,
  "end_line": 74,
  "symbol_start_line": 73,
  "symbol_end_line": 74,
  "source": "    73\tdef _load_prompt(name: str) -> str:\n    74\t    return (PROMPTS_DIR / name).read_text(encoding=\"utf-8\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 16.17,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 11 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "prompts/*.md",
  "repo": "poh-issue-agents",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
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
  "limit": 10,
  "query": "IssueAnalysis analyze_requested run: done: failed:",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::ANALYZE",
      "name": "ANALYZE",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 20,
      "end_line": 20,
      "signature": "ANALYZE = \"analyze\"",
      "qualified_name": "shared.commands.ANALYZE",
      "language": "python",
      "score": 47.51,
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
      "score": 47.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 42.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_bft_workflow.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_bft_workflow.ISSUE",
      "language": "python",
      "score": 42.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_analysis_requested",
      "name": "_analysis_requested",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 955,
      "end_line": 975,
      "signature": "async def _analysis_requested(self, issue: IssueInput) -> tuple",
      "qualified_name": "worker.workflows.IssueLifecycle._analysis_requested",
      "language": "python",
      "score": 22.52,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.analyze_requested",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.analyze_requested\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 5\n\n```\nasync def analyze_requested(self, comment_id: i",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::analyze_requested",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "нты существуют **и по отдельности, и в рамках Issue**.\nДо этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifec",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.finish_command_labels",
      "page_type": "symbol_spotlight",
      "snippet": "Обратный ход: снять метки «идёт», повесить исход.\n\nНеуспех получает СВОЮ метку, а не просто снятый `run:*`: молча снятая метка\nнеотличима от «никто не запускал», а именно это и нужно увидеть в ленте.",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::finish_command_labels",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueBft",
      "page_type": "symbol_spotlight",
      "snippet": "ментарий о сбое) и два места, где эту обвязку надо чинить.\n\nРаботает в двух режимах запуска, как и `IssueAnalysis` (#37): дочерним\nпрогоном цикла, когда цикл жив, и самостоятельным — иначе. Id фиксиро",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueBft",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueAnalysis",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueAnalysis\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueAnalysis\n```\n\n## Overview\n\nАналитика по запросу (Слой C) — воркф",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueAnalysis",
      "file": "worker/workflows.py",
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
      "path": "shared/commands.py"
    },
    {
      "path": "shared/repowise.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_bft_workflow.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/agent_launcher.py"
    },
    {
      "path": "worker/activities.py"
    }
  ],
  "exact_match": true
}

## Ход 13 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueAnalysis"
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
    "timing_ms": 14.55,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/activities.py::finish_command_labels"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::finish_command_labels",
  "file": "worker/activities.py",
  "name": "finish_command_labels",
  "kind": "function",
  "qualified_name": "worker.activities.finish_command_labels",
  "signature": "async def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
  "language": "python",
  "start_line": 487,
  "end_line": 511,
  "symbol_start_line": 487,
  "symbol_end_line": 511,
  "source": "   487\tasync def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:\n   488\t    \"\"\"Обратный ход: снять метки «идёт», повесить исход.\n   489\t\n   490\t    Неуспех получает СВОЮ метку, а не просто снятый `run:*`: молча снятая метка\n   491\t    неотличима от «никто не запускал», а именно это и нужно увидеть в ленте.\n   492\t\n   493\t    Best-effort по каждой метке: прогон уже состоялся, и провал косметики не\n   494\t    должен превращать успешный анализ в проваленный. Ошибка уходит в лог, но\n   495\t    наружу не пробрасывается — activity зовётся из терминальных веток воркфлоу.\n   496\t    \"\"\"\n   497\t    outcome = done_label(command) if ok else failed_label(command)\n   498\t    # Исход ПРЕДЫДУЩЕГО прогона снимается вместе с «идёт»: `done:analyze` рядом\n   499\t    # с `failed:analyze` — противоречие, а не история. По такой паре нельзя\n   500\t    # сказать, чем кончился последний прогон, и выборка `label:failed:*`\n   501\t    # показывает задачи, которые давно починены повторным запуском.\n   502\t    previous = failed_label(command) if ok else done_label(command)\n   503\t    for stale in (*running_labels(command), previous):\n   504\t        try:\n   505\t            await asyncio.to_thread(github_client.remove_label, repo, issue_number, stale)\n   506\t        except Exception as exc:\n   507\t            logger.warning(\"не снял метку %s с %s#%s: %s\", stale, repo, issue_number, exc)\n   508\t    try:\n   509\t        await asyncio.to_thread(github_client.add_label, repo, issue_number, outcome)\n   510\t    except Exception as exc:\n   511\t        logger.warning(\"не поставил метку %s на %s#%s: %s\", outcome, repo, issue_number, exc)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 28.16,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "done_label failed_label running_labels",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/agent_events.py::FAILED",
      "name": "FAILED",
      "kind": "constant",
      "file": "shared/agent_events.py",
      "start_line": 27,
      "end_line": 27,
      "signature": "FAILED = \"failed\"",
      "qualified_name": "shared.agent_events.FAILED",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::FAILED",
      "name": "FAILED",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 42,
      "end_line": 42,
      "signature": "FAILED = \"failed\"",
      "qualified_name": "shared.lifecycle.FAILED",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_command_label_activities.py::test_mark_command_running_labels_the_issue",
      "name": "test_mark_command_running_labels_the_issue",
      "kind": "function",
      "file": "tests/test_command_label_activities.py",
      "start_line": 75,
      "end_line": 80,
      "signature": "def test_mark_command_running_labels_the_issue(monkeypatch)",
      "qualified_name": "tests.test_command_label_activities.test_mark_command_running_labels_the_issue",
      "language": "python",
      "score": 13.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_label_commands.py::test_running_labels_include_legacy_analyzing",
      "name": "test_running_labels_include_legacy_analyzing",
      "kind": "function",
      "file": "tests/test_label_commands.py",
      "start_line": 44,
      "end_line": 49,
      "signature": "def test_running_labels_include_legacy_analyzing()",
      "qualified_name": "tests.test_label_commands.test_running_labels_include_legacy_analyzing",
      "language": "python",
      "score": 13.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::failed_label",
      "name": "failed_label",
      "kind": "function",
      "file": "shared/commands.py",
      "start_line": 51,
      "end_line": 52,
      "signature": "def failed_label(command: str) -> str",
      "qualified_name": "shared.commands.failed_label",
      "language": "python",
      "score": 12.07,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::done_label",
      "name": "done_label",
      "kind": "function",
      "file": "shared/commands.py",
      "start_line": 47,
      "end_line": 48,
      "signature": "def done_label(command: str) -> str",
      "qualified_name": "shared.commands.done_label",
      "language": "python",
      "score": 12.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::running_labels",
      "name": "running_labels",
      "kind": "function",
      "file": "shared/commands.py",
      "start_line": 55,
      "end_line": 57,
      "signature": "def running_labels(command: str) -> tuple[str, ...]",
      "qualified_name": "shared.commands.running_labels",
      "language": "python",
      "score": 12.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::_LEGACY_RUNNING_LABELS",
      "name": "_LEGACY_RUNNING_LABELS",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 40,
      "end_line": 40,
      "signature": "_LEGACY_RUNNING_LABELS = {ANALYZE: (\"analyzing\",)}",
      "qualified_name": "shared.commands._LEGACY_RUNNING_LABELS",
      "language": "python",
      "score": 12.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.finish_command_labels",
      "page_type": "symbol_spotlight",
      "snippet": "наружу не пробрасывается — activity зовётся из терминальных веток воркфлоу.\n    \"\"\"\n    outcome = done_label(command) if ok else failed_label(command)\n    # Исход ПРЕДЫДУЩЕГО прогона снимается вмест",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::finish_command_labels",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "File: scripts/e2e_live.py",
      "page_type": "file_page",
      "snippet": "оценка завершена метка запуска снята E2E_REPO GITHUB_REPOSITORY прогон завершился неуспехом: метка {failed_label(ESTIMATE)} advisor:error триаж упал: метка advisor:error Temporal отвечает, но health-c",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/e2e_live.py",
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
      "path": "shared/agent_events.py"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "tests/test_command_label_activities.py"
    },
    {
      "path": "tests/test_label_commands.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "scripts/e2e_live.py"
    }
  ],
  "exact_match": true
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "_run_staged_analysis",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::_run_staged_analysis",
      "name": "_run_staged_analysis",
      "kind": "function",
      "file": "worker/workflows.py",
      "start_line": 110,
      "end_line": 203,
      "signature": "async def _run_staged_analysis(analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows._run_staged_analysis",
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
      "symbol_id": "shared/repowise.py::ANALYSIS",
      "name": "ANALYSIS",
      "kind": "constant",
      "file": "shared/repowise.py",
      "start_line": 32,
      "end_line": 32,
      "signature": "ANALYSIS = \"analysis\"",
      "qualified_name": "shared.repowise.ANALYSIS",
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
      "path": "worker/workflows.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "shared/repowise.py"
    }
  ],
  "exact_match": true
}

## Ход 17 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/commands.py::done_label"
}
```

**Ответ:**

{
  "symbol_id": "shared/commands.py::done_label",
  "file": "shared/commands.py",
  "name": "done_label",
  "kind": "function",
  "qualified_name": "shared.commands.done_label",
  "signature": "def done_label(command: str) -> str",
  "language": "python",
  "start_line": 47,
  "end_line": 48,
  "symbol_start_line": 47,
  "symbol_end_line": 48,
  "source": "    47\tdef done_label(command: str) -> str:\n    48\t    return f\"{DONE_PREFIX}{command}\"",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 8.08,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 1632
  }
}

## Ход 18 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/commands.py::failed_label"
}
```

**Ответ:**

{
  "symbol_id": "shared/commands.py::failed_label",
  "file": "shared/commands.py",
  "name": "failed_label",
  "kind": "function",
  "qualified_name": "shared.commands.failed_label",
  "signature": "def failed_label(command: str) -> str",
  "language": "python",
  "start_line": 51,
  "end_line": 52,
  "symbol_start_line": 51,
  "symbol_end_line": 52,
  "source": "    51\tdef failed_label(command: str) -> str:\n    52\t    return f\"{FAILED_PREFIX}{command}\"",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 27.84,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 1632
  }
}

## Ход 19 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/commands.py::running_labels"
}
```

**Ответ:**

{
  "symbol_id": "shared/commands.py::running_labels",
  "file": "shared/commands.py",
  "name": "running_labels",
  "kind": "function",
  "qualified_name": "shared.commands.running_labels",
  "signature": "def running_labels(command: str) -> tuple[str, ...]",
  "language": "python",
  "start_line": 55,
  "end_line": 57,
  "symbol_start_line": 55,
  "symbol_end_line": 57,
  "source": "    55\tdef running_labels(command: str) -> tuple[str, ...]:\n    56\t    \"\"\"Все метки «прогон идёт» для команды — их снимает финализация.\"\"\"\n    57\t    return (run_label(command),) + _LEGACY_RUNNING_LABELS.get(command, ())",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.44,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 1632
  }
}

## Ход 20 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::_run_staged_analysis"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::_run_staged_analysis",
  "file": "worker/workflows.py",
  "name": "_run_staged_analysis",
  "kind": "function",
  "qualified_name": "worker.workflows._run_staged_analysis",
  "signature": "async def _run_staged_analysis(analyze: AnalyzeInput) -> bool",
  "language": "python",
  "start_line": 110,
  "end_line": 203,
  "symbol_start_line": 110,
  "symbol_end_line": 203,
  "source": "   110\tasync def _run_staged_analysis(analyze: AnalyzeInput) -> bool:\n   111\t    \"\"\"Пер-стадийный прогон FNR — общий для обоих входов в аналитику.\n   112\t\n   113\t    Один код на команду `/analyze` (IssueAnalysis) и на лейбл research-me внутри\n   114\t    IssueLifecycle. Раньше вторая ветка звала монолитную activity\n   115\t    run_analysis_pipeline: те же пять стадий, но одним чёрным ящиком — застрявшая\n   116\t    стадия не называла себя, а прогон по лейблу и прогон по команде расходились\n   117\t    в поведении, оставаясь «одной и той же аналитикой» на словах.\n   118\t\n   119\t    Каждая стадия — свой шаг Event History со своим таймингом; ретраев нет\n   120\t    (прогон недетерминирован, мутирует файлы и стоит денег — повтор инициирует\n   121\t    человек), сбой всегда доезжает до GitHub, каталог снимается на обоих путях.\n   122\t\n   123\t    Возвращает True, если артефакты опубликованы: от этого зависит, можно ли\n   124\t    передавать задачу разработчику — без аналитики передавать нечего.\n   125\t    \"\"\"\n   126\t    ok = True\n   127\t    try:\n   128\t        await workflow.execute_activity(\n   129\t            activities.prepare_workspace,\n   130\t            analyze,\n   131\t            start_to_close_timeout=timedelta(seconds=1000),  # clone 300 + repomix 600 + буфер\n   132\t            heartbeat_timeout=timedelta(seconds=300),\n   133\t            retry_policy=RetryPolicy(maximum_attempts=2),\n   134\t        )\n   135\t        for stage_name in activities.FNR_STAGE_NAMES:\n   136\t            await workflow.execute_activity(\n   137\t                activities.run_fnr_stage,\n   138\t                args=[analyze, stage_name],\n   139\t                start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n   140\t                heartbeat_timeout=timedelta(seconds=300),\n   141\t                # Сбой самой стадии не повторяется: прогон недетерминирован,\n   142\t                # мутирует файлы и стоит денег — повтор инициирует человек. Но\n   143\t                # heartbeat timeout не её сбой: воркер перезапустили (выкладкой,\n   144\t                # рестартом Docker), активность оборвалась, и ничего произведено\n   145\t                # не было. Без второй попытки любая выкладка посреди прогона\n   146\t                # убивала анализ целиком — так встал Issue #11 на стенде.\n   147\t                #\n   148\t                # Граница по типу: всё, что стадия поднимает сама, — RuntimeError.\n   149\t                # Таймауты и потеря воркера в этот тип не попадают.\n   150\t                retry_policy=RetryPolicy(\n   151\t                    maximum_attempts=2,\n   152\t                    non_retryable_error_types=[\"RuntimeError\"],\n   153\t                ),\n   154\t            )\n   155\t        await workflow.execute_activity(\n   156\t            activities.publish_analysis,\n   157\t            analyze,\n   158\t            start_to_close_timeout=timedelta(seconds=120),\n   159\t            retry_policy=RetryPolicy(maximum_attempts=3),\n   160\t        )\n   161\t        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=True)\n   162\t    except Exception as exc:\n   163\t        ok = False\n   164\t        # exc — ActivityError с общим текстом; настоящая причина в exc.cause\n   165\t        # (например, «стадия concept: артефакт ... не создан»). Разворачиваем.\n   166\t        reason = str(getattr(exc, \"cause\", None) or exc)\n   167\t        # Сначала спасаем сделанное, потом сообщаем о сбое: `cleanup` в\n   168\t        # `finally` снимет каталог, и после него публиковать будет нечего.\n   169\t        saved = []\n   170\t        try:\n   171\t            saved = await workflow.execute_activity(\n   172\t                activities.publish_analysis_partial,\n   173\t                args=[analyze, reason[:300]],\n   174\t                start_to_close_timeout=timedelta(seconds=300),\n   175\t                retry_policy=RetryPolicy(maximum_attempts=2),\n   176\t            )\n   177\t        except Exception as partial_exc:\n   178\t            workflow.logger.warning(\n   179\t                \"публикация частичного анализа не удалась: %s\", partial_exc)\n   180\t        if not saved:\n   181\t            await workflow.execute_activity(\n   182\t                activities.publish_analysis_error,\n   183\t                args=[analyze, reason[:500]],\n   184\t                start_to_close_timeout=timedelta(seconds=60),\n   185\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   186\t            )\n   187\t        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=False)\n   188\t    finally:\n   189\t        # Каталог живёт вне Temporal — снимаем его на обоих путях. Best-effort:\n   190\t        # провал самой уборки (timeout/краш воркера) не должен затирать реальный\n   191\t        # исход — ловим и логируем, но наружу не пробрасываем.\n   192\t        try:\n   193\t            await workflow.execute_activity(\n   194\t                activities.cleanup_workspace,\n   195\t                analyze,\n   196\t                start_to_close_timeout=timedelta(seconds=60),\n   197\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   198\t            )\n   199\t        except Exception as cleanup_exc:\n   200\t            workflow.logger.warning(\n   201\t                \"cleanup_workspace failed (best-effort, ignored): %s\", cleanup_exc\n   202\t            )\n   203\t    return ok",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 17.84,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 21 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "FNR_STAGE_NAMES task concept debate sysreq validate",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::FNR_STAGE_NAMES",
      "name": "FNR_STAGE_NAMES",
      "kind": "constant",
      "file": "worker/activities.py",
      "start_line": 789,
      "end_line": 789,
      "signature": "FNR_STAGE_NAMES = (REPOWISE_STAGE, \"task\", \"concept\", \"debate\", \"sysreq\", \"validate\")",
      "qualified_name": "worker.activities.FNR_STAGE_NAMES",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_analysis_pipeline.py::test_fnr_stage_names_are_the_six_stages",
      "name": "test_fnr_stage_names_are_the_six_stages",
      "kind": "function",
      "file": "tests/test_analysis_pipeline.py",
      "start_line": 108,
      "end_line": 110,
      "signature": "def test_fnr_stage_names_are_the_six_stages()",
      "qualified_name": "tests.test_analysis_pipeline.test_fnr_stage_names_are_the_six_stages",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueBft::stage",
      "name": "stage",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2074,
      "end_line": 2081,
      "signature": "def stage(self) -> str",
      "qualified_name": "worker.workflows.IssueBft.stage",
      "language": "python",
      "score": 50.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::stage",
      "name": "stage",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 377,
      "end_line": 388,
      "signature": "def stage(self) -> str",
      "qualified_name": "worker.workflows.IssueLifecycle.stage",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_e2e_issue_lifecycle.py::_Harness::stage",
      "name": "stage",
      "kind": "method",
      "file": "tests/test_e2e_issue_lifecycle.py",
      "start_line": 304,
      "end_line": 305,
      "signature": "async def stage(self, wf_id: str) -> str",
      "qualified_name": "tests.test_e2e_issue_lifecycle._Harness.stage",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.decompose_issue",
      "page_type": "symbol_spotlight",
      "snippet": "e.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/t",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::decompose_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Key Concepts",
      "page_type": "onboarding",
      "snippet": "# Key Concepts\n\nThe types and functions the rest of `poh-issue-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanati",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/key_concepts",
      "type": "page"
    },
    {
      "title": "File: shared/decomposition.py",
      "page_type": "file_page",
      "snippet": "lease: str) -> str |\n| `normalize_release` | function | def normalize_release(raw: str) -> str |\n| `validate` | function | def validate(items: list[dict]) -> list[dict] |\n| `group` | function | def gr",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "shared/decomposition.py",
      "type": "page"
    },
    {
      "title": "Application Webhook",
      "page_type": "module_page",
      "snippet": "here, not why it is that\nway. Add an API key and run `repowise generate` to have that written.*\n\n## Concept index\n\nWhat the prose above calls things, the identifier to search for, and where it lives.",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "webhook",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.compute_estimate",
      "page_type": "symbol_spotlight",
      "snippet": "e.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/t",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::compute_estimate",
      "file": "worker/activities.py",
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
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_analysis_pipeline.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "tests/test_e2e_issue_lifecycle.py"
    },
    {
      "path": "shared/decomposition.py"
    }
  ],
  "exact_match": true
}

## Ход 22 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/lifecycle.py"
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
        "last_fix_days_ago": 0
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
        "text": "\"\"\"Модель фаз жизненного цикла Issue — единственный источник правды.\n\nСегодня состояние Issue размазано по четырём независимым представлениям (метки,\nпеременные воркфлоу, комментарии, Event History), и ни одно не покрывает путь\nдальше приоритизации. Этот модуль вводит один перечень фаз и одну таблицу\nпереходов; из них выводятся значения query, метки в GitHub, search attribute и\nстроки таймлайна. Иначе каждая подзадача эпика заведёт свои названия, и\nтрассировка будет собирать таймлайн из несовместимых кусков.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как `estimation.py`.\nЛогика состояний проверяется напрямую, а не через прогон воркфлоу.\n\nИменование согласовано с уже внедрёнными словарями: namespace через двоеточие,\nкак `needs-human:*` и `run:*`/`done:*` (протокол агентов v1, задачи #30 и #33).\nФаза в GitHub — метка `phase:<имя>`.\n\"\"\"\n\nfrom dataclasses import dataclass\n\n# --- Основной путь: от создания до прода ---\n\nCREATED = \"created\"\nCLASSIFIED = \"classified\"\nBUSINESS_ANALYSIS = \"business-analysis\"\nSYSTEM_REQUIREMENTS = \"system-requirements\"\nGROOMED = \"groomed\"\nREADY_FOR_DEV = \"ready-for-dev\"\nIN_DEVELOPMENT = \"in-development\"\nPR_OPEN = \"pr-open\"\nPR_REVIEW = \"pr-review\"\nMERGED = \"merged\"\nTESTING = \"testing\"\nRELEASED = \"released\"\n\n# --- Боковые состояния: сегодня существуют де-факто, но нигде не названы ---\n\nSPAM = \"spam\"                # intake gate распознал спам, issue закрыт\nDUPLICATE = \"duplicate\"      # дубликат: решение о закрытии за человеком\nANSWERED = \"answered\"        # классификация закрыла содержательным ответом\nSKIPPED = \"skipped\"          # предфильтр: бот или security-sensitive\nESCALATED = \"escalated\"      # ушло человеку (needs-human:*)\nFAILED = \"failed\"            # стадия сорвалась, нужен разбор\nCANCELLED = \"cancelled\"      # снято с обработки решением человека\n\n# Кто инициирует переход. Различать обязательно: «ждём агента» и «ждём человека» —\n# это разные состояния для того, кто смотрит на очередь.\nAGENT = \"agent\"        # сам Issue-Agent по завершении своей стадии\nHUMAN = \"human\"        # метка или команда человека\nEXTERNAL = \"external\"  # PR-Agent, PR-Closer, CI — внешняя система контура\n\n\n@dataclass(frozen=True)\nclass Transition:\n    ... 8 lines (54-61)\nTERMINAL = frozenset({RELEASED, CANCELLED})\n... 7 lines (63-69)\nTRANSITIONS: dict[str, tuple[Transition, ...]] = {\n    CREATED: (\n        Transition(CLASSIFIED, AGENT, \"триаж завершён\"),\n        Transition(SKIPPED, AGENT, \"предфильтр: бот или security-sensitive\"),\n        Transition(SPAM, AGENT, \"intake gate: спам\"),\n        # Дедуп и advisor-ответ — шаги ВНУТРИ триажа, поэтому их исход виден из\n        # `created`, а не только из `classified`: до конца триажа Issue ещё не\n        # классифицирован формально.\n        Transition(DUPLICATE, AGENT, \"duplicate-check\"),\n        Transition(ANSWERED, AGENT, \"advisor:consultation / existing-functionality\"),\n        Transition(ESCALATED, AGENT, \"не удалось сузить запрос\"),\n        Transition(FAILED, AGENT, \"сбой стадии\"),\n        ... 129 lines (82-210)\n\nPHASES: tuple[str, ...] = tuple(TRANSITIONS)\n\n# Метка фазы в GitHub. Инвариант: одна фаза — ровно одна метка `phase:*`, при\n# переходе предыдущая снимается. Без этого по меткам нельзя восстановить\n# состояние: два `phase:*` на Issue означали бы противоречие, а не историю.\nPHASE_PREFIX = \"phase:\"\n\n# Мост от значений query `stage` (#29) к фазам. Нужен на время перехода: пока\n# `IssueLifecycle` линейный (#36 ещё не сделана), стадия — единственное, что\n# воркфлоу знает о себе.\nSTAGE_TO_PHASE: dict[str, str] = {\n    \"intake\": CREATED,\n    \"classify\": CREATED,\n    \"duplicate-check\": CLASSIFIED,\n    \"priority\": CLASSIFIED,\n    \"awaiting-human-decision\": CLASSIFIED,\n    \"analysis\": BUSINESS_ANALYSIS,\n    \"bug\": READY_FOR_DEV,\n    \"awaiting-build-decision\": READY_FOR_DEV,\n    \"done\": READY_FOR_DEV,\n    \"skipped\": SKIPPED,\n    \"spam\": SPAM,\n    ... 17 lines (234-250)\n\n\nclass InvalidTransition(ValueError):\n    \"\"\"Недопустимый переход — ошибка, а не молчаливая перезапись фазы.\n\n    Молчаливая запись любой фазы поверх любой означала бы, что модель ничего не\n    гарантирует: Issue оказывался бы в состоянии, из которого не выводится ни\n    предыстория, ни следующий шаг.\n    \"\"\"\n\n\ndef phase_label(phase: str) -> str:\n    return f\"{PHASE_PREFIX}{phase}\"\n\n\ndef phase_from_labels(labels: list[str]) -> str | None:\n    \"\"\"Фаза по набору меток Issue, иначе None.\n\n    Инвариант «одна фаза — одна метка» проверяется здесь же: две метки `phase:*`\n    означают противоречие, и мы отказываемся угадывать, какая из них настоящая.\n    \"\"\"\n    found = [name[len(PHASE_PREFIX):].lower() for name in labels\n             if name.lower().startswith(PHASE_PREFIX)]\n    known = [name for name in found if name in TRANSITIONS]\n    if len(known) != 1:\n        return None\n    return known[0]\n\n\ndef is_terminal(phase: str) -> bool:\n    return phase in TERMINAL\n\n\ndef allowed(phase: str) -> tuple[Transition, ...]:\n    \"\"\"Переходы, возможные из фазы. Неизвестная фаза — ошибка модели.\"\"\"\n    ... 3 lines (286-288)\n\n\ndef can(source: str, target: str) -> bool:\n    return any(t.to == target for t in allowed(source))\n\n\ndef transition(source: str, target: str) -> Transition:\n    \"\"\"Переход или InvalidTransition с перечнем допустимых — сообщение должно\n    само говорить, что было возможно вместо этого.\"\"\"\n    for candidate in allowed(source):\n        if candidate.to == target:\n            return candidate\n    options = \", \".join(t.to for t in allowed(source)) or \"—\"\n    raise InvalidTransition(\n        f\"переход {source} → {target} не предусмотрен; допустимо: {options}\")\n\n\ndef initiator(source: str, target: str) -> str:\n    return transition(source, target).initiator\n\n\ndef reachable_from(start: str = CREATED) -> set[str]:\n    \"\"\"Фазы, достижимые из start. Используется тестом полноты: фаза, до которой\n    ... 10 lines (312-321)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 41.8% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 76.47,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 23 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "analyze_requested signal command IssueLifecycle",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested",
      "name": "analyze_requested",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 469,
      "end_line": 523,
      "signature": "async def analyze_requested(self, comment_id: int | None) -> None",
      "qualified_name": "worker.workflows.IssueLifecycle.analyze_requested",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::ANALYZE",
      "name": "ANALYZE",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 20,
      "end_line": 20,
      "signature": "ANALYZE = \"analyze\"",
      "qualified_name": "shared.commands.ANALYZE",
      "language": "python",
      "score": 47.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 42.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_bft_workflow.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_bft_workflow.ISSUE",
      "language": "python",
      "score": 42.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_analysis_requested",
      "name": "_analysis_requested",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 955,
      "end_line": 975,
      "signature": "async def _analysis_requested(self, issue: IssueInput) -> tuple",
      "qualified_name": "worker.workflows.IssueLifecycle._analysis_requested",
      "language": "python",
      "score": 22.52,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.analyze_requested",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.analyze_requested\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 5\n\n```\nasync def analyze_requested(self, comment_id: i",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::analyze_requested",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueLifecycle\n```\n\n## Overview\n\n`IssueLifecycle` is a class defined",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueLifecycle",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifecycle` о них\nне знал и вешал косметическую метку.\n\nРежим выбирает ОДНА функция, а не каждый",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.agent_event",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.agent_event\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 4\n\n```\nasync def agent_event(self, event: AgentEvent) -> Non",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::agent_event",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": "viour.\n\n## Shape`poh-issue-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `webhook/main.py`\n\n- `.claude/skills/b",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
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
      "path": "shared/commands.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_bft_workflow.py"
    },
    {
      "path": "shared/agent_launcher.py"
    }
  ],
  "exact_match": true
}

## Ход 24 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested",
  "file": "worker/workflows.py",
  "name": "analyze_requested",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle.analyze_requested",
  "signature": "async def analyze_requested(self, comment_id: int | None) -> None",
  "language": "python",
  "start_line": 469,
  "end_line": 523,
  "symbol_start_line": 469,
  "symbol_end_line": 523,
  "source": "   469\t    async def analyze_requested(self, comment_id: int | None) -> None:\n   470\t        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n   471\t\n   472\t        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а\n   473\t        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).\n   474\t        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу\n   475\t        из вебхука — связь между циклом Issue и работой агента была\n   476\t        декоративной, о чём и говорил прежний докстринг.\n   477\t\n   478\t        Тяжёлую работу из самого хендлера не запускаем: run() обычно\n   479\t        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с\n   480\t        основным циклом за фазу. Очередь снимает гонку — решение принимает та\n   481\t        фаза, в которой Issue находится сейчас.\n   482\t\n   483\t        Сигнал может прийти в самой первой активации воркфлоу — раньше, чем\n   484\t        run() выполнил `self._issue = issue` (Temporal применяет сигналы до\n   485\t        создания задачи run()); поэтому ЖДЁМ инициализацию через\n   486\t        wait_condition, а не теряем запрос молча по `self._issue is None`.\n   487\t        \"\"\"\n   488\t        # Тот же маркер, что разводит поколения в run(): цикл и дочерние\n   489\t        # агенты приехали вместе, и прогон, не знающий одного, не знает и\n   490\t        # другого. Прежнее поколение обязано доиграть ПРЕЖНИМ кодом хендлера —\n   491\t        # иначе реплей его истории упрётся в несовпадение команд.\n   492\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   493\t            if self._analyze_labeled:\n   494\t                return\n   495\t            self._analyze_labeled = True\n   496\t            await workflow.wait_condition(lambda: self._issue is not None)\n   497\t            await workflow.execute_activity(\n   498\t                activities.mark_analyzing,\n   499\t                args=[self._issue.repo, self._issue.issue_number],\n   500\t                start_to_close_timeout=timedelta(seconds=30),\n   501\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   502\t            )\n   503\t            return\n   504\t\n   505\t        # Запрос уже в очереди — второй прогон был бы шумом и деньгами:\n   506\t        # повторная команда и дубль webhook-доставки означают одно намерение.\n   507\t        # Флаг ставим ДО первого await: хендлеры кооперативны (переключение\n   508\t        # только на await), поэтому почти одновременный второй сигнал увидит\n   509\t        # True. Идентификатор занятого прогона от этой гонки не спасает: к\n   510\t        # моменту второго сигнала первый может уже завершиться, и id\n   511\t        # освободится — а это законный повторный запуск, не дубль.\n   512\t        # Идущий прогон — тоже причина отказать. Пока он идёт, `ack_command`\n   513\t        # вешает на Issue метку `run:analyze`; вебхук видит `issues.labeled` и\n   514\t        # шлёт команду обратно в цикл. Своя метка возвращается как новая\n   515\t        # команда, и на живом стенде это давало три прогона подряд по одному\n   516\t        # Issue. Идентификатор занятого прогона от этого не спасает: к моменту\n   517\t        # разбора очереди первый прогон уже завершён, и id свободен.\n   518\t        if self._analyze_pending or self._analysis_running:\n   519\t            return\n   520\t        self._analyze_pending = True\n   521\t        self._analyze_comment_id = comment_id\n   522\t        await workflow.wait_condition(lambda: self._issue is not None)\n   523\t        await self._signal_queue.put(AGENT_ANALYZE)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.83,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 25 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "AGENT_ANALYZE signal_queue agent_event",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_agent_comment.py::_Handle::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_agent_comment.py",
      "start_line": 112,
      "end_line": 116,
      "signature": "async def signal(self, name, *args, **kwargs)",
      "qualified_name": "tests.test_agent_comment._Handle.signal",
      "language": "python",
      "score": 47.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::ANALYZE",
      "name": "ANALYZE",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 20,
      "end_line": 20,
      "signature": "ANALYZE = \"analyze\"",
      "qualified_name": "shared.commands.ANALYZE",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::AGENT",
      "name": "AGENT",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 47,
      "end_line": 47,
      "signature": "AGENT = \"agent\"",
      "qualified_name": "shared.lifecycle.AGENT",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_webhook.py::FakeHandle::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_bft_webhook.py",
      "start_line": 42,
      "end_line": 43,
      "signature": "async def signal(self, name, arg=None)",
      "qualified_name": "tests.test_bft_webhook.FakeHandle.signal",
      "language": "python",
      "score": 41.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_e2e_issue_lifecycle.py::_Harness::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_e2e_issue_lifecycle.py",
      "start_line": 307,
      "end_line": 309,
      "signature": "async def signal(self, wf_id: str, label: str)",
      "qualified_name": "tests.test_e2e_issue_lifecycle._Harness.signal",
      "language": "python",
      "score": 41.01,
      "next": "get_symbol"
    },
    {
      "title": "File: worker/workflows.py",
      "page_type": "file_page",
      "snippet": "TION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `CLOSED` | constant | CLOSED = \"",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.analyze_requested",
      "page_type": "symbol_spotlight",
      "snippet": "module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `t",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::analyze_requested",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.agent_event",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.agent_event\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 4\n\n```\nasync def agent_event(self, event: AgentEvent) -> Non",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::agent_event",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle",
      "page_type": "symbol_spotlight",
      "snippet": "module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `t",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueLifecycle",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.__init__",
      "page_type": "symbol_spotlight",
      "snippet": "module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `t",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::__init__",
      "file": "worker/workflows.py",
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
      "path": "tests/test_agent_comment.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "tests/test_bft_webhook.py"
    },
    {
      "path": "tests/test_e2e_issue_lifecycle.py"
    },
    {
      "path": "worker/workflows.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'AGENT_ANALYZE', 'signal_queue', 'agent_event'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 26 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "AGENT_ANALYZE = \"__agent__:analyze\"",
  "repo": "poh-issue-agents",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::ANALYZE",
      "name": "ANALYZE",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 20,
      "end_line": 20,
      "signature": "ANALYZE = \"analyze\"",
      "qualified_name": "shared.commands.ANALYZE",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::AGENT",
      "name": "AGENT",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 47,
      "end_line": 47,
      "signature": "AGENT = \"agent\"",
      "qualified_name": "shared.lifecycle.AGENT",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::AGENT_ANALYZE",
      "name": "AGENT_ANALYZE",
      "kind": "constant",
      "file": "worker/workflows.py",
      "start_line": 73,
      "end_line": 73,
      "signature": "AGENT_ANALYZE = \"__agent__:analyze\"",
      "qualified_name": "worker.workflows.AGENT_ANALYZE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agent_launcher.py::_analyze",
      "name": "_analyze",
      "kind": "function",
      "file": "tests/test_agent_launcher.py",
      "start_line": 64,
      "end_line": 66,
      "signature": "def _analyze(comment_id: int | None = 555) -> AnalyzeInput",
      "qualified_name": "tests.test_agent_launcher._analyze",
      "language": "python",
      "score": 45.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::AnalyzeInput",
      "name": "AnalyzeInput",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 224,
      "end_line": 233,
      "signature": "class AnalyzeInput",
      "qualified_name": "shared.workflow_types.AnalyzeInput",
      "language": "python",
      "score": 15.3,
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
      "path": "shared/commands.py"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "tests/test_agent_launcher.py"
    },
    {
      "path": "shared/workflow_types.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'AGENT_ANALYZE = \"__agent__:analyze\"'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 27 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueLifecycle::agent_event"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::agent_event",
  "file": "worker/workflows.py",
  "name": "agent_event",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle.agent_event",
  "signature": "async def agent_event(self, event: AgentEvent) -> None",
  "language": "python",
  "start_line": 526,
  "end_line": 550,
  "symbol_start_line": 526,
  "symbol_end_line": 550,
  "source": "   526\t    async def agent_event(self, event: AgentEvent) -> None:\n   527\t        \"\"\"Факт от внешнего агента контура: PR открыт, ревью взято, CI упал (#38).\n   528\t\n   529\t        Кладём в общую очередь, а не двигаем фазу прямо здесь. Обработчик\n   530\t        сигнала конкурирует с основным циклом: пока тот, скажем, гонит\n   531\t        аналитику, смена фазы из-под него дала бы состояние, которого нет ни в\n   532\t        одном обработчике. Очередь снимает гонку — событие разбирает та фаза, в\n   533\t        которой Issue находится сейчас.\n   534\t\n   535\t        Идемпотентность по паре `(ref, status)`: доставку соседний сервис может\n   536\t        повторить (ретрай, дубль вебхука), но один факт обязан двигать фазу\n   537\t        один раз. Ключи копятся в состоянии прогона, поэтому храним только\n   538\t        последние: цикл живёт месяцами, а сюда попадает каждое событие по\n   539\t        каждому PR.\n   540\t        \"\"\"\n   541\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   542\t            return  # прежнее поколение фаз не знает — двигать нечего\n   543\t        if isinstance(event, dict):\n   544\t            event = AgentEvent(**event)\n   545\t        if event.key() in self._seen_agent_events:\n   546\t            return\n   547\t        self._seen_agent_events.append(event.key())\n   548\t        del self._seen_agent_events[:-SEEN_EVENTS_KEPT]\n   549\t        await workflow.wait_condition(lambda: self._issue is not None)\n   550\t        await self._signal_queue.put(event)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 15.29,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 28 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "query": "signal_queue.get _wait_for_signal IssueLifecycle run",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_e2e_issue_lifecycle.py::_Harness::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_e2e_issue_lifecycle.py",
      "start_line": 307,
      "end_line": 309,
      "signature": "async def signal(self, wf_id: str, label: str)",
      "qualified_name": "tests.test_e2e_issue_lifecycle._Harness.signal",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_e2e_issue_lifecycle.py::_Harness::wait",
      "name": "wait",
      "kind": "method",
      "file": "tests/test_e2e_issue_lifecycle.py",
      "start_line": 301,
      "end_line": 302,
      "signature": "async def wait(self, wf_id: str)",
      "qualified_name": "tests.test_e2e_issue_lifecycle._Harness.wait",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_webhook_issue_closed.py::FakeHandle::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_webhook_issue_closed.py",
      "start_line": 28,
      "end_line": 31,
      "signature": "async def signal(self, name, *args)",
      "qualified_name": "tests.test_webhook_issue_closed.FakeHandle.signal",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agent_comment.py::_Handle::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_agent_comment.py",
      "start_line": 112,
      "end_line": 116,
      "signature": "async def signal(self, name, *args, **kwargs)",
      "qualified_name": "tests.test_agent_comment._Handle.signal",
      "language": "python",
      "score": 40.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 40.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.analyze_requested",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.analyze_requested\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 5\n\n```\nasync def analyze_requested(self, comment_id: i",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::analyze_requested",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueLifecycle\n```\n\n## Overview\n\n`IssueLifecycle` is a class defined",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueLifecycle",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.agent_event",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.agent_event\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 4\n\n```\nasync def agent_event(self, event: AgentEvent) -> Non",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::agent_event",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.__init__",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.__init__\n\n**Kind:** method | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\ndef __init__(self) -> None\n```\n\n## Overview\n\n`__init__` is a met",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::__init__",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifecycle` о них\nне знал и вешал косметическую метку.\n\nРежим выбирает ОДНА функция, а не каждый",
      "relevance_score": 2.769,
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
      "path": "tests/test_e2e_issue_lifecycle.py"
    },
    {
      "path": "tests/test_webhook_issue_closed.py"
    },
    {
      "path": "tests/test_agent_comment.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/agent_launcher.py"
    }
  ],
  "exact_match": true
}

## Ход 29 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "IssueLifecycle::run signal_queue",
  "repo": "poh-issue-agents",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 653,
      "end_line": 705,
      "signature": "async def run(self, issue: IssueInput,\n                  carried: LifecycleState | None = None) -> None",
      "qualified_name": "worker.workflows.IssueLifecycle.run",
      "language": "python",
      "score": 58.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_e2e_issue_lifecycle.py::_Harness::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_e2e_issue_lifecycle.py",
      "start_line": 307,
      "end_line": 309,
      "signature": "async def signal(self, wf_id: str, label: str)",
      "qualified_name": "tests.test_e2e_issue_lifecycle._Harness.signal",
      "language": "python",
      "score": 53.01,
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
      "score": 52.02,
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
      "score": 52.01,
      "next": "get_symbol"
    },
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
      "path": "tests/test_e2e_issue_lifecycle.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'IssueLifecycle::run signal_queue'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 30 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueLifecycle::run"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::run",
  "file": "worker/workflows.py",
  "name": "run",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle.run",
  "signature": "async def run(self, issue: IssueInput,\n                  carried: LifecycleState | None = None) -> None",
  "language": "python",
  "start_line": 653,
  "end_line": 705,
  "symbol_start_line": 653,
  "symbol_end_line": 705,
  "source": "   653\t    async def run(self, issue: IssueInput,\n   654\t                  carried: LifecycleState | None = None) -> None:\n   655\t        \"\"\"Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n   656\t        ожидание, а не заканчивается после приоритизации.\n   657\t\n   658\t        Второй аргумент со значением по умолчанию — ради совместимости: вебхук и\n   659\t        скрипты стартуют воркфлоу одним аргументом, как раньше, а continue-as-new\n   660\t        передаёт снимок состояния вторым.\n   661\t\n   662\t        `workflow.patched` разводит поколения. Прогоны, запущенные до этого\n   663\t        изменения, припаркованы в проде: их история не знает маркера, patched()\n   664\t        вернёт False, и они доиграют по прежнему линейному коду. Новые пойдут\n   665\t        циклом. Без этого реплей старой истории новым кодом упал бы\n   666\t        недетерминизмом — самый дорогой класс отказа в Temporal.\n   667\t        \"\"\"\n   668\t        # Вебхук и скрипты стартуют воркфлоу ОДНИМ аргументом, а сигнатура\n   669\t        # объявляет два. При таком расхождении Temporal не применяет типы ни к\n   670\t        # одному аргументу и отдаёт сырые словари — молча, на первом же\n   671\t        # обращении к полю. Нормализуем сами: ломать существующие стартеры ради\n   672\t        # красоты сигнатуры нельзя, а второй аргумент нужен continue-as-new.\n   673\t        if isinstance(issue, dict):\n   674\t            issue = IssueInput(**issue)\n   675\t        if isinstance(carried, dict):\n   676\t            carried = LifecycleState(**carried)\n   677\t\n   678\t        self._issue = issue  # даёт analyze_requested доступ к repo/number\n   679\t        # Момент входа в фазу. `workflow.now()` детерминирован (время события из\n   680\t        # истории), поэтому реплей даёт то же значение, что и первый прогон.\n   681\t        self._phase_since = workflow.now()\n   682\t        if carried is not None:\n   683\t            self._phase = carried.phase\n   684\t            self._stage = carried.stage\n   685\t            self._priority_tier = carried.priority_tier\n   686\t            self._classification_label = carried.classification_label\n   687\t            self._analysis_done = carried.analysis_done\n   688\t            self._plan_member = carried.plan_member\n   689\t            self._root_issue = carried.root_issue\n   690\t            self._pr_number = carried.pr_number\n   691\t            self._clarify_rounds = carried.clarify_rounds\n   692\t            self._followup_rounds = carried.followup_rounds\n   693\t            self._answered_comment_ids = list(carried.answered_comment_ids)\n   694\t            self._generation = carried.generation\n   695\t            if carried.phase_since_epoch:\n   696\t                # Перезапуск цикла не должен обнулять срок парковки: иначе\n   697\t                # continue-as-new сам стал бы способом ждать вечно.\n   698\t                self._phase_since = datetime.fromtimestamp(\n   699\t                    carried.phase_since_epoch, tz=timezone.utc)\n   700\t\n   701\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   702\t            await self._run_linear(issue)\n   703\t            return\n   704\t        self._phase_driven = True\n   705\t        await self._run_phase_loop(issue)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 13.9,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 31 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "mode": "symbol",
  "query": "_run_phase_loop signal_queue",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_lifecycle_loop.py::_LegacyLifecycle::run",
      "name": "run",
      "kind": "method",
      "file": "tests/test_lifecycle_loop.py",
      "start_line": 387,
      "end_line": 389,
      "signature": "async def run(self, issue: IssueInput) -> None",
      "qualified_name": "tests.test_lifecycle_loop._LegacyLifecycle.run",
      "language": "python",
      "score": 47.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::phase",
      "name": "phase",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 391,
      "end_line": 401,
      "signature": "def phase(self) -> str",
      "qualified_name": "worker.workflows.IssueLifecycle.phase",
      "language": "python",
      "score": 46.02,
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
      "path": "tests/test_lifecycle_loop.py"
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
  "exact_match": false,
  "note": "No indexed symbol exactly matches '_run_phase_loop signal_queue'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 32 · `get_context` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
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
        "last_fix_days_ago": 0,
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
        "tokens": 3100,
        "full_tokens": 28256,
        "pct_of_full": 11.0,
        "bodies_kept": [],
        "text": "\"\"\"\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\"\"\"\n\nimport asyncio\nfrom datetime import datetime, timedelta, timezone\n\nfrom temporalio import workflow\nfrom temporalio.common import RetryPolicy\nfrom temporalio.exceptions import WorkflowAlreadyStartedError\nfrom temporalio.workflow import ParentClosePolicy\n\nwith workflow.unsafe.imports_passed_through():\n    from shared import bft, lifecycle\n    from shared.commands import ANALYZE, BFT, BFT_DEEP, ESTIMATE\n    from shared.workflow_ids import (\n        analysis_workflow_id,\n        bft_workflow_id,\n        estimate_workflow_id,\n    )\n    from shared import agent_events, awaiting as awaiting_mod\n    from shared.agent_events import AgentEvent\n    from shared.awaiting import Awaiting\n    from shared.workflow_types import (\n        AnalyzeInput,\n        BftRequest,\n        ClassificationResult,\n        CommentAckInput,\n        Deadlines,\n        EstimateRequest,\n        EstimateResult,\n        IssueInput,\n        LifecycleState,\n        OrphanEventInput,\n        UserComment,\n        WebhookAuditInput,\n    )\n\n    import activities\n\n# Прогон БФТ, запущенный самим триажем, а не человеком. Отличается тем, что не\n# трогает метки команды: помечать `run:bft` нечего — команды не было, а метка\n# вернулась бы вебхуком как новая.\nBFT_TRIAGE = \"triage\"\n\nMAX_CLARIFICATION_ROUNDS = 2\n... 7 lines (61-67)\nMAX_ANALYSIS_CLARIFY_ROUNDS = 2\n\n# Запрос на прогон аналитики, доставленный в общую очередь сигналов. Та же\n# схема, что у реплики человека (`UserComment`): одна очередь, разные виды\n# событий, и обработчик фазы решает, что с ними делать.\nAGENT_ANALYZE = \"__agent__:analyze\"\n\n# Issue закрыт на GitHub. Тот же приём: сигнал будит парковку, а решение\n# принимает цикл — иначе обработчику каждой фазы пришлось бы знать про закрытие.\nCLOSED = \"__closed__\"\n\n# Сколько ключей событий помнить ради идемпотентности. Цикл живёт месяцами, а\n# событий по одному Issue — десятки: список без потолка рос бы вместе с\n# историей, ровно тем объёмом, который continue-as-new и призван обрывать.\nSEEN_EVENTS_KEPT = 50\n\n# Порог длины истории для continue-as-new. Ниже потолка, на котором уже\n# спотыкалась консолидация (~990 событий): реплей должен укладываться в\n# workflow-task timeout с запасом, а не впритык.\nHISTORY_EVENT_THRESHOLD = 800\n\n\ndef _failure_reason(e: BaseException) -> str:\n    \"\"\"\"ExcType: message\" из ПЕРВОПРИЧИНЫ для тегов/группировки Sentry.\n... 16 lines (92-107)\n\n\nasync def _run_staged_analysis(analyze: AnalyzeInput) -> bool:\n    \"\"\"Пер-стадийный прогон FNR — общий для обоих входов в аналитику.\n... 92 lines (112-203)\n\n\nasync def _agents_off(repo: str, issue_number: int, what: str) -> bool:\n    \"\"\"R4: человек забрал Issue себе — прогон не стартует.\n... 20 lines (208-227)\n\n\nasync def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:\n    \"\"\"Обратный ход меток команды — один вызов на все терминальные ветки.\n... 11 lines (232-242)\n\n\n@workflow.defn(name=\"WebhookAudit\")\nclass WebhookAudit:\n    \"\"\"Надгробие для доставки, отброшенной по конфигу.\n... 11 lines (248-258)\n    async def run(self, audit: WebhookAuditInput) -> str:\n        ... 6 lines (260-265)\n\n\n@workflow.defn(name=\"OrphanAgentEvent\")\nclass OrphanAgentEvent:\n    \"\"\"Надгробие для события агента, не связанного ни с одним Issue.\n... 9 lines (271-279)\n    async def run(self, orphan: OrphanEventInput) -> str:\n        ... 6 lines (281-286)\n\n\n@workflow.defn(name=\"CommentAck\")\nclass CommentAck:\n    \"\"\"Подтверждение приёма комментария — отдельным прогоном, до всего остального.\n... 11 lines (292-302)\n    async def run(self, ack: CommentAckInput) -> None:\n        ... 6 lines (304-309)\n\n\n@workflow.defn(name=\"IssueLifecycle\")\nclass IssueLifecycle:\n    def __init__(self) -> None:\n        ... 60 lines (315-374)\n\n    @workflow.query\n    def stage(self) -> str:\n        \"\"\"Текущая стадия прогона — для Temporal UI (вкладка Queries).\n... 10 lines (379-388)\n\n    @workflow.query\n    def phase(self) -> str:\n        \"\"\"Фаза жизненного цикла — единый словарь на весь контур (#35).\n... 9 lines (393-401)\n\n    @workflow.query\n    def generation(self) -> int:\n        \"\"\"Сколько раз цикл перезапускался через continue-as-new.\n... 7 lines (406-412)\n\n    @workflow.query\n    def awaiting(self) -> Awaiting | None:\n        \"\"\"Чего Issue ждёт: вид, адресат, с какого момента и до какого срока (#39).\n... 6 lines (417-422)\n\n    @workflow.query\n    def handles_agents(self) -> bool:\n        \"\"\"Ведёт ли этот прогон агентов дочерними воркфлоу (#37).\n... 10 lines (427-436)\n\n    @workflow.signal\n    async def human_decision(self, label: str) -> None:\n        await self._signal_queue.put(label)\n\n    @workflow.signal\n    async def user_comment(self, text: str, comment_id: int | None = None) -> None:\n        \"\"\"Реплика человека в Issue.\n... 6 lines (445-450)\n\n    @workflow.signal\n    async def issue_closed(self, who: str | None = None) -> None:\n        \"\"\"Issue закрыт на GitHub — цикл обязан завершиться.\n... 12 lines (455-466)\n\n    @workflow.signal\n    async def analyze_requested(self, comment_id: int | None) -> None:\n        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n... 53 lines (471-523)\n\n    @workflow.signal\n    async def agent_event(self, event: AgentEvent) -> None:\n        \"\"\"Факт от внешнего агента контура: PR открыт, ревью взято, CI упал (#38).\n... 23 lines (528-550)\n\n    @workflow.signal\n    async def bft_requested(self, req: BftRequest) -> None:\n        \"\"\"По Issue запрошен БФТ — командой `/bft`/`/bft-deep` или меткой `run:*`.\n... 21 lines (555-575)\n\n    async def _start_bft(self, req: BftRequest) -> bool:\n        \"\"\"Прогон БФТ по команде — дочерним воркфлоу, без ожидания результата.\n... 23 lines (579-601)\n\n    @workflow.signal\n    async def estimate_requested(self, comment_id: int | None) -> None:\n        \"\"\"По Issue запрошена оценка трудоёмкости.\n... 29 lines (606-634)\n\n    async def _wait_for_signal(\n            self, timeout: timedelta | None = None) -> str | AgentEvent | UserComment | None:\n        ... 13 lines (638-650)\n\n    @workflow.run\n    async def run(self, issue: IssueInput,\n                  carried: LifecycleState | None = None) -> None:\n        \"\"\"Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n        ... 50 lines (656-705)\n\n    # --- Фазовый цикл ---\n\n    def _snapshot(self) -> LifecycleState:\n        \"\"\"Компактное состояние для continue-as-new: фаза и то немногое, что\n        ... 17 lines (711-727)\n\n    def _history_is_long(self) -> bool:\n        \"\"\"Порог по длине истории, а не по числу итераций: цена реплея зависит\n        от событий, а одна фаза может стоить и трёх событий, и трёхсот.\"\"\"\n        return workflow.info().get_current_history_length() >= HISTORY_EVENT_THRESHOLD\n\n    async def _park(self, kind: str, who: str, reason: str, hours: int) -> timedelta:\n        \"\"\"Встать в ожидание: описать его и вернуть срок таймера.\n... 14 lines (736-749)\n\n    async def _publish_awaiting(self) -> None:\n        \"\"\"Отражение ожидания в GitHub: очередь к людям должна быть полной.\n... 22 lines (753-774)\n\n    async def _stop_awaiting(self) -> None:\n        \"\"\"Ожидание снято: описание очищается, метка уходит.\"\"\"\n        ... 4 lines (778-781)\n\n    def _park_timeout(self, hours: int) -> timedelta:\n        \"\"\"Сколько ещё ждать в этой фазе — остаток от срока, а не полный срок.\n... 17 lines (785-801)\n\n    async def _phase_on_close(self) -> tuple[str, str]:\n        \"\"\"Чем закончился путь Issue: слиянием или снятием с обработки.\n... 22 lines (805-826)\n\n    async def _enter(self, phase: str, stage: str, *, write_label: bool = True) -> None:\n        \"\"\"Переход в фазу: проверка допустимости, стадия, метка.\n... 35 lines (830-864)\n\n    async def _run_analysis_child(self, issue: IssueInput,\n                                  trigger: str | None = None) -> bool:\n        \"\"\"Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n... 47 lines (869-915)\n\n    async def _agent_event(self, event: AgentEvent) -> tuple:\n        \"\"\"Факт внешнего агента — переход по той же таблице, что и у своих.\n... 35 lines (919-953)\n\n    async def _analysis_requested(self, issue: IssueInput) -> tuple:\n        \"\"\"Куда ведёт запрос аналитики из ТЕКУЩЕЙ фазы.\n... 19 lines (957-975)\n\n    async def _run_phase_loop(self, issue: IssueInput) -> None:\n        ... 78 lines (978-1055)\n\n    async def _phase_triage(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `created`: тот же триаж, что и раньше, но его исход — фаза.\n... 178 lines (1059-1236)\n\n    async def _bft_on_triage(self, issue: IssueInput) -> None:\n        \"\"\"БФТ как ответ триажа на запрос функционала.\n... 35 lines (1240-1274)\n\n    async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `classified`: ждём решения человека о тяжёлой стадии.\n... 77 lines (1278-1354)\n\n    async def _phase_analysis(self, issue: IssueInput) -> tuple | None:\n        \"\"\"Фаза `business-analysis`: цепочка FNR дочерним прогоном.\n... 10 lines (1358-1367)\n\n    async def _phase_handoff(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `system-requirements`: декомпозиция и передача разработчику (H1).\n... 54 lines (1371-1424)\n\n    async def _clarify_open_questions(self, issue: IssueInput, deadlines,\n                                      branch: str) -> tuple | None:\n        \"\"\"Спросить и подождать. `None` — идти дальше, передавать задачу.\n... 57 lines (1429-1485)\n\n    async def _answer_followup(self, issue: IssueInput, comment: UserComment) -> tuple:\n        \"\"\"Ответить на реплику человека, оставшись в той же фазе.\n... 41 lines (1489-1529)\n\n    async def _phase_await_build(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `ready-for-dev`: ждём, возьмут ли задачу в разработку.\n... 54 lines (1533-1586)\n\n    async def _start_development(self, issue: IssueInput) -> tuple:\n        \"\"\"Активность Develop: передать задачу агенту разработки.\n... 49 lines (1590-1638)\n\n    async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `pr-review`: довести PR по замечаниям, пока они по делу.\n... 57 lines (1642-1698)\n\n    async def _phase_park(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Боковые фазы и фазы внешних агентов.\n... 47 lines (1702-1748)\n\n    async def _run_linear(self, issue: IssueInput) -> None:\n        \"\"\"Прежний линейный сценарий — БЕЗ ИЗМЕНЕНИЙ.\n... 269 lines (1752-2020)\n\n\n@workflow.defn(name=\"IssueAnalysis\")\nclass IssueAnalysis:\n    \"\"\"Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.\n... 11 lines (2026-2036)\n    async def run(self, analyze: AnalyzeInput) -> bool:\n        \"\"\"Возвращает, опубликованы ли артефакты.\n... 14 lines (2039-2052)\n\n\n@workflow.defn(name=\"IssueBft\")\nclass IssueBft:\n    \"\"\"БФТ по Issue: быстрый проход (`/bft`) и глубокая проработка (`/bft-deep`).\n... 11 lines (2058-2068)\n    def __init__(self) -> None:\n        self._stage = \"accepted\"\n        self._mode = bft.FAST\n\n    @workflow.query\n    def stage(self) -> str:\n        \"\"\"Стадия прогона — для Temporal UI (вкладка Queries).\n... 6 lines (2076-2081)\n\n    @workflow.query\n    def mode(self) -> str:\n        return self._mode\n\n    @workflow.run\n    async def run(self, req: BftRequest) -> bool:\n        \"\"\"Возвращает, опубликован ли БФТ.\n... 80 lines (2090-2169)\n\n    async def _run_deep(self, req: BftRequest) -> None:\n        \"\"\"Канонический пайплайн bft-writer — стадия за стадией.\n... 31 lines (2173-2203)\n\n\n@workflow.defn(name=\"IssueEstimation\")\nclass IssueEstimation:\n    \"\"\"Оценка трудоёмкости по команде /estimate.\n... 9 lines (2209-2217)\n    async def run(self, req: EstimateRequest) -> None:\n        ... 56 lines (2219-2274)\n",
        "verified": true
      },
      "episodes": 14
    }
  },
  "_meta": {
    "timing_ms": 202.2,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
