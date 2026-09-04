"""Ревью человека будит круг правок.

Отказ: `poh-demo-checkout#172` — вебхук не подписан на события ревью и
обработчика не имеет, поэтому замечание человека не вызывает ничего. Контур
дважды объявил «PR готов к слиянию», не увидев `CHANGES_REQUESTED`.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "test-secret"


class FakeClient:
    def __init__(self) -> None:
        self.started: list[dict] = []

    async def start_workflow(self, workflow, *args, **kwargs):
        arg = args[0] if args else kwargs.get("args")
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return None


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)

    import main
    from fastapi.testclient import TestClient

    fake = FakeClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    return fake, TestClient(main.app)


def _post(app_client, event: str, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig,
                 "Content-Type": "application/json"},
    )


def _payload(state="changes_requested", login="kibarik", body="есть замечание",
            pr_body="Closes #171"):
    return {
        "action": "submitted",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 172, "body": pr_body},
        "review": {"id": 9, "state": state, "body": body,
                   "commit_id": "abc123", "user": {"login": login, "type": "User"}},
        "sender": {"login": login},
    }


def test_a_human_review_starts_the_lifecycle(make_client):
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review", _payload())

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert fake.started, "цикл не был поднят — замечание снова потеряно"
    started = fake.started[0]
    assert started["workflow"] == "IssueLifecycle"
    assert started.get("start_signal") == "agent_event"
    event = started["start_signal_args"][0]
    assert event.phase == "pr-review"


def test_an_approval_starts_nothing(make_client):
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review", _payload(state="approved"))

    assert resp.status_code == 200
    assert fake.started == []


def test_an_author_outside_the_allowlist_starts_nothing(make_client, monkeypatch):
    """Круг правок стоит прогона агента — запускать его по ревью произвольного
    участника нельзя (R5)."""
    monkeypatch.setenv("AGENT_TRIGGER_ALLOWLIST", "kibarik")
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review", _payload(login="прохожий"))

    assert resp.status_code == 200
    assert fake.started == []


def test_a_review_on_an_unrelated_pr_goes_to_audit(make_client):
    """PR не заводился контуром — событие роняется в аудит, а не поднимает
    цикл разработки (R6)."""
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review",
                _payload(pr_body="без ссылки на задачу"))

    assert resp.status_code == 200
    assert len(fake.started) == 1
    assert fake.started[0]["workflow"] == "OrphanAgentEvent"


def _comment_payload(login="kibarik"):
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {"number": 172, "body": "Closes #171"},
        "comment": {"id": 5, "body": "здесь опечатка", "path": "src/a.py",
                    "line": 12, "commit_id": "abc123",
                    "user": {"login": login, "type": "User"}},
        "sender": {"login": login},
    }


def test_an_inline_comment_starts_the_lifecycle(make_client):
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review_comment", _comment_payload())

    assert resp.status_code == 200
    assert fake.started
    assert fake.started[0]["workflow"] == "IssueLifecycle"


def test_an_inline_comment_from_a_bot_starts_nothing(make_client):
    payload = _comment_payload()
    payload["comment"]["user"] = {"login": "pr-agent[bot]", "type": "Bot"}
    fake, app_client = make_client

    resp = _post(app_client, "pull_request_review_comment", payload)

    assert resp.status_code == 200
    assert fake.started == []
