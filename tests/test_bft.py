"""Чистая логика БФТ: ветка, стадии, сборка письма и постановки.

Ни сети, ни Temporal, ни модели — ровно то, ради чего `shared/bft.py` держится
свободным от зависимостей. Формат письма проверяется здесь, а не через прогон
воркфлоу: сломанный порядок блоков заметен только тому, кто читает результат.
"""

from shared import bft
from shared.commands import (
    BFT,
    BFT_DEEP,
    bft_mode,
    build_bft_request,
    parse_command,
    parse_command_args,
    parse_label_command,
    run_label,
)


# --- Адресация артефактов ---

def test_branch_and_slug_derive_from_the_issue_number():
    """Не из заголовка: заголовок редактируют, и повторный прогон писал бы
    рядом с прошлым вместо того, чтобы дополнить его."""
    assert bft.branch(42) == "bft-research/issue-42"
    assert bft.epic_slug(42) == "issue-42"
    assert bft.document_path(42) == ".bft/documentation/issue-42/issue-42.md"
    assert bft.statement_path(42).startswith(".bft/documentation/issue-42/artefacts/")


def test_bft_branch_does_not_collide_with_the_analysis_branch():
    """`research/issue-N` принадлежит цепочке FNR. Общая ветка означала бы, что
    повторный прогон одного документа затирает историю другого."""
    assert not bft.branch(42).startswith("research/")


# --- Стадии глубокого прогона ---

def test_deep_stages_are_chained_by_their_artifacts():
    """Вход каждой стадии — выход предыдущей. Разорванная цепочка означала бы
    стадию, работающую по пустому месту и не замечающую этого."""
    stages = bft.deep_stages(7)
    assert [name for name, *_ in stages] == list(bft.DEEP_STAGE_NAMES)

    produced: set[str] = set()
    for name, _prompt, expected, requires in stages:
        if requires is not None:
            assert requires in produced, f"стадия {name} требует того, чего никто не создал"
        if expected:
            produced.add(expected)


def test_every_deep_stage_prompt_starts_with_its_command():
    """`claude -p` разворачивает команду только первой строкой. Текст перед ней
    превратил бы вызов навыка в обычный вопрос модели."""
    for name, prompt, _expected, _requires in bft.deep_stages(7):
        assert prompt.startswith("/bft-"), f"стадия {name}: промпт не начинается командой"


def test_deep_stage_lookup_matches_the_table():
    prompt, expected, requires = bft.deep_stage("problem", 7)
    assert prompt == "/bft-problem issue-7"
    assert expected.endswith("problem.md")
    assert requires.endswith("bft-context-pack.md")


def test_unknown_deep_stage_is_an_error():
    try:
        bft.deep_stage("не-стадия", 7)
    except ValueError as exc:
        assert "не-стадия" in str(exc)
    else:
        raise AssertionError("неизвестная стадия должна быть ошибкой, а не тишиной")


# --- Письмо ---

def _letter(**overrides):
    kwargs = dict(
        goal="Покупатели из Казахстана не понимают цену в рублях — показываем KZT.",
        how_to_demo=["Открываю карточку", "Вижу цену в KZT"],
        open_questions=["Откуда берём курс? (Аня)", "Округляем ли до целых?"],
        scope="карточка товара (корзина — не входит в зону БФТ)",
        documentation=["[Эпик GDSLV-1374](https://example.test/1374)"],
        requirements=[{"id": "БТ-1", "as_is": "[ASIS не озвучен]", "to_be": "цена в KZT",
                       "related": "", "source": "«хочу видеть цену в тенге»"}],
        personas=[{"name": "Аня", "role": "PO", "unit": "[не указано]"}],
    )
    kwargs.update(overrides)
    return bft.render_letter(**kwargs)


def test_letter_keeps_the_block_order_of_the_skill():
    """Порядок задан `letter_format.md` и здесь не меняется: письмо пересылают
    как есть, и перетасованные блоки читаются как другой документ."""
    body = _letter()
    order = [body.index(marker) for marker in
             ("**Цель:**", "**How to demo:**", "**Открытые вопросы:**",
              "**Границы:**", "**Документация:**")]
    assert order == sorted(order)


def test_letter_ends_with_the_deep_hint_and_numbered_questions():
    """Постановка требует буквально: приписка снизу и перечисление всех вопросов
    — чтобы на них можно было ответить одной командой."""
    body = _letter()
    tail = body[body.rindex("---"):]
    assert "/bft-deep" in tail
    assert "1. Откуда берём курс? (Аня)" in tail
    assert "2. Округляем ли до целых?" in tail


def test_letter_without_questions_still_offers_the_deep_run():
    """Вопросов нет — приписка остаётся: глубокая проработка нужна не только
    ради ответов, и её отсутствие в письме читалось бы как «нельзя»."""
    body = _letter(open_questions=[])
    assert "**Открытые вопросы:**" not in body
    assert "/bft-deep" in body


def test_empty_blocks_are_omitted_not_left_hollow():
    """Пустой заголовок читается как «подумали, там ничего нет», а означает
    «данных не было». Это разные утверждения."""
    body = _letter(documentation=[], personas=[], scope="")
    assert "**Документация:**" not in body
    assert "**Стейкхолдеры:**" not in body
    assert "**Границы:**" not in body


def test_requirements_table_escapes_pipes_and_newlines():
    """Цитата с `|` иначе разъезжается в лишний столбец и рушит всю таблицу."""
    body = _letter(requirements=[{"id": "ФТ-1", "as_is": "a|b", "to_be": "c\nd",
                                  "related": "", "source": "«цитата»"}])
    row = next(line for line in body.splitlines() if line.startswith("| ФТ-1"))
    # Считаем НЕэкранированные: экранированный `\|` остаётся символом строки,
    # но столбца собой не открывает.
    delimiters = sum(1 for i, ch in enumerate(row)
                     if ch == "|" and (i == 0 or row[i - 1] != "\\"))
    assert delimiters == 6  # 5 столбцов = 6 разделителей
    assert "\\|" in row
    assert "\n" not in row  # перенос строки разорвал бы таблицу


def test_revision_is_named_only_from_the_second_one():
    assert "Редакция" not in _letter(revision=1)
    assert "Редакция 2" in _letter(revision=2)


# --- Постановка и сводка ---

def test_statement_puts_clarifications_above_the_thread():
    """Уточнения — последнее слово заказчика; в постановке они обязаны стоять
    раньше переписки, иначе пайплайн увидит их как реплику среди прочих."""
    text = bft.render_statement(title="Валюты", body="тело", thread="**@bob:** старое",
                                instructions="считать по курсу ЦБ",
                                issue_number=42, repo="acme/widgets")
    assert text.index("считать по курсу ЦБ") < text.index("старое")
    assert "acme/widgets#42" in text


def test_statement_without_clarifications_has_no_empty_section():
    text = bft.render_statement(title="Валюты", body="тело", thread="",
                                instructions="", issue_number=42, repo="acme/widgets")
    assert "Уточнения заказчика" not in text
    assert "Обсуждение Issue" not in text


def test_deep_summary_points_at_the_document_first():
    files = [bft.document_path(42), f"{bft.artefacts_dir(42)}/problem.md"]
    text = bft.render_deep_summary("acme/widgets", 42, files)
    assert "bft-research/issue-42" in text
    assert "issue-42.md" in text
    assert "/bft-deep" in text  # путь к следующей итерации назван


# --- Команды ---

def test_both_bft_commands_parse_with_their_arguments():
    assert parse_command("/bft поправь цель") == BFT
    assert parse_command_args("/bft поправь цель") == "поправь цель"
    assert parse_command("/bft-deep") == BFT_DEEP
    # Хвост многострочный: ответы на пять вопросов в одну строку не пишут.
    assert parse_command_args("/bft-deep 1. курс ЦБ\n2. да") == "1. курс ЦБ\n2. да"


def test_bft_deep_is_not_swallowed_by_bft():
    """Разбор идёт по целому токену: иначе `/bft-deep` запускал бы дешёвый
    прогон, а человек ждал бы документ."""
    assert parse_command("/bft-deep уточнение") == BFT_DEEP


def test_args_are_empty_for_a_non_command():
    assert parse_command_args("просто комментарий") == ""
    assert parse_command_args("> /bft в цитате") == ""
    assert parse_command_args("") == ""
    assert parse_command_args("\n   \n") == ""


def test_leading_blank_lines_do_not_hide_the_command():
    """Комментарий, начатый с пустой строки, — обычное дело в вебе."""
    assert parse_command("\n\n/bft-deep ответы") == BFT_DEEP
    assert parse_command_args("\n\n/bft-deep ответы") == "ответы"


def test_a_bare_command_has_no_arguments():
    assert parse_command_args("/bft") == ""


def test_labels_trigger_the_same_commands():
    assert parse_label_command(run_label(BFT)) == BFT
    assert parse_label_command(run_label(BFT_DEEP)) == BFT_DEEP
    # Метка исхода триггером не является — иначе агент запускал бы себя сам.
    assert parse_label_command("done:bft") is None


def test_mode_is_derived_from_the_command_name():
    assert bft_mode(BFT) == bft.FAST
    assert bft_mode(BFT_DEEP) == bft.DEEP


def test_request_from_a_comment_carries_the_tail_and_the_comment_id():
    payload = {
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 42, "title": "Валюты", "body": "тело"},
        "comment": {"id": 555, "body": "/bft-deep курс берём у ЦБ"},
    }
    req = build_bft_request(payload, bft.DEEP)
    assert (req.repo, req.issue_number, req.mode) == ("acme/widgets", 42, bft.DEEP)
    assert req.instructions == "курс берём у ЦБ"
    assert req.comment_id == 555


def test_request_from_a_label_has_no_arguments_and_nothing_to_react_to():
    payload = {
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 42, "title": "Валюты", "body": "тело"},
    }
    req = build_bft_request(payload, bft.FAST)
    assert req.instructions == ""
    assert req.comment_id is None
