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
async def test_orchestrates_all_stages_in_order():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "research/issue-5"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert calls == ["ack", "prepare", "stage:task", "stage:concept", "stage:debate",
                     "stage:sysreq", "stage:validate", "publish", "cleanup"]


@pytest.mark.asyncio
async def test_stage_failure_publishes_error_and_cleans_up():
    calls = []
    reported = {}

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        if stage_name == "sysreq":
            raise RuntimeError("boom-sysreq")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "b"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        reported["reason"] = reason
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert calls[:6] == ["ack", "prepare", "stage:task", "stage:concept", "stage:debate", "stage:sysreq"]
    assert "stage:validate" not in calls          # остановились на sysreq
    assert "publish" not in calls
    assert "error" in calls and "boom-sysreq" in reported["reason"]
    assert calls[-1] == "cleanup"                  # cleanup всегда последним


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_success():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "research/issue-5"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")
        raise RuntimeError("cleanup-boom")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error]):
            # завершается без ошибки, несмотря на падение cleanup
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert "publish" in calls       # реальный результат состоялся
    assert "cleanup" in calls       # cleanup вызывался
    assert "error" not in calls     # успех НЕ превратился в ошибку
