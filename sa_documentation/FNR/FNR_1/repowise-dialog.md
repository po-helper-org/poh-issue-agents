# Итог

1. **Реестр команд** (`shared/commands.py`): константы (`ESTIMATE`, `ANALYZE`, `BFT`, `BFT_DEEP`) + словарь `_COMMANDS` мапит `/command` → `command_name`. Метки `run:*`, `done:*`, `failed:*` выводятся автоматически через функции `run_label()`, `done_label()`, `failed_label()`. Для добавления команды достаточно: `TRIAGE = "triage"` и `_COMMANDS["/triage"] = TRIAGE`. [shared/commands.py:28-33](shared/commands.py:28-33)

2. **Старт триажа** (`webhook/main.py:418-437`): при `action == "opened"` старт `IssueLifecycle` с `id=workflow_id_for(repo, N)` и `interactive=True`. `WorkflowAlreadyStartedError` → лог `info` (штатная повторная доставка). [webhook/main.py:418-437](webhook/main.py:418-437)

3. **Метки команд** (`webhook/main.py:452-523`): `parse_label_command()` проверяет `run:*` против `_COMMANDS.values()`. Существующие команды (`analyze`, `estimate`, `bft`) запускают **другие воркфлоу** (`IssueAnalysis`, `IssueEstimation`, `IssueBft`) через `shared/agent_launcher.py`. [webhook/main.py:452-523](webhook/main.py:452-523)

4. **Архитектура agent_launcher** (`shared/agent_launcher.py`): единая точка запуска агентов — signal-with-start в `IssueLifecycle` → возможно старт дочернего агента. Сигналы: `analyze_requested`, `estimate_requested`, `bft_requested`. Проверка `_cycle_handles_agents()` решает: child или root. [shared/agent_launcher.py:72-106](shared/agent_launcher.py:72-106)

5. **Жизненный цикл** (`worker/workflows.py`): `IssueLifecycle.run(issue, carried=None)` — если `carried=None`, начинается с фазы `created` (триаж). Сигналы: `human_decision`, `user_comment`, `analyze_requested`, `bft_requested`, `estimate_requested`, `agent_event`. Константа `BFT_TRIAGE = "triage"` (строка 58) — режим БФТ, запускаемый самим триажем, а не человеком. [worker/workflows.py:656-705](worker/workflows.py:656-705)

6. **Backfill** (`scripts/backfill.py`): прямой старт `IssueLifecycle` с `interactive=False`, `WorkflowIDReusePolicy.REJECT_DUPLICATE`, `task_timeout=timedelta(seconds=120)`. `WorkflowAlreadyStartedError` → `skip (already running)`. [scripts/backfill.py:88-107](scripts/backfill.py:88-107)

7. **Метки результата** (`worker/activities.py:499-523`): activity `finish_command_labels` снимает `run:*` и противоположный исход, ставит `done:*` или `failed:*`. Best-effort, ошибки только в лог. Обёртка `_finish_labels` в воркфлоу с таймаутом/ретраями. [worker/activities.py:499-523](worker/activities.py:499-523)

8. **Гейт `_may_start_expensive`** (`webhook/main.py:177-199`): проверка `sender.login` против `AGENT_TRIGGER_ALLOWLIST`. Отказ → лог `warning`, возвращает `False` (вебхук отвечает `ok: True`). Успех → лог `info` с аудитом. [webhook/main.py:177-199](webhook/main.py:177-199)

9. **Паттерн `HUMAN_DECISION_LABELS`** (`webhook/main.py:502-522`): прямой `start_workflow("IssueLifecycle", ...)` с `start_signal="human_decision"`, `interactive=False`. Близкий паттерн для `run:triage`. [webhook/main.py:502-522](webhook/main.py:502-522)

10. **Комментарии** (`webhook/main.py:524-589`): реакция `eyes` на комментарий, фильтр ботов/агента, `parse_command()`, те же `request_*` функции с `interactive=True`. [webhook/main.py:524-589](webhook/main.py:524-589)

11. **Обработка `WorkflowAlreadyStartedError`**: в webhook/main.py (строки 427-437) и agent_launcher.py (строки 127-130) — только лог `info`, без комментария в Issue (принцип "вебхук — чистый транспорт"). [webhook/main.py:427-437](webhook/main.py:427-437)

# Открытые вопросы

1. **Политика повторного запуска** по уже завершённому циклу: перезапуск через `WorkflowIDReusePolicy` или отказ с объяснением? В backfill.py используется `REJECT_DUPLICATE`, но для `/triage` может быть нужен другой подход.

2. **Конфликт имён**: константа `BFT_TRIAGE = "triage"` в `worker/workflows.py:58` — режим БФТ, запускаемый триажем. Команда `/triage` не должна конфликтовать с этим значением.

3. **Закрытые Issue**: команда не должна работать на закрытых Issue (тот же принцип, что `action == "closed"`). Нужно добавить проверку в вебхуке.

4. **Стоимость**: платный прогон по требованию. Учесть #60: сервис сам ставит `run:*`, и при задержанной доставке метка возвращается событием — второй запуск не должен становиться вторым прогоном.

5. **Имя команды**: `/triage` описывает стадию, `/start` — намерение "обработай эту задачу целиком". Выбрать одно.

# Диалог

**Ход 1**: `get_overview()` — получил обзор репозитория: entry points, модули (`webhook`, `shared`, `worker`, `scripts`), hotspot `worker/workflows.py`, workspace с соседними репами.

**Ход 2**: `get_context("shared/commands.py")` — узнал структуру реестра команд: константы, словарь `_COMMANDS`, автогенерация меток `run:*`, `done:*`, `failed:*` через функции. Для добавления команды достаточно одной строки.

**Ход 3**: `get_context("webhook/main.py")` — partial skeleton не показал детали строки 418. Увидел импорты и общую структуру, но не точное место старта IssueLifecycle.

**Ход 4**: `search_codebase("IssueLifecycle start workflow opened action")` — нашёл целевые файлы: `webhook/main.py`, `worker/workflows.py`, `scripts/backfill.py`.

**Ход 5**: `get_symbol("webhook/main.py:390-612")` — получил детали старта IssueLifecycle при `issues.opened` (строки 418-437), обработку меток (labeled), комментарии (issue_comment). Увидел, что существующие команды запускают другие воркфлоу, а не IssueLifecycle.

**Ход 6**: `get_context("shared/agent_launcher.py")` — узнал архитектуру запуска агентов: signal-with-start в IssueLifecycle → возможно старт дочернего агента. Сигналы: `analyze_requested`, `estimate_requested`, `bft_requested`.

**Ход 7**: `get_context("scripts/backfill.py")` — узнал паттерн прямого запуска IssueLifecycle: `interactive=False`, `REJECT_DUPLICATE`, `task_timeout=120s`.

**Ход 8**: `get_context("worker/workflows.py")` — partial skeleton показал структуру IssueLifecycle: сигналы, фазы, метод `run(issue, carried=None)`. Если `carried=None` — начинается с фазы `created` (триаж). Нашёл `BFT_TRIAGE = "triage"` — потенциальный конфликт имён.

**Ход 9**: `search_codebase("done_label failed_label finish_labels")` — нашёл функцию `finish_command_labels` в `worker/activities.py` и `_finish_labels` в `worker/workflows.py`.

**Ход 10**: `get_symbol("worker/activities.py::finish_command_labels")` и `_finish_labels` — узнал механизм меток результата: activity снимает `run:*` и противоположный исход, ставит `done:*` или `failed:*`. Best-effort.

**Ход 11**: `get_symbol("webhook/main.py::_may_start_expensive")` — узнал гейт: проверка `sender.login` против `AGENT_TRIGGER_ALLOWLIST`, отказ → лог `warning`, успех → лог `info` с аудитом.

**Ход 12**: `search_codebase("WorkflowAlreadyStartedError comment issue already running")` — поиск не дал прямых результатов о комментариях.

**Ход 13**: `get_symbol("shared/agent_launcher.py:100-110")` — получил обработку `WorkflowAlreadyStartedError` в агент-лаунчере: только лог `info`, без комментария в Issue.

**Ход 14**: `get_symbol("shared/agent_launcher.py:104-130")` — подтвердил паттерн: "второе было бы шумом. Вебхук — чистый транспорт." такой же, как у `issues.opened`.


---
session: rw-analysis-po-helper-org__poh-issue-agents-112
workspace: contour
turns: 15
started: 2026-08-21T13:02:09Z
finished: 2026-08-21T13:03:23Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `d54073370859` | 17 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "null"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1",
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
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
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
    "shared/commands.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/commands.py": {
      "target": "shared/commands.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/commands.py",
        "summary": "Разбор slash-команд из комментариев Issue и сборка входа аналитики."
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
        "tokens": 1204,
        "full_tokens": 1632,
        "pct_of_full": 73.8,
        "bodies_kept": [
          "parse_command",
          "parse_label_command",
          "parse_command_args",
          "build_analyze_input",
          "build_bft_request"
        ],
        "text": "\"\"\"Разбор slash-команд из комментариев Issue и сборка входа аналитики.\n\nЖивёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен\nворкеру — чтобы исключить сами команды из треда, уходящего в модель. Модуль\nнамеренно не зависит ни от FastAPI, ни от temporalio: логика юнит-тестируема\nбез веб-стека (в dev-окружении fastapi отсутствует). Оба Dockerfile копируют\nshared/ в образ.\n\nУ команды два равноправных триггера — комментарий (`/analyze`) и метка\n(`run:analyze`). Оба ведут в один и тот же воркфлоу, поэтому набор команд\nобъявлен здесь ОДИН раз, а имена меток из него выводятся: разъехавшись, они\nдали бы метку, которая ничего не запускает, и запуск, который ничего не\nпомечает.\n\"\"\"\n\nfrom shared import bft\nfrom shared.workflow_types import AnalyzeInput, BftRequest\n\nESTIMATE = \"estimate\"\nANALYZE = \"analyze\"\n# БФТ двумя командами, а не одной с флагом: цена у них разная на два порядка\n# (один вызов модели против пайплайна в клоне репозитория), и человек обязан\n# видеть, что именно он запускает, ещё до запуска.\nBFT = \"bft\"\nBFT_DEEP = \"bft-deep\"\n\n_COMMANDS = {\"/estimate\": ESTIMATE, \"/analyze\": ANALYZE,\n             ... 6 lines (28-33)\nRUN_PREFIX = \"run:\"\nDONE_PREFIX = \"done:\"\nFAILED_PREFIX = \"failed:\"\n\n# Метки прежних версий, означавшие «идёт прогон». Снимаются вместе с `run:*`,\n# чтобы на завершённом Issue не осталось противоречия `analyzing` + `done:analyze`.\n_LEGACY_RUNNING_LABELS = {ANALYZE: (\"analyzing\",)}\n\n\ndef run_label(command: str) -> str:\n    return f\"{RUN_PREFIX}{command}\"\n\n\ndef done_label(command: str) -> str:\n    return f\"{DONE_PREFIX}{command}\"\n\n\ndef failed_label(command: str) -> str:\n    return f\"{FAILED_PREFIX}{command}\"\n\n\ndef running_labels(command: str) -> tuple[str, ...]:\n    \"\"\"Все метки «прогон идёт» для команды — их снимает финализация.\"\"\"\n    return (run_label(command),) + _LEGACY_RUNNING_LABELS.get(command, ())\n\n\ndef parse_label_command(label: str) -> str | None:\n    \"\"\"Команда, которую запускает метка, иначе None.\n\n    Запускает ТОЛЬКО `run:<команда>`. Это же и защита от петли: метки исхода\n    (`done:*`, `failed:*`) агент ставит себе сам, они прилетают обратно\n    событием issues.labeled — и не совпадают ни с одним триггером.\n    \"\"\"\n    if not label.startswith(RUN_PREFIX):\n        return None\n    command = label[len(RUN_PREFIX):].strip().lower()\n    return command if command in set(_COMMANDS.values()) else None\n\n\ndef bft_mode(command: str) -> str:\n    \"\"\"Режим прогона БФТ по имени команды.\n... 7 lines (75-81)\n\n\ndef parse_command(comment_body: str) -> str | None:\n    \"\"\"Имя команды, если комментарий — вызов команды, иначе None.\n\n    Командой считается только комментарий, ПЕРВАЯ непустая строка которого\n    начинается с самого вызова. Цитата (строка с '>') командой не считается:\n    иначе ответ с процитированной командой запускал бы её повторно. Хвост\n    после имени команды здесь игнорируется — его достаёт `parse_command_args`.\n    \"\"\"\n    for raw_line in comment_body.splitlines():\n        line = raw_line.strip()\n        if not line:\n            continue\n        if line.startswith(\">\"):\n            return None\n        return _COMMANDS.get(line.split()[0].lower())\n    return None\n\n\ndef parse_command_args(comment_body: str) -> str:\n    \"\"\"Всё, что человек написал после имени команды, включая следующие строки.\n\n    У `/analyze` и `/estimate` аргументов нет, у БФТ есть: `/bft` несёт\n    замечания к формулировке, `/bft-deep` — ответы на открытые вопросы. Хвост\n    забирается целиком и многострочно, потому что ответы на пять вопросов в одну\n    строку не пишут.\n\n    Не команда — пустая строка: вызывающий уже знает про это из `parse_command`,\n    и второй способ сказать «это не команда» тут ни к чему.\n    \"\"\"\n    lines = comment_body.splitlines()\n    for index, raw_line in enumerate(lines):\n        line = raw_line.strip()\n        if not line:\n            continue\n        ... 6 lines (118-123)\n\n\ndef build_analyze_input(payload: dict) -> AnalyzeInput:\n    \"\"\"Собирает вход воркфлоу IssueAnalysis из payload вебхука.\n\n    Один сборщик на оба триггера: у события issue_comment есть комментарий, у\n    issues.labeled его нет — тогда comment_id остаётся None, и активности,\n    которым нужен комментарий (реакция на него), просто его не ставят.\n    \"\"\"\n    issue = payload[\"issue\"]\n    comment = payload.get(\"comment\") or {}\n    ... 7 lines (135-141)\n\n\ndef build_bft_request(payload: dict, mode: str) -> BftRequest:\n    \"\"\"Вход воркфлоу БФТ из payload вебхука — один сборщик на оба триггера.\n\n    Аргументы есть только у команды в комментарии: запуск меткой ничего, кроме\n    самого факта запуска, не несёт, и `instructions` там пуст. Это не потеря —\n    метка и означает «пересобери по тому, что уже написано в Issue».\n    \"\"\"\n    issue = payload[\"issue\"]\n    comment = payload.get(\"comment\") or {}\n    ... 16 lines (153-168)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 73.8% of the full file — a direct Read costs little more."
      },
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-bft-writer",
            "file": "commands/bft-draft.md",
            "strength": 0.504
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 59.29,
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
    "timing_ms": 62.78,
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
  "query": "IssueLifecycle start workflow opened action webhook",
  "mode": "concept",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: worker/workflows.py",
      "page_type": "file_page",
      "snippet": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: webhook/main.py",
      "page_type": "file_page",
      "snippet": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "webhook/main.py",
      "confidence_score": 0.98
    },
    {
      "title": "File: scripts/backfill.py",
      "page_type": "file_page",
      "snippet": "# scripts/backfill.py\n\n## Overview\n\nBackfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never p",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/backfill.py",
      "confidence_score": 0.97
    },
    {
      "title": "Application Worker",
      "page_type": "module_page",
      "snippet": ".py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions). Изменился только транс\n\n- `worker/github_client.py`: Обёртка над GitHub REST API. В отличи",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker",
      "confidence_score": 0.94
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": "ed on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Traced flows\n\n\n\n\n### Fr",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
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
      "path": "worker/workflows.py"
    },
    {
      "path": "webhook/main.py"
    },
    {
      "path": "scripts/backfill.py"
    },
    {
      "path": "shared/agent_launcher.py"
    },
    {
      "path": "shared/authz.py"
    }
  ]
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "webhook/main.py:390-612",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "webhook/main.py:390-612",
  "file": "webhook/main.py",
  "kind": "range",
  "start_line": 390,
  "end_line": 589,
  "total_lines": 612,
  "source": "   390\t    body = await request.body()\n   391\t    verify_signature(body, x_hub_signature_256)\n   392\t    payload = await request.json()\n   393\t\n   394\t    # Allowlist: действуем только на репозитории из ISSUE_AGENT_REPOS (пусто/* —\n   395\t    # любой установленный). Чужой репозиторий игнорируем до старта workflow.\n   396\t    repo_full = (payload.get(\"repository\") or {}).get(\"full_name\")\n   397\t    if repo_full and not is_allowed(repo_full, allowed_specs()):\n   398\t        specs = [s for s in allowed_specs() if s.strip()]\n   399\t        # warning, а не info, и вместе с действующим allowlist: строка лога\n   400\t        # обязана сама говорить, что чинить. Раньше отказ был неотличим от\n   401\t        # тишины — GitHub видел 200, в Temporal не появлялось ничего.\n   402\t        _log.warning(\n   403\t            \"ignored repo %s — not in ISSUE_AGENT_REPOS %s; событие отброшено до Temporal\",\n   404\t            repo_full, specs or [\"(пусто)\"],\n   405\t        )\n   406\t        await _audit_dropped_delivery(payload, x_github_event, x_github_delivery,\n   407\t                                      repo_full, specs)\n   408\t        return {\"ok\": True}\n   409\t\n   410\t    client = await get_temporal_client()\n   411\t\n   412\t    if x_github_event == \"issues\":\n   413\t        action = payload[\"action\"]\n   414\t        repo = payload[\"repository\"][\"full_name\"]\n   415\t        issue_number = payload[\"issue\"][\"number\"]\n   416\t        wf_id = workflow_id_for(repo, issue_number)\n   417\t\n   418\t        if action == \"opened\":\n   419\t            try:\n   420\t                await client.start_workflow(\n   421\t                    \"IssueLifecycle\",  # имя workflow строкой — worker зарегистрирует класс под этим именем\n   422\t                    _issue_input(payload, interactive=True),\n   423\t                    id=wf_id,\n   424\t                    task_queue=\"issue-lifecycle\",\n   425\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   426\t                )\n   427\t            except WorkflowAlreadyStartedError:\n   428\t                # Повторная доставка того же события — норма, а не сбой: GitHub\n   429\t                # ретраит, если не дождался ответа, и оба раза просит одного и\n   430\t                # того же. Цикл по этому Issue уже существует, то есть нужное\n   431\t                # состояние достигнуто.\n   432\t                #\n   433\t                # 500 здесь был хуже, чем бесполезен: GitHub на нём ретраит\n   434\t                # снова, каждый ретрай снова падает, и вебхук отвечает ошибкой\n   435\t                # на штатную ситуацию, пока доставка не будет брошена насовсем.\n   436\t                _log.info(\"цикл %s#%s уже запущен — повторная доставка\",\n   437\t                          repo, issue_number)\n   438\t\n   439\t        elif action == \"closed\":\n   440\t            # Закрытый Issue не ждут. Голый signal, а НЕ signal-with-start:\n   441\t            # поднимать цикл по Issue, которым никто не занимался, чтобы тут же\n   442\t            # его закрыть, — лишний прогон в истории и лишние вызовы GitHub.\n   443\t            handle = client.get_workflow_handle(wf_id)\n   444\t            try:\n   445\t                await handle.signal(\n   446\t                    \"issue_closed\", (payload.get(\"sender\") or {}).get(\"login\"))\n   447\t            except Exception:\n   448\t                # Цикла нет или он уже завершён — сигналить некому. Это штатно:\n   449\t                # на 500 GitHub ретраит доставку и в итоге бросает её насовсем.\n   450\t                _log.info(\"no live cycle for closed %s#%s\", repo, issue_number)\n   451\t\n   452\t        elif action == \"labeled\":\n   453\t            label = payload[\"label\"][\"name\"]\n   454\t\n   455\t            # Метка — второй триггер команды, равноправный с комментарием: два\n   456\t            # тапа в мобильном GitHub вместо набора текста в треде. Ведёт в тот\n   457\t            # же воркфлоу, что и `/analyze` — таблица соответствия одна\n   458\t            # (shared/commands.py), поэтому разъехаться им негде.\n   459\t            command = parse_label_command(label)\n   460\t\n   461\t            if command == ANALYZE:\n   462\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   463\t                    return {\"ok\": True}\n   464\t                # Режим (child цикла или самостоятельный прогон) выбирает\n   465\t                # лаунчер — одна точка решения на все входы.\n   466\t                await request_analysis(\n   467\t                    client,\n   468\t                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n   469\t                    _issue_input(payload, interactive=False),\n   470\t                    build_analyze_input(payload),  # без comment_id: триггер — метка\n   471\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   472\t                )\n   473\t                return {\"ok\": True}\n   474\t\n   475\t            if command == ESTIMATE:\n   476\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   477\t                    return {\"ok\": True}\n   478\t                from shared.workflow_types import EstimateRequest\n   479\t\n   480\t                await request_estimate(\n   481\t                    client,\n   482\t                    _issue_input(payload, interactive=False),\n   483\t                    EstimateRequest(repo=repo, issue_number=issue_number),\n   484\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   485\t                )\n   486\t                return {\"ok\": True}\n   487\t\n   488\t            if command in (BFT, BFT_DEEP):\n   489\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   490\t                    return {\"ok\": True}\n   491\t                await request_bft(\n   492\t                    client,\n   493\t                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n   494\t                    _issue_input(payload, interactive=False),\n   495\t                    # Без comment_id и без уточнений: метка несёт только сам факт\n   496\t                    # запуска, и это законно — «пересобери по тому, что в Issue».\n   497\t                    build_bft_request(payload, bft_mode(command)),\n   498\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   499\t                )\n   500\t                return {\"ok\": True}\n   501\t\n   502\t            if label in HUMAN_DECISION_LABELS:\n   503\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   504\t                    return {\"ok\": True}\n   505\t                # signal-with-start, а не голый signal: лейбл прилетает и по\n   506\t                # issue, у которого воркфлоу триажа не существует (issue завели\n   507\t                # до установки App — `issues.opened` никто не доставил; либо\n   508\t                # триаж прогнали в обход Temporal). signal() в несуществующий\n   509\t                # workflow бросает исключение, вебхук отвечает 500, GitHub\n   510\t                # ретраит и бросает доставку — лейбл остаётся мёртвым молча.\n   511\t                await client.start_workflow(\n   512\t                    \"IssueLifecycle\",\n   513\t                    # Отвечать на уточняющий вопрос тут некому: триггер —\n   514\t                    # лейбл, а не диалог. VAGUE обязан эскалировать, иначе цикл\n   515\t                    # уточнений съест только что доставленный сигнал.\n   516\t                    _issue_input(payload, interactive=False),\n   517\t                    id=wf_id,\n   518\t                    task_queue=\"issue-lifecycle\",\n   519\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   520\t                    start_signal=\"human_decision\",\n   521\t                    start_signal_args=[label],\n   522\t                )\n   523\t\n   524\t    elif x_github_event == \"issue_comment\":\n   525\t        if payload[\"action\"] != \"created\":\n   526\t            return {\"ok\": True}\n   527\t        # Комментарии от самого сервиса не должны сигналить сами себя —\n   528\t        # тот же принцип, что и guard `comment.user.type != 'Bot'` в старой\n   529\t        # версии на Actions.\n   530\t        if payload[\"comment\"][\"user\"][\"type\"] == \"Bot\":\n   531\t            return {\"ok\": True}\n   532\t        # Гейта по типу автора мало: под PAT сервис пишет от имени человека, и\n   533\t        # его комментарии возвращаются с `type == \"User\"`. На живом прогоне\n   534\t        # именно так advisor-ответ и разбор приоритета приезжали обратно как\n   535\t        # `user_comment`. Различаем по подписи, а не по логину: владелец токена\n   536\t        # — тот же человек, чьи настоящие ответы кормят цикл уточнений.\n   537\t        if is_agent_comment(payload[\"comment\"].get(\"body\")):\n   538\t            return {\"ok\": True}\n   539\t\n   540\t        repo = payload[\"repository\"][\"full_name\"]\n   541\t        issue_number = payload[\"issue\"][\"number\"]\n   542\t\n   543\t        # Подтверждение приёма — ДО разбора команды и до любого пайплайна.\n   544\t        # Всё, что ниже, ветвится и гейтится (права, живой цикл, лимиты LLM);\n   545\t        # реакция не ветвится ни на чём: комментарий доставлен, значит система\n   546\t        # его увидела, и это должно быть видно человеку сразу.\n   547\t        await _ack_comment_seen(client, repo, issue_number,\n   548\t                                payload[\"comment\"][\"id\"])\n   549\t\n   550\t        # Единственная точка ветвления «команда против обычного комментария»:\n   551\t        # команда НЕ уходит в user_comment, иначе её съел бы цикл уточнений\n   552\t        # intake gate как ответ на уточняющий вопрос.\n   553\t        command = parse_command(payload[\"comment\"].get(\"body\") or \"\")\n   554\t\n   555\t        if command == ESTIMATE:\n   556\t            if not _may_start_expensive(payload, \"/estimate\", repo, issue_number):\n   557\t                return {\"ok\": True}\n   558\t            from shared.workflow_types import EstimateRequest\n   559\t\n   560\t            comment_id = payload[\"comment\"][\"id\"]\n   561\t            await request_estimate(\n   562\t                client,\n   563\t                _issue_input(payload, interactive=True),\n   564\t                EstimateRequest(repo=repo, issue_number=issue_number,\n   565\t                                comment_id=comment_id),\n   566\t                search_attributes=_search_attributes(repo, payload, issue_number),\n   567\t            )\n   568\t            return {\"ok\": True}\n   569\t\n   570\t        if command in (BFT, BFT_DEEP):\n   571\t            if not _may_start_expensive(payload, f\"/{command}\", repo, issue_number):\n   572\t                return {\"ok\": True}\n   573\t            await request_bft(\n   574\t                client,\n   575\t                _issue_input(payload, interactive=True),\n   576\t                build_bft_request(payload, bft_mode(command)),\n   577\t                search_attributes=_search_attributes(repo, payload, issue_number),\n   578\t            )\n   579\t            return {\"ok\": True}\n   580\t\n   581\t        if command == ANALYZE:\n   582\t            if not _may_start_expensive(payload, \"/analyze\", repo, issue_number):\n   583\t                return {\"ok\": True}\n   584\t            # Одна точка решения child-vs-root: раньше здесь стартовал\n   585\t            # самостоятельный IssueAnalysis, а циклу уходило лишь косметическое\n   586\t            # уведомление — связь между владельцем состояния Issue и работой\n   587\t            # агента была декоративной (#37).\n   588\t            await request_analysis(\n   589\t                client,",
  "truncated": true,
  "verified": true,
  "_meta": {
    "timing_ms": 12.65,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6855
  },
  "continuation": "webhook/main.py:590-612",
  "note": "Range capped at 200 lines; served 390-589. Continue in one call: get_symbol('webhook/main.py:590-612')."
}

## Ход 6 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/agent_launcher.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/agent_launcher.py": {
      "target": "shared/agent_launcher.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/agent_launcher.py",
        "summary": "Единая точка запуска агента: child при живом цикле, root — иначе."
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
        "tokens": 1479,
        "full_tokens": 1610,
        "pct_of_full": 91.9,
        "bodies_kept": [
          "_cycle_handles_agents",
          "request_analysis",
          "request_estimate",
          "request_bft"
        ],
        "text": "\"\"\"Единая точка запуска агента: child при живом цикле, root — иначе.\n\nТребование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.\nДо этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifecycle` о них\nне знал и вешал косметическую метку.\n\nРежим выбирает ОДНА функция, а не каждый вызывающий. Иначе решение\n«child или root» разъедется по трём местам ровно так же, как когда-то разъехались\nформаты workflow id (см. `shared/workflow_ids.py`).\n\nКак принимается решение\n-----------------------\nНе «описать воркфлоу и посмотреть статус» — это лишний round-trip и гонка между\nпроверкой и стартом. Вместо этого **всегда signal-with-start** в цикл: он либо\nполучает сигнал, либо поднимается тем же вызовом. Дальше цикл сам решает,\nподнимать ли дочерний прогон.\n\nОстаётся один случай, который цикл обслужить не может: прогоны ПРЕЖНЕГО\nпоколения (линейный путь до #36). Их история не знает ни фазового цикла, ни\nсигнала на запуск агента — команда была бы принята и потеряна. Их отличает\nquery `handles_agents`; для них лаунчер стартует root-прогон, как раньше.\n\nДвойного прогона это не создаёт при любом исходе гонки: id агента фиксирован\n(`shared/workflow_ids.py`), поэтому второй старт упирается в\n`WorkflowAlreadyStarted`, а не тратит деньги второй раз.\n\"\"\"\n\nimport logging\n\nfrom shared.workflow_ids import (\n    analysis_workflow_id,\n    bft_workflow_id,\n    estimate_workflow_id,\n    issue_workflow_id,\n)\n\n_log = logging.getLogger(__name__)\n\nTASK_QUEUE = \"issue-lifecycle\"\n\nANALYSIS_WORKFLOW = \"IssueAnalysis\"\nESTIMATION_WORKFLOW = \"IssueEstimation\"\nBFT_WORKFLOW = \"IssueBft\"\n\n# Режимы — возвращаются вызывающему для лога и тестов.\nCHILD = \"child\"    # работу ведёт цикл дочерним прогоном\nROOT = \"root\"      # цикл прежнего поколения либо автономный запуск\n\n\nasync def _cycle_handles_agents(handle, repo: str, issue_number: int) -> bool:\n    \"\"\"Умеет ли этот цикл вести агентов дочерними прогонами.\n\n    Ошибку query не считаем за «не умеет»: signal-with-start уже прошёл, значит\n    цикл жив, а новых прогонов со временем становится только больше. Поднимать\n    на недоступном query второй дорогой прогон — худший из двух исходов.\n    \"\"\"\n    try:\n        return bool(await handle.query(\"handles_agents\"))\n    except Exception as exc:\n        _log.warning(\"не удалось спросить цикл %s#%s о режиме агентов (%s) — \"\n                     \"считаю, что он ведёт их сам\", repo, issue_number, exc)\n        return True\n\n\nasync def request_analysis(client, issue_input, analyze, *,\n                           search_attributes=None) -> str:\n    \"\"\"`/analyze` или метка `run:analyze` — запустить аналитику по Issue.\"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = analyze.repo, analyze.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"analyze_requested\",\n        start_signal_args=[analyze.comment_id],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            ANALYSIS_WORKFLOW, analyze,\n            id=analysis_workflow_id(repo, issue_number),\n            task_queue=TASK_QUEUE,\n            search_attributes=search_attributes,\n        )\n    except WorkflowAlreadyStartedError:\n        # Прогон по этому Issue уже идёт: пользователь видел ack первого\n        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.\n        _log.info(\"analysis already running for %s#%s\", repo, issue_number)\n    return ROOT\n\n\nasync def request_bft(client, issue_input, req, *, search_attributes=None) -> str:\n    \"\"\"`/bft`, `/bft-deep` или метка `run:bft*` — собрать БФТ по Issue.\n\n    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт\n    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать\n    своё — ровно как с оценкой.\n    \"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = req.repo, req.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"bft_requested\",\n        start_signal_args=[req],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            BFT_WORKFLOW, req,\n            id=bft_workflow_id(repo, issue_number, req.mode),\n            ... 8 lines (124-131)\n\n\nasync def request_estimate(client, issue_input, estimate, *,\n                           search_attributes=None) -> str:\n    \"\"\"`/estimate` или метка `run:estimate` — оценить трудоёмкость.\n\n    Оценка фазу не двигает: это боковая команда, а не стадия пути Issue.\n    Цикл поднимает её дочерним прогоном и продолжает ждать своё.\n    \"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = estimate.repo, estimate.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"estimate_requested\",\n        start_signal_args=[estimate.comment_id],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            ESTIMATION_WORKFLOW, estimate,\n            id=estimate_workflow_id(repo, issue_number, estimate.comment_id),\n            task_queue=TASK_QUEUE,\n            search_attributes=search_attributes,\n        ... 5 lines (162-166)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 91.9% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 44.51,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 7 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "scripts/backfill.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "scripts/backfill.py": {
      "target": "scripts/backfill.py",
      "type": "file",
      "parent_page": {
        "title": "Docs Tooling Scripts",
        "target_path": "scripts",
        "section": "5"
      },
      "docs": {
        "title": "File: scripts/backfill.py",
        "summary": "Backfill: start one IssueLifecycle workflow per already-open Issue."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 3,
        "last_fix_days_ago": 37
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "architectural_layer": {
        "name": "Docs & Tooling",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1070,
        "full_tokens": 1129,
        "pct_of_full": 94.8,
        "bodies_kept": [
          "build_issue_input",
          "main"
        ],
        "text": "\"\"\"Backfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never processes the current backlog. This script enumerates\nopen Issues via `gh` and starts workflows directly against Temporal.\n\nRuns in non-interactive batch mode (interactive=False): a VAGUE issue\nescalates instead of waiting for a human clarification that will not come.\n\nUsage:\n    python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY\n    python scripts/backfill.py --issue 83      # single issue (smoke test)\n    python scripts/backfill.py --limit 5       # first N\n    python scripts/backfill.py --repo owner/name\n\"\"\"\n\nimport argparse\nimport asyncio\nimport json\nimport os\nimport subprocess\nimport sys\nfrom datetime import timedelta\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n\nfrom temporalio.common import WorkflowIDReusePolicy\n\nfrom shared.temporal_client import connect_temporal\nfrom shared.workflow_ids import issue_workflow_id\nfrom shared.workflow_types import IssueInput\n\ntry:\n    from temporalio.client import WorkflowAlreadyStartedError\nexcept ImportError:  # older/newer layout\n    from temporalio.exceptions import WorkflowAlreadyStartedError  # type: ignore\n\nTASK_QUEUE = \"issue-lifecycle\"\n\n\ndef build_issue_input(repo: str, item: dict) -> IssueInput:\n    author = item.get(\"author\") or {}\n    return IssueInput(\n        repo=repo,\n        issue_number=item[\"number\"],\n        title=item[\"title\"],\n        body=item.get(\"body\") or \"\",\n        author_login=author.get(\"login\", \"\"),\n        author_type=\"Bot\" if author.get(\"is_bot\") else \"User\",\n        interactive=False,\n    )\n\n\ndef list_open_issues(repo: str, limit: int) -> list[dict]:\n    ... 4 lines (56-59)\n\n\n# Формат id (в т.ч. suffix для осознанного перепрогона) живёт в\n# shared/workflow_ids.py — его же собирают вебхук и scripts/estimate.py.\nworkflow_id_for = issue_workflow_id\n\n\nasync def main() -> None:\n    parser = argparse.ArgumentParser()\n    parser.add_argument(\"--repo\", default=os.environ.get(\"GITHUB_REPOSITORY\"))\n    parser.add_argument(\"--issue\", type=int, default=None)\n    parser.add_argument(\"--limit\", type=int, default=200)\n    parser.add_argument(\"--suffix\", default=\"\", help=\"append to workflow id (fresh run without terminating prior)\")\n    args = parser.parse_args()\n\n    if not args.repo:\n        raise SystemExit(\"set --repo or GITHUB_REPOSITORY\")\n\n    if args.issue is not None:\n        items = [i for i in list_open_issues(args.repo, args.limit) if i[\"number\"] == args.issue]\n        if not items:\n            raise SystemExit(f\"issue #{args.issue} not found among open issues\")\n    else:\n        items = list_open_issues(args.repo, args.limit)\n\n    client = await connect_temporal()\n\n    started, skipped = 0, 0\n    for item in items:\n        issue = build_issue_input(args.repo, item)\n        wf_id = workflow_id_for(args.repo, issue.issue_number, args.suffix)\n        try:\n            await client.start_workflow(\n                \"IssueLifecycle\", issue, id=wf_id, task_queue=TASK_QUEUE,\n                # REJECT_DUPLICATE keeps re-runs idempotent: a plain re-run skips\n                # already-processed issues (no double comments). To deliberately\n                # re-process, pass --suffix to mint fresh workflow ids instead.\n                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,\n                # A backfill starts dozens of workflows at once against a single\n                # worker whose activities are slow LLM calls. The default 10s\n                # workflow-task timeout is then too tight — tasks time out before\n                # the busy worker processes them, forcing full-history replays\n                # (churn that re-runs activities and wastes LLM calls). 120s\n                # gives the worker room to drain the backlog.\n                task_timeout=timedelta(seconds=120),\n            )\n            started += 1\n            print(f\"started {wf_id}\")\n        except WorkflowAlreadyStartedError:\n            skipped += 1\n            print(f\"skip {wf_id} (already running)\")\n    print(f\"done: started={started} skipped={skipped} total={len(items)}\")\n\n\nif __name__ == \"__main__\":\n    asyncio.run(main())\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 94.8% of the full file — a direct Read costs little more."
      },
      "episodes": 3,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-helper",
            "file": ".claude/commands/bft-fast.md",
            "strength": 0.619
          },
          {
            "repo": "poh-helper",
            "file": ".claude/skills/bft-fast/SKILL.md",
            "strength": 0.619
          },
          {
            "repo": "poh-helper",
            "file": ".claude/skills/bft-deep-swarm/examples/golden_deep_gold.md",
            "strength": 0.619
          },
          {
            "repo": "poh-helper",
            "file": ".claude/skills/bft-deep-swarm/SKILL.md",
            "strength": 0.619
          },
          {
            "repo": "poh-helper",
            "file": ".claude/skills/bft-deep-swarm/resources/eval_rubric.md",
            "strength": 0.619
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 33.46,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 8 · `get_context` · contour

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
    "timing_ms": 120.0,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
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
  "query": "done_label failed_label finish_labels",
  "mode": "concept",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: worker.activities.finish_command_labels",
      "page_type": "symbol_spotlight",
      "snippet": "наружу не пробрасывается — activity зовётся из терминальных веток воркфлоу.\n    \"\"\"\n    outcome = done_label(command) if ok else failed_label(command)\n    # Исход ПРЕДЫДУЩЕГО прогона снимается вмест",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::finish_command_labels",
      "file": "worker/activities.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: shared/commands.py",
      "page_type": "file_page",
      "snippet": "nt | FAILED_PREFIX = \"failed:\" |\n| `run_label` | function | def run_label(command: str) -> str |\n| `done_label` | function | def done_label(command: str) -> str |\n| `failed_label` | function | def fai",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "shared/commands.py",
      "confidence_score": 0.99
    },
    {
      "title": "Symbol: worker.workflows.IssueEstimation",
      "page_type": "symbol_spotlight",
      "snippet": "timedelta(seconds=30),\n                retry_policy=default_retry,\n            )\n            await _finish_labels(req.repo, req.issue_number, ESTIMATE, ok=True)\n        except Exception as e:",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueEstimation",
      "file": "worker/workflows.py",
      "confidence_score": 0.97
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": ".py::IssueAnalysis::run`\n\n2. `worker/workflows.py::_run_staged_analysis`\n\n3. `worker/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. README.md. Start",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
      "confidence_score": 0.95
    },
    {
      "title": "File: shared/agent_events.py",
      "page_type": "file_page",
      "target_path": "shared/agent_events.py",
      "snippet": "Контракт «событие внешнего агента → факт в жизни Issue».",
      "relevance_score": 2.768,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.92
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
      "path": "worker/activities.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/agent_events.py"
    },
    {
      "path": "scripts/e2e_live.py"
    }
  ]
}

## Ход 10 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::finish_command_labels",
  "repo": "poh-issue-agents"
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
  "start_line": 499,
  "end_line": 523,
  "symbol_start_line": 499,
  "symbol_end_line": 523,
  "source": "   499\tasync def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:\n   500\t    \"\"\"Обратный ход: снять метки «идёт», повесить исход.\n   501\t\n   502\t    Неуспех получает СВОЮ метку, а не просто снятый `run:*`: молча снятая метка\n   503\t    неотличима от «никто не запускал», а именно это и нужно увидеть в ленте.\n   504\t\n   505\t    Best-effort по каждой метке: прогон уже состоялся, и провал косметики не\n   506\t    должен превращать успешный анализ в проваленный. Ошибка уходит в лог, но\n   507\t    наружу не пробрасывается — activity зовётся из терминальных веток воркфлоу.\n   508\t    \"\"\"\n   509\t    outcome = done_label(command) if ok else failed_label(command)\n   510\t    # Исход ПРЕДЫДУЩЕГО прогона снимается вместе с «идёт»: `done:analyze` рядом\n   511\t    # с `failed:analyze` — противоречие, а не история. По такой паре нельзя\n   512\t    # сказать, чем кончился последний прогон, и выборка `label:failed:*`\n   513\t    # показывает задачи, которые давно починены повторным запуском.\n   514\t    previous = failed_label(command) if ok else done_label(command)\n   515\t    for stale in (*running_labels(command), previous):\n   516\t        try:\n   517\t            await asyncio.to_thread(github_client.remove_label, repo, issue_number, stale)\n   518\t        except Exception as exc:\n   519\t            logger.warning(\"не снял метку %s с %s#%s: %s\", stale, repo, issue_number, exc)\n   520\t    try:\n   521\t        await asyncio.to_thread(github_client.add_label, repo, issue_number, outcome)\n   522\t    except Exception as exc:\n   523\t        logger.warning(\"не поставил метку %s на %s#%s: %s\", outcome, repo, issue_number, exc)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 20.69,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 34493
  }
}

## Ход 11 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::_finish_labels",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::_finish_labels",
  "file": "worker/workflows.py",
  "name": "_finish_labels",
  "kind": "function",
  "qualified_name": "worker.workflows._finish_labels",
  "signature": "async def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
  "language": "python",
  "start_line": 230,
  "end_line": 242,
  "symbol_start_line": 230,
  "symbol_end_line": 242,
  "source": "   230\tasync def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:\n   231\t    \"\"\"Обратный ход меток команды — один вызов на все терминальные ветки.\n   232\t\n   233\t    Зовётся из трёх мест (IssueAnalysis, IssueEstimation и ветка research-me в\n   234\t    IssueLifecycle), поэтому таймаут и политика ретраев заданы здесь: разъехавшись,\n   235\t    они дали бы Issue, застрявший в `run:*` после завершённого прогона.\n   236\t    \"\"\"\n   237\t    await workflow.execute_activity(\n   238\t        activities.finish_command_labels,\n   239\t        args=[repo, issue_number, command, ok],\n   240\t        start_to_close_timeout=timedelta(seconds=60),\n   241\t        retry_policy=RetryPolicy(maximum_attempts=3),\n   242\t    )",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 18.59,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28921
  }
}

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "webhook/main.py::_may_start_expensive"
}
```

**Ответ:**

{
  "symbol_id": "webhook/main.py::_may_start_expensive",
  "file": "webhook/main.py",
  "name": "_may_start_expensive",
  "kind": "function",
  "qualified_name": "webhook.main._may_start_expensive",
  "signature": "def _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool",
  "language": "python",
  "start_line": 177,
  "end_line": 199,
  "symbol_start_line": 177,
  "symbol_end_line": 199,
  "source": "   177\tdef _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:\n   178\t    \"\"\"Гейт на запуск дорогой стадии + аудит того, кто её запустил.\n   179\t\n   180\t    Проверяем автора события, а не факт наличия метки: метку может поставить\n   181\t    любой с правами на репозиторий, и это самый дешёвый способ потратить чужие\n   182\t    токены. Дешёвые пути (issues.opened, обычные комментарии) сюда не приходят —\n   183\t    триаж обязан работать для всех.\n   184\t\n   185\t    Отказ только логируем: вебхук — чистый транспорт, GitHub-клиента у него нет,\n   186\t    и заводить его ради комментария «недостаточно прав» значит дать наружу\n   187\t    процессу право писать в Issue.\n   188\t    \"\"\"\n   189\t    login = (payload.get(\"sender\") or {}).get(\"login\")\n   190\t    allowlist = trigger_allowlist()\n   191\t    if may_trigger(login, allowlist):\n   192\t        # Аудит: кто и когда запустил дорогую стадию (время ставит логгер).\n   193\t        _log.info(\"expensive trigger %s by %s on %s#%s\", what, login, repo, issue_number)\n   194\t        return True\n   195\t    _log.warning(\n   196\t        \"отклонён запуск %s: %s не входит в AGENT_TRIGGER_ALLOWLIST %s (%s#%s)\",\n   197\t        what, login, allowlist, repo, issue_number,\n   198\t    )\n   199\t    return False",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.17,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6855
  }
}

## Ход 13 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "WorkflowAlreadyStartedError comment issue already running",
  "mode": "concept",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "живом цикле, root — иначе.\n\nТребование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.\nДо этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`\nстартовали",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: scripts/backfill.py",
      "page_type": "file_page",
      "snippet": "# scripts/backfill.py\n\n## Overview\n\nBackfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never p",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/backfill.py",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: scripts/setup.sh",
      "page_type": "infra_page",
      "snippet": "ed up, existing values are offered as\n# defaults, and DRY_RUN defaults to 1 so nothing mutates real issues until you\n# explicitly go live.\n#\n# Usage:  bash scripts/setup.sh   (or: make setup)\n\nset -eu",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/setup.sh",
      "confidence_score": 0.97
    },
    {
      "title": "Docs Tooling Scripts",
      "page_type": "module_page",
      "snippet": "s\n\nHighest-PageRank first: the order to read them in.\n\n- `scripts/backfill.py`: Backfill: start one IssueLifecycle workflow per already-open Issue. GitHub never sends webhooks for Issues that already",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "scripts",
      "confidence_score": 0.94
    },
    {
      "title": "File: shared/agent_events.py",
      "page_type": "file_page",
      "target_path": "shared/agent_events.py",
      "snippet": "Контракт «событие внешнего агента → факт в жизни Issue».",
      "relevance_score": 2.461,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.81
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
      "path": "shared/agent_launcher.py"
    },
    {
      "path": "scripts/backfill.py"
    },
    {
      "path": "scripts/setup.sh"
    },
    {
      "path": "shared/agent_events.py"
    },
    {
      "path": ".claude/skills/systematic-debugging/find-polluter.sh"
    }
  ]
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/agent_launcher.py:100-110"
}
```

**Ответ:**

{
  "symbol_id": "shared/agent_launcher.py:100-110",
  "file": "shared/agent_launcher.py",
  "kind": "range",
  "start_line": 100,
  "end_line": 110,
  "total_lines": 166,
  "source": "   100\t\n   101\t    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт\n   102\t    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать\n   103\t    своё — ровно как с оценкой.\n   104\t    \"\"\"\n   105\t    from temporalio.exceptions import WorkflowAlreadyStartedError\n   106\t\n   107\t    repo, issue_number = req.repo, req.issue_number\n   108\t    handle = await client.start_workflow(\n   109\t        \"IssueLifecycle\",\n   110\t        issue_input,",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.82,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 1610
  }
}

## Ход 15 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/agent_launcher.py:104-130"
}
```

**Ответ:**

{
  "symbol_id": "shared/agent_launcher.py:104-130",
  "file": "shared/agent_launcher.py",
  "kind": "range",
  "start_line": 104,
  "end_line": 130,
  "total_lines": 166,
  "source": "   104\t    \"\"\"\n   105\t    from temporalio.exceptions import WorkflowAlreadyStartedError\n   106\t\n   107\t    repo, issue_number = req.repo, req.issue_number\n   108\t    handle = await client.start_workflow(\n   109\t        \"IssueLifecycle\",\n   110\t        issue_input,\n   111\t        id=issue_workflow_id(repo, issue_number),\n   112\t        task_queue=TASK_QUEUE,\n   113\t        search_attributes=search_attributes,\n   114\t        start_signal=\"bft_requested\",\n   115\t        start_signal_args=[req],\n   116\t    )\n   117\t    if await _cycle_handles_agents(handle, repo, issue_number):\n   118\t        return CHILD\n   119\t\n   120\t    try:\n   121\t        await client.start_workflow(\n   122\t            BFT_WORKFLOW, req,\n   123\t            id=bft_workflow_id(repo, issue_number, req.mode),\n   124\t            task_queue=TASK_QUEUE,\n   125\t            search_attributes=search_attributes,\n   126\t        )\n   127\t    except WorkflowAlreadyStartedError:\n   128\t        # Прогон в этом режиме уже идёт: пользователь видел подтверждение\n   129\t        # первого запуска, второе было бы шумом. Вебхук — чистый транспорт.\n   130\t        _log.info(\"bft %s already running for %s#%s\", req.mode, repo, issue_number)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 16.5,
    "index_age_days": 0,
    "indexed_commit": "d54073370859",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 1610
  }
}
