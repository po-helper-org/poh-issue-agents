"""Автозапуск приёмки при открытии PR.

Приёмка стартует отдельным прогоном и НЕ ждётся: она держит стенд и модель
десятками минут, а цикл фаз обязан оставаться отзывчивым — доклад PR-Agent'а
не должен стоять в очереди за приёмкой.
"""

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

from shared import lifecycle  # noqa: E402
from shared.workflow_ids import howtodemo_workflow_id  # noqa: E402
from shared.workflow_types import Deadlines, IssueInput  # noqa: E402


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=12, title="t", body="b",
                      author_login="human", author_type="User")


class _Cycle:
    """Подделка воркфлоу: подменяем только то, чем врезка пользуется."""

    def __init__(self):
        import workflows

        self.wf = workflows.IssueLifecycle()
        self.wf._phase = lifecycle.PR_OPEN
        self.wf._pr_number = 45
        self.started = []

    async def start_child(self, name, arg=None, **kwargs):
        self.started.append({"name": name, "arg": arg, **kwargs})
        return object()


@pytest.fixture
def cycle(monkeypatch):
    import workflows

    c = _Cycle()
    monkeypatch.setattr(workflows.workflow, "start_child_workflow", c.start_child)
    monkeypatch.setattr(workflows.workflow, "patched", lambda _id: True)
    # `workflow.logger` живёт только внутри цикла событий воркфлоу — вне его
    # он честно падает, поэтому в тесте подменяем.
    monkeypatch.setattr(workflows.workflow, "logger", logging.getLogger("test"))
    return c


async def test_acceptance_starts_on_an_open_pull_request(cycle):
    await cycle.wf._start_howtodemo(_issue())
    assert len(cycle.started) == 1
    started = cycle.started[0]
    assert started["name"] == "HowToDemoVerify"
    assert started["arg"] == {"repo": "o/r", "issue": 12, "pr_number": 45}


async def test_acceptance_runs_on_its_own_queue(cycle):
    """Общая очередь дала бы приёмке вытеснять триаж Issue."""
    await cycle.wf._start_howtodemo(_issue())
    queue = cycle.started[0]["task_queue"]
    assert queue == "howtodemo"
    assert queue not in ("issue-lifecycle", "delivery")


async def test_acceptance_is_not_awaited_and_survives_the_parent(cycle):
    """Закрытие Issue не должно убивать идущий прогон приёмки."""
    from temporalio.workflow import ParentClosePolicy

    await cycle.wf._start_howtodemo(_issue())
    assert cycle.started[0]["parent_close_policy"] == ParentClosePolicy.ABANDON


async def test_id_matches_the_one_a_human_command_would_use(cycle):
    """Совпадение id — это и есть защита от второго прогона по той же задаче."""
    await cycle.wf._start_howtodemo(_issue())
    assert cycle.started[0]["id"] == howtodemo_workflow_id("o/r", 12)


async def test_already_running_acceptance_is_not_an_error(cycle, monkeypatch):
    """Человек успел позвать /howtodemo — это тот прогон, который нам и нужен."""
    import workflows
    from temporalio.exceptions import WorkflowAlreadyStartedError

    async def already(*args, **kwargs):
        raise WorkflowAlreadyStartedError("howtodemo-o/r-12", "HowToDemoVerify")

    monkeypatch.setattr(workflows.workflow, "start_child_workflow", already)
    await cycle.wf._start_howtodemo(_issue())  # не бросает


def test_autostart_is_off_until_asked_for():
    """Стадия поднимает контейнер и зовёт модель — молча её не включают."""
    assert Deadlines().howtodemo_autostart is False


def test_environment_flag_turns_it_on(monkeypatch):
    import activities

    monkeypatch.setenv("HOWTODEMO_AUTOSTART", "1")
    assert activities.read_deadlines().howtodemo_autostart is True
    monkeypatch.setenv("HOWTODEMO_AUTOSTART", "0")
    assert activities.read_deadlines().howtodemo_autostart is False
