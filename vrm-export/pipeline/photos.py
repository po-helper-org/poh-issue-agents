#!/usr/bin/env python3
"""
photos.py — скачивание и вшивание фотографий, логика перенесена из
src/fetch_assets.py в автоматический пайплайн (там она была ручным
постпроцессингом offline-отчёта; здесь встроена прямо в сборку).

ПОЧЕМУ ВШИВАТЬ, А НЕ ССЫЛАТЬСЯ. На Render у процесса есть обычный выход
в интернет (в отличие от прежнего облака-прототипа, где домены объявлений
были недоступны), но просмотрщик отчёта у пользователя всё равно не
подгружает внешние картинки — только вшитые через data:-URL. Проверено
на его стороне 12.08.2026.

Referer ставим на страницу объявления: многие вьетнамские хосты режут
хотлинк именно по нему (см. src/fetch_assets.py, тот же приём).

Дедупликация — по URL картинки, на диске в DATA_DIR/photos_cache: одно и
то же фото не скачивается повторно между прогонами.
"""
import base64
import hashlib
import io
import logging
from pathlib import Path

from PIL import Image

from . import http

log = logging.getLogger("pipeline.photos")

MAX_WIDTH = 1400
JPEG_QUALITY = 82
MAX_PHOTOS_PER_LISTING = 6


def _cache_dir(data_dir) -> Path:
    d = Path(data_dir) / "photos_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _shrink(data: bytes, max_w: int = MAX_WIDTH):
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "P", "LA"):
        im = im.convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def fetch_and_cache(photo_url: str, referer: str, data_dir) -> bytes | None:
    """Возвращает ужатые JPEG-байты (из кэша на диске или
    свежескачанные), либо None если скачать/декодировать не удалось —
    такое фото просто пропускаем, отчёт не должен падать из-за одной битой
    ссылки."""
    cache_dir = _cache_dir(data_dir)
    path = cache_dir / f"{_cache_key(photo_url)}.jpg"
    if path.exists():
        return path.read_bytes()
    try:
        raw, _ctype = http.get_bytes(photo_url, referer=referer)
        jpg = _shrink(raw)
    except Exception as e:
        log.info("фото не скачалось %s: %s", photo_url, e)
        return None
    path.write_bytes(jpg)
    return jpg


def embed_photos(listing_url: str, photo_urls: list, data_dir,
                  limit: int = MAX_PHOTOS_PER_LISTING) -> list:
    """Список исходных URL фотографий -> список data:-URL для отчёта.
    Битые фото молча выпадают из списка (не роняют весь прогон)."""
    out = []
    for u in (photo_urls or [])[:limit]:
        jpg = fetch_and_cache(u, listing_url, data_dir)
        if jpg:
            out.append("data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii"))
    return out
