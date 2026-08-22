"""Обработчик принимает доставку даже когда разобрать её не может.

У GitLab ретраев нет, а четыре подряд провала отключают вебхук на срок до
суток. 500 из обработчика — это потерянное событие плюс шаг к отключению.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "s3cret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "o/r")
    import importlib

    import main
    importlib.reload(main)

    async def no_temporal():
        raise AssertionError("до Temporal дойти не должно")

    monkeypatch.setattr(main, "get_temporal_client", no_temporal)
    return TestClient(main.app)


def _post(client, event, payload):
    body = json.dumps(payload).encode()
    return client.post("/webhook", content=body, headers={
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": _sign(body),
        "X-GitHub-Delivery": "d-1",
        "Content-Type": "application/json",
    })


def test_comment_without_user_type_is_accepted(client):
    """Поля user.type у второго провайдера нет вовсе."""
    payload = {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 1},
        "comment": {"id": 5, "body": "текст", "user": {"login": "human"}},
    }
    assert _post(client, "issue_comment", payload).status_code == 200


def test_issue_without_user_type_is_accepted(client):
    payload = {
        "action": "opened",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 1, "title": "t", "body": "b", "user": {"login": "human"}},
    }
    assert _post(client, "issues", payload).status_code < 500


def test_malformed_payload_is_accepted_not_500(client):
    """Мусор в теле — не повод терять доставку."""
    payload = {"action": "created", "repository": {"full_name": "o/r"}}
    assert _post(client, "issue_comment", payload).status_code == 200


def test_bad_signature_still_401(client):
    """Отказ авторизации остаётся отказом: 401 не считается сбоем доставки."""
    body = json.dumps({"repository": {"full_name": "o/r"}}).encode()
    resp = client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": "sha256=deadbeef",
        "Content-Type": "application/json",
    })
    assert resp.status_code == 401
