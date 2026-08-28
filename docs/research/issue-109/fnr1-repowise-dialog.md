# Итог

1. **Структура GitHub-связанности подтверждена**: `worker/github_client.py` (666 строк, 59 вызовов из `worker/activities.py`), `webhook/main.py` (612 строк, ~520 строк GitHub-логики), `worker/activities.py` (118 call-site). Абстракции провайдера нет — поиск `Protocol`, `ABC`, `abstractmethod`, `provider` в продуктовом коде даёт 0 совпадений.

2. **GitHub-клиент — синглтон функций без класса**: `worker/github_client.py:67-666` реализует прямые REST-вызовы к `api.github.com` с JWT/App-аутентификацией (`_installation_token_for` с кэшем 55 минут). URL не кодируются: 26 мест с `{repo}` в пути, метки кодируются (`:166`), `workflow_file` кодируется (`:450`).

3. **Вебхук-хендлер жёстко завязан на GitHub**: `webhook/main.py` использует `x_github_event`, `x_hub_signature_256`, `x_github_delivery` — GitLab-аналоги (`X-Gitlab-Event`, `webhook-signature`, `X-Gitlab-Delivery`) не поддерживаются. HMAC-проверка только для GitHub.

4. **Allowlist не поддерживает вложенные группы GitLab**: `shared/repos.py:47` `is_allowed` использует `split("/", 1)[0]` для извлечения owner — для `group/subgroup/project` это отработает некорректно (матчит только первый сегмент).

5. **Провайдер-нейтральные модули существуют**: `shared/lifecycle.py` (docstring: «ни сети, ни Temporal, ни GitHub»), `shared/agent_events.py`, `develop.py`, `pr_closing.py` — это шов для абстракции. `/agent-event` эндпоинт уже нейтрален (собственная подпись).

6. **Дублирование GitHub-клиента подтверждено**: `poh-pr-agents/self-hosted/reliability/github_client.py` реализует `GitHubAppClient` (class-based, не function-based) с собственной `InstallationTokenProvider` — независимая реализация той же JWT→installation логики.

7. **Риск регресс на тестах**: 814 тестов, 33 файла касаются `github_client`, но 31 подменяют модуль, а не HTTP. `api.github.com` встречается всего 3 раза. HTTP-моки отсутствуют (`respx`, `responses`, `requests_mock` — 0). Переезд пройдёт зелёным даже если URL поедут.

8. **`_BRANCH_RE` корректно матчит паттерны веток**: `shared/agent_events.py:143` использует `\b` после дефиса, что корректно матчит `research/issue-N` и `bug/issue-N`. Не покрыт только `feature/N-openhands` (третий fallback в `correlate`).

9. **Фильтр «только боты» сломается на GitLab**: `worker/github_client.py:611` проверяет `user.type == "Bot"` — поля в GitLab нет, условие истинно всегда, все комментарии молча отбрасываются.

10. **Нет bootstrap меток**: grep по `label create` даёт 0 — GitHub заводит метку сам при добавлении. В GitLab поведение не задокументировано; 16 вызовов `add_label` не обёрнуты и уронят активность.

# Открытые вопросы

- Какая логика аутентификации используется в `poh-pr-closer` (репозиторий не проиндексирован)?
- Существуют ли другие репозитории организации с дублирующей реализацией GitHub-клиента?
- Есть ли в кодовой базе необработанные обращения к `user["type"]` индексацией, кроме упомянутых в `webhook/main.py:530,172`?
- Какие именно 16 мест вызова `add_label` не обёрнуты в try/except (список из описания требует верификации по коду)?
- Существуют ли в кодовой базе заготовки для абстракции провайдера (mocking, test doubles)?

# Диалог

1. **`get_overview`** — Получен обзор репозитория: 323 файла, 80,733 строки кода. Основные модули: `worker/` (с `github_client.py` как центральный элемент), `shared/`, `webhook/`. Высокий churn в `worker/activities.py`, `worker/workflows.py`. Репозиторий входит в workspace с соседними репозиториями (`poh-pr-agents`, `poh-bft-writer` и др.).

2. **`get_context(worker/github_client.py)`** — Подтверждено: 666 строк, синглтон функций (не класс). Аутентификация через GitHub App (JWT → installation token, кэш 55 мин). Прямые REST-вызовы к `api.github.com`. 59 inbound calls из `worker/activities.py`. 7 bug fixes (bug_magnet: true).

3. **`get_context(webhook/main.py)`** — Подтверждено: 612 строк, ~520 строк GitHub-логики. HMAC-проверка через `verify_signature` (`x_hub_signature_256`). События: `issues.opened`, `issue_comment.created`, `issues.labeled`. Использует `shared/repos.py` для allowlist. `/agent-event` уже провайдер-нейтрален.

4. **`get_context(shared/repos.py)`** — Подтверждена ловушка для GitLab: `parse_repo_specs` и `is_allowed` работают только с двухсегментными путями `owner/repo`. Для GitLab `group/subgroup/project` это matчит только первый сегмент как owner.

5. **`get_context(shared/agent_events.py)`** — Подтверждён паттерн `_BRANCH_RE = re.compile(r"\b(?:research|bug)/issue-(\d+)\b")`. `\b` корректно срабатывает после дефиса. Функция `correlate` использует три fallback: `root_issue` → `Closes #N` → `_BRANCH_RE`.

6. **`get_context(poh-pr-agents/self-hosted/reliability/github_client.py)`** — Подтверждено дублирование: `GitHubAppClient` (class-based, не function-based как в `poh-issue-agents`) с собственной token provider логикой. Другая архитектура, та же функциональность.

7. **`search_codebase('Protocol ABC abstractmethod provider interface', mode='symbol')`** — Подтверждено отсутствие абстракций провайдера: найден только `ProtocolState` (workflow state), не относящийся к провайдерам. Никаких `Protocol`, `ABC`, `abstractmethod` для провайдерной логики.

8. **`get_context(shared/lifecycle.py)`** — Подтверждена провайдер-нейтральность: docstring прямо заявляет «ни сети, ни Temporal, ни GitHub». Модель фаз Issue, единственный источник правды о состояниях, не зависит от трекера.

9. **`get_context(poh-pr-closer/shared/github_client.py)`** — Ошибка: репозиторий `poh-pr-closer` не проиндексирован. Доступные репозитории: `poh-bft-writer`, `poh-cortex`, `poh-helper`, `poh-infra`, `poh-issue-agents`, `poh-memory-engine`, `poh-pr-agents`, `poh-scheduller`, `poh-sprint-agents`.

---

*Диалог собран через MCP-сервер repowise. Индекс актуален (commit a41f569f0381).*


---
session: rw-analysis-po-helper-org__poh-issue-agents-109
workspace: contour
turns: 9
started: 2026-08-21T10:31:07Z
finished: 2026-08-21T10:31:46Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-pr-agents` | `9f15ada9e4e9` | 47 мин |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "null",
  "include": [
    "outline",
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
        "descendants": 5,
        "children": [
          {
            "section": "4.1",
            "page_id": "file_page:.claude/skills/architecture/scripts/generate_taxonomy.py",
            "title": "File: .claude/skills/architecture/scripts/generate_taxonomy.py",
            "page_type": "file_page",
            "target_path": ".claude/skills/architecture/scripts/generate_taxonomy.py"
          },
          {
            "section": "4.2",
            "page_id": "file_page:.claude/skills/brainstorming/scripts/helper.js",
            "title": "File: .claude/skills/brainstorming/scripts/helper.js",
            "page_type": "file_page",
            "target_path": ".claude/skills/brainstorming/scripts/helper.js"
          },
          {
            "section": "4.3",
            "page_id": "file_page:.claude/skills/brainstorming/scripts/server.cjs",
            "title": "File: .claude/skills/brainstorming/scripts/server.cjs",
            "page_type": "file_page",
            "target_path": ".claude/skills/brainstorming/scripts/server.cjs"
          },
          {
            "section": "4.4",
            "page_id": "file_page:.claude/skills/systematic-debugging/condition-based-waiting-example.ts",
            "title": "File: .claude/skills/systematic-debugging/condition-based-waiting-example.ts",
            "page_type": "file_page",
            "target_path": ".claude/skills/systematic-debugging/condition-based-waiting-example.ts"
          },
          {
            "section": "4.5",
            "page_id": "file_page:.claude/skills/writing-skills/render-graphs.js",
            "title": "File: .claude/skills/writing-skills/render-graphs.js",
            "page_type": "file_page",
            "target_path": ".claude/skills/writing-skills/render-graphs.js"
          }
        ]
      },
      {
        "section": "5",
        "page_id": "module_page:scripts",
        "title": "Docs Tooling Scripts",
        "page_type": "module_page",
        "target_path": "scripts",
        "descendants": 8,
        "children": [
          {
            "section": "5.1",
            "page_id": "infra_page:scripts/setup.sh",
            "title": "Infrastructure: scripts/setup.sh",
            "page_type": "infra_page",
            "target_path": "scripts/setup.sh"
          },
          {
            "section": "5.2",
            "page_id": "file_page:scripts/backfill.py",
            "title": "File: scripts/backfill.py",
            "page_type": "file_page",
            "target_path": "scripts/backfill.py"
          },
          {
            "section": "5.3",
            "page_id": "file_page:scripts/consolidate.py",
            "title": "File: scripts/consolidate.py",
            "page_type": "file_page",
            "target_path": "scripts/consolidate.py"
          },
          {
            "section": "5.4",
            "page_id": "file_page:scripts/demo_e2e.py",
            "title": "File: scripts/demo_e2e.py",
            "page_type": "file_page",
            "target_path": "scripts/demo_e2e.py"
          },
          {
            "section": "5.5",
            "page_id": "file_page:scripts/diag.py",
            "title": "File: scripts/diag.py",
            "page_type": "file_page",
            "target_path": "scripts/diag.py"
          },
          {
            "section": "5.6",
            "page_id": "file_page:scripts/e2e_live.py",
            "title": "File: scripts/e2e_live.py",
            "page_type": "file_page",
            "target_path": "scripts/e2e_live.py"
          },
          {
            "section": "5.7",
            "page_id": "file_page:scripts/estimate.py",
            "title": "File: scripts/estimate.py",
            "page_type": "file_page",
            "target_path": "scripts/estimate.py"
          },
          {
            "section": "5.8",
            "page_id": "file_page:scripts/smoke_temporal.py",
            "title": "File: scripts/smoke_temporal.py",
            "page_type": "file_page",
            "target_path": "scripts/smoke_temporal.py"
          }
        ]
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 45,
        "children": [
          {
            "section": "6.1",
            "page_id": "file_page:shared/agent_comment.py",
            "title": "File: shared/agent_comment.py",
            "page_type": "file_page",
            "target_path": "shared/agent_comment.py"
          },
          {
            "section": "6.2",
            "page_id": "file_page:shared/agent_events.py",
            "title": "File: shared/agent_events.py",
            "page_type": "file_page",
            "target_path": "shared/agent_events.py"
          },
          {
            "section": "6.3",
            "page_id": "file_page:shared/agent_launcher.py",
            "title": "File: shared/agent_launcher.py",
            "page_type": "file_page",
            "target_path": "shared/agent_launcher.py"
          },
          {
            "section": "6.4",
            "page_id": "file_page:shared/authz.py",
            "title": "File: shared/authz.py",
            "page_type": "file_page",
            "target_path": "shared/authz.py"
          },
          {
            "section": "6.5",
            "page_id": "file_page:shared/awaiting.py",
            "title": "File: shared/awaiting.py",
            "page_type": "file_page",
            "target_path": "shared/awaiting.py"
          },
          {
            "section": "6.6",
            "page_id": "file_page:shared/bft.py",
            "title": "File: shared/bft.py",
            "page_type": "file_page",
            "target_path": "shared/bft.py"
          },
          {
            "section": "6.7",
            "page_id": "file_page:shared/commands.py",
            "title": "File: shared/commands.py",
            "page_type": "file_page",
            "target_path": "shared/commands.py"
          },
          {
            "section": "6.8",
            "page_id": "file_page:shared/decomposition.py",
            "title": "File: shared/decomposition.py",
            "page_type": "file_page",
            "target_path": "shared/decomposition.py"
          },
          {
            "section": "6.9",
            "page_id": "file_page:shared/develop.py",
            "title": "File: shared/develop.py",
            "page_type": "file_page",
            "target_path": "shared/develop.py"
          },
          {
            "section": "6.10",
            "page_id": "file_page:shared/labels.py",
            "title": "File: shared/labels.py",
            "page_type": "file_page",
            "target_path": "shared/labels.py"
          }
        ]
      },
      {
        "section": "7",
        "page_id": "module_page:webhook",
        "title": "Application Webhook",
        "page_type": "module_page",
        "target_path": "webhook",
        "descendants": 2,
        "children": [
          {
            "section": "7.1",
            "page_id": "infra_page:webhook/Dockerfile",
            "title": "Infrastructure: webhook/Dockerfile",
            "page_type": "infra_page",
            "target_path": "webhook/Dockerfile"
          },
          {
            "section": "7.2",
            "page_id": "file_page:webhook/main.py",
            "title": "File: webhook/main.py",
            "page_type": "file_page",
            "target_path": "webhook/main.py"
          }
        ]
      },
      {
        "section": "8",
        "page_id": "module_page:worker",
        "title": "Application Worker",
        "page_type": "module_page",
        "target_path": "worker",
        "descendants": 101,
        "children": [
          {
            "section": "8.1",
            "page_id": "infra_page:worker/Dockerfile",
            "title": "Infrastructure: worker/Dockerfile",
            "page_type": "infra_page",
            "target_path": "worker/Dockerfile"
          },
          {
            "section": "8.2",
            "page_id": "file_page:worker/activities.py",
            "title": "File: worker/activities.py",
            "page_type": "file_page",
            "target_path": "worker/activities.py",
            "descendants": 63
          },
          {
            "section": "8.3",
            "page_id": "file_page:worker/consolidation_activities.py",
            "title": "File: worker/consolidation_activities.py",
            "page_type": "file_page",
            "target_path": "worker/consolidation_activities.py"
          },
          {
            "section": "8.4",
            "page_id": "file_page:worker/consolidation_workflow.py",
            "title": "File: worker/consolidation_workflow.py",
            "page_type": "file_page",
            "target_path": "worker/consolidation_workflow.py"
          },
          {
            "section": "8.5",
            "page_id": "file_page:worker/estimate_report.py",
            "title": "File: worker/estimate_report.py",
            "page_type": "file_page",
            "target_path": "worker/estimate_report.py"
          },
          {
            "section": "8.6",
            "page_id": "file_page:worker/estimation.py",
            "title": "File: worker/estimation.py",
            "page_type": "file_page",
            "target_path": "worker/estimation.py",
            "descendants": 9
          },
          {
            "section": "8.7",
            "page_id": "file_page:worker/github_client.py",
            "title": "File: worker/github_client.py",
            "page_type": "file_page",
            "target_path": "worker/github_client.py",
            "descendants": 8
          },
          {
            "section": "8.8",
            "page_id": "file_page:worker/llm.py",
            "title": "File: worker/llm.py",
            "page_type": "file_page",
            "target_path": "worker/llm.py"
          },
          {
            "section": "8.9",
            "page_id": "file_page:worker/worker.py",
            "title": "File: worker/worker.py",
            "page_type": "file_page",
            "target_path": "worker/worker.py",
            "descendants": 1
          },
          {
            "section": "8.10",
            "page_id": "file_page:worker/workflows.py",
            "title": "File: worker/workflows.py",
            "page_type": "file_page",
            "target_path": "worker/workflows.py",
            "descendants": 10
          }
        ]
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
        "54af441e65b7"
      ],
      "tokens": 2070,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "omission_marker": "[repowise#54af441e65b7: 62 lines omitted (~2070 tokens); restore: repowise expand 54af441e65b7]"
}

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/github_client.py"
  ],
  "include": [
    "skeleton",
    "ownership",
    "metrics",
    "callers",
    "callees"
  ],
  "compact": false
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
        "last_fix_days_ago": 2,
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
      "callers": [
        {
          "file": "worker/activities.py",
          "imports": true,
          "inbound_calls": 59
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
          "file": "tests/test_github_client_pr.py",
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
          "file": "tests/test_github_client_dryrun.py",
          "imports": true
        },
        {
          "file": "tests/test_github_client_labels.py",
          "imports": true
        }
      ],
      "_call_graph_note": "File-level rollup: importing files plus inbound cross-file call counts. For symbol-precise callers pass 'file.py::Symbol'.",
      "callees": [],
      "metrics": {
        "pagerank": 0.01172,
        "pagerank_percentile": 97,
        "betweenness": 0.000875,
        "betweenness_percentile": 98,
        "in_degree": 12,
        "out_degree": 2,
        "community_id": 3,
        "community_label": "tests (23)"
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
    "timing_ms": 144.2,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
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
  "compact": false,
  "include": [
    "skeleton",
    "ownership",
    "metrics"
  ],
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
      "metrics": {
        "pagerank": 0.00839,
        "pagerank_percentile": 95,
        "betweenness": 0.00107,
        "betweenness_percentile": 98,
        "in_degree": 11,
        "out_degree": 12,
        "community_id": 3,
        "community_label": "tests (23)"
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
    "timing_ms": 115.8,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 4 · `get_context` · contour

**Запрос:**

```json
{
  "compact": false,
  "include": [
    "skeleton",
    "ownership"
  ],
  "targets": [
    "shared/repos.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/repos.py": {
      "target": "shared/repos.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/repos.py",
        "summary": "Список отслеживаемых репозиториев (ISSUE_AGENT_REPOS)."
      },
      "hotspot": false,
      "ownership": {
        "primary_owner": "kibarik",
        "owner_pct": 1.0,
        "contributor_count": 1,
        "bus_factor": 1
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
        "tokens": 531,
        "full_tokens": 531,
        "pct_of_full": 100.0,
        "bodies_kept": [
          "parse_repo_specs",
          "is_allowed"
        ],
        "text": "\"\"\"Список отслеживаемых репозиториев (ISSUE_AGENT_REPOS).\n\nАналог RELIABILITY_REPOS в poh-pr-agents. Чистые функции: разбор спецификаций\nи проверка допуска репозитория. Сетевых вызовов нет — проверка строковая.\n\nФорматы записи (comma-separated в ISSUE_AGENT_REPOS):\n  owner/repo — конкретный репозиторий\n  owner/*    — любой репозиторий этого owner\n  owner      — голый owner: то же, что owner/*\n  *          — любой репозиторий (все установки App)\n  (пусто)    — то же, что * — любой установленный\n\"\"\"\nfrom __future__ import annotations\n\nimport os\n\n\ndef parse_repo_specs(specs: list[str]) -> tuple[list[str], list[str]]:\n    \"\"\"Делит записи на точные `owner/repo` и маски-owner'ы.\n\n    Возвращает (concrete, mask_owners); для `*` в mask_owners кладётся \"*\".\n    Пустые записи игнорируются. Порт `parse_repo_specs` из pr-agents.\n    \"\"\"\n    concrete: list[str] = []\n    mask_owners: list[str] = []\n    for spec in specs:\n        spec = spec.strip()\n        if not spec:\n            continue\n        if spec == \"*\":\n            mask_owners.append(\"*\")\n        elif spec.endswith(\"/*\"):\n            mask_owners.append(spec[: -len(\"/*\")])\n        elif \"/\" not in spec:\n            mask_owners.append(spec)  # голый owner → маска owner/*\n        else:\n            concrete.append(spec)\n    return concrete, mask_owners\n\n\ndef is_allowed(repo: str, specs: list[str]) -> bool:\n    \"\"\"True, если репозиторий `owner/name` входит в allowlist.\n\n    Пустой список или `*` → разрешено всё. Иначе — точное совпадение full_name\n    (регистронезависимо) либо owner под маской.\n    \"\"\"\n    concrete, mask_owners = parse_repo_specs(specs)\n    if not concrete and not mask_owners:\n        return True  # пусто → любой установленный\n    if \"*\" in mask_owners:\n        return True\n    repo_l = repo.lower()\n    if repo_l in {c.lower() for c in concrete}:\n        return True\n    owner = repo_l.split(\"/\", 1)[0]\n    return owner in {m.lower() for m in mask_owners}\n\n\ndef allowed_specs() -> list[str]:\n    \"\"\"Записи ISSUE_AGENT_REPOS из окружения (comma-separated, пустые допустимы).\"\"\"\n    return os.environ.get(\"ISSUE_AGENT_REPOS\", \"\").split(\",\")\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 100.0% of the full file — a direct Read costs little more."
      }
    }
  },
  "_meta": {
    "timing_ms": 36.26,
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
  "compact": false,
  "include": [
    "skeleton"
  ],
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
    "timing_ms": 37.94,
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
  "compact": false,
  "include": [
    "skeleton"
  ],
  "targets": [
    "self-hosted/reliability/github_client.py"
  ],
  "repo": "poh-pr-agents"
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
        "last_fix_days_ago": 36
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
    "timing_ms": 97.92,
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
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
  "compact": false,
  "include": [
    "skeleton"
  ],
  "repo": "poh-pr-closer",
  "targets": [
    "shared/github_client.py"
  ]
}
```

**Ответ:**

{
  "error": "Unknown repo 'poh-pr-closer'. Available: ['poh-bft-writer', 'poh-cortex', 'poh-helper', 'poh-infra', 'poh-issue-agents', 'poh-memory-engine', 'poh-pr-agents', 'poh-scheduller', 'poh-sprint-agents']",
  "remedy": "Call list_repos to see the valid repo aliases, or omit the 'repo' argument to use the default repository."
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "Protocol ABC abstractmethod provider interface",
  "mode": "symbol",
  "limit": 10
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
      "score": 6.252,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::read_protocol_state",
      "name": "read_protocol_state",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 405,
      "end_line": 444,
      "signature": "def read_protocol_state(repo: str, issue_number: int) -> ProtocolState",
      "qualified_name": "worker.activities.read_protocol_state",
      "language": "python",
      "score": 6.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_protocol_state.py::_issue",
      "name": "_issue",
      "kind": "function",
      "file": "tests/test_protocol_state.py",
      "start_line": 6,
      "end_line": 7,
      "signature": "def _issue(labels_list, body=\"\")",
      "qualified_name": "tests.test_protocol_state._issue",
      "language": "python",
      "score": 1.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_protocol_state.py::_wire",
      "name": "_wire",
      "kind": "function",
      "file": "tests/test_protocol_state.py",
      "start_line": 10,
      "end_line": 22,
      "signature": "def _wire(monkeypatch, issues: dict)",
      "qualified_name": "tests.test_protocol_state._wire",
      "language": "python",
      "score": 1.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_workflow_protocol.py::_issue",
      "name": "_issue",
      "kind": "function",
      "file": "tests/test_workflow_protocol.py",
      "start_line": 25,
      "end_line": 27,
      "signature": "def _issue() -> IssueInput",
      "qualified_name": "tests.test_workflow_protocol._issue",
      "language": "python",
      "score": 1.032,
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
      "score": 1.032,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_workflow_protocol.py::_run",
      "name": "_run",
      "kind": "function",
      "file": "tests/test_workflow_protocol.py",
      "start_line": 96,
      "end_line": 109,
      "signature": "async def _run(state: ProtocolState) -> str",
      "qualified_name": "tests.test_workflow_protocol._run",
      "language": "python",
      "score": 1.023,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agent_event_workflow.py::protocol_default",
      "name": "protocol_default",
      "kind": "function",
      "file": "tests/test_agent_event_workflow.py",
      "start_line": 42,
      "end_line": 43,
      "signature": "async def protocol_default(repo: str, issue_number: int) -> ProtocolState",
      "qualified_name": "tests.test_agent_event_workflow.protocol_default",
      "language": "python",
      "score": 1.012,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::protocol_default",
      "name": "protocol_default",
      "kind": "function",
      "file": "tests/test_agents_as_children.py",
      "start_line": 52,
      "end_line": 53,
      "signature": "async def protocol_default(repo: str, issue_number: int) -> ProtocolState",
      "qualified_name": "tests.test_agents_as_children.protocol_default",
      "language": "python",
      "score": 1.012,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_awaiting_wiring.py::protocol_default",
      "name": "protocol_default",
      "kind": "function",
      "file": "tests/test_awaiting_wiring.py",
      "start_line": 50,
      "end_line": 51,
      "signature": "async def protocol_default(repo: str, issue_number: int) -> ProtocolState",
      "qualified_name": "tests.test_awaiting_wiring.protocol_default",
      "language": "python",
      "score": 1.012,
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
      "path": "shared/workflow_types.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_protocol_state.py"
    },
    {
      "path": "tests/test_workflow_protocol.py"
    },
    {
      "path": "tests/test_agent_event_workflow.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_awaiting_wiring.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'Protocol ABC abstractmethod provider interface'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 9 · `get_context` · contour

**Запрос:**

```json
{
  "compact": false,
  "include": [
    "skeleton"
  ],
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
    "timing_ms": 33.92,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
