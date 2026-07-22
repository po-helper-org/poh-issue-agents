# `/analyze` Command (Layer C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Комментарий `/analyze` в Issue запускает автономный прогон SA-helper (полная цепочка FNR), результат возвращается в Issue: артефакты в ветке `research/issue-<n>` + комментарий-сводка.

**Architecture:** Диспатч команды — одна точка ветвления в webhook; тяжёлую работу всегда несёт выделенный Temporal-воркфлоу `IssueAnalysis` (фикс. id `analysis-<repo>-<n>` даёт идемпотентность). Пайплайн — одна heartbeat-activity: `git clone --depth 1` → `repomix` → 5 стадий `claude -p` → сбор артефактов → публикация через GitHub REST.

**Tech Stack:** Python 3.12, temporalio 1.9.0, FastAPI (webhook), requests, pytest + pytest-asyncio, `claude-code` CLI, `repomix` (npx), z.ai Anthropic-эндпоинт.

**Спека:** `sa_documentation/FNR/FNR_2/system_requirements.md` (концепт B с модификациями, вердикт дебатов в `concept.md`).

## Global Constraints

- **Команда тестов (единственная рабочая в этом worktree):** `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`. `make test` и `.venv/bin/pytest` здесь НЕ работают: worktree не имеет своего `.venv`, а console-скрипты основного venv имеют сломанный shebang (`/Users/aleksishmanov/projects/po-helper-issues/.venv/bin/python`). Запускать только через `python -m pytest`.
- **Базовый прогон:** 12 тестов проходят до начала работ. Любая задача обязана оставлять suite зелёным.
- `fastapi` в venv **отсутствует** → `webhook/main.py` не импортируется в тестах. Вся тестируемая логика команд живёт в `shared/commands.py` (без зависимостей от FastAPI/temporalio).
- Все мутации GitHub обязаны соблюдать `DRY_RUN` (`worker/github_client.py:19`).
- Защищённые компоненты (НЕ менять поведение): триаж Слоя A (`worker/activities.py:105-274`), семантика цикла уточнений (`worker/workflows.py:89-116`), идемпотентность по `workflow_id` (`webhook/main.py:44-45`).
- Никакой новой внешней инфраструктуры (инвариант single-node, zero external infra).
- Комментарии в коде — на русском, в стиле существующих модулей (объяснять «почему», а не «что»).
- Conventional Commits; коммит после каждой задачи.
- **Осознанное отклонение от спеки:** sysreq 4.1.1.1(3) / 4.1.1.6(4) требует комментарий «уже выполняется» при повторном `/analyze`. Реализуем как **лог в webhook без комментария**: webhook документирован как чистый транспортный слой (`webhook/main.py:11`), а публикация потребовала бы затащить туда `requests` + GitHub-аутентификацию. Пользователь уже видит ack первого прогона, второй ack — шум. Отклонение зафиксировать в спеке при обновлении.

---

## File Structure

| Файл | Ответственность | Действие |
|---|---|---|
| `shared/workflow_types.py` | Датаклассы входов воркфлоу | Modify: `AnalyzeInput` |
| `shared/commands.py` | Чистый разбор команд + id воркфлоу аналитики (без веб-зависимостей) | Create |
| `worker/github_client.py` | REST-обёртка GitHub | Modify: `auth_token`, `add_reaction`, `ensure_branch`, `put_file`, `push_artifacts_to_branch` |
| `worker/activities.py` | Стадии как Temporal-activities | Modify: `ack_command`, `publish_analysis_error`, `run_analysis_pipeline` + приватные хелперы |
| `worker/workflows.py` | Оркестрация | Modify: сигнал `analyze_requested`; Create: класс `IssueAnalysis` |
| `worker/worker.py` | Регистрация | Modify: воркфлоу + 3 activities |
| `worker/Dockerfile` | Среда исполнения `claude -p` | Modify: skills/commands в `~/.claude`, `repomix` |
| `webhook/main.py` | Транспорт + диспатч команды | Modify: ветка `/analyze` |
| `tests/*` | Юнит-тесты | Create: 5 файлов |

---

## Task 1: Спайк-gate — tool-calling `claude -p` через z.ai

> **🔴 GATE.** Пока этот спайк не зелёный, задачи 3-8 не начинать. Вся фича опирается на способность `claude -p` вызывать инструменты (`Write`/`Read`) через Anthropic-совместимый эндпоинт z.ai. Для GLM уже зафиксирована несовместимость OpenAI tool-calling (`worker/llm.py:28-30`) — Anthropic-путь не проверялся. Это риск R-01 (высокий) из спеки.

**Files:**
- Read only: `.env`, `worker/Dockerfile:3-13`

**Interfaces:**
- Consumes: ничего
- Produces: решение GO / NO-GO для задач 3-8

- [ ] **Step 1: Убедиться, что образ воркера собран и `claude` доступен**

```bash
docker compose build worker
docker compose run --rm --entrypoint sh worker -c "claude --version"
```

Expected: печатает версию `claude-code` (установлен в `worker/Dockerfile:12`).

- [ ] **Step 2: Проверить, что `ANTHROPIC_*` заданы**

```bash
grep -E '^ANTHROPIC_(BASE_URL|AUTH_TOKEN)=' .env
```

Expected: обе строки присутствуют, `ANTHROPIC_AUTH_TOKEN` НЕ пустой. Если пустой — заполнить ключом z.ai перед продолжением (`.env.example:18-21`).

- [ ] **Step 3: Прогнать спайк — заставить агента записать файл через tool-call**

```bash
docker compose run --rm --entrypoint sh worker -c '
  cd /tmp && \
  claude -p "Create a file named spike.txt containing exactly the text OK. Use the Write tool." \
    --permission-mode acceptEdits ; \
  echo "exit=$?" ; \
  cat /tmp/spike.txt 2>/dev/null || echo "NO FILE"
'
```

Expected (GO): `exit=0` и вывод `OK` — значит tool-call `Write` отработал.
Expected (NO-GO): `NO FILE`, либо ненулевой exit, либо ошибка вида `tools not supported` / `Invalid API parameter`.

- [ ] **Step 4: Зафиксировать вердикт**

Если GO — записать результат и продолжать с Task 2.

Если NO-GO — **остановиться и доложить пользователю**. Реализация по этому плану невозможна; спека предусматривает пивот на концепт D (генерация документа через уже рабочий `llm.extract`, `worker/llm.py:41-53`), что требует отдельного плана. Не пытаться обойти это внутри текущего плана.

- [ ] **Step 5: Commit результата спайка**

```bash
mkdir -p docs/spikes
# записать в docs/spikes/2026-07-22-claude-p-zai-tool-calling.md:
#   команду, полный вывод, вердикт GO/NO-GO, версию claude и модель
git add docs/spikes/2026-07-22-claude-p-zai-tool-calling.md
git commit -m "docs(spike): verify claude -p tool-calling via z.ai Anthropic endpoint"
```

---

## Task 2: Среда исполнения — skills, commands, repomix в образе воркера

**Files:**
- Modify: `worker/Dockerfile:1-27`

**Interfaces:**
- Consumes: GO из Task 1
- Produces: контейнер, в котором `claude -p "/fnr-new-task …"` находит команду и skills, а `npx repomix` работает

- [ ] **Step 1: Добавить skills/commands и repomix в образ**

Заменить содержимое `worker/Dockerfile` на:

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code repomix \
    && rm -rf /var/lib/apt/lists/*

# TODO: установка deb8flow — подставь реальный способ (pip/бинарь/build).

# Скиллы и FNR-команды SA-helper кладём в ПОЛЬЗОВАТЕЛЬСКИЙ ~/.claude, а не в
# проектный .claude: `claude -p` запускается с cwd внутри КЛОНА целевого
# репозитория, у которого может быть свой .claude — проектный каталог бы его
# перекрыл. Пользовательский уровень виден из любого cwd и не конфликтует.
COPY .claude/skills /root/.claude/skills
COPY .claude/commands /root/.claude/commands

WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/ .
COPY shared/ /app/shared/

ENV PYTHONPATH=/app

CMD ["python", "worker.py"]
```

- [ ] **Step 2: Пересобрать и проверить наличие команд и repomix**

```bash
docker compose build worker
docker compose run --rm --entrypoint sh worker -c '
  ls /root/.claude/commands/fnr-new-task.md && \
  ls -d /root/.claude/skills/system-analyst-sysreq && \
  repomix --version
'
```

Expected: обе `ls` печатают пути, `repomix --version` печатает версию.

- [ ] **Step 3: Проверить, что команда резолвится агентом**

```bash
docker compose run --rm --entrypoint sh worker -c '
  cd /tmp && claude -p "/fnr-new-task тестовая задача: описать проблему X" \
    --dangerously-skip-permissions 2>&1 | head -30
'
```

Expected: агент не сообщает «unknown command»; видно, что он начал исполнять инструкцию FNR (читает skill/шаблон). Полный прогон не требуется — достаточно резолва команды. Прервать по готовности.

- [ ] **Step 4: Commit**

```bash
git add worker/Dockerfile
git commit -m "build(worker): ship SA-helper skills/commands and repomix in image"
```

---

## Task 3: `AnalyzeInput` + чистый разбор команд

**Files:**
- Modify: `shared/workflow_types.py` (добавить датакласс в конец)
- Create: `shared/commands.py`
- Create: `tests/test_commands.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `AnalyzeInput(repo: str, issue_number: int, title: str, body: str, comment_id: int | None = None)`
  - `is_analyze_command(body: str | None) -> bool`
  - `analysis_workflow_id_for(repo_full_name: str, issue_number: int) -> str`
  - `build_analyze_input(payload: dict) -> AnalyzeInput`
  - константа `ANALYZE_COMMAND = "/analyze"`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_commands.py`:

```python
from shared.commands import (
    analysis_workflow_id_for,
    build_analyze_input,
    is_analyze_command,
)


def test_recognises_bare_command():
    assert is_analyze_command("/analyze") is True


def test_recognises_command_with_trailing_text():
    assert is_analyze_command("/analyze  спроектируй решение") is True


def test_recognises_command_case_insensitively():
    assert is_analyze_command("/ANALYZE") is True


def test_ignores_command_not_at_start():
    assert is_analyze_command("см. выше /analyze") is False


def test_ignores_plain_comment():
    assert is_analyze_command("это обычный ответ на уточнение") is False


def test_ignores_empty_and_none():
    assert is_analyze_command("") is False
    assert is_analyze_command(None) is False
    assert is_analyze_command("   ") is False


def test_analysis_workflow_id_is_distinct_from_lifecycle_id():
    wf_id = analysis_workflow_id_for("o/r", 5)
    assert wf_id == "analysis-o/r-5"
    assert wf_id != "issue-o/r-5"


def test_build_analyze_input_extracts_payload_fields():
    payload = {
        "repository": {"full_name": "o/r"},
        "issue": {"number": 5, "title": "Ревизия reliability", "body": "текст"},
        "comment": {"id": 999},
    }
    analyze = build_analyze_input(payload)
    assert analyze.repo == "o/r"
    assert analyze.issue_number == 5
    assert analyze.title == "Ревизия reliability"
    assert analyze.body == "текст"
    assert analyze.comment_id == 999


def test_build_analyze_input_tolerates_null_body():
    payload = {
        "repository": {"full_name": "o/r"},
        "issue": {"number": 5, "title": "t", "body": None},
        "comment": {"id": 1},
    }
    assert build_analyze_input(payload).body == ""
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_commands.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.commands'`

- [ ] **Step 3: Добавить `AnalyzeInput`**

В конец `shared/workflow_types.py`:

```python
@dataclass
class AnalyzeInput:
    repo: str
    issue_number: int
    title: str
    body: str
    comment_id: int | None = None  # комментарий-триггер, на него ставится реакция
```

- [ ] **Step 4: Создать `shared/commands.py`**

```python
"""Разбор команд из комментариев Issue и идентификаторы воркфлоу аналитики.

Модуль намеренно не зависит ни от FastAPI, ни от temporalio: webhook — чистый
транспортный слой, а эта логика должна оставаться юнит-тестируемой без
установленного веб-стека (в dev-окружении fastapi отсутствует).
"""

from shared.workflow_types import AnalyzeInput

ANALYZE_COMMAND = "/analyze"


def is_analyze_command(body: str | None) -> bool:
    """True, если комментарий — команда `/analyze`.

    Команда распознаётся только в начале комментария: упоминание `/analyze`
    в середине текста (цитата, обсуждение) не должно запускать тяжёлый прогон.
    """
    if not body:
        return False
    tokens = body.strip().split()
    return bool(tokens) and tokens[0].lower() == ANALYZE_COMMAND


def analysis_workflow_id_for(repo_full_name: str, issue_number: int) -> str:
    """Фиксированный id воркфлоу аналитики — источник идемпотентности.

    Повторный `/analyze` при идущем прогоне упрётся в WorkflowAlreadyStarted
    вместо запуска второго дорогого прогона. Namespace отличается от
    `issue-<repo>-<n>`, чтобы не конфликтовать с воркфлоу триажа.
    """
    return f"analysis-{repo_full_name}-{issue_number}"


def build_analyze_input(payload: dict) -> AnalyzeInput:
    """Собирает вход воркфлоу из payload вебхука issue_comment."""
    issue = payload["issue"]
    return AnalyzeInput(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        comment_id=payload["comment"]["id"],
    )
```

- [ ] **Step 5: Прогнать тесты — убедиться, что проходят**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_commands.py -q`
Expected: PASS (9 passed)

- [ ] **Step 6: Прогнать весь suite**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (21 passed)

- [ ] **Step 7: Commit**

```bash
git add shared/commands.py shared/workflow_types.py tests/test_commands.py
git commit -m "feat(shared): add AnalyzeInput and /analyze command parsing"
```

---

## Task 4: GitHub-клиент — реакция и публикация артефактов в ветку

**Files:**
- Modify: `worker/github_client.py` (добавить в конец + рефактор `search_candidates:91`)
- Create: `tests/test_github_client_analyze.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `auth_token() -> str`
  - `add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None`
  - `ensure_branch(repo: str, branch: str) -> None`
  - `put_file(repo: str, branch: str, path: str, content: str, message: str) -> None`
  - `push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None`

> **Почему REST, а не `git push`:** клон делается `--depth 1`, а push из shallow-клона GitHub может отклонить (`shallow update not allowed`). Contents API создаёт коммиты без git-ремоута и полностью мокается в тестах.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_github_client_analyze.py`:

```python
import importlib


def _fresh(monkeypatch, dry):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    import github_client
    return importlib.reload(github_client)


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_auth_token_strips_bearer_prefix(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    assert gc.auth_token() == "tok"


def test_dry_run_makes_no_http_calls(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "put", boom)
    monkeypatch.setattr(gc.requests, "get", boom)

    gc.add_reaction("o/r", 42)
    gc.push_artifacts_to_branch("o/r", "research/issue-5", {"a/b.md": "x"}, "msg")


def test_dry_run_ensure_branch_makes_no_http_call(monkeypatch):
    """Прямой вызов, в обход push_artifacts_to_branch: ensure_branch публична,
    её может дёрнуть будущий код — гард обязан быть в ней самой."""
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "get", boom)
    monkeypatch.setattr(gc.requests, "post", boom)
    gc.ensure_branch("o/r", "research/issue-5")


def test_dry_run_put_file_makes_no_http_call(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "get", boom)
    monkeypatch.setattr(gc.requests, "put", boom)
    gc.put_file("o/r", "research/issue-5", "docs/a.md", "x", "msg")


def test_add_reaction_posts_to_comment_reactions_endpoint(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        return Resp(201)

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.add_reaction("o/r", 42)

    assert seen["url"].endswith("/repos/o/r/issues/comments/42/reactions")
    assert seen["json"] == {"content": "eyes"}


def test_ensure_branch_creates_ref_from_default_branch(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    posted = {}

    def fake_get(url, **kwargs):
        if url.endswith("/repos/o/r"):
            return Resp(200, {"default_branch": "main"})
        if url.endswith("/git/ref/heads/main"):
            return Resp(200, {"object": {"sha": "deadbeef"}})
        return Resp(404)  # ветки ещё нет

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        return Resp(201)

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.ensure_branch("o/r", "research/issue-5")

    assert posted["json"]["ref"] == "refs/heads/research/issue-5"
    assert posted["json"]["sha"] == "deadbeef"


def test_ensure_branch_is_noop_when_branch_exists(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(200, {}))

    def boom(*a, **k):
        raise AssertionError("branch re-created though it already exists")

    monkeypatch.setattr(gc.requests, "post", boom)
    gc.ensure_branch("o/r", "research/issue-5")


def test_push_artifacts_puts_each_file_base64_encoded(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    puts = []

    monkeypatch.setattr(gc, "ensure_branch", lambda repo, branch: None)
    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(404))

    def fake_put(url, **kwargs):
        puts.append((url, kwargs.get("json")))
        return Resp(201)

    monkeypatch.setattr(gc.requests, "put", fake_put)
    gc.push_artifacts_to_branch(
        "o/r", "research/issue-5", {"docs/a.md": "hello", "docs/b.md": "world"}, "msg",
    )

    assert len(puts) == 2
    url, body = puts[0]
    assert "/repos/o/r/contents/docs/a.md" in url
    assert body["branch"] == "research/issue-5"
    import base64
    assert base64.b64decode(body["content"]).decode() == "hello"


def test_put_file_includes_sha_when_file_already_exists(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    captured = {}

    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(200, {"sha": "oldsha"}))

    def fake_put(url, **kwargs):
        captured["json"] = kwargs.get("json")
        return Resp(200)

    monkeypatch.setattr(gc.requests, "put", fake_put)
    gc.put_file("o/r", "research/issue-5", "docs/a.md", "new", "msg")

    assert captured["json"]["sha"] == "oldsha"
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_github_client_analyze.py -q`
Expected: FAIL — `AttributeError: module 'github_client' has no attribute 'auth_token'`

- [ ] **Step 3: Добавить `import base64` в шапку `worker/github_client.py`**

Строка `import logging` (`worker/github_client.py:8`) — добавить перед ней:

```python
import base64
```

- [ ] **Step 4: Добавить функции в конец `worker/github_client.py`**

```python
def auth_token() -> str:
    """Голый токен для внешних процессов (git clone, gh CLI)."""
    return _auth_headers()["Authorization"].split(" ", 1)[1]


def add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None:
    """Реакция на комментарий — видимое «команда принята» до тяжёлой работы."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s comment %s: %s", repo, comment_id, content)
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"
    resp = requests.post(url, headers=_auth_headers(), json={"content": content}, timeout=30)
    resp.raise_for_status()


def ensure_branch(repo: str, branch: str) -> None:
    """Создаёт ветку от дефолтной, если её ещё нет."""
    if _dry_run():
        _log.info("[DRY_RUN] ensure branch %s#%s", repo, branch)
        return
    if branch_exists(repo, branch):
        return
    meta = requests.get(f"https://api.github.com/repos/{repo}", headers=_auth_headers(), timeout=30)
    meta.raise_for_status()
    base = meta.json()["default_branch"]

    ref = requests.get(
        f"https://api.github.com/repos/{repo}/git/ref/heads/{base}",
        headers=_auth_headers(), timeout=30,
    )
    ref.raise_for_status()
    sha = ref.json()["object"]["sha"]

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=_auth_headers(),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=30,
    )
    resp.raise_for_status()


def put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:
    """Создаёт или обновляет файл в ветке через Contents API.

    Contents API, а не `git push`: клон делается shallow (--depth 1), а push из
    такого клона GitHub может отклонить. Здесь ремоут вообще не нужен.
    """
    if _dry_run():
        _log.info("[DRY_RUN] put file %s#%s: %s", repo, branch, path)
        return
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    existing = requests.get(url, headers=_auth_headers(), params={"ref": branch}, timeout=30)
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]  # перезапись требует sha текущей версии

    resp = requests.put(url, headers=_auth_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:
    """Публикует артефакты (путь -> содержимое) в ветку одним проходом."""
    if _dry_run():
        _log.info("[DRY_RUN] push %s files to %s#%s: %s",
                  len(files), repo, branch, sorted(files))
        return
    ensure_branch(repo, branch)
    for path, content in files.items():
        put_file(repo, branch, path, content, message)
```

- [ ] **Step 5: Устранить дублирование извлечения токена**

В `worker/github_client.py:91` заменить строку:

```python
    env = {**os.environ, "GH_TOKEN": _auth_headers()["Authorization"].split(" ")[1]}
```

на:

```python
    env = {**os.environ, "GH_TOKEN": auth_token()}
```

- [ ] **Step 6: Прогнать тесты**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_github_client_analyze.py -q`
Expected: PASS (9 passed)

- [ ] **Step 7: Прогнать весь suite (регресс существующих github_client-тестов)**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (30 passed)

- [ ] **Step 8: Commit**

```bash
git add worker/github_client.py tests/test_github_client_analyze.py
git commit -m "feat(github): add reactions and branch artifact publishing via Contents API"
```

---

## Task 5: Activities подтверждения приёма и ошибки

**Files:**
- Modify: `worker/activities.py` (импорт `AnalyzeInput` в блоке `:19-25`; функции — в конец файла)
- Create: `tests/test_activities_analyze.py`

**Interfaces:**
- Consumes: `AnalyzeInput` (Task 3), `github_client.add_reaction` (Task 4)
- Produces:
  - `ack_command(analyze: AnalyzeInput) -> None`
  - `publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_activities_analyze.py`:

```python
import asyncio

import activities
from shared.workflow_types import AnalyzeInput


def _analyze(comment_id=999):
    return AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=comment_id)


def test_ack_reacts_and_comments(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "add_reaction",
                        lambda repo, cid, content="eyes": calls.append(("reaction", repo, cid, content)))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))

    asyncio.run(activities.ack_command(_analyze()))

    assert ("reaction", "o/r", 999, "eyes") in calls
    comment = next(c for c in calls if c[0] == "comment")
    assert "/analyze" in comment[3]


def test_ack_skips_reaction_without_comment_id(monkeypatch):
    posted = {}

    def boom(*a, **k):
        raise AssertionError("reaction attempted without comment_id")

    monkeypatch.setattr(activities.github_client, "add_reaction", boom)
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(repo=repo, n=n, body=body))

    asyncio.run(activities.ack_command(_analyze(comment_id=None)))

    # Контракт двухчастный: реакция пропущена, НО подтверждение всё равно
    # опубликовано. Без второго ассерта регрессия, загнавшая post_comment
    # внутрь `if comment_id is not None`, прошла бы незамеченной.
    assert posted, "подтверждающий комментарий не опубликован"
    assert posted["n"] == 5


def test_error_comment_mentions_reason_and_retry(monkeypatch):
    posted = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body, repo=repo, n=n))

    asyncio.run(activities.publish_analysis_error(_analyze(), "clone failed"))

    assert posted["repo"] == "o/r"
    assert posted["n"] == 5
    assert "clone failed" in posted["body"]
    assert "/analyze" in posted["body"]
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_activities_analyze.py -q`
Expected: FAIL — `AttributeError: module 'activities' has no attribute 'ack_command'`

- [ ] **Step 3: Расширить импорт типов**

В `worker/activities.py` блок импорта (`:19-25`) заменить на:

```python
from shared.workflow_types import (
    AnalyzeInput,
    ClassificationResult,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
)
```

- [ ] **Step 4: Добавить activities в конец `worker/activities.py`**

```python
# --- Слой C: аналитика по запросу (команда /analyze) ---

@activity.defn
async def ack_command(analyze: AnalyzeInput) -> None:
    """Видимое подтверждение приёма команды ДО тяжёлой работы.

    Реакция ставится на сам комментарий-триггер, комментарий объясняет
    задержку: полный прогон FNR занимает минуты, без ack это выглядит как
    молчание бота.
    """
    if analyze.comment_id is not None:
        github_client.add_reaction(analyze.repo, analyze.comment_id, "eyes")
    github_client.post_comment(
        analyze.repo,
        analyze.issue_number,
        "🔍 Взял `/analyze` в работу — запускаю автономный анализ через SA-helper.\n\n"
        "Прогон занимает несколько минут: артефакты появятся в ветке "
        f"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.",
    )


@activity.defn
async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:
    """Не молчать при провале: прогон дорогой и долгий, тихое падение
    неотличимо от «ещё работает»."""
    github_client.post_comment(
        analyze.repo,
        analyze.issue_number,
        f"⚠️ Автономный анализ не удался: {reason}\n\n"
        "Прогон не повторяется автоматически (он недетерминирован и дорог). "
        "Запустить заново — командой `/analyze`.",
    )
```

- [ ] **Step 5: Прогнать тесты**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_activities_analyze.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Прогнать весь suite**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (33 passed)

- [ ] **Step 7: Commit**

```bash
git add worker/activities.py tests/test_activities_analyze.py
git commit -m "feat(activities): add /analyze ack and failure-notice activities"
```

---

## Task 6: Пайплайн `run_analysis_pipeline`

**Files:**
- Modify: `worker/activities.py` (шапка импортов `:9-12`; заменить заглушку `run_research_pipeline` на `:280-287`)
- Create: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: `AnalyzeInput`, `github_client.auth_token`, `github_client.push_artifacts_to_branch`, `github_client.post_comment`
- Produces:
  - `run_analysis_pipeline(analyze: AnalyzeInput) -> str` (возвращает имя ветки)
  - приватные: `_fnr_stages(description) -> list[tuple[str, str, str | None]]`, `_clone_repo(repo, dest)`, `_run_repomix(clone_dir)`, `_run_claude(prompt, cwd)`, `_collect_artifacts(clone_dir) -> dict[str, str]`, `_build_summary(analyze, branch, files) -> str`
  - константы `FNR_DIR`, `ARTIFACT_FILES`, `CLAUDE_STAGE_TIMEOUT_SEC`, `REPOMIX_TIMEOUT_SEC`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_analysis_pipeline.py`:

```python
import asyncio
from pathlib import Path

import pytest

import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="Ревизия", body="текст", comment_id=1)


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Подменяет внешние эффекты, оставляя настоящую оркестрацию стадий."""
    state = {"stages": [], "beats": [], "pushed": None, "comment": None, "clone_dir": None}

    monkeypatch.setattr(activities.activity, "heartbeat",
                        lambda *a: state["beats"].append(a[0] if a else None))

    def fake_clone(repo, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)
        state["clone_dir"] = dest

    def fake_repomix(clone_dir):
        state["stages"].append("repomix")

    def fake_claude(prompt, cwd):
        # первое слово промпта — сама FNR-команда
        state["stages"].append(prompt.split()[0])
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        produced = {
            "/fnr-new-task": "task.md",
            "/fnr-concept": "concept.md",
            "/fnr-system-requirements": "system_requirements.md",
            "/validate-doc": "validation.md",
        }.get(prompt.split()[0])
        if produced:
            (fnr / produced).write_text(f"# {produced}", encoding="utf-8")

    monkeypatch.setattr(activities, "_clone_repo", fake_clone)
    monkeypatch.setattr(activities, "_run_repomix", fake_repomix)
    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda repo, branch, files, message: state.update(pushed=(branch, dict(files))))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: state.update(comment=body))
    return state


def test_runs_all_five_fnr_stages_in_order(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert wired["stages"] == [
        "repomix",
        "/fnr-new-task",
        "/fnr-concept",
        "/fnr-debate",
        "/fnr-system-requirements",
        "/validate-doc",
    ]


def test_heartbeats_at_least_once_per_stage(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))
    # clone + repomix + 5 стадий
    assert len(wired["beats"]) >= 7


def test_pushes_artifacts_to_research_branch(wired):
    branch = asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert branch == "research/issue-5"
    pushed_branch, files = wired["pushed"]
    assert pushed_branch == "research/issue-5"
    assert f"{activities.FNR_DIR}/system_requirements.md" in files
    assert len(files) == 4


def test_summary_comment_links_artifacts(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    body = wired["comment"]
    assert "research/issue-5" in body
    assert "system_requirements.md" in body
    assert len(body) <= 65536


def test_missing_expected_artifact_fails_the_stage(monkeypatch, wired):
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)  # ничего не пишет

    with pytest.raises(RuntimeError, match="system_requirements.md|task.md"):
        asyncio.run(activities.run_analysis_pipeline(_analyze()))


def test_workspace_is_removed_even_on_failure(monkeypatch, wired):
    seen = {}
    real_mkdtemp = activities.tempfile.mkdtemp

    def tracking_mkdtemp(*a, **k):
        seen["dir"] = real_mkdtemp(*a, **k)
        return seen["dir"]

    monkeypatch.setattr(activities.tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(activities, "_run_claude",
                        lambda prompt, cwd: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert not Path(seen["dir"]).exists()
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_analysis_pipeline.py -q`
Expected: FAIL — `AttributeError: module 'activities' has no attribute 'FNR_DIR'`

- [ ] **Step 3: Расширить шапку импортов `worker/activities.py`**

Заменить блок `:9-12`:

```python
import re
import subprocess
import tomllib
from pathlib import Path
```

на:

```python
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
```

- [ ] **Step 4: Заменить заглушку `run_research_pipeline` (`worker/activities.py:280-287`)**

Удалить функцию `run_research_pipeline` целиком и вставить на её место:

```python
# --- Пайплайн SA-helper (FNR) ---

FNR_DIR = "sa_documentation/FNR/FNR_1"
ARTIFACT_FILES = ("task.md", "concept.md", "system_requirements.md", "validation.md")
CLAUDE_STAGE_TIMEOUT_SEC = 900
REPOMIX_TIMEOUT_SEC = 600
CLONE_TIMEOUT_SEC = 300


def _fnr_stages(description: str) -> list[tuple[str, str, str | None]]:
    """Стадии цепочки FNR: (имя, промпт, ожидаемый артефакт).

    У `debate` и `validate` ожидаемого файла нет: дебаты дописываются в
    concept.md, а валидация может остаться отчётом в выводе.
    """
    return [
        ("task", f"/fnr-new-task {description}", f"{FNR_DIR}/task.md"),
        ("concept", f"/fnr-concept {FNR_DIR}/task.md", f"{FNR_DIR}/concept.md"),
        ("debate", f"/fnr-debate {FNR_DIR}/concept.md", None),
        ("sysreq", f"/fnr-system-requirements {FNR_DIR}/concept.md",
         f"{FNR_DIR}/system_requirements.md"),
        ("validate", f"/validate-doc {FNR_DIR}/system_requirements.md", None),
    ]


def _clone_repo(repo: str, dest: str) -> None:
    """Shallow-клон целевого репозитория: артефакты FNR обязаны опираться на
    реальный код (`файл:строка`), одного текста Issue недостаточно."""
    url = f"https://x-access-token:{github_client.auth_token()}@github.com/{repo}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", url, dest],
        check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT_SEC,
    )


def _run_repomix(clone_dir: str) -> None:
    """Упаковка кода один раз: 5 стадий переиспользуют один файл вместо того,
    чтобы каждая заново обходила репозиторий."""
    out = Path(clone_dir) / "sa_documentation" / "repomix-output.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["repomix", "--output", str(out)],
        cwd=clone_dir, check=True, capture_output=True, text=True,
        timeout=REPOMIX_TIMEOUT_SEC,
    )


def _run_claude(prompt: str, cwd: str) -> None:
    """Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.

    ANTHROPIC_* берутся из окружения контейнера (env_file .env) и направляют
    claude-code на Anthropic-совместимый эндпоинт z.ai.
    """
    result = subprocess.run(
        # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера
        # работает от root, а тот флаг под root запрещён самим claude-code
        # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).
        ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
        cwd=cwd, capture_output=True, text=True,
        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p exit {result.returncode}: {result.stderr[-1000:]}")


def _collect_artifacts(clone_dir: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for name in ARTIFACT_FILES:
        path = Path(clone_dir) / FNR_DIR / name
        if path.exists():
            files[f"{FNR_DIR}/{name}"] = path.read_text(encoding="utf-8")
    return files


def _build_summary(analyze: AnalyzeInput, branch: str, files: dict[str, str]) -> str:
    base = f"https://github.com/{analyze.repo}/blob/{branch}"
    links = "\n".join(f"- [`{path.rsplit('/', 1)[-1]}`]({base}/{path})" for path in sorted(files))
    return (
        "## 🤖 Автономный анализ (SA-helper)\n\n"
        f"Прогнал полную цепочку FNR по этой задаче. Артефакты — в ветке `{branch}`:\n\n"
        f"{links}\n\n"
        "Начни с `system_requirements.md` — это ответ на вопрос «как реализовать эту "
        "задачу»: разбор текущего поведения на код-доказательствах, план миграции с "
        "откатами, задачи с критериями приёмки и риски с митигацией.\n\n"
        "Повторить анализ — командой `/analyze`."
    )


@activity.defn
async def run_analysis_pipeline(analyze: AnalyzeInput) -> str:
    """Полный прогон SA-helper одной activity.

    Одна activity, а не пять: клон, упаковка и стадии делят рабочий каталог на
    локальном диске одного процесса — разбиение по activity потребовало бы
    общего тома. Heartbeat между стадиями держит таск живым (долгие стадии уже
    приводили к ложным срабатываниям детектора дедлоков, worker/worker.py:44-51).
    """
    workdir = tempfile.mkdtemp(prefix=f"analysis-{analyze.issue_number}-")
    clone_dir = str(Path(workdir) / "repo")
    try:
        _clone_repo(analyze.repo, clone_dir)
        activity.heartbeat("cloned")
        _run_repomix(clone_dir)
        activity.heartbeat("packed")

        description = f"{analyze.title}\n\n{analyze.body}"
        for name, prompt, expected in _fnr_stages(description):
            _run_claude(prompt, clone_dir)
            if expected and not (Path(clone_dir) / expected).exists():
                raise RuntimeError(f"стадия {name}: артефакт {expected} не создан")
            activity.heartbeat(name)

        files = _collect_artifacts(clone_dir)
        if not files:
            raise RuntimeError("пайплайн не произвёл ни одного артефакта")

        branch = f"research/issue-{analyze.issue_number}"
        github_client.push_artifacts_to_branch(
            analyze.repo, branch, files,
            f"docs(sa): анализ issue #{analyze.issue_number} через SA-helper",
        )
        github_client.post_comment(
            analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),
        )
        return branch
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
```

- [ ] **Step 5: Прогнать тесты**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_analysis_pipeline.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: Прогнать весь suite**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (39 passed)

> `run_research_pipeline` удалён — он ещё числится в регистрации воркера (`worker/worker.py:38`). Импорт `worker.py` пока не ломается на уровне тестов, но это чинится в Task 7, который обязателен сразу следом.

- [ ] **Step 7: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(activities): implement SA-helper FNR pipeline for /analyze"
```

---

## Task 7: Воркфлоу `IssueAnalysis`, сигнал и регистрация

**Files:**
- Modify: `worker/workflows.py` (сигнал в `IssueLifecycle` рядом с `:37-43`; новый класс — в конец файла)
- Modify: `worker/worker.py:26-41`
- Create: `tests/test_workflow_analysis.py`

**Interfaces:**
- Consumes: `activities.ack_command`, `activities.run_analysis_pipeline`, `activities.publish_analysis_error`, `AnalyzeInput`
- Produces: воркфлоу `IssueAnalysis` (зарегистрирован под этим именем), сигнал `analyze_requested(comment_id: int)` на `IssueLifecycle`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_workflow_analysis.py`:

```python
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import AnalyzeInput
from workflows import IssueAnalysis


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=1)


@pytest.mark.asyncio
async def test_happy_path_acks_then_runs_pipeline():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="run_analysis_pipeline")
    async def pipeline(analyze: AnalyzeInput) -> str:
        calls.append("pipeline")
        return "research/issue-5"

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=task_queue,
                          workflows=[IssueAnalysis],
                          activities=[ack, pipeline, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(),
                id=f"analysis-{uuid.uuid4()}", task_queue=task_queue,
            )

    assert calls == ["ack", "pipeline"]


@pytest.mark.asyncio
async def test_pipeline_failure_publishes_error_and_does_not_retry():
    attempts = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        pass

    @activity.defn(name="run_analysis_pipeline")
    async def pipeline(analyze: AnalyzeInput) -> str:
        attempts.append(1)
        raise RuntimeError("boom")

    reported = {}

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        reported["reason"] = reason

    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=task_queue,
                          workflows=[IssueAnalysis],
                          activities=[ack, pipeline, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(),
                id=f"analysis-{uuid.uuid4()}", task_queue=task_queue,
            )

    assert len(attempts) == 1, "дорогой недетерминированный прогон не должен ретраиться"
    assert "boom" in reported["reason"]
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_workflow_analysis.py -q`
Expected: FAIL — `ImportError: cannot import name 'IssueAnalysis' from 'workflows'`

- [ ] **Step 3: Расширить импорт типов в `worker/workflows.py`**

В блоке `with workflow.unsafe.imports_passed_through():` (`:24-27`) заменить:

```python
    from shared.workflow_types import IssueInput
```

на:

```python
    from shared.workflow_types import AnalyzeInput, IssueInput
```

- [ ] **Step 4: Добавить сигнал `analyze_requested` в `IssueLifecycle`**

Сразу после сигнала `user_comment` (`worker/workflows.py:41-43`) вставить:

```python
    @workflow.signal
    async def analyze_requested(self, comment_id: int) -> None:
        """Уведомление, что по Issue запрошен автономный анализ.

        Намеренно НЕ запускает пайплайн и не спавнит дочерний воркфлоу: run()
        в этот момент обычно припаркован в _wait_for_signal(), и спавн из
        хендлера сигнала гонялся бы с основным циклом. Тяжёлый прогон несёт
        отдельный воркфлоу IssueAnalysis, стартующий из webhook.
        """
        self._analyze_requested_comment_id = comment_id
```

И в `__init__` (`worker/workflows.py:34-35`) добавить строку:

```python
        self._analyze_requested_comment_id: int | None = None
```

- [ ] **Step 5: Добавить класс `IssueAnalysis` в конец `worker/workflows.py`**

```python
@workflow.defn(name="IssueAnalysis")
class IssueAnalysis:
    """Аналитика по запросу (Слой C) — отдельный воркфлоу на команду /analyze.

    Отдельный, а не часть IssueLifecycle: команда приходит в произвольный
    момент, когда воркфлоу триажа уже завершён (advisor-ответ) или припаркован
    в ожидании лейбла. Фиксированный id `analysis-<repo>-<n>` даёт
    идемпотентность: повторный /analyze упрётся в WorkflowAlreadyStarted.
    """

    @workflow.run
    async def run(self, analyze: AnalyzeInput) -> None:
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        try:
            await workflow.execute_activity(
                activities.run_analysis_pipeline,
                analyze,
                start_to_close_timeout=timedelta(seconds=4500),  # 75 минут на 5 стадий
                heartbeat_timeout=timedelta(seconds=300),
                # Прогон недетерминирован и дорог — слепой авторетрай сжёг бы
                # бюджет впустую. Повтор инициирует человек командой /analyze.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:
            await workflow.execute_activity(
                activities.publish_analysis_error,
                args=[analyze, str(exc)[:500]],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
```

- [ ] **Step 6: Обновить регистрацию в `worker/worker.py`**

Заменить строку `:18`:

```python
from workflows import IssueLifecycle
```

на:

```python
from workflows import IssueAnalysis, IssueLifecycle
```

Заменить `:26`:

```python
        workflows=[IssueLifecycle],
```

на:

```python
        workflows=[IssueLifecycle, IssueAnalysis],
```

В списке `activities=[...]` (`:27-41`) заменить строку `activities.run_research_pipeline,` на три строки:

```python
            activities.run_analysis_pipeline,
            activities.ack_command,
            activities.publish_analysis_error,
```

- [ ] **Step 7: Прогнать тесты**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_workflow_analysis.py -q`
Expected: PASS (2 passed)

- [ ] **Step 8: Проверить, что регистрация воркера импортируется**

Run:
```bash
cd worker && /Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -c "
import sys; sys.path.insert(0, '..')
import worker
print('worker module imports OK')
" ; cd ..
```
Expected: печатает `worker module imports OK` (ошибки `AttributeError: run_research_pipeline` быть не должно).

- [ ] **Step 9: Прогнать весь suite**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (41 passed)

- [ ] **Step 10: Commit**

```bash
git add worker/workflows.py worker/worker.py tests/test_workflow_analysis.py
git commit -m "feat(workflow): add IssueAnalysis workflow and analyze_requested signal"
```

---

## Task 8: Диспатч в webhook + сквозная проверка

**Files:**
- Modify: `webhook/main.py` (шапка импортов `:14-19`; ветка `issue_comment` `:89-107`)

**Interfaces:**
- Consumes: `shared.commands` (Task 3), воркфлоу `IssueAnalysis` (Task 7)
- Produces: рабочий сквозной путь `/analyze`

> Юнит-тестов здесь нет намеренно: `fastapi` отсутствует в dev-venv, поэтому `webhook/main.py` не импортируется тестами. Вся тестируемая логика уже покрыта в Task 3; здесь остаётся тонкая проводка, проверяемая сквозным прогоном (шаги 4-6).

- [ ] **Step 1: Расширить импорты `webhook/main.py`**

Заменить блок `:14-19`:

```python
import hashlib
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client
```

на:

```python
import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared.commands import (
    analysis_workflow_id_for,
    build_analyze_input,
    is_analyze_command,
)

_log = logging.getLogger("webhook")
```

- [ ] **Step 2: Добавить ветку команды в обработчик `issue_comment`**

Заменить блок `:98-107`:

```python
        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]
        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", payload["comment"]["body"])
        except Exception:
            # Workflow мог уже завершиться (issue закрыт) — комментарий
            # после этого просто не на что сигналить, это не ошибка.
            pass
```

на:

```python
        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]

        # Команда `/analyze` — отдельная ветка, и это ЕДИНСТВЕННАЯ точка
        # ветвления «команда против обычного комментария». Если бы команда
        # уходила в user_comment, её съел бы цикл уточнений intake gate как
        # ответ на уточняющий вопрос.
        if is_analyze_command(payload["comment"].get("body")):
            analyze = build_analyze_input(payload)

            # Живому воркфлоу триажа шлём только уведомление — исполнителем
            # всегда остаётся выделенный IssueAnalysis.
            lifecycle = client.get_workflow_handle(workflow_id_for(repo, issue_number))
            try:
                await lifecycle.signal("analyze_requested", analyze.comment_id)
            except Exception:
                pass  # триаж уже завершён — уведомлять некого, это не ошибка

            try:
                await client.start_workflow(
                    "IssueAnalysis",
                    analyze,
                    id=analysis_workflow_id_for(repo, issue_number),
                    task_queue="issue-lifecycle",
                )
            except WorkflowAlreadyStartedError:
                # Прогон по этому Issue уже идёт: пользователь видел ack первого
                # запуска, второй ack был бы шумом. Webhook — чистый транспорт,
                # публиковать отсюда в GitHub не будем.
                _log.info("analysis already running for %s#%s", repo, issue_number)
            return {"ok": True}

        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", payload["comment"]["body"])
        except Exception:
            # Workflow мог уже завершиться (issue закрыт) — комментарий
            # после этого просто не на что сигналить, это не ошибка.
            pass
```

- [ ] **Step 3: Обновить docstring модуля**

В `webhook/main.py` в docstring (`:5-7`) заменить строку:

```
- issue_comment.created    -> сигнал уже идущему workflow (текст комментария —
                               используется циклом уточнений, если issue
                               в состоянии ожидания ответа)
```

на:

```
- issue_comment.created    -> `/analyze` запускает отдельный workflow
                               IssueAnalysis (аналитика по запросу); любой
                               другой комментарий — сигнал уже идущему
                               workflow (используется циклом уточнений)
```

- [ ] **Step 4: Прогнать весь suite (регресса быть не должно)**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS (41 passed)

- [ ] **Step 5: Поднять стек в DRY_RUN и проверить сквозной путь**

```bash
grep -q '^DRY_RUN=1' .env || echo 'DRY_RUN=1' >> .env
docker compose build worker webhook
docker compose up -d
docker compose logs -f worker
```

Затем написать `/analyze` в тестовом Issue (или отправить тестовый payload на `/webhook`).

Expected в логах: `[DRY_RUN] reaction …`, `[DRY_RUN] comment …` (ack), затем стадии пайплайна, затем `[DRY_RUN] push 4 files to …research/issue-<n>` и `[DRY_RUN] comment …` (сводка). В Temporal UI (http://localhost:8080) виден воркфлоу `analysis-<repo>-<n>`.

- [ ] **Step 6: Проверить идемпотентность и отсутствие регресса триажа**

1. Написать `/analyze` второй раз, пока первый прогон идёт → в логах webhook `analysis already running`, второго воркфлоу в Temporal UI нет.
2. Написать обычный комментарий → уходит как `user_comment`, воркфлоу `IssueAnalysis` не создаётся.

- [ ] **Step 7: Commit**

```bash
git add webhook/main.py
git commit -m "feat(webhook): dispatch /analyze to the IssueAnalysis workflow"
```

- [ ] **Step 8: Прогон на реальном Issue и калибровка**

Снять `DRY_RUN`, прогнать `/analyze` на `po-helper-org/poh-pr-agents#5`. Замерить фактическое время всех 5 стадий. Если прогон приблизился к 4500 с — поднять `start_to_close_timeout` в `worker/workflows.py` и зафиксировать новое значение в `sa_documentation/FNR/FNR_2/system_requirements.md` (NFR 4.3.2.4).

---

## Self-Review

**Покрытие спеки (sysreq FNR-2 → задачи):**

| Требование | Задача |
|---|---|
| 4.1.1 Диспатч `/analyze`, маршрутизация | Task 3 (парсинг) + Task 8 (проводка) |
| 4.2.1 Воркфлоу `IssueAnalysis` | Task 7 |
| 4.2.2 Сигнал `analyze_requested` | Task 7 |
| 4.2.3 Регистрация в воркере | Task 7 |
| 4.3.1 Спайк-gate tool-calling | Task 1 |
| 4.3.2 `run_analysis_pipeline` | Task 6 |
| 4.3.3 Ack + обработка сбоя | Task 5 |
| 4.4.1 Реакция + публикация в ветку | Task 4 |
| 4.5.1 Skills/commands/repomix в образе | Task 2 |
| План миграции, этап 6 (прогон + калибровка) | Task 8, шаги 5-8 |

Пробелов нет.

**Известные отклонения (осознанные, зафиксировать в спеке при обновлении):**
1. Комментарий «уже выполняется» заменён логом в webhook — см. Global Constraints.
2. ~~`claude -p` запускается только с `--dangerously-skip-permissions`~~ — **опровергнуто спайком (Task 1)**. Контейнер воркера работает от root, а `--dangerously-skip-permissions` под root запрещён самим claude-code (`cannot be used with root/sudo privileges`). Рабочий флаг — `--permission-mode acceptEdits`; спека 4.3.2.4 NFR 5 приведена к нему же. Детали: `docs/spikes/2026-07-22-claude-p-zai-tool-calling.md`.
3. Публикация артефактов идёт через Contents API вместо `git push` (спека допускала оба варианта) — причина в shallow-клоне, зафиксирована в Task 4.

**Консистентность имён:** `AnalyzeInput` (поля `repo`, `issue_number`, `title`, `body`, `comment_id`) используется идентично в Tasks 3, 5, 6, 7, 8; `push_artifacts_to_branch(repo, branch, files, message)` вызывается в Task 6 ровно с сигнатурой из Task 4; `FNR_DIR` определён в Task 6 и используется его же тестами.
