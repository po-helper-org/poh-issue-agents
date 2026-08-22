---
session: rw-openhands-po-helper-org__poh-issue-agents-65
workspace: contour
turns: 1
started: 2026-08-22T19:17:44Z
finished: 2026-08-22T19:17:44Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 40 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 40 мин |
| `poh-helper` | `18512c1e7ce9` | 40 мин |
| `poh-infra` | `a1db4f02f10c` | 40 мин |
| `poh-issue-agents` | `8ee2a0cd85f8` | 40 мин |
| `poh-memory-engine` | `194e39319b3f` | 40 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 40 мин |
| `poh-scheduller` | `04cc3f47aff9` | 40 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 40 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 2 сут |

# Диалог

## Ход 1 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "How are LLM models currently configured and used in the Issue Agent? Focus on MODEL_GATE and MODEL_CLASSIFY in worker/llm.py and how _run_claude uses models in worker/activities.py"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but the evidence is here: `symbol_bodies` carries the live source of `_run_claude`, read from the current checkout in full. Answer from that; `retrieval`, `fallback_targets` and `candidates` cover the wider question.",
  "citations": [
    "worker/activities.py"
  ],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "worker/activities.py",
    "worker/worker.py",
    "worker/llm.py",
    "worker/activities.py::intake_gate",
    "worker/activities.py::decompose_issue"
  ],
  "retrieval": [
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 117 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `CommentIntentExtraction` | class | class CommentIntentExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) ->",
      "score": 6.384,
      "key_symbols": [
        {
          "name": "GateExtraction",
          "kind": "class",
          "signature": "class GateExtraction(BaseModel):",
          "docstring": "",
          "start_line": 81,
          "end_line": 83,
          "source_excerpt": "class GateExtraction(BaseModel):\n    status: str = Field(description=\"SPAM | VAGUE | SUFFICIENT\")\n    content: str = Field(description=\"Причина (SPAM) или уточняющие вопросы (VAGUE) или подтверждение (SUFFICIENT)\")"
        },
        {
          "name": "ClassificationExtraction",
          "kind": "class",
          "signature": "class ClassificationExtraction(BaseModel):",
          "docstring": "",
          "start_line": 86,
          "end_line": 88,
          "source_excerpt": "class ClassificationExtraction(BaseModel):\n    category: str = Field(description=\"EXISTING | CONSULTATION | BUG | FEATURE\")\n    answer: str"
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
          "name": "read_issue_labels",
          "kind": "function",
          "signature": "def read_issue_labels(repo: str, issue_number: int) -> list[str]:",
          "docstring": "Читает текущие метки Issue для проверки уже стоящих решений.\n    \n    Используется в сценариях, когда Issue приходит в фазу с уже проставленными\n    метками (например, `research-me` на Issue, который вернулся из DUPLICATE),\n    чтобы не ждать нового сигнала человека, а сразу продолжить обработку.",
          "start_line": 455,
          "end_line": 463,
          "source_excerpt": "def read_issue_labels(repo: str, issue_number: int) -> list[str]:\n    \"\"\"Читает текущие метки Issue для проверки уже стоящих решений.\n    \n    Используется в сценариях, когда Issue приходит в фазу с уже проставленными\n    метками (например, `research-me` на Issue, который вернулся из DUPLICATE),\n    чтобы не ждать нового сигнала человека, а сразу продолжить обработку.\n    \"\"\"\n    issue = github_client.get_issue(repo, issue_number)\n    return [label[\"name\"] for label in issue.get(\"labels\", [])]"
        },
        {
          "name": "classify_issue",
          "kind": "function",
          "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:",
          "docstring": "Тип запроса плюс ответ advisor комментарием.\n\n    `bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:\n    на него отвечает БФТ, и два комментария подряд означали бы, что первый\n    неактуален уже в момент публикации. Для бага, консультации и «уже\n    реализовано» ответ публикуется как прежде — БФТ по ним не собирается, и\n    молчание оставило бы Issue вообще без содержательного комментария.\n\n    Решение принимается ЗДЕСЬ, а не отдельной активностью публикации, потому что\n    зависит от категории — а категорию знает только эта активность. Развести их\n    значило бы гонять текст ответа через воркфлоу ради условия, которое здесь\n    уже вычислено.\n\n    Аргумент со значением по умолчанию, а не новая activity: прогоны прежнего\n    поколения зовут её одним аргументом и обязаны получить прежнее поведение.",
          "start_line": 538,
          "end_line": 576,
          "source_excerpt": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:\n    \"\"\"Тип запроса плюс ответ advisor комментарием.\n\n    `bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:\n    на него отвечает БФТ, и два комментария подряд означали бы, что первый\n    неактуален уже в момент публикации. Для бага, консультации и «уже\n    реализовано» ответ публикуется как прежде — БФТ по ним не собирается, и\n    молчание оставило бы Issue вообще без содержательного комментария.\n\n    Решение принимается ЗДЕСЬ, а не отдельной активностью публикации, потому что\n    зависит от категории — а категорию знает только эта активность. Развести их\n    значило бы гонять текст ответа через воркфлоу ради условия, которое здесь\n    уже вычислено.\n\n    Аргумент со значением по умолчанию, а не новая activity: прогоны прежнего\n    поколения зовут её одним аргументом и обязаны получить прежнее поведение.\n    \"\"\"\n    capabilities = (WORKSPACE_DIR / \"capabilities.md\").read_text(encoding=\"utf-8\") \\\n        if (WORKSPACE_DIR / \"capabilities.md\").exists() else \"(пусто)\"\n    user_message = f\"Заголовок: {issue.title}\\n\\nОписание:\\n{issue.body}\\n\\nИзвестный функционал:\\n{capabilities}\"\n    result = llm.extract(\n        _load_prompt(\"system_advisor.md\"), user_message, ClassificationExtraction, model=llm.MODEL_CLASSIFY,\n    )\n    label_map = {\n        \"EXISTING\": \"advisor:existing-functionality\",\n        \"CONSULTATION\": \"advisor:consultation\",\n        \"BUG\": \"advisor:bug\",\n        \"FEATURE\": \"advisor:feature-request\",\n    }\n    label = label_map.get(result.category, \"advisor:answered\")\n    # The advisor prompt still asks the model to prefix its answer with a\n    # legacy [[MARKER]] (from the pre-Instructor text-parsing era). The\n    # category is now carried structurally, so strip that marker line before\n    # posting — it must not appear in the user-facing comment.\n    answer = re.sub(r\"^\\s*\\[\\[[^\\]]+\\]\\]\\s*\", \"\", result.answer)\n    if not (bft_on_triage and label == \"advisor:feature-request\"):\n        github_client.post_comment(issue.repo, issue.issue_number, answer)\n    github_client.add_label(issue.repo, issue.issue_number, label)\n    return ClassificationResult(label=label, answer=answer)"
        },
        {
          "name": "_run_claude",
          "kind": "function",
          "signature": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:",
          "docstring": "Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.",
          "start_line": 1014,
          "end_line": 1059,
          "source_excerpt": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:\n    \"\"\"Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.\n    \"\"\"\n    token, base = _claude_anthropic_creds()\n    # Понятная ошибка вместо голого \"exit 1\", если z.ai не сконфигурирован:\n    # без креды claude-code уходит на дефолтный Anthropic API и падает.\n    if not token or not base:\n        raise RuntimeError(\n            \"claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL \"\n            \"(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера.\"\n        )\n    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера\n    # работает от root, а тот флаг под root запрещён самим claude-code\n    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).\n    command = [\"claude\", \"-p\", prompt, \"--permission-mode\", \"acceptEdits\"]\n    if mcp_config:\n        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы\n        # затесаться серверы из окружения образа, и стадия ходила бы не туда,\n        # куда её послали.\n        #\n        # --allowedTools по имени сервера: без него вызов инструмента ждёт\n        # подтверждения, которого в неинтерактивном режиме не будет, и диалог\n        # молча не состоится.\n        command += [\"--mcp-config\", mcp_config, \"--strict-mcp-config\",\n                    \"--allowedTools\", f\"mcp__{repowise.SERVER_NAME}\"]\n    result = subprocess.run(\n        command,\n        cwd=cwd, capture_output=True, text=True,\n        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,\n        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.\n        env={**os.environ, \"ANTHROPIC_AUTH_TOKEN\": token, \"ANTHROPIC_BASE_URL\": base},\n    )\n    if result.returncode != 0:\n        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба\n        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.\n        detail = result.stderr.strip() or result.stdout.strip() or \"(пустой вывод)\"\n        raise RuntimeError(f\"claude -p exit {result.returncode}: {detail[-1500:]}\")"
        },
        {
          "name": "_refresh_issue_body",
          "kind": "function",
          "signature": "def _refresh_issue_body(issue: IssueInput) -> str:",
          "docstring": "Перечитывает тело Issue из GitHub вместо устаревшего снимка.\n    \n    Снимок в `IssueInput` создается вебхуком один раз и устаревает для\n    долгоживущих задач в `ready-for-dev`.",
          "start_line": 1214,
          "end_line": 1226,
          "source_excerpt": "def _refresh_issue_body(issue: IssueInput) -> str:\n    \"\"\"Перечитывает тело Issue из GitHub вместо устаревшего снимка.\n    \n    Снимок в `IssueInput` создается вебхуком один раз и устаревает для\n    долгоживущих задач в `ready-for-dev`.\n    \"\"\"\n    try:\n        fresh = github_client.get_issue(issue.repo, issue.issue_number)\n        return fresh.get(\"body\") or \"\"\n    except Exception as exc:  # noqa: BLE001 — деградация к старому снимку\n        logger.warning(\"не удалось обновить тело #%s, используется снимок: %s\",\n                       issue.issue_number, exc)\n        return issue.body"
        },
        {
          "name": "_dev_run_agent",
          "kind": "function",
          "signature": "def _dev_run_agent(issue: IssueInput) -> str:",
          "docstring": "Прогон одноразового контейнера. Возвращает хвост вывода.",
          "start_line": 1849,
          "end_line": 1878,
          "source_excerpt": "def _dev_run_agent(issue: IssueInput) -> str:\n    \"\"\"Прогон одноразового контейнера. Возвращает хвост вывода.\"\"\"\n    slug = develop.task_slug(issue.repo, issue.issue_number)\n    _reap_runner(slug)\n    command = develop.runner_command(\n        slug,\n        image=develop.runner_image(),\n        volume=develop.workspace_volume(),\n        mount=develop.workspace_mount(),\n        network=develop.proxy_network(),\n        home=_runner_home(slug),\n    )\n    env = {**os.environ, **develop.runner_env(\n        os.environ.get(\"ZAI_API_KEY\", \"\"),\n        os.environ.get(\"ZAI_BASE_URL\", \"\"),\n        os.environ.get(\"DEVELOP_MODEL\", \"\").strip() or \"openai/glm-4.6\",\n    )}\n    result = subprocess.run(command, env=env, capture_output=True, text=True,\n                            timeout=develop.run_timeout())\n    tail = (result.stdout or \"\")[-4000:] + (result.stderr or \"\")[-2000:]\n    if result.returncode != 0:\n        raise RuntimeError(\n            f\"прогон агента разработки завершился с кодом {result.returncode}: \"\n            f\"{tail[-1500:]}\")\n    # Логируем и на успехе. Раньше вывод жил только в тексте исключения, то есть\n    # при ненулевом коде, — и прогон, который отработал двадцать минут и не\n    # тронул ни одного файла, не оставлял ни строки. Разбираться было не с чем.\n    logger.info(\"Develop %s#%s: вывод агента\\n%s\",\n                issue.repo, issue.issue_number, tail or \"(пусто)\")\n    return tail"
        },
        {
          "name": "dev_run_agent",
          "kind": "function",
          "signature": "async def dev_run_agent(issue: IssueInput) -> None:",
          "docstring": "Шаг 3: прогон одноразового контейнера агента.\n\n    Возврата нет: хвост вывода уходит в лог воркера на любом исходе\n    (`_dev_run_agent`), а в историю воркфлоу ему не место — это килобайты\n    текста на прогон.",
          "start_line": 2124,
          "end_line": 2131,
          "source_excerpt": "async def dev_run_agent(issue: IssueInput) -> None:\n    \"\"\"Шаг 3: прогон одноразового контейнера агента.\n\n    Возврата нет: хвост вывода уходит в лог воркера на любом исходе\n    (`_dev_run_agent`), а в историю воркфлоу ему не место — это килобайты\n    текста на прогон.\n    \"\"\"\n    await _run_with_heartbeat(_dev_run_agent, issue, label=\"dev:agent\")"
        },
        {
          "name": "decompose_issue",
          "kind": "function",
          "signature": "def decompose_issue(issue: IssueInput, branch: str) -> dict:",
          "docstring": "Разбор задачи на подзадачи с раскладкой по релизам.\n\n    Требования читаются из ветки аналитики: разбивать по одному телу Issue —\n    значит делить намерение, а не работу. Если аналитики не было, разбор идёт\n    от тела, и это честнее, чем притворяться, будто требования есть.",
          "start_line": 2278,
          "end_line": 2299,
          "source_excerpt": "def decompose_issue(issue: IssueInput, branch: str) -> dict:\n    \"\"\"Разбор задачи на подзадачи с раскладкой по релизам.\n\n    Требования читаются из ветки аналитики: разбивать по одному телу Issue —\n    значит делить намерение, а не работу. Если аналитики не было, разбор идёт\n    от тела, и это честнее, чем притворяться, будто требования есть.\n    \"\"\"\n    context = [f\"Заголовок: {issue.title}\", \"\", \"Описание:\", issue.body or \"(пусто)\"]\n    if branch:\n        for name in (\"system_requirements.md\", \"concept.md\"):\n            text = github_client.get_file(issue.repo, f\"{FNR_DIR}/{name}\", branch)\n            if text:\n                context += [\"\", f\"--- {name} ---\", text]\n\n    result = llm.extract(\n        _load_prompt(\"system_decompose_issue.md\"),\n        \"\\n\".join(context)[:60000],\n        DecompositionExtraction,\n        model=llm.MODEL_CLASSIFY,\n    )\n    items = decomposition.validate([i.model_dump() for i in result.items])\n    return {\"summary\": result.summary, \"items\": items}"
        }
      ]
    },
    {
      "path": "worker/worker.py",
      "title": "File: worker/worker.py",
      "summary": "`worker/worker.py` is a python source file in the Application layer.",
      "snippet": "`worker/worker.py` is a python source file in the Application layer.",
      "excerpt": "# worker/worker.py\n\n## Overview\n\n`worker/worker.py` is a python source file in the Application layer.\n\nIt exposes 2 public symbols and depends on 7 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `DEVELOP_ACTIVITIES` | constant | DEVELOP_ACTIVITIES = [ |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `worker/activities.py`\n- `worker/consolidation_activities.py`\n- `worker/consolidation_workflow.py`\n- `shared/__init__.py`\n- `shared/sentry_setup.py`\n- `shared/temporal_client.py`\n- `worker/workflows.py`\n\n## Used by\n\nImported by 30 files in this repository.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bft_workflow.py`\n- `tests/test_clarify_after_analysis.py`\n- `tests/test_comment_ack.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_is_a_child.py`\n- `tests/test_develop_workflow.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_duplicate_phase_transitions.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_fnr3_workflow.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_loop.py`\n- `tests/test_park_deadline_absolute.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_pr_fix_child.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_research_autostart.py`\n- `tests/test_workflow_analysis.py`\n- `tests/test_workflow_batch.py`\n- `tests/test_workflow_cl",
      "score": 4.469,
      "key_symbols": [
        {
          "name": "DEVELOP_ACTIVITIES",
          "kind": "constant",
          "signature": "DEVELOP_ACTIVITIES = [",
          "docstring": "",
          "start_line": 41,
          "end_line": 50,
          "source_excerpt": "DEVELOP_ACTIVITIES = [\n    activities.dev_begin,\n    activities.dev_dispatch,\n    activities.dev_prepare,\n    activities.dev_announce,\n    activities.dev_run_agent,\n    activities.dev_followups,\n    activities.dev_tests,\n    activities.dev_publish,\n]"
        },
        {
          "name": "main",
          "kind": "function",
          "signature": "async def main() -> None:",
          "docstring": "",
          "start_line": 53,
          "end_line": 155
        }
      ]
    },
    {
      "path": "worker/llm.py",
      "title": "File: worker/llm.py",
      "summary": "LLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/ priority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт типобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON, вместо ручного json.loads()+try/except, как было в исходной версии на Actions.",
      "snippet": "# worker/llm.py\n\n## Overview\n\nLLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/\npriority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт\nтипобезопасные Pydantic-о",
      "excerpt": "# worker/llm.py\n\n## Overview\n\nLLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/\npriority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт\nтипобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON,\nвместо ручного json.loads()+try/except, как было в исходной версии на\nActions.\n\nДля po-helper/SA-helper (Claude Code skills) используется ДРУГОЙ путь —\nAnthropic-совместимый эндпоинт z.ai через переменные окружения ANTHROPIC_*,\nсм. activities.run_fnr_stage (запускает `claude -p` как subprocess,\nа не через этот клиент).\n\nIt exposes 5 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `MODEL_GATE` | constant | MODEL_GATE = os.environ.get(\"MODEL_GATE\", \"glm-4.5-air\") |\n| `MODEL_CLASSIFY` | constant | MODEL_CLASSIFY = os.environ.get(\"MODEL_CLASSIFY\", \"glm-5.2\") |\n| `get_client` | function | def get_client() -> instructor.Instructor |\n| `extract` | function | def extract(system_prompt: str, user_message: str, response_model, model: str = MODEL_GATE) |\n| `complete` | function | def complete(system_prompt: str, user_message: str, *, model: str, max_tokens: int = 16000 … |\n\n## Used by\n\nImported by 3 files in this repository.\n\n- `tests/test_llm_client.py`\n- `worker/activities.py`\n- `worker/consolidation_activities.py`\n\n## Usage Notes\n\n**Layer:** Application | **Role:** internal\n\n## Questions this page answers\n\n- What does `worker/llm.py` export?\n- Where is `MODEL_GATE` defined?\n- What imports `worker/llm.py",
      "score": 4.384
    },
    {
      "path": "worker/activities.py::intake_gate",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.intake_gate",
      "summary": "`intake_gate` is a function defined in `worker/activities.py`. It carries no docstring.",
      "snippet": "# worker.activities.intake_gate\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateRes",
      "excerpt": "# worker.activities.intake_gate\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\ndef intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult\n```\n\n## Overview\n\n`intake_gate` is a function defined in `worker/activities.py`. It carries no docstring.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n37 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_issue_113_basic.py`\n- `tests/test_issue_113_context_loss.py`\n- `tests/test_lifecycle_phases.py`\n- `tests/test_park_deadlines.py`\n\n_and 12 more._\n\n## Implementation\n\n```\ndef intake_gate(issue: IssueInput, comment_thread: list[str]) -> Ga",
      "score": 3.525
    },
    {
      "path": "worker/activities.py::decompose_issue",
      "file": "worker/activities.py",
      "title": "Symbol: worker.activities.decompose_issue",
      "summary": "Разбор задачи на подзадачи с раскладкой по релизам.",
      "snippet": "# worker.activities.decompose_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\ndef decompose_issue(issue: IssueInput, branch: str) -> dict\n```\n\n##",
      "excerpt": "# worker.activities.decompose_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 5\n\n```\ndef decompose_issue(issue: IssueInput, branch: str) -> dict\n```\n\n## Overview\n\nРазбор задачи на подзадачи с раскладкой по релизам.\n\nТребования читаются из ветки аналитики: разбивать по одному телу Issue —\nзначит делить намерение, а не работу. Если аналитики не было, разбор идёт\nот тела, и это честнее, чем притворяться, будто требования есть.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n37 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_activities_analyze.py`\n- `tests/test_activities_error.py`\n- `tests/test_agent_comment.py`\n- `tests/test_analysis_pipeline.py`\n- `tests/test_bft_activities.py`\n- `tests/test_bft_direct_stage.py`\n- `tests/test_bft_entire_session.py`\n- `tests/test_bft_partial_resume.py`\n- `tests/test_build_task_context.py`\n- `tests/test_command_label_activities.py`\n- `tests/test_comment_ack.py`\n- `tests/test_dev_handoff_once.py`\n- `tests/test_develop.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_develop_child.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `tests/test_fnr_partial_resume.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_issue_113_basic.py`\n- `tests/test_issue_113_context_loss.py`\n- `tests/t",
      "score": 3.415
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question. symbol_bodies carries the live body of the symbol(s) you named, so answer from that rather than re-reading the file.",
  "best_guesses": [
    {
      "file": "worker/activities.py",
      "why_relevant": "Implements function post_agents_off_notice.",
      "score": 6.384
    },
    {
      "file": "worker/worker.py",
      "why_relevant": "`worker/worker.py` is a python source file in the Application layer..",
      "score": 4.469
    },
    {
      "file": "worker/llm.py",
      "why_relevant": "LLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/ priority).",
      "score": 4.384
    }
  ],
  "code_rationale": [
    {
      "path": "worker/activities.py",
      "lines": [
        1128,
        1134
      ],
      "comment": "Отмена активности (terminate воркфлоу, таймаут) обрывает ожидание, но НЕ поток: `to_thread` не прерывается, docker-прогон доигрывает и кладёт исключение в задачу, которую уже никто не ждёт. asyncio на сборке такой задачи пишет «Task exception was never retrieved» уровнем ERROR — и это уезжает в Sentry как сбой контура (ISSUE-AGENT-C: код 137 у контейнера агента, снятого намеренно). Колбэк забирает исключение, поэтому предупреждения не будет.",
      "matched_terms": [
        "agent",
        "issue"
      ]
    },
    {
      "path": "worker/activities.py",
      "lines": [
        148,
        150
      ],
      "comment": "Latin terms must match whole words: the substring \"rce\" otherwise fires on \"source\"/\"resource\"/\"ресурс\" and false-flags most feature issues as security-sensitive. Cyrillic stems stay as substrings (morphology).",
      "matched_terms": [
        "issue"
      ]
    }
  ],
  "symbol_bodies": [
    {
      "path": "worker/activities.py",
      "name": "_run_claude",
      "lines": [
        1014,
        1059
      ],
      "source": "def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:\n    \"\"\"Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.\n\n    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его\n    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.\n\n    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это\n    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.\n    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на\n    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов\n    не увидела и артефакта не создала.\n    \"\"\"\n    token, base = _claude_anthropic_creds()\n    # Понятная ошибка вместо голого \"exit 1\", если z.ai не сконфигурирован:\n    # без креды claude-code уходит на дефолтный Anthropic API и падает.\n    if not token or not base:\n        raise RuntimeError(\n            \"claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL \"\n            \"(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера.\"\n        )\n    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера\n    # работает от root, а тот флаг под root запрещён самим claude-code\n    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).\n    command = [\"claude\", \"-p\", prompt, \"--permission-mode\", \"acceptEdits\"]\n    if mcp_config:\n        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы\n        # затесаться серверы из окружения образа, и стадия ходила бы не туда,\n        # куда её послали.\n        #\n        # --allowedTools по имени сервера: без него вызов инструмента ждёт\n        # подтверждения, которого в неинтерактивном режиме не будет, и диалог\n        # молча не состоится.\n        command += [\"--mcp-config\", mcp_config, \"--strict-mcp-config\",\n                    \"--allowedTools\", f\"mcp__{repowise.SERVER_NAME}\"]\n    result = subprocess.run(\n        command,\n        cwd=cwd, capture_output=True, text=True,\n        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,\n        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.\n        env={**os.environ, \"ANTHROPIC_AUTH_TOKEN\": token, \"ANTHROPIC_BASE_URL\": base},\n    )\n    if result.returncode != 0:\n        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба\n        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.\n        detail = result.stderr.strip() or result.stdout.strip() or \"(пустой вывод)\"\n        raise RuntimeError(f\"claude -p exit {result.returncode}: {detail[-1500:]}\")"
    }
  ],
  "grounding": "symbol_body",
  "next_action_hint": "Read the _run_claude body in symbol_bodies: it is the full live source, so no follow-up call is needed.",
  "_meta": {
    "timing_ms": 1183.0,
    "hint": "Synthesis is what is missing here, not retrieval. Answer from symbol_bodies; retrieval_quality rates what was served.",
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
      "lines": "81-2299",
      "defines": "_run_claude:1014, GateExtraction:81, ClassificationExtraction:86, DuplicateCandidate:91, DuplicateExtraction:97, PriorityExtraction:101"
    },
    {
      "path": "worker/worker.py",
      "lines": "41-155",
      "defines": "main:53, DEVELOP_ACTIVITIES:41"
    },
    {
      "path": "worker/llm.py",
      "defines": "MODEL_GATE:19, MODEL_CLASSIFY:20, get_client:25, extract:41, complete:56"
    },
    {
      "path": "scripts/setup.sh",
      "defines": "bold:21, ok:22, warn:23, die:24, cur:63"
    },
    {
      "path": "worker/workflows.py",
      "defines": "WebhookAudit:286, OrphanAgentEvent:309, CommentAck:330, IssueLifecycle:353, IssueDevelopment:2271, IssuePrFix:2364"
    }
  ]
}
