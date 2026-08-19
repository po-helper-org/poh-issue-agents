import asyncio

import activities
from shared.workflow_types import AnalyzeInput, EstimateRequest, IssueInput


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


def _comment_of(calls) -> str:
    return next(c[3] for c in calls if c[0] == "comment")


def test_post_error_label_puts_the_sentry_link_in_the_comment(monkeypatch):
    """Логи контейнера человеку недоступны: без ссылки «не удалось» — тупик."""
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)
    monkeypatch.setattr(activities.sentry_setup, "capture_pipeline_failure",
                        lambda *a: "ev-1")
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.post_error_label(issue, "RuntimeError: z.ai timeout")

    assert "https://poh-orgranization.sentry.io/issues/?query=ev-1" in _comment_of(calls)


def test_error_comment_has_no_dangling_link_when_sentry_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)
    monkeypatch.setattr(activities.sentry_setup, "capture_pipeline_failure",
                        lambda *a: None)

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.post_error_label(issue)

    assert "Sentry" not in _comment_of(calls)


def test_publish_analysis_error_reports_and_links(monkeypatch):
    """Дорогой прогон падал молча для Sentry: сюда эскалации не было вовсе."""
    calls = []
    captured = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))

    def capture(analyze, exc_type, message):
        captured.update(exc_type=exc_type, message=message)
        return "ev-2"

    monkeypatch.setattr(activities.sentry_setup, "capture_analysis_failure", capture)
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")

    asyncio.run(activities.publish_analysis_error(
        AnalyzeInput(repo="o/r", issue_number=7, title="t", body="b"),
        "RateLimitError: z.ai quota exceeded"))

    assert captured == {"exc_type": "RateLimitError", "message": "z.ai quota exceeded"}
    assert "https://poh-orgranization.sentry.io/issues/?query=ev-2" in _comment_of(calls)


def test_post_estimate_error_links_the_event(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_reaction", lambda *a: None)
    monkeypatch.setattr(activities.sentry_setup, "capture_estimate_failure",
                        lambda *a: "ev-3")
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")

    activities.post_estimate_error(EstimateRequest(repo="o/r", issue_number=7,
                                                   comment_id=99), "расчёт")

    assert "https://poh-orgranization.sentry.io/issues/?query=ev-3" in _comment_of(calls)


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
