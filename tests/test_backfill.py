import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backfill
from shared.workflow_types import IssueInput


def test_build_issue_input_maps_bot_author():
    item = {"number": 5, "title": "t", "body": "b",
            "author": {"login": "dependabot", "is_bot": True}}
    issue = backfill.build_issue_input("o/r", item)
    assert issue == IssueInput(
        repo="o/r", issue_number=5, title="t", body="b",
        author_login="dependabot", author_type="Bot", interactive=False,
    )


def test_build_issue_input_maps_human_author_and_null_body():
    item = {"number": 6, "title": "t", "body": None,
            "author": {"login": "alice", "is_bot": False}}
    issue = backfill.build_issue_input("o/r", item)
    assert issue.author_type == "User"
    assert issue.body == ""
    assert issue.interactive is False


def test_start_workflow_uses_reject_duplicate_id_reuse_policy(monkeypatch):
    """Re-running backfill against an already-completed workflow ID must raise
    WorkflowAlreadyStartedError (not silently re-execute and re-post comments).
    That only happens if id_reuse_policy=REJECT_DUPLICATE is passed through."""
    fake_issue = {
        "number": 42, "title": "t", "body": "b",
        "author": {"login": "alice", "is_bot": False},
    }
    monkeypatch.setattr(backfill, "list_open_issues", lambda repo, limit: [fake_issue])
    monkeypatch.setattr(sys, "argv", ["backfill", "--repo", "o/r", "--issue", "42"])

    mock_client = AsyncMock()
    mock_client.start_workflow = AsyncMock()

    with patch("backfill.connect_temporal", AsyncMock(return_value=mock_client)):
        asyncio.run(backfill.main())

    mock_client.start_workflow.assert_awaited_once()
    _, kwargs = mock_client.start_workflow.call_args
    assert kwargs["id_reuse_policy"] == backfill.WorkflowIDReusePolicy.REJECT_DUPLICATE
