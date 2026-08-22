---
session: rw-openhands-po-helper-org__poh-issue-agents-77
workspace: contour
turns: 8
started: 2026-08-22T19:55:16Z
finished: 2026-08-22T19:57:53Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 15 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 15 мин |
| `poh-helper` | `18512c1e7ce9` | 15 мин |
| `poh-infra` | `a1db4f02f10c` | 15 мин |
| `poh-issue-agents` | `993d8561f100` | 15 мин |
| `poh-memory-engine` | `194e39319b3f` | 15 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 15 мин |
| `poh-scheduller` | `04cc3f47aff9` | 15 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 15 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 2 сут |

# Диалог

## Ход 1 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "How are the pipeline stages (FNR, БФТ) currently implemented? What components are responsible for running claude -p and where are they located?"
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
    "worker/activities.py",
    "shared/bft.py",
    "worker/activities.py::run_bft_stage",
    ".claude/skills/brainstorming/scripts/stop-server.sh",
    ".claude/skills/writing-skills/render-graphs.js"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "zing` | function | async def mark_analyzing(repo: str, issue_number: int) -> None |\n| `mark_command_running` | function | async def mark_command_running(repo: str, issue_number: int, command: str) ->",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 117 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) ->",
      "score": 1.865,
      "key_symbols": [
        {
          "name": "mark_command_running",
          "kind": "function",
          "signature": "async def mark_command_running(repo: str, issue_number: int, command: str) -> None:",
          "docstring": "Метка «прогон идёт» ставится САМИМ прогоном, а не только триггером.\n\n    Иначе выборка `label:run:*` врала бы: запуск командой в комментарии не\n    оставлял бы следа в ленте Issue. Повторная установка той же метки для\n    GitHub безопасна — при запуске лейблом она уже висит.",
          "start_line": 496,
          "end_line": 502,
          "source_excerpt": "async def mark_command_running(repo: str, issue_number: int, command: str) -> None:\n    \"\"\"Метка «прогон идёт» ставится САМИМ прогоном, а не только триггером.\n\n    Иначе выборка `label:run:*` врала бы: запуск командой в комментарии не\n    оставлял бы следа в ленте Issue. Повторная установка той же метки для\n    GitHub безопасна — при запуске лейблом она уже висит.\"\"\"\n    await asyncio.to_thread(github_client.add_label, repo, issue_number, run_label(command))"
        },
        {
          "name": "CLAUDE_STAGE_TIMEOUT_SEC",
          "kind": "constant",
          "signature": "CLAUDE_STAGE_TIMEOUT_SEC = 900",
          "docstring": "",
          "start_line": 818,
          "end_line": 818,
          "source_excerpt": "CLAUDE_STAGE_TIMEOUT_SEC = 900"
        },
        {
          "name": "_claude_anthropic_creds",
          "kind": "function",
          "signature": "def _claude_anthropic_creds() -> tuple[str, str]:",
          "docstring": "Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ\n    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ\n    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),\n    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать\n    не нужно, но если заданы — приоритетнее (явный override).",
          "start_line": 997,
          "end_line": 1011
        },
        {
          "name": "_run_claude",
          "kind": "function",
          "signature": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:",
          "docstring": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.",
          "start_line": 1014,
          "end_line": 1059
        },
        {
          "name": "run_bug_pipeline",
          "kind": "function",
          "signature": "def run_bug_pipeline(issue: IssueInput) -> None:",
          "docstring": "TODO: перенести содержимое bug-pipeline.yml аналогично.",
          "start_line": 1578,
          "end_line": 1580
        },
        {
          "name": "_runner_home",
          "kind": "function",
          "signature": "def _runner_home(slug: str) -> str:",
          "docstring": "Домашний каталог раннера — каталог задачи, но только при живой интеграции.\n\n    Агент ищет конфигурацию MCP в `$HOME/.openhands/mcp.json` (спайк FR-16), а\n    общий том смонтирован в другом месте. Переставить HOME дешевле, чем\n    оборачивать ENTRYPOINT образа.\n\n    Интеграция выключена — возвращаем пусто, и HOME остаётся тем, что задан\n    образом: поведение прогонов без Repowise не меняется вовсе.",
          "start_line": 1587,
          "end_line": 1599
        },
        {
          "name": "_write_runner_mcp_config",
          "kind": "function",
          "signature": "def _write_runner_mcp_config(issue: IssueInput, root: Path) -> None:",
          "docstring": "Конфигурация MCP в каталог задачи, откуда её прочитает раннер.\n\n    Каталог лежит на общем томе и виден обоим контейнерам; права выставляются\n    вместе с остальным содержимым каталога задачи — раннер работает от\n    непривилегированного пользователя и в чужой каталог писать не сможет.",
          "start_line": 1602,
          "end_line": 1618
        },
        {
          "name": "_handover_to_runner",
          "kind": "function",
          "signature": "def _handover_to_runner(path: Path) -> None:",
          "docstring": "Передать каталог задачи раннеру целиком: он работает не от root.\n\n    Передаётся ВЕСЬ каталог задачи, а не только клон. Каталог задачи — это\n    ещё и `$HOME` раннера (см. `_runner_home`), а OpenHands держит там своё\n    состояние: `$HOME/.openhands/conversations`. Оставленный за root'ом, он\n    даёт `PermissionError` на первом же шаге, но код возврата остаётся нулевым\n    — снаружи прогон выглядит как отработавший, а правок нет ни одной.\n\n    Падаем громко. Молча оставленный каталог root'а — рабочее место, в которое\n    агент не может писать: он не сообщает об отказе, а уходит писать в /tmp и\n    докладывает об успехе. Прогон отрабатывает целиком и не оставляет ни одной\n    правки — отказ, который снаружи выглядит как исправная работа.",
          "start_line": 1809,
          "end_line": 1833
        },
        {
          "name": "_reap_runner",
          "kind": "function",
          "signature": "def _reap_runner(slug: str) -> None:",
          "docstring": "Снять контейнер прошлой попытки, если он пережил своего запускателя.\n\n    Temporal повторяет активность до трёх раз. Умерший вместе с воркером прогон\n    контейнер за собой не убирает (`--rm` срабатывает только на нормальном\n    выходе), и вторая попытка либо упирается в занятое имя, либо запускает\n    второго агента в тот же рабочий каталог. На стенде остаток жил полчаса и\n    доедал память, из-за которой следующая задача еле ползла.",
          "start_line": 1836,
          "end_line": 1846
        },
        {
          "name": "CLAUDE_HOME",
          "kind": "constant",
          "signature": "CLAUDE_HOME = Path(os.environ.get(\"CLAUDE_HOME\", \"/root/.claude\"))",
          "docstring": "",
          "start_line": 2838,
          "end_line": 2838
        }
      ]
    },
    {
      "path": "shared/bft.py",
      "title": "File: shared/bft.py",
      "summary": "БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.",
      "snippet": "er: int) -> str |\n| `DEEP_STAGE_NAMES` | constant | DEEP_STAGE_NAMES: tuple[str, ...] = ( |\n| `deep_stages` | function | def deep_stages(issue_number: int) -> list[tuple[str, str, str \\| None, str \\|",
      "excerpt": "# shared/bft.py\n\n## Overview\n\nБФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.\n\nМодуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и\n`estimation.py`. Формат комментария и перечень стадий проверяются напрямую, без\nпрогона воркфлоу и без обращения к модели.\n\nПочему БФТ, а не прежний advisor-ответ\n--------------------------------------\nКлассификация отвечала свободным текстом «Ситуация / Ограничение / Варианты\nрешения / Оценка сложности». В нём нет сценария приёмки, нет границ и нет\nсписка открытых вопросов с владельцами, зато есть «варианты решения» — то есть\nпроектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)\nдаёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`\n→ `Границы` → `Документация` плюс таблицу требований на цитатах.\n\nДва режима, две цены\n--------------------\n`fast` — один вызов модели по тексту Issue и треду: секунды, комментарий в Issue.\n`deep` — канонический пайплайн `bft-writer` внутри клона репозитория: минуты,\nартефакты в ветке. Первый идёт сам на триаже, второй — только по явной команде:\nдорогую стадию запускает человек, а не догадка агента.\n\nIt exposes 43 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `FAST` | constant | FAST = \"fast\" |\n| `DEEP` | constant | DEEP = \"deep\" |\n| `MODES` | constant | MODES = (FAST, DEEP) |\n| `BRANCH_PREFIX` | constant | BRANCH_PREFIX = \"bft-research\" |\n| `DOCS_ROOT` | constant | DOC",
      "score": 1.792,
      "key_symbols": [
        {
          "name": "statement_path",
          "kind": "function",
          "signature": "def statement_path(issue_number: int) -> str:",
          "docstring": "Постановка от заказчика — файл, который пайплайн читает вместо JIRA.\n\n    В контуре Issue трекера нет: `/bft-context-gen` штатно тянет эпик из JIRA, а\n    здесь его роль играет сам Issue вместе с тредом и уточнениями из команды.\n    Путь фиксирован, потому что на него ссылается адаптированная команда\n    (`.claude/commands/bft-context-gen.md`, раздел «Постановка без JIRA»).",
          "start_line": 65,
          "end_line": 73,
          "source_excerpt": "def statement_path(issue_number: int) -> str:\n    \"\"\"Постановка от заказчика — файл, который пайплайн читает вместо JIRA.\n\n    В контуре Issue трекера нет: `/bft-context-gen` штатно тянет эпик из JIRA, а\n    здесь его роль играет сам Issue вместе с тредом и уточнениями из команды.\n    Путь фиксирован, потому что на него ссылается адаптированная команда\n    (`.claude/commands/bft-context-gen.md`, раздел «Постановка без JIRA»).\n    \"\"\"\n    return f\"{artefacts_dir(issue_number)}/po-statement.md\""
        },
        {
          "name": "deep_stages",
          "kind": "function",
          "signature": "def deep_stages(issue_number: int) -> list[tuple[str, str, str | None, str | None]]:",
          "docstring": "(имя, промпт, ожидаемый артефакт, требуемый вход) для каждой стадии.\n\n    Промпт — `/<команда> <аргументы>` и ничего больше: `claude -p` разворачивает\n    команду только тогда, когда она стоит первой, а произвольный текст после\n    аргументов команда прочитает как ещё один аргумент.\n\n    `index` и `debate` ожидаемого файла не имеют: первый строит каталог\n    `.bft/index/`, второй дописывает вердикт в конец `concept.md`.\n\n    Issue #78, находка D: требуемый вход объявлен полностью, чтобы не терять\n    зависимости при смене исполнителя.",
          "start_line": 92,
          "end_line": 128,
          "source_excerpt": "def deep_stages(issue_number: int) -> list[tuple[str, str, str | None, str | None]]:\n    \"\"\"(имя, промпт, ожидаемый артефакт, требуемый вход) для каждой стадии.\n\n    Промпт — `/<команда> <аргументы>` и ничего больше: `claude -p` разворачивает\n    команду только тогда, когда она стоит первой, а произвольный текст после\n    аргументов команда прочитает как ещё один аргумент.\n\n    `index` и `debate` ожидаемого файла не имеют: первый строит каталог\n    `.bft/index/`, второй дописывает вердикт в конец `concept.md`.\n\n    Issue #78, находка D: требуемый вход объявлен полностью, чтобы не терять\n    зависимости при смене исполнителя.\n    \"\"\"\n    slug = epic_slug(issue_number)\n    artefacts = artefacts_dir(issue_number)\n    pack = f\"{artefacts}/bft-context-pack.md\"\n    problem = f\"{artefacts}/problem.md\"\n    concept = f\"{artefacts}/concept.md\"\n    statement = f\"{artefacts}/po-statement.md\"\n    document = document_path(issue_number)\n    validation = f\"{artefacts}/validation.md\"\n    \n    return [\n        (\"index\", \"/bft-index\", None, None),\n        # Второй аргумент `/bft-context-gen` — ключ эпика в трекере. Трекера нет,\n        # и подставлять туда выдуманный ключ хуже, чем назвать вещи своими\n        # именами: команда увидит тот же slug и не станет искать несуществующий\n        # проект.\n        (\"context\", f\"/bft-context-gen {slug} {slug}\", pack, None),\n        (\"problem\", f\"/bft-problem {slug}\", problem, f\"{pack},{statement}\"),\n        (\"concept\", f\"/bft-concept {slug}\", concept, f\"{problem},{pack},{statement}\"),\n        (\"debate\", f\"/bft-debate {slug}\", None, concept),\n        # Для draft нужны все предыдущие артефакты плюс исходники репозитория\n        (\"draft\", f\"/bft-draft {slug}\", document, \n         f\"{concept},{problem},{pack},{statement},src\"),\n        (\"validate\", f\"/bft-validate {slug}\", validation, document),\n    ]"
        },
        {
          "name": "direct_stages",
          "kind": "function",
          "signature": "def direct_stages() -> set[str]:",
          "docstring": "Стадии, которые идут прямыми вызовами вместо `claude -p`.\n\n    Пусто (умолчание) — прежнее поведение целиком: ни одна стадия не меняет\n    исполнителя. Флаг перечисляет стадии поимённо, чтобы переключать их по одной\n    и сравнивать результат с агентом на той же задаче.",
          "start_line": 383,
          "end_line": 391
        },
        {
          "name": "parse_session_id",
          "kind": "function",
          "signature": "def parse_session_id(text: str) -> str:",
          "docstring": "Id сессии entire из вывода `entire session list`.\n\n    Формат строки: `Claude Code · <repo> · session <uuid>`. Разбираем по\n    ключевому слову, а не по позиции: CLI меняет оформление между версиями, а\n    слово `session` перед идентификатором держится.",
          "start_line": 720,
          "end_line": 730
        }
      ]
    },
    {
      "path": "worker/activities.py::run_bft_stage",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.run_bft_stage",
      "summary": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.",
      "snippet": "st, stage_name: str) -> dict\n```\n\n## Overview\n\nОдна стадия канонического пайплайна БФТ — отдельный `claude -p`.\n\nРазложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной\nактивностью вес",
      "excerpt": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 13\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) -> dict\n```\n\n## Overview\n\nОдна стадия канонического пайплайна БФТ — отдельный `claude -p`.\n\nРазложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной\nактивностью весь пайплайн был бы одним баром в Event History на десятки\nминут, и застрявшая стадия не называла бы себя.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n32 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_phases.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_closing.py`\n- `tests/test_",
      "score": 1.714
    },
    {
      "path": ".claude/skills/brainstorming/scripts/stop-server.sh",
      "title": "Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh",
      "summary": "`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructure file (shell). It declares 5 named targets, listed below. Its behaviour is not derivable from structure, so the source is reproduced in full.",
      "snippet": "# Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh\n\n**Type:** shell | **Declared targets:** 5\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructur",
      "excerpt": "# Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh\n\n**Type:** shell | **Declared targets:** 5\n\n## Overview\n\n`.claude/skills/brainstorming/scripts/stop-server.sh` is an infrastructure file (shell). It declares 5 named targets, listed below. Its behaviour is not derivable from structure, so the source is reproduced in full.\n\n\n## Declared targets\n\n- `mark_stopped`\n\n- `read_expected_server_id`\n\n- `command_line_for_pid`\n\n- `command_has_server_id`\n\n- `is_brainstorm_server`\n\n\n\n\n## Source\n\n```shell\n#!/usr/bin/env bash\n# Stop the brainstorm server and clean up\n# Usage: stop-server.sh <session_dir>\n#\n# Kills the server process. Only deletes session directory if it's\n# under /tmp (ephemeral). Persistent directories (.superpowers/) are\n# kept so mockups can be reviewed later.\n\nSESSION_DIR=\"$1\"\n\nif [[ -z \"$SESSION_DIR\" ]]; then\n  echo '{\"error\": \"Usage: stop-server.sh <session_dir>\"}'\n  exit 1\nfi\n\nSTATE_DIR=\"${SESSION_DIR}/state\"\nPID_FILE=\"${STATE_DIR}/server.pid\"\nSERVER_ID_FILE=\"${STATE_DIR}/server-instance-id\"\n\nmark_stopped() {\n  local reason=\"$1\"\n  rm -f \"${STATE_DIR}/server-info\"\n  printf '{\"reason\":\"%s\",\"timestamp\":%s}\\n' \"$reason\" \"$(date +%s)\" > \"${STATE_DIR}/server-stopped\"\n}\n\nread_expected_server_id() {\n  [[ -f \"$SERVER_ID_FILE\" ]] || return 1\n  local id\n  id=\"$(tr -d '\\r\\n' < \"$SERVER_ID_FILE\" 2>/dev/null || true)\"\n  [[ \"$id\" =~ ^[A-Za-z0-9_-]{32,64}$ ]] || return 1\n  printf '%s\\n' \"$id\"\n}\n\ncommand_line_for_pid() {\n  local pid=\"$1\"\n  if [[ -r \"/proc/$pid/cmdli",
      "score": 1.692
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js",
      "title": "File: .claude/skills/writing-skills/render-graphs.js",
      "summary": "`.claude/skills/writing-skills/render-graphs.js` is a javascript source file in the Config layer.",
      "snippet": "# .claude/skills/writing-skills/render-graphs.js\n\n## Overview\n\n`.claude/skills/writing-skills/render-graphs.js` is a javascript source file in the Config layer.\n\n## Usage Notes\n\n**Layer:** Config | **",
      "excerpt": "# .claude/skills/writing-skills/render-graphs.js\n\n## Overview\n\n`.claude/skills/writing-skills/render-graphs.js` is a javascript source file in the Config layer.\n\n## Usage Notes\n\n**Layer:** Config | **Role:** entry_point\n\n## In the code\n\nlabel input encoding path child_process ${block.name} ).map(line => + line).join( dot -Tsvg utf-8 Error running dot: --combine Usage: render-graphs.js <skill-directory> [--combine] Options: --combine    Combine all diagrams into one SVG Example: ./render-graphs.js ../subagent-driven-development SKILL.md which dot Error: graphviz (dot) not found. Install with: brew install graphviz    # macOS apt install graphviz     # Linux No ```dot blocks found in diagrams Failed to render combined diagram !/usr/bin/env node Extract digraph name Extract just the body (nodes and edges) from a digraph Remove rankdir (we'll set it once at the top level) Wrap each subgraph in a cluster for visual grouping Check if dot is available Combine all graphs into one Also write the dot source for debugging Render each separately usr bin env node render graphviz from skill svg files usage graphs directory each diagram separately combine all into one extracts dot blocks and renders useful for helping your human partner visualize the process flows requires installed system const require exec sync child function extract markdown regex let match while null content trim digraph name graph length push return body\n\n---\n\n*Built from the code itself: parsed symbols, the import gra",
      "score": 1.664
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на.",
      "score": 1.865
    },
    {
      "file": "shared/bft.py",
      "why_relevant": "БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария..",
      "score": 1.792
    },
    {
      "file": "worker/activities.py",
      "why_relevant": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`..",
      "score": 1.714
    }
  ],
  "code_rationale": [
    {
      "path": "worker/activities.py",
      "lines": [
        1015,
        1025
      ],
      "comment": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом. Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно. `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам. Положить файл в каталог прогона и надеяться — ровно то, что провалилось на первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов не увидела и артефакта не создала.",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        1447,
        1449
      ],
      "comment": "Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога, затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам.",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        3197,
        3202
      ],
      "comment": "Одна стадия канонического пайплайна БФТ — отдельный `claude -p`. Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной активностью весь пайплайн был бы одним баром в Event History на десятки минут, и застрявшая стадия не называла бы себя.",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    },
    {
      "path": "shared/bft.py",
      "lines": [
        81,
        86
      ],
      "comment": "--- Стадии глубокого прогона --- Канонический пайплайн bft-writer, разложенный по стадиям: каждая — свой `claude -p` и свой шаг Event History со своим таймингом. Одной активностью на весь пайплайн он был бы чёрным ящиком на десятки минут — ровно тем, от чего ушла цепочка FNR (#26).",
      "matched_terms": [
        "claude",
        "fnr"
      ]
    },
    {
      "path": "shared/bft.py",
      "lines": [
        661,
        672
      ],
      "comment": "--- Журнал прямых вызовов: слепая зона трекера --- Диалог стадий пишет entire — но только там, где есть АГЕНТ: он цепляется хуками за сессию Claude Code. Стадия, переведённая на прямые вызовы модели (`BFT_DIRECT_STAGES`), сессии не имеет, и для трекера её работы не существует. Журнал закрывает ровно эту дыру: что делал прямой вызов, сколько заходов понадобилось и чем кончилось. Стадии агента сюда не пишут — дублировать чекпоинты значит вести две записи одного и того же и обе поддерживать. Промпты целиком не кладутся: у стадии системная часть под сто килобайт, и в ветке она стала бы мусором, который никто не читает.",
      "matched_terms": [
        "claude",
        "stages"
      ]
    },
    {
      "path": "shared/bft.py",
      "lines": [
        705,
        715
      ],
      "comment": "--- Сессия entire: диалог стадий как ветка репозитория --- Артефакты показывают результат, но не путь к нему. entire вешает хуки на `claude -p` и складывает диалог стадий чекпоинтами в git-рефы: получается ветка `entire/<hash>`, которая уезжает в origin рядом с артефактами. По id сессии оборванный прогон поднимается там, где встал, — без внешнего хранилища и без аккаунта, всё внутри репозитория задачи. ⚠️ Границы: entire перехватывает АГЕНТА. Стадия, переведённая на прямые вызовы модели (`BFT_DIRECT_STAGES`), для него невидима — у неё нет сессии Claude Code, которую можно зацепить хуком. Такие стадии видны только по артефактам.",
      "matched_terms": [
        "claude",
        "stages"
      ]
    }
  ],
  "_meta": {
    "timing_ms": 857.3,
    "hint": "No synthesis, and retrieval was weak. Refine the query with search_codebase rather than reading these files in order.",
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "worker/activities.py",
      "lines": "496-2838",
      "defines": "GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101, CommentIntentExtraction:115"
    },
    {
      "path": "shared/bft.py",
      "lines": "65-730",
      "defines": "epic_slug:43, branch:53, epic_dir:57, artefacts_dir:61, statement_path:65, document_path:76"
    },
    {
      "path": ".claude/skills/brainstorming/scripts/stop-server.sh",
      "defines": "mark_stopped:20, read_expected_server_id:26, command_line_for_pid:34, command_has_server_id:43, is_brainstorm_server:65"
    },
    {
      "path": ".claude/skills/writing-skills/render-graphs.js",
      "defines": "extractDotBlocks:20, extractGraphBody:38, combineGraphs:51, renderToSvg:70, main:84"
    },
    {
      "path": "scripts/demo_e2e.py",
      "defines": "gh:61, issue_state:68, wait_for:98, sentry_errors:114, main:156, STAGES:34"
    }
  ]
}

## Ход 2 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_bft_direct_draft"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_bft_direct_draft",
  "file": "worker/activities.py",
  "name": "_bft_direct_draft",
  "kind": "function",
  "qualified_name": "worker.activities._bft_direct_draft",
  "signature": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str",
  "language": "python",
  "start_line": 3052,
  "end_line": 3138,
  "symbol_start_line": 3052,
  "symbol_end_line": 3138,
  "source": "  3052\tdef _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:\n  3053\t    \"\"\"Стадия `draft` двумя вызовами модели вместо агента.\n  3054\t\n  3055\t    Первый вызов собирает каскад требований и якоря структурой, второй рендерит\n  3056\t    из них документ. Между ними — программная проверка полноты и якорей: ради\n  3057\t    неё разбиение и сделано, одним ответом проверять нечего.\n  3058\t    \"\"\"\n  3059\t    model = os.environ.get(\"BFT_DIRECT_MODEL\", \"glm-4.6\")\n  3060\t    sources = _bft_sources(clone_dir)\n  3061\t    line_counts = {rel: len(body.splitlines()) for rel, body in sources.items()}\n  3062\t    inputs = _bft_stage_inputs(clone_dir, req.issue_number, sources)\n  3063\t    issue = req.issue_number\n  3064\t\n  3065\t    system = _bft_stage_system(\n  3066\t        \"draft\", \"СЕЙЧАС ты собираешь ТОЛЬКО каскад требований и таблицу якорей. \"\n  3067\t                 \"Документ не пишешь — его соберёт следующий шаг.\")\n  3068\t    cascade_task = (\n  3069\t        f\"{inputs}\\n\\n---\\n\\n# Задание\\n\\n\"\n  3070\t        f\"Собери каскад требований БФТ для эпика issue-{issue} и таблицу якорей.\\n\\n\"\n  3071\t        \"Разворачивай, а не сворачивай: каждый пункт TOBE из problem.md, каждое \"\n  3072\t        \"уточнение постановки, каждая ветка сценария демонстрации, каждый экран \"\n  3073\t        \"актора, каждая измеримая характеристика — отдельное требование.\\n\\n\"\n  3074\t        \"Якоря: As-Is-факт → `файл:строки` из исходников выше (ранг R1, тип \"\n  3075\t        \"«Код»); требование постановки → `po-statement.md:N` (R2, «Постановка»); \"\n  3076\t        \"решение концепта → `concept.md` (R2, «Решение»). To-Be на код НЕ \"\n  3077\t        \"якорится.\\n\\n\"\n  3078\t        \"Нижняя граница: \"\n  3079\t        + \", \".join(f\"{k} ≥ {v}\" for k, v in bft.CASCADE_FLOOR.items())\n  3080\t        + f\", якорей ≥ {bft.ANCHOR_FLOOR}.\\n\\n\"\n  3081\t        f\"Верни ТОЛЬКО JSON по схеме:\\n{bft.CASCADE_SCHEMA}\")\n  3082\t\n  3083\t    started = time.monotonic()\n  3084\t    cascade = bft.parse_cascade(llm.complete(system, cascade_task, model=model))\n  3085\t    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n  3086\t        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"каскад требований\",\n  3087\t        outcome=\"готово\", elapsed=time.monotonic() - started,\n  3088\t        detail=f\"требований {len(cascade.get('requirements') or [])}, \"\n  3089\t               f\"якорей {len(cascade.get('anchors') or [])}\"))\n  3090\t    for _ in range(BFT_TOP_UP_ATTEMPTS):\n  3091\t        gaps = bft.cascade_gaps(cascade, line_counts)\n  3092\t        if not gaps:\n  3093\t            break\n  3094\t        logger.info(\"БФТ %s#%s: добор каскада — %s\", req.repo, issue, \"; \".join(gaps))\n  3095\t        _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n  3096\t            stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"добор каскада\",\n  3097\t            outcome=\"добор\", detail=\"; \".join(gaps)))\n  3098\t        top_up = (f\"{inputs}\\n\\n---\\n\\n# Уже собрано\\n\\n```json\\n\"\n  3099\t                  + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n  3100\t                  \"# Чего не хватает\\n\\n- \" + \"\\n- \".join(gaps) + \"\\n\\n\"\n  3101\t                  \"Верни ПОЛНЫЙ JSON той же схемы: собранное дословно плюс \"\n  3102\t                  \"недостающее. Ничего не удаляй и не переформулируй.\")\n  3103\t        cascade = bft.parse_cascade(llm.complete(system, top_up, model=model))\n  3104\t\n  3105\t    left = bft.cascade_gaps(cascade, line_counts)\n  3106\t    if left:\n  3107\t        # Не падаем: неполный каскад — это плохой документ, а не сорванный\n  3108\t        # прогон, и человеку полезнее увидеть его с честной пометкой в логе,\n  3109\t        # чем не увидеть ничего. Полнота проверяется стадией `validate`.\n  3110\t        logger.warning(\"БФТ %s#%s: каскад неполон после добора — %s\",\n  3111\t                       req.repo, issue, \"; \".join(left))\n  3112\t\n  3113\t    system2 = _bft_stage_system(\n  3114\t        \"draft\", \"СЕЙЧАС ты рендеришь документ из УТВЕРЖДЁННОГО каскада. \"\n  3115\t                 \"Требования и якоря уже собраны: переносишь их все, ничего не \"\n  3116\t                 \"теряя и не добавляя новых идентификаторов.\")\n  3117\t    render_task = (\n  3118\t        f\"{inputs}\\n\\n---\\n\\n# Утверждённый каскад\\n\\n```json\\n\"\n  3119\t        + json.dumps(cascade, ensure_ascii=False, indent=1) + \"\\n```\\n\\n\"\n  3120\t        f\"# Задание\\n\\nСобери чистовик БФТ issue-{issue} по корп-шаблону. Все \"\n  3121\t        \"требования каскада обязаны попасть в свои разделы, все якоря — в раздел \"\n  3122\t        \"«Якоря истины» таблицей `Факт | Источник | Ранг | Тип`.\\n\\n\"\n  3123\t        \"Файловых инструментов нет: ты не записываешь файл, а выводишь его \"\n  3124\t        \"содержимое целиком.\\n\\n\"\n  3125\t        f\"YAML-шапка ровно такая:\\n```\\n---\\nEpic: issue-{issue}\\n\"\n  3126\t        \"Название: <название>\\nСтатус: Черновик\\nДата: <сегодня>\\n\"\n  3127\t        \"Автор: bft-draft\\nВерсия: 1.0\\n---\\n```\\n\\n\"\n  3128\t        \"Заголовки разделов — только `##`. Ответ начинается со строки `---` и \"\n  3129\t        \"заканчивается последней строкой таблицы якорей, без обрамляющих \"\n  3130\t        \"```-блоков и без фраз до или после.\")\n  3131\t\n  3132\t    started = time.monotonic()\n  3133\t    document = llm.complete(system2, render_task, model=model)\n  3134\t    _append_dialog(clone_dir, issue, bft.render_dialog_entry(\n  3135\t        stage=\"draft\", actor=f\"прямой вызов ({model})\", step=\"рендер документа\",\n  3136\t        outcome=\"готово\", elapsed=time.monotonic() - started,\n  3137\t        detail=f\"{len(document)} символов\"))\n  3138\t    return document",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 728.5,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "live_head": "993d8561f100",
    "index_behind": true,
    "stale_warning": "A file this response serves changed after indexing — verify against source or run `repowise update`.",
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}

## Ход 3 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_bft_sources"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_bft_sources",
  "file": "worker/activities.py",
  "name": "_bft_sources",
  "kind": "function",
  "qualified_name": "worker.activities._bft_sources",
  "signature": "def _bft_sources(clone_dir: str) -> dict[str, str]",
  "language": "python",
  "start_line": 2850,
  "end_line": 2862,
  "symbol_start_line": 2850,
  "symbol_end_line": 2862,
  "source": "  2850\tdef _bft_sources(clone_dir: str) -> dict[str, str]:\n  2851\t    \"\"\"Файлы репозитория для якорей R1 — путь → содержимое.\"\"\"\n  2852\t    root = Path(clone_dir)\n  2853\t    out: dict[str, str] = {}\n  2854\t    for pattern in BFT_SOURCE_GLOBS:\n  2855\t        for path in sorted(root.glob(pattern)):\n  2856\t            if not path.is_file() or path.stat().st_size > BFT_SOURCE_LIMIT_BYTES:\n  2857\t                continue\n  2858\t            rel = path.relative_to(root).as_posix()\n  2859\t            if rel.startswith(\".bft/\"):\n  2860\t                continue  # артефакты пайплайна подаются отдельно, это не исходники\n  2861\t            out[rel] = path.read_text(encoding=\"utf-8\", errors=\"replace\")\n  2862\t    return out",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 191.9,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "live_head": "993d8561f100",
    "index_behind": true,
    "stale_warning": "A file this response serves changed after indexing — verify against source or run `repowise update`.",
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::_bft_stage_inputs"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::_bft_stage_inputs",
  "file": "worker/activities.py",
  "name": "_bft_stage_inputs",
  "kind": "function",
  "qualified_name": "worker.activities._bft_stage_inputs",
  "signature": "def _bft_stage_inputs(clone_dir: str, issue_number: int,\n                      sources: dict[str, str]) -> str",
  "language": "python",
  "start_line": 2892,
  "end_line": 2909,
  "symbol_start_line": 2892,
  "symbol_end_line": 2909,
  "source": "  2892\tdef _bft_stage_inputs(clone_dir: str, issue_number: int,\n  2893\t                      sources: dict[str, str]) -> str:\n  2894\t    \"\"\"Вход стадии: артефакты предшественников плюс исходники с номерами строк.\n  2895\t\n  2896\t    Список шире, чем `requires` в `deep_stages`: там записан лишь артефакт, без\n  2897\t    которого стадию нельзя начинать, а работает она по всем. Агент дочитывал\n  2898\t    остальное сам — прямому вызову эту зависимость надо назвать (#78, находка D).\n  2899\t    \"\"\"\n  2900\t    root = Path(clone_dir)\n  2901\t    parts = []\n  2902\t    for name in (\"po-statement.md\", \"bft-context-pack.md\", \"problem.md\", \"concept.md\"):\n  2903\t        path = root / bft.artefacts_dir(issue_number) / name\n  2904\t        if path.exists():\n  2905\t            parts.append(f\"# Вход: {name}\\n\\n{path.read_text(encoding='utf-8')}\")\n  2906\t    for rel, body in sources.items():\n  2907\t        parts.append(f\"# Исходник: {rel} (с номерами строк)\\n\\n\"\n  2908\t                     f\"```\\n{_numbered(body)}\\n```\")\n  2909\t    return \"\\n\\n---\\n\\n\".join(parts)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.5,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::BFT_SOURCE_GLOBS"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::BFT_SOURCE_GLOBS",
  "file": "worker/activities.py",
  "name": "BFT_SOURCE_GLOBS",
  "kind": "constant",
  "qualified_name": "worker.activities.BFT_SOURCE_GLOBS",
  "signature": "BFT_SOURCE_GLOBS = (\"src/*\", \"*.md\", \"package.json\")",
  "language": "python",
  "start_line": 2846,
  "end_line": 2846,
  "symbol_start_line": 2846,
  "symbol_end_line": 2846,
  "source": "  2846\tBFT_SOURCE_GLOBS = (\"src/*\", \"*.md\", \"package.json\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 28.88,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}

## Ход 6 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "shared/bft.py::CASCADE_FLOOR"
}
```

**Ответ:**

{
  "symbol_id": "shared/bft.py::CASCADE_FLOOR",
  "file": "shared/bft.py",
  "name": "CASCADE_FLOOR",
  "kind": "constant",
  "qualified_name": "shared.bft.CASCADE_FLOOR",
  "signature": "CASCADE_FLOOR: dict[str, int] = {\"БТ\": 4, \"ПТ\": 5, \"ИТ\": 6, \"ФТ\": 10, \"НФТ\": 4}",
  "language": "python",
  "start_line": 358,
  "end_line": 358,
  "symbol_start_line": 358,
  "symbol_end_line": 358,
  "source": "   358\tCASCADE_FLOOR: dict[str, int] = {\"БТ\": 4, \"ПТ\": 5, \"ИТ\": 6, \"ФТ\": 10, \"НФТ\": 4}",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.22,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 7592
  }
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "_bft_direct_ function implementation"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: worker.activities.run_bft_stage",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.run_bft_stage\n\n**Kind:** function (async) | **Defined in:** `worker/activities.py` | **Estimated complexity:** 13\n\n```\nasync def run_bft_stage(req: BftRequest, stage_name: str) ->",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::run_bft_stage",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.Taxonomy",
      "page_type": "symbol_spotlight",
      "snippet": "s/test_awaiting_wiring.py`\n- `tests/test_backfill.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `t",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::Taxonomy",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.ClusterSet",
      "page_type": "symbol_spotlight",
      "snippet": "s/test_awaiting_wiring.py`\n- `tests/test_backfill.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `t",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClusterSet",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_bft_direct_draft",
      "name": "_bft_direct_draft",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 3052,
      "end_line": 3138,
      "signature": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str",
      "qualified_name": "worker.activities._bft_direct_draft",
      "language": "python",
      "score": 60.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_direct_stage.py::_full_cascade",
      "name": "_full_cascade",
      "kind": "function",
      "file": "tests/test_bft_direct_stage.py",
      "start_line": 58,
      "end_line": 69,
      "signature": "def _full_cascade(**over)",
      "qualified_name": "tests.test_bft_direct_stage._full_cascade",
      "language": "python",
      "score": 55.08,
      "next": "get_symbol"
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
      "path": "worker/activities.py"
    },
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "tests/test_bft_direct_stage.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches '_bft_direct_'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "_bft_direct_problem _bft_direct_concept _bft_direct_debate _bft_direct_validate"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::BFT",
      "name": "BFT",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 24,
      "end_line": 24,
      "signature": "BFT = \"bft\"",
      "qualified_name": "shared.commands.BFT",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/decomposition.py::validate",
      "name": "validate",
      "kind": "function",
      "file": "shared/decomposition.py",
      "start_line": 74,
      "end_line": 107,
      "signature": "def validate(items: list[dict]) -> list[dict]",
      "qualified_name": "shared.decomposition.validate",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_bft_direct_draft",
      "name": "_bft_direct_draft",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 3052,
      "end_line": 3138,
      "signature": "def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str",
      "qualified_name": "worker.activities._bft_direct_draft",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/bft.py::direct_stages",
      "name": "direct_stages",
      "kind": "function",
      "file": "shared/bft.py",
      "start_line": 383,
      "end_line": 391,
      "signature": "def direct_stages() -> set[str]",
      "qualified_name": "shared.bft.direct_stages",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/bft.py::validate_formal_gates",
      "name": "validate_formal_gates",
      "kind": "function",
      "file": "shared/bft.py",
      "start_line": 532,
      "end_line": 589,
      "signature": "def validate_formal_gates(document_content: str, epic_slug: str) -> list[str]",
      "qualified_name": "shared.bft.validate_formal_gates",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
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
      "path": "shared/commands.py"
    },
    {
      "path": "shared/decomposition.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "shared/bft.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches '_bft_direct_problem', '_bft_direct_concept', '_bft_direct_debate'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}
