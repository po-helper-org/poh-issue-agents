import asyncio

import activities
from shared.workflow_types import IssueInput


def test_post_error_label_comments_and_labels(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append(("label", repo, n, label)))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    asyncio.run(activities.post_error_label(issue))

    assert ("label", "o/r", 7, "advisor:error") in calls
    assert any(c[0] == "comment" and c[1] == "o/r" and c[2] == 7 for c in calls)
