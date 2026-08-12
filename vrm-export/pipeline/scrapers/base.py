#!/usr/bin/env python3
"""
base.py — общие типы и утилиты для скрейперов досок объявлений.

Ключевая идея, которую просит промпт: "0 карточек" — это два РАЗНЫХ
состояния, которые нельзя путать.
  - found=0, broken=False: страница отдалась нормально, но в выдаче
    действительно ничего нет (например, DotProperty дороже вилки —
    это норма, а не поломка).
  - broken=True: либо хост отдал капчу/челлендж (http.BlockedError),
    либо ожидаемая структура карточек не нашлась вовсе (found_raw>0,
    но ни один селектор не сработал — вёрстка сайта поменялась), либо
    сработала защита от "поймал общевьетнамский список вместо районного"
    (см. scrapers/batdongsan.py).
Только это различие даёт логированию по каждому источнику смысл:
"найдено / прошло / отсеяно и почему" (см. PROMPT.md, "Что обязательно
сделать").
"""
import logging
from dataclasses import dataclass, field

from .. import http

log = logging.getLogger("pipeline.scrapers")


@dataclass
class SourceResult:
    name: str
    city: str
    url: str
    found: int = 0                 # карточек получено с сайта (до всех фильтров)
    listings: list = field(default_factory=list)   # core.Listing, detailed=False
    passed: int = 0                # заполняется пайплайном после passes_criteria
    studio_dropped: int = 0        # заполняется пайплайном
    broken: bool = False
    broken_reason: str = ""


def fetch_page(url: str) -> str | None:
    """Возвращает HTML или None (с логом) — исключение наверх не летит,
    чтобы одна упавшая доска не роняла весь прогон."""
    try:
        return http.get_html(url)
    except http.BlockedError as e:
        log.warning("%s: похоже на капчу/челлендж — %s", url, e)
        return None
    except Exception as e:
        log.warning("%s: не удалось получить страницу — %s", url, e)
        return None


# Соседства/индикаторы, которые встречаются ТОЛЬКО в выдаче для Ханоя/ХШМ.
# Если они попались в результатах поиска по Дананг/Нячанг/Вунгтау — сайт
# молча подменил районный фильтр на общевьетнамский список (см. "Ловушка
# Batdongsan" в PROMPT.md). Это специфика batdongsan, но проверка дешёвая
# и безопасная для любого источника, поэтому лежит здесь как общая утилита.
FOREIGN_CITY_MARKERS = [
    "vinhomes smart city", "tây mỗ", "tay mo", "bến nghé", "ben nghe",
    "hà nội", "ha noi", "hồ chí minh", "ho chi minh", "quận 1", "quan 1",
    "cầu giấy", "cau giay", "đống đa", "dong da", "tân bình", "tan binh",
]


def has_foreign_city_marker(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in FOREIGN_CITY_MARKERS)
