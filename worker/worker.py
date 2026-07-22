import asyncio
import logging
import os

from temporalio.client import Client
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
from workflows import IssueEstimation, IssueLifecycle


async def main() -> None:
    client = await Client.connect(os.environ["TEMPORAL_ADDRESS"])
    worker = Worker(
        client,
        task_queue="issue-lifecycle",
        workflows=[IssueLifecycle, IssueEstimation],
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
        ],
        # Our workflow code is trusted first-party code; unsandboxed avoids the
        # per-task re-import of heavy modules (instructor/openai/pydantic).
        workflow_runner=UnsandboxedWorkflowRunner(),
        # The activities use a BLOCKING sync LLM client that also does CPU-heavy
        # JSON/pydantic parsing. Under a backfill burst that starves the single
        # workflow event-loop thread of the GIL for >2s, tripping the deadlock
        # detector (TMPRL1101) with false positives — our workflows never truly
        # deadlock. debug_mode disables that detector; safe for trusted,
        # deterministic first-party workflows.
        debug_mode=True,
        # LLM calls are I/O-bound (release the GIL while awaiting the network),
        # so a modest fan-out speeds the backfill without real contention.
        max_concurrent_activities=8,
    )
    print("Worker started, listening on task queue 'issue-lifecycle'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
