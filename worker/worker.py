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
from workflows import IssueLifecycle


async def main() -> None:
    client = await Client.connect(os.environ["TEMPORAL_ADDRESS"])
    worker = Worker(
        client,
        task_queue="issue-lifecycle",
        workflows=[IssueLifecycle],
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
        ],
        # Our workflow code is trusted first-party code; unsandboxed avoids the
        # per-task re-import of heavy modules (instructor/openai/pydantic).
        workflow_runner=UnsandboxedWorkflowRunner(),
        # Activities use a BLOCKING sync LLM client. A backfill burst (dozens of
        # workflows) otherwise spawns dozens of blocking activity threads that,
        # with the GIL, starve the single workflow event-loop thread — tripping
        # the 2s deadlock detector (TMPRL1101) and workflow-task timeouts. Cap
        # concurrent activities so the event loop keeps getting CPU.
        max_concurrent_activities=4,
    )
    print("Worker started, listening on task queue 'issue-lifecycle'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
