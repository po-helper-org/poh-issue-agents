# Итог

## Подтверждение проблемы

1. **В `.github/workflows/` репозитория `poh-issue-agents` есть только `tests.yml`** — прогон pytest. Ни `pr-review.yml`, ни `openhands-resolver.yml` отсутствуют ([.github/workflows/tests.yml](.github/workflows/tests.yml:1)).

2. **Круг правок PR реализован в `shared/pr_closing.py`** и использует переменные окружения `PR_FIX_ENABLED`/`PR_FIX_MAX_ROUNDS` ([shared/pr_closing.py:52-54](shared/pr_closing.py:52), [shared/pr_closing.py:42-43](shared/pr_closing.py:42)). По умолчанию включено (`True`) и 3 круга.

3. **Фаза `PR_REVIEW` обрабатывается в `worker/workflows.py::_phase_pr_review`** ([worker/workflows.py:1640-1698](worker/workflows.py:1640)). Проверяет `deadlines.pr_fix_enabled` и запускает `activities.run_pr_fix_round` для каждого круга.

4. **Внешние события принимаются через webhook `/agent-event`** ([webhook/main.py:317-353](webhook/main.py:317)). Требуется секрет `AGENT_EVENT_SECRET` для подписи событий от внешних агентов (PR-Agent, PR-Closer, CI).

5. **Контракт событий определён в `shared/agent_events.py`** — публичный интерфейс для соседних сервисов контура ([shared/agent_events.py:1-13](shared/agent_events.py:1)). События доставляются по HTTP, не напрямую по Temporal.

6. **Режим dispatch для разработки использует `openhands-resolver.yml`** ([shared/develop.py:39](shared/develop.py:39)) — workflow файл в репозитории-цели для режима `workflow_dispatch`.

7. **GitHub dispatch доступен через `worker/github_client.py::dispatch_workflow`** ([worker/github_client.py:438-457](worker/github_client.py:438)) — запускает workflow репозитория через GitHub Actions API.

## Что НЕ найдено

1. **В `poh-issue-agents` нет workflow файлов для автоматического запуска PR-ревью** — ни `pr-review.yml`, ни другого механизма, который бы триггерил внешний агент для ревью PR.

2. **Логика перехода в фазу `PR_REVIEW` есть** ([worker/workflows.py:1640](worker/workflows.py:1640)), но она ожидает входящее событие `AgentEvent` от внешнего агента, а не инициирует ревью самостоятельно.

3. **В соседних репозиториях workspace (poh-pr-agents и др.) workflow файлы не проверены** — индекс доступен только для текущего репо.

## Архитектурные наблюдения

1. **Контур ожидает события от EXTERNAL инициатора** (PR-Agent, PR-Closer, CI) для перехода в фазу `PR_REVIEW` ([shared/lifecycle.py:35](shared/lifecycle.py:35)). Это означает, что запуск ревью делегирован внешнему сервису.

2. **Вебхук `/agent-event` — единственная точка входа для событий от внешних агентов** ([webhook/main.py:317](webhook/main.py:317)). Без соответствующего workflow в соседнем сервисе (poh-pr-agents?) события не приходят.

3. **`poh-issue-agents` не имеет замкнутого контура для self-improvement** — PR, открываемые агентом в этом же репо, не проходят автоматическое ревью, так как нет workflow файла, который бы инициировал этот процесс.

# Открытые вопросы

1. **В каком репозитории должны лежать workflow файлы `pr-review.yml` и `openhands-resolver.yml`?** В description указан `poh-demo-checkout`, но индекс не подтвердил наличие этих файлов в доступных репо workspace.

2. **Какой внешний агент (PR-Agent?) должен отправлять события на `/agent-event` и где его код?** Упомянутый в description `poh-pr-agents` не проверен из-за ограничений доступа.

3. **Существует ли в `poh-pr-agents` или другом репозитории логика, которая отправляет AgentEvent для фазы `PR_REVIEW`?** Без этого круг правок в `poh-issue-agents` не запускается.

4. **Где определён секрет `ISSUE_AGENT_URL` (упомянут в description)?** В коде `poh-issue-agents` найден только `AGENT_EVENT_SECRET` для вебхука.

5. **Какая логика связывает PR с его Issue для запуска ревью?** В `shared/agent_events.py` есть корреляция по `root_issue`, `Closes #N` и имени ветки ([shared/agent_events.py:171-192](shared/agent_events.py:171)), но не найдено место, где это вызывается для PR.

# Диалог

## Ход 1: Overview репозитория
**Инструмент:** `get_overview(repo="poh-issue-agents")`
**Результат:** Получена архитектура репозитория: 323 файла, основной модуль `worker`, утилиты в `shared`, webhook для GitHub событий. Hotspot в `worker/workflows.py` (health=1).

## Ход 2: Поиск workflow файлов
**Инструмент:** `search_codebase(mode="path", query="github workflows workflow.yml .github")`
**Результат:** Путь не найден через индекс. Проверен через `ls -la .github/workflows/` — только `tests.yml`.

## Ход 3: Чтение tests.yml
**Инструмент:** `Read(.github/workflows/tests.yml)`
**Результат:** Подтверждено: workflow только для pytest. Нет pr-review или openhands-resolver.

## Ход 4: Поиск логики круга правок
**Инструмент:** `search_codebase(mode="concept", query="pr-review openhands-resolver pr_closing PR_FIX workflow")`
**Результат:** Найдены ключевые модули: `worker/activities.py::run_pr_fix_round`, `shared/pr_closing.py`, `worker/workflows.py::IssueLifecycle::_phase_pr_review`.

## Ход 5: Контекст pr_closing.py
**Инструмент:** `get_context(targets=["shared/pr_closing.py"], include=["skeleton"])`
**Результат:** Модуль круга правок. Использует `PR_FIX_ENABLED`/`PR_FIX_MAX_ROUNDS`, константу `NEEDS_HUMAN_PR = "needs-human:pr"`. Чистый модуль без сети/Temporal/GitHub.

## Ход 6: Символ run_pr_fix_round
**Инструмент:** `get_symbol("worker/activities.py::run_pr_fix_round")`
**Результат:** Полный код функции круга правок. Запускает агент в контейнере, читает `.verdict.md`, пушит правки через `github_client.push_fixes`, оставляет комментарий с `/review`.

## Ход 7: Символ _phase_pr_review
**Инструмент:** `get_symbol("worker/workflows.py::IssueLifecycle::_phase_pr_review")`
**Результат:** Фаза pr-review в воркфлоу. Проверяет `deadlines.pr_fix_enabled`, запускает `run_pr_fix_round` в цикле, ждёт `AgentEvent` от ревью после каждого круга.

## Ход 8: Поиск Deadlines
**Инструмент:** `search_codebase(mode="symbol", query="deadlines pr_fix_enabled pr_fix_max_rounds")`
**Результат:** Найден `shared/workflow_types.py::Deadlines` с полями `pr_fix_enabled: bool = True`, `pr_fix_max_rounds: int = 3`.

## Ход 9: Контекст agent_events.py
**Инструмент:** `get_context(targets=["shared/agent_events.py"], include=["skeleton"])`
**Результат:** Контракт для событий от внешних агентов (PR-Agent, PR-Closer, CI). Доставка по HTTP с подписью, не напрямую по Temporal. Публичный интерфейс с функцией корреляции.

## Ход 10: Контекст webhook/main.py
**Инструмент:** `get_context(targets=["webhook/main.py"], include=["skeleton"])`
**Результат:** Webhook `/agent-event` принимает события от внешних агентов. Проверяет подпись через `AGENT_EVENT_SECRET`. Функция `verify_agent_signature` требует секрет, иначе 503.

## Ход 11: Поиск dispatch_workflow
**Инструмент:** `search_codebase(mode="concept", query="ISSUE_AGENT_URL AGENT_EVENT_SECRET webhook dispatch")`
**Результат:** Найден `worker/github_client.py::dispatch_workflow` — запуск workflow через GitHub Actions API. Упомянут `shared/develop.py::DISPATCH` режим.

## Ход 12: Символ dispatch_workflow
**Инструмент:** `get_symbol("worker/github_client.py::dispatch_workflow")`
**Результат:** Функция для dispatch workflow репозитория через `workflow_dispatch`. Формирует URL к GitHub API.

## Ход 13: Контекст develop.py
**Инструмент:** `get_context(targets=["shared/develop.py"], include=["skeleton"])`
**Результат:** Два режима: `local` (контейнер на своём сервере) и `dispatch` (GitHub Actions). `DEFAULT_WORKFLOW_FILE = "openhands-resolver.yml"` для режима dispatch.

## Ход 14: Контекст lifecycle.py
**Инструмент:** `get_context(targets=["shared/lifecycle.py"], include=["skeleton"])`
**Результат:** Модель фаз жизненного цикла. `PR_REVIEW = "pr-review"`, инициируется `EXTERNAL` (PR-Agent, PR-Closer, CI). Таблица переходов `TRANSITIONS`.

## Ход 15: Поиск переходов в PR_REVIEW
**Инструмент:** `search_codebase(mode="symbol", query="PR_REVIEW transition pr_open")`
**Результат:** Найдены символы `transition`, `Transition`, `_phase_pr_review`, `PR_OPEN`, `PR_REVIEW`. Подтверждает структуру переходов, но не даёт места инициации ревью.

## Ограничения

- Индекс доступен только для репозитория `poh-issue-agents`. Соседние репозитории (`poh-pr-agents`, `poh-demo-checkout`) не проверены из-за ограничений файловой системы.
- Некоторые функции слишком большие (например, `worker/activities.py::trigger_openhands_resolver`), их body был omitted из-за размера.
- Поиск по `poh-demo-checkout` не дал результатов в индексе `poh-issue-agents` — упоминания только в комментариях (например, `poh-demo-checkout#42` в `shared/workflow_types.py`).


---
session: rw-analysis-po-helper-org__poh-issue-agents-103
workspace: contour
turns: 24
started: 2026-08-21T05:40:20Z
finished: 2026-08-21T05:42:44Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `a41f569f0381` | 0 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 0 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "po-helper-org/poh-issue-agents"
}
```

**Ответ:**

{
  "error": "Unknown repo 'po-helper-org/poh-issue-agents'. Available: ['poh-bft-writer', 'poh-cortex', 'poh-helper', 'poh-infra', 'poh-issue-agents', 'poh-memory-engine', 'poh-pr-agents', 'poh-scheduller', 'poh-sprint-agents']",
  "remedy": "Call list_repos to see the valid repo aliases, or omit the 'repo' argument to use the default repository."
}

## Ход 2 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1",
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
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
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
  "query": "github workflows workflow.yml .github",
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

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "path",
  "query": ".github/workflows",
  "repo": "poh-pr-agents"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
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
  "mode": "concept",
  "query": "pr-review openhands-resolver pr_closing PR_FIX workflow",
  "repo": "poh-issue-agents"
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
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "snippet": "етки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсю",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "shared/develop.py",
      "confidence_score": 0.99
    },
    {
      "title": "Symbol: worker.activities.run_pr_fix_round",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_pr_fix_round\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_pr_fix_round(repo: str, pr_number: int, round",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_pr_fix_round",
      "file": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.96
    },
    {
      "title": "Symbol: worker.worker.main",
      "page_type": "symbol_spotlight",
      "snippet": "evel references, not confirmed call sites.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bf",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/worker.py::main",
      "file": "worker/worker.py",
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
      "path": "worker/activities.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "worker/worker.py"
    },
    {
      "path": "shared/pr_closing.py"
    },
    {
      "path": "openhands/Dockerfile"
    }
  ]
}

## Ход 6 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/pr_closing.py"
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
    "shared/pr_closing.py": {
      "target": "shared/pr_closing.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/pr_closing.py",
        "summary": "Доведение PR по замечаниям ревью — круг правок (точка передачи H3→H4)."
      },
      "hotspot": false,
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
        "tokens": 1432,
        "full_tokens": 1812,
        "pct_of_full": 79.0,
        "bodies_kept": [
          "max_rounds",
          "build_task",
          "round_comment",
          "settled_comment",
          "exhausted_comment"
        ],
        "text": "\"\"\"Доведение PR по замечаниям ревью — круг правок (точка передачи H3→H4).\n\nPR-Agent публикует ревью и останавливается: доводить код до соответствия\nзамечаниям — не его работа. До сих пор это делал человек, и именно здесь контур\nпереставал быть автономным.\n\nКруг ведёт тот же цикл, который уже владеет состоянием задачи: он стоит в фазе\n`pr-review` и ждёт. Отдельный сервис потребовал бы второй копии всего — клона,\nраннера, прогона тестов, пуша — и ещё одного канала докладов обратно.\n\nПризнак «замечаний нет» — ПУСТОЙ ДИФФ после прогона агента.\n\nЭто главное решение модуля. Разметку ревью можно было бы разбирать и считать,\nкакие пункты блокирующие, — но тогда контур зависел бы от формата чужого\nинструмента, который меняется без предупреждения. Вместо этого агенту отдаётся\nтекст ревью и правило «исправь то, что требует исправления; если по существу\nнечего — не меняй ничего». Пустой дифф — это его вердикт, выраженный делом.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub.\n\"\"\"\n\nimport os\n\n# Потолок кругов. Правило R8 протокола: доведение — не разработка, у него есть\n# предел. Агент, который третий раз не сходится с ревью, дальше не сойдётся —\n# он спорит с ним, а не исправляет. Такой PR уходит человеку.\nDEFAULT_MAX_ROUNDS = 3\n\n# Метка очереди к человеку из общего словаря контура.\nNEEDS_HUMAN_PR = \"needs-human:pr\"\n\n# Команда, которой круг просит PR-Agent перепроверить. Комментарий от живого\n# пользователя события порождает, поэтому цикл пишет её своим токеном.\nREVIEW_COMMAND = \"/review\"\n... 5 lines (35-39)\nVERDICT_FILE = \".verdict.md\"\n\n\ndef max_rounds() -> int:\n    raw = os.environ.get(\"PR_FIX_MAX_ROUNDS\", \"\").strip()\n    try:\n        value = int(raw) if raw else DEFAULT_MAX_ROUNDS\n    except ValueError:\n        return DEFAULT_MAX_ROUNDS\n    return value if value > 0 else DEFAULT_MAX_ROUNDS\n\n\ndef enabled() -> bool:\n    \"\"\"Пусто — включено. Явное `0` оставляет PR человеку сразу после ревью.\"\"\"\n    return os.environ.get(\"PR_FIX_ENABLED\", \"\").strip().lower() not in {\"0\", \"false\", \"no\", \"off\"}\n\n\ndef task_slug(repo: str, pr_number: int) -> str:\n    return f\"prfix-{repo.replace('/', '__')}-{pr_number}\"\n\n\ndef build_task(pr_number: int, *, review: str, round_number: int, max_rounds_: int) -> str:\n    \"\"\"Постановка круга правок.\n\n    Замечания отдаются ДОСЛОВНО: пересказ своими словами — лишнее звено, в\n    котором теряется именно то, что ревьюер счёл важным.\n    \"\"\"\n    return f\"\"\"# Довести PR #{pr_number} по замечаниям ревью\n\nКруг {round_number} из {max_rounds_}.\n\n## Замечания ревьюера\n\n{review.strip() or \"(текст ревью пуст)\"}\n\n## Что делать\n\nСначала **реши по каждому замечанию, стоит ли оно правки**. Автоматический\nревьюер находит к чему придраться всегда — это его работа. Твоя работа —\nотличить то, что улучшит код, от того, что просто сожжёт круг.\n\n**Исправлять:** неверное поведение, необработанный случай, расхождение с\nтребованиями задачи, отсутствующий тест на новую логику, настоящая уязвимость.\n... 23 lines (83-105)\n\n\ndef round_comment(pr_number: int, *, round_number: int, max_rounds_: int,\n                  verdict: str = \"\") -> str:\n    # Команда ПЕРВОЙ строкой — это не оформление, а условие срабатывания:\n    # перепроверка запускается по `startsWith(comment.body, '/review')`, той же\n    # конвенцией, что и команды в Issue (`shared/commands.parse_command`).\n    # Команда в конце текста читается человеком как просьба, а автоматикой — никак:\n    # круг вносил правки и ждал ревью, которое не начиналось.\n    body = (f\"{REVIEW_COMMAND}\\n\\n\"\n            f\"🔧 Внёс правки по замечаниям ревью (круг {round_number} из \"\n            f\"{max_rounds_}) и прошу перепроверить.\")\n    if verdict.strip():\n        body += (\"\\n\\n<details><summary>Разбор замечаний</summary>\\n\\n\"\n                 f\"{verdict.strip()}\\n\\n</details>\")\n    return body\n\n\ndef settled_comment(round_number: int, verdict: str = \"\") -> str:\n    \"\"\"Итог: правок не потребовалось. Разбор публикуется вместе с итогом.\n\n    Без разбора этот комментарий означал бы «мы ничего не сделали, поверьте на\n    слово». С ним видно, какие замечания отклонены и почему, — и следующий круг\n    не начнёт спорить о том же заново.\n    \"\"\"\n    body = (\n        \"✅ Круг правок завершён: агент не нашёл в ревью того, что требует \"\n        f\"изменений в коде (кругов пройдено: {round_number}).\\n\\n\"\n        \"PR готов к слиянию и ждёт решения разработчика.\"\n    )\n    if verdict.strip():\n        body += (\"\\n\\n<details><summary>Разбор замечаний</summary>\\n\\n\"\n                 f\"{verdict.strip()}\\n\\n</details>\")\n    return body\n\n\ndef exhausted_comment(max_rounds_: int, rounds_done: int | None = None) -> str:\n    \"\"\"Итог, когда довести не удалось.\n\n    Пройденное и потолок — разные числа, и путать их нельзя. Сообщение печатало\n    потолок, и оборвавшийся первый круг выглядел как три круга спора с ревьюером:\n    человек шёл разбирать то, чего не было. Меньше потолка означает, что круг\n    сорвался, — и об этом надо сказать прямо.\n    \"\"\"\n    done = max_rounds_ if rounds_done is None else rounds_done\n    if done < max_rounds_:\n        return (\n            f\"⚠️ Доведение остановлено: круг правок сорвался (пройдено {done} из \"\n            f\"{max_rounds_}).\\n\\n\"\n            \"Дальше нужен человек. Замечания ревью остались в силе, но исправить \"\n            \"их контур не смог — сорвался сам прогон, а не согласие с ревьюером. \"\n            \"Причина — в логе воркера по этой задаче.\"\n        )\n    return (\n        f\"⚠️ Доведение остановлено: пройдено {max_rounds_} кругов правок, а \"\n        \"замечания продолжают появляться.\\n\\n\"\n        \"Дальше нужен человек. Столько кругов — это уже не придирки ревьюера: так \"\n        \"выглядит проблема в самом коде или в том, как устроен репозиторий, и \"\n        ... 3 lines (164-166)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 79.0% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 43.12,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
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
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "worker/activities.py::trigger_openhands_resolver",
    "worker/activities.py::run_pr_fix_round"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/activities.py::trigger_openhands_resolver": {
      "target": "worker/activities.py::trigger_openhands_resolver",
      "type": "symbol",
      "docs": {
        "name": "trigger_openhands_resolver",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.trigger_openhands_resolver",
        "signature": "async def trigger_openhands_resolver(issue: IssueInput) -> int | None",
        "docstring": "Активность Develop: разработка по подготовленному Issue.\n\n    Два режима (`shared/develop.py`). `local` — прогон одноразовым контейнером\n    на своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\n    в GitHub Actions, для репозиториев без стенда.\n\n    Возвращает номер PR (режим `local`) либо None (`dispatch`: результат\n    придёт событием `pr-open`, прогон идёт на чужой стороне).",
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
        "symbol_hint": "Skeleton of the file defining 'trigger_openhands_resolver'. For that symbol's full body call get_symbol('worker/activities.py::trigger_openhands_resolver').",
        "omitted": true
      },
      "episodes": 20
    },
    "worker/activities.py::run_pr_fix_round": {
      "target": "worker/activities.py::run_pr_fix_round",
      "type": "symbol",
      "docs": {
        "name": "run_pr_fix_round",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.run_pr_fix_round",
        "signature": "async def run_pr_fix_round(repo: str, pr_number: int, round_number: int)",
        "docstring": "Один круг правок.\n\n    `True` — правки внесены и запрошена перепроверка. Строка (возможно пустая) —\n    правок не потребовалось, и это её разбор: агент не нашёл в ревью того, что\n    требует изменений в коде. Законный исход, а не сбой; на нём круг и\n    останавливается.\n\n    Разные типы возврата намеренно: «сделали» и «не потребовалось» — разные\n    исходы, и сводить их к булеву значению значило бы потерять объяснение,\n    ради которого разбор и заводился.",
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
        "symbol_hint": "Skeleton of the file defining 'run_pr_fix_round'. For that symbol's full body call get_symbol('worker/activities.py::run_pr_fix_round').",
        "omitted": true
      },
      "episodes": 20
    }
  },
  "_meta": {
    "timing_ms": 394.9,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "a64651acfa50",
        "a64651acfa50",
        "6172dc6bc990"
      ],
      "tokens": 11648,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {},
  "omission_marker": "[repowise#6172dc6bc990: 7 lines omitted (~88 tokens); restore: repowise expand 6172dc6bc990]"
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::run_pr_fix_round",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::run_pr_fix_round",
  "file": "worker/activities.py",
  "name": "run_pr_fix_round",
  "kind": "function",
  "qualified_name": "worker.activities.run_pr_fix_round",
  "signature": "async def run_pr_fix_round(repo: str, pr_number: int, round_number: int)",
  "language": "python",
  "start_line": 1982,
  "end_line": 2047,
  "symbol_start_line": 1982,
  "symbol_end_line": 2047,
  "source": "  1982\tasync def run_pr_fix_round(repo: str, pr_number: int, round_number: int):\n  1983\t    \"\"\"Один круг правок.\n  1984\t\n  1985\t    `True` — правки внесены и запрошена перепроверка. Строка (возможно пустая) —\n  1986\t    правок не потребовалось, и это её разбор: агент не нашёл в ревью того, что\n  1987\t    требует изменений в коде. Законный исход, а не сбой; на нём круг и\n  1988\t    останавливается.\n  1989\t\n  1990\t    Разные типы возврата намеренно: «сделали» и «не потребовалось» — разные\n  1991\t    исходы, и сводить их к булеву значению значило бы потерять объяснение,\n  1992\t    ради которого разбор и заводился.\n  1993\t    \"\"\"\n  1994\t    pr = await asyncio.to_thread(github_client.get_pull, repo, pr_number)\n  1995\t    branch = pr[\"head\"][\"ref\"]\n  1996\t    review = await asyncio.to_thread(github_client.review_text, repo, pr_number)\n  1997\t    task = pr_closing.build_task(pr_number, review=review, round_number=round_number,\n  1998\t                                 max_rounds_=pr_closing.max_rounds())\n  1999\t\n  2000\t    await _run_with_heartbeat(_prfix_prepare, repo, pr_number, branch, task,\n  2001\t                              label=\"prfix:prepare\")\n  2002\t\n  2003\t    slug = pr_closing.task_slug(repo, pr_number)\n  2004\t    await asyncio.to_thread(_reap_runner, slug)\n  2005\t    command = develop.runner_command(\n  2006\t        slug, image=develop.runner_image(),\n  2007\t        volume=develop.workspace_volume(), mount=develop.workspace_mount(),\n  2008\t        network=develop.proxy_network(), home=_runner_home(slug))\n  2009\t    env = {**os.environ, **develop.runner_env(\n  2010\t        os.environ.get(\"ZAI_API_KEY\", \"\"), os.environ.get(\"ZAI_BASE_URL\", \"\"),\n  2011\t        os.environ.get(\"DEVELOP_MODEL\", \"\").strip() or \"openai/glm-4.6\")}\n  2012\t\n  2013\t    def _run() -> None:\n  2014\t        result = subprocess.run(command, env=env, capture_output=True, text=True,\n  2015\t                                timeout=develop.run_timeout())\n  2016\t        if result.returncode != 0:\n  2017\t            tail = ((result.stdout or \"\") + (result.stderr or \"\"))[-1500:]\n  2018\t            raise RuntimeError(f\"круг правок сорвался (код {result.returncode}): {tail}\")\n  2019\t\n  2020\t    await _run_with_heartbeat(_run, label=\"prfix:agent\")\n  2021\t\n  2022\t    _, clone_dir = _prfix_paths(repo, pr_number)\n  2023\t    verdict_path = clone_dir / pr_closing.VERDICT_FILE\n  2024\t    verdict = verdict_path.read_text(encoding=\"utf-8\") if verdict_path.exists() else \"\"\n  2025\t    # Ни разбор, ни постановка круга не уезжают в коммит: они живут в\n  2026\t    # комментарии PR, а не в коде.\n  2027\t    #\n  2028\t    # Постановка опаснее разбора. Она меняется на КАЖДОМ круге — номер круга,\n  2029\t    # накопленный текст ревью, — поэтому пуш всегда видел дифф и всегда\n  2030\t    # докладывал «правки внесены». Исход «замечаний нет, PR готов к merge»\n  2031\t    # становился недостижим: цикл сжигал все три круга и отдавал PR человеку, а\n  2032\t    # настоящий вердикт агента терялся.\n  2033\t    verdict_path.unlink(missing_ok=True)\n  2034\t    (clone_dir / \".task.md\").unlink(missing_ok=True)\n  2035\t\n  2036\t    pushed = await _run_with_heartbeat(\n  2037\t        github_client.push_fixes, repo, str(clone_dir), branch,\n  2038\t        f\"fix(#{pr_number}): правки по замечаниям ревью (круг {round_number})\",\n  2039\t        label=\"prfix:push\")\n  2040\t    if not pushed:\n  2041\t        return verdict or \"\"\n  2042\t\n  2043\t    await asyncio.to_thread(\n  2044\t        github_client.post_comment, repo, pr_number,\n  2045\t        pr_closing.round_comment(pr_number, round_number=round_number,\n  2046\t                                 max_rounds_=pr_closing.max_rounds(), verdict=verdict))\n  2047\t    return True",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 9.17,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "poh-demo-checkout repository specific check pr-review workflow_dispatch",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: shared.workflow_types.UserComment",
      "page_type": "symbol_spotlight",
      "snippet": "кстом обязан ехать ключ\nкомментария. Вебхук доставляет каждое событие ДВАЖДЫ (в истории прогона по\n`poh-demo-checkout#42` сигналов ровно вдвое), и без ключа один вопрос\nчеловека получал бы два ответа.",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::UserComment",
      "file": "shared/workflow_types.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: scripts/demo_e2e.py",
      "page_type": "file_page",
      "snippet": "# scripts/demo_e2e.py\n\n## Overview\n\nАвтономный прогон контура по сценарию демо.\n\nЗаводит Issue на простую доработку и ведёт его по стадиям, проверяя каждую.\nСуществует потому, что модульные тесты не л",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/demo_e2e.py",
      "confidence_score": 0.99
    },
    {
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "snippet": "етки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсю",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "shared/develop.py",
      "confidence_score": 0.98
    },
    {
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "ь «варианты решения» — то есть\nпроектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)\nдаёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`\n→",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "confidence_score": 0.96
    },
    {
      "title": "Repository Overview: poh-issue-agents",
      "page_type": "repo_overview",
      "snippet": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `web",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "poh-issue-agents",
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
      "path": "shared/workflow_types.py"
    },
    {
      "path": "scripts/demo_e2e.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "shared/bft.py"
    },
    {
      "path": "shared/pr_closing.py"
    }
  ]
}

## Ход 10 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/workflow_types.py::UserComment"
}
```

**Ответ:**

{
  "symbol_id": "shared/workflow_types.py::UserComment",
  "file": "shared/workflow_types.py",
  "name": "UserComment",
  "kind": "class",
  "qualified_name": "shared.workflow_types.UserComment",
  "signature": "class UserComment",
  "language": "python",
  "start_line": 16,
  "end_line": 29,
  "symbol_start_line": 16,
  "symbol_end_line": 29,
  "source": "    16\tclass UserComment:\n    17\t    \"\"\"Реплика человека в Issue, доехавшая до цикла сигналом.\n    18\t\n    19\t    Отдельный тип, а не строка с префиксом: вместе с текстом обязан ехать ключ\n    20\t    комментария. Вебхук доставляет каждое событие ДВАЖДЫ (в истории прогона по\n    21\t    `poh-demo-checkout#42` сигналов ровно вдвое), и без ключа один вопрос\n    22\t    человека получал бы два ответа.\n    23\t\n    24\t    `comment_id is None` — реплика от вебхука прежнего поколения, который слал\n    25\t    сигнал одним аргументом. Такую отвечаем без защиты от повтора: молчание\n    26\t    хуже возможного дубля.\n    27\t    \"\"\"\n    28\t    text: str\n    29\t    comment_id: int | None = None",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 9.27,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3167
  }
}

## Ход 11 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "symbol",
  "query": "pr_review workflow pr-fix",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "tests/test_workflow_closed_by_merge.py::_drive_to_pr_review",
      "name": "_drive_to_pr_review",
      "kind": "function",
      "file": "tests/test_workflow_closed_by_merge.py",
      "start_line": 138,
      "end_line": 148,
      "signature": "async def _drive_to_pr_review(env, handle) -> None",
      "qualified_name": "tests.test_workflow_closed_by_merge._drive_to_pr_review",
      "language": "python",
      "score": 17.53,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::run_pr_fix_round",
      "name": "run_pr_fix_round",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 1982,
      "end_line": 2047,
      "signature": "async def run_pr_fix_round(repo: str, pr_number: int, round_number: int)",
      "qualified_name": "worker.activities.run_pr_fix_round",
      "language": "python",
      "score": 15.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_phase_pr_review",
      "name": "_phase_pr_review",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 1640,
      "end_line": 1698,
      "signature": "async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None",
      "qualified_name": "worker.workflows.IssueLifecycle._phase_pr_review",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::PR_REVIEW",
      "name": "PR_REVIEW",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 30,
      "end_line": 30,
      "signature": "PR_REVIEW = \"pr-review\"",
      "qualified_name": "shared.lifecycle.PR_REVIEW",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/pr_closing.py::REVIEW_COMMAND",
      "name": "REVIEW_COMMAND",
      "kind": "constant",
      "file": "shared/pr_closing.py",
      "start_line": 34,
      "end_line": 34,
      "signature": "REVIEW_COMMAND = \"/review\"",
      "qualified_name": "shared.pr_closing.REVIEW_COMMAND",
      "language": "python",
      "score": 15.01,
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
      "path": "tests/test_workflow_closed_by_merge.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "shared/pr_closing.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'pr_review workflow pr-fix'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/workflows.py::IssueLifecycle::_phase_pr_review"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::_phase_pr_review",
  "file": "worker/workflows.py",
  "name": "_phase_pr_review",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle._phase_pr_review",
  "signature": "async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None",
  "language": "python",
  "start_line": 1640,
  "end_line": 1698,
  "symbol_start_line": 1640,
  "symbol_end_line": 1698,
  "source": "  1640\t    async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None:\n  1641\t        \"\"\"Фаза `pr-review`: довести PR по замечаниям, пока они по делу.\n  1642\t\n  1643\t        Круг ведёт цикл, а не отдельный сервис: он уже владеет состоянием\n  1644\t        задачи и стоит здесь же. Отдельный сервис потребовал бы второй копии\n  1645\t        клона, раннера, прогона тестов и пуша — и ещё одного канала докладов.\n  1646\t\n  1647\t        Признак завершения — агент сам сказал, что правок не требуется. Тогда\n  1648\t        активность возвращает разбор (строку), а не `True`.\n  1649\t        \"\"\"\n  1650\t        if not self._pr_number or not deadlines.pr_fix_enabled:\n  1651\t            return await self._phase_park(issue, deadlines)\n  1652\t\n  1653\t        rounds = 0\n  1654\t        verdict = \"\"\n  1655\t        while rounds < deadlines.pr_fix_max_rounds:\n  1656\t            rounds += 1\n  1657\t            try:\n  1658\t                outcome = await workflow.execute_activity(\n  1659\t                    activities.run_pr_fix_round,\n  1660\t                    args=[issue.repo, self._pr_number, rounds],\n  1661\t                    start_to_close_timeout=timedelta(seconds=3600),\n  1662\t                    heartbeat_timeout=timedelta(seconds=300),\n  1663\t                    # Круг недетерминирован и стоит денег: повтор инициирует\n  1664\t                    # следующая итерация, а не политика ретраев.\n  1665\t                    retry_policy=RetryPolicy(maximum_attempts=1),\n  1666\t                )\n  1667\t            except Exception as e:\n  1668\t                workflow.logger.warning(\"круг правок сорвался: %s\", _failure_reason(e))\n  1669\t                break\n  1670\t            if outcome is not True:\n  1671\t                verdict = outcome or \"\"\n  1672\t                await workflow.execute_activity(\n  1673\t                    activities.finish_pr_fixing,\n  1674\t                    args=[issue.repo, self._pr_number, rounds, True, verdict],\n  1675\t                    start_to_close_timeout=timedelta(seconds=60),\n  1676\t                    retry_policy=RetryPolicy(maximum_attempts=3),\n  1677\t                )\n  1678\t                return await self._phase_park(issue, deadlines)\n  1679\t            # Правки внесены и перепроверка запрошена. Ждём нового доклада\n  1680\t            # ревью: без него следующий круг работал бы по устаревшему тексту.\n  1681\t            signal = await self._wait_for_signal(timedelta(minutes=30))\n  1682\t            if isinstance(signal, AgentEvent):\n  1683\t                # Не всякое событие — это «ревью перепроверило». PR могли влить\n  1684\t                # или вернуть в разработку, и тогда доводить больше нечего:\n  1685\t                # фазу двигает событие, а круг заканчивается.\n  1686\t                if agent_events.target_phase(signal) != lifecycle.PR_REVIEW:\n  1687\t                    return await self._agent_event(signal)\n  1688\t                continue\n  1689\t            if signal is None:\n  1690\t                break\n  1691\t\n  1692\t        await workflow.execute_activity(\n  1693\t            activities.finish_pr_fixing,\n  1694\t            args=[issue.repo, self._pr_number, rounds, False, verdict],\n  1695\t            start_to_close_timeout=timedelta(seconds=60),\n  1696\t            retry_policy=RetryPolicy(maximum_attempts=3),\n  1697\t        )\n  1698\t        return (lifecycle.ESCALATED, \"escalated\", True)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.35,
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
  "mode": "symbol",
  "query": "deadlines pr_fix_enabled pr_fix_max_rounds",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/pr_closing.py::enabled",
      "name": "enabled",
      "kind": "function",
      "file": "shared/pr_closing.py",
      "start_line": 52,
      "end_line": 54,
      "signature": "def enabled() -> bool",
      "qualified_name": "shared.pr_closing.enabled",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::Deadlines",
      "name": "Deadlines",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 49,
      "end_line": 106,
      "signature": "class Deadlines",
      "qualified_name": "shared.workflow_types.Deadlines",
      "language": "python",
      "score": 45.36,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/decomposition.py::enabled",
      "name": "enabled",
      "kind": "function",
      "file": "shared/decomposition.py",
      "start_line": 57,
      "end_line": 60,
      "signature": "def enabled() -> bool",
      "qualified_name": "shared.decomposition.enabled",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/develop.py::enabled",
      "name": "enabled",
      "kind": "function",
      "file": "shared/develop.py",
      "start_line": 98,
      "end_line": 106,
      "signature": "def enabled() -> bool",
      "qualified_name": "shared.develop.enabled",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/repowise.py::enabled",
      "name": "enabled",
      "kind": "function",
      "file": "shared/repowise.py",
      "start_line": 58,
      "end_line": 64,
      "signature": "def enabled() -> bool",
      "qualified_name": "shared.repowise.enabled",
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
      "path": "shared/pr_closing.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "shared/decomposition.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "shared/repowise.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'deadlines pr_fix_enabled pr_fix_max_rounds'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "shared/workflow_types.py::Deadlines"
}
```

**Ответ:**

{
  "symbol_id": "shared/workflow_types.py::Deadlines",
  "file": "shared/workflow_types.py",
  "name": "Deadlines",
  "kind": "class",
  "qualified_name": "shared.workflow_types.Deadlines",
  "signature": "class Deadlines",
  "language": "python",
  "start_line": 49,
  "end_line": 106,
  "symbol_start_line": 49,
  "symbol_end_line": 106,
  "source": "    49\tclass Deadlines:\n    50\t    \"\"\"Сроки ожиданий (правило R3: каждая парковка имеет дедлайн).\n    51\t\n    52\t    Едут в воркфлоу отдельной activity, а не читаются из окружения прямо в\n    53\t    коде воркфлоу: результат activity лежит в истории, поэтому реплей после\n    54\t    смены конфигурации возьмёт то же значение, что и первый прогон. Прочитай\n    55\t    воркфлоу os.environ напрямую — изменённая переменная дала бы другой таймер\n    56\t    при воспроизведении и уронила бы прогон недетерминизмом.\n    57\t    \"\"\"\n    58\t    human_decision_hours: int = 72   # ожидание research-me / bug-me\n    59\t    clarification_hours: int = 48    # ответ на уточняющий вопрос intake gate\n    60\t    build_decision_hours: int = 72   # ожидание build-me после аналитики\n    61\t    # Боковые фазы (spam, duplicate, answered, skipped, escalated, failed) —\n    62\t    # не тупики: человек может вернуть Issue в работу. Но и не вечная сессия.\n    63\t    side_state_hours: int = 168      # неделя на возврат из бокового состояния\n    64\t    # Парковаться ли на `ready-for-dev` вообще. Живёт здесь, а не отдельным\n    65\t    # чтением окружения в воркфлоу, ровно по причине из docstring: значение\n    66\t    # обязано лежать в истории, иначе переключённый посреди прогона тумблер\n    67\t    # уронил бы реплей недетерминизмом.\n    68\t    #\n    69\t    # False (умолчание) — протокол в чистом виде: H1 отдаёт задачу человеку, и\n    70\t    # разработку начинает его решение `build-me`. True — контур замкнут и идёт\n    71\t    # от Issue до PR без единого касания.\n    72\t    develop_autostart: bool = False\n    73\t    # Парковаться ли на `classified` — то есть ждать ли решения человека о\n    74\t    # запуске аналитики (`research-me` / `bug-me`).\n    75\t    #\n    76\t    # Парковок на основном пути ровно две, и снимаются они РАЗНЫМИ тумблерами:\n    77\t    # эта — перед дорогой аналитикой, `develop_autostart` — перед разработкой.\n    78\t    # Один общий тумблер не годится: «пусть сам исследует, но код я запущу\n    79\t    # руками» — рабочий режим, а не половинчатая настройка. Замкнутый контур —\n    80\t    # это обе включённые.\n    81\t    research_autostart: bool = False\n    82\t    # Доведение PR по замечаниям ревью. Живёт здесь по той же причине, что и\n    83\t    # остальное: значение обязано лежать в истории, иначе переключённый посреди\n    84\t    # прогона тумблер уронил бы реплей недетерминизмом.\n    85\t    pr_fix_enabled: bool = True\n    86\t    # Потолок кругов. Больше трёх — это уже не придирки ревьюера: так выглядит\n    87\t    # проблема в самом коде, и лечится она разбором, а не следующим кругом.\n    88\t    pr_fix_max_rounds: int = 3\n    89\t    # Разбивать ли задачу на подзадачи перед передачей в разработку.\n    90\t    decompose_enabled: bool = True\n    91\t    # Отписывать ли БФТ вместо свободного advisor-ответа на триаже запроса\n    92\t    # функционала. Живёт здесь по той же причине, что и остальные тумблеры:\n    93\t    # значение обязано лежать в истории, иначе переключённый посреди прогона\n    94\t    # тумблер уронил бы реплей недетерминизмом.\n    95\t    #\n    96\t    # Умолчание здесь означает «не сконфигурировано», а не «выключено в проде»:\n    97\t    # продуктовое умолчание задаёт `read_deadlines`, и там БФТ ВКЛЮЧЁН — гасится\n    98\t    # только явным `BFT_ON_TRIAGE=0`. Так же устроены `develop_autostart` и\n    99\t    # `research_autostart`. Разница между этим полем и переменной окружения\n   100\t    # существует ради одного: `Deadlines()` в тестах не должен незаметно\n   101\t    # затаскивать в прогон стадию, о которой тест не знает.\n   102\t    bft_on_triage: bool = False\n   103\t    # Сколько реплик человека в припаркованном Issue контур отвечает содержательно.\n   104\t    # Потолок нужен затем же, что и у кругов уточнения: диалог без конца — это\n   105\t    # счёт за модель без конца. Исчерпан — реплики снова просто будят парковку.\n   106\t    followup_max_rounds: int = 10",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 8.02,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3167
  }
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "AgentEvent pr-review workflow_dispatch github actions",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: worker/github_client.py",
      "page_type": "file_page",
      "snippet": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "worker/github_client.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: shared/agent_events.py",
      "page_type": "file_page",
      "snippet": "«событие внешнего агента → факт в жизни Issue».\n\nПубличный интерфейс для соседних сервисов контура (PR-Agent, PR-Closer, CI).\nЭто не общая шина и не общий код: у них свой релизный цикл и своя\nответств",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_events.py",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/review-package` is an infrastruct",
      "relevance_score": 2.918,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/review-package",
      "confidence_score": 0.96
    },
    {
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "snippet": "етки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсю",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "shared/develop.py",
      "confidence_score": 0.95
    },
    {
      "title": "File: worker/workflows.py",
      "page_type": "file_page",
      "snippet": "ssues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- u",
      "relevance_score": 2.842,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py",
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
      "path": "worker/github_client.py"
    },
    {
      "path": "shared/agent_events.py"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "worker/workflows.py"
    }
  ]
}

## Ход 16 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/agent_events.py"
  ]
}
```

**Ответ:**

{
  "targets": {
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
    "timing_ms": 54.16,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 17 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "webhook/main.py"
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
    "timing_ms": 37.75,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 18 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "ISSUE_AGENT_URL AGENT_EVENT_SECRET webhook dispatch",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "snippet": "амкнутым: репозиторий обслуживается целиком\nвнутри стенда, без чужих раннеров и без минут GitHub.\n\n`dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся\nдля репозиториев, где ст",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/develop.py",
      "confidence_score": 1.0
    },
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "lop.py`). `local` — прогон одноразовым контейнером\nна своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\nв GitHub Actions, для репозиториев без стенда.\n\nВозвращает номер PR (режи",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "File: worker/github_client.py",
      "page_type": "file_page",
      "snippet": "list |\n| `get_issue_body` | function | def get_issue_body(repo: str, issue_number: int) -> str |\n| `dispatch_workflow` | function | def dispatch_workflow(repo: str, workflow_file: str, ref: str, input",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "worker/github_client.py",
      "confidence_score": 0.97
    },
    {
      "title": "File: webhook/main.py",
      "page_type": "file_page",
      "snippet": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "webhook/main.py",
      "confidence_score": 0.95
    },
    {
      "title": "File: shared/lifecycle.py",
      "page_type": "file_page",
      "target_path": "shared/lifecycle.py",
      "snippet": "Модель фаз жизненного цикла Issue — единственный источник правды.",
      "relevance_score": 2.431,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.8
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
      "path": "shared/develop.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/github_client.py"
    },
    {
      "path": "webhook/main.py"
    },
    {
      "path": "shared/lifecycle.py"
    }
  ]
}

## Ход 19 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/github_client.py::dispatch_workflow"
}
```

**Ответ:**

{
  "symbol_id": "worker/github_client.py::dispatch_workflow",
  "file": "worker/github_client.py",
  "name": "dispatch_workflow",
  "kind": "function",
  "qualified_name": "worker.github_client.dispatch_workflow",
  "signature": "def dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None",
  "language": "python",
  "start_line": 438,
  "end_line": 457,
  "symbol_start_line": 438,
  "symbol_end_line": 457,
  "source": "   438\tdef dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:\n   439\t    \"\"\"Запускает workflow репозитория-цели через `workflow_dispatch`.\n   440\t\n   441\t    Отсутствующий файл workflow, ветка без него и отключённые Actions — всё это\n   442\t    GitHub возвращает как 404/422, и все три означают одно: прогон НЕ начался.\n   443\t    Поднимаем ошибку с текстом ответа, а не глотаем: цикл на ней уходит в\n   444\t    `failed`, и человек видит причину, вместо Issue, который «уехал в\n   445\t    разработку» и там растворился.\n   446\t    \"\"\"\n   447\t    if _dry_run():\n   448\t        _log.info(\"[DRY_RUN] dispatch %s %s@%s inputs=%s\", repo, workflow_file, ref, inputs)\n   449\t        return\n   450\t    quoted = urllib.parse.quote(workflow_file, safe=\"\")\n   451\t    url = f\"https://api.github.com/repos/{repo}/actions/workflows/{quoted}/dispatches\"\n   452\t    resp = requests.post(url, headers=_auth_headers(repo),\n   453\t                         json={\"ref\": ref, \"inputs\": inputs}, timeout=30)\n   454\t    if resp.status_code >= 400:\n   455\t        raise RuntimeError(\n   456\t            f\"workflow_dispatch {workflow_file}@{ref} в {repo} не принят \"\n   457\t            f\"({resp.status_code}): {resp.text.strip()[:300]}\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.92,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6774
  }
}

## Ход 20 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "symbol",
  "query": "dispatch_workflow",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/github_client.py::dispatch_workflow",
      "name": "dispatch_workflow",
      "kind": "function",
      "file": "worker/github_client.py",
      "start_line": 438,
      "end_line": 457,
      "signature": "def dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None",
      "qualified_name": "worker.github_client.dispatch_workflow",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/develop.py::DISPATCH",
      "name": "DISPATCH",
      "kind": "constant",
      "file": "shared/develop.py",
      "start_line": 34,
      "end_line": 34,
      "signature": "DISPATCH = \"dispatch\"",
      "qualified_name": "shared.develop.DISPATCH",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::IssueInput",
      "name": "IssueInput",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 5,
      "end_line": 12,
      "signature": "class IssueInput",
      "qualified_name": "shared.workflow_types.IssueInput",
      "language": "python",
      "score": 15.83,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::Deadlines",
      "name": "Deadlines",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 49,
      "end_line": 106,
      "signature": "class Deadlines",
      "qualified_name": "shared.workflow_types.Deadlines",
      "language": "python",
      "score": 15.36,
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
      "path": "worker/github_client.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "shared/workflow_types.py"
    }
  ],
  "exact_match": true
}

## Ход 21 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/develop.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/develop.py": {
      "target": "shared/develop.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/develop.py",
        "summary": "Контракт активности Develop — разработка по подготовленному Issue."
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
        "tokens": 1838,
        "full_tokens": 2824,
        "pct_of_full": 65.1,
        "bodies_kept": [
          "enabled",
          "run_timeout",
          "runner_command",
          "proxy_network",
          "dispatch_inputs"
        ],
        "text": "\"\"\"Контракт активности Develop — разработка по подготовленному Issue.\n\nResearch доводит Issue до системных требований и метки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсюда два режима:\n\n`local` (умолчание) — прогон идёт **одноразовым контейнером на своём же\nсервере**. Контур получается замкнутым: репозиторий обслуживается целиком\nвнутри стенда, без чужих раннеров и без минут GitHub.\n\n`dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся\nдля репозиториев, где стенда нет.\n\nПочему отдельный контейнер, а не воркер. Аналитика (`claude -p`) пишет\nдокументы, и её соседство с токенами безобидно. Агент разработки делает другое:\nон ИСПОЛНЯЕТ код репозитория — ставит зависимости, гоняет тесты. Внутри воркера\nэто означало бы выполнение произвольного кода чужого проекта рядом с\nGitHub-токеном и ключом модели. Поэтому прогон живёт минуты в отдельном\nконтейнере, видит только каталог своей задачи и умирает вместе с ней; коммит,\nпуш и PR делает воркер уже после — своими руками и своим токеном.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как\n`shared/lifecycle.py` и `shared/agent_events.py`.\n\"\"\"\n\nimport os\nimport shlex\n\n# --- Режимы ---\n\nLOCAL = \"local\"\nDISPATCH = \"dispatch\"\n\n# Файл workflow в репозитории-цели для режима `dispatch`. Диспатчится по имени\n# файла, а не по имени workflow: имя внутри файла человек меняет свободно,\n# путь — контракт.\nDEFAULT_WORKFLOW_FILE = \"openhands-resolver.yml\"\nDEFAULT_REF = \"main\"\n\n# Метка-индикатор для человека: видно в списке Issue, что задача уехала в\n# разработку, не открывая ни Actions, ни Temporal.\nIN_DEVELOPMENT_LABEL = \"in-development\"\n\nAGENT_NAME = \"openhands\"\n\n# Образ агента разработки и том, который воркер делит с ним. Том именно общий:\n# воркер готовит каталог задачи и читает результат, раннер пишет в него. Через\n# bind-mount это не сделать — путь внутри воркера не существует на хосте.\nDEFAULT_RUNNER_IMAGE = \"poh-openhands-runner:local\"\nDEFAULT_WORKSPACE_VOLUME = \"poh-dev-workspace\"\nDEFAULT_WORKSPACE_MOUNT = \"/workspaces\"\n... 8 lines (54-61)\nRUNNER_UID = 10001\nRUNNER_GID = 10001\n... 5 lines (64-68)\nMCP_CONFIG_DIR = \".openhands\"\nMCP_CONFIG_NAME = \"mcp.json\"\n\n# Потолок прогона. Больше часа — это не «агент думает», это агент застрял, и\n# держать задачу в неопределённости дороже, чем оборвать и сказать об этом.\nDEFAULT_RUN_TIMEOUT_SEC = 2700\n... 9 lines (75-83)\nFOLLOWUPS_FILE = \".followups.md\"\n\n# Потолок находок за прогон. Тридцать «надо бы потом учесть» — это не бэклог, а\n# способ не делать основную работу; и каждый такой Issue контур обработает\n# рекурсивно, то есть за них ещё и заплатит.\nMAX_FOLLOWUPS = 8\n\n\ndef mode() -> str:\n    \"\"\"`local` по умолчанию: стенд самодостаточен, пока явно не сказано иначе.\"\"\"\n    raw = os.environ.get(\"DEVELOP_MODE\", \"\").strip().lower()\n    return DISPATCH if raw == DISPATCH else LOCAL\n\n\ndef enabled() -> bool:\n    \"\"\"Выключатель контура разработки.\n\n    Пусто — включено: демо-контур замкнут по умолчанию, иначе забытая\n    переменная тихо обрывает путь на самом дорогом шаге. Явное `0` оставляет\n    Issue в `ready-for-dev`, то есть в очереди к живому разработчику.\n    \"\"\"\n    raw = os.environ.get(\"DEVELOP_ENABLED\", \"\").strip().lower()\n    return raw not in {\"0\", \"false\", \"no\", \"off\"}\n\n\ndef workflow_file() -> str:\n    return os.environ.get(\"DEVELOP_WORKFLOW_FILE\", \"\").strip() or DEFAULT_WORKFLOW_FILE\n\n\ndef workflow_ref() -> str:\n    return os.environ.get(\"DEVELOP_REF\", \"\").strip() or DEFAULT_REF\n\n\ndef runner_image() -> str:\n    return os.environ.get(\"DEVELOP_RUNNER_IMAGE\", \"\").strip() or DEFAULT_RUNNER_IMAGE\n\n\ndef workspace_volume() -> str:\n    return os.environ.get(\"DEVELOP_WORKSPACE_VOLUME\", \"\").strip() or DEFAULT_WORKSPACE_VOLUME\n\n\ndef workspace_mount() -> str:\n    return os.environ.get(\"DEVELOP_WORKSPACE_MOUNT\", \"\").strip() or DEFAULT_WORKSPACE_MOUNT\n\n\ndef run_timeout() -> int:\n    raw = os.environ.get(\"DEVELOP_TIMEOUT_SEC\", \"\").strip()\n    try:\n        value = int(raw) if raw else DEFAULT_RUN_TIMEOUT_SEC\n    except ValueError:\n        return DEFAULT_RUN_TIMEOUT_SEC\n    return value if value > 0 else DEFAULT_RUN_TIMEOUT_SEC\n\n\ndef task_slug(repo: str, issue_number: int) -> str:\n    \"\"\"Имя каталога задачи в общем томе. Слэш репозитория заменён: это имя\n    каталога, а не путь.\"\"\"\n    return f\"dev-{repo.replace('/', '__')}-{issue_number}\"\n\n\ndef work_branch(issue_number: int) -> str:\n    return f\"feature/{issue_number}-openhands\"\n\n\ndef runner_command(slug: str, *, image: str, volume: str, mount: str,\n                   network: str = \"\", home: str = \"\") -> list[str]:\n    \"\"\"Команда запуска одноразового контейнера.\n\n    `--rm` обязателен: контейнер существует ради одного прогона, и оставлять\n    его — значит копить мусор с ключом модели в переменных окружения.\n\n    Сеть агенту нужна: он ставит зависимости проекта. Секреты внутрь идут\n    ровно два — ключ и адрес модели; GitHub-токена там нет, потому что пушит\n    и открывает PR воркер, а не агент.\n\n    `network` — сеть, в которой раннеру виден MCP-прокси Repowise. Пусто —\n    раннер работает без индекса; это штатный режим, а не отказ.\n\n    `home` — куда переставить домашний каталог. Нужен ровно затем, чтобы агент\n    нашёл конфигурацию MCP: он читает её из `$HOME/.openhands/mcp.json`\n    (спайк FR-16), а общий том смонтирован в другом месте. Переставить одну\n    переменную дешевле, чем оборачивать ENTRYPOINT образа или монтировать\n    отдельный файл, путь которого на хосте воркеру неизвестен.\n... 23 lines (167-189)\n\n\ndef proxy_network() -> str:\n    \"\"\"Сеть docker, в которой раннеру виден MCP-прокси Repowise.\n\n    Пусто — раннер работает без индекса. Это штатный режим: интеграция может\n    быть не поднята вовсе, и разработка от этого останавливаться не должна.\n    \"\"\"\n    return os.environ.get(\"REPOWISE_NETWORK\", \"\").strip()\n\n\ndef reap_command(slug: str) -> list[str]:\n    \"\"\"Снять остаток прошлой попытки. Нет такого контейнера — команда просто\n    вернёт ненулевой код, и это штатно.\"\"\"\n    return [\"docker\", \"rm\", \"-f\", slug]\n\n\ndef runner_env(api_key: str, base_url: str, model: str) -> dict[str, str]:\n    return {\"LLM_API_KEY\": api_key, \"LLM_BASE_URL\": base_url, \"LLM_MODEL\": model}\n\n\ndef dispatch_inputs(issue_number: int, *, branch: str, priority: str = \"\") -> dict[str, str]:\n    \"\"\"Входы прогона для режима `dispatch`. Только строки: `workflow_dispatch`\n    других не принимает.\"\"\"\n    return {\n        \"issue_number\": str(issue_number),\n        \"research_branch\": branch or \"\",\n        \"priority\": priority or \"\",\n    }\n\n\ndef handoff_comment(issue_number: int, *, repo: str, branch: str, where: str) -> str:\n    \"\"\"Комментарий в Issue о старте разработки.\"\"\"\n    ... 11 lines (223-233)\n\n\ndef pr_body(issue_number: int, *, branch: str) -> str:\n    ... 7 lines (237-243)\n\n\ndef parse_followups(text: str) -> list[dict]:\n    \"\"\"Находки из файла агента: заголовок `## …` — название, остальное — тело.\n... 25 lines (248-272)\n\n\ndef followup_body(item: dict, *, parent: int) -> str:\n    \"\"\"Тело SubIssue по находке. Ключ цепочки первой строкой — по нему контур\n    ... 9 lines (277-285)\n\n\ndef quote(command: list[str]) -> str:\n    \"\"\"Команда одной строкой — для лога и сообщений об ошибке.\"\"\"\n    return \" \".join(shlex.quote(part) for part in command)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 65.1% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 35.89,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 22 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "pr-review workflow file pr_agent reviewer",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/review-package` is an infrastruct",
      "relevance_score": 3.015,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/review-package",
      "confidence_score": 1.0
    },
    {
      "title": "File: shared/pr_closing.py",
      "page_type": "file_page",
      "snippet": "# shared/pr_closing.py\n\n## Overview\n\nДоведение PR по замечаниям ревью — круг правок (точка передачи H3→H4).\n\nPR-Agent публикует ревью и останавливается: доводить код до соответствия\nзамечаниям — не ег",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "shared/pr_closing.py",
      "confidence_score": 0.99
    },
    {
      "title": "File: shared/lifecycle.py",
      "page_type": "file_page",
      "snippet": "_FOR_DEV = \"ready-for-dev\" |\n| `IN_DEVELOPMENT` | constant | IN_DEVELOPMENT = \"in-development\" |\n| `PR_OPEN` | constant | PR_OPEN = \"pr-open\" |\n| `PR_REVIEW` | constant | PR_REVIEW = \"pr-review\" |\n| `",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "shared/lifecycle.py",
      "confidence_score": 0.97
    },
    {
      "title": "Symbol: tests.test_estimate_report.test_pipe_in_unit_text_does_not_break_the_table",
      "page_type": "symbol_spotlight",
      "snippet": "где встречаются `|`\nи переводы строк. Без экранирования таблица в комментарии разъезжается.\nПоймано pr_agent на живом PR.\n\n## Where it is used\n\n1 file imports the module that defines it. These are imp",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_report.py::test_pipe_in_unit_text_does_not_break_the_table",
      "file": "tests/test_estimate_report.py",
      "confidence_score": 0.95
    },
    {
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "target_path": "shared/develop.py",
      "snippet": "Контракт активности Develop — разработка по подготовленному Issue.",
      "relevance_score": 2.461,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.82
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
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    },
    {
      "path": "shared/pr_closing.py"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "tests/test_estimate_report.py"
    },
    {
      "path": "shared/develop.py"
    }
  ]
}

## Ход 23 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/lifecycle.py"
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
        "text": "\"\"\"Модель фаз жизненного цикла Issue — единственный источник правды.\n\nСегодня состояние Issue размазано по четырём независимым представлениям (метки,\nпеременные воркфлоу, комментарии, Event History), и ни одно не покрывает путь\nдальше приоритизации. Этот модуль вводит один перечень фаз и одну таблицу\nпереходов; из них выводятся значения query, метки в GitHub, search attribute и\nстроки таймлайна. Иначе каждая подзадача эпика заведёт свои названия, и\nтрассировка будет собирать таймлайн из несовместимых кусков.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как `estimation.py`.\nЛогика состояний проверяется напрямую, а не через прогон воркфлоу.\n\nИменование согласовано с уже внедрёнными словарями: namespace через двоеточие,\nкак `needs-human:*` и `run:*`/`done:*` (протокол агентов v1, задачи #30 и #33).\nФаза в GitHub — метка `phase:<имя>`.\n\"\"\"\n\nfrom dataclasses import dataclass\n\n# --- Основной путь: от создания до прода ---\n\nCREATED = \"created\"\nCLASSIFIED = \"classified\"\nBUSINESS_ANALYSIS = \"business-analysis\"\nSYSTEM_REQUIREMENTS = \"system-requirements\"\nGROOMED = \"groomed\"\nREADY_FOR_DEV = \"ready-for-dev\"\nIN_DEVELOPMENT = \"in-development\"\nPR_OPEN = \"pr-open\"\nPR_REVIEW = \"pr-review\"\nMERGED = \"merged\"\nTESTING = \"testing\"\nRELEASED = \"released\"\n\n# --- Боковые состояния: сегодня существуют де-факто, но нигде не названы ---\n\nSPAM = \"spam\"                # intake gate распознал спам, issue закрыт\nDUPLICATE = \"duplicate\"      # дубликат: решение о закрытии за человеком\nANSWERED = \"answered\"        # классификация закрыла содержательным ответом\nSKIPPED = \"skipped\"          # предфильтр: бот или security-sensitive\nESCALATED = \"escalated\"      # ушло человеку (needs-human:*)\nFAILED = \"failed\"            # стадия сорвалась, нужен разбор\nCANCELLED = \"cancelled\"      # снято с обработки решением человека\n\n# Кто инициирует переход. Различать обязательно: «ждём агента» и «ждём человека» —\n# это разные состояния для того, кто смотрит на очередь.\nAGENT = \"agent\"        # сам Issue-Agent по завершении своей стадии\nHUMAN = \"human\"        # метка или команда человека\nEXTERNAL = \"external\"  # PR-Agent, PR-Closer, CI — внешняя система контура\n\n\n@dataclass(frozen=True)\nclass Transition:\n    ... 8 lines (54-61)\nTERMINAL = frozenset({RELEASED, CANCELLED})\n... 7 lines (63-69)\nTRANSITIONS: dict[str, tuple[Transition, ...]] = {\n    CREATED: (\n        Transition(CLASSIFIED, AGENT, \"триаж завершён\"),\n        Transition(SKIPPED, AGENT, \"предфильтр: бот или security-sensitive\"),\n        Transition(SPAM, AGENT, \"intake gate: спам\"),\n        # Дедуп и advisor-ответ — шаги ВНУТРИ триажа, поэтому их исход виден из\n        # `created`, а не только из `classified`: до конца триажа Issue ещё не\n        # классифицирован формально.\n        Transition(DUPLICATE, AGENT, \"duplicate-check\"),\n        Transition(ANSWERED, AGENT, \"advisor:consultation / existing-functionality\"),\n        Transition(ESCALATED, AGENT, \"не удалось сузить запрос\"),\n        Transition(FAILED, AGENT, \"сбой стадии\"),\n        ... 129 lines (82-210)\n\nPHASES: tuple[str, ...] = tuple(TRANSITIONS)\n\n# Метка фазы в GitHub. Инвариант: одна фаза — ровно одна метка `phase:*`, при\n# переходе предыдущая снимается. Без этого по меткам нельзя восстановить\n# состояние: два `phase:*` на Issue означали бы противоречие, а не историю.\nPHASE_PREFIX = \"phase:\"\n\n# Мост от значений query `stage` (#29) к фазам. Нужен на время перехода: пока\n# `IssueLifecycle` линейный (#36 ещё не сделана), стадия — единственное, что\n# воркфлоу знает о себе.\nSTAGE_TO_PHASE: dict[str, str] = {\n    \"intake\": CREATED,\n    \"classify\": CREATED,\n    \"duplicate-check\": CLASSIFIED,\n    \"priority\": CLASSIFIED,\n    \"awaiting-human-decision\": CLASSIFIED,\n    \"analysis\": BUSINESS_ANALYSIS,\n    \"bug\": READY_FOR_DEV,\n    \"awaiting-build-decision\": READY_FOR_DEV,\n    \"done\": READY_FOR_DEV,\n    \"skipped\": SKIPPED,\n    \"spam\": SPAM,\n    ... 17 lines (234-250)\n\n\nclass InvalidTransition(ValueError):\n    \"\"\"Недопустимый переход — ошибка, а не молчаливая перезапись фазы.\n\n    Молчаливая запись любой фазы поверх любой означала бы, что модель ничего не\n    гарантирует: Issue оказывался бы в состоянии, из которого не выводится ни\n    предыстория, ни следующий шаг.\n    \"\"\"\n\n\ndef phase_label(phase: str) -> str:\n    return f\"{PHASE_PREFIX}{phase}\"\n\n\ndef phase_from_labels(labels: list[str]) -> str | None:\n    \"\"\"Фаза по набору меток Issue, иначе None.\n\n    Инвариант «одна фаза — одна метка» проверяется здесь же: две метки `phase:*`\n    означают противоречие, и мы отказываемся угадывать, какая из них настоящая.\n    \"\"\"\n    found = [name[len(PHASE_PREFIX):].lower() for name in labels\n             if name.lower().startswith(PHASE_PREFIX)]\n    known = [name for name in found if name in TRANSITIONS]\n    if len(known) != 1:\n        return None\n    return known[0]\n\n\ndef is_terminal(phase: str) -> bool:\n    return phase in TERMINAL\n\n\ndef allowed(phase: str) -> tuple[Transition, ...]:\n    \"\"\"Переходы, возможные из фазы. Неизвестная фаза — ошибка модели.\"\"\"\n    ... 3 lines (286-288)\n\n\ndef can(source: str, target: str) -> bool:\n    return any(t.to == target for t in allowed(source))\n\n\ndef transition(source: str, target: str) -> Transition:\n    \"\"\"Переход или InvalidTransition с перечнем допустимых — сообщение должно\n    само говорить, что было возможно вместо этого.\"\"\"\n    for candidate in allowed(source):\n        if candidate.to == target:\n            return candidate\n    options = \", \".join(t.to for t in allowed(source)) or \"—\"\n    raise InvalidTransition(\n        f\"переход {source} → {target} не предусмотрен; допустимо: {options}\")\n\n\ndef initiator(source: str, target: str) -> str:\n    return transition(source, target).initiator\n\n\ndef reachable_from(start: str = CREATED) -> set[str]:\n    \"\"\"Фазы, достижимые из start. Используется тестом полноты: фаза, до которой\n    ... 10 lines (312-321)\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 41.8% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 49.69,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 24 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "symbol",
  "query": "PR_REVIEW transition pr_open",
  "repo": "poh-issue-agents"
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
      "score": 47.52,
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
      "score": 47.52,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::_phase_pr_review",
      "name": "_phase_pr_review",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 1640,
      "end_line": 1698,
      "signature": "async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None",
      "qualified_name": "worker.workflows.IssueLifecycle._phase_pr_review",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::PR_OPEN",
      "name": "PR_OPEN",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 29,
      "end_line": 29,
      "signature": "PR_OPEN = \"pr-open\"",
      "qualified_name": "shared.lifecycle.PR_OPEN",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/lifecycle.py::PR_REVIEW",
      "name": "PR_REVIEW",
      "kind": "constant",
      "file": "shared/lifecycle.py",
      "start_line": 30,
      "end_line": 30,
      "signature": "PR_REVIEW = \"pr-review\"",
      "qualified_name": "shared.lifecycle.PR_REVIEW",
      "language": "python",
      "score": 15.01,
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
      "path": "shared/lifecycle.py"
    },
    {
      "path": "worker/workflows.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'PR_REVIEW transition pr_open'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}
