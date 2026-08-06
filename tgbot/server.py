"""
HTTP-сторона бота: приём вебхуков от Telegram, бэкенд мини-аппа и раздача его
статики. Логика обработки апдейтов та же самая, что в polling — общий dispatch().

Запускать имеет смысл там, где у сервиса есть публичный HTTPS-адрес: Telegram
ходит к вебхуку сам и только на 80/88/443/8443.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import TelegramAPI
from .config import Config, load_config
from .runner import handle_update
from .security import InitDataError, check_webhook_secret, validate_init_data

_log = logging.getLogger("tgbot.server")

MINIAPP_DIR = Path(__file__).resolve().parent / "miniapp"


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.api = TelegramAPI(cfg.token)
        yield
        await app.state.api.close()

    app = FastAPI(title="telegram-bot", lifespan=lifespan)
    app.state.config = cfg
    app.state.api = None

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "webhook_path": cfg.webhook_path,
                "miniapp_url": cfg.miniapp_url}

    @app.post(cfg.webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, str]:
        if not check_webhook_secret(cfg.webhook_secret, x_telegram_bot_api_secret_token):
            raise HTTPException(status_code=401, detail="bad secret token")

        update = await request.json()
        _log.info("webhook update %s", update.get("update_id"))
        await handle_update(app.state.api, update, cfg.miniapp_url)
        # Telegram ретраит апдейт на любой не-2xx — отвечаем сразу и всегда.
        return {"status": "ok"}

    @app.post("/api/miniapp/verify")
    async def miniapp_verify(payload: dict[str, Any]) -> JSONResponse:
        """Мини-апп присылает свою initData — сервер проверяет подпись и
        возвращает, кем на самом деле является пользователь."""
        init_data = payload.get("init_data") or ""
        try:
            fields = validate_init_data(init_data, cfg.token)
        except InitDataError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=401)
        return JSONResponse({"ok": True, "fields": fields})

    if MINIAPP_DIR.is_dir():
        app.mount("/miniapp", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")

    return app
