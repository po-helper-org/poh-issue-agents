"""dispatch() — чистая функция, поэтому проверяется без сети и моков."""

from tgbot.handlers import HELP_TEXT, dispatch

MINIAPP = "https://example.com/miniapp/"


def message(text: str, chat_id: int = 42, **extra) -> dict:
    msg = {
        "message_id": 1,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": 7, "first_name": "Ада", "username": "ada"},
        "text": text,
    }
    msg.update(extra)
    return {"update_id": 1, "message": msg}


def test_start_greets_and_offers_miniapp():
    actions = dispatch(message("/start"), MINIAPP)

    assert actions[0][0] == "sendMessage"
    assert "Ада" in actions[0][1]["text"]
    buttons = actions[0][1]["reply_markup"]["inline_keyboard"]
    assert any(b.get("web_app", {}).get("url") == MINIAPP for row in buttons for b in row)
    # Вторым сообщением — reply-клавиатура, только из неё работает sendData.
    assert actions[1][1]["reply_markup"]["keyboard"][0][0]["web_app"]["url"] == MINIAPP


def test_start_without_miniapp_has_no_webapp_buttons():
    actions = dispatch(message("/start"), None)

    assert len(actions) == 1
    buttons = actions[0][1]["reply_markup"]["inline_keyboard"]
    assert all("web_app" not in b for row in buttons for b in row)


def test_ping():
    assert dispatch(message("/ping")) == [("sendMessage", {"chat_id": 42, "text": "pong"})]


def test_command_with_bot_suffix_is_recognised():
    assert dispatch(message("/ping@test_bot"))[0][1]["text"] == "pong"


def test_echo_repeats_argument():
    assert dispatch(message("/echo привет мир"))[0][1]["text"] == "привет мир"


def test_echo_without_argument_explains_format():
    assert "Формат" in dispatch(message("/echo"))[0][1]["text"]


def test_whoami_reports_ids():
    text = dispatch(message("/whoami"))[0][1]["text"]
    assert "chat_id: 42" in text
    assert "user_id: 7" in text
    assert "@ada" in text


def test_help():
    assert dispatch(message("/help"))[0][1]["text"] == HELP_TEXT


def test_unknown_command():
    assert "Не знаю команду" in dispatch(message("/nope"))[0][1]["text"]


def test_plain_text_is_echoed_back():
    assert dispatch(message("просто текст"))[0][1]["text"] == "Ты написал: просто текст"


def test_web_app_data_is_acknowledged():
    update = message("", web_app_data={"data": '{"note":"ок"}', "button_text": "Мини-апп"})
    action = dispatch(update)[0]

    assert action[0] == "sendMessage"
    assert '{"note":"ок"}' in action[1]["text"]


def test_callback_answers_query_first():
    update = {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "data": "ping",
            "from": {"id": 7},
            "message": {"message_id": 1, "chat": {"id": 42}},
        },
    }
    actions = dispatch(update)

    assert actions[0] == ("answerCallbackQuery", {"callback_query_id": "cb1"})
    assert actions[1][1]["text"] == "pong (из кнопки)"


def test_unknown_update_type_is_ignored():
    assert dispatch({"update_id": 3, "poll": {}}) == []
