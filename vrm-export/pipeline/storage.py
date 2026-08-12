#!/usr/bin/env python3
"""
storage.py — всё, что переживает рестарт процесса, на диске под DATA_DIR.

Render Cron Job не может примонтировать постоянный диск (см. render.yaml) —
поэтому система живёт как Web Service с диском, а этот модуль — единственное
место, которое знает про раскладку файлов на нём:

    DATA_DIR/
      seen_listings.json   накопленная база объявлений (fingerprint -> запись)
      ranking.json         снимок последнего построенного рейтинга
      phone_counts.json    счётчик телефонов между прогонами (портфели)
      manual_listings.json посты из Facebook, разобранные /import
      fx_cache.json        курс ЦБ (пишет pipeline/fx.py напрямую)
      photos_cache/        скачанные и ужатые фото (пишет pipeline/photos.py)
      reports/report-YYYY-MM-DD-HHMM.html   архив прогонов
      report.html           копия последнего отчёта — то, что отдаёт "/"
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("pipeline.storage")


class Storage:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.reports_dir = self.data_dir / "reports"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # -- generic --
    def _read(self, name, default):
        p = self.data_dir / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.error("не смог прочитать %s: %s — использую значение по умолчанию", name, e)
            return default

    def _write(self, name, value):
        p = self.data_dir / name
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)  # атомарная замена — прогон, упавший на середине записи, не бьёт файл

    # -- seen_listings.json: fingerprint -> запись со всеми полями Listing --
    def load_seen(self) -> dict:
        return self._read("seen_listings.json", {})

    def save_seen(self, seen: dict) -> None:
        self._write("seen_listings.json", seen)

    # -- ranking.json: снимок последнего построенного рейтинга (для отладки
    #    и как самостоятельный артефакт, который просил промпт) --
    def save_ranking(self, ranking: list) -> None:
        self._write("ranking.json", ranking)

    # -- phone_counts.json: портфельные контакты --
    def load_phone_counts(self) -> dict:
        return self._read("phone_counts.json", {})

    def save_phone_counts(self, counts: dict) -> None:
        self._write("phone_counts.json", counts)

    # -- manual_listings.json: посты из Facebook (POST /import) --
    def load_manual(self) -> list:
        return self._read("manual_listings.json", [])

    def save_manual(self, items: list) -> None:
        self._write("manual_listings.json", items)

    # -- отчёты --
    def save_report(self, html: str, stamp: str) -> Path:
        dated = self.reports_dir / f"report-{stamp}.html"
        dated.write_text(html, encoding="utf-8")
        (self.data_dir / "report.html").write_text(html, encoding="utf-8")
        return dated

    def latest_report_html(self) -> str | None:
        p = self.data_dir / "report.html"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def list_reports(self) -> list:
        """Новые сверху: (имя_файла, дата-строка-для-показа)."""
        files = sorted(self.reports_dir.glob("report-*.html"), reverse=True)
        return [(f.name, f.stem.replace("report-", "")) for f in files]

    def report_path(self, filename: str) -> Path | None:
        # Имя приходит из URL (/archive/<filename>) — не доверяем ему:
        # ни разделителей пути, ни ".." быть не должно.
        if "/" in filename or "\\" in filename or ".." in filename:
            return None
        p = self.reports_dir / filename
        if p.exists() and p.is_file():
            return p
        return None
