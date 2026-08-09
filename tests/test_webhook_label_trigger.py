"""Метка как триггер команды: `run:<команда>` ведёт в тот же воркфлоу, что и
команда в комментарии, а метки исхода не запускают ничего."""

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


class FakeClient:
    def __init__(self, already_started: set[str] | None = None) -> None:
        self.started: list[dict] = []
        self._already = already_started or set()

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})

    def get_workflow_handle(self, wf_id):
        raise AssertionError("метка не должна слать голый signal")


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main

    from fastapi.testclient import TestClient

    def _build(already_started: set[str] | None = None):
        fake = FakeClient(already_started)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig,
                 "Content-Type": "application/json"},
    )


def _labeled(label: str) -> dict:
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
        "sender": {"login": "alice"},
    }


def test_run_analyze_starts_the_same_workflow_as_the_command(make_client):
    fake, app_client = make_client()

    assert _post(app_client, _labeled("run:analyze")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "IssueAnalysis"
    assert call["id"] == "analysis-acme/widgets-7"
    assert call["arg"].issue_number == 7
    assert call["arg"].title == "Тестовая задача"
    # Комментария-триггера нет: реагировать не на что, ack назовёт метку.
    assert call["arg"].comment_id is None


def test_run_estimate_starts_estimation_without_a_comment(make_client):
    fake, app_client = make_client()

    assert _post(app_client, _labeled("run:estimate")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "IssueEstimation"
    assert call["id"] == "estimate-acme/widgets-7-label"
    assert call["arg"].comment_id is None


def test_outcome_labels_start_nothing(make_client):
    """Защита от петли: done:/failed: агент ставит себе сам, и они возвращаются
    событием issues.labeled. Запусти они прогон — он запускал бы сам себя."""
    fake, app_client = make_client()

    for label in ("done:analyze", "failed:analyze", "done:estimate", "failed:estimate",
                  "analyzing", "estimated", "priority:P1"):
        assert _post(app_client, _labeled(label)).status_code == 200

    assert fake.started == []


def test_repeated_delivery_does_not_start_a_second_run(make_client):
    """Повторная доставка того же вебхука (или метка, снятая и поставленная
    заново на идущем прогоне) не должна ни падать в 500, ни жечь второй прогон."""
    fake, app_client = make_client(already_started={"IssueAnalysis"})

    assert _post(app_client, _labeled("run:analyze")).status_code == 200
    assert fake.started == []


def test_human_decision_labels_still_signal_with_start(make_client):
    """Обратная совместимость: research-me / bug-me / build-me работают как были."""
    fake, app_client = make_client()

    assert _post(app_client, _labeled("research-me")).status_code == 200

    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["start_signal"] == "human_decision"
    assert call["start_signal_args"] == ["research-me"]
