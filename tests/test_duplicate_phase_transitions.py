"""Issue #93: phase:duplicate should have outgoing transitions.

Проблема: Issue, попавший в phase:duplicate, стоит там навсегда, потому что:
1. В TRANSITIONS нет исходящих переходов (уже исправлено в lifecycle.py)
2. В webhook нет меток для "не дубликат" / "подтвердить дубликат" (исправлено)
3. В workflow не обработаны эти сигналы (исправлено)

Проверяем, что Issue может выйти из фазы DUPLICATE как в работу, так и в отмену.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
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

_calls: list[str] = []


# --- заглушки ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: здесь — шум."""
    pass


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False):
    return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


@activity.defn(name="intake_gate")
async def gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="duplicate_check")
async def duplicate_detected(issue: IssueInput) -> DuplicateResult:
    """Имитация дубликата: возвращает результат, который переводит в DUPLICATE."""
    _calls.append("duplicate_check")
    return DuplicateResult(
        decision="duplicate",
        best_match_number=90,
        probability=0.95,
        reason="такое же описание",
        context_branch=None
    )


@activity.defn(name="post_comment")
async def post_comment_stub(repo: str, issue_number: int, body: str) -> None:
    pass


@activity.defn(name="add_label")
async def add_label_stub(repo: str, issue_number: int, label: str) -> None:
    _calls.append(f"label:{label}")


@activity.defn(name="classify_issue")
async def classify_stub(issue: IssueInput, bft_on_triage: bool = False):
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="score_priority")
async def score_priority_stub(issue: IssueInput, c, d):
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority_stub(issue: IssueInput, p, d):
    _calls.append("priority_posted")


@activity.defn(name="escalate_to_human")
async def escalate_stub(issue: IssueInput, reason: str = ""):
    _calls.append(f"escalate:{reason}")


@activity.defn(name="post_error_label")
async def post_error_stub(repo: str, issue_number: int, error: str):
    _calls.append(f"error-label:{error[:30]}")


@activity.defn(name="read_issue_labels")
async def read_labels_stub(repo: str, issue_number: int) -> list[str]:
    """Заглушка без меток решения — обычная парковка после not-duplicate."""
    return []


def _issue(interactive: bool = True) -> IssueInput:
    return IssueInput(
        repo="test/repo",
        issue_number=93,
        title="Test duplicate issue",
        body="This is a duplicate",
        author_login="testuser",
        author_type="User",
        interactive=interactive
    )


async def _await_phase(env, handle, expected_phase: str) -> str:
    """Ждём, пока фаза не станет expected_phase, с таймаутом."""
    for _ in range(50):  # до 5 секунд при 0.1 сек пауза
        current = await handle.query(IssueLifecycle.phase)
        if current == expected_phase:
            return current
        await env.sleep(0.1)
    return current


@pytest.mark.timeout(90)
async def test_duplicate_phase_has_not_duplicate_transition():
    """Issue в phase:duplicate должен уйти в phase:classified по сигналу not-duplicate."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub, read_labels_stub]

        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Ждём, пока Issue перейдёт в DUPLICATE
            current = await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
            assert "duplicate_check" in _calls

            # Отправляем сигнал "not-duplicate"
            await handle.signal(IssueLifecycle.human_decision, "not-duplicate")

            # Ждём перехода в CLASSIFIED
            current = await _await_phase(env, handle, lifecycle.CLASSIFIED)
            assert current == lifecycle.CLASSIFIED, f"Expected CLASSIFIED, got {current}"
            stage = await handle.query(IssueLifecycle.stage)
            assert stage == "awaiting-human-decision"


@pytest.mark.timeout(90)
async def test_duplicate_phase_has_confirm_duplicate_transition():
    """Issue в phase:duplicate должен уйти в phase:cancelled по сигналу confirm-duplicate."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub]
        
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            
            # Ждём, пока Issue перейдёт в DUPLICATE
            current = await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
            
            # Отправляем сигнал "confirm-duplicate"
            await handle.signal(IssueLifecycle.human_decision, "confirm-duplicate")
            
            # Ждём перехода в CANCELLED
            current = await _await_phase(env, handle, lifecycle.CANCELLED)
            assert current == lifecycle.CANCELLED, f"Expected CANCELLED, got {current}"
            stage = await handle.query(IssueLifecycle.stage)
            assert stage == "cancelled"


@pytest.mark.timeout(90)
async def test_foreign_signal_does_not_duplicate_issue():
    """Случайный сигнал на припаркованном DUPLICATE Issue не должен выбивать его из фазы."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub]
        
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            
            # Ждём, пока Issue перейдёт в DUPLICATE
            current = await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
            
            # Отправляем посторонний сигнал
            await handle.signal(IssueLifecycle.human_decision, "wontfix")
            await env.sleep(1)
            
            # Фаза не должна измениться
            assert await handle.query(IssueLifecycle.phase) == lifecycle.DUPLICATE
            assert (await handle.describe()).status.name == "RUNNING"


@pytest.mark.timeout(90)
async def test_reopen_still_works_for_duplicate():
    """Сигнал reopen должен работать как раньше для возврата в работу."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub]
        
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            
            # Ждём, пока Issue перейдёт в DUPLICATE
            current = await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
            
            # Отправляем сигнал "reopen"
            await handle.signal(IssueLifecycle.human_decision, "reopen")
            
            # Ждём перехода в CLASSIFIED
            current = await _await_phase(env, handle, lifecycle.CLASSIFIED)
            assert current == lifecycle.CLASSIFIED, f"Expected CLASSIFIED, got {current}"
