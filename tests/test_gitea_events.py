"""Нормализация вебхуков Gitea.

Формы payload — живые доставки Gitea 28.1 стенда харнесса (tests/fixtures/gitea),
а не документация: событие задачи приезжает с `X-Gitea-Event-Type`, а смена меток —
действием `label_updated` без поля «какая метка».
"""
import json
from pathlib import Path

import pytest

from shared.gitea_events import UnsupportedEvent, normalize

FIX = Path(__file__).resolve().parent / "fixtures" / "gitea"


def delivery(name):
    d = json.loads((FIX / f"{name}.json").read_text())
    return d["headers"]["X-Gitea-Event-Type"], d["body"]


def test_новая_задача_в_форме_github():
    event, payload = delivery("issues_opened")
    out = normalize(event, payload, bot_login="bft-bot")
    assert out["action"] == "opened"
    assert out["repository"]["full_name"] == "bft/requests"
    assert out["issue"]["number"] == 2
    assert out["issue"]["title"] == "Экспорт заказов в CSV"
    assert out["issue"]["body"] == "Вводная: бухгалтер вручную копирует заказы."
    assert out["issue"]["labels"] == []


def test_комментарий_с_текстом_и_автором():
    event, payload = delivery("issue_comment_created")
    out = normalize(event, payload, bot_login=None)
    assert out["action"] == "created"
    assert out["issue"]["number"] == 2
    assert out["comment"]["id"] == 3
    assert out["comment"]["body"] == "Уточнение: нужен период."
    assert out["comment"]["user"] == {"login": "bft-bot", "type": "User", "id": 1}


def test_свой_сервисный_аккаунт_опознаётся_ботом():
    """У Gitea поле user.type всегда «User»: ботом считаем логин сервисного аккаунта, как у GitLab."""
    event, payload = delivery("issue_comment_created")
    out = normalize(event, payload, bot_login="bft-bot")
    assert out["sender"]["type"] == "Bot"
    assert out["comment"]["user"]["type"] == "Bot"


def test_метки_задачи_именами():
    event, payload = delivery("issues_edited")
    out = normalize(event, payload)
    assert out["action"] == "edited"
    assert out["issue"]["labels"] == [{"name": "phase:inbox"}]


def test_смена_меток_пока_не_поддерживается():
    """Без поля «какая метка» `labeled` не собрать; сигнал card_updated — задача T2 (#330)."""
    event, payload = delivery("issue_label_updated")
    with pytest.raises(UnsupportedEvent):
        normalize(event, payload)


def test_чужое_событие_не_молчит():
    with pytest.raises(UnsupportedEvent):
        normalize("push", {})


def test_карточку_от_учётки_приёма_контур_берёт_в_работу():
    """Карточки заводят сервисы (бот @bft, синхронизация с Jira, перенос) через свою учётку `bft-intake`.

    Ботом считается только аккаунт агента. Если бы карточки заводил он сам, prefilter
    отбросил бы их как «bot» и поставил phase:skipped — так и было на первом smoke T1 (bft/requests#3).
    """
    event, payload = delivery("issues_opened")
    payload["sender"] = {"id": 2, "login": "bft-intake"}
    payload["issue"]["user"] = {"id": 2, "login": "bft-intake"}
    out = normalize(event, payload, bot_login="bft-bot")
    assert out["sender"]["type"] == "User"
    assert out["issue"]["user"]["type"] == "User"
