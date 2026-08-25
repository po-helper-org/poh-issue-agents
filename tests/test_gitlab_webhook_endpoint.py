"""Эндпоинт /gitlab/webhook.

Главное свойство — не отдавать 5xx. У GitLab нет автоматических ретраев, а
четыре подряд провала отключают вебхук на срок до суток: 500 здесь стоит не
одного события, а всех последующих.
"""
import base64
import hashlib
import hmac
import importlib
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "s3cret-key"
PROJECT = {"id": 85686131, "path_with_namespace": "poh-harness/threads-harness"}
USER = {"id": 1, "username": "human"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GITLAB_SIGNATURE_MODE", "hmac")
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "poh-harness/threads-harness")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "unused")
    import main
    importlib.reload(main)

    started = []

    class FakeClient:
        async def start_workflow(self, *a, **k):
            started.append((a, k))
            class H:
                id = "wf"
                result_run_id = "run"
            return H()

        def get_workflow_handle(self, *a, **k):
            class H:
                async def signal(self, *a, **k): started.append(("signal", a))
            return H()

    async def fake_temporal():
        return FakeClient()

    monkeypatch.setattr(main, "get_temporal_client", fake_temporal)
    c = TestClient(main.app)
    c.started = started
    return c


def signed(body: bytes, wid="msg-1", ts=None, secret=SECRET):
    ts = str(int(time.time())) if ts is None else str(ts)
    msg = f"{wid}.{ts}.".encode() + body
    sig = base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{sig}"}


def post(client, event, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    h = signed(body, secret=secret)
    h["X-Gitlab-Event"] = event
    h["Idempotency-Key"] = "delivery-1"
    h["Content-Type"] = "application/json"
    return client.post("/gitlab/webhook", content=body, headers=h)


def issue_hook(action="open", changes=None):
    return {
        "object_kind": "issue", "user": USER, "project": PROJECT,
        "object_attributes": {"id": 999, "iid": 7, "title": "Заголовок",
                              "description": "Тело", "state": "opened",
                              "action": action, "labels": []},
        **({"changes": changes} if changes else {}),
    }


# --- подлинность ---

def test_чужая_подпись_отвергается_401(client):
    r = post(client, "Issue Hook", issue_hook(), secret="не тот")
    assert r.status_code == 401


def test_без_заголовков_подписи_401(client):
    body = json.dumps(issue_hook()).encode()
    r = client.post("/gitlab/webhook", content=body,
                    headers={"X-Gitlab-Event": "Issue Hook", "Content-Type": "application/json"})
    assert r.status_code == 401


def test_без_секрета_503_а_не_200(client, monkeypatch):
    """Не настроены — не принимаем. 200 означал бы приём неаутентифицированного."""
    import main
    monkeypatch.setattr(main, "GITLAB_WEBHOOK_SECRET", "")
    r = post(client, "Issue Hook", issue_hook())
    assert r.status_code == 503


# --- никаких 5xx ---

def test_мусор_вместо_payload_не_роняет(client):
    r = post(client, "Issue Hook", {"нет": "ничего"})
    assert r.status_code < 500


def test_неизвестное_событие_подтверждается(client):
    """Событие, на которое контур не подписан, вебхук выключать не должно."""
    r = post(client, "Pipeline Hook", {"object_kind": "pipeline", "project": PROJECT})
    assert r.status_code == 200


def test_заметка_к_merge_request_подтверждается(client):
    payload = {"object_kind": "note", "user": USER, "project": PROJECT,
               "object_attributes": {"id": 1, "note": "текст",
                                     "noteable_type": "MergeRequest", "action": "create"}}
    assert post(client, "Note Hook", payload).status_code == 200


def test_комментарий_без_поля_user_type_не_роняет(client):
    """Поля user.type у GitLab нет вовсе — на GitHub-пути это давало KeyError."""
    payload = {"object_kind": "note", "user": USER, "project": PROJECT,
               "object_attributes": {"id": 42, "note": "обычная реплика",
                                     "noteable_type": "Issue", "action": "create"},
               "issue": {"id": 9, "iid": 7, "title": "t", "description": "",
                         "state": "opened", "labels": []}}
    assert post(client, "Note Hook", payload).status_code < 500


# --- маршрутизация ---

def test_чужой_проект_не_попадает_в_жизненный_цикл(client):
    """Отказ по allowlist оставляет след аудита, но задачу в работу не берёт.

    Пустой список стартов был бы неверным ожиданием: отброшенная доставка
    обязана быть записана, иначе отказ неотличим от тишины.
    """
    payload = issue_hook()
    payload["project"] = {"id": 1, "path_with_namespace": "someone/else"}
    r = post(client, "Issue Hook", payload)
    assert r.status_code == 200
    names = [a[0][0] for a, _ in client.started if a]
    assert "IssueLifecycle" not in names, names
    assert names, "отказ должен оставлять след аудита"


def test_новая_задача_стартует_воркфлоу(client):
    r = post(client, "Issue Hook", issue_hook("open"))
    assert r.status_code == 200
    assert client.started, "воркфлоу не стартовал"


def test_постановка_метки_доезжает(client):
    changes = {"labels": {"previous": [], "current": [{"title": "research-me"}]}}
    r = post(client, "Issue Hook", issue_hook("update", changes=changes))
    assert r.status_code == 200
    assert client.started, "триггер по метке не сработал"
