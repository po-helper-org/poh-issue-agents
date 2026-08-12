#!/usr/bin/env python3
"""
nhatot.py — ОГРАНИЧЕНИЕ, ЗАФИКСИРОВАННОЕ ЧЕСТНО: с сети, где собирался этот
пайплайн, nhatot.com отдаёт Cloudflare-челлендж ("Just a moment...") на
обычный GET — pipeline.http распознаёт его и роняет запрос в BlockedError
раньше парсинга. Живую разметку списка проверить не удалось.

nhatot/Chợ Tốt — Next.js-сайт: данные страницы обычно лежат целиком в
<script id="__NEXT_DATA__" type="application/json">, а не только в HTML
карточек. Это устойчивее к вёрстке (Cloudflare Bot Management такое всё
равно не пропустит без JS-рендера, но если когда-то пропустит — JSON
переживёт любой редизайн CSS). Поэтому парсер сначала пытается найти
__NEXT_DATA__ и рекурсивно найти в нём объекты, похожие на объявление
(есть list_id/ad_id + subject + price) — точный путь до массива объявлений
в дереве пропсов может меняться между релизами, полный обход это обходит.
Если __NEXT_DATA__ не нашёлся — второй попыткой пробуем CSS-селекторы по
карточкам, для страховки.
"""
import json
import logging
import re

from bs4 import BeautifulSoup

from .. import parsing
from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.nhatot")


def _walk_find_ads(node, out, seen_ids, depth=0):
    if depth > 60:  # защита от патологически глубокого дерева пропсов
        return
    if isinstance(node, dict):
        has_id = any(k in node for k in ("list_id", "ad_id", "id"))
        has_subject = any(k in node for k in ("subject", "title"))
        has_price = "price" in node
        if has_id and has_subject and has_price:
            key = node.get("list_id") or node.get("ad_id") or node.get("id")
            if key not in seen_ids:
                seen_ids.add(key)
                out.append(node)
        else:
            for v in node.values():
                _walk_find_ads(v, out, seen_ids, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _walk_find_ads(v, out, seen_ids, depth + 1)


def parse_list_json(html: str):
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, TypeError):
        return None
    ads, seen = [], set()
    _walk_find_ads(data, ads, seen)
    cards = []
    for ad in ads:
        list_id = ad.get("list_id") or ad.get("ad_id") or ad.get("id")
        if not list_id:
            continue
        url = ad.get("url") or f"https://www.nhatot.com/{list_id}.htm"
        if not url.startswith("http"):
            url = "https://www.nhatot.com" + url
        cards.append(dict(
            url=url, title=str(ad.get("subject") or ad.get("title") or ""),
            price_text=str(ad.get("price") or ""),
            area_text=str(ad.get("size") or ad.get("area") or ""),
            address=str(ad.get("area_name") or ad.get("region_name") or ad.get("address") or ""),
            thumb=ad.get("image") or (ad.get("images") or [None])[0] or "",
        ))
    return cards


CARD_SELECTORS = ["li[data-adid]", "div.AdItem_wrapper__adItem"]


def parse_list_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for sel in CARD_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    cards = []
    for it in items:
        a = it.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = "https://www.nhatot.com" + href
        text = it.get_text(" ", strip=True)
        img = it.find("img")
        cards.append(dict(url=href, title=a.get_text(strip=True) or text[:80],
                           price_text=text, area_text=text, address=text,
                           thumb=(img.get("src") if img else "") or ""))
    return cards


def scrape(target: dict, fx: dict) -> base.SourceResult:
    del fx
    result = base.SourceResult(name=target["name"], city=target["city"], url=target["url"])
    html = base.fetch_page(target["url"])
    if html is None:
        result.broken = True
        result.broken_reason = "страница не отдалась (челлендж/сеть)"
        return result
    cards = parse_list_json(html)
    if cards is None:
        cards = parse_list_html(html)
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
    tag = soup.find("script", id="__NEXT_DATA__")
    desc, photos = "", []
    if tag and tag.string:
        try:
            data = json.loads(tag.string)
            found = []
            _walk_find_ads(data, found, set())
            if found:
                ad = found[0]
                desc = str(ad.get("body") or ad.get("description") or "")
                photos = ad.get("images") or []
        except (json.JSONDecodeError, TypeError):
            pass
    if not desc:
        body = soup.select_one("div.AdView_adOverviewContent__1EJQr") or soup.select_one("[class*=description]")
        if body:
            desc = body.get_text(" ", strip=True)
    if desc:
        listing.raw_text = f"{listing.raw_text} {desc}".strip()
    if photos:
        listing.photos = photos
    listing.detailed = bool(desc)
    return bool(desc)
