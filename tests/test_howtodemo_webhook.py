"""Маршрутизация приёмки: `/howtodemo` и `run:howtodemo` доезжают до агента.

Приёмка — команда ISSUE, и на транспортном слое у неё два отличия от релиза:
своя очередь Temporal (воркер HowToDemo-Agent) и id по Issue, а не по
репозиторию. Разъехалось любое из двух — команда молча уходит в никуда с
ответом 200.
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

    async def start_workflow(self, workflow, arg=None, **kwargs):
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle()

    def get_workflow_handle(self, wf_id):
        return FakeHandle()


class FakeHandle:
    async def query(self, name):
        return True

    async def signal(self, name, arg=None, args=None):
        return None


@pytest.fixture
def client_and_app(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)

    import main

    fake = FakeClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(main, "get_temporal_client", _get_client)

    from fastapi.testclient import TestClient

    return fake, TestClient(main.app)


def _post(app, event: str, payload: dict):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app.post("/webhook", content=body, headers={
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": "d1",
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    })


def _comment_payload(body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 12, "title": "t", "body": "b", "labels": [],
                  "user": {"login": "human"}, "state": "open"},
        "comment": {"id": 777, "body": body, "user": {"login": "human"}},
        "sender": {"login": "human"},
    }


def _label_payload(label: str) -> dict:
    return {
        "action": "labeled",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 12, "title": "t", "body": "b",
                  "labels": [{"name": label}], "user": {"login": "human"},
                  "state": "open"},
        "label": {"name": label},
        "sender": {"login": "human"},
    }


def _howtodemo_starts(fake) -> list[dict]:
    return [s for s in fake.started if s["workflow"] == "HowToDemoVerify"]


def test_comment_command_starts_verification(client_and_app):
    fake, app = client_and_app
    assert _post(app, "issue_comment", _comment_payload("/howtodemo")).status_code == 200
    started = _howtodemo_starts(fake)
    assert len(started) == 1
    assert started[0]["arg"] == {"repo": "o/r", "issue": 12, "pr_number": 0}


def test_label_starts_verification(client_and_app):
    fake, app = client_and_app
    assert _post(app, "issues", _label_payload("run:howtodemo")).status_code == 200
    assert len(_howtodemo_starts(fake)) == 1


def test_id_is_per_issue_not_per_repository(client_and_app):
    """Два Issue одного репозитория принимаются независимо."""
    fake, app = client_and_app
    _post(app, "issue_comment", _comment_payload("/howtodemo"))
    from shared.workflow_ids import howtodemo_workflow_id

    assert _howtodemo_starts(fake)[0]["id"] == howtodemo_workflow_id("o/r", 12)
    assert howtodemo_workflow_id("o/r", 12) != howtodemo_workflow_id("o/r", 13)


def test_runs_on_its_own_task_queue(client_and_app):
    """Очередь своя: приёмка держит активность десятками минут."""
    fake, app = client_and_app
    _post(app, "issue_comment", _comment_payload("/howtodemo"))
    queue = _howtodemo_starts(fake)[0]["task_queue"]
    assert queue == "howtodemo"
    assert queue not in ("issue-lifecycle", "delivery")


def test_command_does_not_leak_into_the_lifecycle_as_a_comment(client_and_app):
    """Команда не должна уехать в user_comment — её съел бы цикл уточнений."""
    fake, app = client_and_app
    _post(app, "issue_comment", _comment_payload("/howtodemo"))
    assert not [s for s in fake.started if s["workflow"] == "IssueLifecycle"]


def test_second_run_of_the_same_issue_is_answered_200(client_and_app):
    """Повторная команда при идущей приёмке — не сбой доставки."""
    from temporalio.exceptions import WorkflowAlreadyStartedError

    fake, app = client_and_app

    async def already(workflow, arg=None, **kwargs):
        raise WorkflowAlreadyStartedError("howtodemo-o/r-12", "HowToDemoVerify")

    fake.start_workflow = already
    assert _post(app, "issue_comment", _comment_payload("/howtodemo")).status_code == 200


def test_quoted_command_is_not_a_command(client_and_app):
    fake, app = client_and_app
    _post(app, "issue_comment", _comment_payload("> /howtodemo — вот так зовут приёмку"))
    assert _howtodemo_starts(fake) == []
