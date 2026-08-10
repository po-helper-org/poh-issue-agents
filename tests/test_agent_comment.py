"""#58: сервис не должен принимать собственные комментарии за ответ человека.

На живом прогоне оба сигнала `user_comment` оказались нашими же комментариями —
advisor-ответом и разбором приоритета. Гейт `comment.user.type == "Bot"` их не
поймал: под PAT сервис пишет от имени человека.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

import activities as activities_module  # noqa: E402
import github_client  # noqa: E402
from shared.agent_comment import MARKER, is_agent_comment, sign  # noqa: E402

SECRET = "test-secret"


# --- сама подпись ---

def test_signed_body_is_recognised():
    assert is_agent_comment(sign("Приоритет: P1"))


def test_human_text_is_not_mistaken_for_ours():
    assert not is_agent_comment("да, речь про мобильный клиент")


def test_missing_body_is_not_ours():
    assert not is_agent_comment(None)


def test_signing_is_idempotent():
    """Один и тот же текст может пройти через несколько слоёв — вторая подпись
    выглядела бы в GitHub как мусор в конце комментария."""
    once = sign("текст")
    assert sign(once) == once
    assert once.count(MARKER) == 1


def test_marker_is_invisible_in_rendered_markdown():
    """GitHub не показывает HTML-комментарии — подпись не должна попадаться на
    глаза человеку, который читает тред."""
    assert MARKER.startswith("<!--") and MARKER.endswith("-->")


# --- отправка ---

def test_every_posted_comment_is_signed(monkeypatch):
    """Подпись ставится в единственной точке отправки: пропущенная в каком-то
    одном месте означала бы, что именно этот комментарий вернётся сигналом."""
    sent = {}
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    class _Resp:
        def raise_for_status(self): ...

    monkeypatch.setattr(github_client.requests, "post",
                        lambda url, headers, json, timeout: sent.update(body=json["body"]) or _Resp())

    github_client.post_comment("o/r", 7, "## Приоритет: P3")

    assert is_agent_comment(sent["body"])
    assert "## Приоритет: P3" in sent["body"]


def test_advisor_answer_goes_out_signed(monkeypatch):
    """Проверка через настоящую активность, а не только через клиент: именно
    advisor-ответ и приезжал обратно сигналом на живом прогоне."""
    sent = {}
    monkeypatch.setattr(activities_module.github_client, "post_comment",
                        lambda repo, n, body: sent.update(body=sign(body)))
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: None)

    activities_module.escalate_to_human(
        activities_module.IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                                     author_login="u", author_type="User"),
        "срок вышел",
    )

    assert is_agent_comment(sent["body"])


# --- гейт в вебхуке ---

class FakeClient:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.signals: list = []

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append({"workflow": workflow, **kwargs})
        return _Handle(self.signals)

    def get_workflow_handle(self, wf_id):
        return _Handle(self.signals)


class _Handle:
    def __init__(self, sink) -> None:
        self._sink = sink

    async def signal(self, name, *args):
        self._sink.append((name, args))

    async def query(self, name, *args):
        return True


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)

    import main
    from fastapi.testclient import TestClient

    fake = FakeClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    return fake, TestClient(main.app)


def _post(app_client, body_text: str):
    payload = {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "т", "body": "б",
                  "user": {"login": "kibarik", "type": "User"}},
        "comment": {"id": 555, "body": body_text,
                    "user": {"login": "kibarik", "type": "User"}},
        "sender": {"login": "kibarik"},
    }
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return app_client.post("/webhook", content=raw, headers={
        "X-GitHub-Event": "issue_comment", "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": "dlv-1", "Content-Type": "application/json"})


def test_our_own_comment_does_not_feed_the_clarification_loop(webhook):
    """Тот самый случай с живого прогона: разбор приоритета приезжает обратно
    вебхуком с `type == "User"` и не должен становиться сигналом."""
    fake, app_client = webhook

    assert _post(app_client, sign("## Приоритет: P3\n\nEffort: 6/10")).status_code == 200

    assert fake.signals == [], "сервис накормил цикл уточнений своим же комментарием"
    assert fake.started == []


def test_a_human_answer_still_gets_through(webhook):
    """Гейт различает происхождение, а не автора: у владельца токена и сервиса
    логин один и тот же, и настоящий ответ обязан доехать."""
    fake, app_client = webhook

    assert _post(app_client, "да, речь про мобильный клиент").status_code == 200

    assert ("user_comment", ("да, речь про мобильный клиент",)) in fake.signals


def test_command_quoted_by_our_own_comment_does_not_run(webhook):
    """Наш комментарий может содержать `/analyze` в тексте подсказки — команду
    из него запускать нельзя, иначе контур кормит сам себя."""
    fake, app_client = webhook

    assert _post(app_client, sign("Готово. Дальше можно запустить /analyze")).status_code == 200

    assert fake.started == []
    assert fake.signals == []
