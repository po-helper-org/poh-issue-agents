#!/usr/bin/env python3
"""config.py — конфигурация из окружения. Список переменных — см. PROMPT.md
и README.md; единственное добавление сверх списка из промпта — PUBLIC_URL
(опционально), нужен только для ссылки на отчёт в сводке Telegram. Render
сам прокидывает RENDER_EXTERNAL_URL в каждый сервис, так что для деплоя на
Render отдельно задавать PUBLIC_URL не нужно."""
import os
from dataclasses import dataclass


@dataclass
class Config:
    data_dir: str
    cbr_url: str
    price_min_vnd: int
    price_max_vnd: int
    studio_area: float
    basic_auth_user: str
    basic_auth_pass: str
    run_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    run_cron: str
    public_url: str


def load() -> Config:
    return Config(
        data_dir=os.environ.get("DATA_DIR", "/data"),
        cbr_url=os.environ.get("CBR_URL", "https://www.cbr.ru/scripts/XML_daily.asp"),
        price_min_vnd=int(os.environ.get("PRICE_MIN_VND", "12000000")),
        price_max_vnd=int(os.environ.get("PRICE_MAX_VND", "18000000")),
        studio_area=float(os.environ.get("STUDIO_AREA", "45")),
        basic_auth_user=os.environ.get("BASIC_AUTH_USER", ""),
        basic_auth_pass=os.environ.get("BASIC_AUTH_PASS", ""),
        run_token=os.environ.get("RUN_TOKEN", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        run_cron=os.environ.get("RUN_CRON", "0 2 * * *"),
        public_url=(os.environ.get("PUBLIC_URL")
                    or os.environ.get("RENDER_EXTERNAL_URL")
                    or f"http://localhost:{os.environ.get('PORT', '10000')}"),
    )
