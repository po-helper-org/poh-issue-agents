# Итог

Задача: частичная публикация сорванного прогона разработки (ветка + черновой PR + честный комментарий, фаза остаётся `failed`). Индекс отвечал в деградации `no-llm-provider` — синтеза не было, но retrieval отдавал живые тела символов; все факты ниже взяты из этих тел.

1. **Где живёт отказ.** `IssueDevelopment` — `worker/workflows.py:3540`, дочерний Temporal-workflow с фиксированным id `develop-<repo>-<n>`. Порядок в `run` (`worker/workflows.py:3561`): `dev_begin` → (при `mode == "dispatch"` — `dev_dispatch` и `return None`) → `dev_prepare` → `dev_announce` → `build_mvp_plan` (под маркером `issue-lifecycle-develop-plan-stage`, отказ плана прогон НЕ роняет) → `dev_run_agent` → `dev_followups` → `dev_tests` → `dev_publish`. `finally` делает ровно одно — `capture_episode` (маркер `issue-lifecycle-capture-episode-always`). Очистки рабочего каталога в теле воркфлоу нет вовсе — публиковать «что успел» из `finally` некому и нечему мешать.
2. **Ретраи объясняют каскад.** `cheap = RetryPolicy(maximum_attempts=3)` — клон, публикация, запись эпизода; `once` — агент, тесты, план. `dev_tests` стоит ДО `dev_publish` и в одной попытке: красные тесты → публикация не выполняется ни разу, исключение уходит в родителя.
3. **Точная точка ошибки из #166** — `_dev_tests` (`worker/activities.py:3252`): `RuntimeError(f"проверки не прошли (код {returncode})...")`. Сигнал `tests_passed` пишется на диск (`_write_signal(root, ...)`) ДО возбуждения; команда берётся из `DEVELOP_TEST_COMMAND` и гоняется `subprocess.run(shell=True)` — в `activities.py` это зафиксировано как security-сигнал.
4. **«Честный комментарий с причиной» уже существует.** Родитель `_begin_development` (`worker/workflows.py:2939`) ловит исключение стадии, зовёт `activities.post_error_label(issue, reason)` (30 c, 5 попыток) и возвращает `(lifecycle.FAILED, "failed", True)`; отдельная ветка `WorkflowAlreadyStartedError` уводит в `in-development`. Черновой PR в эту схему встраивается как дополнительная активность в `finally`, не меняя контракт возврата (`int | None`).
5. **Пустой прогон — соседний, но другой исход**: после `finally` при `number is None` — диагноз `dev_empty_run_reason` (маркер `issue-lifecycle-empty-run-diagnosis`, уточнение не имеет права подменить исходный отказ) и `raise ApplicationError(reason)` (`worker/workflows.py:3690-3713`). Частичной публикации тут нет — копировать её семантику «не подменять причину» стоит.
6. **Прецедент для подражания** — `publish_analysis_partial(analyze, reason) -> list[str]` (`worker/activities.py:2550`): клон ещё жив? (нет → warning и `[]`) → собрать артефакты (пусто → `[]`, не ошибка) → `github_client.push_artifacts_to_branch` в `research/issue-N` → push entire-сессии → комментарий «⏸ Анализ собран частично» с причиной и ссылками. Вторые прецеденты: `publish_bft_partial` (`worker/activities.py:4852`); для текстов отказа — `publish_analysis_error` (4075) и `publish_bft_error` (4895, комментарий + Sentry). У разработки аналога нет — подтверждено.
7. **Черновой PR клиентом сегодня не открывается.** `publish_worktree` (`worker/github_client.py:674-826`) коммитит (`git add -A`, `add -f` для `force_include`), пушит `--force-with-lease` и открывает PR прямым `POST /pulls` с телом `{title, head, base, body}` — поля `draft` НЕТ (хвост `worker/github_client.py:806-811`); 422 «already exists» возвращает существующий PR — идемпотентность ретраев уже есть. Параметры `ignore_for_empty_check`/`force_include` уже решают вопрос «пустой прогон vs только `.harness/`».
8. **Готовые помощники в `shared/develop.py`** (чистый модуль): `work_branch(n) -> "feature/{n}-openhands"` (`shared/develop.py:316`), `pr_body(n, branch)` (`:409`, содержит `Closes #N` — для черновика с красными тестами, вероятно, не годится как есть), `SERVICE_FILES = (.task.md, .followups.md, .verdict.md, .reflect.md)` (`:212`), `clear_service_files(clone_dir, keep_dir)` (`:234`), `IN_DEVELOPMENT_LABEL`. Ветка анализа (`research/issue-N`) и ветка разработки — разные имена.
9. **Точки интеграции новой активности**: регистрация в `DEVELOP_ACTIVITIES` (`worker/worker.py:44`); любая новая команда в теле воркфлоу — только под `workflow.patched(...)` (три живых прецедента внутри `IssueDevelopment.run`); обёртка активностей — `_run_with_heartbeat` (`worker/activities.py`, `dev_tests:3509`, `dev_publish:3519`).
10. **Тесты и риск правки.** Активностные: `tests/test_dev_empty_run.py` (диагностика пустого прогона, guard памяти, MCP-конфиг) и `tests/test_dev_handoff_once.py` (announce-once, git-ошибки, неутечка токена); воркфлоу: `tests/test_develop_workflow.py` и `tests/test_develop_is_a_child.py` (обе `ISSUE = 39`) — естественное место сценария «шаг упал → публикация в finally». Подмены: `FakeGitHub` (`tests/test_e2e_issue_lifecycle.py:82`, `tests/test_estimate_activities.py:10`) + monkeypatch `_issue()`. Риск: `worker/workflows.py` — hotspot 0.998, 41 фикс/6 мес, `test_gap: true`; `worker/activities.py` — hotspot 1.0, 55 фиксов; файлы меняются вместе (последняя совместная правка 2026-09-01). Практический вывод: изменения вести парами «активность + воркфлоу», под маркером, с тестом на оба ветки маркера.

# Открытые вопросы

1. **Фильтр draft у свипера PR-Agent.** В `poh-pr-agents` точка фильтрации не установлена: в `webhook.parse_events` триггеры `PR_TRIGGER_ACTIONS = {opened, reopened, ready_for_review, synchronize}` без проверки draft, и в теле `sweep` (`self-hosted/reliability/sweeper.py`) фильтра по draft нет; реализация инъектируемого `list_open_prs` (`sweeper_adapter`) не читалась. Факт сегодня: черновой PR разработки получил бы `/describe`+`/review` от вебхука и дозапуск от свипера — правка в `poh-pr-agents` действительно нужна, но где именно резать (webhook vs adapter vs `ready_for_review`-семантика) индекс не ответил.
2. **Текст спеки D1–D14 и плана** индексу недоступен: ветка `spec/dev-partial-publish` не проиндексирована (индекс — коммит `3eafc42` на `main`), в рабочей копии файлов тоже нет. Отсюда неясно предписанное имя ветки/тела черновика: переиспользовать `develop.work_branch`/`pr_body` или вводить свои (в `pr_body` стоит `Closes #N`, что для черновика по красным тестам скорее всего меняется).
3. **Жизнь клона после сорванного прогона.** Cleanup-активности в `IssueDevelopment.run` нет (проверено по телу 3561–3714), но нет и подтверждения, что каталог задачи гарантированно жив до момента частичной публикации (состав `root` из `_dev_paths`, внешние чистильщики). Аналога проверки `clone_dir.is_dir()` из `publish_analysis_partial` для разработки в индексе не нашлось — её, по-видимому, и надо завести.

# Диалог

1. **Рамка.** `list_repos` + `get_overview`: workspace из 9 репозиториев, целевой — `poh-issue-agents` (default); `poh-demo-checkout` в workspace нет (сосед — только `poh-pr-agents`). Сразу видно: `worker/workflows.py` — худший по health файл и топ-churn.
2. **«Где IssueDevelopment и что делают dev_tests/dev_publish»** (`get_answer`): каркас `IssueDevelopment.run` со всеми шагами, маркерами и политиками ретраев; тела `dev_tests`/`dev_publish` и `_dev_tests`/`_dev_publish`; точный текст RuntimeError из отказа #166.
3. **«Как устроен образец publish_analysis_partial»** (`get_answer`): полное тело активности, список её соседей-прецедентов (`publish_bft_partial`, `publish_analysis_error`, `publish_bft_error`), замечание, что анализ публикует только ветку — PR не открывает.
4. **«Умеет ли клиент открывать draft PR»** (`get_answer` + `get_symbol` хвоста 795-826): сигнатура `publish_worktree` без `draft`; push `--force-with-lease` и `POST /pulls {title,head,base,body}`; идемпотентность на 422; `create_pr_with_files` как второй путь.
5. **«Что после исключения из dev_tests»** (`get_answer` + два диапазонных чтения): `finally` → только `capture_episode`; пустой прогон → `ApplicationError` с диагностикой; родитель ловит, зовёт `post_error_label`, возвращает `FAILED`; cleanup-активности в стадии нет.
6. **«Что даёт shared/develop.py»** (`get_answer`): `work_branch`, `pr_body`, `SERVICE_FILES`, `clear_service_files`, `IN_DEVELOPMENT_LABEL`; модуль намеренно чистый (без сети и Temporal).
7. **«Чем покрыты тестами стадии разработки»** (`get_answer` → пустой `search_codebase` по путям → `get_context` двух файлов → `search_codebase` по символам): активностные тесты перечислены; воркфлоу-тесты найдены — `tests/test_develop_workflow.py`, `tests/test_develop_is_a_child.py`; обе реализации `FakeGitHub` показаны телами.
8. **«Чем грозит правка»** (`get_risk` по 4 файлам): хотспот-оценки, число фиксов, `test_gap` на `workflows.py`, co-change пары, security-сигнал `shell=True` в `_dev_tests`, биомаркеры на `clear_service_files`.
9. **Соседний репозиторий `poh-pr-agents` (отдельным ходом, с alias)**: `get_answer` дал слабый набор → переспрос `get_context` по `sweeper.py` и `webhook.py` со скелетами: `PR_TRIGGER_ACTIONS` без draft, `sweep` дозапускает ревью на любом открытом PR, `STOP_LABELS`, `parse_root_issue` читает `Closes #N` из тела PR. Вопрос о draft-фильтре закрыт наполовину — точка фильтрации не названа (см. «Открытые вопросы»).


---
session: rw-analysis-po-helper-org__poh-issue-agents-293
workspace: contour
turns: 17
started: 2026-09-02T18:21:08Z
finished: 2026-09-02T18:26:46Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-pr-agents` | `9f15ada9e4e9` | 15 мин |

# Диалог

## Ход 1 · `list_repos` · contour

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
      "last_commit_at_index": "c656249634f1d651b0b97775981bf9f906dd5f03"
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
      "last_commit_at_index": "cf604a7306602bd5f1120d53dd9d7ac7ea16f882"
    },
    {
      "alias": "poh-issue-agents",
      "path": "poh-issue-agents",
      "absolute_path": "/workspaces/contour/poh-issue-agents",
      "is_default": true,
      "indexed_at": "2026-08-19T16:06:57.382649+00:00",
      "last_commit_at_index": "3eafc421513518cab04b3e9b99678a19aea125e6"
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

## Ход 2 · `get_overview` · contour

**Запрос:**

```json
{}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1",
  "code_health": {
    "average_health": 8.5,
    "band": "healthy",
    "hotspot_health": 5.49,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 766,
    "file_count": 454,
    "distribution": {
      "total_files": 454,
      "total_nloc": 92641,
      "bands": {
        "healthy": {
          "files": 392,
          "nloc": 69671,
          "pct": 75.2
        },
        "warning": {
          "files": 57,
          "nloc": 14748,
          "pct": 15.9
        },
        "alert": {
          "files": 5,
          "nloc": 8222,
          "pct": 8.9
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
    "files_git_attributed": 462,
    "hotspot_count": 63,
    "avg_bus_factor": 0.8,
    "files_with_bus_factor_1": 206,
    "churn_trend": "increasing",
    "top_churn_modules": [
      "worker/activities.py",
      ".claude/skills",
      "worker/workflows.py",
      "worker/worker.py",
      "docs/superpowers"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 168,
        "percentage": 36.4
      },
      {
        "name": "kibarik",
        "files_owned": 83,
        "percentage": 18.0
      },
      {
        "name": "openhands-agent",
        "files_owned": 14,
        "percentage": 3.0
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "tests (45)",
      "size": 12
    },
    {
      "id": 1,
      "label": "acceptance_proposal",
      "size": 12
    },
    {
      "id": 2,
      "label": "tests (24)",
      "size": 10
    },
    {
      "id": 3,
      "label": "tests (34)",
      "size": 10
    },
    {
      "id": 4,
      "label": "tests",
      "size": 8
    },
    {
      "id": 5,
      "label": "server",
      "size": 7
    },
    {
      "id": 6,
      "label": "external:~/threads",
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
    "total_pages": 298,
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
        "descendants": 10
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 59
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
        "descendants": 130
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
        "file_count": 66
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 140
      },
      {
        "name": "Utility",
        "description": "",
        "file_count": 31
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 70
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 147
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
      "section": "6.30"
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
      "co_change_count": 86,
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
            "poh-infra",
            "poh-issue-agents"
          ],
          "edge_count": 12
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
        }
      ]
    },
    "contract_links": {
      "total_contracts": 24,
      "total_links": 0,
      "by_type": {
        "http": 13,
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
    "indexed_commit": "3eafc4215135",
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

## Ход 3 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Где определён класс IssueDevelopment, каков полный порядок стадий (phases) workflow разработки — какие стадии идут и в каком порядке, и что именно делает стадия dev_tests и dev_publish? Какая активность публикует ветку и создаёт пул-реквест?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `dev_tests`, `dev_publish`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py"
  ],
  "confidence": "low",
  "retrieval_quality": "weak",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    "worker/workflows.py",
    "shared/lifecycle.py",
    "worker/activities.py::trigger_openhands_resolver",
    "shared/workflow_types.py"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "ssue: IssueInput) -> None |\n| `DEV_CLONE_TIMEOUT_SEC` | constant | DEV_CLONE_TIMEOUT_SEC = 300 |\n| `DEV_TESTS_TIMEOUT_SEC` | constant | DEV_TESTS_TIMEOUT_SEC = 900 |\n| `INJECTED_RULES_FILE` | constant",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 136 public symbols and depends on 23 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `github_client` | variable | github_client = forge |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_cl",
      "score": 4.564,
      "key_symbols": [
        {
          "name": "close_answered_by_body_edit",
          "kind": "function",
          "signature": "def close_answered_by_body_edit(issue: IssueInput) -> None:",
          "docstring": "Снять вопрос гейта критерия, если человек ответил на него ВПИСЫВАНИЕМ\n    критерия в тело, а не командой `/harness-answer` (спека A23: «команда —\n    удобство, а не единственная дверь»).\n\n    Финальное ревью ветки, находка I4 (Important). `_start_development`\n    (`worker/workflows.py`) верно пропускает задачу в разработку, как только\n    `read_acceptance_criterion` вернул непустой текст, — но раньше это никак\n    не трогало ни блок открытого вопроса в теле, ни метку\n    `NEEDS_HUMAN_ANSWER`: они оставались висеть на задаче, уже ушедшей в\n    разработку, и ничто их больше не снимало. Выборка `needs-human:*`\n    переставала быть полной очередью к людям.\n\n    Снимаем ТЕМ ЖЕ путём, что и обычный ответ командой: записываем решение в\n    журнал (текстом уже вписанного в тело критерия) и чистим блок вопроса и\n    метку — `_record_decision` уже умеет это одним атомарным обращением к\n    телу (запись в журнал, `clear_open`, `clear_draft`, снятие метки).\n\n    `place=False` (находка F8, Minor, второй круг финального ревью): текст\n    ответа уже ВЗЯТ из тела (`_howtodemo_block` читает либо размеченный\n    блок, либо раздел по заголовку — см. её докстринг), класть его же\n    обратно в размеченный блок незачем. Если источником был раздел по\n    заголовку (человек вписал критерий заголовком, а не через `/harness-\n    answer`), запись всё равно создала бы там ВТОРОЙ, размеченный экземпляр\n    — а чтение отдаёт приоритет размеченному блоку над разделом, так что\n    дальнейшие правки заголовка человеком молча переставали бы учитываться.\n\n    НЕ идемпотентна тривиально, хотя раньше докстринг это утверждал.\n    `_record_decision` пишет тело ОДНИМ обращением, но снимает метку\n    `NEEDS_HUMAN_ANSWER` ОТДЕЛЬНЫМ, следующим сетевым вызовом (тот же край,\n    что уже закрыт в `answer_question` — см. её комментарий «Ревью, находка\n    1»). Падение именно на этом, втором вызове раньше означало: повтор\n    видит — блока вопроса в теле уже нет (записан прошлой попыткой) — и\n    молча возвращается, доложив успех, а метка остаётся висеть НАВСЕГДА:\n    `_start_development` эту активность по данной задаче больше не позовёт,\n    фаза уже ушла в разработку. Находка F1 (Important, второй круг\n    финального ревью) — ровно тот дефект, ради устранения которого сама\n    активность (I4) и заводилась, доложенный как успех.\n\n    `answer_question` тот же край закрывает сверкой ответа с журналом ПО\n    `question_id` — но у ЭТОЙ функции id нет: вопрос обнаруживается заново\n    каждый вызов, и к моменту повтора он уже пропал из тела вместе со своим\n    id. Прямой и дешёвый признак прерванной попытки — сама метка:\n    `_record_decision` снимает её ПОСЛЕДНЕЙ, значит если открытого вопроса\n    уже нет, а метка всё ещё висит — предыдущая попытка прервалась ровно\n    между записью тела и снятием метки, и остаётся только довершить этот\n    один недостающий шаг.",
          "start_line": 711,
          "end_line": 770
        },
        {
          "name": "report_question_close_failure",
          "kind": "function",
          "signature": "def report_question_close_failure(issue: IssueInput, reason: str) -> None:",
          "docstring": "Сделать видимым отказ `close_answered_by_body_edit` (находка F6,\n    Important, второй круг финального ревью).\n\n    Вызывается из `_start_development` (`worker/workflows.py`) ПОСЛЕ того,\n    как решение продолжить в разработку УЖЕ принято, — отказ здесь не\n    условие входа, а сорвавшаяся уборка (блок вопроса и метка `NEEDS_HUMAN_\n    ANSWER` могли остаться висеть на задаче, ушедшей в разработку). До этой\n    правки видимость была только `workflow.logger.warning` — хлебной\n    крошкой для Sentry (порог `event_level=ERROR`, не WARNING, см. докстринг\n    `sentry_setup`), а комментарий человеку с обещанием «донастрою при\n    следующем проходе» был бы неправдой: следующего прохода этой ветки НЕ\n    будет — фаза уже уезжает из READY_FOR_DEV вместе с этим самым вызовом.",
          "start_line": 774,
          "end_line": 797
        },
        {
          "name": "set_phase",
          "kind": "function",
          "signature": "def set_phase(repo: str, issue_number: int, phase: str) -> None:",
          "docstring": "Метка фазы с соблюдением инварианта «одна фаза — одна метка».\n\n    Две метки `phase:*` на Issue — противоречие, а не история: по ним нельзя\n    восстановить состояние. Поэтому предыдущая снимается, а не остаётся рядом.\n\n    Допустимость самого перехода проверяет воркфлоу (у него есть предыдущая\n    фаза); здесь — только запись, идемпотентная по построению.\n\n    Целевая метка ставится раньше снятия прежних: окно, в котором меток\n    `phase:*` нет вовсе, хуже окна, в котором их две. Атомарно это делается\n    только на провайдере, умеющем менять набор одним запросом.",
          "start_line": 1087,
          "end_line": 1108,
          "source_excerpt": "def set_phase(repo: str, issue_number: int, phase: str) -> None:\n    \"\"\"Метка фазы с соблюдением инварианта «одна фаза — одна метка».\n\n    Две метки `phase:*` на Issue — противоречие, а не история: по ним нельзя\n    восстановить состояние. Поэтому предыдущая снимается, а не остаётся рядом.\n\n    Допустимость самого перехода проверяет воркфлоу (у него есть предыдущая\n    фаза); здесь — только запись, идемпотентная по построению.\n\n    Целевая метка ставится раньше снятия прежних: окно, в котором меток\n    `phase:*` нет вовсе, хуже окна, в котором их две. Атомарно это делается\n    только на провайдере, умеющем менять набор одним запросом.\n    \"\"\"\n    target = lifecycle.phase_label(phase)\n    stale_labels = [lifecycle.phase_label(other) for other in lifecycle.PHASES]\n    # Индикатор разработки — не фаза, но живёт по тому же правилу: он сообщает\n    # «задача у агента разработки», и после открытия PR это уже неправда.\n    # Снимать его в самой активности Develop нельзя — она к тому моменту давно\n    # завершилась; единственная точка, которая знает о смене состояния, — здесь.\n    if phase != lifecycle.IN_DEVELOPMENT:\n        stale_labels.append(develop.IN_DEVELOPMENT_LABEL)\n    github_client.set_labels(repo, issue_number, add=[target], remove=stale_labels)"
        },
        {
          "name": "DEV_TESTS_TIMEOUT_SEC",
          "kind": "constant",
          "signature": "DEV_TESTS_TIMEOUT_SEC = 900",
          "docstring": "",
          "start_line": 2608,
          "end_line": 2608,
          "source_excerpt": "DEV_TESTS_TIMEOUT_SEC = 900"
        },
        {
          "name": "_publish_dev_dialog_sync",
          "kind": "function",
          "signature": "def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:",
          "docstring": "Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.\n\n    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе\n    разбор начнут не с того места.",
          "start_line": 3226,
          "end_line": 3249,
          "source_excerpt": "def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:\n    \"\"\"Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.\n\n    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе\n    разбор начнут не с того места.\n    \"\"\"\n    if not repowise.enabled():\n        return\n    text = _collect_dev_dialog(issue.repo, issue.issue_number, run_failed=False)\n    path = DEV_DIALOG_PATH.format(n=issue.issue_number)\n    try:\n        if branch:\n            github_client.push_artifacts_to_branch(\n                issue.repo, branch, {path: text},\n                f\"docs(repowise): диалог разработки по issue #{issue.issue_number}\")\n        github_client.post_comment(\n            issue.repo, issue.issue_number,\n            f\"## 🧭 Контекст из Repowise (разработка)\\n\\n\"\n            f\"Диалог агента разработки с индексом кода — `{path}`\"\n            f\"{f' в ветке `{branch}`' if branch else ''}.\\n\\n\"\n            f\"<details><summary>Показать</summary>\\n\\n{text[:20000]}\\n\\n</details>\")\n    except Exception as exc:\n        logger.warning(\"диалог разработки не опубликован (%s#%s): %s\",\n                       issue.repo, issue.issue_number, exc)"
        },
        {
          "name": "_dev_tests",
          "kind": "function",
          "signature": "def _dev_tests(issue: IssueInput) -> str:",
          "docstring": "Прогон проверок проекта. Пусто в конфиге — шаг пропускается.\n\n    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от\n    агента CI может и не запуститься (события от токена Actions не порождают\n    прогонов).",
          "start_line": 3252,
          "end_line": 3279,
          "source_excerpt": "def _dev_tests(issue: IssueInput) -> str:\n    \"\"\"Прогон проверок проекта. Пусто в конфиге — шаг пропускается.\n\n    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от\n    агента CI может и не запуститься (события от токена Actions не порождают\n    прогонов).\n    \"\"\"\n    root, clone_dir = _dev_paths(issue)\n    command = os.environ.get(\"DEVELOP_TEST_COMMAND\", \"\").strip()\n    if not command:\n        # Пусто — шаг пропускается, и это НЕ «тесты прошли». Записываем\n        # неизвестность явно: иначе слой саморефлексии засчитает пропуск как\n        # успех, а свёртка сигналов начнёт хвалить прогоны, которых не было.\n        _write_signal(root, \"tests_passed\", None)\n        return \"(проверки не заданы — DEVELOP_TEST_COMMAND пуст)\"\n\n    result = subprocess.run(command, shell=True, cwd=str(clone_dir),\n                            capture_output=True, text=True, timeout=DEV_TESTS_TIMEOUT_SEC)\n    out = ((result.stdout or \"\") + (result.stderr or \"\"))[-3000:]\n\n    # Исход пишется ДО возможного исключения. Красный прогон — самый интересный\n    # для разбора, и терять о нём запись значит собирать статистику только по\n    # удачам.\n    _write_signal(root, \"tests_passed\", result.returncode == 0)\n\n    if result.returncode != 0:\n        raise RuntimeError(f\"проверки не прошли (код {result.returncode}):\\n{out[-1500:]}\")\n    return out"
        },
        {
          "name": "_dev_publish",
          "kind": "function",
          "signature": "def _dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Коммит, пуш и PR — руками воркера, его токеном.\n\n    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен\n    контуру. Возвращает номер PR либо None, если агент ничего не изменил.",
          "start_line": 3282,
          "end_line": 3321,
          "source_excerpt": "def _dev_publish(issue: IssueInput, branch: str) -> int | None:\n    \"\"\"Коммит, пуш и PR — руками воркера, его токеном.\n\n    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен\n    контуру. Возвращает номер PR либо None, если агент ничего не изменил.\n    \"\"\"\n    # Корень задачи нужен не только клону: туда перекладывается файл намерений,\n    # чтобы пережить снятие из рабочего дерева.\n    root, clone_dir = _dev_paths(issue)\n    # Постановка — вход контура, а не часть правки. Она лежит в рабочем дереве, и\n    # `git add -A` забирает её вместе с кодом: на живом прогоне это дало PR из\n    # одного файла на 1721 строку — нашей же постановки. Хуже того, дифф из неё\n    # обманывал гвард «изменений нет — открывать нечего», и PR открывался по\n    # прогону, в котором агент не тронул ни одного файла.\n    # Одна точка снятия на весь контур: перечень служебных файлов живёт в\n    # `shared/develop.py`, а не переписывается в каждой функции заново.\n    removed = develop.clear_service_files(clone_dir, keep_dir=root)\n    if removed:\n        logger.info(\"Develop %s#%s: сняты служебные файлы: %s\",\n                    issue.repo, issue.issue_number, \", \".join(removed))\n    work = develop.work_branch(issue.issue_number)\n    return github_client.publish_worktree(\n        issue.repo, str(clone_dir), work,\n        title=f\"feat(#{issue.issue_number}): {issue.title}\",\n        body=develop.pr_body(issue.issue_number, branch=branch),\n        message=f\"feat(#{issue.issue_number}): реализация по системным требованиям\",\n        # `.harness/` — единственный служебный каталог, что НЕ снимается\n        # (задача 7: контекст обязан дойти до PR). Он пишется в `_dev_prepare`\n        # ДО прогона агента и потому существует независимо от того, тронул ли\n        # агент код, — «пустой прогон» больше не значит «дифф пуст», если\n        # эту проверку не поправить. Исключаем каталог из решения «есть ли\n        # диф», а не из самого коммита: `git add -A` продолжает забирать его.\n        ignore_for_empty_check=(f\"{task_context.DIR}/**\",),\n        # M3 (ревью задачи 7): если `.gitignore` ЦЕЛЕВОГО репозитория содержит\n        # `.harness/`, голый `git add -A` молча пропускает каталог — PR уйдёт\n        # без контекста и без единого предупреждения. `force_include`\n        # заставляет каталог попасть в коммит независимо от `.gitignore` и\n        # подтверждает это фактом (деревом HEAD), а не только вызовом `add -f`.\n        force_include=(task_context.DIR,),\n    )"
        },
        {
          "name": "dev_tests",
          "kind": "function",
          "signature": "async def dev_tests(issue: IssueInput) -> None:",
          "docstring": "Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.",
          "start_line": 3509,
          "end_line": 3515,
          "source_excerpt": "async def dev_tests(issue: IssueInput) -> None:\n    \"\"\"Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.\n    \"\"\"\n    await _run_with_heartbeat(_dev_tests, issue, label=\"dev:tests\")"
        },
        {
          "name": "dev_publish",
          "kind": "function",
          "signature": "async def dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Шаг 6: коммит, пуш и PR — руками воркера, его токеном.\n\n    `None` — агент не изменил ни одного файла. Это не сбой шага, а его\n    результат; решение, что делать с пустым прогоном, принимает воркфлоу.",
          "start_line": 3519,
          "end_line": 3525,
          "source_excerpt": "async def dev_publish(issue: IssueInput, branch: str) -> int | None:\n    \"\"\"Шаг 6: коммит, пуш и PR — руками воркера, его токеном.\n\n    `None` — агент не изменил ни одного файла. Это не сбой шага, а его\n    результат; решение, что делать с пустым прогоном, принимает воркфлоу.\n    \"\"\"\n    return await _run_with_heartbeat(_dev_publish, issue, branch, label=\"dev:publish\")"
        },
        {
          "name": "publish_decomposition",
          "kind": "function",
          "signature": "def publish_decomposition(issue: IssueInput, plan: dict, branch: str) -> list[int]:",
          "docstring": "Создаёт подзадачи и публикует план в родителе.\n\n    Порядок важен: сначала все подзадачи, потом сводка. Сводка ссылается на\n    номера, которых до создания не существует, а план с битыми ссылками хуже\n    отсутствующего — по нему пойдут и упрутся.\n\n    Зависимости проставляются вторым проходом по той же причине: подзадача\n    может зависеть от той, что создаётся позже.",
          "start_line": 3842,
          "end_line": 3880
        }
      ]
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 48 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `AGENT_RESEARCH` | constant | AGENT_RESEARCH = \"__agent__:research\" |\n| `HOWTODEMO_TASK_QUEUE` | constant | HOWTODEMO_TASK_QUEUE = \"howtodemo\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | c",
      "score": 4.564,
      "key_symbols": [
        {
          "name": "_phase_await_decision",
          "kind": "method",
          "signature": "async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:",
          "docstring": "Фаза `classified`: ждём решения человека о тяжёлой стадии.\n\n        При `RESEARCH_AUTOSTART` ожидания нет: триаж сам решает, куда двигаться\n        дальше, по типу задачи. Это первая из двух парковок основного пути;\n        вторая — перед разработкой (`DEVELOP_AUTOSTART`). Включены обе — контур\n        идёт от заявки до PR без единого касания человека.\n\n        Тип решает так же, как решала бы метка человека: запрос на функционал\n        уходит в аналитику, баг — сразу разработчику мимо неё. Сокращённый триаж\n        (`origin:agent`) типа не имеет — follow-up контура заводит агент, уже\n        понимая, что это; такую задачу ведём в аналитику, потому что описание в\n        ней короткое и требований не содержит.",
          "start_line": 1515,
          "end_line": 1613,
          "source_excerpt": "    async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:\n        \"\"\"Фаза `classified`: ждём решения человека о тяжёлой стадии.\n\n        При `RESEARCH_AUTOSTART` ожидания нет: триаж сам решает, куда двигаться\n        дальше, по типу задачи. Это первая из двух парковок основного пути;\n        вторая — перед разработкой (`DEVELOP_AUTOSTART`). Включены обе — контур\n        идёт от заявки до PR без единого касания человека.\n\n        Тип решает так же, как решала бы метка человека: запрос на функционал\n        уходит в аналитику, баг — сразу разработчику мимо неё. Сокращённый триаж\n        (`origin:agent`) типа не имеет — follow-up контура заводит агент, уже\n        понимая, что это; такую задачу ведём в аналитику, потому что описание в\n        ней короткое и требований не содержит.\n        \"\"\"\n        if deadlines.research_autostart:\n            label = self._classification_label\n            if label == \"advisor:bug\":\n                return (lifecycle.READY_FOR_DEV, \"bug\", True)\n            # Подзадача плана аналитику не заказывает: требования по фиче уже\n            # написаны — они в ветке анализа РОДИТЕЛЯ, и сама подзадача выведена\n            # из них. Полная цепочка FNR по каждой выводила бы выведенное: на\n            # фиче из четырёх подзадач это четыре прогона по восемь минут,\n            # четыре ветки `research/issue-N` и счёт впятеро больше — ради\n            # текста, который ничего не добавляет.\n            # Под маркером патча: у подзадач, уже уехавших в аналитику, этот\n            # выбор записан в историю, и другой на реплее — недетерминизм.\n            if self._plan_member and workflow.patched(\n                    \"issue-lifecycle-plan-member-skips-analysis\"):\n                return (lifecycle.SYSTEM_REQUIREMENTS, \"analysis\", True)\n            if label is None or label == \"advisor:feature-request\":\n                return (lifecycle.BUSINESS_ANALYSIS, \"analysis\", True)\n            # Консультация и «уже реализовано» закрываются ответом, а не кодом:\n            # автозапуск дорогой стадии по ним был бы тратой без адресата.\n            # Такие задачи и до этой фазы обычно не доходят, но если дошли —\n            # ждём человека, как раньше.\n\n        decision = await self._wait_for_signal(await self._park(\n            awaiting_mod.kind_for_phase(lifecycle.CLASSIFIED),\n            who=awaiting_mod.who_for_phase(lifecycle.CLASSIFIED),\n            reason=awaiting_mod.reason_for_phase(lifecycle.CLASSIFIED),\n            hours=awaiting_mod.deadline_hours(awaiting_mod.HUMAN_DECISION,"
        },
        {
          "name": "_begin_development",
          "kind": "method",
          "signature": "async def _begin_development(self, issue: IssueInput) -> tuple:",
          "docstring": "Передать задачу агенту разработки — без повторной проверки критерия.\n\n        Отдельная функция, а не хвост `_start_development`, по одной причине:\n        принятый ответ на вопрос о критерии (`_phase_await_build`) знает, что\n        критерий только что записан — `_place_decision` в `answer_question`\n        (`worker/activities.py`) положил его в блок HOWTODEMO ДО того, как\n        сюда вернулось управление. Дёрнуть `_start_development` заново означало\n        бы честный, но ЛИШНИЙ круг `read_acceptance_criterion` за тем же самым\n        текстом — активность, которая станет предсказуемым `True` в 100%\n        случаев, кроме одного: тело Issue успели поправить руками между\n        ответом и этим вызовом, и тогда лишний круг превратился бы в вопрос\n        по уже отвеченному критерию. Дешевле и честнее звать разработку\n        напрямую: `answer_question` вернула `accepted` — этого достаточно.\n\n        Одна точка на оба оставшихся входа — решение человека `build-me` и\n        автостарт. Две копии этого вызова разъехались бы на первой же правке\n        ретраев, и один из входов молча остался бы со старым поведением.\n\n        ISSUE-113: для подзадачи плана передаём root_issue и ветку родителя.",
          "start_line": 2939,
          "end_line": 3037,
          "source_excerpt": "    async def _begin_development(self, issue: IssueInput) -> tuple:\n        \"\"\"Передать задачу агенту разработки — без повторной проверки критерия.\n\n        Отдельная функция, а не хвост `_start_development`, по одной причине:\n        принятый ответ на вопрос о критерии (`_phase_await_build`) знает, что\n        критерий только что записан — `_place_decision` в `answer_question`\n        (`worker/activities.py`) положил его в блок HOWTODEMO ДО того, как\n        сюда вернулось управление. Дёрнуть `_start_development` заново означало\n        бы честный, но ЛИШНИЙ круг `read_acceptance_criterion` за тем же самым\n        текстом — активность, которая станет предсказуемым `True` в 100%\n        случаев, кроме одного: тело Issue успели поправить руками между\n        ответом и этим вызовом, и тогда лишний круг превратился бы в вопрос\n        по уже отвеченному критерию. Дешевле и честнее звать разработку\n        напрямую: `answer_question` вернула `accepted` — этого достаточно.\n\n        Одна точка на оба оставшихся входа — решение человека `build-me` и\n        автостарт. Две копии этого вызова разъехались бы на первой же правке\n        ретраев, и один из входов молча остался бы со старым поведением.\n\n        ISSUE-113: для подзадачи плана передаём root_issue и ветку родителя.\n        \"\"\"\n        # ISSUE-113 пункт 2: вычисляем ветку так же, как в _phase_handoff\n        source = self._root_issue if self._plan_member and self._root_issue else issue.issue_number\n        branch = f\"research/issue-{source}\"\n\n        try:\n            if workflow.patched(\"issue-lifecycle-develop-child\"):\n                # Дочерний прогон: у стадии появляется свой WorkflowId, а\n                # значит строка в `workflow list` и след, переживающий её\n                # завершение. Одна попытка на уровне стадии — ретраи живут\n                # внутри, на отдельных шагах.\n                pr_number = await workflow.execute_child_workflow(\n                    IssueDevelopment.run, issue,\n                    id=development_workflow_id(issue.repo, issue.issue_number),\n                    # Прогон агента идёт до 45 минут. Ни continue-as-new\n                    # родителя, ни его завершение не должны его убивать.\n                    parent_close_policy=ParentClosePolicy.ABANDON,\n                    retry_policy=RetryPolicy(maximum_attempts=1),\n                )\n            else:\n                pr_number = await workflow.execute_activity("
        },
        {
          "name": "IssueDevelopment",
          "kind": "class",
          "signature": "class IssueDevelopment:",
          "docstring": "Разработка по подготовленному Issue — дочерний прогон цикла.\n\n    Отдельным воркфлоу, а не активностью, по двум причинам сразу.\n\n    Первая — видимость. Активность внутри родителя не имеет своего\n    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся\n    и следа — операционная история собиралась логами контейнера и `docker ps`.\n\n    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на\n    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл\n    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого\n    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в\n    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.\n\n    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск\n    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает\n    второго агента в тот же рабочий каталог.",
          "start_line": 3540,
          "end_line": 3714,
          "source_excerpt": "class IssueDevelopment:\n    \"\"\"Разработка по подготовленному Issue — дочерний прогон цикла.\n\n    Отдельным воркфлоу, а не активностью, по двум причинам сразу.\n\n    Первая — видимость. Активность внутри родителя не имеет своего\n    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся\n    и следа — операционная история собиралась логами контейнера и `docker ps`.\n\n    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на\n    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл\n    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого\n    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в\n    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.\n\n    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск\n    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает\n    второго агента в тот же рабочий каталог.\n    \"\"\"\n\n    @workflow.run\n    async def run(self, issue: IssueInput) -> int | None:\n        \"\"\"Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.\n        \"\"\"\n        cheap = RetryPolicy(maximum_attempts=3)\n        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и\n        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.\n        once = RetryPolicy(maximum_attempts=1)\n\n        plan = await workflow.execute_activity(\n            activities.dev_begin, issue,\n            start_to_close_timeout=timedelta(seconds=120),\n            retry_policy=cheap,\n        )\n\n        if plan.mode == \"dispatch\":\n            await workflow.execute_activity(\n                activities.dev_dispatch, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=120),\n                retry_policy=cheap,\n            )\n            return None\n\n        number: int | None = None\n        try:\n            # Порядок не косметический: сначала клон и постановка — они\n            # единственные могут не состояться до того, как что-либо сказано\n            # человеку.\n            await workflow.execute_activity(\n                activities.dev_prepare, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_announce, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=60),\n                retry_policy=cheap,\n            )\n            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом\n            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.\n            #\n            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,\n            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена\n            # ревью, revert 80b3291) звала планирование до подготовки —\n            # находка K2, «холодный старт»: стадия падала в каталоге,\n            # которого никто ещё не создал.\n            #\n            # Не позже: план — вход агента, а не отчёт по итогам его работы.\n            #\n            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и\n            # прогоны, начатые до выкладки, обязаны реплеиться прежней\n            # последовательностью, без неё.\n            #\n            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не\n            # результат стадии (`PLAN` не входит в `task_context.required()`\n            # намеренно) — агент штатно работает без него уже сегодня. Топить\n            # дорогой прогон разработки из-за упавшего необязательного шага\n            # значило бы разменивать штатный путь на необязательное ускорение.\n            if workflow.patched(\"issue-lifecycle-develop-plan-stage\"):\n                try:\n                    has_plan = await workflow.execute_activity(\n                        activities.build_mvp_plan, args=[issue, plan.branch],\n                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n                        heartbeat_timeout=timedelta(seconds=300),\n                        retry_policy=once,\n                    )\n                except Exception as e:                    # noqa: BLE001\n                    workflow.logger.warning(\n                        \"план работ не построен: %s\", _failure_reason(e))\n                else:\n                    if not has_plan:\n                        workflow.logger.warning(\n                            \"план работ пуст или не создан — агент продолжит без него\")\n            await workflow.execute_activity(\n                activities.dev_run_agent, issue,\n                start_to_close_timeout=timedelta(seconds=3600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из\n            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на\n            # следующем круге правок агент прочитает свои прошлые находки как новые.\n            await workflow.execute_activity(\n                activities.dev_followups, issue,\n                start_to_close_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_tests, issue,\n                start_to_close_timeout=timedelta(seconds=1800),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            number = await workflow.execute_activity(\n                activities.dev_publish, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),"
        },
        {
          "name": "run",
          "kind": "method",
          "signature": "async def run(self, issue: IssueInput) -> int | None:",
          "docstring": "Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.",
          "start_line": 3561,
          "end_line": 3714,
          "source_excerpt": "    async def run(self, issue: IssueInput) -> int | None:\n        \"\"\"Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.\n        \"\"\"\n        cheap = RetryPolicy(maximum_attempts=3)\n        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и\n        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.\n        once = RetryPolicy(maximum_attempts=1)\n\n        plan = await workflow.execute_activity(\n            activities.dev_begin, issue,\n            start_to_close_timeout=timedelta(seconds=120),\n            retry_policy=cheap,\n        )\n\n        if plan.mode == \"dispatch\":\n            await workflow.execute_activity(\n                activities.dev_dispatch, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=120),\n                retry_policy=cheap,\n            )\n            return None\n\n        number: int | None = None\n        try:\n            # Порядок не косметический: сначала клон и постановка — они\n            # единственные могут не состояться до того, как что-либо сказано\n            # человеку.\n            await workflow.execute_activity(\n                activities.dev_prepare, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_announce, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=60),\n                retry_policy=cheap,\n            )\n            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом\n            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.\n            #\n            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,\n            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена\n            # ревью, revert 80b3291) звала планирование до подготовки —\n            # находка K2, «холодный старт»: стадия падала в каталоге,\n            # которого никто ещё не создал.\n            #\n            # Не позже: план — вход агента, а не отчёт по итогам его работы.\n            #\n            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и\n            # прогоны, начатые до выкладки, обязаны реплеиться прежней\n            # последовательностью, без неё.\n            #\n            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не\n            # результат стадии (`PLAN` не входит в `task_context.required()`\n            # намеренно) — агент штатно работает без него уже сегодня. Топить\n            # дорогой прогон разработки из-за упавшего необязательного шага\n            # значило бы разменивать штатный путь на необязательное ускорение.\n            if workflow.patched(\"issue-lifecycle-develop-plan-stage\"):\n                try:\n                    has_plan = await workflow.execute_activity(\n                        activities.build_mvp_plan, args=[issue, plan.branch],\n                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n                        heartbeat_timeout=timedelta(seconds=300),\n                        retry_policy=once,\n                    )\n                except Exception as e:                    # noqa: BLE001\n                    workflow.logger.warning(\n                        \"план работ не построен: %s\", _failure_reason(e))\n                else:\n                    if not has_plan:\n                        workflow.logger.warning(\n                            \"план работ пуст или не создан — агент продолжит без него\")\n            await workflow.execute_activity(\n                activities.dev_run_agent, issue,\n                start_to_close_timeout=timedelta(seconds=3600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из\n            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на\n            # следующем круге правок агент прочитает свои прошлые находки как новые.\n            await workflow.execute_activity(\n                activities.dev_followups, issue,\n                start_to_close_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_tests, issue,\n                start_to_close_timeout=timedelta(seconds=1800),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            number = await workflow.execute_activity(\n                activities.dev_publish, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n        finally:\n            # Запись об итерации — В FINALLY, а не после успешных шагов.\n            #\n            # Красные тесты и сорвавшийся прогон агента — самые интересные для\n            # разбора исходы, и именно они пропускали запись: исключение из\n            # шага уносило управление мимо неё. Слой собирал статистику только\n            # по удачам и на ней же учился.\n            #\n            # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет\n            # недетерминизмом прогоны, начатые до выкладки, а прогон агента\n            # идёт до 45 минут. Прецедент в этом же файле — реплей без маркера\n            # падает `Timer machine does not handle ActivityTaskScheduled`.\n            if workflow.patched(\"issue-lifecycle-capture-episode-always\"):\n                try:\n                    await workflow.execute_activity(\n                        activities.capture_episode,\n                        args=[issue, plan.branch, number],\n                        start_to_close_timeout=timedelta(seconds=60),\n                        retry_policy=cheap,"
        }
      ]
    },
    {
      "path": "shared/lifecycle.py",
      "title": "File: shared/lifecycle.py",
      "summary": "Модель фаз жизненного цикла Issue — единственный источник правды.",
      "snippet": "CANCELLED}) |\n| `TRANSITIONS` | constant | TRANSITIONS: dict[str, tuple[Transition, ...]] = { |\n| `PHASES` | constant | PHASES: tuple[str, ...] = tuple(TRANSITIONS) |\n| `PHASE_PREFIX` | constant | PH",
      "excerpt": "# shared/lifecycle.py\n\n## Overview\n\nМодель фаз жизненного цикла Issue — единственный источник правды.\n\nСегодня состояние Issue размазано по четырём независимым представлениям (метки,\nпеременные воркфлоу, комментарии, Event History), и ни одно не покрывает путь\nдальше приоритизации. Этот модуль вводит один перечень фаз и одну таблицу\nпереходов; из них выводятся значения query, метки в GitHub, search attribute и\nстроки таймлайна. Иначе каждая подзадача эпика заведёт свои названия, и\nтрассировка будет собирать таймлайн из несовместимых кусков.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как `estimation.py`.\nЛогика состояний проверяется напрямую, а не через прогон воркфлоу.\n\nИменование согласовано с уже внедрёнными словарями: namespace через двоеточие,\nкак `needs-human:*` и `run:*`/`done:*` (протокол агентов v1, задачи #30 и #33).\nФаза в GitHub — метка `phase:<имя>`.\n\nIt exposes 38 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `CREATED` | constant | CREATED = \"created\" |\n| `CLASSIFIED` | constant | CLASSIFIED = \"classified\" |\n| `BUSINESS_ANALYSIS` | constant | BUSINESS_ANALYSIS = \"business-analysis\" |\n| `PRODUCT_RESEARCH` | constant | PRODUCT_RESEARCH = \"product-research\" |\n| `SYSTEM_REQUIREMENTS` | constant | SYSTEM_REQUIREMENTS = \"system-requirements\" |\n| `GROOMED` | constant | GROOMED = \"groomed\" |\n| `READY_FOR_DEV` | constant | READY_FOR_DEV = \"ready-for-dev\" |\n| `IN_DEVELOPMENT` | constant | IN_DEVELOPMENT = \"in-developme",
      "score": 2.564
    },
    {
      "path": "worker/activities.py::trigger_openhands_resolver",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.trigger_openhands_resolver",
      "summary": "Активность Develop: разработка по подготовленному Issue.",
      "snippet": "— номер родительской задачи (если это подзадача плана),\n`branch` — готовая ветка (если вычислена в workflow).\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n40 files impo",
      "excerpt": "# worker.activities.trigger_openhands_resolver\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 3\n\n```\nasync def trigger_openhands_resolver(issue: IssueInput, root_issue: int | None = None, \n                                     branch: str | None = None) -> int | None\n```\n\n## Overview\n\nАктивность Develop: разработка по подготовленному Issue.\n\nДва режима (`shared/develop.py`). `local` — прогон одноразовым контейнером\nна своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает\nв GitHub Actions, для репозиториев без стенда.\n\nВозвращает номер PR (режим `local`) либо None (`dispatch`: результат\nпридёт событием `pr-open`, прогон идёт на чужой стороне).\n\nISSUE-113: для подзадачи плана использует ветку родителя, а не свою.\n`root_issue` — номер родительской задачи (если это подзадача плана),\n`branch` — готовая ветка (если вычислена в workflow).\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n40 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_",
      "score": 1.8
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 1.795
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements constant DEV_TESTS_TIMEOUT_SEC.",
      "score": 4.564
    },
    {
      "file": "worker/workflows.py",
      "why_relevant": "Implements class IssueDevelopment.",
      "score": 4.564
    },
    {
      "file": "shared/lifecycle.py",
      "why_relevant": "Модель фаз жизненного цикла Issue — единственный источник правды..",
      "score": 2.564
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "dev_tests",
      "lines": [
        3509,
        3515
      ],
      "source": "async def dev_tests(issue: IssueInput) -> None:\n    \"\"\"Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.\n    \"\"\"\n    await _run_with_heartbeat(_dev_tests, issue, label=\"dev:tests\")"
    },
    {
      "path": "worker/activities.py",
      "name": "dev_publish",
      "lines": [
        3519,
        3525
      ],
      "source": "async def dev_publish(issue: IssueInput, branch: str) -> int | None:\n    \"\"\"Шаг 6: коммит, пуш и PR — руками воркера, его токеном.\n\n    `None` — агент не изменил ни одного файла. Это не сбой шага, а его\n    результат; решение, что делать с пустым прогоном, принимает воркфлоу.\n    \"\"\"\n    return await _run_with_heartbeat(_dev_publish, issue, branch, label=\"dev:publish\")"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the dev_tests body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 1381.0,
    "hint": "No synthesis, and retrieval was weak. Refine the query with search_codebase rather than reading these files in order.",
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "711-3880",
      "defines": "dev_tests:3509, dev_publish:3519, GateExtraction:94, ClassificationExtraction:99, DuplicateCandidate:104, DuplicateExtraction:110"
    },
    {
      "path": "worker/workflows.py",
      "lines": "1515-3714",
      "defines": "IssueDevelopment:3540, WebhookAudit:307, OrphanAgentEvent:330, CommentAck:351, IssueLifecycle:374, IssuePrFix:3718"
    },
    {
      "path": "shared/lifecycle.py",
      "defines": "Transition:54, InvalidTransition:275, phase_label:284, phase_from_labels:288, is_terminal:302, allowed:306"
    },
    {
      "path": "shared/workflow_types.py",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:116, OrphanEventInput:194"
    },
    {
      "path": "worker/estimation.py",
      "defines": "EstimationError:64, WorkUnit:68, EstimationFacts:74, AppliedRisk:93, AppliedPenalty:101, Estimate:108"
    }
  ]
}

## Ход 4 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Как устроена publish_analysis_partial: где определена, её сигнатура, при каком условии воркфлоу анализа её вызывает (перехват какого исключения), что именно она публикует — ветку, пул-реквест (черновой?), комментарий — и какое состояние/фазу при этом фиксирует? В каком месте воркфлоу анализа она стоит относительно стадий анализа?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `publish_analysis_partial`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    "shared/workflow_types.py",
    "worker/estimation.py",
    "worker/github_client.py",
    "worker/activities.py::publish_analysis_partial"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "t |\n| `publish_analysis` | function | async def publish_analysis(analyze: AnalyzeInput) -> str |\n| `publish_analysis_partial` | function | async def publish_analysis_partial(analyze: AnalyzeInput, rea",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 136 public symbols and depends on 23 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `github_client` | variable | github_client = forge |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_cl",
      "score": 7.074,
      "key_symbols": [
        {
          "name": "publish_analysis",
          "kind": "function",
          "signature": "async def publish_analysis(analyze: AnalyzeInput) -> str:",
          "docstring": "Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.",
          "start_line": 2529,
          "end_line": 2546,
          "source_excerpt": "async def publish_analysis(analyze: AnalyzeInput) -> str:\n    \"\"\"Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.\"\"\"\n    clone_dir = _require_workspace(analyze, None)\n    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)\n    if not files:\n        raise RuntimeError(\"пайплайн не произвёл ни одного артефакта\")\n    branch = f\"research/issue-{analyze.issue_number}\"\n    await asyncio.to_thread(\n        github_client.push_artifacts_to_branch,\n        analyze.repo, branch, files,\n        f\"docs(sa): анализ issue #{analyze.issue_number} через SA-helper\",\n    )\n    await asyncio.to_thread(\n        github_client.post_comment,\n        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),\n    )\n    return branch"
        },
        {
          "name": "publish_analysis_partial",
          "kind": "function",
          "signature": "async def publish_analysis_partial(analyze: AnalyzeInput, reason: str) -> list[str]:",
          "docstring": "Сорванный анализ отдаёт то, что успел собрать — как и БФТ.\n\n    Цепочка FNR стоит тех же денег и рвётся по тем же причинам: лимит\n    провайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу:\n    артефакты жили в каталоге, который `cleanup_workspace` снимал на любом\n    исходе, а публикация случалась только после последней стадии.\n\n    Возвращает имена уцелевших артефактов: воркфлоу называет их человеку, а\n    следующий `/analyze` по ним понимает, какие стадии можно не повторять.",
          "start_line": 2550,
          "end_line": 2590,
          "source_excerpt": "async def publish_analysis_partial(analyze: AnalyzeInput, reason: str) -> list[str]:\n    \"\"\"Сорванный анализ отдаёт то, что успел собрать — как и БФТ.\n\n    Цепочка FNR стоит тех же денег и рвётся по тем же причинам: лимит\n    провайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу:\n    артефакты жили в каталоге, который `cleanup_workspace` снимал на любом\n    исходе, а публикация случалась только после последней стадии.\n\n    Возвращает имена уцелевших артефактов: воркфлоу называет их человеку, а\n    следующий `/analyze` по ним понимает, какие стадии можно не повторять.\n    \"\"\"\n    clone_dir = _workspace_dir(analyze) / \"repo\"\n    if not clone_dir.is_dir():\n        logger.warning(\"FNR %s#%s: каталог уже снят — публиковать нечего\",\n                       analyze.repo, analyze.issue_number)\n        return []\n    files = await asyncio.to_thread(_collect_fnr_artifacts, str(clone_dir))\n    if not files:\n        return []\n    branch = f\"research/issue-{analyze.issue_number}\"\n    await asyncio.to_thread(\n        github_client.push_artifacts_to_branch,\n        analyze.repo, branch, files,\n        f\"docs(sa): частичный анализ issue #{analyze.issue_number}\",\n    )\n    session_id, session_branch = await asyncio.to_thread(_entire_session, str(clone_dir))\n    await asyncio.to_thread(_push_entire_branch, analyze.repo, str(clone_dir),\n                            session_branch)\n    links = \"\\n\".join(\n        f\"- [`{path.rsplit('/', 1)[-1]}`]\"\n        f\"(https://github.com/{analyze.repo}/blob/{branch}/{path})\"\n        for path in sorted(files))\n    await asyncio.to_thread(\n        github_client.post_comment, analyze.repo, analyze.issue_number,\n        f\"## ⏸ Анализ собран частично\\n\\nПрогон оборвался: {reason}\\n\\n\"\n        f\"Что успели — в ветке `{branch}`:\\n\\n{links}\\n\\n\"\n        \"Работа не потеряна: повторный `/analyze` поднимет эту ветку и продолжит \"\n        \"с места обрыва — готовые стадии заново не считаются.\"\n        + bft.render_session_hint(analyze.repo, session_id, session_branch),\n    )\n    return sorted(files)"
        },
        {
          "name": "_publish_dev_dialog_sync",
          "kind": "function",
          "signature": "def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:",
          "docstring": "Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.\n\n    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе\n    разбор начнут не с того места.",
          "start_line": 3226,
          "end_line": 3249
        },
        {
          "name": "_dev_publish",
          "kind": "function",
          "signature": "def _dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Коммит, пуш и PR — руками воркера, его токеном.\n\n    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен\n    контуру. Возвращает номер PR либо None, если агент ничего не изменил.",
          "start_line": 3282,
          "end_line": 3321
        },
        {
          "name": "dev_publish",
          "kind": "function",
          "signature": "async def dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Шаг 6: коммит, пуш и PR — руками воркера, его токеном.\n\n    `None` — агент не изменил ни одного файла. Это не сбой шага, а его\n    результат; решение, что делать с пустым прогоном, принимает воркфлоу.",
          "start_line": 3519,
          "end_line": 3525
        },
        {
          "name": "publish_decomposition",
          "kind": "function",
          "signature": "def publish_decomposition(issue: IssueInput, plan: dict, branch: str) -> list[int]:",
          "docstring": "Создаёт подзадачи и публикует план в родителе.\n\n    Порядок важен: сначала все подзадачи, потом сводка. Сводка ссылается на\n    номера, которых до создания не существует, а план с битыми ссылками хуже\n    отсутствующего — по нему пойдут и упрутся.\n\n    Зависимости проставляются вторым проходом по той же причине: подзадача\n    может зависеть от той, что создаётся позже.",
          "start_line": 3842,
          "end_line": 3880
        },
        {
          "name": "publish_analysis_error",
          "kind": "function",
          "signature": "async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:",
          "docstring": "Не молчать при провале: прогон дорогой и долгий, тихое падение\n    неотличимо от «ещё работает».",
          "start_line": 4075,
          "end_line": 4090,
          "source_excerpt": "async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:\n    \"\"\"Не молчать при провале: прогон дорогой и долгий, тихое падение\n    неотличимо от «ещё работает».\"\"\"\n    exc_type, _, message = reason.partition(\": \")\n    event_id = await asyncio.to_thread(\n        sentry_setup.capture_analysis_failure,\n        analyze, exc_type or \"unknown\", message or reason)\n    await asyncio.to_thread(\n        github_client.post_comment,\n        analyze.repo,\n        analyze.issue_number,\n        f\"⚠️ Автономный анализ не удался: {reason}\\n\\n\"\n        \"Прогон не повторяется автоматически (он недетерминирован и дорог). \"\n        \"Запустить заново — командой `/analyze`.\"\n        + sentry_setup.debug_reference(event_id),\n    )"
        },
        {
          "name": "publish_bft_deep",
          "kind": "function",
          "signature": "async def publish_bft_deep(req: BftRequest) -> str:",
          "docstring": "Финал глубокого прогона: артефакты в ветку, сводка комментарием.",
          "start_line": 4821,
          "end_line": 4841
        },
        {
          "name": "publish_bft_partial",
          "kind": "function",
          "signature": "async def publish_bft_partial(req: BftRequest, reason: str) -> list[str]:",
          "docstring": "Сорванный прогон отдаёт то, что успел собрать.\n\n    Прогон срывается не только от ошибок в коде: провайдер отвечает 524, кончается\n    лимит запросов, стенд передеплоивают посреди работы. Раньше это стоило всей\n    работы — артефакты жили в каталоге, который `cleanup` стирал на любом исходе,\n    и повтор начинался с нуля, заново оплачивая уже пройденные стадии.\n\n    Возвращает список стадий, чьи артефакты уже готовы: воркфлоу называет их\n    человеку, а следующий `/bft-deep` по ним же понимает, с чего продолжать.\n    Пустой результат — не ошибка: сорваться могло и на первой стадии.",
          "start_line": 4852,
          "end_line": 4891
        },
        {
          "name": "publish_bft_error",
          "kind": "function",
          "signature": "async def publish_bft_error(req: BftRequest, reason: str) -> None:",
          "docstring": "Не молчать при сбое — требование постановки, а не вежливость.\n\n    Молчащий сбой неотличим от «ещё думает»: человек ждёт БФТ, которого уже не\n    будет, и узнаёт об этом, только когда сам придёт спрашивать.",
          "start_line": 4895,
          "end_line": 4907
        }
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 3.552,
      "key_symbols": [
        {
          "name": "IssueInput",
          "kind": "class",
          "signature": "class IssueInput:",
          "docstring": "",
          "start_line": 6,
          "end_line": 13
        },
        {
          "name": "UserComment",
          "kind": "class",
          "signature": "class UserComment:",
          "docstring": "Реплика человека в Issue, доехавшая до цикла сигналом.\n\n    Отдельный тип, а не строка с префиксом: вместе с текстом обязан ехать ключ\n    комментария. Вебхук доставляет каждое событие ДВАЖДЫ (в истории прогона по\n    `poh-demo-checkout#42` сигналов ровно вдвое), и без ключа один вопрос\n    человека получал бы два ответа.\n\n    `comment_id is None` — реплика от вебхука прежнего поколения, который слал\n    сигнал одним аргументом. Такую отвечаем без защиты от повтора: молчание\n    хуже возможного дубля.",
          "start_line": 17,
          "end_line": 30
        },
        {
          "name": "WebhookAuditInput",
          "kind": "class",
          "signature": "class WebhookAuditInput:",
          "docstring": "След доставки, отброшенной вебхуком по конфигу.\n\n    Существует только ради видимости: workflow с таким входом — единственный\n    способ узнать, что событие приходило и было отклонено (GitHub получает 200,\n    ничего другого не остаётся).",
          "start_line": 34,
          "end_line": 46
        },
        {
          "name": "Deadlines",
          "kind": "class",
          "signature": "class Deadlines:",
          "docstring": "Сроки ожиданий (правило R3: каждая парковка имеет дедлайн).\n\n    Едут в воркфлоу отдельной activity, а не читаются из окружения прямо в\n    коде воркфлоу: результат activity лежит в истории, поэтому реплей после\n    смены конфигурации возьмёт то же значение, что и первый прогон. Прочитай\n    воркфлоу os.environ напрямую — изменённая переменная дала бы другой таймер\n    при воспроизведении и уронила бы прогон недетерминизмом.",
          "start_line": 50,
          "end_line": 112
        }
      ]
    },
    {
      "path": "worker/estimation.py",
      "title": "File: worker/estimation.py",
      "summary": "Детерминированный расчёт оценки задачи.",
      "snippet": "Детерминированный расчёт оценки задачи.",
      "excerpt": "# worker/estimation.py\n\n## Overview\n\nДетерминированный расчёт оценки задачи.\n\nЧистый модуль: ни сети, ни LLM, ни Temporal. Модель отдаёт только факты\n(EstimationFacts), а коэффициенты, надбавки, PERT, cross-check и коридоры\nсчитаются здесь по config/estimation-rules.toml. Тот же принцип, что уже\nработает в score_priority: модель извлекает, код считает — иначе одна и та\nже задача давала бы разные числа от прогона к прогону.\n\nПоля «итоговая оценка» в схеме фактов нет намеренно: модель структурно не\nможет вернуть готовое число в обход расчёта.\n\nIt exposes 15 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `RULES_PATH` | constant | RULES_PATH = Path(\"/app/config/estimation-rules.toml\") |\n| `WORK_TYPE_RU` | constant | WORK_TYPE_RU = { |\n| `ARTIFACT_TYPE_RU` | constant | ARTIFACT_TYPE_RU = { |\n| `RISK_LABELS` | constant | RISK_LABELS = { |\n| `PENALTY_LABELS` | constant | PENALTY_LABELS = { |\n| `CONFIDENCE_RU` | constant | CONFIDENCE_RU = {\"high\": \"высокая\", \"medium\": \"средняя\", \"low\": \"низкая\"} |\n| `EstimationError` | class | class EstimationError |\n| `WorkUnit` | class | class WorkUnit |\n| `EstimationFacts` | class | class EstimationFacts |\n| `AppliedRisk` | class | class AppliedRisk |\n| `AppliedPenalty` | class | class AppliedPenalty |\n| `Estimate` | class | class Estimate |\n| `load_rules` | function | def load_rules(path: Path = RULES_PATH) -> dict |\n| `positive_units` | function | def positive_units(facts: EstimationFacts) -> list[WorkUnit] |",
      "score": 3.552
    },
    {
      "path": "worker/github_client.py",
      "title": "File: worker/github_client.py",
      "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час).",
      "snippet": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужн",
      "excerpt": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\nIt exposes 34 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `add_label` | function | def add_label(repo: str, issue_number: int, label: str) -> None |\n| `remove_label` | function | def remove_label(repo: str, issue_number: int, label: str) -> None |\n| `set_labels` | function | def set_labels(repo: str, issue_number: int, *, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None |\n| `ensure_labels_exist` | function | def ensure_labels_exist(repo: str, specs) -> int |\n| `create_issue` | function | def create_issue(repo: str, title: str, body: str, labels: list[str] \\| None = None) -> int |\n| `issue_node_id` | function | def issue_node_id(repo: str, issue_number: int) -> int |\n| `link_sub_issue` | function | def link_sub_issue(repo: str, parent: int, child_id: int) -> None |\n| `list_sub_issues` | function | def list_sub_issues(repo: str, parent: int) -> list[dict] |\n| `close_issue` | function | def close_issue(repo: str, issue_number: int) -> None |\n| `search_candidates` | function | def search_candidates(repo: str, q",
      "score": 3.552
    },
    {
      "path": "worker/activities.py::publish_analysis_partial",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.publish_analysis_partial",
      "summary": "Сорванный анализ отдаёт то, что успел собрать — как и БФТ.",
      "snippet": "# worker.activities.publish_analysis_partial\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 3\n\n```\nasync def publish_analysis_partial(analyze: Analyze",
      "excerpt": "# worker.activities.publish_analysis_partial\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 3\n\n```\nasync def publish_analysis_partial(analyze: AnalyzeInput, reason: str) -> list[str]\n```\n\n## Overview\n\nСорванный анализ отдаёт то, что успел собрать — как и БФТ.\n\nЦепочка FNR стоит тех же денег и рвётся по тем же причинам: лимит\nпровайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу:\nартефакты жили в каталоге, который `cleanup_workspace` снимал на любом\nисходе, а публикация случалась только после последней стадии.\n\nВозвращает имена уцелевших артефактов: воркфлоу называет их человеку, а\nследующий `/analyze` по ним понимает, какие стадии можно не повторять.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n47 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_acceptance_proposal.py`\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_answer_question.py`\n- `tests/test_ask_question.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_empty_run.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_dev_task_ass",
      "score": 3.0
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements function publish_analysis_partial.",
      "score": 7.074
    },
    {
      "file": "shared/workflow_types.py",
      "why_relevant": "`shared/workflow_types.py` is a python source file in the Utility layer..",
      "score": 3.552
    },
    {
      "file": "worker/estimation.py",
      "why_relevant": "Детерминированный расчёт оценки задачи..",
      "score": 3.552
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "publish_analysis_partial",
      "lines": [
        2550,
        2590
      ],
      "source": "async def publish_analysis_partial(analyze: AnalyzeInput, reason: str) -> list[str]:\n    \"\"\"Сорванный анализ отдаёт то, что успел собрать — как и БФТ.\n\n    Цепочка FNR стоит тех же денег и рвётся по тем же причинам: лимит\n    провайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу:\n    артефакты жили в каталоге, который `cleanup_workspace` снимал на любом\n    исходе, а публикация случалась только после последней стадии.\n\n    Возвращает имена уцелевших артефактов: воркфлоу называет их человеку, а\n    следующий `/analyze` по ним понимает, какие стадии можно не повторять.\n    \"\"\"\n    clone_dir = _workspace_dir(analyze) / \"repo\"\n    if not clone_dir.is_dir():\n        logger.warning(\"FNR %s#%s: каталог уже снят — публиковать нечего\",\n                       analyze.repo, analyze.issue_number)\n        return []\n    files = await asyncio.to_thread(_collect_fnr_artifacts, str(clone_dir))\n    if not files:\n        return []\n    branch = f\"research/issue-{analyze.issue_number}\"\n    await asyncio.to_thread(\n        github_client.push_artifacts_to_branch,\n        analyze.repo, branch, files,\n        f\"docs(sa): частичный анализ issue #{analyze.issue_number}\",\n    )\n    session_id, session_branch = await asyncio.to_thread(_entire_session, str(clone_dir))\n    await asyncio.to_thread(_push_entire_branch, analyze.repo, str(clone_dir),\n                            session_branch)\n    links = \"\\n\".join(\n        f\"- [`{path.rsplit('/', 1)[-1]}`]\"\n        f\"(https://github.com/{analyze.repo}/blob/{branch}/{path})\"\n        for path in sorted(files))\n    await asyncio.to_thread(\n        github_client.post_comment, analyze.repo, analyze.issue_number,\n        f\"## ⏸ Анализ собран частично\\n\\nПрогон оборвался: {reason}\\n\\n\"\n        f\"Что успели — в ветке `{branch}`:\\n\\n{links}\\n\\n\"\n        \"Работа не потеряна: повторный `/analyze` поднимет эту ветку и продолжит \"\n        \"с места обрыва — готовые стадии заново не считаются.\"\n        + bft.render_session_hint(analyze.repo, session_id, session_branch),\n    )\n    return sorted(files)"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the publish_analysis_partial body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 835.9,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "2529-4907",
      "defines": "publish_analysis_partial:2550, GateExtraction:94, ClassificationExtraction:99, DuplicateCandidate:104, DuplicateExtraction:110, PriorityExtraction:114"
    },
    {
      "path": "shared/workflow_types.py",
      "lines": "6-112",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:116, OrphanEventInput:194"
    },
    {
      "path": "worker/estimation.py",
      "defines": "EstimationError:64, WorkUnit:68, EstimationFacts:74, AppliedRisk:93, AppliedPenalty:101, Estimate:108"
    },
    {
      "path": "worker/github_client.py",
      "defines": "GitCommandError:620, post_comment:130, add_label:153, remove_label:160, set_labels:179, ensure_labels_exist:226"
    },
    {
      "path": "worker/worker.py",
      "defines": "main:126, DEVELOP_ACTIVITIES:44"
    }
  ]
}

## Ход 5 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Что делает github_client.publish_worktree — полная сигнатура и поведение: коммитит ли сам, создаёт ли ветку, открывает ли пул-реквест, поддерживает ли черновой (draft) PR? Какие ещё методы клиента создают пул-реквесты или ветки (create_pull_request, push_artifacts_to_branch) и какие параметры они принимают?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `push_artifacts_to_branch`, `publish_worktree`, read from the current checkout, cut at the line cap where noted; see `continuation`. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/github_client.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/github_client.py",
    "worker/gitlab_client.py",
    "shared/workflow_types.py",
    "worker/activities.py",
    "shared/agent_comment.py"
  ],
  "retrieval": [
    {
      "path": "worker/github_client.py",
      "title": "File: worker/github_client.py",
      "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час).",
      "snippet": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется",
      "excerpt": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\nIt exposes 34 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `add_label` | function | def add_label(repo: str, issue_number: int, label: str) -> None |\n| `remove_label` | function | def remove_label(repo: str, issue_number: int, label: str) -> None |\n| `set_labels` | function | def set_labels(repo: str, issue_number: int, *, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None |\n| `ensure_labels_exist` | function | def ensure_labels_exist(repo: str, specs) -> int |\n| `create_issue` | function | def create_issue(repo: str, title: str, body: str, labels: list[str] \\| None = None) -> int |\n| `issue_node_id` | function | def issue_node_id(repo: str, issue_number: int) -> int |\n| `link_sub_issue` | function | def link_sub_issue(repo: str, parent: int, child_id: int) -> None |\n| `list_sub_issues` | function | def list_sub_issues(repo: str, parent: int) -> list[dict] |\n| `close_issue` | function | def close_issue(repo: str, issue_number: int) -> None |\n| `search_candidates` | function | def search_candidates(repo: str, q",
      "score": 5.12,
      "key_symbols": [
        {
          "name": "_log",
          "kind": "variable",
          "signature": "_log = logging.getLogger(\"github_client\")",
          "docstring": "",
          "start_line": 23,
          "end_line": 23
        },
        {
          "name": "_app_private_key",
          "kind": "function",
          "signature": "def _app_private_key() -> bytes:",
          "docstring": "Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла\n    GITHUB_PRIVATE_KEY_PATH (обратная совместимость).",
          "start_line": 38,
          "end_line": 45
        },
        {
          "name": "_installation_token_for",
          "kind": "function",
          "signature": "def _installation_token_for(repo: str) -> str:",
          "docstring": "Installation-токен под установку App на данный репозиторий. Установка\n    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →\n    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.\n\n    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому\n    cache-hit по одному репо не блокируется за token-обменом другого. Lock\n    сериализует только сам обмен (редкий — раз в ~55 мин на репо).",
          "start_line": 61,
          "end_line": 89
        },
        {
          "name": "_auth_headers",
          "kind": "function",
          "signature": "def _auth_headers(repo: str) -> dict:",
          "docstring": "PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.",
          "start_line": 119,
          "end_line": 127
        },
        {
          "name": "create_issue",
          "kind": "function",
          "signature": "def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:",
          "docstring": "Создаёт Issue и возвращает его номер.\n\n    Нужно живому E2E: проверка контура начинается с появления задачи, а\n    подкладывать её руками — значит проверять не тот путь. В обычном пайплайне\n    сервис Issue не создаёт (их заводит человек либо PR-Closer).",
          "start_line": 269,
          "end_line": 285,
          "source_excerpt": "def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    \"\"\"Создаёт Issue и возвращает его номер.\n\n    Нужно живому E2E: проверка контура начинается с появления задачи, а\n    подкладывать её руками — значит проверять не тот путь. В обычном пайплайне\n    сервис Issue не создаёт (их заводит человек либо PR-Closer).\n    \"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] create issue %s: %s\", repo, title)\n        return 0\n    url = f\"https://api.github.com/repos/{repo}/issues\"\n    payload: dict = {\"title\": title, \"body\": body}\n    if labels:\n        payload[\"labels\"] = labels\n    resp = requests.post(url, headers=_auth_headers(repo), json=payload, timeout=30)\n    resp.raise_for_status()\n    return resp.json()[\"number\"]"
        },
        {
          "name": "push_artifacts_to_branch",
          "kind": "function",
          "signature": "def push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:",
          "docstring": "Публикует артефакты (путь -> содержимое) в ветку одним проходом.",
          "start_line": 455,
          "end_line": 463,
          "source_excerpt": "def push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] push %s files to %s#%s: %s\",\n                  len(files), repo, branch, sorted(files))\n        return\n    ensure_branch(repo, branch)\n    for path, content in files.items():\n        put_file(repo, branch, path, content, message)"
        },
        {
          "name": "create_pr_with_files",
          "kind": "function",
          "signature": "def create_pr_with_files(repo: str, branch: str, base: str, files: dict, title: str, body: str):",
          "docstring": "",
          "start_line": 536,
          "end_line": 569
        },
        {
          "name": "publish_worktree",
          "kind": "function",
          "signature": "def publish_worktree(repo: str, clone_dir: str, branch: str, *, title: str, body: str, message: str, ignore_for_empty_check: tuple[str, ...] = (), force_include: tuple[str, ...] = ()) -> int | None:",
          "docstring": "Коммит рабочего дерева в ветку и PR. None — изменений нет.\n\n    Делает это ВОРКЕР, а не агент разработки: агенту токен не давали намеренно,\n    он исполняет код чужого репозитория. Здесь токен уже нужен не агенту, а\n    контуру — и живёт он ровно в этом процессе.\n\n    Токен идёт через credential.helper в env, а не в URL: argv команды целиком\n    попадает в текст CalledProcessError, и вклеенный токен уехал бы в историю\n    Temporal при первом же сбое пуша.\n\n    `ignore_for_empty_check` — пути (git pathspec, например `\".harness/**\"`),\n    которые не учитываются при решении «есть ли изменения». Они по-прежнему\n    попадают в сам коммит через `git add -A` ниже — исключаются только из\n    ПРОВЕРКИ пустоты. Нужно вызывающему, который пишет в рабочее дерево\n    каталог, обязанный дойти до PR независимо от того, менял ли агент код: без\n    исключения такой каталог сам по себе выглядел бы диффом, и «агент ничего\n    не изменил» перестало бы обнаруживаться.\n\n    `force_include` — пути (без pathspec-магии, например `\".harness\"`),\n    которые обязаны попасть в коммит НЕЗАВИСИМО от `.gitignore` целевого\n    репозитория (M3, ревью задачи 7). Голый `git add -A` молча пропускает\n    путь, который репозиторий игнорирует: проверка пустоты (уже не\n    учитывающая этот путь через `ignore_for_empty_check`) видит только код\n    агента, коммит и PR проходят — а каталог контекста теряется без единого\n    предупреждения. `git add -f` ниже обходит `.gitignore`; после решения о\n    коммите факт присутствия в дереве HEAD подтверждается ЗАНОВО\n    (`_missing_from_tree`) — замыслом («мы же вызвали add -f») здесь не\n    обойтись, потому что путь может остаться только в индексе, если решение\n    «коммитить или нет» приняло его не в расчёт (см. ветку `forced_pending`\n    ниже).",
          "start_line": 674,
          "end_line": 826,
          "source_excerpt": "def publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str,\n                     ignore_for_empty_check: tuple[str, ...] = (),\n                     force_include: tuple[str, ...] = ()) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n\n    Делает это ВОРКЕР, а не агент разработки: агенту токен не давали намеренно,\n    он исполняет код чужого репозитория. Здесь токен уже нужен не агенту, а\n    контуру — и живёт он ровно в этом процессе.\n\n    Токен идёт через credential.helper в env, а не в URL: argv команды целиком\n    попадает в текст CalledProcessError, и вклеенный токен уехал бы в историю\n    Temporal при первом же сбое пуша.\n\n    `ignore_for_empty_check` — пути (git pathspec, например `\".harness/**\"`),\n    которые не учитываются при решении «есть ли изменения». Они по-прежнему\n    попадают в сам коммит через `git add -A` ниже — исключаются только из\n    ПРОВЕРКИ пустоты. Нужно вызывающему, который пишет в рабочее дерево\n    каталог, обязанный дойти до PR независимо от того, менял ли агент код: без\n    исключения такой каталог сам по себе выглядел бы диффом, и «агент ничего\n    не изменил» перестало бы обнаруживаться.\n\n    `force_include` — пути (без pathspec-магии, например `\".harness\"`),\n    которые обязаны попасть в коммит НЕЗАВИСИМО от `.gitignore` целевого\n    репозитория (M3, ревью задачи 7). Голый `git add -A` молча пропускает\n    путь, который репозиторий игнорирует: проверка пустоты (уже не\n    учитывающая этот путь через `ignore_for_empty_check`) видит только код\n    агента, коммит и PR проходят — а каталог контекста теряется без единого\n    предупреждения. `git add -f` ниже обходит `.gitignore`; после решения о\n    коммите факт присутствия в дереве HEAD подтверждается ЗАНОВО\n    (`_missing_from_tree`) — замыслом («мы же вызвали add -f») здесь не\n    обойтись, потому что путь может остаться только в индексе, если решение\n    «коммитить или нет» приняло его не в расчёт (см. ветку `forced_pending`\n    ниже).\n    \"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] publish %s -> %s: %s\", clone_dir, branch, title)\n        return None\n\n    token = auth_token(repo)\n    env = {\n        **os.environ,\n        \"GIT_CONFIG_COUNT\": \"4\",\n        \"GIT_CONFIG_KEY_0\": \"credential.helper\",\n        \"GIT_CONFIG_VALUE_0\": \"!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f\",\n        \"GIT_CONFIG_KEY_1\": \"user.name\",\n        \"GIT_CONFIG_VALUE_1\": \"openhands-agent\",\n        \"GIT_CONFIG_KEY_2\": \"user.email\",\n        \"GIT_CONFIG_VALUE_2\": \"openhands-agent@users.noreply.github.com\",\n        # Каталог задачи передан раннеру (uid 10001), а коммит и пуш делает воркер\n        # от root. Git на такое отвечает `fatal: detected dubious ownership` и\n        # отказывается работать — готовая работа агента не доехала бы до PR.\n        # Объявляем каталог доверенным для этой команды, не трогая общий конфиг.\n        \"GIT_CONFIG_KEY_3\": \"safe.directory\",\n        \"GIT_CONFIG_VALUE_3\": clone_dir,\n        \"GH_PUSH_TOKEN\": token,\n    }\n\n    git = _git_runner(clone_dir, env)\n\n    # ДО checkout: ветка уже существует ЛОКАЛЬНО только если по этому же\n    # clone_dir сюда уже заходил предыдущий вызов этой функции. `dev_prepare`\n    # клонирует репозиторий заново на каждый прогон СТАДИИ (а не на каждую\n    # попытку публикации), поэтому в пределах ретраев `dev_publish` рабочее\n    # дерево — то же самое: если ветка уже есть, коммит на ней, скорее всего,\n    # уже сделан прошлой попыткой, и упал только пуш (или сам PR). На старом\n    # линейном пути (`trigger_openhands_resolver`, ретраев нет) `dev_prepare`\n    # отрабатывает заново при каждом вызове — там ветки здесь никогда не будет,\n    # и поведение не меняется.\n    branch_existed = git(\"show-ref\", \"--verify\", \"--quiet\", f\"refs/heads/{branch}\",\n                         check=False).returncode == 0\n\n    git(\"checkout\", \"-B\", branch)\n    git(\"add\", \"-A\")\n    for path in force_include:\n        # -f обходит .gitignore целевого репозитория: без него `add -A` выше\n        # молча пропускает путь, который репозиторий игнорирует (M3).\n        git(\"add\", \"-f\", \"--\", path)\n    # Пустой ИНДЕКС — не то же самое, что «агент ничего не менял»: если ветка\n    # уже существовала до этого вызова, значит, коммит уехал в прошлой попытке,\n    # а сорвался только пуш (или создание PR) — публикацию нужно довести, а не\n    # объявлять «нет диффа». Пустой коммит по-прежнему не делаем: PR без диффа\n    # ревьюить нечего, а фаза задачи от него сдвинулась бы как от настоящей\n    # работы — это по-прежнему верно для ПЕРВОЙ попытки на новой ветке.\n    #\n    # Проверка идёт БЕЗ путей из `ignore_for_empty_check` (git pathspec\n    # `:(exclude)...`) — сам коммит их всё равно заберёт, `git add -A` выше\n    # уже отработал по всему дереву.\n    diff_args = [\"diff\", \"--cached\", \"--quiet\", \"--\", \".\"]\n    diff_args += [f\":(exclude){pattern}\" for pattern in ignore_for_empty_check]\n    visible_diff = git(*diff_args, check=False).returncode != 0\n\n    # M3: `force_include` может внести изменение, которого «видимый» дифф не\n    # видит (он же его специально исключает через `ignore_for_empty_check`) —\n    # например, .harness/ не попал в САМЫЙ ПЕРВЫЙ коммит на этой ветке (был\n    # проигнорирован .gitignore до этой правки или иным путём), а рабочее\n    # дерево на ретрае больше не менялось. Не заметить такое pending-изменение\n    # значило бы никогда его не закоммитить: индекс не хранится между\n    # вызовами дольше жизни рабочего дерева.\n    #\n    # Гейт на `branch_existed` обязателен: на СОВЕРШЕННО НОВОЙ ветке\n    # force_include-путь «новый» ВСЕГДА (только что собран `_dev_prepare`,\n    # разница с базовым коммитом гарантирована) — без гейта пустой прогон\n    # (агент не менял код, есть только `.harness/`) считался бы правкой при\n    # КАЖДОМ вызове, и это ровно тот регресс M1/H1, ради которого\n    # `ignore_for_empty_check` вообще существует. На РЕТРАЕ существующей\n    # ветки предыдущий коммит — это факт, а не свежая сборка, и его нехватку\n    # (гитигнор, старая версия кода) нужно чинить именно здесь.\n    forced_pending = branch_existed and bool(force_include) and git(\n        \"diff\", \"--cached\", \"--quiet\", \"--\", *force_include, check=False\n    ).returncode != 0\n\n    if visible_diff or forced_pending:\n        git(\"commit\", \"-m\", message, \"-m\",\n            \"Автор изменений — OpenHands, запущен активностью Develop.\")\n    elif not branch_existed:\n        _log.warning(\"%s: агент не изменил ни одного файла\", repo)\n        return None\n\n    # Подтверждаем ФАКТОМ, а не замыслом вызова `add -f` выше (M3): проверяем\n    # дерево HEAD — то, что вот-вот уйдёт в push, — а не полагаемся на то, что"
        },
        {
          "name": "list_pull_request_comments",
          "kind": "function",
          "signature": "def list_pull_request_comments(repo: str, pull_number: int, limit: int = 50) -> list[dict]:",
          "docstring": "Список построчных комментариев PR с привязкой к коммитам.\n\n    Возвращает список построчных комментариев с полями id, user, body, \n    created_at, commit_id, path. Используется для определения свежести \n    ревью по commit_id.",
          "start_line": 868,
          "end_line": 880,
          "source_excerpt": "def list_pull_request_comments(repo: str, pull_number: int, limit: int = 50) -> list[dict]:\n    \"\"\"Список построчных комментариев PR с привязкой к коммитам.\n\n    Возвращает список построчных комментариев с полями id, user, body, \n    created_at, commit_id, path. Используется для определения свежести \n    ревью по commit_id.\n    \"\"\"\n    url = f\"https://api.github.com/repos/{repo}/pulls/{pull_number}/comments\"\n    resp = requests.get(\n        url, headers=_auth_headers(repo), params={\"per_page\": min(limit, 100)}, timeout=30\n    )\n    resp.raise_for_status()\n    return resp.json()[:limit]"
        },
        {
          "name": "push_fixes",
          "kind": "function",
          "signature": "def push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:",
          "docstring": "Коммит правок в ветку PR. False — агент ничего не изменил.\n\n    Пустой коммит не делаем: он выглядел бы как круг работы и заставил бы\n    ревьюера смотреть на PR заново без единой правки.",
          "start_line": 931,
          "end_line": 963
        }
      ]
    },
    {
      "path": "worker/gitlab_client.py",
      "title": "File: worker/gitlab_client.py",
      "summary": "Клиент GitLab: та же поверхность, что у `github_client`.",
      "snippet": "# worker/gitlab_client.py\n\n## Overview\n\nКлиент GitLab: та же поверхность, что у `github_client`.\n\nИмена и сигнатуры повторяют GitHub-клиент намеренно — activities не должны\nзнать, с каким провайдером",
      "excerpt": "# worker/gitlab_client.py\n\n## Overview\n\nКлиент GitLab: та же поверхность, что у `github_client`.\n\nИмена и сигнатуры повторяют GitHub-клиент намеренно — activities не должны\nзнать, с каким провайдером работают. Различие живёт здесь.\n\nЧего у GitLab нет и как это восполняется:\n\n* **Аналога GitHub App.** Токен статический, из окружения. Короткоживущих\n  installation-токенов не существует ни в одном документированном механизме.\n* **Timeline API с событием `cross-referenced`.** Связь задачи и MR\n  пересобирается из `related_merge_requests`, `closed_by` и системных нот.\n* **Сущности Review с состояниями.** У GitLab это approvals (бинарно) и\n  заметки (текст) — два независимых механизма.\n* **Поля `user.type`.** Ботов различаем по логину сервисного аккаунта.\n* **`workflow_dispatch`.** Не реализуется: решением дизайна стадия разработки\n  для GitLab идёт локальным раннером.\n\nПути проекта URL-кодируются целиком, включая слэши: у GitLab проект может\nлежать во вложенной подгруппе, и `group/sub/project` в пути API — это\n`group%2Fsub%2Fproject`.\n\nIt exposes 31 public symbols and depends on 1 other file.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BASE` | constant | BASE = os.environ.get(\"GITLAB_URL\", \"https://gitlab.com\").rstrip(\"/\") + \"/api/v4\" |\n| `TIMEOUT` | constant | TIMEOUT = 30 |\n| `bot_login` | function | def bot_login() -> str |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `list_comments` | function | de",
      "score": 3.584,
      "key_symbols": [
        {
          "name": "_request",
          "kind": "function",
          "signature": "def _request(method: str, url: str, **kwargs):",
          "docstring": "",
          "start_line": 76,
          "end_line": 83,
          "source_excerpt": "def _request(method: str, url: str, **kwargs):\n    kwargs.setdefault(\"timeout\", TIMEOUT)\n    kwargs.setdefault(\"headers\", _headers())\n    resp = requests.request(method, url, **kwargs)\n    if resp.status_code == 429:\n        retry = resp.headers.get(\"Retry-After\") or resp.headers.get(\"RateLimit-Reset\") or \"?\"\n        raise RuntimeError(f\"429 от GitLab, Retry-After={retry}\")\n    return resp"
        },
        {
          "name": "create_issue",
          "kind": "function",
          "signature": "def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:",
          "docstring": "",
          "start_line": 257,
          "end_line": 265,
          "source_excerpt": "def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    if _dry_run():\n        _log.info(\"[DRY_RUN] create issue %s: %s\", repo, title)\n        return 0\n    data = {\"title\": title, \"description\": body}\n    if labels:\n        data[\"labels\"] = \",\".join(labels)\n    resp = _ok(_request(\"POST\", _url(repo, \"/issues\"), data=data))\n    return resp.json()[\"iid\"]"
        },
        {
          "name": "push_artifacts_to_branch",
          "kind": "function",
          "signature": "def push_artifacts_to_branch(repo: str, branch: str, files: dict, message: str) -> None:",
          "docstring": "",
          "start_line": 374,
          "end_line": 376,
          "source_excerpt": "def push_artifacts_to_branch(repo: str, branch: str, files: dict, message: str) -> None:\n    for path, content in files.items():\n        put_file(repo, path, content, branch=branch, message=message)"
        },
        {
          "name": "find_change_request",
          "kind": "function",
          "signature": "def find_change_request(repo: str, source_branch: str) -> dict | None:",
          "docstring": "",
          "start_line": 398,
          "end_line": 402
        }
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 2.184
    },
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 136 public symbols and depends on 23 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `github_client` | variable | github_client = forge |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_cl",
      "score": 2.184
    },
    {
      "path": "shared/agent_comment.py",
      "title": "File: shared/agent_comment.py",
      "summary": "Подпись под комментариями сервиса — чтобы он не принимал их за ответ человека.",
      "snippet": "Подпись под комментариями сервиса — чтобы он не принимал их за ответ человека.",
      "excerpt": "# shared/agent_comment.py\n\n## Overview\n\nПодпись под комментариями сервиса — чтобы он не принимал их за ответ человека.\n\nНайдено на живом прогоне: оба сигнала `user_comment` в истории цикла оказались\nнашими же комментариями — advisor-ответом и разбором приоритета. Гейт вебхука\nна `comment.user.type == \"Bot\"` их не отсекает, потому что сервис ходит в GitHub\nпод PAT, а не как GitHub App, и его комментарии приходят с `type == \"User\"`.\n\nПочему подпись, а не логин. Владелец PAT — живой человек, и он же заводит Issue\nи отвечает на уточняющие вопросы. Фильтр по логину выкинул бы вместе с нашими\nкомментариями его настоящие ответы — то есть сломал бы цикл уточнений ради\nпочинки самоподдува. Подпись различает не автора, а происхождение, и работает\nодинаково при обеих схемах авторизации.\n\nМаркер невидим в отрендеренном Markdown: GitHub не показывает HTML-комментарии.\n\nIt exposes 3 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `MARKER` | constant | MARKER = \"<!-- issue-agent -->\" |\n| `sign` | function | def sign(body: str) -> str |\n| `is_agent_comment` | function | def is_agent_comment(body: str \\| None) -> bool |\n\n## Used by\n\nImported by 4 files in this repository.\n\n- `tests/test_agent_comment.py`\n- `tests/test_github_client_pr.py`\n- `webhook/main.py`\n- `worker/github_client.py`\n\n## Usage Notes\n\n**Layer:** Utility | **Role:** edge_connector\n\n## Questions this page answers\n\n- What does `shared/agent_comment.py` export?\n- Where is `MARKER` defined?\n- W",
      "score": 2.184
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/github_client.py",
      "why_relevant": "Implements function push_artifacts_to_branch.",
      "score": 5.12
    },
    {
      "file": "worker/gitlab_client.py",
      "why_relevant": "Implements function push_artifacts_to_branch.",
      "score": 3.584
    },
    {
      "file": "shared/workflow_types.py",
      "why_relevant": "`shared/workflow_types.py` is a python source file in the Utility layer..",
      "score": 2.184
    }
  ],
  "code_rationale": [
    {
      "path": "worker/activities.py",
      "lines": [
        427,
        438
      ],
      "comment": "Принять ответ человека на открытый вопрос. `accepted`    — решение записано, ожидание снято. `confirm`     — толкование показано, ждём второго ответа. `empty`       — команда без содержания, вопрос остался открытым. `no-question` — вопроса не задавали, либо открытый вопрос — не тот, на который отвечает эта команда (ревью, находка 3). `reasked`     — блок вопроса пропал из тела, вопрос задан заново. Возвращает голую строку-вердикт, как и раньше (НЕ структуру с id нового вопроса — финальное ревью ветки, находка C2, Critical, разбирает это явно). Тип возврата активности — часть протокола Temporal: сериализованный результат уже лежит в истории у любого прогона, который хоть раз дошёл до исхода `reasked` СТАРЫМ кодом (bare-строка). Смени тип возврата на структуру — и реплей такой истории попыт…",
      "matched_terms": [
        "draft",
        "github_client"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/github_client.py",
      "name": "push_artifacts_to_branch",
      "lines": [
        455,
        463
      ],
      "source": "def push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] push %s files to %s#%s: %s\",\n                  len(files), repo, branch, sorted(files))\n        return\n    ensure_branch(repo, branch)\n    for path, content in files.items():\n        put_file(repo, branch, path, content, message)"
    },
    {
      "path": "worker/github_client.py",
      "name": "publish_worktree",
      "lines": [
        674,
        794
      ],
      "source": "def publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str,\n                     ignore_for_empty_check: tuple[str, ...] = (),\n                     force_include: tuple[str, ...] = ()) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n\n    Делает это ВОРКЕР, а не агент разработки: агенту токен не давали намеренно,\n    он исполняет код чужого репозитория. Здесь токен уже нужен не агенту, а\n    контуру — и живёт он ровно в этом процессе.\n\n    Токен идёт через credential.helper в env, а не в URL: argv команды целиком\n    попадает в текст CalledProcessError, и вклеенный токен уехал бы в историю\n    Temporal при первом же сбое пуша.\n\n    `ignore_for_empty_check` — пути (git pathspec, например `\".harness/**\"`),\n    которые не учитываются при решении «есть ли изменения». Они по-прежнему\n    попадают в сам коммит через `git add -A` ниже — исключаются только из\n    ПРОВЕРКИ пустоты. Нужно вызывающему, который пишет в рабочее дерево\n    каталог, обязанный дойти до PR независимо от того, менял ли агент код: без\n    исключения такой каталог сам по себе выглядел бы диффом, и «агент ничего\n    не изменил» перестало бы обнаруживаться.\n\n    `force_include` — пути (без pathspec-магии, например `\".harness\"`),\n    которые обязаны попасть в коммит НЕЗАВИСИМО от `.gitignore` целевого\n    репозитория (M3, ревью задачи 7). Голый `git add -A` молча пропускает\n    путь, который репозиторий игнорирует: проверка пустоты (уже не\n    учитывающая этот путь через `ignore_for_empty_check`) видит только код\n    агента, коммит и PR проходят — а каталог контекста теряется без единого\n    предупреждения. `git add -f` ниже обходит `.gitignore`; после решения о\n    коммите факт присутствия в дереве HEAD подтверждается ЗАНОВО\n    (`_missing_from_tree`) — замыслом («мы же вызвали add -f») здесь не\n    обойтись, потому что путь может остаться только в индексе, если решение\n    «коммитить или нет» приняло его не в расчёт (см. ветку `forced_pending`\n    ниже).\n    \"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] publish %s -> %s: %s\", clone_dir, branch, title)\n        return None\n\n    token = auth_token(repo)\n    env = {\n        **os.environ,\n        \"GIT_CONFIG_COUNT\": \"4\",\n        \"GIT_CONFIG_KEY_0\": \"credential.helper\",\n        \"GIT_CONFIG_VALUE_0\": \"!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f\",\n        \"GIT_CONFIG_KEY_1\": \"user.name\",\n        \"GIT_CONFIG_VALUE_1\": \"openhands-agent\",\n        \"GIT_CONFIG_KEY_2\": \"user.email\",\n        \"GIT_CONFIG_VALUE_2\": \"openhands-agent@users.noreply.github.com\",\n        # Каталог задачи передан раннеру (uid 10001), а коммит и пуш делает воркер\n        # от root. Git на такое отвечает `fatal: detected dubious ownership` и\n        # отказывается работать — готовая работа агента не доехала бы до PR.\n        # Объявляем каталог доверенным для этой команды, не трогая общий конфиг.\n        \"GIT_CONFIG_KEY_3\": \"safe.directory\",\n        \"GIT_CONFIG_VALUE_3\": clone_dir,\n        \"GH_PUSH_TOKEN\": token,\n    }\n\n    git = _git_runner(clone_dir, env)\n\n    # ДО checkout: ветка уже существует ЛОКАЛЬНО только если по этому же\n    # clone_dir сюда уже заходил предыдущий вызов этой функции. `dev_prepare`\n    # клонирует репозиторий заново на каждый прогон СТАДИИ (а не на каждую\n    # попытку публикации), поэтому в пределах ретраев `dev_publish` рабочее\n    # дерево — то же самое: если ветка уже есть, коммит на ней, скорее всего,\n    # уже сделан прошлой попыткой, и упал только пуш (или сам PR). На старом\n    # линейном пути (`trigger_openhands_resolver`, ретраев нет) `dev_prepare`\n    # отрабатывает заново при каждом вызове — там ветки здесь никогда не будет,\n    # и поведение не меняется.\n    branch_existed = git(\"show-ref\", \"--verify\", \"--quiet\", f\"refs/heads/{branch}\",\n                         check=False).returncode == 0\n\n    git(\"checkout\", \"-B\", branch)\n    git(\"add\", \"-A\")\n    for path in force_include:\n        # -f обходит .gitignore целевого репозитория: без него `add -A` выше\n        # молча пропускает путь, который репозиторий игнорирует (M3).\n        git(\"add\", \"-f\", \"--\", path)\n    # Пустой ИНДЕКС — не то же самое, что «агент ничего не менял»: если ветка\n    # уже существовала до этого вызова, значит, коммит уехал в прошлой попытке,\n    # а сорвался только пуш (или создание PR) — публикацию нужно довести, а не\n    # объявлять «нет диффа». Пустой коммит по-прежнему не делаем: PR без диффа\n    # ревьюить нечего, а фаза задачи от него сдвинулась бы как от настоящей\n    # работы — это по-прежнему верно для ПЕРВОЙ попытки на новой ветке.\n    #\n    # Проверка идёт БЕЗ путей из `ignore_for_empty_check` (git pathspec\n    # `:(exclude)...`) — сам коммит их всё равно заберёт, `git add -A` выше\n    # уже отработал по всему дереву.\n    diff_args = [\"diff\", \"--cached\", \"--quiet\", \"--\", \".\"]\n    diff_args += [f\":(exclude){pattern}\" for pattern in ignore_for_empty_check]\n    visible_diff = git(*diff_args, check=False).returncode != 0\n\n    # M3: `force_include` может внести изменение, которого «видимый» дифф не\n    # видит (он же его специально исключает через `ignore_for_empty_check`) —\n    # например, .harness/ не попал в САМЫЙ ПЕРВЫЙ коммит на этой ветке (был\n    # проигнорирован .gitignore до этой правки или иным путём), а рабочее\n    # дерево на ретрае больше не менялось. Не заметить такое pending-изменение\n    # значило бы никогда его не закоммитить: индекс не хранится между\n    # вызовами дольше жизни рабочего дерева.\n    #\n    # Гейт на `branch_existed` обязателен: на СОВЕРШЕННО НОВОЙ ветке\n    # force_include-путь «новый» ВСЕГДА (только что собран `_dev_prepare`,\n    # разница с базовым коммитом гарантирована) — без гейта пустой прогон\n    # (агент не менял код, есть только `.harness/`) считался бы правкой при\n    # КАЖДОМ вызове, и это ровно тот регресс M1/H1, ради которого\n    # `ignore_for_empty_check` вообще существует. На РЕТРАЕ существующей\n    # ветки предыдущий коммит — это факт, а не свежая сборка, и его нехватку\n    # (гитигнор, старая версия кода) нужно чинить именно здесь.\n    forced_pending = branch_existed and bool(force_include) and git(\n        \"diff\", \"--cached\", \"--quiet\", \"--\", *force_include, check=False\n    ).returncode != 0\n\n    if visible_diff or forced_pending:\n        git(\"commit\", \"-m\", message, \"-m\",\n            \"Автор изменений — OpenHands, запущен активностью Develop.\")\n    elif not branch_existed:\n        _log.warning(\"%s: агент не изменил ни одного файла\", repo)\n        return None\n\n    # Подтверждаем ФАКТОМ, а не замыслом вызова `add -f` выше (M3): проверяем\n    # дерево HEAD — то, что вот-вот уйдёт в push, — а не полагаемся на то, что",
      "truncated": true,
      "continuation": "worker/github_client.py:795-826",
      "withheld_symbols": [
        {
          "name": "publish_worktree",
          "kind": "def",
          "line": 674,
          "symbol_id": "worker/github_client.py::publish_worktree",
          "signature": "def publish_worktree(repo: str, clone_dir: str, branch: str, *, title: str, body: str, message: str, ignore_for_empty_check: tuple[str, ...] = (), force_include: tuple[str, ...] = ()) -> int | None:",
          "body_continues": true
        }
      ]
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "publish_worktree was served through line 794; call get_symbol id='worker/github_client.py:795-826' for the rest of it.",
  "_meta": {
    "timing_ms": 333.5,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/github_client.py",
      "lines": "23-963",
      "defines": "push_artifacts_to_branch:455, publish_worktree:674, GitCommandError:620, post_comment:130, add_label:153, remove_label:160"
    },
    {
      "path": "worker/gitlab_client.py",
      "lines": "76-402",
      "defines": "push_artifacts_to_branch:374, bot_login:56, post_comment:95, list_comments:111, add_reaction:139, set_labels:164"
    },
    {
      "path": "shared/workflow_types.py",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:116, OrphanEventInput:194"
    },
    {
      "path": "worker/activities.py",
      "defines": "GateExtraction:94, ClassificationExtraction:99, DuplicateCandidate:104, DuplicateExtraction:110, PriorityExtraction:114, CommentIntentExtraction:128"
    },
    {
      "path": "shared/agent_comment.py",
      "defines": "sign:20, is_agent_comment:31, MARKER:17"
    }
  ]
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/github_client.py:795-826"
}
```

**Ответ:**

{
  "symbol_id": "worker/github_client.py:795-826",
  "file": "worker/github_client.py",
  "kind": "range",
  "start_line": 795,
  "end_line": 826,
  "total_lines": 972,
  "source": "   795\t    # `git add -f` где-то раньше отработал как задумано.\n   796\t    missing = _missing_from_tree(git, force_include)\n   797\t    if missing:\n   798\t        raise RuntimeError(\n   799\t            f\"{repo}: {', '.join(missing)} не попал(и) в коммит ветки {branch}, \"\n   800\t            \"хотя force_include этого требует — вероятно, .gitignore целевого \"\n   801\t            \"репозитория. Публикация остановлена до пуша.\"\n   802\t        )\n   803\t\n   804\t    git(\"push\", \"--force-with-lease\", \"-u\", \"origin\", branch)\n   805\t\n   806\t    resp = requests.post(\n   807\t        f\"https://api.github.com/repos/{repo}/pulls\",\n   808\t        headers=_auth_headers(repo),\n   809\t        json={\"title\": title, \"head\": branch, \"base\": _default_branch(repo), \"body\": body},\n   810\t        timeout=30,\n   811\t    )\n   812\t    if resp.status_code == 422 and \"already exists\" in resp.text:\n   813\t        # Ветку переоткрыли поверх существующего PR — это повтор прогона, а не\n   814\t        # сбой: возвращаем номер уже открытого.\n   815\t        existing = requests.get(\n   816\t            f\"https://api.github.com/repos/{repo}/pulls\",\n   817\t            headers=_auth_headers(repo),\n   818\t            params={\"head\": f\"{repo.split('/')[0]}:{branch}\", \"state\": \"open\"},\n   819\t            timeout=30,\n   820\t        )\n   821\t        existing.raise_for_status()\n   822\t        items = existing.json()\n   823\t        if items:\n   824\t            return items[0][\"number\"]\n   825\t    resp.raise_for_status()\n   826\t    return resp.json()[\"number\"]",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 22.54,
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 10310
  }
}

## Ход 7 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Что происходит после исключения из шага dev_tests в воркфлоу IssueDevelopment и в родительском воркфлоу: есть ли очистка рабочего каталога (какая активность её делает и на каком исходе — всегда или только при успехе), и кто сообщает человеку о провале разработки — есть ли активность вроде publish_dev_error или комментарий из родительского воркфлоу?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `dev_tests`, `IssueDevelopment`, read from the current checkout, cut at the line cap where noted; see `continuation`. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py",
    "worker/workflows.py"
  ],
  "confidence": "low",
  "retrieval_quality": "weak",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    "worker/workflows.py",
    "shared/workflow_types.py",
    "worker/estimation.py",
    "worker/github_client.py"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "ssue: IssueInput) -> None |\n| `DEV_CLONE_TIMEOUT_SEC` | constant | DEV_CLONE_TIMEOUT_SEC = 300 |\n| `DEV_TESTS_TIMEOUT_SEC` | constant | DEV_TESTS_TIMEOUT_SEC = 900 |\n| `INJECTED_RULES_FILE` | constant",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 136 public symbols and depends on 23 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `github_client` | variable | github_client = forge |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_cl",
      "score": 5.304,
      "key_symbols": [
        {
          "name": "publish_analysis",
          "kind": "function",
          "signature": "async def publish_analysis(analyze: AnalyzeInput) -> str:",
          "docstring": "Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.",
          "start_line": 2529,
          "end_line": 2546
        },
        {
          "name": "DEV_TESTS_TIMEOUT_SEC",
          "kind": "constant",
          "signature": "DEV_TESTS_TIMEOUT_SEC = 900",
          "docstring": "",
          "start_line": 2608,
          "end_line": 2608,
          "source_excerpt": "DEV_TESTS_TIMEOUT_SEC = 900"
        },
        {
          "name": "_publish_dev_dialog_sync",
          "kind": "function",
          "signature": "def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:",
          "docstring": "Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.\n\n    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе\n    разбор начнут не с того места.",
          "start_line": 3226,
          "end_line": 3249,
          "source_excerpt": "def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:\n    \"\"\"Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.\n\n    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе\n    разбор начнут не с того места.\n    \"\"\"\n    if not repowise.enabled():\n        return\n    text = _collect_dev_dialog(issue.repo, issue.issue_number, run_failed=False)\n    path = DEV_DIALOG_PATH.format(n=issue.issue_number)\n    try:\n        if branch:\n            github_client.push_artifacts_to_branch(\n                issue.repo, branch, {path: text},\n                f\"docs(repowise): диалог разработки по issue #{issue.issue_number}\")\n        github_client.post_comment(\n            issue.repo, issue.issue_number,\n            f\"## 🧭 Контекст из Repowise (разработка)\\n\\n\"\n            f\"Диалог агента разработки с индексом кода — `{path}`\"\n            f\"{f' в ветке `{branch}`' if branch else ''}.\\n\\n\"\n            f\"<details><summary>Показать</summary>\\n\\n{text[:20000]}\\n\\n</details>\")\n    except Exception as exc:\n        logger.warning(\"диалог разработки не опубликован (%s#%s): %s\",\n                       issue.repo, issue.issue_number, exc)"
        },
        {
          "name": "_dev_tests",
          "kind": "function",
          "signature": "def _dev_tests(issue: IssueInput) -> str:",
          "docstring": "Прогон проверок проекта. Пусто в конфиге — шаг пропускается.\n\n    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от\n    агента CI может и не запуститься (события от токена Actions не порождают\n    прогонов).",
          "start_line": 3252,
          "end_line": 3279,
          "source_excerpt": "def _dev_tests(issue: IssueInput) -> str:\n    \"\"\"Прогон проверок проекта. Пусто в конфиге — шаг пропускается.\n\n    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от\n    агента CI может и не запуститься (события от токена Actions не порождают\n    прогонов).\n    \"\"\"\n    root, clone_dir = _dev_paths(issue)\n    command = os.environ.get(\"DEVELOP_TEST_COMMAND\", \"\").strip()\n    if not command:\n        # Пусто — шаг пропускается, и это НЕ «тесты прошли». Записываем\n        # неизвестность явно: иначе слой саморефлексии засчитает пропуск как\n        # успех, а свёртка сигналов начнёт хвалить прогоны, которых не было.\n        _write_signal(root, \"tests_passed\", None)\n        return \"(проверки не заданы — DEVELOP_TEST_COMMAND пуст)\"\n\n    result = subprocess.run(command, shell=True, cwd=str(clone_dir),\n                            capture_output=True, text=True, timeout=DEV_TESTS_TIMEOUT_SEC)\n    out = ((result.stdout or \"\") + (result.stderr or \"\"))[-3000:]\n\n    # Исход пишется ДО возможного исключения. Красный прогон — самый интересный\n    # для разбора, и терять о нём запись значит собирать статистику только по\n    # удачам.\n    _write_signal(root, \"tests_passed\", result.returncode == 0)\n\n    if result.returncode != 0:\n        raise RuntimeError(f\"проверки не прошли (код {result.returncode}):\\n{out[-1500:]}\")\n    return out"
        },
        {
          "name": "_dev_publish",
          "kind": "function",
          "signature": "def _dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Коммит, пуш и PR — руками воркера, его токеном.\n\n    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен\n    контуру. Возвращает номер PR либо None, если агент ничего не изменил.",
          "start_line": 3282,
          "end_line": 3321,
          "source_excerpt": "def _dev_publish(issue: IssueInput, branch: str) -> int | None:\n    \"\"\"Коммит, пуш и PR — руками воркера, его токеном.\n\n    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен\n    контуру. Возвращает номер PR либо None, если агент ничего не изменил.\n    \"\"\"\n    # Корень задачи нужен не только клону: туда перекладывается файл намерений,\n    # чтобы пережить снятие из рабочего дерева.\n    root, clone_dir = _dev_paths(issue)\n    # Постановка — вход контура, а не часть правки. Она лежит в рабочем дереве, и\n    # `git add -A` забирает её вместе с кодом: на живом прогоне это дало PR из\n    # одного файла на 1721 строку — нашей же постановки. Хуже того, дифф из неё\n    # обманывал гвард «изменений нет — открывать нечего», и PR открывался по\n    # прогону, в котором агент не тронул ни одного файла.\n    # Одна точка снятия на весь контур: перечень служебных файлов живёт в\n    # `shared/develop.py`, а не переписывается в каждой функции заново.\n    removed = develop.clear_service_files(clone_dir, keep_dir=root)\n    if removed:\n        logger.info(\"Develop %s#%s: сняты служебные файлы: %s\",\n                    issue.repo, issue.issue_number, \", \".join(removed))\n    work = develop.work_branch(issue.issue_number)\n    return github_client.publish_worktree(\n        issue.repo, str(clone_dir), work,\n        title=f\"feat(#{issue.issue_number}): {issue.title}\",\n        body=develop.pr_body(issue.issue_number, branch=branch),\n        message=f\"feat(#{issue.issue_number}): реализация по системным требованиям\",\n        # `.harness/` — единственный служебный каталог, что НЕ снимается\n        # (задача 7: контекст обязан дойти до PR). Он пишется в `_dev_prepare`\n        # ДО прогона агента и потому существует независимо от того, тронул ли\n        # агент код, — «пустой прогон» больше не значит «дифф пуст», если\n        # эту проверку не поправить. Исключаем каталог из решения «есть ли\n        # диф», а не из самого коммита: `git add -A` продолжает забирать его.\n        ignore_for_empty_check=(f\"{task_context.DIR}/**\",),\n        # M3 (ревью задачи 7): если `.gitignore` ЦЕЛЕВОГО репозитория содержит\n        # `.harness/`, голый `git add -A` молча пропускает каталог — PR уйдёт\n        # без контекста и без единого предупреждения. `force_include`\n        # заставляет каталог попасть в коммит независимо от `.gitignore` и\n        # подтверждает это фактом (деревом HEAD), а не только вызовом `add -f`.\n        force_include=(task_context.DIR,),\n    )"
        },
        {
          "name": "dev_tests",
          "kind": "function",
          "signature": "async def dev_tests(issue: IssueInput) -> None:",
          "docstring": "Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.",
          "start_line": 3509,
          "end_line": 3515,
          "source_excerpt": "async def dev_tests(issue: IssueInput) -> None:\n    \"\"\"Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.\n    \"\"\"\n    await _run_with_heartbeat(_dev_tests, issue, label=\"dev:tests\")"
        },
        {
          "name": "dev_publish",
          "kind": "function",
          "signature": "async def dev_publish(issue: IssueInput, branch: str) -> int | None:",
          "docstring": "Шаг 6: коммит, пуш и PR — руками воркера, его токеном.\n\n    `None` — агент не изменил ни одного файла. Это не сбой шага, а его\n    результат; решение, что делать с пустым прогоном, принимает воркфлоу.",
          "start_line": 3519,
          "end_line": 3525
        },
        {
          "name": "publish_decomposition",
          "kind": "function",
          "signature": "def publish_decomposition(issue: IssueInput, plan: dict, branch: str) -> list[int]:",
          "docstring": "Создаёт подзадачи и публикует план в родителе.\n\n    Порядок важен: сначала все подзадачи, потом сводка. Сводка ссылается на\n    номера, которых до создания не существует, а план с битыми ссылками хуже\n    отсутствующего — по нему пойдут и упрутся.\n\n    Зависимости проставляются вторым проходом по той же причине: подзадача\n    может зависеть от той, что создаётся позже.",
          "start_line": 3842,
          "end_line": 3880
        },
        {
          "name": "publish_analysis_error",
          "kind": "function",
          "signature": "async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:",
          "docstring": "Не молчать при провале: прогон дорогой и долгий, тихое падение\n    неотличимо от «ещё работает».",
          "start_line": 4075,
          "end_line": 4090
        },
        {
          "name": "publish_bft_error",
          "kind": "function",
          "signature": "async def publish_bft_error(req: BftRequest, reason: str) -> None:",
          "docstring": "Не молчать при сбое — требование постановки, а не вежливость.\n\n    Молчащий сбой неотличим от «ещё думает»: человек ждёт БФТ, которого уже не\n    будет, и узнаёт об этом, только когда сам придёт спрашивать.",
          "start_line": 4895,
          "end_line": 4907
        }
      ]
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "ethod | async def run(self, issue: IssueInput, carried: LifecycleState \\| None = None) -> None |\n| `IssueDevelopment` | class | class IssueDevelopment |\n| `run` | method | async def run(self, issue: I",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 48 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `AGENT_RESEARCH` | constant | AGENT_RESEARCH = \"__agent__:research\" |\n| `HOWTODEMO_TASK_QUEUE` | constant | HOWTODEMO_TASK_QUEUE = \"howtodemo\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | c",
      "score": 5.304,
      "key_symbols": [
        {
          "name": "_start_development",
          "kind": "method",
          "signature": "async def _start_development(self, issue: IssueInput) -> tuple:",
          "docstring": "Гейт критерия приёмки, а затем — передача задачи агенту разработки.\n\n        Одна точка на все входы — решение человека `build-me`, автостарт и\n        принятый ответ на вопрос о критерии (см. `_phase_await_build`). Точка\n        входа ОДНА и до этой задачи вела прямиком к разработке; гейт встаёт\n        перед ней, не заменяя её — сама передача осталась в `_begin_development`.\n\n        Маркер обязателен: у припаркованных прогонов решение «начать\n        разработку» УЖЕ лежит в истории на этом месте, и новый код запланировал\n        бы здесь активность, которой там нет, — реплей упал бы недетерминизмом.\n        Так легли 29 прогонов из 149 после коммита `ac625e7`.",
          "start_line": 2508,
          "end_line": 2937,
          "source_excerpt": "    async def _start_development(self, issue: IssueInput) -> tuple:\n        \"\"\"Гейт критерия приёмки, а затем — передача задачи агенту разработки.\n\n        Одна точка на все входы — решение человека `build-me`, автостарт и\n        принятый ответ на вопрос о критерии (см. `_phase_await_build`). Точка\n        входа ОДНА и до этой задачи вела прямиком к разработке; гейт встаёт\n        перед ней, не заменяя её — сама передача осталась в `_begin_development`.\n\n        Маркер обязателен: у припаркованных прогонов решение «начать\n        разработку» УЖЕ лежит в истории на этом месте, и новый код запланировал\n        бы здесь активность, которой там нет, — реплей упал бы недетерминизмом.\n        Так легли 29 прогонов из 149 после коммита `ac625e7`.\n        \"\"\"\n        if workflow.patched(\"issue-lifecycle-acceptance-gate\"):\n            # Тело Issue живёт снаружи воркфлоу — активность, не чтение здесь:\n            # реплей обязан быть детерминированным, а тело меняется без нас.\n            try:\n                criterion = await workflow.execute_activity(\n                    activities.read_acceptance_criterion, issue,\n                    start_to_close_timeout=timedelta(minutes=2),\n                    retry_policy=RetryPolicy(maximum_attempts=3),\n                )\n            except Exception as e:\n                # Ревью, находка 1 (Important): устойчивый отказ GitHub (после\n                # исчерпания ретраев) не должен ронять весь IssueLifecycle —\n                # тогда Issue теряет владельца состояния целиком из-за\n                # временного сбоя сети. Симметрично `_clarify_open_questions`\n                # (там же рядом — чтение открытых вопросов аналитики) гасим\n                # сбой чтения, не давая ему остановить цикл.\n                #\n                # Но, В ОТЛИЧИЕ от неё, дальше НЕ идём как обычно (там сбой\n                # читает необязательное улучшение, задачу можно передать и без\n                # него). Здесь сам факт критерия — условие входа в разработку,\n                # а мы его не знаем: не прочитали, а не «прочитали и там\n                # пусто». Трактовать сбой чтения как «критерия нет» и тут же\n                # задать вопрос было бы неправдой человеку — критерий, возможно,\n                # ЕСТЬ, просто тело Issue не прочиталось, а «не вижу критерия»\n                # это утверждение о содержимом, а не о сети. Гейт обязан\n                # держать закрыто при неизвестном ответе: пропустить задачу в\n                # разработку из-за сетевого сбоя хуже, чем не начать её вовремя\n                # — поэтому остаёмся на парковке той же фазы, ничего не спрашивая"
        },
        {
          "name": "_begin_development",
          "kind": "method",
          "signature": "async def _begin_development(self, issue: IssueInput) -> tuple:",
          "docstring": "Передать задачу агенту разработки — без повторной проверки критерия.\n\n        Отдельная функция, а не хвост `_start_development`, по одной причине:\n        принятый ответ на вопрос о критерии (`_phase_await_build`) знает, что\n        критерий только что записан — `_place_decision` в `answer_question`\n        (`worker/activities.py`) положил его в блок HOWTODEMO ДО того, как\n        сюда вернулось управление. Дёрнуть `_start_development` заново означало\n        бы честный, но ЛИШНИЙ круг `read_acceptance_criterion` за тем же самым\n        текстом — активность, которая станет предсказуемым `True` в 100%\n        случаев, кроме одного: тело Issue успели поправить руками между\n        ответом и этим вызовом, и тогда лишний круг превратился бы в вопрос\n        по уже отвеченному критерию. Дешевле и честнее звать разработку\n        напрямую: `answer_question` вернула `accepted` — этого достаточно.\n\n        Одна точка на оба оставшихся входа — решение человека `build-me` и\n        автостарт. Две копии этого вызова разъехались бы на первой же правке\n        ретраев, и один из входов молча остался бы со старым поведением.\n\n        ISSUE-113: для подзадачи плана передаём root_issue и ветку родителя.",
          "start_line": 2939,
          "end_line": 3037,
          "source_excerpt": "    async def _begin_development(self, issue: IssueInput) -> tuple:\n        \"\"\"Передать задачу агенту разработки — без повторной проверки критерия.\n\n        Отдельная функция, а не хвост `_start_development`, по одной причине:\n        принятый ответ на вопрос о критерии (`_phase_await_build`) знает, что\n        критерий только что записан — `_place_decision` в `answer_question`\n        (`worker/activities.py`) положил его в блок HOWTODEMO ДО того, как\n        сюда вернулось управление. Дёрнуть `_start_development` заново означало\n        бы честный, но ЛИШНИЙ круг `read_acceptance_criterion` за тем же самым\n        текстом — активность, которая станет предсказуемым `True` в 100%\n        случаев, кроме одного: тело Issue успели поправить руками между\n        ответом и этим вызовом, и тогда лишний круг превратился бы в вопрос\n        по уже отвеченному критерию. Дешевле и честнее звать разработку\n        напрямую: `answer_question` вернула `accepted` — этого достаточно.\n\n        Одна точка на оба оставшихся входа — решение человека `build-me` и\n        автостарт. Две копии этого вызова разъехались бы на первой же правке\n        ретраев, и один из входов молча остался бы со старым поведением.\n\n        ISSUE-113: для подзадачи плана передаём root_issue и ветку родителя.\n        \"\"\"\n        # ISSUE-113 пункт 2: вычисляем ветку так же, как в _phase_handoff\n        source = self._root_issue if self._plan_member and self._root_issue else issue.issue_number\n        branch = f\"research/issue-{source}\"\n\n        try:\n            if workflow.patched(\"issue-lifecycle-develop-child\"):\n                # Дочерний прогон: у стадии появляется свой WorkflowId, а\n                # значит строка в `workflow list` и след, переживающий её\n                # завершение. Одна попытка на уровне стадии — ретраи живут\n                # внутри, на отдельных шагах.\n                pr_number = await workflow.execute_child_workflow(\n                    IssueDevelopment.run, issue,\n                    id=development_workflow_id(issue.repo, issue.issue_number),\n                    # Прогон агента идёт до 45 минут. Ни continue-as-new\n                    # родителя, ни его завершение не должны его убивать.\n                    parent_close_policy=ParentClosePolicy.ABANDON,\n                    retry_policy=RetryPolicy(maximum_attempts=1),\n                )\n            else:\n                pr_number = await workflow.execute_activity("
        },
        {
          "name": "IssueDevelopment",
          "kind": "class",
          "signature": "class IssueDevelopment:",
          "docstring": "Разработка по подготовленному Issue — дочерний прогон цикла.\n\n    Отдельным воркфлоу, а не активностью, по двум причинам сразу.\n\n    Первая — видимость. Активность внутри родителя не имеет своего\n    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся\n    и следа — операционная история собиралась логами контейнера и `docker ps`.\n\n    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на\n    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл\n    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого\n    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в\n    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.\n\n    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск\n    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает\n    второго агента в тот же рабочий каталог.",
          "start_line": 3540,
          "end_line": 3714,
          "source_excerpt": "class IssueDevelopment:\n    \"\"\"Разработка по подготовленному Issue — дочерний прогон цикла.\n\n    Отдельным воркфлоу, а не активностью, по двум причинам сразу.\n\n    Первая — видимость. Активность внутри родителя не имеет своего\n    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся\n    и следа — операционная история собиралась логами контейнера и `docker ps`.\n\n    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на\n    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл\n    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого\n    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в\n    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.\n\n    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск\n    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает\n    второго агента в тот же рабочий каталог.\n    \"\"\"\n\n    @workflow.run\n    async def run(self, issue: IssueInput) -> int | None:\n        \"\"\"Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.\n        \"\"\"\n        cheap = RetryPolicy(maximum_attempts=3)\n        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и\n        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.\n        once = RetryPolicy(maximum_attempts=1)\n\n        plan = await workflow.execute_activity(\n            activities.dev_begin, issue,\n            start_to_close_timeout=timedelta(seconds=120),\n            retry_policy=cheap,\n        )\n\n        if plan.mode == \"dispatch\":\n            await workflow.execute_activity(\n                activities.dev_dispatch, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=120),\n                retry_policy=cheap,\n            )\n            return None\n\n        number: int | None = None\n        try:\n            # Порядок не косметический: сначала клон и постановка — они\n            # единственные могут не состояться до того, как что-либо сказано\n            # человеку.\n            await workflow.execute_activity(\n                activities.dev_prepare, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_announce, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=60),\n                retry_policy=cheap,\n            )\n            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом\n            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.\n            #\n            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,\n            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена\n            # ревью, revert 80b3291) звала планирование до подготовки —\n            # находка K2, «холодный старт»: стадия падала в каталоге,\n            # которого никто ещё не создал.\n            #\n            # Не позже: план — вход агента, а не отчёт по итогам его работы.\n            #\n            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и\n            # прогоны, начатые до выкладки, обязаны реплеиться прежней\n            # последовательностью, без неё.\n            #\n            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не\n            # результат стадии (`PLAN` не входит в `task_context.required()`\n            # намеренно) — агент штатно работает без него уже сегодня. Топить\n            # дорогой прогон разработки из-за упавшего необязательного шага\n            # значило бы разменивать штатный путь на необязательное ускорение.\n            if workflow.patched(\"issue-lifecycle-develop-plan-stage\"):\n                try:\n                    has_plan = await workflow.execute_activity(\n                        activities.build_mvp_plan, args=[issue, plan.branch],\n                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n                        heartbeat_timeout=timedelta(seconds=300),\n                        retry_policy=once,\n                    )\n                except Exception as e:                    # noqa: BLE001\n                    workflow.logger.warning(\n                        \"план работ не построен: %s\", _failure_reason(e))\n                else:\n                    if not has_plan:\n                        workflow.logger.warning(\n                            \"план работ пуст или не создан — агент продолжит без него\")\n            await workflow.execute_activity(\n                activities.dev_run_agent, issue,\n                start_to_close_timeout=timedelta(seconds=3600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из\n            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на\n            # следующем круге правок агент прочитает свои прошлые находки как новые.\n            await workflow.execute_activity(\n                activities.dev_followups, issue,\n                start_to_close_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_tests, issue,\n                start_to_close_timeout=timedelta(seconds=1800),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            number = await workflow.execute_activity(\n                activities.dev_publish, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),"
        },
        {
          "name": "run",
          "kind": "method",
          "signature": "async def run(self, issue: IssueInput) -> int | None:",
          "docstring": "Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.",
          "start_line": 3561,
          "end_line": 3714,
          "source_excerpt": "    async def run(self, issue: IssueInput) -> int | None:\n        \"\"\"Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.\n        \"\"\"\n        cheap = RetryPolicy(maximum_attempts=3)\n        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и\n        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.\n        once = RetryPolicy(maximum_attempts=1)\n\n        plan = await workflow.execute_activity(\n            activities.dev_begin, issue,\n            start_to_close_timeout=timedelta(seconds=120),\n            retry_policy=cheap,\n        )\n\n        if plan.mode == \"dispatch\":\n            await workflow.execute_activity(\n                activities.dev_dispatch, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=120),\n                retry_policy=cheap,\n            )\n            return None\n\n        number: int | None = None\n        try:\n            # Порядок не косметический: сначала клон и постановка — они\n            # единственные могут не состояться до того, как что-либо сказано\n            # человеку.\n            await workflow.execute_activity(\n                activities.dev_prepare, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_announce, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=60),\n                retry_policy=cheap,\n            )\n            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом\n            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.\n            #\n            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,\n            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена\n            # ревью, revert 80b3291) звала планирование до подготовки —\n            # находка K2, «холодный старт»: стадия падала в каталоге,\n            # которого никто ещё не создал.\n            #\n            # Не позже: план — вход агента, а не отчёт по итогам его работы.\n            #\n            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и\n            # прогоны, начатые до выкладки, обязаны реплеиться прежней\n            # последовательностью, без неё.\n            #\n            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не\n            # результат стадии (`PLAN` не входит в `task_context.required()`\n            # намеренно) — агент штатно работает без него уже сегодня. Топить\n            # дорогой прогон разработки из-за упавшего необязательного шага\n            # значило бы разменивать штатный путь на необязательное ускорение.\n            if workflow.patched(\"issue-lifecycle-develop-plan-stage\"):\n                try:\n                    has_plan = await workflow.execute_activity(\n                        activities.build_mvp_plan, args=[issue, plan.branch],\n                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n                        heartbeat_timeout=timedelta(seconds=300),\n                        retry_policy=once,\n                    )\n                except Exception as e:                    # noqa: BLE001\n                    workflow.logger.warning(\n                        \"план работ не построен: %s\", _failure_reason(e))\n                else:\n                    if not has_plan:\n                        workflow.logger.warning(\n                            \"план работ пуст или не создан — агент продолжит без него\")\n            await workflow.execute_activity(\n                activities.dev_run_agent, issue,\n                start_to_close_timeout=timedelta(seconds=3600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из\n            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на\n            # следующем круге правок агент прочитает свои прошлые находки как новые.\n            await workflow.execute_activity(\n                activities.dev_followups, issue,\n                start_to_close_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_tests, issue,\n                start_to_close_timeout=timedelta(seconds=1800),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            number = await workflow.execute_activity(\n                activities.dev_publish, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n        finally:\n            # Запись об итерации — В FINALLY, а не после успешных шагов.\n            #\n            # Красные тесты и сорвавшийся прогон агента — самые интересные для\n            # разбора исходы, и именно они пропускали запись: исключение из\n            # шага уносило управление мимо неё. Слой собирал статистику только\n            # по удачам и на ней же учился.\n            #\n            # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет\n            # недетерминизмом прогоны, начатые до выкладки, а прогон агента\n            # идёт до 45 минут. Прецедент в этом же файле — реплей без маркера\n            # падает `Timer machine does not handle ActivityTaskScheduled`.\n            if workflow.patched(\"issue-lifecycle-capture-episode-always\"):\n                try:\n                    await workflow.execute_activity(\n                        activities.capture_episode,\n                        args=[issue, plan.branch, number],\n                        start_to_close_timeout=timedelta(seconds=60),\n                        retry_policy=cheap,"
        }
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 2.313
    },
    {
      "path": "worker/estimation.py",
      "title": "File: worker/estimation.py",
      "summary": "Детерминированный расчёт оценки задачи.",
      "snippet": "Детерминированный расчёт оценки задачи.",
      "excerpt": "# worker/estimation.py\n\n## Overview\n\nДетерминированный расчёт оценки задачи.\n\nЧистый модуль: ни сети, ни LLM, ни Temporal. Модель отдаёт только факты\n(EstimationFacts), а коэффициенты, надбавки, PERT, cross-check и коридоры\nсчитаются здесь по config/estimation-rules.toml. Тот же принцип, что уже\nработает в score_priority: модель извлекает, код считает — иначе одна и та\nже задача давала бы разные числа от прогона к прогону.\n\nПоля «итоговая оценка» в схеме фактов нет намеренно: модель структурно не\nможет вернуть готовое число в обход расчёта.\n\nIt exposes 15 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `RULES_PATH` | constant | RULES_PATH = Path(\"/app/config/estimation-rules.toml\") |\n| `WORK_TYPE_RU` | constant | WORK_TYPE_RU = { |\n| `ARTIFACT_TYPE_RU` | constant | ARTIFACT_TYPE_RU = { |\n| `RISK_LABELS` | constant | RISK_LABELS = { |\n| `PENALTY_LABELS` | constant | PENALTY_LABELS = { |\n| `CONFIDENCE_RU` | constant | CONFIDENCE_RU = {\"high\": \"высокая\", \"medium\": \"средняя\", \"low\": \"низкая\"} |\n| `EstimationError` | class | class EstimationError |\n| `WorkUnit` | class | class WorkUnit |\n| `EstimationFacts` | class | class EstimationFacts |\n| `AppliedRisk` | class | class AppliedRisk |\n| `AppliedPenalty` | class | class AppliedPenalty |\n| `Estimate` | class | class Estimate |\n| `load_rules` | function | def load_rules(path: Path = RULES_PATH) -> dict |\n| `positive_units` | function | def positive_units(facts: EstimationFacts) -> list[WorkUnit] |",
      "score": 2.313
    },
    {
      "path": "worker/github_client.py",
      "title": "File: worker/github_client.py",
      "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час).",
      "snippet": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужн",
      "excerpt": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\nIt exposes 34 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `add_label` | function | def add_label(repo: str, issue_number: int, label: str) -> None |\n| `remove_label` | function | def remove_label(repo: str, issue_number: int, label: str) -> None |\n| `set_labels` | function | def set_labels(repo: str, issue_number: int, *, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None |\n| `ensure_labels_exist` | function | def ensure_labels_exist(repo: str, specs) -> int |\n| `create_issue` | function | def create_issue(repo: str, title: str, body: str, labels: list[str] \\| None = None) -> int |\n| `issue_node_id` | function | def issue_node_id(repo: str, issue_number: int) -> int |\n| `link_sub_issue` | function | def link_sub_issue(repo: str, parent: int, child_id: int) -> None |\n| `list_sub_issues` | function | def list_sub_issues(repo: str, parent: int) -> list[dict] |\n| `close_issue` | function | def close_issue(repo: str, issue_number: int) -> None |\n| `search_candidates` | function | def search_candidates(repo: str, q",
      "score": 2.313
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements constant DEV_TESTS_TIMEOUT_SEC.",
      "score": 5.304
    },
    {
      "file": "worker/workflows.py",
      "why_relevant": "Implements class IssueDevelopment.",
      "score": 5.304
    },
    {
      "file": "shared/workflow_types.py",
      "why_relevant": "`shared/workflow_types.py` is a python source file in the Utility layer..",
      "score": 2.313
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "dev_tests",
      "lines": [
        3509,
        3515
      ],
      "source": "async def dev_tests(issue: IssueInput) -> None:\n    \"\"\"Шаг 5: проверки проекта — до пуша.\n\n    Красный код не должен доезжать до PR, а на PR от агента CI может и не\n    запуститься: события от токена Actions не порождают прогонов.\n    \"\"\"\n    await _run_with_heartbeat(_dev_tests, issue, label=\"dev:tests\")"
    },
    {
      "path": "worker/workflows.py",
      "name": "IssueDevelopment",
      "lines": [
        3540,
        3660
      ],
      "source": "class IssueDevelopment:\n    \"\"\"Разработка по подготовленному Issue — дочерний прогон цикла.\n\n    Отдельным воркфлоу, а не активностью, по двум причинам сразу.\n\n    Первая — видимость. Активность внутри родителя не имеет своего\n    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся\n    и следа — операционная история собиралась логами контейнера и `docker ps`.\n\n    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на\n    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл\n    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого\n    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в\n    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.\n\n    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск\n    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает\n    второго агента в тот же рабочий каталог.\n    \"\"\"\n\n    @workflow.run\n    async def run(self, issue: IssueInput) -> int | None:\n        \"\"\"Возвращает номер PR (`local`) либо None (`dispatch`).\n\n        `None` родитель читает как «работа идёт на чужой стороне, жди события\n        `pr-open`», а не как отказ.\n        \"\"\"\n        cheap = RetryPolicy(maximum_attempts=3)\n        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и\n        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.\n        once = RetryPolicy(maximum_attempts=1)\n\n        plan = await workflow.execute_activity(\n            activities.dev_begin, issue,\n            start_to_close_timeout=timedelta(seconds=120),\n            retry_policy=cheap,\n        )\n\n        if plan.mode == \"dispatch\":\n            await workflow.execute_activity(\n                activities.dev_dispatch, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=120),\n                retry_policy=cheap,\n            )\n            return None\n\n        number: int | None = None\n        try:\n            # Порядок не косметический: сначала клон и постановка — они\n            # единственные могут не состояться до того, как что-либо сказано\n            # человеку.\n            await workflow.execute_activity(\n                activities.dev_prepare, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_announce, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=60),\n                retry_policy=cheap,\n            )\n            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом\n            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.\n            #\n            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,\n            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена\n            # ревью, revert 80b3291) звала планирование до подготовки —\n            # находка K2, «холодный старт»: стадия падала в каталоге,\n            # которого никто ещё не создал.\n            #\n            # Не позже: план — вход агента, а не отчёт по итогам его работы.\n            #\n            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и\n            # прогоны, начатые до выкладки, обязаны реплеиться прежней\n            # последовательностью, без неё.\n            #\n            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не\n            # результат стадии (`PLAN` не входит в `task_context.required()`\n            # намеренно) — агент штатно работает без него уже сегодня. Топить\n            # дорогой прогон разработки из-за упавшего необязательного шага\n            # значило бы разменивать штатный путь на необязательное ускорение.\n            if workflow.patched(\"issue-lifecycle-develop-plan-stage\"):\n                try:\n                    has_plan = await workflow.execute_activity(\n                        activities.build_mvp_plan, args=[issue, plan.branch],\n                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n                        heartbeat_timeout=timedelta(seconds=300),\n                        retry_policy=once,\n                    )\n                except Exception as e:                    # noqa: BLE001\n                    workflow.logger.warning(\n                        \"план работ не построен: %s\", _failure_reason(e))\n                else:\n                    if not has_plan:\n                        workflow.logger.warning(\n                            \"план работ пуст или не создан — агент продолжит без него\")\n            await workflow.execute_activity(\n                activities.dev_run_agent, issue,\n                start_to_close_timeout=timedelta(seconds=3600),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из\n            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на\n            # следующем круге правок агент прочитает свои прошлые находки как новые.\n            await workflow.execute_activity(\n                activities.dev_followups, issue,\n                start_to_close_timeout=timedelta(seconds=300),\n                retry_policy=cheap,\n            )\n            await workflow.execute_activity(\n                activities.dev_tests, issue,\n                start_to_close_timeout=timedelta(seconds=1800),\n                heartbeat_timeout=timedelta(seconds=300),\n                retry_policy=once,\n            )\n            number = await workflow.execute_activity(\n                activities.dev_publish, args=[issue, plan.branch],\n                start_to_close_timeout=timedelta(seconds=600),\n                heartbeat_timeout=timedelta(seconds=300),",
      "truncated": true,
      "continuation": "worker/workflows.py:3661-3714",
      "withheld_symbols": [
        {
          "name": "run",
          "kind": "def",
          "line": 3561,
          "symbol_id": "worker/workflows.py::run",
          "signature": "async def run(self, issue: IssueInput) -> int | None:",
          "body_continues": true
        }
      ]
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "IssueDevelopment was served through line 3660; call get_symbol id='worker/workflows.py::run' for the withheld body.",
  "_meta": {
    "timing_ms": 1228.0,
    "hint": "No synthesis, and retrieval was weak. Refine the query with search_codebase rather than reading these files in order.",
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "2529-4907",
      "defines": "dev_tests:3509, GateExtraction:94, ClassificationExtraction:99, DuplicateCandidate:104, DuplicateExtraction:110, PriorityExtraction:114"
    },
    {
      "path": "worker/workflows.py",
      "lines": "2508-3714",
      "defines": "IssueDevelopment:3540, WebhookAudit:307, OrphanAgentEvent:330, CommentAck:351, IssueLifecycle:374, IssuePrFix:3718"
    },
    {
      "path": "shared/workflow_types.py",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:116, OrphanEventInput:194"
    },
    {
      "path": "worker/estimation.py",
      "defines": "EstimationError:64, WorkUnit:68, EstimationFacts:74, AppliedRisk:93, AppliedPenalty:101, Estimate:108"
    },
    {
      "path": "worker/github_client.py",
      "defines": "GitCommandError:620, post_comment:130, add_label:153, remove_label:160, set_labels:179, ensure_labels_exist:226"
    }
  ]
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py:3661-3714"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py:3661-3714",
  "file": "worker/workflows.py",
  "kind": "range",
  "start_line": 3661,
  "end_line": 3714,
  "total_lines": 4032,
  "source": "  3661\t                retry_policy=cheap,\n  3662\t            )\n  3663\t        finally:\n  3664\t            # Запись об итерации — В FINALLY, а не после успешных шагов.\n  3665\t            #\n  3666\t            # Красные тесты и сорвавшийся прогон агента — самые интересные для\n  3667\t            # разбора исходы, и именно они пропускали запись: исключение из\n  3668\t            # шага уносило управление мимо неё. Слой собирал статистику только\n  3669\t            # по удачам и на ней же учился.\n  3670\t            #\n  3671\t            # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет\n  3672\t            # недетерминизмом прогоны, начатые до выкладки, а прогон агента\n  3673\t            # идёт до 45 минут. Прецедент в этом же файле — реплей без маркера\n  3674\t            # падает `Timer machine does not handle ActivityTaskScheduled`.\n  3675\t            if workflow.patched(\"issue-lifecycle-capture-episode-always\"):\n  3676\t                try:\n  3677\t                    await workflow.execute_activity(\n  3678\t                        activities.capture_episode,\n  3679\t                        args=[issue, plan.branch, number],\n  3680\t                        start_to_close_timeout=timedelta(seconds=60),\n  3681\t                        retry_policy=cheap,\n  3682\t                    )\n  3683\t                except Exception as e:                   # noqa: BLE001\n  3684\t                    # Слой опционален и не имеет права стоить прогона — тем\n  3685\t                    # более уже упавшего, где запись лишь пояснение к отказу.\n  3686\t                    workflow.logger.warning(\n  3687\t                        \"запись об итерации не отдана слою памяти: %s\",\n  3688\t                        _failure_reason(e))\n  3689\t\n  3690\t        if number is None:\n  3691\t            reason = \"агент не изменил ни одного файла — открывать нечего\"\n  3692\t            if workflow.patched(\"issue-lifecycle-empty-run-diagnosis\"):\n  3693\t                # Прежнее сообщение обвиняло агента в бездействии даже тогда,\n  3694\t                # когда он не сделал ни одного хода — то есть когда отказало\n  3695\t                # окружение. Человек шёл разбирать постановку вместо\n  3696\t                # инфраструктуры. Признак лежит на диске, поэтому спрашиваем\n  3697\t                # активность: воркфлоу файловой системы не видит.\n  3698\t                #\n  3699\t                # Уточнение НЕ ИМЕЕТ ПРАВА подменить собой исходный отказ:\n  3700\t                # диагностика, способная сломать то, что диагностирует, хуже\n  3701\t                # её отсутствия. Не вышло — докладываем прежним текстом.\n  3702\t                try:\n  3703\t                    reason = await workflow.execute_activity(\n  3704\t                        activities.dev_empty_run_reason,\n  3705\t                        args=[issue],\n  3706\t                        start_to_close_timeout=timedelta(seconds=30),\n  3707\t                        retry_policy=cheap,\n  3708\t                    )\n  3709\t                except Exception as e:                   # noqa: BLE001\n  3710\t                    workflow.logger.warning(\n  3711\t                        \"причину пустого прогона выяснить не удалось: %s\",\n  3712\t                        _failure_reason(e))\n  3713\t            raise ApplicationError(reason)\n  3714\t        return number",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.46,
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 54825
  }
}

## Ход 9 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py:2990-3060"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py:2990-3060",
  "file": "worker/workflows.py",
  "kind": "range",
  "start_line": 2990,
  "end_line": 3060,
  "total_lines": 4032,
  "source": "  2990\t                )\n  2991\t        except WorkflowAlreadyStartedError:\n  2992\t            # Разработка по этому Issue уже идёт — второй дорогой прогон не\n  2993\t            # нужен. Но вернуть ТЕКУЩУЮ фазу здесь нельзя: `_enter` на той же\n  2994\t            # фазе — короткое замыкание без единого await (ни активности, ни\n  2995\t            # таймера, см. начало метода), а автостарт вызывает этот метод\n  2996\t            # СНОВА на следующем же витке `while True`, без парковки между\n  2997\t            # попытками. Получался бы спин на скорости round-trip к серверу:\n  2998\t            # WorkflowAlreadyStarted на каждой попытке, история распухает до\n  2999\t            # continue-as-new и после него — по новой, потому что причина\n  3000\t            # (чужой прогон всё ещё жив) никуда не делась.\n  3001\t            #\n  3002\t            # Разработка ПО ФАКТУ идёт — иначе не было бы этой ошибки, просто\n  3003\t            # ведёт её не этот прогон (человек снял зависший `IssueLifecycle`,\n  3004\t            # а дочерний `develop-*` пережил его благодаря ParentClosePolicy.\n  3005\t            # ABANDON). Честная фаза — `in-development`, тот же исход, что и\n  3006\t            # у режима `dispatch` ниже: результат придёт событием, а не\n  3007\t            # прямым возвратом. Переход `ready-for-dev -> in-development`\n  3008\t            # уже есть в таблице `shared/lifecycle.py` (инициатор `human`, но\n  3009\t            # `transition()` не проверяет, кто зовёт). Дальше фаза уходит в\n  3010\t            # `_phase_park` и честно ждёт сигнала — спин обрывается самим\n  3011\t            # устройством цикла, а не таймаутом.\n  3012\t            workflow.logger.info(\"development already running for %s#%s\",\n  3013\t                                 issue.repo, issue.issue_number)\n  3014\t            return (lifecycle.IN_DEVELOPMENT, \"in-development\", True)\n  3015\t        except Exception as e:\n  3016\t            # Раньше NotImplementedError отсюда ронял весь воркфлоу: цикл\n  3017\t            # исчезал, и Issue терял владельца состояния.\n  3018\t            reason = _failure_reason(e)\n  3019\t            workflow.logger.warning(\"передача в разработку не выполнена: %s\", reason)\n  3020\t            # Отчёт человеку, а не только метка фазы: до этого срыв передачи был\n  3021\t            # виден лишь как `phase:failed` в списке — отличить его от «ещё\n  3022\t            # работает» можно было только чтением логов контейнера.\n  3023\t            await workflow.execute_activity(\n  3024\t                activities.post_error_label,\n  3025\t                args=[issue, reason],\n  3026\t                start_to_close_timeout=timedelta(seconds=30),\n  3027\t                retry_policy=RetryPolicy(maximum_attempts=5),\n  3028\t            )\n  3029\t            return (lifecycle.FAILED, \"failed\", True)\n  3030\t        if pr_number is None:\n  3031\t            # Режим `dispatch`: работа идёт на чужой стороне, и о её исходе\n  3032\t            # придёт событие `pr-open`. Ждём в `in-development`.\n  3033\t            return (lifecycle.IN_DEVELOPMENT, \"in-development\", True)\n  3034\t        # Режим `local`: PR открыт прямо сейчас, ждать доклада не о чем — фаза\n  3035\t        # двигается сразу. Ревью доложит о себе само, уже из `pr-open`.\n  3036\t        self._pr_number = pr_number\n  3037\t        return (lifecycle.PR_OPEN, \"pr-open\", True)\n  3038\t\n  3039\t    async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None:\n  3040\t        \"\"\"Фаза `pr-review`: довести PR по замечаниям, пока они по делу.\n  3041\t\n  3042\t        Круг ведёт цикл, а не отдельный сервис: он уже владеет состоянием\n  3043\t        задачи и стоит здесь же. Отдельный сервис потребовал бы второй копии\n  3044\t        клона, раннера, прогона тестов и пуша — и ещё одного канала докладов.\n  3045\t\n  3046\t        Признак завершения — агент сам сказал, что правок не требуется. Тогда\n  3047\t        активность возвращает разбор (строку), а не `True`.\n  3048\t        \"\"\"\n  3049\t        if not self._pr_number or not deadlines.pr_fix_enabled:\n  3050\t            return await self._phase_park(issue, deadlines)\n  3051\t\n  3052\t        rounds = 0\n  3053\t        verdict = \"\"\n  3054\t        while rounds < deadlines.pr_fix_max_rounds:\n  3055\t            rounds += 1\n  3056\t            try:\n  3057\t                if workflow.patched(\"issue-lifecycle-prfix-child\"):\n  3058\t                    outcome = await workflow.execute_child_workflow(\n  3059\t                        IssuePrFix.run,\n  3060\t                        args=[issue.repo, self._pr_number, rounds],",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.16,
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 54825
  }
}

## Ход 10 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Что делает модуль shared/develop.py: какие функции work_branch, pr_body, clear_service_files, WORK_BRANCH — их сигнатуры и как формируется имя рабочей ветки и тело пул-реквеста? Какие ещё служебные помощники там есть для публикации разработки?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `clear_service_files`, `work_branch`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "shared/develop.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "shared/develop.py",
    "shared/repowise.py",
    "shared/memory.py",
    "shared/workflow_types.py",
    "worker/workflows.py"
  ],
  "retrieval": [
    {
      "path": "shared/develop.py",
      "title": "File: shared/develop.py",
      "summary": "Контракт активности Develop — разработка по подготовленному Issue.",
      "snippet": "# shared/develop.py\n\n## Overview\n\nКонтракт активности Develop — разработка по подготовленному Issue.\n\nResearch доводит Issue до системных требований и метки `ready-for-dev` (точка\nпередачи H1 протокол",
      "excerpt": "# shared/develop.py\n\n## Overview\n\nКонтракт активности Develop — разработка по подготовленному Issue.\n\nResearch доводит Issue до системных требований и метки `ready-for-dev` (точка\nпередачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.\n\nКод пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса\nпоражения, и отсюда два режима:\n\n`local` (умолчание) — прогон идёт **одноразовым контейнером на своём же\nсервере**. Контур получается замкнутым: репозиторий обслуживается целиком\nвнутри стенда, без чужих раннеров и без минут GitHub.\n\n`dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся\nдля репозиториев, где стенда нет.\n\nПочему отдельный контейнер, а не воркер. Аналитика (`claude -p`) пишет\nдокументы, и её соседство с токенами безобидно. Агент разработки делает другое:\nон ИСПОЛНЯЕТ код репозитория — ставит зависимости, гоняет тесты. Внутри воркера\nэто означало бы выполнение произвольного кода чужого проекта рядом с\nGitHub-токеном и ключом модели. Поэтому прогон живёт минуты в отдельном\nконтейнере, видит только каталог своей задачи и умирает вместе с ней; коммит,\nпуш и PR делает воркер уже после — своими руками и своим токеном.\n\nМодуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как\n`shared/lifecycle.py` и `shared/agent_events.py`.\n\nIt exposes 47 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `LOCAL` | constant | LOCAL = \"local\" |\n| `DISPATCH` | constant | DISPATCH = \"dispatch\" |\n|",
      "score": 4.879,
      "key_symbols": [
        {
          "name": "LOCAL",
          "kind": "constant",
          "signature": "LOCAL = \"local\"",
          "docstring": "",
          "start_line": 34,
          "end_line": 34
        },
        {
          "name": "DISPATCH",
          "kind": "constant",
          "signature": "DISPATCH = \"dispatch\"",
          "docstring": "",
          "start_line": 35,
          "end_line": 35
        },
        {
          "name": "DEFAULT_WORKFLOW_FILE",
          "kind": "constant",
          "signature": "DEFAULT_WORKFLOW_FILE = \"openhands-resolver.yml\"",
          "docstring": "",
          "start_line": 40,
          "end_line": 40
        },
        {
          "name": "IN_DEVELOPMENT_LABEL",
          "kind": "constant",
          "signature": "IN_DEVELOPMENT_LABEL = \"in-development\"",
          "docstring": "",
          "start_line": 45,
          "end_line": 45,
          "source_excerpt": "IN_DEVELOPMENT_LABEL = \"in-development\""
        },
        {
          "name": "SERVICE_FILES",
          "kind": "constant",
          "signature": "SERVICE_FILES = (",
          "docstring": "",
          "start_line": 212,
          "end_line": 217,
          "source_excerpt": "SERVICE_FILES = (\n    \".task.md\",        # постановка, собранная контуром\n    \".followups.md\",   # находки агента для бэклога\n    \".verdict.md\",     # разбор замечаний ревью на круге правок\n    \".reflect.md\",     # намерения агента для слоя саморефлексии\n)"
        },
        {
          "name": "clear_service_files",
          "kind": "function",
          "signature": "def clear_service_files(clone_dir, keep_dir=None) -> list[str]:",
          "docstring": "Снять служебные файлы из рабочего дерева. Возвращает имена снятых.\n\n    Вызывается ПЕРЕД коммитом на обоих путях — и в разработке, и в круге\n    правок. Одна точка снятия вместо разрозненных: пропущенный файл здесь\n    означает не ошибку сборки, а тихо испорченный пул-реквест.\n\n    `keep_dir` — куда переложить файлы из `PRESERVED_FILES` вместо удаления.\n    Обычно это корень задачи: он лежит ВНЕ рабочего дерева git, поэтому в\n    коммит содержимое не попадёт, а прочитать его позже можно.",
          "start_line": 234,
          "end_line": 261,
          "source_excerpt": "def clear_service_files(clone_dir, keep_dir=None) -> list[str]:\n    \"\"\"Снять служебные файлы из рабочего дерева. Возвращает имена снятых.\n\n    Вызывается ПЕРЕД коммитом на обоих путях — и в разработке, и в круге\n    правок. Одна точка снятия вместо разрозненных: пропущенный файл здесь\n    означает не ошибку сборки, а тихо испорченный пул-реквест.\n\n    `keep_dir` — куда переложить файлы из `PRESERVED_FILES` вместо удаления.\n    Обычно это корень задачи: он лежит ВНЕ рабочего дерева git, поэтому в\n    коммит содержимое не попадёт, а прочитать его позже можно.\n    \"\"\"\n    from pathlib import Path\n    removed = []\n    for name in SERVICE_FILES:\n        path = Path(clone_dir) / name\n        if not path.exists():\n            continue\n        if keep_dir is not None and name in PRESERVED_FILES:\n            target = Path(keep_dir) / name\n            try:\n                target.write_bytes(path.read_bytes())\n            except OSError:\n                # Не сохранили — не повод оставить файл в дереве: в коммите он\n                # опаснее, чем потеря его содержимого.\n                pass\n        path.unlink(missing_ok=True)\n        removed.append(name)\n    return removed"
        },
        {
          "name": "work_branch",
          "kind": "function",
          "signature": "def work_branch(issue_number: int) -> str:",
          "docstring": "",
          "start_line": 316,
          "end_line": 317,
          "source_excerpt": "def work_branch(issue_number: int) -> str:\n    return f\"feature/{issue_number}-openhands\""
        },
        {
          "name": "dispatch_inputs",
          "kind": "function",
          "signature": "def dispatch_inputs(issue_number: int, *, branch: str, priority: str = \"\") -> dict[str, str]:",
          "docstring": "Входы прогона для режима `dispatch`. Только строки: `workflow_dispatch`\n    других не принимает.",
          "start_line": 383,
          "end_line": 390
        },
        {
          "name": "handoff_comment",
          "kind": "function",
          "signature": "def handoff_comment(issue_number: int, *, repo: str, branch: str, where: str) -> str:",
          "docstring": "Комментарий в Issue о старте разработки.",
          "start_line": 393,
          "end_line": 406
        },
        {
          "name": "pr_body",
          "kind": "function",
          "signature": "def pr_body(issue_number: int, *, branch: str) -> str:",
          "docstring": "",
          "start_line": 409,
          "end_line": 416,
          "source_excerpt": "def pr_body(issue_number: int, *, branch: str) -> str:\n    return (\n        f\"Closes #{issue_number}\\n\\n\"\n        f\"Разработку вёл OpenHands по системным требованиям из `{branch or '—'}`.\\n\"\n        \"Найденные по дороге edge-кейсы в этой ветке не чинились — они собраны \"\n        f\"строками в секции GROW тела #{issue_number} и ждут гейта приёмки.\\n\\n\"\n        f\"<sub>origin: agent · root-issue: #{issue_number}</sub>\\n\"\n    )"
        }
      ]
    },
    {
      "path": "shared/repowise.py",
      "title": "File: shared/repowise.py",
      "summary": "Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.",
      "snippet": "# shared/repowise.py\n\n## Overview\n\nКлиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.\n\nПрокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по\nworkspace, треб",
      "excerpt": "# shared/repowise.py\n\n## Overview\n\nКлиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.\n\nПрокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по\nworkspace, требует токен и идентификатор сессии, журналирует каждый обмен и\nрендерит из журнала артефакт диалога.\n\nПочему транскрипт забирается у прокси, а не пишется агентом. Guard стадии\n(`worker/activities.py`, проверка ожидаемого артефакта в `run_fnr_stage`) умеет\nпроверить только существование файла и его размер; отличить полный транскрипт\nот правдоподобного пересказа ему не с чем. Журнал на стороне прокси делает\nполноту свойством построения, а не добросовестности модели.\n\nМодуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и\n`shared/agent_events.py`. Он вызывается и из воркера, и из подготовки каталога\nразработки; лишний импорт втащил бы клиент GitHub вместе с токеном туда, где\nего быть не должно.\n\nIt exposes 20 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `ANALYSIS` | constant | ANALYSIS = \"analysis\" |\n| `DEVELOP` | constant | DEVELOP = \"openhands\" |\n| `CONTOUR` | constant | CONTOUR = \"contour\" |\n| `PRODUCT` | constant | PRODUCT = \"product\" |\n| `DEFAULT_MAX_TURNS` | constant | DEFAULT_MAX_TURNS = 12 |\n| `PROBE_TIMEOUT_SEC` | constant | PROBE_TIMEOUT_SEC = 5.0 |\n| `TRANSCRIPT_TIMEOUT_SEC` | constant | TRANSCRIPT_TIMEOUT_SEC = 30.0 |\n| `SERVER_NAME` | constant | SERVER_NAME = \"repowise\" |\n| `proxy_bas",
      "score": 2.278,
      "key_symbols": [
        {
          "name": "DEVELOP",
          "kind": "constant",
          "signature": "DEVELOP = \"openhands\"",
          "docstring": "",
          "start_line": 33,
          "end_line": 33,
          "source_excerpt": "DEVELOP = \"openhands\""
        },
        {
          "name": "SERVER_NAME",
          "kind": "constant",
          "signature": "SERVER_NAME = \"repowise\"",
          "docstring": "",
          "start_line": 47,
          "end_line": 47,
          "source_excerpt": "SERVER_NAME = \"repowise\""
        },
        {
          "name": "session_id",
          "kind": "function",
          "signature": "def session_id(repo: str, issue_number: int, agent: str) -> str:",
          "docstring": "Детерминированный идентификатор сессии.\n\n    Детерминированный по той же причине, что и идентификаторы прогонов\n    (`shared/workflow_ids.py`): повторный запуск по тому же Issue должен\n    попадать в ту же сессию, а не плодить осиротевшие журналы.\n\n    Слэш в имени репозитория заменяется на `__` — идентификатор уезжает в\n    query-параметр, и кодировать его на каждой стороне незачем. Тот же приём\n    применяется для каталога прогона (`worker/activities.py`, `_workspace_dir`).",
          "start_line": 91,
          "end_line": 102
        },
        {
          "name": "transcript",
          "kind": "function",
          "signature": "def transcript(session: str) -> str | None:",
          "docstring": "Отрендеренный транскрипт сессии либо None, если получить не удалось.\n\n    None — не ошибка вызывающего: он подставит артефакт с отметкой о том, что\n    обращений не было (см. забор транскрипта разработки в `worker/activities.py`).",
          "start_line": 168,
          "end_line": 184
        }
      ]
    },
    {
      "path": "shared/memory.py",
      "title": "File: shared/memory.py",
      "summary": "Клиент слоя саморефлексии — правила организации и запись об итерации.",
      "snippet": "# shared/memory.py\n\n## Overview\n\nКлиент слоя саморефлексии — правила организации и запись об итерации.\n\nСлой живёт отдельным сервисом (`po-helper-org/harness-memory-base`) и хранит\nдве вещи: правила и",
      "excerpt": "# shared/memory.py\n\n## Overview\n\nКлиент слоя саморефлексии — правила организации и запись об итерации.\n\nСлой живёт отдельным сервисом (`po-helper-org/harness-memory-base`) и хранит\nдве вещи: правила и принципы, накопленные конкретной организацией, и след того,\nчем кончались итерации агентов. Перед работой агент берёт выжимку из правил,\nпосле работы оставляет запись.\n\n**Слой опционален целиком.** Пустой `MEMORY_BASE_URL` — ни одного сетевого\nвызова, ни одного изменения в постановках. Это умолчание, и оно закреплено\nтестом: постановка при выключенном слое обязана быть побайтово равна постановке\nбез слоя.\n\n**Отказ слоя не роняет прогон.** Недоступность, таймаут, любой код ответа кроме\nдвухсотых дают пустой результат и предупреждение в лог. Агент работает без\nправил. То же решение, что у интеграции с индексом кода: опциональный источник\nобязан деградировать, а не отказывать.\n\nМодуль намеренно чистый — только stdlib, ни Temporal, ни GitHub. Как\n`shared/repowise.py` и `shared/develop.py`: он вызывается из подготовки каталога\nразработки, и лишний импорт втащил бы туда клиент GitHub вместе с токеном.\nОтдельная причина не брать `httpx`: у образа воркера его нет, а тянуть\nзависимость ради четырёх запросов дороже, чем написать их на `urllib`.\n\nIt exposes 18 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `ISSUE` | constant | ISSUE = \"issue\" |\n| `DEVELOP` | constant | DEVELOP = \"develop\" |\n| `REVIEW` | constant | REVIEW = \"review\" |\n| `DELIVERY` | cons",
      "score": 2.255
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | -",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 2.065
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 48 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `AGENT_RESEARCH` | constant | AGENT_RESEARCH = \"__agent__:research\" |\n| `HOWTODEMO_TASK_QUEUE` | constant | HOWTODEMO_TASK_QUEUE = \"howtodemo\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | c",
      "score": 2.016
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "shared/develop.py",
      "why_relevant": "Implements function clear_service_files.",
      "score": 4.879
    },
    {
      "file": "shared/repowise.py",
      "why_relevant": "Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода..",
      "score": 2.278
    },
    {
      "file": "shared/memory.py",
      "why_relevant": "Клиент слоя саморефлексии — правила организации и запись об итерации..",
      "score": 2.255
    }
  ],
  "code_rationale": [
    {
      "path": "shared/develop.py",
      "lines": [
        1,
        12
      ],
      "comment": "Контракт активности Develop — разработка по подготовленному Issue. Research доводит Issue до системных требований и метки `ready-for-dev` (точка передачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR. Код пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса поражения, и отсюда два режима: `local` (умолчание) — прогон идёт **одноразовым контейнером на своём же сервере**. Контур получается замкнутым: репозиторий обслуживается целиком внутри стенда, без чужих раннеров и без минут GitHub. `dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся для репозиториев, где стенда нет. Почему отдельный контейнер, а не воркер. Аналитика (`claude -p`) пишет документы, и её соседство с токенами безобидно. Агент разработки делает другое: он ИСП…",
      "matched_terms": [
        "develop",
        "shared"
      ]
    },
    {
      "path": "shared/repowise.py",
      "lines": [
        1,
        12
      ],
      "comment": "Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода. Прокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по workspace, требует токен и идентификатор сессии, журналирует каждый обмен и рендерит из журнала артефакт диалога. Почему транскрипт забирается у прокси, а не пишется агентом. Guard стадии (`worker/activities.py`, проверка ожидаемого артефакта в `run_fnr_stage`) умеет проверить только существование файла и его размер; отличить полный транскрипт от правдоподобного пересказа ему не с чем. Журнал на стороне прокси делает полноту свойством построения, а не добросовестности модели. Модуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и `shared/agent_events.py`. Он вызывается и из воркера, и из подготовки каталога разработки; ли…",
      "matched_terms": [
        "develop",
        "shared"
      ]
    },
    {
      "path": "shared/memory.py",
      "lines": [
        1,
        12
      ],
      "comment": "Клиент слоя саморефлексии — правила организации и запись об итерации. Слой живёт отдельным сервисом (`po-helper-org/harness-memory-base`) и хранит две вещи: правила и принципы, накопленные конкретной организацией, и след того, чем кончались итерации агентов. Перед работой агент берёт выжимку из правил, после работы оставляет запись. **Слой опционален целиком.** Пустой `MEMORY_BASE_URL` — ни одного сетевого вызова, ни одного изменения в постановках. Это умолчание, и оно закреплено тестом: постановка при выключенном слое обязана быть побайтово равна постановке без слоя. **Отказ слоя не роняет прогон.** Недоступность, таймаут, любой код ответа кроме двухсотых дают пустой результат и предупреждение в лог. Агент работает без правил. То же решение, что у интеграции с индексом кода: опциональный…",
      "matched_terms": [
        "develop",
        "shared"
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "lines": [
        291,
        291
      ],
      "comment": "\"local\" | \"dispatch\" (`shared/develop.py`)",
      "matched_terms": [
        "develop",
        "shared"
      ]
    },
    {
      "path": "worker/workflows.py",
      "lines": [
        465,
        472
      ],
      "comment": "Отказ гейта критерия приёмки (`_start_development`) уже показан хотя бы раз в ЭТОЙ серии подряд идущих отказов. Значение по умолчанию — для свежего прогона; при continue-as-new оно приезжает из `carried.criterion_gate_notified` в `run()` — см. её докстринг в `shared/workflow_types.py` за тем, почему флаг ОБЯЗАН переживать перезапуск (находка 2 ревью: без переноса дедупликация «одно сообщение на серию» ломается именно на задаче, застрявшей на этом гейте, — не в редком случае, а в обычном).",
      "matched_terms": [
        "develop",
        "shared"
      ]
    },
    {
      "path": "worker/workflows.py",
      "lines": [
        2992,
        3003
      ],
      "comment": "Разработка по этому Issue уже идёт — второй дорогой прогон не нужен. Но вернуть ТЕКУЩУЮ фазу здесь нельзя: `_enter` на той же фазе — короткое замыкание без единого await (ни активности, ни таймера, см. начало метода), а автостарт вызывает этот метод СНОВА на следующем же витке `while True`, без парковки между попытками. Получался бы спин на скорости round-trip к серверу: WorkflowAlreadyStarted на каждой попытке, история распухает до continue-as-new и после него — по новой, потому что причина (чужой прогон всё ещё жив) никуда не делась. Разработка ПО ФАКТУ идёт — иначе не было бы этой ошибки, просто ведёт её не этот прогон (человек снял зависший `IssueLifecycle`, а дочерний `develop-*` пережил его благодаря ParentClosePolicy. ABANDON). Честная фаза — `in-development`, тот же исход, что и у…",
      "matched_terms": [
        "develop",
        "shared"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "shared/develop.py",
      "name": "clear_service_files",
      "lines": [
        234,
        261
      ],
      "source": "def clear_service_files(clone_dir, keep_dir=None) -> list[str]:\n    \"\"\"Снять служебные файлы из рабочего дерева. Возвращает имена снятых.\n\n    Вызывается ПЕРЕД коммитом на обоих путях — и в разработке, и в круге\n    правок. Одна точка снятия вместо разрозненных: пропущенный файл здесь\n    означает не ошибку сборки, а тихо испорченный пул-реквест.\n\n    `keep_dir` — куда переложить файлы из `PRESERVED_FILES` вместо удаления.\n    Обычно это корень задачи: он лежит ВНЕ рабочего дерева git, поэтому в\n    коммит содержимое не попадёт, а прочитать его позже можно.\n    \"\"\"\n    from pathlib import Path\n    removed = []\n    for name in SERVICE_FILES:\n        path = Path(clone_dir) / name\n        if not path.exists():\n            continue\n        if keep_dir is not None and name in PRESERVED_FILES:\n            target = Path(keep_dir) / name\n            try:\n                target.write_bytes(path.read_bytes())\n            except OSError:\n                # Не сохранили — не повод оставить файл в дереве: в коммите он\n                # опаснее, чем потеря его содержимого.\n                pass\n        path.unlink(missing_ok=True)\n        removed.append(name)\n    return removed"
    },
    {
      "path": "shared/develop.py",
      "name": "work_branch",
      "lines": [
        316,
        317
      ],
      "source": "def work_branch(issue_number: int) -> str:\n    return f\"feature/{issue_number}-openhands\""
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the clear_service_files body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 270.0,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "shared/develop.py",
      "lines": "34-416",
      "defines": "clear_service_files:234, work_branch:316, pr_body:409, min_free_mb:90, free_memory_mb:100, resource_shortage:119"
    },
    {
      "path": "shared/repowise.py",
      "lines": "33-184",
      "defines": "proxy_base:50, agent_token:54, enabled:58, max_turns:67, workspace_for:78, session_id:91"
    },
    {
      "path": "shared/memory.py",
      "defines": "Rules:90, control_arm:73, base_url:105, token:109, timeout_sec:113, enabled:120"
    },
    {
      "path": "shared/workflow_types.py",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:116, OrphanEventInput:194"
    },
    {
      "path": "worker/workflows.py",
      "defines": "WebhookAudit:307, OrphanAgentEvent:330, CommentAck:351, IssueLifecycle:374, IssueDevelopment:3540, IssuePrFix:3718"
    }
  ]
}

## Ход 11 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Какие тесты покрывают шаги воркфлоу разработки IssueDevelopment — dev_tests, dev_publish, пустой прогон, обработку ошибки стадии? В каких файлах (test_dev_*), какие фикстуры и подмены они используют (FakeGitHub, activities, workflow environment), и какой из них ближе всего по устройству к сценарию «шаг упал — воркфлоу что-то публикует в finally»?"
}
```

**Ответ:**

{
  "answer": "`FakeGitHub` has 2 definition(s) in this repo; all are inlined in symbol_bodies below. They are distinct implementations, so pick the one for your context.",
  "citations": [
    "tests/test_e2e_issue_lifecycle.py",
    "tests/test_estimate_activities.py"
  ],
  "confidence": "high",
  "retrieval_quality": "weak",
  "grounding": "exact_symbol",
  "symbol_bodies": [
    {
      "path": "tests/test_e2e_issue_lifecycle.py",
      "name": "FakeGitHub",
      "lines": [
        82,
        150
      ],
      "source": "class FakeGitHub:\n    \"\"\"Состояние Issue в памяти. Ведёт себя как GitHub в том, что важно\n    пайплайну: метки накапливаются и снимаются, комментарии дописываются.\"\"\"\n\n    def __init__(self) -> None:\n        self.labels: list[str] = []\n        self.comments: list[str] = []\n        self.state = \"open\"\n        self.reactions: list[tuple[int, str]] = []\n        self.branches: dict[str, dict[str, str]] = {}\n        self.calls: list[str] = []\n\n    # --- мутации ---\n    def post_comment(self, repo, issue_number, body):\n        self.calls.append(\"post_comment\")\n        self.comments.append(body)\n\n    def add_label(self, repo, issue_number, label):\n        self.calls.append(f\"add_label:{label}\")\n        if label not in self.labels:\n            self.labels.append(label)\n\n    def remove_label(self, repo, issue_number, label):\n        self.calls.append(f\"remove_label:{label}\")\n        if label in self.labels:\n            self.labels.remove(label)\n\n    def set_labels(self, repo, issue_number, *, add=(), remove=()):\n        \"\"\"Смена набора одной операцией: делегирует общему двойнику\n        (tests/conftest.py), который ставит через add_label и снимает через\n        remove_label, так что self.labels/self.calls остаются той же точкой\n        правды, которую читают остальные тесты этого файла.\"\"\"\n        make_fake_set_labels(self.add_label, self.remove_label)(\n            repo, issue_number, add=add, remove=remove)\n\n    def close_issue(self, repo, issue_number):\n        self.state = \"closed\"\n\n    def add_reaction(self, repo, comment_id, content=\"eyes\"):\n        self.reactions.append((comment_id, content))\n\n    def push_artifacts_to_branch(self, repo, branch, files, message):\n        self.calls.append(f\"push:{branch}\")\n        self.branches.setdefault(branch, {}).update(files)\n\n    # --- чтения ---\n    def get_issue(self, repo, issue_number):\n        return {\"number\": issue_number, \"title\": \"Ревизия оплаты\",\n                \"body\": \"нужен ретрай платежей\", \"state\": self.state,\n                \"labels\": [{\"name\": name} for name in self.labels]}\n\n    def get_issue_body(self, repo, issue_number):\n        return \"нужен ретрай платежей\"\n\n    def list_comments(self, repo, issue_number, limit=50):\n        return [{\"user\": {\"login\": \"alice\", \"type\": \"User\"}, \"body\": c,\n                 \"created_at\": \"2026-08-09T10:00:00Z\"} for c in self.comments]\n\n    def list_linked_prs(self, repo, issue_number, limit=20):\n        return []\n\n    def search_candidates(self, repo, query, limit=15):\n        return []  # дублей нет — ветка duplicate_check без LLM\n\n    def branch_exists(self, repo, branch):\n        return branch in self.branches\n\n    def get_file(self, repo, path, ref):\n        return self.branches.get(ref, {}).get(path)"
    },
    {
      "path": "tests/test_estimate_activities.py",
      "name": "FakeGitHub",
      "lines": [
        10,
        39
      ],
      "source": "class FakeGitHub:\n    def __init__(self, issue=None, comments=None, branches=(), files=None):\n        self.issue = issue or {\"title\": \"Заголовок\", \"body\": \"Описание\", \"labels\": []}\n        self.comments = comments or []\n        self.branches = set(branches)\n        self.files = files or {}\n        self.reactions = []\n        self.posted = []\n        self.labels = []\n\n    def get_issue(self, repo, number):\n        return self.issue\n\n    def list_comments(self, repo, number, limit=50):\n        return self.comments[:limit]\n\n    def branch_exists(self, repo, branch):\n        return branch in self.branches\n\n    def get_file(self, repo, path, ref):\n        return self.files.get(path)\n\n    def add_reaction(self, repo, comment_id, content=\"eyes\"):\n        self.reactions.append((comment_id, content))\n\n    def post_comment(self, repo, number, body):\n        self.posted.append(body)\n\n    def add_label(self, repo, number, label):\n        self.labels.append(label)"
    }
  ],
  "fallback_targets": [
    "tests/test_e2e_issue_lifecycle.py",
    "tests/test_estimate_activities.py"
  ],
  "retrieval": [],
  "note": "2 definition(s) of FakeGitHub exist (exact-name index scan; this is the complete set of DEFINITIONS). 2 inlined below in symbol_bodies as live source; use them directly, no verification Read. If the question was about something other than these definitions, candidates holds the files retrieval ranked for it.",
  "_meta": {
    "timing_ms": 1345.0,
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "711-3525",
      "defines": "dev_tests:3509, dev_publish:3519, GateExtraction:94, ClassificationExtraction:99, DuplicateCandidate:104, DuplicateExtraction:110"
    },
    {
      "path": "worker/workflows.py",
      "lines": "2508-3714",
      "defines": "IssueDevelopment:3540, WebhookAudit:307, OrphanAgentEvent:330, CommentAck:351, IssueLifecycle:374, IssuePrFix:3718"
    },
    {
      "path": "tests/test_estimate_activities.py",
      "defines": "FakeGitHub:10, comment:42, fake:47, test_ack_puts_eyes_on_the_command_comment:56, test_context_carries_title_body_and_labels:61, test_bot_comments_and_commands_are_excluded_from_the_thread:69"
    },
    {
      "path": "worker/worker.py",
      "defines": "main:126, DEVELOP_ACTIVITIES:44"
    },
    {
      "path": "shared/sentry_setup.py",
      "defines": "configure:106, event_url:143, debug_reference:158, capture_pipeline_failure:173, capture_analysis_failure:198, capture_estimate_failure:221"
    }
  ]
}

## Ход 12 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 12,
  "query": "tests/test_dev",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "Query names identifier(s) 'test_dev' but nothing matched. Search the identifier alone with mode=\"symbol\", then pipe the hit into get_symbol for its body. For an exhaustive every-usage sweep, Grep the literal name."
}

## Ход 13 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "tests/test_dev_empty_run.py",
    "tests/test_dev_handoff_once.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "tests/test_dev_empty_run.py": {
      "target": "tests/test_dev_empty_run.py",
      "type": "file",
      "docs": {
        "symbols": [
          {
            "name": "ROOT",
            "kind": "constant",
            "signature": "ROOT = Path(__file__).resolve().parent.parent",
            "line": 15,
            "symbol_id": "tests/test_dev_empty_run.py::ROOT"
          },
          {
            "name": "_conversation",
            "kind": "function",
            "signature": "def _conversation(task_dir: Path, with_events: bool) -> None",
            "line": 21,
            "symbol_id": "tests/test_dev_empty_run.py::_conversation"
          },
          {
            "name": "test_agent_that_never_moved_is_not_blamed_for_inaction",
            "kind": "function",
            "signature": "def test_agent_that_never_moved_is_not_blamed_for_inaction(tmp_path)",
            "line": 31,
            "symbol_id": "tests/test_dev_empty_run.py::test_agent_that_never_moved_is_not_blamed_for_inaction"
          },
          {
            "name": "test_agent_that_worked_and_changed_nothing_is_reported_as_such",
            "kind": "function",
            "signature": "def test_agent_that_worked_and_changed_nothing_is_reported_as_such(tmp_path)",
            "line": 38,
            "symbol_id": "tests/test_dev_empty_run.py::test_agent_that_worked_and_changed_nothing_is_reported_as_such"
          },
          {
            "name": "test_missing_conversation_counts_as_never_started",
            "kind": "function",
            "signature": "def test_missing_conversation_counts_as_never_started(tmp_path)",
            "line": 43,
            "symbol_id": "tests/test_dev_empty_run.py::test_missing_conversation_counts_as_never_started"
          },
          {
            "name": "test_two_reasons_are_different_texts",
            "kind": "function",
            "signature": "def test_two_reasons_are_different_texts()",
            "line": 48,
            "symbol_id": "tests/test_dev_empty_run.py::test_two_reasons_are_different_texts"
          },
          {
            "name": "test_run_is_refused_when_the_host_is_out_of_memory",
            "kind": "function",
            "signature": "def test_run_is_refused_when_the_host_is_out_of_memory(monkeypatch)",
            "line": 55,
            "symbol_id": "tests/test_dev_empty_run.py::test_run_is_refused_when_the_host_is_out_of_memory"
          },
          {
            "name": "test_enough_memory_means_no_objection",
            "kind": "function",
            "signature": "def test_enough_memory_means_no_objection(monkeypatch)",
            "line": 63,
            "symbol_id": "tests/test_dev_empty_run.py::test_enough_memory_means_no_objection"
          },
          {
            "name": "test_check_is_switched_off_by_zero",
            "kind": "function",
            "signature": "def test_check_is_switched_off_by_zero(monkeypatch)",
            "line": 69,
            "symbol_id": "tests/test_dev_empty_run.py::test_check_is_switched_off_by_zero"
          },
          {
            "name": "test_unmeasurable_memory_does_not_block_the_run",
            "kind": "function",
            "signature": "def test_unmeasurable_memory_does_not_block_the_run(monkeypatch)",
            "line": 76,
            "symbol_id": "tests/test_dev_empty_run.py::test_unmeasurable_memory_does_not_block_the_run"
          },
          {
            "name": "test_broken_threshold_falls_back_to_the_default",
            "kind": "function",
            "signature": "def test_broken_threshold_falls_back_to_the_default(monkeypatch)",
            "line": 83,
            "symbol_id": "tests/test_dev_empty_run.py::test_broken_threshold_falls_back_to_the_default"
          },
          {
            "name": "acts",
            "kind": "function",
            "signature": "def acts(monkeypatch)",
            "line": 91,
            "symbol_id": "tests/test_dev_empty_run.py::acts"
          },
          {
            "name": "_issue",
            "kind": "function",
            "signature": "def _issue()",
            "line": 98,
            "symbol_id": "tests/test_dev_empty_run.py::_issue"
          },
          {
            "name": "test_dead_proxy_means_no_mcp_config_at_all",
            "kind": "function",
            "signature": "def test_dead_proxy_means_no_mcp_config_at_all(acts, monkeypatch, tmp_path)",
            "line": 105,
            "symbol_id": "tests/test_dev_empty_run.py::test_dead_proxy_means_no_mcp_config_at_all"
          },
          {
            "name": "test_live_proxy_still_gets_its_config",
            "kind": "function",
            "signature": "def test_live_proxy_still_gets_its_config(acts, monkeypatch, tmp_path)",
            "line": 112,
            "symbol_id": "tests/test_dev_empty_run.py::test_live_proxy_still_gets_its_config"
          },
          {
            "name": "test_disabled_integration_writes_nothing_as_before",
            "kind": "function",
            "signature": "def test_disabled_integration_writes_nothing_as_before(acts, monkeypatch, tmp_path)",
            "line": 119,
            "symbol_id": "tests/test_dev_empty_run.py::test_disabled_integration_writes_nothing_as_before"
          }
        ],
        "summary": "test_dev_empty_run.py: functions _conversation, test_agent_that_never_moved_is_not_blamed_for_inaction, test_agent_that_worked_and_changed_nothing_is_reported_as_such (+12 more)."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 7
      },
      "freshness": {
        "confidence_score": null,
        "freshness_status": null,
        "is_stale": null
      },
      "architectural_layer": {
        "name": "Test",
        "description": "",
        "role": "entry_point"
      },
      "episodes": 1
    },
    "tests/test_dev_handoff_once.py": {
      "target": "tests/test_dev_handoff_once.py",
      "type": "file",
      "docs": {
        "symbols": [
          {
            "name": "_issue",
            "kind": "function",
            "signature": "def _issue() -> IssueInput",
            "line": 19,
            "symbol_id": "tests/test_dev_handoff_once.py::_issue"
          },
          {
            "name": "test_announce_is_skipped_when_already_in_development",
            "kind": "function",
            "signature": "def test_announce_is_skipped_when_already_in_development(monkeypatch)",
            "line": 26,
            "symbol_id": "tests/test_dev_handoff_once.py::test_announce_is_skipped_when_already_in_development"
          },
          {
            "name": "test_announce_posts_on_the_first_handoff",
            "kind": "function",
            "signature": "def test_announce_posts_on_the_first_handoff(monkeypatch)",
            "line": 39,
            "symbol_id": "tests/test_dev_handoff_once.py::test_announce_posts_on_the_first_handoff"
          },
          {
            "name": "test_announce_speaks_up_when_labels_are_unreadable",
            "kind": "function",
            "signature": "def test_announce_speaks_up_when_labels_are_unreadable(monkeypatch)",
            "line": 52,
            "symbol_id": "tests/test_dev_handoff_once.py::test_announce_speaks_up_when_labels_are_unreadable"
          },
          {
            "name": "test_git_failure_carries_stderr",
            "kind": "function",
            "signature": "def test_git_failure_carries_stderr(monkeypatch, tmp_path)",
            "line": 71,
            "symbol_id": "tests/test_dev_handoff_once.py::test_git_failure_carries_stderr"
          },
          {
            "name": "test_git_failure_does_not_leak_the_token",
            "kind": "function",
            "signature": "def test_git_failure_does_not_leak_the_token(monkeypatch, tmp_path)",
            "line": 87,
            "symbol_id": "tests/test_dev_handoff_once.py::test_git_failure_does_not_leak_the_token"
          },
          {
            "name": "test_git_returns_result_when_check_is_off",
            "kind": "function",
            "signature": "def test_git_returns_result_when_check_is_off(monkeypatch, tmp_path)",
            "line": 103,
            "symbol_id": "tests/test_dev_handoff_once.py::test_git_returns_result_when_check_is_off"
          }
        ],
        "summary": "test_dev_handoff_once.py: functions _issue, test_announce_is_skipped_when_already_in_development, test_announce_posts_on_the_first_handoff (+4 more)."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 14
      },
      "freshness": {
        "confidence_score": null,
        "freshness_status": null,
        "is_stale": null
      },
      "architectural_layer": {
        "name": "Test",
        "description": "",
        "role": "entry_point"
      },
      "episodes": 1
    }
  },
  "_meta": {
    "timing_ms": 55.4,
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 14 · `search_codebase` · contour

**Запрос:**

```json
{
  "limit": 8,
  "mode": "symbol",
  "query": "IssueDevelopment workflow test"
}
```

**Ответ:**

{
  "results": [
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
      "score": 57.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_develop_workflow.py",
      "start_line": 21,
      "end_line": 21,
      "signature": "ISSUE = 39",
      "qualified_name": "tests.test_develop_workflow.ISSUE",
      "language": "python",
      "score": 57.51,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_answer_question.py::issue",
      "name": "issue",
      "kind": "function",
      "file": "tests/test_answer_question.py",
      "start_line": 11,
      "end_line": 13,
      "signature": "def issue()",
      "qualified_name": "tests.test_answer_question.issue",
      "language": "python",
      "score": 50.05,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_ask_question.py::issue",
      "name": "issue",
      "kind": "function",
      "file": "tests/test_ask_question.py",
      "start_line": 9,
      "end_line": 12,
      "signature": "def issue()",
      "qualified_name": "tests.test_ask_question.issue",
      "language": "python",
      "score": 50.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_gate_notification_activities.py::issue",
      "name": "issue",
      "kind": "function",
      "file": "tests/test_gate_notification_activities.py",
      "start_line": 37,
      "end_line": 40,
      "signature": "def issue()",
      "qualified_name": "tests.test_gate_notification_activities.issue",
      "language": "python",
      "score": 50.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_harness_answer_e2e.py::issue",
      "name": "issue",
      "kind": "function",
      "file": "tests/test_harness_answer_e2e.py",
      "start_line": 27,
      "end_line": 31,
      "signature": "def issue()",
      "qualified_name": "tests.test_harness_answer_e2e.issue",
      "language": "python",
      "score": 50.01,
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
      "symbol_id": "tests/test_develop_is_a_child.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_develop_is_a_child.py",
      "start_line": 33,
      "end_line": 33,
      "signature": "ISSUE = 39",
      "qualified_name": "tests.test_develop_is_a_child.ISSUE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "tests/test_bft_workflow.py"
    },
    {
      "path": "tests/test_develop_workflow.py"
    },
    {
      "path": "tests/test_answer_question.py"
    },
    {
      "path": "tests/test_ask_question.py"
    },
    {
      "path": "tests/test_gate_notification_activities.py"
    },
    {
      "path": "tests/test_harness_answer_e2e.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_develop_is_a_child.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'IssueDevelopment workflow test'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 15 · `get_risk` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/workflows.py",
    "worker/activities.py",
    "worker/github_client.py",
    "shared/develop.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/workflows.py": {
      "target": "worker/workflows.py",
      "hotspot_score": 0.9978,
      "dependents_count": 35,
      "co_change_partners": [
        {
          "file_path": "worker/activities.py",
          "weight": 42.28,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "worker/worker.py",
          "weight": 35.45,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "shared/workflow_types.py",
          "weight": 25.42,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "README.md",
          "weight": 16.74,
          "last_co_change": "2026-08-19",
          "has_import_link": false
        },
        {
          "file_path": "webhook/main.py",
          "weight": 15.14,
          "last_co_change": "2026-08-27",
          "has_import_link": false
        }
      ],
      "primary_owner": "ALeks ishmanov",
      "owner_pct": 0.6706,
      "recent_owner": "ALeks ishmanov",
      "recent_owner_pct": 0.6706,
      "bus_factor": 2,
      "contributor_count": 6,
      "trend": "increasing",
      "risk_type": "bug-prone",
      "change_pattern": "fix-heavy",
      "change_magnitude": {
        "lines_added_90d": 4812,
        "lines_deleted_90d": 781,
        "avg_commit_size": 65.8
      },
      "impact_surface": [
        {
          "file_path": "worker/worker.py",
          "pagerank": 0.01074,
          "is_entry_point": false
        },
        {
          "file_path": "scripts/replay_histories.py",
          "pagerank": 0.001344,
          "is_entry_point": false
        },
        {
          "file_path": "scripts/smoke_temporal.py",
          "pagerank": 0.001344,
          "is_entry_point": false
        }
      ],
      "defect_profile": {
        "fix_count": 41,
        "last_fix_days_ago": 0,
        "bug_magnet": true,
        "window": "6 months",
        "top_symbols": {
          "_phase_await_build": 8,
          "_phase_triage": 6,
          "_handle_comment_intent": 4
        }
      },
      "test_gap": true,
      "security_signals": [],
      "commit_count_capped": false,
      "risk_summary": "worker/workflows.py — 41 bug fixes in 6mo, last 0d ago (bug magnet), hotspot score 100% (increasing), 35 dependents, bug-prone, fix-heavy, 5 co-change partners, owned 67% by ALeks ishmanov",
      "health_score": 1.0,
      "top_biomarkers": [
        {
          "biomarker_type": "untested_hotspot",
          "severity": "critical",
          "function_name": null,
          "impact": 2.0
        },
        {
          "biomarker_type": "co_change_scatter",
          "severity": "high",
          "function_name": null,
          "impact": 1.48
        },
        {
          "biomarker_type": "prior_defect",
          "severity": "critical",
          "function_name": null,
          "impact": 1.37
        }
      ],
      "episodes": 41
    },
    "worker/activities.py": {
      "target": "worker/activities.py",
      "hotspot_score": 1.0,
      "dependents_count": 46,
      "co_change_partners": [
        {
          "file_path": "worker/workflows.py",
          "weight": 42.28,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "worker/worker.py",
          "weight": 34.96,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "shared/workflow_types.py",
          "weight": 22.69,
          "last_co_change": "2026-09-01",
          "has_import_link": true
        },
        {
          "file_path": "worker/github_client.py",
          "weight": 15.49,
          "last_co_change": "2026-08-31",
          "has_import_link": false
        },
        {
          "file_path": "webhook/main.py",
          "weight": 13.37,
          "last_co_change": "2026-08-27",
          "has_import_link": false
        }
      ],
      "primary_owner": "ALeks ishmanov",
      "owner_pct": 0.6911,
      "recent_owner": "ALeks ishmanov",
      "recent_owner_pct": 0.6911,
      "bus_factor": 2,
      "contributor_count": 6,
      "trend": "increasing",
      "risk_type": "bug-prone",
      "change_pattern": "feature-active",
      "change_magnitude": {
        "lines_added_90d": 6275,
        "lines_deleted_90d": 1206,
        "avg_commit_size": 60.8
      },
      "impact_surface": [
        {
          "file_path": "tests/conftest.py",
          "pagerank": 0.07163,
          "is_entry_point": false
        },
        {
          "file_path": "tests/test_estimate_activities.py",
          "pagerank": 0.01654,
          "is_entry_point": false
        },
        {
          "file_path": "worker/worker.py",
          "pagerank": 0.01074,
          "is_entry_point": false
        }
      ],
      "defect_profile": {
        "fix_count": 55,
        "last_fix_days_ago": 0,
        "bug_magnet": true,
        "window": "6 months",
        "top_symbols": {
          "answer_question": 8,
          "ask_question": 7,
          "_record_decision": 5
        }
      },
      "test_gap": false,
      "security_signals": [
        {
          "kind": "subprocess_shell_true",
          "severity": "high",
          "snippet": "result = subprocess.run(command, shell=True, cwd=str(clone_dir),"
        }
      ],
      "commit_count_capped": false,
      "risk_summary": "worker/activities.py — 55 bug fixes in 6mo, last 0d ago (bug magnet), hotspot score 100% (increasing), 46 dependents, bug-prone, feature-active, 5 co-change partners, owned 69% by ALeks ishmanov",
      "health_score": 1.0,
      "top_biomarkers": [
        {
          "biomarker_type": "untested_hotspot",
          "severity": "critical",
          "function_name": null,
          "impact": 2.0
        },
        {
          "biomarker_type": "co_change_scatter",
          "severity": "high",
          "function_name": null,
          "impact": 1.48
        },
        {
          "biomarker_type": "prior_defect",
          "severity": "critical",
          "function_name": null,
          "impact": 1.37
        }
      ],
      "episodes": 55
    },
    "worker/github_client.py": {
      "target": "worker/github_client.py",
      "hotspot_score": 0.987,
      "dependents_count": 24,
      "co_change_partners": [
        {
          "file_path": "worker/activities.py",
          "weight": 15.49,
          "last_co_change": "2026-08-31",
          "has_import_link": false
        },
        {
          "file_path": "worker/workflows.py",
          "weight": 11.52,
          "last_co_change": "2026-08-31",
          "has_import_link": false
        },
        {
          "file_path": "shared/workflow_types.py",
          "weight": 8.68,
          "last_co_change": "2026-08-19",
          "has_import_link": false
        },
        {
          "file_path": "README.md",
          "weight": 8.52,
          "last_co_change": "2026-08-19",
          "has_import_link": false
        },
        {
          "file_path": "worker/worker.py",
          "weight": 6.96,
          "last_co_change": "2026-08-31",
          "has_import_link": false
        }
      ],
      "primary_owner": "ALeks ishmanov",
      "owner_pct": 0.6296,
      "recent_owner": "ALeks ishmanov",
      "recent_owner_pct": 0.7027,
      "bus_factor": 2,
      "contributor_count": 3,
      "trend": "increasing",
      "risk_type": "bug-prone",
      "change_pattern": "feature-active",
      "change_magnitude": {
        "lines_added_90d": 1110,
        "lines_deleted_90d": 129,
        "avg_commit_size": 33.5
      },
      "impact_surface": [
        {
          "file_path": "worker/activities.py",
          "pagerank": 0.01827,
          "is_entry_point": false
        },
        {
          "file_path": "worker/worker.py",
          "pagerank": 0.01074,
          "is_entry_point": false
        },
        {
          "file_path": "worker/consolidation_activities.py",
          "pagerank": 0.006289,
          "is_entry_point": false
        }
      ],
      "defect_profile": {
        "fix_count": 14,
        "last_fix_days_ago": 1,
        "bug_magnet": true,
        "window": "6 months",
        "top_symbols": {
          "list_comments": 2,
          "list_linked_prs": 2,
          "GitCommandError": 1
        }
      },
      "test_gap": false,
      "security_signals": [],
      "commit_count_capped": false,
      "risk_summary": "worker/github_client.py — 14 bug fixes in 6mo, last 1d ago (bug magnet), hotspot score 99% (increasing), 24 dependents, bug-prone, feature-active, 5 co-change partners, owned 63% by ALeks ishmanov",
      "cross_repo_impact": {
        "cross_repo_consumers": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.609
          },
          {
            "repo": "poh-bft-writer",
            "file": "README.md",
            "strength": 0.444
          },
          {
            "repo": "poh-bft-writer",
            "file": "skills/bft-fast/resources/document_assembly.md",
            "strength": 0.428
          },
          {
            "repo": "poh-bft-writer",
            "file": "skills/bft-writer/examples/ideal_bft.md",
            "strength": 0.426
          },
          {
            "repo": "poh-bft-writer",
            "file": "skills/bft-writer/SKILL.md",
            "strength": 0.407
          }
        ],
        "affected_repos": [
          "poh-bft-writer",
          "poh-memory-engine"
        ]
      },
      "health_score": 2.25,
      "top_biomarkers": [
        {
          "biomarker_type": "untested_hotspot",
          "severity": "critical",
          "function_name": null,
          "impact": 2.0
        },
        {
          "biomarker_type": "co_change_scatter",
          "severity": "high",
          "function_name": null,
          "impact": 0.97
        },
        {
          "biomarker_type": "prior_defect",
          "severity": "critical",
          "function_name": null,
          "impact": 0.9
        }
      ],
      "episodes": 14
    },
    "shared/develop.py": {
      "target": "shared/develop.py",
      "hotspot_score": 0.9653,
      "dependents_count": 11,
      "co_change_partners": [
        {
          "file_path": "worker/activities.py",
          "weight": 10.33,
          "last_co_change": "2026-08-27",
          "has_import_link": true
        },
        {
          "file_path": "tests/test_develop.py",
          "weight": 4.65,
          "last_co_change": "2026-08-27",
          "has_import_link": true
        },
        {
          "file_path": "worker/workflows.py",
          "weight": 3.74,
          "last_co_change": "2026-08-26",
          "has_import_link": false
        },
        {
          "file_path": "tests/test_memory_integration.py",
          "weight": 2.87,
          "last_co_change": "2026-08-27",
          "has_import_link": true
        },
        {
          "file_path": "tests/test_develop_followups.py",
          "weight": 2.85,
          "last_co_change": "2026-08-27",
          "has_import_link": true
        }
      ],
      "primary_owner": "kibarik",
      "owner_pct": 0.6523,
      "recent_owner": "ALeks ishmanov",
      "recent_owner_pct": 0.4545,
      "bus_factor": 2,
      "contributor_count": 3,
      "trend": "increasing",
      "risk_type": "bug-prone",
      "change_pattern": "feature-active",
      "change_magnitude": {
        "lines_added_90d": 527,
        "lines_deleted_90d": 64,
        "avg_commit_size": 53.7
      },
      "impact_surface": [
        {
          "file_path": "worker/activities.py",
          "pagerank": 0.01827,
          "is_entry_point": false
        },
        {
          "file_path": "tests/test_estimate_activities.py",
          "pagerank": 0.01654,
          "is_entry_point": false
        },
        {
          "file_path": "worker/worker.py",
          "pagerank": 0.01074,
          "is_entry_point": false
        }
      ],
      "defect_profile": {
        "fix_count": 5,
        "last_fix_days_ago": 6,
        "bug_magnet": true,
        "window": "6 months",
        "top_symbols": {
          "agent_moved": 1,
          "dispatch_inputs": 1,
          "free_memory_mb": 1
        }
      },
      "test_gap": false,
      "security_signals": [],
      "commit_count_capped": false,
      "risk_summary": "shared/develop.py — 5 bug fixes in 6mo, last 6d ago (bug magnet), hotspot score 97% (increasing), 11 dependents, bug-prone, feature-active, 5 co-change partners, owned 65% by kibarik",
      "cross_repo_impact": {
        "cross_repo_consumers": [
          {
            "repo": "poh-infra",
            "file": "docs/harness/README.md",
            "strength": 0.493
          }
        ],
        "affected_repos": [
          "poh-infra"
        ]
      },
      "health_score": 5.65,
      "top_biomarkers": [
        {
          "biomarker_type": "prior_defect",
          "severity": "critical",
          "function_name": null,
          "impact": 2.0
        },
        {
          "biomarker_type": "nested_complexity",
          "severity": "medium",
          "function_name": "clear_service_files",
          "impact": 0.94
        },
        {
          "biomarker_type": "function_hotspot",
          "severity": "medium",
          "function_name": "clear_service_files",
          "impact": 0.81
        }
      ],
      "episodes": 5
    }
  },
  "global_hotspots": [
    {
      "file_path": "worker/worker.py",
      "hotspot_score": 0.9176,
      "primary_owner": "kibarik",
      "fix_count": 15,
      "last_fix_days_ago": 0,
      "bug_magnet": true
    },
    {
      "file_path": "tests/test_workflow_final_review_gate_findings.py",
      "hotspot_score": 0.9957,
      "primary_owner": "ALeks ishmanov",
      "fix_count": 12,
      "last_fix_days_ago": 1,
      "bug_magnet": true
    },
    {
      "file_path": "webhook/main.py",
      "hotspot_score": 0.9913,
      "primary_owner": "kibarik",
      "fix_count": 9,
      "last_fix_days_ago": 2,
      "bug_magnet": true
    },
    {
      "file_path": "shared/questions.py",
      "hotspot_score": 0.9805,
      "primary_owner": "ALeks ishmanov",
      "fix_count": 7,
      "last_fix_days_ago": 2,
      "bug_magnet": true
    },
    {
      "file_path": "shared/sentry_setup.py",
      "hotspot_score": 0.9414,
      "primary_owner": "ALeks ishmanov",
      "fix_count": 7,
      "last_fix_days_ago": 1,
      "bug_magnet": true
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "3eafc4215135",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 16 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Как свипер PR-Agent в репозитории poh-pr-agents выбирает пул-реквесты для ревью: реагирует ли он на все открытые PR, включая черновые (draft), и есть ли у него фильтр по draft или меткам? Что запускает ревью — метка, событие PR?",
  "repo": "poh-pr-agents"
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
    "onboarding/key_concepts",
    "self-hosted/reliability/agent_event.py",
    "onboarding/active_landscape",
    "onboarding/how_it_works"
  ],
  "retrieval": [
    {
      "path": "poh-pr-agents",
      "title": "Repository Overview: poh-pr-agents",
      "summary": "`poh-pr-agents` is a python codebase of 87 files. Execution starts at `self-hosted/reliability/app.py`.",
      "snippet": "# Repository Overview: poh-pr-agents\n\n**Files:** 87 | **Lines:** 15233 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-pr-agents` is a python codebase of 87 files. Execution starts at `self-hosted/r",
      "excerpt": "# Repository Overview: poh-pr-agents\n\n**Files:** 87 | **Lines:** 15233 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-pr-agents` is a python codebase of 87 files. Execution starts at `self-hosted/reliability/app.py`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `self-hosted/reliability/app.py`\n\n\n\n\n## Primary Execution Flows\n\n- `self-hosted/reliability/worker.py::main` (7 steps)\n\n- `self-hosted/reliability/app.py::webhook` (4 steps)\n\n- `self-hosted/reliability/worker.py::handle_lease` (4 steps)\n\n- `self-hosted/reliability/mapreduce_worker.py::route_and_fanout` (4 steps)\n\n- `self-hosted/reliability/sweeper.py::sweep` (3 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `self-hosted/reliability/state.py` (0.0929)\n\n- `self-hosted/reliability/sizing.py` (0.0501)\n\n- `self-hosted/reliability/chunk_review.py` (0.0338)\n\n- `self-hosted/reliability/__init__.py` (0.0305)\n\n- `self-hosted/reliability/metrics.py` (0.0243)\n\n- `self-hosted/reliability/chunking.py` (0.0215)\n\n- `self-hosted/reliability/reduce.py` (0.0201)\n\n- `self-hosted/reliability/queue.py` (0.0184)\n\n- `self-hosted/reliability/webhook.py` (0.0177)\n\n- `self-hosted/reliability/token.py` (0.0173)\n\n- `self-hosted/reliability/sweeper.py` (0.0172)\n\n- `self-hosted/reliability/security.py` (0.0171)\n\n- `self-hosted/reliability/quality_eval.py` (0.0168)\n\n- `self-hosted/reliability/github_client.py` (0.0158)\n\n- `self-hosted/reliabilit",
      "score": 2.625
    },
    {
      "path": "onboarding/key_concepts",
      "title": "Key Concepts",
      "summary": "The types and functions the rest of `poh-pr-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanation of it.",
      "snippet": "# Key Concepts\n\nThe types and functions the rest of `poh-pr-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanation",
      "excerpt": "# Key Concepts\n\nThe types and functions the rest of `poh-pr-agents` leans on most, ranked by how many files across the codebase reach for them. This is a list of what to learn, not yet an explanation of it.\n\n\n**Layers these sit in:** Application\n\n\n\n## Core symbols\n\n### `StateStore`\n\n**class** in `self-hosted/reliability/state.py` · Application · used from 24 other files\n\n_No docstring._\n\n### `FileChange`\n\n**class** in `self-hosted/reliability/sizing.py` · Application · used from 16 other files\n\n_No docstring._\n\n### `DurableQueue`\n\n**class** in `self-hosted/reliability/queue.py` · Application · used from 16 other files\n\n_No docstring._\n\n### `Gateway`\n\n**class** in `self-hosted/reliability/gateway.py` · Application · used from 10 other files\n\n_No docstring._\n\n### `GitHubAppClient`\n\n**class** in `self-hosted/reliability/github_client.py` · Application · used from 8 other files\n\n_No docstring._\n\n### `OpenPR`\n\n**class** in `self-hosted/reliability/sweeper.py` · Application · used from 8 other files\n\n_No docstring._\n\n\n\n\n\n\n## Vocabulary from the clusters\n\nDependency analysis named these groups. Their names are usually the codebase's own words for its parts.\n\n- .mcp\n\n- .pr_agent\n\n- agent_event\n\n- agents\n\n- architecture\n\n- autoscale\n\n\n\n\n---\n\n*Built from the code's structure. It states what is there, not why it is that\nway. Add an API key and run `repowise generate` to have that written.*",
      "score": 2.582
    },
    {
      "path": "self-hosted/reliability/agent_event.py",
      "title": "File: self-hosted/reliability/agent_event.py",
      "summary": "Доклад PR-Agent в цикл Issue (точка передачи H3 протокола агентов).",
      "snippet": "# self-hosted/reliability/agent_event.py\n\n## Overview\n\nДоклад PR-Agent в цикл Issue (точка передачи H3 протокола агентов).\n\nIssue-Agent держит задачу живым Temporal-workflow и после открытия PR ждёт в",
      "excerpt": "# self-hosted/reliability/agent_event.py\n\n## Overview\n\nДоклад PR-Agent в цикл Issue (точка передачи H3 протокола агентов).\n\nIssue-Agent держит задачу живым Temporal-workflow и после открытия PR ждёт в\nфазе `pr-open`. Без доклада отсюда он там и остаётся: своих вебхуков по PR он не\nслушает намеренно — фазу двигает тот, кто выполнил работу, а не тот, кто мимо\nпроходил.\n\nКонтракт узкий и односторонний: `POST /agent-event` с HMAC-подписью, конверт\n`{repo, agent, phase, status, ref, root_issue?, detail?}`. Temporal сюда не\nвтаскивается — у этого сервиса свой релизный цикл, и знание чужих workflow id\nбыло бы ровно той связностью, ради ухода от которой контракт и заводился.\n\nДоклад — вспомогательный канал, и он НИКОГДА не роняет обработку. Ревью уже\nопубликовано; уронить его из-за недоступного соседа значило бы обменять\nсделанную работу на несделанный доклад.\n\nСекрет и адрес берутся из окружения. Не задан любой из двух — канал выключен\nцеликом: это и есть процедура отката.\n\nIt exposes 11 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(\"reliability.agent_event\") |\n| `Transport` | variable | Transport = Callable[[str, str, \"Optional[bytes]\", dict], \"tuple[int, bytes]\"] |\n| `AGENT` | constant | AGENT = \"pr-agent\" |\n| `PHASE` | constant | PHASE = \"pr-review\" |\n| `STARTED` | constant | STARTED = \"started\" |\n| `FAILED` | constant | FAILED = \"failed\" |\n| `parse_root_issue` | function | def parse_root_issue",
      "score": 2.559,
      "key_symbols": [
        {
          "name": "logger",
          "kind": "variable",
          "signature": "logger = logging.getLogger(\"reliability.agent_event\")",
          "docstring": "",
          "start_line": 31,
          "end_line": 31,
          "source_excerpt": "logger = logging.getLogger(\"reliability.agent_event\")"
        },
        {
          "name": "Transport",
          "kind": "variable",
          "signature": "Transport = Callable[[str, str, \"Optional[bytes]\", dict], \"tuple[int, bytes]\"]",
          "docstring": "",
          "start_line": 35,
          "end_line": 35
        },
        {
          "name": "AGENT",
          "kind": "constant",
          "signature": "AGENT = \"pr-agent\"",
          "docstring": "",
          "start_line": 37,
          "end_line": 37,
          "source_excerpt": "AGENT = \"pr-agent\""
        },
        {
          "name": "parse_root_issue",
          "kind": "function",
          "signature": "def parse_root_issue(pr_body: str | None) -> Optional[int]:",
          "docstring": "Номер задачи из `Closes #N` в теле PR, иначе None.\n\n    Несколько закрываемых Issue — НЕ повод выбрать первый: привязать работу не к\n    той задаче значит испортить трассировку сразу двум. Такой случай уходит без\n    ключа, и Issue-Agent разберётся сам (у него та же развилка) либо запишет\n    сироту.",
          "start_line": 58,
          "end_line": 69,
          "source_excerpt": "def parse_root_issue(pr_body: str | None) -> Optional[int]:\n    \"\"\"Номер задачи из `Closes #N` в теле PR, иначе None.\n\n    Несколько закрываемых Issue — НЕ повод выбрать первый: привязать работу не к\n    той задаче значит испортить трассировку сразу двум. Такой случай уходит без\n    ключа, и Issue-Agent разберётся сам (у него та же развилка) либо запишет\n    сироту.\n    \"\"\"\n    if not pr_body:\n        return None\n    found = {int(n) for n in _CLOSES_RE.findall(pr_body)}\n    return found.pop() if len(found) == 1 else None"
        }
      ]
    },
    {
      "path": "onboarding/active_landscape",
      "title": "Active Landscape",
      "summary": "Where `poh-pr-agents` has actually been changing. 198 commits touched 64 files in the last 90 days.",
      "snippet": "# Active Landscape\n\nWhere `poh-pr-agents` has actually been changing. 198 commits touched 64 files in the last 90 days.\n\n\n## Files under active change\n\n| File | Commits (90d) | Owner | Hotspot | Age |",
      "excerpt": "# Active Landscape\n\nWhere `poh-pr-agents` has actually been changing. 198 commits touched 64 files in the last 90 days.\n\n\n## Files under active change\n\n| File | Commits (90d) | Owner | Hotspot | Age |\n| --- | --- | --- | --- | --- |\n| `self-hosted/reliability/worker.py` | 12 | Claude | yes | 35d |\n| `self-hosted/reliability/tests/test_worker.py` | 10 | Claude | yes | 35d |\n| `self-hosted/reliability/github_client.py` | 9 | Claude | yes | 36d |\n| `self-hosted/reliability/state.py` | 9 | Claude | yes | 36d |\n| `self-hosted/reliability/supervisor.py` | 9 | Claude | no | 36d |\n| `self-hosted/reliability/app.py` | 8 | Claude | no | 36d |\n| `self-hosted/reliability/tests/test_supervisor.py` | 8 | Claude | yes | 36d |\n| `self-hosted/reliability/tests/test_github_client.py` | 7 | Claude | yes | 36d |\n| `self-hosted/reliability/sweeper_runner.py` | 6 | Claude | no | 34d |\n| `self-hosted/reliability/gateway.py` | 5 | Claude | yes | 33d |\n| `self-hosted/reliability/sweeper_adapter.py` | 5 | Claude | yes | 34d |\n| `self-hosted/reliability/tests/test_sweeper_adapter.py` | 5 | Claude | yes | 34d |\n\n\nA hotspot is a file that is both high-churn and structurally complex. Those are the ones where changes are most likely to go wrong.\n\n\n\n## Areas under active change\n\n| Directory | Commits (90d) | Files | Hotspots |\n| --- | --- | --- | --- |\n| `self-hosted` | 198 | 64 | 14 |\n\n\n\n\n---\n\n*Built from the code's structure. It states what is there, not why it is that\nway. Add an API key and run `repowis",
      "score": 2.54
    },
    {
      "path": "onboarding/how_it_works",
      "title": "How It Works",
      "summary": "Traced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.",
      "snippet": "from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-pr-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as",
      "excerpt": "# How It Works\n\nTraced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-pr-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `self-hosted/reliability/app.py`\n\n\n\n\n## Traced flows\n\n\n\n\n### From `self-hosted/reliability/sweeper_runner.py::main`\n\n\n\n1. `self-hosted/reliability/sweeper_runner.py::main`\n\n2. `self-hosted/reliability/sweeper.py::sweep`\n\n3. `self-hosted/reliability/state.py::StateStore::transition`\n\n4. `self-hosted/reliability/state.py::StateStore::get`\n\n\n\n\n\n\n### From `self-hosted/reliability/worker.py::main`\n\n\n\n1. `self-hosted/reliability/worker.py::main`\n\n2. `self-hosted/reliability/worker.py::run_forever`\n\n3. `self-hosted/reliability/worker.py::run_once`\n\n4. `self-hosted/reliability/worker.py::handle_lease`\n\n5. `self-hosted/reliability/supervisor.py::process`\n\n6. `self-hosted/reliability/state.py::StateStore::transition`\n\n7. `self-hosted/reliability/state.py::StateStore::get`\n\n\n\n\n\n\n### From `self-hosted/reliability/app.py::webhook`\n\n\n\n1. `self-hosted/reliability/app.py::webhook`\n\n2. `self-hosted/reliability/ingress.py::handle_webhook`\n\n3. `self-hosted/reliability/webhook.py::parse_events`\n\n4. `self-hosted/reliability/webhook.py::stop_labels_present`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. R",
      "score": 2.5
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval.",
  "best_guesses": [
    {
      "file": "self-hosted/reliability/agent_event.py",
      "why_relevant": "Implements constant AGENT.",
      "score": 2.559
    }
  ],
  "_meta": {
    "timing_ms": 348.9,
    "hint": "No synthesis, and retrieval was weak. Refine the query with search_codebase rather than reading these files in order.",
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "self-hosted/reliability/agent_event.py",
      "lines": "31-69",
      "defines": "AGENT:37, parse_root_issue:58, build_payload:72, sign:89, configured:93, report:99"
    },
    {
      "path": "self-hosted/reliability/chunk_review.py",
      "defines": "build_review_prompt:36, review_chunk:50, patches_for_files:64, glm_model_call:70, DEFAULT_REVIEW_INSTRUCTIONS:21, SYSTEM_PROMPT:26"
    },
    {
      "path": "self-hosted/reliability/analyze_adapter.py",
      "defines": "PRAgentAnalyzer:23, installation_token:86, provider:93, run:34"
    },
    {
      "path": "self-hosted/reliability/webhook.py",
      "defines": "stop_labels_present:29, enrich_events:47, parse_events:76, DEFAULT_PR_COMMANDS:17, STOP_LABELS:26, PR_TRIGGER_ACTIONS:73"
    },
    {
      "path": "self-hosted/reliability/notifier.py",
      "defines": "GitHubClient:12, build_failure_comment:16, notify_failure:30, upsert_comment:13"
    }
  ]
}

## Ход 17 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "skeleton"
  ],
  "repo": "poh-pr-agents",
  "targets": [
    "self-hosted/reliability/sweeper.py",
    "self-hosted/reliability/webhook.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "self-hosted/reliability/sweeper.py": {
      "target": "self-hosted/reliability/sweeper.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/sweeper.py",
        "summary": "Reconciliation sweeper (СТ-13, 29..32): периодическая сверка и дозапуск."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 49
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
        "tokens": 1293,
        "full_tokens": 1344,
        "pct_of_full": 96.2,
        "bodies_kept": [
          "sweep"
        ],
        "text": "\"\"\"Reconciliation sweeper (СТ-13, 29..32): периодическая сверка и дозапуск.\n\nЛовит пропущенные webhook'и, необработанные PR и застрявших воркеров — и\nдозапускает. Насколько строг критерий «есть ревью» — определяет инъектируемый\nпорт `has_completed_review`; текущая go-live реализация (`sweeper_adapter`)\nпроверяет DONE-строку в store, чем закрывает пропуск/застревание. Детект\n«проглоченного» сбоя (DONE в сторе, но ревью на GitHub нет) — followup: тот же\nпорт, но со сверкой артефакта на GitHub (тюнится на смоуке). Порты инъектируются\n→ тестируется без GitHub/сети.\n\nЗа один проход:\n1) застрявшие вне терминала события (СТ-13) → свежий retry или dead-letter;\n2) открытые PR без подтверждённого ревью (СТ-29/31) → reconcile-enqueue (force);\n3) эскалация после max_cycles циклов (СТ-32) — не бесконечная тихая петля.\n\"\"\"\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass, field\nfrom typing import Callable\n\nfrom reliability import metrics\nfrom reliability.notifier import GitHubClient, notify_failure\nfrom reliability.state import Event, State, StateStore\n\n\nclass StuckTimeout(Exception):\n    \"\"\"Событие застряло вне терминала дольше deadline (СТ-13).\"\"\"\n\n\n@dataclass(frozen=True)\nclass OpenPR:\n    ... 3 lines (32-34)\n\n\n@dataclass\nclass SweepReport:\n    ... 4 lines (39-42)\n\n\ndef business_key(repo: str, number: int, head_sha: str, command: str) -> str:\n    return f\"{repo}#{number}@{head_sha}:{command}\"\n\n\ndef _event_from_row(row, delivery_id: str, event_type: str) -> Event:\n    return Event(delivery_id=delivery_id, repo=row[\"repo\"], number=int(row[\"number\"]),\n                 head_sha=row[\"head_sha\"], command=row[\"command\"], event_type=event_type)\n\n\ndef sweep(store: StateStore, *,\n          list_open_prs: Callable[[], list],\n          has_completed_review: Callable[[str, int, str, str], bool],\n          enqueue: Callable[..., None],\n          client: GitHubClient,\n          commands,\n          stale_deadline: float,\n          max_attempts: int,\n          max_cycles: int) -> SweepReport:\n    rep = SweepReport()\n\n    # 1) СТ-13: застрявшие вне терминала. FAILED — тоже не терминал и попадает сюда,\n    # поэтому переходы делаем с учётом текущего состояния (без FAILED->FAILED).\n    for row in store.stale(stale_deadline):\n        did = row[\"delivery_id\"]\n        attempts = int(row[\"attempts\"])\n        cur = State(row[\"state\"])\n        if attempts >= max_attempts:\n            if cur != State.FAILED:\n                store.transition(did, State.FAILED)\n            store.transition(did, State.DEAD_LETTER)  # довести до терминала\n            metrics.incr(\"dead_letter_total\")\n            notify_failure(client, _event_from_row(row, did, row[\"event_type\"]),\n                           StuckTimeout(\"stuck beyond deadline\"), attempts, escalated=True)\n            rep.dead_lettered.append(did)\n        else:\n            # claim: вернуть ту же строку в очередь легальными переходами (обновляет\n            # timestamp → покидает stale-выборку), затем повторно обработать её же.\n            if cur == State.PROCESSING:\n                store.transition(did, State.FAILED)\n                cur = State.FAILED\n            if cur in (State.RECEIVED, State.FAILED):\n                store.transition(did, State.QUEUED)\n            enqueue(_event_from_row(row, did, row[\"event_type\"]))\n            metrics.incr(\"reconcile_requeues\")\n            rep.requeued.append(did)\n\n    # 2) СТ-29/31: открытые PR без подтверждённого ревью → reconcile\n    for pr in list_open_prs():\n        for cmd in commands:\n            bkey = business_key(pr.repo, pr.number, pr.head_sha, cmd)\n            if has_completed_review(pr.repo, pr.number, pr.head_sha, cmd):\n                store.clear_reconcile(bkey)   # эффект есть — сбросить счётчик\n                continue\n            if store.in_flight(bkey):\n                continue                       # СТ-30: уже в работе, не дублируем\n            cycles = store.bump_reconcile(bkey)\n            if cycles > max_cycles:            # СТ-32: эскалация\n                if cycles == max_cycles + 1:   # оповещаем один раз, дальше молча стоп\n                    metrics.incr(\"reconcile_escalated_total\")\n                    client.upsert_comment(\n                        pr.repo, pr.number, f\"<!-- reliability:reconcile:{cmd} -->\",\n                        f\"⚠️ Автоматические попытки получить `{cmd}` исчерпаны \"\n                        f\"({max_cycles} циклов). Требуется ручной запуск: `{cmd}`.\")\n                    rep.escalated.append(bkey)\n                continue\n            # reconcile-событие с force: обходим already_done (has_completed_review\n            # уже сказал «ревью нет» — истина порта, для go-live это store).\n            # id на монотонном seq — не коллизится при флапе has_completed_review.\n            rec = Event(delivery_id=f\"reconcile:{bkey}:{store.next_seq()}\", repo=pr.repo,\n                        number=pr.number, head_sha=pr.head_sha, command=cmd,\n                        event_type=\"reconcile\")\n            if store.record_received(rec):\n                enqueue(rec, force=True)\n                metrics.incr(\"reconcile_requeues\")\n                rep.reconciled.append(bkey)\n\n    return rep\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 96.2% of the full file — a direct Read costs little more."
      },
      "episodes": 1
    },
    "self-hosted/reliability/webhook.py": {
      "target": "self-hosted/reliability/webhook.py",
      "type": "file",
      "parent_page": {
        "title": "Self Hosted Reliability",
        "target_path": "self-hosted/reliability",
        "section": "4"
      },
      "docs": {
        "title": "File: self-hosted/reliability/webhook.py",
        "summary": "Разбор webhook GitHub → список Event (СТ-8)."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 2,
        "last_fix_days_ago": 47
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
        "tokens": 1145,
        "full_tokens": 1279,
        "pct_of_full": 89.5,
        "bodies_kept": [
          "parse_events",
          "stop_labels_present",
          "enrich_events"
        ],
        "text": "\"\"\"Разбор webhook GitHub → список Event (СТ-8).\n\nОдна доставка PR-события может породить несколько команд (describe+review) —\nдля каждой формируется отдельный Event с уникальным ключом идемпотентности\n`{delivery_id}:{command}` (чтобы dedup и PK работали покомандно).\n\"\"\"\nfrom __future__ import annotations\n\nimport logging\nfrom dataclasses import replace\nfrom typing import Callable\n\nfrom reliability.state import Event\n\nlogger = logging.getLogger(__name__)\n\nDEFAULT_PR_COMMANDS = (\"/describe\", \"/review\")\n... 8 lines (18-25)\nSTOP_LABELS = frozenset({\"pr-closer:closed\", \"agents:off\"})\n\n\ndef stop_labels_present(payload: dict) -> frozenset[str]:\n    \"\"\"Стоп-метки из payload события.\n\n    Читаем и pull_request, и issue: у issue_comment PR приходит под ключом\n    `issue`, и метки лежат там же.\n    \"\"\"\n    names: set[str] = set()\n    for key in (\"pull_request\", \"issue\"):\n        for label in (payload.get(key) or {}).get(\"labels\") or []:\n            name = label.get(\"name\") if isinstance(label, dict) else label\n            if name:\n                names.add(str(name))\n    return frozenset(names & STOP_LABELS)\n\n# (repo, number) -> head_sha (\"\" если issue не является PR / API недоступен)\nFetchHeadSha = Callable[[str, int], str]\n\n\ndef enrich_events(events: list[Event], fetch_head_sha: FetchHeadSha) -> list[Event]:\n    \"\"\"Дозаполнить head_sha для событий без него (issue_comment: в payload sha нет).\n\n    Ключ идемпотентности (business_key) зависит от head_sha, поэтому обогащение\n    ОБЯЗАНО выполняться до record_received/enqueue — иначе строка сохранится с\n    пустым sha и reconcile/дедуп по push сломаются. События, для которых sha так и\n    не получен (issue — не PR, либо API молчит), отбрасываются: ревьюить нечего,\n    а неполный ключ хуже отсутствия события. PR-события уже несут sha → проходят\n    без обращения к API.\n    \"\"\"\n    out: list[Event] = []\n    for e in events:\n        if e.head_sha:\n            out.append(e)\n            continue\n        try:\n            sha = fetch_head_sha(e.repo, e.number)\n        except Exception:\n            # транзиентная ошибка GitHub-API трактуется как 404 (см. модульный\n            # docstring ingress: 500 + бесконечные ретраи доставки — риск против\n            # К-1). Событие отбрасываем; свипер добэкстопит настроенные команды на\n            # открытых PR. Один сбойный fetch не рушит весь батч.\n            ... 4 lines (69-72)\nPR_TRIGGER_ACTIONS = frozenset({\"opened\", \"reopened\", \"ready_for_review\", \"synchronize\"})\n\n\ndef parse_events(event_type: str, delivery_id: str, payload: dict,\n                 pr_commands=DEFAULT_PR_COMMANDS) -> list[Event]:\n    stopped = stop_labels_present(payload)\n    if stopped:\n        # Снятие метки — осознанное действие человека, и оно возвращает PR\n        # в оборот. Пока метка стоит, не запускается ничего, включая явную\n        # команду в комментарии: иначе рубильник переставал бы быть рубильником.\n        logger.info(\"событие пропущено: на PR стоит %s (event=%s delivery=%s)\",\n                    \", \".join(sorted(stopped)), event_type, delivery_id)\n        return []\n\n    if event_type == \"pull_request\":\n        if payload.get(\"action\") not in PR_TRIGGER_ACTIONS:\n            return []\n        pr = payload.get(\"pull_request\") or {}\n        repo = (payload.get(\"repository\") or {}).get(\"full_name\")\n        number = pr.get(\"number\")\n        head_sha = (pr.get(\"head\") or {}).get(\"sha\")\n        if not (repo and number is not None and head_sha):\n            return []  # неполный payload — не выдумываем событие\n        return [\n            Event(delivery_id=f\"{delivery_id}:{cmd}\", repo=repo, number=number,\n                  head_sha=head_sha, command=cmd, event_type=event_type)\n            for cmd in pr_commands\n        ]\n\n    if event_type == \"issue_comment\":\n        if payload.get(\"action\") != \"created\":\n            return []\n        body = ((payload.get(\"comment\") or {}).get(\"body\") or \"\").strip()\n        if not body.startswith(\"/\"):\n            return []\n        cmd = body.split()[0]\n        repo = (payload.get(\"repository\") or {}).get(\"full_name\")\n        number = (payload.get(\"issue\") or {}).get(\"number\")\n        if not (repo and number is not None):\n            return []\n        # head_sha из payload issue_comment недоступен напрямую — обогащается на\n        # следующем шаге (запрос PR по номеру); пока пусто (см. issue #1).\n        head_sha = payload.get(\"_head_sha\", \"\")\n        return [Event(delivery_id=f\"{delivery_id}:{cmd}\", repo=repo, number=number,\n                      head_sha=head_sha, command=cmd, event_type=event_type)]\n\n    return []\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 89.5% of the full file — a direct Read costs little more."
      },
      "episodes": 2
    }
  },
  "_meta": {
    "timing_ms": 53.62,
    "index_age_days": 0,
    "indexed_commit": "9f15ada9e4e9",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}
