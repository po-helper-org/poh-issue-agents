# Итог

1. **Функция `render_letter`** находится в `shared/bft.py:175-240` ([symbol](shared/bft.py::render_letter)). Это основной компонент, который форматирует быстрый комментарий БФТ.

2. **Текущий формат включает визуальный шум**: заголовок `## 📋 БФТ (быстрый проход)` (строка 196), bold-разметка на всех подписях блоков (`**Цель:**`, `**How to demo:**`, `**Открытые вопросы:**`, `**Границы:**`, `**Документация:**` — строки 200-215), таблицы требований и стейкхолдеров в теле письма (строки 217-229), разделитель `---` (строка 231).

3. **Вызывается из `worker/activities.py::run_bft_fast`** ([строки 2304-2313](worker/activities.py::run_bft_fast)), который публикует результат в GitHub Issue.

4. **Формат задан противоречиво**:
   - `letter_format.md` ([.claude/skills/bft-fast/resources/letter_format.md](.claude/skills/bft-fast/resources/letter_format.md)) описывает чистый формат без эмодзи-заголовка и bold-разметки
   - `docs/BFT.md` (строки 31-66) описывает текущий формат с шумом как канонический
   - docstring `render_letter` ссылается на `letter_format.md`, но код реализует другой формат

5. **Константы футера**: `DEEP_HINT` и `DEEP_HINT_NO_QUESTIONS` определены в `shared/bft.py:135-142` — подсказка про `/bft-deep`, которая добавляется после разделителя `---`.

6. **Тесты расположены в `tests/test_bft.py`**: функции `test_letter_keeps_the_block_order_of_the_skill`, `test_letter_ends_with_the_deep_hint_and_numbered_questions`, `test_letter_without_questions_still_offers_the_deep_run`, `test_empty_blocks_are_omitted_not_left_hollow`, `test_requirements_table_escapes_pipes_and_newlines`, `test_revision_is_named_only_from_the_second_one` проверяют порядок блоков, наличие футера, обработку пустых блоков, формат таблиц и редакций.

7. **Вспомогательные функции**: `_bullets`, `_numbered`, `_table` в `shared/bft.py:147-172` — отвечают за форматирование списков и таблиц.

8. **Связанные функции вне периметра**: `render_statement` (постановка для глубокого прогона), `render_deep_summary`, `render_partial_summary` — не трогаем в рамках задачи.

9. **Класс экстракции**: `BftLetterExtraction` в `worker/activities.py:2180-2188` описывает поля, извлекаемые из LLM-ответа — логика извлечения не меняется, только формат вывода.

10. **Документация рассинхронизирована**: `docs/BFT.md` фиксирует текущий "тяжёлый" формат как канонический, но должен быть обновлён для соответствия новому чистому виду.

# Открытые вопросы

- В задаче указано, что таблицы требований и стейкхолдеров нужно либо вынести из письма, либо свернуть в `<details>`. Какое решение принять на этапе разработки?
- Должна ли сохраниться функциональность показа таблиц в GitHub-комментарии, но в свёрнутом виде?
- Нужно ли обновлять `letter_format.md` после правки или он уже описывает целевой формат?

# Диалог

**Ход 1**: Получен обзор репозитория через `get_overview`. `shared/bft.py` присутствует в центральных файлах, PageRank 0.0079 (94-й перцентиль). Repo здоровый (средний балл 8.36), hotspot-score 5.11. Модуль импортируется в 9 файлов включая `worker/activities.py` и тесты.

**Ход 2**: Получен контекст по `shared/bft.py` через `get_context(include=["skeleton", "callers", "ownership"])`. Файл hotspot=true, ownership=50% Claude/80% ALeks ishmanov (свежие правки). Вызывается из `worker/activities.py::run_bft_fast`, тестов 7 штук. skeleton показал структуру файла и сигнатуру `render_letter`.

**Ход 3**: Поиск `render_letter` через `search_codebase(mode="symbol")` дал точное попадание: `shared/bft.py::render_letter` строки 175-240.

**Ход 4**: Получено тело функции через `get_symbol(symbol_id="shared/bft.py::render_letter")`. Виден текущий формат: `parts.append("## 📋 БФТ (быстрый проход)")`, `**Цель:**`, таблицы требований/стейкхолдеров, `---`, футер с `DEEP_HINT`.

**Ход 5**: Поиск тестов и документации. `docs/BFT.md` не найден через repowise (не индексирован), найден через bash. `letter_format.md` найден в `.claude/skills/bft-fast/resources/`. Прочтены оба файла — обнаружено расхождение: letter_format описывает чистый формат, BFT.md — текущий с шумом.

**Ход 6**: Найдены тестовые файлы через bash: 7 файлов `test_bft*.py`. Прочитаны тесты в `tests/test_bft.py` — проверяют порядок блоков (через `**Цель:**` и т.д.), футер, пустые блоки, таблицы, редакции. Вспомогательная функция `_letter` определена.

**Ход 7**: Получена деталь по `run_bft_fast` через `get_symbol` — видно, как вызывается `render_letter` с параметрами из `BftLetterExtraction`. Получен класс `BftLetterExtraction` с описанием полей.

**Ход 8**: Проверены константы `DEEP_HINT` и `DEEP_HINT_NO_QUESTIONS` — они формируют футер после разделителя `---`. Это часть функциональности, которая должна остаться, но податься тише.

**Ход 9**: Поиск документации через bash подтвердил наличие `docs/BFT.md` и `.claude/skills/bft-fast/resources/letter_format.md`. Оба файла прочитаны — выявлено противоречие описания формата.

**Ход 10**: Завершение диалога. Собрана полная картина: что менять (заголовок, bold, таблицы, футер), что не трогать (другие render_* функции, логику извлечения), какие тесты обновлять.


---
session: rw-analysis-po-helper-org__poh-issue-agents-91
workspace: contour
turns: 16
started: 2026-08-20T16:47:51Z
finished: 2026-08-20T16:48:12Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `564c0ffc7131` | 9 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 9 мин |
| `poh-helper` | `18512c1e7ce9` | 9 мин |
| `poh-infra` | `ac430395f649` | 9 мин |
| `poh-issue-agents` | `a223cc6ade57` | 9 мин |
| `poh-memory-engine` | `194e39319b3f` | 9 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 9 мин |
| `poh-scheduller` | `04cc3f47aff9` | 9 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 9 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 12 ч |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
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
    "open_findings": 444,
    "file_count": 343,
    "distribution": {
      "total_files": 343,
      "total_nloc": 48218,
      "bands": {
        "healthy": {
          "files": 306,
          "nloc": 36134,
          "pct": 74.9
        },
        "warning": {
          "files": 33,
          "nloc": 7070,
          "pct": 14.7
        },
        "alert": {
          "files": 4,
          "nloc": 5014,
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
    "files_git_attributed": 346,
    "hotspot_count": 39,
    "avg_bus_factor": 0.6,
    "files_with_bus_factor_1": 107,
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
        "percentage": 23.7
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
      "size": 12
    },
    {
      "id": 1,
      "label": "tests (42)",
      "size": 9
    },
    {
      "id": 2,
      "label": "server",
      "size": 7
    },
    {
      "id": 3,
      "label": "tests (22)",
      "size": 6
    },
    {
      "id": 4,
      "label": "worker",
      "size": 5
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
    "total_pages": 246,
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
        "descendants": 96
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
        "file_count": 93
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
    "indexed_commit": "a223cc6ade57",
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
    "shared/bft.py"
  ],
  "include": [
    "skeleton",
    "callers",
    "callees",
    "metrics",
    "last_change",
    "ownership"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/bft.py": {
      "target": "shared/bft.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/bft.py",
        "summary": "БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария."
      },
      "hotspot": true,
      "ownership": {
        "primary_owner": "Claude",
        "owner_pct": 0.5334,
        "contributor_count": 2,
        "bus_factor": 1,
        "recent_owner": "ALeks ishmanov",
        "recent_owner_pct": 0.8,
        "agent_authored_pct": 1.0,
        "agent_commit_count": 5,
        "agent_tier_counts": {
          "3": 4,
          "1": 1
        }
      },
      "last_change": {
        "date": "2026-08-20T05:30:15",
        "author": "Claude",
        "days_ago": 1
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
      "callers": [
        {
          "file": "shared/commands.py",
          "imports": true
        },
        {
          "file": "tests/test_bft.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_activities.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_direct_stage.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_entire_session.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_partial_resume.py",
          "imports": true
        },
        {
          "file": "tests/test_bft_workflow.py",
          "imports": true
        },
        {
          "file": "worker/activities.py",
          "imports": true
        },
        {
          "file": "worker/workflows.py",
          "imports": true
        }
      ],
      "_call_graph_note": "File-level rollup: importing files plus inbound cross-file call counts. For symbol-precise callers pass 'file.py::Symbol'.",
      "callees": [],
      "metrics": {
        "pagerank": 0.007931,
        "pagerank_percentile": 94,
        "betweenness": 0.0,
        "betweenness_percentile": 0,
        "in_degree": 9,
        "out_degree": 0,
        "community_id": 0,
        "community_label": "tests"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 2096,
        "full_tokens": 6049,
        "pct_of_full": 34.7,
        "bodies_kept": [
          "epic_slug",
          "deep_stages",
          "stage_artifacts",
          "_table",
          "statement_path"
        ],
        "text": "\"\"\"БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py`. Формат комментария и перечень стадий проверяются напрямую, без\nпрогона воркфлоу и без обращения к модели.\n\nПочему БФТ, а не прежний advisor-ответ\n--------------------------------------\nКлассификация отвечала свободным текстом «Ситуация / Ограничение / Варианты\nрешения / Оценка сложности». В нём нет сценария приёмки, нет границ и нет\nсписка открытых вопросов с владельцами, зато есть «варианты решения» — то есть\nпроектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)\nдаёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`\n→ `Границы` → `Документация` плюс таблицу требований на цитатах.\n\nДва режима, две цены\n--------------------\n`fast` — один вызов модели по тексту Issue и треду: секунды, комментарий в Issue.\n`deep` — канонический пайплайн `bft-writer` внутри клона репозитория: минуты,\nартефакты в ветке. Первый идёт сам на триаже, второй — только по явной команде:\nдорогую стадию запускает человек, а не догадка агента.\n\"\"\"\n\nimport json\nimport os\nimport re\n\nFAST = \"fast\"\nDEEP = \"deep\"\nMODES = (FAST, DEEP)\n\n# Ветка артефактов глубокого прогона. Отдельная от `research/issue-N` (цепочка\n# FNR): у документов разные авторы и разная судьба, и складывать их в одну ветку\n# значило бы, что повторный прогон одного затирает историю другого.\nBRANCH_PREFIX = \"bft-research\"\n\n# Корень документации bft-writer внутри воркспейса — дефолт `docs_path` из\n# `bft-config.md`. Задан здесь явно, чтобы публикация знала, что забирать, не\n# угадывая по маске.\nDOCS_ROOT = \".bft/documentation\"\n\n\ndef epic_slug(issue_number: int) -> str:\n    \"\"\"Имя эпика для пайплайна — от НОМЕРА Issue, а не от заголовка.\n\n    Заголовок редактируют, и slug из него менял бы каталог артефактов между\n    прогонами: второй `/bft-deep` писал бы рядом с первым, а не поверх, и\n    «документ с дополнительными требованиями» превращался бы во второй документ.\n    \"\"\"\n    return f\"issue-{issue_number}\"\n\n\ndef branch(issue_number: int) -> str:\n    return f\"{BRANCH_PREFIX}/{epic_slug(issue_number)}\"\n\n\ndef epic_dir(issue_number: int) -> str:\n    return f\"{DOCS_ROOT}/{epic_slug(issue_number)}\"\n\n\ndef artefacts_dir(issue_number: int) -> str:\n    return f\"{epic_dir(issue_number)}/artefacts\"\n\n\ndef statement_path(issue_number: int) -> str:\n    \"\"\"Постановка от заказчика — файл, который пайплайн читает вместо JIRA.\n\n    В контуре Issue трекера нет: `/bft-context-gen` штатно тянет эпик из JIRA, а\n    здесь его роль играет сам Issue вместе с тредом и уточнениями из команды.\n    ... 4 lines (70-73)\n\n\ndef document_path(issue_number: int) -> str:\n    \"\"\"Главный документ БФТ — то, что открывает человек.\"\"\"\n    ... 9 lines (78-86)\nDEEP_STAGE_NAMES: tuple[str, ...] = (\n    \"index\", \"context\", \"problem\", \"concept\", \"debate\", \"draft\", \"validate\",\n)\n\n\ndef deep_stages(issue_number: int) -> list[tuple[str, str, str | None, str | None]]:\n    \"\"\"(имя, промпт, ожидаемый артефакт, требуемый вход) для каждой стадии.\n\n    Промпт — `/<команда> <аргументы>` и ничего больше: `claude -p` разворачивает\n    команду только тогда, когда она стоит первой, а произвольный текст после\n    аргументов команда прочитает как ещё один аргумент.\n\n    `index` и `debate` ожидаемого файла не имеют: первый строит каталог\n    `.bft/index/`, второй дописывает вердикт в конец `concept.md`.\n    ... 20 lines (101-120)\n\n\ndef deep_stage(name: str, issue_number: int) -> tuple[str, str | None, str | None]:\n    \"\"\"(промпт, ожидаемый артефакт, требуемый вход) стадии по имени.\"\"\"\n    ... 10 lines (125-134)\nDEEP_HINT = (\n    \"Если задача касается больших изменений — запустите команду `/bft-deep` \"\n    \"и ответьте на ряд этих уточняющих вопросов:\"\n)\n\nDEEP_HINT_NO_QUESTIONS = (\n    \"Если задача касается больших изменений — запустите команду `/bft-deep` \"\n    \"(можно с уточнениями в том же комментарии): она соберёт полный БФТ по \"\n    \"канону и приложит артефакты веткой.\"\n)\n\n\ndef _bullets(items: list[str]) -> str:\n    return \"\\n\".join(f\"* {item.strip()}\" for item in items if item and item.strip())\n\n\ndef _numbered(items: list[str]) -> str:\n    kept = [item.strip() for item in items if item and item.strip()]\n    return \"\\n\".join(f\"{i}. {item}\" for i, item in enumerate(kept, 1))\n\n\ndef _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:\n    \"\"\"Markdown-таблица из строк-словарей. Пустой список строк → пустая строка.\n\n    В `/bft-fast` требования уезжают вложением csv. В Issue вложений нет, и\n    таблица — единственная форма, в которой они и читаются глазами, и остаются\n    ... 12 lines (161-172)\n\n\ndef render_letter(\n    *,\n    goal: str,\n    how_to_demo: list[str],\n    open_questions: list[str],\n    scope: str,\n    documentation: list[str],\n    requirements: list[dict],\n    personas: list[dict],\n    revision: int = 1,\n) -> str:\n    \"\"\"Комментарий fast-режима: письмо `/bft-fast` плюс приписка про `/bft-deep`.\n... 54 lines (187-240)\n\n\ndef render_statement(\n    *,\n    title: str,\n    body: str,\n    thread: str,\n    instructions: str,\n    issue_number: int,\n    repo: str,\n) -> str:\n    \"\"\"Постановка для глубокого прогона — единственный вход задачи в пайплайн.\n... 29 lines (253-281)\n\n\ndef render_config() -> str:\n    \"\"\"`bft-config.md` для клона — конфигурация пайплайна на этот прогон.\n... 20 lines (286-305)\n\n\ndef render_deep_summary(repo: str, issue_number: int, files: list[str]) -> str:\n    \"\"\"Сводка глубокого прогона: где лежит документ и что ещё появилось.\"\"\"\n    ... 40 lines (310-349)\nCASCADE_FLOOR: dict[str, int] = {\"БТ\": 4, \"ПТ\": 5, \"ИТ\": 6, \"ФТ\": 10, \"НФТ\": 4}\nANCHOR_FLOOR = 24\n\nCASCADE_SCHEMA = \"\"\"{\n  ... 8 lines (354-361)\n\n\ndef direct_stages() -> set[str]:\n    \"\"\"Стадии, которые идут прямыми вызовами вместо `claude -p`.\n... 7 lines (366-372)\n\n\ndef parse_cascade(text: str) -> dict:\n    \"\"\"JSON каскада из ответа модели.\n... 8 lines (377-384)\n\n\ndef cascade_gaps(cascade: dict, line_counts: dict[str, int]) -> list[str]:\n    \"\"\"Чего каскаду не хватает — претензиями на языке добора.\n... 55 lines (389-443)\ndef stage_artifacts(issue_number: int) -> dict[str, str]:\n    \"\"\"Стадия → путь её артефакта. Только стадии, у которых он есть.\n\n    `index` строит каталог `.bft/index/`, `debate` дописывает вердикт в конец\n    `concept.md` — по файлу их «сделанность» не определить, поэтому в карте их\n    ... 5 lines (449-453)\n\n\ndef done_stages(issue_number: int, exists) -> list[str]:\n    \"\"\"Стадии, чей артефакт уже лежит в рабочем каталоге.\n... 6 lines (458-463)\n\n\ndef remaining_stages(issue_number: int, done: list[str]) -> list[str]:\n    \"\"\"Стадии, которые осталось прогнать — в каноническом порядке.\"\"\"\n    return [name for name in DEEP_STAGE_NAMES if name not in done]\n\n\ndef render_partial_summary(repo: str, issue_number: int, files: list[str],\n                           done: list[str], reason: str) -> str:\n    \"\"\"Комментарий о прогоне, оборванном на середине.\n... 39 lines (474-512)\nDIALOG_LOG = \"dialog-log.md\"\n\n\ndef dialog_log_path(issue_number: int) -> str:\n    return f\"{artefacts_dir(issue_number)}/{DIALOG_LOG}\"\n\n\ndef render_dialog_entry(*, stage: str, actor: str, step: str, outcome: str,\n                        detail: str = \"\", tokens: str = \"\",\n                        elapsed: float | None = None) -> str:\n    \"\"\"Одна запись журнала — строка таблицы.\n... 9 lines (524-532)\n\n\nDIALOG_LOG_HEADER = (\n    \"# Журнал прогона БФТ\\n\\n\"\n    \"Что делал пайплайн и чем это кончилось. Пишется по ходу, поэтому уцелевает\\n\"\n    \"и у оборванного прогона — по нему видно, на чём именно остановились.\\n\\n\"\n    \"| Стадия | Исполнитель | Шаг | Исход | Время | Токены | Подробности |\\n\"\n    \"|---|---|---|---|---|---|---|\\n\"\n)\n... 14 lines (542-555)\nENTIRE_BRANCH_PREFIX = \"entire/\"\n\n\ndef parse_session_id(text: str) -> str:\n    \"\"\"Id сессии entire из вывода `entire session list`.\n... 9 lines (561-569)\n\n\ndef parse_session_branch(text: str) -> str:\n    \"\"\"Ветка чекпоинтов из вывода `git branch` или `git for-each-ref`.\"\"\"\n    ... 5 lines (574-578)\n\n\ndef render_session_hint(repo: str, session_id: str, session_branch: str) -> str:\n    \"\"\"Блок про сессию для комментария: где диалог и чем продолжить.\n... 15 lines (583-597)\n\n\ndef split_session_arg(instructions: str) -> tuple[str, str]:\n    \"\"\"(id сессии, остальные инструкции) из хвоста `/bft-deep`.\n... 12 lines (602-613)\n",
        "verified": true
      }
    }
  },
  "_meta": {
    "timing_ms": 165.8,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "render_letter",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/bft.py::render_letter",
      "name": "render_letter",
      "kind": "function",
      "file": "shared/bft.py",
      "start_line": 175,
      "end_line": 240,
      "signature": "def render_letter(\n    *,\n    goal: str,\n    how_to_demo: list[str],\n    open_questions: list[str],\n    scope: str,\n    documentation: list[str],\n    requirements: list[dict],\n    personas: list[dict],\n    revision: int = 1,\n) -> str",
      "qualified_name": "shared.bft.render_letter",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/estimate_report.py::render",
      "name": "render",
      "kind": "function",
      "file": "worker/estimate_report.py",
      "start_line": 121,
      "end_line": 205,
      "signature": "def render(estimate: Estimate, facts: EstimationFacts,\n           context: EstimationContext) -> str",
      "qualified_name": "worker.estimate_report.render",
      "language": "python",
      "score": 55.05,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/brainstorming/scripts/server.cjs::renderBranding",
      "name": "renderBranding",
      "kind": "function",
      "file": ".claude/skills/brainstorming/scripts/server.cjs",
      "start_line": 254,
      "end_line": 256,
      "signature": "function renderBranding(html)",
      "qualified_name": ".claude.skills.brainstorming.scripts.server.renderBranding",
      "language": "javascript",
      "score": 15.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/writing-skills/render-graphs.js::extractGraphBody",
      "name": "extractGraphBody",
      "kind": "function",
      "file": ".claude/skills/writing-skills/render-graphs.js",
      "start_line": 38,
      "end_line": 49,
      "signature": "function extractGraphBody(dotContent)",
      "qualified_name": ".claude.skills.writing-skills.render-graphs.extractGraphBody",
      "language": "javascript",
      "score": 15.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/writing-skills/render-graphs.js::main",
      "name": "main",
      "kind": "function",
      "file": ".claude/skills/writing-skills/render-graphs.js",
      "start_line": 84,
      "end_line": 166,
      "signature": "function main()",
      "qualified_name": ".claude.skills.writing-skills.render-graphs.main",
      "language": "javascript",
      "score": 15.02,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/bft.py"
    },
    {
      "path": "worker/estimate_report.py"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/server.cjs"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js"
    }
  ],
  "exact_match": true
}

## Ход 4 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "docs/BFT.md",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "shared/bft.py::render_letter",
  "depth": 1
}
```

**Ответ:**

{
  "symbol_id": "shared/bft.py::render_letter",
  "file": "shared/bft.py",
  "name": "render_letter",
  "kind": "function",
  "qualified_name": "shared.bft.render_letter",
  "signature": "def render_letter(\n    *,\n    goal: str,\n    how_to_demo: list[str],\n    open_questions: list[str],\n    scope: str,\n    documentation: list[str],\n    requirements: list[dict],\n    personas: list[dict],\n    revision: int = 1,\n) -> str",
  "language": "python",
  "start_line": 175,
  "end_line": 240,
  "symbol_start_line": 175,
  "symbol_end_line": 240,
  "source": "   175\tdef render_letter(\n   176\t    *,\n   177\t    goal: str,\n   178\t    how_to_demo: list[str],\n   179\t    open_questions: list[str],\n   180\t    scope: str,\n   181\t    documentation: list[str],\n   182\t    requirements: list[dict],\n   183\t    personas: list[dict],\n   184\t    revision: int = 1,\n   185\t) -> str:\n   186\t    \"\"\"Комментарий fast-режима: письмо `/bft-fast` плюс приписка про `/bft-deep`.\n   187\t\n   188\t    Порядок блоков письма зафиксирован скиллом (`letter_format.md`) и здесь не\n   189\t    меняется: `Цель` → `How to demo` → `Открытые вопросы` → `Границы` →\n   190\t    `Документация`. Таблицы требований и персон идут после письма — в оригинале\n   191\t    это csv-вложение, которого в Issue быть не может.\n   192\t\n   193\t    Пустой блок не выводится вовсе: пустой заголовок читается как «мы про это\n   194\t    подумали и там ничего нет», а на деле означает «данных не было».\n   195\t    \"\"\"\n   196\t    parts: list[str] = [\"## 📋 БФТ (быстрый проход)\"]\n   197\t    if revision > 1:\n   198\t        parts.append(f\"_Редакция {revision} — с учётом замечаний из обсуждения._\")\n   199\t\n   200\t    parts.append(f\"**Цель:** {goal.strip()}\")\n   201\t\n   202\t    demo = _numbered(how_to_demo)\n   203\t    if demo:\n   204\t        parts.append(f\"**How to demo:**\\n{demo}\")\n   205\t\n   206\t    questions = [q.strip() for q in open_questions if q and q.strip()]\n   207\t    if questions:\n   208\t        parts.append(f\"**Открытые вопросы:**\\n{_bullets(questions)}\")\n   209\t\n   210\t    if scope and scope.strip():\n   211\t        parts.append(f\"**Границы:** {scope.strip()}\")\n   212\t\n   213\t    docs = _bullets(documentation)\n   214\t    if docs:\n   215\t        parts.append(f\"**Документация:**\\n{docs}\")\n   216\t\n   217\t    table = _table(requirements, [\n   218\t        (\"id\", \"ID\"),\n   219\t        (\"as_is\", \"Сейчас (AS IS)\"),\n   220\t        (\"to_be\", \"После (TO BE)\"),\n   221\t        (\"related\", \"Связанные\"),\n   222\t        (\"source\", \"Источник\"),\n   223\t    ])\n   224\t    if table:\n   225\t        parts.append(f\"**Ключевые требования:**\\n\\n{table}\")\n   226\t\n   227\t    people = _table(personas, [(\"name\", \"Кто\"), (\"role\", \"Роль\"), (\"unit\", \"Департамент\")])\n   228\t    if people:\n   229\t        parts.append(f\"**Стейкхолдеры:**\\n\\n{people}\")\n   230\t\n   231\t    parts.append(\"---\")\n   232\t    if questions:\n   233\t        parts.append(f\"{DEEP_HINT}\\n\\n{_numbered(questions)}\")\n   234\t    else:\n   235\t        parts.append(DEEP_HINT_NO_QUESTIONS)\n   236\t    parts.append(\n   237\t        \"Не согласны с формулировкой — вызовите `/bft` с замечаниями в том же \"\n   238\t        \"комментарии, и БФТ пересоберётся с их учётом.\"\n   239\t    )\n   240\t    return \"\\n\\n\".join(parts)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.18,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6049
  }
}

## Ход 6 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "path",
  "query": "test_bft"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "No indexed match for identifier 'test_bft'. Retry with mode=\"symbol\" (or check spelling/casing); if you need every literal usage for an exhaustive sweep such as a rename, Grep is the right tool for that."
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "BFT documentation format"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "page_type": "infra_page",
      "snippet": "# Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh\n\n**Type:** shell\n\n## Overview\n\n`.claude/skills/technical-documentation/scripts/find_sql_queries.sh` is an infrastru",
      "relevance_score": 3.015,
      "sources": [
        "fts"
      ],
      "target_path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh",
      "confidence_score": 1.0
    },
    {
      "title": "File: worker/worker.py",
      "page_type": "file_page",
      "snippet": "t_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bft_workflow.py`\n- `tests/test_clarify_after_analysis.py`\n- `tests/test_comment_ack.py`\n- `tests/tes",
      "relevance_score": 2.981,
      "sources": [
        "fts"
      ],
      "target_path": "worker/worker.py",
      "confidence_score": 0.99
    },
    {
      "title": "Symbol: worker.activities.run_bft_fast",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_bft_fast\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_bft_fast(req: BftRequest) -> str\n```\n\n## Overview",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_fast",
      "file": "worker/activities.py",
      "confidence_score": 0.96
    },
    {
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "# shared/bft.py\n\n## Overview\n\nБФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py",
      "relevance_score": 2.887,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "confidence_score": 0.96
    },
    {
      "title": "Symbol: worker.activities.BftLetterExtraction",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.BftLetterExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass BftLetterExtraction\n```\n\n## Overview\n\n`BftLetterExtraction` i",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::BftLetterExtraction",
      "file": "worker/activities.py",
      "confidence_score": 0.93
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
    },
    {
      "path": "worker/worker.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/bft.py"
    },
    {
      "path": "worker/estimation.py"
    }
  ]
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "path",
  "query": "tests/test_bft"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "Query names identifier(s) 'test_bft' but nothing matched. Search the identifier alone with mode=\"symbol\", then pipe the hit into get_symbol for its body. For an exhaustive every-usage sweep, Grep the literal name."
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "path",
  "query": "docs/"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 10 · `get_context` · contour

**Запрос:**

```json
{
  "include": [
    "ownership",
    "last_change",
    "callers"
  ],
  "targets": [
    "worker/activities.py"
  ]
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
        "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "symbols": [
          {
            "name": "logger",
            "kind": "variable",
            "signature": "logger = logging.getLogger(__name__)",
            "line": 66,
            "symbol_id": "worker/activities.py::logger"
          },
          {
            "name": "PROMPTS_DIR",
            "kind": "constant",
            "signature": "PROMPTS_DIR = Path(\"/app/prompts\")",
            "line": 68,
            "symbol_id": "worker/activities.py::PROMPTS_DIR"
          },
          {
            "name": "CONFIG_DIR",
            "kind": "constant",
            "signature": "CONFIG_DIR = Path(\"/app/config\")",
            "line": 69,
            "symbol_id": "worker/activities.py::CONFIG_DIR"
          },
          {
            "name": "WORKSPACE_DIR",
            "kind": "constant",
            "signature": "WORKSPACE_DIR = Path(\"/app/workspace\")",
            "line": 70,
            "symbol_id": "worker/activities.py::WORKSPACE_DIR"
          },
          {
            "name": "_load_prompt",
            "kind": "function",
            "signature": "def _load_prompt(name: str) -> str",
            "line": 73,
            "symbol_id": "worker/activities.py::_load_prompt"
          },
          {
            "name": "GateExtraction",
            "kind": "class",
            "signature": "class GateExtraction",
            "line": 79,
            "symbol_id": "worker/activities.py::GateExtraction"
          },
          {
            "name": "ClassificationExtraction",
            "kind": "class",
            "signature": "class ClassificationExtraction",
            "line": 84,
            "symbol_id": "worker/activities.py::ClassificationExtraction"
          },
          {
            "name": "DuplicateCandidate",
            "kind": "class",
            "signature": "class DuplicateCandidate",
            "line": 89,
            "symbol_id": "worker/activities.py::DuplicateCandidate"
          },
          {
            "name": "DuplicateExtraction",
            "kind": "class",
            "signature": "class DuplicateExtraction",
            "line": 95,
            "symbol_id": "worker/activities.py::DuplicateExtraction"
          },
          {
            "name": "PriorityExtraction",
            "kind": "class",
            "signature": "class PriorityExtraction",
            "line": 99,
            "symbol_id": "worker/activities.py::PriorityExtraction"
          },
          {
            "name": "prefilter_bot_and_security",
            "kind": "function",
            "signature": "def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str | None",
            "line": 116,
            "symbol_id": "worker/activities.py::prefilter_bot_and_security"
          },
          {
            "name": "intake_gate",
            "kind": "function",
            "signature": "def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult",
            "line": 164,
            "symbol_id": "worker/activities.py::intake_gate"
          },
          {
            "name": "post_clarifying_question",
            "kind": "function",
            "signature": "def post_clarifying_question(issue: IssueInput, questions: str) -> None",
            "line": 174,
            "symbol_id": "worker/activities.py::post_clarifying_question"
          },
          {
            "name": "close_as_spam",
            "kind": "function",
            "signature": "def close_as_spam(issue: IssueInput, reason: str) -> None",
            "line": 180,
            "symbol_id": "worker/activities.py::close_as_spam"
          },
          {
            "name": "escalate_to_human",
            "kind": "function",
            "signature": "def escalate_to_human(issue: IssueInput, reason: str = \"\") -> None",
            "line": 187,
            "symbol_id": "worker/activities.py::escalate_to_human"
          },
          {
            "name": "set_phase",
            "kind": "function",
            "signature": "def set_phase(repo: str, issue_number: int, phase: str) -> None",
            "line": 199,
            "symbol_id": "worker/activities.py::set_phase"
          },
          {
            "name": "mark_awaiting",
            "kind": "function",
            "signature": "def mark_awaiting(repo: str, issue_number: int, waiting=None) -> None",
            "line": 227,
            "symbol_id": "worker/activities.py::mark_awaiting"
          },
          {
            "name": "read_deadlines",
            "kind": "function",
            "signature": "def read_deadlines() -> Deadlines",
            "line": 250,
            "symbol_id": "worker/activities.py::read_deadlines"
          },
          {
            "name": "OPEN_QUESTION_MARKER",
            "kind": "constant",
            "signature": "OPEN_QUESTION_MARKER = \"[УТОЧНИТЬ]\"",
            "line": 297,
            "symbol_id": "worker/activities.py::OPEN_QUESTION_MARKER"
          },
          {
            "name": "MAX_OPEN_QUESTIONS",
            "kind": "constant",
            "signature": "MAX_OPEN_QUESTIONS = 15",
            "line": 298,
            "symbol_id": "worker/activities.py::MAX_OPEN_QUESTIONS"
          },
          {
            "name": "_open_questions",
            "kind": "function",
            "signature": "def _open_questions(repo: str, branch: str) -> list[str]",
            "line": 301,
            "symbol_id": "worker/activities.py::_open_questions"
          },
          {
            "name": "read_open_questions",
            "kind": "function",
            "signature": "def read_open_questions(repo: str, branch: str) -> list[str]",
            "line": 322,
            "symbol_id": "worker/activities.py::read_open_questions"
          },
          {
            "name": "ask_open_questions",
            "kind": "function",
            "signature": "def ask_open_questions(issue: IssueInput, questions: list[str], round_number: int) -> None",
            "line": 334,
            "symbol_id": "worker/activities.py::ask_open_questions"
          },
          {
            "name": "mark_ready_for_dev",
            "kind": "function",
            "signature": "def mark_ready_for_dev(issue: IssueInput, priority_tier: str, branch: str) -> None",
            "line": 355,
            "symbol_id": "worker/activities.py::mark_ready_for_dev"
          },
          {
            "name": "post_agents_off_notice",
            "kind": "function",
            "signature": "def post_agents_off_notice(repo: str, issue_number: int, what: str) -> None",
            "line": 390,
            "symbol_id": "worker/activities.py::post_agents_off_notice"
          },
          {
            "name": "read_protocol_state",
            "kind": "function",
            "signature": "def read_protocol_state(repo: str, issue_number: int) -> ProtocolState",
            "line": 405,
            "symbol_id": "worker/activities.py::read_protocol_state"
          },
          {
            "name": "post_error_label",
            "kind": "function",
            "signature": "def post_error_label(issue: IssueInput, reason: str = \"\") -> None",
            "line": 448,
            "symbol_id": "worker/activities.py::post_error_label"
          },
          {
            "name": "mark_analyzing",
            "kind": "function",
            "signature": "async def mark_analyzing(repo: str, issue_number: int) -> None",
            "line": 468,
            "symbol_id": "worker/activities.py::mark_analyzing"
          },
          {
            "name": "mark_command_running",
            "kind": "function",
            "signature": "async def mark_command_running(repo: str, issue_number: int, command: str) -> None",
            "line": 477,
            "symbol_id": "worker/activities.py::mark_command_running"
          },
          {
            "name": "finish_command_labels",
            "kind": "function",
            "signature": "async def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
            "line": 487,
            "symbol_id": "worker/activities.py::finish_command_labels"
          },
          {
            "name": "classify_issue",
            "kind": "function",
            "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
            "line": 517,
            "symbol_id": "worker/activities.py::classify_issue"
          },
          {
            "name": "duplicate_check",
            "kind": "function",
            "signature": "def duplicate_check(issue: IssueInput) -> DuplicateResult",
            "line": 635,
            "symbol_id": "worker/activities.py::duplicate_check"
          },
          {
            "name": "score_priority",
            "kind": "function",
            "signature": "def score_priority(issue: IssueInput, classification: ClassificationResult | None, dup: DuplicateResult) -> PriorityResult",
            "line": 686,
            "symbol_id": "worker/activities.py::score_priority"
          },
          {
            "name": "post_priority_comment",
            "kind": "function",
            "signature": "def post_priority_comment(issue: IssueInput, priority: PriorityResult, dup: DuplicateResult) -> None",
            "line": 736,
            "symbol_id": "worker/activities.py::post_priority_comment"
          },
          {
            "name": "FNR_DIR",
            "kind": "constant",
            "signature": "FNR_DIR = \"sa_documentation/FNR/FNR_1\"",
            "line": 749,
            "symbol_id": "worker/activities.py::FNR_DIR"
          },
          {
            "name": "ARTIFACT_FILES",
            "kind": "constant",
            "signature": "ARTIFACT_FILES = (\"repowise-dialog.md\", \"task.md\", \"concept.md\",",
            "line": 750,
            "symbol_id": "worker/activities.py::ARTIFACT_FILES"
          },
          {
            "name": "CLAUDE_STAGE_TIMEOUT_SEC",
            "kind": "constant",
            "signature": "CLAUDE_STAGE_TIMEOUT_SEC = 900",
            "line": 752,
            "symbol_id": "worker/activities.py::CLAUDE_STAGE_TIMEOUT_SEC"
          },
          {
            "name": "REPOMIX_TIMEOUT_SEC",
            "kind": "constant",
            "signature": "REPOMIX_TIMEOUT_SEC = 600",
            "line": 753,
            "symbol_id": "worker/activities.py::REPOMIX_TIMEOUT_SEC"
          },
          {
            "name": "CLONE_TIMEOUT_SEC",
            "kind": "constant",
            "signature": "CLONE_TIMEOUT_SEC = 300",
            "line": 754,
            "symbol_id": "worker/activities.py::CLONE_TIMEOUT_SEC"
          },
          {
            "name": "HEARTBEAT_INTERVAL_SEC",
            "kind": "constant",
            "signature": "HEARTBEAT_INTERVAL_SEC = 30.0",
            "line": 755,
            "symbol_id": "worker/activities.py::HEARTBEAT_INTERVAL_SEC"
          }
        ],
        "symbols_truncated": {
          "shown": 40,
          "total": 165,
          "hint": "Call with compact=False or include=['full_doc'] for the full list."
        }
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
          "file": "tests/test_analysis_pipeline.py",
          "imports": true,
          "inbound_calls": 44
        },
        {
          "file": "tests/test_bft_activities.py",
          "imports": true,
          "inbound_calls": 35
        },
        {
          "file": "tests/test_develop.py",
          "imports": true,
          "inbound_calls": 14
        },
        {
          "file": "tests/test_command_label_activities.py",
          "imports": true,
          "inbound_calls": 13
        },
        {
          "file": "tests/test_repowise_stage.py",
          "imports": true,
          "inbound_calls": 13
        },
        {
          "file": "tests/test_estimate_activities.py",
          "imports": true,
          "inbound_calls": 12
        },
        {
          "file": "tests/test_build_task_context.py",
          "imports": true,
          "inbound_calls": 9
        },
        {
          "file": "tests/test_repowise_develop.py",
          "imports": true,
          "inbound_calls": 9
        },
        {
          "file": "tests/test_activities_error.py",
          "imports": true,
          "inbound_calls": 8
        },
        {
          "file": "tests/test_bft_partial_resume.py",
          "imports": true,
          "inbound_calls": 8
        },
        {
          "file": "tests/test_protocol_state.py",
          "imports": true,
          "inbound_calls": 8
        },
        {
          "file": "tests/test_fnr_partial_resume.py",
          "imports": true,
          "inbound_calls": 7
        },
        {
          "file": "tests/test_bft_entire_session.py",
          "imports": true,
          "inbound_calls": 6
        },
        {
          "file": "tests/test_develop_followups.py",
          "imports": true,
          "inbound_calls": 5
        },
        {
          "file": "tests/test_ready_for_dev.py",
          "imports": true,
          "inbound_calls": 5
        },
        {
          "file": "tests/test_activities_analyze.py",
          "imports": true,
          "inbound_calls": 4
        },
        {
          "file": "tests/test_bft_direct_stage.py",
          "imports": true,
          "inbound_calls": 4
        },
        {
          "file": "tests/test_develop_autostart.py",
          "imports": true,
          "inbound_calls": 4
        },
        {
          "file": "tests/test_park_deadlines.py",
          "imports": true,
          "inbound_calls": 4
        },
        {
          "file": "tests/test_dev_handoff_once.py",
          "imports": true,
          "inbound_calls": 3
        }
      ],
      "_call_graph_note": "File-level rollup: importing files plus inbound cross-file call counts. For symbol-precise callers pass 'file.py::Symbol'.",
      "episodes": 20
    }
  },
  "_meta": {
    "timing_ms": 102.2,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
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
  "depth": 2,
  "symbol_id": "worker/activities.py::run_bft_fast"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::run_bft_fast",
  "file": "worker/activities.py",
  "name": "run_bft_fast",
  "kind": "function",
  "qualified_name": "worker.activities.run_bft_fast",
  "signature": "async def run_bft_fast(req: BftRequest) -> str",
  "language": "python",
  "start_line": 2286,
  "end_line": 2316,
  "symbol_start_line": 2286,
  "symbol_end_line": 2316,
  "source": "  2286\tasync def run_bft_fast(req: BftRequest) -> str:\n  2287\t    \"\"\"Быстрый проход: письмо БФТ комментарием в Issue.\n  2288\t\n  2289\t    Один вызов модели, без клона и без claude-code: формат `/bft-fast` — это\n  2290\t    структурирование уже сказанного, а не исследование кода. Клонировать\n  2291\t    репозиторий ради него значило бы платить минутами за то, что нужно секундами.\n  2292\t\n  2293\t    Возвращает опубликованный текст — он же уходит в историю Temporal, поэтому\n  2294\t    разбор «что именно агент отписал» не требует лезть в GitHub.\n  2295\t    \"\"\"\n  2296\t    thread, revision = await asyncio.to_thread(_bft_thread, req)\n  2297\t    letter = await asyncio.to_thread(\n  2298\t        llm.extract,\n  2299\t        _load_prompt(\"system_bft_fast.md\"),\n  2300\t        _bft_user_message(req, thread),\n  2301\t        BftLetterExtraction,\n  2302\t        llm.MODEL_CLASSIFY,\n  2303\t    )\n  2304\t    body = bft.render_letter(\n  2305\t        goal=letter.goal,\n  2306\t        how_to_demo=letter.how_to_demo,\n  2307\t        open_questions=letter.open_questions,\n  2308\t        scope=letter.scope,\n  2309\t        documentation=letter.documentation,\n  2310\t        requirements=[r.model_dump() for r in letter.requirements],\n  2311\t        personas=[p.model_dump() for p in letter.personas],\n  2312\t        revision=revision,\n  2313\t    )\n  2314\t    await asyncio.to_thread(\n  2315\t        github_client.post_comment, req.repo, req.issue_number, body)\n  2316\t    return body",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 19.11,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
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
        "symbol_id": "worker/activities.py::_load_prompt",
        "name": "_load_prompt",
        "file": "worker/activities.py",
        "kind": "function",
        "signature": "def _load_prompt(name: str) -> str",
        "depth": 1,
        "start_line": 73,
        "end_line": 74,
        "source": "    73\tdef _load_prompt(name: str) -> str:\n    74\t    return (PROMPTS_DIR / name).read_text(encoding=\"utf-8\")",
        "verified": true
      },
      {
        "symbol_id": "worker/activities.py::_bft_user_message",
        "name": "_bft_user_message",
        "file": "worker/activities.py",
        "kind": "function",
        "signature": "def _bft_user_message(req: BftRequest, thread: str) -> str",
        "depth": 1,
        "start_line": 2228,
        "end_line": 2238,
        "source": "  2228\tdef _bft_user_message(req: BftRequest, thread: str) -> str:\n  2229\t    parts = [f\"# Issue {req.repo}#{req.issue_number}: {req.title}\", \"\",\n  2230\t             \"## Описание\", \"\", req.body.strip() or \"(тело пустое)\"]\n  2231\t    if req.instructions.strip():\n  2232\t        parts += [\"\", \"## Замечания и уточнения к этой редакции\", \"\",\n  2233\t                  \"> Правки человека к БФТ. Сильнее и текста Issue, и прежней \"\n  2234\t                  \"редакции: человек уточняет собственный запрос.\", \"\",\n  2235\t                  req.instructions.strip()]\n  2236\t    if thread:\n  2237\t        parts += [\"\", \"## Вся переписка Issue\", \"\", thread]\n  2238\t    return \"\\n\".join(parts)",
        "verified": true
      }
    ]
  }
}

## Ход 12 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "symbol",
  "query": "render_letter"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/bft.py::render_letter",
      "name": "render_letter",
      "kind": "function",
      "file": "shared/bft.py",
      "start_line": 175,
      "end_line": 240,
      "signature": "def render_letter(\n    *,\n    goal: str,\n    how_to_demo: list[str],\n    open_questions: list[str],\n    scope: str,\n    documentation: list[str],\n    requirements: list[dict],\n    personas: list[dict],\n    revision: int = 1,\n) -> str",
      "qualified_name": "shared.bft.render_letter",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/estimate_report.py::render",
      "name": "render",
      "kind": "function",
      "file": "worker/estimate_report.py",
      "start_line": 121,
      "end_line": 205,
      "signature": "def render(estimate: Estimate, facts: EstimationFacts,\n           context: EstimationContext) -> str",
      "qualified_name": "worker.estimate_report.render",
      "language": "python",
      "score": 55.05,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/brainstorming/scripts/server.cjs::renderBranding",
      "name": "renderBranding",
      "kind": "function",
      "file": ".claude/skills/brainstorming/scripts/server.cjs",
      "start_line": 254,
      "end_line": 256,
      "signature": "function renderBranding(html)",
      "qualified_name": ".claude.skills.brainstorming.scripts.server.renderBranding",
      "language": "javascript",
      "score": 15.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/writing-skills/render-graphs.js::extractGraphBody",
      "name": "extractGraphBody",
      "kind": "function",
      "file": ".claude/skills/writing-skills/render-graphs.js",
      "start_line": 38,
      "end_line": 49,
      "signature": "function extractGraphBody(dotContent)",
      "qualified_name": ".claude.skills.writing-skills.render-graphs.extractGraphBody",
      "language": "javascript",
      "score": 15.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/writing-skills/render-graphs.js::main",
      "name": "main",
      "kind": "function",
      "file": ".claude/skills/writing-skills/render-graphs.js",
      "start_line": 84,
      "end_line": 166,
      "signature": "function main()",
      "qualified_name": ".claude.skills.writing-skills.render-graphs.main",
      "language": "javascript",
      "score": 15.02,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/bft.py"
    },
    {
      "path": "worker/estimate_report.py"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/server.cjs"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js"
    }
  ],
  "exact_match": true
}

## Ход 13 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "concept",
  "query": "DEEP_HINT bft",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
    {
      "title": "File: shared/bft.py",
      "page_type": "file_page",
      "snippet": "# shared/bft.py\n\n## Overview\n\nБФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py",
      "relevance_score": 3.03,
      "sources": [
        "fts"
      ],
      "target_path": "shared/bft.py",
      "confidence_score": 1.0
    },
    {
      "title": "Symbol: worker.activities.publish_bft_deep",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.publish_bft_deep\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 2\n\n```\nasync def publish_bft_deep(req: BftRequest) -> str\n```\n\n##",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::publish_bft_deep",
      "file": "worker/activities.py",
      "confidence_score": 0.97
    },
    {
      "title": "Symbol: worker.activities.cleanup_bft_workspace",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.cleanup_bft_workspace\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def cleanup_bft_workspace(req: BftRequest) -> No",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::cleanup_bft_workspace",
      "file": "worker/activities.py",
      "confidence_score": 0.96
    },
    {
      "title": "Symbol: worker.activities.prepare_bft_workspace",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.prepare_bft_workspace\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def prepare_bft_workspace(req: BftRequest) -> No",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::prepare_bft_workspace",
      "file": "worker/activities.py",
      "confidence_score": 0.94
    },
    {
      "title": "Symbol: worker.activities.run_bft_fast",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_bft_fast\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_bft_fast(req: BftRequest) -> str\n```\n\n## Overview",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_fast",
      "file": "worker/activities.py",
      "confidence_score": 0.93
    },
    {
      "title": "Symbol: worker.activities.publish_bft_error",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.publish_bft_error\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 2\n\n```\nasync def publish_bft_error(req: BftRequest, reason: str)",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::publish_bft_error",
      "file": "worker/activities.py",
      "confidence_score": 0.91
    },
    {
      "title": "Symbol: worker.activities.publish_bft_partial",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.publish_bft_partial\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 4\n\n```\nasync def publish_bft_partial(req: BftRequest, reason: s",
      "relevance_score": 2.727,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::publish_bft_partial",
      "file": "worker/activities.py",
      "confidence_score": 0.9
    },
    {
      "title": "Symbol: worker.activities.run_bft_stage",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 8\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) -> d",
      "relevance_score": 2.687,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_stage",
      "file": "worker/activities.py",
      "confidence_score": 0.89
    },
    {
      "title": "File: shared/commands.py",
      "page_type": "file_page",
      "snippet": "| `ESTIMATE` | constant | ESTIMATE = \"estimate\" |\n| `ANALYZE` | constant | ANALYZE = \"analyze\" |\n| `BFT` | constant | BFT = \"bft\" |\n| `BFT_DEEP` | constant | BFT_DEEP = \"bft-deep\" |\n| `RUN_PREFIX` | c",
      "relevance_score": 2.677,
      "sources": [
        "fts"
      ],
      "target_path": "shared/commands.py",
      "confidence_score": 0.88
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "and: str, ok: bool) -> None |\n| `classify_issue` | function | def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult |\n| `FOLLOWUP_THREAD_COMMENTS` | constant | FOL",
      "relevance_score": 2.639,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "confidence_score": 0.87
    }
  ],
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/bft.py"
    },
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
      "path": "shared/workflow_types.py"
    }
  ]
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "shared/bft.py::DEEP_HINT"
}
```

**Ответ:**

{
  "symbol_id": "shared/bft.py::DEEP_HINT",
  "file": "shared/bft.py",
  "name": "DEEP_HINT",
  "kind": "constant",
  "qualified_name": "shared.bft.DEEP_HINT",
  "signature": "DEEP_HINT = (",
  "language": "python",
  "start_line": 135,
  "end_line": 138,
  "symbol_start_line": 135,
  "symbol_end_line": 138,
  "source": "   135\tDEEP_HINT = (\n   136\t    \"Если задача касается больших изменений — запустите команду `/bft-deep` \"\n   137\t    \"и ответьте на ряд этих уточняющих вопросов:\"\n   138\t)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.26,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6049
  }
}

## Ход 15 · `get_symbol` · contour

**Запрос:**

```json
{
  "depth": 1,
  "symbol_id": "worker/activities.py::BftLetterExtraction"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::BftLetterExtraction",
  "file": "worker/activities.py",
  "name": "BftLetterExtraction",
  "kind": "class",
  "qualified_name": "worker.activities.BftLetterExtraction",
  "signature": "class BftLetterExtraction",
  "language": "python",
  "start_line": 2180,
  "end_line": 2188,
  "symbol_start_line": 2180,
  "symbol_end_line": 2188,
  "source": "  2180\tclass BftLetterExtraction(BaseModel):\n  2181\t    goal: str = Field(description=\"1-2 предложения, WHY вперёд\")\n  2182\t    how_to_demo: list[str] = Field(default_factory=list, description=\"шаги E2E-приёмки\")\n  2183\t    open_questions: list[str] = Field(default_factory=list,\n  2184\t                                      description=\"вопрос/блокер/решение, владелец в скобках\")\n  2185\t    scope: str = Field(default=\"\", description=\"in-scope (out-of-scope — не входит в зону БФТ)\")\n  2186\t    documentation: list[str] = Field(default_factory=list)\n  2187\t    requirements: list[BftRequirementExtraction] = Field(default_factory=list)\n  2188\t    personas: list[BftPersonaExtraction] = Field(default_factory=list)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 26.73,
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "mode": "path",
  "query": "tests/test_bft_activities.py"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "a223cc6ade57",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "Query names identifier(s) 'test_bft_activities' but nothing matched. Search the identifier alone with mode=\"symbol\", then pipe the hit into get_symbol for its body. For an exhaustive every-usage sweep, Grep the literal name."
}
