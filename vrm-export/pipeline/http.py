#!/usr/bin/env python3
"""
http.py — общий HTTP-слой для всех скрейперов.

Требования из промпта: ретраи с экспоненциальной паузой, вежливый
User-Agent, пауза 2-3 секунды между запросами к одному хосту. Плюс своё:
отдельное распознавание "страницы вместо контента" (капча/Cloudflare-
челлендж) — это НЕ то же самое, что "0 карточек нашли", и вызывающий код
должен уметь их различать (см. pipeline/scrapers/base.py: BlockedError
против пустой выдачи).
"""
import logging
import random
import threading
import time

import requests
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                       wait_exponential)

log = logging.getLogger("pipeline.http")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

TIMEOUT = 20
HOST_DELAY = (2.0, 3.0)  # секунд, между запросами к одному хосту


class BlockedError(RuntimeError):
    """Хост отдал капчу / Cloudflare-челлендж вместо контента."""


class FetchError(RuntimeError):
    """Обычная сетевая неудача после всех ретраев."""


_BLOCK_MARKERS = (
    "just a moment",                       # Cloudflare challenge (batdongsan, nhatot)
    "cf-chl", "challenges.cloudflare.com",
    "vui lòng xác minh không phải robot",   # капча alonhadat
    "verifying you are human",
    "attention required",                   # Cloudflare 1020
)

_last_request = {}
_lock = threading.Lock()


def _throttle(host: str) -> None:
    with _lock:
        prev = _last_request.get(host, 0.0)
        wait = prev + random.uniform(*HOST_DELAY) - time.monotonic()
        should_sleep = wait > 0
        if should_sleep:
            _last_request[host] = prev + random.uniform(*HOST_DELAY)
        else:
            _last_request[host] = time.monotonic()
    if should_sleep:
        time.sleep(wait)


def looks_blocked(html: str) -> bool:
    head = html[:4000].lower()
    return any(m in head for m in _BLOCK_MARKERS)


_session = requests.Session()
_session.headers.update(DEFAULT_HEADERS)


@retry(reraise=True, stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=1.5, min=2, max=30),
       retry=retry_if_exception_type((requests.RequestException, FetchError)))
def get(url: str, *, referer: str = "", extra_headers: dict = None) -> requests.Response:
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    _throttle(host)
    headers = dict(extra_headers or {})
    if referer:
        headers["Referer"] = referer
    resp = _session.get(url, headers=headers, timeout=TIMEOUT)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise FetchError(f"{url} -> HTTP {resp.status_code}")
    return resp


def get_html(url: str, *, referer: str = "") -> str:
    resp = get(url, referer=referer)
    if resp.status_code >= 400:
        raise FetchError(f"{url} -> HTTP {resp.status_code}")
    if looks_blocked(resp.text):
        raise BlockedError(f"{url} -> похоже на капчу/челлендж, не контент")
    return resp.text


def get_bytes(url: str, *, referer: str = "") -> tuple:
    """Возвращает (bytes, content-type) — для скачивания фотографий."""
    resp = get(url, referer=referer, extra_headers={
        "Accept": "image/avif,image/webp,image/jpeg,image/png,*/*;q=0.8"})
    if resp.status_code >= 400:
        raise FetchError(f"{url} -> HTTP {resp.status_code}")
    ctype = resp.headers.get("Content-Type", "")
    if not ctype.startswith("image/"):
        raise FetchError(f"{url} -> отдали не картинку, а {ctype or 'ничего'}")
    return resp.content, ctype
