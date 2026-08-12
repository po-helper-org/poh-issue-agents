#!/usr/bin/env python3
"""
telegram.py — короткая сводка после прогона. Токен и chat_id опциональны:
если не заданы, просто логируем, что отправка пропущена, и не роняем
прогон (см. PROMPT.md, "Telegram").
"""
import logging

import requests

log = logging.getLogger("pipeline.telegram")

API = "https://api.telegram.org/bot{token}/sendMessage"


def send_summary(*, token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id:
        log.info("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — сводка только в лог:\n%s", text)
        return False
    try:
        resp = requests.post(
            API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
        if resp.status_code != 200:
            log.error("Telegram ответил %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as e:
        log.error("Не удалось отправить сводку в Telegram: %s", e)
        return False


def build_summary_text(*, collected: int, passed: int, studio_dropped: int,
                        top: list, report_url: str, broken_sources: list) -> str:
    lines = [
        f"🏠 Прогон завершён: собрано {collected}, прошло {passed}, "
        f"отсеяно как студии {studio_dropped}.",
    ]
    if broken_sources:
        lines.append("⚠️ Сломанные источники: " + ", ".join(broken_sources))
    if top:
        lines.append("\nТоп-3:")
        for r in top[:3]:
            lines.append(f"· {r['rub']:,} ₽ · {r['street']} — {r['url']}".replace(",", " "))
    lines.append(f"\nПолный отчёт: {report_url}")
    return "\n".join(lines)
