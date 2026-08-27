"""Блоки тела Issue: контур правит только своё.

Тело правят и человек, и контур. Без границ они затирают друг друга: дописывание
в конец плодит дубли разделов, а перезапись целиком уносит текст человека.
"""

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
