"""Проверка подлинности доставки вебхука GitLab.

У GitLab два несовместимых механизма, и какой доступен — зависит от версии
инстанса:

* **Signing token, HMAC** — с 19.0, GA в 19.1. Заголовок `webhook-signature`,
  подписывается строка `{webhook-id}.{webhook-timestamp}.{body}`, ключ — base64
  после снятия префикса `whsec_`.
* **Plain token** — везде. Заголовок `X-Gitlab-Token` сравнивается с секретом
  как есть. Сама документация GitLab называет его нерекомендуемым для новых
  вебхуков.

Режим выбирается явно, а не угадывается. Молчаливый откат с HMAC на сравнение
строки — это тихое ослабление проверки подлинности: инстанс обновили, подпись
появилась, а контур продолжает принимать доставки по секрету в заголовке, и
никто об этом не узнает.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

MODE_HMAC = "hmac"
MODE_TOKEN = "token"

# Доставка старше этого срока отвергается: подпись верна вечно, и без окна
# перехваченный запрос можно переиграть когда угодно.
DEFAULT_TOLERANCE_SECONDS = 300


class SignatureError(Exception):
    """Доставка не прошла проверку подлинности."""


def _decode_key(secret: str) -> bytes:
    """Ключ подписи из секрета.

    GitLab выдаёт signing token с префиксом `whsec_`, за которым base64. Если
    префикса нет — считаем, что дали сырой ключ, и берём его как есть: падать
    на своей же догадке о формате хуже, чем подписать тем, что дали.
    """
    raw = secret.strip()
    if raw.startswith("whsec_"):
        raw = raw[len("whsec_"):]
        try:
            return base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise SignatureError(f"signing token после whsec_ не base64: {exc}") from exc
    return raw.encode()


def verify_hmac(body: bytes, headers: dict, secret: str, *,
                tolerance: int = DEFAULT_TOLERANCE_SECONDS,
                now: float | None = None) -> None:
    """Проверка подписи GitLab 19.0+. Молча возвращается, если всё сошлось."""
    get = lambda name: (headers.get(name) or headers.get(name.lower()) or "").strip()  # noqa: E731

    webhook_id = get("webhook-id")
    timestamp = get("webhook-timestamp")
    signature = get("webhook-signature")
    if not (webhook_id and timestamp and signature):
        raise SignatureError(
            "нет заголовков подписи: нужны webhook-id, webhook-timestamp, webhook-signature")

    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise SignatureError(f"webhook-timestamp не число: {timestamp!r}") from exc

    current = time.time() if now is None else now
    if tolerance > 0 and abs(current - sent_at) > tolerance:
        raise SignatureError(
            f"доставка старше допуска: {int(abs(current - sent_at))} с при пороге {tolerance} с")

    message = f"{webhook_id}.{timestamp}.".encode() + body
    digest = hmac.new(_decode_key(secret), message, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()

    # Заголовок несёт СПИСОК подписей через пробел: во время ротации ключа их
    # две. Совпадение с любой означает подлинность.
    for candidate in signature.split(" "):
        version, _, value = candidate.partition(",")
        if version != "v1" or not value:
            continue
        if hmac.compare_digest(expected, value):
            return
    raise SignatureError("ни одна подпись из webhook-signature не сошлась")


def verify_token(headers: dict, secret: str) -> None:
    """Проверка plain-токена. Молча возвращается, если сошлось."""
    sent = (headers.get("X-Gitlab-Token") or headers.get("x-gitlab-token") or "")
    if not sent:
        raise SignatureError("нет заголовка X-Gitlab-Token")
    # Сравниваем БАЙТЫ, не строки: compare_digest на str поддерживает только
    # ASCII и бросает TypeError на всём остальном. Заголовок приходит снаружи,
    # и что в нём — не нам решать; исключение здесь означало бы 500, потерянную
    # доставку и шаг к отключению вебхука вместо честного «не совпал».
    if not hmac.compare_digest(sent.strip().encode("utf-8", "surrogatepass"),
                               secret.strip().encode("utf-8", "surrogatepass")):
        raise SignatureError("X-Gitlab-Token не совпал с секретом")


def verify(body: bytes, headers: dict, secret: str, mode: str, **kwargs) -> None:
    """Проверка в заданном режиме.

    Режим — явный параметр, а не результат угадывания по наличию заголовков.
    Угадывание означало бы, что отправитель сам выбирает, как его проверять.
    """
    if not secret:
        raise SignatureError("секрет вебхука не задан")
    if mode == MODE_HMAC:
        return verify_hmac(body, headers, secret, **kwargs)
    if mode == MODE_TOKEN:
        return verify_token(headers, secret)
    raise SignatureError(f"неизвестный режим проверки: {mode!r}")
