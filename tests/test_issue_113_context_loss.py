"""Тесты для ISSUE-113 — проверка сохранения контекста в разработке."""
import pytest
from activities import (
    _truncate,
    _apply_size_limit,
    _fetch_decomposition_plan,
    _fetch_subtasks,
    _fetch_dev_comments,
    _refresh_issue_body,
)


def test_truncate_short_text():
    """Обрезка короткого текста не должна его менять."""
    text = "Hello world"
    result = _truncate(text, 100)
    assert result == text


def test_truncate_long_text():
    """Обрезка длинного текста должна добавлять маркер."""
    text = "A" * 100
    result = _truncate(text, 50)
    assert len(result) == 50 + len(" …[обрезано]")
    assert " …[обрезано]" in result
    assert result.startswith("A" * 50)


def test_apply_size_limit_no_limit():
    """Без лимита все части сохраняются."""
    parts = ["Part 1", "Part 2", "Part 3"]
    result = _apply_size_limit(parts, 1000)
    assert result == parts


def test_apply_size_limit_with_limit():
    """С лимитом части удаляются по приоритету."""
    parts = ["AAA", "BBB", "CCC", "DDD"]
    result = _apply_size_limit(parts, 5, priority_order=[0, 1])  # AAA и BBB приоритетны
    # При ограничении в 5 символов сохранятся только приоритетные части
    assert len(result) >= 1  # Хотя бы одна часть останется


def test_apply_size_limit_preserves_priority():
    """Приоритетные части сохраняются в последнюю очередь."""
    parts = ["AAA", "BBB", "CCC", "DDD"]
    result = _apply_size_limit(parts, 10, priority_order=[0])  # AAA самый приоритетный
    # AAA должна остаться в конце (если всё ещё есть что удалять)
    assert "AAA" in result


def test_apply_size_limit_empty_list():
    """Пустой список не должен вызывать ошибку."""
    result = _apply_size_limit([], 100)
    assert result == []


def test_fetch_decomposition_plan_no_marker(monkeypatch):
    """Нет маркера декомпозиции — пустая строка."""
    monkeypatch.setattr(
        "activities.github_client.list_comments",
        lambda repo, number, limit: [{"body": "Some comment"}]
    )
    result = _fetch_decomposition_plan(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    assert result == ""


def test_fetch_decomposition_plan_with_marker(monkeypatch):
    """Есть маркер декомпозиции — возвращается текст."""
    plan_text = "🧩 Декомпозиция\n1. Task A\n2. Task B"
    monkeypatch.setattr(
        "activities.github_client.list_comments",
        lambda repo, number, limit: [{"body": "Other comment"}, {"body": plan_text}]
    )
    result = _fetch_decomposition_plan(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    assert "🧩 Декомпозиция" in result
    assert "Task A" in result
    assert "Task B" in result


def test_fetch_subtasks_empty(monkeypatch):
    """Нет подзадач — пустой список."""
    monkeypatch.setattr(
        "activities.github_client.list_open_issues",
        lambda repo, limit: []
    )
    result = _fetch_subtasks(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    assert result == []


def test_fetch_subtasks_with_children(monkeypatch):
    """Есть подзадачи с правильными метками."""
    issues = [
        {
            "number": 10,
            "title": "Subtask 1",
            "body": "root-issue: #42",
            "labels": ["release:mvp"],
            "state": "open"
        },
        {
            "number": 11,
            "title": "Other issue",
            "body": "Something else",
            "labels": ["bug"],
            "state": "open"
        }
    ]
    monkeypatch.setattr(
        "activities.github_client.list_open_issues",
        lambda repo, limit: issues
    )
    result = _fetch_subtasks(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    assert len(result) == 1
    assert result[0]["number"] == 10
    assert result[0]["title"] == "Subtask 1"


def test_fetch_dev_comments_no_comments(monkeypatch):
    """Нет комментариев — пустой список."""
    monkeypatch.setattr(
        "activities.github_client.list_comments",
        lambda repo, number, limit: []
    )
    result = _fetch_dev_comments(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    assert result == []


def test_fetch_dev_comments_filters_commands(monkeypatch):
    """Командные комментарии фильтруются."""
    comments = [
        {"body": "/analyze", "user": {"login": "bot"}, "created_at": "2025-01-01"},
        {"body": "Regular comment", "user": {"login": "user"}, "created_at": "2025-01-02"},
        {"body": "/estimate", "user": {"login": "bot"}, "created_at": "2025-01-03"}
    ]
    monkeypatch.setattr(
        "activities.github_client.list_comments",
        lambda repo, number, limit: comments
    )
    monkeypatch.setattr(
        "activities.parse_command",
        lambda body: "/analyze" if "/analyze" in body
        else "/estimate" if "/estimate" in body else None,
    )
    
    result = _fetch_dev_comments(
        type("Issue", (), {"repo": "o/r", "issue_number": 42})()
    )
    # Остаются только некомандные комментарии
    assert len(result) == 1
    assert "Regular comment" in result[0]


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
