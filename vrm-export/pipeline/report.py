#!/usr/bin/env python3
"""
report.py — сборка отчёта для автоматического пайплайна. Тот же приём, что
в src/build_report.py (шаблон + серверный рендер таблицы из
src/render_html.py, чтобы таблица была в HTML без JS — см. докстринг
render_html.py), но данные не зашиты в файл, а приходят из текущего
прогона. src/build_report.py и src/template.html не переписаны — сюда
перенесена только сборка, вёрстка и js в template.html остались как были
(там же несколько демонстрационных чисел из прототипа превращены в
плейсхолдеры __TITLE__/__CRITERIA__/__COLLECTED__/__NSRC__/__NERR__, без
переписывания остального).
"""
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import render_html as rh  # noqa: E402

TEMPLATE_PATH = SRC_DIR / "template.html"


def build_html(*, rows: list, source_stats: list, new_count: int,
                total_collected: int, fx_note: str, run_label: str,
                title: str, criteria_note: str, broken_count: int = 0) -> str:
    """rows — список словарей строго той же формы, что в src/build_report.py
    (street/district/city/area/rub/vnd/score/floor/level/sep/wash/dryer/
    dish/bright/owner/phone/zalo/otype/posted/portfolio/checked/note/ask/
    photos/src/url) — этот контракт совпадает 1-в-1 с rowHTML() в
    template.html, иначе после первого клика по фильтру строки "прыгнут"
    (см. докстринг render_html.py)."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    n_wash = sum(1 for r in rows if r["wash"])
    n_tot = len(rows)
    html = (template
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__RUNDATE__", run_label)
            .replace("__TITLE__", title)
            .replace("__CRITERIA__", criteria_note)
            .replace("__FX__", fx_note)
            .replace("__SOURCES__", json.dumps(source_stats, ensure_ascii=False))
            .replace("__NWASH__", str(n_wash))
            .replace("__NTOT__", str(n_tot))
            .replace("__NEW__", str(new_count))
            .replace("__COLLECTED__", str(total_collected))
            .replace("__NSRC__", str(len(source_stats)))
            .replace("__NERR__", str(broken_count))
            .replace("__HEAD__", rh.head_html())
            .replace("__BODY__", rh.body_html(rows))
            .replace("__SRCTBL__", rh.srctbl_html(source_stats))
            .replace("__COUNT__", rh.count_html(n_tot, n_tot, total_collected)))
    return html
