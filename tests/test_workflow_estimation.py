import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import EstimateRequest, EstimateResult, EstimationContext
from workflows import IssueEstimation

_state: dict = {}

REQ = EstimateRequest(repo="o/r", issue_number=7, comment_id=555)

CONTEXT = EstimationContext(
    title="Т", body="О", labels=[], thread=[], branch=None, artifacts={}, truncated=False
)


@activity.defn(name="ack_estimate_command")
async def stub_ack(req: EstimateRequest):
    _state["acked"] = req.comment_id


@activity.defn(name="collect_estimation_context")
async def stub_context(req: EstimateRequest):
    _state["collected"] = True
    return CONTEXT


@activity.defn(name="extract_estimation_facts")
async def stub_facts(context: EstimationContext):
    return {"work_type": "new_development"}


@activity.defn(name="compute_estimate")
async def stub_compute(facts: dict, context: EstimationContext):
    _state["computed_from"] = facts
    return EstimateResult(markdown="## Оценка задачи", stopped=False)


@activity.defn(name="post_estimate_comment")
async def stub_post(req: EstimateRequest, result: EstimateResult):
    _state["posted"] = result.markdown


@activity.defn(name="post_estimate_error")
async def stub_error(req: EstimateRequest, stage: str):
    _state["error_stage"] = stage


@activity.defn(name="collect_estimation_context")
async def stub_context_boom(req: EstimateRequest):
    raise RuntimeError("GitHub недоступен")


ALL_STUBS = [stub_ack, stub_context, stub_facts, stub_compute, stub_post, stub_error]


async def _run(activities_list):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tq",
            workflows=[IssueEstimation],
            activities=activities_list,
        ):
            await env.client.execute_workflow(
                IssueEstimation.run, REQ, id=f"wf-{uuid.uuid4()}", task_queue="tq"
            )


@pytest.mark.timeout(60)
async def test_happy_path_acks_then_posts():
    _state.clear()
    await _run(ALL_STUBS)
    assert _state["acked"] == 555
    assert _state["collected"] is True
    assert _state["computed_from"] == {"work_type": "new_development"}
    assert _state["posted"] == "## Оценка задачи"
    assert "error_stage" not in _state


@pytest.mark.timeout(60)
async def test_failure_reports_the_stage_it_broke_on():
    _state.clear()
    await _run([stub_ack, stub_context_boom, stub_facts, stub_compute, stub_post, stub_error])
    assert _state["error_stage"] == "сбор контекста"
    assert "posted" not in _state
