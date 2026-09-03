"""Красный прогон: диагноз, починка, повторная проверка.

Отказ, ради которого написано: #166 и #167 — оба прогона кончились человеком,
хотя агент ничего не ломал.
"""

import inspect
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import DevelopPlan, Diagnosis, IssueInput
from workflows import IssueDevelopment

_calls: list[str] = []
_repair_args: list[list[str]] = []


@activity.defn(name="dev_begin")
async def begin_local(issue: IssueInput) -> DevelopPlan:
    _calls.append("begin")
    return DevelopPlan(mode="local", branch="research/issue-167", repair_rounds=1)


@activity.defn(name="dev_dispatch")
async def dispatch_stub(issue: IssueInput, branch: str) -> None:
    _calls.append("dispatch")


@activity.defn(name="dev_prepare")
async def prepare_ok(issue: IssueInput, branch: str) -> int:
    _calls.append("prepare")
    return 1


@activity.defn(name="dev_announce")
async def announce_ok(issue: IssueInput, branch: str) -> None:
    _calls.append("announce")


@activity.defn(name="build_mvp_plan")
async def plan_ok(issue: IssueInput, branch: str) -> bool:
    _calls.append("plan")
    return True


@activity.defn(name="dev_run_agent")
async def agent_ok(issue: IssueInput) -> None:
    _calls.append("agent")


@activity.defn(name="dev_followups")
async def followups_ok(issue: IssueInput) -> list[int]:
    _calls.append("followups")
    return []


@activity.defn(name="dev_tests")
async def checks_ok(issue: IssueInput) -> None:
    _calls.append("tests")


@activity.defn(name="dev_publish")
async def publish_ok(issue: IssueInput, branch: str, foreign: list[str]) -> int | None:
    _calls.append("publish")
    return 101


@activity.defn(name="capture_episode")
async def episode_ok(issue: IssueInput, branch: str, pr_number: int | None) -> bool:
    _calls.append("capture_episode")
    return True


@activity.defn(name="dev_publish_partial")
async def partial_stub(issue: IssueInput, branch: str, reason: str) -> int | None:
    _calls.append("partial")
    return 42


@activity.defn(name="dev_announce_repair")
async def announce_repair_stub(issue: IssueInput, own: list[str]) -> None:
    _calls.append("announce_repair")


BASE = [begin_local, dispatch_stub, prepare_ok, announce_ok, plan_ok, agent_ok,
        followups_ok, checks_ok, publish_ok, episode_ok, partial_stub,
        announce_repair_stub]


@activity.defn(name="dev_tests")
async def checks_fail(issue: IssueInput) -> None:
    _calls.append("tests")
    raise RuntimeError("проверки не прошли (код 1):\n# fail 3")


def _acts(*overrides):
    def _name(fn):
        return activity._Definition.must_from_callable(fn).name

    replaced = {_name(fn): fn for fn in overrides}
    base = [replaced.pop(_name(fn), fn) for fn in BASE]
    return [*base, *replaced.values()]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=167, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _run(env, acts, expect_failure: bool):
    tq = f"tq-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=tq, workflows=[IssueDevelopment],
                      activities=acts):
        if expect_failure:
            with pytest.raises(Exception) as excinfo:
                await env.client.execute_workflow(
                    IssueDevelopment.run, _issue(), id=f"wf-{uuid.uuid4()}",
                    task_queue=tq)
            return excinfo.value
        return await env.client.execute_workflow(
            IssueDevelopment.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)


@pytest.mark.timeout(60)
async def test_a_green_run_costs_nothing_extra():
    """Зелёный прогон не гоняет ни диагноза, ни починки (B1)."""
    _calls.clear()

    @activity.defn(name="dev_diagnose")
    async def diagnose_stub(issue: IssueInput,
                            baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        return Diagnosis(parsed=True, baseline=[], own=[], foreign=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        number = await _run(env, _acts(diagnose_stub), expect_failure=False)

    assert number == 101
    assert "diagnose" not in _calls
    assert "repair" not in _calls


@pytest.mark.timeout(60)
async def test_foreign_redness_publishes_instead_of_failing():
    """Чужая краснота — прогон УДАЛСЯ (B14). Ровно случай #167."""
    _calls.clear()

    @activity.defn(name="dev_diagnose")
    async def diagnose_foreign(issue: IssueInput,
                               baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        return Diagnosis(parsed=True, baseline=["p::a"], own=[], foreign=["p::a"])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        number = await _run(env, _acts(checks_fail, diagnose_foreign),
                            expect_failure=False)

    assert number == 101, "PR должен открыться, человека звать не за чем"
    assert "repair" not in _calls
    assert "partial" not in _calls, "черновик тут не при чём — прогон удался"


@pytest.mark.timeout(60)
async def test_our_breakage_triggers_exactly_one_repair_round():
    """Своя поломка чинится, и ровно один раз (B9, B10)."""
    _calls.clear()
    _repair_args.clear()
    seen = {"n": 0}

    @activity.defn(name="dev_diagnose")
    async def diagnose_own(issue: IssueInput,
                           baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        seen["n"] += 1
        if seen["n"] == 1:
            return Diagnosis(parsed=True, baseline=["p::a"], own=["s::мой"],
                             foreign=["p::a"])
        return Diagnosis(parsed=True, baseline=["p::a"], own=[], foreign=["p::a"])

    @activity.defn(name="dev_repair")
    async def repair_stub(issue: IssueInput, own: list[str]) -> None:
        _calls.append("repair")
        _repair_args.append(own)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        number = await _run(env, _acts(checks_fail, diagnose_own, repair_stub),
                            expect_failure=False)

    assert number == 101, "починка удалась — PR обязан открыться"
    assert _calls.count("repair") == 1
    assert _repair_args == [["s::мой"]], "агенту уходят только СВОИ падения"
    assert _calls.count("tests") == 2, "после починки набор гоняется заново"


@pytest.mark.timeout(60)
async def test_a_failed_repair_ends_with_a_human_and_a_draft():
    """Не починил — отказ, черновик, человек (B10, B26)."""
    _calls.clear()

    @activity.defn(name="dev_diagnose")
    async def diagnose_own(issue: IssueInput,
                           baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        return Diagnosis(parsed=True, baseline=[], own=["s::мой"], foreign=[])

    @activity.defn(name="dev_repair")
    async def repair_stub(issue: IssueInput, own: list[str]) -> None:
        _calls.append("repair")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, _acts(checks_fail, diagnose_own, repair_stub),
                   expect_failure=True)

    assert _calls.count("repair") == 1, "заход обязан быть один"
    assert "partial" in _calls, "работа агента должна уехать черновиком"


@pytest.mark.timeout(60)
async def test_an_unparsed_diagnosis_keeps_the_old_behaviour():
    """Исход не разобран — ведём себя как прежде (B15).

    Ни починки, ни публикации: отказ тестов остаётся отказом.
    """
    _calls.clear()

    @activity.defn(name="dev_diagnose")
    async def diagnose_blind(issue: IssueInput,
                             baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        return Diagnosis(parsed=False, baseline=[], own=[], foreign=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        err = await _run(env, _acts(checks_fail, diagnose_blind),
                         expect_failure=True)

    assert "repair" not in _calls
    assert "partial" in _calls
    parts = []
    cur: BaseException | None = err
    while cur is not None:
        parts.append(str(cur))
        cur = cur.__cause__
    assert "fail 3" in "\n".join(parts), "наружу должна уйти причина отказа тестов"


@pytest.mark.timeout(60)
async def test_repair_can_be_turned_off_entirely():
    """`repair_rounds=0` — починки нет, поведение прежнее (B10)."""
    _calls.clear()

    @activity.defn(name="dev_begin")
    async def begin_no_repair(issue: IssueInput) -> DevelopPlan:
        _calls.append("begin")
        return DevelopPlan(mode="local", branch="b", repair_rounds=0)

    @activity.defn(name="dev_diagnose")
    async def diagnose_own(issue: IssueInput,
                           baseline: list[str] | None) -> Diagnosis:
        _calls.append("diagnose")
        return Diagnosis(parsed=True, baseline=[], own=["s::мой"], foreign=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run(env, _acts(begin_no_repair, checks_fail, diagnose_own),
                   expect_failure=True)

    assert "repair" not in _calls


def test_repair_loop_patch_marker_is_frozen():
    """Идентификатор патча — часть истории идущих прогонов разработки."""
    src = inspect.getsource(IssueDevelopment.run)
    assert 'workflow.patched("issue-development-repair-loop")' in src
