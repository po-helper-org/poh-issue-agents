"""Путь issue_comment в вебхуке: на нём держатся обе команды, а тестов на
уровне HTTP у него не было вовсе (покрытие webhook/main.py — 72%)."""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "test-secret"


class FakeHandle:
    def __init__(self, sink: list, fail: bool = False) -> None:
        self._sink = sink
        self._fail = fail

    async def signal(self, name, *args):
        if self._fail:
            raise RuntimeError("workflow уже завершён")
        self._sink.append((name, args))


class FakeClient:
    def __init__(self, already: set[str] | None = None, signal_fails: bool = False) -> None:
        self.started: list[dict] = []
        self.signals: list = []
        self._already = already or set()
        self._signal_fails = signal_fails

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})

    def get_workflow_handle(self, wf_id):
        self.signals.append(wf_id)
        return FakeHandle(self.signals, fail=self._signal_fails)


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)

    import main

    from fastapi.testclient import TestClient

    def _build(**kwargs):
        fake = FakeClient(**kwargs)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "issue_comment", "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": "dlv-1", "Content-Type": "application/json"})


def _comment(body: str, user_type: str = "User", comment_id: int = 555) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "Тестовая задача", "body": "тело",
                  "user": {"login": "alice", "type": "User"}},
        "comment": {"id": comment_id, "body": body,
                    "user": {"login": "alice", "type": user_type}},
        "sender": {"login": "alice"},
    }


def test_estimate_command_starts_estimation_with_comment_id(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _comment("/estimate")).status_code == 200

    call = fake.started[0]
    assert call["workflow"] == "IssueEstimation"
    # comment_id в id прогона: повторная доставка того же вебхука не запустит вторую оценку.
    assert call["id"] == "estimate-acme/widgets-7-555"
    assert call["arg"].comment_id == 555


def test_analyze_command_starts_analysis_and_notifies_triage(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _comment("/analyze")).status_code == 200

    call = fake.started[0]
    assert call["workflow"] == "IssueAnalysis"
    assert call["id"] == "analysis-acme/widgets-7"
    assert call["arg"].comment_id == 555
    # Живому триажу уходит уведомление — он повесит метку `analyzing`.
    assert ("analyze_requested", (555,)) in fake.signals


def test_analyze_survives_a_finished_triage_workflow(webhook):
    """Триаж мог завершиться неделю назад — сигналить некому, но анализ обязан
    стартовать: уведомление косметическое, исполнитель — IssueAnalysis."""
    fake, app_client = webhook(signal_fails=True)

    assert _post(app_client, _comment("/analyze")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["IssueAnalysis"]


def test_repeated_analyze_does_not_start_a_second_run(webhook):
    fake, app_client = webhook(already={"IssueAnalysis"})

    assert _post(app_client, _comment("/analyze")).status_code == 200
    assert fake.started == []


def test_repeated_estimate_delivery_is_swallowed(webhook):
    fake, app_client = webhook(already={"IssueEstimation"})

    assert _post(app_client, _comment("/estimate")).status_code == 200
    assert fake.started == []


def test_plain_comment_feeds_the_clarification_loop(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _comment("да, речь про мобильный клиент")).status_code == 200

    assert fake.started == []
    assert fake.signals[0] == "issue-acme/widgets-7"
    assert ("user_comment", ("да, речь про мобильный клиент",)) in fake.signals


def test_comment_after_workflow_finished_is_not_an_error(webhook):
    """Issue закрыт, воркфлоу завершён — комментарий просто некуда сигналить."""
    fake, app_client = webhook(signal_fails=True)

    assert _post(app_client, _comment("обычный текст")).status_code == 200


def test_bot_comments_are_ignored(webhook):
    """Сервис не должен сигналить сам себе: свои же комментарии приходят обратно."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("/analyze", user_type="Bot")).status_code == 200
    assert fake.started == []
    assert fake.signals == []


def test_non_created_actions_are_ignored(webhook):
    fake, app_client = webhook()
    payload = _comment("/analyze")
    payload["action"] = "edited"

    assert _post(app_client, payload).status_code == 200
    assert fake.started == []


def test_quoted_command_does_not_run(webhook):
    """Ответ с процитированной командой не должен запускать её повторно."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("> /analyze\n\nсогласен")).status_code == 200

    assert fake.started == []
    assert ("user_comment", ("> /analyze\n\nсогласен",)) in fake.signals
