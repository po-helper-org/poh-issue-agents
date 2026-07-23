"""Smoke harness: start one IssueEstimation workflow without the webhook.

`/estimate` normally arrives as an `issue_comment.created` webhook, which
needs Layer B (GitHub App + public endpoint). This script starts the same
workflow directly against Temporal, so the estimation path — including the
real LLM call — can be exercised with only `temporal` and `worker` running.

The workflow reacts 👀 on the comment that carried the command. There is no
such comment here, so `--comment-id` defaults to 0: harmless under DRY_RUN
(the reaction is only logged), a 404 without it. Pass a real comment id when
running for real.

Usage:
    python scripts/estimate.py --issue 83
    python scripts/estimate.py --issue 83 --comment-id 2145678901
    python scripts/estimate.py --issue 83 --no-wait
"""

import argparse
import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio.client import Client

from shared.workflow_ids import estimate_workflow_id
from shared.workflow_types import EstimateRequest

try:
    from temporalio.client import WorkflowAlreadyStartedError
except ImportError:  # older/newer layout
    from temporalio.exceptions import WorkflowAlreadyStartedError  # type: ignore

TASK_QUEUE = "issue-lifecycle"

workflow_id_for = estimate_workflow_id


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--comment-id", type=int, default=0)
    parser.add_argument("--no-wait", action="store_true",
                        help="не ждать завершения (по умолчанию скрипт ждёт)")
    args = parser.parse_args()

    if not args.repo:
        raise SystemExit("set --repo or GITHUB_REPOSITORY")

    if args.comment_id == 0:
        print("comment-id не задан: реакция 👀 сработает только под DRY_RUN")

    request = EstimateRequest(
        repo=args.repo, issue_number=args.issue, comment_id=args.comment_id
    )
    wf_id = workflow_id_for(args.repo, args.issue, args.comment_id)

    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    try:
        handle = await client.start_workflow(
            "IssueEstimation", request, id=wf_id, task_queue=TASK_QUEUE,
            # Извлечение фактов — медленный LLM-вызов; при дефолтных 10 с
            # workflow-задача истекает раньше, чем воркер её разберёт, и
            # история переигрывается заново, сжигая повторные вызовы модели.
            task_timeout=timedelta(seconds=120),
        )
    except WorkflowAlreadyStartedError:
        raise SystemExit(f"{wf_id} уже выполняется — дождись его или задай другой --comment-id")

    print(f"started {wf_id}")
    if args.no_wait:
        return
    await handle.result()
    # Workflow гасит исключения в post_estimate_error, поэтому успешное
    # завершение здесь означает «дошёл до конца», а не «оценка получилась».
    # Что именно опубликовано — видно в логах воркера.
    print(f"finished {wf_id} — смотри `docker compose logs worker`")


if __name__ == "__main__":
    asyncio.run(main())
