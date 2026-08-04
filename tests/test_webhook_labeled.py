"""Лейбл-решение человека (research-me / bug-me / build-me) обязан доезжать до
Temporal даже когда воркфлоу триажа по issue не существует."""

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

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})

    def get_workflow_handle(self, wf_id):
        raise AssertionError("labeled не должен слать голый signal в несуществующий workflow")


@pytest.fixture
def client_and_app(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main

    fake = FakeClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(main, "get_temporal_client", _get_client)

    from fastapi.testclient import TestClient

    return fake, TestClient(main.app)


def _post(app_client, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig,
                 "Content-Type": "application/json"},
    )


def _labeled_payload(label: str) -> dict:
    return {
        "action": "labeled",
        "label": {"name": label},
        "repository": {"full_name": "acme/widgets"},
        "issue": {
            "number": 7,
            "title": "Тестовая задача",
            "body": "тело",
            "user": {"login": "alice", "type": "User"},
        },
    }


def test_research_me_signal_with_start(client_and_app):
    """Воркфлоу нет — лейбл поднимает его и доставляет сигнал одним вызовом."""
    fake, app_client = client_and_app

    assert _post(app_client, _labeled_payload("research-me")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["id"] == "issue-acme/widgets-7"
    assert call["start_signal"] == "human_decision"
    assert call["start_signal_args"] == ["research-me"]
    assert call["arg"].issue_number == 7
    # Отвечать на уточняющий вопрос тут некому: VAGUE обязан эскалировать,
    # иначе только что доставленный сигнал съест цикл уточнений.
    assert call["arg"].interactive is False


def test_unknown_label_ignored(client_and_app):
    fake, app_client = client_and_app

    assert _post(app_client, _labeled_payload("wontfix")).status_code == 200
    assert fake.started == []
