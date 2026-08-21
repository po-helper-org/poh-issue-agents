"""Issue #104: выход из DUPLICATE проверяет уже стоящие метки.

Проблема: после перехода `DUPLICATE → CLASSIFIED` по сигналу `not-duplicate`,
воркфлоу парковался на полный срок, даже если на Issue уже стояла метка
`research-me` или `bug-me`. Это задерживало обработку на ~3 суток.

Решение: при выходе из DUPLICATE проверять текущие метки Issue и, если
решение уже проставлено, сразу переходить к соответствующей фазе, минуя
парковку.
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import activities as activities_module
from shared import labels, lifecycle
from shared.workflow_types import (
    AnalyzeInput,
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


def _issue() -> IssueInput:
    return IssueInput(repo="test/repo", issue_number=104, title="Test duplicate", 
                      body="This is a duplicate", author_login="testuser", 
                      author_type="User", interactive=True)


# --- заглушки ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    _calls.append("awaiting")


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False):
    return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="read_issue_labels")
async def read_labels_stub(repo: str, issue_number: int) -> list[str]:
    """Заглушка, которая возвращает метки Issue."""
    return []


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


@activity.defn(name="finish_command_labels")
async def finish_command_stub(repo: str, issue_number: int, command: str, ok: bool):
    _calls.append(f"finish:{command}:{ok}")


@activity.defn(name="read_deadlines")
async def read_deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="decompose_issue")
async def decompose_stub(issue: IssueInput, branch: str) -> dict:
    return {"plan": []}


@activity.defn(name="prepare_workspace")
async def prepare_stub(analyze: AnalyzeInput) -> None:
    pass


@activity.defn(name="ack_command")
async def ack_stub(analyze: AnalyzeInput) -> None:
    pass


@activity.defn(name="mark_command_running")
async def mark_running_stub(repo: str, issue_number: int, command: str) -> None:
    pass


@activity.defn(name="run_fnr_stage")
async def run_fnr_stage_stub(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="develop_start")
async def develop_start_stub(issue: IssueInput, stage: str) -> None:
    pass


async def _await_phase(env, handle, expected_phase: str) -> str:
    """Ждём, пока фаза не станет expected_phase, с таймаутом."""
    for _ in range(50):  # до 5 секунд при 0.1 сек пауза
        current = await handle.query(IssueLifecycle.phase)
        if current == expected_phase:
            return current
        await env.sleep(0.1)
    return current


@pytest.mark.timeout(90)
async def test_duplicate_exit_with_research_me_label_skips_park():
    """Issue с меткой research-me должен уйти в анализ сразу после not-duplicate."""
    _calls.clear()
    
    # Заглушка, которая возвращает метку research-me
    @activity.defn(name="read_issue_labels")
    async def read_labels_with_research_me(repo: str, issue_number: int) -> list[str]:
        return ["research-me", "phase:duplicate"]
    
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, read_labels_with_research_me,
                      set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub, finish_command_stub,
                      decompose_stub, prepare_stub, ack_stub, mark_running_stub,
                      run_fnr_stage_stub, develop_start_stub]
        
        async with Worker(env.client, task_queue=tq, 
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Таймскип отключаем на время наблюдения: без этого авто-продвижение
            # времени на каждом query гонится с параллельными парковками
            # (см. тот же приём в test_research_autostart.py) и валит запрос
            # RPCError'ом "query deadline exceeded".
            with env.auto_time_skipping_disabled():
                # Ждём, пока Issue перейдёт в DUPLICATE
                current = await _await_phase(env, handle, lifecycle.DUPLICATE)
                assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
                assert "duplicate_check" in _calls

                # Отправляем сигнал "not-duplicate" при уже стоящей метке research-me
                await handle.signal(IssueLifecycle.human_decision, "not-duplicate")

                # Ждём перехода в BUSINESS_ANALYSIS (не в CLASSIFIED!)
                current = await _await_phase(env, handle, lifecycle.BUSINESS_ANALYSIS)
                assert current == lifecycle.BUSINESS_ANALYSIS, \
                    f"Expected BUSINESS_ANALYSIS, got {current}"


@pytest.mark.timeout(90)
async def test_duplicate_exit_with_bug_me_label_skips_park():
    """Issue с меткой bug-me должен уйти в разработку сразу после not-duplicate."""
    _calls.clear()
    
    # Заглушка, которая возвращает метку bug-me
    @activity.defn(name="read_issue_labels")
    async def read_labels_with_bug_me(repo: str, issue_number: int) -> list[str]:
        return ["bug-me", "phase:duplicate"]
    
    # Заглушка классификации для бага
    @activity.defn(name="classify_issue")
    async def classify_bug(issue: IssueInput, bft_on_triage: bool = False):
        return ClassificationResult(label="advisor:bug", answer="ok")
    
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, read_labels_with_bug_me,
                      set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_bug, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub, finish_command_stub,
                      decompose_stub, prepare_stub, ack_stub, mark_running_stub,
                      run_fnr_stage_stub, develop_start_stub]
        
        async with Worker(env.client, task_queue=tq, 
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            with env.auto_time_skipping_disabled():
                # Ждём, пока Issue перейдёт в DUPLICATE
                current = await _await_phase(env, handle, lifecycle.DUPLICATE)
                assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"

                # Отправляем сигнал "not-duplicate" при уже стоящей метке bug-me
                await handle.signal(IssueLifecycle.human_decision, "not-duplicate")

                # Ждём перехода в READY_FOR_DEV (не в CLASSIFIED!)
                current = await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
                assert current == lifecycle.READY_FOR_DEV, \
                    f"Expected READY_FOR_DEV, got {current}"


@pytest.mark.timeout(90)
async def test_duplicate_exit_without_decision_labels_parks_normally():
    """Issue без меток решения должен парковаться в CLASSIFIED как обычно."""
    _calls.clear()
    
    # Заглушка, которая возвращает метки без решения
    @activity.defn(name="read_issue_labels")
    async def read_labels_no_decision(repo: str, issue_number: int) -> list[str]:
        return ["phase:duplicate"]
    
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [awaiting_stub, prefilter_ok, protocol_default,
                      deadlines_stub, read_labels_no_decision,
                      set_phase_stub, gate_sufficient,
                      duplicate_detected, post_comment_stub, add_label_stub,
                      classify_stub, score_priority_stub, post_priority_stub,
                      escalate_stub, post_error_stub, finish_command_stub,
                      decompose_stub, prepare_stub, ack_stub, mark_running_stub,
                      run_fnr_stage_stub, develop_start_stub]
        
        async with Worker(env.client, task_queue=tq, 
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=activities):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            
            # Ждём, пока Issue перейдёт в DUPLICATE
            current = await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert current == lifecycle.DUPLICATE, f"Expected DUPLICATE, got {current}"
            
            # Отправляем сигнал "not-duplicate" без меток решения
            await handle.signal(IssueLifecycle.human_decision, "not-duplicate")
            
            # Ждём перехода в CLASSIFIED (обычное поведение)
            current = await _await_phase(env, handle, lifecycle.CLASSIFIED)
            assert current == lifecycle.CLASSIFIED, f"Expected CLASSIFIED, got {current}"
            stage = await handle.query(IssueLifecycle.stage)
            assert stage == "awaiting-human-decision"
