"""Сквозной прогон pipeline.run.run_once() на одном фиктивном источнике —
без сети (реальные сайты недоступны/непредсказуемы из тестового окружения),
но через ВСЮ остальную цепочку: скрейпер -> фильтр/скоринг -> состояние на
диске -> отчёт -> ranking.json. Ловит ошибки стыковки между модулями
(несовпадение полей и т.п.), которые модульные тесты по отдельности не видят."""
import shutil
from pathlib import Path

import pytest

from pipeline import core
from pipeline.config import Config
from pipeline.core import Listing
from pipeline.scrapers import base
from pipeline.scrapers import TARGETS as REAL_TARGETS


class _FakeEngine:
    """Один скрейпер, отдающий одно заведомо проходящее объявление и одно
    заведомо отсеиваемое (студия) — без единого сетевого запроса."""

    def scrape(self, target, fx):
        result = base.SourceResult(name=target["name"], city=target["city"], url=target["url"])
        good = Listing(
            source=target["name"], url="https://example.com/good-1",
            title="Căn hộ 1PN cho thuê Sơn Trà", raw_text="máy giặt riêng, ban công thoáng, phòng khách rộng",
            city="Дананг", district="Sơn Trà, Đà Nẵng", price_vnd=15_000_000, area_m2=46.0,
            photos=[], detailed=True,
        )
        studio = Listing(
            source=target["name"], url="https://example.com/studio-1",
            title="Căn hộ mini cho thuê giá rẻ", raw_text="",
            city="Дананг", district="Sơn Trà, Đà Nẵng", price_vnd=14_000_000, area_m2=20.0,
            detailed=True,
        )
        result.listings = [good, studio]
        result.found = 2
        return result

    def enrich_detail(self, listing):
        return False


def test_run_once_end_to_end_with_fake_source(tmp_path, monkeypatch):
    fake_engine = _FakeEngine()
    fake_target = dict(engine=fake_engine, name="Тест · Fake", city="Дананг", url="https://example.com/list")

    saved = list(REAL_TARGETS)
    REAL_TARGETS.clear()
    REAL_TARGETS.append(fake_target)
    try:
        from pipeline import run as run_module
        # Курс ЦБ — не сетевой тест: подменяем на фиксированное значение,
        # чтобы не ждать ретраев tenacity на заведомо недоступный домен.
        monkeypatch.setattr(run_module.fx, "fetch_rates",
                             lambda cbr_url, data_dir: {"vnd_to_rub": 32.2690 / 10000,
                                                         "usd_to_rub": 82.1665, "date": "test", "stale": False})
        isolated_data_dir = tmp_path
        cfg = Config(
            data_dir=str(isolated_data_dir), cbr_url="https://invalid.example/xml",
            price_min_vnd=12_000_000, price_max_vnd=18_000_000, studio_area=45,
            basic_auth_user="u", basic_auth_pass="p", run_token="t",
            telegram_bot_token="", telegram_chat_id="", run_cron="0 2 * * *",
            public_url="http://localhost:8000",
        )
        summary = run_module.run_once(cfg)

        assert summary["passed"] == 1  # студия отсеялась, прошла ровно одна
        assert summary["new"] == 2     # но новых карточек в базе — обе (для дедупа)

        report_html = Path(isolated_data_dir, "report.html").read_text(encoding="utf-8")
        assert "Sơn Trà" in report_html or "Sơn" in report_html
        import re
        assert not re.search(r"__[A-Z]+__", report_html), "остался незаполненный плейсхолдер шаблона"

        ranking = Path(isolated_data_dir, "ranking.json")
        assert ranking.exists()
    finally:
        REAL_TARGETS.clear()
        REAL_TARGETS.extend(saved)
