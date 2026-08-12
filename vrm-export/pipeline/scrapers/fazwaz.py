#!/usr/bin/env python3
"""
fazwaz.py — структура снята с живой страницы 12.08.2026. Карточка —
div.result-search__item; ссылка/заголовок — a.unit-info__description-title;
цена — div.price-tag, ВСЕГДА в USD ("$200/mo", см. PROMPT.md); площадь —
span.area-tooltip (не area-per-tooltip — там цена за м²); короткое, но
полноценное описание — div.unit-info__shot-description (достаточно текста,
чтобы не выглядеть как список, поэтому detailed=True сразу, без отдельного
захода на страницу объявления — экономим запросы к сайту, который и так
самый крупный по числу карточек).
"""
import logging
import re

from bs4 import BeautifulSoup

from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.fazwaz")

_PRICE_USD = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_AREA = re.compile(r"([\d.]+)\s*sqm", re.I)


def parse_list(html: str):
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for item in soup.select("div.result-search__item"):
        link = item.select_one("a.unit-info__description-title") or item.select_one("a.link-unit")
        if not link or not link.get("href"):
            continue
        price_el = item.select_one("div.price-tag")
        price_text = price_el.contents[0].strip() if price_el and price_el.contents else ""
        area_el = item.select_one("span.area-tooltip:not(.area-per-tooltip)")
        loc_el = item.select_one("div.location-unit")
        desc_el = item.select_one("div.unit-info__shot-description")
        bed = None
        wrap = item.select_one("div.wrap-icon-info")
        if wrap:
            m = re.search(r"i-bed[^>]*>\s*</i>\s*(\d+)", str(wrap))
            if m:
                bed = int(m.group(1))
        photos = [img.get("src") for img in item.select("img.thumb-gallery-img, img.main-gallery-img") if img.get("src")]
        cards.append(dict(
            url=link["href"], title=link.get_text(strip=True),
            price_text=price_text, area_text=area_el.get_text(strip=True) if area_el else "",
            address=loc_el.get_text(strip=True) if loc_el else "",
            description=desc_el.get_text(" ", strip=True) if desc_el else "",
            bedrooms=bed, photos=photos,
        ))
    return cards


def scrape(target: dict, fx: dict) -> base.SourceResult:
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

    usd_to_vnd = fx["usd_to_rub"] / fx["vnd_to_rub"]
    for c in cards:
        price_vnd = None
        m = _PRICE_USD.search(c["price_text"])
        if m:
            usd = float(m.group(1).replace(",", ""))
            price_vnd = round(usd * usd_to_vnd)
        area = None
        m = _AREA.search(c["area_text"])
        if m:
            area = float(m.group(1))
        bedroom_marker = f"{c['bedrooms']} bedroom" if c.get("bedrooms") and c["bedrooms"] >= 2 else ""
        raw_text = " ".join(filter(None, [c["title"], c["address"], c["description"], bedroom_marker]))
        listing = Listing(
            source=target["name"], url=c["url"], title=c["title"], raw_text=raw_text,
            city=target["city"], district=c["address"], price_vnd=price_vnd, area_m2=area,
            photos=c["photos"], detailed=True,
        )
        result.listings.append(listing)
    return result


def enrich_detail(listing: Listing) -> bool:
    return False  # уже detailed=True с листинга, отдельный заход не нужен
