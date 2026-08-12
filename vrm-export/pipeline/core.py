#!/usr/bin/env python3
"""
core.py — доменная модель и точка сшивки с прототипом.

Здесь ровно то, чего не было в прототипе (Listing, CRITERIA), плюс вызов
``patch_v2.apply(core)`` — тот самый паттерн, который описан в докстринге
patch_v2.py: "импортируй ПОСЛЕ danang_monitor и вызови apply()". Модуль
``core`` играет роль danang_monitor: определяет Listing и CRITERIA,
патч навешивает passes_criteria / qualitative_flags / score_listing /
Listing.fingerprint.

VND_TO_RUB, который patch_v2.apply() проставляет по умолчанию, — это курс
на 08.08.2026 (см. CBR_VND_TO_RUB в patch_v2.py). Пайплайн перед каждым
прогоном перезаписывает core.VND_TO_RUB актуальным значением из fx.py —
жёстко зашитая константа остаётся только как fallback на случай, если
ЦБ недоступен и в кэше на диске тоже пусто (см. fx.py).
"""
from dataclasses import dataclass, field
from typing import Optional

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import patch_v2  # noqa: E402  — модули прототипа лежат в src/


@dataclass
class Listing:
    source: str
    url: str
    title: str = ""
    raw_text: str = ""          # заголовок + полное описание, для текстовых правил
    city: str = ""
    district: str = ""
    price_vnd: Optional[int] = None
    area_m2: Optional[float] = None
    floor: Optional[int] = None
    owner: str = ""
    phone: str = ""
    zalo: bool = False
    otype: str = "Не проверено"
    posted: str = ""
    note: str = ""
    ask: str = ""
    photos: list = field(default_factory=list)
    checked: bool = False       # карточка открыта и разобрана вручную/детально
    detailed: bool = False      # есть ли полное описание (открывали страницу объявления)
    first_seen: str = ""
    last_seen: str = ""

    # заполняется пайплайном после конвертации по курсу ЦБ
    price_rub: Optional[int] = None
    # заполняется пайплайном по счётчику телефонов между прогонами
    portfolio: bool = False

    def fingerprint(self) -> str:  # переопределяется patch_v2.apply()
        raise RuntimeError("patch_v2.apply(core) не был вызван")


# Жёстких критериев ровно два — цена (в донгах, переводится в рубли) и
# «не студия». Верхняя/нижняя граница в донгах приходит из env, а в рубли
# пересчитывается пайплайном каждый прогон через актуальный курс ЦБ —
# см. pipeline/run.py: refresh_criteria().
CRITERIA = {
    "price_vnd_min": 12_000_000,
    "price_vnd_max": 18_000_000,
    "price_rub_min": 0,
    "price_rub_max": 10**9,
}

VND_TO_RUB = patch_v2.CBR_VND_TO_RUB  # временный дефолт до первого refresh_criteria()

patch_v2.apply(sys.modules[__name__])

# Обязательно после apply(): вешает "спорно"-расширение на
# patch_v2.layout_verdict (см. докстринг pipeline/layout.py про то, почему
# порядок неважен для замыканий, но импортировать всё равно нужно, чтобы
# монтаж вообще произошёл).
from . import layout as _layout  # noqa: E402,F401


def refresh_criteria(vnd_to_rub: float, price_vnd_min: int, price_vnd_max: int) -> None:
    """Пересчитать рублёвые границы критерия по текущему курсу.

    Курс ЦБ РФ котирует донг НАПРЯМУЮ (10 000 ₫ = X ₽) — см. patch_v2.py,
    FIX 1. Кросс-курс через доллар здесь не участвует.
    """
    global VND_TO_RUB
    VND_TO_RUB = vnd_to_rub
    CRITERIA["price_vnd_min"] = price_vnd_min
    CRITERIA["price_vnd_max"] = price_vnd_max
    CRITERIA["price_rub_min"] = round(price_vnd_min * vnd_to_rub)
    CRITERIA["price_rub_max"] = round(price_vnd_max * vnd_to_rub)


def price_to_rub(price_vnd: Optional[int]) -> Optional[int]:
    if price_vnd is None:
        return None
    return round(price_vnd * VND_TO_RUB)
