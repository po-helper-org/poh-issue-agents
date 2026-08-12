"""Обязательная проверка перед выкладкой (см. PROMPT.md): просмотрщик
пользователя не выполняет инлайновый <script>, поэтому если таблица
рисуется только на JS, отчёт открывается пустым. Открываем собранный
report.html в Playwright с javaScriptEnabled=False и убеждаемся, что строк в tbody
не ноль."""
import pytest

from pipeline import report


def _sample_rows(n=3):
    rows = []
    for i in range(n):
        rows.append(dict(
            street=f"Test St {i}", district="Son Tra", city="Дананг", area=45.0 + i,
            rub=40000 + i * 1000, vnd=(14 + i) * 1_000_000, score=8.5 - i, floor=5,
            level="B", sep="да", wash=True, dryer=False, dish=False, bright=True,
            owner=f"Owner {i}", phone="0905154727", zalo=True, otype="Собственник",
            posted="12.08.2026", portfolio=False, checked=True, note="", ask="",
            photos=[], src="Mogi", url=f"https://example.com/{i}",
        ))
    return rows


@pytest.fixture
def sample_report_html():
    rows = _sample_rows()
    return report.build_html(
        rows=rows, source_stats=[("Mogi", 10, 3)], new_count=2, total_collected=10,
        fx_note="10 000 ₫ = 32,28 ₽", run_label="12.08.2026 09:00",
        title="Дананг · euro-1BR", criteria_note="Бюджет 12–18 млн ₫ · не студия",
        broken_count=0,
    )


def test_report_html_has_rows_in_markup_without_running_js(sample_report_html):
    """Санити-проверка на уровне разметки — без браузера: <tbody> в самом
    HTML уже должен содержать <tr>, а не быть пустым до JS-рендера. Считаем
    через парсер, а не substring: JS ниже по странице тоже содержит текст
    "<tr>" внутри шаблонной строки rowHTML(), naive-подсчёт даёт ложный плюс."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(sample_report_html, "html.parser")
    assert len(soup.find("tbody", id="body").find_all("tr")) == 3
    assert 'class="nojs"' in sample_report_html


def test_report_renders_without_js_in_real_browser(tmp_path, sample_report_html):
    playwright = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "report.html"
    path.write_text(sample_report_html, encoding="utf-8")

    import os
    executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    launch_kwargs = {"executable_path": executable_path} if os.path.exists(executable_path) else {}

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(java_script_enabled=False)
            page.goto(path.as_uri())
            rows = page.query_selector_all("tbody#body tr")
            assert len(rows) == 3, "с выключенным JS таблица не должна быть пустой"
            # Прогрессивное улучшение: без JS фильтры скрыты, класс остаётся "nojs"
            html_class = page.eval_on_selector("html", "el => el.className")
            assert html_class == "nojs"
        finally:
            browser.close()
