"""Launch a single ConsolidationWorkflow over the open backlog."""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

from temporalio.client import Client

from shared.workflow_types import ConsolidationInput

TASK_QUEUE = "issue-lifecycle"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    args = parser.parse_args()
    if not args.repo:
        raise SystemExit("set --repo or GITHUB_REPOSITORY")
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    url = await client.execute_workflow(
        "ConsolidationWorkflow", ConsolidationInput(repo=args.repo),
        id=f"consolidation-{args.repo}-{uuid.uuid4().hex[:8]}", task_queue=TASK_QUEUE,
        # A consolidation run accumulates a long history (one activity result per
        # backlog issue). Replaying it must fit inside the workflow-task timeout;
        # the 10s default is too tight once the backlog is ~50 issues and the
        # worker churns on WorkflowTaskTimedOut. 120s matches backfill.py.
        task_timeout=timedelta(seconds=120))
    print(f"consolidation PR: {url}")


if __name__ == "__main__":
    asyncio.run(main())
