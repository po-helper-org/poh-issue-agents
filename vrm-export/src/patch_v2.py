#!/usr/bin/env python3
"""
patch_v2.py — исправления к danang_monitor.py, найденные на первом реальном прогоне
10.08.2026. Импортируй ПОСЛЕ danang_monitor и вызови apply(), либо перенеси
функции в основной файл.

    import danang_monitor as dm
    import patch_v2; patch_v2.apply(dm)
"""
import re

# --- FIX 1: курс ЦБ котирует донг НАПРЯМУЮ ----------------------------------
# Было: VND_TO_RUB = USD_TO_RUB / 26205 (кросс-курс через доллар, даёт -2.9%)
# Стало: 10 000 VND = 32.2690 RUB (ЦБ РФ, 08.08.2026)
CBR_VND_TO_RUB = 32.2690 / 10000
CBR_USD_TO_RUB = 82.1665

TARGET_DISTRICTS = ["son tra", "ngu hanh son", "my an", "an thuong",
                    "my khe", "an hai", "phuoc my", "man thai", "bac my an"]

# --- FIX 2: 'giặt riêng' — главная пропажа ----------------------------------
# Во вьетнамских объявлениях стиралка в квартире почти всегда пишется как
# "giặt riêng" (личная стирка) в противовес "giặt chung" (общая машина на этаж).
# Старый фильтр искал только "máy giặt" и пропускал ВСЕ такие объявления —
# на прогоне 10.08 это 5 из 5 топ-кандидатов с флагом washing_machine=False.
WASH_IN_UNIT = ["máy giặt riêng", "giặt riêng", "may giat rieng", "giat rieng",
                "máy giặt", "may giat", "washing machine", "washer"]
WASH_SHARED = ["giặt chung", "giat chung", "shared washing", "shared laundry"]

DRYER = ["máy sấy", "may say", "giặt sấy", "giat say", "dryer", "tumble dry"]
DISHWASHER = ["máy rửa bát", "máy rửa chén", "may rua bat", "may rua chen", "dishwasher"]
BRIGHT = ["thoáng", "thoang", "cửa sổ", "cua so", "ban công", "ban cong",
          "bright", "airy", "natural light", "sáng"]

# --- FIX 3: отсев не-euro-1BR и студий ------------------------------------
# Старый фильтр отсекал только слово "studio". Но в Дананге студию почти
# никогда так не называют: пишут "căn hộ mini", "phòng khép kín", "officetel",
# "chung cư mini" — формально «квартира», фактически одна комната.
NOT_1BR = [
    r"\b2\s*pn\b", r"\b3\s*pn\b", r"\b2\s*phòng ngủ", r"\b3\s*phòng ngủ",
    r"\b2\s*phong ngu", r"\b3\s*phong ngu", r"\b2\s*bedroom", r"\b3\s*bedroom",
    r"\b2\s*br\b", r"\b3\s*br\b",
    # "2 кровати" = открытая планировка. НО "1-2 giường" — гибкая конфигурация
    # (1 кровать за одну цену, 2 за другую), это не повод отсекать: отрицательный
    # просмотр назад гасит правило, планировку помечаем как спорную.
    r"(?<!1-)(?<!1 - )\b2\s*giường\b", r"(?<!1-)(?<!1 - )\b2\s*giuong\b",
]

# Прямые синонимы студии — отсекаем жёстко.
STUDIO = [
    r"\bstudio\b", r"\bstudios\b", r"\bофистел\b", r"\bofficetel\b",
    r"căn hộ mini", r"can ho mini", r"chung cư mini", r"chung cu mini",
    r"phòng khép kín", r"phong khep kin", r"\bphòng trọ\b", r"\bphong tro\b",
    r"\bktx\b", r"ký túc xá", r"ky tuc xa", r"\bhomestay\b",
    r"open[- ]plan", r"open space", r"\bloft\b", r"phòng cho thuê", r"phong cho thue",
]

# Прямые признаки отдельной спальни — то, ради чего всё затевалось.
SEP_YES = [
    "phòng ngủ riêng", "phong ngu rieng", "riêng biệt", "rieng biet",
    "ngủ riêng", "ngu rieng", "separate bedroom", "closed bedroom",
    "1 phòng ngủ, 1 wc", "phòng khách riêng", "phong khach rieng",
    "living room", "phòng khách", "phong khach",
]

# Порог, ниже которого «однушка» без подтверждения почти всегда оказывается
# студией: euro-1BR в Дананге меньше 45 м² встречается, но редко.
STUDIO_AREA = 45


def layout_verdict(text, area, detailed):
    """'studio' — отсечь; 'likely_studio' — почти наверняка студия, но не
    доказано; 'ok' — спальня подтверждена; 'unconfirmed' — неясно.

    Почему два разных вердикта вместо одного. Прямые маркеры («studio»,
    «căn hộ mini», «2PN») — это факт, такие режем. А «меньше 45 м² и ни слова
    про спальню» — всего лишь улика: описания на досках короткие, и настоящая
    euro-1BR на 40 м² вполне может не упомянуть планировку. Резать по улике
    дорого: потерять живой вариант хуже, чем сделать лишний звонок. Поэтому
    такие не выбрасываем, а топим в рейтинге и подписываем.

    Строгое правило применяем только к объявлениям с открытой карточкой:
    на странице списка текста почти нет, там молчание ничего не значит.
    """
    t = text.lower()
    if any(re.search(p, t) for p in STUDIO):
        return "studio"
    if any(re.search(p, t) for p in NOT_1BR):
        return "studio"
    if any(k in t for k in SEP_YES):
        return "ok"
    if detailed and area is not None and area < STUDIO_AREA:
        return "likely_studio"
    return "unconfirmed"


def apply(dm):
    dm.VND_TO_RUB = CBR_VND_TO_RUB

    def passes_criteria(listing) -> bool:
        """Жёстких критериев ровно два: цена и «не студия».
        Район, площадь и техника больше не отсекают — они ушли в скоринг,
        чтобы подборка не схлопывалась до трёх строк. Отсечь всегда
        успеем фильтром в отчёте, а вот не увидеть вариант — потеря."""
        if listing.price_rub is None:
            return False
        if not (dm.CRITERIA["price_rub_min"] <= listing.price_rub <= dm.CRITERIA["price_rub_max"]):
            return False
        # Не критерий, а гигиена данных: 1 м² — мусор парсинга, а не квартира
        if listing.area_m2 is not None and listing.area_m2 < 15:
            return False
        text = (listing.title + " " + listing.raw_text).lower()
        detailed = getattr(listing, "detailed", False)
        if layout_verdict(text, listing.area_m2, detailed) == "studio":
            return False
        return True

    def qualitative_flags(listing) -> dict:
        text = (listing.title + " " + listing.raw_text).lower()
        wash_shared = any(k in text for k in WASH_SHARED)
        detailed = getattr(listing, "detailed", False)
        return {
            "layout": layout_verdict(text, listing.area_m2, detailed),
            "sep_confirmed": layout_verdict(text, listing.area_m2, detailed) == "ok",
            "washing_machine": (not wash_shared) and any(k in text for k in WASH_IN_UNIT),
            "washing_shared": wash_shared,
            "dryer": any(k in text for k in DRYER),
            "dishwasher": any(k in text for k in DISHWASHER),
            "bright": any(k in text for k in BRIGHT),
        }

    def fingerprint(self) -> str:
        # FIX: старый ключ (район|цена|площадь) схлопывал разные квартиры
        # с одинаковыми 40м²/8млн в одну. Добавляем URL.
        import hashlib
        key = f"{self.district}|{self.price_vnd}|{self.area_m2}|{self.url}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def district_weight(listing) -> float:
        """Целевые районы у пляжа — плюс; заведомо далёкие — крупный минус.
        Минус специально меньше веса стиралки: квартира с полным набором
        техники в Hai Chau должна быть видна, просто не в первой пятёрке."""
        hay = (listing.district + " " + listing.title + " " + listing.raw_text).lower()
        if re.search(r"\b(hai chau|cam le|lien chieu|thanh khe|hoa vang)\b", hay):
            return -4.0
        if any(re.search(rf"\b{re.escape(d)}\b", hay) for d in TARGET_DISTRICTS):
            return 2.0
        return 0.0

    def score_listing(listing, flags) -> float:
        score = district_weight(listing)
        if listing.price_rub:
            span = dm.CRITERIA["price_rub_max"] - dm.CRITERIA["price_rub_min"]
            score += (dm.CRITERIA["price_rub_max"] - listing.price_rub) / span * 3
        if listing.area_m2:
            if listing.area_m2 >= 45:
                score += 1
            elif listing.area_m2 >= 40:
                score += 0.5
            elif listing.area_m2 < 35:
                score -= 1
        # FIX: стиралка — обязательный критерий, вес должен доминировать над ценой
        if flags.get("washing_machine"):
            score += 4
        elif flags.get("washing_shared"):
            score -= 2
        if flags.get("dryer"):
            score += 1
        if flags.get("dishwasher"):
            score += 1.5
        if flags.get("bright"):
            score += 1
        # Неподтверждённая отдельная спальня — не отказ, но и не наравне
        # с подтверждённой: такие уходят под низ списка.
        if flags.get("layout") == "likely_studio":
            score -= 3
        elif flags.get("layout") == "unconfirmed":
            score -= 2
        return round(score, 2)

    dm.passes_criteria = passes_criteria
    dm.qualitative_flags = qualitative_flags
    dm.score_listing = score_listing
    dm.Listing.fingerprint = fingerprint
    return dm
