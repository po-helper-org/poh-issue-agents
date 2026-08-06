"""
Исполнитель действий: берёт то, что вернул dispatch(), и реально дёргает Bot API.
Ошибка на одном действии не должна ронять обработку апдейта целиком — логируем
и идём дальше.
"""

import logging
from typing import Any

import httpx

from .api import TelegramAPI, TelegramError
from .handlers import dispatch

_log = logging.getLogger("tgbot.runner")


async def handle_update(api: TelegramAPI, update: dict[str, Any],
                        miniapp_url: str | None) -> None:
    for method, payload in dispatch(update, miniapp_url):
        try:
            await api.call(method, **payload)
        except (TelegramError, httpx.HTTPError) as exc:
            _log.error("update %s: %s не прошёл — %s", update.get("update_id"), method, exc)
