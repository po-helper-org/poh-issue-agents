"""Сигнал `issue_closed` завершает цикл терминальной фазой.

Парковка со сроком (R3) гарантирует, что цикл не живёт вечно, но закрытый Issue
ждать нечего: до этой правки закрытие на GitHub никак не влияло на цикл, и он
стоял на парковке весь свой срок — в проде так набралось 22 прогона по уже
закрытым Issue. Терминальная фаза — `cancelled`: в таблице переходов она и
означает «снято с обработки», и разрешена из любой фазы.
"""

import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import (
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle

_phases: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None: ...


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _phases.append(phase)


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score_p1(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P1", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None: ...


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None:
    _phases.append("escalated-activity")


@activity.defn(name="read_deadlines")
async def deadlines_long() -> Deadlines:
    # Срок заведомо больше времени теста: цикл обязан закрыться по сигналу, а не
    # по дедлайну парковки — иначе тест доказывал бы не то.
    return Deadlines(human_decision_hours=720)


ACTIVITIES = [awaiting_stub, prefilter_ok, protocol_default, set_phase_stub, gate_ok,
              classify_feature, duplicate_none, score_p1, post_priority, escalate,
              deadlines_long]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _wait_for_park(env, handle) -> None:
    for _ in range(300):
        if await handle.query(IssueLifecycle.stage) == "awaiting-human-decision":
            return
        await env.sleep(1)
    raise AssertionError("цикл не дошёл до парковки в ожидании решения человека")


@pytest.mark.timeout(120)
async def test_closed_issue_ends_the_cycle():
    _phases.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _wait_for_park(env, handle)

            await handle.signal(IssueLifecycle.issue_closed, "alice")

            await handle.result()
            assert await handle.query(IssueLifecycle.phase) == "cancelled"
            desc = await handle.describe()
            assert desc.status == WorkflowExecutionStatus.COMPLETED
    assert "escalated-activity" not in _phases, "закрытие не эскалируют людям"
    assert _phases[-1] == "cancelled", f"метка фазы не доехала: {_phases}"


@pytest.mark.timeout(120)
async def test_closed_issue_ends_the_cycle_from_a_side_park():
    """Боковая фаза (`escalated`, `answered`, `spam`) — то же правило: закрытый
    Issue не ждут. Именно в таких фазах и висело большинство прода."""
    _phases.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _wait_for_park(env, handle)
            # Посторонний сигнал фазу не двигает — доводим цикл до боковой фазы
            # через настоящую эскалацию по сроку.
            await env.sleep(timedelta(hours=721))
            for _ in range(300):
                if await handle.query(IssueLifecycle.phase) == "escalated":
                    break
                await env.sleep(timedelta(hours=1))

            await handle.signal(IssueLifecycle.issue_closed, "alice")

            await handle.result()
            assert await handle.query(IssueLifecycle.phase) == "cancelled"
