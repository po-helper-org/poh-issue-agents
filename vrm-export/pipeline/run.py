#!/usr/bin/env python3
"""
run.py — оркестратор одного прогона: обошли доски -> отфильтровали и
оценили -> вмержили Facebook-импорт -> обновили состояние на диске ->
скачали фото -> собрали отчёт -> заархивировали -> отправили сводку.

Логирование по каждому источнику ("найдено / прошло / отсеяно и почему")
и различение "пусто, потому что не подошло" от "поломка вёрстки" — прямое
требование PROMPT.md; оба состояния видны в SourceResult (см.
scrapers/base.py) и в логах ниже.
"""
import datetime
import logging
from dataclasses import asdict

from . import core, districts, fx, importer, layout, photos, report, storage, telegram
from .config import Config
from .core import Listing
from .scrapers import TARGETS
from .scrapers.base import SourceResult

log = logging.getLogger("pipeline.run")

MAX_DETAIL_FETCHES_PER_TARGET = 40   # чтобы один прогон не растянулся на часы
STALE_DAYS = 14                       # сколько дней держим объявление в рейтинге без повторного подтверждения
MAX_PHOTO_LISTINGS = 200              # верхняя граница на скачивание фото за прогон


def _classify(listing: Listing) -> str:
    """passed / price / studio / area_hygiene — для лога и телеметрии
    источника. Не меняет поведение passes_criteria, только объясняет его."""
    if listing.price_rub is None:
        return "price"
    if not (core.CRITERIA["price_rub_min"] <= listing.price_rub <= core.CRITERIA["price_rub_max"]):
        return "price"
    if listing.area_m2 is not None and listing.area_m2 < 15:
        return "area_hygiene"
    text = (listing.title + " " + listing.raw_text).lower()
    if layout.patch_v2.layout_verdict(text, listing.area_m2, listing.detailed) == "studio":
        return "studio"
    return "passed"


def collect_all(fx_rates: dict) -> list:
    """Возвращает список SourceResult — по одному на каждый URL-таргет."""
    results = []
    for target in TARGETS:
        engine = target["engine"]
        try:
            result = engine.scrape(target, fx_rates)
        except Exception as e:  # одна упавшая доска не должна ронять весь прогон
            log.exception("%s: необработанное исключение скрейпера", target["name"])
            result = SourceResult(name=target["name"], city=target["city"], url=target["url"],
                                   broken=True, broken_reason=f"исключение: {e}")
        results.append(result)

        if result.broken:
            log.error("ИСТОЧНИК СЛОМАН: %s — %s", result.name, result.broken_reason)
            continue

        # Район — из адреса, не из ориентира (см. pipeline/districts.py)
        for listing in result.listings:
            listing.district = districts.normalize_district(
                address=listing.district, title=listing.title, raw_text=listing.raw_text) or listing.district
            listing.price_rub = core.price_to_rub(listing.price_vnd)

        # Детальный заход — только для тех, кто хоть примерно похож на бюджет
        # (или у кого вообще не распознали цену на списке — стоит проверить),
        # и с потолком на источник, чтобы не растягивать прогон бесконечно.
        margin = 0.5
        lo = core.CRITERIA["price_vnd_min"] * (1 - margin)
        hi = core.CRITERIA["price_vnd_max"] * (1 + margin)
        candidates = [ln for ln in result.listings
                      if ln.price_vnd is None or lo <= ln.price_vnd <= hi]
        fetched = 0
        for listing in candidates:
            if fetched >= MAX_DETAIL_FETCHES_PER_TARGET:
                log.info("%s: лимит детальных заходов (%d) исчерпан, остальное — по данным со списка",
                         target["name"], MAX_DETAIL_FETCHES_PER_TARGET)
                break
            try:
                if engine.enrich_detail(listing):
                    fetched += 1
                    listing.district = districts.normalize_district(
                        address=listing.district, title=listing.title,
                        raw_text=listing.raw_text) or listing.district
            except Exception as e:
                log.info("%s: не удалось дозапросить деталку %s: %s", target["name"], listing.url, e)

        found = len(result.listings)
        passed = sum(1 for ln in result.listings if _classify(ln) == "passed")
        studios = sum(1 for ln in result.listings if _classify(ln) == "studio")
        log.info("%s: найдено %d, прошло %d, студий отсеяно %d", result.name, found, passed, studios)
        result.passed = passed
        result.studio_dropped = studios
    return results


def _listing_to_record(listing: Listing, first_seen: str, today: str) -> dict:
    d = asdict(listing)
    d["first_seen"] = first_seen or today
    d["last_seen"] = today
    return d


def _record_to_listing(rec: dict) -> Listing:
    fields = {k: v for k, v in rec.items() if k in Listing.__dataclass_fields__}
    return Listing(**fields)


def merge_into_state(store: storage.Storage, results: list, manual_listings: list, today: str):
    """Обновляет seen_listings.json и счётчик телефонов. Возвращает
    (все_живые_Listing, число_новых_за_прогон)."""
    seen = store.load_seen()
    phone_counts = store.load_phone_counts()
    new_count = 0

    def upsert(listing: Listing):
        nonlocal new_count
        fp = listing.fingerprint()
        prev = seen.get(fp)
        first_seen = prev["first_seen"] if prev else today
        if not prev:
            new_count += 1
        seen[fp] = _listing_to_record(listing, first_seen, today)
        if listing.phone:
            phone_counts[listing.phone] = phone_counts.get(listing.phone, 0) + (0 if prev else 1)

    for result in results:
        if result.broken:
            continue
        for listing in result.listings:
            upsert(listing)
    for listing in manual_listings:
        upsert(listing)

    store.save_seen(seen)
    store.save_phone_counts(phone_counts)

    # Свежесть: объявление, которое не подтверждалось STALE_DAYS дней ни
    # одним прогоном, из живого рейтинга убираем (в базе для дедупа остаётся).
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=STALE_DAYS)).isoformat()
    live = []
    for rec in seen.values():
        if rec.get("last_seen", today) >= cutoff:
            listing = _record_to_listing(rec)
            listing.portfolio = phone_counts.get(listing.phone, 0) >= 3 if listing.phone else False
            live.append(listing)
    return live, new_count


def build_row(listing: Listing, flags: dict, score: float, data_dir) -> dict:
    text = (listing.title + " " + listing.raw_text)
    sep = layout.sep_label(text, listing.area_m2, listing.detailed)
    note = listing.note
    contra = layout.contradiction_note(text, listing.detailed)
    if contra:
        note = (note + " " + contra).strip()
    level = "A" if (flags.get("washing_machine") and flags.get("dryer") and flags.get("dishwasher")) \
        else ("B" if flags.get("washing_machine") else "?")
    embedded_photos = photos.embed_photos(listing.url, listing.photos, data_dir)
    return dict(
        street=listing.title or listing.district or "Без названия",
        district=listing.district, city=listing.city,
        area=listing.area_m2, rub=listing.price_rub or 0, vnd=listing.price_vnd or 0,
        score=score, floor=listing.floor, level=level, sep=sep,
        wash=bool(flags.get("washing_machine")), dryer=bool(flags.get("dryer")),
        dish=bool(flags.get("dishwasher")), bright=bool(flags.get("bright")),
        owner=listing.owner, phone=listing.phone, zalo=listing.zalo, otype=listing.otype,
        posted=listing.posted, portfolio=listing.portfolio, checked=listing.checked,
        note=note, ask=listing.ask, photos=embedded_photos,
        src=listing.source, url=listing.url,
    )


CITY_ORDER = ["Дананг", "Нячанг", "Вунгтау"]


def run_once(cfg: Config) -> dict:
    """Один полный прогон. Возвращает сводку (для ответа /run и логов)."""
    store = storage.Storage(cfg.data_dir)
    today = datetime.date.today().isoformat()
    now_label = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    fx_rates = fx.fetch_rates(cfg.cbr_url, cfg.data_dir)
    core.refresh_criteria(fx_rates["vnd_to_rub"], cfg.price_min_vnd, cfg.price_max_vnd)
    layout.patch_v2.STUDIO_AREA = cfg.studio_area
    if fx_rates.get("stale"):
        log.warning("Курс ЦБ устарел (%s) — используется последнее известное значение", fx_rates.get("date"))

    results = collect_all(fx_rates)
    for result in results:
        for listing in result.listings:
            listing.checked = listing.detailed

    manual_raw = store.load_manual()
    manual_listings = []
    for entry in manual_raw:
        try:
            manual_listings.append(importer.manual_to_listing(entry))
        except Exception as e:
            log.warning("не удалось разобрать сохранённый Facebook-пост: %s", e)

    live, new_count = merge_into_state(store, results, manual_listings, today)

    # Курс мог обновиться с момента первого захвата — пересчитываем рубли
    # по сегодняшнему курсу перед тем как проверять критерии и считать score.
    ranked = []
    for listing in live:
        listing.price_rub = core.price_to_rub(listing.price_vnd)
        if not core.passes_criteria(listing):
            continue
        flags = core.qualitative_flags(listing)
        score = core.score_listing(listing, flags)
        ranked.append((listing, flags, score))
    ranked.sort(key=lambda t: t[2], reverse=True)

    rows = []
    for listing, flags, score in ranked[:MAX_PHOTO_LISTINGS]:
        rows.append(build_row(listing, flags, score, cfg.data_dir))
    for listing, flags, score in ranked[MAX_PHOTO_LISTINGS:]:
        # За пределами MAX_PHOTO_LISTINGS фото не качаем — источник и так внизу
        # списка, а на диск и в отчёт идут те, что реально кто-то увидит.
        r = build_row(listing, flags, score, cfg.data_dir)
        r["photos"] = []
        rows.append(r)

    source_stats = [(r.name, r.found, r.passed) for r in results]
    total_fb = len(manual_raw)
    fb_passed = sum(1 for ln in manual_listings if core.passes_criteria(ln))
    if manual_raw:
        source_stats.append(("Facebook (ручной импорт)", total_fb, fb_passed))
    broken = [r.name for r in results if r.broken]
    total_collected = sum(r.found for r in results) + total_fb

    cities = sorted({r["city"] for r in rows} or {t["city"] for t in TARGETS}, key=lambda c: CITY_ORDER.index(c) if c in CITY_ORDER else 99)
    title = " + ".join(cities) + " · euro-1BR"
    criteria_note = (f"Бюджет <b>{cfg.price_min_vnd/1e6:.0f}–{cfg.price_max_vnd/1e6:.0f} млн ₫</b> "
                      f"· не студия · площадь от 15 м²")
    fx_note = (f"10 000 ₫ = {fx_rates['vnd_to_rub']*10000:.4f} ₽ · 1 $ = {fx_rates['usd_to_rub']:.4f} ₽"
               + (" (устарел)" if fx_rates.get("stale") else ""))

    html = report.build_html(
        rows=rows, source_stats=source_stats, new_count=new_count,
        total_collected=total_collected, fx_note=fx_note, run_label=now_label,
        title=title, criteria_note=criteria_note, broken_count=len(broken),
    )
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    store.save_report(html, stamp)
    store.save_ranking(rows)

    summary = dict(collected=total_collected, passed=len(rows), new=new_count,
                    studio_dropped=sum(r.studio_dropped for r in results),
                    broken=broken, report_stamp=stamp)

    text = telegram.build_summary_text(
        collected=summary["collected"], passed=summary["passed"],
        studio_dropped=summary["studio_dropped"], top=rows,
        report_url=cfg.public_url.rstrip("/") + "/", broken_sources=broken,
    )
    telegram.send_summary(token=cfg.telegram_bot_token, chat_id=cfg.telegram_chat_id, text=text)
    log.info("Прогон завершён: %s", summary)
    return summary
