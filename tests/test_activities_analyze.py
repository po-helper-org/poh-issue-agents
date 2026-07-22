import asyncio

import activities
from shared.workflow_types import AnalyzeInput


def _analyze(comment_id=999):
    return AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=comment_id)


def test_ack_reacts_and_comments(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "add_reaction",
                        lambda repo, cid, content="eyes": calls.append(("reaction", repo, cid, content)))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))

    asyncio.run(activities.ack_command(_analyze()))

    assert ("reaction", "o/r", 999, "eyes") in calls
    comment = next(c for c in calls if c[0] == "comment")
    assert "/analyze" in comment[3]


def test_ack_skips_reaction_without_comment_id(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("reaction attempted without comment_id")

    monkeypatch.setattr(activities.github_client, "add_reaction", boom)
    monkeypatch.setattr(activities.github_client, "post_comment", lambda repo, n, body: None)

    asyncio.run(activities.ack_command(_analyze(comment_id=None)))


def test_error_comment_mentions_reason_and_retry(monkeypatch):
    posted = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body, repo=repo, n=n))

    asyncio.run(activities.publish_analysis_error(_analyze(), "clone failed"))

    assert posted["repo"] == "o/r"
    assert posted["n"] == 5
    assert "clone failed" in posted["body"]
    assert "/analyze" in posted["body"]
