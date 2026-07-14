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
                start_to_close_timeout=timedelta(seconds=240), retry_policy=retry)
            for r in refs])

        # The reduce call clusters ALL profiles in one shot; over a ~50-issue
        # backlog that is a large structured-output generation, and under the
        # z.ai rate limit + Instructor retries it can run well past a few
        # minutes. 900s per attempt (2 attempts) keeps it from a false
        # StartToClose timeout (the 300s default failed a 50-issue run).
        clusterset = await workflow.execute_activity(
            ca.cluster_profiles, profiles,
            start_to_close_timeout=timedelta(seconds=900),
            retry_policy=RetryPolicy(maximum_attempts=2))

        drafts = await asyncio.gather(*[
            workflow.execute_activity(
                ca.synthesize_unifying_issue, args=[c, profiles],
                start_to_close_timeout=timedelta(seconds=360),
                retry_policy=RetryPolicy(maximum_attempts=2))
            for c in clusterset.clusters])

        return await workflow.execute_activity(
            ca.write_consolidation_pr, args=[clusterset, drafts, cfg.repo],
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)
