"""
Проверки подлинности. Два независимых механизма:

1. Webhook: Telegram шлёт заголовок X-Telegram-Bot-Api-Secret-Token с тем
   значением, которое мы передали в setWebhook. Сверяем его — иначе кто угодно,
   узнав URL, сможет слать боту поддельные апдейты.

2. Mini App initData: подписанная строка от Telegram-клиента. Ключ —
   HMAC-SHA256("WebAppData", bot_token), подпись — HMAC-SHA256 от отсортированных
   пар key=value. Без этой проверки данные из мини-аппа — просто текст из
   браузера, которому нельзя верить.
"""

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode


class InitDataError(ValueError):
    """initData не прошла проверку."""


def check_webhook_secret(expected: str | None, received: str | None) -> bool:
    """Сравнение секрета вебхука в постоянном времени."""
    if not expected:
        return True  # секрет не настроен — проверять нечего
    if not received:
        return False
    return hmac.compare_digest(expected, received)


def validate_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86400,
                       now: float | None = None) -> dict[str, Any]:
    """Проверить подпись Telegram.WebApp.initData и вернуть разобранные поля.

    Бросает InitDataError, если подписи нет, она не сходится или данные протухли.
    """
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("в initData нет поля hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("подпись initData не совпадает")

    auth_date = pairs.get("auth_date")
    if max_age_seconds and auth_date:
        current = time.time() if now is None else now
        if current - int(auth_date) > max_age_seconds:
            raise InitDataError("initData просрочена")

    return pairs


def build_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Собрать корректно подписанную initData. Нужно только тестам — в проде
    подписывает Telegram."""
    # Подпись считается по декодированным значениям, а в строку они уходят
    # процентно-закодированными — как это делает Telegram-клиент.
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})
