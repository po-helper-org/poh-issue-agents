#!/usr/bin/env python3
"""
layout.py — надстройка над patch_v2.layout_verdict: случай «противоречие».

Реальный пример, который её потребовал: объявление «CĂN HỘ MINI» на
Nguyễn Văn Thoại — заголовок формально студийный маркер, а в описании
раздельно идут phòng khách (гостиная) и phòng ngủ (спальня). Базовое
правило patch_v2 отсекает по STUDIO-маркеру в тексте ещё до того, как
успевает посмотреть на остальное описание — и теряет живой вариант.

Здесь это не отсев, а «спорно»: не подтверждаем и не режем, а всплывает
первым вопросом владельцу в карточке. На скоринг влияет как unconfirmed
(-2) — доказательств нет ни в одну, ни в другую сторону, топить сильнее
studio-эвристикой (-3) было бы неправильно: тут ровно 50/50, а не «почти
наверняка студия».

ВАЖНО про монтаж: patch_v2.passes_criteria/qualitative_flags — это
замыкания, определённые внутри patch_v2.apply(), которые вызывают имя
`layout_verdict` НЕ как локальную переменную, а через глобальное
пространство имён модуля patch_v2 — Python резолвит его в момент вызова,
а не в момент определения. Поэтому достаточно подменить атрибут
`patch_v2.layout_verdict`, не трогая сам файл: passes_criteria и
qualitative_flags начинают использовать расширенную версию прозрачно.
Оригинальный файл patch_v2.py остаётся нетронутым — вместе с комментариями,
которые фиксируют историю багов.
"""
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import patch_v2  # noqa: E402

_base_layout_verdict = patch_v2.layout_verdict

LIVING_MARKERS = ["phòng khách", "phong khach", "living room"]
BEDROOM_MARKERS = ["phòng ngủ", "phong ngu", "bedroom"]


def is_contradiction(text: str, detailed: bool) -> bool:
    """True, если заголовок+описание содержат STUDIO-маркер, но при этом
    в тексте раздельно упомянуты гостиная и спальня. Только для открытых
    карточек: на странице списка текста мало, случайное совпадение слов
    там ничего не доказывает."""
    if not detailed:
        return False
    t = text.lower()
    if not any(re.search(p, t) for p in patch_v2.STUDIO):
        return False  # это либо не студия вовсе, либо отсев по NOT_1BR (2PN и т.п.)
    return any(k in t for k in LIVING_MARKERS) and any(k in t for k in BEDROOM_MARKERS)


def layout_verdict(text: str, area, detailed: bool) -> str:
    """Совместимая по контракту замена patch_v2.layout_verdict: тот же
    набор строк на выходе (studio/likely_studio/ok/unconfirmed), поэтому
    passes_criteria и score_listing продолжают работать без изменений.
    Единственная разница — противоречие превращает 'studio' в 'unconfirmed'
    вместо жёсткого отсева."""
    verdict = _base_layout_verdict(text, area, detailed)
    if verdict == "studio" and is_contradiction(text, detailed):
        return "unconfirmed"
    return verdict


def install() -> None:
    patch_v2.layout_verdict = layout_verdict


install()


def sep_label(text: str, area, detailed: bool) -> str:
    """Человекочитаемая метка планировки для отчёта. Комбинирует базовый
    вердикт (после патча — с учётом противоречия) с отдельной пометкой
    'спорно', которая нужна только для отображения и заметки владельцу,
    но не должна влиять на скоринг иначе, чем unconfirmed (см. докстринг
    модуля)."""
    if is_contradiction(text, detailed):
        return "спорно"
    verdict = patch_v2.layout_verdict(text, area, detailed)
    return {"ok": "да", "likely_studio": "вероятно студия", "unconfirmed": "не указано"}.get(verdict, "не указано")


def contradiction_note(text: str, detailed: bool) -> str:
    if is_contradiction(text, detailed):
        return ("Заголовок похож на студию, но в описании отдельно указаны "
                "гостиная и спальня — уточните у владельца в первую очередь.")
    return ""
