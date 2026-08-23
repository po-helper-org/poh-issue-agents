---
session: rw-openhands-po-helper-org__poh-issue-agents-112
workspace: contour
turns: 5
started: 2026-08-23T13:14:07Z
finished: 2026-08-23T13:17:47Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 21 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 21 мин |
| `poh-helper` | `18512c1e7ce9` | 21 мин |
| `poh-infra` | `a1db4f02f10c` | 21 мин |
| `poh-issue-agents` | `993d8561f100` | 21 мин |
| `poh-memory-engine` | `194e39319b3f` | 21 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 21 мин |
| `poh-scheduller` | `04cc3f47aff9` | 21 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 21 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 3 сут |

# Диалог

## Ход 1 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Как устроена система команд в shared/commands.py и как реализованы другие команды вроде /analyze или /estimate?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but retrieval succeeded and this payload is usable: 5 ranked hits in `retrieval`, the files to open in `fallback_targets`, and the wider ranked shortlist in `candidates`. Read those rather than starting a fresh search.",
  "citations": [],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "shared/commands.py",
    "shared/workflow_types.py",
    "worker/activities.py",
    "worker/workflows.py",
    "scripts/estimate.py"
  ],
  "retrieval": [
    {
      "path": "shared/commands.py",
      "title": "File: shared/commands.py",
      "summary": "Разбор slash-команд из комментариев Issue и сборка входа аналитики.",
      "snippet": "# shared/commands.py\n\n## Overview\n\nРазбор slash-команд из комментариев Issue и сборка входа аналитики.\n\nЖивёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен\nворкеру — чтобы иск",
      "excerpt": "# shared/commands.py\n\n## Overview\n\nРазбор slash-команд из комментариев Issue и сборка входа аналитики.\n\nЖивёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен\nворкеру — чтобы исключить сами команды из треда, уходящего в модель. Модуль\nнамеренно не зависит ни от FastAPI, ни от temporalio: логика юнит-тестируема\nбез веб-стека (в dev-окружении fastapi отсутствует). Оба Dockerfile копируют\nshared/ в образ.\n\nУ команды два равноправных триггера — комментарий (`/analyze`) и метка\n(`run:analyze`). Оба ведут в один и тот же воркфлоу, поэтому набор команд\nобъявлен здесь ОДИН раз, а имена меток из него выводятся: разъехавшись, они\nдали бы метку, которая ничего не запускает, и запуск, который ничего не\nпомечает.\n\nIt exposes 17 public symbols and depends on 3 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `ESTIMATE` | constant | ESTIMATE = \"estimate\" |\n| `ANALYZE` | constant | ANALYZE = \"analyze\" |\n| `BFT` | constant | BFT = \"bft\" |\n| `BFT_DEEP` | constant | BFT_DEEP = \"bft-deep\" |\n| `RUN_PREFIX` | constant | RUN_PREFIX = \"run:\" |\n| `DONE_PREFIX` | constant | DONE_PREFIX = \"done:\" |\n| `FAILED_PREFIX` | constant | FAILED_PREFIX = \"failed:\" |\n| `run_label` | function | def run_label(command: str) -> str |\n| `done_label` | function | def done_label(command: str) -> str |\n| `failed_label` | function | def failed_label(command: str) -> str |\n| `running_labels` | function | def running_labels(command: str) -> tuple[str, ...] |\n| `parse_lab",
      "score": 3.235,
      "key_symbols": [
        {
          "name": "ESTIMATE",
          "kind": "constant",
          "signature": "ESTIMATE = \"estimate\"",
          "docstring": "",
          "start_line": 19,
          "end_line": 19
        },
        {
          "name": "ANALYZE",
          "kind": "constant",
          "signature": "ANALYZE = \"analyze\"",
          "docstring": "",
          "start_line": 20,
          "end_line": 20
        },
        {
          "name": "_COMMANDS",
          "kind": "constant",
          "signature": "_COMMANDS = {\"/estimate\": ESTIMATE, \"/analyze\": ANALYZE,",
          "docstring": "",
          "start_line": 27,
          "end_line": 28,
          "source_excerpt": "_COMMANDS = {\"/estimate\": ESTIMATE, \"/analyze\": ANALYZE,\n             \"/bft\": BFT, \"/bft-deep\": BFT_DEEP}"
        },
        {
          "name": "_LEGACY_RUNNING_LABELS",
          "kind": "constant",
          "signature": "_LEGACY_RUNNING_LABELS = {ANALYZE: (\"analyzing\",)}",
          "docstring": "",
          "start_line": 40,
          "end_line": 40
        },
        {
          "name": "run_label",
          "kind": "function",
          "signature": "def run_label(command: str) -> str:",
          "docstring": "",
          "start_line": 43,
          "end_line": 44
        },
        {
          "name": "done_label",
          "kind": "function",
          "signature": "def done_label(command: str) -> str:",
          "docstring": "",
          "start_line": 47,
          "end_line": 48
        },
        {
          "name": "parse_label_command",
          "kind": "function",
          "signature": "def parse_label_command(label: str) -> str | None:",
          "docstring": "Команда, которую запускает метка, иначе None.\n\n    Запускает ТОЛЬКО `run:<команда>`. Это же и защита от петли: метки исхода\n    (`done:*`, `failed:*`) агент ставит себе сам, они прилетают обратно\n    событием issues.labeled — и не совпадают ни с одним триггером.",
          "start_line": 60,
          "end_line": 70
        },
        {
          "name": "parse_command",
          "kind": "function",
          "signature": "def parse_command(comment_body: str) -> str | None:",
          "docstring": "Имя команды, если комментарий — вызов команды, иначе None.\n\n    Командой считается только комментарий, ПЕРВАЯ непустая строка которого\n    начинается с самого вызова. Цитата (строка с '>') командой не считается:\n    иначе ответ с процитированной командой запускал бы её повторно. Хвост\n    после имени команды здесь игнорируется — его достаёт `parse_command_args`.",
          "start_line": 84,
          "end_line": 99
        },
        {
          "name": "parse_command_args",
          "kind": "function",
          "signature": "def parse_command_args(comment_body: str) -> str:",
          "docstring": "Всё, что человек написал после имени команды, включая следующие строки.\n\n    У `/analyze` и `/estimate` аргументов нет, у БФТ есть: `/bft` несёт\n    замечания к формулировке, `/bft-deep` — ответы на открытые вопросы. Хвост\n    забирается целиком и многострочно, потому что ответы на пять вопросов в одну\n    строку не пишут.\n\n    Не команда — пустая строка: вызывающий уже знает про это из `parse_command`,\n    и второй способ сказать «это не команда» тут ни к чему.",
          "start_line": 102,
          "end_line": 123,
          "source_excerpt": "def parse_command_args(comment_body: str) -> str:\n    \"\"\"Всё, что человек написал после имени команды, включая следующие строки.\n\n    У `/analyze` и `/estimate` аргументов нет, у БФТ есть: `/bft` несёт\n    замечания к формулировке, `/bft-deep` — ответы на открытые вопросы. Хвост\n    забирается целиком и многострочно, потому что ответы на пять вопросов в одну\n    строку не пишут.\n\n    Не команда — пустая строка: вызывающий уже знает про это из `parse_command`,\n    и второй способ сказать «это не команда» тут ни к чему.\n    \"\"\"\n    lines = comment_body.splitlines()\n    for index, raw_line in enumerate(lines):\n        line = raw_line.strip()\n        if not line:\n            continue\n        if line.startswith(\">\") or _COMMANDS.get(line.split()[0].lower()) is None:\n            return \"\"\n        head = line.split(\" \", 1)[1] if \" \" in line else \"\"\n        tail = \"\\n\".join(lines[index + 1:])\n        return f\"{head}\\n{tail}\".strip()\n    return \"\""
        },
        {
          "name": "build_analyze_input",
          "kind": "function",
          "signature": "def build_analyze_input(payload: dict) -> AnalyzeInput:",
          "docstring": "Собирает вход воркфлоу IssueAnalysis из payload вебхука.\n\n    Один сборщик на оба триггера: у события issue_comment есть комментарий, у\n    issues.labeled его нет — тогда comment_id остаётся None, и активности,\n    которым нужен комментарий (реакция на него), просто его не ставят.",
          "start_line": 126,
          "end_line": 141
        }
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 29 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `DevelopPlan` | class | class DevelopPlan |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | cl",
      "score": 2.265,
      "key_symbols": [
        {
          "name": "AnalyzeInput",
          "kind": "class",
          "signature": "class AnalyzeInput:",
          "docstring": "",
          "start_line": 231,
          "end_line": 240,
          "source_excerpt": "class AnalyzeInput:\n    repo: str\n    issue_number: int\n    title: str\n    body: str\n    comment_id: int | None = None  # комментарий-триггер, на него ставится реакция\n    # Чем прогон вызван — для подтверждения приёма. Пусто означает `/analyze`\n    # либо метку `run:analyze`; цикл ставит сюда `research-me`, чтобы ack не\n    # называл человеку метку, которую тот не ставил.\n    trigger: str | None = None"
        },
        {
          "name": "EstimateRequest",
          "kind": "class",
          "signature": "class EstimateRequest:",
          "docstring": "",
          "start_line": 282,
          "end_line": 287,
          "source_excerpt": "class EstimateRequest:\n    repo: str\n    issue_number: int\n    # Комментарий с командой: на него ставится реакция. None — запуск меткой\n    # `run:estimate`, реагировать не на что.\n    comment_id: int | None = None"
        },
        {
          "name": "EstimationContext",
          "kind": "class",
          "signature": "class EstimationContext:",
          "docstring": "",
          "start_line": 291,
          "end_line": 298
        },
        {
          "name": "EstimateResult",
          "kind": "class",
          "signature": "class EstimateResult:",
          "docstring": "",
          "start_line": 302,
          "end_line": 304
        }
      ]
    },
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 117 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) ->",
      "score": 2.265
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 42 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | constant | SEEN_EVENTS_KEPT = 50 |\n| `HISTORY_EVENT_THRESHOLD` | constant | HISTORY_EVENT_THRESHOLD = 800 |\n| `WebhookAudit` | class | class Webhook",
      "score": 2.265
    },
    {
      "path": "scripts/estimate.py",
      "title": "File: scripts/estimate.py",
      "summary": "Smoke harness: start one IssueEstimation workflow without the webhook.",
      "snippet": "Smoke harness: start one IssueEstimation workflow without the webhook.",
      "excerpt": "# scripts/estimate.py\n\n## Overview\n\nSmoke harness: start one IssueEstimation workflow without the webhook.\n\n`/estimate` normally arrives as an `issue_comment.created` webhook, which\nneeds Layer B (GitHub App + public endpoint). This script starts the same\nworkflow directly against Temporal, so the estimation path — including the\nreal LLM call — can be exercised with only `temporal` and `worker` running.\n\nThe workflow reacts 👀 on the comment that carried the command. There is no\nsuch comment here, so `--comment-id` defaults to 0: harmless under DRY_RUN\n(the reaction is only logged), a 404 without it. Pass a real comment id when\nrunning for real.\n\nUsage:\n    python scripts/estimate.py --issue 83\n    python scripts/estimate.py --issue 83 --comment-id 2145678901\n    python scripts/estimate.py --issue 83 --no-wait\n\nIt exposes 3 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `TASK_QUEUE` | constant | TASK_QUEUE = \"issue-lifecycle\" |\n| `workflow_id_for` | variable | workflow_id_for = estimate_workflow_id |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `shared/workflow_ids.py`\n- `shared/workflow_types.py`\n\n## Used by\n\nImported by 1 file in this repository.\n\n- `tests/test_estimate_script.py`\n\n## Usage Notes\n\n**Layer:** Docs & Tooling | **Role:** internal\n\n## Questions this page answers\n\n- What does `scripts/estimate.py` export?\n- Where is `TASK_QUEUE` defined?\n- What imports `scripts/estimate.py`?\n\n",
      "score": 2.265
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question.",
  "best_guesses": [
    {
      "file": "shared/commands.py",
      "why_relevant": "Разбор slash-команд из комментариев Issue и сборка входа аналитики..",
      "score": 3.235
    },
    {
      "file": "shared/workflow_types.py",
      "why_relevant": "`shared/workflow_types.py` is a python source file in the Utility layer..",
      "score": 2.265
    },
    {
      "file": "worker/activities.py",
      "why_relevant": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на.",
      "score": 2.265
    }
  ],
  "code_rationale": [
    {
      "path": "shared/commands.py",
      "lines": [
        1,
        12
      ],
      "comment": "Разбор slash-команд из комментариев Issue и сборка входа аналитики. Живёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен воркеру — чтобы исключить сами команды из треда, уходящего в модель. Модуль намеренно не зависит ни от FastAPI, ни от temporalio: логика юнит-тестируема без веб-стека (в dev-окружении fastapi отсутствует). Оба Dockerfile копируют shared/ в образ. У команды два равноправных триггера — комментарий (`/analyze`) и метка (`run:analyze`). Оба ведут в один и тот же воркфлоу, поэтому набор команд объявлен здесь ОДИН раз, а имена меток из него выводятся: разъехавшись, они дали бы метку, которая ничего не запускает, и запуск, который ничего не помечает.",
      "matched_terms": [
        "analyze",
        "shared"
      ]
    },
    {
      "path": "shared/commands.py",
      "lines": [
        103,
        112
      ],
      "comment": "Всё, что человек написал после имени команды, включая следующие строки. У `/analyze` и `/estimate` аргументов нет, у БФТ есть: `/bft` несёт замечания к формулировке, `/bft-deep` — ответы на открытые вопросы. Хвост забирается целиком и многострочно, потому что ответы на пять вопросов в одну строку не пишут. Не команда — пустая строка: вызывающий уже знает про это из `parse_command`, и второй способ сказать «это не команда» тут ни к чему.",
      "matched_terms": [
        "analyze",
        "estimate"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        1260,
        1268
      ],
      "comment": "Свежие комментарии обсуждения (старые→свежие) без командного шума. Командные комментарии (`/analyze`, `/estimate` и с хвостом) отсекаются через parse_command — тот же разбор, что и в вебхуке. Сбой fetch ИЛИ разбора ответа (неожиданная форма payload) → пустой список: анализ продолжается на title+body. Фильтрация и сборка блоков нарочно внутри того же try, что и сам fetch — некорректный элемент payload не должен пробрасывать исключение мимо этого хелпера.",
      "matched_terms": [
        "analyze",
        "estimate"
      ]
    }
  ],
  "next_action_hint": "Start from shared/commands.py — it ranked highest, and best_guesses says why each candidate is in the running.",
  "_meta": {
    "timing_ms": 403.1,
    "hint": "Synthesis is what is missing here, not retrieval. retrieval_quality rates the ranked hits; start from the first one.",
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
      "path": "shared/commands.py",
      "lines": "19-141",
      "defines": "run_label:43, done_label:47, failed_label:51, running_labels:55, parse_label_command:60, bft_mode:73"
    },
    {
      "path": "shared/workflow_types.py",
      "lines": "231-304",
      "defines": "IssueInput:6, UserComment:17, WebhookAuditInput:34, Deadlines:50, LifecycleState:111, OrphanEventInput:157"
    },
    {
      "path": "worker/activities.py",
      "defines": "GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101, CommentIntentExtraction:115"
    },
    {
      "path": "worker/workflows.py",
      "defines": "WebhookAudit:286, OrphanAgentEvent:309, CommentAck:330, IssueLifecycle:353, IssueDevelopment:2271, IssuePrFix:2364"
    },
    {
      "path": "scripts/estimate.py",
      "defines": "main:43, TASK_QUEUE:38"
    }
  ]
}

## Ход 2 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Что делает функция _issue_input в webhook/main.py и как она формирует вход для workflow?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `_issue_input`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "webhook/main.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "webhook/main.py",
    "worker/workflows.py",
    "scripts/backfill.py",
    "scripts/estimate.py",
    "scripts/diag.py"
  ],
  "retrieval": [
    {
      "path": "webhook/main.py",
      "title": "File: webhook/main.py",
      "summary": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:",
      "snippet": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID",
      "excerpt": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и\n                               через signal-with-start поднимает цикл-владелец\n                               состояния, `/estimate` — IssueEstimation,\n                               `/bft` и `/bft-deep` — IssueBft (хвост команды\n                               уезжает в прогон как замечания/уточнения); любой\n                               другой комментарий — сигнал уже идущему workflow\n                               (используется циклом уточнений)\n- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и\n                               команда в комментарии (run:analyze ->\n                               IssueAnalysis, run:estimate -> IssueEstimation,\n                               run:bft / run:bft-deep -> IssueBft);\n                               точки решения человека (research-me / bug-me /\n                               build-me) идут через signal-with-start: воркфлоу\n                               триажа может не существовать, тогда он\n                               поднимается тем же вызовом\n\nНичего из бизнес-логики здесь нет — это чистый транспортный слой.\n\nIt exposes 8 public symbols and depends on 13 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n|",
      "score": 5.205,
      "key_symbols": [
        {
          "name": "_log",
          "kind": "variable",
          "signature": "_log = logging.getLogger(\"webhook\")",
          "docstring": "",
          "start_line": 62,
          "end_line": 62
        },
        {
          "name": "_client_disconnect",
          "kind": "function",
          "signature": "async def _client_disconnect(request: Request, exc: ClientDisconnect):",
          "docstring": "Отправитель ушёл, не дослав тело.\n\n    Отвечать 500 некому: соединения уже нет, а событие уезжает в Sentry как\n    сбой вебхука (ISSUE-AGENT-8, пять штук за один разрыв связи с прокси).\n    Доставка не потеряна: GitHub повторит её сам. У GitLab ретраев нет — там\n    оборванная доставка теряется, поэтому обработчик ниже принимает всё, что\n    прошло подпись, и разбирается внутри. 204 закрывает запрос тихо и\n    оставляет след в логе.",
          "start_line": 68,
          "end_line": 80
        },
        {
          "name": "workflow_id_for",
          "kind": "variable",
          "signature": "workflow_id_for = issue_workflow_id",
          "docstring": "",
          "start_line": 128,
          "end_line": 128,
          "source_excerpt": "workflow_id_for = issue_workflow_id"
        },
        {
          "name": "estimate_workflow_id_for",
          "kind": "variable",
          "signature": "estimate_workflow_id_for = estimate_workflow_id",
          "docstring": "",
          "start_line": 129,
          "end_line": 129,
          "source_excerpt": "estimate_workflow_id_for = estimate_workflow_id"
        },
        {
          "name": "_search_attributes",
          "kind": "function",
          "signature": "def _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None:",
          "docstring": "Сквозной ключ цепочки в Temporal: `RootIssue` и `Repo`.\n\n    Они дают одну ленту на всю цепочку от триажа Issue до стоп-слова на PR —\n    ради этого протокол и предпочитает централизованный кластер трём\n    изолированным.\n\n    За флагом TEMPORAL_SEARCH_ATTRIBUTES, потому что атрибут, не\n    зарегистрированный на кластере, роняет САМ старт воркфлоу:\n\n        temporal operator search-attribute create --name RootIssue --type Int\n        temporal operator search-attribute create --name Repo --type Keyword\n\n    Пока оператор их не завёл, включение сломало бы обработку целиком — цена\n    ошибки конфигурации несопоставима с пользой от фильтра в UI.",
          "start_line": 132,
          "end_line": 153
        },
        {
          "name": "_issue_input",
          "kind": "function",
          "signature": "def _issue_input(payload: dict, *, interactive: bool):",
          "docstring": "`IssueInput` из полезной нагрузки вебхука.\n\n    Импорт внутри функции — как и в остальных ветках: shared/ подтягивается\n    лениво, чтобы старт вебхука не зависел от воркерных зависимостей.",
          "start_line": 156,
          "end_line": 173,
          "source_excerpt": "def _issue_input(payload: dict, *, interactive: bool):\n    \"\"\"`IssueInput` из полезной нагрузки вебхука.\n\n    Импорт внутри функции — как и в остальных ветках: shared/ подтягивается\n    лениво, чтобы старт вебхука не зависел от воркерных зависимостей.\n    \"\"\"\n    from shared.workflow_types import IssueInput\n\n    issue = payload[\"issue\"]\n    return IssueInput(\n        repo=payload[\"repository\"][\"full_name\"],\n        issue_number=issue[\"number\"],\n        title=issue[\"title\"],\n        body=issue.get(\"body\") or \"\",\n        author_login=issue[\"user\"][\"login\"],\n        author_type=(issue.get(\"user\") or {}).get(\"type\") or \"User\",\n        interactive=interactive,\n    )"
        },
        {
          "name": "_may_start_expensive",
          "kind": "function",
          "signature": "def _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:",
          "docstring": "Гейт на запуск дорогой стадии + аудит того, кто её запустил.\n\n    Проверяем автора события, а не факт наличия метки: метку может поставить\n    любой с правами на репозиторий, и это самый дешёвый способ потратить чужие\n    токены. Дешёвые пути (issues.opened, обычные комментарии) сюда не приходят —\n    триаж обязан работать для всех.\n\n    Отказ только логируем: вебхук — чистый транспорт, GitHub-клиента у него нет,\n    и заводить его ради комментария «недостаточно прав» значит дать наружу\n    процессу право писать в Issue.",
          "start_line": 176,
          "end_line": 198
        },
        {
          "name": "_ack_comment_seen",
          "kind": "function",
          "signature": "async def _ack_comment_seen(client, repo: str, issue_number: int, comment_id: int) -> None:",
          "docstring": "Реакция `eyes` на принятый комментарий — отдельным прогоном.\n\n    Ставит её воркер, а не вебхук: GitHub-клиента здесь нет намеренно (см.\n    `_may_start_expensive`), и заводить его ради реакции значило бы дать\n    смотрящему наружу процессу право писать в Issue. Вебхук лишь просит.\n\n    Сбой самого запроса не должен ронять обработку комментария: подтверждение\n    приёма дороже своей стоимости только пока оно бесплатно для основного пути.",
          "start_line": 239,
          "end_line": 264
        },
        {
          "name": "_lifecycle_args_for",
          "kind": "function",
          "signature": "def _lifecycle_args_for(event, issue_number: int) -> list:",
          "docstring": "Аргументы старта цикла для события агента.\n\n    Цикла может не быть: Issue завели до установки App, либо его прогон уже\n    закрылся по сроку. Поднимать его обычным путём нельзя — триаж пошёл бы по\n    пустым заголовку и телу, задал бы человеку уточняющий вопрос и потратил\n    вызовы модели на задачу, которая давно в разработке.\n\n    Поэтому цикл поднимается СРАЗУ в той фазе, о которой доложил агент, через\n    тот же снимок состояния, что используется для continue-as-new (#36).\n    Триажу тут делать нечего: работа уже в PR.",
          "start_line": 355,
          "end_line": 379
        },
        {
          "name": "github_webhook",
          "kind": "function",
          "signature": "async def github_webhook( request: Request, x_github_event: str = Header(...), x_hub_signature_256: str | None = Header(None),",
          "docstring": "Приём доставки. Отказать может только подпись.\n\n    Всё остальное — включая payload, который мы не сумели разобрать, — уезжает\n    в аудит и подтверждается 200. Причина: у GitLab автоматических ретраев нет,\n    доставка теряется навсегда, а четыре подряд провала отключают вебхук на\n    срок до суток. 500 отсюда стоит дороже, чем необработанное событие.",
          "start_line": 383,
          "end_line": 411
        }
      ]
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 42 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | constant | SEEN_EVENTS_KEPT = 50 |\n| `HISTORY_EVENT_THRESHOLD` | constant | HISTORY_EVENT_THRESHOLD = 800 |\n| `WebhookAudit` | class | class Webhook",
      "score": 3.643,
      "key_symbols": [
        {
          "name": "run",
          "kind": "method",
          "signature": "async def run(self, audit: WebhookAuditInput) -> str:",
          "docstring": "",
          "start_line": 299,
          "end_line": 305
        },
        {
          "name": "run",
          "kind": "method",
          "signature": "async def run(self, issue: IssueInput, carried: LifecycleState | None = None) -> None:",
          "docstring": "Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n        ожидание, а не заканчивается после приоритизации.\n\n        Второй аргумент со значением по умолчанию — ради совместимости: вебхук и\n        скрипты стартуют воркфлоу одним аргументом, как раньше, а continue-as-new\n        передаёт снимок состояния вторым.\n\n        `workflow.patched` разводит поколения. Прогоны, запущенные до этого\n        изменения, припаркованы в проде: их история не знает маркера, patched()\n        вернёт False, и они доиграют по прежнему линейному коду. Новые пойдут\n        циклом. Без этого реплей старой истории новым кодом упал бы\n        недетерминизмом — самый дорогой класс отказа в Temporal.",
          "start_line": 698,
          "end_line": 751,
          "source_excerpt": "    async def run(self, issue: IssueInput,\n                  carried: LifecycleState | None = None) -> None:\n        \"\"\"Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n        ожидание, а не заканчивается после приоритизации.\n\n        Второй аргумент со значением по умолчанию — ради совместимости: вебхук и\n        скрипты стартуют воркфлоу одним аргументом, как раньше, а continue-as-new\n        передаёт снимок состояния вторым.\n\n        `workflow.patched` разводит поколения. Прогоны, запущенные до этого\n        изменения, припаркованы в проде: их история не знает маркера, patched()\n        вернёт False, и они доиграют по прежнему линейному коду. Новые пойдут\n        циклом. Без этого реплей старой истории новым кодом упал бы\n        недетерминизмом — самый дорогой класс отказа в Temporal.\n        \"\"\"\n        # Вебхук и скрипты стартуют воркфлоу ОДНИМ аргументом, а сигнатура\n        # объявляет два. При таком расхождении Temporal не применяет типы ни к\n        # одному аргументу и отдаёт сырые словари — молча, на первом же\n        # обращении к полю. Нормализуем сами: ломать существующие стартеры ради\n        # красоты сигнатуры нельзя, а второй аргумент нужен continue-as-new.\n        if isinstance(issue, dict):\n            issue = IssueInput(**issue)\n        if isinstance(carried, dict):\n            carried = LifecycleState(**carried)\n\n        self._issue = issue  # даёт analyze_requested доступ к repo/number\n        # Момент входа в фазу. `workflow.now()` детерминирован (время события из\n        # истории), поэтому реплей даёт то же значение, что и первый прогон.\n        self._phase_since = workflow.now()\n        if carried is not None:\n            self._phase = carried.phase\n            self._stage = carried.stage\n            self._priority_tier = carried.priority_tier\n            self._classification_label = carried.classification_label\n            self._analysis_done = carried.analysis_done\n            self._plan_member = carried.plan_member\n            self._root_issue = carried.root_issue\n            self._pr_number = carried.pr_number\n            self._clarify_rounds = carried.clarify_rounds\n            self._followup_rounds = carried.followup_rounds\n            self._answered_comment_ids = list(carried.answered_comment_ids)"
        },
        {
          "name": "_run_analysis_child",
          "kind": "method",
          "signature": "async def _run_analysis_child(self, issue: IssueInput, trigger: str | None = None) -> bool:",
          "docstring": "Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n\n        Один код на оба режима (#37): в Temporal UI прогон виден как child\n        цикла, а id остаётся прежним (`analysis-<repo>-<n>`), поэтому повторная\n        команда по-прежнему упирается в `WorkflowAlreadyStarted`, а не тратит\n        деньги второй раз.",
          "start_line": 913,
          "end_line": 962,
          "source_excerpt": "    async def _run_analysis_child(self, issue: IssueInput,\n                                  trigger: str | None = None) -> bool:\n        \"\"\"Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n\n        Один код на оба режима (#37): в Temporal UI прогон виден как child\n        цикла, а id остаётся прежним (`analysis-<repo>-<n>`), поэтому повторная\n        команда по-прежнему упирается в `WorkflowAlreadyStarted`, а не тратит\n        деньги второй раз.\n        \"\"\"\n        analyze = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,\n                               title=issue.title, body=issue.body,\n                               comment_id=self._analyze_comment_id,\n                               trigger=trigger)\n        # Запрос израсходован — но снимается он ПОСЛЕ прогона, а не до.\n        #\n        # Пока прогон идёт, `ack_command` вешает на Issue метку `run:analyze`.\n        # Вебхук видит `issues.labeled` и шлёт `analyze_requested` обратно в\n        # цикл: наша собственная метка возвращается как новая команда. Со\n        # снятым флагом она вставала в очередь, и по завершении прогона цикл\n        # запускал второй — на живом стенде это дало три прогона аналитики\n        # подряд по одному Issue. Идентификатор занятого прогона от этого не\n        # спасает: к моменту обработки очереди первый уже завершён, и id\n        # свободен.\n        #\n        # Команда, пришедшая ВО ВРЕМЯ прогона, — эхо своей метки либо повторный\n        # клик человека. Ни то, ни другое не стоит второго дорогого прогона.\n        self._analysis_running = True\n        try:\n            return await workflow.execute_child_workflow(\n                IssueAnalysis.run, analyze,\n                id=analysis_workflow_id(issue.repo, issue.issue_number),\n                # Цепочка FNR идёт до 4500 с. Ни continue-as-new родителя, ни\n                # его завершение не должны её убивать — иначе дорогой прогон\n                # обрывается на середине по причине, к нему не относящейся.\n                parent_close_policy=ParentClosePolicy.ABANDON,\n                # Прогон недетерминирован, мутирует файлы и стоит денег:\n                # повтор инициирует человек, а не политика ретраев.\n                retry_policy=RetryPolicy(maximum_attempts=1),\n            )\n        except WorkflowAlreadyStartedError:\n            # Прогон по этому Issue уже идёт — второй дорогой не нужен."
        },
        {
          "name": "_run_linear",
          "kind": "method",
          "signature": "async def _run_linear(self, issue: IssueInput) -> None:",
          "docstring": "Прежний линейный сценарий — БЕЗ ИЗМЕНЕНИЙ.\n\n        Живёт ради прогонов, запущенных до перехода на фазовый цикл: они\n        припаркованы в проде, и их история не знает маркера патча. Реплей такой\n        истории обязан идти по тому же коду, иначе Temporal уронит прогон\n        недетерминизмом. Удалять — только когда все прогоны этого поколения\n        завершатся (workflow.deprecate_patch).",
          "start_line": 1997,
          "end_line": 2267
        }
      ]
    },
    {
      "path": "scripts/backfill.py",
      "title": "File: scripts/backfill.py",
      "summary": "Backfill: start one IssueLifecycle workflow per already-open Issue.",
      "snippet": "# scripts/backfill.py\n\n## Overview\n\nBackfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never p",
      "excerpt": "# scripts/backfill.py\n\n## Overview\n\nBackfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never processes the current backlog. This script enumerates\nopen Issues via `gh` and starts workflows directly against Temporal.\n\nRuns in non-interactive batch mode (interactive=False): a VAGUE issue\nescalates instead of waiting for a human clarification that will not come.\n\nUsage:\n    python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY\n    python scripts/backfill.py --issue 83      # single issue (smoke test)\n    python scripts/backfill.py --limit 5       # first N\n    python scripts/backfill.py --repo owner/name\n\nIt exposes 5 public symbols and depends on 3 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `TASK_QUEUE` | constant | TASK_QUEUE = \"issue-lifecycle\" |\n| `build_issue_input` | function | def build_issue_input(repo: str, item: dict) -> IssueInput |\n| `list_open_issues` | function | def list_open_issues(repo: str, limit: int) -> list[dict] |\n| `workflow_id_for` | variable | workflow_id_for = issue_workflow_id |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `shared/temporal_client.py`\n- `shared/workflow_ids.py`\n- `shared/workflow_types.py`\n\n## Used by\n\nImported by 2 files in this repository.\n\n- `tests/test_backfill.py`\n- `tests/test_estimate_script.py`\n\n## Usage Notes\n\n**Layer:** Docs & Tooling ",
      "score": 3.205
    },
    {
      "path": "scripts/estimate.py",
      "title": "File: scripts/estimate.py",
      "summary": "Smoke harness: start one IssueEstimation workflow without the webhook.",
      "snippet": "# scripts/estimate.py\n\n## Overview\n\nSmoke harness: start one IssueEstimation workflow without the webhook.\n\n`/estimate` normally arrives as an `issue_comment.created` webhook, which\nneeds Layer B (Git",
      "excerpt": "# scripts/estimate.py\n\n## Overview\n\nSmoke harness: start one IssueEstimation workflow without the webhook.\n\n`/estimate` normally arrives as an `issue_comment.created` webhook, which\nneeds Layer B (GitHub App + public endpoint). This script starts the same\nworkflow directly against Temporal, so the estimation path — including the\nreal LLM call — can be exercised with only `temporal` and `worker` running.\n\nThe workflow reacts 👀 on the comment that carried the command. There is no\nsuch comment here, so `--comment-id` defaults to 0: harmless under DRY_RUN\n(the reaction is only logged), a 404 without it. Pass a real comment id when\nrunning for real.\n\nUsage:\n    python scripts/estimate.py --issue 83\n    python scripts/estimate.py --issue 83 --comment-id 2145678901\n    python scripts/estimate.py --issue 83 --no-wait\n\nIt exposes 3 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `TASK_QUEUE` | constant | TASK_QUEUE = \"issue-lifecycle\" |\n| `workflow_id_for` | variable | workflow_id_for = estimate_workflow_id |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `shared/workflow_ids.py`\n- `shared/workflow_types.py`\n\n## Used by\n\nImported by 1 file in this repository.\n\n- `tests/test_estimate_script.py`\n\n## Usage Notes\n\n**Layer:** Docs & Tooling | **Role:** internal\n\n## Questions this page answers\n\n- What does `scripts/estimate.py` export?\n- Where is `TASK_QUEUE` defined?\n- What imports `scripts/estimate.py`?\n\n",
      "score": 2.862
    },
    {
      "path": "scripts/diag.py",
      "title": "File: scripts/diag.py",
      "summary": "Диагностика эффективного конфига сервиса — «почему issue не доехал».",
      "snippet": "# scripts/diag.py\n\n## Overview\n\nДиагностика эффективного конфига сервиса — «почему issue не доехал».\n\nСобытие может пропасть молча: репозиторий вне ISSUE_AGENT_REPOS отбрасывается\nдо старта workflow,",
      "excerpt": "# scripts/diag.py\n\n## Overview\n\nДиагностика эффективного конфига сервиса — «почему issue не доехал».\n\nСобытие может пропасть молча: репозиторий вне ISSUE_AGENT_REPOS отбрасывается\nдо старта workflow, а GH_TOKEN незаметно подменяет GitHub App личным аккаунтом.\nНи то, ни другое не видно снаружи — GitHub получает 200, в Temporal пусто.\nСкрипт печатает то, что сервис реально видит в своём окружении.\n\nЗапускать ВНУТРИ контейнера, иначе прочитаешь окружение хоста, а не сервиса:\n\n    docker compose exec webhook python scripts/diag.py\n    docker compose exec webhook python scripts/diag.py --repo owner/name\n    docker compose exec webhook python scripts/diag.py --no-temporal\n\nЗначения секретов не печатаются ни при каких условиях — только «задан/не задан».\nВывод уходит в stdout и может попасть в тикет или чат, а конфиг сервиса\n(список репозиториев, адрес кластера) — уже разведданные для постороннего.\n\nКоды возврата: 0 — конфиг рабочий; 1 — Temporal недостижим либо авторизация в\nGitHub не настроена вовсе (ни PAT, ни App).\n\nIt exposes 9 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `SECRET_VARS` | constant | SECRET_VARS = ( |\n| `allowlist_lines` | function | def allowlist_lines(specs: list[str]) -> list[str] |\n| `repo_verdict_lines` | function | def repo_verdict_lines(repo: str, specs: list[str]) -> list[str] |\n| `auth_lines` | function | def auth_lines() -> tuple[list[str], bool] |\n| `temporal_config_lines` | function | ",
      "score": 2.337
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "webhook/main.py",
      "why_relevant": "Implements function _issue_input.",
      "score": 5.205
    },
    {
      "file": "worker/workflows.py",
      "why_relevant": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вто.",
      "score": 3.643
    },
    {
      "file": "scripts/backfill.py",
      "why_relevant": "Backfill: start one IssueLifecycle workflow per already-open Issue..",
      "score": 3.205
    }
  ],
  "code_rationale": [
    {
      "path": "scripts/backfill.py",
      "lines": [
        1,
        12
      ],
      "comment": "Backfill: start one IssueLifecycle workflow per already-open Issue. GitHub never sends webhooks for Issues that already exist, so the running service alone never processes the current backlog. This script enumerates open Issues via `gh` and starts workflows directly against Temporal. Runs in non-interactive batch mode (interactive=False): a VAGUE issue escalates instead of waiting for a human clarification that will not come. Usage: python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY python scripts/backfill.py --issue 83      # single issue (smoke test) python scripts/backfill.py --limit 5       # first N python scripts/backfill.py --repo owner/name",
      "matched_terms": [
        "webhook",
        "workflow"
      ]
    },
    {
      "path": "scripts/backfill.py",
      "lines": [
        94,
        96
      ],
      "comment": "REJECT_DUPLICATE keeps re-runs idempotent: a plain re-run skips already-processed issues (no double comments). To deliberately re-process, pass --suffix to mint fresh workflow ids instead.",
      "matched_terms": [
        "workflow"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "webhook/main.py",
      "name": "_issue_input",
      "lines": [
        156,
        173
      ],
      "source": "def _issue_input(payload: dict, *, interactive: bool):\n    \"\"\"`IssueInput` из полезной нагрузки вебхука.\n\n    Импорт внутри функции — как и в остальных ветках: shared/ подтягивается\n    лениво, чтобы старт вебхука не зависел от воркерных зависимостей.\n    \"\"\"\n    from shared.workflow_types import IssueInput\n\n    issue = payload[\"issue\"]\n    return IssueInput(\n        repo=payload[\"repository\"][\"full_name\"],\n        issue_number=issue[\"number\"],\n        title=issue[\"title\"],\n        body=issue.get(\"body\") or \"\",\n        author_login=issue[\"user\"][\"login\"],\n        author_type=(issue.get(\"user\") or {}).get(\"type\") or \"User\",\n        interactive=interactive,\n    )"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the _issue_input body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 462.7,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
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
      "path": "webhook/main.py",
      "lines": "62-411",
      "defines": "_issue_input:156, get_temporal_client:110, verify_signature:117, verify_agent_signature:267, agent_event:311, github_webhook:383"
    },
    {
      "path": "worker/workflows.py",
      "lines": "299-2267",
      "defines": "WebhookAudit:286, OrphanAgentEvent:309, CommentAck:330, IssueLifecycle:353, IssueDevelopment:2271, IssuePrFix:2364"
    },
    {
      "path": "scripts/backfill.py",
      "defines": "build_issue_input:42, list_open_issues:55, main:67, TASK_QUEUE:39"
    },
    {
      "path": "scripts/estimate.py",
      "defines": "main:43, TASK_QUEUE:38"
    },
    {
      "path": "scripts/diag.py",
      "defines": "allowlist_lines:51, repo_verdict_lines:69, auth_lines:90, temporal_config_lines:117, temporal_check_lines:125, secrets_lines:142"
    }
  ]
}

## Ход 3 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "shared/workflow_types.py::IssueInput"
}
```

**Ответ:**

{
  "symbol_id": "shared/workflow_types.py::IssueInput",
  "file": "shared/workflow_types.py",
  "name": "IssueInput",
  "kind": "class",
  "qualified_name": "shared.workflow_types.IssueInput",
  "signature": "class IssueInput",
  "language": "python",
  "start_line": 6,
  "end_line": 13,
  "symbol_start_line": 6,
  "symbol_end_line": 13,
  "source": "     6\tclass IssueInput:\n     7\t    repo: str\n     8\t    issue_number: int\n     9\t    title: str\n    10\t    body: str\n    11\t    author_login: str\n    12\t    author_type: str  # \"Bot\" | \"User\" | ...\n    13\t    interactive: bool = True  # False in batch backfill: VAGUE escalates, no wait",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 17.21,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3498
  }
}

## Ход 4 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Что делает функция request_analysis в shared/agent_launcher.py?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `request_analysis`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "shared/agent_launcher.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "shared/agent_launcher.py",
    "worker/workflows.py",
    "webhook/main.py",
    "scripts/backfill.py",
    "shared/workflow_ids.py"
  ],
  "retrieval": [
    {
      "path": "shared/agent_launcher.py",
      "title": "File: shared/agent_launcher.py",
      "summary": "Единая точка запуска агента: child при живом цикле, root — иначе.",
      "snippet": "# shared/agent_launcher.py\n\n## Overview\n\nЕдиная точка запуска агента: child при живом цикле, root — иначе.\n\nТребование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.\nДо этого воз",
      "excerpt": "# shared/agent_launcher.py\n\n## Overview\n\nЕдиная точка запуска агента: child при живом цикле, root — иначе.\n\nТребование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.\nДо этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifecycle` о них\nне знал и вешал косметическую метку.\n\nРежим выбирает ОДНА функция, а не каждый вызывающий. Иначе решение\n«child или root» разъедется по трём местам ровно так же, как когда-то разъехались\nформаты workflow id (см. `shared/workflow_ids.py`).\n\nКак принимается решение\n-----------------------\nНе «описать воркфлоу и посмотреть статус» — это лишний round-trip и гонка между\nпроверкой и стартом. Вместо этого **всегда signal-with-start** в цикл: он либо\nполучает сигнал, либо поднимается тем же вызовом. Дальше цикл сам решает,\nподнимать ли дочерний прогон.\n\nОстаётся один случай, который цикл обслужить не может: прогоны ПРЕЖНЕГО\nпоколения (линейный путь до #36). Их история не знает ни фазового цикла, ни\nсигнала на запуск агента — команда была бы принята и потеряна. Их отличает\nquery `handles_agents`; для них лаунчер стартует root-прогон, как раньше.\n\nДвойного прогона это не создаёт при любом исходе гонки: id агента фиксирован\n(`shared/workflow_ids.py`), поэтому второй старт упирается в\n`WorkflowAlreadyStarted`, а не тратит деньги второй раз.\n\nIt exposes 9 public symbols and depends on 1 other file.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- ",
      "score": 5.555,
      "key_symbols": [
        {
          "name": "_log",
          "kind": "variable",
          "signature": "_log = logging.getLogger(__name__)",
          "docstring": "",
          "start_line": 38,
          "end_line": 38
        },
        {
          "name": "TASK_QUEUE",
          "kind": "constant",
          "signature": "TASK_QUEUE = \"issue-lifecycle\"",
          "docstring": "",
          "start_line": 40,
          "end_line": 40
        },
        {
          "name": "ANALYSIS_WORKFLOW",
          "kind": "constant",
          "signature": "ANALYSIS_WORKFLOW = \"IssueAnalysis\"",
          "docstring": "",
          "start_line": 42,
          "end_line": 42
        },
        {
          "name": "ESTIMATION_WORKFLOW",
          "kind": "constant",
          "signature": "ESTIMATION_WORKFLOW = \"IssueEstimation\"",
          "docstring": "",
          "start_line": 43,
          "end_line": 43
        },
        {
          "name": "BFT_WORKFLOW",
          "kind": "constant",
          "signature": "BFT_WORKFLOW = \"IssueBft\"",
          "docstring": "",
          "start_line": 44,
          "end_line": 44
        },
        {
          "name": "CHILD",
          "kind": "constant",
          "signature": "CHILD = \"child\"",
          "docstring": "",
          "start_line": 47,
          "end_line": 47
        },
        {
          "name": "_cycle_handles_agents",
          "kind": "function",
          "signature": "async def _cycle_handles_agents(handle, repo: str, issue_number: int) -> bool:",
          "docstring": "Умеет ли этот цикл вести агентов дочерними прогонами.\n\n    Ошибку query не считаем за «не умеет»: signal-with-start уже прошёл, значит\n    цикл жив, а новых прогонов со временем становится только больше. Поднимать\n    на недоступном query второй дорогой прогон — худший из двух исходов.",
          "start_line": 51,
          "end_line": 63,
          "source_excerpt": "async def _cycle_handles_agents(handle, repo: str, issue_number: int) -> bool:\n    \"\"\"Умеет ли этот цикл вести агентов дочерними прогонами.\n\n    Ошибку query не считаем за «не умеет»: signal-with-start уже прошёл, значит\n    цикл жив, а новых прогонов со временем становится только больше. Поднимать\n    на недоступном query второй дорогой прогон — худший из двух исходов.\n    \"\"\"\n    try:\n        return bool(await handle.query(\"handles_agents\"))\n    except Exception as exc:\n        _log.warning(\"не удалось спросить цикл %s#%s о режиме агентов (%s) — \"\n                     \"считаю, что он ведёт их сам\", repo, issue_number, exc)\n        return True"
        },
        {
          "name": "request_analysis",
          "kind": "function",
          "signature": "async def request_analysis(client, issue_input, analyze, *, search_attributes=None) -> str:",
          "docstring": "`/analyze` или метка `run:analyze` — запустить аналитику по Issue.",
          "start_line": 66,
          "end_line": 95,
          "source_excerpt": "async def request_analysis(client, issue_input, analyze, *,\n                           search_attributes=None) -> str:\n    \"\"\"`/analyze` или метка `run:analyze` — запустить аналитику по Issue.\"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = analyze.repo, analyze.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"analyze_requested\",\n        start_signal_args=[analyze.comment_id],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            ANALYSIS_WORKFLOW, analyze,\n            id=analysis_workflow_id(repo, issue_number),\n            task_queue=TASK_QUEUE,\n            search_attributes=search_attributes,\n        )\n    except WorkflowAlreadyStartedError:\n        # Прогон по этому Issue уже идёт: пользователь видел ack первого\n        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.\n        _log.info(\"analysis already running for %s#%s\", repo, issue_number)\n    return ROOT"
        },
        {
          "name": "request_bft",
          "kind": "function",
          "signature": "async def request_bft(client, issue_input, req, *, search_attributes=None) -> str:",
          "docstring": "`/bft`, `/bft-deep` или метка `run:bft*` — собрать БФТ по Issue.\n\n    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт\n    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать\n    своё — ровно как с оценкой.",
          "start_line": 98,
          "end_line": 131,
          "source_excerpt": "async def request_bft(client, issue_input, req, *, search_attributes=None) -> str:\n    \"\"\"`/bft`, `/bft-deep` или метка `run:bft*` — собрать БФТ по Issue.\n\n    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт\n    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать\n    своё — ровно как с оценкой.\n    \"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = req.repo, req.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"bft_requested\",\n        start_signal_args=[req],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            BFT_WORKFLOW, req,\n            id=bft_workflow_id(repo, issue_number, req.mode),\n            task_queue=TASK_QUEUE,\n            search_attributes=search_attributes,\n        )\n    except WorkflowAlreadyStartedError:\n        # Прогон в этом режиме уже идёт: пользователь видел подтверждение\n        # первого запуска, второе было бы шумом. Вебхук — чистый транспорт.\n        _log.info(\"bft %s already running for %s#%s\", req.mode, repo, issue_number)\n    return ROOT"
        },
        {
          "name": "request_estimate",
          "kind": "function",
          "signature": "async def request_estimate(client, issue_input, estimate, *, search_attributes=None) -> str:",
          "docstring": "`/estimate` или метка `run:estimate` — оценить трудоёмкость.\n\n    Оценка фазу не двигает: это боковая команда, а не стадия пути Issue.\n    Цикл поднимает её дочерним прогоном и продолжает ждать своё.",
          "start_line": 134,
          "end_line": 166
        }
      ]
    },
    {
      "path": "worker/workflows.py",
      "title": "File: worker/workflows.py",
      "summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "snippet": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
      "excerpt": "# worker/workflows.py\n\n## Overview\n\nIssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,\nэто даёт идемпотентность бесплатно: повторный issues.opened webhook не\nсоздаст вторую сущность).\n\nSignals заменяют то, что раньше делали отдельные GitHub Actions,\nтриггерящиеся на лейблы:\n- human_decision(\"research-me\" | \"bug-me\" | \"build-me\")\n- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос\n  либо новый вопрос по припаркованной задаче\n\nWorkflow буквально приостанавливается на await self._wait_for_signal() —\nэто устраняет и гонку между duplicate-check/priority-scoring (теперь\nпоследовательные шаги одного потока, не параллельные Actions), и ручной\nпарсинг HTML-маркеров для счётчика раундов уточнения (состояние просто\nживёт в переменных workflow, Temporal журналирует его сам).\n\nIt exposes 42 public symbols and depends on 10 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `BFT_TRIAGE` | constant | BFT_TRIAGE = \"triage\" |\n| `MAX_CLARIFICATION_ROUNDS` | constant | MAX_CLARIFICATION_ROUNDS = 2 |\n| `MAX_ANALYSIS_CLARIFY_ROUNDS` | constant | MAX_ANALYSIS_CLARIFY_ROUNDS = 2 |\n| `MAX_REWORK_ROUNDS` | constant | MAX_REWORK_ROUNDS = 2 |\n| `AGENT_ANALYZE` | constant | AGENT_ANALYZE = \"__agent__:analyze\" |\n| `CLOSED` | constant | CLOSED = \"__closed__\" |\n| `SEEN_EVENTS_KEPT` | constant | SEEN_EVENTS_KEPT = 50 |\n| `HISTORY_EVENT_THRESHOLD` | constant | HISTORY_EVENT_THRESHOLD = 800 |\n| `WebhookAudit` | class | class Webhook",
      "score": 2.488,
      "key_symbols": [
        {
          "name": "handles_agents",
          "kind": "method",
          "signature": "def handles_agents(self) -> bool:",
          "docstring": "Ведёт ли этот прогон агентов дочерними воркфлоу (#37).\n\n        Спрашивает `shared/agent_launcher.py`, чтобы выбрать режим запуска.\n        Прогоны прежнего поколения (линейный путь) сигнала на запуск агента не\n        понимают — команда была бы принята и потеряна; для них лаунчер стартует\n        root-прогон, как раньше. Отдельного флага нет намеренно: цикл и\n        дочерние агенты приехали одним поколением, и разводить их двумя\n        независимыми признаками значило бы завести четыре состояния там, где\n        существуют два.",
          "start_line": 470,
          "end_line": 481,
          "source_excerpt": "    def handles_agents(self) -> bool:\n        \"\"\"Ведёт ли этот прогон агентов дочерними воркфлоу (#37).\n\n        Спрашивает `shared/agent_launcher.py`, чтобы выбрать режим запуска.\n        Прогоны прежнего поколения (линейный путь) сигнала на запуск агента не\n        понимают — команда была бы принята и потеряна; для них лаунчер стартует\n        root-прогон, как раньше. Отдельного флага нет намеренно: цикл и\n        дочерние агенты приехали одним поколением, и разводить их двумя\n        независимыми признаками значило бы завести четыре состояния там, где\n        существуют два.\n        \"\"\"\n        return self._phase_driven"
        },
        {
          "name": "analyze_requested",
          "kind": "method",
          "signature": "async def analyze_requested(self, comment_id: int | None) -> None:",
          "docstring": "По Issue запрошена аналитика — командой `/analyze` или меткой.\n\n        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а\n        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).\n        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу\n        из вебхука — связь между циклом Issue и работой агента была\n        декоративной, о чём и говорил прежний докстринг.\n\n        Тяжёлую работу из самого хендлера не запускаем: run() обычно\n        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с\n        основным циклом за фазу. Очередь снимает гонку — решение принимает та\n        фаза, в которой Issue находится сейчас.\n\n        Сигнал может прийти в самой первой активации воркфлоу — раньше, чем\n        run() выполнил `self._issue = issue` (Temporal применяет сигналы до\n        создания задачи run()); поэтому ЖДЁМ инициализацию через\n        wait_condition, а не теряем запрос молча по `self._issue is None`.",
          "start_line": 514,
          "end_line": 568
        },
        {
          "name": "bft_requested",
          "kind": "method",
          "signature": "async def bft_requested(self, req: BftRequest) -> None:",
          "docstring": "По Issue запрошен БФТ — командой `/bft`/`/bft-deep` или меткой `run:*`.\n\n        В очередь НЕ кладём, как и оценку: БФТ фазу не двигает. Быстрый проход —\n        это формулировка запроса, а не стадия пути; глубокий кладёт артефакты в\n        свою ветку и оставляет фазу честной. Двигать фазу в `business-analysis`\n        значило бы, что БФТ и цепочка FNR — одна и та же стадия, а это разные\n        документы с разной судьбой.\n\n        Прогон поднимаем прямо здесь и результата не ждём: цикл продолжает ждать\n        своё. Двойного прогона это не создаёт — id фиксирован в пределах режима.\n\n        Прогоны прежнего поколения сигнал получают, но обслужить не могут; им\n        лаунчер стартует root-прогон (см. query `handles_agents`), поэтому здесь\n        достаточно молча выйти — иначе на реплее их истории появилась бы команда,\n        которой там нет.",
          "start_line": 598,
          "end_line": 620
        },
        {
          "name": "_analysis_requested",
          "kind": "method",
          "signature": "async def _analysis_requested(self, issue: IssueInput) -> tuple:",
          "docstring": "Куда ведёт запрос аналитики из ТЕКУЩЕЙ фазы.\n\n        Если из неё есть ход в `business-analysis` — идём туда, и прогон\n        становится стадией пути Issue. Если нет (задача уже у разработчика, или\n        Issue в боковом состоянии), команду всё равно выполняем, но фазу не\n        трогаем: соврать про состояние хуже, чем не отразить в нём разовый\n        прогон.",
          "start_line": 1002,
          "end_line": 1022,
          "source_excerpt": "    async def _analysis_requested(self, issue: IssueInput) -> tuple:\n        \"\"\"Куда ведёт запрос аналитики из ТЕКУЩЕЙ фазы.\n\n        Если из неё есть ход в `business-analysis` — идём туда, и прогон\n        становится стадией пути Issue. Если нет (задача уже у разработчика, или\n        Issue в боковом состоянии), команду всё равно выполняем, но фазу не\n        трогаем: соврать про состояние хуже, чем не отразить в нём разовый\n        прогон.\n        \"\"\"\n        if lifecycle.can(self._phase, lifecycle.BUSINESS_ANALYSIS) and (\n                # Ход из `failed` появился позже самого цикла, и он меняет\n                # РЕШЕНИЕ, уже записанное в истории: у прогонов, где `/analyze`\n                # из `failed` однажды отработал мимо пути, на этом месте лежит\n                # `StartChildWorkflowExecutionInitiated`, а новый код планирует\n                # активность смены фазы. Без маркера реплей такой истории падает\n                # по недетерминизму — так на стенде встал воркфлоу Issue #11.\n                self._phase != lifecycle.FAILED\n                or workflow.patched(\"issue-lifecycle-analyze-recovers-failed\")):\n            return (lifecycle.BUSINESS_ANALYSIS, \"analysis\", True)\n        await self._run_analysis_child(issue)\n        return (self._phase, self._stage, False)"
        }
      ]
    },
    {
      "path": "webhook/main.py",
      "title": "File: webhook/main.py",
      "summary": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:",
      "snippet": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:",
      "excerpt": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и\n                               через signal-with-start поднимает цикл-владелец\n                               состояния, `/estimate` — IssueEstimation,\n                               `/bft` и `/bft-deep` — IssueBft (хвост команды\n                               уезжает в прогон как замечания/уточнения); любой\n                               другой комментарий — сигнал уже идущему workflow\n                               (используется циклом уточнений)\n- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и\n                               команда в комментарии (run:analyze ->\n                               IssueAnalysis, run:estimate -> IssueEstimation,\n                               run:bft / run:bft-deep -> IssueBft);\n                               точки решения человека (research-me / bug-me /\n                               build-me) идут через signal-with-start: воркфлоу\n                               триажа может не существовать, тогда он\n                               поднимается тем же вызовом\n\nНичего из бизнес-логики здесь нет — это чистый транспортный слой.\n\nIt exposes 8 public symbols and depends on 13 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n|",
      "score": 2.488
    },
    {
      "path": "scripts/backfill.py",
      "title": "File: scripts/backfill.py",
      "summary": "Backfill: start one IssueLifecycle workflow per already-open Issue.",
      "snippet": "Backfill: start one IssueLifecycle workflow per already-open Issue.",
      "excerpt": "# scripts/backfill.py\n\n## Overview\n\nBackfill: start one IssueLifecycle workflow per already-open Issue.\n\nGitHub never sends webhooks for Issues that already exist, so the running\nservice alone never processes the current backlog. This script enumerates\nopen Issues via `gh` and starts workflows directly against Temporal.\n\nRuns in non-interactive batch mode (interactive=False): a VAGUE issue\nescalates instead of waiting for a human clarification that will not come.\n\nUsage:\n    python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY\n    python scripts/backfill.py --issue 83      # single issue (smoke test)\n    python scripts/backfill.py --limit 5       # first N\n    python scripts/backfill.py --repo owner/name\n\nIt exposes 5 public symbols and depends on 3 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `TASK_QUEUE` | constant | TASK_QUEUE = \"issue-lifecycle\" |\n| `build_issue_input` | function | def build_issue_input(repo: str, item: dict) -> IssueInput |\n| `list_open_issues` | function | def list_open_issues(repo: str, limit: int) -> list[dict] |\n| `workflow_id_for` | variable | workflow_id_for = issue_workflow_id |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `shared/temporal_client.py`\n- `shared/workflow_ids.py`\n- `shared/workflow_types.py`\n\n## Used by\n\nImported by 2 files in this repository.\n\n- `tests/test_backfill.py`\n- `tests/test_estimate_script.py`\n\n## Usage Notes\n\n**Layer:** Docs & Tooling ",
      "score": 2.488
    },
    {
      "path": "shared/workflow_ids.py",
      "title": "File: shared/workflow_ids.py",
      "summary": "Идентификаторы Temporal-workflow — в одном месте.",
      "snippet": "# shared/workflow_ids.py\n\n## Overview\n\nИдентификаторы Temporal-workflow — в одном месте.\n\nID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный\n`issues.opened` идемпотентным, `",
      "excerpt": "# shared/workflow_ids.py\n\n## Overview\n\nИдентификаторы Temporal-workflow — в одном месте.\n\nID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный\n`issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делает\nидемпотентной повторную доставку вебхука с командой. Формат собирают и вебхук,\nи скрипты прямого запуска; разъехавшись, они молча потеряли бы именно эту\nидемпотентность — поэтому строка живёт здесь одна.\n\nIt exposes 7 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `issue_workflow_id` | function | def issue_workflow_id(repo_full_name: str, issue_number: int, suffix: str = \"\") -> str |\n| `estimate_workflow_id` | function | def estimate_workflow_id(repo_full_name: str, issue_number: int, comment_id: int \\| None = None) -> str |\n| `bft_workflow_id` | function | def bft_workflow_id(repo_full_name: str, issue_number: int, mode: str) -> str |\n| `comment_ack_workflow_id` | function | def comment_ack_workflow_id(repo_full_name: str, comment_id: int) -> str |\n| `analysis_workflow_id` | function | def analysis_workflow_id(repo_full_name: str, issue_number: int) -> str |\n| `development_workflow_id` | function | def development_workflow_id(repo_full_name: str, issue_number: int) -> str |\n| `pr_fix_workflow_id` | function | def pr_fix_workflow_id(repo_full_name: str, pr_number: int, round_number: int) -> str |\n\n## Used by\n\nImported by 15 files in this repository.\n\n- `scripts/backfill.py`\n- `scripts/e2e_live.py`\n- `sc",
      "score": 2.472
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "shared/agent_launcher.py",
      "why_relevant": "Implements function request_analysis.",
      "score": 5.555
    },
    {
      "file": "worker/workflows.py",
      "why_relevant": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вто.",
      "score": 2.488
    },
    {
      "file": "webhook/main.py",
      "why_relevant": "Webhook receiver: единственная точка входа для GitHub.",
      "score": 2.488
    }
  ],
  "code_rationale": [
    {
      "path": "worker/workflows.py",
      "lines": [
        471,
        480
      ],
      "comment": "Ведёт ли этот прогон агентов дочерними воркфлоу (#37). Спрашивает `shared/agent_launcher.py`, чтобы выбрать режим запуска. Прогоны прежнего поколения (линейный путь) сигнала на запуск агента не понимают — команда была бы принята и потеряна; для них лаунчер стартует root-прогон, как раньше. Отдельного флага нет намеренно: цикл и дочерние агенты приехали одним поколением, и разводить их двумя независимыми признаками значило бы завести четыре состояния там, где существуют два.",
      "matched_terms": [
        "agent_launcher",
        "shared"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "shared/agent_launcher.py",
      "name": "request_analysis",
      "lines": [
        66,
        95
      ],
      "source": "async def request_analysis(client, issue_input, analyze, *,\n                           search_attributes=None) -> str:\n    \"\"\"`/analyze` или метка `run:analyze` — запустить аналитику по Issue.\"\"\"\n    from temporalio.exceptions import WorkflowAlreadyStartedError\n\n    repo, issue_number = analyze.repo, analyze.issue_number\n    handle = await client.start_workflow(\n        \"IssueLifecycle\",\n        issue_input,\n        id=issue_workflow_id(repo, issue_number),\n        task_queue=TASK_QUEUE,\n        search_attributes=search_attributes,\n        start_signal=\"analyze_requested\",\n        start_signal_args=[analyze.comment_id],\n    )\n    if await _cycle_handles_agents(handle, repo, issue_number):\n        return CHILD\n\n    try:\n        await client.start_workflow(\n            ANALYSIS_WORKFLOW, analyze,\n            id=analysis_workflow_id(repo, issue_number),\n            task_queue=TASK_QUEUE,\n            search_attributes=search_attributes,\n        )\n    except WorkflowAlreadyStartedError:\n        # Прогон по этому Issue уже идёт: пользователь видел ack первого\n        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.\n        _log.info(\"analysis already running for %s#%s\", repo, issue_number)\n    return ROOT"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the request_analysis body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 457.1,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
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
      "path": "shared/agent_launcher.py",
      "lines": "38-166",
      "defines": "request_analysis:66, request_bft:98, request_estimate:134, TASK_QUEUE:40, ANALYSIS_WORKFLOW:42, ESTIMATION_WORKFLOW:43"
    },
    {
      "path": "worker/workflows.py",
      "lines": "470-1022",
      "defines": "WebhookAudit:286, OrphanAgentEvent:309, CommentAck:330, IssueLifecycle:353, IssueDevelopment:2271, IssuePrFix:2364"
    },
    {
      "path": "webhook/main.py",
      "defines": "get_temporal_client:110, verify_signature:117, verify_agent_signature:267, agent_event:311, github_webhook:383"
    },
    {
      "path": "scripts/backfill.py",
      "defines": "build_issue_input:42, list_open_issues:55, main:67, TASK_QUEUE:39"
    },
    {
      "path": "shared/workflow_ids.py",
      "defines": "issue_workflow_id:12, estimate_workflow_id:19, bft_workflow_id:29, comment_ack_workflow_id:38, analysis_workflow_id:45, development_workflow_id:51"
    }
  ]
}

## Ход 5 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "Где в README.md описаны команды вроде /analyze или /estimate?"
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
    "onboarding/how_it_works",
    "worker/activities.py::decompose_issue"
  ],
  "retrieval": [
    {
      "path": "onboarding/how_it_works",
      "title": "How It Works",
      "summary": "Traced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.",
      "snippet": "/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. README.md. Start here for the end-to-end picture before diving into the code.\n   - `README.md`\n\n\n2.",
      "excerpt": "# How It Works\n\nTraced from the entry points outward: which files each run touches, in order. What happens at each hop is not derivable from the call graph, so this page shows the shape of execution rather than the behaviour.\n\n## Shape`poh-issue-agents` looks like a **module**, based on:\n\n- no service / CLI / library signal — treating as module collection\n\n\n\n\n## Entry points\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Traced flows\n\n\n\n\n### From `worker/workflows.py::IssueLifecycle::run`\n\n\n\n1. `worker/workflows.py::IssueLifecycle::run`\n\n2. `worker/workflows.py::IssueLifecycle::_run_phase_loop`\n\n3. `worker/workflows.py::IssueLifecycle::_phase_await_build`\n\n4. `worker/workflows.py::IssueLifecycle::_park`\n\n5. `shared/awaiting.py::Awaiting`\n\n\n\n\n\n\n### From `webhook/main.py::github_webhook`\n\n\n\n1. `webhook/main.py::github_webhook`\n\n2. `shared/agent_launcher.py::request_analysis`\n\n3. `shared/workflow_ids.py::issue_workflow_id`\n\n\n\n\n\n\n### From `worker/workflows.py::IssueAnalysis::run`\n\n\n\n1. `worker/workflows.py::IssueAnalysis::run`\n\n2. `worker/workflows.py::_run_staged_analysis`\n\n3. `worker/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided tour walks these in sequence.\n\n1. README.md. Start here for the end-to-end picture before diving into the code.\n   - `README.md`\n\n\n2. main.py. An entry point — execution and imports fan out from here.\n   - `webhook/main.py`\n\n\n3. workflow_types.py. Directly used by the entry points above; a core collab",
      "score": 2.0
    },
    {
      "path": "webhook",
      "title": "Application Webhook",
      "summary": "`webhook`",
      "snippet": "mporting it.\n\n- `tests` (co-changed 9×)\n\n- `worker` (co-changed 4×)\n\n- `shared` (co-changed 3×)\n\n- `README.md` (co-changed 1×)\n\n- `.env.example` (co-changed 1×)\n\n\n\n\n## Recent activity\nMost active file",
      "excerpt": "# Application Webhook\n\n`webhook`\n\n**Language:** python | **Files:** 1 | **Public symbols:** 9 / 21\n\n\nCovers the 1 source files in webhook. Does not cover code outside those directories, which is documented on its own pages.\n\n\n\n\n## Overview\n\nApplication Webhook covers 1 python file across 1 directory, exposing 9 public symbols. It hosts 1 entry point into this subsystem; sits centrally in the import graph (mean PageRank 0.0090); is imported by 11 other modules; draws on 12 internal modules.\n\n\n## Entry Points\n\n- `webhook/main.py`\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `webhook/main.py` *(entry point)*: Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal: - issues.opened -> старт нового workflow (ID = repo-issue-N) - issue_comment.\n\n\n\n\n\n\n\n\n## Dependencies (modules this imports)\n\n- `shared/__init__.py`\n\n- `shared/agent_comment.py`\n\n- `shared/agent_events.py`\n\n- `shared/agent_launcher.py`\n\n- `shared/authz.py`\n\n- `shared/commands.py`\n\n- `shared/labels.py`\n\n- `shared/repos.py`\n\n- `shared/sentry_setup.py`\n\n- `shared/temporal_client.py`\n\n- `shared/workflow_ids.py`\n\n- `shared/workflow_types.py`\n\n\n\n\n## Dependents (modules that import this)\n\n- `tests/test_agent_comment.py`\n\n- `tests/test_agent_event_endpoint.py`\n\n- `tests/test_bft_webhook.py`\n\n- `tests/test_e2e_issue_lifecycle.py`\n\n- `tests/test_sentry_noise.py`\n\n- `tests/test_trigger_authz.py`\n\n- `tests/test_webhook_audit.py`\n\n- `tests/test_webhook_co",
      "score": 1.967
    },
    {
      "path": "shared",
      "title": "Utility Shared",
      "summary": "`shared`",
      "snippet": "мысл, а не только уникальность: `issue-<repo>-<n>` делает повторный `issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делае\n\n- `shared/labels.py`: Словарь меток протокола агентов v1. И",
      "excerpt": "# Utility Shared\n\n`shared`\n\n**Language:** python | **Files:** 18 | **Public symbols:** 236 / 256\n\n\nCovers the 18 source files in shared. Does not cover code outside those directories, which is documented on its own pages.\n\n\n\n\n## Overview\n\nUtility Shared covers 18 python files across 1 directory, exposing 236 public symbols. It sits centrally in the import graph (mean PageRank 0.0091); is imported by 74 other modules.\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `shared/workflow_types.py`: `shared/workflow_types.py` is a python source file in the Utility layer. It exposes 26 public symbols.\n\n- `shared/__init__.py`\n\n- `shared/lifecycle.py`: Модель фаз жизненного цикла Issue — единственный источник правды. Сегодня состояние Issue размазано по четырём независимым представлениям (метки, переменные воркфлоу, комментарии, Event History), и н\n\n- `shared/workflow_ids.py`: Идентификаторы Temporal-workflow — в одном месте. ID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный `issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делае\n\n- `shared/labels.py`: Словарь меток протокола агентов v1. Источник: po-helper-org/.github → AGENT-PROTOCOL.md, раздел 4. Правило протокола — **одна метка, один писатель**: метку из чужой зоны агент только читает, иначе дв\n\n- `shared/agent_comment.py`: Подпись под комментариями сервиса — чтобы он не принимал их за ответ человека. Найдено на живом прогоне: оба сигнала `user_comment` в истории цикла о",
      "score": 1.935
    },
    {
      "path": "worker",
      "title": "Application Worker",
      "summary": "`worker`",
      "snippet": "вместимого эндпоинта z.ai — даёт типобезопасные Pydantic-ответы с автоматическим retry п\n\n- `worker/estimate_report.py`: Рендер комментария с оценкой. Чистая функция: Estimate + факты + контекст -> ma",
      "excerpt": "# Application Worker\n\n`worker`\n\n**Language:** python | **Files:** 9 | **Public symbols:** 190 / 294\n\n\nCovers the 9 source files in worker. Does not cover code outside those directories, which is documented on its own pages.\n\n\n\n\n## Overview\n\nApplication Worker covers 9 python files across 1 directory, exposing 190 public symbols. It sits centrally in the import graph (mean PageRank 0.0116); is imported by 55 other modules; draws on 15 internal modules.\n\n\n\n## Files\n\nHighest-PageRank first: the order to read them in.\n\n- `worker/estimation.py`: Детерминированный расчёт оценки задачи. Чистый модуль: ни сети, ни LLM, ни Temporal. Модель отдаёт только факты (EstimationFacts), а коэффициенты, надбавки, PERT, cross-check и коридоры считаются зде\n\n- `worker/activities.py`: Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions). Изменился только транс\n\n- `worker/github_client.py`: Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужн\n\n- `worker/worker.py`: `worker/worker.py` is a python source file in the Application layer. It exposes 1 public symbol and depends on 7 other files.\n\n- `worker/workflows.py`: IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повто",
      "score": 1.875
    },
    {
      "path": "worker/activities.py::decompose_issue",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.decompose_issue",
      "summary": "Разбор задачи на подзадачи с раскладкой по релизам.",
      "snippet": "worker.activities.decompose_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\ndef decompose_issue(issue: IssueInput, branch: str) -> dict\n```\n\n## O",
      "excerpt": "# worker.activities.decompose_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\ndef decompose_issue(issue: IssueInput, branch: str) -> dict\n```\n\n## Overview\n\nРазбор задачи на подзадачи с раскладкой по релизам.\n\nТребования читаются из ветки аналитики: разбивать по одному телу Issue —\nзначит делить намерение, а не работу. Если аналитики не было, разбор идёт\nот тела, и это честнее, чем притворяться, будто требования есть.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n35 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_issue_113_basic.py`\n- `tests/test_issue_113_context_loss.py`\n- `tests/t",
      "score": 1.818
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval.",
  "_meta": {
    "timing_ms": 220.8,
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
      "path": "worker/activities.py",
      "defines": "GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101, CommentIntentExtraction:115"
    },
    {
      "path": "tests/test_estimate_activities.py",
      "defines": "FakeGitHub:10, comment:42, fake:47, test_ack_puts_eyes_on_the_command_comment:56, test_context_carries_title_body_and_labels:61, test_bot_comments_and_commands_are_excluded_from_the_thread:69"
    },
    {
      "path": "worker/consolidation_activities.py",
      "defines": "ProfileExtraction:22, SynthOut:44, ZoneOut:111, TaxonomyExtraction:117, AssignExtraction:136, IncrementOut:159"
    },
    {
      "path": "shared/bft.py",
      "defines": "epic_slug:43, branch:53, epic_dir:57, artefacts_dir:61, statement_path:65, document_path:76"
    },
    {
      "path": ".claude/skills/subagent-driven-development/scripts/task-brief"
    }
  ]
}
