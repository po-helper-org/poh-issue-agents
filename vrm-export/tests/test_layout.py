"""Жёсткие критерии (цена, студия), скоринг и защита от районной
подстрочной ловушки — сквозь настоящий core.passes_criteria/score_listing
(patch_v2 + расширение "спорно" из pipeline/layout.py), а не переизобретённые
в тесте копии."""
import pytest

from pipeline import core, districts
from pipeline.core import Listing


def make_listing(**kw):
    defaults = dict(source="test", url="https://example.com/1", title="", raw_text="",
                     city="Дананг", district="", price_vnd=15_000_000, area_m2=45.0,
                     detailed=True)
    defaults.update(kw)
    ln = Listing(**defaults)
    ln.price_rub = core.price_to_rub(ln.price_vnd)
    return ln


@pytest.fixture(autouse=True)
def _criteria():
    core.refresh_criteria(32.2690 / 10000, 12_000_000, 18_000_000)


def test_studio_marker_rejected():
    ln = make_listing(title="Cho thuê căn hộ mini giá rẻ")
    assert core.passes_criteria(ln) is False


def test_not_1br_rejected():
    ln = make_listing(title="Cho thuê CC 2 phòng ngủ view đẹp")
    assert core.passes_criteria(ln) is False


def test_flexible_bed_count_not_rejected():
    # "1-2 giường" — гибкая конфигурация, не повод отсекать (см. patch_v2.py NOT_1BR)
    ln = make_listing(title="Căn hộ 1-2 giường tuỳ chọn, giá tốt")
    assert core.passes_criteria(ln) is True


def test_pure_studio_without_contradiction_still_rejected():
    ln = make_listing(title="CĂN HỘ MINI cho thuê", raw_text="đầy đủ nội thất, gần biển")
    assert core.passes_criteria(ln) is False


def test_contradiction_is_not_rejected_and_labeled_disputed():
    # Реальный пример из PROMPT.md: заголовок "CĂN HỘ MINI", а описание
    # отдельно перечисляет гостиную и спальню.
    ln = make_listing(
        title="CĂN HỘ MINI cho thuê đường Nguyễn Văn Thoại",
        raw_text="Căn hộ có phòng khách rộng rãi và phòng ngủ riêng biệt, đầy đủ nội thất",
        detailed=True,
    )
    assert core.passes_criteria(ln) is True
    from pipeline import layout
    text = ln.title + " " + ln.raw_text
    assert layout.sep_label(text, ln.area_m2, ln.detailed) == "спорно"
    assert layout.contradiction_note(text, ln.detailed) != ""


def test_contradiction_only_applies_to_detailed_cards():
    ln = make_listing(
        title="CĂN HỘ MINI cho thuê",
        raw_text="phòng khách phòng ngủ riêng biệt",
        detailed=False,
    )
    # На списке (не открытой карточке) тексту доверять нельзя — жёсткий отсев остаётся.
    assert core.passes_criteria(ln) is False


def test_area_hygiene_below_15_dropped():
    ln = make_listing(area_m2=10.0)
    assert core.passes_criteria(ln) is False


def test_price_out_of_range_rejected():
    ln = make_listing(price_vnd=25_000_000)
    assert core.passes_criteria(ln) is False


def test_price_in_range_accepted():
    ln = make_listing(price_vnd=15_000_000)
    assert core.passes_criteria(ln) is True


def test_washing_machine_giat_rieng_detected():
    ln = make_listing(raw_text="phòng có máy giặt riêng, ban công thoáng")
    flags = core.qualitative_flags(ln)
    assert flags["washing_machine"] is True
    assert flags["washing_shared"] is False


def test_washing_machine_may_giat_fallback_still_detected():
    # Первая версия прототипа искала только "máy giặt" — этот случай не должен сломаться
    ln = make_listing(raw_text="có máy giặt trong nhà")
    flags = core.qualitative_flags(ln)
    assert flags["washing_machine"] is True


def test_washing_shared_penalizes_and_not_counted_as_in_unit():
    ln = make_listing(raw_text="giặt chung ở tầng trệt")
    flags = core.qualitative_flags(ln)
    assert flags["washing_shared"] is True
    assert flags["washing_machine"] is False
    score_with = core.score_listing(ln, flags)
    ln2 = make_listing(raw_text="máy giặt riêng trong phòng")
    flags2 = core.qualitative_flags(ln2)
    score_without = core.score_listing(ln2, flags2)
    assert score_without > score_with  # вес стиралки (+4/-2) должен доминировать


def test_district_word_boundary_trap():
    # "quan hai chau" содержит подстроку "an hai" (целевой район Son Tra),
    # но это Hải Châu — не целевой район. Наивный substring подставил бы
    # Son Tra; регулярка с границами слов (\b) — нет.
    d = districts.normalize_district(address="Quận Hải Châu, Đà Nẵng")
    assert d == "вне целевых"


def test_district_target_still_matches_with_boundaries():
    d = districts.normalize_district(address="An Hải, Sơn Trà, Đà Nẵng")
    assert d == "Son Tra"


def test_district_landmark_only_used_as_fallback():
    # Явный район важнее ориентира — "An Thượng" не должен уехать в Son Tra
    # только из-за упоминания пляжа Mỹ Khê где-то в тексте.
    d = districts.normalize_district(
        title="Căn hộ An Thượng cho thuê", raw_text="cách biển Mỹ Khê 5 phút đi bộ")
    assert d == "Ngu Hanh Son"
