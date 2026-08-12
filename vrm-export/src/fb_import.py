#!/usr/bin/env python3
"""
fb_import.py — разбор постов аренды из Facebook Marketplace и групп.

ПОЧЕМУ РУЧНОЙ ВВОД, А НЕ ПАРСЕР САЙТА
Автоматически тянуть Marketplace нельзя, и это не техническая лень:
  1. robots.txt Facebook запрещает /marketplace/ — санкционированный загрузчик
     отказывается (ROBOTS_DISALLOWED), обходить его я не буду;
  2. официального API на ЧТЕНИЕ чужих объявлений не существует. Marketplace
     Partner Item API умеет только публиковать свой каталог (CREATE/UPDATE/
     DELETE) и выдаётся одобренным партнёрам;
  3. скрейпинг Marketplace нарушает условия использования Facebook, а если
     делать его вашими куками — под угрозой ваш аккаунт.
Поэтому поток такой: вы листаете ленту как обычно, копируете текст поста —
скрипт разбирает его теми же правилами, что и остальные источники, и кладёт
в общий рейтинг. Ровно тот же фильтр, тот же скоринг, тот же отчёт.

ИСПОЛЬЗОВАНИЕ
    python3 fb_import.py posts.txt              # посты через строку '---'
    cat post.txt | python3 fb_import.py -        # из stdin
    python3 fb_import.py --json posts.json       # [{"text":..,"url":..,"photos":[..]}]
Результат дописывается в manual_listings.json и подхватывается сборкой отчёта.
"""
import argparse
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).with_name("manual_listings.json")

# Курс ЦБ РФ — держать в одном месте с patch_v2
VND_TO_RUB = 32.2690 / 10000
USD_TO_RUB = 82.1665

# Районы и кварталы — то, где квартира РЕАЛЬНО находится.
PRIMARY_DISTRICTS = {
    "son tra": "Son Tra", "sơn trà": "Son Tra",
    "ngu hanh son": "Ngu Hanh Son", "ngũ hành sơn": "Ngu Hanh Son",
    "an thuong": "Ngu Hanh Son", "an thượng": "Ngu Hanh Son",
    "my an": "Ngu Hanh Son", "mỹ an": "Ngu Hanh Son",
    "bac my an": "Ngu Hanh Son", "bắc mỹ an": "Ngu Hanh Son",
    "an hai": "Son Tra", "an hải": "Son Tra",
    "phuoc my": "Son Tra", "phước mỹ": "Son Tra",
    "man thai": "Son Tra", "mân thái": "Son Tra",
    "tho quang": "Son Tra", "thọ quang": "Son Tra",
}
# Ориентиры. Пляж рядом — это не адрес: «в 5 минутах от Мỹ Khê» пишут и те,
# кто сдаёт в другом районе. Берём их только если район не нашёлся.
LANDMARKS = {
    "my khe": "Son Tra", "mỹ khê": "Son Tra",
    "pham van dong": "Son Tra", "phạm văn đồng": "Son Tra",
    "non nuoc": "Ngu Hanh Son", "non nước": "Ngu Hanh Son",
}
OFF_DISTRICTS = ["hai chau", "hải châu", "cam le", "cẩm lệ", "lien chieu",
                 "liên chiểu", "thanh khe", "thanh khê", "hoa vang", "hòa vang"]

WASH_IN_UNIT = ["máy giặt riêng", "giặt riêng", "may giat rieng", "giat rieng",
                "máy giặt", "may giat", "washing machine", "washer", "in-unit laundry"]
WASH_SHARED = ["giặt chung", "giat chung", "shared washing", "shared laundry", "chung máy giặt"]
DRYER = ["máy sấy", "may say", "giặt sấy", "giat say", "dryer", "tumble dry"]
DISHWASHER = ["máy rửa bát", "máy rửa chén", "may rua bat", "may rua chen", "dishwasher"]
BRIGHT = ["thoáng", "thoang", "cửa sổ", "cua so", "ban công", "ban cong", "balcony",
          "bright", "airy", "natural light", "sáng", "sea view", "view biển"]

# Прямые синонимы студии. В Дананге студию редко называют "studio":
# пишут "căn hộ mini", "phòng khép kín", "officetel", "chung cư mini".
STUDIO = [r"\bstudio\b", r"\bstudios\b", r"\bofficetel\b",
          r"căn hộ mini", r"can ho mini", r"chung cư mini", r"chung cu mini",
          r"phòng khép kín", r"phong khep kin", r"\bphòng trọ\b", r"\bphong tro\b",
          r"\bktx\b", r"ký túc xá", r"ky tuc xa", r"\bhomestay\b",
          r"open[- ]plan", r"open space", r"\bloft\b",
          r"phòng cho thuê", r"phong cho thue"]

SEP_YES = ["phòng ngủ riêng", "phong ngu rieng", "riêng biệt", "rieng biet",
           "ngủ riêng", "ngu rieng", "separate bedroom", "closed bedroom",
           "phòng khách", "phong khach", "living room"]

# Меньше 45 м² без единого слова про отдельную спальню — почти всегда студия
STUDIO_AREA = 45

NOT_1BR = [r"\b2\s*pn\b", r"\b3\s*pn\b", r"\b2\s*phòng ngủ", r"\b3\s*phòng ngủ",
           r"\b2\s*phong ngu", r"\b3\s*phong ngu", r"\b2\s*bedroom", r"\b3\s*bedroom",
           r"\b2\s*br\b", r"\b3\s*br\b", r"\bstudio\b", r"\bphòng trọ\b", r"\bphong tro\b",
           r"(?<!1-)\b2\s*giường\b", r"(?<!1-)\b2\s*giuong\b"]

# Посуточные ловушки: на Marketplace их заметно больше, чем на досках
NIGHTLY = [r"/\s*night", r"per night", r"/\s*đêm", r"một đêm", r"mỗi đêm",
           r"/\s*ngày", r"per day", r"nightly", r"short term", r"ngắn hạn"]


def _num(s):
    """'8,5' и '8.5' -> 8.5 ; '1.200.000' -> 1200000"""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):      # 1.200.000
        return float(s.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(,\d{3})+", s):       # 1,200,000
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def parse_price_vnd(text):
    """Возвращает (цена_в_донгах, пометка) — пометка объясняет, откуда взялось."""
    t = text.lower()

    # вьетнамское сокращение "8tr5" = 8,5 млн — ловим до общего правила,
    # иначе оно прочтёт только "8" и потеряет полмиллиона
    m = re.search(r"(\d+)\s*tr\s*(\d)\b", t)
    if m:
        return int((float(m.group(1)) + float(m.group(2)) / 10) * 1_000_000), "млн ₫"

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr|củ)\b", t)
    if m:
        return int(_num(m.group(1)) * 1_000_000), "млн ₫"

    m = re.search(r"(\d[\d.,]{5,})\s*(?:vnđ|vnd|đ|d)\b", t)
    if m:
        v = _num(m.group(1))
        if v >= 1_000_000:
            return int(v), "₫"

    m = re.search(r"(?:\$|usd\s*)(\d+(?:[.,]\d+)?)", t)
    if m:
        usd = _num(m.group(1))
        return int(usd * USD_TO_RUB / VND_TO_RUB), f"${usd:.0f}"

    return None, None


def parse_area(text):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|sqm|mét vuông|met vuong)", text, re.I)
    if m:
        return float(_num(m.group(1)))
    m = re.search(r"(?:diện tích|dien tich|area)\D{0,6}(\d+(?:[.,]\d+)?)", text, re.I)
    return float(_num(m.group(1))) if m else None


def parse_district(text):
    """Приоритет: явный район/квартал -> чужой район -> ориентир.
    Если сначала смотреть ориентиры, фраза «рядом с пляжем Мỹ Khê» в посте
    про An Thuong подменит район, и объявление уедет не в ту корзину."""
    t = text.lower()
    for k, v in PRIMARY_DISTRICTS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            return v
    for d in OFF_DISTRICTS:
        if re.search(rf"\b{re.escape(d)}\b", t):
            return "вне целевых"
    for k, v in LANDMARKS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            return v
    return ""


def flags_for(text):
    t = text.lower()
    shared = any(k in t for k in WASH_SHARED)
    return {
        "washing_machine": (not shared) and any(k in t for k in WASH_IN_UNIT),
        "washing_shared": shared,
        "dryer": any(k in t for k in DRYER),
        "dishwasher": any(k in t for k in DISHWASHER),
        "bright": any(k in t for k in BRIGHT),
    }


def score(price_rub, area, flags, sep_confirmed=None, district=""):
    # район теперь вес, а не отсечка
    s = 2.0 if district in ("Son Tra", "Ngu Hanh Son") else (-4.0 if district == "вне целевых" else 0.0)
    if price_rub:
        s += (50000 - price_rub) / 25000 * 3
    if area:
        if area >= 45: s += 1
        elif area >= 40: s += 0.5
        elif area < 35: s -= 1
    if flags["washing_machine"]:
        s += 4
    elif flags["washing_shared"]:
        s -= 2
    if flags["dryer"]:
        s += 1
    if flags["dishwasher"]:
        s += 1.5
    if flags["bright"]:
        s += 1
    if sep_confirmed == "вероятно студия":
        s -= 3
    elif sep_confirmed != "да":
        s -= 2
    return round(s, 2)


def parse_post(text, url="", photos=None):
    """Разбирает один пост. Всегда возвращает результат — даже отсеянный,
    с указанием причины: молча терять объявления хуже, чем показать отказ."""
    photos = photos or []
    price_vnd, price_note = parse_price_vnd(text)
    area = parse_area(text)
    district = parse_district(text)
    fl = flags_for(text)
    price_rub = round(price_vnd * VND_TO_RUB) if price_vnd else None

    reasons = []
    if price_rub is None:
        reasons.append("цена не распознана")
    elif price_vnd < 12_000_000:
        reasons.append(f"дешевле 12 млн ₫ ({price_vnd/1e6:.1f})")
    elif price_vnd > 18_000_000:
        reasons.append(f"дороже 18 млн ₫ ({price_vnd/1e6:.1f})")

    # Планировка. Пост из Facebook — всегда полный текст, поэтому строгое
    # правило про площадь применяем сразу, без скидки на «это список».
    t = text.lower()
    if any(re.search(p, t) for p in STUDIO):
        sep, studio = "студия", True
    elif any(re.search(p, t) for p in NOT_1BR):
        sep, studio = "не 1BR", True
    elif any(k in t for k in SEP_YES):
        sep, studio = "да", False
    elif area is not None and area < STUDIO_AREA:
        # Улика, а не факт: топим в рейтинге, но не выбрасываем
        sep, studio = "вероятно студия", False
    else:
        sep, studio = "не указано", False
    if studio:
        reasons.append(f"планировка: {sep}")   # единственный отсев кроме цены

    nightly = any(re.search(p, t) for p in NIGHTLY)
    warn = []
    if nightly:
        warn.append("похоже на посуточную ставку — проверить, что цена за месяц")
    if price_rub and area and price_rub / area < 450:
        warn.append("подозрительно дёшево для района — проверить на фейк")
    if fl["washing_shared"]:
        warn.append("стиралка общая, не в квартире")

    return {
        "source": "facebook",
        "url": url,
        "title": " ".join(text.split())[:100],
        "district": district if district and district != "вне целевых" else "",
        "price_vnd": price_vnd,
        "price_rub": price_rub,
        "price_note": price_note,
        "area_m2": area,
        "flags": fl,
        "score": score(price_rub, area, fl, sep, district) if price_rub else 0.0,
        "photos": photos,
        "raw_text": " ".join(text.split())[:800],
        "sep": sep,
        "passed": not reasons,
        "reasons": reasons,
        "warnings": warn,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="файл с постами через '---', '-' для stdin, или .json с --json")
    ap.add_argument("--json", action="store_true", help="вход — JSON-список {text,url,photos}")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.src == "-" else Path(args.src).read_text(encoding="utf-8")
    posts = (json.loads(raw) if args.json
             else [{"text": p} for p in re.split(r"^-{3,}$", raw, flags=re.M) if p.strip()])

    parsed = [parse_post(p.get("text", ""), p.get("url", ""), p.get("photos")) for p in posts]

    existing = json.loads(OUT.read_text()) if OUT.exists() else []
    seen = {e["raw_text"][:120] for e in existing}
    fresh = [p for p in parsed if p["raw_text"][:120] not in seen]
    OUT.write_text(json.dumps(existing + fresh, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = [p for p in parsed if p["passed"]]
    print(f"Разобрано постов: {len(parsed)}, новых: {len(fresh)}, прошло фильтр: {len(ok)}\n")
    for p in sorted(parsed, key=lambda x: -x["score"]):
        mark = "✓" if p["passed"] else "✗"
        price = f'{p["price_rub"]:,} ₽'.replace(",", " ") if p["price_rub"] else "цена ?"
        area = f'{p["area_m2"]:g} м²' if p["area_m2"] else "площадь ?"
        print(f'{mark} [{p["score"]:>5}] {p["district"] or "район ?":<14} {area:>10}  {price:>12}  '
              f'{p["title"][:44]}')
        if p["reasons"]:
            print(f'      отсеяно: {"; ".join(p["reasons"])}')
        for w in p["warnings"]:
            print(f'      ⚠ {w}')
    print(f"\nЗаписано в {OUT.name} — сборка отчёта подхватит.")


if __name__ == "__main__":
    main()
