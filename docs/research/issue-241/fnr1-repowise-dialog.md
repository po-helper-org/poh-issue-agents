# Итог

1. **Вебхук эндпоинт** — `webhook/main.py` обрабатывает только GitHub события через `/webhook` с проверкой подписи `verify_signature`. Отдельного эндпоинта `/gitlab/webhook` нет. Единственное упоминание GitLab — в докстринге `_client_disconnect` о том, что у GitLab нет ретраев ([webhook/main.py:47](webhook/main.py:47)).

2. **Клиент GitHub API** — `worker/github_client.py` — обёртка над GitHub REST API с аутентификацией через GitHub App (JWT + installation token) или PAT. Все методы заточены под GitHub: `post_comment`, `set_labels`, `ensure_branch`, `put_file`, `create_pr_with_files`, `review_text` ([worker/github_client.py:1](worker/github_client.py:1)).

3. **Проблема фильтрации ботов** — в `review_text` (строка 723) и в `poh-pr-agents` (`_matching_comments`, `has_bot_activity`) используется проверка `(item.get("user") or {}).get("type") == "Bot"`. В GitLab нет поля `type` у пользователя → условие всегда истинно → функции вернут пустоту ([worker/github_client.py:723](worker/github_client.py:723)).

4. **Поиск дублей** — `search_candidates` использует gh CLI: `gh issue list` и `gh pr list`. В GitLab нет gh CLI, нужен GitLab API: `GET /projects/:id/issues?search=&in=title,description` ([worker/github_client.py:297](worker/github_client.py:297)).

5. **Обработка меток** — в `issues.labeled` GitHub присылает `payload["label"]["name"]` напрямую. В GitLab формат другой — `changes.labels.previous/current`, дельту нужно считать в нормализаторе ([webhook/main.py:475](webhook/main.py:475)).

6. **Единственный GitLab-код** — `shared/repo_ref.py` с константами `GITHUB` и `GITLAB` и методом `api_segment` для кодирования пути в URL API. Это заготовка для будущего драйвера провайдера ([shared/repo_ref.py:13](shared/repo_ref.py:13)).

7. **Отдельный сервис PR-агент** — `poh-pr-agents` (87 файлов) с собственным вебхуком, воркером и системой токенов. Критерии приёмки 11-12 требуют его порта под GitLab, но работа не началась ([poh-pr-agents:1](poh-pr-agents:1)).

8. **Git операции** — методы `ensure_branch`, `put_file`, `publish_worktree` используют git через subprocess и GitHub API. Для GitLab нужно учесть другую семантику: POST/PUT разделены, конкурентность по `last_commit_id` (commit SHA, а не blob SHA) ([worker/github_client.py:342](worker/github_client.py:342)).

9. **Связь Issue↔MR** — в GitHub есть Timeline API с событием `cross-referenced`. В GitLab аналога нет, граф собирается из `related_merge_requests`, `closed_by` и системных нот ([worker/github_client.py:419](worker/github_client.py:419)).

10. **Состояние работ** — этап 1 (закалка, PR #116) сделан, этапы 2 и 3 не начинались. Нет эндпоинта `/gitlab/webhook`, проверки подписи GitLab, клиента GitLab API, переменных `GITLAB_*`, драйвера провайдера `poh-forge`.

# Открытые вопросы

1. Какой формат нормализатора событий GitLab? Какие поля `ForgeEvent` нужно расширить для поддержки GitLab?
2. Какой выбрать подход для аутентификации в GitLab API — PAT или OAuth App?
3. Как организовать драйвер провайдера `poh-forge` — абстрактный базовый класс или два отдельных клиента?
4. Нужно ли поддерживать GitLab self-hosted или только gitlab.com?
5. Как мигрировать `poh-pr-agents` — отдельный проект или модуль в `poh-issue-agents`?
6. Как тестировать GitLab-интеграцию — моковый сервер или живый стенд?

# Диалог

**Ход 1:** Webhook эндпоинт — `webhook/main.py` обрабатывает GitHub события через `/webhook` с проверкой подписи. Отдельного эндпоинта для GitLab нет. Единственное упоминание GitLab — в докстринге про отсутствие ретраев.

**Ход 2:** Клиент GitHub API — `worker/github_client.py` с аутентификацией через GitHub App или PAT. Методы для issues, comments, labels, branches, PR. Все заточены под GitHub.

**Ход 3:** Метод `review_text` фильтрует комментарии по `user.type == "Bot"`. В GitLab нет поля `type` → функция вернёт пустоту — молчаливый отказ.

**Ход 4:** Метод `search_candidates` использует gh CLI. В GitLab нет gh CLI, нужен REST API.

**Ход 5:** Модуль `shared/labels.py` с константами меток протокола. `HUMAN_DECISION_LABELS` — точки решения человека.

**Ход 6:** Обработка `issues.labeled` — GitHub присылает `payload["label"]["name"]` напрямую. В GitLab формат `changes.labels.previous/current`.

**Ход 7:** `shared/repo_ref.py` — единственный настоящий GitLab-код с константами и `api_segment` для кодирования пути в URL.

**Ход 8:** `poh-pr-agents` — отдельный сервис с собственным вебхуком и клиентом. Та же проблема с фильтрацией по `user.type == "Bot"`. Два хода подряд дали одну проблему — остановка.


---
session: rw-analysis-po-helper-org__poh-issue-agents-241
workspace: contour
turns: 11
started: 2026-08-24T03:30:17Z
finished: 2026-08-24T03:31:05Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-issue-agents` | `993d8561f100` | 27 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 27 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "po-helper-org/poh-issue-agents",
  "include": [
    "content"
  ]
}
```

**Ответ:**

{
  "error": "Unknown repo 'po-helper-org/poh-issue-agents'. Available: ['poh-bft-writer', 'poh-cortex', 'poh-helper', 'poh-infra', 'poh-issue-agents', 'poh-memory-engine', 'poh-pr-agents', 'poh-scheduller', 'poh-sprint-agents']",
  "remedy": "Call list_repos to see the valid repo aliases, or omit the 'repo' argument to use the default repository."
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
      "last_commit_at_index": "a1db4f02f10c0d144bc2a8222b3865a6eecb9dc4"
    },
    {
      "alias": "poh-issue-agents",
      "path": "poh-issue-agents",
      "absolute_path": "/workspaces/contour/poh-issue-agents",
      "is_default": true,
      "indexed_at": "2026-08-19T16:06:57.382649+00:00",
      "last_commit_at_index": "993d8561f100c3a36cdad946a4c9d33fd0dfc5e5"
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

## Ход 3 · `get_overview` · contour

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
    "average_health": 8.34,
    "band": "healthy",
    "hotspot_health": 5.41,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 531,
    "file_count": 375,
    "distribution": {
      "total_files": 375,
      "total_nloc": 56077,
      "bands": {
        "healthy": {
          "files": 338,
          "nloc": 42581,
          "pct": 75.9
        },
        "warning": {
          "files": 33,
          "nloc": 7741,
          "pct": 13.8
        },
        "alert": {
          "files": 4,
          "nloc": 5755,
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
    "files_git_attributed": 378,
    "hotspot_count": 47,
    "avg_bus_factor": 0.7,
    "files_with_bus_factor_1": 124,
    "churn_trend": "increasing",
    "top_churn_modules": [
      ".claude/skills",
      "worker/activities.py",
      "worker/workflows.py",
      "docs/superpowers",
      "worker/worker.py"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 96,
        "percentage": 25.4
      },
      {
        "name": "kibarik",
        "files_owned": 71,
        "percentage": 18.8
      },
      {
        "name": "openhands-agent",
        "files_owned": 11,
        "percentage": 2.9
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
      "label": "tests (17)",
      "size": 10
    },
    {
      "id": 2,
      "label": "server",
      "size": 7
    },
    {
      "id": 3,
      "label": "tests (17)",
      "size": 7
    },
    {
      "id": 4,
      "label": "tests (37)",
      "size": 5
    },
    {
      "id": 5,
      "label": "external:~/threads",
      "size": 3
    },
    {
      "id": 6,
      "label": "tests (6)",
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
    "total_pages": 269,
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
        "descendants": 9
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 49
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
        "descendants": 112
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
        "page_id": "symbol_spotlight:tests/conftest.py::forge_env",
        "title": "Symbol: tests.conftest.forge_env",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::forge_env"
      },
      {
        "section": "22",
        "page_id": "symbol_spotlight:tests/conftest.py::make_fake_set_labels",
        "title": "Symbol: tests.conftest.make_fake_set_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::make_fake_set_labels"
      },
      {
        "section": "23",
        "page_id": "symbol_spotlight:tests/conftest.py::rules",
        "title": "Symbol: tests.conftest.rules",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::rules"
      },
      {
        "section": "24",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::FakeGitHub",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::FakeGitHub"
      },
      {
        "section": "25",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::__init__",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.__init__",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::__init__"
      },
      {
        "section": "26",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_label",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_label",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_label"
      },
      {
        "section": "27",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_reaction",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_reaction",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_reaction"
      },
      {
        "section": "28",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::branch_exists",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.branch_exists",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::branch_exists"
      },
      {
        "section": "29",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::comment",
        "title": "Symbol: tests.test_estimate_activities.comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::comment"
      },
      {
        "section": "30",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::fake",
        "title": "Symbol: tests.test_estimate_activities.fake",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::fake"
      },
      {
        "section": "31",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_file",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_file",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_file"
      },
      {
        "section": "32",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_issue",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_issue",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_issue"
      },
      {
        "section": "33",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::list_comments",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.list_comments",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::list_comments"
      },
      {
        "section": "34",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::post_comment",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.post_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::post_comment"
      },
      {
        "section": "35",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment",
        "title": "Symbol: tests.test_estimate_activities.test_ack_puts_eyes_on_the_command_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment"
      },
      {
        "section": "36",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread",
        "title": "Symbol: tests.test_estimate_activities.test_bot_comments_and_commands_are_excluded_from_the_thread",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread"
      },
      {
        "section": "37",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch",
        "title": "Symbol: tests.test_estimate_activities.test_bug_branch_is_used_when_there_is_no_research_branch",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch"
      },
      {
        "section": "38",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown",
        "title": "Symbol: tests.test_estimate_activities.test_compute_activity_returns_rendered_markdown",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown"
      },
      {
        "section": "39",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_context_carries_title_body_and_labels",
        "title": "Symbol: tests.test_estimate_activities.test_context_carries_title_body_and_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_context_carries_title_body_and_labels"
      },
      {
        "section": "40",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts",
        "title": "Symbol: tests.test_estimate_activities.test_error_reports_the_stage_and_reacts",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts"
      }
    ],
    "sections_total": 91,
    "sections_truncated": true
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 57
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 139
      },
      {
        "name": "Utility",
        "description": "",
        "file_count": 21
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 45
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 113
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
      "section": "6.20"
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
      "co_change_count": 78,
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
            "poh-infra",
            "poh-issue-agents"
          ],
          "edge_count": 4
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
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "87a528171e88"
      ],
      "tokens": 2044,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "omission_marker": "[repowise#87a528171e88: 55 lines omitted (~2044 tokens); restore: repowise expand 87a528171e88]"
}

## Ход 4 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "webhook/main.py"
  ],
  "include": [
    "skeleton",
    "callers",
    "callees"
  ],
  "repo": "poh-issue-agents"
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
        "fix_count": 6,
        "last_fix_days_ago": 2,
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
      "callers": [
        {
          "file": "tests/test_sentry_noise.py",
          "imports": true,
          "inbound_calls": 1
        },
        {
          "file": "tests/test_agent_comment.py",
          "imports": true
        },
        {
          "file": "tests/test_agent_event_endpoint.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_webhook.py",
          "imports": true
        },
        {
          "file": "tests/test_e2e_issue_lifecycle.py",
          "imports": true
        },
        {
          "file": "tests/test_gitlab_webhook_resilience.py",
          "imports": true
        },
        {
          "file": "tests/test_trigger_authz.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_audit.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_comment_commands.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_issue_closed.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_label_trigger.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_labeled.py",
          "imports": true
        },
        {
          "file": "tests/test_webhook_never_5xx.py",
          "imports": true
        }
      ],
      "_call_graph_note": "File-level rollup: importing files plus inbound cross-file call counts. For symbol-precise callers pass 'file.py::Symbol'.",
      "callees": [],
      "skeleton": {
        "mode": "smart",
        "tokens": 2072,
        "full_tokens": 7352,
        "pct_of_full": 28.2,
        "bodies_kept": [
          "_client_disconnect",
          "_log_effective_config",
          "_audit_dropped_delivery",
          "verify_signature",
          "_handle_delivery"
        ],
        "text": "\"\"\"\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и\n                               через signal-with-start поднимает цикл-владелец\n                               состояния, `/estimate` — IssueEstimation,\n                               `/bft` и `/bft-deep` — IssueBft (хвост команды\n                               уезжает в прогон как замечания/уточнения); любой\n                               другой комментарий — сигнал уже идущему workflow\n                               (используется циклом уточнений)\n- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и\n                               команда в комментарии (run:analyze ->\n                               IssueAnalysis, run:estimate -> IssueEstimation,\n                               run:bft / run:bft-deep -> IssueBft);\n                               точки решения человека (research-me / bug-me /\n                               build-me) идут через signal-with-start: воркфлоу\n                               триажа может не существовать, тогда он\n                               поднимается тем же вызовом\n\nНичего из бизнес-логики здесь нет — это чистый транспортный слой.\n\"\"\"\nimport hashlib\nimport hmac\nimport logging\nimport os\nfrom fastapi import FastAPI, Header, HTTPException, Request, Response\nfrom starlette.requests import ClientDisconnect\nfrom temporalio.client import Client\nfrom temporalio.exceptions import WorkflowAlreadyStartedError\nfrom shared import sentry_setup\nfrom shared.commands import (\n    ... 10 lines (36-45)\nfrom shared.agent_comment import is_agent_comment\nfrom shared.agent_launcher import request_analysis, request_bft, request_estimate\nfrom shared.authz import may_trigger, trigger_allowlist\nfrom shared.labels import HUMAN_DECISION_LABELS, parse_root_issue\nfrom shared.repos import allowed_specs, is_allowed\nfrom shared.temporal_client import connect_temporal\nfrom shared.workflow_ids import (\n    ... 9 lines (53-61)\n_log = logging.getLogger(\"webhook\")\n\napp = FastAPI()\n\n\n@app.exception_handler(ClientDisconnect)\nasync def _client_disconnect(request: Request, exc: ClientDisconnect):\n    \"\"\"Отправитель ушёл, не дослав тело.\n\n    Отвечать 500 некому: соединения уже нет, а событие уезжает в Sentry как\n    сбой вебхука (ISSUE-AGENT-8, пять штук за один разрыв связи с прокси).\n    Доставка не потеряна: GitHub повторит её сам. У GitLab ретраев нет — там\n    оборванная доставка теряется, поэтому обработчик ниже принимает всё, что\n    прошло подпись, и разбирается внутри. 204 закрывает запрос тихо и\n    оставляет след в логе.\n    \"\"\"\n    _log.info(\"отправитель разорвал соединение до конца тела (%s) — доставка будет повторена\",\n              request.headers.get(\"x-github-delivery\", \"без id\"))\n    return Response(status_code=204)\n\n\ndef _log_effective_config() -> None:\n    \"\"\"Один раз на старте — какой конфиг реально действует.\n\n    Секреты не логируются: только режим авторизации. Полная картина —\n    `scripts/diag.py` внутри контейнера; эта строка нужна, чтобы после\n    передеплоя не гадать, подхватились ли переменные.\n    \"\"\"\n    specs = [s for s in allowed_specs() if s.strip()]\n    if os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\"):\n        auth = \"PAT (перебивает GitHub App)\" if os.environ.get(\"GITHUB_APP_ID\") else \"PAT\"\n    elif os.environ.get(\"GITHUB_APP_ID\"):\n        auth = \"GitHub App\"\n    else:\n        auth = \"НЕ НАСТРОЕНА\"\n    _log.info(\n        \"effective config: ISSUE_AGENT_REPOS=%s auth=%s temporal=%s/%s\",\n        specs or [\"(пусто — любой репозиторий)\"], auth,\n        os.environ.get(\"TEMPORAL_ADDRESS\", \"localhost:7233\"),\n        os.environ.get(\"TEMPORAL_NAMESPACE\", \"default\"),\n    )\n\n\n_log_effective_config()\n\n_temporal_client: Client | None = None\n\n\nasync def get_temporal_client() -> Client:\n    ... 4 lines (111-114)\n\n\ndef verify_signature(body: bytes, signature_header: str | None) -> None:\n    secret = os.environ[\"GITHUB_WEBHOOK_SECRET\"].encode()\n    if not signature_header or not signature_header.startswith(\"sha256=\"):\n        raise HTTPException(status_code=401, detail=\"Missing signature\")\n    expected = \"sha256=\" + hmac.new(secret, body, hashlib.sha256).hexdigest()\n    if not hmac.compare_digest(expected, signature_header):\n        raise HTTPException(status_code=401, detail=\"Invalid signature\")\n\n\n# Формат ID живёт в shared/workflow_ids.py: его же собирают скрипты прямого\n# запуска, и разъехавшись, они потеряли бы идемпотентность.\nworkflow_id_for = issue_workflow_id\nestimate_workflow_id_for = estimate_workflow_id\n\n\ndef _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None:\n    \"\"\"Сквозной ключ цепочки в Temporal: `RootIssue` и `Repo`.\n... 20 lines (134-153)\n\n\ndef _issue_input(payload: dict, *, interactive: bool):\n    \"\"\"`IssueInput` из полезной нагрузки вебхука.\n... 16 lines (158-173)\n\n\ndef _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:\n    \"\"\"Гейт на запуск дорогой стадии + аудит того, кто её запустил.\n... 21 lines (178-198)\n\n\nasync def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None,\n                                  repo: str, specs: list[str]) -> None:\n    \"\"\"След в Temporal UI для события, отброшенного по allowlist.\n\n    Единственный молчаливый отказ, о котором иначе неоткуда узнать: workflow не\n    создаётся, GitHub получает 200. Аудит-воркфлоу не исполняет ни одной\n    activity — его ценность в том, что вход виден там же, где смотрят всё\n    остальное: пришло, отклонено, вот причина и вот действовавший allowlist.\n\n    Без заголовка X-GitHub-Delivery (ручной curl, тест) аудит пропускаем: без\n    уникального id ретраи GitHub плодили бы дубли. Сбой самого аудита тоже не\n    должен ронять обработку — это диагностика, а не путь события.\n    \"\"\"\n    if not delivery_id:\n        return\n    from shared.workflow_types import WebhookAuditInput\n\n    ... 19 lines (218-236)\n\n\nasync def _ack_comment_seen(client, repo: str, issue_number: int,\n                            comment_id: int) -> None:\n    \"\"\"Реакция `eyes` на принятый комментарий — отдельным прогоном.\n... 23 lines (242-264)\n\n\ndef verify_agent_signature(body: bytes, signature_header: str | None) -> None:\n    \"\"\"Подпись входящего события агента — своим секретом, не гитхабовским.\n... 14 lines (269-282)\n\n\nasync def _report_orphan(client, event, reason: str) -> None:\n    \"\"\"Событие, которое не удалось связать с Issue, не пропадает молча.\n... 21 lines (287-307)\n\n\n@app.post(\"/agent-event\")\nasync def agent_event(\n    request: Request,\n    x_agent_signature_256: str | None = Header(None),\n):\n    \"\"\"Приём фактов от внешних агентов контура (#38).\n... 37 lines (316-352)\n\n\ndef _lifecycle_args_for(event, issue_number: int) -> list:\n    \"\"\"Аргументы старта цикла для события агента.\n... 23 lines (357-379)\n\n\n@app.post(\"/webhook\")\nasync def github_webhook(\n    request: Request,\n    x_github_event: str = Header(...),\n    x_hub_signature_256: str | None = Header(None),\n    x_github_delivery: str | None = Header(None),\n):\n    \"\"\"Приём доставки. Отказать может только подпись.\n... 22 lines (390-411)\n\n\nasync def _handle_delivery(payload: dict, x_github_event: str,\n                           x_github_delivery: str | None):\n    # Allowlist: действуем только на репозитории из ISSUE_AGENT_REPOS (пусто/* —\n    # любой установленный). Чужой репозиторий игнорируем до старта workflow.\n    repo_full = (payload.get(\"repository\") or {}).get(\"full_name\")\n    if repo_full and not is_allowed(repo_full, allowed_specs()):\n        specs = [s for s in allowed_specs() if s.strip()]\n        # warning, а не info, и вместе с действующим allowlist: строка лога\n        # обязана сама говорить, что чинить. Раньше отказ был неотличим от\n        # тишины — GitHub видел 200, в Temporal не появлялось ничего.\n        _log.warning(\n            \"ignored repo %s — not in ISSUE_AGENT_REPOS %s; событие отброшено до Temporal\",\n            repo_full, specs or [\"(пусто)\"],\n        )\n        await _audit_dropped_delivery(payload, x_github_event, x_github_delivery,\n                                      repo_full, specs)\n        ... 223 lines (430-652)\n",
        "verified": true
      },
      "episodes": 6
    }
  },
  "_meta": {
    "timing_ms": 67.49,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
    "worker/github_client.py"
  ],
  "include": [
    "skeleton",
    "callers",
    "callees"
  ],
  "repo": "poh-issue-agents"
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
        "fix_count": 9,
        "last_fix_days_ago": 2,
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
      "callers": [
        {
          "file": "worker/activities.py",
          "imports": true,
          "inbound_calls": 62
        },
        {
          "file": "tests/test_github_client_pr.py",
          "imports": true,
          "inbound_calls": 5
        },
        {
          "file": "scripts/e2e_live.py",
          "imports": true,
          "inbound_calls": 4
        },
        {
          "file": "tests/test_dev_handoff_once.py",
          "imports": true,
          "inbound_calls": 3
        },
        {
          "file": "tests/test_github_client_linked_prs.py",
          "imports": true,
          "inbound_calls": 3
        },
        {
          "file": "worker/consolidation_activities.py",
          "imports": true,
          "inbound_calls": 3
        },
        {
          "file": "tests/test_github_client_list.py",
          "imports": true,
          "inbound_calls": 2
        },
        {
          "file": "scripts/bootstrap_labels.py",
          "imports": true,
          "inbound_calls": 1
        },
        {
          "file": "tests/test_agent_comment.py",
          "imports": true,
          "inbound_calls": 1
        },
        {
          "file": "tests/test_github_client_analyze.py",
          "imports": true
        },
        {
          "file": "tests/test_github_client_auth.py",
          "imports": true
        },
        {
          "file": "tests/test_github_client_contract.py",
          "imports": true
        },
        {
          "file": "tests/test_github_client_dryrun.py",
          "imports": true
        },
        {
          "file": "tests/test_github_client_labels.py",
          "imports": true
        },
        {
          "file": "tests/test_set_labels.py",
          "imports": true
        },
        {
          "file": "tests/test_transport_url_encoding.py",
          "imports": true
        }
      ],
      "_call_graph_note": "File-level rollup: importing files plus inbound cross-file call counts. For symbol-precise callers pass 'file.py::Symbol'.",
      "callees": [],
      "skeleton": {
        "mode": "smart",
        "tokens": 1987,
        "full_tokens": 8045,
        "pct_of_full": 24.7,
        "bodies_kept": [
          "_auth_headers",
          "_warn_pat_over_app",
          "_installation_token_for",
          "post_comment",
          "_app_private_key"
        ],
        "text": "\"\"\"\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\"\"\"\n\nimport base64\nimport logging\nimport os\nimport subprocess\nimport threading\nimport time\nimport urllib.parse\nfrom collections.abc import Sequence\n\nimport jwt\nimport requests\n\nfrom shared.agent_comment import is_agent_comment, sign\nfrom shared.labels import ORIGIN_AGENT\n\n_log = logging.getLogger(\"github_client\")\n\n\ndef _dry_run() -> bool:\n    ... 7 lines (27-33)\n_token_cache: dict[str, tuple[str, float]] = {}\n_token_lock = threading.Lock()\n\n\ndef _app_private_key() -> bytes:\n    \"\"\"Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла\n    GITHUB_PRIVATE_KEY_PATH (обратная совместимость).\"\"\"\n    b64 = os.environ.get(\"GITHUB_PRIVATE_KEY_B64\")\n    if b64:\n        return base64.b64decode(b64)\n    with open(os.environ[\"GITHUB_PRIVATE_KEY_PATH\"], \"rb\") as f:\n        return f.read()\n\n\ndef _app_jwt() -> str:\n    ... 3 lines (49-51)\n\n\ndef _cached_token(repo: str) -> str | None:\n    ... 4 lines (55-58)\n\n\ndef _installation_token_for(repo: str) -> str:\n    \"\"\"Installation-токен под установку App на данный репозиторий. Установка\n    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →\n    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.\n\n    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому\n    cache-hit по одному репо не блокируется за token-обменом другого. Lock\n    сериализует только сам обмен (редкий — раз в ~55 мин на репо).\"\"\"\n    hot = _cached_token(repo)\n    if hot is not None:\n        return hot\n    with _token_lock:\n        warm = _cached_token(repo)  # перепроверка под lock: конкурент мог уже выпустить\n        if warm is not None:\n            ... 15 lines (75-89)\n\n\ndef _installation_token_headers(repo: str) -> dict:\n    return {\"Authorization\": f\"Bearer {_installation_token_for(repo)}\",\n            \"Accept\": \"application/vnd.github+json\"}\n\n\n_pat_over_app_warned = False\n\n\ndef _warn_pat_over_app() -> None:\n    \"\"\"Один раз на процесс: PAT задан вместе с App и молча его отключает.\n\n    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от\n    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный\n    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.\n    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.\n    \"\"\"\n    global _pat_over_app_warned\n    if _pat_over_app_warned:\n        return\n    _pat_over_app_warned = True\n    _log.warning(\n        \"GH_TOKEN/GITHUB_TOKEN задан одновременно с GITHUB_APP_ID: GitHub App НЕ \"\n        \"используется, все действия идут от имени владельца токена. Убери PAT, \"\n        \"если ожидаешь работу от приложения (см. scripts/diag.py).\"\n    )\n\n\ndef _auth_headers(repo: str) -> dict:\n    \"\"\"PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.\"\"\"\n    token = os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\")\n    if token:\n        if os.environ.get(\"GITHUB_APP_ID\"):\n            _warn_pat_over_app()\n        return {\"Authorization\": f\"Bearer {token}\", \"Accept\": \"application/vnd.github+json\"}\n    return _installation_token_headers(repo)\n\n\ndef post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    ... 6 lines (139-144)\n\n\ndef _post_labels(repo: str, issue_number: int, labels: list[str]) -> None:\n    ... 3 lines (148-150)\n\n\ndef add_label(repo: str, issue_number: int, label: str) -> None:\n    ... 4 lines (154-157)\n\n\ndef remove_label(repo: str, issue_number: int, label: str) -> None:\n    \"\"\"Снимает метку. Отсутствующая метка (404) — штатная ситуация, а не ошибка:\n    ... 15 lines (162-176)\n\n\ndef set_labels(repo: str, issue_number: int, *,\n               add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:\n    \"\"\"Приводит набор меток к нужному виду одной операцией.\n... 42 lines (182-223)\n\n\ndef ensure_labels_exist(repo: str, specs) -> int:\n    \"\"\"Заводит недостающие метки. Возвращает число созданных.\n... 39 lines (228-266)\n\n\ndef create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    \"\"\"Создаёт Issue и возвращает его номер.\n... 15 lines (271-285)\n\n\ndef close_issue(repo: str, issue_number: int) -> None:\n    ... 6 lines (289-294)\n\n\ndef search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:\n    \"\"\"Через gh CLI — тот же паттерн, что и в версии на Actions, но токен\n    ... 14 lines (299-312)\n\n\ndef branch_exists(repo: str, branch: str) -> bool:\n    ... 3 lines (316-318)\n\n\ndef auth_token(repo: str) -> str:\n    \"\"\"Голый токен для внешних процессов (git clone, gh CLI).\n... 4 lines (323-326)\n\n\ndef add_reaction(repo: str, comment_id: int, content: str = \"eyes\") -> None:\n    \"\"\"Реакция на комментарий — видимое «команда принята» до тяжёлой работы.\n    ... 7 lines (331-337)\n\n\ndef ensure_branch(repo: str, branch: str) -> None:\n    \"\"\"Создаёт ветку от дефолтной, если её ещё нет.\"\"\"\n    ... 23 lines (342-364)\n\n\ndef put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:\n    \"\"\"Создаёт или обновляет файл в ветке через Contents API.\n... 19 lines (369-387)\n\n\ndef push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    ... 7 lines (392-398)\n\n\ndef get_issue(repo: str, issue_number: int) -> dict:\n    ... 4 lines (402-405)\n\n\ndef list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:\n    ... 6 lines (409-414)\n\n\ndef list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:\n    \"\"\"PR, кросс-ссылающиеся на issue (Timeline API).\n... 35 lines (419-453)\n\n\ndef get_file(repo: str, path: str, ref: str) -> str | None:\n    \"\"\"Содержимое файла из ветки. None — файла нет; для артефактов это\n    ... 11 lines (458-468)\n\n\ndef create_pr_with_files(repo: str, branch: str, base: str,\n                         files: dict, title: str, body: str):\n    ... 32 lines (473-504)\n\n\ndef list_open_issues(repo: str, limit: int = 300) -> list:\n    ... 16 lines (508-523)\n\n\ndef get_issue_body(repo: str, issue_number: int) -> str:\n    ... 4 lines (527-530)\n\n\ndef dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:\n    \"\"\"Запускает workflow репозитория-цели через `workflow_dispatch`.\n... 18 lines (535-552)\n\n\nclass GitCommandError(RuntimeError):\n    \"\"\"Отказ git с сохранённой причиной.\n... 6 lines (557-562)\n\n\ndef _git_runner(clone_dir: str, env: dict):\n    \"\"\"git по рабочему дереву задачи, с видимой причиной отказа.\n... 19 lines (567-585)\n\n\ndef publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n... 84 lines (591-674)\n\n\ndef _default_branch(repo: str) -> str:\n    ... 4 lines (678-681)\n\n\ndef get_pull(repo: str, number: int) -> dict:\n    ... 4 lines (685-688)\n\n\ndef review_text(repo: str, number: int, limit: int = 12000) -> str:\n    \"\"\"Замечания ревью одним текстом: обзорные комментарии + построчные.\n... 42 lines (693-734)\n\n\ndef push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:\n    \"\"\"Коммит правок в ветку PR. False — агент ничего не изменил.\n... 31 lines (739-769)\n\n\ndef update_issue_body(repo: str, issue_number: int, body: str) -> None:\n    ... 6 lines (773-778)\n",
        "verified": true
      },
      "episodes": 9,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.623
          },
          {
            "repo": "poh-bft-writer",
            "file": "commands/bft-draft.md",
            "strength": 0.503
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 74.34,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/github_client.py::review_text",
  "repo": "poh-issue-agents"
}
```

**Ответ:**

{
  "symbol_id": "worker/github_client.py::review_text",
  "file": "worker/github_client.py",
  "name": "review_text",
  "kind": "function",
  "qualified_name": "worker.github_client.review_text",
  "signature": "def review_text(repo: str, number: int, limit: int = 12000) -> str",
  "language": "python",
  "start_line": 691,
  "end_line": 734,
  "symbol_start_line": 691,
  "symbol_end_line": 734,
  "source": "   691\tdef review_text(repo: str, number: int, limit: int = 12000) -> str:\n   692\t    \"\"\"Замечания ревью одним текстом: обзорные комментарии + построчные.\n   693\t\n   694\t    Берутся комментарии БОТОВ и построчные замечания — они и есть ревью.\n   695\t    Реплики людей в тред сюда не попадают: круг правок отвечает ревьюеру, а не\n   696\t    участвует в обсуждении, и подмешивать туда чужие реплики значит кормить\n   697\t    агента спором вместо задачи.\n   698\t    \"\"\"\n   699\t    parts: list[str] = []\n   700\t\n   701\t    reviews = requests.get(f\"https://api.github.com/repos/{repo}/pulls/{number}/reviews\",\n   702\t                           headers=_auth_headers(repo), params={\"per_page\": 50}, timeout=30)\n   703\t    if reviews.ok:\n   704\t        for item in reviews.json():\n   705\t            body = (item.get(\"body\") or \"\").strip()\n   706\t            if body:\n   707\t                parts.append(f\"### Ревью ({item.get('state','')})\\n{body}\")\n   708\t\n   709\t    inline = requests.get(f\"https://api.github.com/repos/{repo}/pulls/{number}/comments\",\n   710\t                          headers=_auth_headers(repo), params={\"per_page\": 100}, timeout=30)\n   711\t    if inline.ok:\n   712\t        for item in inline.json():\n   713\t            body = (item.get(\"body\") or \"\").strip()\n   714\t            if body:\n   715\t                where = f\"{item.get('path')}:{item.get('line') or item.get('original_line') or '?'}\"\n   716\t                parts.append(f\"### {where}\\n{body}\")\n   717\t\n   718\t    issue_comments = requests.get(\n   719\t        f\"https://api.github.com/repos/{repo}/issues/{number}/comments\",\n   720\t        headers=_auth_headers(repo), params={\"per_page\": 100}, timeout=30)\n   721\t    if issue_comments.ok:\n   722\t        for item in issue_comments.json():\n   723\t            if (item.get(\"user\") or {}).get(\"type\") != \"Bot\":\n   724\t                continue\n   725\t            body = (item.get(\"body\") or \"\").strip()\n   726\t            # Комментарии контура — тоже от бота: он ходит в GitHub как App.\n   727\t            # Без этого фильтра на втором круге агент читал собственную просьбу\n   728\t            # «внёс правки, прошу перепроверить» как часть замечаний и правил по\n   729\t            # ней — то есть спорил сам с собой вместо ревьюера.\n   730\t            if body and not is_agent_comment(body):\n   731\t                parts.append(body)\n   732\t\n   733\t    text = \"\\n\\n\".join(parts)\n   734\t    return text[-limit:] if len(text) > limit else text",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 9.5,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 8045
  }
}

## Ход 7 · `get_symbol` · contour

**Запрос:**

```json
{
  "repo": "poh-issue-agents",
  "symbol_id": "worker/github_client.py::search_candidates"
}
```

**Ответ:**

{
  "symbol_id": "worker/github_client.py::search_candidates",
  "file": "worker/github_client.py",
  "name": "search_candidates",
  "kind": "function",
  "qualified_name": "worker.github_client.search_candidates",
  "signature": "def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]",
  "language": "python",
  "start_line": 297,
  "end_line": 312,
  "symbol_start_line": 297,
  "symbol_end_line": 312,
  "source": "   297\tdef search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:\n   298\t    \"\"\"Через gh CLI — тот же паттерн, что и в версии на Actions, но токен\n   299\t    для gh нужно прокинуть через переменную окружения перед вызовом.\"\"\"\n   300\t    env = {**os.environ, \"GH_TOKEN\": auth_token(repo)}\n   301\t    candidates = []\n   302\t    for kind in (\"issue\", \"pr\"):\n   303\t        fields = \"number,title,body,url,state,labels\" if kind == \"issue\" else \"number,title,body,url,state\"\n   304\t        cmd = [\"gh\", kind, \"list\", \"--repo\", repo, \"--state\", \"all\", \"--search\", query, \"--limit\", str(limit), \"--json\", fields]\n   305\t        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)\n   306\t        if result.returncode != 0:\n   307\t            continue\n   308\t        import json\n   309\t        for item in json.loads(result.stdout or \"[]\"):\n   310\t            item[\"_kind\"] = kind\n   311\t            candidates.append(item)\n   312\t    return candidates[:limit]",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 9.9,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 8045
  }
}

## Ход 8 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/labels.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/labels.py": {
      "target": "shared/labels.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/labels.py",
        "summary": "Словарь меток протокола агентов v1."
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
        "tokens": 956,
        "full_tokens": 1239,
        "pct_of_full": 77.2,
        "bodies_kept": [
          "parse_root_issue"
        ],
        "text": "\"\"\"Словарь меток протокола агентов v1.\n\nИсточник: po-helper-org/.github → AGENT-PROTOCOL.md, раздел 4. Правило протокола —\n**одна метка, один писатель**: метку из чужой зоны агент только читает, иначе два\nагента затирают друг друга.\n\nЗдесь живут:\n- Метки контура (общие для Issue-Agent, PR-Agent, PR-Closer)\n- Внутренние метки Issue-Agent (`advisor:*`, `priority:*`, плоские метки)\n\nКонстанты живут здесь, чтобы и вебхук, и воркер, и каталог меток читали из\nодного источника — иначе новый добавленный в коде label не попадёт в каталог и\nразъедется.\n\nМодуль намеренно без зависимостей: его читают и вебхук, и воркер.\n\"\"\"\n\nimport re\n\n# --- Очередь к человеку: единый префикс на всю организацию ---\n# Было врозь: `needs-human-triage` здесь и `pr-closer:needs-human` в PR-Closer.\n# Одна выборка `label:needs-human:*` теперь показывает всю очередь к людям.\nNEEDS_HUMAN_PREFIX = \"needs-human:\"\nNEEDS_HUMAN_TRIAGE = f\"{NEEDS_HUMAN_PREFIX}triage\"\n\n# Историческое имя. Оставлено ради поиска по старым Issue: сервис его больше не\n# ставит, но выборка по бэклогу до перехода всё ещё им пользуется.\nLEGACY_NEEDS_HUMAN_TRIAGE = \"needs-human-triage\"\n... 5 lines (29-33)\nREADY_FOR_DEV = \"ready-for-dev\"\n\n# --- Рубильник человека (R4) ---\n# Ставит человек, читают все агенты. Проверяется раньше первого обращения к LLM:\n# смысл в том, чтобы не тратить бюджет на то, что человек уже забрал себе.\nAGENTS_OFF = \"agents:off\"\n\n# --- Провенанс (R6) ---\n# Артефакт, созданный агентом. Без него агенты не отличают вход от собственного\n# выхода, и контур начинает кормить сам себя.\nORIGIN_AGENT = \"origin:agent\"\n... 8 lines (45-52)\nADVISOR_PREFIX = \"advisor:\"\nADVISOR_EXISTING = f\"{ADVISOR_PREFIX}existing-functionality\"\nADVISOR_CONSULTATION = f\"{ADVISOR_PREFIX}consultation\"\nADVISOR_BUG = f\"{ADVISOR_PREFIX}bug\"\nADVISOR_FEATURE = f\"{ADVISOR_PREFIX}feature-request\"\nADVISOR_ANSWERED = f\"{ADVISOR_PREFIX}answered\"\nADVISOR_LABELS = frozenset({\n    ADVISOR_EXISTING,\n    ADVISOR_CONSULTATION,\n    ADVISOR_BUG,\n    ADVISOR_FEATURE,\n    ADVISOR_ANSWERED,\n})\n\n# Приоритеты: рассчитываются по формуле Cost of Delay / Effort\nPRIORITY_PREFIX = \"priority:\"\nPRIORITY_P0 = f\"{PRIORITY_PREFIX}P0\"\nPRIORITY_P1 = f\"{PRIORITY_PREFIX}P1\"\nPRIORITY_P2 = f\"{PRIORITY_PREFIX}P2\"\nPRIORITY_P3 = f\"{PRIORITY_PREFIX}P3\"\nPRIORITY_LABELS = frozenset({PRIORITY_P0, PRIORITY_P1, PRIORITY_P2, PRIORITY_P3})\n\n# Плоские метки: используются в разных точках контура\nBOT_AUTHORED = \"bot-authored\"\nSECURITY_SENSITIVE = \"security-sensitive\"\nNEEDS_CLARIFICATION = \"needs-clarification\"\nSPAM = \"spam\"\nDUPLICATE = \"duplicate\"\nPOSSIBLE_DUPLICATE = \"possible-duplicate\"\nESTIMATED = \"estimated\"\nFLAT_LABELS = frozenset({\n    BOT_AUTHORED,\n    SECURITY_SENSITIVE,\n    NEEDS_CLARIFICATION,\n    SPAM,\n    DUPLICATE,\n    POSSIBLE_DUPLICATE,\n    ESTIMATED,\n})\n... 9 lines (92-100)\nHUMAN_DECISION_LABELS = {\"research-me\", \"bug-me\", \"build-me\", \"not-duplicate\", \"confirm-duplicate\"}\n\n# Сквозной ключ цепочки: строка `root-issue: #N` в теле follow-up Issue\n# (AGENT-PROTOCOL.md, раздел 3). По ней Issue-Agent находит исходную задачу и\n# считает глубину.\n_ROOT_ISSUE_RE = re.compile(r\"^\\s*root-issue:\\s*#(\\d+)\\s*$\", re.IGNORECASE | re.MULTILINE)\n\n\ndef parse_root_issue(body: str | None) -> int | None:\n    \"\"\"Номер исходного Issue из тела follow-up, иначе None.\n\n    Отсутствие ключа — штатная ситуация, а не ошибка: PR мог не ссылаться на\n    Issue, тогда follow-up вешается на PR и `root-issue` неизвестен.\n    \"\"\"\n    if not body:\n        return None\n    match = _ROOT_ISSUE_RE.search(body)\n    return int(match.group(1)) if match else None\n\n\ndef has(labels: list[str], name: str) -> bool:\n    \"\"\"Регистронезависимая проверка наличия метки: GitHub сохраняет регистр,\n    но считает `Agents:Off` и `agents:off` одной и той же меткой.\"\"\"\n    return name.lower() in {label.lower() for label in labels}\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 77.2% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 31.2,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 9 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-issue-agents",
  "targets": [
    "shared/repo_ref.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/repo_ref.py": {
      "target": "shared/repo_ref.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/repo_ref.py",
        "summary": "Ссылка на репозиторий, не привязанная к форме `owner/repo`."
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
        "tokens": 486,
        "full_tokens": 578,
        "pct_of_full": 84.1,
        "bodies_kept": [
          "parse",
          "api_segment"
        ],
        "text": "\"\"\"Ссылка на репозиторий, не привязанная к форме `owner/repo`.\n\nGitHub адресует репозиторий ровно двумя сегментами. GitLab — путём из двух и\nболее (подгруппы вкладываются до 20 уровней) либо числовым id проекта, причём\nпуть в URL API обязан быть закодирован целиком: `group%2Fsub%2Fproject`.\n\nКодирование живёт здесь, а не в вызывающем коде. Иначе повторяется то, что\nуже случилось в `worker/github_client.py`: имя метки там кодируется, имя файла\nворкфлоу кодируется, а путь репозитория — ни в одном из 26 URL.\n\nЧистый модуль: ни сети, ни Temporal, ни обращений к трекеру.\n\"\"\"\nfrom __future__ import annotations\n\nimport urllib.parse\nfrom dataclasses import dataclass\n\nGITHUB = \"github\"\nGITLAB = \"gitlab\"\n\n\n@dataclass(frozen=True)\nclass RepoRef:\n    \"\"\"Репозиторий у конкретного провайдера.\n... 12 lines (25-36)\n    def parse(cls, raw: str, provider: str = GITHUB,\n              project_id: int | None = None) -> \"RepoRef\":\n        path = (raw or \"\").strip().strip(\"/\")\n        segments = [s for s in path.split(\"/\") if s]\n        if len(segments) < 2:\n            raise ValueError(\n                f\"ссылка на репозиторий требует как минимум два сегмента: {raw!r}\")\n        return cls(provider=provider, path=\"/\".join(segments), project_id=project_id)\n\n    @property\n    def segments(self) -> tuple[str, ...]:\n        return tuple(self.path.split(\"/\"))\n\n    @property\n    def owner(self) -> str:\n        \"\"\"Верхнеуровневый владелец: организация GitHub или корневая группа.\"\"\"\n        return self.segments[0]\n\n    @property\n    def name(self) -> str:\n        return self.segments[-1]\n\n    @property\n    def api_segment(self) -> str:\n        \"\"\"Готовая подстановка в путь REST API.\"\"\"\n        if self.provider == GITLAB:\n            if self.project_id is not None:\n                return str(self.project_id)\n            return urllib.parse.quote(self.path, safe=\"\")\n        return self.path\n\n    def __str__(self) -> str:\n        return self.path\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 84.1% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 32.95,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
      "co_change_count": 78,
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
            "poh-infra",
            "poh-issue-agents"
          ],
          "edge_count": 4
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
    "self-hosted/reliability/github_client.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "self-hosted/reliability/github_client.py": {
      "target": "self-hosted/reliability/github_client.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/github_client.py",
        "summary": "GitHub-клиент: идемпотентная публикация комментария (СТ-25, upsert)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 39
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
        "tokens": 1439,
        "full_tokens": 2143,
        "pct_of_full": 67.1,
        "bodies_kept": [
          "_headers",
          "upsert_comment",
          "_matching_comments",
          "has_bot_activity",
          "list_pull_files"
        ],
        "text": "\"\"\"GitHub-клиент: идемпотентная публикация комментария (СТ-25, upsert).\n\n`upsert_comment` правит существующий бот-коммент, найденный по скрытому маркеру\n`<!-- reliability:... -->`, либо создаёт новый — так ретраи/reconcile не плодят\nдубликаты. Токен установки и HTTP-транспорт (method-aware) инъектируются →\nтестируется без сети и крипто. Дефолтный транспорт — stdlib urllib.\n\"\"\"\nfrom __future__ import annotations\n\nimport json\nimport urllib.request\nfrom typing import Callable, Optional\n\n# (method, url, data, headers) -> (status_code, body_bytes)\nTransport = Callable[[str, str, \"Optional[bytes]\", dict], \"tuple[int, bytes]\"]\n\n\ndef _urllib_transport(method: str, url: str, data: \"Optional[bytes]\", headers: dict):  # pragma: no cover\n    ... 3 lines (19-21)\n\n\nclass GitHubAppClient:\n    def __init__(self, token_provider: Callable[[str], str],\n                 api_base: str = \"https://api.github.com\",\n                 transport: Transport = _urllib_transport):\n        ... 3 lines (28-30)\n\n    def _headers(self, repo: str) -> dict:\n        return {\n            \"Authorization\": f\"Bearer {self._token_provider(repo)}\",\n            \"Accept\": \"application/vnd.github+json\",\n            \"Content-Type\": \"application/json\",\n            \"User-Agent\": \"pr-agent-reliability\",\n        }\n\n    def _matching_comments(self, repo: str, number: int, marker: str) -> list:\n        \"\"\"Комменты БОТА с маркером по всем страницам (пагинация — иначе на PR с\n        >30 комментами наш коммент не находится и плодится дубль). Фильтр по\n        user.type=='Bot', чтобы чужой процитированный маркер не матчился.\"\"\"\n        found, page = [], 1\n        while True:\n            s, b = self._transport(\n                \"GET\",\n                f\"{self._api}/repos/{repo}/issues/{number}/comments?per_page=100&page={page}\",\n                None, self._headers(repo))\n            if s >= 300:\n                raise RuntimeError(f\"list comments {s}: {b[:200]!r}\")\n            items = json.loads(b)\n            for c in items:\n                if marker in (c.get(\"body\") or \"\") and (c.get(\"user\") or {}).get(\"type\") == \"Bot\":\n                    found.append(c)\n            ... 3 lines (56-58)\n\n    def list_installation_repos(self, installation_token: str) -> list:\n        \"\"\"Все репозитории, доступные установке App (org-wide свипер). Пагинация.\n        ... 16 lines (62-77)\n\n    def get_pull_head_sha(self, repo: str, number: int) -> str:\n        \"\"\"head SHA открытого PR по номеру — для обогащения issue_comment-событий\n        ... 9 lines (81-89)\n\n    def get_pull_body(self, repo: str, number: int) -> str:\n        \"\"\"Тело PR — источник сквозного ключа `Closes #N` (AGENT-PROTOCOL, §3).\n... 14 lines (93-106)\n\n    def list_open_pulls(self, repo: str) -> list:\n        \"\"\"Открытые PR репозитория (по всем страницам) — для reconciliation sweeper.\"\"\"\n        ... 12 lines (110-121)\n\n    def list_pull_files(self, repo: str, number: int) -> list:\n        \"\"\"Изменённые файлы PR (пагинация): [{filename, additions, deletions, status, patch}].\n        Источник для классификатора размера (ФТ-APRP-1), плана чанков (ФТ-APRP-4) и\n        ревью чанка (ФТ-APRP-7). `patch` GitHub отдаёт и так; для бинарных/огромных\n        файлов он пустой.\"\"\"\n        out, page = [], 1\n        while True:\n            s, b = self._transport(\n                \"GET\", f\"{self._api}/repos/{repo}/pulls/{number}/files?per_page=100&page={page}\",\n                None, self._headers(repo))\n            if s >= 300:\n                raise RuntimeError(f\"list pull files {s}: {b[:200]!r}\")\n            items = json.loads(b)\n            out.extend({\"filename\": f.get(\"filename\", \"\"),\n                        \"additions\": int(f.get(\"additions\", 0)),\n                        ... 6 lines (138-143)\n\n    def has_bot_activity(self, repo: str, number: int) -> bool:\n        \"\"\"Есть ли на PR хоть один коммент от бота — опорное доказательство того,\n        что ревью опубликовано (для детекта «проглоченного» сбоя в свипере). Точную\n        эвристику артефакта донастроить на смоуке; пагинация как в _matching_comments.\"\"\"\n        page = 1\n        while True:\n            s, b = self._transport(\n                \"GET\",\n                f\"{self._api}/repos/{repo}/issues/{number}/comments?per_page=100&page={page}\",\n                None, self._headers(repo))\n            if s >= 300:\n                raise RuntimeError(f\"list comments {s}: {b[:200]!r}\")\n            items = json.loads(b)\n            if any((c.get(\"user\") or {}).get(\"type\") == \"Bot\" for c in items):\n                return True\n            ... 3 lines (160-162)\n\n    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:\n        \"\"\"СТ-25: правит существующий бот-коммент с маркером, иначе создаёт новый.\n        Лишние дубликаты (от гонок) схлопывает — идемпотентность самовосстанавливается.\"\"\"\n        tagged = f\"{body}\\n\\n{marker}\"\n        data = json.dumps({\"body\": tagged}).encode()\n        matches = self._matching_comments(repo, number, marker)\n        if not matches:\n            s, b = self._transport(\n                \"POST\", f\"{self._api}/repos/{repo}/issues/{number}/comments\",\n                data, self._headers(repo))\n            if s >= 300:\n                raise RuntimeError(f\"create comment {s}: {b[:200]!r}\")\n            return\n        s, b = self._transport(\n            \"PATCH\", f\"{self._api}/repos/{repo}/issues/comments/{matches[0]['id']}\",\n            data, self._headers(repo))\n        if s >= 300:\n            raise RuntimeError(f\"update comment {s}: {b[:200]!r}\")\n        for extra in matches[1:]:  # self-heal: удалить дубли, оставить один\n            self._transport(\n                \"DELETE\", f\"{self._api}/repos/{repo}/issues/comments/{extra['id']}\",\n                None, self._headers(repo))\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 67.1% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 31.42,
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
