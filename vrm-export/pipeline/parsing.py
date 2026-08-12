#!/usr/bin/env python3
"""
parsing.py — тонкие обёртки над регулярками из src/fb_import.py.

fb_import.py уже содержит обкатанные на реальных объявлениях парсеры цены
("8tr5", "12.000.000đ", "$380") и площади ("45m2", "diện tích 48"). Вместо
дублирования регулярок в новом коде — импортируем их напрямую: одна
точка правды на оба потребителя (ручной импорт из Facebook и автоматические
скрейперы).
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fb_import import parse_price_vnd, parse_area  # noqa: E402,F401

__all__ = ["parse_price_vnd", "parse_area"]
