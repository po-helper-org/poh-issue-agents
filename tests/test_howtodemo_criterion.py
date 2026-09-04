"""Критерий приёмки: один читатель на гейт разработки и на приёмщика.

Живой разбор (#301, `poh-demo-checkout#171`): гейт нашёл критерий в размеченном
блоке и пропустил задачу в разработку за полминуты, а приёмщик через двадцать
минут ответил «проверять нечем» и повесил `demo:no-scenario` — на задачу, у
которой сценарий есть. Приёмщик знает только формы заголовка; о блоке
`harness:howtodemo` он не знает и знать не обязан.

Проверки идут ЧЕРЕЗ НАСТОЯЩИЙ разбор приёмщика (`poh_howtodemo.anchor`), а не
через его копию здесь: копия — ровно то второе место, из расхождения с которым
задача и выросла.
"""

from poh_howtodemo import anchor

from shared import howtodemo, issue_blocks


def block(content: str) -> str:
    return issue_blocks.write("## Что происходит\n\nОписание задачи.",
                              issue_blocks.HOWTODEMO, content)


def test_the_defect_of_301_is_reproducible_on_the_real_parser():
    """Сырое тело с блоком приёмщику ничего не говорит — это и был дефект."""
    body = block("было — 404 на HEAD; стало — 405")
    assert howtodemo.read(body) == "было — 404 на HEAD; стало — 405"
    assert anchor.extract_block(body) is None


def test_approved_block_reaches_the_acceptance_agent():
    body = block("было — 404 на HEAD; стало — 405")
    assert anchor.extract_block(howtodemo.expose(body)) == \
        "было — 404 на HEAD; стало — 405"


def test_exposed_criterion_does_not_swallow_the_rest_of_the_body():
    """Граница нужна заголовком: приёмщик читает до следующего заголовка."""
    body = issue_blocks.write("Первая строка без заголовка вообще.",
                              issue_blocks.HOWTODEMO, "было — А; стало — Б")
    assert anchor.extract_block(howtodemo.expose(body)) == "было — А; стало — Б"


def test_body_without_a_criterion_is_handed_over_untouched():
    """Сценарий мог остаться в письме БФТ — приёмщик заберёт его из ленты сам."""
    body = "## Что происходит\n\nОписание задачи без единого критерия."
    assert howtodemo.expose(body) == body


def test_empty_block_is_not_an_approval():
    body = issue_blocks.write("Текст задачи.", issue_blocks.HOWTODEMO, "")
    assert howtodemo.read(body) == ""
    assert howtodemo.expose(body) == body


def test_russian_heading_also_reaches_the_acceptance_agent():
    """Тот же разрыв другой стороной: `## Как принимаем` контур знает, приёмщик — нет.

    Русские формы заголовка появились в контуре после `poh-demo-checkout#163`,
    и приёмщику о них никто не сообщал. Пока критерий разбирали двое, каждая
    новая форма означала новое расхождение.
    """
    body = "## Как принимаем\n\nбыло — пусто; стало — список заказов"
    assert anchor.extract_block(body) is None
    assert anchor.extract_block(howtodemo.expose(body)) == \
        "было — пусто; стало — список заказов"


def test_approved_block_wins_over_a_section_for_both_readers():
    """Приоритет один: подтверждённый блок старше раздела, а приёмщик берёт первое."""
    body = issue_blocks.write("## HowToDemo\n\nстарая редакция",
                              issue_blocks.HOWTODEMO, "подтверждённый критерий")
    assert howtodemo.read(body) == "подтверждённый критерий"
    assert anchor.extract_block(howtodemo.expose(body)) == "подтверждённый критерий"


def test_numbered_criterion_stays_a_numbered_scenario():
    """Нумерация — не украшение: по ней приёмщик решает, разбирать ли по шагам."""
    steps = "1. Открываю корзину\n2. Вижу итог 0"
    exposed = howtodemo.expose(block(steps))
    found = anchor.extract_block(exposed)
    assert anchor.is_numbered(found)
    assert anchor.parse_steps(found) == ["Открываю корзину", "Вижу итог 0"]


def test_corrupted_markers_do_not_break_the_handover():
    """Обрывок маркера в теле — не повод ронять приёмку: читаем по заголовку."""
    body = ("<!-- harness:howtodemo:start -->\n"
            "## HowToDemo\n\nбыло — А; стало — Б")
    assert howtodemo.read(body) == "было — А; стало — Б"
    assert anchor.extract_block(howtodemo.expose(body)) == "было — А; стало — Б"


def test_the_list_of_recognised_headings_is_closed_and_named_correctly():
    """Формы заголовка перечислены проверкой, а не только регэкспом.

    Ревью PR #306 поймало ровно этот разрыв: `docs/HOWTODEMO.md` называл
    работающей формой `## Критерий приёмки`, которой шаблон не знает — «приёмка»
    в нём литерал, и «приёмки» под него не подходит. Пока список нигде не
    перечислен списком, следующая правка документации разойдётся с кодом так же
    молча, и эксплуатация будет ждать поддержки, которой нет.
    """
    for heading in ("## HowToDemo", "### How to demo", "## Как принимаем",
                    "## Как проверяем", "## Как демонстрируем", "## Приёмка",
                    "## Приемка"):
        assert howtodemo.read(f"{heading}\nсценарий") == "сценарий", heading
    for heading in ("## Критерий приёмки", "## Критерии приёмки", "## Приёмки"):
        assert howtodemo.read(f"{heading}\nсценарий") == "", heading
