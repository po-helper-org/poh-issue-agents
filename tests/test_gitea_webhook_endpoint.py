"""Эндпоинт /gitea/webhook харнесса БФТ.

Как и у GitLab, отказать может только подпись: необработанное событие уходит в
аудит и подтверждается 200, иначе Gitea копит неудачные доставки.
Тела доставок — живые, с подписью, посчитанной как у Gitea: hex HMAC-SHA256 тела
в `X-Gitea-Signature`.
"""
import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))
FIX = ROOT / "tests" / "fixtures" / "gitea"

SECRET = "gitea-s3cret"


@pytest.fixture
def webhook_app(monkeypatch):
    monkeypatch.setenv("GITEA_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GITEA_BOT_LOGIN", "bft-bot")
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "bft/requests")
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

        async def signal_with_start_workflow(self, *a, **k):
            started.append((a, k))

        def get_workflow_handle(self, *a, **k):
            class H:
                async def signal(self, *a, **k):
                    started.append(("signal", a))
            return H()

    async def fake_temporal():
        return FakeClient()

    monkeypatch.setattr(main, "get_temporal_client", fake_temporal)
    c = TestClient(main.app)
    c.started = started
    return c


def post(client, name, secret=SECRET, body=None):
    d = json.loads((FIX / f"{name}.json").read_text())
    raw = body if body is not None else json.dumps(d["body"]).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"X-Gitea-Event": d["headers"]["X-Gitea-Event"],
               "X-Gitea-Event-Type": d["headers"]["X-Gitea-Event-Type"],
               "X-Gitea-Delivery": "delivery-1", "X-Gitea-Signature": sig,
               "Content-Type": "application/json"}
    return client.post("/gitea/webhook", content=raw, headers=headers)


def test_чужая_подпись_отвергается_401(webhook_app):
    assert post(webhook_app, "issues_opened", secret="wrong").status_code == 401
    assert not webhook_app.started


def test_без_секрета_503_а_не_200(webhook_app, monkeypatch):
    """Не настроены — не принимаем: молчаливые 200 пропускали бы неподписанные доставки."""
    import main
    monkeypatch.setattr(main, "GITEA_WEBHOOK_SECRET", "")
    assert post(webhook_app, "issues_opened").status_code == 503


def test_новая_задача_стартует_воркфлоу(webhook_app):
    r = post(webhook_app, "issues_opened")
    assert r.status_code == 200
    names = [a[0] for a, _ in webhook_app.started if a and isinstance(a[0], str)]
    assert "IssueLifecycle" in names, webhook_app.started


def test_смена_меток_подтверждается_без_запуска(webhook_app):
    r = post(webhook_app, "issue_label_updated")
    assert r.status_code == 200
    assert not webhook_app.started


def test_мусор_вместо_payload_не_роняет(webhook_app):
    assert post(webhook_app, "issues_opened", body=b"{not json").status_code == 200


def test_нераспознанная_доставка_оставляет_след_аудита(webhook_app):
    """Разобранный JSON, который нормализатор не понял, — не тишина: след в Temporal, как у GitLab."""
    d = json.loads((FIX / "issues_opened.json").read_text())
    d["body"]["issue"] = "не объект"
    raw = json.dumps(d["body"]).encode()
    r = post(webhook_app, "issues_opened", body=raw)
    assert r.status_code == 200
    assert webhook_app.started, "отказ разбора должен оставлять след аудита"
