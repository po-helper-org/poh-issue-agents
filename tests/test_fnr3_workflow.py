import uuid
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from consolidation_workflow import ConsolidationWorkflow
from shared.workflow_types import (ConsolidationInput, IssueInput, SolutionProfile,
                                    Taxonomy, DeliveryZone, ZoneAssignment, Increment,
                                    UnifyingIssueDraft)


@activity.defn(name="fetch_open_issues")
async def f(cfg): return [IssueInput("o/r", 1, "t", "", "", "User")]
@activity.defn(name="extract_solution_profile")
async def p(issue): return SolutionProfile(1, "t", "e", "m", "tg", "d", ["a"], "")
@activity.defn(name="derive_taxonomy")
async def d(profiles, prior): return Taxonomy([DeliveryZone("z", "b", "s")])
@activity.defn(name="assign_zone")
async def a(profile, taxonomy): return ZoneAssignment(1, "z", [])
@activity.defn(name="slice_zone")
async def s(zone, members, profiles): return [Increment("z", "r", [1])]
@activity.defn(name="synthesize_unifying_issue")
async def sy(increment, profiles): return UnifyingIssueDraft("z", "T", "# b", [1])
@activity.defn(name="write_consolidation_pr")
async def w(taxonomy, increments, drafts, repo): return "http://pr/1"


@pytest.mark.timeout(30)
async def test_fnr3_workflow_end_to_end():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq", workflows=[ConsolidationWorkflow],
                          activities=[f, p, d, a, s, sy, w]):
            url = await env.client.execute_workflow(
                ConsolidationWorkflow.run, ConsolidationInput(repo="o/r"),
                id=f"c-{uuid.uuid4()}", task_queue="tq")
    assert url == "http://pr/1"
