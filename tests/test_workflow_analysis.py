import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import AnalyzeInput
from workflows import IssueAnalysis


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=1)


@pytest.mark.asyncio
async def test_happy_path_acks_then_runs_pipeline():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="run_analysis_pipeline")
    async def pipeline(analyze: AnalyzeInput) -> str:
        calls.append("pipeline")
        return "research/issue-5"

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=task_queue,
                          workflows=[IssueAnalysis],
                          activities=[ack, pipeline, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(),
                id=f"analysis-{uuid.uuid4()}", task_queue=task_queue,
            )

    assert calls == ["ack", "pipeline"]


@pytest.mark.asyncio
async def test_pipeline_failure_publishes_error_and_does_not_retry():
    attempts = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        pass

    @activity.defn(name="run_analysis_pipeline")
    async def pipeline(analyze: AnalyzeInput) -> str:
        attempts.append(1)
        raise RuntimeError("boom")

    reported = {}

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        reported["reason"] = reason

    async with await WorkflowEnvironment.start_time_skipping() as env:
        task_queue = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=task_queue,
                          workflows=[IssueAnalysis],
                          activities=[ack, pipeline, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(),
                id=f"analysis-{uuid.uuid4()}", task_queue=task_queue,
            )

    assert len(attempts) == 1, "дорогой недетерминированный прогон не должен ретраиться"
    assert "boom" in reported["reason"]
