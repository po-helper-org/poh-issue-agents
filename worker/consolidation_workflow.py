import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import consolidation_activities as ca
    from shared.workflow_types import ConsolidationInput, Increment


@workflow.defn
class ConsolidationWorkflow:
    @workflow.run
    async def run(self, cfg: ConsolidationInput):
        retry = RetryPolicy(maximum_attempts=3)
        refs = await workflow.execute_activity(
            ca.fetch_open_issues, cfg,
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)

        profiles = await asyncio.gather(*[
            workflow.execute_activity(ca.extract_solution_profile, r,
                                      start_to_close_timeout=timedelta(seconds=240),
                                      retry_policy=retry) for r in refs])

        taxonomy = await workflow.execute_activity(
            ca.derive_taxonomy, args=[profiles, None],
            start_to_close_timeout=timedelta(seconds=300), retry_policy=retry)

        assignments = await asyncio.gather(*[
            workflow.execute_activity(ca.assign_zone, args=[p, taxonomy],
                                      start_to_close_timeout=timedelta(seconds=180),
                                      retry_policy=retry) for p in profiles])

        by_zone: dict[str, list[int]] = {}
        for a in assignments:
            by_zone.setdefault(a.primary_zone, []).append(a.issue_number)

        increments = []
        for zone in taxonomy.zones:
            members = by_zone.get(zone.name, [])
            if not members:
                continue
            zi = await workflow.execute_activity(
                ca.slice_zone, args=[zone, members, profiles],
                start_to_close_timeout=timedelta(seconds=360),
                retry_policy=RetryPolicy(maximum_attempts=2))
            increments.extend(zi)

        other = by_zone.get("other", [])
        if other:
            increments.append(Increment(name="other:unassigned",
                                        rationale="вне выведенных зон — требует ручного разбора",
                                        issue_numbers=sorted(other)))

        drafts = await asyncio.gather(*[
            workflow.execute_activity(ca.synthesize_unifying_issue, args=[inc, profiles],
                                      start_to_close_timeout=timedelta(seconds=360),
                                      retry_policy=RetryPolicy(maximum_attempts=2))
            for inc in increments])

        return await workflow.execute_activity(
            ca.write_consolidation_pr, args=[taxonomy, increments, drafts, cfg.repo],
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)
