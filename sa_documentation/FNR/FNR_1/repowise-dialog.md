# Итог

## Текущий механизм комментариев

1. **Поток подтверждения приёма**: `webhook/main.py:547` → `_ack_comment_seen` → `CommentAck` workflow → `worker/activities.py:2068-2082` (`ack_comment_seen`) → `worker/github_client.py:236-242` (`add_reaction`). Только реакция `eyes`, без placeholder-комментария.

2. **Разрозненные ack → publish пары**: В `worker/activities.py` 28+ вызовов `post_comment`, уже есть 3 пары с отдельными реализациями:
   - `ack_command:2088-2120` → `publish_analysis:1325-1342`
   - `ack_bft_command:2242-2282` → `run_bft_fast`, `publish_bft_deep`
   - `ack_estimate_command:2889-2902` → `post_estimate_comment`
   Каждая пара постит СВОЙ новый комментарий, никак не связаны.

3. **GitHub Client API неполный**: `worker/github_client.py` имеет `post_comment:129-143` (возвращает `None`), `add_reaction`, `list_comments`, `update_issue_body`. **Отсутствуют**: `update_comment`, `delete_comment`. Comment ID негде взять для update/delete.

4. **Подпись агента**: `shared/agent_comment.py` — `MARKER = "<!-- issue-agent -->"`, `sign(body)` добавляет маркер, `is_agent_comment(body)` проверяет. `post_comment` всегда вызывает `sign()`. Вебхук фильтрует по `is_agent_comment` ([`webhook/main.py:537`](webhook/main.py#L537)). Placeholder ОБЯЗАН нести подпись, иначе его правка уйдёт в цикл как реплика человека.

5. **Состояние workflow**: `shared/workflow_types.py::LifecycleState` — компактное состояние для `continue-as-new`. Поля: `phase`, `stage`, `pr_number`, `clarify_rounds`, `answered_comment_ids`. Восстанавливается в [`worker/workflows.py::IssueLifecycle::run`](worker/workflows.py#L653) из параметра `carried`. ID placeholder'а обязан жить здесь, иначе activity retry или continue-as-new потеряет его.

6. **RunID**: В коде не используется. Берётся из `workflow.info().run_id` (Temporal API). В финальном сообщении дублируется — иначе умирает с placeholder'ом.

7. **Идемпотентность**: Повторная доставка упирается в тот же workflow ID ([`webhook/main.py:261`](webhook/main.py#L261) — `WorkflowAlreadyStartedError`). Placeholder не должен задваиваться на ретраях GitHub.

## Требуемые изменения

1. **`worker/github_client.py`**: Добавить `update_comment(repo, comment_id, body)` → `PATCH /repos/{repo}/issues/comments/{id}`, `delete_comment(repo, comment_id)` → `DELETE ...`, обе с `DRY_RUN`. `post_comment` возвращать ID созданного комментария.

2. **Состояние**: Добавить поле `placeholder_comment_id: int | None` в `LifecycleState` (и аналогично для других workflow-состояний).

3. **Новый слой**: `shared/run_comment.py` с `open(repo, issue, text) -> comment_id`, `update(comment_id, text)`, `finish(repo, issue, comment_id, text)`. `finish` инкапсулирует политику: опубликовать результат, потом удалить placeholder.

4. **Ack-activity**: Создавать placeholder с RunID, возвращать его ID, сохранять в состояние workflow.

5. **Publish-activity**: Публиковать результат новым комментарием, затем удалять placeholder по ID из состояния.

# Открытые вопросы

Нет — индекс ответил на все заданные вопросы.

# Диалог

## Ход 1: Overview
**Инструмент**: `get_overview(poh-issue-agents)`
**Ответ**: Репозиторий `poh-issue-agents`, 323 файла, 80733 строк. Entry points: `webhook/main.py`. Key modules: `worker/`, `shared/`. Hotspot: `worker/activities.py`. Index за сегодня (commit a41f569f0381). Workspace mode: есть соседние репо `poh-bft-writer`, `poh-pr-agents`, etc.

## Ход 2: Текущий поток комментариев
**Инструмент**: `get_context(webhook/main.py, worker/workflows.py, worker/activities.py, worker/github_client.py)` + `get_symbol(github_webhook)`, `get_symbol(ack_comment_seen)`
**Ответ**: Flow: `_ack_comment_seen` → `CommentAck` workflow → `ack_comment_seen` activity → `add_reaction`. Только `eyes`, без placeholder. `github_client.py` имеет `post_comment` (возвращает `None`), `add_reaction`, `list_comments`. НЕТ `update_comment`, `delete_comment`.

## Ход 3: Пары ack → publish
**Инструмент**: `get_symbol(ack_command)`, `get_symbol(publish_analysis)`, `search_codebase(ack_command)`, `grep(post_comment)`
**Ответ**: `ack_command:2088-2120` постит "Взял в работу" комментарий. `publish_analysis:1325-1342` постит результат. НЕТ связи между ними — оба остаются в треде. В `activities.py` ~30 вызовов `post_comment`. 4 ack → publish пары с разными реализациями.

## Ход 4: Подпись агента
**Инструмент**: `get_context(shared/agent_comment.py)`
**Ответ**: `MARKER = "<!-- issue-agent -->"`. `sign(body)` добавляет маркер. `is_agent_comment(body)` проверяет. `post_comment` всегда вызывает `sign()`. Вебхук фильтрует по `is_agent_comment` ([`webhook/main.py:537`](webhook/main.py#L537)). Placeholder ОБЯЗАН нести подпись.

## Ход 5: Состояние workflow
**Инструмент**: `get_symbol(LifecycleState)`, `get_symbol(IssueLifecycle::run)`
**Ответ**: `LifecycleState` — компактное состояние для `continue-as-new`. Поля: `phase`, `stage`, `pr_number`, `clarify_rounds`, `answered_comment_ids`. Восстанавливается из `carried` параметра. ID placeholder'а обязан жить здесь.

## Ход 6: Сигнальный механизм
**Инструмент**: `search_codebase(analyze_requested signal)`, `grep(analyze_requested)`
**Ответ**: `worker/workflows.py:469` — `analyze_requested(comment_id)` signal handler. Очередь сигналов, обработка в phase loop.

## Итого
6 ходов. Все вопросы из описания задачи раскрыты. Границы изменений ясны: github_client (add methods), state (add field), new layer (run_comment.py), refactor existing pairs.


---
session: rw-analysis-po-helper-org__poh-issue-agents-76
workspace: contour
turns: 17
started: 2026-08-20T19:20:48Z
finished: 2026-08-20T19:21:52Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 41 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 41 мин |
| `poh-helper` | `18512c1e7ce9` | 42 мин |
| `poh-infra` | `ac430395f649` | 42 мин |
| `poh-issue-agents` | `a41f569f0381` | 42 мин |
| `poh-memory-engine` | `194e39319b3f` | 41 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 42 мин |
| `poh-scheduller` | `04cc3f47aff9` | 41 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 41 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 14 ч |

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

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "webhook/main.py",
    "worker/workflows.py",
    "worker/activities.py",
    "worker/github_client.py"
  ],
  "include": [
    "skeleton",
    "ownership",
    "last_change"
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
      "ownership": {
        "primary_owner": "kibarik",
        "owner_pct": 0.7729,
        "contributor_count": 4,
        "bus_factor": 2,
        "agent_authored_pct": 0.7273,
        "agent_commit_count": 16,
        "agent_tier_counts": {
          "3": 15,
          "1": 1
        }
      },
      "last_change": {
        "date": "2026-08-20T18:30:53",
        "author": "kibarik",
        "days_ago": 40
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
        "text": "[repowise#31511851a0c8: 203 lines omitted (~2046 tokens); restore: repowise expand 31511851a0c8]",
        "verified": true,
        "omitted": true
      },
      "episodes": 4
    },
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
      "ownership": {
        "primary_owner": "ALeks ishmanov",
        "owner_pct": 0.5714,
        "contributor_count": 4,
        "bus_factor": 2,
        "agent_authored_pct": 0.8333,
        "agent_commit_count": 35,
        "agent_tier_counts": {
          "3": 34,
          "1": 1
        }
      },
      "last_change": {
        "date": "2026-08-20T18:30:53",
        "author": "ALeks ishmanov",
        "days_ago": 40
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
        "text": "[repowise#4877530b27a4: 349 lines omitted (~3100 tokens); restore: repowise expand 4877530b27a4]",
        "verified": true,
        "omitted": true
      },
      "episodes": 14
    },
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
      "ownership": {
        "primary_owner": "ALeks ishmanov",
        "owner_pct": 0.6316,
        "contributor_count": 3,
        "bus_factor": 2,
        "agent_authored_pct": 0.807,
        "agent_commit_count": 46,
        "agent_tier_counts": {
          "3": 44,
          "1": 2
        }
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
    },
    "worker/github_client.py": {
      "target": "worker/github_client.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/github_client.py",
        "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 7,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "ownership": {
        "primary_owner": "ALeks ishmanov",
        "owner_pct": 0.5045,
        "contributor_count": 2,
        "bus_factor": 2,
        "agent_authored_pct": 0.5417,
        "agent_commit_count": 13,
        "agent_tier_counts": {
          "3": 13
        }
      },
      "last_change": {
        "date": "2026-08-19T10:07:44",
        "author": "ALeks ishmanov",
        "days_ago": 38
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
        "tokens": 1933,
        "full_tokens": 6774,
        "pct_of_full": 28.5,
        "bodies_kept": [
          "_auth_headers",
          "_warn_pat_over_app",
          "_installation_token_for",
          "post_comment",
          "add_label"
        ],
        "text": "\"\"\"\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\"\"\"\n\nimport base64\nimport logging\nimport os\nimport subprocess\nimport threading\nimport time\nimport urllib.parse\n\nimport jwt\nimport requests\n\nfrom shared.agent_comment import is_agent_comment, sign\nfrom shared.labels import ORIGIN_AGENT\n\n_log = logging.getLogger(\"github_client\")\n\n\ndef _dry_run() -> bool:\n    ... 7 lines (26-32)\n_token_cache: dict[str, tuple[str, float]] = {}\n_token_lock = threading.Lock()\n\n\ndef _app_private_key() -> bytes:\n    \"\"\"Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла\n    ... 6 lines (39-44)\n\n\ndef _app_jwt() -> str:\n    ... 3 lines (48-50)\n\n\ndef _cached_token(repo: str) -> str | None:\n    ... 4 lines (54-57)\n\n\ndef _installation_token_for(repo: str) -> str:\n    \"\"\"Installation-токен под установку App на данный репозиторий. Установка\n    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →\n    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.\n\n    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому\n    cache-hit по одному репо не блокируется за token-обменом другого. Lock\n    сериализует только сам обмен (редкий — раз в ~55 мин на репо).\"\"\"\n    hot = _cached_token(repo)\n    if hot is not None:\n        return hot\n    with _token_lock:\n        warm = _cached_token(repo)  # перепроверка под lock: конкурент мог уже выпустить\n        if warm is not None:\n            return warm\n        app_headers = {\"Authorization\": f\"Bearer {_app_jwt()}\",\n                       ... 13 lines (76-88)\n\n\ndef _installation_token_headers(repo: str) -> dict:\n    return {\"Authorization\": f\"Bearer {_installation_token_for(repo)}\",\n            \"Accept\": \"application/vnd.github+json\"}\n\n\n_pat_over_app_warned = False\n\n\ndef _warn_pat_over_app() -> None:\n    \"\"\"Один раз на процесс: PAT задан вместе с App и молча его отключает.\n\n    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от\n    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный\n    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.\n    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.\n    \"\"\"\n    global _pat_over_app_warned\n    if _pat_over_app_warned:\n        return\n    _pat_over_app_warned = True\n    _log.warning(\n        \"GH_TOKEN/GITHUB_TOKEN задан одновременно с GITHUB_APP_ID: GitHub App НЕ \"\n        \"используется, все действия идут от имени владельца токена. Убери PAT, \"\n        \"если ожидаешь работу от приложения (см. scripts/diag.py).\"\n    )\n\n\ndef _auth_headers(repo: str) -> dict:\n    \"\"\"PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.\"\"\"\n    token = os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\")\n    if token:\n        if os.environ.get(\"GITHUB_APP_ID\"):\n            _warn_pat_over_app()\n        return {\"Authorization\": f\"Bearer {token}\", \"Accept\": \"application/vnd.github+json\"}\n    return _installation_token_headers(repo)\n\n\ndef post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    if _dry_run():\n        _log.info(\"[DRY_RUN] comment %s#%s: %s\", repo, issue_number, body[:200])\n        ... 4 lines (140-143)\n\n\ndef add_label(repo: str, issue_number: int, label: str) -> None:\n    if _dry_run():\n        _log.info(\"[DRY_RUN] label %s#%s += %s\", repo, issue_number, label)\n        return\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/labels\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"labels\": [label]}, timeout=30)\n    resp.raise_for_status()\n\n\ndef remove_label(repo: str, issue_number: int, label: str) -> None:\n    \"\"\"Снимает метку. Отсутствующая метка (404) — штатная ситуация, а не ошибка:\n    ... 15 lines (157-171)\n\n\ndef create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    \"\"\"Создаёт Issue и возвращает его номер.\n... 15 lines (176-190)\n\n\ndef close_issue(repo: str, issue_number: int) -> None:\n    ... 6 lines (194-199)\n\n\ndef search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:\n    \"\"\"Через gh CLI — тот же паттерн, что и в версии на Actions, но токен\n    ... 14 lines (204-217)\n\n\ndef branch_exists(repo: str, branch: str) -> bool:\n    ... 3 lines (221-223)\n\n\ndef auth_token(repo: str) -> str:\n    \"\"\"Голый токен для внешних процессов (git clone, gh CLI).\n... 4 lines (228-231)\n\n\ndef add_reaction(repo: str, comment_id: int, content: str = \"eyes\") -> None:\n    \"\"\"Реакция на комментарий — видимое «команда принята» до тяжёлой работы.\n    ... 7 lines (236-242)\n\n\ndef ensure_branch(repo: str, branch: str) -> None:\n    \"\"\"Создаёт ветку от дефолтной, если её ещё нет.\"\"\"\n    ... 23 lines (247-269)\n\n\ndef put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:\n    \"\"\"Создаёт или обновляет файл в ветке через Contents API.\n... 19 lines (274-292)\n\n\ndef push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    ... 7 lines (297-303)\n\n\ndef get_issue(repo: str, issue_number: int) -> dict:\n    ... 4 lines (307-310)\n\n\ndef list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:\n    ... 6 lines (314-319)\n\n\ndef list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:\n    \"\"\"PR, кросс-ссылающиеся на issue (Timeline API).\n... 35 lines (324-358)\n\n\ndef get_file(repo: str, path: str, ref: str) -> str | None:\n    \"\"\"Содержимое файла из ветки. None — файла нет; для артефактов это\n    ... 11 lines (363-373)\n\n\ndef create_pr_with_files(repo: str, branch: str, base: str,\n                         files: dict, title: str, body: str):\n    ... 32 lines (378-409)\n\n\ndef list_open_issues(repo: str, limit: int = 300) -> list:\n    ... 16 lines (413-428)\n\n\ndef get_issue_body(repo: str, issue_number: int) -> str:\n    ... 4 lines (432-435)\n\n\ndef dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:\n    \"\"\"Запускает workflow репозитория-цели через `workflow_dispatch`.\n... 18 lines (440-457)\n\n\nclass GitCommandError(RuntimeError):\n    \"\"\"Отказ git с сохранённой причиной.\n... 6 lines (462-467)\n\n\ndef _git_runner(clone_dir: str, env: dict):\n    \"\"\"git по рабочему дереву задачи, с видимой причиной отказа.\n... 19 lines (472-490)\n\n\ndef publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n... 67 lines (496-562)\n\n\ndef _default_branch(repo: str) -> str:\n    ... 4 lines (566-569)\n\n\ndef get_pull(repo: str, number: int) -> dict:\n    ... 4 lines (573-576)\n\n\ndef review_text(repo: str, number: int, limit: int = 12000) -> str:\n    \"\"\"Замечания ревью одним текстом: обзорные комментарии + построчные.\n... 42 lines (581-622)\n\n\ndef push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:\n    \"\"\"Коммит правок в ветку PR. False — агент ничего не изменил.\n... 31 lines (627-657)\n\n\ndef update_issue_body(repo: str, issue_number: int, body: str) -> None:\n    ... 6 lines (661-666)\n",
        "verified": true
      },
      "episodes": 7,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.625
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 355.2,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "a64651acfa50",
        "4877530b27a4",
        "31511851a0c8"
      ],
      "tokens": 10926,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {}
}

## Ход 3 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "webhook/main.py::github_webhook",
  "depth": 2
}
```

**Ответ:**

{
  "symbol_id": "webhook/main.py::github_webhook",
  "file": "webhook/main.py",
  "name": "github_webhook",
  "kind": "function",
  "qualified_name": "webhook.main.github_webhook",
  "signature": "async def github_webhook(\n    request: Request,\n    x_github_event: str = Header(...),\n    x_hub_signature_256: str | None = Header(None),\n    x_github_delivery: str | None = Header(None),\n)",
  "language": "python",
  "start_line": 384,
  "end_line": 612,
  "symbol_start_line": 384,
  "symbol_end_line": 612,
  "source": "   384\tasync def github_webhook(\n   385\t    request: Request,\n   386\t    x_github_event: str = Header(...),\n   387\t    x_hub_signature_256: str | None = Header(None),\n   388\t    x_github_delivery: str | None = Header(None),\n   389\t):\n   390\t    body = await request.body()\n   391\t    verify_signature(body, x_hub_signature_256)\n   392\t    payload = await request.json()\n   393\t\n   394\t    # Allowlist: действуем только на репозитории из ISSUE_AGENT_REPOS (пусто/* —\n   395\t    # любой установленный). Чужой репозиторий игнорируем до старта workflow.\n   396\t    repo_full = (payload.get(\"repository\") or {}).get(\"full_name\")\n   397\t    if repo_full and not is_allowed(repo_full, allowed_specs()):\n   398\t        specs = [s for s in allowed_specs() if s.strip()]\n   399\t        # warning, а не info, и вместе с действующим allowlist: строка лога\n   400\t        # обязана сама говорить, что чинить. Раньше отказ был неотличим от\n   401\t        # тишины — GitHub видел 200, в Temporal не появлялось ничего.\n   402\t        _log.warning(\n   403\t            \"ignored repo %s — not in ISSUE_AGENT_REPOS %s; событие отброшено до Temporal\",\n   404\t            repo_full, specs or [\"(пусто)\"],\n   405\t        )\n   406\t        await _audit_dropped_delivery(payload, x_github_event, x_github_delivery,\n   407\t                                      repo_full, specs)\n   408\t        return {\"ok\": True}\n   409\t\n   410\t    client = await get_temporal_client()\n   411\t\n   412\t    if x_github_event == \"issues\":\n   413\t        action = payload[\"action\"]\n   414\t        repo = payload[\"repository\"][\"full_name\"]\n   415\t        issue_number = payload[\"issue\"][\"number\"]\n   416\t        wf_id = workflow_id_for(repo, issue_number)\n   417\t\n   418\t        if action == \"opened\":\n   419\t            try:\n   420\t                await client.start_workflow(\n   421\t                    \"IssueLifecycle\",  # имя workflow строкой — worker зарегистрирует класс под этим именем\n   422\t                    _issue_input(payload, interactive=True),\n   423\t                    id=wf_id,\n   424\t                    task_queue=\"issue-lifecycle\",\n   425\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   426\t                )\n   427\t            except WorkflowAlreadyStartedError:\n   428\t                # Повторная доставка того же события — норма, а не сбой: GitHub\n   429\t                # ретраит, если не дождался ответа, и оба раза просит одного и\n   430\t                # того же. Цикл по этому Issue уже существует, то есть нужное\n   431\t                # состояние достигнуто.\n   432\t                #\n   433\t                # 500 здесь был хуже, чем бесполезен: GitHub на нём ретраит\n   434\t                # снова, каждый ретрай снова падает, и вебхук отвечает ошибкой\n   435\t                # на штатную ситуацию, пока доставка не будет брошена насовсем.\n   436\t                _log.info(\"цикл %s#%s уже запущен — повторная доставка\",\n   437\t                          repo, issue_number)\n   438\t\n   439\t        elif action == \"closed\":\n   440\t            # Закрытый Issue не ждут. Голый signal, а НЕ signal-with-start:\n   441\t            # поднимать цикл по Issue, которым никто не занимался, чтобы тут же\n   442\t            # его закрыть, — лишний прогон в истории и лишние вызовы GitHub.\n   443\t            handle = client.get_workflow_handle(wf_id)\n   444\t            try:\n   445\t                await handle.signal(\n   446\t                    \"issue_closed\", (payload.get(\"sender\") or {}).get(\"login\"))\n   447\t            except Exception:\n   448\t                # Цикла нет или он уже завершён — сигналить некому. Это штатно:\n   449\t                # на 500 GitHub ретраит доставку и в итоге бросает её насовсем.\n   450\t                _log.info(\"no live cycle for closed %s#%s\", repo, issue_number)\n   451\t\n   452\t        elif action == \"labeled\":\n   453\t            label = payload[\"label\"][\"name\"]\n   454\t\n   455\t            # Метка — второй триггер команды, равноправный с комментарием: два\n   456\t            # тапа в мобильном GitHub вместо набора текста в треде. Ведёт в тот\n   457\t            # же воркфлоу, что и `/analyze` — таблица соответствия одна\n   458\t            # (shared/commands.py), поэтому разъехаться им негде.\n   459\t            command = parse_label_command(label)\n   460\t\n   461\t            if command == ANALYZE:\n   462\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   463\t                    return {\"ok\": True}\n   464\t                # Режим (child цикла или самостоятельный прогон) выбирает\n   465\t                # лаунчер — одна точка решения на все входы.\n   466\t                await request_analysis(\n   467\t                    client,\n   468\t                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n   469\t                    _issue_input(payload, interactive=False),\n   470\t                    build_analyze_input(payload),  # без comment_id: триггер — метка\n   471\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   472\t                )\n   473\t                return {\"ok\": True}\n   474\t\n   475\t            if command == ESTIMATE:\n   476\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   477\t                    return {\"ok\": True}\n   478\t                from shared.workflow_types import EstimateRequest\n   479\t\n   480\t                await request_estimate(\n   481\t                    client,\n   482\t                    _issue_input(payload, interactive=False),\n   483\t                    EstimateRequest(repo=repo, issue_number=issue_number),\n   484\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   485\t                )\n   486\t                return {\"ok\": True}\n   487\t\n   488\t            if command in (BFT, BFT_DEEP):\n   489\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   490\t                    return {\"ok\": True}\n   491\t                await request_bft(\n   492\t                    client,\n   493\t                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n   494\t                    _issue_input(payload, interactive=False),\n   495\t                    # Без comment_id и без уточнений: метка несёт только сам факт\n   496\t                    # запуска, и это законно — «пересобери по тому, что в Issue».\n   497\t                    build_bft_request(payload, bft_mode(command)),\n   498\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   499\t                )\n   500\t                return {\"ok\": True}\n   501\t\n   502\t            if label in HUMAN_DECISION_LABELS:\n   503\t                if not _may_start_expensive(payload, label, repo, issue_number):\n   504\t                    return {\"ok\": True}\n   505\t                # signal-with-start, а не голый signal: лейбл прилетает и по\n   506\t                # issue, у которого воркфлоу триажа не существует (issue завели\n   507\t                # до установки App — `issues.opened` никто не доставил; либо\n   508\t                # триаж прогнали в обход Temporal). signal() в несуществующий\n   509\t                # workflow бросает исключение, вебхук отвечает 500, GitHub\n   510\t                # ретраит и бросает доставку — лейбл остаётся мёртвым молча.\n   511\t                await client.start_workflow(\n   512\t                    \"IssueLifecycle\",\n   513\t                    # Отвечать на уточняющий вопрос тут некому: триггер —\n   514\t                    # лейбл, а не диалог. VAGUE обязан эскалировать, иначе цикл\n   515\t                    # уточнений съест только что доставленный сигнал.\n   516\t                    _issue_input(payload, interactive=False),\n   517\t                    id=wf_id,\n   518\t                    task_queue=\"issue-lifecycle\",\n   519\t                    search_attributes=_search_attributes(repo, payload, issue_number),\n   520\t                    start_signal=\"human_decision\",\n   521\t                    start_signal_args=[label],\n   522\t                )\n   523\t\n   524\t    elif x_github_event == \"issue_comment\":\n   525\t        if payload[\"action\"] != \"created\":\n   526\t            return {\"ok\": True}\n   527\t        # Комментарии от самого сервиса не должны сигналить сами себя —\n   528\t        # тот же принцип, что и guard `comment.user.type != 'Bot'` в старой\n   529\t        # версии на Actions.\n   530\t        if payload[\"comment\"][\"user\"][\"type\"] == \"Bot\":\n   531\t            return {\"ok\": True}\n   532\t        # Гейта по типу автора мало: под PAT сервис пишет от имени человека, и\n   533\t        # его комментарии возвращаются с `type == \"User\"`. На живом прогоне\n   534\t        # именно так advisor-ответ и разбор приоритета приезжали обратно как\n   535\t        # `user_comment`. Различаем по подписи, а не по логину: владелец токена\n   536\t        # — тот же человек, чьи настоящие ответы кормят цикл уточнений.\n   537\t        if is_agent_comment(payload[\"comment\"].get(\"body\")):\n   538\t            return {\"ok\": True}\n   539\t\n   540\t        repo = payload[\"repository\"][\"full_name\"]\n   541\t        issue_number = payload[\"issue\"][\"number\"]\n   542\t\n   543\t        # Подтверждение приёма — ДО разбора команды и до любого пайплайна.\n   544\t        # Всё, что ниже, ветвится и гейтится (права, живой цикл, лимиты LLM);\n   545\t        # реакция не ветвится ни на чём: комментарий доставлен, значит система\n   546\t        # его увидела, и это должно быть видно человеку сразу.\n   547\t        await _ack_comment_seen(client, repo, issue_number,\n   548\t                                payload[\"comment\"][\"id\"])\n   549\t\n   550\t        # Единственная точка ветвления «команда против обычного комментария»:\n   551\t        # команда НЕ уходит в user_comment, иначе её съел бы цикл уточнений\n   552\t        # intake gate как ответ на уточняющий вопрос.\n   553\t        command = parse_command(payload[\"comment\"].get(\"body\") or \"\")\n   554\t\n   555\t        if command == ESTIMATE:\n   556\t            if not _may_start_expensive(payload, \"/estimate\", repo, issue_number):\n   557\t                return {\"ok\": True}\n   558\t            from shared.workflow_types import EstimateRequest\n   559\t\n   560\t            comment_id = payload[\"comment\"][\"id\"]\n   561\t            await request_estimate(\n   562\t                client,\n   563\t                _issue_input(payload, interactive=True),\n   564\t                EstimateRequest(repo=repo, issue_number=issue_number,\n   565\t                                comment_id=comment_id),\n   566\t                search_attributes=_search_attributes(repo, payload, issue_number),\n   567\t            )\n   568\t            return {\"ok\": True}\n   569\t\n   570\t        if command in (BFT, BFT_DEEP):\n   571\t            if not _may_start_expensive(payload, f\"/{command}\", repo, issue_number):\n   572\t                return {\"ok\": True}\n   573\t            await request_bft(\n   574\t                client,\n   575\t                _issue_input(payload, interactive=True),\n   576\t                build_bft_request(payload, bft_mode(command)),\n   577\t                search_attributes=_search_attributes(repo, payload, issue_number),\n   578\t            )\n   579\t            return {\"ok\": True}\n   580\t\n   581\t        if command == ANALYZE:\n   582\t            if not _may_start_expensive(payload, \"/analyze\", repo, issue_number):\n   583\t                return {\"ok\": True}\n   584\t            # Одна точка решения child-vs-root: раньше здесь стартовал\n   585\t            # самостоятельный IssueAnalysis, а циклу уходило лишь косметическое\n   586\t            # уведомление — связь между владельцем состояния Issue и работой\n   587\t            # агента была декоративной (#37).\n   588\t            await request_analysis(\n   589\t                client,\n   590\t                _issue_input(payload, interactive=True),\n   591\t                build_analyze_input(payload),\n   592\t                search_attributes=_search_attributes(repo, payload, issue_number),\n   593\t            )\n   594\t            return {\"ok\": True}\n   595\t\n   596\t        wf_id = workflow_id_for(repo, issue_number)\n   597\t        handle = client.get_workflow_handle(wf_id)\n   598\t        try:\n   599\t            await handle.signal(\"user_comment\", args=[payload[\"comment\"][\"body\"],\n   600\t                                                       payload[\"comment\"][\"id\"]])\n   601\t        except Exception:\n   602\t            # Сознательное исключение из правила «сигнал поднимает цикл».\n   603\t            # Команды (`/analyze`, `/estimate`, метки решения) идут через\n   604\t            # signal-with-start и проходят гейт на дорогую стадию; обычный\n   605\t            # комментарий гейта не проходит — им можно завести триаж на любом\n   606\t            # Issue репозитория, включая тысячи старых. Цена ошибки здесь —\n   607\t            # веер LLM-прогонов, а польза — доставка реплики в цикл, которого\n   608\t            # нет; поэтому комментарий по-прежнему best-effort.\n   609\t            _log.info(\"no live lifecycle for %s#%s — комментарий не доставлен\",\n   610\t                      repo, issue_number)\n   611\t\n   612\t    return {\"ok\": True}",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 19.09,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6855
  },
  "callee_bodies": {
    "depth": 2,
    "callees": [
      {
        "symbol_id": "shared/agent_comment.py::is_agent_comment",
        "name": "is_agent_comment",
        "file": "shared/agent_comment.py",
        "kind": "function",
        "signature": "def is_agent_comment(body: str | None) -> bool",
        "depth": 1,
        "start_line": 31,
        "end_line": 32,
        "source": "    31\tdef is_agent_comment(body: str | None) -> bool:\n    32\t    return MARKER in (body or \"\")",
        "verified": true
      },
      {
        "symbol_id": "shared/agent_launcher.py::request_analysis",
        "name": "request_analysis",
        "file": "shared/agent_launcher.py",
        "kind": "function",
        "signature": "async def request_analysis(client, issue_input, analyze, *, search_attributes=None) -> str",
        "depth": 1,
        "start_line": 66,
        "end_line": 95,
        "source": "    66\tasync def request_analysis(client, issue_input, analyze, *,\n    67\t                           search_attributes=None) -> str:\n    68\t    \"\"\"`/analyze` или метка `run:analyze` — запустить аналитику по Issue.\"\"\"\n    69\t    from temporalio.exceptions import WorkflowAlreadyStartedError\n    70\t\n    71\t    repo, issue_number = analyze.repo, analyze.issue_number\n    72\t    handle = await client.start_workflow(\n    73\t        \"IssueLifecycle\",\n    74\t        issue_input,\n    75\t        id=issue_workflow_id(repo, issue_number),\n    76\t        task_queue=TASK_QUEUE,\n    77\t        search_attributes=search_attributes,\n    78\t        start_signal=\"analyze_requested\",\n    79\t        start_signal_args=[analyze.comment_id],\n    80\t    )\n    81\t    if await _cycle_handles_agents(handle, repo, issue_number):\n    82\t        return CHILD\n    83\t\n    84\t    try:\n    85\t        await client.start_workflow(\n    86\t            ANALYSIS_WORKFLOW, analyze,\n    87\t            id=analysis_workflow_id(repo, issue_number),\n    88\t            task_queue=TASK_QUEUE,\n    89\t            search_attributes=search_attributes,\n    90\t        )\n    91\t    except WorkflowAlreadyStartedError:\n    92\t        # Прогон по этому Issue уже идёт: пользователь видел ack первого\n    93\t        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.\n    94\t        _log.info(\"analysis already running for %s#%s\", repo, issue_number)\n    95\t    return ROOT",
        "verified": true
      },
      {
        "symbol_id": "shared/agent_launcher.py::request_bft",
        "name": "request_bft",
        "file": "shared/agent_launcher.py",
        "kind": "function",
        "signature": "async def request_bft(client, issue_input, req, *, search_attributes=None) -> str",
        "depth": 1,
        "start_line": 98,
        "end_line": 131,
        "source": "    98\tasync def request_bft(client, issue_input, req, *, search_attributes=None) -> str:\n    99\t    \"\"\"`/bft`, `/bft-deep` или метка `run:bft*` — собрать БФТ по Issue.\n   100\t\n   101\t    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт\n   102\t    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать\n   103\t    своё — ровно как с оценкой.\n   104\t    \"\"\"\n   105\t    from temporalio.exceptions import WorkflowAlreadyStartedError\n   106\t\n   107\t    repo, issue_number = req.repo, req.issue_number\n   108\t    handle = await client.start_workflow(\n   109\t        \"IssueLifecycle\",\n   110\t        issue_input,\n   111\t        id=issue_workflow_id(repo, issue_number),\n   112\t        task_queue=TASK_QUEUE,\n   113\t        search_attributes=search_attributes,\n   114\t        start_signal=\"bft_requested\",\n   115\t        start_signal_args=[req],\n   116\t    )\n   117\t    if await _cycle_handles_agents(handle, repo, issue_number):\n   118\t        return CHILD\n   119\t\n   120\t    try:\n   121\t        await client.start_workflow(\n   122\t            BFT_WORKFLOW, req,\n   123\t            id=bft_workflow_id(repo, issue_number, req.mode),\n   124\t            task_queue=TASK_QUEUE,\n   125\t            search_attributes=search_attributes,\n   126\t        )\n   127\t    except WorkflowAlreadyStartedError:\n   128\t        # Прогон в этом режиме уже идёт: пользователь видел подтверждение\n   129\t        # первого запуска, второе было бы шумом. Вебхук — чистый транспорт.\n   130\t        _log.info(\"bft %s already running for %s#%s\", req.mode, repo, issue_number)\n   131\t    return ROOT",
        "verified": true
      },
      {
        "symbol_id": "shared/agent_launcher.py::request_estimate",
        "name": "request_estimate",
        "file": "shared/agent_launcher.py",
        "kind": "function",
        "signature": "async def request_estimate(client, issue_input, estimate, *, search_attributes=None) -> str",
        "depth": 1,
        "start_line": 134,
        "end_line": 166,
        "source": "   134\tasync def request_estimate(client, issue_input, estimate, *,\n   135\t                           search_attributes=None) -> str:\n   136\t    \"\"\"`/estimate` или метка `run:estimate` — оценить трудоёмкость.\n   137\t\n   138\t    Оценка фазу не двигает: это боковая команда, а не стадия пути Issue.\n   139\t    Цикл поднимает её дочерним прогоном и продолжает ждать своё.\n   140\t    \"\"\"\n   141\t    from temporalio.exceptions import WorkflowAlreadyStartedError\n   142\t\n   143\t    repo, issue_number = estimate.repo, estimate.issue_number\n   144\t    handle = await client.start_workflow(\n   145\t        \"IssueLifecycle\",\n   146\t        issue_input,\n   147\t        id=issue_workflow_id(repo, issue_number),\n   148\t        task_queue=TASK_QUEUE,\n   149\t        search_attributes=search_attributes,\n   150\t        start_signal=\"estimate_requested\",\n   151\t        start_signal_args=[estimate.comment_id],\n   152\t    )\n   153\t    if await _cycle_handles_agents(handle, repo, issue_number):\n   154\t        return CHILD\n   155\t\n   156\t    try:\n   157\t        await client.start_workflow(\n   158\t            ESTIMATION_WORKFLOW, estimate,\n   159\t            id=estimate_workflow_id(repo, issue_number, estimate.comment_id),\n   160\t            task_queue=TASK_QUEUE,\n   161\t            search_attributes=search_attributes,\n   162\t        )\n   163\t    except WorkflowAlreadyStartedError:\n   164\t        # Тот же вебхук доставлен повторно — оценка уже идёт.\n   165\t        _log.info(\"estimate already running for %s#%s\", repo, issue_number)\n   166\t    return ROOT",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::get_temporal_client",
        "name": "get_temporal_client",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "async def get_temporal_client() -> Client",
        "depth": 1,
        "start_line": 111,
        "end_line": 115,
        "source": "   111\tasync def get_temporal_client() -> Client:\n   112\t    global _temporal_client\n   113\t    if _temporal_client is None:\n   114\t        _temporal_client = await connect_temporal()\n   115\t    return _temporal_client",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::verify_signature",
        "name": "verify_signature",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "def verify_signature(body: bytes, signature_header: str | None) -> None",
        "depth": 1,
        "start_line": 118,
        "end_line": 124,
        "source": "   118\tdef verify_signature(body: bytes, signature_header: str | None) -> None:\n   119\t    secret = os.environ[\"GITHUB_WEBHOOK_SECRET\"].encode()\n   120\t    if not signature_header or not signature_header.startswith(\"sha256=\"):\n   121\t        raise HTTPException(status_code=401, detail=\"Missing signature\")\n   122\t    expected = \"sha256=\" + hmac.new(secret, body, hashlib.sha256).hexdigest()\n   123\t    if not hmac.compare_digest(expected, signature_header):\n   124\t        raise HTTPException(status_code=401, detail=\"Invalid signature\")",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::workflow_id_for",
        "name": "workflow_id_for",
        "file": "webhook/main.py",
        "kind": "variable",
        "signature": "workflow_id_for = issue_workflow_id",
        "depth": 1,
        "start_line": 129,
        "end_line": 129,
        "source": "   129\tworkflow_id_for = issue_workflow_id",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::_search_attributes",
        "name": "_search_attributes",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "def _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None",
        "depth": 1,
        "start_line": 133,
        "end_line": 154,
        "source": "   133\tdef _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None:\n   134\t    \"\"\"Сквозной ключ цепочки в Temporal: `RootIssue` и `Repo`.\n   135\t\n   136\t    Они дают одну ленту на всю цепочку от триажа Issue до стоп-слова на PR —\n   137\t    ради этого протокол и предпочитает централизованный кластер трём\n   138\t    изолированным.\n   139\t\n   140\t    За флагом TEMPORAL_SEARCH_ATTRIBUTES, потому что атрибут, не\n   141\t    зарегистрированный на кластере, роняет САМ старт воркфлоу:\n   142\t\n   143\t        temporal operator search-attribute create --name RootIssue --type Int\n   144\t        temporal operator search-attribute create --name Repo --type Keyword\n   145\t\n   146\t    Пока оператор их не завёл, включение сломало бы обработку целиком — цена\n   147\t    ошибки конфигурации несопоставима с пользой от фильтра в UI.\n   148\t    \"\"\"\n   149\t    if not os.environ.get(\"TEMPORAL_SEARCH_ATTRIBUTES\", \"\").strip():\n   150\t        return None\n   151\t    # Для обычного Issue корень — он сам; у follow-up он указан в теле строкой\n   152\t    # `root-issue: #N` (AGENT-PROTOCOL.md, раздел 3).\n   153\t    root = parse_root_issue((payload.get(\"issue\") or {}).get(\"body\")) or issue_number\n   154\t    return {\"Repo\": [repo], \"RootIssue\": [root]}",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::_issue_input",
        "name": "_issue_input",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "def _issue_input(payload: dict, *, interactive: bool)",
        "depth": 1,
        "start_line": 157,
        "end_line": 174,
        "source": "   157\tdef _issue_input(payload: dict, *, interactive: bool):\n   158\t    \"\"\"`IssueInput` из полезной нагрузки вебхука.\n   159\t\n   160\t    Импорт внутри функции — как и в остальных ветках: shared/ подтягивается\n   161\t    лениво, чтобы старт вебхука не зависел от воркерных зависимостей.\n   162\t    \"\"\"\n   163\t    from shared.workflow_types import IssueInput\n   164\t\n   165\t    issue = payload[\"issue\"]\n   166\t    return IssueInput(\n   167\t        repo=payload[\"repository\"][\"full_name\"],\n   168\t        issue_number=issue[\"number\"],\n   169\t        title=issue[\"title\"],\n   170\t        body=issue.get(\"body\") or \"\",\n   171\t        author_login=issue[\"user\"][\"login\"],\n   172\t        author_type=issue[\"user\"][\"type\"],\n   173\t        interactive=interactive,\n   174\t    )",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::_may_start_expensive",
        "name": "_may_start_expensive",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "def _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool",
        "depth": 1,
        "start_line": 177,
        "end_line": 199,
        "source": "   177\tdef _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:\n   178\t    \"\"\"Гейт на запуск дорогой стадии + аудит того, кто её запустил.\n   179\t\n   180\t    Проверяем автора события, а не факт наличия метки: метку может поставить\n   181\t    любой с правами на репозиторий, и это самый дешёвый способ потратить чужие\n   182\t    токены. Дешёвые пути (issues.opened, обычные комментарии) сюда не приходят —\n   183\t    триаж обязан работать для всех.\n   184\t\n   185\t    Отказ только логируем: вебхук — чистый транспорт, GitHub-клиента у него нет,\n   186\t    и заводить его ради комментария «недостаточно прав» значит дать наружу\n   187\t    процессу право писать в Issue.\n   188\t    \"\"\"\n   189\t    login = (payload.get(\"sender\") or {}).get(\"login\")\n   190\t    allowlist = trigger_allowlist()\n   191\t    if may_trigger(login, allowlist):\n   192\t        # Аудит: кто и когда запустил дорогую стадию (время ставит логгер).\n   193\t        _log.info(\"expensive trigger %s by %s on %s#%s\", what, login, repo, issue_number)\n   194\t        return True\n   195\t    _log.warning(\n   196\t        \"отклонён запуск %s: %s не входит в AGENT_TRIGGER_ALLOWLIST %s (%s#%s)\",\n   197\t        what, login, allowlist, repo, issue_number,\n   198\t    )\n   199\t    return False",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::_audit_dropped_delivery",
        "name": "_audit_dropped_delivery",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "async def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None, repo: str, specs: list[str]) -> None",
        "depth": 1,
        "start_line": 202,
        "end_line": 237,
        "source": "   202\tasync def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None,\n   203\t                                  repo: str, specs: list[str]) -> None:\n   204\t    \"\"\"След в Temporal UI для события, отброшенного по allowlist.\n   205\t\n   206\t    Единственный молчаливый отказ, о котором иначе неоткуда узнать: workflow не\n   207\t    создаётся, GitHub получает 200. Аудит-воркфлоу не исполняет ни одной\n   208\t    activity — его ценность в том, что вход виден там же, где смотрят всё\n   209\t    остальное: пришло, отклонено, вот причина и вот действовавший allowlist.\n   210\t\n   211\t    Без заголовка X-GitHub-Delivery (ручной curl, тест) аудит пропускаем: без\n   212\t    уникального id ретраи GitHub плодили бы дубли. Сбой самого аудита тоже не\n   213\t    должен ронять обработку — это диагностика, а не путь события.\n   214\t    \"\"\"\n   215\t    if not delivery_id:\n   216\t        return\n   217\t    from shared.workflow_types import WebhookAuditInput\n   218\t\n   219\t    try:\n   220\t        client = await get_temporal_client()\n   221\t        await client.start_workflow(\n   222\t            \"WebhookAudit\",\n   223\t            WebhookAuditInput(\n   224\t                delivery_id=delivery_id,\n   225\t                event=event,\n   226\t                action=str(payload.get(\"action\") or \"\"),\n   227\t                repo=repo,\n   228\t                reason=\"repo_not_allowed\",\n   229\t                allowlist=specs,\n   230\t            ),\n   231\t            id=f\"webhook-drop-{delivery_id}\",\n   232\t            task_queue=\"issue-lifecycle\",\n   233\t        )\n   234\t    except WorkflowAlreadyStartedError:\n   235\t        pass  # ретрай той же доставки — запись уже есть\n   236\t    except Exception as exc:\n   237\t        _log.warning(\"не удалось записать аудит отброшенной доставки: %s\", exc)",
        "verified": true
      },
      {
        "symbol_id": "webhook/main.py::_ack_comment_seen",
        "name": "_ack_comment_seen",
        "file": "webhook/main.py",
        "kind": "function",
        "signature": "async def _ack_comment_seen(client, repo: str, issue_number: int, comment_id: int) -> None",
        "depth": 1,
        "start_line": 240,
        "end_line": 265,
        "source": "   240\tasync def _ack_comment_seen(client, repo: str, issue_number: int,\n   241\t                            comment_id: int) -> None:\n   242\t    \"\"\"Реакция `eyes` на принятый комментарий — отдельным прогоном.\n   243\t\n   244\t    Ставит её воркер, а не вебхук: GitHub-клиента здесь нет намеренно (см.\n   245\t    `_may_start_expensive`), и заводить его ради реакции значило бы дать\n   246\t    смотрящему наружу процессу право писать в Issue. Вебхук лишь просит.\n   247\t\n   248\t    Сбой самого запроса не должен ронять обработку комментария: подтверждение\n   249\t    приёма дороже своей стоимости только пока оно бесплатно для основного пути.\n   250\t    \"\"\"\n   251\t    from shared.workflow_types import CommentAckInput\n   252\t\n   253\t    try:\n   254\t        await client.start_workflow(\n   255\t            \"CommentAck\",\n   256\t            CommentAckInput(repo=repo, issue_number=issue_number,\n   257\t                            comment_id=comment_id),\n   258\t            id=comment_ack_workflow_id(repo, comment_id),\n   259\t            task_queue=\"issue-lifecycle\",\n   260\t        )\n   261\t    except WorkflowAlreadyStartedError:\n   262\t        pass  # повторная доставка того же комментария — реакция уже заказана\n   263\t    except Exception as exc:\n   264\t        _log.warning(\"не удалось подтвердить приём комментария %s#%s (%s): %s\",\n   265\t                     repo, issue_number, comment_id, exc)",
        "verified": true
      }
    ]
  }
}

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "CommentAck",
  "limit": 10,
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::CommentAck",
      "name": "CommentAck",
      "kind": "class",
      "file": "worker/workflows.py",
      "start_line": 290,
      "end_line": 309,
      "signature": "class CommentAck",
      "qualified_name": "worker.workflows.CommentAck",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::CommentAckInput",
      "name": "CommentAckInput",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 169,
      "end_line": 178,
      "signature": "class CommentAckInput",
      "qualified_name": "shared.workflow_types.CommentAckInput",
      "language": "python",
      "score": 60.03,
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
      "score": 60.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_ids.py::comment_ack_workflow_id",
      "name": "comment_ack_workflow_id",
      "kind": "function",
      "file": "shared/workflow_ids.py",
      "start_line": 38,
      "end_line": 42,
      "signature": "def comment_ack_workflow_id(repo_full_name: str, comment_id: int) -> str",
      "qualified_name": "shared.workflow_ids.comment_ack_workflow_id",
      "language": "python",
      "score": 50.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_estimate_activities.py::comment",
      "name": "comment",
      "kind": "function",
      "file": "tests/test_estimate_activities.py",
      "start_line": 42,
      "end_line": 43,
      "signature": "def comment(body, user_type=\"User\")",
      "qualified_name": "tests.test_estimate_activities.comment",
      "language": "python",
      "score": 50.02,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.CommentAck",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.CommentAck\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass CommentAck\n```\n\n## Overview\n\nПодтверждение приёма комментария — отдельны",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::CommentAck",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.CommentAckInput",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.CommentAckInput\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass CommentAckInput\n```\n\n## Overview\n\nКомментарий, приём кото",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::CommentAckInput",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.ack_comment_seen",
      "page_type": "symbol_spotlight",
      "snippet": "ned in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def ack_comment_seen(ack: CommentAckInput) -> None\n```\n\n## Overview\n\n«Система увидела комментарий» — реакция `eyes` до разбора",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::ack_comment_seen",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.worker.main",
      "page_type": "symbol_spotlight",
      "snippet": "ssueBft, IssueEstimation,\n                   ConsolidationWorkflow, WebhookAudit, OrphanAgentEvent, CommentAck],\n        activities=[\n            activities.prefilter_bot_and_security,\n            act",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/worker.py::main",
      "file": "worker/worker.py",
      "type": "page"
    },
    {
      "title": "Utility Shared",
      "page_type": "module_page",
      "snippet": "` |\n| Orphan event input | `OrphanEventInput` | `shared/workflow_types.py` |\n| Comment ack input | `CommentAckInput` | `shared/workflow_types.py` |\n| Protocol state | `ProtocolState` | `shared/workflo",
      "relevance_score": 2.687,
      "sources": [
        "fts"
      ],
      "target_path": "shared",
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
    },
    {
      "path": "shared/workflow_ids.py"
    },
    {
      "path": "tests/test_estimate_activities.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/worker.py"
    }
  ],
  "exact_match": true
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::CommentAck",
  "depth": 2
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::CommentAck",
  "file": "worker/workflows.py",
  "name": "CommentAck",
  "kind": "class",
  "qualified_name": "worker.workflows.CommentAck",
  "signature": "class CommentAck",
  "language": "python",
  "start_line": 290,
  "end_line": 309,
  "symbol_start_line": 290,
  "symbol_end_line": 309,
  "source": "   290\tclass CommentAck:\n   291\t    \"\"\"Подтверждение приёма комментария — отдельным прогоном, до всего остального.\n   292\t\n   293\t    Отдельный workflow, а не шаг цикла: комментарий приходит и туда, где цикла\n   294\t    нет (issue старше установки App, прогон уже закрыт), а поднимать ради\n   295\t    реакции полный `IssueLifecycle` — это веер LLM-прогонов на тысяче старых\n   296\t    issue. Реакция обязана стоять во всех исходах одинаково.\n   297\t\n   298\t    Ретраи с потолком: rate limit GitHub проходит сам, а 404 (комментарий уже\n   299\t    удалили) не пройдёт никогда — держать ради него бесконечный прогон незачем.\n   300\t    \"\"\"\n   301\t\n   302\t    @workflow.run\n   303\t    async def run(self, ack: CommentAckInput) -> None:\n   304\t        await workflow.execute_activity(\n   305\t            activities.ack_comment_seen,\n   306\t            ack,\n   307\t            start_to_close_timeout=timedelta(seconds=30),\n   308\t            retry_policy=RetryPolicy(maximum_attempts=3),\n   309\t        )",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.08,
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
  "depth": 2,
  "symbol_id": "worker/activities.py::ack_comment_seen"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::ack_comment_seen",
  "file": "worker/activities.py",
  "name": "ack_comment_seen",
  "kind": "function",
  "qualified_name": "worker.activities.ack_comment_seen",
  "signature": "async def ack_comment_seen(ack: CommentAckInput) -> None",
  "language": "python",
  "start_line": 2068,
  "end_line": 2082,
  "symbol_start_line": 2068,
  "symbol_end_line": 2082,
  "source": "  2068\tasync def ack_comment_seen(ack: CommentAckInput) -> None:\n  2069\t    \"\"\"«Система увидела комментарий» — реакция `eyes` до разбора и до пайплайнов.\n  2070\t\n  2071\t    Ставится на КАЖДЫЙ человеческий комментарий, а не только на команду: с\n  2072\t    телефона иначе не отличить «не доехало» от «думает». Дальше вход может\n  2073\t    оказаться командой, репликой в цикл уточнений или ничем (живого цикла нет —\n  2074\t    комментарий best-effort и тихо теряется, webhook/main.py); реакция стоит в\n  2075\t    любом из этих исходов.\n  2076\t\n  2077\t    Реакция идемпотентна на стороне GitHub: повторная доставка того же\n  2078\t    комментария упирается в тот же workflow id, а совпавший гонкой второй POST\n  2079\t    возвращает 200 на уже поставленную реакцию.\n  2080\t    \"\"\"\n  2081\t    await asyncio.to_thread(\n  2082\t        github_client.add_reaction, ack.repo, ack.comment_id, \"eyes\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 22.2,
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
  "limit": 15,
  "mode": "symbol",
  "query": "ack_command"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::ack_command",
      "name": "ack_command",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 2088,
      "end_line": 2120,
      "signature": "async def ack_command(analyze: AnalyzeInput) -> None",
      "qualified_name": "worker.activities.ack_command",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_command_label_activities.py::test_ack_command_from_label_names_the_label_and_skips_reaction",
      "name": "test_ack_command_from_label_names_the_label_and_skips_reaction",
      "kind": "function",
      "file": "tests/test_command_label_activities.py",
      "start_line": 95,
      "end_line": 109,
      "signature": "def test_ack_command_from_label_names_the_label_and_skips_reaction(monkeypatch)",
      "qualified_name": "tests.test_command_label_activities.test_ack_command_from_label_names_the_label_and_skips_reaction",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_command_label_activities.py::test_ack_command_marks_running_whatever_the_trigger",
      "name": "test_ack_command_marks_running_whatever_the_trigger",
      "kind": "function",
      "file": "tests/test_command_label_activities.py",
      "start_line": 83,
      "end_line": 92,
      "signature": "def test_ack_command_marks_running_whatever_the_trigger(monkeypatch)",
      "qualified_name": "tests.test_command_label_activities.test_ack_command_marks_running_whatever_the_trigger",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::ack_bft_command",
      "name": "ack_bft_command",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 2242,
      "end_line": 2282,
      "signature": "async def ack_bft_command(req: BftRequest) -> None",
      "qualified_name": "worker.activities.ack_bft_command",
      "language": "python",
      "score": 50.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::ack_estimate_command",
      "name": "ack_estimate_command",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 2889,
      "end_line": 2902,
      "signature": "def ack_estimate_command(req: EstimateRequest) -> None",
      "qualified_name": "worker.activities.ack_estimate_command",
      "language": "python",
      "score": 50.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ack",
      "name": "ack",
      "kind": "function",
      "file": "tests/test_agents_as_children.py",
      "start_line": 110,
      "end_line": 111,
      "signature": "async def ack(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_agents_as_children.ack",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_clarify_after_analysis.py::ack",
      "name": "ack",
      "kind": "function",
      "file": "tests/test_clarify_after_analysis.py",
      "start_line": 104,
      "end_line": 104,
      "signature": "async def ack(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_clarify_after_analysis.ack",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::ack",
      "name": "ack",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 109,
      "end_line": 109,
      "signature": "async def ack(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_develop_autostart.ack",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_lifecycle_loop.py::ack",
      "name": "ack",
      "kind": "function",
      "file": "tests/test_lifecycle_loop.py",
      "start_line": 127,
      "end_line": 130,
      "signature": "async def ack(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_lifecycle_loop.ack",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::ack",
      "name": "ack",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 169,
      "end_line": 169,
      "signature": "async def ack(analyze: AnalyzeInput) -> None",
      "qualified_name": "tests.test_ready_for_dev.ack",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_command_label_activities.py::test_ack_estimate_from_comment_still_reacts",
      "name": "test_ack_estimate_from_comment_still_reacts",
      "kind": "function",
      "file": "tests/test_command_label_activities.py",
      "start_line": 129,
      "end_line": 143,
      "signature": "def test_ack_estimate_from_comment_still_reacts(monkeypatch)",
      "qualified_name": "tests.test_command_label_activities.test_ack_estimate_from_comment_still_reacts",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_command_label_activities.py::test_ack_estimate_from_label_comments_instead_of_reacting",
      "name": "test_ack_estimate_from_label_comments_instead_of_reacting",
      "kind": "function",
      "file": "tests/test_command_label_activities.py",
      "start_line": 112,
      "end_line": 126,
      "signature": "def test_ack_estimate_from_label_comments_instead_of_reacting(monkeypatch)",
      "qualified_name": "tests.test_command_label_activities.test_ack_estimate_from_label_comments_instead_of_reacting",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment",
      "name": "test_ack_puts_eyes_on_the_command_comment",
      "kind": "function",
      "file": "tests/test_estimate_activities.py",
      "start_line": 56,
      "end_line": 58,
      "signature": "async def test_ack_puts_eyes_on_the_command_comment(fake)",
      "qualified_name": "tests.test_estimate_activities.test_ack_puts_eyes_on_the_command_comment",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::parse_command",
      "name": "parse_command",
      "kind": "function",
      "file": "shared/commands.py",
      "start_line": 84,
      "end_line": 99,
      "signature": "def parse_command(comment_body: str) -> str | None",
      "qualified_name": "shared.commands.parse_command",
      "language": "python",
      "score": 15.25,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::finish_command_labels",
      "name": "finish_command_labels",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 487,
      "end_line": 511,
      "signature": "async def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
      "qualified_name": "worker.activities.finish_command_labels",
      "language": "python",
      "score": 15.06,
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
      "path": "tests/test_command_label_activities.py"
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
    },
    {
      "path": "tests/test_ready_for_dev.py"
    },
    {
      "path": "tests/test_estimate_activities.py"
    },
    {
      "path": "shared/commands.py"
    }
  ],
  "exact_match": true
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 2,
  "symbol_id": "worker/activities.py::ack_command"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::ack_command",
  "file": "worker/activities.py",
  "name": "ack_command",
  "kind": "function",
  "qualified_name": "worker.activities.ack_command",
  "signature": "async def ack_command(analyze: AnalyzeInput) -> None",
  "language": "python",
  "start_line": 2088,
  "end_line": 2120,
  "symbol_start_line": 2088,
  "symbol_end_line": 2120,
  "source": "  2088\tasync def ack_command(analyze: AnalyzeInput) -> None:\n  2089\t    \"\"\"Видимое подтверждение приёма команды ДО тяжёлой работы.\n  2090\t\n  2091\t    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не\n  2092\t    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;\n  2093\t    если комментарий-триггер к этому моменту удалили (404) или сработал\n  2094\t    rate limit, сбой реакции не должен утопить сам ack.\n  2095\t\n  2096\t    Триггер виден по comment_id: он есть у команды в комментарии и пуст у\n  2097\t    запуска меткой — реагировать там не на что, и подтверждение называет\n  2098\t    метку, а не команду. Явно переданный `trigger` перекрывает эту догадку:\n  2099\t    аналитику запускает и цикл по метке `research-me`, и назвать её\n  2100\t    `run:analyze` значило бы указать человеку на метку, которой он не ставил.\n  2101\t    \"\"\"\n  2102\t    trigger = (f\"`{analyze.trigger}`\" if analyze.trigger\n  2103\t               else f\"`{run_label(ANALYZE)}`\" if analyze.comment_id is None\n  2104\t               else \"`/analyze`\")\n  2105\t    await asyncio.to_thread(\n  2106\t        github_client.post_comment,\n  2107\t        analyze.repo,\n  2108\t        analyze.issue_number,\n  2109\t        f\"🔍 Взял {trigger} в работу — запускаю автономный анализ через SA-helper.\\n\\n\"\n  2110\t        \"Прогон занимает несколько минут: артефакты появятся в ветке \"\n  2111\t        f\"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.\",\n  2112\t    )\n  2113\t    await asyncio.to_thread(\n  2114\t        github_client.add_label, analyze.repo, analyze.issue_number, run_label(ANALYZE)\n  2115\t    )\n  2116\t    if analyze.comment_id is not None:\n  2117\t        try:\n  2118\t            await asyncio.to_thread(github_client.add_reaction, analyze.repo, analyze.comment_id, \"eyes\")\n  2119\t        except Exception:\n  2120\t            pass  # best-effort: декорация не должна ронять ack или весь прогон",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.17,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  },
  "callee_bodies": {
    "depth": 2,
    "callees": [
      {
        "symbol_id": "shared/commands.py::run_label",
        "name": "run_label",
        "file": "shared/commands.py",
        "kind": "function",
        "signature": "def run_label(command: str) -> str",
        "depth": 1,
        "start_line": 43,
        "end_line": 44,
        "source": "    43\tdef run_label(command: str) -> str:\n    44\t    return f\"{RUN_PREFIX}{command}\"",
        "verified": true
      }
    ]
  }
}

## Ход 9 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 2,
  "symbol_id": "worker/activities.py::publish_analysis"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::publish_analysis",
  "file": "worker/activities.py",
  "name": "publish_analysis",
  "kind": "function",
  "qualified_name": "worker.activities.publish_analysis",
  "signature": "async def publish_analysis(analyze: AnalyzeInput) -> str",
  "language": "python",
  "start_line": 1325,
  "end_line": 1342,
  "symbol_start_line": 1325,
  "symbol_end_line": 1342,
  "source": "  1325\tasync def publish_analysis(analyze: AnalyzeInput) -> str:\n  1326\t    \"\"\"Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n  1327\t    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.\"\"\"\n  1328\t    clone_dir = _require_workspace(analyze, None)\n  1329\t    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)\n  1330\t    if not files:\n  1331\t        raise RuntimeError(\"пайплайн не произвёл ни одного артефакта\")\n  1332\t    branch = f\"research/issue-{analyze.issue_number}\"\n  1333\t    await asyncio.to_thread(\n  1334\t        github_client.push_artifacts_to_branch,\n  1335\t        analyze.repo, branch, files,\n  1336\t        f\"docs(sa): анализ issue #{analyze.issue_number} через SA-helper\",\n  1337\t    )\n  1338\t    await asyncio.to_thread(\n  1339\t        github_client.post_comment,\n  1340\t        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),\n  1341\t    )\n  1342\t    return branch",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 24.61,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  },
  "callee_bodies": {
    "depth": 2,
    "callees": [
      {
        "symbol_id": "worker/activities.py::_require_workspace",
        "name": "_require_workspace",
        "file": "worker/activities.py",
        "kind": "function",
        "signature": "def _require_workspace(analyze: AnalyzeInput, requires: str | None) -> str",
        "depth": 1,
        "start_line": 865,
        "end_line": 875,
        "source": "   865\tdef _require_workspace(analyze: AnalyzeInput, requires: str | None) -> str:\n   866\t    \"\"\"Guard стадии: каталог+repomix на месте? требуемый вход на месте? Иначе\n   867\t    fail-fast (без пере-клона — он дал бы свежий репозиторий без артефактов).\"\"\"\n   868\t    clone_dir = _clone_dir(analyze)\n   869\t    if not (Path(clone_dir) / \"sa_documentation\" / \"repomix-output.xml\").exists():\n   870\t        raise RuntimeError(\"рабочий каталог потерян (рестарт воркера?) — повтори /analyze\")\n   871\t    if requires and not (Path(clone_dir) / requires).exists():\n   872\t        raise RuntimeError(\n   873\t            f\"нет входа {requires} (стадия-предшественник не отработала?) — повтори /analyze\"\n   874\t        )\n   875\t    return clone_dir",
        "verified": true
      },
      {
        "symbol_id": "worker/activities.py::_build_summary",
        "name": "_build_summary",
        "file": "worker/activities.py",
        "kind": "function",
        "signature": "def _build_summary(analyze: AnalyzeInput, branch: str, files: dict[str, str]) -> str",
        "depth": 1,
        "start_line": 1000,
        "end_line": 1023,
        "source": "  1000\tdef _build_summary(analyze: AnalyzeInput, branch: str, files: dict[str, str]) -> str:\n  1001\t    base = f\"https://github.com/{analyze.repo}/blob/{branch}\"\n  1002\t    links = \"\\n\".join(f\"- [`{path.rsplit('/', 1)[-1]}`]({base}/{path})\" for path in sorted(files))\n  1003\t    # Артефакт диалога называется отдельно: без пояснения он выглядит служебным\n  1004\t    # мусором рядом с документами FNR, а это источник, из которого выведена\n  1005\t    # часть постановки, — и повод перечитать её критически, если диалог пуст.\n  1006\t    dialog = \"\"\n  1007\t    if any(p.endswith(\"repowise-dialog.md\") for p in files):\n  1008\t        dialog = (\n  1009\t            \"\\n`repowise-dialog.md` — диалог с **Repowise**, постоянным индексом кода: \"\n  1010\t            \"что уже было известно о затронутых компонентах до постановки задачи. \"\n  1011\t            \"Пустой диалог означает, что индекс был недоступен, и остальные документы \"\n  1012\t            \"написаны без него.\\n\"\n  1013\t        )\n  1014\t    return (\n  1015\t        \"## 🤖 Автономный анализ (SA-helper)\\n\\n\"\n  1016\t        f\"Прогнал полную цепочку FNR по этой задаче. Артефакты — в ветке `{branch}`:\\n\\n\"\n  1017\t        f\"{links}\\n\"\n  1018\t        f\"{dialog}\\n\"\n  1019\t        \"Начни с `system_requirements.md` — это ответ на вопрос «как реализовать эту \"\n  1020\t        \"задачу»: разбор текущего поведения на код-доказательствах, план миграции с \"\n  1021\t        \"откатами, задачи с критериями приёмки и риски с митигацией.\\n\\n\"\n  1022\t        \"Повторить анализ — командой `/analyze`.\"\n  1023\t    )",
        "verified": true
      }
    ]
  }
}

## Ход 10 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 1,
  "symbol_id": "shared/agent_comment.py"
}
```

**Ответ:**

{
  "symbol_id": "shared/agent_comment.py",
  "error": "Symbol not found: 'shared/agent_comment.py'. Use get_context to list available symbols in the file, then try again with the exact symbol_id from that response.",
  "_meta": {
    "timing_ms": 10.31,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
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
  "targets": [
    "shared/agent_comment.py"
  ],
  "include": [
    "skeleton"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/agent_comment.py": {
      "target": "shared/agent_comment.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/agent_comment.py",
        "summary": "Подпись под комментариями сервиса — чтобы он не принимал их за ответ человека."
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
        "tokens": 316,
        "full_tokens": 316,
        "pct_of_full": 100.0,
        "bodies_kept": [
          "sign"
        ],
        "text": "\"\"\"Подпись под комментариями сервиса — чтобы он не принимал их за ответ человека.\n\nНайдено на живом прогоне: оба сигнала `user_comment` в истории цикла оказались\nнашими же комментариями — advisor-ответом и разбором приоритета. Гейт вебхука\nна `comment.user.type == \"Bot\"` их не отсекает, потому что сервис ходит в GitHub\nпод PAT, а не как GitHub App, и его комментарии приходят с `type == \"User\"`.\n\nПочему подпись, а не логин. Владелец PAT — живой человек, и он же заводит Issue\nи отвечает на уточняющие вопросы. Фильтр по логину выкинул бы вместе с нашими\nкомментариями его настоящие ответы — то есть сломал бы цикл уточнений ради\nпочинки самоподдува. Подпись различает не автора, а происхождение, и работает\nодинаково при обеих схемах авторизации.\n\nМаркер невидим в отрендеренном Markdown: GitHub не показывает HTML-комментарии.\n\"\"\"\n\nMARKER = \"<!-- issue-agent -->\"\n\n\ndef sign(body: str) -> str:\n    \"\"\"Добавляет подпись, если её ещё нет.\n\n    Идемпотентность важна: один и тот же текст может пройти через несколько\n    слоёв (например, шаблон уже подписан, а отправляет его общий post_comment).\n    \"\"\"\n    if MARKER in body:\n        return body\n    return f\"{body}\\n\\n{MARKER}\"\n\n\ndef is_agent_comment(body: str | None) -> bool:\n    return MARKER in (body or \"\")\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 100.0% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 91.82,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 12 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "targets": [
    "worker/github_client.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/github_client.py": {
      "target": "worker/github_client.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/github_client.py",
        "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 7,
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
        "tokens": 1933,
        "full_tokens": 6774,
        "pct_of_full": 28.5,
        "bodies_kept": [
          "_auth_headers",
          "_warn_pat_over_app",
          "_installation_token_for",
          "post_comment",
          "add_label"
        ],
        "text": "\"\"\"\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\"\"\"\n\nimport base64\nimport logging\nimport os\nimport subprocess\nimport threading\nimport time\nimport urllib.parse\n\nimport jwt\nimport requests\n\nfrom shared.agent_comment import is_agent_comment, sign\nfrom shared.labels import ORIGIN_AGENT\n\n_log = logging.getLogger(\"github_client\")\n\n\ndef _dry_run() -> bool:\n    ... 7 lines (26-32)\n_token_cache: dict[str, tuple[str, float]] = {}\n_token_lock = threading.Lock()\n\n\ndef _app_private_key() -> bytes:\n    \"\"\"Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла\n    ... 6 lines (39-44)\n\n\ndef _app_jwt() -> str:\n    ... 3 lines (48-50)\n\n\ndef _cached_token(repo: str) -> str | None:\n    ... 4 lines (54-57)\n\n\ndef _installation_token_for(repo: str) -> str:\n    \"\"\"Installation-токен под установку App на данный репозиторий. Установка\n    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →\n    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.\n\n    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому\n    cache-hit по одному репо не блокируется за token-обменом другого. Lock\n    сериализует только сам обмен (редкий — раз в ~55 мин на репо).\"\"\"\n    hot = _cached_token(repo)\n    if hot is not None:\n        return hot\n    with _token_lock:\n        warm = _cached_token(repo)  # перепроверка под lock: конкурент мог уже выпустить\n        if warm is not None:\n            return warm\n        app_headers = {\"Authorization\": f\"Bearer {_app_jwt()}\",\n                       ... 13 lines (76-88)\n\n\ndef _installation_token_headers(repo: str) -> dict:\n    return {\"Authorization\": f\"Bearer {_installation_token_for(repo)}\",\n            \"Accept\": \"application/vnd.github+json\"}\n\n\n_pat_over_app_warned = False\n\n\ndef _warn_pat_over_app() -> None:\n    \"\"\"Один раз на процесс: PAT задан вместе с App и молча его отключает.\n\n    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от\n    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный\n    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.\n    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.\n    \"\"\"\n    global _pat_over_app_warned\n    if _pat_over_app_warned:\n        return\n    _pat_over_app_warned = True\n    _log.warning(\n        \"GH_TOKEN/GITHUB_TOKEN задан одновременно с GITHUB_APP_ID: GitHub App НЕ \"\n        \"используется, все действия идут от имени владельца токена. Убери PAT, \"\n        \"если ожидаешь работу от приложения (см. scripts/diag.py).\"\n    )\n\n\ndef _auth_headers(repo: str) -> dict:\n    \"\"\"PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.\"\"\"\n    token = os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\")\n    if token:\n        if os.environ.get(\"GITHUB_APP_ID\"):\n            _warn_pat_over_app()\n        return {\"Authorization\": f\"Bearer {token}\", \"Accept\": \"application/vnd.github+json\"}\n    return _installation_token_headers(repo)\n\n\ndef post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    if _dry_run():\n        _log.info(\"[DRY_RUN] comment %s#%s: %s\", repo, issue_number, body[:200])\n        ... 4 lines (140-143)\n\n\ndef add_label(repo: str, issue_number: int, label: str) -> None:\n    if _dry_run():\n        _log.info(\"[DRY_RUN] label %s#%s += %s\", repo, issue_number, label)\n        return\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/labels\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"labels\": [label]}, timeout=30)\n    resp.raise_for_status()\n\n\ndef remove_label(repo: str, issue_number: int, label: str) -> None:\n    \"\"\"Снимает метку. Отсутствующая метка (404) — штатная ситуация, а не ошибка:\n    ... 15 lines (157-171)\n\n\ndef create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    \"\"\"Создаёт Issue и возвращает его номер.\n... 15 lines (176-190)\n\n\ndef close_issue(repo: str, issue_number: int) -> None:\n    ... 6 lines (194-199)\n\n\ndef search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:\n    \"\"\"Через gh CLI — тот же паттерн, что и в версии на Actions, но токен\n    ... 14 lines (204-217)\n\n\ndef branch_exists(repo: str, branch: str) -> bool:\n    ... 3 lines (221-223)\n\n\ndef auth_token(repo: str) -> str:\n    \"\"\"Голый токен для внешних процессов (git clone, gh CLI).\n... 4 lines (228-231)\n\n\ndef add_reaction(repo: str, comment_id: int, content: str = \"eyes\") -> None:\n    \"\"\"Реакция на комментарий — видимое «команда принята» до тяжёлой работы.\n    ... 7 lines (236-242)\n\n\ndef ensure_branch(repo: str, branch: str) -> None:\n    \"\"\"Создаёт ветку от дефолтной, если её ещё нет.\"\"\"\n    ... 23 lines (247-269)\n\n\ndef put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:\n    \"\"\"Создаёт или обновляет файл в ветке через Contents API.\n... 19 lines (274-292)\n\n\ndef push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    ... 7 lines (297-303)\n\n\ndef get_issue(repo: str, issue_number: int) -> dict:\n    ... 4 lines (307-310)\n\n\ndef list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:\n    ... 6 lines (314-319)\n\n\ndef list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:\n    \"\"\"PR, кросс-ссылающиеся на issue (Timeline API).\n... 35 lines (324-358)\n\n\ndef get_file(repo: str, path: str, ref: str) -> str | None:\n    \"\"\"Содержимое файла из ветки. None — файла нет; для артефактов это\n    ... 11 lines (363-373)\n\n\ndef create_pr_with_files(repo: str, branch: str, base: str,\n                         files: dict, title: str, body: str):\n    ... 32 lines (378-409)\n\n\ndef list_open_issues(repo: str, limit: int = 300) -> list:\n    ... 16 lines (413-428)\n\n\ndef get_issue_body(repo: str, issue_number: int) -> str:\n    ... 4 lines (432-435)\n\n\ndef dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:\n    \"\"\"Запускает workflow репозитория-цели через `workflow_dispatch`.\n... 18 lines (440-457)\n\n\nclass GitCommandError(RuntimeError):\n    \"\"\"Отказ git с сохранённой причиной.\n... 6 lines (462-467)\n\n\ndef _git_runner(clone_dir: str, env: dict):\n    \"\"\"git по рабочему дереву задачи, с видимой причиной отказа.\n... 19 lines (472-490)\n\n\ndef publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n... 67 lines (496-562)\n\n\ndef _default_branch(repo: str) -> str:\n    ... 4 lines (566-569)\n\n\ndef get_pull(repo: str, number: int) -> dict:\n    ... 4 lines (573-576)\n\n\ndef review_text(repo: str, number: int, limit: int = 12000) -> str:\n    \"\"\"Замечания ревью одним текстом: обзорные комментарии + построчные.\n... 42 lines (581-622)\n\n\ndef push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:\n    \"\"\"Коммит правок в ветку PR. False — агент ничего не изменил.\n... 31 lines (627-657)\n\n\ndef update_issue_body(repo: str, issue_number: int, body: str) -> None:\n    ... 6 lines (661-666)\n",
        "verified": true
      },
      "episodes": 7,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.625
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 71.15,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 13 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 10,
  "mode": "hybrid",
  "query": "workflow state temporal"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::ProtocolState",
      "name": "ProtocolState",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 182,
      "end_line": 193,
      "signature": "class ProtocolState",
      "qualified_name": "shared.workflow_types.ProtocolState",
      "language": "python",
      "score": 20.25,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::LifecycleState",
      "name": "LifecycleState",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 110,
      "end_line": 147,
      "signature": "class LifecycleState",
      "qualified_name": "shared.workflow_types.LifecycleState",
      "language": "python",
      "score": 20.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/smoke_temporal.py::SmokeWorkflow",
      "name": "SmokeWorkflow",
      "kind": "class",
      "file": "scripts/smoke_temporal.py",
      "start_line": 45,
      "end_line": 50,
      "signature": "class SmokeWorkflow",
      "qualified_name": "scripts.smoke_temporal.SmokeWorkflow",
      "language": "python",
      "score": 20.01,
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
      "score": 20.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_workflow_protocol.py::_state_stub",
      "name": "_state_stub",
      "kind": "function",
      "file": "tests/test_workflow_protocol.py",
      "start_line": 87,
      "end_line": 93,
      "signature": "def _state_stub(state: ProtocolState)",
      "qualified_name": "tests.test_workflow_protocol._state_stub",
      "language": "python",
      "score": 15.03,
      "next": "get_symbol"
    },
    {
      "title": "File: shared/temporal_client.py",
      "page_type": "file_page",
      "snippet": "# shared/temporal_client.py\n\n## Overview\n\nЕдиная точка подключения к Temporal для worker, webhook и скриптов.\n\nКонфигурация из окружения:\n  TEMPORAL_ADDRESS    host:port (по умолчанию localhost:7233)",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/temporal_client.py",
      "type": "page"
    },
    {
      "title": "File: webhook/main.py",
      "page_type": "file_page",
      "snippet": "bhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.cr",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "webhook/main.py",
      "type": "page"
    },
    {
      "title": "Docs Tooling Scripts",
      "page_type": "module_page",
      "snippet": "Rank first: the order to read them in.\n\n- `scripts/backfill.py`: Backfill: start one IssueLifecycle workflow per already-open Issue. GitHub never sends webhooks for Issues that already exist, so the r",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "scripts",
      "type": "page"
    },
    {
      "title": "Utility Shared",
      "page_type": "module_page",
      "snippet": "ted by 74 other modules.\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `shared/workflow_types.py`: `shared/workflow_types.py` is a python source file in the Utility layer. It expo",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "shared",
      "type": "page"
    },
    {
      "title": "File: scripts/estimate.py",
      "page_type": "file_page",
      "snippet": "# scripts/estimate.py\n\n## Overview\n\nSmoke harness: start one IssueEstimation workflow without the webhook.\n\n`/estimate` normally arrives as an `issue_comment.created` webhook, which\nneeds Layer B (Git",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/estimate.py",
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
      "path": "shared/workflow_types.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "tests/test_workflow_protocol.py"
    },
    {
      "path": "shared/temporal_client.py"
    },
    {
      "path": "webhook/main.py"
    },
    {
      "path": "scripts/estimate.py"
    }
  ]
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 1,
  "symbol_id": "shared/workflow_types.py::LifecycleState"
}
```

**Ответ:**

{
  "symbol_id": "shared/workflow_types.py::LifecycleState",
  "file": "shared/workflow_types.py",
  "name": "LifecycleState",
  "kind": "class",
  "qualified_name": "shared.workflow_types.LifecycleState",
  "signature": "class LifecycleState",
  "language": "python",
  "start_line": 110,
  "end_line": 147,
  "symbol_start_line": 110,
  "symbol_end_line": 147,
  "source": "   110\tclass LifecycleState:\n   111\t    \"\"\"Снимок цикла для continue-as-new.\n   112\t\n   113\t    Переносится КОМПАКТНОЕ состояние — фаза, стадия и то немногое, что нужно\n   114\t    следующим фазам, — а не тред и не история. Долгоживущий цикл на активном\n   115\t    Issue иначе упрётся в тот же потолок, который уже словила консолидация:\n   116\t    на ~75 Issue история превышает ~990 событий и реплей не укладывается в\n   117\t    workflow-task timeout.\n   118\t    \"\"\"\n   119\t    phase: str = \"created\"\n   120\t    stage: str = \"intake\"\n   121\t    priority_tier: str = \"\"              # нужен чеклисту готовности (H1)\n   122\t    classification_label: str | None = None  # None — сокращённый триаж (R6)\n   123\t    analysis_done: bool = False\n   124\t    generation: int = 0                  # сколько раз цикл перезапускался\n   125\t    # Момент входа в текущую фазу, epoch-секунды. Дедлайн парковки отсчитывается\n   126\t    # от него, а не от последнего сигнала, — иначе любой посторонний комментарий\n   127\t    # продлевал бы ожидание, и правило R3 переставало бы что-либо гарантировать.\n   128\t    # Переносится через continue-as-new: перезапуск цикла не должен обнулять срок.\n   129\t    phase_since_epoch: float = 0.0\n   130\t    # Задача — часть чужого плана (подзадача декомпозиции). Ни своей\n   131\t    # декомпозиции, ни своей разработки у неё нет: и то и другое ведёт родитель.\n   132\t    plan_member: bool = False\n   133\t    root_issue: int | None = None        # родитель плана, если это подзадача\n   134\t    # Номер PR по задаче. Без него фаза доведения не знает, что доводить, и\n   135\t    # вместо круга правок молча уходит в парковку: PR открыт, ревью прошло,\n   136\t    # замечания не исправляются.\n   137\t    pr_number: int | None = None\n   138\t    # Сколько кругов уточнения после аналитики потрачено: потолок обязан\n   139\t    # переживать перезапуск, иначе continue-as-new обнулял бы его и вопросы\n   140\t    # могли задаваться заново без конца.\n   141\t    clarify_rounds: int = 0\n   142\t    # Сколько реплик человека уже отвечено содержательно и ключи последних из\n   143\t    # них. Переносятся по той же причине, что и `clarify_rounds`: перезапуск\n   144\t    # цикла не должен ни обнулять потолок, ни терять защиту от повторной\n   145\t    # доставки вебхука — иначе первый же continue-as-new отвечает дважды.\n   146\t    followup_rounds: int = 0\n   147\t    answered_comment_ids: list[int] = field(default_factory=list)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 22.27,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3167
  }
}

## Ход 15 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 1,
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
    "timing_ms": 15.22,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 5,
  "mode": "symbol",
  "query": "analyze_requested signal"
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
      "score": 50.01,
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
      "score": 45.01,
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
      "score": 45.01,
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
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_trigger_authz.py::_Handle::signal",
      "name": "signal",
      "kind": "method",
      "file": "tests/test_trigger_authz.py",
      "start_line": 49,
      "end_line": 50,
      "signature": "async def signal(self, *a, **k)",
      "qualified_name": "tests.test_trigger_authz._Handle.signal",
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
      "path": "shared/commands.py"
    },
    {
      "path": "tests/test_agent_comment.py"
    },
    {
      "path": "tests/test_bft_webhook.py"
    },
    {
      "path": "tests/test_e2e_issue_lifecycle.py"
    },
    {
      "path": "tests/test_trigger_authz.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'analyze_requested signal'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 17 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 1,
  "symbol_id": "worker/workflows.py:469-480"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py:469-480",
  "file": "worker/workflows.py",
  "kind": "range",
  "start_line": 469,
  "end_line": 480,
  "total_lines": 2274,
  "source": "   469\t    async def analyze_requested(self, comment_id: int | None) -> None:\n   470\t        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n   471\t\n   472\t        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а\n   473\t        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).\n   474\t        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу\n   475\t        из вебхука — связь между циклом Issue и работой агента была\n   476\t        декоративной, о чём и говорил прежний докстринг.\n   477\t\n   478\t        Тяжёлую работу из самого хендлера не запускаем: run() обычно\n   479\t        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с\n   480\t        основным циклом за фазу. Очередь снимает гонку — решение принимает та",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 15.54,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 28256
  }
}
