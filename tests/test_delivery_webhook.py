"""Маршрутизация релиза: `/release` и `run:release` доезжают до Delivery-Agent.

Релиз — команда РЕПОЗИТОРИЯ, и на транспортном слое у неё два отличия от
остальных команд: своя очередь Temporal (воркер Delivery-Agent) и id по
репозиторию, а не по Issue. Разъехалось любое из двух — команда молча уходит в
никуда с ответом 200.
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


def _post(app_client, payload: dict, event: str):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig,
                 "Content-Type": "application/json"},
    )


def _comment(body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 42, "title": "Релиз", "body": "",
                  "user": {"login": "alice", "type": "User"}},
        "comment": {"id": 555, "body": body, "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def _labeled(label: str) -> dict:
    return {
        "action": "labeled",
        "label": {"name": label},
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 42, "title": "Релиз", "body": "",
                  "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def _release_run(fake) -> dict | None:
    for call in fake.started:
        if call.get("workflow") == "DeliveryRelease":
            return call
    return None


def test_command_starts_release_on_delivery_queue(client_and_app):
    fake, app_client = client_and_app
    assert _post(app_client, _comment("/release"), "issue_comment").status_code == 200

    call = _release_run(fake)
    assert call is not None
    assert call["task_queue"] == "delivery"
    assert call["arg"]["repo"] == "acme/widgets"
    assert call["arg"]["requested_by"] == "alice"
    assert call["arg"]["issue_number"] == 42
    assert call["arg"]["comment_id"] == 555


def test_label_starts_the_same_release(client_and_app):
    fake, app_client = client_and_app
    assert _post(app_client, _labeled("run:release"), "issues").status_code == 200

    call = _release_run(fake)
    assert call is not None
    assert call["task_queue"] == "delivery"
    # Метка триггером комментария не притворяется: отвечать в неё некому.
    assert call["arg"]["comment_id"] == 0


def test_release_id_is_per_repo_not_per_issue(client_and_app):
    """Два релиза в одном репозитории одновременно недопустимы.

    id по Issue дал бы по релизу на каждую команду: два плана мержили бы в одну
    ветку, и ни один не смог бы честно сказать, что он выкатил.
    """
    fake, app_client = client_and_app
    _post(app_client, _comment("/release"), "issue_comment")
    call = _release_run(fake)
    assert call["id"] == "delivery-acme/widgets"


def test_release_is_gated_like_other_expensive_commands(client_and_app, monkeypatch):
    """Метка `agents:off` — рубильник человека, и релиз обязан его слушать."""
    fake, app_client = client_and_app
    import main

    monkeypatch.setattr(main, "_may_start_expensive", lambda *args, **kwargs: False)
    _post(app_client, _comment("/release"), "issue_comment")
    assert _release_run(fake) is None


def test_quoted_command_does_not_start_release(client_and_app):
    fake, app_client = client_and_app
    _post(app_client, _comment("> /release\n\nэто цитата"), "issue_comment")
    assert _release_run(fake) is None
