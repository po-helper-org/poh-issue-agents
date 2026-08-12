#!/usr/bin/env python3
"""
fx.py — курс ЦБ РФ, донг напрямую (см. patch_v2.py FIX 1).

ЦБ публикует донг с номиналом 10 000 (Value = рублей за 10 000 донгов).
Опасность — читать это как обычный курс "за 1 единицу" и по ошибке лезть
в кросс-курс через доллар: первая версия прототипа так и делала и
занижала рубль на 2,9%. Здесь VND_TO_RUB = Value / Nominal, без USD
на промежуточном шаге.

Кэш на диске переживает недоступность ЦБ: если запрос не удался,
используем последнее сохранённое значение и явно логируем это —
молча ехать на курсе недельной давности нельзя, это стоит увидеть в логах.
"""
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from . import http

log = logging.getLogger("pipeline.fx")

DEFAULT_CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
# Резервное значение, если ЦБ недоступен И на диске ещё нет кэша —
# курс на 08.08.2026 из первого реального прогона (patch_v2.py).
FALLBACK_VND_TO_RUB = 32.2690 / 10000
FALLBACK_USD_TO_RUB = 82.1665


def _cache_path(data_dir: Path) -> Path:
    return Path(data_dir) / "fx_cache.json"


def _parse_cbr_xml(raw_bytes: bytes) -> dict:
    root = ET.fromstring(raw_bytes.decode("windows-1251"))
    out = {}
    for node in root.findall("Valute"):
        code = node.findtext("CharCode")
        if code not in ("VND", "USD"):
            continue
        nominal = float(node.findtext("Nominal").replace(",", "."))
        value = float(node.findtext("Value").replace(",", "."))
        out[code] = value / nominal
    return out


def fetch_rates(cbr_url: str, data_dir: Path) -> dict:
    """Возвращает {'vnd_to_rub':.., 'usd_to_rub':.., 'date':.., 'stale':bool}.

    stale=True значит "ЦБ не ответил, это последнее известное значение
    с диска (или совсем зашитый фолбэк, если и диска ещё не было)".
    """
    cache = _cache_path(data_dir)
    try:
        resp = http.get(cbr_url)
        resp.raise_for_status()
        rates = _parse_cbr_xml(resp.content)
        if "VND" not in rates:
            raise ValueError("в ответе ЦБ нет донга (VND)")
        result = {
            "vnd_to_rub": rates["VND"],
            "usd_to_rub": rates.get("USD", FALLBACK_USD_TO_RUB),
            "date": _today_from_xml(resp.content),
            "stale": False,
        }
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        return result
    except Exception as e:
        log.warning("ЦБ недоступен (%s), беру курс из кэша", e)
        if cache.exists():
            cached = json.loads(cache.read_text(encoding="utf-8"))
            cached["stale"] = True
            return cached
        log.warning("Кэша курса на диске тоже нет — использую зашитый резерв от 08.08.2026")
        return {"vnd_to_rub": FALLBACK_VND_TO_RUB, "usd_to_rub": FALLBACK_USD_TO_RUB,
                "date": "08.08.2026 (резерв)", "stale": True}


def _today_from_xml(raw_bytes: bytes) -> str:
    try:
        return ET.fromstring(raw_bytes.decode("windows-1251")).get("Date", "")
    except Exception:
        return ""
