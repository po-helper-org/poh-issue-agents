from . import alonhadat, batdongsan, dotproperty, fazwaz, mogi, nhatot

# Каждая запись — один URL одной доски. Источников с точки зрения промпта
# "8+", целей (URL) больше, потому что alonhadat и mogi покрывают несколько
# районов/городов отдельными ссылками — см. PROMPT.md, раздел "Источники".
TARGETS = [
    # -- Дананг --
    dict(engine=alonhadat, name="Дананг · Alonhadat (Sơn Trà)", city="Дананг",
         url="https://alonhadat.com.vn/nha-dat/cho-thue/can-ho-chung-cu/da-nang/586/quan-son-tra.html?dt=0&gia=5&huong=0"),
    dict(engine=alonhadat, name="Дананг · Alonhadat (весь город)", city="Дананг",
         url="https://alonhadat.com.vn/nha-dat/cho-thue/can-ho-chung-cu/3/da-nang.html?dt=0&gia=5&huong=0"),
    dict(engine=nhatot, name="Дананг · Nhà Tốt", city="Дананг",
         url="https://www.nhatot.com/thue-can-ho-chung-cu-da-nang-1-phong-ngu-sdro1"),
    dict(engine=batdongsan, name="Дананг · Batdongsan", city="Дананг",
         url="https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-da-nang"),
    dict(engine=fazwaz, name="Дананг · FazWaz", city="Дананг",
         url="https://www.fazwaz.vn/1-bedroom-property-for-rent/vietnam/da-nang"),
    dict(engine=mogi, name="Дананг · Mogi (Sơn Trà)", city="Дананг",
         url="https://mogi.vn/da-nang/quan-son-tra/thue-can-ho-chung-cu"),
    dict(engine=mogi, name="Дананг · Mogi (Ngũ Hành Sơn)", city="Дананг",
         url="https://mogi.vn/da-nang/quan-ngu-hanh-son/thue-can-ho-chung-cu"),
    dict(engine=dotproperty, name="Дананг · DotProperty", city="Дананг",
         url="https://www.dotproperty.com.vn/en/apartments-for-rent/%C4%91%C3%A0-n%E1%BA%B5ng/1-bedroom"),
    # -- Нячанг --
    dict(engine=nhatot, name="Нячанг · Nhà Tốt", city="Нячанг",
         url="https://www.nhatot.com/thue-can-ho-chung-cu-thanh-pho-nha-trang-khanh-hoa"),
    dict(engine=mogi, name="Нячанг · Mogi", city="Нячанг",
         url="https://mogi.vn/khanh-hoa/thue-can-ho-chung-cu"),
    # -- Вунгтау: рынок есть, но однушки обычно ниже вилки 12-18 млн ₫.
    #    Держим источник подключённым на случай смены бюджета (см. PROMPT.md) --
    dict(engine=mogi, name="Вунгтау · Mogi", city="Вунгтау",
         url="https://mogi.vn/ba-ria-vung-tau/thue-can-ho-chung-cu"),
]
