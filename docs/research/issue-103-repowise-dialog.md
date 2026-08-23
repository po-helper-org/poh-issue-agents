---
session: rw-openhands-po-helper-org__poh-issue-agents-103
workspace: contour
turns: 5
started: 2026-08-23T05:57:11Z
finished: 2026-08-23T05:57:56Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 6 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 6 мин |
| `poh-helper` | `18512c1e7ce9` | 6 мин |
| `poh-infra` | `a1db4f02f10c` | 6 мин |
| `poh-issue-agents` | `993d8561f100` | 7 мин |
| `poh-memory-engine` | `194e39319b3f` | 6 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 6 мин |
| `poh-scheduller` | `04cc3f47aff9` | 6 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 6 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 3 сут |

# Диалог

## Ход 1 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "poh-demo-checkout",
  "limit": 10
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
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "ь «варианты решения» — то есть\nпроектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)\nдаёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`\n→",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "confidence_score": 0.98
    },
    {
      "title": "Docs Tooling Scripts",
      "page_type": "module_page",
      "snippet": ", which needs Layer B (GitHub App + public endpoint). This scr\n\n- `scripts/__init__.py`\n\n- `scripts/demo_e2e.py`: Автономный прогон контура по сценарию демо. Заводит Issue на простую доработку и ведёт",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "scripts",
      "confidence_score": 0.95
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
    },
    {
      "title": "File: scripts/smoke_temporal.py",
      "page_type": "file_page",
      "snippet": "scribe_namespace — namespace существует и REGISTERED\n  3) поднимает временный worker на task-queue `poh-smoke-test`, запускает\n     тривиальный workflow (activity возвращает pong) и ждёт результат —",
      "relevance_score": 2.784,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/smoke_temporal.py",
      "confidence_score": 0.93
    },
    {
      "title": "Symbol: worker.activities.run_bft_fast",
      "page_type": "symbol_spotlight",
      "snippet": "llm.MODEL_CLASSIFY,\n    )\n    body = bft.render_letter(\n        goal=letter.goal,\n        how_to_demo=letter.how_to_demo,\n        open_questions=letter.open_questions,\n        scope=letter.scope,",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_fast",
      "file": "worker/activities.py",
      "confidence_score": 0.91
    },
    {
      "title": "Active Landscape",
      "page_type": "onboarding",
      "snippet": "# Active Landscape\n\nWhere `poh-issue-agents` has actually been changing. 501 commits touched 129 files in the last 90 days.\n\n\n## Files under active change\n\n| File | Commits (90d) | Owner | Hotspot | A",
      "relevance_score": 2.687,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/active_landscape",
      "confidence_score": 0.9
    },
    {
      "title": "File: shared/repos.py",
      "page_type": "file_page",
      "snippet": "py\n\n## Overview\n\nСписок отслеживаемых репозиториев (ISSUE_AGENT_REPOS).\n\nАналог RELIABILITY_REPOS в poh-pr-agents. Чистые функции: разбор спецификаций\nи проверка допуска репозитория. Сетевых вызовов н",
      "relevance_score": 2.677,
      "sources": [
        "fts"
      ],
      "target_path": "shared/repos.py",
      "confidence_score": 0.89
    },
    {
      "title": "Key Concepts",
      "page_type": "onboarding",
      "snippet": "# Key Concepts\n\nThe types and functions the rest of `poh-issue-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanati",
      "relevance_score": 2.609,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/key_concepts",
      "confidence_score": 0.87
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
      "path": "shared/bft.py"
    },
    {
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/repos.py"
    },
    {
      "path": "shared/develop.py"
    },
    {
      "path": "shared/agent_events.py"
    },
    {
      "path": "scripts/setup.sh"
    }
  ]
}

## Ход 2 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Where are the PR review automation workflows located in the codebase? Look for pr-review.yml, openhands-resolver.yml, or any references to PR review automation and openhands resolver workflows."
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but retrieval succeeded and this payload is usable: 5 ranked hits in `retrieval`, the files to open in `fallback_targets`, and the wider ranked shortlist in `candidates`. Read those rather than starting a fresh search.",
  "citations": [],
  "confidence": "low",
  "retrieval_quality": "weak",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "shared/develop.py",
    "worker/activities.py::trigger_openhands_resolver",
    "onboarding/how_it_works",
    "shared/label_catalog.py"
  ],
  "retrieval": [
    {
      "path": "shared/develop.py",
      "title": "File: shared/develop.py",
      "summary": "Контракт активности Develop — разработка по подготовленному Issue.",
      "snippet": "етки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсю",
      "excerpt": "# shared/develop.py\n\n## Overview\n\nКонтракт активности Develop — разработка по подготовленному Issue.\n\nResearch доводит Issue до системных требований и метки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсюда два режима:\n\n`local` (умолчание) — прогон идёт **одноразовым контейнером на своём же\nсервере**. Контур получается замкнутым: репозиторий обслуживается целиком\nвнутри стенда, без чужих раннеров и без минут GitHub.\n\n`dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся\nдля репозиториев, где стенда нет.\n\nПочему отдельный контейнер, а не воркер. Аналитика (`claude -p`) пишет\nдокументы, и её соседство с токенами безобидно. Агент разработки делает другое:\nон ИСПОЛНЯЕТ код репозитория — ставит зависимости, гоняет тесты. Внутри воркера\nэто означало бы выполнение произвольного кода чужого проекта рядом с\nGitHub-токеном и ключом модели. Поэтому прогон живёт минуты в отдельном\nконтейнере, видит только каталог своей задачи и умирает вместе с ней; коммит,\nпуш и PR делает воркер уже после — своими руками и своим токеном.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как\n`shared/lifecycle.py` и `shared/agent_events.py`.\n\nIt exposes 36 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `LOCAL` | constant | LOCAL = \"local\" |\n| `DISPATCH` | constant | DISPATCH = \"dispatch\" |\n|",
      "score": 3.494,
      "key_symbols": [
        {
          "name": "LOCAL",
          "kind": "constant",
          "signature": "LOCAL = \"local\"",
          "docstring": "",
          "start_line": 33,
          "end_line": 33
        },
        {
          "name": "DISPATCH",
          "kind": "constant",
          "signature": "DISPATCH = \"dispatch\"",
          "docstring": "",
          "start_line": 34,
          "end_line": 34
        },
        {
          "name": "DEFAULT_WORKFLOW_FILE",
          "kind": "constant",
          "signature": "DEFAULT_WORKFLOW_FILE = \"openhands-resolver.yml\"",
          "docstring": "",
          "start_line": 39,
          "end_line": 39,
          "source_excerpt": "DEFAULT_WORKFLOW_FILE = \"openhands-resolver.yml\""
        },
        {
          "name": "AGENT_NAME",
          "kind": "constant",
          "signature": "AGENT_NAME = \"openhands\"",
          "docstring": "",
          "start_line": 46,
          "end_line": 46
        },
        {
          "name": "DEFAULT_RUNNER_IMAGE",
          "kind": "constant",
          "signature": "DEFAULT_RUNNER_IMAGE = \"poh-openhands-runner:local\"",
          "docstring": "",
          "start_line": 51,
          "end_line": 51
        },
        {
          "name": "MCP_CONFIG_DIR",
          "kind": "constant",
          "signature": "MCP_CONFIG_DIR = \".openhands\"",
          "docstring": "",
          "start_line": 69,
          "end_line": 69
        },
        {
          "name": "workflow_file",
          "kind": "function",
          "signature": "def workflow_file() -> str:",
          "docstring": "",
          "start_line": 109,
          "end_line": 110,
          "source_excerpt": "def workflow_file() -> str:\n    return os.environ.get(\"DEVELOP_WORKFLOW_FILE\", \"\").strip() or DEFAULT_WORKFLOW_FILE"
        },
        {
          "name": "workflow_ref",
          "kind": "function",
          "signature": "def workflow_ref() -> str:",
          "docstring": "",
          "start_line": 113,
          "end_line": 114
        },
        {
          "name": "work_branch",
          "kind": "function",
          "signature": "def work_branch(issue_number: int) -> str:",
          "docstring": "",
          "start_line": 144,
          "end_line": 145
        },
        {
          "name": "dispatch_inputs",
          "kind": "function",
          "signature": "def dispatch_inputs(issue_number: int, *, branch: str, priority: str = \"\") -> dict[str, str]:",
          "docstring": "Входы прогона для режима `dispatch`. Только строки: `workflow_dispatch`\n    других не принимает.",
          "start_line": 211,
          "end_line": 218
        }
      ]
    },
    {
      "path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "summary": "Активность Develop: разработка по подготовленному Issue.",
      "snippet": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\nasync def trigger_openhands_resolver(issue: Issue",
      "excerpt": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\nasync def trigger_openhands_resolver(issue: IssueInput) -> int | None\n```\n\n## Overview\n\nАктивность Develop: разработка по подготовленному Issue.\n\nДва режима (`shared/develop.py`). `local` — прогон одноразовым контейнером\nна своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\nв GitHub Actions, для репозиториев без стенда.\n\nВозвращает номер PR (режим `local`) либо None (`dispatch`: результат\nпридёт событием `pr-open`, прогон идёт на чужой стороне).\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n32 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `",
      "score": 3.487
    },
    {
      "path": "poh-issue-agents",
      "title": "Repository Overview: poh-issue-agents",
      "summary": "`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.",
      "snippet": "Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webho",
      "excerpt": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Primary Execution Flows\n\n- `worker/workflows.py::IssueLifecycle::run` (5 steps)\n\n- `webhook/main.py::github_webhook` (3 steps)\n\n- `worker/workflows.py::IssueAnalysis::run` (3 steps)\n\n- `webhook/main.py::agent_event` (3 steps)\n\n- `worker/github_client.py::dispatch_workflow` (6 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `tests/conftest.py` (0.0634)\n\n- `shared/workflow_types.py` (0.0442)\n\n- `worker/estimation.py` (0.0293)\n\n- `shared/__init__.py` (0.0190)\n\n- `worker/activities.py` (0.0170)\n\n- `tests/test_estimate_activities.py` (0.0155)\n\n- `tests/test_estimate_report.py` (0.0155)\n\n- `tests/test_estimation_compute.py` (0.0155)\n\n- `worker/github_client.py` (0.0125)\n\n- `shared/lifecycle.py` (0.0109)\n\n- `shared/workflow_ids.py` (0.0108)\n\n- `worker/worker.py` (0.0106)\n\n- `worker/workflows.py` (0.0099)\n\n- `shared/labels.py` (0.0095)\n\n- `worker/consolidation_activities.py` (0.0093)\n\n- `webhook/main.py` (0.0090)\n\n- `shared/agent_comment.py` (0.0089)\n\n- `shared/temporal_client.py` (0.0084)\n\n- `shared/",
      "score": 2.931
    },
    {
      "path": "onboarding/how_it_works",
      "title": "How It Works",
      "summary": "Traced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.",
      "snippet": "h, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-issue-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collect",
      "excerpt": "# How It Works\n\nTraced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-issue-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Traced flows\n\n\n\n\n### From `worker/workflows.py::IssueLifecycle::run`\n\n\n\n1. `worker/workflows.py::IssueLifecycle::run`\n\n2. `worker/workflows.py::IssueLifecycle::_run_phase_loop`\n\n3. `worker/workflows.py::IssueLifecycle::_phase_await_build`\n\n4. `worker/workflows.py::IssueLifecycle::_park`\n\n5. `shared/awaiting.py::Awaiting`\n\n\n\n\n\n\n### From `webhook/main.py::github_webhook`\n\n\n\n1. `webhook/main.py::github_webhook`\n\n2. `shared/agent_launcher.py::request_analysis`\n\n3. `shared/workflow_ids.py::issue_workflow_id`\n\n\n\n\n\n\n### From `worker/workflows.py::IssueAnalysis::run`\n\n\n\n1. `worker/workflows.py::IssueAnalysis::run`\n\n2. `worker/workflows.py::_run_staged_analysis`\n\n3. `worker/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. README.md. Start here for the end-to-end picture before diving into the code.\n   - `README.md`\n\n\n2. main.py. An entry point — execution and imports fan out from here.\n   - `webhook/main.py`\n\n\n3. workflow_types.py. Directly used by the entry points above; a core collab",
      "score": 2.766
    },
    {
      "path": "shared/label_catalog.py",
      "title": "File: shared/label_catalog.py",
      "summary": "Единый каталог меток Issue-Agent: имена, цвета и описания.",
      "snippet": "Единый каталог меток Issue-Agent: имена, цвета и описания.",
      "excerpt": "# shared/label_catalog.py\n\n## Overview\n\nЕдиный каталог меток Issue-Agent: имена, цвета и описания.\n\nИмена собираются из тех же констант, что и рабочий код. Это не даёт каталогу\nтихо разъехаться с вебхуком или воркером при добавлении новой фазы, команды или\nрешения человека.\n\nIt exposes 17 public symbols and depends on 5 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `PHASE_COLOR` | constant | PHASE_COLOR = \"#1F75CB\" |\n| `ADVISOR_COLOR` | constant | ADVISOR_COLOR = \"#6E49CB\" |\n| `PRIORITY_COLOR` | constant | PRIORITY_COLOR = \"#ED9121\" |\n| `RUNNING_COLOR` | constant | RUNNING_COLOR = \"#FC9403\" |\n| `DONE_COLOR` | constant | DONE_COLOR = \"#108548\" |\n| `FAILED_COLOR` | constant | FAILED_COLOR = \"#DD2B0E\" |\n| `HUMAN_COLOR` | constant | HUMAN_COLOR = \"#E24329\" |\n| `TRIGGER_COLOR` | constant | TRIGGER_COLOR = \"#2DA160\" |\n| `NEUTRAL_COLOR` | constant | NEUTRAL_COLOR = \"#666666\" |\n| `ADVISOR_KINDS` | constant | ADVISOR_KINDS = (\"answered\", \"bug\", \"consultation\", \"error\", |\n| `PRIORITY_LEVELS` | constant | PRIORITY_LEVELS = (\"P0\", \"P1\", \"P2\", \"P3\") |\n| `TRIGGERS` | constant | TRIGGERS = {name: _HUMAN_DECISION_DESCRIPTIONS[name] |\n| `FLAT` | constant | FLAT = { |\n| `LabelSpec` | class | class LabelSpec |\n| `label_families` | function | def label_families() -> dict[str, frozenset[str]] |\n| `all_labels` | function | def all_labels() -> frozenset[str] |\n| `catalog` | function | def catalog() -> dict[str, LabelSpec] |\n\n## Depends on\n\n- `shared/commands.py`\n-",
      "score": 2.446,
      "key_symbols": [
        {
          "name": "PHASE_COLOR",
          "kind": "constant",
          "signature": "PHASE_COLOR = \"#1F75CB\"",
          "docstring": "",
          "start_line": 14,
          "end_line": 14
        },
        {
          "name": "ADVISOR_COLOR",
          "kind": "constant",
          "signature": "ADVISOR_COLOR = \"#6E49CB\"",
          "docstring": "",
          "start_line": 15,
          "end_line": 15
        },
        {
          "name": "PRIORITY_COLOR",
          "kind": "constant",
          "signature": "PRIORITY_COLOR = \"#ED9121\"",
          "docstring": "",
          "start_line": 16,
          "end_line": 16
        },
        {
          "name": "RUNNING_COLOR",
          "kind": "constant",
          "signature": "RUNNING_COLOR = \"#FC9403\"",
          "docstring": "",
          "start_line": 17,
          "end_line": 17
        }
      ]
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval.",
  "best_guesses": [
    {
      "file": "shared/develop.py",
      "why_relevant": "Контракт активности Develop — разработка по подготовленному Issue..",
      "score": 3.494
    },
    {
      "file": "worker/activities.py",
      "why_relevant": "Активность Develop: разработка по подготовленному Issue..",
      "score": 3.487
    }
  ],
  "_meta": {
    "timing_ms": 441.6,
    "hint": "No synthesis, and retrieval was weak. Refine the query with search_codebase rather than reading these files in order.",
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "shared/develop.py",
      "lines": "33-218",
      "defines": "mode:92, enabled:98, workflow_file:109, workflow_ref:113, runner_image:117, workspace_volume:121"
    },
    {
      "path": "worker/activities.py",
      "defines": "GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101, CommentIntentExtraction:115"
    },
    {
      "path": "shared/label_catalog.py",
      "lines": "14-17",
      "defines": "LabelSpec:49, label_families:88, all_labels:102, catalog:110, PHASE_COLOR:14, ADVISOR_COLOR:15"
    },
    {
      "path": "shared/lifecycle.py",
      "defines": "Transition:53, InvalidTransition:267, phase_label:276, phase_from_labels:280, is_terminal:294, allowed:298"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    }
  ]
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "github actions workflow pr-review openhands-resolver",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\nasync def trigger_openhands_resolver(issue: Issue",
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
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT",
      "relevance_score": 2.933,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.98
    },
    {
      "title": "Infrastructure: openhands/Dockerfile",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: openhands/Dockerfile\n\n**Type:** dockerfile | **Declared targets:** 1\n\n## Overview\n\n`openhands/Dockerfile` is an infrastructure file (dockerfile). It declares 1 named target, listed b",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "openhands/Dockerfile",
      "confidence_score": 0.96
    },
    {
      "title": "File: worker/github_client.py",
      "page_type": "file_page",
      "snippet": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется",
      "relevance_score": 2.842,
      "sources": [
        "fts"
      ],
      "target_path": "worker/github_client.py",
      "confidence_score": 0.95
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/review-package` is an infrastruct",
      "relevance_score": 2.784,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/review-package",
      "confidence_score": 0.93
    },
    {
      "title": "Symbol: worker.worker.main",
      "page_type": "symbol_spotlight",
      "snippet": "evel references, not confirmed call sites.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bf",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/worker.py::main",
      "file": "worker/worker.py",
      "confidence_score": 0.91
    },
    {
      "title": "File: shared/repowise.py",
      "page_type": "file_page",
      "snippet": "лноту свойством построения, а не добросовестности модели.\n\nМодуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и\n`shared/agent_events.py`. Он вызывается и из воркера, и из подгот",
      "relevance_score": 2.717,
      "sources": [
        "fts"
      ],
      "target_path": "shared/repowise.py",
      "confidence_score": 0.91
    },
    {
      "title": "File: shared/pr_closing.py",
      "page_type": "file_page",
      "snippet": "# shared/pr_closing.py\n\n## Overview\n\nДоведение PR по замечаниям ревью — круг правок (точка передачи H3→H4).\n\nPR-Agent публикует ревью и останавливается: доводить код до соответствия\nзамечаниям — не ег",
      "relevance_score": 2.677,
      "sources": [
        "fts"
      ],
      "target_path": "shared/pr_closing.py",
      "confidence_score": 0.89
    },
    {
      "title": "File: shared/repo_ref.py",
      "page_type": "file_page",
      "target_path": "shared/repo_ref.py",
      "snippet": "Ссылка на репозиторий, не привязанная к форме `owner/repo`.",
      "relevance_score": 2.022,
      "sources": [
        "symbol"
      ],
      "confidence_score": 0.67
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
      "path": "openhands/Dockerfile"
    },
    {
      "path": "worker/github_client.py"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    },
    {
      "path": "worker/worker.py"
    },
    {
      "path": "shared/repowise.py"
    },
    {
      "path": "shared/pr_closing.py"
    },
    {
      "path": "shared/repo_ref.py"
    },
    {
      "path": "worker/llm.py"
    }
  ]
}

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "pr-review.yml workflow dispatch",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/develop.py",
      "page_type": "file_page",
      "snippet": "етки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсю",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/develop.py",
      "confidence_score": 1.0
    },
    {
      "title": "File: worker/github_client.py",
      "page_type": "file_page",
      "snippet": "n | def list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict] |\n| `list_linked_prs` | function | def list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict] |",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "worker/github_client.py",
      "confidence_score": 0.98
    },
    {
      "title": "Symbol: worker.activities.dev_dispatch",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.dev_dispatch\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def dev_dispatch(issue: IssueInput, branch: str) -> None",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::dev_dispatch",
      "file": "worker/activities.py",
      "confidence_score": 0.96
    },
    {
      "title": "Symbol: worker.activities.run_bug_pipeline",
      "page_type": "symbol_spotlight",
      "snippet": "n_bug_pipeline(issue: IssueInput) -> None\n```\n\n## Overview\n\nTODO: перенести содержимое bug-pipeline.yml аналогично.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n32 files",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bug_pipeline",
      "file": "worker/activities.py",
      "confidence_score": 0.94
    },
    {
      "title": "Infrastructure: Makefile",
      "page_type": "infra_page",
      "snippet": "n infrastructure file (makefile). Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n\n\n## Source\n\n```makefile\n# Layer A operator commands. Run `make setup` once, the",
      "relevance_score": 2.828,
      "sources": [
        "fts"
      ],
      "target_path": "Makefile",
      "confidence_score": 0.93
    },
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "lop.py`). `local` — прогон одноразовым контейнером\nна своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\nв GitHub Actions, для репозиториев без стенда.\n\nВозвращает номер PR (режи",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "confidence_score": 0.91
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/subagent-driven-development/scripts/review-package` is an infrastruct",
      "relevance_score": 2.742,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/review-package",
      "confidence_score": 0.91
    },
    {
      "title": "File: shared/pr_closing.py",
      "page_type": "file_page",
      "snippet": "# shared/pr_closing.py\n\n## Overview\n\nДоведение PR по замечаниям ревью — круг правок (точка передачи H3→H4).\n\nPR-Agent публикует ревью и останавливается: доводить код до соответствия\nзамечаниям — не ег",
      "relevance_score": 2.717,
      "sources": [
        "fts"
      ],
      "target_path": "shared/pr_closing.py",
      "confidence_score": 0.9
    },
    {
      "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "page_type": "infra_page",
      "snippet": "s an infrastructure file (shell). Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Resolve and ensure the working-tree",
      "relevance_score": 2.662,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace",
      "confidence_score": 0.88
    },
    {
      "title": "File: shared/lifecycle.py",
      "page_type": "file_page",
      "snippet": "_FOR_DEV = \"ready-for-dev\" |\n| `IN_DEVELOPMENT` | constant | IN_DEVELOPMENT = \"in-development\" |\n| `PR_OPEN` | constant | PR_OPEN = \"pr-open\" |\n| `PR_REVIEW` | constant | PR_REVIEW = \"pr-review\" |\n| `",
      "relevance_score": 2.639,
      "sources": [
        "fts"
      ],
      "target_path": "shared/lifecycle.py",
      "confidence_score": 0.87
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
      "path": "worker/github_client.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "Makefile"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/review-package"
    },
    {
      "path": "shared/pr_closing.py"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
    },
    {
      "path": "shared/lifecycle.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": ".claude/skills/systematic-debugging/find-polluter.sh"
    }
  ]
}

## Ход 5 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "dispatch_workflow function github_client",
  "limit": 5
}
```

**Ответ:**

{
  "results": [
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
      "score": 47.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/repo_ref.py::GITHUB",
      "name": "GITHUB",
      "kind": "constant",
      "file": "shared/repo_ref.py",
      "start_line": 18,
      "end_line": 18,
      "signature": "GITHUB = \"github\"",
      "qualified_name": "shared.repo_ref.GITHUB",
      "language": "python",
      "score": 47.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_gitlab_webhook_resilience.py::client",
      "name": "client",
      "kind": "function",
      "file": "tests/test_gitlab_webhook_resilience.py",
      "start_line": 24,
      "end_line": 38,
      "signature": "def client(monkeypatch)",
      "qualified_name": "tests.test_gitlab_webhook_resilience.client",
      "language": "python",
      "score": 42.65,
      "next": "get_symbol"
    },
    {
      "title": "Repository Overview: poh-issue-agents",
      "page_type": "repo_overview",
      "snippet": "/workflows.py::IssueAnalysis::run` (3 steps)\n\n- `webhook/main.py::agent_event` (3 steps)\n\n- `worker/github_client.py::dispatch_workflow` (6 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over t",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "poh-issue-agents",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\nasync def trigger_openhands_resolver(issue: Issue",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
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
      "path": "shared/repo_ref.py"
    },
    {
      "path": "tests/test_gitlab_webhook_resilience.py"
    },
    {
      "path": "worker/activities.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'dispatch_workflow', 'github_client'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}
