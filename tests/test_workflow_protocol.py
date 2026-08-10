"""Маршруты протокола в IssueLifecycle: рубильник, сокращённый триаж и потолок
глубины. Проверяем не метки, а поведение — что именно НЕ было вызвано."""

import uuid

import pytest
from temporalio import activity
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
from workflows import IssueLifecycle

_calls: list[str] = []


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=False)


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput):
    _calls.append("prefilter")
    return None

@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    """Метка фазы: инвариант проверяется в test_lifecycle_phases, здесь — шум."""



@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    """Сроки по умолчанию: тесты проверяют маршруты, а не сами таймеры."""
    return Deadlines()


@activity.defn(name="intake_gate")
async def gate(issue: IssueInput, thread: list[str]) -> GateResult:
    _calls.append("intake_gate")          # ← вызов LLM
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify(issue: IssueInput) -> ClassificationResult:
    _calls.append("classify")             # ← вызов LLM
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate(issue: IssueInput) -> DuplicateResult:
    _calls.append("duplicate")
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score(issue: IssueInput, c, d) -> PriorityResult:
    _calls.append("priority")
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None:
    _calls.append("post_priority")


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None:
    _calls.append(f"escalate:{reason[:20]}")


def _state_stub(state: ProtocolState):
    @activity.defn(name="read_protocol_state")
    async def read(repo: str, issue_number: int) -> ProtocolState:
        _calls.append("read_state")
        return state

    return read


async def _run(state: ProtocolState) -> str:
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[prefilter_ok, gate, classify, duplicate, score,
                                      post_priority, escalate, _state_stub(state), deadlines_stub, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # Триаж без сигнала припарковался бы навсегда — шлём заведомо
            # несовпадающий лейбл, чтобы прогон дошёл до конца.
            await handle.signal(IssueLifecycle.human_decision, "no-match")
            await handle.result()
            return await handle.query(IssueLifecycle.stage)


@pytest.mark.timeout(60)
async def test_agents_off_spends_nothing():
    """R4, определение готовности задачи: прогон по Issue с `agents:off` не
    делает НИ ОДНОГО вызова LLM. Проверяем именно это, а не наличие метки."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[prefilter_ok, gate, classify, duplicate, score,
                                      post_priority, escalate,
                                      _state_stub(ProtocolState(agents_off=True)), deadlines_stub, phase_stub]):
            await env.client.execute_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

    assert "intake_gate" not in _calls
    assert "classify" not in _calls
    assert "duplicate" not in _calls
    assert "priority" not in _calls


@pytest.mark.timeout(60)
async def test_agents_off_is_visible_as_a_stage():
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[prefilter_ok, gate, classify, duplicate, score,
                                      post_priority, escalate,
                                      _state_stub(ProtocolState(agents_off=True)), deadlines_stub, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.result()
            assert await handle.query(IssueLifecycle.stage) == "agents-off"


@pytest.mark.timeout(60)
async def test_agent_issue_skips_gate_and_advisor_answer():
    """R6: Issue от агента уже классифицирован. Intake gate и advisor-ответ —
    разговор сервиса с самим собой; дедуп и приоритет по-прежнему нужны."""
    await _run(ProtocolState(origin_agent=True))

    assert "intake_gate" not in _calls
    assert "classify" not in _calls
    assert "duplicate" in _calls
    assert "priority" in _calls


@pytest.mark.timeout(60)
async def test_human_issue_keeps_the_full_route():
    """Обратная совместимость: обычный Issue проходит всё как раньше."""
    await _run(ProtocolState())

    assert _calls.count("intake_gate") == 1
    assert "classify" in _calls
    assert "duplicate" in _calls
    assert "priority" in _calls


@pytest.mark.timeout(60)
async def test_second_round_follow_up_goes_straight_to_a_human():
    """R7: контур перестаёт кормить сам себя — ни одной дорогой стадии."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[prefilter_ok, gate, classify, duplicate, score,
                                      post_priority, escalate,
                                      _state_stub(ProtocolState(origin_agent=True,
                                                                depth_exceeded=True)), deadlines_stub, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.result()
            assert await handle.query(IssueLifecycle.stage) == "escalated"

    assert any(c.startswith("escalate") for c in _calls)
    assert "intake_gate" not in _calls
    assert "classify" not in _calls
    assert "duplicate" not in _calls
