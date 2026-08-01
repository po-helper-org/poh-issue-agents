import asyncio

import activities
from shared.workflow_types import EstimateRequest, IssueInput


def test_post_error_label_comments_and_labels(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append(("label", repo, n, label)))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    # activities are now sync defs (run in the worker's ThreadPoolExecutor);
    # call directly rather than via asyncio.run.
    activities.post_error_label(issue)

    assert ("label", "o/r", 7, "advisor:error") in calls
    assert any(c[0] == "comment" and c[1] == "o/r" and c[2] == 7 for c in calls)


def test_mark_analyzing_adds_label(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append((repo, n, label)))

    asyncio.run(activities.mark_analyzing("o/r", 5))

    assert calls == [("o/r", 5, "analyzing")]


def test_post_error_label_reports_reason_to_sentry(monkeypatch):
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)
    captured = {}
    monkeypatch.setattr(activities.sentry_setup, "capture_pipeline_failure",
                        lambda issue, exc_type, msg: captured.update(exc_type=exc_type, msg=msg))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.post_error_label(issue, "RuntimeError: z.ai timeout")

    # "ExcType: message" из catch-ветки workflow'а разбирается на тег и extra.
    assert captured == {"exc_type": "RuntimeError", "msg": "z.ai timeout"}


def test_post_estimate_error_reports_stage_to_sentry(monkeypatch):
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    monkeypatch.setattr(activities.github_client, "add_reaction", lambda *a: None)
    captured = {}
    monkeypatch.setattr(activities.sentry_setup, "capture_estimate_failure",
                        lambda req, stage, exc_type, msg: captured.update(
                            stage=stage, exc_type=exc_type))

    req = EstimateRequest(repo="o/r", issue_number=7, comment_id=99)
    activities.post_estimate_error(req, "извлечение фактов", "ValidationError: bad schema")

    assert captured == {"stage": "извлечение фактов", "exc_type": "ValidationError"}
