# Итог

## Текущее состояние разделения моделей

### Layer A (автотриаж, worker/llm.py)
- **`MODEL_GATE`** (дефолт `glm-4.5-air`) — используется для простых/дешёвых операций:
  - `intake_gate` (worker/activities.py:168)
  - `duplicate_check` (worker/activities.py:650)
  - `score_priority` (worker/activities.py:698)
- **`MODEL_CLASSIFY`** (дефолт в коде `glm-5.2`, в .env.example `glm-4.6`) — используется для более сложных задач:
  - `classify_issue` (worker/activities.py:538)
  - `extract_estimation_facts` (worker/activities.py:2985)
  - Другие операции в consolidation_activities.py

**Рассинхрон:** Дефолт в `llm.py:20` (`glm-5.2`) отличается от .env.example (`glm-4.6`).

### Layer C (FNR-пайплайн `/analyze`, worker/activities.py)
- **Нет дифференциации моделей** — все 6 стадий запускаются через `_run_claude()` (worker/activities.py:943) с одними и теми же кредами:
  1. `repowise` — сбор контекста из индекса кода (через `/repowise-context`)
  2. `task` — структурирование постановки (`/fnr-new-task`)
  3. `concept` — генерация концептов (`/fnr-concept`)
  4. `debate` — архитектурные дебаты (`/fnr-debate`)
  5. `sysreq` — системные требования (`/fnr-system-requirements`)
  6. `validate` — валидация (`/validate-doc`)

- `_run_claude()` получает креды через `_claude_anthropic_creds()` (worker/activities.py:926), который выводит их из `ZAI_*` переменных окружения в `ANTHROPIC_*` формат для `claude -p`.
- **Нет механизма для выбора разных моделей по стадиям** — используется единая модель для всего пайплайна.

### Затронутые файлы
- `worker/llm.py` — текущая конфигурация `MODEL_GATE`/`MODEL_CLASSIFY`
- `worker/activities.py` — функции `_fnr_stages()` (764), `_fnr_stage()` (807), `_run_claude()` (943), `_claude_anthropic_creds()` (926), `run_fnr_stage()` (1266)
- `.env.example` — дефолтные значения переменных окружения (строки 147-148)
- `docs/superpowers/specs/2026-07-12-issue-agent-layer-a-triage-design.md` — документация по Layer A (строки 167-171 описывают текущее разделение)

## Ключевые находки

1. **Per-stage конфигурация отсутствует** — `_run_claude()` не принимает параметр модели, все стадии используют одинаковую конфигурацию.
2. **Существующая матрица Layer A** (из спеки):
   - GLM-air (дешёвый): intake_gate, duplicate_check, priority scoring
   - GLM-5.2/4.6 (сильный): classify_issue, advisor-ответ
3. **Рассинхрон дефолтов** — `MODEL_CLASSIFY` в коде (`glm-5.2`) ≠ .env.example (`glm-4.6`).
4. **Потенциал для оптимизации** — стадии FNR сильно различаются по сложности:
   - Простые: `task` (структурирование), `validate` (проверка)
   - Сложные: `debate` (архитектурные дебаты), `sysreq` (генерация требований)
5. **Конфигурация БФТ** — в .env.example уже есть `BFT_DIRECT_MODEL=glm-4.6` (строка 156) для прямых вызовов, что показывает precedent для per-stage конфигурации.

# Открытые вопросы

Нет — индекс ответил на все вопросы по текущей архитектуре.

# Диалог

## Ход 1: Обзор репозитория
**Инструмент:** `get_overview`
**Вопрос:** Какова общая структура репозитория и какие модули задействованы в LLM-вызовах?
**Ответ:** Получен обзор: 323 файла, 80K строк. Ключевые модули:
- `worker/` — Activities, LLM-клиент, воркфлоу (hotspot: activities.py)
- `shared/` — Утилиты, типы воркфлоу
- `config/` — Конфигурация (estimation-rules.toml)
Репозиторий part of workspace `contour` с соседями: poh-bft-writer, poh-pr-agents, poh-helper.

## Ход 2: Контекст ключевых файлов
**Инструмент:** `get_context` для `worker/llm.py` и `worker/activities.py`
**Вопрос:** Как устроена текущая конфигурация моделей и где находятся функции FNR-стадий?
**Ответ:**
- `worker/llm.py`: содержит `MODEL_GATE` и `MODEL_CLASSIFY`, функции `extract()` и `complete()` для Instructor-клиента.
- `worker/activities.py`: hotspot (20 фиксов), содержит всю логику FNR-стадий. Skeleton сокращён (omission ref).

## Ход 3: Детали FNR-стадий
**Инструмент:** `get_symbol` для `_fnr_stages`, `_run_claude`, `_claude_anthropic_creds`
**Вопрос:** Как определены стадии FNR и как они запускаются?
**Ответ:**
- `_fnr_stages()` (764-782): возвращает 6 стадий с промптами и ожидаемыми артефактами.
- `_run_claude()` (943-988): запускает `claude -p` subprocess с кредами из `_claude_anthropic_creds()`.
- `_claude_anthropic_creds()` (926-940): выводит Anthropic-креды из ZAI_* переменных.

## Ход 4: Переменные окружения
**Инструмент:** `Read` для `.env.example`
**Вопрос:** Какие переменные конфигурируют модели сейчас?
**Ответ:**
- `MODEL_GATE=glm-4.5-air`
- `MODEL_CLASSIFY=glm-4.6`
- `BFT_DIRECT_MODEL=glm-4.6` (для БФТ стадий)
- `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` закомментированы (выводятся из ZAI_*)

## Ход 5: Использование MODEL_GATE/CLASSIFY
**Инструмент:** `get_symbol` для `intake_gate`, `classify_issue`, `extract_estimation_facts` + grep
**Вопрос:** Какие функции используют MODEL_GATE и MODEL_CLASSIFY?
**Ответ:**
- `MODEL_GATE`: intake_gate (168), duplicate_check (650), score_priority (698)
- `MODEL_CLASSIFY`: classify_issue (538), extract_estimation_facts (2985), plus consolidation_activities.py
- **Рассинхрон:** дефолт в llm.py (`glm-5.2`) ≠ .env.example (`glm-4.6`)

## Ход 6: Поиск документации Layer A
**Инструмент:** `find` + `Read` для `2026-07-12-issue-agent-layer-a-triage-design.md`
**Вопрос:** Есть ли документация по текущему разделению моделей в Layer A?
**Ответ:** Документ найден в `docs/superpowers/specs/`. Строки 167-171 описывают:
- intake_gate (GLM-air)
- classify_issue (GLM-5.2)
- duplicate_check (GLM-air)
- score_priority (GLM + Python)
Подтверждает current two-tier конфиг, но без per-stage для Layer C.

## Ход 7: Детали run_fnr_stage
**Инструмент:** `get_symbol` для `run_fnr_stage`, `_fnr_stage`
**Вопрос:** Как запускается каждая стадия FNR и можно ли передать модель?
**Ответ:**
- `run_fnr_stage()` (1266-1321): запускает одну стадию, вызывает `_run_claude()`.
- `_fnr_stage()` (807-812): получает (промпт, артефакт, requires) по имени стадии.
- **Нет параметра для модели** — все стадии используют одинаковый `_run_claude()`.

## Ход 8: Проверка всех использований
**Инструмент:** `grep -rn "MODEL_GATE\|MODEL_CLASSIFY"`
**Вопрос:** Все ли использования моделей учтены?
**Ответ:** Подтверждён полный список:
- 3 использования MODEL_GATE (intake_gate, duplicate_check, priority)
- 6+ использований MODEL_CLASSIFY (classify, extract, consolidation)
- Полная картина confirmed.


---
session: rw-analysis-po-helper-org__poh-issue-agents-65
workspace: contour
turns: 13
started: 2026-08-20T18:55:58Z
finished: 2026-08-20T18:56:21Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 16 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 16 мин |
| `poh-helper` | `18512c1e7ce9` | 16 мин |
| `poh-infra` | `ac430395f649` | 16 мин |
| `poh-issue-agents` | `a41f569f0381` | 16 мин |
| `poh-memory-engine` | `194e39319b3f` | 16 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 16 мин |
| `poh-scheduller` | `04cc3f47aff9` | 16 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 16 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 14 ч |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "null",
  "include": [
    "outline"
  ]
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
    "worker/llm.py",
    "worker/activities.py"
  ],
  "include": [
    "skeleton",
    "metrics",
    "ownership"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/llm.py": {
      "target": "worker/llm.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/llm.py",
        "summary": "LLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/ priority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт типобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON, вместо ручного json.loads()+try/except, как было в исходной версии на Actions."
      },
      "hotspot": false,
      "fix_history": {
        "fix_count": 1,
        "last_fix_days_ago": 28
      },
      "ownership": {
        "primary_owner": "kibarik",
        "owner_pct": 0.7027,
        "contributor_count": 2,
        "bus_factor": 2,
        "agent_authored_pct": 0.8,
        "agent_commit_count": 4,
        "agent_tier_counts": {
          "3": 4
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
      "metrics": {
        "pagerank": 0.006142,
        "pagerank_percentile": 94,
        "betweenness": 0.0,
        "betweenness_percentile": 0,
        "in_degree": 3,
        "out_degree": 0,
        "community_id": 4,
        "community_label": "worker"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 666,
        "full_tokens": 666,
        "pct_of_full": 100.0,
        "bodies_kept": [
          "get_client",
          "extract",
          "complete"
        ],
        "text": "\"\"\"\nLLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/\npriority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт\nтипобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON,\nвместо ручного json.loads()+try/except, как было в исходной версии на\nActions.\n\nДля po-helper/SA-helper (Claude Code skills) используется ДРУГОЙ путь —\nAnthropic-совместимый эндпоинт z.ai через переменные окружения ANTHROPIC_*,\nсм. activities.run_fnr_stage (запускает `claude -p` как subprocess,\nа не через этот клиент).\n\"\"\"\n\nimport os\n\nimport instructor\nfrom openai import OpenAI\n\nMODEL_GATE = os.environ.get(\"MODEL_GATE\", \"glm-4.5-air\")\nMODEL_CLASSIFY = os.environ.get(\"MODEL_CLASSIFY\", \"glm-5.2\")\n\n_client: instructor.Instructor | None = None\n\n\ndef get_client() -> instructor.Instructor:\n    global _client\n    if _client is None:\n        # z.ai GLM rejects OpenAI tool-calling (400 \"Invalid API parameter\" —\n        # instructor's default Mode.TOOLS). JSON mode works: the model returns\n        # a JSON object matching the Pydantic schema.\n        _client = instructor.from_openai(\n            OpenAI(\n                base_url=os.environ[\"ZAI_BASE_URL\"],\n                api_key=os.environ[\"ZAI_API_KEY\"],\n            ),\n            mode=instructor.Mode.JSON,\n        )\n    return _client\n\n\ndef extract(system_prompt: str, user_message: str, response_model, model: str = MODEL_GATE):\n    \"\"\"Структурированное извлечение — LLM обязана вернуть response_model,\n    Instructor сам ретраит при несоответствии схеме.\"\"\"\n    client = get_client()\n    return client.chat.completions.create(\n        model=model,\n        response_model=response_model,\n        max_retries=2,\n        messages=[\n            {\"role\": \"system\", \"content\": system_prompt},\n            {\"role\": \"user\", \"content\": user_message},\n        ],\n    )\n\n\ndef complete(system_prompt: str, user_message: str, *, model: str,\n             max_tokens: int = 16000, temperature: float = 0.2) -> str:\n    \"\"\"Сырой ответ модели текстом — без Pydantic-схемы.\n\n    `extract` рядом требует response_model и годится для коротких структур.\n    Стадии БФТ возвращают либо большой JSON каскада, либо готовый markdown на\n    двадцать килобайт: схемой это не описать, а Instructor на таком объёме\n    только мешает ретраями по несоответствию.\n    \"\"\"\n    resp = get_client().client.chat.completions.create(\n        model=model,\n        messages=[\n            {\"role\": \"system\", \"content\": system_prompt},\n            {\"role\": \"user\", \"content\": user_message},\n        ],\n        max_tokens=max_tokens,\n        temperature=temperature,\n    )\n    return resp.choices[0].message.content or \"\"\n",
        "verified": true,
        "mostly_full": true,
        "note": "Skeleton is 100.0% of the full file — a direct Read costs little more."
      },
      "episodes": 1
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
    "timing_ms": 388.4,
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

## Ход 3 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_fnr_stages"
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
  "start_line": 764,
  "end_line": 782,
  "symbol_start_line": 764,
  "symbol_end_line": 782,
  "source": "   764\tdef _fnr_stages(description: str) -> list[tuple[str, str, str | None]]:\n   765\t    \"\"\"Стадии цепочки FNR: (имя, промпт, ожидаемый артефакт).\n   766\t\n   767\t    У `debate` и `validate` ожидаемого файла нет: дебаты дописываются в\n   768\t    concept.md, а валидация может остаться отчётом в выводе.\n   769\t\n   770\t    `repowise` идёт ПЕРВОЙ: её результат — вход для постановки задачи, и\n   771\t    обращаться к индексу после написания task.md уже поздно.\n   772\t    \"\"\"\n   773\t    return [\n   774\t        (\"repowise\", f\"/repowise-context {description}\",\n   775\t         f\"{FNR_DIR}/repowise-dialog.md\"),\n   776\t        (\"task\", f\"/fnr-new-task {description}\", f\"{FNR_DIR}/task.md\"),\n   777\t        (\"concept\", f\"/fnr-concept {FNR_DIR}/task.md\", f\"{FNR_DIR}/concept.md\"),\n   778\t        (\"debate\", f\"/fnr-debate {FNR_DIR}/concept.md\", None),\n   779\t        (\"sysreq\", f\"/fnr-system-requirements {FNR_DIR}/concept.md\",\n   780\t         f\"{FNR_DIR}/system_requirements.md\"),\n   781\t        (\"validate\", f\"/validate-doc {FNR_DIR}/system_requirements.md\", None),\n   782\t    ]",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 23.99,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_run_claude"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_run_claude",
  "file": "worker/activities.py",
  "name": "_run_claude",
  "kind": "function",
  "qualified_name": "worker.activities._run_claude",
  "signature": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None",
  "language": "python",
  "start_line": 943,
  "end_line": 988,
  "symbol_start_line": 943,
  "symbol_end_line": 988,
  "source": "   943\tdef _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:\n   944\t    \"\"\"Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n   945\t\n   946\t    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n   947\t    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n   948\t\n   949\t    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n   950\t    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n   951\t    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n   952\t    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n   953\t    не увидела и артефакта не создала.\n   954\t    \"\"\"\n   955\t    token, base = _claude_anthropic_creds()\n   956\t    # Понятная ошибка вместо голого \"exit 1\", если z.ai не сконфигурирован:\n   957\t    # без креды claude-code уходит на дефолтный Anthropic API и падает.\n   958\t    if not token or not base:\n   959\t        raise RuntimeError(\n   960\t            \"claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL \"\n   961\t            \"(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера.\"\n   962\t        )\n   963\t    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера\n   964\t    # работает от root, а тот флаг под root запрещён самим claude-code\n   965\t    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).\n   966\t    command = [\"claude\", \"-p\", prompt, \"--permission-mode\", \"acceptEdits\"]\n   967\t    if mcp_config:\n   968\t        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы\n   969\t        # затесаться серверы из окружения образа, и стадия ходила бы не туда,\n   970\t        # куда её послали.\n   971\t        #\n   972\t        # --allowedTools по имени сервера: без него вызов инструмента ждёт\n   973\t        # подтверждения, которого в неинтерактивном режиме не будет, и диалог\n   974\t        # молча не состоится.\n   975\t        command += [\"--mcp-config\", mcp_config, \"--strict-mcp-config\",\n   976\t                    \"--allowedTools\", f\"mcp__{repowise.SERVER_NAME}\"]\n   977\t    result = subprocess.run(\n   978\t        command,\n   979\t        cwd=cwd, capture_output=True, text=True,\n   980\t        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,\n   981\t        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.\n   982\t        env={**os.environ, \"ANTHROPIC_AUTH_TOKEN\": token, \"ANTHROPIC_BASE_URL\": base},\n   983\t    )\n   984\t    if result.returncode != 0:\n   985\t        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба\n   986\t        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.\n   987\t        detail = result.stderr.strip() or result.stdout.strip() or \"(пустой вывод)\"\n   988\t        raise RuntimeError(f\"claude -p exit {result.returncode}: {detail[-1500:]}\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 19.89,
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
  "symbol_id": "worker/activities.py::_claude_anthropic_creds"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_claude_anthropic_creds",
  "file": "worker/activities.py",
  "name": "_claude_anthropic_creds",
  "kind": "function",
  "qualified_name": "worker.activities._claude_anthropic_creds",
  "signature": "def _claude_anthropic_creds() -> tuple[str, str]",
  "language": "python",
  "start_line": 926,
  "end_line": 940,
  "symbol_start_line": 926,
  "symbol_end_line": 940,
  "source": "   926\tdef _claude_anthropic_creds() -> tuple[str, str]:\n   927\t    \"\"\"Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n   928\t    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n   929\t    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n   930\t    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n   931\t    не нужно, но если заданы — приоритетнее (явный override).\"\"\"\n   932\t    token = os.environ.get(\"ANTHROPIC_AUTH_TOKEN\") or os.environ.get(\"ZAI_API_KEY\", \"\")\n   933\t    base = os.environ.get(\"ANTHROPIC_BASE_URL\", \"\")\n   934\t    if not base:\n   935\t        zai = os.environ.get(\"ZAI_BASE_URL\", \"\")\n   936\t        if zai:\n   937\t            from urllib.parse import urlsplit\n   938\t            p = urlsplit(zai)\n   939\t            base = f\"{p.scheme}://{p.netloc}/api/anthropic\"\n   940\t    return token, base",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 17.72,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 6 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "MODEL_GATE MODEL_CLASSIFY extract complete worker activities",
  "mode": "hybrid",
  "limit": 10
}
```

**Ответ:**

{
  "results": [
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
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_develop_autostart.py::gate",
      "name": "gate",
      "kind": "function",
      "file": "tests/test_develop_autostart.py",
      "start_line": 76,
      "end_line": 77,
      "signature": "async def gate(issue: IssueInput, thread: list[str]) -> GateResult",
      "qualified_name": "tests.test_develop_autostart.gate",
      "language": "python",
      "score": 45.01,
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
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::classify",
      "name": "classify",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 141,
      "end_line": 142,
      "signature": "async def classify(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
      "qualified_name": "tests.test_ready_for_dev.classify",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_ready_for_dev.py::gate",
      "name": "gate",
      "kind": "function",
      "file": "tests/test_ready_for_dev.py",
      "start_line": 136,
      "end_line": 137,
      "signature": "async def gate(issue: IssueInput, thread: list[str]) -> GateResult",
      "qualified_name": "tests.test_ready_for_dev.gate",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "title": "Infrastructure: scripts/setup.sh",
      "page_type": "infra_page",
      "snippet": "thon 3.12)\"\nelse\n  ok \".venv already exists\"\nfi\nuv pip install --quiet --python .venv/bin/python -r worker/requirements.txt -r requirements-dev.txt\nok \"dependencies installed\"\necho\n\n# --- 3. Parameter",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "scripts/setup.sh",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.extract_estimation_facts",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.extract_estimation_facts\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef extract_estimation_facts(context: EstimationContext) ->",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::extract_estimation_facts",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.score_priority",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.score_priority\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef score_priority(issue: IssueInput, classification: ClassificationR",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::score_priority",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.intake_gate",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.intake_gate\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateRes",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::intake_gate",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.decompose_issue",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.decompose_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef decompose_issue(issue: IssueInput, branch: str) -> dict\n```\n\n##",
      "relevance_score": 2.769,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::decompose_issue",
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
      "path": "tests/test_develop_autostart.py"
    },
    {
      "path": "tests/test_park_deadlines.py"
    },
    {
      "path": "tests/test_ready_for_dev.py"
    },
    {
      "path": "scripts/setup.sh"
    },
    {
      "path": "worker/activities.py"
    }
  ],
  "exact_match": true
}

## Ход 7 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::intake_gate"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::intake_gate",
  "file": "worker/activities.py",
  "name": "intake_gate",
  "kind": "function",
  "qualified_name": "worker.activities.intake_gate",
  "signature": "def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult",
  "language": "python",
  "start_line": 164,
  "end_line": 170,
  "symbol_start_line": 164,
  "symbol_end_line": 170,
  "source": "   164\tdef intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult:\n   165\t    thread_text = \"\\n\\n\".join(f\"Пользователь: {c}\" for c in comment_thread)\n   166\t    user_message = f\"Заголовок: {issue.title}\\n\\nОписание:\\n{issue.body}\\n\\n{thread_text}\"\n   167\t    result = llm.extract(\n   168\t        _load_prompt(\"system_intake_gate.md\"), user_message, GateExtraction, model=llm.MODEL_GATE,\n   169\t    )\n   170\t    return GateResult(status=result.status, content=result.content)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.36,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::classify_issue"
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
    "timing_ms": 16.87,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 9 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::extract_estimation_facts"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::extract_estimation_facts",
  "file": "worker/activities.py",
  "name": "extract_estimation_facts",
  "kind": "function",
  "qualified_name": "worker.activities.extract_estimation_facts",
  "signature": "def extract_estimation_facts(context: EstimationContext) -> dict",
  "language": "python",
  "start_line": 2972,
  "end_line": 2989,
  "symbol_start_line": 2972,
  "symbol_end_line": 2989,
  "source": "  2972\tdef extract_estimation_facts(context: EstimationContext) -> dict:\n  2973\t    parts = [f\"Заголовок: {context.title}\", f\"Описание:\\n{context.body}\"]\n  2974\t    if context.labels:\n  2975\t        parts.append(\"Лейблы: \" + \", \".join(context.labels))\n  2976\t    if context.thread:\n  2977\t        parts.append(\"Обсуждение:\\n\" + \"\\n---\\n\".join(context.thread))\n  2978\t    for path, content in context.artifacts.items():\n  2979\t        parts.append(f\"Артефакт {path}:\\n{content}\")\n  2980\t\n  2981\t    facts = llm.extract(\n  2982\t        _load_prompt(\"system_estimate_extract.md\"),\n  2983\t        \"\\n\\n\".join(parts),\n  2984\t        estimation.EstimationFacts,\n  2985\t        model=llm.MODEL_CLASSIFY,\n  2986\t    )\n  2987\t    # Между activity ездит dict: штатный JSON-конвертер Temporal знает\n  2988\t    # dataclass'ы, но не модели Pydantic. Схема при этом одна.\n  2989\t    return facts.model_dump()",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.28,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 10 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "run_fnr_stage fnr_stages analyze",
  "mode": "hybrid",
  "limit": 10
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
      "score": 47.52,
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
      "score": 47.52,
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
      "score": 47.51,
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
      "score": 47.51,
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
      "score": 47.51,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.run_fnr_stage",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_fnr_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_fnr_stage",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "File: worker/llm.py",
      "page_type": "file_page",
      "snippet": "Й путь —\nAnthropic-совместимый эндпоинт z.ai через переменные окружения ANTHROPIC_*,\nсм. activities.run_fnr_stage (запускает `claude -p` как subprocess,\nа не через этот клиент).\n\nIt exposes 5 public s",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/llm.py",
      "type": "page"
    },
    {
      "title": "File: shared/repowise.py",
      "page_type": "file_page",
      "snippet": "рокси, а не пишется агентом. Guard стадии\n(`worker/activities.py`, проверка ожидаемого артефакта в `run_fnr_stage`) умеет\nпроверить только существование файла и его размер; отличить полный транскрипт",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/repowise.py",
      "type": "page"
    },
    {
      "title": "File: worker/activities.py",
      "page_type": "file_page",
      "snippet": "\", \"debate\", \"sysreq\", \"validate\") |\n| `prepare_workspace` | function | async def prepare_workspace(analyze: AnalyzeInput) -> None |\n| `run_fnr_stage` | function | async def run_fnr_stage(analyze: Ana",
      "relevance_score": 2.857,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.worker.main",
      "page_type": "symbol_spotlight",
      "snippet": "activities.post_priority_comment,\n            activities.prepare_workspace,\n            activities.run_fnr_stage,\n            activities.publish_analysis,\n            activities.cleanup_workspace,",
      "relevance_score": 2.812,
      "sources": [
        "fts"
      ],
      "target_path": "worker/worker.py::main",
      "file": "worker/worker.py",
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
      "path": "scripts/smoke_temporal.py"
    },
    {
      "path": "worker/consolidation_workflow.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/llm.py"
    },
    {
      "path": "shared/repowise.py"
    },
    {
      "path": "worker/worker.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'run_fnr_stage', 'fnr_stages'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 11 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::run_fnr_stage"
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
  "start_line": 1266,
  "end_line": 1321,
  "symbol_start_line": 1266,
  "symbol_end_line": 1321,
  "source": "  1266\tasync def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:\n  1267\t    \"\"\"Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,\n  1268\t    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный\n  1269\t    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.\"\"\"\n  1270\t    # Бриф с обсуждением и связанными PR нужен ровно стадии `task`: только её\n  1271\t    # промпт несёт описание задачи, остальные ссылаются на уже готовые артефакты.\n  1272\t    # Регрессия, из-за которой это место и появилось: при переходе на\n  1273\t    # пер-стадийные activity обогащение осталось в монолите, и `/analyze`\n  1274\t    # уезжал в модель с одними title+body — агент переоткрывал вопросы,\n  1275\t    # закрытые в комментариях.\n  1276\t    description = (\n  1277\t        await asyncio.to_thread(_build_task_context, analyze)\n  1278\t        if stage_name == \"task\"\n  1279\t        else f\"{analyze.title}\\n\\n{analyze.body}\"\n  1280\t    )\n  1281\t    prompt, expected, requires = _fnr_stage(stage_name, description)\n  1282\t    clone_dir = _require_workspace(analyze, requires)\n  1283\t    if expected:\n  1284\t        ready = Path(clone_dir) / expected\n  1285\t        if ready.is_file() and ready.stat().st_size > 0:\n  1286\t            # Артефакт приехал с веткой прошлого прогона: стадия сделана, и\n  1287\t            # повторять её — платить второй раз за тот же документ.\n  1288\t            logger.info(\"FNR %s#%s: стадия %s уже сделана — пропускаю\",\n  1289\t                        analyze.repo, analyze.issue_number, stage_name)\n  1290\t            return {\"stage\": stage_name, \"artifact\": expected,\n  1291\t                    \"bytes\": ready.stat().st_size, \"outcome\": \"skipped\"}\n  1292\t    mcp_config = _write_repowise_config(analyze, clone_dir)\n  1293\t    if stage_name == REPOWISE_STAGE:\n  1294\t        degraded = await asyncio.to_thread(_degrade_repowise_stage, analyze, clone_dir, expected)\n  1295\t        if degraded is not None:\n  1296\t            return degraded\n  1297\t    # Конфигурация MCP передаётся ТОЛЬКО стадии сбора контекста: остальным\n  1298\t    # стадиям индекс не нужен, а лишние инструменты в сессии — лишние соблазны\n  1299\t    # и лишние деньги.\n  1300\t    await _run_with_heartbeat(\n  1301\t        _run_claude, prompt, clone_dir,\n  1302\t        mcp_config if stage_name == REPOWISE_STAGE else None,\n  1303\t        label=stage_name)\n  1304\t\n  1305\t    outcome = \"ok\"\n  1306\t    if stage_name == REPOWISE_STAGE and expected:\n  1307\t        # Артефакт дописывается транскриптом из журнала прокси и потому не\n  1308\t        # зависит от того, вспомнила ли модель его записать.\n  1309\t        outcome = await asyncio.to_thread(\n  1310\t            _ensure_dialog_artifact, analyze, clone_dir, expected)\n  1311\t\n  1312\t    artifact: str | None = None\n  1313\t    size = 0\n  1314\t    if expected:\n  1315\t        path = Path(clone_dir) / expected\n  1316\t        if not path.exists():\n  1317\t            raise RuntimeError(f\"стадия {stage_name}: артефакт {expected} не создан\")\n  1318\t        artifact = expected\n  1319\t        size = path.stat().st_size\n  1320\t    return {\"stage\": stage_name, \"artifact\": artifact, \"bytes\": size,\n  1321\t            \"outcome\": outcome}",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.41,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_fnr_stage"
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
  "start_line": 807,
  "end_line": 812,
  "symbol_start_line": 807,
  "symbol_end_line": 812,
  "source": "   807\tdef _fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]:\n   808\t    \"\"\"(промпт, ожидаемый артефакт, требуемый вход) для стадии по имени.\"\"\"\n   809\t    for n, prompt, expected in _fnr_stages(description):\n   810\t        if n == name:\n   811\t            return prompt, expected, _FNR_STAGE_REQUIRES[name]\n   812\t    raise ValueError(f\"неизвестная стадия FNR: {name}\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 16.3,
    "index_age_days": 0,
    "indexed_commit": "a41f569f0381",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 33526
  }
}

## Ход 13 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "2026-07-12-issue-agent-layer-a-triage-design.md docs/superpowers/specs",
  "mode": "path",
  "limit": 5
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
