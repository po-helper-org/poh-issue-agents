#!/usr/bin/env python3
"""
importer.py — эндпоинт-обвязка над src/fb_import.py.parse_post().

Facebook Marketplace не парсим (robots.txt запрещает /marketplace/,
официального read-API нет, скрейпинг рискует аккаунтом — см. докстринг
fb_import.py). Вместо этого POST /import с токеном принимает JSON
[{text, url, photos}], собранный расширением (например, Claude in Chrome)
в браузере пользователя, и разбирает теми же правилами, что и остальные
источники — тем же parse_post(), которым пользуется CLI fb_import.py.
"""
import hashlib
import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import fb_import  # noqa: E402

from .core import Listing  # noqa: E402

log = logging.getLogger("pipeline.importer")


def import_posts(store, posts: list) -> dict:
    """posts — [{text, url?, photos?}, ...]. Дописывает в manual_listings.json
    с той же дедупликацией по первым 120 символам текста, что и CLI-версия."""
    existing = store.load_manual()
    seen = {e["raw_text"][:120] for e in existing}
    parsed = [fb_import.parse_post(p.get("text", ""), p.get("url", ""), p.get("photos")) for p in posts]
    fresh = [p for p in parsed if p["raw_text"][:120] not in seen]
    store.save_manual(existing + fresh)
    return dict(received=len(posts), new=len(fresh), passed=sum(1 for p in fresh if p["passed"]))


def manual_to_listing(entry: dict) -> Listing:
    url = entry.get("url") or "fb-post:" + hashlib.sha256(
        entry.get("raw_text", "").encode("utf-8")).hexdigest()[:16]
    return Listing(
        source="Facebook", url=url,
        title=entry.get("title") or "Пост Facebook",
        raw_text=entry.get("raw_text", ""),
        city="Дананг",  # fb_import.py разбирает районы только для Дананга
        district=entry.get("district", ""),
        price_vnd=entry.get("price_vnd"),
        area_m2=entry.get("area_m2"),
        photos=entry.get("photos") or [],
        detailed=True,  # пост из Facebook — всегда полный текст
        checked=False,
        otype="Facebook — писать в личные сообщения",
    )
