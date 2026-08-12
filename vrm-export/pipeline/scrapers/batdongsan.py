#!/usr/bin/env python3
"""
batdongsan.py — ОГРАНИЧЕНИЕ, ЗАФИКСИРОВАННОЕ ЧЕСТНО: с сети, где собирался
этот пайплайн, batdongsan.com.vn отдаёт Cloudflare-челлендж ("Just a
moment...") на обычный GET — pipeline.http его распознаёт и запрос падает
в BlockedError раньше парсинга. Живую разметку карточек проверить не
удалось; селекторы ниже — лучшее предположение по типовой структуре
(`div.js__card`, `.js__card-title`, `.js__card-config-item`) с запасным
вариантом.

ЛОВУШКА РАЙОННОГО URL (см. PROMPT.md). У batdongsan НЕТ отдельного URL на
район вида ".../cho-thue-can-ho-chung-cu-quan-son-tra-da-nang" — сайт не
отдаёт 404, а молча показывает общевьетнамский список (44 000+ объявлений,
Ханой и Хошимин вперемешку). Поэтому:
  1. в scrapers/__init__.py заведён только ГОРОДСКОЙ URL, район фильтруется
     здесь, в коде, через districts.normalize_district;
  2. дополнительно — сторожевая проверка has_foreign_city_marker(): если в
     выдаче попались явно чужие адреса (Vinhomes Smart City, Tây Mỗ,
     Bến Nghé и т.п.), результат источника выбрасывается ЦЕЛИКОМ и логируется
     как сломанный URL, а не просто "плохие карточки отфильтровались".
"""
import logging
import re

from bs4 import BeautifulSoup

from .. import parsing
from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.batdongsan")

CARD_SELECTORS = ["div.js__card", "div.re__card-full", "div.js__product-item-web"]


def parse_list(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for sel in CARD_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    cards = []
    for it in items:
        a = it.select_one(".js__card-title a") or it.select_one("a.js__product-link-for-product-id") \
            or it.find("a", href=True)
        if not a or not a.get("href"):
            continue
        href = a["href"]
        if href.startswith("/"):
            href = "https://batdongsan.com.vn" + href
        text = it.get_text(" ", strip=True)
        img = it.find("img")
        thumb = (img.get("src") or img.get("data-src") or "") if img else ""
        cards.append(dict(url=href, title=a.get_text(strip=True) or text[:80],
                           text=text, thumb=thumb))
    return cards


def scrape(target: dict, fx: dict) -> base.SourceResult:
    del fx
    result = base.SourceResult(name=target["name"], city=target["city"], url=target["url"])
    html = base.fetch_page(target["url"])
    if html is None:
        result.broken = True
        result.broken_reason = "страница не отдалась (челлендж/сеть)"
        return result

    if base.has_foreign_city_marker(html):
        result.broken = True
        result.broken_reason = ("в выдаче нашлись чужие адреса (Ханой/ХШМ) — "
                                 "сайт подменил районный URL общевьетнамским списком")
        log.error("batdongsan %s: %s", target["url"], result.broken_reason)
        return result

    cards = parse_list(html)
    if not cards:
        result.broken = True
        result.broken_reason = "страница получена, но 0 карточек — вероятно, сменилась вёрстка"
        return result
    result.found = len(cards)
    for c in cards:
        price_vnd, _ = parsing.parse_price_vnd(c["text"])
        area = parsing.parse_area(c["text"])
        listing = Listing(
            source=target["name"], url=c["url"], title=c["title"], raw_text=c["text"],
            city=target["city"], district=c["text"], price_vnd=price_vnd, area_m2=area,
            photos=[c["thumb"]] if c["thumb"] else [],
        )
        result.listings.append(listing)
    return result


def enrich_detail(listing: Listing) -> bool:
    html = base.fetch_page(listing.url)
    if html is None:
        return False
    if base.has_foreign_city_marker(html):
        return False
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.re__detail-content") or soup.select_one("[class*=description]")
    if body:
        listing.raw_text = f"{listing.raw_text} {body.get_text(' ', strip=True)}".strip()
    photos = [img.get("src") for img in soup.select("div.re__media-thumb-item img") if img.get("src")]
    if photos:
        listing.photos = photos
    listing.detailed = bool(body)
    return bool(body)
