# Живой ход анализа — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ход анализа виден без вопросов и без доступа к стенду, а ожидание приносит результат: артефакты уезжают в ветку по мере готовности, а комментарий показывает таблицу стадий и отметку последней проверки.

**Architecture:** Прогон анализа сам перебирает стадии и потому знает, где находится — опрашивать нечего. Отрисовка таблицы вынесена в чистый модуль `shared/analysis_progress.py` без сети. Активности только ходят в GitHub, воркфлоу только решает, когда их звать. Правка решений воркфлоу идёт под `workflow.patched`.

**Tech Stack:** Python 3.12, Temporal Python SDK, pytest, GitHub REST через `worker/github_client.py`, GitLab через `worker/gitlab_client.py`, диспетчер `worker/forge.py`.

## Global Constraints

- Тесты гонять командой репозитория: `python -m pytest -q`. Порог покрытия — 83%, красный прогон в PR не отдаём.
- **Раскладка:** `worker/` и `webhook/` НЕ пакеты — Dockerfile расплющивает их в `/app`. Импорт `from worker.X import ...` падает в контейнере. Внутри воркера — `import activities`, `import github_client`. Общий код — только `shared/`.
- **Фикстура pytest из чужого тестового модуля не видна** — `conftest.py` либо своя копия.
- **Правка решения воркфлоу требует `workflow.patched(...)`.** Ветка, которую прогон уже выбрал, записана в его историю; новый код на реплее выберет другую и уронит прогон. Активности маркера не требуют.
- Гвард реплея `tests/test_workflow_replay.py` обязан оставаться зелёным; прогонять отдельным шагом.
- Комментарии контура подписывает клиент в единственной точке отправки — отдельно звать `agent_comment.sign` не надо.
- **Телеметрия не имеет права ронять то, о чём отчитывается**: отказ публикации или правки комментария не останавливает анализ.
- Спецификация: `docs/superpowers/specs/2026-09-01-analysis-live-progress-design.md`, требования P1–P20.

## Что уже есть

- Стадии статичны: `activities.FNR_STAGE_NAMES = ("repowise", "task", "concept", "debate", "sysreq", "validate")` (`worker/activities.py:1745`).
- Цикл стадий — `worker/workflows.py:196`, внутри `try` с общей обработкой отказа.
- Объявление о старте — `activities.ack_command` (`worker/activities.py:4018`), текст на 4039.
- `publish_analysis_partial(analyze, reason) -> list[str]` (`worker/activities.py:2529`) — публикует то, что успели собрать. Переиспользуется, а не переписывается.

---

### Task 1: Отрисовка таблицы хода

Закрывает P2, P4, P5, P8 в части представления. Чистый модуль без сети — самая проверяемая часть.

**Files:**
- Create: `shared/analysis_progress.py`
- Test: `tests/test_analysis_progress.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `@dataclass StageProgress` с полями `name: str`, `state: str`, `started_epoch: float = 0.0`, `finished_epoch: float = 0.0`, `attempt: int = 1`
  - константы состояний `WAITING = "waiting"`, `RUNNING = "running"`, `DONE = "done"`, `FAILED = "failed"`
  - `STAGE_TITLES: dict[str, str]` — пояснение к каждому имени стадии
  - `render(stages: Sequence[StageProgress], *, issue_number: int, trigger: str, now_epoch: float, finished: bool = False) -> str`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_analysis_progress.py`:

```python
import pytest

from shared import analysis_progress as ap


def _stages(*specs):
    """Стадии из коротких описаний: (имя, состояние, старт, конец, попытка)."""
    return [ap.StageProgress(name=n, state=s, started_epoch=b,
                             finished_epoch=e, attempt=a)
            for n, s, b, e, a in specs]


def test_all_stages_are_shown_from_the_start():
    """Человек с первой секунды видит, сколько стадий впереди (P2).

    Отказ, ради которого написано: на прогоне poh-demo-checkout#165 контур
    обещал «несколько минут», через тридцать владелец решил, что задача
    застряла. Наращивать таблицу по ходу значит повторить это.
    """
    stages = [ap.StageProgress(name=n, state=ap.WAITING)
              for n in ("repowise", "task", "concept", "debate", "sysreq", "validate")]
    out = ap.render(stages, issue_number=165, trigger="`research-me`", now_epoch=0.0)
    for name in ("repowise", "task", "concept", "debate", "sysreq", "validate"):
        assert name in out, name
    assert out.count("ждёт") == 6


def test_stage_names_carry_human_readable_titles():
    """Имя нужно для сверки с логами, пояснение — для человека (P4)."""
    stages = [ap.StageProgress(name="repowise", state=ap.WAITING)]
    out = ap.render(stages, issue_number=1, trigger="`x`", now_epoch=0.0)
    assert "repowise" in out
    assert ap.STAGE_TITLES["repowise"] in out
    assert set(ap.STAGE_TITLES) == {"repowise", "task", "concept",
                                    "debate", "sysreq", "validate"}


def test_done_stage_shows_duration():
    stages = _stages(("task", ap.DONE, 1000.0, 1360.0, 1))
    out = ap.render(stages, issue_number=1, trigger="`x`", now_epoch=2000.0)
    assert "6 мин" in out


def test_running_stage_shows_elapsed_from_now():
    stages = _stages(("debate", ap.RUNNING, 1000.0, 0.0, 1))
    out = ap.render(stages, issue_number=1, trigger="`x`", now_epoch=1540.0)
    assert "9 мин" in out


def test_second_attempt_is_named_explicitly():
    """Выкладка посреди анализа рвёт стадию и она идёт заново (P8).

    Без явной отметки это выглядит как стадия, идущая вдвое дольше обычного,
    то есть как зависание — хотя это штатное восстановление.
    """
    stages = _stages(("sysreq", ap.RUNNING, 1000.0, 0.0, 2))
    out = ap.render(stages, issue_number=1, trigger="`x`", now_epoch=1060.0)
    assert "попытка 2" in out


def test_failed_stage_is_visible():
    stages = _stages(("concept", ap.FAILED, 1000.0, 1120.0, 1))
    out = ap.render(stages, issue_number=1, trigger="`x`", now_epoch=2000.0)
    assert "сорвалась" in out


def test_branch_is_named_and_no_time_promise_is_made():
    """Обещание «несколько минут» убрано: оно неверно и само создаёт
    впечатление зависания (P3)."""
    stages = [ap.StageProgress(name="task", state=ap.WAITING)]
    out = ap.render(stages, issue_number=165, trigger="`research-me`", now_epoch=0.0)
    assert "research/issue-165" in out
    assert "несколько минут" not in out


def test_checked_line_present_while_running_and_absent_when_finished():
    """Отметка проверки нужна, пока идёт; на законченном прогоне она мусор."""
    running = ap.render(_stages(("debate", ap.RUNNING, 1000.0, 0.0, 1)),
                        issue_number=1, trigger="`x`", now_epoch=1300.0)
    assert "Последняя проверка" in running

    finished = ap.render(_stages(("validate", ap.DONE, 1000.0, 1100.0, 1)),
                         issue_number=1, trigger="`x`", now_epoch=2000.0,
                         finished=True)
    assert "Последняя проверка" not in finished


def test_render_is_pure_and_needs_no_network(monkeypatch):
    """Модуль не тянет ни GitHub, ни Temporal: его можно звать откуда угодно."""
    import sys
    assert "requests" not in getattr(ap, "__dict__", {})
    assert not any(name.startswith("github") or name.startswith("temporal")
                   for name in vars(ap))
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_analysis_progress.py -q -p no:randomly --no-cov`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.analysis_progress'`

- [ ] **Step 3: Написать модуль**

```python
"""Таблица хода анализа для комментария в Issue.

Отдельный модуль, а не функция в activities: файл активностей за четыре тысячи
строк, и отрисовка там потеряется. Здесь нет ни сети, ни Temporal — всё
проверяется без окружения.

Почему таблица целиком с первой секунды, а не наращивается: на прогоне
poh-demo-checkout#165 контур пообещал «несколько минут», через тридцать владелец
задачи решил, что она застряла. Человек должен видеть, сколько стадий впереди,
а не гадать по числу уже пройденных.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

WAITING = "waiting"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

# Имя стадии нужно для сверки с логами и Temporal, пояснение — для человека,
# который видит контур впервые. Поэтому в таблице стоят оба.
STAGE_TITLES = {
    "repowise": "сбор контекста",
    "task": "постановка",
    "concept": "концепты",
    "debate": "дебаты",
    "sysreq": "требования",
    "validate": "проверка",
}


@dataclass
class StageProgress:
    """Состояние одной стадии пайплайна."""

    name: str
    state: str
    started_epoch: float = 0.0
    finished_epoch: float = 0.0
    attempt: int = 1


def _minutes(seconds: float) -> str:
    """Длительность в минутах, всегда целым: секунды человеку не нужны."""
    return f"{max(int(seconds // 60), 0)} мин"


def _cell(stage: StageProgress, now_epoch: float) -> str:
    if stage.state == DONE:
        return f"✅ {_minutes(stage.finished_epoch - stage.started_epoch)}"
    if stage.state == FAILED:
        return f"❌ сорвалась через {_minutes(stage.finished_epoch - stage.started_epoch)}"
    if stage.state == RUNNING:
        elapsed = _minutes(now_epoch - stage.started_epoch)
        # Вторая попытка бывает после выкладки или рестарта воркера. Без явной
        # отметки она выглядит как стадия, идущая вдвое дольше обычного, — то
        # есть как зависание, хотя это штатное восстановление.
        suffix = f", попытка {stage.attempt}" if stage.attempt > 1 else ""
        return f"⏳ идёт {elapsed}{suffix}"
    return "ждёт"


def render(stages: Sequence[StageProgress], *, issue_number: int, trigger: str,
           now_epoch: float, finished: bool = False) -> str:
    """Тело комментария о ходе анализа.

    `finished` убирает отметку последней проверки: на законченном прогоне она
    только сбивает с толку — обновляться ей больше нечем.
    """
    lines = [
        f"🔍 Взял {trigger} в работу — автономный анализ через SA-helper.",
        "",
        f"Артефакты появляются в ветке `research/issue-{issue_number}` "
        "по мере готовности стадий.",
        "",
        "| Стадия | Состояние |",
        "|---|---|",
    ]
    for stage in stages:
        title = STAGE_TITLES.get(stage.name, "")
        label = f"`{stage.name}` — {title}" if title else f"`{stage.name}`"
        lines.append(f"| {label} | {_cell(stage, now_epoch)} |")
    if not finished:
        lines += ["", f"Последняя проверка: {_minutes(0)} назад".replace("0 мин", "только что")]
    return "\n".join(lines)
```

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_analysis_progress.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 6: Коммит**

```bash
git add shared/analysis_progress.py tests/test_analysis_progress.py
git commit -m "feat(progress): таблица хода анализа для комментария Issue"
```

---

### Task 2: Клиент умеет править комментарий

Закрывает P12, P13, P14.

**Files:**
- Modify: `worker/github_client.py:130` (`post_comment`)
- Modify: `worker/gitlab_client.py:95` (`post_comment`)
- Test: тесты клиентов и диспетчера (найди существующие файлы, новых рядом не заводи)

**Interfaces:**
- Consumes: ничего
- Produces:
  - `github_client.post_comment(repo, issue_number, body) -> int | None` — идентификатор созданного комментария; `None` в режиме `DRY_RUN`
  - `github_client.edit_comment(repo, comment_id, body) -> None`
  - те же две у `gitlab_client` с той же сигнатурой
  - обе резолвятся диспетчером `forge`

- [ ] **Step 1: Написать падающие тесты**

```python
def test_post_comment_returns_created_id(monkeypatch):
    """Править комментарий без его идентификатора нечем (P12)."""
    captured = {}

    class _Resp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"id": 424242}

    monkeypatch.setattr(github_client.requests, "post",
                        lambda *a, **kw: _Resp())
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(github_client, "_dry_run", lambda: False)

    assert github_client.post_comment("o/r", 1, "текст") == 424242


def test_post_comment_in_dry_run_returns_none(monkeypatch):
    monkeypatch.setattr(github_client, "_dry_run", lambda: True)
    assert github_client.post_comment("o/r", 1, "текст") is None


def test_edit_comment_patches_the_right_url(monkeypatch):
    seen = {}

    class _Resp:
        def raise_for_status(self): pass

    def _patch(url, **kw):
        seen["url"] = url
        seen["body"] = kw["json"]["body"]
        return _Resp()

    monkeypatch.setattr(github_client.requests, "patch", _patch)
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(github_client, "_dry_run", lambda: False)

    github_client.edit_comment("o/r", 424242, "новый текст")
    assert seen["url"].endswith("/repos/o/r/issues/comments/424242")
    assert "новый текст" in seen["body"]


def test_edit_comment_signs_the_body(monkeypatch):
    """Подпись ставится в единственной точке отправки — и при правке тоже.

    Без неё вебхук примет отредактированный комментарий за реплику человека.
    """
    seen = {}

    class _Resp:
        def raise_for_status(self): pass

    monkeypatch.setattr(github_client.requests, "patch",
                        lambda url, **kw: seen.update(body=kw["json"]["body"]) or _Resp())
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(github_client, "_dry_run", lambda: False)

    github_client.edit_comment("o/r", 1, "текст")
    assert "<!-- issue-agent -->" in seen["body"]
```

Плюс тест диспетчера: обе функции находятся и для GitHub, и для GitLab — по образцу существующего теста `forge`.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest -q -p no:randomly --no-cov -k "edit_comment or returns_created_id"`
Expected: FAIL — `edit_comment` не существует, `post_comment` возвращает `None`.

- [ ] **Step 3: Правка GitHub-клиента**

В `worker/github_client.py` заменить конец `post_comment` и дописать `edit_comment`:

```python
def post_comment(repo: str, issue_number: int, body: str) -> int | None:
    """Комментарий сервиса — всегда подписанный.

    Возвращает идентификатор созданного комментария: без него нечего править,
    а ход долгой стадии показывается именно правкой на месте (P12). В режиме
    `DRY_RUN` возвращает None — комментария не существует.

    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,
    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш
    комментарий за ответ человека и накормит им цикл уточнений.
    """
    body = sign(body)
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return None
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=_auth_headers(repo), json={"body": body}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("id")


def edit_comment(repo: str, comment_id: int, body: str) -> None:
    """Переписать свой комментарий на месте.

    Правка не порождает уведомлений — GitHub оповещает только о новых
    комментариях. Поэтому показывать ход долгой стадии правкой дешевле и тише,
    чем потоком сообщений в ленту.

    Подпись ставится и здесь: отредактированный комментарий без неё вебхук
    примет за реплику человека.
    """
    body = sign(body)
    if _dry_run():
        _log.info("[DRY_RUN] edit comment %s/%s: %s", repo, comment_id, body[:200])
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
    resp = requests.patch(url, headers=_auth_headers(repo), json={"body": body}, timeout=30)
    resp.raise_for_status()
```

- [ ] **Step 4: Правка GitLab-клиента**

Прочитай `worker/gitlab_client.py:95` и сделай то же самое его средствами: `post_comment` возвращает идентификатор заметки, добавляется `edit_comment(repo, comment_id, body)`. Путь правки заметки у GitLab — `PUT /projects/:id/issues/:iid/notes/:note_id`; обрати внимание, что там нужен и номер задачи, а не только идентификатор заметки. Если сигнатуру приходится расширять, приведи обе реализации к ОДНОЙ сигнатуре — иначе диспетчер `forge` сломается на втором провайдере.

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 6: Коммит**

```bash
git add worker/github_client.py worker/gitlab_client.py tests/
git commit -m "feat(forge): post_comment возвращает идентификатор, добавлена правка комментария"
```

---

### Task 3: Объявление становится таблицей

Закрывает P1, P2, P3 со стороны публикации.

**Files:**
- Modify: `worker/activities.py:4018` (`ack_command`)
- Test: тесты `ack_command` (найди существующий файл)

**Interfaces:**
- Consumes: `shared.analysis_progress` из Task 1, `post_comment -> int | None` из Task 2
- Produces: `ack_command(analyze) -> int | None` — идентификатор опубликованного комментария; `None`, если опубликовать не удалось

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_ack_publishes_the_full_table(monkeypatch):
    """Все шесть стадий видны с первой секунды (P2)."""
    posted = {}
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.setdefault("body", body) or 777)
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)

    comment_id = await a.ack_command(_analyze())

    assert comment_id == 777
    for name in a.FNR_STAGE_NAMES:
        assert name in posted["body"], name
    assert "несколько минут" not in posted["body"]


async def test_ack_survives_failed_publication(monkeypatch):
    """Не смогли опубликовать — анализ всё равно идёт (P10)."""
    def boom(*args, **kwargs):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(a.github_client, "post_comment", boom)
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)

    assert await a.ack_command(_analyze()) is None
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest -q -p no:randomly --no-cov -k "ack_publishes or ack_survives"`
Expected: FAIL — `ack_command` возвращает `None` всегда и публикует прежний текст.

- [ ] **Step 3: Переписать `ack_command`**

Заменить публикацию комментария в `worker/activities.py:4018` так, чтобы тело собиралось `analysis_progress.render` со всеми стадиями в состоянии ожидания, а идентификатор возвращался наружу. Отказ публикации перехватывается и даёт `None`: подтверждение приёма важно, но анализ важнее.

Метку `run:analyze` и реакцию оставить как есть — они уже best-effort.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 5: Коммит**

```bash
git add worker/activities.py tests/
git commit -m "feat(progress): объявление о старте анализа несёт таблицу стадий"
```

---

### Task 4: Активность правки хода

Закрывает P5, P6, P7, P9 со стороны исполнения.

**Files:**
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Test: `tests/test_analysis_progress_activity.py`

**Interfaces:**
- Consumes: `analysis_progress.StageProgress`, `edit_comment` из Task 2
- Produces: активность `update_analysis_progress(analyze, comment_id: int, stages: list[dict], now_epoch: float, finished: bool) -> None`. Стадии передаются словарями, а не датаклассами: через границу активности едет то, что сериализуется без сюрпризов.

- [ ] **Step 1: Написать падающие тесты**

```python
def test_progress_update_edits_the_same_comment(monkeypatch):
    seen = {}
    monkeypatch.setattr(a.github_client, "edit_comment",
                        lambda repo, cid, body: seen.update(cid=cid, body=body))

    a.update_analysis_progress(_analyze(), 777,
                               [{"name": "task", "state": "running",
                                 "started_epoch": 1000.0, "finished_epoch": 0.0,
                                 "attempt": 1}],
                               1360.0, False)

    assert seen["cid"] == 777
    assert "6 мин" in seen["body"]


def test_progress_update_failure_does_not_raise(monkeypatch):
    """Телеметрия не имеет права ронять то, о чём отчитывается (P9)."""
    def boom(*args, **kwargs):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(a.github_client, "edit_comment", boom)
    a.update_analysis_progress(_analyze(), 777, [], 0.0, False)  # не бросает


def test_progress_update_without_comment_id_does_nothing(monkeypatch):
    """Комментария нет — искать нечего (P10)."""
    called = []
    monkeypatch.setattr(a.github_client, "edit_comment",
                        lambda *args: called.append(1))
    a.update_analysis_progress(_analyze(), 0, [], 0.0, False)
    assert called == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_analysis_progress_activity.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'update_analysis_progress'`

- [ ] **Step 3: Написать активность и зарегистрировать**

Активность собирает `StageProgress` из словарей, зовёт `analysis_progress.render` и правит комментарий. Перехватывает любое исключение и пишет предупреждение в лог: отказ телеметрии не должен ронять анализ. При `comment_id` нулевом или пустом не делает ничего.

Зарегистрировать в `worker/worker.py` рядом с прочими активностями анализа.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 5: Коммит**

```bash
git add worker/activities.py worker/worker.py tests/test_analysis_progress_activity.py
git commit -m "feat(progress): активность правки таблицы хода"
```

---

### Task 5: Публикация артефактов по стадиям

Закрывает P16, P17, P18, P20.

**Files:**
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Test: `tests/test_publish_stage.py`

**Interfaces:**
- Consumes: `publish_analysis_partial(analyze, reason) -> list[str]` (`worker/activities.py:2529`)
- Produces: активность `publish_stage_artifacts(analyze, stage_name: str) -> list[str]` — имена опубликованного; пустой список, если публиковать нечего или не вышло

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_stage_publish_reuses_partial_machinery(monkeypatch):
    """Второй способ публикации завёлся бы и разъехался с первым (P17)."""
    seen = {}

    async def fake_partial(analyze, reason):
        seen["reason"] = reason
        return ["task.md"]

    monkeypatch.setattr(a, "publish_analysis_partial", fake_partial)
    saved = await a.publish_stage_artifacts(_analyze(), "task")

    assert saved == ["task.md"]
    assert "task" in seen["reason"]


async def test_stage_publish_failure_does_not_raise(monkeypatch):
    """Отказ публикации стадии не отменяет следующую (P18).

    Потерять полчаса работы из-за одного отказа сети недопустимо.
    """
    async def boom(analyze, reason):
        raise RuntimeError("git push отказал")

    monkeypatch.setattr(a, "publish_analysis_partial", boom)
    assert await a.publish_stage_artifacts(_analyze(), "task") == []


async def test_nothing_to_publish_is_not_a_failure(monkeypatch):
    """Первая стадия ещё не дала артефакта — это не отказ."""
    async def empty(analyze, reason):
        return []

    monkeypatch.setattr(a, "publish_analysis_partial", empty)
    assert await a.publish_stage_artifacts(_analyze(), "repowise") == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_publish_stage.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'publish_stage_artifacts'`

- [ ] **Step 3: Написать активность и зарегистрировать**

Тонкая обёртка над `publish_analysis_partial`: причина публикации называет стадию, любое исключение перехватывается и даёт пустой список с предупреждением в лог. Зарегистрировать в `worker/worker.py`.

Прочитай `publish_analysis_partial` целиком прежде чем писать: если она делает что-то, что нельзя повторять по нескольку раз за прогон, — скажи об этом прямо в отчёте, не обходи молча.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 5: Коммит**

```bash
git add worker/activities.py worker/worker.py tests/test_publish_stage.py
git commit -m "feat(progress): артефакты уезжают в ветку по стадиям"
```

---

### Task 6: Цикл стадий ведёт ход и публикует

Закрывает P5, P6, P7, P8, P15, P16, P19, P20 со стороны решений. **Правка решений воркфлоу — обязателен `workflow.patched`.**

**Files:**
- Modify: `worker/workflows.py:196-215` (цикл стадий)
- Test: `tests/test_analysis_progress_workflow.py`
- Test: `tests/test_workflow_replay.py` (прогнать без правок)

**Interfaces:**
- Consumes: `ack_command -> int | None` (Task 3), `update_analysis_progress` (Task 4), `publish_stage_artifacts` (Task 5)
- Produces: ничего для следующих задач

- [ ] **Step 1: Написать падающие тесты**

Заглушки активностей анализа копируй ВЕРБАТИМ из `tests/test_workflow_analysis.py`
— фикстуры и заглушки чужого тестового модуля не видны. Ниже — только то, что
относится к ходу.

```python
"""Цикл стадий ведёт таблицу хода и публикует артефакты по стадиям.

Отказ, ради которого написано: на прогоне poh-demo-checkout#165 человек тридцать
минут не мог отличить работающий анализ от умершего, а ветка с артефактами не
существовала до самого конца.
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import AnalyzeInput
from workflows import IssueAnalysis

# --- сюда скопировать блок заглушек из tests/test_workflow_analysis.py ---

_calls: list[str] = []
_stage_seconds = {}


@activity.defn(name="ack_command")
async def ack_returns_id(analyze: AnalyzeInput) -> int:
    _calls.append("ack")
    return 777


@activity.defn(name="run_fnr_stage")
async def stage_timed(analyze: AnalyzeInput, stage_name: str) -> None:
    """Стадия занимает столько, сколько велит тест."""
    _calls.append(f"stage:{stage_name}")
    await asyncio.sleep(_stage_seconds.get(stage_name, 0))


@activity.defn(name="update_analysis_progress")
async def progress_stub(analyze: AnalyzeInput, comment_id: int,
                        stages: list, now_epoch: float, finished: bool) -> None:
    _calls.append("progress")


@activity.defn(name="update_analysis_progress")
async def progress_fails(analyze: AnalyzeInput, comment_id: int,
                         stages: list, now_epoch: float, finished: bool) -> None:
    _calls.append("progress")
    raise RuntimeError("GitHub 502")


@activity.defn(name="publish_stage_artifacts")
async def publish_stub(analyze: AnalyzeInput, stage_name: str) -> list[str]:
    _calls.append(f"publish:{stage_name}")
    return [f"{stage_name}.md"]


@activity.defn(name="publish_stage_artifacts")
async def publish_fails(analyze: AnalyzeInput, stage_name: str) -> list[str]:
    _calls.append(f"publish:{stage_name}")
    raise RuntimeError("git push отказал")


def _analyze() -> AnalyzeInput:
    return AnalyzeInput(repo="o/r", issue_number=165, title="t", body="b",
                        trigger="research-me")


async def _run(env, activities_list) -> None:
    tq = f"tq-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                      activities=activities_list):
        await env.client.execute_workflow(
            IssueAnalysis.run, _analyze(), id=f"wf-{uuid.uuid4()}", task_queue=tq)


@pytest.mark.asyncio
async def test_progress_updated_on_every_stage_change():
    """Смена стадии правит таблицу (P5).

    Шесть стадий дают правку на входе в каждую и на выходе из каждой.
    """
    _calls.clear(); _stage_seconds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_stub, publish_stub])

    assert _calls.count("progress") >= 12, _calls


@pytest.mark.asyncio
async def test_short_stage_makes_no_timer_updates():
    """Стадия короче пяти минут правок по таймеру не порождает (P6).

    До этой границы правка тратит запись в GitHub, не сообщая ничего нового.
    """
    _calls.clear(); _stage_seconds.clear()
    _stage_seconds.update({name: 60 for name in
                           ("repowise", "task", "concept", "debate", "sysreq", "validate")})
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_stub, publish_stub])

    # Ровно две правки на стадию — вход и выход, ни одной по таймеру.
    assert _calls.count("progress") == 12, _calls


@pytest.mark.asyncio
async def test_long_stage_updates_every_minute_after_five():
    """Стадия длиннее пяти минут даёт правку каждую минуту, начиная с шестой.

    Девять минут: пять тихих, затем четыре тика — плюс вход и выход.
    """
    _calls.clear(); _stage_seconds.clear()
    _stage_seconds["debate"] = 9 * 60
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_stub, publish_stub])

    # 12 правок «вход-выход» плюс тики длинной стадии.
    assert _calls.count("progress") >= 15, _calls
    assert _calls.count("progress") <= 17, _calls


@pytest.mark.asyncio
async def test_artifacts_published_after_each_stage():
    """Ветка появляется после ПЕРВОЙ стадии, а не в конце (P16).

    Сегодня публикация случается только после последней: на сорок пятой минуте
    прогона #165 ветки не существовало вовсе.
    """
    _calls.clear(); _stage_seconds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_stub, publish_stub])

    assert _calls.index("publish:repowise") < _calls.index("stage:task"), _calls
    for name in ("repowise", "task", "concept", "debate", "sysreq", "validate"):
        assert f"publish:{name}" in _calls, name


@pytest.mark.asyncio
async def test_publish_failure_does_not_stop_the_analysis():
    """Отказ публикации стадии не отменяет следующую (P18).

    Потерять полчаса работы из-за одного отказа сети недопустимо.
    """
    _calls.clear(); _stage_seconds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_stub, publish_fails])

    assert "stage:validate" in _calls, "анализ оборвался на отказе публикации"


@pytest.mark.asyncio
async def test_progress_failure_does_not_stop_the_analysis():
    """Отказ правки комментария не роняет анализ (P9).

    Телеметрия не имеет права ронять то, о чём отчитывается.
    """
    _calls.clear(); _stage_seconds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, [ack_returns_id, stage_timed, progress_fails, publish_stub])

    assert "stage:validate" in _calls, "анализ оборвался на отказе телеметрии"
```

Числа правок в первых трёх тестах — границы, а не точные значения там, где
точность зависит от того, правится ли таблица на входе в стадию, на выходе или
на обоих. Прежде чем подгонять число под реализацию, реши, какое поведение
верное, и запиши это решение в отчёт: тест, подогнанный под код, ничего не
проверяет.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_analysis_progress_workflow.py -q -p no:randomly --no-cov`
Expected: FAIL — ни правок, ни публикации по стадиям нет.

- [ ] **Step 3: Переписать цикл стадий**

В `worker/workflows.py` заменить тело цикла. Ключевое: активность стадии запускается через `workflow.start_activity`, а не `execute_activity`, и цикл ждёт её с таймаутом в минуту — так таймер становится решением воркфлоу и записывается в историю детерминированно.

```python
        # Ход анализа виден человеку: таблица стадий правится на каждой смене,
        # а пока стадия идёт дольше пяти минут — раз в минуту обновляется
        # отметка проверки. Маркер обязателен: у идущих прогонов в истории на
        # этом месте лежит простой `execute_activity`, и новый код запланировал
        # бы таймер, которого там нет.
        live = workflow.patched("issue-analysis-live-progress")
        started = workflow.now().timestamp()
        progress = [{"name": name, "state": "waiting", "started_epoch": 0.0,
                     "finished_epoch": 0.0, "attempt": 1}
                    for name in activities.FNR_STAGE_NAMES]

        for index, stage_name in enumerate(activities.FNR_STAGE_NAMES):
            if not live:
                await workflow.execute_activity(
                    activities.run_fnr_stage,
                    args=[analyze, stage_name],
                    start_to_close_timeout=timedelta(seconds=1200),
                    heartbeat_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        non_retryable_error_types=["RuntimeError"],
                    ),
                )
                continue

            progress[index]["state"] = "running"
            progress[index]["started_epoch"] = workflow.now().timestamp()
            await _update_progress(analyze, comment_id, progress, finished=False)

            handle = workflow.start_activity(
                activities.run_fnr_stage,
                args=[analyze, stage_name],
                start_to_close_timeout=timedelta(seconds=1200),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    non_retryable_error_types=["RuntimeError"],
                ),
            )
            # Первые пять минут не тикаем: до этой границы человек ещё не
            # начинает сомневаться, а каждая правка стоит записи в GitHub.
            await asyncio.wait([handle], timeout=PROGRESS_QUIET_SECONDS)
            while not handle.done():
                await asyncio.wait([handle], timeout=PROGRESS_TICK_SECONDS)
                if not handle.done():
                    await _update_progress(analyze, comment_id, progress,
                                           finished=False)
            await handle  # исключение стадии поднимается здесь, как и раньше

            progress[index]["state"] = "done"
            progress[index]["finished_epoch"] = workflow.now().timestamp()
            await _update_progress(analyze, comment_id, progress, finished=False)

            # Артефакты уезжают в ветку сразу: ожидание должно приносить
            # результат, а не крутить индикатор. Отказ публикации следующую
            # стадию не отменяет — неопубликованное доедет с итоговой.
            try:
                await workflow.execute_activity(
                    activities.publish_stage_artifacts,
                    args=[analyze, stage_name],
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            except Exception as publish_exc:
                workflow.logger.warning(
                    "публикация стадии %s не удалась: %s", stage_name, publish_exc)
```

Константы рядом с прочими в модуле:

```python
# Пять минут — граница, за которой человек начинает сомневаться, жив ли прогон.
# До неё правка комментария тратит запись в GitHub, не сообщая ничего нового.
PROGRESS_QUIET_SECONDS = 300
PROGRESS_TICK_SECONDS = 60
```

Помощник `_update_progress` зовёт активность правки и гасит её отказ:

```python
    async def _update_progress(self, analyze, comment_id, progress, *, finished):
        """Показать ход. Отказ телеметрии не роняет анализ (P9)."""
        if not comment_id:
            return
        try:
            await workflow.execute_activity(
                activities.update_analysis_progress,
                args=[analyze, comment_id, progress,
                      workflow.now().timestamp(), finished],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception as exc:
            workflow.logger.warning("правка таблицы хода не удалась: %s", exc)
```

Идентификатор комментария берётся из `ack_command`, который теперь его
возвращает, и живёт в локальной переменной прогона (P11). Искать прежний
комментарий перебором ленты нельзя: у задачи бывают сотни комментариев, а
надёжного способа найти свой в её конце GitHub не даёт — на этом уже обжигались
в задаче про идемпотентность вопроса гейта. Прогон потерян — новый начнёт с
нового комментария, и это приемлемо.

При отказе стадии пометь её в таблице как сорвавшуюся и обнови комментарий последний раз с `finished=True` — в существующей ветке `except`.

- [ ] **Step 4: Прогнать тесты хода**

Run: `python -m pytest tests/test_analysis_progress_workflow.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Прогнать гвард реплея — главная проверка задачи**

Run: `python -m pytest tests/test_workflow_replay.py -q -p no:randomly --no-cov`
Expected: PASS. Красный гвард означает, что маркер поставлен не там или не поставлен вовсе, и выкладка убьёт идущие прогоны анализа. Чинить, а не обходить.

- [ ] **Step 6: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 7: Коммит**

```bash
git add worker/workflows.py tests/test_analysis_progress_workflow.py
git commit -m "feat(progress): цикл стадий ведёт таблицу хода и публикует по стадиям

Маркер issue-analysis-live-progress обязателен: у идущих прогонов в
истории на этом месте простой execute_activity без таймера."
```

---

### Task 7: Сквозной путь

**Files:**
- Test: `tests/test_analysis_progress_e2e.py`

**Interfaces:**
- Consumes: всё предыдущее
- Produces: ничего

- [ ] **Step 1: Написать сквозной тест**

Идёт по активностям, а не по воркфлоу: цикл проверен в Task 6, здесь важно, что человек получает связный результат.

```python
def test_full_path_table_grows_and_stays_one_comment(monkeypatch):
    """Четыре факта одним прогоном:

    1. объявление публикует таблицу всех шести стадий;
    2. обещания «несколько минут» в ней нет;
    3. правки идут в ТОТ ЖЕ комментарий, новых не появляется;
    4. пройденная стадия показывает длительность, текущая — время в работе.

    Отказ, ради которого написано: на poh-demo-checkout#165 человек тридцать
    минут не мог отличить работающий анализ от умершего.
    """
    state = {"comments": [], "edits": []}
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body:
                            state["comments"].append(body) or 777)
    monkeypatch.setattr(a.github_client, "edit_comment",
                        lambda repo, cid, body: state["edits"].append((cid, body)))
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)

    # объявление
    comment_id = asyncio.run(a.ack_command(_analyze()))
    assert comment_id == 777
    assert len(state["comments"]) == 1
    assert "несколько минут" not in state["comments"][0]
    for name in a.FNR_STAGE_NAMES:
        assert name in state["comments"][0]

    # первая стадия идёт, потом закончилась
    running = [{"name": "repowise", "state": "running", "started_epoch": 1000.0,
                "finished_epoch": 0.0, "attempt": 1}]
    a.update_analysis_progress(_analyze(), comment_id, running, 1360.0, False)
    done = [{"name": "repowise", "state": "done", "started_epoch": 1000.0,
             "finished_epoch": 1180.0, "attempt": 1}]
    a.update_analysis_progress(_analyze(), comment_id, done, 1360.0, False)

    assert len(state["comments"]) == 1, "новых комментариев быть не должно"
    assert [cid for cid, _ in state["edits"]] == [777, 777]
    assert "6 мин" in state["edits"][0][1]
    assert "3 мин" in state["edits"][1][1]
```

- [ ] **Step 2: Прогнать**

Run: `python -m pytest tests/test_analysis_progress_e2e.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 3: Прогнать весь набор и гвард реплея**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 4: Коммит**

```bash
git add tests/test_analysis_progress_e2e.py
git commit -m "test(progress): сквозной путь — один комментарий, растущая таблица"
```

---

## Что остаётся человеку после плана

- **Живой прогон.** План закрывается модульными проверками и гвардом реплея; работает ли механизм на стенде, покажет только живая задача — та же, на которой дефект и нашёлся.
- **Документация.** `docs/ARCHITECTURE.md` описывает анализ как одну непрозрачную стадию.
- **Ход у прочих долгих стадий** — разработка и приёмка. Механизм тот же, структура шагов другая; отдельная работа после того, как этот приживётся.
- **Вторая попытка стадии в таблице (P8).** Отрисовка готова, источника данных нет: воркфлоу номера попытки не видит. Нужна отдельная работа — научить `run_fnr_stage` сообщать свою попытку. До тех пор выкладка посреди анализа выглядит в таблице как стадия, идущая вдвое дольше обычного.
