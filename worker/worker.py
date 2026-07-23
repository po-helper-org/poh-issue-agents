import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import UnsandboxedWorkflowRunner, Worker

# Surface INFO logs — notably github_client's [DRY_RUN] lines, which are the
# operator's audit of what the pipeline WOULD do before going live. Without
# this the root logger defaults to WARNING and swallows them.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,  # temporalio configures the root logger on import; reset it
)

import activities
import consolidation_activities as ca
from consolidation_workflow import ConsolidationWorkflow
from shared import sentry_setup
from shared.temporal_client import connect_temporal
from workflows import IssueEstimation, IssueLifecycle

sentry_setup.configure("worker")  # no-op без SENTRY_DSN


async def main() -> None:
    client = await connect_temporal()
    worker = Worker(
        client,
        task_queue="issue-lifecycle",
        workflows=[IssueLifecycle, IssueEstimation, ConsolidationWorkflow],
        activities=[
            activities.prefilter_bot_and_security,
            activities.intake_gate,
            activities.post_clarifying_question,
            activities.close_as_spam,
            activities.escalate_to_human,
            activities.post_error_label,
            activities.classify_issue,
            activities.duplicate_check,
            activities.score_priority,
            activities.post_priority_comment,
            activities.run_research_pipeline,
            activities.run_bug_pipeline,
            activities.trigger_openhands_resolver,
            activities.ack_estimate_command,
            activities.collect_estimation_context,
            activities.extract_estimation_facts,
            activities.compute_estimate,
            activities.post_estimate_comment,
            activities.post_estimate_error,
            ca.fetch_open_issues,
            ca.extract_solution_profile,
            ca.derive_taxonomy,
            ca.assign_zone,
            ca.slice_zone,
            ca.synthesize_unifying_issue,
            ca.write_consolidation_pr,
        ],
        # Our workflow code is trusted first-party code; unsandboxed avoids the
        # per-task re-import of heavy modules (instructor/openai/pydantic).
        workflow_runner=UnsandboxedWorkflowRunner(),
        # The activities are now SYNC defs doing BLOCKING LLM/HTTP + CPU-heavy
        # pydantic parsing. Running them in a ThreadPoolExecutor keeps the
        # blocking work OFF the workflow event-loop thread, so under a backfill
        # burst the loop stays free to process workflow tasks (no task-timeout
        # churn) and up to `max_workers` activities run truly concurrently.
        activity_executor=ThreadPoolExecutor(max_workers=3),
        # debug_mode still disables the deadlock detector (TMPRL1101); with the
        # blocking work offloaded it should rarely trigger, but it is safe for
        # trusted, deterministic first-party workflows.
        debug_mode=True,
        # Capped at 3: the z.ai backend rate-limits (HTTP 429) under an 8-wide
        # fan-out, and Instructor's own retries multiply the request rate. 3
        # concurrent activities keeps the backfill under the limit while still
        # draining meaningfully faster than serial.
        max_concurrent_activities=3,
    )
    print("Worker started, listening on task queue 'issue-lifecycle'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
