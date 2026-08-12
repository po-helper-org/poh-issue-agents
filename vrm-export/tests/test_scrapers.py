"""Парсеры карточек — на зафиксированных HTML-фикстурах с живых страниц
(сняты 12.08.2026, см. tests/fixtures/). Если сайт сменит вёрстку, эти
тесты покраснеют раньше, чем прогон в проде тихо начнёт терять объявления."""
from conftest import read_fixture

from pipeline.scrapers import base, batdongsan, dotproperty, fazwaz, mogi


def test_mogi_list_parses_real_cards():
    cards = mogi.parse_list(read_fixture("mogi_list.html"), "Дананг", "test", "https://mogi.vn/x")
    assert len(cards) == 2
    c = cards[0]
    assert c["url"].startswith("https://mogi.vn/")
    assert c["price_text"]
    assert c["bedrooms"] == 1
    # "45 m<sup>2</sup>" не должно разъезжаться на "45 m 2"
    assert "m2" in c["area_text"].replace(" ", "")


def test_mogi_detail_parses_description_and_photos():
    d = mogi.parse_detail(read_fixture("mogi_detail.html"))
    assert "Cho thuê" in d["description"]
    assert len(d["photos"]) >= 3
    assert d["posted"]


def test_fazwaz_list_parses_real_cards():
    cards = fazwaz.parse_list(read_fixture("fazwaz_list.html"))
    assert len(cards) == 1
    c = cards[0]
    assert c["url"].startswith("https://www.fazwaz.vn/")
    assert c["price_text"].startswith("$")
    assert "sqm" in c["area_text"].lower()
    assert c["photos"]


def test_dotproperty_list_parses_real_cards():
    cards = dotproperty.parse_list(read_fixture("dotproperty_list.html"))
    assert len(cards) == 1
    c = cards[0]
    assert c["url"].startswith("https://www.dotproperty.com.vn/")
    assert "₫" in c["text"]


def test_dotproperty_price_prefix_format():
    # У DotProperty валюта ПЕРЕД числом ("₫ 20,000,000"), не после, как в
    # остальных источниках — это отдельный формат, не покрытый fb_import.
    m = dotproperty._PRICE_VND.search("Giá thuê ₫ 20,000,000 / tháng")
    assert m and m.group(1).replace(",", "") == "20000000"


def test_batdongsan_foreign_city_trap_detected():
    # Ловушка из PROMPT.md: районный URL molчa подменяется общевьетнамским
    # списком с Ханоем/ХШМ вперемешку.
    html = "<html><body><div class='js__card'>Vinhomes Smart City, Tây Mỗ, Hà Nội</div></body></html>"
    assert base.has_foreign_city_marker(html) is True


def test_batdongsan_normal_danang_page_not_flagged():
    html = "<html><body><div class='js__card'>Căn hộ Sơn Trà, Đà Nẵng</div></body></html>"
    assert base.has_foreign_city_marker(html) is False
