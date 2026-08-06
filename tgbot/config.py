"""
Конфигурация Telegram-бота: всё берётся из окружения, ничего не хардкодится.

Токен обязателен всегда. Остальное нужно только для соответствующих режимов:
WEBHOOK_* — для приёма апдейтов по HTTP, MINIAPP_URL — чтобы кнопка меню
открывала мини-апп.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    token: str
    webhook_base_url: str | None
    webhook_path: str
    webhook_secret: str | None
    miniapp_url: str | None
    host: str
    port: int

    @property
    def webhook_url(self) -> str | None:
        if not self.webhook_base_url:
            return None
        return self.webhook_base_url.rstrip("/") + self.webhook_path


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан — положи его в .env или в окружение")

    return Config(
        token=token,
        webhook_base_url=os.environ.get("TELEGRAM_WEBHOOK_BASE_URL", "").strip() or None,
        webhook_path=os.environ.get("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook").strip(),
        webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip() or None,
        miniapp_url=os.environ.get("TELEGRAM_MINIAPP_URL", "").strip() or None,
        host=os.environ.get("TELEGRAM_BOT_HOST", "0.0.0.0"),
        port=int(os.environ.get("TELEGRAM_BOT_PORT", "8081")),
    )
