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


# --- report_criterion_gate_stall: тело активности, а не только вызов её из
# воркфлоу (тот уже проверен в tests/test_workflow_acceptance_gate.py стабом).
# Тот же приём, что и у post_error_label выше: Sentry — ПЕРЕД комментарием,
# сообщение не должно утверждать «критерия нет».

def test_report_criterion_gate_stall_reports_reason_to_sentry(monkeypatch):
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    captured = {}
    monkeypatch.setattr(activities.sentry_setup, "capture_criterion_gate_stall",
                        lambda issue, exc_type, msg: captured.update(
                            exc_type=exc_type, msg=msg))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_criterion_gate_stall(issue, "ApplicationError: GitHub 503")

    assert captured == {"exc_type": "ApplicationError", "msg": "GitHub 503"}


def test_report_criterion_gate_stall_puts_the_sentry_link_in_the_comment(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.sentry_setup, "capture_criterion_gate_stall",
                        lambda *a: "ev-4")
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_criterion_gate_stall(issue, "ApplicationError: GitHub 503")

    assert "https://poh-orgranization.sentry.io/issues/?query=ev-4" in _comment_of(calls)


def test_report_criterion_gate_stall_does_not_claim_criterion_is_absent(monkeypatch):
    """Требование ревью: сообщение не лжёт. Отказ ЧТЕНИЯ — не «критерия нет»
    (критерий может быть на месте, просто тело Issue не отдалось), и текст
    обязан говорить именно про попытку прочитать, а не про содержимое."""
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.sentry_setup, "capture_criterion_gate_stall",
                        lambda *a: None)

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_criterion_gate_stall(issue, "ApplicationError: GitHub 503")

    text = _comment_of(calls)
    assert "критерия нет" not in text.lower()
    assert "не вижу критери" not in text.lower()
    assert "не смог проверить" in text.lower()


# --- report_ask_question_gate_failure (G2, третий круг финального ревью):
# тело активности, а не только вызов её из воркфлоу (тот уже проверен стабом
# в tests/test_workflow_final_review_gate_findings.py). Тот же приём, что и у
# report_criterion_gate_stall выше: Sentry — ПЕРЕД комментарием, а текст не
# должен лгать про то, что именно сломалось.

def test_report_ask_question_gate_failure_reports_reason_to_sentry(monkeypatch):
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    captured = {}
    monkeypatch.setattr(activities.sentry_setup, "capture_ask_question_gate_failure",
                        lambda issue, exc_type, msg: captured.update(
                            exc_type=exc_type, msg=msg))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_ask_question_gate_failure(issue, "ApplicationError: GitHub 422")

    assert captured == {"exc_type": "ApplicationError", "msg": "GitHub 422"}


def test_report_ask_question_gate_failure_puts_the_sentry_link_in_the_comment(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.sentry_setup, "capture_ask_question_gate_failure",
                        lambda *a: "ev-5")
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_ask_question_gate_failure(issue, "ApplicationError: GitHub 422")

    assert "https://poh-orgranization.sentry.io/issues/?query=ev-5" in _comment_of(calls)


def test_report_ask_question_gate_failure_does_not_claim_criterion_is_missing(monkeypatch):
    """Находка G2 (Important, третий круг финального ревью): к моменту этого
    вызова критерий уже прочитан и признан отсутствующим (иначе гейт не дошёл
    бы до постановки вопроса) — упала САМА постановка. Сообщение обязано
    говорить о вопросе, а не переиспользовать текст `report_criterion_gate_
    stall` («не смог проверить критерий приёмки») — это неправда именно
    здесь: критерий проверен, вопрос не задался."""
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.sentry_setup, "capture_ask_question_gate_failure",
                        lambda *a: None)

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    activities.report_ask_question_gate_failure(issue, "ApplicationError: GitHub 422")

    text = _comment_of(calls)
    assert "не смог проверить критерий" not in text.lower()
    assert "не смог задать" in text.lower()
