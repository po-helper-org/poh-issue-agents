#!/usr/bin/env python3
"""
districts.py — нормализация района для отображения, поверх src/fb_import.py.

Правила уже реализованы в fb_import.parse_district() и используются без
изменений:
  1. границы слов (\\bXXX\\b), а не substring — иначе "an hai" находится
     внутри "quan hai chau" (Hải Châu) и протаскивает не-целевой район
     в целевые (см. TARGET_DISTRICTS trap в patch_v2.py и тест
     tests/test_layout.py::test_district_word_boundary_trap);
  2. приоритет: явный район из адреса -> чужой район -> ориентир по
     тексту. "В 5 минутах от пляжа Мỹ Khê" пишут и те, кто сдаёт в другом
     конце города — ориентир смотрим, только если явного района не нашли.

Здесь только выбор ИСТОЧНИКА текста: сначала структурированный адрес с
карточки (самый надёжный), и только если сайт его не дал — заголовок
плюс описание целиком.

ВАЖНО: нормализованное значение (например, "вне целевых") кладётся в
Listing.district только для отображения/группировки в отчёте. Regex-проверка
в patch_v2.district_weight() ищет вьетнамские названия районов в
district+title+raw_text — поэтому raw_text должен по-прежнему содержать
исходную строку адреса на вьетнамском, иначе штраф/вес по району потеряется
после нормализации. Скрейперы обязаны класть адрес в raw_text, а не только
сюда.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fb_import import parse_district  # noqa: E402


def normalize_district(address: str = "", title: str = "", raw_text: str = "") -> str:
    for text in (address, f"{title} {raw_text}"):
        if text and text.strip():
            d = parse_district(text)
            if d:
                return d
    return ""
