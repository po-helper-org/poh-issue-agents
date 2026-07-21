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


@pytest.mark.timeout(30)
async def test_fnr3_workflow_other_zone_not_dropped():
    received_increments = []

    @activity.defn(name="fetch_open_issues")
    async def f2(cfg: ConsolidationInput) -> list[IssueInput]:
        return [IssueInput("o/r", 1, "t1", "", "", "User"),
                IssueInput("o/r", 2, "t2", "", "", "User")]

    @activity.defn(name="extract_solution_profile")
    async def p2(issue: IssueInput) -> SolutionProfile:
        return SolutionProfile(issue.issue_number, "t", "e", "m", "tg", "d", ["a"], "")

    @activity.defn(name="derive_taxonomy")
    async def d2(profiles: list[SolutionProfile], prior) -> Taxonomy:
        return Taxonomy([DeliveryZone("z", "b", "s")])

    @activity.defn(name="assign_zone")
    async def a2(profile: SolutionProfile, taxonomy: Taxonomy) -> ZoneAssignment:
        if profile.issue_number == 1:
            return ZoneAssignment(1, "z", [])
        return ZoneAssignment(2, "other", [])

    @activity.defn(name="slice_zone")
    async def s2(zone: DeliveryZone, members: list[int],
                  profiles: list[SolutionProfile]) -> list[Increment]:
        return [Increment("z", "r", members)]

    @activity.defn(name="synthesize_unifying_issue")
    async def sy2(increment: Increment, profiles: list[SolutionProfile]) -> UnifyingIssueDraft:
        return UnifyingIssueDraft(increment.name, "T", "# b", increment.issue_numbers)

    @activity.defn(name="write_consolidation_pr")
    async def w2(taxonomy: Taxonomy, increments: list[Increment],
                  drafts: list[UnifyingIssueDraft], repo: str) -> str:
        received_increments.extend(increments)
        return "http://pr/2"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq2", workflows=[ConsolidationWorkflow],
                          activities=[f2, p2, d2, a2, s2, sy2, w2]):
            url = await env.client.execute_workflow(
                ConsolidationWorkflow.run, ConsolidationInput(repo="o/r"),
                id=f"c-{uuid.uuid4()}", task_queue="tq2")

    assert url == "http://pr/2"
    assert any(2 in inc.issue_numbers for inc in received_increments)
