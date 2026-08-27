"""Под-задача шага не поднимает свой жизненный цикл.

Она живёт часы, закрывается вместе со своим шагом, и триаж ей не нужен: задачу
уже разобрал план родителя. Каждый лишний цикл — вечный воркфлоу и вызов модели
на приоритет.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "s3cret"


def _payload(label_names):
    return {
        "action": "opened",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 152, "title": "Шаг 2", "body": "тело",
                  "user": {"login": "bot", "type": "Bot"},
                  "labels": [{"name": name} for name in label_names]},
    }


def _post(client, payload):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body,
                       headers={"X-GitHub-Event": "issues",
                                "X-Hub-Signature-256": sig,
                                "Content-Type": "application/json"})


def test_step_subissue_starts_nothing(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main
    from fastapi.testclient import TestClient

    started = []

    class FakeClient:
        async def start_workflow(self, workflow, arg, **kwargs):
            started.append(workflow)

        def get_workflow_handle(self, wf_id):
            raise AssertionError("под-задача не должна ничего сигналить")

    async def _get_client():
        return FakeClient()

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    client = TestClient(main.app)

    assert _post(client, _payload(["harness:step"])).status_code == 200
    assert started == [], "под-задача подняла цикл"

    assert _post(client, _payload([])).status_code == 200
    assert started, "обычный Issue перестал подниматься"
