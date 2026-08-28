"""Активности MvpDelivery: `mvp_read_plan`, `mvp_open_substep`, `mvp_develop_step`,
`mvp_close_substep` — тела, не подделки.

`tests/test_mvp_delivery.py` проверяет ПОРЯДОК шагов воркфлоу, полностью
подменяя эти четыре активности подделками по имени. Здесь — обратное: сам
воркфлоу не поднимается, каждая активность вызывается напрямую (`asyncio.run`,
как и в `tests/test_plan_mvp.py`), а граница мира (GitHub, `_run_claude`,
файловая система) подменяется `monkeypatch`.

Два требования закреплены тут утверждением, а не доверием к докстрингу:

1. `mvp_read_plan` обязана звать `decomposition.dependency_reason_missing` и
   отказывать при находке — ДО того, как хоть одна под-задача появится в
   GitHub (Task 2 подготовила проверку, но её не звала ни одна задача плана;
   выдуманное ребро плодит задачи в трекере, ради чего вся декомпозиция и
   затевалась).
2. `mvp_open_substep` обязана заводить под-задачу с метками `ORIGIN_AGENT` И
   `STEP` разом — без `STEP` вебхук поднимет на ней полноценный цикл с
   триажом, и смысл под-задачи шага теряется.
"""

import asyncio

import pytest

import activities
from shared import decomposition, task_context
from shared.labels import ORIGIN_AGENT, STEP
from shared.workflow_types import IssueInput


def _issue(number: int = 9) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User")


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value
    return _fn


# --- mvp_read_plan: честность рёбер (требование 1) ---

def test_mvp_read_plan_refuses_dependency_without_reason(monkeypatch, tmp_path):
    """Ребро объявлено (`depends_on=[0]`), а предмет — нет (`depends_reason`
    пуст для этого индекса). `dependency_reason_missing` реальная (Task 2), а
    вот `plan_parse.parse` подменена: разобранный текст плана НИКОГДА не даёт
    ребро без причины по построению регулярки (причина — вся строка
    Consumes целиком), так что нечестное ребро сюда может попасть только из
    другого источника — упражнение на то, что `mvp_read_plan` действительно
    зовёт проверку, а не полагается на то, что parse() её сама исключает.
    """
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)
    (harness / task_context.PLAN).write_text("# План\n\n### Task 1\n", encoding="utf-8")

    monkeypatch.setattr(activities, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    monkeypatch.setattr(activities, "_dev_resolve_branch", _async_return(""))
    monkeypatch.setattr(activities, "build_mvp_plan", _async_return(True))
    monkeypatch.setattr(
        activities.plan_parse, "parse",
        lambda text: [
            {"title": "Первый", "depends_on": [], "depends_reason": {}},
            {"title": "Второй", "depends_on": [0], "depends_reason": {}},
        ],
    )
    created = []
    monkeypatch.setattr(activities.github_client, "create_issue",
                        lambda *a, **k: created.append((a, k)) or 999)

    with pytest.raises(decomposition.InvalidPlan):
        asyncio.run(activities.mvp_read_plan(_issue()))

    assert not created, "план с недоказанным ребром не должен доехать до GitHub"


def test_mvp_read_plan_builds_and_parses_honest_plan(monkeypatch, tmp_path):
    """Путь без находок: план строится, парсится настоящим `plan_parse.parse`,
    рёбра объяснены — активность отдаёт шаги как есть."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)

    def fake_run_claude(prompt, cwd, mcp_config=None):
        (harness / task_context.PLAN).write_text(
            "# План\n\n"
            "### Task 1: Первый\n\n"
            "### Task 2: Второй\n\n"
            "- Consumes: Task 1, читает parse() из первого шага\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(activities, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    monkeypatch.setattr(activities, "_dev_resolve_branch", _async_return(""))
    monkeypatch.setattr(activities, "_run_claude", fake_run_claude)

    items = asyncio.run(activities.mvp_read_plan(_issue()))

    assert [item["title"] for item in items] == ["Первый", "Второй"]
    assert items[1]["depends_on"] == [0]
    assert items[1]["depends_reason"]["0"]


def test_mvp_read_plan_fails_loudly_when_plan_not_built(monkeypatch, tmp_path):
    """`build_mvp_plan` вернула `False` (навык не оставил файл) — стадия
    обязана отказать, а не тихо отдать `[]`. Пустой список воркфлоу читает
    как легитимное «делить нечего» и молча завершается: самый дорогой класс
    отказов («шаг отработал, доложил успех, результата нет») ровно об этом.
    """
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)

    monkeypatch.setattr(activities, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    monkeypatch.setattr(activities, "_dev_resolve_branch", _async_return(""))
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd, mcp_config=None: None)

    with pytest.raises(RuntimeError):
        asyncio.run(activities.mvp_read_plan(_issue()))


# --- mvp_open_substep: метка STEP обязательна (требование 2) ---

def test_mvp_open_substep_labels_origin_agent_and_step(monkeypatch):
    """Без `STEP` вебхук поднимет на под-задаче полноценный цикл с триажом —
    план родителя её уже разобрал, и такой цикл был бы разговором контура с
    самим собой. Закреплено утверждением на реальных метках модуля `labels`,
    а не строкой-копией."""
    seen = {}

    def fake_create_issue(repo, title, body, labels=None):
        seen.update(repo=repo, title=title, body=body, labels=labels)
        return 555

    monkeypatch.setattr(activities.github_client, "create_issue", fake_create_issue)
    monkeypatch.setattr(activities.github_client, "issue_node_id",
                        lambda repo, number: 424242)
    linked = {}
    monkeypatch.setattr(
        activities.github_client, "link_sub_issue",
        lambda repo, parent, child_id: linked.update(
            repo=repo, parent=parent, child_id=child_id))

    number = asyncio.run(activities.mvp_open_substep(_issue(), 0, "Шаг 1"))

    assert number == 555
    assert seen["labels"] == [ORIGIN_AGENT, STEP]
    assert seen["repo"] == "o/r" and seen["title"] == "Шаг 1"
    # Привязка идёт по внутреннему id, не по номеру (github_client.link_sub_issue).
    assert linked == {"repo": "o/r", "parent": 9, "child_id": 424242}


# --- mvp_close_substep ---

def test_mvp_close_substep_closes_issue_and_marks_checklist(monkeypatch):
    closed = []
    monkeypatch.setattr(activities.github_client, "close_issue",
                        lambda repo, number: closed.append((repo, number)))
    monkeypatch.setattr(activities.github_client, "get_issue_body",
                        lambda repo, number: "Текст человека.\n")
    updated = {}
    monkeypatch.setattr(
        activities.github_client, "update_issue_body",
        lambda repo, number, body: updated.update(repo=repo, number=number, body=body))

    asyncio.run(activities.mvp_close_substep(_issue(), 555, 0))

    assert closed == [("o/r", 555)]
    assert updated["repo"] == "o/r" and updated["number"] == 9
    assert "Шаг 1 — #555" in updated["body"]
    assert "Текст человека." in updated["body"], "тело человека затёрто"


def test_mvp_close_substep_is_idempotent_on_retry(monkeypatch):
    """Повторный заход по тому же шагу не должен задваивать строку чеклиста."""
    monkeypatch.setattr(activities.github_client, "close_issue", lambda *a: None)
    state = {"body": "Текст человека.\n"}
    monkeypatch.setattr(activities.github_client, "get_issue_body",
                        lambda repo, number: state["body"])

    def fake_update(repo, number, body):
        state["body"] = body
    monkeypatch.setattr(activities.github_client, "update_issue_body", fake_update)

    asyncio.run(activities.mvp_close_substep(_issue(), 555, 0))
    asyncio.run(activities.mvp_close_substep(_issue(), 555, 0))

    assert state["body"].count("Шаг 1 — #555") == 1


# --- mvp_develop_step ---

def test_mvp_develop_step_delegates_to_existing_development_run(monkeypatch):
    seen = {}

    async def fake_trigger(issue, root_issue=None, branch=None):
        seen["root_issue"] = root_issue
        return 777

    monkeypatch.setattr(activities, "trigger_openhands_resolver", fake_trigger)

    assert asyncio.run(activities.mvp_develop_step(_issue(), 2)) == 777
    assert seen["root_issue"] == 9


def test_mvp_develop_step_rejects_dispatch_mode_instead_of_returning_none(monkeypatch):
    """`dispatch`: `trigger_openhands_resolver` отдаёт `None` (результат
    приедет позже событием `pr-open`). `MvpDelivery` ждёт номер PR сразу для
    следующего шага — несовместимо. Явный отказ вместо `result_type=int`,
    споткнувшегося о `None`."""
    monkeypatch.setattr(activities, "trigger_openhands_resolver", _async_return(None))

    with pytest.raises(RuntimeError):
        asyncio.run(activities.mvp_develop_step(_issue(), 0))
