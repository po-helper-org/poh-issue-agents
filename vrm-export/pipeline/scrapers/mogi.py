#!/usr/bin/env python3
"""
mogi.py — карточки живой разметки сняты 12.08.2026, структура проверена
руками (см. scratchpad прогона). Список: <li> с div.prop-img + div.prop-info,
пагинация ?cp=N. Деталка: h2.info-title "Giới thiệu" -> следующий
div.info-content-body — полное описание; div.info-attr — атрибуты
("Phòng ngủ", "Diện tích sử dụng", "Ngày đăng"); div.media-item img — фото.

ПРЕИМУЩЕСТВО MOGI (см. PROMPT.md): число спален — отдельное поле
("1 PN"/"2 PN" в prop-attr на списке, "Phòng ngủ" в info-attr на деталке),
не текст описания. Используем его напрямую для отсева 2PN/3PN — это
надёжнее регулярок по свободному тексту.
"""
import logging
import re

from bs4 import BeautifulSoup

from .. import parsing
from ..core import Listing
from . import base

log = logging.getLogger("pipeline.scrapers.mogi")

MAX_PAGES = 3


def _bedroom_count(attr_lis) -> int | None:
    for li in attr_lis:
        t = li.get_text(" ", strip=True).lower()
        m = re.match(r"(\d+)\s*(?:pn|phòng ngủ|phong ngu)\b", t)
        if m:
            return int(m.group(1))
    return None


def parse_list(html: str, city: str, source_name: str, page_url: str):
    soup = BeautifulSoup(html, "html.parser")
    infos = soup.select("div.prop-info")
    cards = []
    for info in infos:
        a = info.select_one("a.link-overlay")
        if not a or not a.get("href"):
            continue
        title = info.select_one("h2.prop-title")
        addr = info.select_one("div.prop-addr")
        price = info.select_one("div.price")
        attrs = info.select("ul.prop-attr li")
        bedrooms = _bedroom_count(attrs)
        # БЕЗ разделителя-пробела: "45 m<sup>2</sup>" должно остаться "45 m2",
        # а не превратиться в "45 m 2" — иначе parse_area его не узнает.
        area_text = attrs[0].get_text(strip=True) if attrs else ""
        parent = info.find_parent("li") or info.parent
        img = parent.select_one("div.prop-img img") if parent else None
        thumb = (img.get("src") or img.get("data-src") or "") if img else ""
        cards.append(dict(
            url=a["href"], title=title.get_text(strip=True) if title else "",
            address=addr.get_text(strip=True) if addr else "",
            price_text=price.get_text(strip=True) if price else "",
            area_text=area_text, bedrooms=bedrooms, thumb=thumb,
        ))
    return cards


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out = {"description": "", "photos": [], "floor": None, "owner": "", "posted": ""}
    h2 = soup.find("h2", string=re.compile("Giới thiệu|Gioi thieu"))
    if h2:
        body = h2.find_next_sibling("div", class_="info-content-body")
        if body:
            out["description"] = body.get_text(" ", strip=True)
    for row in soup.select("div.info-attr"):
        parts = row.get_text(" | ", strip=True).split(" | ")
        if len(parts) >= 2:
            label, value = parts[0].lower(), parts[1]
            if "ngày đăng" in label or "ngay dang" in label:
                out["posted"] = value
            elif "tầng" in label or "tang" in label:
                m = re.search(r"\d+", value)
                if m:
                    out["floor"] = int(m.group())
    agent = soup.select_one("div.agent-name")
    if agent:
        out["owner"] = agent.get_text(strip=True)
    for m in soup.select("div.media-item img"):
        src = m.get("data-src") or m.get("src")
        if src:
            out["photos"].append(src)
    return out


def scrape(target: dict, fx: dict) -> base.SourceResult:
    del fx  # Mogi всегда в донгах, курс не нужен — сигнатура одинаковая для всех движков
    result = base.SourceResult(name=target["name"], city=target["city"], url=target["url"])
    all_cards, page_url = [], target["url"]
    for page in range(1, MAX_PAGES + 1):
        url = page_url if page == 1 else f"{page_url}{'&' if '?' in page_url else '?'}cp={page}"
        html = base.fetch_page(url)
        if html is None:
            if page == 1:
                result.broken = True
                result.broken_reason = "страница не отдалась (капча/сеть)"
            break
        cards = parse_list(html, target["city"], target["name"], url)
        if page == 1 and not cards:
            # Страница получена нормально, но ни одной карточки — это НЕ
            # "ничего не подошло" (то нормально, см. DotProperty в PROMPT.md),
            # а разметка сайта, скорее всего, поменялась. Кричать в Telegram.
            result.broken = True
            result.broken_reason = "страница получена, но 0 карточек — вероятно, сменилась вёрстка"
            break
        if not cards:
            break
        all_cards.extend(cards)

    result.found = len(all_cards)
    for c in all_cards:
        price_vnd, _note = parsing.parse_price_vnd(c["price_text"])
        area = parsing.parse_area(c["area_text"]) or parsing.parse_area(c["title"])
        if c.get("bedrooms") and c["bedrooms"] >= 2:
            # Mogi отдаёт спальни отдельным полем — отсев надёжнее регулярки
            # по тексту. Помечаем явным маркером в raw_text, чтобы
            # NOT_1BR-правило в patch_v2 сработало и на этом основании тоже.
            bedroom_marker = f"{c['bedrooms']} phòng ngủ"
        else:
            bedroom_marker = ""
        raw_text = " ".join(filter(None, [c["title"], c["address"], bedroom_marker]))
        listing = Listing(
            source=target["name"], url=c["url"], title=c["title"], raw_text=raw_text,
            city=target["city"], district=c["address"], price_vnd=price_vnd,
            area_m2=area, photos=[c["thumb"]] if c["thumb"] else [],
        )
        result.listings.append(listing)
    return result


def enrich_detail(listing: Listing) -> bool:
    """Дозапрашивает страницу объявления, возвращает True если получилось."""
    html = base.fetch_page(listing.url)
    if html is None:
        return False
    d = parse_detail(html)
    if d["description"]:
        listing.raw_text = f"{listing.raw_text} {d['description']}".strip()
    if d["photos"]:
        listing.photos = d["photos"]
    if d["floor"] is not None:
        listing.floor = d["floor"]
    if d["owner"]:
        listing.owner = d["owner"]
    if d["posted"]:
        listing.posted = d["posted"]
    listing.detailed = True
    return True
