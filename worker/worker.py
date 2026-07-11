import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

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
            activities.classify_issue,
            activities.duplicate_check,
            activities.score_priority,
            activities.post_priority_comment,
            activities.run_research_pipeline,
            activities.run_bug_pipeline,
            activities.trigger_openhands_resolver,
        ],
    )
    print("Worker started, listening on task queue 'issue-lifecycle'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
