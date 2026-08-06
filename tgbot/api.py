"""
Тонкий асинхронный клиент Bot API. Никакой бизнес-логики — только транспорт:
собрать URL, отправить JSON, развернуть конверт {"ok": ..., "result": ...}.
"""

import logging
from typing import Any

import httpx

_log = logging.getLogger("tgbot.api")

API_ROOT = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Bot API вернул ok=false."""

    def __init__(self, method: str, code: int | None, description: str) -> None:
        super().__init__(f"{method} -> {code}: {description}")
        self.method = method
        self.code = code
        self.description = description


class TelegramAPI:
    def __init__(self, token: str, *, timeout: float = 65.0) -> None:
        self._base = f"{API_ROOT}/bot{token}"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "TelegramAPI":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, **payload: Any) -> Any:
        """Вызвать метод Bot API. None-поля выбрасываем — Telegram их не любит."""
        body = {k: v for k, v in payload.items() if v is not None}
        response = await self._client.post(f"{self._base}/{method}", json=body)
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(method, data.get("error_code"), data.get("description", ""))
        return data["result"]

    # --- сахар для методов, которые реально используются ---

    async def get_me(self) -> dict[str, Any]:
        return await self.call("getMe")

    async def send_message(self, chat_id: int | str, text: str, **kw: Any) -> dict[str, Any]:
        return await self.call("sendMessage", chat_id=chat_id, text=text, **kw)

    async def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        return await self.call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )

    async def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        return await self.call("deleteWebhook", drop_pending_updates=drop_pending_updates)

    async def set_webhook(self, url: str, secret_token: str | None = None) -> bool:
        return await self.call(
            "setWebhook",
            url=url,
            secret_token=secret_token,
            allowed_updates=["message", "callback_query"],
        )

    async def get_webhook_info(self) -> dict[str, Any]:
        return await self.call("getWebhookInfo")
