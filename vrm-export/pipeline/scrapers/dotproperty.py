#!/usr/bin/env python3
"""
dotproperty.py — карточка article.listing-snippet, снята с живой страницы
12.08.2026. Вся вёрстка — сгенерированные Tailwind-классы без семантики
("text-secondary-base font-bold text-3xl" на цене), которые с высокой
вероятностью пересобираются при каждом деплое сайта. Цепляться за них
бессмысленно — вместо этого разбираем текст всей карточки регулярками
(цена "₫ 20,000,000", площадь "Area: 63 m²" — совпадает с форматом,
который уже понимает pipeline.parsing.parse_area).

Заголовка как отдельного текстового узла на списке нет (изображение без
alt, ссылка без текста) — берём его из слага URL, это единственное
стабильное место. Списочный текст уже достаточно полный (адрес +
"PROPERTY DETAILS" + "DESCRIPTION"), поэтому detailed=True сразу.
"""
import logging
import re

from bs4 import BeautifulSoup

from .. import parsing
from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.dotproperty")

_PRICE_VND = re.compile(r"₫\s*([\d,\.]{4,})")
_PRICE_USD = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def _title_from_slug(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"_[0-9a-f-]{8,}$", "", slug)  # хвост-идентификатор
    return slug.replace("-", " ").strip().capitalize()


def parse_list(html: str):
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for art in soup.select("article.listing-snippet"):
        link = art.find("a", href=re.compile(r"/ads/"))
        if not link or not link.get("href"):
            continue
        text = art.get_text(" ", strip=True)
        photos = [i["src"] for i in art.select("img[src]")
                  if i.get("src", "").startswith("http")][:6]
        cards.append(dict(url=link["href"], text=text, photos=photos))
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
        m = _PRICE_VND.search(c["text"])
        if m:
            price_vnd = int(m.group(1).replace(",", "").replace(".", ""))
        else:
            m = _PRICE_USD.search(c["text"])
            if m:
                price_vnd = round(float(m.group(1).replace(",", "")) * usd_to_vnd)
        area = parsing.parse_area(c["text"])
        title = _title_from_slug(c["url"])
        listing = Listing(
            source=target["name"], url=c["url"], title=title, raw_text=c["text"],
            city=target["city"], district=c["text"], price_vnd=price_vnd, area_m2=area,
            photos=c["photos"], detailed=True,
        )
        result.listings.append(listing)
    return result


def enrich_detail(listing: Listing) -> bool:
    return False
