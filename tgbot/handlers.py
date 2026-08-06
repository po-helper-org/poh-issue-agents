"""
Вся логика бота — одна чистая функция `dispatch(update, miniapp_url)`, которая
превращает апдейт в список вызовов Bot API. Ни сети, ни глобального состояния:
благодаря этому polling и webhook гоняют один и тот же код, а тесты обходятся
без моков HTTP.

Действие — это кортеж (метод Bot API, payload).
"""

from typing import Any

Action = tuple[str, dict[str, Any]]

HELP_TEXT = (
    "Что я умею:\n"
    "/start — приветствие и кнопки\n"
    "/ping — проверка живости (отвечаю pong)\n"
    "/whoami — твои chat_id и user_id\n"
    "/echo <текст> — повторю текст\n"
    "/app — открыть мини-апп\n"
    "/help — эта справка"
)


def _keyboard(miniapp_url: str | None) -> dict[str, Any]:
    """Inline-клавиатура под приветствием. Кнопка мини-аппа появляется, только
    если URL сконфигурирован: Telegram отклоняет web_app без https."""
    rows: list[list[dict[str, Any]]] = [
        [
            {"text": "🏓 Ping", "callback_data": "ping"},
            {"text": "❓ Справка", "callback_data": "help"},
        ]
    ]
    if miniapp_url:
        rows.append([{"text": "🚀 Открыть мини-апп", "web_app": {"url": miniapp_url}}])
    return {"inline_keyboard": rows}


def _reply_keyboard(miniapp_url: str | None) -> dict[str, Any] | None:
    """Кнопка мини-аппа на обычной клавиатуре. Нужна отдельно от inline: только
    из такой кнопки мини-апп может вернуть данные через WebApp.sendData()."""
    if not miniapp_url:
        return None
    return {
        "keyboard": [[{"text": "🚀 Мини-апп", "web_app": {"url": miniapp_url}}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _handle_command(command: str, args: str, chat_id: int, user: dict[str, Any],
                    miniapp_url: str | None) -> list[Action]:
    if command == "start":
        name = user.get("first_name") or "друг"
        actions: list[Action] = [
            (
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Привет, {name}! Я тестовый бот. {HELP_TEXT}",
                    "reply_markup": _keyboard(miniapp_url),
                },
            )
        ]
        reply_kb = _reply_keyboard(miniapp_url)
        if reply_kb:
            actions.append(
                (
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Кнопка мини-аппа закреплена внизу — из неё он умеет "
                                "отправлять данные обратно в чат.",
                        "reply_markup": reply_kb,
                    },
                )
            )
        return actions

    if command == "ping":
        return [("sendMessage", {"chat_id": chat_id, "text": "pong"})]

    if command == "help":
        return [("sendMessage", {"chat_id": chat_id, "text": HELP_TEXT})]

    if command == "whoami":
        lines = [f"chat_id: {chat_id}", f"user_id: {user.get('id')}"]
        if user.get("username"):
            lines.append(f"username: @{user['username']}")
        return [("sendMessage", {"chat_id": chat_id, "text": "\n".join(lines)})]

    if command == "echo":
        if not args:
            return [("sendMessage", {"chat_id": chat_id, "text": "Формат: /echo <текст>"})]
        return [("sendMessage", {"chat_id": chat_id, "text": args})]

    if command == "app":
        if not miniapp_url:
            return [
                (
                    "sendMessage",
                    {"chat_id": chat_id, "text": "Мини-апп не сконфигурирован "
                                                 "(нет TELEGRAM_MINIAPP_URL)."},
                )
            ]
        return [
            (
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "Открывай:",
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "🚀 Мини-апп", "web_app": {"url": miniapp_url}}]
                        ]
                    },
                },
            )
        ]

    return [
        (
            "sendMessage",
            {"chat_id": chat_id, "text": f"Не знаю команду /{command}. Попробуй /help"},
        )
    ]


def _parse_command(text: str) -> tuple[str, str] | None:
    """`/echo@bot привет` -> ('echo', 'привет'). Не команда -> None."""
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    command = head.split("@", 1)[0].lower()
    if not command:
        return None
    return command, rest.strip()


def _handle_message(message: dict[str, Any], miniapp_url: str | None) -> list[Action]:
    chat_id = message["chat"]["id"]
    user = message.get("from") or {}

    # Данные из мини-аппа приходят не как текст, а отдельным полем.
    web_app_data = message.get("web_app_data")
    if web_app_data:
        payload = web_app_data.get("data", "")
        return [
            (
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Мини-апп прислал данные:\n<code>{payload}</code>",
                    "parse_mode": "HTML",
                },
            )
        ]

    text = (message.get("text") or "").strip()
    if not text:
        return [("sendMessage", {"chat_id": chat_id, "text": "Понимаю только текст и команды."})]

    parsed = _parse_command(text)
    if parsed:
        return _handle_command(parsed[0], parsed[1], chat_id, user, miniapp_url)

    return [("sendMessage", {"chat_id": chat_id, "text": f"Ты написал: {text}"})]


def _handle_callback(callback: dict[str, Any], miniapp_url: str | None) -> list[Action]:
    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    # Telegram крутит спиннер на кнопке, пока не придёт answerCallbackQuery.
    actions: list[Action] = [("answerCallbackQuery", {"callback_query_id": callback["id"]})]
    if chat_id is None:
        return actions

    if data == "ping":
        actions.append(("sendMessage", {"chat_id": chat_id, "text": "pong (из кнопки)"}))
    elif data == "help":
        actions.append(("sendMessage", {"chat_id": chat_id, "text": HELP_TEXT}))
    else:
        actions.append(
            ("sendMessage", {"chat_id": chat_id, "text": f"Неизвестная кнопка: {data}"})
        )
    return actions


def dispatch(update: dict[str, Any], miniapp_url: str | None = None) -> list[Action]:
    """Апдейт -> список вызовов Bot API. Незнакомый тип апдейта игнорируем."""
    if "message" in update:
        return _handle_message(update["message"], miniapp_url)
    if "callback_query" in update:
        return _handle_callback(update["callback_query"], miniapp_url)
    return []
