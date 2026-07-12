import sys
from pathlib import Path

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
