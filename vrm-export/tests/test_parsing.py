"""Цена и площадь — форматы, обкатанные на реальных объявлениях
(см. src/fb_import.py). Проверяем через pipeline.parsing, который эти
регулярки переиспользует, а не дублирует."""
from pipeline import parsing


def test_price_tr5_shorthand():
    # "8tr5" = 8,5 млн — сокращение, которое ловится ДО общего "triệu"-правила
    assert parsing.parse_price_vnd("cho thuê giá 8tr5 thương lượng")[0] == 8_500_000


def test_price_dotted_dong():
    price, note = parsing.parse_price_vnd("Giá 12.000.000đ / tháng")
    assert price == 12_000_000
    assert note == "₫"


def test_price_usd():
    price, note = parsing.parse_price_vnd("Rent $380 per month, negotiable")
    assert price is not None and price > 0
    assert note.startswith("$")


def test_price_trieu_word():
    assert parsing.parse_price_vnd("Giá thuê 15 triệu/tháng")[0] == 15_000_000


def test_area_m2_compact():
    assert parsing.parse_area("Căn hộ 45m2 đầy đủ nội thất") == 45.0


def test_area_dien_tich_label():
    assert parsing.parse_area("Thông tin: diện tích 48, tầng 5") == 48.0


def test_area_missing_returns_none():
    assert parsing.parse_area("Không có thông tin diện tích ở đây") is None


def test_price_missing_returns_none_and_no_note():
    price, note = parsing.parse_price_vnd("Liên hệ để biết giá")
    assert price is None
    assert note is None
