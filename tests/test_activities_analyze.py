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


def test_ack_posts_comment_even_when_reaction_raises(monkeypatch):
    """Реакция — декорация, комментарий — сама суть ack. Если реакция падает
    (комментарий-триггер удалили → 404, rate limit), ack обязан всё равно
    дойти, а исключение не должно уйти наружу и уронить весь /analyze."""
    def boom(repo, cid, content="eyes"):
        raise RuntimeError("404 Not Found: comment deleted")

    posted = {}
    monkeypatch.setattr(activities.github_client, "add_reaction", boom)
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(repo=repo, n=n, body=body))

    asyncio.run(activities.ack_command(_analyze(comment_id=999)))  # не должно поднять исключение

    assert posted["repo"] == "o/r"
    assert posted["n"] == 5
    assert "/analyze" in posted["body"]


def test_ack_skips_reaction_without_comment_id(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("reaction attempted without comment_id")

    posted = {}
    monkeypatch.setattr(activities.github_client, "add_reaction", boom)
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(repo=repo, n=n, body=body))

    asyncio.run(activities.ack_command(_analyze(comment_id=None)))

    # Ensure acknowledgement comment was still posted even without comment_id
    assert posted["repo"] == "o/r"
    assert posted["n"] == 5
    assert "/analyze" in posted["body"]


def test_error_comment_mentions_reason_and_retry(monkeypatch):
    posted = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body, repo=repo, n=n))

    asyncio.run(activities.publish_analysis_error(_analyze(), "clone failed"))

    assert posted["repo"] == "o/r"
    assert posted["n"] == 5
    assert "clone failed" in posted["body"]
    assert "/analyze" in posted["body"]
