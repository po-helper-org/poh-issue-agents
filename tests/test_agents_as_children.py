"""#37: агент действительно становится дочерним прогоном цикла.

Тест лаунчера (`test_agent_launcher.py`) проверяет маршрутизацию, но не то, что
получилось в Temporal. Здесь поднимается настоящий воркфлоу и проверяется
результат: прогон агента виден как child владельца состояния Issue, переживает
завершение родителя (`ParentClosePolicy.ABANDON`) и сохраняет канонический id.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import ParentClosePolicy as ProtoParentClosePolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.workflow_ids import analysis_workflow_id, estimate_workflow_id
from shared.workflow_types import (
    AnalyzeInput,
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    EstimateRequest,
    EstimateResult,
    EstimationContext,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle

REPO = "o/r"
ISSUE = 7

_calls: list[str] = []


# --- границы триажа ---

@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


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
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="post_error_label")
async def post_error(issue: IssueInput, reason: str) -> None: ...


# --- границы аналитики ---

@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None:
    _calls.append(f"ack:{analyze.trigger}")


@activity.defn(name="prepare_workspace")
async def prepare(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="run_fnr_stage")
async def stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="publish_analysis")
async def publish(analyze: AnalyzeInput) -> str:
    return f"research/issue-{ISSUE}"


@activity.defn(name="cleanup_workspace")
async def cleanup(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="publish_analysis_error")
async def publish_error(analyze: AnalyzeInput, reason: str) -> None: ...


@activity.defn(name="finish_command_labels")
async def finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:
    _calls.append(f"finish:{command}:{ok}")


@activity.defn(name="mark_ready_for_dev")
async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None:
    _calls.append(f"ready:{priority_tier}")


# --- границы оценки ---

@activity.defn(name="ack_estimate_command")
async def ack_estimate(req: EstimateRequest) -> None:
    _calls.append(f"estimate-ack:{req.comment_id}")


@activity.defn(name="collect_estimation_context")
async def collect(req: EstimateRequest) -> EstimationContext:
    return EstimationContext(title="t", body="b", labels=[], thread=[],
                             branch=None, artifacts={}, truncated=False)


@activity.defn(name="extract_estimation_facts")
async def facts(context: EstimationContext) -> dict:
    return {}


@activity.defn(name="compute_estimate")
async def compute(facts: dict, context: EstimationContext) -> EstimateResult:
    return EstimateResult(markdown="оценка", stopped=False)


@activity.defn(name="post_estimate_comment")
async def post_estimate(req: EstimateRequest, result: EstimateResult) -> None:
    _calls.append("estimate-posted")


@activity.defn(name="post_estimate_error")
async def post_estimate_err(req: EstimateRequest, stage: str, reason: str) -> None:
    _calls.append(f"estimate-error:{stage}")


ALL_ACTIVITIES = [prefilter_ok, protocol_default, deadlines_stub, set_phase_stub,
                  gate_ok, classify_feature, duplicate_none, score_p1, post_priority,
                  escalate, post_error, ack, prepare, stage_ok, publish, cleanup,
                  publish_error, finish_labels, ready, ack_estimate, collect, facts,
                  compute, post_estimate, post_estimate_err]


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=ISSUE, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _worker(env, tq):
    return Worker(env.client, task_queue=tq,
                  workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                  activities=ALL_ACTIVITIES)


async def _await_phase(env, handle, expected: str) -> str:
    for _ in range(300):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


async def _child_starts(handle) -> list:
    """События старта дочерних прогонов из истории родителя."""
    out = []
    async for ev in handle.fetch_history_events():
        attrs = ev.start_child_workflow_execution_initiated_event_attributes
        if ev.HasField("start_child_workflow_execution_initiated_event_attributes"):
            out.append(attrs)
    return out


@pytest.mark.timeout(90)
async def test_analyze_runs_as_a_child_and_moves_the_phase():
    """Определение готовности #37: `/analyze` по Issue с живым циклом виден как
    дочерний прогон и двигает фазу в `business-analysis` → `system-requirements`."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            await handle.signal(IssueLifecycle.analyze_requested, 555)

            assert await _await_phase(env, handle, lifecycle.READY_FOR_DEV) == \
                lifecycle.READY_FOR_DEV
            children = await _child_starts(handle)

    assert [c.workflow_id for c in children] == [analysis_workflow_id(REPO, ISSUE)], (
        "аналитика не стала дочерним прогоном цикла"
    )
    # Передача разработчику состоялась — значит родитель получил результат child.
    assert "ready:P1" in _calls


@pytest.mark.timeout(90)
async def test_expensive_child_survives_the_parent():
    """Цепочка FNR идёт до 4500 с. Завершение цикла или его continue-as-new не
    должны её убивать — иначе дорогой прогон обрывается по причине, к нему не
    относящейся."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
            children = await _child_starts(handle)

    assert [c.parent_close_policy for c in children] == [
        ProtoParentClosePolicy.PARENT_CLOSE_POLICY_ABANDON
    ], "дочерний прогон погибнет вместе с родителем"


@pytest.mark.timeout(90)
async def test_estimate_runs_as_a_child_without_touching_the_phase():
    """Оценка — боковая команда, а не стадия пути: она обязана отработать, но
    не сдвинуть состояние Issue."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            await handle.signal(IssueLifecycle.estimate_requested, 555)
            for _ in range(60):
                if "estimate-posted" in _calls:
                    break
                await env.sleep(1)

            assert await handle.query(IssueLifecycle.phase) == lifecycle.CLASSIFIED
            children = await _child_starts(handle)

    assert [c.workflow_id for c in children] == [
        estimate_workflow_id(REPO, ISSUE, 555)
    ], "оценка не стала дочерним прогоном либо потеряла канонический id"
    assert "estimate-ack:555" in _calls


@pytest.mark.timeout(90)
async def test_analyze_on_a_parked_issue_runs_without_faking_the_phase():
    """Из `ready-for-dev` хода в аналитику нет. Команду всё равно выполняем, но
    фазу не трогаем: соврать про состояние хуже, чем не отразить разовый прогон.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
            _calls.clear()

            await handle.signal(IssueLifecycle.analyze_requested, 777)
            for _ in range(60):
                if any(c.startswith("finish:analyze") for c in _calls):
                    break
                await env.sleep(1)

            assert await handle.query(IssueLifecycle.phase) == lifecycle.READY_FOR_DEV

    assert "finish:analyze:True" in _calls, "команда по припаркованному Issue потерялась"
