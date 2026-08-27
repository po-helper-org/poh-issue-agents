"""Блоки тела Issue: контур правит только своё.

Тело правят и человек, и контур. Без границ они затирают друг друга: дописывание
в конец плодит дубли разделов, а перезапись целиком уносит текст человека.
"""

import pytest

from shared import issue_blocks


def test_write_into_empty_body_appends_block():
    body = "Описание задачи от человека."
    result = issue_blocks.write(body, issue_blocks.MVP_PLAN, "- [ ] 1. Шаг")
    assert "Описание задачи от человека." in result
    assert issue_blocks.read(result, issue_blocks.MVP_PLAN) == "- [ ] 1. Шаг"


def test_write_replaces_block_and_keeps_human_text():
    body = issue_blocks.write("Текст человека.", issue_blocks.MVP_PLAN, "старое")
    result = issue_blocks.write(body, issue_blocks.MVP_PLAN, "новое")
    assert issue_blocks.read(result, issue_blocks.MVP_PLAN) == "новое"
    assert "старое" not in result
    assert "Текст человека." in result
    assert result.count("harness:mvp-plan:start") == 1


def test_two_blocks_are_independent():
    body = issue_blocks.write("Текст.", issue_blocks.MVP_PLAN, "план")
    body = issue_blocks.write(body, issue_blocks.GROW, "находки")
    assert issue_blocks.read(body, issue_blocks.MVP_PLAN) == "план"
    assert issue_blocks.read(body, issue_blocks.GROW) == "находки"


def test_read_absent_block_is_none():
    assert issue_blocks.read("просто текст", issue_blocks.MVP_PLAN) is None


def test_body_without_markers_survives_untouched():
    """Тело, где маркеров нет вовсе, не должно потерять ни строки."""
    body = "Строка 1\n\nСтрока 2"
    result = issue_blocks.write(body, issue_blocks.GROW, "x")
    assert result.startswith(body)


def test_write_refuses_content_containing_its_own_end_marker():
    """Ревью, находка 1 (Critical). Нежадный `.*?` в парсере останавливается на
    первом же вхождении конечного маркера. Если его текст есть в самом
    содержимом блока, запись раньше молча резала хвост тела и оставляла
    осиротевший кусок, который ни один следующий read()/write() не подбирал.
    Теперь такая запись отказывает громко, а не портит тело.
    """
    content = "верхняя строка\n<!-- harness:grow:end -->\nнижняя строка"
    with pytest.raises(ValueError):
        issue_blocks.write("Текст.", issue_blocks.GROW, content)


def test_write_cannot_distinguish_human_marker_illustration_from_real_block():
    """Ревью, находка 2 (Critical, известное и задокументированное ограничение).

    Текст человека, дословно совпадающий с форматом маркера (ровно одна пара
    start/end), от настоящего блока неотличим в принципе — это не баг, который
    чинится, а свойство любой текстовой разметки без экранирования. Пункты 1
    и 2 из ревью не убирают этот конкретный случай (структура здесь валидна:
    ровно одна пара), они только гарантируют, что источником двусмысленности
    может быть исключительно текст человека, а не сам контур (находка 1) и не
    более грубая порча (находка 3). Тест фиксирует эту границу — см. докстринг
    модуля.
    """
    human = (
        "Смотрите, формат будет такой:\n"
        "<!-- harness:mvp-plan:start -->\nплан тут\n<!-- harness:mvp-plan:end -->\n"
        "Это иллюстрация, а не блок бота."
    )
    result = issue_blocks.write(human, issue_blocks.MVP_PLAN, "реальный план")
    assert issue_blocks.read(result, issue_blocks.MVP_PLAN) == "реальный план"
    assert "план тут" not in result


def test_orphaned_start_marker_is_corrupted_body_not_append_signal():
    """Ревью, находка 3 (Important). Старт без конца (человек правил markdown
    руками, тело обрезано апстримом) раньше уводил write() в ветку добавления:
    появлялся второй `start`, осиротевший первый оставался, а read() тем
    временем тихо отдавал None, маскируя порчу под «блока просто нет». Теперь
    и read(), и write() считают вхождения маркеров и честно отказывают на
    структуре, которая не равна нулю и не равна ровно одной паре.
    """
    body = "Планирование.\n<!-- harness:grow:start -->\nобрезано апстримом"
    with pytest.raises(ValueError):
        issue_blocks.write(body, issue_blocks.GROW, "новые находки")
    with pytest.raises(ValueError):
        issue_blocks.read(body, issue_blocks.GROW)


def test_read_and_write_accept_none_body():
    """Ревью, находка 4 (Minor). GitHub отдаёт `body: null` у Issue без
    описания, и это уже принималось и осмысленно обрабатывалось (`body or
    ""`) — сигнатуры честно объявляли `str`, хотя реально принимают
    `str | None`, как это сделано в `shared/agent_comment.py`. Поведение не
    менялось, тест закрепляет его как основание для правки типов.
    """
    assert issue_blocks.read(None, issue_blocks.GROW) is None
    result = issue_blocks.write(None, issue_blocks.GROW, "находки")
    assert issue_blocks.read(result, issue_blocks.GROW) == "находки"
