"""Sentry-обвязка: скраббер секретов, необязательность DSN, no-op без configure.

Сеть не трогаем: скраббер — чистая функция, а capture_* без configure() = no-op.
"""
import os

from shared import sentry_setup
from shared.workflow_types import EstimateRequest, IssueInput


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
    req = EstimateRequest(repo="o/r", issue_number=7, comment_id=99)
    sentry_setup.capture_pipeline_failure(issue, "RuntimeError", "boom")
    sentry_setup.capture_estimate_failure(req, "расчёт", "ValueError", "bad")
