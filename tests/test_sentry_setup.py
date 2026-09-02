"""Sentry-обвязка: скраббер секретов, необязательность DSN, no-op без configure.

Сеть не трогаем: скраббер — чистая функция, а capture_* без configure() = no-op.
"""
import os

from shared import sentry_setup
from shared.workflow_types import AnalyzeInput, EstimateRequest, IssueInput


# --- Скраббер ---

def test_filters_secrets_in_stack_frame_vars():
    event = {"exception": {"values": [{"stacktrace": {"frames": [{"vars": {
        "token": "ghs_liveInstallationToken",
        "GITHUB_PRIVATE_KEY_B64": "LS0tLS1CRUdJTi...",
        "ZAI_API_KEY": "sk-live",
        "repo": "po-helper-org/app",
        "attempts": 5,
    }}]}}]}}
    sentry_setup._scrub_event(event)
    v = event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert v["token"] == "[Filtered]"
    assert v["GITHUB_PRIVATE_KEY_B64"] == "[Filtered]"
    assert v["ZAI_API_KEY"] == "[Filtered]"
    assert v["repo"] == "po-helper-org/app"  # диагностика сохраняется
    assert v["attempts"] == 5


def test_filters_request_headers_and_drops_body():
    event = {"request": {
        "headers": {"X-Hub-Signature-256": "sha256=deadbeef", "User-Agent": "GitHub"},
        "data": "весь payload webhook'а",
    }}
    sentry_setup._scrub_event(event)
    assert event["request"]["headers"]["X-Hub-Signature-256"] == "[Filtered]"
    assert event["request"]["headers"]["User-Agent"] == "GitHub"
    assert "data" not in event["request"]


def test_truncates_long_values():
    event = {"extra": {"body": "x" * 5000}}
    sentry_setup._scrub_event(event)
    assert len(event["extra"]["body"]) < 5000
    assert event["extra"]["body"].endswith("[truncated]")


def test_scrubs_nested_dicts():
    event = {"extra": {"ctx": {"api_token": "t", "n": 1}}}
    sentry_setup._scrub_event(event)
    assert event["extra"]["ctx"]["api_token"] == "[Filtered]"
    assert event["extra"]["ctx"]["n"] == 1


def test_handles_event_without_exception_or_request():
    event = {"message": "hello"}
    assert sentry_setup._scrub_event(event) == {"message": "hello"}


# --- Необязательность (процедура отката) ---

def test_configure_without_dsn_is_noop(monkeypatch):
    monkeypatch.setattr(sentry_setup, "_configured", False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert sentry_setup.configure("worker") is False


def test_capture_helpers_are_noop_when_disabled(monkeypatch):
    # Без configure() (или с _configured=False) хелперы не бросают и не требуют
    # установленного sentry_sdk — это гарантия, что стек без DSN работает как раньше.
    monkeypatch.setattr(sentry_setup, "_configured", False)
    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    analyze = AnalyzeInput(repo="o/r", issue_number=7, title="t", body="b")
    req = EstimateRequest(repo="o/r", issue_number=7, comment_id=99)
    assert sentry_setup.capture_pipeline_failure(issue, "RuntimeError", "boom") is None
    assert sentry_setup.capture_analysis_failure(analyze, "RuntimeError", "boom") is None
    assert sentry_setup.capture_estimate_failure(req, "расчёт", "ValueError", "bad") is None
    assert sentry_setup.capture_followups_failure(issue, "RuntimeError", "boom") is None
    assert sentry_setup.capture_criterion_gate_stall(issue, "RuntimeError", "boom") is None
    assert sentry_setup.capture_nondeterminism("run-1", "[TMPRL1100]") is None
    # Находка F5 (второй круг финального ревью): `capture_answer_question_
    # failure` не звалась НИ РАЗУ ни в одном тесте — воркфлоу-тесты заглушают
    # саму активность `report_answer_question_failure` по имени и до неё
    # никогда не доходят. То же для двух новых хелперов этого круга (F6, F9).
    assert sentry_setup.capture_answer_question_failure(issue, "RuntimeError", "boom") is None
    assert sentry_setup.capture_question_repoint_failure(issue, "RuntimeError", "boom") is None
    assert sentry_setup.capture_question_close_failure(issue, "RuntimeError", "boom") is None
    # Находка G2 (третий круг финального ревью): новый хелпер этого круга —
    # тот же приём, что и у соседей выше.
    assert sentry_setup.capture_ask_question_gate_failure(issue, "RuntimeError", "boom") is None


# --- Ссылка на событие для комментария в Issue ---

def test_event_url_needs_the_org_slug(monkeypatch):
    # Из DSN слаг не выводится: там числовой id организации.
    monkeypatch.delenv("SENTRY_ORG", raising=False)
    assert sentry_setup.event_url("abc123") is None


def test_event_url_points_at_the_event(monkeypatch):
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")
    assert sentry_setup.event_url("abc123") == (
        "https://poh-orgranization.sentry.io/issues/?query=abc123")


def test_debug_reference_is_empty_without_an_event(monkeypatch):
    # Sentry выключен — обещать ссылку, за которой ничего нет, нельзя.
    monkeypatch.setenv("SENTRY_ORG", "poh-orgranization")
    assert sentry_setup.debug_reference(None) == ""


def test_debug_reference_falls_back_to_the_bare_event_id(monkeypatch):
    monkeypatch.delenv("SENTRY_ORG", raising=False)
    reference = sentry_setup.debug_reference("abc123")
    assert "abc123" in reference and "https://" not in reference
