"""Дорогая стадия запускается только теми, кому это разрешено.

Метка — самый дешёвый способ потратить самые дорогие токены, и поставить её
может любой с правами на репозиторий. Решает автор события, а не метка.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

from shared.authz import may_trigger  # noqa: E402

SECRET = "test-secret"


# --- чистая функция допуска ---

def test_empty_allowlist_allows_everyone():
    """Прежнее поведение по умолчанию: включение allowlist — осознанный шаг."""
    assert may_trigger("anyone", []) is True


def test_listed_login_is_allowed():
    assert may_trigger("kibarik", ["kibarik", "other"]) is True


def test_unlisted_login_is_rejected():
    assert may_trigger("stranger", ["kibarik"]) is False


def test_login_match_is_case_insensitive():
    assert may_trigger("KiBaRiK", ["kibarik"]) is True


def test_missing_login_is_rejected_when_allowlist_is_set():
    assert may_trigger(None, ["kibarik"]) is False


# --- гейт в вебхуке ---

class _Handle:
    async def signal(self, *a, **k):
        return None

    async def query(self, name, *a):
        """Живой цикл ведёт агентов сам (#37) — гейт стоит ДО этого вопроса."""
        return True


class FakeClient:
    def __init__(self) -> None:
        self.started: list[dict] = []

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append({"workflow": workflow, **kwargs})
        return _Handle()

    def get_workflow_handle(self, wf_id):
        return _Handle()


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main

    from fastapi.testclient import TestClient

    def _build(allowlist: str):
        monkeypatch.setenv("AGENT_TRIGGER_ALLOWLIST", allowlist)
        fake = FakeClient()

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict, event: str):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post("/webhook", content=body, headers={
        "X-GitHub-Event": event, "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": "dlv-1", "Content-Type": "application/json"})


def _labeled(label: str, sender: str) -> dict:
    return {
        "action": "labeled",
        "label": {"name": label},
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "т", "body": "б",
                  "user": {"login": "alice", "type": "User"}},
        "sender": {"login": sender},
    }


def _commented(body: str, sender: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "т", "body": "б",
                  "user": {"login": "alice", "type": "User"}},
        "comment": {"id": 99, "body": body, "user": {"login": sender, "type": "User"}},
        "sender": {"login": sender},
    }


def test_stranger_cannot_start_analysis_by_label(webhook):
    fake, app_client = webhook("kibarik")

    assert _post(app_client, _labeled("run:analyze", "stranger"), "issues").status_code == 200
    assert fake.started == []


def test_allowed_user_starts_analysis_by_label(webhook):
    fake, app_client = webhook("kibarik")

    assert _post(app_client, _labeled("run:analyze", "kibarik"), "issues").status_code == 200
    # Гейт пропустил — команда доехала до цикла, который и ведёт аналитику.
    assert [c["workflow"] for c in fake.started] == ["IssueLifecycle"]
    assert fake.started[0]["start_signal"] == "analyze_requested"


def test_stranger_cannot_start_estimate_by_command(webhook):
    fake, app_client = webhook("kibarik")

    assert _post(app_client, _commented("/estimate", "stranger"), "issue_comment").status_code == 200
    assert fake.started == []


def test_stranger_cannot_start_heavy_stage_by_research_me(webhook):
    """Старый лейбл-триггер закрыт тем же гейтом: он запускает ту же аналитику."""
    fake, app_client = webhook("kibarik")

    assert _post(app_client, _labeled("research-me", "stranger"), "issues").status_code == 200
    assert fake.started == []


def test_triage_of_new_issues_stays_open_to_everyone(webhook):
    """Гейт стоит на дорогих стадиях, а не на входе: Issue от постороннего
    обязан обрабатываться, иначе сервис перестаёт быть полезным."""
    fake, app_client = webhook("kibarik")

    opened = {
        "action": "opened",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 8, "title": "т", "body": "б",
                  "user": {"login": "stranger", "type": "User"}},
        "sender": {"login": "stranger"},
    }
    assert _post(app_client, opened, "issues").status_code == 200
    assert [c["workflow"] for c in fake.started] == ["IssueLifecycle"]


def test_without_allowlist_nothing_changes(webhook):
    """Пустая переменная — прежнее поведение, без сюрпризов после обновления."""
    fake, app_client = webhook("")

    assert _post(app_client, _labeled("run:analyze", "stranger"), "issues").status_code == 200
    assert [c["workflow"] for c in fake.started] == ["IssueLifecycle"]
    assert fake.started[0]["start_signal"] == "analyze_requested"
