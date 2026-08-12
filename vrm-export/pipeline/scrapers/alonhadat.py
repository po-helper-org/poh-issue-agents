#!/usr/bin/env python3
"""
alonhadat.py — ОГРАНИЧЕНИЕ, ЗАФИКСИРОВАННОЕ ЧЕСТНО: с сети, где собирался
этот пайплайн, alonhadat.com.vn отвечает капчей ("Vui lòng xác minh không
phải Robot") на обычный GET уже на первой странице — pipeline.http её
распознаёт (looks_blocked) и весь запрос падает в BlockedError раньше,
чем до парсинга вообще доходит. Проверить реальную разметку списка
объявлений с этой сети не удалось.

Селекторы ниже — типовая структура старых досок объявлений на движке
alonhadat (`div.content-item`, `.ct_title a`, `.ct_dis`, `.ct_price`,
`.ct_dt`), сохранены как лучшее предположение и снабжены запасным
селектором. Если на Render (другая сеть, другая репутация IP) капча не
встанет — код заработает как есть; если структура на самом деле другая —
found=0 при полученной странице немедленно уйдёт в broken=True и будет
видно в логах/Telegram, что селекторы пора поправить руками (см. README,
"Как чинить парсер при смене вёрстки").
"""
import logging
import re

from bs4 import BeautifulSoup

from .. import parsing
from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.alonhadat")

CARD_SELECTORS = ["div.content-item", "div.ct-item", "div.content_item"]


def parse_list(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for sel in CARD_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    cards = []
    for it in items:
        a = it.select_one(".ct_title a") or it.find("a", href=True)
        if not a or not a.get("href"):
            continue
        href = a["href"]
        if href.startswith("/"):
            href = "https://alonhadat.com.vn" + href
        addr = it.select_one(".ct_dis") or it.select_one(".ct_diachi")
        price = it.select_one(".ct_price")
        area = it.select_one(".ct_dt") or it.select_one(".ct_area")
        img = it.find("img")
        thumb = (img.get("src") or img.get("data-src") or "") if img else ""
        cards.append(dict(
            url=href, title=a.get_text(strip=True),
            address=addr.get_text(strip=True) if addr else "",
            price_text=price.get_text(strip=True) if price else "",
            area_text=area.get_text(strip=True) if area else "",
            thumb=thumb,
        ))
    return cards


def scrape(target: dict, fx: dict) -> base.SourceResult:
    del fx
    result = base.SourceResult(name=target["name"], city=target["city"], url=target["url"])
    html = base.fetch_page(target["url"])
    if html is None:
        result.broken = True
        result.broken_reason = "страница не отдалась (капча/сеть)"
        return result
    cards = parse_list(html)
    if not cards:
        result.broken = True
        result.broken_reason = "страница получена, но 0 карточек — вероятно, сменилась вёрстка"
        return result
    result.found = len(cards)
    for c in cards:
        price_vnd, _ = parsing.parse_price_vnd(c["price_text"])
        area = parsing.parse_area(c["area_text"]) or parsing.parse_area(c["title"])
        raw_text = " ".join(filter(None, [c["title"], c["address"]]))
        listing = Listing(
            source=target["name"], url=c["url"], title=c["title"], raw_text=raw_text,
            city=target["city"], district=c["address"], price_vnd=price_vnd, area_m2=area,
            photos=[c["thumb"]] if c["thumb"] else [],
        )
        result.listings.append(listing)
    return result


def enrich_detail(listing: Listing) -> bool:
    html = base.fetch_page(listing.url)
    if html is None:
        return False
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.ct_dtl_content") or soup.select_one("div.detail_content")
    if body:
        listing.raw_text = f"{listing.raw_text} {body.get_text(' ', strip=True)}".strip()
    photos = [img.get("src") for img in soup.select("div.slide_show img, div.slide-show img") if img.get("src")]
    if photos:
        listing.photos = photos
    listing.detailed = bool(body)
    return bool(body)
