# Analyze Context Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Кормить FNR-цепочку `/analyze` живым контекстом issue — комментариями обсуждения и связанными PR, — а не только `title + body`.

**Architecture:** Обогащение живёт внутри `run_analysis_pipeline` (подход A из спеки): новый хелпер `activities._build_task_context` собирает markdown-бриф, дёргая `github_client.list_comments` и новый `github_client.list_linked_prs`. Контекст остаётся в воркере (не идёт в Temporal history). Любой сбой fetch деградирует до `title + body` — прогон не падает.

**Tech Stack:** Python 3.12, `requests` (GitHub REST + Timeline API), `temporalio` activities, pytest + monkeypatch.

## Global Constraints

- **Интерпретатор тестов:** `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest` (venv в основном чекауте, worktree его переиспользует; `make test` и `.venv/bin/pytest` сломаны — не использовать).
- **Спека:** `docs/superpowers/specs/2026-07-24-analyze-context-enrichment-design.md` — источник истины.
- **Scope:** только комментарии + связанные PR. Без стиринга из команды, без лейблов, без явных указателей на доки, без отдельной activity.
- **Деградация обязательна:** ни один fetch-сбой не роняет прогон; пол = `title + body`.
- **Числовые дефолты** (константы модуля `worker/activities.py`): `CONTEXT_COMMENT_LIMIT = 20`, `CONTEXT_COMMENT_CHARS = 1500`, `CONTEXT_PR_LIMIT = 20`, `CONTEXT_TOTAL_CHARS = 16000`.
- **Токен не в URL:** новые вызовы клиента идут через `_auth_headers()`, как остальной `github_client`.
- **Каждая стадия — коммит** с `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: `github_client.list_linked_prs`

Timeline API возвращает кросс-ссылки; отбираем только ссылки на PR (не на issue), без дублей.

**Files:**
- Modify: `worker/github_client.py` (добавить функцию после `list_comments`, ~строка 204)
- Test: `tests/test_github_client_linked_prs.py` (создать)

**Interfaces:**
- Consumes: `github_client.requests`, `github_client._auth_headers` (существуют).
- Produces: `list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]`, каждый элемент `{"number": int, "title": str, "state": str, "url": str}`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_github_client_linked_prs.py`:

```python
import github_client


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pr_event(number, title="PR", state="open"):
    return {
        "event": "cross-referenced",
        "source": {"issue": {
            "number": number, "title": title, "state": state,
            "html_url": f"https://github.com/o/r/pull/{number}",
            "pull_request": {"url": f"https://api.github.com/repos/o/r/pulls/{number}"},
        }},
    }


def test_keeps_only_cross_referenced_prs(monkeypatch):
    timeline = [
        {"event": "labeled"},                       # не cross-ref — выкинуть
        _pr_event(2, "Ingress", "open"),            # PR — оставить
        {"event": "cross-referenced", "source": {"issue": {  # issue, не PR — выкинуть
            "number": 7, "title": "just issue", "state": "open",
            "html_url": "https://github.com/o/r/issues/7"}}},
    ]
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: _FakeResp(timeline))

    prs = github_client.list_linked_prs("o/r", 1)

    assert prs == [{
        "number": 2, "title": "Ingress", "state": "open",
        "url": "https://github.com/o/r/pull/2",
    }]


def test_dedups_and_respects_limit(monkeypatch):
    timeline = [_pr_event(2)] * 3 + [_pr_event(3), _pr_event(4), _pr_event(5)]
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: _FakeResp(timeline))

    prs = github_client.list_linked_prs("o/r", 1, limit=2)

    assert [p["number"] for p in prs] == [2, 3]  # дедуп #2, обрезка до 2


def test_uses_timeline_endpoint_with_preview_header(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        seen["accept"] = headers.get("Accept", "")
        return _FakeResp([])

    monkeypatch.setattr(github_client.requests, "get", fake_get)

    github_client.list_linked_prs("o/r", 1)

    assert seen["url"].endswith("/repos/o/r/issues/1/timeline")
    assert "mockingbird" in seen["accept"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_github_client_linked_prs.py -v`
Expected: FAIL — `AttributeError: module 'github_client' has no attribute 'list_linked_prs'`.

- [ ] **Step 3: Write minimal implementation**

В `worker/github_client.py` сразу после функции `list_comments` (перед `get_file`) добавить:

```python
def list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:
    """PR, кросс-ссылающиеся на issue (Timeline API).

    Трекинг-issue связан с PR событиями cross-referenced; тело issue их не
    содержит. Оставляем только ссылки на PR (source.issue с ключом
    pull_request), не на другие issue, и убираем дубли.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/timeline"
    resp = requests.get(
        url,
        headers={**_auth_headers(),
                 "Accept": "application/vnd.github.mockingbird-preview+json"},
        params={"per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    seen: set[int] = set()
    prs: list[dict] = []
    for event in resp.json():
        if event.get("event") != "cross-referenced":
            continue
        src = (event.get("source") or {}).get("issue") or {}
        if "pull_request" not in src:
            continue
        number = src.get("number")
        if number is None or number in seen:
            continue
        seen.add(number)
        prs.append({
            "number": number,
            "title": src.get("title", ""),
            "state": src.get("state", ""),
            "url": src.get("html_url", ""),
        })
        if len(prs) >= limit:
            break
    return prs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_github_client_linked_prs.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/github_client.py tests/test_github_client_linked_prs.py
git commit -m "feat(github_client): list_linked_prs via Timeline API

Кросс-ссылки issue на PR (event=cross-referenced, source.issue.pull_request),
без issue-ссылок и дублей. Нужен обогащению контекста /analyze.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `activities._build_task_context` + вспомогательные

Хелпер собирает бриф; секции тянутся отдельными функциями с деградацией.

**Files:**
- Modify: `worker/activities.py` (добавить `import logging` в блок stdlib-импортов; `logger = logging.getLogger(__name__)` после импортов; 4 константы рядом с `HEARTBEAT_INTERVAL_SEC` ~строка 314; 4 функции перед `run_analysis_pipeline`)
- Test: `tests/test_build_task_context.py` (создать)

**Interfaces:**
- Consumes: `github_client.list_comments` (есть), `github_client.list_linked_prs` (Task 1), `shared.commands.parse_command` (импортирован, `activities.py:26`).
- Produces: `_build_task_context(analyze: AnalyzeInput) -> str`; хелперы `_truncate(text: str, limit: int) -> str`, `_fetch_comment_blocks(analyze) -> list[str]`, `_fetch_prs_section(analyze) -> str`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_build_task_context.py`:

```python
import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=1, title="Надёжность",
                        body="Ядро платформы.", comment_id=1)


def _comment(login, body, date="2026-07-20T10:00:00Z"):
    return {"user": {"login": login}, "body": body, "created_at": date}


def _wire(monkeypatch, comments=None, prs=None, comments_exc=None, prs_exc=None):
    def fake_comments(repo, n, limit=50):
        if comments_exc:
            raise comments_exc
        return comments or []

    def fake_prs(repo, n, limit=20):
        if prs_exc:
            raise prs_exc
        return prs or []

    monkeypatch.setattr(activities.github_client, "list_comments", fake_comments)
    monkeypatch.setattr(activities.github_client, "list_linked_prs", fake_prs)


def test_includes_title_body_comments_and_prs(monkeypatch):
    _wire(monkeypatch,
          comments=[_comment("kibarik", "Решение: retry-only, один ключ Z.AI")],
          prs=[{"number": 2, "title": "Ingress", "state": "open",
                "url": "https://github.com/o/r/pull/2"}])

    ctx = activities._build_task_context(_analyze())

    assert "Надёжность" in ctx and "Ядро платформы." in ctx
    assert "@kibarik" in ctx and "retry-only" in ctx
    assert "#2 Ingress [open]" in ctx and "pull/2" in ctx


def test_filters_command_comments(monkeypatch):
    _wire(monkeypatch, comments=[
        _comment("kibarik", "/analyze"),
        _comment("kibarik", "/analyze разбери фазу 2"),
        _comment("dev", "Реальный комментарий по существу"),
    ])

    ctx = activities._build_task_context(_analyze())

    assert "по существу" in ctx
    assert "/analyze" not in ctx
    assert "разбери фазу 2" not in ctx


def test_truncates_long_comment(monkeypatch):
    _wire(monkeypatch, comments=[_comment("dev", "x" * 5000)])

    ctx = activities._build_task_context(_analyze())

    assert "…[обрезано]" in ctx
    assert "x" * 5000 not in ctx


def test_caps_total_and_keeps_newest(monkeypatch):
    big = "B" * 2000
    comments = [_comment("dev", f"OLD-{i}-{big}", date=f"2026-07-{10+i:02d}T00:00:00Z")
                for i in range(20)]
    comments[-1] = _comment("dev", "NEWEST-marker-" + big, date="2026-08-01T00:00:00Z")
    _wire(monkeypatch, comments=comments)

    ctx = activities._build_task_context(_analyze())

    assert len(ctx) <= activities.CONTEXT_TOTAL_CHARS
    assert "Надёжность" in ctx           # title/body неприкосновенны
    assert "NEWEST-marker" in ctx        # свежий уцелел
    assert "OLD-0-" not in ctx           # старейший отброшен


def test_degrades_to_body_only_when_comments_fetch_fails(monkeypatch):
    _wire(monkeypatch, comments_exc=RuntimeError("boom"),
          prs=[{"number": 2, "title": "Ingress", "state": "open",
                "url": "https://github.com/o/r/pull/2"}])

    ctx = activities._build_task_context(_analyze())

    assert "Ядро платформы." in ctx       # база на месте
    assert "## Обсуждение" not in ctx      # секция комментариев пропущена
    assert "#2 Ingress" in ctx            # PR-секция уцелела (независимая деградация)


def test_degrades_when_prs_fetch_fails(monkeypatch):
    _wire(monkeypatch, comments=[_comment("dev", "живой контекст")],
          prs_exc=RuntimeError("boom"))

    ctx = activities._build_task_context(_analyze())

    assert "живой контекст" in ctx
    assert "## Связанные PR" not in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_build_task_context.py -v`
Expected: FAIL — `AttributeError: module 'activities' has no attribute '_build_task_context'` (или `CONTEXT_TOTAL_CHARS`).

- [ ] **Step 3: Write minimal implementation**

3a. В `worker/activities.py` добавить `import logging` в stdlib-блок (после `import asyncio`, строка 9):

```python
import asyncio
import logging
import os
```

3b. После блока импортов (перед `PROMPTS_DIR = Path("/app/prompts")`, строка 39) добавить:

```python
logger = logging.getLogger(__name__)
```

3c. Рядом с таймаут-константами (после `HEARTBEAT_INTERVAL_SEC = 30.0`, строка 314) добавить:

```python
# Обогащение контекста /analyze (спека 2026-07-24). Двигаются без правки логики.
CONTEXT_COMMENT_LIMIT = 20      # свежих комментариев в бриф
CONTEXT_COMMENT_CHARS = 1500    # обрезка одного комментария
CONTEXT_PR_LIMIT = 20           # связанных PR
CONTEXT_TOTAL_CHARS = 16000     # потолок брифа (title+body неприкосновенны)
```

3d. Перед `async def run_analysis_pipeline` (строка 459) добавить 4 функции:

```python
def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …[обрезано]"


def _fetch_comment_blocks(analyze: AnalyzeInput) -> list[str]:
    """Свежие комментарии обсуждения (старые→свежие) без командного шума.

    Командные комментарии (`/analyze`, `/estimate` и с хвостом) отсекаются
    через parse_command — тот же разбор, что и в вебхуке. Сбой fetch → пустой
    список: анализ продолжается на title+body.
    """
    try:
        comments = github_client.list_comments(
            analyze.repo, analyze.issue_number, limit=50
        )
    except Exception as exc:  # noqa: BLE001 — деградация важнее причины сбоя
        logger.warning("list_comments failed for #%s: %s", analyze.issue_number, exc)
        return []
    kept = [c for c in comments if parse_command(c.get("body") or "") is None]
    kept = kept[-CONTEXT_COMMENT_LIMIT:]
    blocks: list[str] = []
    for c in kept:
        user = (c.get("user") or {}).get("login", "?")
        date = (c.get("created_at") or "")[:10]
        body = _truncate(c.get("body") or "", CONTEXT_COMMENT_CHARS)
        blocks.append(f"**@{user} ({date}):**\n{body}")
    return blocks


def _fetch_prs_section(analyze: AnalyzeInput) -> str:
    """Секция связанных PR. Сбой fetch → пустая строка (прогон не падает)."""
    try:
        prs = github_client.list_linked_prs(
            analyze.repo, analyze.issue_number, limit=CONTEXT_PR_LIMIT
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_linked_prs failed for #%s: %s", analyze.issue_number, exc)
        return ""
    if not prs:
        return ""
    lines = ["## Связанные PR"]
    for pr in prs:
        lines.append(f"- #{pr['number']} {pr['title']} [{pr['state']}] {pr['url']}")
    return "\n".join(lines)


def _build_task_context(analyze: AnalyzeInput) -> str:
    """Обогащённый бриф задачи для /fnr-new-task.

    Живое состояние issue (обсуждение, связанные PR) поверх title+body: тело
    issue — статичный снимок, решения и прогресс живут в комментариях и PR.
    Потолок CONTEXT_TOTAL_CHARS: title+body и компактная PR-секция
    неприкосновенны, комментарии отбрасываются от самых старых к свежим, пока
    бриф не влезает. Любой сбой fetch деградирует до title+body.
    """
    base = f"# {analyze.title}\n\n{analyze.body}".strip()
    prs = _fetch_prs_section(analyze)
    blocks = _fetch_comment_blocks(analyze)

    reserved = len(base) + (len(prs) + 2 if prs else 0)
    budget = CONTEXT_TOTAL_CHARS - reserved
    while blocks:
        section = "## Обсуждение\n" + "\n\n".join(blocks)
        if len(section) <= budget:
            break
        blocks = blocks[1:]  # выкинуть старейший комментарий
    comments = "## Обсуждение\n" + "\n\n".join(blocks) if blocks else ""

    parts = [base]
    if comments:
        parts.append(comments)
    if prs:
        parts.append(prs)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_build_task_context.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_build_task_context.py
git commit -m "feat(activities): _build_task_context — comments + linked PRs

Бриф /fnr-new-task поверх title+body: свежие комментарии (фильтр командного
шума через parse_command, обрезка, потолок с отбросом старейших) и связанные
PR. Каждый fetch деградирует независимо до title+body.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Проводка в пайплайн + фикс фикстуры

Заменить статичный `description` на обогащённый; починить существующие тесты пайплайна (иначе полезут в реальный HTTP) и доказать, что контекст доходит до стадии `task`.

**Files:**
- Modify: `worker/activities.py:487`
- Modify: `tests/test_analysis_pipeline.py` (фикстура `wired` + новый тест проводки)

**Interfaces:**
- Consumes: `activities._build_task_context` (Task 2).
- Produces: обогащённый `description`, уходящий в `/fnr-new-task {description}` (первая стадия FNR).

- [ ] **Step 1: Write the failing test + patch fixture**

1a. В `tests/test_analysis_pipeline.py`, в фикстуру `wired` (после подмены `_run_claude`, ~строка 53) добавить стабы клиента:

```python
    monkeypatch.setattr(activities.github_client, "list_comments",
                        lambda repo, n, limit=50: [])
    monkeypatch.setattr(activities.github_client, "list_linked_prs",
                        lambda repo, n, limit=20: [])
```

1b. В конец `tests/test_analysis_pipeline.py` добавить тест проводки:

```python
def test_enriched_context_reaches_task_stage(monkeypatch, wired):
    """Контекст обсуждения обязан долетать до стадии /fnr-new-task, а не
    оставаться в title+body."""
    monkeypatch.setattr(
        activities.github_client, "list_comments",
        lambda repo, n, limit=50: [
            {"user": {"login": "kibarik"},
             "body": "Зафиксировано: retry-only",
             "created_at": "2026-07-20T10:00:00Z"}
        ],
    )
    prompts = {}

    def capture(prompt, cwd):
        stage = prompt.split()[0]
        prompts[stage] = prompt
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        produced = {
            "/fnr-new-task": "task.md",
            "/fnr-concept": "concept.md",
            "/fnr-system-requirements": "system_requirements.md",
            "/validate-doc": "validation.md",
        }.get(stage)
        if produced:
            (fnr / produced).write_text(f"# {produced}", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", capture)

    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert "Зафиксировано: retry-only" in prompts["/fnr-new-task"]
    assert prompts["/fnr-new-task"].startswith("/fnr-new-task")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_enriched_context_reaches_task_stage -v`
Expected: FAIL — `KeyError: '/fnr-new-task'` в `prompts` не будет содержать текст коммента (или `AssertionError`), т.к. `run_analysis_pipeline` ещё шлёт статичный `title+body`.

- [ ] **Step 3: Wire the helper**

В `worker/activities.py` заменить строку 487:

```python
        description = f"{analyze.title}\n\n{analyze.body}"
```

на:

```python
        description = await asyncio.to_thread(_build_task_context, analyze)
```

(Вынос в поток: `_build_task_context` делает блокирующие REST-вызовы, а `run_analysis_pipeline` крутится на event loop — как и остальные блокирующие вызовы в этой activity.)

- [ ] **Step 4: Run the new test + full pipeline suite**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest tests/test_analysis_pipeline.py -v`
Expected: PASS (все прежние тесты + `test_enriched_context_reaches_task_stage`).

- [ ] **Step 5: Run full suite (regression)**

Run: `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q`
Expected: PASS — 164 прежних + 10 новых (3 Task 1 + 6 Task 2 + 1 Task 3) = 174 passed.

- [ ] **Step 6: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(activities): feed enriched context into /analyze pipeline

run_analysis_pipeline берёт _build_task_context вместо статичного title+body;
фикстура wired стабит fetch-клиенты, новый тест доказывает, что комментарии
долетают до стадии /fnr-new-task.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Комментарии (фильтр шума, обрезка, потолок) → Task 2 (`_fetch_comment_blocks`, `_build_task_context`) ✓
- Связанные PR → Task 1 (`list_linked_prs`) + Task 2 (`_fetch_prs_section`) ✓
- Деградация на сбое fetch → Task 2 (try/except в обоих fetch-хелперах, тесты `test_degrades_*`) ✓
- Потолок 16 КБ, отброс старейших, title+body неприкосновенны → Task 2 (`test_caps_total_and_keeps_newest`) ✓
- Формат инлайн в `/fnr-new-task`, префикс цел → Task 3 (`test_enriched_context_reaches_task_stage`) ✓
- Фикс фикстуры `wired` (реальный HTTP) → Task 3 step 1a ✓
- `list_linked_prs` фильтрует issue-ссылки, дедуп, limit → Task 1 тесты ✓

**Placeholder scan:** нет TBD/TODO/«add error handling» — весь код и все команды приведены. ✓

**Type consistency:** `list_linked_prs(repo, issue_number, limit=20) -> list[dict]{number,title,state,url}` — одинаково в Task 1 (определение), Task 2 (`_fetch_prs_section` читает `pr['number']/title/state/url`), тестах. `_build_task_context(analyze) -> str` согласован в Task 2/3. Константы `CONTEXT_*` заданы в Task 2 step 3c, используются там же и в тесте Task 2. ✓
