"""Тесты для ISSUE-113 — проверка сохранения контекста в разработке.

Усечение постановки (`_apply_size_limit`) задача 7 сняла целиком вместе с
общим потолком: контекст теперь лежит файлами `.harness/`, а не пересказом с
жёстким лимитом.

L5 (ревью задачи 7): `_fetch_decomposition_plan`, `_fetch_subtasks` и
`_fetch_dev_comments` были отключены от `_dev_prepare` в задаче 7, но
оставлены в коде и держались зелёными одиннадцатью тестами этого файла (из
которых на сами эти три функции приходилось шесть — остальные пять
проверяли `_truncate`/`_refresh_issue_body`, которые работают и сейчас) —
впечатление, что контекст декомпозиции и обсуждения по-прежнему доезжает,
было ложным. Решение: удалить вместе с тестами, а не вернуть в дело.
Причины: (а) план декомпозиции и подзадачи функционально заменены
`shared/decomposition.py` — структурированным механизмом с зависимостями и
релизами (MVP/GROW/SUPPORT), а не поиском по маркеру "🧩 Декомпозиция" в
комментариях и строке "root-issue: #N" среди ВСЕХ открытых Issue репозитория;
(б) `_fetch_subtasks` ничем не ограничен по объёму — оживить его значило бы
вернуть именно тот канал неограниченного роста постановки, ради устранения
которого затевалась задача 7; (в) `task_context.PLAN` уже зарезервирован под
плановый контекст будущей стадии декомпозиции — параллельный путь через
комментарии избыточен. `_fetch_dev_comments` не имеет отдельной замены, но и
отдельной причины возвращать именно её не нашлось: недостающий контекст
обсуждения, если понадобится, естественнее лёг бы файлом `.harness/`
(по образцу M4), а не инлайном в постановку, как раньше.
"""
from activities import (
    _truncate,
    _refresh_issue_body,
)


def test_truncate_short_text():
    """Обрезка короткого текста не должна его менять."""
    text = "Hello world"
    result = _truncate(text, 100)
    assert result == text


def test_truncate_long_text():
    """Обрезка длинного текста должна добавлять маркер."""
    from shared import task_context

    text = "A" * 100
    result = _truncate(text, 50)
    assert len(result) == 50 + len(" " + task_context.TRUNCATION_MARKER)
    assert task_context.TRUNCATION_MARKER in result
    assert result.startswith("A" * 50)


def test_refresh_issue_body_success(monkeypatch):
    """Успешное обновление тела Issue."""
    fresh_body = "Updated body text"
    monkeypatch.setattr(
        "activities.github_client.get_issue",
        lambda repo, number: {"body": fresh_body}
    )

    issue = type("Issue", (), {
        "repo": "o/r",
        "issue_number": 42,
        "body": "Old body"
    })()

    result = _refresh_issue_body(issue)
    assert result == fresh_body


def test_refresh_issue_body_failure_fallback(monkeypatch):
    """При ошибке используется старое тело."""
    def boom(repo, number):
        raise RuntimeError("GitHub API error")

    monkeypatch.setattr("activities.github_client.get_issue", boom)

    issue = type("Issue", (), {
        "repo": "o/r",
        "issue_number": 42,
        "body": "Old body"
    })()

    result = _refresh_issue_body(issue)
    assert result == "Old body"  # Fallback to old body


def test_truncate_whitespace():
    """Обрезка удаляет пробелы по краям."""
    text = "  Hello world  "
    result = _truncate(text, 100)
    assert result == "Hello world"
    assert not result.startswith(" ")
    assert not result.endswith(" ")
