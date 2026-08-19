"""Маршрутизация БФТ: команда в комментарии и метка ведут в один воркфлоу.

Транспортный слой — не бизнес-логика, но именно здесь команда либо доезжает до
Temporal, либо умирает молча с ответом 200.
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
        self.signalled: list[tuple[str, str]] = []

    async def start_workflow(self, workflow, arg=None, **kwargs):
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle(self)

    def get_workflow_handle(self, wf_id):
        return FakeHandle(self, wf_id)


class FakeHandle:
    def __init__(self, client, wf_id: str = "") -> None:
        self._client = client
        self._id = wf_id

    async def query(self, name):
        return True  # цикл ведёт агентов дочерними прогонами

    async def signal(self, name, arg=None):
        self._client.signalled.append((self._id, name))


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


def _issue() -> dict:
    return {"number": 42, "title": "Валюты", "body": "тело",
            "user": {"login": "alice", "type": "User"}}


def _comment_payload(body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": _issue(),
        "comment": {"id": 555, "body": body, "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def _labeled_payload(label: str) -> dict:
    return {
        "action": "labeled",
        "label": {"name": label},
        "repository": {"full_name": "acme/widgets"},
        "issue": _issue(),
        "sender": {"login": "alice"},
    }


def _bft_run(fake) -> dict | None:
    """Старт прогона БФТ среди всех поднятых воркфлоу.

    Ищем по сигналу, а не по индексу: комментарий поднимает ещё и `CommentAck`
    (реакция 👀 на любую реплику), и он идёт первым. Проверка «БФТ — нулевой
    старт» ломалась бы от каждого следующего воркфлоу, добавленного в обработку
    комментария, хотя к самому БФТ это отношения не имеет.
    """
    for call in fake.started:
        if call.get("start_signal") == "bft_requested":
            return call
    return None


def test_bft_command_carries_its_corrections_into_the_run(client_and_app):
    """Хвост команды — замечания человека. Потеряв их, прогон пересобрал бы то
    же самое и человек получил бы тот же текст в ответ на правку."""
    fake, app_client = client_and_app

    assert _post(app_client, _comment_payload("/bft поправь цель"),
                 "issue_comment").status_code == 200

    call = _bft_run(fake)
    assert call is not None, "прогон БФТ не запущен"
    assert call["workflow"] == "IssueLifecycle"
    req = call["start_signal_args"][0]
    assert req.mode == "fast"
    assert req.instructions == "поправь цель"
    assert req.comment_id == 555


def test_bft_deep_command_routes_to_the_deep_mode(client_and_app):
    fake, app_client = client_and_app

    assert _post(app_client, _comment_payload("/bft-deep 1. курс ЦБ\n2. да"),
                 "issue_comment").status_code == 200

    req = _bft_run(fake)["start_signal_args"][0]
    assert req.mode == "deep"
    assert req.instructions == "1. курс ЦБ\n2. да"


def test_bft_command_is_not_delivered_as_a_plain_comment(client_and_app):
    """Уйдя в `user_comment`, команда была бы съедена циклом уточнений intake
    gate как ответ на его вопрос."""
    fake, app_client = client_and_app

    _post(app_client, _comment_payload("/bft-deep уточнение"), "issue_comment")

    assert fake.signalled == [], "команда ушла в цикл уточнений вместо прогона"


def test_bft_labels_start_the_same_run(client_and_app):
    fake, app_client = client_and_app

    assert _post(app_client, _labeled_payload("run:bft-deep"), "issues").status_code == 200

    call = _bft_run(fake)
    assert call is not None, "прогон БФТ не запущен"
    req = call["start_signal_args"][0]
    assert req.mode == "deep"
    # Триггер — метка: реагировать не на что, аргументов нет.
    assert req.comment_id is None
    assert req.instructions == ""
    # Отвечать на уточняющий вопрос тоже некому.
    assert call["arg"].interactive is False


def test_outcome_labels_do_not_start_anything(client_and_app):
    """Метки исхода агент ставит себе сам, и они прилетают обратно событием
    `issues.labeled`. Совпади они с триггером — контур кормил бы сам себя."""
    fake, app_client = client_and_app

    _post(app_client, _labeled_payload("done:bft"), "issues")
    _post(app_client, _labeled_payload("failed:bft-deep"), "issues")

    assert fake.started == []


def test_an_unauthorized_login_cannot_spend_the_budget(client_and_app, monkeypatch):
    """Дорогую стадию запускает не всякий, у кого есть права на репозиторий.

    Гейт стоит на прогоне, а не на подтверждении приёма: реакция 👀 бесплатна и
    честна — комментарий действительно доехал. Молчание вместо неё означало бы,
    что человек не отличает «не хватило прав» от «вебхук не работает».
    """
    monkeypatch.setenv("AGENT_TRIGGER_ALLOWLIST", "bob")
    fake, app_client = client_and_app

    assert _post(app_client, _comment_payload("/bft-deep"),
                 "issue_comment").status_code == 200
    assert _bft_run(fake) is None, "прогон БФТ запущен без прав"
