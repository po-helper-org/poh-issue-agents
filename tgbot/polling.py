"""
Long polling: единственный режим, который работает без публичного IP — бот сам
ходит за апдейтами наружу. Ровно поэтому он выбран режимом по умолчанию для
разработки в изолированном окружении.

Каждый входящий апдейт дополнительно пишется в JSONL-журнал: так его можно
посмотреть постфактум, не поднимая отладчик.
"""

import asyncio
import json
import logging
import signal
from pathlib import Path
from typing import Any

from .api import TelegramAPI, TelegramError
from .config import Config
from .runner import handle_update

_log = logging.getLogger("tgbot.polling")

JOURNAL_PATH = Path(__file__).resolve().parent.parent / ".runtime" / "updates.jsonl"


def journal(update: dict[str, Any], path: Path = JOURNAL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(update, ensure_ascii=False) + "\n")


async def run_polling(config: Config, *, poll_timeout: int = 30) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with TelegramAPI(config.token, timeout=poll_timeout + 15) as api:
        me = await api.get_me()
        # getUpdates и вебхук взаимоисключающи — Telegram вернёт 409, если не снять.
        await api.delete_webhook()
        _log.info("polling запущен для @%s", me.get("username"))

        offset: int | None = None
        while not stop.is_set():
            try:
                updates = await api.get_updates(offset, poll_timeout)
            except (TelegramError, OSError) as exc:
                _log.warning("getUpdates упал (%s), повтор через 3с", exc)
                await asyncio.sleep(3)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                journal(update)
                _log.info("update %s: %s", update["update_id"], _summary(update))
                await handle_update(api, update, config.miniapp_url)

    _log.info("polling остановлен")


def _summary(update: dict[str, Any]) -> str:
    message = update.get("message")
    if message:
        if message.get("web_app_data"):
            return f"web_app_data от {(message.get('from') or {}).get('id')}"
        return f"message {(message.get('text') or '<нетекст>')!r}"
    if update.get("callback_query"):
        return f"callback {update['callback_query'].get('data')!r}"
    return "прочее"
