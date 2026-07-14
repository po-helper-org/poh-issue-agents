import uuid
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from consolidation_workflow import ConsolidationWorkflow
from shared.workflow_types import (ConsolidationInput, SolutionProfile,
                                    ClusterSet, Cluster, ClusterMember, UnifyingIssueDraft,
                                    IssueInput)


@activity.defn(name="fetch_open_issues")
async def stub_fetch(cfg):
    return [IssueInput("o/r", 1, "t", "b", "", "User")]

@activity.defn(name="extract_solution_profile")
async def stub_profile(issue):
    return SolutionProfile(1, "t", "p", "FTS", "cut", "d", ["a"], "")

@activity.defn(name="cluster_profiles")
async def stub_cluster(profiles):
    return ClusterSet([Cluster("cluster-1", "FTS", "cut",
                               [ClusterMember(1, "primary", "x")], [])], [])

@activity.defn(name="synthesize_unifying_issue")
async def stub_synth(cluster, profiles):
    return UnifyingIssueDraft("cluster-1", "Unify", "# body", [1])

@activity.defn(name="write_consolidation_pr")
async def stub_write(clusterset, drafts, repo):
    return "http://pr/1"


@pytest.mark.timeout(30)
async def test_workflow_runs_end_to_end():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[ConsolidationWorkflow],
                          activities=[stub_fetch, stub_profile, stub_cluster,
                                      stub_synth, stub_write]):
            url = await env.client.execute_workflow(
                ConsolidationWorkflow.run,
                ConsolidationInput(repo="o/r"),
                id=f"c-{uuid.uuid4()}", task_queue="tq")
    assert url == "http://pr/1"
