"""Отброшенная по allowlist доставка обязана оставлять след в Temporal UI:
логи контейнера читают только те, кто уже заподозрил проблему."""

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
    def __init__(self, already: set[str] | None = None) -> None:
        self.started: list[dict] = []
        self._already = already or set()

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})

    def get_workflow_handle(self, wf_id):
        raise AssertionError("отброшенная доставка не должна никуда сигналить")


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    import main

    from fastapi.testclient import TestClient

    def _build(allowlist: str, already: set[str] | None = None):
        monkeypatch.setenv("ISSUE_AGENT_REPOS", allowlist)
        fake = FakeClient(already)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict, delivery: str | None = "dlv-1"):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig,
               "Content-Type": "application/json"}
    if delivery is not None:
        headers["X-GitHub-Delivery"] = delivery
    return app_client.post("/webhook", content=body, headers=headers)


def _opened(repo: str) -> dict:
    return {
        "action": "opened",
        "repository": {"full_name": repo},
        "issue": {"number": 7, "title": "т", "body": "б",
                  "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def test_dropped_repo_leaves_an_audit_trail(make_client):
    fake, app_client = make_client("acme/widgets")

    assert _post(app_client, _opened("other/thing")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "WebhookAudit"
    assert call["id"] == "webhook-drop-dlv-1"
    assert call["arg"].repo == "other/thing"
    assert call["arg"].reason == "repo_not_allowed"
    assert call["arg"].allowlist == ["acme/widgets"]  # действовавший на момент отказа
    assert call["arg"].event == "issues"
    assert call["arg"].action == "opened"


def test_dropped_repo_starts_no_lifecycle(make_client):
    fake, app_client = make_client("acme/widgets")

    _post(app_client, _opened("other/thing"))

    assert [c["workflow"] for c in fake.started] == ["WebhookAudit"]


def test_allowed_repo_is_not_audited(make_client):
    """Аудит покрывает ровно один молчаливый отказ; штатный трафик в него не идёт."""
    fake, app_client = make_client("acme/widgets")

    assert _post(app_client, _opened("acme/widgets")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["IssueLifecycle"]


def test_missing_delivery_header_does_not_break_processing(make_client):
    """Ручной curl без X-GitHub-Delivery: без уникального id аудит пропускаем,
    но обработка не падает."""
    fake, app_client = make_client("acme/widgets")

    assert _post(app_client, _opened("other/thing"), delivery=None).status_code == 200
    assert fake.started == []


def test_retried_delivery_does_not_duplicate_the_record(make_client):
    """GitHub ретраит доставку — id тот же, второй записи быть не должно."""
    fake, app_client = make_client("acme/widgets", already={"WebhookAudit"})

    assert _post(app_client, _opened("other/thing")).status_code == 200
    assert fake.started == []


def test_audit_failure_does_not_break_the_response(make_client, monkeypatch):
    """Аудит — диагностика, а не путь события: его сбой не должен ронять вебхук."""
    fake, app_client = make_client("acme/widgets")

    async def boom(*a, **k):
        raise RuntimeError("temporal недоступен")

    monkeypatch.setattr(fake, "start_workflow", boom)

    assert _post(app_client, _opened("other/thing")).status_code == 200
