#!/usr/bin/env python3
"""
build_report.py — ranking.json -> самодостаточная HTML-страница
с сортировкой по столбцам, фильтрами, галереей фото и карточкой владельца.

    python3 build_report.py            # -> report.html

ФОТО. Картинки подставляются ссылками на хосты объявлений (alonhadat.com.vn,
cdn.chotot.com). Скачать и зашить их в base64 из облачного контейнера нельзя —
прокси эти домены режет. Значит: если сайт закроет хотлинк, картинки отвалятся.
На этот случай у каждой <img> есть onerror-заглушка со ссылкой на карточку.
"""
import json
from pathlib import Path

import render_html as rh

RUN_DATE = "12.08.2026 · Дананг + Нячанг · 12–18 млн ₫"
NEW_COUNT = 16   # новых объявлений за этот прогон (дедуп по seen_listings.json)
FX_NOTE = "ЦБ РФ · 10 000 ₫ = 32,2690 ₽ · 1 $ = 82,1665 ₽ · диапазон 38 723 – 58 084 ₽"

SOURCE_STATS = [
    ("Дананг · Batdongsan",     20,  4),
    ("Дананг · Nhà Tốt",        22,  3),
    ("Дананг · FazWaz",        27,  4),
    ("Дананг · Alonhadat",       9,  2),
    ("Дананг · DotProperty",     7,  1),
    ("Дананг · Mogi",           30,  0),
    ("Нячанг · Nhà Tốt",        20,  1),
    ("Нячанг · Mogi",           15,  1),
    ("Вунгтау · Mogi",          15,  0),
    ("Далат · Mogi",            12,  0),
    ("Фукуок · Nhà Tốt",         1,  0),
]

A = "https://alonhadat.com.vn/files/properties"

ENRICH_BY_URL = {c["url"]: c for c in json.loads(
    (Path(__file__).with_name("run_cards.json")).read_text(encoding="utf-8"))}



SRC_LABEL = {}   # источники в ranking.json уже подписаны по-человечески


def enrich_for(url):
    """Карточки этого прогона лежат в run_cards.json — ключ точный URL,
    а не подстрока: подстрочный поиск уже путал похожие объявления."""
    c = ENRICH_BY_URL.get(url)
    if not c:
        return dict(street="", floor=None, level="?", sep="не указано", checked=False,
                    owner="", phone="", zalo=False, otype="Не проверено", posted="",
                    portfolio=False, note="", ask="", photos=[])
    # Уровень A — полный комплект; B — стиралка есть, но не всё
    lvl = "A" if (c["wash"] and c["dry"] and c["dish"]) else ("B" if c["wash"] else "?")
    return dict(street=c["title"], floor=c["floor"], level=lvl, sep=c["layout"],
                checked=c["checked"], owner=c["owner"], phone=c["phone"], zalo=c["zalo"],
                otype=c["otype"], posted=c["posted"], portfolio=c["portfolio"],
                note=c["note"], ask=c["ask"], photos=c["photos"])


MANUAL = Path(__file__).with_name("manual_listings.json")


def manual_rows():
    """Посты из Facebook, разобранные fb_import.py. Берём только прошедшие
    фильтр; предупреждения парсера переносим в заметку, чтобы посуточная
    ставка или общая стиралка не потерялись при просмотре."""
    if not MANUAL.exists():
        return []
    out = []
    for e in json.loads(MANUAL.read_text(encoding="utf-8")):
        if not e.get("passed"):
            continue
        f = e["flags"]
        head = e["title"].split(",")[0][:44].strip()
        note = e["raw_text"][:150]
        if e.get("warnings"):
            note = "⚠ " + " · ".join(e["warnings"]) + ". " + note
        out.append({
            "street": head or "Пост Facebook", "district": e["district"], "city": "Дананг",
            "area": e["area_m2"], "rub": int(e["price_rub"]), "vnd": e["price_vnd"],
            "score": e["score"], "floor": None, "level": "?",
            "sep": e.get("sep", "не указано"),
            "wash": f["washing_machine"], "dryer": f["dryer"],
            "dish": f["dishwasher"], "bright": f["bright"],
            "owner": "", "phone": "", "zalo": False,
            "otype": "Facebook — писать в личные сообщения", "posted": "",
            "portfolio": False, "checked": False,
            "note": note, "ask": "", "photos": e.get("photos") or [],
            "src": "Facebook", "url": e.get("url", ""),
        })
    return out


def build(ranking_path="ranking.json", out="report.html"):
    rows = []
    SEPMAP = {"ok": "да", "likely_studio": "вероятно студия", "unconfirmed": "не указано"}
    for e in json.loads(Path(ranking_path).read_text()):
        x, f = enrich_for(e["url"]), e["flags"]
        # Планировку берём из вердикта парсера, а не из ручной таблицы:
        # иначе ENRICH и скоринг разъедутся и в отчёте будет «да» у того,
        # кого скоринг считает студией.
        sep_from_flags = x["sep"]
        rows.append({
            "street": x["street"] or e["title"][:40], "district": e["district"],
            "city": e.get("city", "Дананг"),
            "area": e["area_m2"], "rub": int(e["price_rub"]), "vnd": e["price_vnd"],
            "score": e["score"], "floor": x["floor"], "level": x["level"], "sep": sep_from_flags,
            "wash": bool(f.get("washing_machine")), "dryer": bool(f.get("dryer")),
            "dish": bool(f.get("dishwasher")), "bright": bool(f.get("bright")),
            "owner": x["owner"], "phone": x["phone"], "zalo": x["zalo"], "otype": x["otype"],
            "posted": x["posted"], "portfolio": x["portfolio"], "checked": x["checked"],
            "note": x["note"], "ask": x["ask"], "photos": x["photos"],
            "src": SRC_LABEL.get(e["source"], e["source"]), "url": e["url"],
        })
    fb = manual_rows()
    rows.extend(fb)
    rows.sort(key=lambda r: r["score"], reverse=True)
    stats = list(SOURCE_STATS)
    if MANUAL.exists():
        total_fb = len(json.loads(MANUAL.read_text(encoding="utf-8")))
        stats.append(("Facebook (ручной импорт)", total_fb, len(fb)))

    n_ph = sum(1 for r in rows if r["photos"])
    html = (TEMPLATE.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
                    .replace("__RUNDATE__", RUN_DATE).replace("__FX__", FX_NOTE)
                    .replace("__SOURCES__", json.dumps(SOURCE_STATS, ensure_ascii=False))
                    .replace("__NWASH__", str(sum(r["wash"] for r in rows)))
                    .replace("__NTOT__", str(len(rows)))
                    .replace("__NEW__", str(NEW_COUNT))
                    .replace("__HEAD__", rh.head_html())
                    .replace("__BODY__", rh.body_html(rows))
                    .replace("__SRCTBL__", rh.srctbl_html(stats))
                    .replace("__COUNT__", rh.count_html(len(rows), len(rows), 178 + (len(fb) and total_fb))))

    # манифест для fetch_assets.py — скачивание фото на машине пользователя
    manifest = [{"id": Path(r["url"]).stem.split("-")[-1] or str(i),
                 "listing_url": r["url"], "photos": r["photos"]}
                for i, r in enumerate(rows) if r["photos"]]
    Path(out).with_name("photos_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    Path(out).write_text(html, encoding="utf-8")
    print(f"{out}: {len(rows)} объявлений, {n_ph} с фото, "
          f"{sum(len(r['photos']) for r in rows)} снимков")


TEMPLATE = Path(__file__).with_name("template.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    build()
