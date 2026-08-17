"""Закрытый Issue обязан снимать цикл с ожидания.

Найдено на живом прогоне: 22 из 115 идущих IssueLifecycle относились к Issue,
уже закрытым на GitHub. Вебхук слушал только `opened` и `labeled`, поэтому
закрытие никуда не доезжало, и цикл продолжал стоять на парковке (до 168 ч),
занимая место в выборке Running и продолжая писать в закрытый Issue.
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


class FakeHandle:
    def __init__(self, sink: list, fail: bool = False) -> None:
        self._sink = sink
        self._fail = fail

    async def signal(self, name, *args):
        if self._fail:
            raise RuntimeError("workflow уже завершён")
        self._sink.append((name, args))


class FakeClient:
    def __init__(self, signal_fails: bool = False) -> None:
        self.started: list[dict] = []
        self.signals: list = []
        self.handles: list[str] = []
        self._signal_fails = signal_fails

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle(self.signals)

    def get_workflow_handle(self, wf_id):
        self.handles.append(wf_id)
        return FakeHandle(self.signals, fail=self._signal_fails)


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

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
        "X-GitHub-Event": "issues", "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": "dlv-1", "Content-Type": "application/json"})


def _closed(login: str = "alice") -> dict:
    return {
        "action": "closed",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "Тестовая задача", "body": "тело",
                  "state": "closed",
                  "user": {"login": "alice", "type": "User"}},
        "sender": {"login": login},
    }


def test_closed_issue_signals_the_cycle(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _closed()).status_code == 200

    assert fake.handles == ["issue-acme/widgets-7"]
    assert fake.signals == [("issue_closed", ("alice",))]
    # Закрытие — не повод поднимать цикл по Issue, которым никто не занимался.
    assert fake.started == []


def test_closed_issue_without_a_live_cycle_is_not_an_error(webhook):
    """Цикл уже завершён (или его не было) — сигналить некому. GitHub обязан
    получить 200: на 500 он ретраит доставку и в итоге бросает её насовсем."""
    fake, app_client = webhook(signal_fails=True)

    assert _post(app_client, _closed()).status_code == 200
