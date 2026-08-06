"""
Сквозная проверка HTTP-слоя: то, что пришлёт Telegram на вебхук, доезжает до
Bot API. Вместо настоящего Bot API подставляется рекордер — сеть не нужна.
"""

import pytest
from fastapi.testclient import TestClient

from tgbot.config import Config
from tgbot.server import create_app

TOKEN = "123456:TEST-TOKEN"

UPDATE = {
    "update_id": 10,
    "message": {
        "message_id": 1,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 7, "first_name": "Ада"},
        "text": "/ping",
    },
}


class RecordingAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, **payload):
        self.calls.append((method, payload))
        return {"message_id": 1}

    async def close(self) -> None:
        pass


@pytest.fixture
def client_and_api():
    config = Config(
        token=TOKEN,
        webhook_base_url="https://example.com",
        webhook_path="/telegram/webhook",
        webhook_secret="s3cret",
        miniapp_url=None,
        host="127.0.0.1",
        port=8081,
    )
    app = create_app(config)
    with TestClient(app) as client:
        recorder = RecordingAPI()
        app.state.api = recorder  # startup успел положить настоящий клиент — меняем
        yield client, recorder


def test_healthz(client_and_api):
    client, _ = client_and_api
    assert client.get("/healthz").json()["status"] == "ok"


def test_update_with_valid_secret_is_processed(client_and_api):
    client, api = client_and_api

    response = client.post(
        "/telegram/webhook", json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )

    assert response.status_code == 200
    assert api.calls == [("sendMessage", {"chat_id": 42, "text": "pong"})]


def test_update_without_secret_is_rejected(client_and_api):
    client, api = client_and_api

    response = client.post("/telegram/webhook", json=UPDATE)

    assert response.status_code == 401
    assert api.calls == []


def test_update_with_wrong_secret_is_rejected(client_and_api):
    client, api = client_and_api

    response = client.post(
        "/telegram/webhook", json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "guess"},
    )

    assert response.status_code == 401
    assert api.calls == []


def test_miniapp_verify_rejects_unsigned_init_data(client_and_api):
    client, _ = client_and_api

    response = client.post("/api/miniapp/verify", json={"init_data": "user=%7B%7D"})

    assert response.status_code == 401
    assert response.json()["ok"] is False


def test_miniapp_verify_accepts_signed_init_data(client_and_api):
    from tgbot.security import build_init_data

    client, _ = client_and_api
    init_data = build_init_data({"auth_date": str(2 ** 31), "user": '{"id": 7}'}, TOKEN)

    response = client.post("/api/miniapp/verify", json={"init_data": init_data})

    assert response.status_code == 200
    assert response.json()["fields"]["user"] == '{"id": 7}'


def test_miniapp_static_is_served(client_and_api):
    client, _ = client_and_api

    response = client.get("/miniapp/")

    assert response.status_code == 200
    assert "telegram-web-app.js" in response.text
