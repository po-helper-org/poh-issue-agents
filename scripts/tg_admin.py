#!/usr/bin/env python3
"""
Разовые настройки бота и ручные проверки — то, что дёргается из терминала, а не
крутится в рантайме.

    python -m scripts.tg_admin info                  # getMe + текущий вебхук
    python -m scripts.tg_admin setup                 # меню команд + кнопка мини-аппа
    python -m scripts.tg_admin webhook-set           # включить вебхук (нужен BASE_URL)
    python -m scripts.tg_admin webhook-delete        # вернуться на polling
    python -m scripts.tg_admin send <chat_id> <текст>
"""

import asyncio
import json
import sys

from tgbot.api import TelegramAPI
from tgbot.config import load_config

COMMANDS = [
    {"command": "start", "description": "Начать"},
    {"command": "ping", "description": "Проверка живости"},
    {"command": "whoami", "description": "Мои chat_id и user_id"},
    {"command": "echo", "description": "Повторить текст"},
    {"command": "app", "description": "Открыть мини-апп"},
    {"command": "help", "description": "Справка"},
]


async def cmd_info(api: TelegramAPI, cfg, _args: list[str]) -> None:
    print(json.dumps(await api.get_me(), ensure_ascii=False, indent=2))
    print(json.dumps(await api.get_webhook_info(), ensure_ascii=False, indent=2))


async def cmd_setup(api: TelegramAPI, cfg, _args: list[str]) -> None:
    await api.call("setMyCommands", commands=COMMANDS)
    print(f"команды установлены: {len(COMMANDS)}")

    if cfg.miniapp_url:
        await api.call(
            "setChatMenuButton",
            menu_button={"type": "web_app", "text": "Мини-апп",
                         "web_app": {"url": cfg.miniapp_url}},
        )
        print(f"кнопка меню -> {cfg.miniapp_url}")
    else:
        await api.call("setChatMenuButton", menu_button={"type": "commands"})
        print("TELEGRAM_MINIAPP_URL не задан — в меню оставлены команды")


async def cmd_webhook_set(api: TelegramAPI, cfg, _args: list[str]) -> None:
    if not cfg.webhook_url:
        sys.exit("TELEGRAM_WEBHOOK_BASE_URL не задан")
    await api.set_webhook(cfg.webhook_url, cfg.webhook_secret)
    print(f"вебхук -> {cfg.webhook_url}")
    print(json.dumps(await api.get_webhook_info(), ensure_ascii=False, indent=2))


async def cmd_webhook_delete(api: TelegramAPI, cfg, _args: list[str]) -> None:
    await api.delete_webhook()
    print("вебхук снят, можно работать через polling")


async def cmd_send(api: TelegramAPI, cfg, args: list[str]) -> None:
    if len(args) < 2:
        sys.exit("нужно: send <chat_id> <текст>")
    result = await api.send_message(args[0], " ".join(args[1:]))
    print(f"отправлено, message_id={result['message_id']}")


COMMANDS_MAP = {
    "info": cmd_info,
    "setup": cmd_setup,
    "webhook-set": cmd_webhook_set,
    "webhook-delete": cmd_webhook_delete,
    "send": cmd_send,
}


async def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS_MAP:
        sys.exit(__doc__)
    cfg = load_config()
    async with TelegramAPI(cfg.token) as api:
        await COMMANDS_MAP[sys.argv[1]](api, cfg, sys.argv[2:])


if __name__ == "__main__":
    asyncio.run(main())
