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
    comments = [{"body": "Persistent review updated to latest commit abc1234"}]
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: comments)
    assert delivery_bridge._review_is_fresh("o/r", 1, "abc1234def567890")
    assert not delivery_bridge._review_is_fresh("o/r", 1, "9999999aaaa")


def test_review_without_any_mark_is_not_fresh(monkeypatch):
    """Ревью не проводилось — значит вердикта нет, а не «всё хорошо»."""
    monkeypatch.setattr(delivery_bridge.github_client, "list_comments",
                        lambda repo, n, limit=100: [{"body": "просто комментарий"}])
    assert not delivery_bridge._review_is_fresh("o/r", 1, "abc1234")
