import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows import IssueLifecycle
from shared.workflow_types import IssueInput, GateResult

_state = {}


@activity.defn(name="prefilter_bot_and_security")
async def stub_prefilter(issue): return None


@activity.defn(name="intake_gate")
async def stub_gate_vague(issue, thread):
    return GateResult(status="VAGUE", content="need details")


@activity.defn(name="escalate_to_human")
async def stub_escalate(issue):
    _state["escalated"] = True


@pytest.mark.timeout(30)
async def test_batch_vague_escalates_without_hanging():
    _state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq", workflows=[IssueLifecycle],
            activities=[stub_prefilter, stub_gate_vague, stub_escalate],
        ):
            await env.client.execute_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                           author_login="u", author_type="User", interactive=False),
                id=f"wf-{uuid.uuid4()}", task_queue="tq",
            )
    assert _state.get("escalated") is True
