# Итог

1. **Точка вызова sysreq-стадии** — `worker/activities.py:_fnr_stages` (строки 779-780): стадия `"sysreq"` вызывает промпт `/fnr-system-requirements` с входом `{FNR_DIR}/concept.md` и ожидает артефакт `{FNR_DIR}/system_requirements.md`. Вызов идёт через `run_fnr_stage` → `_fnr_stage` → `_run_claude`.

2. **Точка встраивания в Docker** — `worker/Dockerfile:54-55`: `COPY .claude/skills /root/.claude/skills` и `COPY .claude/commands /root/.claude/commands`. Именно сюда попадают скиллы и команды при сборке образа воркера.

3. **Артефакты sysreq-стадии в текущем репозитории**:
   - `.claude/skills/system-analyst-sysreq/SKILL.md` (16KB)
   - `.claude/skills/system-analyst-sysreq/examples/ideal_system_requirements.md` (25KB)
   - `.claude/skills/system-analyst-sysreq/resources/sysreq_validation_checklist.md` (10KB)
   - `.claude/commands/fnr-system-requirements.md` (12KB)

4. **Контракт вызова не меняется** — `worker/activities.py:run_fnr_stage` запускает `claude -p /fnr-system-requirements <concept.md>`. Меняется только источник промпта/скилла (из внешнего модуля вместо локальной копии).

5. **CI/CD не задействован** — `.github/workflows/tests.yml` гоняет только pytest без сборки Docker-образов. Сборка происходит локально через `docker compose up --build` (Makefile) или в проде (Dokploy).

6. **Паттернов внешних модулей в проекте нет** — нет git submodules (отсутствует `.gitmodules`), нет vendoring-скриптов, нет упоминаний external dependencies в GitHub workflows.

7. **Связи с другими репозиториями** — workspace содержит `poh-bft-writer`, `poh-cortex`, `poh-helper`, `poh-infra`, `poh-memory-engine`, `poh-pr-agents`, `poh-scheduller`, `poh-sprint-agents`. Связи только через co-change, структурных зависимостей нет.

8. **`fnr-system-requirements` не используется в других репозиториях** — поиск по workspace не нашёл использования этой команды или скилла `system-analyst-sysreq` вне `poh-issue-agents`. Вынос безопасен для других репо.

9. **Константы lifecycle** — `shared/lifecycle.py` содержит `SYSTEM_REQUIREMENTS = "system-requirements"` — это фаза жизненного цикла Issue, а не зависимость от скилла. Не затрагивается выносом.

10. **Кандидаты механизма встраивания** — варианты из issue: git submodule / git subtree / sync-шаг в CI или Dockerfile. Требуется выбор и документация при реализации.

# Открытые вопросы

- Какой механизм встраивания выбрать: git submodule (простое версионирование, но неудобства при клонировании/CI) vs git subtree vs явный sync-шаг в Dockerfile, тянущий тег/коммит `poh-sysreq-agent`?
- Нужно ли публиковать `poh-sysreq-agent` как переиспользуемый npm/pip-подобный пакет, или достаточно файловой синхронизации `.claude/skills` + `.claude/commands`?
- Кто и как согласует изменение версии sysreq-агента перед тем, как оно попадёт в prod-пайплайн issue-агента (ревью промптов = ревью кода)?
- Нужно ли менять `.gitignore` после подключения внешнего модуля (например, исключить из индекса локальную копию sysreq-артефактов)?

# Диалог

**Ход 1:** Получил overview репозитория `poh-issue-agents` — 323 файла, workspace с 7 другими репозиториями, горячие точки в `worker/activities.py`.

**Ход 2:** Изучил `worker/activities.py::run_fnr_stage` — функция запускает одну стадию FNR через `claude -p`, проверяет артефакт, возвращает отчёт. Нашёл `_fnr_stages` с определением всех 5 стадий.

**Ход 3:** Изучил `_fnr_stages` (строки 779-780) — sysreq-стадия вызывает `/fnr-system-requirements {FNR_DIR}/concept.md` и ожидает `{FNR_DIR}/system_requirements.md`.

**Ход 4:** Проверил `.claude/commands/` — нашёл `fnr-system-requirements.md` (12KB). Проверил `.claude/skills/system-analyst-sysreq/` — нашёл SKILL.md (16KB), examples/ideal_system_requirements.md (25KB), resources/sysreq_validation_checklist.md (10KB).

**Ход 5:** Изучил `worker/Dockerfile` — строки 54-55 копируют `.claude/skills` и `.claude/commands` в `/root/.claude` образа воркера. Это точка встраивания внешнего модуля.

**Ход 6:** Проверил `.github/workflows/tests.yml` — только pytest, без сборки Docker-образов. Сборка через `docker compose up --build` (Makefile).

**Ход 7:** Проверил наличие git submodules — `.gitmodules` отсутствует, субмодулей нет.

**Ход 8:** Изучил `poh-infra` — инфраструктурный репозиторий (harness, repowise, MCP), не содержит паттернов подключения внешних модулей к приложениям.

**Ход 9:** Проверил `poh-bft-writer` — имеет 50 связей co-change с `poh-issue-agents`, но паттернов внешних модулей не обнаружил.

**Ход 10:** Нашёл `tests/test_estimation_rules_doc_sync.py` — это тест синхронизации чисел между config и docs, не паттерн для внешних модулей.

**Ход 11:** Поиск `fnr-system-requirements` по всем репозиториям workspace — не нашёл использования вне `poh-issue-agents`. Вынос безопасен.

**Ход 12:** Изучил `shared/lifecycle.py` — константа `SYSTEM_REQUIREMENTS = "system-requirements"` описывает фазу жизненного цикла Issue, не является зависимостью от скилла.


---
session: rw-analysis-po-helper-org__poh-issue-agents-70
workspace: contour
turns: 18
started: 2026-08-20T19:04:19Z
finished: 2026-08-20T19:05:33Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 25 мин |
| `poh-infra` | `ac430395f649` | 25 мин |
| `poh-issue-agents` | `a41f569f0381` | 25 мин |

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

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/activities.py"
  ],
  "include": [
    "skeleton",
    "last_change",
    "metrics"
  ],
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "targets": {
    "worker/activities.py": {
      "target": "worker/activities.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/activities.py",
        "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 20,
        "last_fix_days_ago": 0,
        "bug_magnet": true
      },
      "last_change": {
        "date": "2026-08-20T10:23:13",
        "author": "ALeks ishmanov",
        "days_ago": 39
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
      "metrics": {
        "pagerank": 0.01847,
        "pagerank_percentile": 99,
        "betweenness": 0.009493,
        "betweenness_percentile": 100,
        "in_degree": 30,
        "out_degree": 16,
        "community_id": 0,
        "community_label": "tests"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 5780,
        "full_tokens": 33526,
        "pct_of_full": 17.2,
        "bodies_kept": [],
        "text": "[repowise#a64651acfa50: 748 lines omitted (~5780 tokens); restore: repowise expand a64651acfa50]",
        "verified": true,
        "omitted": true
      },
      "episodes": 20
    }
  },
  "_meta": {
    "timing_ms": 347.3,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "a64651acfa50"
      ],
      "tokens": 5780,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {}
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "FNR_STAGE_NAMES sysreq _fnr_stages run_fnr_stage",
  "repo": "poh-issue-agents",
  "limit": 5
}
```

**Ответ:**

{
  "results": [
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
      "symbol_id": "worker/workflows.py::IssueBft::stage",
      "name": "stage",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2074,
      "end_line": 2081,
      "signature": "def stage(self) -> str",
      "qualified_name": "worker.workflows.IssueBft.stage",
      "language": "python",
      "score": 46.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/demo_e2e.py::STAGES",
      "name": "STAGES",
      "kind": "constant",
      "file": "scripts/demo_e2e.py",
      "start_line": 34,
      "end_line": 53,
      "signature": "STAGES = [",
      "qualified_name": "scripts.demo_e2e.STAGES",
      "language": "python",
      "score": 46.01,
      "next": "get_symbol"
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "nt | CONTEXT_TOTAL_CHARS = 16000 |\n| `REPOWISE_STAGE` | constant | REPOWISE_STAGE = \"repowise\" |\n| `FNR_STAGE_NAMES` | constant | FNR_STAGE_NAMES = (REPOWISE_STAGE, \"task\", \"concept\", \"debate\", \"sysre",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.run_fnr_stage",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_fnr_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_fnr_stage",
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
      "path": "worker/workflows.py"
    },
    {
      "path": "scripts/demo_e2e.py"
    },
    {
      "path": "worker/activities.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'FNR_STAGE_NAMES', '_fnr_stages', 'run_fnr_stage'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::run_fnr_stage",
  "repo": "poh-issue-agents",
  "context_lines": 5
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::run_fnr_stage",
  "file": "worker/activities.py",
  "name": "run_fnr_stage",
  "kind": "function",
  "qualified_name": "worker.activities.run_fnr_stage",
  "signature": "async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict",
  "language": "python",
  "start_line": 1261,
  "end_line": 1326,
  "symbol_start_line": 1266,
  "symbol_end_line": 1321,
  "source": "  1261\t    return {\"stage\": REPOWISE_STAGE, \"artifact\": expected,\n  1262\t            \"bytes\": path.stat().st_size, \"outcome\": \"degraded\"}\n  1263\t\n  1264\t\n  1265\t@activity.defn\n  1266\tasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:\n  1267\t    \"\"\"Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\n  1268\t    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\n  1269\t    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.\"\"\"\n  1270\t    # Бриф с обсуждением и связанными PR нужен ровно стадии `task`: только её\n  1271\t    # промпт несёт описание задачи, остальные ссылаются на уже готовые артефакты.\n  1272\t    # Регрессия, из-за которой это место и появилось: при переходе на\n  1273\t    # пер-стадийные activity обогащение осталось в монолите, и `/analyze`\n  1274\t    # уезжал в модель с одними title+body — агент переоткрывал вопросы,\n  1275\t    # закрытые в комментариях.\n  1276\t    description = (\n  1277\t        await asyncio.to_thread(_build_task_context, analyze)\n  1278\t        if stage_name == \"task\"\n  1279\t        else f\"{analyze.title}\\n\\n{analyze.body}\"\n  1280\t    )\n  1281\t    prompt, expected, requires = _fnr_stage(stage_name, description)\n  1282\t    clone_dir = _require_workspace(analyze, requires)\n  1283\t    if expected:\n  1284\t        ready = Path(clone_dir) / expected\n  1285\t        if ready.is_file() and ready.stat().st_size > 0:\n  1286\t            # Артефакт приехал с веткой прошлого прогона: стадия сделана, и\n  1287\t            # повторять её — платить второй раз за тот же документ.\n  1288\t            logger.info(\"FNR %s#%s: стадия %s уже сделана — пропускаю\",\n  1289\t                        analyze.repo, analyze.issue_number, stage_name)\n  1290\t            return {\"stage\": stage_name, \"artifact\": expected,\n  1291\t                    \"bytes\": ready.stat().st_size, \"outcome\": \"skipped\"}\n  1292\t    mcp_config = _write_repowise_config(analyze, clone_dir)\n  1293\t    if stage_name == REPOWISE_STAGE:\n  1294\t        degraded = await asyncio.to_thread(_degrade_repowise_stage, analyze, clone_dir, expected)\n  1295\t        if degraded is not None:\n  1296\t            return degraded\n  1297\t    # Конфигурация MCP передаётся ТОЛЬКО стадии сбора контекста: остальным\n  1298\t    # стадиям индекс не нужен, а лишние инструменты в сессии — лишние соблазны\n  1299\t    # и лишние деньги.\n  1300\t    await _run_with_heartbeat(\n  1301\t        _run_claude, prompt, clone_dir,\n  1302\t        mcp_config if stage_name == REPOWISE_STAGE else None,\n  1303\t        label=stage_name)\n  1304\t\n  1305\t    outcome = \"ok\"\n  1306\t    if stage_name == REPOWISE_STAGE and expected:\n  1307\t        # Артефакт дописывается транскриптом из журнала прокси и потому не\n  1308\t        # зависит от того, вспомнила ли модель его записать.\n  1309\t        outcome = await asyncio.to_thread(\n  1310\t            _ensure_dialog_artifact, analyze, clone_dir, expected)\n  1311\t\n  1312\t    artifact: str | None = None\n  1313\t    size = 0\n  1314\t    if expected:\n  1315\t        path = Path(clone_dir) / expected\n  1316\t        if not path.exists():\n  1317\t            raise RuntimeError(f\"стадия {stage_name}: артефакт {expected} не создан\")\n  1318\t        artifact = expected\n  1319\t        size = path.stat().st_size\n  1320\t    return {\"stage\": stage_name, \"artifact\": artifact, \"bytes\": size,\n  1321\t            \"outcome\": outcome}\n  1322\t\n  1323\t\n  1324\t@activity.defn\n  1325\tasync def publish_analysis(analyze: AnalyzeInput) -> str:\n  1326\t    \"\"\"Финал пайплайна: собрать артефакты, push ветки research/issue-N,",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 22.61,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_fnr_stage",
  "repo": "poh-issue-agents",
  "context_lines": 5
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_fnr_stage",
  "file": "worker/activities.py",
  "name": "_fnr_stage",
  "kind": "function",
  "qualified_name": "worker.activities._fnr_stage",
  "signature": "def _fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]",
  "language": "python",
  "start_line": 802,
  "end_line": 817,
  "symbol_start_line": 807,
  "symbol_end_line": 812,
  "source": "   802\t    \"sysreq\": f\"{FNR_DIR}/concept.md\",\n   803\t    \"validate\": f\"{FNR_DIR}/system_requirements.md\",\n   804\t}\n   805\t\n   806\t\n   807\tdef _fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]:\n   808\t    \"\"\"(промпт, ожидаемый артефакт, требуемый вход) для стадии по имени.\"\"\"\n   809\t    for n, prompt, expected in _fnr_stages(description):\n   810\t        if n == name:\n   811\t            return prompt, expected, _FNR_STAGE_REQUIRES[name]\n   812\t    raise ValueError(f\"неизвестная стадия FNR: {name}\")\n   813\t\n   814\t\n   815\tdef _workspace_dir(analyze: AnalyzeInput) -> Path:\n   816\t    \"\"\"Детерминированный рабочий каталог прогона (переживает activity в пределах\n   817\t    жизни контейнера). База — ANALYSIS_WORKSPACE_ROOT или системный temp.\"\"\"",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 18.37,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/activities.py::_fnr_stages",
  "context_lines": 5
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_fnr_stages",
  "file": "worker/activities.py",
  "name": "_fnr_stages",
  "kind": "function",
  "qualified_name": "worker.activities._fnr_stages",
  "signature": "def _fnr_stages(description: str) -> list[tuple[str, str, str | None]]",
  "language": "python",
  "start_line": 759,
  "end_line": 787,
  "symbol_start_line": 764,
  "symbol_end_line": 782,
  "source": "   759\tCONTEXT_COMMENT_CHARS = 1500    # обрезка одного комментария\n   760\tCONTEXT_PR_LIMIT = 20           # связанных PR\n   761\tCONTEXT_TOTAL_CHARS = 16000     # потолок брифа (title+body неприкосновенны)\n   762\t\n   763\t\n   764\tdef _fnr_stages(description: str) -> list[tuple[str, str, str | None]]:\n   765\t    \"\"\"Стадии цепочки FNR: (имя, промпт, ожидаемый артефакт).\n   766\t\n   767\t    У `debate` и `validate` ожидаемого файла нет: дебаты дописываются в\n   768\t    concept.md, а валидация может остаться отчётом в выводе.\n   769\t\n   770\t    `repowise` идёт ПЕРВОЙ: её результат — вход для постановки задачи, и\n   771\t    обращаться к индексу после написания task.md уже поздно.\n   772\t    \"\"\"\n   773\t    return [\n   774\t        (\"repowise\", f\"/repowise-context {description}\",\n   775\t         f\"{FNR_DIR}/repowise-dialog.md\"),\n   776\t        (\"task\", f\"/fnr-new-task {description}\", f\"{FNR_DIR}/task.md\"),\n   777\t        (\"concept\", f\"/fnr-concept {FNR_DIR}/task.md\", f\"{FNR_DIR}/concept.md\"),\n   778\t        (\"debate\", f\"/fnr-debate {FNR_DIR}/concept.md\", None),\n   779\t        (\"sysreq\", f\"/fnr-system-requirements {FNR_DIR}/concept.md\",\n   780\t         f\"{FNR_DIR}/system_requirements.md\"),\n   781\t        (\"validate\", f\"/validate-doc {FNR_DIR}/system_requirements.md\", None),\n   782\t    ]\n   783\t\n   784\t\n   785\t# Имя стадии сбора контекста — константой: на него ссылается ветвь деградации,\n   786\t# и разъехавшийся литерал означал бы стадию, которая деградировать не умеет.\n   787\tREPOWISE_STAGE = \"repowise\"",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.83,
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
  "limit": 3,
  "query": "fnr-system-requirements .claude/commands",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: worker/Dockerfile",
      "page_type": "infra_page",
      "snippet": "ce.com/setup_22.x | bash - \\\n    && apt-get install -y nodejs \\\n    && npm install -g @anthropic-ai/claude-code repomix \\\n    && rm -rf /var/lib/apt/lists/*\n\n# Только КЛИЕНТ Docker (`docker-ce-cli`),",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "worker/Dockerfile",
      "confidence_score": 1.0
    },
    {
      "title": "Symbol: worker.activities.run_bft_fast",
      "page_type": "symbol_spotlight",
      "snippet": "## Overview\n\nБыстрый проход: письмо БФТ комментарием в Issue.\n\nОдин вызов модели, без клона и без claude-code: формат `/bft-fast` — это\nструктурирование уже сказанного, а не исследование кода. Клони",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_fast",
      "file": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "Utility Shared",
      "page_type": "module_page",
      "snippet": "_ADDRESS host:port (по умолчанию localhost:7233) TEMPORAL_NAMESPACE namespace (по умолча\n\n- `shared/commands.py`: Разбор slash-команд из комментариев Issue и сборка входа аналитики. Живёт в shared/, п",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared",
      "confidence_score": 0.96
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
      "path": "worker/Dockerfile"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/lifecycle.py"
    }
  ]
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 3,
  "query": ".claude/commands/fnr-system-requirements.md",
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
  "limit": 5,
  "query": "system-analyst-sysreq",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/lifecycle.py",
      "page_type": "file_page",
      "snippet": "ED = \"classified\" |\n| `BUSINESS_ANALYSIS` | constant | BUSINESS_ANALYSIS = \"business-analysis\" |\n| `SYSTEM_REQUIREMENTS` | constant | SYSTEM_REQUIREMENTS = \"system-requirements\" |\n| `GROOMED` | consta",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/lifecycle.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: .claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "page_type": "file_page",
      "snippet": "# .claude/skills/systematic-debugging/condition-based-waiting-example.ts\n\n## Overview\n\n`.claude/skills/systematic-debugging/condition-based-waiting-example.ts` is a typescript source file in the Confi",
      "relevance_score": 2.966,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: .claude/skills/systematic-debugging/find-polluter.sh",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/systematic-debugging/find-polluter.sh\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/systematic-debugging/find-polluter.sh` is an infrastructure file (shell). Its beha",
      "relevance_score": 2.918,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/systematic-debugging/find-polluter.sh",
      "confidence_score": 0.96
    },
    {
      "title": "File: worker/consolidation_activities.py",
      "page_type": "file_page",
      "snippet": "ndary_zones secondary names zones_block model rationale issue_numbers increments /app/prompts utf-8 system_solution_profile.md #{n} {by_num[n].title if n in by_num else ''} anchors={by_num[n].anchors",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "worker/consolidation_activities.py",
      "confidence_score": 0.95
    },
    {
      "title": "Architecture Scripts",
      "page_type": "module_page",
      "snippet": "s\n\n`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascript | **Files:** 5 | *",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/architecture/scripts",
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
      "path": "shared/lifecycle.py"
    },
    {
      "path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts"
    },
    {
      "path": ".claude/skills/systematic-debugging/find-polluter.sh"
    },
    {
      "path": "worker/consolidation_activities.py"
    },
    {
      "path": "worker/activities.py"
    }
  ]
}

## Ход 10 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/Dockerfile"
  ],
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "targets": {
    "worker/Dockerfile": {
      "target": "worker/Dockerfile",
      "type": "file",
      "docs": {
        "summary": "Dockerfile: function cmd."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1
      },
      "freshness": {
        "confidence_score": null,
        "freshness_status": null,
        "is_stale": null
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "entry_point"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 104,
        "full_tokens": 992,
        "pct_of_full": 10.5,
        "bodies_kept": [],
        "text": "FROM python:3.12-slim\n\n# Node ТОТ ЖЕ, что у раннера и у CI целевого репозитория. Воркер прогоняет\n# `DEVELOP_TEST_COMMAND` — ту же строку, что гоняет CI, — и разъехавшаяся\n# мажорная версия означает «проверки красные здесь и зелёные там». На живом\n# прогоне это дало `Could not find 'tests/*.test.mjs'`: glob в `node --test`\n# раскрывает сам Node, и только начиная с 22.\n... 71 lines (8-78)\nCMD [\"python\", \"worker.py\"]\n",
        "verified": true
      }
    }
  },
  "_meta": {
    "timing_ms": 96.12,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 11 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/Dockerfile:35-50"
}
```

**Ответ:**

{
  "symbol_id": "worker/Dockerfile:35-50",
  "file": "worker/Dockerfile",
  "kind": "range",
  "start_line": 35,
  "end_line": 50,
  "total_lines": 79,
  "source": "    35\t\n    36\t# TODO: установка deb8flow — подставь реальный способ (pip/бинарь/build).\n    37\t\n    38\t# entire — трекер сессий агента. Ставит хуки Claude Code и складывает диалог\n    39\t# стадий чекпоинтами в git-рефы, то есть в сам репозиторий задачи: ветка\n    40\t# `entire/<hash>` уезжает в origin рядом с артефактами, и по id сессии прогон\n    41\t# поднимается там, где оборвался. Аккаунт для этого не нужен — запись локальная.\n    42\t#\n    43\t# Версия зафиксирована: install.sh тянет последнюю, и молчаливое обновление\n    44\t# посреди прогонов меняло бы формат чекпоинтов под ногами.\n    45\tENV ENTIRE_VERSION=0.10.2\n    46\tRUN curl -fsSL https://entire.io/install.sh | bash \\\n    47\t    && /root/.local/bin/entire version | head -1\n    48\tENV PATH=\"/root/.local/bin:${PATH}\"\n    49\t\n    50\t# Скиллы и FNR-команды SA-helper кладём в ПОЛЬЗОВАТЕЛЬСКИЙ ~/.claude, а не в",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 6.16,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 992
  }
}

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/Dockerfile:50-65"
}
```

**Ответ:**

{
  "symbol_id": "worker/Dockerfile:50-65",
  "file": "worker/Dockerfile",
  "kind": "range",
  "start_line": 50,
  "end_line": 65,
  "total_lines": 79,
  "source": "    50\t# Скиллы и FNR-команды SA-helper кладём в ПОЛЬЗОВАТЕЛЬСКИЙ ~/.claude, а не в\n    51\t# проектный .claude: `claude -p` запускается с cwd внутри КЛОНА целевого\n    52\t# репозитория, у которого может быть свой .claude — проектный каталог бы его\n    53\t# перекрыл. Пользовательский уровень виден из любого cwd и не конфликтует.\n    54\tCOPY .claude/skills /root/.claude/skills\n    55\tCOPY .claude/commands /root/.claude/commands\n    56\t\n    57\tWORKDIR /app\n    58\tCOPY worker/requirements.txt .\n    59\tRUN pip install --no-cache-dir -r requirements.txt\n    60\t\n    61\tCOPY worker/ .\n    62\tCOPY shared/ /app/shared/\n    63\t# Та же диагностика доступна и из воркера: у него своё окружение (креды claude -p,\n    64\t# ZAI_*), и расходиться с вебхуком оно может незаметно.\n    65\tCOPY scripts/ /app/scripts/",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 17.23,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 992
  }
}

## Ход 13 · `get_blast_radius` · contour

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

## Ход 14 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "github actions workflow CI CD docker build",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: worker/Dockerfile",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: worker/Dockerfile\n\n**Type:** dockerfile | **Declared targets:** 1\n\n## Overview\n\n`worker/Dockerfile` is an infrastructure file (dockerfile). It declares 1 named target, listed below.",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "worker/Dockerfile",
      "confidence_score": 1.0
    },
    {
      "title": "Infrastructure: scripts/setup.sh",
      "page_type": "infra_page",
      "snippet": "h — one-shot Layer A onboarding.\n#\n# Prepares everything needed to run the autonomous triage over a GitHub repo:\n#   1. preflight checks (docker, uv, gh)\n#   2. python 3.12 venv + deps (via uv)\n#   3.",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/setup.sh",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: webhook/Dockerfile",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: webhook/Dockerfile\n\n**Type:** dockerfile | **Declared targets:** 1\n\n## Overview\n\n`webhook/Dockerfile` is an infrastructure file (dockerfile). It declares 1 named target, listed below",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "webhook/Dockerfile",
      "confidence_score": 0.97
    },
    {
      "title": "Infrastructure: Makefile",
      "page_type": "infra_page",
      "snippet": "dry-run backfill-one go-live dry-again down test consolidate\n\n# Три конфигурации compose:\n#   main (docker-compose.yml)       — только приложение, внешний Temporal из .env\n#   local (docker-compose.lo",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "Makefile",
      "confidence_score": 0.95
    },
    {
      "title": "Infrastructure: openhands/Dockerfile",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: openhands/Dockerfile\n\n**Type:** dockerfile | **Declared targets:** 1\n\n## Overview\n\n`openhands/Dockerfile` is an infrastructure file (dockerfile). It declares 1 named target, listed b",
      "relevance_score": 2.842,
      "sources": [
        "fts"
      ],
      "target_path": "openhands/Dockerfile",
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
      "path": "worker/Dockerfile"
    },
    {
      "path": "scripts/setup.sh"
    },
    {
      "path": "webhook/Dockerfile"
    },
    {
      "path": "Makefile"
    },
    {
      "path": "openhands/Dockerfile"
    }
  ]
}

## Ход 15 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "poh-infra",
  "include": [
    "outline"
  ]
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-infra",
  "content_md": "# Repository Overview: poh-infra\n\n**Files:** 20 | **Lines:** 3430",
  "code_health": {
    "average_health": 8.77,
    "band": "healthy",
    "hotspot_health": 6.66,
    "worst_performer_path": "repowise/proxy/proxy.py",
    "worst_performer_score": 5.2,
    "open_findings": 49,
    "file_count": 38,
    "distribution": {
      "total_files": 38,
      "total_nloc": 4061,
      "bands": {
        "healthy": {
          "files": 34,
          "nloc": 3003,
          "pct": 73.9
        },
        "warning": {
          "files": 4,
          "nloc": 1058,
          "pct": 26.1
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
    "files_git_attributed": 40,
    "hotspot_count": 2,
    "avg_bus_factor": 0.6,
    "files_with_bus_factor_1": 23,
    "churn_trend": "increasing",
    "top_churn_modules": [
      "harness/docker-compose.yml",
      "docs/repowise",
      "mcp/poh-org",
      "harness/DOKPLOY.md",
      "harness/STATUS.md"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 19,
        "percentage": 47.5
      },
      {
        "name": "ALeks ishmanov",
        "files_owned": 4,
        "percentage": 10.0
      },
      {
        "name": "kibarik",
        "files_owned": 1,
        "percentage": 2.5
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
      "label": "docs/harness",
      "size": 1
    },
    {
      "id": 3,
      "label": "docs/harness (1)",
      "size": 1
    },
    {
      "id": 4,
      "label": "docs/harness (1)",
      "size": 1
    },
    {
      "id": 5,
      "label": "docs/repowise",
      "size": 1
    },
    {
      "id": 6,
      "label": "docs/repowise (1)",
      "size": 1
    },
    {
      "id": 7,
      "label": "docs/repowise (1)",
      "size": 1
    },
    {
      "id": 8,
      "label": "docs/repowise (1)",
      "size": 1
    },
    {
      "id": 9,
      "label": "docs/repowise (1)",
      "size": 1
    }
  ],
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-infra",
      "title": "Repository Overview: poh-infra"
    },
    "total_pages": 17,
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
        "page_id": "infra_page:harness/finish-registration.sh",
        "title": "Infrastructure: harness/finish-registration.sh",
        "page_type": "infra_page",
        "target_path": "harness/finish-registration.sh"
      },
      {
        "section": "3",
        "page_id": "infra_page:harness/host/poh-harness-isolation.sh",
        "title": "Infrastructure: harness/host/poh-harness-isolation.sh",
        "page_type": "infra_page",
        "target_path": "harness/host/poh-harness-isolation.sh"
      },
      {
        "section": "4",
        "page_id": "infra_page:mcp/poh-org/setup.sh",
        "title": "Infrastructure: mcp/poh-org/setup.sh",
        "page_type": "infra_page",
        "target_path": "mcp/poh-org/setup.sh"
      },
      {
        "section": "5",
        "page_id": "file_page:repowise/indexer/indexer.py",
        "title": "File: repowise/indexer/indexer.py",
        "page_type": "file_page",
        "target_path": "repowise/indexer/indexer.py",
        "descendants": 4,
        "children": [
          {
            "section": "5.1",
            "page_id": "symbol_spotlight:repowise/indexer/indexer.py::bootstrap",
            "title": "Symbol: repowise.indexer.indexer.bootstrap",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/indexer/indexer.py::bootstrap"
          },
          {
            "section": "5.2",
            "page_id": "symbol_spotlight:repowise/indexer/indexer.py::clone_url",
            "title": "Symbol: repowise.indexer.indexer.clone_url",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/indexer/indexer.py::clone_url"
          },
          {
            "section": "5.3",
            "page_id": "symbol_spotlight:repowise/indexer/indexer.py::embedder_args",
            "title": "Symbol: repowise.indexer.indexer.embedder_args",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/indexer/indexer.py::embedder_args"
          },
          {
            "section": "5.4",
            "page_id": "symbol_spotlight:repowise/indexer/indexer.py::ensure_clone",
            "title": "Symbol: repowise.indexer.indexer.ensure_clone",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/indexer/indexer.py::ensure_clone"
          }
        ]
      },
      {
        "section": "6",
        "page_id": "file_page:repowise/proxy/proxy.py",
        "title": "File: repowise/proxy/proxy.py",
        "page_type": "file_page",
        "target_path": "repowise/proxy/proxy.py",
        "descendants": 5,
        "children": [
          {
            "section": "6.1",
            "page_id": "symbol_spotlight:repowise/proxy/proxy.py::close",
            "title": "Symbol: repowise.proxy.proxy.close",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/proxy/proxy.py::close"
          },
          {
            "section": "6.2",
            "page_id": "symbol_spotlight:repowise/proxy/proxy.py::health",
            "title": "Symbol: repowise.proxy.proxy.health",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/proxy/proxy.py::health"
          },
          {
            "section": "6.3",
            "page_id": "symbol_spotlight:repowise/proxy/proxy.py::index_age",
            "title": "Symbol: repowise.proxy.proxy.index_age",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/proxy/proxy.py::index_age"
          },
          {
            "section": "6.4",
            "page_id": "symbol_spotlight:repowise/proxy/proxy.py::mcp",
            "title": "Symbol: repowise.proxy.proxy.mcp",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/proxy/proxy.py::mcp"
          },
          {
            "section": "6.5",
            "page_id": "symbol_spotlight:repowise/proxy/proxy.py::render",
            "title": "Symbol: repowise.proxy.proxy.render",
            "page_type": "symbol_spotlight",
            "target_path": "repowise/proxy/proxy.py::render"
          }
        ]
      },
      {
        "section": "7",
        "page_id": "symbol_spotlight:harness/host/poh-harness-isolation.sh::ensure",
        "title": "Symbol: harness.host.poh-harness-isolation.ensure",
        "page_type": "symbol_spotlight",
        "target_path": "harness/host/poh-harness-isolation.sh::ensure"
      }
    ]
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 22
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 1
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 12
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 3
      }
    ],
    "tour_available": true,
    "tour_step_count": 4
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-infra",
      "page_id": "repo_overview:poh-infra",
      "target_path": "poh-infra",
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
      "target_path": "harness/README.md",
      "page_id": "repo_overview:harness/README.md",
      "section": null
    },
    {
      "order": 2,
      "title": "DOKPLOY.md",
      "kind": "code",
      "reason": "The walk's anchor — its imports fan out the widest in a repo with no single entry point.",
      "target_path": "harness/DOKPLOY.md",
      "page_id": "file_page:harness/DOKPLOY.md",
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
    "indexed_commit": "ac430395f649",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "query": "external module import submodule dependency",
  "repo": "poh-bft-writer"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Repository Overview: poh-bft-writer",
      "page_type": "repo_overview",
      "snippet": "er` is a markdown codebase of 54 files.\n\n\n\n\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `README.md` (0.0185)\n\n- `bft-",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "poh-bft-writer",
      "confidence_score": 1.0
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": "ge shows the shape of execution rather than the behaviour.\n\n## Shape`poh-bft-writer` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n\n\n\n\n##",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
      "confidence_score": 0.98
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

## Ход 17 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 3,
  "query": "fnr-system-requirements",
  "repo": "all"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: skills/bft-writer/scripts/bft-lint.py",
      "page_type": "file_page",
      "snippet": "tage h1_line slug nxt following head_start head start goal seen titles ordered header_line personas requirements src_idx src idx rid heads clean positions key text fence_open open lang found else cont",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "skills/bft-writer/scripts/bft-lint.py",
      "repo": "poh-bft-writer",
      "rrf_score": 0.01667,
      "confidence_score": 1.0
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": "n the repo; worth understanding early.\n   - `install.sh`\n\n\n7. conftest.py. The test suite — how the system's behavior is verified.\n   - `.claude/skills/okr-planner/resources/engine/tests/conftest.py`",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
      "repo": "poh-helper",
      "rrf_score": 0.01667,
      "confidence_score": 1.0
    },
    {
      "title": "File: repowise/proxy/proxy.py",
      "page_type": "file_page",
      "snippet": "к индексу из контура производства.\n\nТри обязанности, и все три — следствия конкретных решений спеки FNR-5\n(`po-helper-org/poh-issue-agents`, `sa_documentation/FNR/FNR_5/`).\n\n**Маршрутизация по workspa",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "repowise/proxy/proxy.py",
      "repo": "poh-infra",
      "rrf_score": 0.01667,
      "confidence_score": 1.0
    }
  ],
  "_meta": {
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "skills/bft-writer/scripts/bft-lint.py"
    },
    {
      "path": "repowise/proxy/proxy.py"
    },
    {
      "path": "shared/lifecycle.py"
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
    "timing_ms": 70.24,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
