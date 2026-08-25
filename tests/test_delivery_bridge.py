"""Разрешение конфликтов для Delivery-Agent: где именно контур ошибся вживую.

Первый живой прогон на `poh-demo-checkout` провалил три PR подряд с
«конфликт остался», хотя агент разработки конфликт развёл и тесты были зелёные.
Причина — проверка по ИНДЕКСУ git. Эти тесты держат исправление.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import delivery_bridge


def test_resolved_file_without_markers_is_not_conflicted(tmp_path):
    """Агент правит файлы и НИЧЕГО не индексирует.

    По индексу такой файл остаётся `U` до `git add`, и проверка по индексу
    считала разрешённый конфликт неразрешённым.
    """
    (tmp_path / "a.mjs").write_text("test('раз', () => {});\ntest('два', () => {});\n")
    assert delivery_bridge._files_still_conflicted(tmp_path, ["a.mjs"]) == []


def test_leftover_markers_are_caught(tmp_path):
    (tmp_path / "a.mjs").write_text(
        "<<<<<<< HEAD\nмоё\n=======\nчужое\n>>>>>>> origin/main\n")
    assert delivery_bridge._files_still_conflicted(tmp_path, ["a.mjs"]) == ["a.mjs"]


def test_markdown_underline_is_not_a_conflict(tmp_path):
    """`=======` — обычное подчёркивание заголовка в markdown, не маркер."""
    (tmp_path / "README.md").write_text("Заголовок\n=======\n\nтекст\n")
    assert delivery_bridge._files_still_conflicted(tmp_path, ["README.md"]) == []


def test_missing_file_is_not_conflicted(tmp_path):
    """Файл мог быть удалён при разрешении — это исход, а не сбой."""
    assert delivery_bridge._files_still_conflicted(tmp_path, ["нет-такого.mjs"]) == []


def test_conflict_task_names_files_and_forbids_dropping_work():
    task = delivery_bridge._conflict_task("acme/widgets", 42, "main",
                                          ["src/a.mjs", "tests/a.test.mjs"])
    assert "#42" in task and "main" in task
    assert "src/a.mjs" in task and "tests/a.test.mjs" in task
    # Ровно та ошибка, которую агент сделал на первом прогоне: оставил чужую
    # версию целиком и выкинул работу самого PR.
    assert "обе функциональности" in task
    assert "Коммит и пуш НЕ делай" in task


def test_paths_live_under_shared_workspace():
    root, clone = delivery_bridge._paths("acme/widgets", 7)
    assert clone == root / "repo"
    assert str(root).endswith("delivery-acme__widgets-7")


def test_review_request_carries_the_command_first(monkeypatch):
    """`/review` обязана быть ПЕРВОЙ строкой — по ней срабатывает workflow ревью.

    Команда в конце текста читается человеком как просьба, а автоматикой — никак:
    круг вносил правки и ждал ревью, которое не начиналось.
    """
    assert delivery_bridge.REVIEW_REQUEST.startswith("/review")


def test_review_is_fresh_only_for_the_current_head(monkeypatch):
    """Отметка PR-Agent с правильным SHA считается свежей."""
    comments = [{"body": "Persistent review updated to latest commit abc1234"}]
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: comments)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234def567890")
    assert not delivery_bridge._review_is_fresh("o/r", 1, "9999999aaaa")


def test_review_without_any_mark_is_not_fresh(monkeypatch):
    """Ревью не проводилось — значит вердикта нет, а не «всё хорошо»."""
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_review_with_matching_commit_id_is_fresh(monkeypatch):
    """Ревю с совпадающим commit_id считается свежим — точнее времени."""
    commit_time = "2026-01-01T10:00:00Z"
    review_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "APPROVED",
                            "commit_id": "abc1234def567890"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234def567890")


def test_review_without_mark_but_submitted_after_commit_is_fresh(monkeypatch):
    """Ревю без отметки PR-Agent, отправленное ПОСЛЕ коммита — свежее."""
    # Время коммита — 1 января 2026
    commit_time = "2026-01-01T10:00:00Z"
    
    # Ревю отправлено ПОСЛЕ коммита — 2 января 2026
    review_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "APPROVED",
                            "commit_id": "differentcommit"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_review_without_mark_but_submitted_before_commit_is_not_fresh(monkeypatch):
    """Ревю без отметки PR-Agent, отправленное ДО коммита — несвежее."""
    # Время коммита — 2 января 2026
    commit_time = "2026-01-02T10:00:00Z"
    
    # Ревю отправлено ДО коммита — 1 января 2026
    review_time = "2026-01-01T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "APPROVED",
                            "commit_id": "oldcommit"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_review_with_mark_pointing_to_different_commit_still_checks_time(monkeypatch):
    """Устаревшая отметка не блокирует проверку по времени — может быть свежее ревю."""
    commit_time = "2026-01-02T10:00:00Z"
    review_time = "2026-01-03T12:00:00Z"
    
    comments = [{"body": "Review updated until commit old123"}]
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: comments)
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "APPROVED",
                            "commit_id": "newcommit"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    # Должно вернуть True, потому что есть свежее ревю, несмотря на устаревшую отметку
    assert delivery_bridge._review_is_fresh("o/r", 1, "new456def789")


def test_pending_review_is_ignored(monkeypatch):
    """PENDING-ревю не считается — оно ещё не отправлено."""
    commit_time = "2026-01-01T10:00:00Z"
    review_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "PENDING",
                            "commit_id": "abc1234"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_dismissed_review_is_ignored(monkeypatch):
    """DISMISSED-ревю не считается даже если оно свежее."""
    commit_time = "2026-01-01T10:00:00Z"
    review_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [{
                            "submitted_at": review_time, 
                            "state": "DISMISSED",
                            "commit_id": "abc1234"
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_inline_comment_with_matching_commit_id_is_fresh(monkeypatch):
    """Построчное замечание с совпадающим commit_id считается свежим."""
    commit_time = "2026-01-01T10:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий", "user": {"type": "User"}}])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [{
                            "commit_id": "abc1234def567890",
                            "body": "Fix this"
                        }])
    
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234def567890")


def test_bot_comment_after_commit_is_fresh(monkeypatch):
    """Комментарий бота после коммита считается свежим ревью."""
    commit_time = "2026-01-01T10:00:00Z"
    bot_comment_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{
                            "body": "PR Reviewer Guide: please review",
                            "user": {"type": "Bot"},
                            "created_at": bot_comment_time
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_agent_command_comment_is_filtered_out(monkeypatch):
    """Служебные комментарии контура не считаются ревью."""
    commit_time = "2026-01-01T10:00:00Z"
    agent_comment_time = "2026-01-02T12:00:00Z"
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{
                            "body": "/review",
                            "user": {"type": "Bot"},
                            "created_at": agent_comment_time
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    # Служебный комментарий не должен считаться свежим ревью
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_delivery_agent_service_comment_is_filtered_out(monkeypatch):
    """Служебный комментарий Delivery-Agent с маркером <!-- issue-agent --> не считается ревью.
    
    Это критический тест для блокирующего замечания ревьюера. Без этой проверки
    собственный комментарий контура "взял в работу" будет считаться свежим ревю,
    и круг правок начнёт открывать мерж по факту того, что он сам поздоровался.
    """
    commit_time = "2026-01-01T10:00:00Z"
    agent_comment_time = "2026-01-02T12:00:00Z"
    
    # Служебный комментарий Delivery-Agent с HTML-маркером
    service_comment_body = """**Delivery-Agent взял релиз в работу.**

Temporal: …

<!-- issue-agent -->"""
    
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{
                            "body": service_comment_body,
                            "user": {"type": "Bot"},
                            "created_at": agent_comment_time
                        }])
    monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                        lambda repo, sha: commit_time)
    monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                        lambda repo, n, limit=100: [])
    monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                        lambda repo, n, limit=100: [])
    
    # Служебный комментарий НЕ должен считаться свежим ревью
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")


def test_multiple_agent_commands_filtered_correctly(monkeypatch):
    """Все типы служебных комментариев контура должны отсеиваться."""
    commit_time = "2026-01-01T10:00:00Z"
    
    # Различные служебные комментарии с маркером
    agent_comments = [
        "**Delivery-Agent взял релиз в работу.**\n\n<!-- issue-agent -->",
        "PR включён в релиз…\n\n<!-- issue-agent -->",
        "шаг 1 отгружен\n\n<!-- issue-agent -->",
        "/review\n\n<!-- issue-agent -->",  # старый формат тоже должен работать
    ]
    
    for comment_body in agent_comments:
        # Используем замыкание для захвата значения comment_body
        def make_list_comments(body):
            return lambda repo, n, limit=100: [{
                "body": body,
                "user": {"type": "Bot"},
                "created_at": "2026-01-02T12:00:00Z"
            }]
        
        monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                            make_list_comments(comment_body))
        monkeypatch.setattr(delivery_bridge.github_client, "get_commit_timestamp",
                            lambda repo, sha: commit_time)
        monkeypatch.setattr(delivery_bridge.github_client, "list_reviews",
                            lambda repo, n, limit=100: [])
        monkeypatch.setattr(delivery_bridge.github_client, "list_pull_request_comments",
                            lambda repo, n, limit=100: [])
        
        # Ни один из служебных комментариев не должен считаться свежим ревью
        assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234"), \
            f"Comment '{comment_body}' was incorrectly treated as fresh review"
