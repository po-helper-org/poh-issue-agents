"""Backfill: start one IssueLifecycle workflow per already-open Issue.

GitHub never sends webhooks for Issues that already exist, so the running
service alone never processes the current backlog. This script enumerates
open Issues via `gh` and starts workflows directly against Temporal.

Runs in non-interactive batch mode (interactive=False): a VAGUE issue
escalates instead of waiting for a human clarification that will not come.

Usage:
    python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY
    python scripts/backfill.py --issue 83      # single issue (smoke test)
    python scripts/backfill.py --limit 5       # first N
    python scripts/backfill.py --repo owner/name
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy

from shared.workflow_types import IssueInput

try:
    from temporalio.client import WorkflowAlreadyStartedError
except ImportError:  # older/newer layout
    from temporalio.exceptions import WorkflowAlreadyStartedError  # type: ignore

TASK_QUEUE = "issue-lifecycle"


def build_issue_input(repo: str, item: dict) -> IssueInput:
    author = item.get("author") or {}
    return IssueInput(
        repo=repo,
        issue_number=item["number"],
        title=item["title"],
        body=item.get("body") or "",
        author_login=author.get("login", ""),
        author_type="Bot" if author.get("is_bot") else "User",
        interactive=False,
    )


def list_open_issues(repo: str, limit: int) -> list[dict]:
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--limit", str(limit), "--json", "number,title,body,author"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out or "[]")


def workflow_id_for(repo: str, n: int) -> str:
    return f"issue-{repo}-{n}"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    if not args.repo:
        raise SystemExit("set --repo or GITHUB_REPOSITORY")

    if args.issue is not None:
        items = [i for i in list_open_issues(args.repo, args.limit) if i["number"] == args.issue]
        if not items:
            raise SystemExit(f"issue #{args.issue} not found among open issues")
    else:
        items = list_open_issues(args.repo, args.limit)

    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))

    started, skipped = 0, 0
    for item in items:
        issue = build_issue_input(args.repo, item)
        wf_id = workflow_id_for(args.repo, issue.issue_number)
        try:
            await client.start_workflow(
                "IssueLifecycle", issue, id=wf_id, task_queue=TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
            started += 1
            print(f"started {wf_id}")
        except WorkflowAlreadyStartedError:
            skipped += 1
            print(f"skip {wf_id} (already running)")
    print(f"done: started={started} skipped={skipped} total={len(items)}")


if __name__ == "__main__":
    asyncio.run(main())
