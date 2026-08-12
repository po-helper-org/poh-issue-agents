#!/usr/bin/env python3
"""
render_html.py — серверный рендер таблицы.

ЗАЧЕМ. Просмотрщик файлов в мобильном приложении не выполняет инлайновый
<script>. Раньше вся таблица рисовалась только на JS, поэтому в приложении
страница открывалась пустой: шапка, плитки и фильтры на месте, а строк нет.
Теперь HTML содержит готовую таблицу, а JS сверху только улучшает —
сортировка кликом, фильтры, галерея, карточка владельца.

Разметка здесь обязана совпадать с rowHTML() в template.html, иначе после
первого клика по фильтру строки визуально «прыгнут».
"""

COLS = [("_i", "#", 0), ("_ph", "Фото", 0), ("street", "Адрес", 1), ("rub", "Цена, ₽", 1),
        ("area", "м²", 1), ("score", "Score", 1), ("_am", "Удобства", 0),
        ("level", "Уровень", 1), ("sep", "Спальня", 1), ("owner", "Владелец", 1)]


def esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def ru(n):
    """27429 -> '27 429' с неразрывным пробелом — как toLocaleString('ru-RU')."""
    return f"{int(n):,}".replace(",", " ")


def head_html():
    out = []
    for k, t, sortable in COLS:
        if not sortable:
            out.append(f"<th>{t}</th>")
        else:
            cls = ' class="sorted"' if k == "score" else ""
            out.append(f'<th data-k="{k}" tabindex="0"{cls}>{t}<span class="ar">&#9660;</span></th>')
    return "".join(out)


def row_html(r, i):
    sc = "s-hi" if r["score"] >= 7 else "s-mid" if r["score"] >= 3 else "s-lo"
    tel = "".join(c for c in (r.get("phone") or "") if c.isdigit())

    if r["photos"]:
        # Превью — фоновая картинка поверх подписи, а не <img>.
        # <img> при неудаче рисует ломаный значок, и onerror без JS не спасает.
        ph = (f'<a class="thumb" href="{esc(r["photos"][0])}" target="_blank" rel="noopener" '
              f'onclick="return openGal({i},0)" aria-label="Фото: {esc(r["street"])}">'
              f'<span class="fb">Фото&nbsp;&#8599;</span>'
              f'<span class="ph" style="background-image:url(&#39;{esc(r["photos"][0])}&#39;)"></span>'
              f'<span class="cnt">{len(r["photos"])}</span></a>')
    else:
        ph = '<div class="nophoto">нет фото</div>'

    floor = f' &middot; {r["floor"]}-й этаж' if r["floor"] else ""
    note = f'<div class="note">{esc(r["note"])}</div>' if r["note"] else ""
    lvl = "не проверен" if r["level"] == "?" else "уровень " + r["level"]
    lvl_cls = "b" if r["level"] == "B" else "q"
    sep_cls = ("b" if r["sep"] == "да"
               else "w" if r["sep"] in ("спорно", "вероятно студия")
               else "q")
    href = f'tel:+84{tel.lstrip("0")}' if tel else esc(r["url"])
    phone_line = f'<div class="ophone">{tel[:4]}.{tel[4:7]}.{tel[7:]}</div>' if tel else ""
    on = lambda k: "on" if r[k] else ""

    return (
        f'<tr>'
        f'<td class="rank">{i+1}</td>'
        f'<td>{ph}</td>'
        f'<td>'
        f'<div class="street"><a href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["street"])}</a></div>'
        f'<div class="meta"><b class="city">{esc(r["city"])}</b> &middot; {esc(r["district"])}{floor} &middot; {esc(r["src"])}</div>'
        f'{note}'
        f'<a class="orig" href="{esc(r["url"])}" target="_blank" rel="noopener">'
        f'<span class="arw">&#8599;</span> Оригинал на {esc(r["src"])}</a>'
        f'</td>'
        f'<td class="num" data-l="Цена"><div class="rub">{ru(r["rub"])} &#8381;</div>'
        f'<div class="vnd">{r["vnd"]/1e6:.1f} млн &#8363;</div></td>'
        f'<td class="num" data-l="м²">{r["area"]}</td>'
        f'<td class="num score {sc}" data-l="Score">{r["score"]:.2f}</td>'
        f'<td data-l="Удобства"><span class="am">'
        f'<i class="{on("wash")}" title="стиралка в квартире">С</i>'
        f'<i class="{on("dryer")}" title="сушилка">Су</i>'
        f'<i class="{on("dish")}" title="посудомойка">П</i>'
        f'<i class="{on("bright")}" title="свет">&#9728;</i></span></td>'
        f'<td data-l="Уровень"><span class="tag {lvl_cls}">{lvl}</span></td>'
        f'<td data-l="Спальня"><span class="tag {sep_cls}">{esc(r["sep"])}</span></td>'
        f'<td data-l="Владелец"><a class="obtn {"pf" if r["portfolio"] else ""}" href="{href}" '
        f'onclick="return openOwner({i})"><span class="dot"></span>'
        f'{esc(r["owner"] or "нет данных")}</a>{phone_line}</td>'
        f'</tr>'
    )


def body_html(rows):
    return "".join(row_html(r, i) for i, r in enumerate(rows))


def srctbl_html(source_stats):
    return "".join(
        f'<div><span>{esc(n)}</span><span>{f} найдено &middot; '
        f'<b style="color:{"var(--good)" if p else "var(--tx3)"}">{p}</b> прошло</span></div>'
        for n, f, p in source_stats)


def count_html(shown, total, collected):
    return (f"Показано <b>{shown}</b> из <b>{total}</b> прошедших фильтр "
            f"(всего собрано {collected})")
