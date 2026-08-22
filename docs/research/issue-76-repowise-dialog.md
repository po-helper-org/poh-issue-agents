---
session: rw-openhands-po-helper-org__poh-issue-agents-76
workspace: contour
turns: 12
started: 2026-08-22T20:32:37Z
finished: 2026-08-22T20:39:25Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 50 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 50 мин |
| `poh-helper` | `18512c1e7ce9` | 50 мин |
| `poh-infra` | `a1db4f02f10c` | 50 мин |
| `poh-issue-agents` | `993d8561f100` | 50 мин |
| `poh-memory-engine` | `194e39319b3f` | 50 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 50 мин |
| `poh-scheduller` | `04cc3f47aff9` | 50 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 50 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 2 сут |

# Диалог

## Ход 1 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "How does the current post_comment implementation work in worker/github_client.py and worker/activities.py? What are the existing ack → publication patterns mentioned in the task?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `post_comment`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/github_client.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/github_client.py",
    "worker/activities.py",
    "worker/worker.py",
    "worker/activities.py::prefilter_bot_and_security",
    "worker/activities.py::interpret_user_comment"
  ],
  "retrieval": [
    {
      "path": "worker/github_client.py",
      "title": "File: worker/github_client.py",
      "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час).",
      "snippet": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется",
      "excerpt": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\nIt exposes 28 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `add_label` | function | def add_label(repo: str, issue_number: int, label: str) -> None |\n| `remove_label` | function | def remove_label(repo: str, issue_number: int, label: str) -> None |\n| `set_labels` | function | def set_labels(repo: str, issue_number: int, *, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None |\n| `ensure_labels_exist` | function | def ensure_labels_exist(repo: str, specs) -> int |\n| `create_issue` | function | def create_issue(repo: str, title: str, body: str, labels: list[str] \\| None = None) -> int |\n| `close_issue` | function | def close_issue(repo: str, issue_number: int) -> None |\n| `search_candidates` | function | def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict] |\n| `branch_exists` | function | def branch_exists(repo: str, branch: str) -> bool |\n| `auth_token` | function | def auth_token(repo: str) -> str |\n| `add_reaction` | function | def add_reaction(repo: str, comment_id: int, content: str = \"",
      "score": 4.149,
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
          "name": "_dry_run",
          "kind": "function",
          "signature": "def _dry_run() -> bool:",
          "docstring": "",
          "start_line": 26,
          "end_line": 27
        },
        {
          "name": "_token_cache",
          "kind": "variable",
          "signature": "_token_cache: dict[str, tuple[str, float]] = {}",
          "docstring": "",
          "start_line": 34,
          "end_line": 34
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
          "name": "post_comment",
          "kind": "function",
          "signature": "def post_comment(repo: str, issue_number: int, body: str) -> None:",
          "docstring": "Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).",
          "start_line": 130,
          "end_line": 144,
          "source_excerpt": "def post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    if _dry_run():\n        _log.info(\"[DRY_RUN] comment %s#%s: %s\", repo, issue_number, body[:200])\n        return\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/comments\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"body\": body}, timeout=30)\n    resp.raise_for_status()"
        },
        {
          "name": "_post_labels",
          "kind": "function",
          "signature": "def _post_labels(repo: str, issue_number: int, labels: list[str]) -> None:",
          "docstring": "",
          "start_line": 147,
          "end_line": 150,
          "source_excerpt": "def _post_labels(repo: str, issue_number: int, labels: list[str]) -> None:\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/labels\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"labels\": labels}, timeout=30)\n    resp.raise_for_status()"
        },
        {
          "name": "ensure_labels_exist",
          "kind": "function",
          "signature": "def ensure_labels_exist(repo: str, specs) -> int:",
          "docstring": "Заводит недостающие метки. Возвращает число созданных.\n\n    Трекеры создают метку сами при первом применении — и GitHub, и GitLab\n    (проверено 2026-08-21). Проблема не в отказе, а в тишине: опечатка в имени\n    оседает новой меткой вместо ошибки, и выборка тихо перестаёт находить то,\n    что искала. Явное заведение делает набор конечным и заодно даёт цвета.\n\n    Идемпотентна: существующая метка не трогается, цвет ей не переписывается —\n    человек мог поправить его руками, и спорить с ним незачем.",
          "start_line": 226,
          "end_line": 266,
          "source_excerpt": "def ensure_labels_exist(repo: str, specs) -> int:\n    \"\"\"Заводит недостающие метки. Возвращает число созданных.\n\n    Трекеры создают метку сами при первом применении — и GitHub, и GitLab\n    (проверено 2026-08-21). Проблема не в отказе, а в тишине: опечатка в имени\n    оседает новой меткой вместо ошибки, и выборка тихо перестаёт находить то,\n    что искала. Явное заведение делает набор конечным и заодно даёт цвета.\n\n    Идемпотентна: существующая метка не трогается, цвет ей не переписывается —\n    человек мог поправить его руками, и спорить с ним незачем.\n    \"\"\"\n    if _dry_run():\n        _log.info(\"[DRY_RUN] ensure labels %s: %s\", repo, [s.name for s in specs])\n        return 0\n    url = f\"https://api.github.com/repos/{repo}/labels\"\n    existing: set[str] = set()\n    page = 1\n    while True:\n        resp = requests.get(url, headers=_auth_headers(repo),\n                            params={\"per_page\": 100, \"page\": page}, timeout=30)\n        resp.raise_for_status()\n        chunk = resp.json()\n        existing.update(item[\"name\"] for item in chunk)\n        if len(chunk) < 100:\n            break\n        page += 1\n\n    created = 0\n    for spec in specs:\n        if spec.name in existing:\n            continue\n        resp = requests.post(url, headers=_auth_headers(repo), timeout=30, json={\n            \"name\": spec.name,\n            \"color\": spec.color.lstrip(\"#\"),\n            \"description\": spec.description,\n        })\n        if resp.status_code == 422:\n            continue  # завелась параллельно — не наша забота\n        resp.raise_for_status()\n        created += 1\n    return created"
        },
        {
          "name": "branch_exists",
          "kind": "function",
          "signature": "def branch_exists(repo: str, branch: str) -> bool:",
          "docstring": "",
          "start_line": 315,
          "end_line": 318
        }
      ]
    },
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 117 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) ->",
      "score": 2.904,
      "key_symbols": [
        {
          "name": "post_clarifying_question",
          "kind": "function",
          "signature": "def post_clarifying_question(issue: IssueInput, questions: str) -> None:",
          "docstring": "",
          "start_line": 182,
          "end_line": 184,
          "source_excerpt": "def post_clarifying_question(issue: IssueInput, questions: str) -> None:\n    github_client.post_comment(issue.repo, issue.issue_number, questions)\n    github_client.add_label(issue.repo, issue.issue_number, labels.NEEDS_CLARIFICATION)"
        },
        {
          "name": "post_agents_off_notice",
          "kind": "function",
          "signature": "def post_agents_off_notice(repo: str, issue_number: int, what: str) -> None:",
          "docstring": "Короткий ответ на явную команду человека при поднятом рубильнике.\n\n    Молча проигнорировать нельзя: команду набрал человек и ждёт результата, а\n    тишина неотличима от поломки. Комментарий бюджета не стоит — правило R4\n    защищает от вызовов LLM, а не от одной строки в треде.",
          "start_line": 397,
          "end_line": 408,
          "source_excerpt": "def post_agents_off_notice(repo: str, issue_number: int, what: str) -> None:\n    \"\"\"Короткий ответ на явную команду человека при поднятом рубильнике.\n\n    Молча проигнорировать нельзя: команду набрал человек и ждёт результата, а\n    тишина неотличима от поломки. Комментарий бюджета не стоит — правило R4\n    защищает от вызовов LLM, а не от одной строки в треде.\n    \"\"\"\n    github_client.post_comment(\n        repo, issue_number,\n        f\"⏸️ На Issue стоит `{labels.AGENTS_OFF}` — `{what}` не запускаю. \"\n        \"Сними метку, если работа агентов снова нужна.\",\n    )"
        },
        {
          "name": "post_error_label",
          "kind": "function",
          "signature": "def post_error_label(issue: IssueInput, reason: str = \"\") -> None:",
          "docstring": "",
          "start_line": 467,
          "end_line": 483
        },
        {
          "name": "post_priority_comment",
          "kind": "function",
          "signature": "def post_priority_comment(issue: IssueInput, priority: PriorityResult, dup: DuplicateResult) -> None:",
          "docstring": "",
          "start_line": 803,
          "end_line": 814
        }
      ]
    },
    {
      "path": "worker/worker.py",
      "title": "File: worker/worker.py",
      "summary": "`worker/worker.py` is a python source file in the Application layer.",
      "snippet": "`worker/worker.py` is a python source file in the Application layer.",
      "excerpt": "# worker/worker.py\n\n## Overview\n\n`worker/worker.py` is a python source file in the Application layer.\n\nIt exposes 2 public symbols and depends on 7 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `DEVELOP_ACTIVITIES` | constant | DEVELOP_ACTIVITIES = [ |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `worker/activities.py`\n- `worker/consolidation_activities.py`\n- `worker/consolidation_workflow.py`\n- `shared/__init__.py`\n- `shared/sentry_setup.py`\n- `shared/temporal_client.py`\n- `worker/workflows.py`\n\n## Used by\n\nImported by 30 files in this repository.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bft_workflow.py`\n- `tests/test_clarify_after_analysis.py`\n- `tests/test_comment_ack.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_is_a_child.py`\n- `tests/test_develop_workflow.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_duplicate_phase_transitions.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_fnr3_workflow.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_loop.py`\n- `tests/test_park_deadline_absolute.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_fix_child.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_research_autostart.py`\n- `tests/test_workflow_analysis.py`\n- `tests/test_workflow_batch.py`\n- `tests/test_workflow_cl",
      "score": 2.904
    },
    {
      "path": "worker/activities.py::prefilter_bot_and_security",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.prefilter_bot_and_security",
      "summary": "Возвращает причину пропуска, если стоит остановиться, иначе None.",
      "snippet": "# worker.activities.prefilter_bot_and_security\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 6\n\n```\ndef prefilter_bot_and_security(issue: IssueInput, origin_",
      "excerpt": "# worker.activities.prefilter_bot_and_security\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 6\n\n```\ndef prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str | None\n```\n\n## Overview\n\nВозвращает причину пропуска, если стоит остановиться, иначе None.\n\n`origin_agent` снимает ТОЛЬКО проверку на бота. Follow-up контура заводит\nагент — под токеном Actions либо под своим App, — и по автору он бот. Но\nпровенанс `origin:agent` означает ровно обратное тому, ради чего фильтр\nзаведён: это не шум от dependabot, а собственный выход контура, которому\nпротокол (R6) предписывает сокращённый триаж, а не пропуск. Без этого\nисключения каждый найденный агентом edge-кейс тихо умирал бы с меткой\n`bot-authored`, и декомпозиция работы не доезжала бы до бэклога.\n\nПроверка на безопасность остаётся: она о содержимом, а не об авторе, и\nрепорт об уязвимости не становится безопаснее оттого, что его завёл агент.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n32 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activit",
      "score": 1.846
    },
    {
      "path": "worker/activities.py::interpret_user_comment",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.interpret_user_comment",
      "summary": "Разбор намерения из реплики человека.",
      "snippet": "# worker.activities.interpret_user_comment\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 9\n\n```\ndef interpret_user_comment(issue: IssueInput, comment_text: s",
      "excerpt": "# worker.activities.interpret_user_comment\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 9\n\n```\ndef interpret_user_comment(issue: IssueInput, comment_text: str, current_phase: str,\n                          classification_label: str | None, awaiting_reason: str | None,\n                          recent_artifacts: dict[str, str] | None = None) -> CommentIntent\n```\n\n## Overview\n\nРазбор намерения из реплики человека.\n\nАнализирует комментарий и определяет, чего хочет человек: продолжить работу,\nпеределать этап, задать вопрос или просто подтвердить получение.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n35 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_re",
      "score": 1.816
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/github_client.py",
      "why_relevant": "Implements function post_comment.",
      "score": 4.149
    },
    {
      "file": "worker/activities.py",
      "why_relevant": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на.",
      "score": 2.904
    },
    {
      "file": "worker/worker.py",
      "why_relevant": "`worker/worker.py` is a python source file in the Application layer..",
      "score": 2.904
    }
  ],
  "code_rationale": [
    {
      "path": "worker/activities.py",
      "lines": [
        1132,
        1138
      ],
      "comment": "Отмена активности (terminate воркфлоу, таймаут) обрывает ожидание, но НЕ поток: `to_thread` не прерывается, docker-прогон доигрывает и кладёт исключение в задачу, которую уже никто не ждёт. asyncio на сборке такой задачи пишет «Task exception was never retrieved» уровнем ERROR — и это уезжает в Sentry как сбой контура (ISSUE-AGENT-C: код 137 у контейнера агента, снятого намеренно). Колбэк забирает исключение, поэтому предупреждения не будет.",
      "matched_terms": [
        "task"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        1794,
        1797
      ],
      "comment": "_DEV_FALLBACK_RULES = f",
      "matched_terms": [
        "ack"
      ]
    },
    {
      "path": "worker/worker.py",
      "lines": [
        135,
        136
      ],
      "comment": "Our workflow code is trusted first-party code; unsandboxed avoids the per-task re-import of heavy modules (instructor/openai/pydantic).",
      "matched_terms": [
        "task"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/github_client.py",
      "name": "post_comment",
      "lines": [
        130,
        144
      ],
      "source": "def post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    if _dry_run():\n        _log.info(\"[DRY_RUN] comment %s#%s: %s\", repo, issue_number, body[:200])\n        return\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/comments\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"body\": body}, timeout=30)\n    resp.raise_for_status()"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the post_comment body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 928.2,
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
      "path": "worker/github_client.py",
      "lines": "23-318",
      "defines": "post_comment:130, GitCommandError:555, add_label:153, remove_label:160, set_labels:179, ensure_labels_exist:226"
    },
    {
      "path": "worker/activities.py",
      "lines": "182-814",
      "defines": "GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101, CommentIntentExtraction:115"
    },
    {
      "path": "worker/worker.py",
      "defines": "main:53, DEVELOP_ACTIVITIES:41"
    },
    {
      "path": "shared/lifecycle.py",
      "defines": "Transition:53, InvalidTransition:267, phase_label:276, phase_from_labels:280, is_terminal:294, allowed:298"
    },
    {
      "path": "scripts/backfill.py",
      "defines": "build_issue_input:42, list_open_issues:55, main:67, TASK_QUEUE:39"
    }
  ]
}

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/activities.py::ack_command",
    "worker/activities.py::ack_bft_command",
    "worker/activities.py::ack_estimate_command",
    "worker/activities.py::publish_analysis",
    "worker/activities.py::run_bft_fast",
    "worker/activities.py::publish_bft_deep",
    "worker/activities.py::post_estimate_comment",
    "worker/activities.py::_dev_announce",
    "worker/activities.py::collect_dev_followups",
    "worker/activities.py::finish_pr_fixing"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/activities.py::ack_command": {
      "target": "worker/activities.py::ack_command",
      "type": "symbol",
      "docs": {
        "name": "ack_command",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.ack_command",
        "signature": "async def ack_command(analyze: AnalyzeInput) -> None",
        "docstring": "Видимое подтверждение приёма команды ДО тяжёлой работы.\n\n    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не\n    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;\n    если комментарий-триггер к этому моменту удалили (404) или сработал\n    rate limit, сбой реакции не должен утопить сам ack.\n\n    Триггер виден по comment_id: он есть у команды в комментарии и пуст у\n    запуска меткой — реагировать там не на что, и подтверждение называет\n    метку, а не команду. Явно переданный `trigger` перекрывает эту догадку:\n    аналитику запускает и цикл по метке `research-me`, и назвать её\n    `run:analyze` значило бы указать человеку на метку, которой он не ставил.",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::ack_bft_command": {
      "target": "worker/activities.py::ack_bft_command",
      "type": "symbol",
      "docs": {
        "name": "ack_bft_command",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.ack_bft_command",
        "signature": "async def ack_bft_command(req: BftRequest) -> None",
        "docstring": "Видимое подтверждение приёма БФТ-команды ДО работы.\n\n    Реакция «глаза» на комментарий-триггер — та же механика, что у `/analyze`, и\n    по той же причине best-effort: комментарий могли удалить, а rate limit никто\n    не отменял, и декорация не должна ронять приём команды.\n\n    Комментарий пишется только для глубокого прогона и запуска меткой: быстрый\n    проход по команде отвечает письмом через считанные секунды, и «взял в работу»\n    прямо перед ним было бы шумом.\n\n    Метку `run:*` вешает на себя ТОЛЬКО глубокий прогон. Метка возвращается\n    вебхуком как событие `issues.labeled`, то есть как новая команда, — и на\n    многоминутном прогоне это безобидно (второй старт упирается в занятый id),\n    а на быстром, длящемся секунды, эхо успело бы прилететь уже после\n    завершения и запустить второй прогон с дублирующим комментарием. Для\n    быстрого прохода подтверждением служит реакция на комментарий-триггер.",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::ack_estimate_command": {
      "target": "worker/activities.py::ack_estimate_command",
      "type": "symbol",
      "docs": {
        "name": "ack_estimate_command",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.ack_estimate_command",
        "signature": "def ack_estimate_command(req: EstimateRequest) -> None",
        "docstring": "Подтверждение приёма. У команды в комментарии это реакция на него; у\n    запуска меткой реагировать не на что, поэтому подтверждением служит сама\n    метка `run:estimate` плюс короткий комментарий — иначе с телефона не видно,\n    что метка вообще доехала.",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::publish_analysis": {
      "target": "worker/activities.py::publish_analysis",
      "type": "symbol",
      "docs": {
        "name": "publish_analysis",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.publish_analysis",
        "signature": "async def publish_analysis(analyze: AnalyzeInput) -> str",
        "docstring": "Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::run_bft_fast": {
      "target": "worker/activities.py::run_bft_fast",
      "type": "symbol",
      "docs": {
        "name": "run_bft_fast",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.run_bft_fast",
        "signature": "async def run_bft_fast(req: BftRequest) -> str",
        "docstring": "Быстрый проход: письмо БФТ комментарием в Issue.\n\n    Один вызов модели, без клона и без claude-code: формат `/bft-fast` — это\n    структурирование уже сказанного, а не исследование кода. Клонировать\n    репозиторий ради него значило бы платить минутами за то, что нужно секундами.\n\n    Возвращает опубликованный текст — он же уходит в историю Temporal, поэтому\n    разбор «что именно агент отписал» не требует лезть в GitHub.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::publish_bft_deep": {
      "target": "worker/activities.py::publish_bft_deep",
      "type": "symbol",
      "docs": {
        "name": "publish_bft_deep",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.publish_bft_deep",
        "signature": "async def publish_bft_deep(req: BftRequest) -> str",
        "docstring": "Финал глубокого прогона: артефакты в ветку, сводка комментарием.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::post_estimate_comment": {
      "target": "worker/activities.py::post_estimate_comment",
      "type": "symbol",
      "docs": {
        "name": "post_estimate_comment",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.post_estimate_comment",
        "signature": "def post_estimate_comment(req: EstimateRequest, result: EstimateResult) -> None",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::_dev_announce": {
      "target": "worker/activities.py::_dev_announce",
      "type": "symbol",
      "docs": {
        "name": "_dev_announce",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities._dev_announce",
        "signature": "async def _dev_announce(issue: IssueInput, branch: str, *, where: str) -> None",
        "docstring": "Метка и комментарий о начале работы — best-effort и ОДИН раз на задачу.\n\n    Прогон к этому моменту начался; падать из-за непоставленной метки значило\n    бы отправить в `failed` задачу, которая на самом деле в работе.\n\n    Повторный вход в передачу (перезапуск активности, второе решение человека)\n    не должен давать второго объявления: на живом прогоне #39 их набралось три\n    штуки подряд, и по треду нельзя было понять, идёт одна работа или три.\n    Признак — метка `in-development`: её ставит эта же функция строкой ниже, и\n    снимает смена фазы (`set_phase`), то есть она держится ровно столько,\n    сколько длится передача.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::collect_dev_followups": {
      "target": "worker/activities.py::collect_dev_followups",
      "type": "symbol",
      "docs": {
        "name": "collect_dev_followups",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.collect_dev_followups",
        "signature": "async def collect_dev_followups(issue: IssueInput) -> list[int]",
        "docstring": "Edge-кейсы агента разработки — в бэклог, руками воркера.\n\n    Агент оставляет находки файлом: `gh` и GITHUB_TOKEN ему не дают, и это не\n    упущение, а весь смысл его изоляции — он исполняет чужой код. Issue по\n    находкам заводит воркер, у которого токен уже есть.\n\n    Best-effort по каждой находке: прогон разработки состоялся, и невзятая\n    находка не должна отменять остальные, а тем более ронять шаг целиком. Зато\n    файл снимается всегда — даже если ни один Issue не удалось завести, в PR он\n    не уедет.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    },
    "worker/activities.py::finish_pr_fixing": {
      "target": "worker/activities.py::finish_pr_fixing",
      "type": "symbol",
      "docs": {
        "name": "finish_pr_fixing",
        "kind": "function",
        "file_path": "worker/activities.py",
        "qualified_name": "worker.activities.finish_pr_fixing",
        "signature": "async def finish_pr_fixing(repo: str, pr_number: int, rounds: int, settled: bool, verdict: str = \"\") -> None",
        "docstring": "Итог доведения: либо PR готов, либо он уходит человеку.",
        "file_summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
        "used_by": [
          "tests/test_estimate_activities.py",
          "worker/worker.py",
          "worker/workflows.py",
          "tests/test_activities_analyze.py",
          "tests/test_activities_error.py",
          "tests/test_agent_comment.py",
          "tests/test_analysis_pipeline.py",
          "tests/test_bft_activities.py",
          "tests/test_bft_direct_stage.py",
          "tests/test_bft_entire_session.py",
          "tests/test_bft_partial_resume.py",
          "tests/test_build_task_context.py",
          "tests/test_command_label_activities.py",
          "tests/test_comment_ack.py",
          "tests/test_dev_handoff_once.py",
          "tests/test_develop.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_child.py",
          "tests/test_develop_followups.py",
          "tests/test_duplicate_exit_with_existing_labels.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 22,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 22
    }
  },
  "_meta": {
    "timing_ms": 132.5,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "9d60243d670b"
      ],
      "tokens": 132,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {},
  "omission_marker": "[repowise#9d60243d670b: 9 lines omitted (~132 tokens); restore: repowise expand 9d60243d670b]"
}

## Ход 3 · `get_symbol` · contour

**Запрос:**

```json
{
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
  "start_line": 2495,
  "end_line": 2527,
  "symbol_start_line": 2495,
  "symbol_end_line": 2527,
  "source": "  2495\tasync def ack_command(analyze: AnalyzeInput) -> None:\n  2496\t    \"\"\"Видимое подтверждение приёма команды ДО тяжёлой работы.\n  2497\t\n  2498\t    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не\n  2499\t    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;\n  2500\t    если комментарий-триггер к этому моменту удалили (404) или сработал\n  2501\t    rate limit, сбой реакции не должен утопить сам ack.\n  2502\t\n  2503\t    Триггер виден по comment_id: он есть у команды в комментарии и пуст у\n  2504\t    запуска меткой — реагировать там не на что, и подтверждение называет\n  2505\t    метку, а не команду. Явно переданный `trigger` перекрывает эту догадку:\n  2506\t    аналитику запускает и цикл по метке `research-me`, и назвать её\n  2507\t    `run:analyze` значило бы указать человеку на метку, которой он не ставил.\n  2508\t    \"\"\"\n  2509\t    trigger = (f\"`{analyze.trigger}`\" if analyze.trigger\n  2510\t               else f\"`{run_label(ANALYZE)}`\" if analyze.comment_id is None\n  2511\t               else \"`/analyze`\")\n  2512\t    await asyncio.to_thread(\n  2513\t        github_client.post_comment,\n  2514\t        analyze.repo,\n  2515\t        analyze.issue_number,\n  2516\t        f\"🔍 Взял {trigger} в работу — запускаю автономный анализ через SA-helper.\\n\\n\"\n  2517\t        \"Прогон занимает несколько минут: артефакты появятся в ветке \"\n  2518\t        f\"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.\",\n  2519\t    )\n  2520\t    await asyncio.to_thread(\n  2521\t        github_client.add_label, analyze.repo, analyze.issue_number, run_label(ANALYZE)\n  2522\t    )\n  2523\t    if analyze.comment_id is not None:\n  2524\t        try:\n  2525\t            await asyncio.to_thread(github_client.add_reaction, analyze.repo, analyze.comment_id, \"eyes\")\n  2526\t        except Exception:\n  2527\t            pass  # best-effort: декорация не должна ронять ack или весь прогон",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.66,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
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
  "start_line": 1509,
  "end_line": 1526,
  "symbol_start_line": 1509,
  "symbol_end_line": 1526,
  "source": "  1509\tasync def publish_analysis(analyze: AnalyzeInput) -> str:\n  1510\t    \"\"\"Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n  1511\t    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.\"\"\"\n  1512\t    clone_dir = _require_workspace(analyze, None)\n  1513\t    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)\n  1514\t    if not files:\n  1515\t        raise RuntimeError(\"пайплайн не произвёл ни одного артефакта\")\n  1516\t    branch = f\"research/issue-{analyze.issue_number}\"\n  1517\t    await asyncio.to_thread(\n  1518\t        github_client.push_artifacts_to_branch,\n  1519\t        analyze.repo, branch, files,\n  1520\t        f\"docs(sa): анализ issue #{analyze.issue_number} через SA-helper\",\n  1521\t    )\n  1522\t    await asyncio.to_thread(\n  1523\t        github_client.post_comment,\n  1524\t        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),\n  1525\t    )\n  1526\t    return branch",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 13.87,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}

## Ход 5 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/workflows.py::IssueLifecycle",
    "shared/lifecycle.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "worker/workflows.py::IssueLifecycle": {
      "target": "worker/workflows.py::IssueLifecycle",
      "type": "symbol",
      "docs": {
        "name": "IssueLifecycle",
        "kind": "class",
        "file_path": "worker/workflows.py",
        "qualified_name": "worker.workflows.IssueLifecycle",
        "signature": "class IssueLifecycle",
        "file_summary": "IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>, это даёт идемпотентность бесплатно: повторный issues.opened webhook не создаст вторую сущность).",
        "used_by": [
          "worker/worker.py",
          "tests/test_agent_event_workflow.py",
          "tests/test_agents_as_children.py",
          "tests/test_awaiting_wiring.py",
          "tests/test_bft_workflow.py",
          "tests/test_clarify_after_analysis.py",
          "tests/test_comment_ack.py",
          "tests/test_develop_autostart.py",
          "tests/test_develop_is_a_child.py",
          "tests/test_develop_workflow.py",
          "tests/test_duplicate_exit_with_existing_labels.py",
          "tests/test_duplicate_phase_transitions.py",
          "tests/test_e2e_issue_lifecycle.py",
          "tests/test_followup_dialog.py",
          "tests/test_lifecycle_loop.py",
          "tests/test_lifecycle_phases.py",
          "tests/test_park_deadline_absolute.py",
          "tests/test_park_deadlines.py",
          "tests/test_pr_fix_child.py",
          "tests/test_ready_for_dev.py"
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 18,
        "last_fix_days_ago": 1,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "episodes": 18
    },
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
        "summary": "Модель фаз жизненного цикла Issue — единственный источник правды.",
        "symbols": [
          {
            "name": "CREATED",
            "kind": "constant",
            "signature": "CREATED = \"created\"",
            "line": 22,
            "symbol_id": "shared/lifecycle.py::CREATED"
          },
          {
            "name": "CLASSIFIED",
            "kind": "constant",
            "signature": "CLASSIFIED = \"classified\"",
            "line": 23,
            "symbol_id": "shared/lifecycle.py::CLASSIFIED"
          },
          {
            "name": "BUSINESS_ANALYSIS",
            "kind": "constant",
            "signature": "BUSINESS_ANALYSIS = \"business-analysis\"",
            "line": 24,
            "symbol_id": "shared/lifecycle.py::BUSINESS_ANALYSIS"
          },
          {
            "name": "SYSTEM_REQUIREMENTS",
            "kind": "constant",
            "signature": "SYSTEM_REQUIREMENTS = \"system-requirements\"",
            "line": 25,
            "symbol_id": "shared/lifecycle.py::SYSTEM_REQUIREMENTS"
          },
          {
            "name": "GROOMED",
            "kind": "constant",
            "signature": "GROOMED = \"groomed\"",
            "line": 26,
            "symbol_id": "shared/lifecycle.py::GROOMED"
          },
          {
            "name": "READY_FOR_DEV",
            "kind": "constant",
            "signature": "READY_FOR_DEV = \"ready-for-dev\"",
            "line": 27,
            "symbol_id": "shared/lifecycle.py::READY_FOR_DEV"
          },
          {
            "name": "IN_DEVELOPMENT",
            "kind": "constant",
            "signature": "IN_DEVELOPMENT = \"in-development\"",
            "line": 28,
            "symbol_id": "shared/lifecycle.py::IN_DEVELOPMENT"
          },
          {
            "name": "PR_OPEN",
            "kind": "constant",
            "signature": "PR_OPEN = \"pr-open\"",
            "line": 29,
            "symbol_id": "shared/lifecycle.py::PR_OPEN"
          },
          {
            "name": "PR_REVIEW",
            "kind": "constant",
            "signature": "PR_REVIEW = \"pr-review\"",
            "line": 30,
            "symbol_id": "shared/lifecycle.py::PR_REVIEW"
          },
          {
            "name": "MERGED",
            "kind": "constant",
            "signature": "MERGED = \"merged\"",
            "line": 31,
            "symbol_id": "shared/lifecycle.py::MERGED"
          },
          {
            "name": "TESTING",
            "kind": "constant",
            "signature": "TESTING = \"testing\"",
            "line": 32,
            "symbol_id": "shared/lifecycle.py::TESTING"
          },
          {
            "name": "RELEASED",
            "kind": "constant",
            "signature": "RELEASED = \"released\"",
            "line": 33,
            "symbol_id": "shared/lifecycle.py::RELEASED"
          },
          {
            "name": "SPAM",
            "kind": "constant",
            "signature": "SPAM = \"spam\"",
            "line": 37,
            "symbol_id": "shared/lifecycle.py::SPAM"
          },
          {
            "name": "DUPLICATE",
            "kind": "constant",
            "signature": "DUPLICATE = \"duplicate\"",
            "line": 38,
            "symbol_id": "shared/lifecycle.py::DUPLICATE"
          },
          {
            "name": "ANSWERED",
            "kind": "constant",
            "signature": "ANSWERED = \"answered\"",
            "line": 39,
            "symbol_id": "shared/lifecycle.py::ANSWERED"
          },
          {
            "name": "SKIPPED",
            "kind": "constant",
            "signature": "SKIPPED = \"skipped\"",
            "line": 40,
            "symbol_id": "shared/lifecycle.py::SKIPPED"
          },
          {
            "name": "ESCALATED",
            "kind": "constant",
            "signature": "ESCALATED = \"escalated\"",
            "line": 41,
            "symbol_id": "shared/lifecycle.py::ESCALATED"
          },
          {
            "name": "FAILED",
            "kind": "constant",
            "signature": "FAILED = \"failed\"",
            "line": 42,
            "symbol_id": "shared/lifecycle.py::FAILED"
          },
          {
            "name": "CANCELLED",
            "kind": "constant",
            "signature": "CANCELLED = \"cancelled\"",
            "line": 43,
            "symbol_id": "shared/lifecycle.py::CANCELLED"
          },
          {
            "name": "AGENT",
            "kind": "constant",
            "signature": "AGENT = \"agent\"",
            "line": 47,
            "symbol_id": "shared/lifecycle.py::AGENT"
          },
          {
            "name": "HUMAN",
            "kind": "constant",
            "signature": "HUMAN = \"human\"",
            "line": 48,
            "symbol_id": "shared/lifecycle.py::HUMAN"
          },
          {
            "name": "EXTERNAL",
            "kind": "constant",
            "signature": "EXTERNAL = \"external\"",
            "line": 49,
            "symbol_id": "shared/lifecycle.py::EXTERNAL"
          },
          {
            "name": "Transition",
            "kind": "class",
            "signature": "class Transition",
            "line": 53,
            "symbol_id": "shared/lifecycle.py::Transition"
          },
          {
            "name": "TERMINAL",
            "kind": "constant",
            "signature": "TERMINAL = frozenset({RELEASED, CANCELLED})",
            "line": 62,
            "symbol_id": "shared/lifecycle.py::TERMINAL"
          },
          {
            "name": "TRANSITIONS",
            "kind": "constant",
            "signature": "TRANSITIONS: dict[str, tuple[Transition, ...]] = {",
            "line": 70,
            "symbol_id": "shared/lifecycle.py::TRANSITIONS"
          },
          {
            "name": "PHASES",
            "kind": "constant",
            "signature": "PHASES: tuple[str, ...] = tuple(TRANSITIONS)",
            "line": 226,
            "symbol_id": "shared/lifecycle.py::PHASES"
          },
          {
            "name": "PHASE_PREFIX",
            "kind": "constant",
            "signature": "PHASE_PREFIX = \"phase:\"",
            "line": 231,
            "symbol_id": "shared/lifecycle.py::PHASE_PREFIX"
          },
          {
            "name": "STAGE_TO_PHASE",
            "kind": "constant",
            "signature": "STAGE_TO_PHASE: dict[str, str] = {",
            "line": 236,
            "symbol_id": "shared/lifecycle.py::STAGE_TO_PHASE"
          },
          {
            "name": "InvalidTransition",
            "kind": "class",
            "signature": "class InvalidTransition",
            "line": 267,
            "symbol_id": "shared/lifecycle.py::InvalidTransition"
          },
          {
            "name": "phase_label",
            "kind": "function",
            "signature": "def phase_label(phase: str) -> str",
            "line": 276,
            "symbol_id": "shared/lifecycle.py::phase_label"
          },
          {
            "name": "phase_from_labels",
            "kind": "function",
            "signature": "def phase_from_labels(labels: list[str]) -> str | None",
            "line": 280,
            "symbol_id": "shared/lifecycle.py::phase_from_labels"
          },
          {
            "name": "is_terminal",
            "kind": "function",
            "signature": "def is_terminal(phase: str) -> bool",
            "line": 294,
            "symbol_id": "shared/lifecycle.py::is_terminal"
          },
          {
            "name": "allowed",
            "kind": "function",
            "signature": "def allowed(phase: str) -> tuple[Transition, ...]",
            "line": 298,
            "symbol_id": "shared/lifecycle.py::allowed"
          },
          {
            "name": "can",
            "kind": "function",
            "signature": "def can(source: str, target: str) -> bool",
            "line": 305,
            "symbol_id": "shared/lifecycle.py::can"
          },
          {
            "name": "transition",
            "kind": "function",
            "signature": "def transition(source: str, target: str) -> Transition",
            "line": 309,
            "symbol_id": "shared/lifecycle.py::transition"
          },
          {
            "name": "initiator",
            "kind": "function",
            "signature": "def initiator(source: str, target: str) -> str",
            "line": 320,
            "symbol_id": "shared/lifecycle.py::initiator"
          },
          {
            "name": "reachable_from",
            "kind": "function",
            "signature": "def reachable_from(start: str = CREATED) -> set[str]",
            "line": 324,
            "symbol_id": "shared/lifecycle.py::reachable_from"
          }
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 3,
        "last_fix_days_ago": 1
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "episodes": 3,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-infra",
            "file": "docs/harness/README.md",
            "strength": 0.664
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 59.7,
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
  "symbol_id": "worker/workflows.py::IssueLifecycle",
  "depth": 2
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle",
  "file": "worker/workflows.py",
  "name": "IssueLifecycle",
  "kind": "class",
  "qualified_name": "worker.workflows.IssueLifecycle",
  "signature": "class IssueLifecycle",
  "language": "python",
  "start_line": 353,
  "end_line": 952,
  "symbol_start_line": 353,
  "symbol_end_line": 2267,
  "source": "   353\tclass IssueLifecycle:\n   354\t    def __init__(self) -> None:\n   355\t        # Очередь несёт и решения человека (строки), и факты внешних агентов\n   356\t        # (AgentEvent). Один поток вместо двух — иначе фаза, ждущая решения, не\n   357\t        # проснулась бы на событии, и наоборот.\n   358\t        self._signal_queue: asyncio.Queue[str | AgentEvent | UserComment] = asyncio.Queue()\n   359\t        self._analyze_labeled = False\n   360\t        self._issue: IssueInput | None = None\n   361\t        self._stage = \"intake\"\n   362\t        self._phase = lifecycle.CREATED\n   363\t        self._phase_driven = False  # True — прогон идёт фазовым циклом\n   364\t        self._priority_tier = \"\"\n   365\t        self._classification_label: str | None = None\n   366\t        self._analysis_done = False\n   367\t        # Задача — часть чужого плана: подзадача декомпозиции. Ни своей\n   368\t        # декомпозиции, ни своей разработки у неё нет — и то и другое ведёт\n   369\t        # родитель, одним прогоном на весь объём MVP.\n   370\t        self._plan_member = False\n   371\t        # Номер родителя плана. Нужен подзадаче, чтобы сослаться на требования:\n   372\t        # своей ветки анализа у неё нет, и ссылка на `research/issue-<своё>`\n   373\t        # была бы битой.\n   374\t        self._root_issue: int | None = None\n   375\t        # Сколько кругов уточнения ПОСЛЕ аналитики уже потрачено. Потолок нужен\n   376\t        # затем же, что и на входе: вопрос, на который не отвечают, не должен\n   377\t        # держать задачу вечно.\n   378\t        self._clarify_rounds = 0\n   379\t        # Сколько реплик человека уже отвечено содержательно и ключи последних\n   380\t        # из них. Ключ нужен из-за повторной доставки вебхука: одно событие\n   381\t        # приезжает сигналом дважды, и без него один вопрос получал бы два\n   382\t        # ответа. Потолок — из `Deadlines`, вместе с остальными тумблерами.\n   383\t        self._followup_rounds = 0\n   384\t        self._answered_comment_ids: list[int] = []\n   385\t        self._followup_max_rounds = Deadlines().followup_max_rounds\n   386\t        # Сколько раз человек вернул этап на пересборку (rework intent).\n   387\t        # Потолок нужен, чтобы пара «переделай» ↔ «переделал» не стояла по\n   388\t        # LLM-прогону за круг без конца.\n   389\t        self._rework_rounds = 0\n   390\t        self._rework_max_rounds = MAX_REWORK_ROUNDS\n   391\t        self._generation = 0\n   392\t        # Момент входа в текущую фазу. Проставляется в run() до первого await;\n   393\t        # None только пока воркфлоу не начал исполняться.\n   394\t        self._phase_since: datetime | None = None\n   395\t        self._analyze_comment_id: int | None = None\n   396\t        self._analyze_pending = False  # запрос на аналитику лежит в очереди\n   397\t        # Прогон аналитики идёт прямо сейчас. Отдельно от `_analyze_pending`:\n   398\t        # тот говорит «запрос в очереди», этот — «работа выполняется». Первый\n   399\t        # прогон запускает метка `research-me` мимо очереди сигналов, и без\n   400\t        # второго флага команда, пришедшая во время такого прогона, вставала\n   401\t        # бы в очередь и заводила второй.\n   402\t        self._analysis_running = False\n   403\t        # Номер PR по этой задаче. Известен из доклада внешнего агента либо от\n   404\t        # локального прогона разработки; нужен фазе доведения.\n   405\t        self._pr_number: int | None = None\n   406\t        # Разбивать ли задачу на подзадачи перед передачей в разработку.\n   407\t        # Значение приезжает активностью вместе со сроками — по той же причине,\n   408\t        # что и остальные тумблеры: оно обязано лежать в истории.\n   409\t        self._decompose = True\n   410\t        # Ключи уже учтённых событий агентов: один факт двигает фазу один раз.\n   411\t        self._seen_agent_events: list[str] = []\n   412\t        # Чего Issue ждёт прямо сейчас. None — работа идёт, ожидания нет.\n   413\t        self._awaiting: Awaiting | None = None\n   414\t        # Стоит ли сейчас метка очереди к людям. Нужен, чтобы не дёргать GitHub\n   415\t        # на каждом переходе: метку трогаем только когда состояние меняется.\n   416\t        self._human_queue_labelled = False\n   417\t        # Кто закрыл Issue на GitHub. None — открыт. Закрытие обрывает любую\n   418\t        # парковку: досиживать срок в закрытом Issue незачем.\n   419\t        self._closed_by: str | None = None\n   420\t\n   421\t    @workflow.query\n   422\t    def stage(self) -> str:\n   423\t        \"\"\"Текущая стадия прогона — для Temporal UI (вкладка Queries).\n   424\t\n   425\t        Прогон, припаркованный в ожидании лейбла, показан просто как `Running`\n   426\t        бессрочно, и отличить «триаж закончен, ждём человека» от «активность\n   427\t        зависла» можно было только разбирая Event History руками. Значение\n   428\t        `awaiting-human-decision` снимает эту двусмысленность прямо в UI.\n   429\t\n   430\t        Чтение атрибута детерминировано и побочных эффектов не имеет, поэтому\n   431\t        на воспроизведение истории query не влияет.\n   432\t        \"\"\"\n   433\t        return self._stage\n   434\t\n   435\t    @workflow.query\n   436\t    def phase(self) -> str:\n   437\t        \"\"\"Фаза жизненного цикла — единый словарь на весь контур (#35).\n   438\t\n   439\t        Фазовый цикл ведёт фазу сам. Прогоны ПРЕЖНЕГО поколения (линейный путь,\n   440\t        выбранный workflow.patched) фазы не знают — для них она выводится из\n   441\t        стадии через мост STAGE_TO_PHASE. Иначе такой прогон вечно показывал бы\n   442\t        `created`, хотя триаж давно прошёл.\n   443\t        \"\"\"\n   444\t        if self._phase_driven:\n   445\t            return self._phase\n   446\t        return lifecycle.STAGE_TO_PHASE.get(self._stage, lifecycle.CREATED)\n   447\t\n   448\t    @workflow.query\n   449\t    def generation(self) -> int:\n   450\t        \"\"\"Сколько раз цикл перезапускался через continue-as-new.\n   451\t\n   452\t        Долгоживущий прогон обязан обрывать историю, иначе реплей перестаёт\n   453\t        укладываться в workflow-task timeout. После перезапуска Event History в\n   454\t        UI начинается с чистого листа — без этого счётчика по одной истории\n   455\t        нельзя понять, это новый Issue или продолжение старого.\n   456\t        \"\"\"\n   457\t        return self._generation\n   458\t\n   459\t    @workflow.query\n   460\t    def awaiting(self) -> Awaiting | None:\n   461\t        \"\"\"Чего Issue ждёт: вид, адресат, с какого момента и до какого срока (#39).\n   462\t\n   463\t        Расширение query `stage`: та отвечает «в какой стадии прогон», эта —\n   464\t        «почему он там стоит и кто его сдвинет». Без неё припаркованный прогон\n   465\t        и зависший выглядят в Temporal UI одинаково.\n   466\t        \"\"\"\n   467\t        return self._awaiting\n   468\t\n   469\t    @workflow.query\n   470\t    def handles_agents(self) -> bool:\n   471\t        \"\"\"Ведёт ли этот прогон агентов дочерними воркфлоу (#37).\n   472\t\n   473\t        Спрашивает `shared/agent_launcher.py`, чтобы выбрать режим запуска.\n   474\t        Прогоны прежнего поколения (линейный путь) сигнала на запуск агента не\n   475\t        понимают — команда была бы принята и потеряна; для них лаунчер стартует\n   476\t        root-прогон, как раньше. Отдельного флага нет намеренно: цикл и\n   477\t        дочерние агенты приехали одним поколением, и разводить их двумя\n   478\t        независимыми признаками значило бы завести четыре состояния там, где\n   479\t        существуют два.\n   480\t        \"\"\"\n   481\t        return self._phase_driven\n   482\t\n   483\t    @workflow.signal\n   484\t    async def human_decision(self, label: str) -> None:\n   485\t        await self._signal_queue.put(label)\n   486\t\n   487\t    @workflow.signal\n   488\t    async def user_comment(self, text: str, comment_id: int | None = None) -> None:\n   489\t        \"\"\"Реплика человека в Issue.\n   490\t\n   491\t        Второй аргумент со значением по умолчанию, а не новый сигнал: вебхук\n   492\t        прежнего поколения шлёт один аргумент, и прогоны, припаркованные до\n   493\t        этой правки, обязаны понимать обе формы.\n   494\t        \"\"\"\n   495\t        await self._signal_queue.put(UserComment(text=text, comment_id=comment_id))\n   496\t\n   497\t    @workflow.signal\n   498\t    async def issue_closed(self, who: str | None = None) -> None:\n   499\t        \"\"\"Issue закрыт на GitHub — цикл обязан завершиться.\n   500\t\n   501\t        Парковка со сроком (R3) гарантирует, что цикл не живёт вечно, но\n   502\t        закрытый Issue ждать нечего: в проде так набралось 22 прогона по уже\n   503\t        закрытым Issue, каждый досиживал свою парковку (до 168 ч) и продолжал\n   504\t        занимать место в выборке Running.\n   505\t\n   506\t        Флаг, а не переход прямо здесь: хендлер сигнала выполняется вне цикла\n   507\t        фаз, и смена фазы отсюда гонялась бы с обработчиком текущей фазы.\n   508\t        Значение в очереди будит парковку, решение принимает `_run_phase_loop`.\n   509\t        \"\"\"\n   510\t        self._closed_by = who or \"human\"\n   511\t        await self._signal_queue.put(CLOSED)\n   512\t\n   513\t    @workflow.signal\n   514\t    async def analyze_requested(self, comment_id: int | None) -> None:\n   515\t        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n   516\t\n   517\t        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а\n   518\t        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).\n   519\t        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу\n   520\t        из вебхука — связь между циклом Issue и работой агента была\n   521\t        декоративной, о чём и говорил прежний докстринг.\n   522\t\n   523\t        Тяжёлую работу из самого хендлера не запускаем: run() обычно\n   524\t        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с\n   525\t        основным циклом за фазу. Очередь снимает гонку — решение принимает та\n   526\t        фаза, в которой Issue находится сейчас.\n   527\t\n   528\t        Сигнал может прийти в самой первой активации воркфлоу — раньше, чем\n   529\t        run() выполнил `self._issue = issue` (Temporal применяет сигналы до\n   530\t        создания задачи run()); поэтому ЖДЁМ инициализацию через\n   531\t        wait_condition, а не теряем запрос молча по `self._issue is None`.\n   532\t        \"\"\"\n   533\t        # Тот же маркер, что разводит поколения в run(): цикл и дочерние\n   534\t        # агенты приехали вместе, и прогон, не знающий одного, не знает и\n   535\t        # другого. Прежнее поколение обязано доиграть ПРЕЖНИМ кодом хендлера —\n   536\t        # иначе реплей его истории упрётся в несовпадение команд.\n   537\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   538\t            if self._analyze_labeled:\n   539\t                return\n   540\t            self._analyze_labeled = True\n   541\t            await workflow.wait_condition(lambda: self._issue is not None)\n   542\t            await workflow.execute_activity(\n   543\t                activities.mark_analyzing,\n   544\t                args=[self._issue.repo, self._issue.issue_number],\n   545\t                start_to_close_timeout=timedelta(seconds=30),\n   546\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   547\t            )\n   548\t            return\n   549\t\n   550\t        # Запрос уже в очереди — второй прогон был бы шумом и деньгами:\n   551\t        # повторная команда и дубль webhook-доставки означают одно намерение.\n   552\t        # Флаг ставим ДО первого await: хендлеры кооперативны (переключение\n   553\t        # только на await), поэтому почти одновременный второй сигнал увидит\n   554\t        # True. Идентификатор занятого прогона от этой гонки не спасает: к\n   555\t        # моменту второго сигнала первый может уже завершиться, и id\n   556\t        # освободится — а это законный повторный запуск, не дубль.\n   557\t        # Идущий прогон — тоже причина отказать. Пока он идёт, `ack_command`\n   558\t        # вешает на Issue метку `run:analyze`; вебхук видит `issues.labeled` и\n   559\t        # шлёт команду обратно в цикл. Своя метка возвращается как новая\n   560\t        # команда, и на живом стенде это давало три прогона подряд по одному\n   561\t        # Issue. Идентификатор занятого прогона от этого не спасает: к моменту\n   562\t        # разбора очереди первый прогон уже завершён, и id свободен.\n   563\t        if self._analyze_pending or self._analysis_running:\n   564\t            return\n   565\t        self._analyze_pending = True\n   566\t        self._analyze_comment_id = comment_id\n   567\t        await workflow.wait_condition(lambda: self._issue is not None)\n   568\t        await self._signal_queue.put(AGENT_ANALYZE)\n   569\t\n   570\t    @workflow.signal\n   571\t    async def agent_event(self, event: AgentEvent) -> None:\n   572\t        \"\"\"Факт от внешнего агента контура: PR открыт, ревью взято, CI упал (#38).\n   573\t\n   574\t        Кладём в общую очередь, а не двигаем фазу прямо здесь. Обработчик\n   575\t        сигнала конкурирует с основным циклом: пока тот, скажем, гонит\n   576\t        аналитику, смена фазы из-под него дала бы состояние, которого нет ни в\n   577\t        одном обработчике. Очередь снимает гонку — событие разбирает та фаза, в\n   578\t        которой Issue находится сейчас.\n   579\t\n   580\t        Идемпотентность по паре `(ref, status)`: доставку соседний сервис может\n   581\t        повторить (ретрай, дубль вебхука), но один факт обязан двигать фазу\n   582\t        один раз. Ключи копятся в состоянии прогона, поэтому храним только\n   583\t        последние: цикл живёт месяцами, а сюда попадает каждое событие по\n   584\t        каждому PR.\n   585\t        \"\"\"\n   586\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   587\t            return  # прежнее поколение фаз не знает — двигать нечего\n   588\t        if isinstance(event, dict):\n   589\t            event = AgentEvent(**event)\n   590\t        if event.key() in self._seen_agent_events:\n   591\t            return\n   592\t        self._seen_agent_events.append(event.key())\n   593\t        del self._seen_agent_events[:-SEEN_EVENTS_KEPT]\n   594\t        await workflow.wait_condition(lambda: self._issue is not None)\n   595\t        await self._signal_queue.put(event)\n   596\t\n   597\t    @workflow.signal\n   598\t    async def bft_requested(self, req: BftRequest) -> None:\n   599\t        \"\"\"По Issue запрошен БФТ — командой `/bft`/`/bft-deep` или меткой `run:*`.\n   600\t\n   601\t        В очередь НЕ кладём, как и оценку: БФТ фазу не двигает. Быстрый проход —\n   602\t        это формулировка запроса, а не стадия пути; глубокий кладёт артефакты в\n   603\t        свою ветку и оставляет фазу честной. Двигать фазу в `business-analysis`\n   604\t        значило бы, что БФТ и цепочка FNR — одна и та же стадия, а это разные\n   605\t        документы с разной судьбой.\n   606\t\n   607\t        Прогон поднимаем прямо здесь и результата не ждём: цикл продолжает ждать\n   608\t        своё. Двойного прогона это не создаёт — id фиксирован в пределах режима.\n   609\t\n   610\t        Прогоны прежнего поколения сигнал получают, но обслужить не могут; им\n   611\t        лаунчер стартует root-прогон (см. query `handles_agents`), поэтому здесь\n   612\t        достаточно молча выйти — иначе на реплее их истории появилась бы команда,\n   613\t        которой там нет.\n   614\t        \"\"\"\n   615\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   616\t            return\n   617\t        if isinstance(req, dict):\n   618\t            req = BftRequest(**req)\n   619\t        await workflow.wait_condition(lambda: self._issue is not None)\n   620\t        await self._start_bft(req)\n   621\t\n   622\t    async def _start_bft(self, req: BftRequest) -> bool:\n   623\t        \"\"\"Прогон БФТ по команде — дочерним воркфлоу, без ожидания результата.\n   624\t\n   625\t        Результата не ждём: фазу БФТ не двигает, и циклу с его исходом делать\n   626\t        нечего. Прогон сам отвечает человеку — письмом, сводкой либо\n   627\t        комментарием о сбое.\n   628\t        \"\"\"\n   629\t        try:\n   630\t            await workflow.start_child_workflow(\n   631\t                IssueBft.run, req,\n   632\t                id=bft_workflow_id(req.repo, req.issue_number, req.mode),\n   633\t                # Глубокий прогон идёт десятками минут. Ни continue-as-new\n   634\t                # родителя, ни его завершение не должны его обрывать.\n   635\t                parent_close_policy=ParentClosePolicy.ABANDON,\n   636\t                # Прогон недетерминирован и стоит денег: повтор инициирует\n   637\t                # человек, а не политика ретраев.\n   638\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   639\t            )\n   640\t        except WorkflowAlreadyStartedError:\n   641\t            # Прогон в этом режиме уже идёт: повторная команда, эхо собственной\n   642\t            # метки или дубль доставки вебхука — все три означают одно намерение.\n   643\t            workflow.logger.info(\"bft %s already running for %s#%s\",\n   644\t                                 req.mode, req.repo, req.issue_number)\n   645\t            return False\n   646\t        return True\n   647\t\n   648\t    @workflow.signal\n   649\t    async def estimate_requested(self, comment_id: int | None) -> None:\n   650\t        \"\"\"По Issue запрошена оценка трудоёмкости.\n   651\t\n   652\t        В очередь НЕ кладём: оценка фазу не двигает — это боковая команда, а не\n   653\t        стадия пути. Поднимаем дочерний прогон прямо здесь и не ждём его\n   654\t        результата: цикл продолжает ждать своё, а оценка идёт параллельно.\n   655\t\n   656\t        Прогоны прежнего поколения этот сигнал получают, но обслужить не могут;\n   657\t        им лаунчер стартует root-прогон (см. query `handles_agents`), поэтому\n   658\t        здесь достаточно молча выйти — иначе на реплее их истории появилась бы\n   659\t        команда, которой там нет.\n   660\t        \"\"\"\n   661\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   662\t            return\n   663\t        await workflow.wait_condition(lambda: self._issue is not None)\n   664\t        req = EstimateRequest(repo=self._issue.repo,\n   665\t                              issue_number=self._issue.issue_number,\n   666\t                              comment_id=comment_id)\n   667\t        try:\n   668\t            await workflow.start_child_workflow(\n   669\t                IssueEstimation.run, req,\n   670\t                id=estimate_workflow_id(req.repo, req.issue_number, comment_id),\n   671\t                # Родитель переживёт continue-as-new и завершение цикла, а\n   672\t                # оценка — нет: ABANDON оставляет её доигрывать саму.\n   673\t                parent_close_policy=ParentClosePolicy.ABANDON,\n   674\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   675\t            )\n   676\t        except WorkflowAlreadyStartedError:\n   677\t            # Тот же вебхук доставлен повторно — оценка уже идёт.\n   678\t            workflow.logger.info(\"estimate already running for %s#%s\",\n   679\t                                 req.repo, req.issue_number)\n   680\t\n   681\t    async def _wait_for_signal(\n   682\t            self, timeout: timedelta | None = None) -> str | AgentEvent | UserComment | None:\n   683\t        # Нулевой остаток означает «срок уже вышел», а не «ждать без ограничения»:\n   684\t        # `if timeout:` ниже принял бы timedelta(0) за отсутствие таймаута и\n   685\t        # припарковал бы Issue навсегда — ровно то, от чего чинили #58.\n   686\t        if timeout is not None and timeout <= timedelta(0):\n   687\t            return None\n   688\t        try:\n   689\t            if timeout:\n   690\t                return await asyncio.wait_for(\n   691\t                    self._signal_queue.get(), timeout=timeout.total_seconds()\n   692\t                )\n   693\t            return await self._signal_queue.get()\n   694\t        except asyncio.TimeoutError:\n   695\t            return None\n   696\t\n   697\t    @workflow.run\n   698\t    async def run(self, issue: IssueInput,\n   699\t                  carried: LifecycleState | None = None) -> None:\n   700\t        \"\"\"Владелец состояния Issue: живёт, пока у Issue есть непросроченное\n   701\t        ожидание, а не заканчивается после приоритизации.\n   702\t\n   703\t        Второй аргумент со значением по умолчанию — ради совместимости: вебхук и\n   704\t        скрипты стартуют воркфлоу одним аргументом, как раньше, а continue-as-new\n   705\t        передаёт снимок состояния вторым.\n   706\t\n   707\t        `workflow.patched` разводит поколения. Прогоны, запущенные до этого\n   708\t        изменения, припаркованы в проде: их история не знает маркера, patched()\n   709\t        вернёт False, и они доиграют по прежнему линейному коду. Новые пойдут\n   710\t        циклом. Без этого реплей старой истории новым кодом упал бы\n   711\t        недетерминизмом — самый дорогой класс отказа в Temporal.\n   712\t        \"\"\"\n   713\t        # Вебхук и скрипты стартуют воркфлоу ОДНИМ аргументом, а сигнатура\n   714\t        # объявляет два. При таком расхождении Temporal не применяет типы ни к\n   715\t        # одному аргументу и отдаёт сырые словари — молча, на первом же\n   716\t        # обращении к полю. Нормализуем сами: ломать существующие стартеры ради\n   717\t        # красоты сигнатуры нельзя, а второй аргумент нужен continue-as-new.\n   718\t        if isinstance(issue, dict):\n   719\t            issue = IssueInput(**issue)\n   720\t        if isinstance(carried, dict):\n   721\t            carried = LifecycleState(**carried)\n   722\t\n   723\t        self._issue = issue  # даёт analyze_requested доступ к repo/number\n   724\t        # Момент входа в фазу. `workflow.now()` детерминирован (время события из\n   725\t        # истории), поэтому реплей даёт то же значение, что и первый прогон.\n   726\t        self._phase_since = workflow.now()\n   727\t        if carried is not None:\n   728\t            self._phase = carried.phase\n   729\t            self._stage = carried.stage\n   730\t            self._priority_tier = carried.priority_tier\n   731\t            self._classification_label = carried.classification_label\n   732\t            self._analysis_done = carried.analysis_done\n   733\t            self._plan_member = carried.plan_member\n   734\t            self._root_issue = carried.root_issue\n   735\t            self._pr_number = carried.pr_number\n   736\t            self._clarify_rounds = carried.clarify_rounds\n   737\t            self._followup_rounds = carried.followup_rounds\n   738\t            self._answered_comment_ids = list(carried.answered_comment_ids)\n   739\t            self._rework_rounds = carried.rework_rounds\n   740\t            self._generation = carried.generation\n   741\t            if carried.phase_since_epoch:\n   742\t                # Перезапуск цикла не должен обнулять срок парковки: иначе\n   743\t                # continue-as-new сам стал бы способом ждать вечно.\n   744\t                self._phase_since = datetime.fromtimestamp(\n   745\t                    carried.phase_since_epoch, tz=timezone.utc)\n   746\t\n   747\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   748\t            await self._run_linear(issue)\n   749\t            return\n   750\t        self._phase_driven = True\n   751\t        await self._run_phase_loop(issue)\n   752\t\n   753\t    # --- Фазовый цикл ---\n   754\t\n   755\t    def _snapshot(self) -> LifecycleState:\n   756\t        \"\"\"Компактное состояние для continue-as-new: фаза и то немногое, что\n   757\t        нужно следующим фазам. Тред и история не переносятся — именно их объём\n   758\t        и упирается в потолок.\"\"\"\n   759\t        return LifecycleState(\n   760\t            phase=self._phase,\n   761\t            stage=self._stage,\n   762\t            priority_tier=self._priority_tier,\n   763\t            classification_label=self._classification_label,\n   764\t            analysis_done=self._analysis_done,\n   765\t            plan_member=self._plan_member,\n   766\t            root_issue=self._root_issue,\n   767\t            pr_number=self._pr_number,\n   768\t            clarify_rounds=self._clarify_rounds,\n   769\t            followup_rounds=self._followup_rounds,\n   770\t            answered_comment_ids=list(self._answered_comment_ids),\n   771\t            rework_rounds=self._rework_rounds,\n   772\t            generation=self._generation + 1,\n   773\t            phase_since_epoch=self._phase_since.timestamp() if self._phase_since else 0.0,\n   774\t        )\n   775\t\n   776\t    def _history_is_long(self) -> bool:\n   777\t        \"\"\"Порог по длине истории, а не по числу итераций: цена реплея зависит\n   778\t        от событий, а одна фаза может стоить и трёх событий, и трёхсот.\"\"\"\n   779\t        return workflow.info().get_current_history_length() >= HISTORY_EVENT_THRESHOLD\n   780\t\n   781\t    async def _park(self, kind: str, who: str, reason: str, hours: int) -> timedelta:\n   782\t        \"\"\"Встать в ожидание: описать его и вернуть срок таймера.\n   783\t\n   784\t        Одно место на все точки парковки. Разнесённые «поставить таймер» и\n   785\t        «записать, чего ждём» разошлись бы при первой же правке одной из них —\n   786\t        и получилось бы ожидание с таймером, но без причины, то есть ровно то,\n   787\t        что чинит #39.\n   788\t        \"\"\"\n   789\t        since = self._phase_since or workflow.now()\n   790\t        self._awaiting = Awaiting(\n   791\t            kind=kind, who=who, reason=reason,\n   792\t            since_epoch=since.timestamp(),\n   793\t            deadline_epoch=(since + timedelta(hours=hours)).timestamp(),\n   794\t        )\n   795\t        await self._publish_awaiting()\n   796\t        return self._park_timeout(hours)\n   797\t\n   798\t    async def _publish_awaiting(self) -> None:\n   799\t        \"\"\"Отражение ожидания в GitHub: очередь к людям должна быть полной.\n   800\t\n   801\t        Метку вешаем только на ожидание ЧЕЛОВЕКА: задача, ждущая стенд или\n   802\t        соседний сервис, в очереди к людям — шум, из-за которого перестают\n   803\t        смотреть на саму выборку.\n   804\t\n   805\t        Под patched: у идущих прогонов этой команды в истории нет.\n   806\t        \"\"\"\n   807\t        if not workflow.patched(\"issue-lifecycle-awaiting\") or self._issue is None:\n   808\t            return\n   809\t        want = self._awaiting is not None and self._awaiting.blocks_on_human\n   810\t        if want == self._human_queue_labelled:\n   811\t            # Состояние метки не изменилось. Без этой проверки каждый переход\n   812\t            # фазы давал бы пару «снять/поставить»: лишние вызовы GitHub и\n   813\t            # мигание метки в таймлайне Issue.\n   814\t            return\n   815\t        self._human_queue_labelled = want\n   816\t        await workflow.execute_activity(\n   817\t            activities.mark_awaiting,\n   818\t            args=[self._issue.repo, self._issue.issue_number, self._awaiting],\n   819\t            start_to_close_timeout=timedelta(seconds=60),\n   820\t            retry_policy=RetryPolicy(maximum_attempts=3),\n   821\t        )\n   822\t\n   823\t    async def _stop_awaiting(self) -> None:\n   824\t        \"\"\"Ожидание снято: описание очищается, метка уходит.\"\"\"\n   825\t        if self._awaiting is None:\n   826\t            return\n   827\t        self._awaiting = None\n   828\t        await self._publish_awaiting()\n   829\t\n   830\t    def _park_timeout(self, hours: int) -> timedelta:\n   831\t        \"\"\"Сколько ещё ждать в этой фазе — остаток от срока, а не полный срок.\n   832\t\n   833\t        Обработчик фазы вызывается в цикле: посторонний сигнал (чужая метка,\n   834\t        комментарий) фазу не двигает, но возвращает управление наверх. Пока\n   835\t        таймер заводился на полный срок, каждый такой сигнал начинал отсчёт\n   836\t        заново — дедлайн получался «N часов с последнего шороха», и Issue,\n   837\t        которому раз в трое суток что-то прилетает, не эскалировался никогда.\n   838\t        Правило R3 требует обратного: срок отсчитывается от входа в фазу.\n   839\t\n   840\t        `workflow.patched` обязателен: у припаркованных прогонов таймер уже\n   841\t        записан в историю, и другая длительность на реплее — недетерминизм.\n   842\t        \"\"\"\n   843\t        if not workflow.patched(\"issue-lifecycle-absolute-park-deadline\"):\n   844\t            return timedelta(hours=hours)\n   845\t        if self._phase_since is None:\n   846\t            return timedelta(hours=hours)\n   847\t        left = self._phase_since + timedelta(hours=hours) - workflow.now()\n   848\t        return left if left > timedelta(0) else timedelta(0)\n   849\t\n   850\t    async def _phase_on_close(self) -> tuple[str, str]:\n   851\t        \"\"\"Чем закончился путь Issue: слиянием или снятием с обработки.\n   852\t\n   853\t        Спрашиваем сам PR, а не того, кто закрыл Issue: закрыть его по `Closes`\n   854\t        может и бот, и человек, а `state_reason` у закрытия «как выполненное»\n   855\t        одинаков в обоих случаях. Номер PR у цикла уже есть — он запомнил его,\n   856\t        когда PR открылся.\n   857\t\n   858\t        Вопрос задаём, только если ответ может что-то изменить: PR нет либо из\n   859\t        текущей фазы в `merged` хода нет — значит, это отмена, и лишний вызов\n   860\t        GitHub на каждом закрытии не нужен.\n   861\t        \"\"\"\n   862\t        if (self._issue is None or not self._pr_number\n   863\t                or not lifecycle.can(self._phase, lifecycle.MERGED)):\n   864\t            return (lifecycle.CANCELLED, \"cancelled\")\n   865\t        merged = await workflow.execute_activity(\n   866\t            activities.pr_is_merged,\n   867\t            args=[self._issue.repo, self._pr_number],\n   868\t            start_to_close_timeout=timedelta(seconds=30),\n   869\t            retry_policy=RetryPolicy(maximum_attempts=3),\n   870\t        )\n   871\t        if merged:\n   872\t            return (lifecycle.MERGED, \"merged\")\n   873\t        return (lifecycle.CANCELLED, \"cancelled\")\n   874\t\n   875\t    async def _enter(self, phase: str, stage: str, *, write_label: bool = True) -> None:\n   876\t        \"\"\"Переход в фазу: проверка допустимости, стадия, метка.\n   877\t\n   878\t        Недопустимый переход поднимает InvalidTransition и роняет прогон — это\n   879\t        осознанно. Молчаливая перезапись фазы означала бы Issue в состоянии, из\n   880\t        которого не выводится ни предыстория, ни следующий шаг; такую ошибку\n   881\t        лучше увидеть в тестах и в Temporal UI, чем годами не замечать.\n   882\t        \"\"\"\n   883\t        if phase == self._phase:\n   884\t            # Остаться в своей фазе, не дождавшись нужного сигнала, — штатное\n   885\t            # поведение парковки, а не смена состояния: ни проверять переход,\n   886\t            # ни переписывать метку не нужно.\n   887\t            self._stage = stage\n   888\t            return\n   889\t        lifecycle.transition(self._phase, phase)\n   890\t        self._phase = phase\n   891\t        self._stage = stage\n   892\t        # Прежнее ожидание закрыто самим фактом перехода. Метку обычно не\n   893\t        # трогаем: следующая точка парковки опишет новое ожидание и приведёт\n   894\t        # метку в порядок одним вызовом — снимать и ставить её на каждом\n   895\t        # переходе значило бы мигать ею в таймлайне Issue.\n   896\t        self._awaiting = None\n   897\t        # Исключение — фазы, в которых цикл работает и не паркуется вовсе: там\n   898\t        # следующего вызова просто не будет, и метка очереди к людям осталась бы\n   899\t        # висеть на задаче, которую ведёт агент.\n   900\t        if (workflow.patched(\"issue-lifecycle-clear-queue-on-work\")\n   901\t                and phase in awaiting_mod.WORKED_BY_AGENT):\n   902\t            await self._publish_awaiting()\n   903\t        # Отсчёт срока парковки начинается здесь и только здесь.\n   904\t        self._phase_since = workflow.now()\n   905\t        if write_label and self._issue is not None:\n   906\t            await workflow.execute_activity(\n   907\t                activities.set_phase,\n   908\t                args=[self._issue.repo, self._issue.issue_number, phase],\n   909\t                start_to_close_timeout=timedelta(seconds=60),\n   910\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   911\t            )\n   912\t\n   913\t    async def _run_analysis_child(self, issue: IssueInput,\n   914\t                                  trigger: str | None = None) -> bool:\n   915\t        \"\"\"Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.\n   916\t\n   917\t        Один код на оба режима (#37): в Temporal UI прогон виден как child\n   918\t        цикла, а id остаётся прежним (`analysis-<repo>-<n>`), поэтому повторная\n   919\t        команда по-прежнему упирается в `WorkflowAlreadyStarted`, а не тратит\n   920\t        деньги второй раз.\n   921\t        \"\"\"\n   922\t        analyze = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,\n   923\t                               title=issue.title, body=issue.body,\n   924\t                               comment_id=self._analyze_comment_id,\n   925\t                               trigger=trigger)\n   926\t        # Запрос израсходован — но снимается он ПОСЛЕ прогона, а не до.\n   927\t        #\n   928\t        # Пока прогон идёт, `ack_command` вешает на Issue метку `run:analyze`.\n   929\t        # Вебхук видит `issues.labeled` и шлёт `analyze_requested` обратно в\n   930\t        # цикл: наша собственная метка возвращается как новая команда. Со\n   931\t        # снятым флагом она вставала в очередь, и по завершении прогона цикл\n   932\t        # запускал второй — на живом стенде это дало три прогона аналитики\n   933\t        # подряд по одному Issue. Идентификатор занятого прогона от этого не\n   934\t        # спасает: к моменту обработки очереди первый уже завершён, и id\n   935\t        # свободен.\n   936\t        #\n   937\t        # Команда, пришедшая ВО ВРЕМЯ прогона, — эхо своей метки либо повторный\n   938\t        # клик человека. Ни то, ни другое не стоит второго дорогого прогона.\n   939\t        self._analysis_running = True\n   940\t        try:\n   941\t            return await workflow.execute_child_workflow(\n   942\t                IssueAnalysis.run, analyze,\n   943\t                id=analysis_workflow_id(issue.repo, issue.issue_number),\n   944\t                # Цепочка FNR идёт до 4500 с. Ни continue-as-new родителя, ни\n   945\t                # его завершение не должны её убивать — иначе дорогой прогон\n   946\t                # обрывается на середине по причине, к нему не относящейся.\n   947\t                parent_close_policy=ParentClosePolicy.ABANDON,\n   948\t                # Прогон недетерминирован, мутирует файлы и стоит денег:\n   949\t                # повтор инициирует человек, а не политика ретраев.\n   950\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   951\t            )\n   952\t        except WorkflowAlreadyStartedError:",
  "truncated": true,
  "verified": true,
  "_meta": {
    "timing_ms": 12.58,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 32935
  },
  "continuation": "worker/workflows.py:953-2267",
  "note": "Symbol body (353-2267) exceeds the 600-line serve cap; served 353-952. Fetch the remainder in one call: get_symbol('worker/workflows.py:953-2267')."
}

## Ход 7 · `get_symbol` · contour

**Запрос:**

```json
{
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
  "start_line": 111,
  "end_line": 153,
  "symbol_start_line": 111,
  "symbol_end_line": 153,
  "source": "   111\tclass LifecycleState:\n   112\t    \"\"\"Снимок цикла для continue-as-new.\n   113\t\n   114\t    Переносится КОМПАКТНОЕ состояние — фаза, стадия и то немногое, что нужно\n   115\t    следующим фазам, — а не тред и не история. Долгоживущий цикл на активном\n   116\t    Issue иначе упрётся в тот же потолок, который уже словила консолидация:\n   117\t    на ~75 Issue история превышает ~990 событий и реплей не укладывается в\n   118\t    workflow-task timeout.\n   119\t    \"\"\"\n   120\t    phase: str = \"created\"\n   121\t    stage: str = \"intake\"\n   122\t    priority_tier: str = \"\"              # нужен чеклисту готовности (H1)\n   123\t    classification_label: str | None = None  # None — сокращённый триаж (R6)\n   124\t    analysis_done: bool = False\n   125\t    generation: int = 0                  # сколько раз цикл перезапускался\n   126\t    # Момент входа в текущую фазу, epoch-секунды. Дедлайн парковки отсчитывается\n   127\t    # от него, а не от последнего сигнала, — иначе любой посторонний комментарий\n   128\t    # продлевал бы ожидание, и правило R3 переставало бы что-либо гарантировать.\n   129\t    # Переносится через continue-as-new: перезапуск цикла не должен обнулять срок.\n   130\t    phase_since_epoch: float = 0.0\n   131\t    # Задача — часть чужого плана (подзадача декомпозиции). Ни своей\n   132\t    # декомпозиции, ни своей разработки у неё нет: и то и другое ведёт родитель.\n   133\t    plan_member: bool = False\n   134\t    root_issue: int | None = None        # родитель плана, если это подзадача\n   135\t    # Номер PR по задаче. Без него фаза доведения не знает, что доводить, и\n   136\t    # вместо круга правок молча уходит в парковку: PR открыт, ревью прошло,\n   137\t    # замечания не исправляются.\n   138\t    pr_number: int | None = None\n   139\t    # Сколько кругов уточнения после аналитики потрачено: потолок обязан\n   140\t    # переживать перезапуск, иначе continue-as-new обнулял бы его и вопросы\n   141\t    # могли задаваться заново без конца.\n   142\t    clarify_rounds: int = 0\n   143\t    # Сколько реплик человека уже отвечено содержательно и ключи последних из\n   144\t    # них. Переносятся по той же причине, что и `clarify_rounds`: перезапуск\n   145\t    # цикла не должен ни обнулять потолок, ни терять защиту от повторной\n   146\t    # доставки вебхука — иначе первый же continue-as-new отвечает дважды.\n   147\t    followup_rounds: int = 0\n   148\t    answered_comment_ids: list[int] = field(default_factory=list)\n   149\t    # Сколько раз человек вернул этап на пересборку (rework intent).\n   150\t    # Переносится по той же причине, что и `clarify_rounds`: перезапуск\n   151\t    # не должен обнулять потолок, иначе «переделай» ↔ «переделал» будет\n   152\t    # повторяться бесконечно.\n   153\t    rework_rounds: int = 0",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 14.24,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3498
  }
}

## Ход 8 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::IssueAnalysis"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueAnalysis",
  "file": "worker/workflows.py",
  "name": "IssueAnalysis",
  "kind": "class",
  "qualified_name": "worker.workflows.IssueAnalysis",
  "signature": "class IssueAnalysis",
  "language": "python",
  "start_line": 2393,
  "end_line": 2421,
  "symbol_start_line": 2393,
  "symbol_end_line": 2421,
  "source": "  2393\tclass IssueAnalysis:\n  2394\t    \"\"\"Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.\n  2395\t\n  2396\t    Работает в двух режимах (#37): дочерним прогоном `IssueLifecycle`, когда\n  2397\t    цикл жив, и самостоятельным — при автономном запуске (скрипт, прогон\n  2398\t    прежнего поколения). Код один и тот же; отличается только родитель.\n  2399\t\n  2400\t    Фиксированный id `analysis-<repo>-<n>` даёт идемпотентность в обоих\n  2401\t    режимах: повторный `/analyze` упрётся в WorkflowAlreadyStarted, а не\n  2402\t    запустит второй дорогой прогон.\n  2403\t    \"\"\"\n  2404\t\n  2405\t    @workflow.run\n  2406\t    async def run(self, analyze: AnalyzeInput) -> bool:\n  2407\t        \"\"\"Возвращает, опубликованы ли артефакты.\n  2408\t\n  2409\t        Родителю этот ответ нужен, чтобы решить, можно ли передавать задачу\n  2410\t        разработчику: без аналитики передавать нечего. Автономный запуск\n  2411\t        результат просто игнорирует.\n  2412\t        \"\"\"\n  2413\t        if await _agents_off(analyze.repo, analyze.issue_number, \"/analyze\"):\n  2414\t            return False\n  2415\t        await workflow.execute_activity(\n  2416\t            activities.ack_command,\n  2417\t            analyze,\n  2418\t            start_to_close_timeout=timedelta(seconds=60),\n  2419\t            retry_policy=RetryPolicy(maximum_attempts=3),\n  2420\t        )\n  2421\t        return await _run_staged_analysis(analyze)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 13.71,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 32935
  }
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "def _run_staged_analysis"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::_run_staged_analysis",
      "name": "_run_staged_analysis",
      "kind": "function",
      "file": "worker/workflows.py",
      "start_line": 150,
      "end_line": 243,
      "signature": "async def _run_staged_analysis(analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows._run_staged_analysis",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2406,
      "end_line": 2421,
      "signature": "async def run(self, analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows.IssueAnalysis.run",
      "language": "python",
      "score": 60.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueEstimation::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2587,
      "end_line": 2643,
      "signature": "async def run(self, req: EstimateRequest) -> None",
      "qualified_name": "worker.workflows.IssueEstimation.run",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "title": "How It Works",
      "page_type": "onboarding",
      "snippet": "s.py::IssueAnalysis::run`\n\n\n\n1. `worker/workflows.py::IssueAnalysis::run`\n\n2. `worker/workflows.py::_run_staged_analysis`\n\n3. `worker/workflows.py::_finish_labels`\n\n\n\n\n\n\n## Reading order\n\nThe guided t",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "onboarding/how_it_works",
      "type": "page"
    },
    {
      "title": "Symbol: worker.workflows.IssueAnalysis",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueAnalysis\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueAnalysis\n```\n\n## Overview\n\nАналитика по запросу (Слой C) — воркф",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueAnalysis",
      "file": "worker/workflows.py",
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
      "path": "worker/workflows.py"
    }
  ],
  "exact_match": true
}

## Ход 10 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::_run_staged_analysis"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::_run_staged_analysis",
  "file": "worker/workflows.py",
  "name": "_run_staged_analysis",
  "kind": "function",
  "qualified_name": "worker.workflows._run_staged_analysis",
  "signature": "async def _run_staged_analysis(analyze: AnalyzeInput) -> bool",
  "language": "python",
  "start_line": 150,
  "end_line": 243,
  "symbol_start_line": 150,
  "symbol_end_line": 243,
  "source": "   150\tasync def _run_staged_analysis(analyze: AnalyzeInput) -> bool:\n   151\t    \"\"\"Пер-стадийный прогон FNR — общий для обоих входов в аналитику.\n   152\t\n   153\t    Один код на команду `/analyze` (IssueAnalysis) и на лейбл research-me внутри\n   154\t    IssueLifecycle. Раньше вторая ветка звала монолитную activity\n   155\t    run_analysis_pipeline: те же пять стадий, но одним чёрным ящиком — застрявшая\n   156\t    стадия не называла себя, а прогон по лейблу и прогон по команде расходились\n   157\t    в поведении, оставаясь «одной и той же аналитикой» на словах.\n   158\t\n   159\t    Каждая стадия — свой шаг Event History со своим таймингом; ретраев нет\n   160\t    (прогон недетерминирован, мутирует файлы и стоит денег — повтор инициирует\n   161\t    человек), сбой всегда доезжает до GitHub, каталог снимается на обоих путях.\n   162\t\n   163\t    Возвращает True, если артефакты опубликованы: от этого зависит, можно ли\n   164\t    передавать задачу разработчику — без аналитики передавать нечего.\n   165\t    \"\"\"\n   166\t    ok = True\n   167\t    try:\n   168\t        await workflow.execute_activity(\n   169\t            activities.prepare_workspace,\n   170\t            analyze,\n   171\t            start_to_close_timeout=timedelta(seconds=1000),  # clone 300 + repomix 600 + буфер\n   172\t            heartbeat_timeout=timedelta(seconds=300),\n   173\t            retry_policy=RetryPolicy(maximum_attempts=2),\n   174\t        )\n   175\t        for stage_name in activities.FNR_STAGE_NAMES:\n   176\t            await workflow.execute_activity(\n   177\t                activities.run_fnr_stage,\n   178\t                args=[analyze, stage_name],\n   179\t                start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер\n   180\t                heartbeat_timeout=timedelta(seconds=300),\n   181\t                # Сбой самой стадии не повторяется: прогон недетерминирован,\n   182\t                # мутирует файлы и стоит денег — повтор инициирует человек. Но\n   183\t                # heartbeat timeout не её сбой: воркер перезапустили (выкладкой,\n   184\t                # рестартом Docker), активность оборвалась, и ничего произведено\n   185\t                # не было. Без второй попытки любая выкладка посреди прогона\n   186\t                # убивала анализ целиком — так встал Issue #11 на стенде.\n   187\t                #\n   188\t                # Граница по типу: всё, что стадия поднимает сама, — RuntimeError.\n   189\t                # Таймауты и потеря воркера в этот тип не попадают.\n   190\t                retry_policy=RetryPolicy(\n   191\t                    maximum_attempts=2,\n   192\t                    non_retryable_error_types=[\"RuntimeError\"],\n   193\t                ),\n   194\t            )\n   195\t        await workflow.execute_activity(\n   196\t            activities.publish_analysis,\n   197\t            analyze,\n   198\t            start_to_close_timeout=timedelta(seconds=120),\n   199\t            retry_policy=RetryPolicy(maximum_attempts=3),\n   200\t        )\n   201\t        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=True)\n   202\t    except Exception as exc:\n   203\t        ok = False\n   204\t        # exc — ActivityError с общим текстом; настоящая причина в exc.cause\n   205\t        # (например, «стадия concept: артефакт ... не создан»). Разворачиваем.\n   206\t        reason = str(getattr(exc, \"cause\", None) or exc)\n   207\t        # Сначала спасаем сделанное, потом сообщаем о сбое: `cleanup` в\n   208\t        # `finally` снимет каталог, и после него публиковать будет нечего.\n   209\t        saved = []\n   210\t        try:\n   211\t            saved = await workflow.execute_activity(\n   212\t                activities.publish_analysis_partial,\n   213\t                args=[analyze, reason[:300]],\n   214\t                start_to_close_timeout=timedelta(seconds=300),\n   215\t                retry_policy=RetryPolicy(maximum_attempts=2),\n   216\t            )\n   217\t        except Exception as partial_exc:\n   218\t            workflow.logger.warning(\n   219\t                \"публикация частичного анализа не удалась: %s\", partial_exc)\n   220\t        if not saved:\n   221\t            await workflow.execute_activity(\n   222\t                activities.publish_analysis_error,\n   223\t                args=[analyze, reason[:500]],\n   224\t                start_to_close_timeout=timedelta(seconds=60),\n   225\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   226\t            )\n   227\t        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=False)\n   228\t    finally:\n   229\t        # Каталог живёт вне Temporal — снимаем его на обоих путях. Best-effort:\n   230\t        # провал самой уборки (timeout/краш воркера) не должен затирать реальный\n   231\t        # исход — ловим и логируем, но наружу не пробрасываем.\n   232\t        try:\n   233\t            await workflow.execute_activity(\n   234\t                activities.cleanup_workspace,\n   235\t                analyze,\n   236\t                start_to_close_timeout=timedelta(seconds=60),\n   237\t                retry_policy=RetryPolicy(maximum_attempts=1),\n   238\t            )\n   239\t        except Exception as cleanup_exc:\n   240\t            workflow.logger.warning(\n   241\t                \"cleanup_workspace failed (best-effort, ignored): %s\", cleanup_exc\n   242\t            )\n   243\t    return ok",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.29,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 32935
  }
}

## Ход 11 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::ack_command",
  "depth": 2
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
  "start_line": 2495,
  "end_line": 2527,
  "symbol_start_line": 2495,
  "symbol_end_line": 2527,
  "source": "  2495\tasync def ack_command(analyze: AnalyzeInput) -> None:\n  2496\t    \"\"\"Видимое подтверждение приёма команды ДО тяжёлой работы.\n  2497\t\n  2498\t    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не\n  2499\t    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;\n  2500\t    если комментарий-триггер к этому моменту удалили (404) или сработал\n  2501\t    rate limit, сбой реакции не должен утопить сам ack.\n  2502\t\n  2503\t    Триггер виден по comment_id: он есть у команды в комментарии и пуст у\n  2504\t    запуска меткой — реагировать там не на что, и подтверждение называет\n  2505\t    метку, а не команду. Явно переданный `trigger` перекрывает эту догадку:\n  2506\t    аналитику запускает и цикл по метке `research-me`, и назвать её\n  2507\t    `run:analyze` значило бы указать человеку на метку, которой он не ставил.\n  2508\t    \"\"\"\n  2509\t    trigger = (f\"`{analyze.trigger}`\" if analyze.trigger\n  2510\t               else f\"`{run_label(ANALYZE)}`\" if analyze.comment_id is None\n  2511\t               else \"`/analyze`\")\n  2512\t    await asyncio.to_thread(\n  2513\t        github_client.post_comment,\n  2514\t        analyze.repo,\n  2515\t        analyze.issue_number,\n  2516\t        f\"🔍 Взял {trigger} в работу — запускаю автономный анализ через SA-helper.\\n\\n\"\n  2517\t        \"Прогон занимает несколько минут: артефакты появятся в ветке \"\n  2518\t        f\"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.\",\n  2519\t    )\n  2520\t    await asyncio.to_thread(\n  2521\t        github_client.add_label, analyze.repo, analyze.issue_number, run_label(ANALYZE)\n  2522\t    )\n  2523\t    if analyze.comment_id is not None:\n  2524\t        try:\n  2525\t            await asyncio.to_thread(github_client.add_reaction, analyze.repo, analyze.comment_id, \"eyes\")\n  2526\t        except Exception:\n  2527\t            pass  # best-effort: декорация не должна ронять ack или весь прогон",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 15.85,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
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

## Ход 12 · `get_symbol` · contour

**Запрос:**

```json
{
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
  "start_line": 1509,
  "end_line": 1526,
  "symbol_start_line": 1509,
  "symbol_end_line": 1526,
  "source": "  1509\tasync def publish_analysis(analyze: AnalyzeInput) -> str:\n  1510\t    \"\"\"Финал пайплайна: собрать артефакты, push ветки research/issue-N,\n  1511\t    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client.\"\"\"\n  1512\t    clone_dir = _require_workspace(analyze, None)\n  1513\t    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)\n  1514\t    if not files:\n  1515\t        raise RuntimeError(\"пайплайн не произвёл ни одного артефакта\")\n  1516\t    branch = f\"research/issue-{analyze.issue_number}\"\n  1517\t    await asyncio.to_thread(\n  1518\t        github_client.push_artifacts_to_branch,\n  1519\t        analyze.repo, branch, files,\n  1520\t        f\"docs(sa): анализ issue #{analyze.issue_number} через SA-helper\",\n  1521\t    )\n  1522\t    await asyncio.to_thread(\n  1523\t        github_client.post_comment,\n  1524\t        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),\n  1525\t    )\n  1526\t    return branch",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.56,
    "index_age_days": 0,
    "indexed_commit": "993d8561f100",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38670
  }
}
