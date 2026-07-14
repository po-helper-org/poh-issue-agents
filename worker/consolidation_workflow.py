import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import consolidation_activities as ca
    from shared.workflow_types import ConsolidationInput


@workflow.defn
class ConsolidationWorkflow:
    @workflow.run
    async def run(self, cfg: ConsolidationInput):
        retry = RetryPolicy(maximum_attempts=3)
        refs = await workflow.execute_activity(
            ca.fetch_open_issues, cfg,
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)

        profiles = await asyncio.gather(*[
            workflow.execute_activity(
                ca.extract_solution_profile, r,
                start_to_close_timeout=timedelta(seconds=180), retry_policy=retry)
            for r in refs])

        clusterset = await workflow.execute_activity(
            ca.cluster_profiles, profiles,
            start_to_close_timeout=timedelta(seconds=300), retry_policy=retry)

        drafts = await asyncio.gather(*[
            workflow.execute_activity(
                ca.synthesize_unifying_issue, args=[c, profiles],
                start_to_close_timeout=timedelta(seconds=240),
                retry_policy=RetryPolicy(maximum_attempts=2))
            for c in clusterset.clusters])

        return await workflow.execute_activity(
            ca.write_consolidation_pr, args=[clusterset, drafts, cfg.repo],
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)
