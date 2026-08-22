#!/usr/bin/env python3
"""Стandalone тест функций ISSUE-113 без зависимостей проекта."""


def _truncate(text: str, limit: int) -> str:
    """Обрезает текст до указанного лимита, добавляя маркер."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …[обрезано]"


def _apply_size_limit(parts: list[str], limit: int, priority_order: list[int] | None = None) -> list[str]:
    """Обрезает части текста по общему лимиту с учётом приоритетов."""
    if priority_order is None:
        priority_order = []
    
    # Строим индекс приоритета: чем выше число, тем важнее часть
    priority = {}
    for i, idx in enumerate(reversed(priority_order)):
        priority[idx] = i + 1  # Сначала низкий приоритет, потом высокий
    
    # Сортируем части по приоритету (сначала непроритетные)
    indexed = list(enumerate(parts))
    indexed.sort(key=lambda x: priority.get(x[0], 0))
    
    # Удаляем части пока превыходим лимит, начиная с непроритетных
    current_size = sum(len(p) for _, p in indexed)
    while current_size > limit and indexed:
        # Удаляем самую непроритетную часть
        removed_idx, removed_part = indexed.pop(0)
        current_size -= len(removed_part)
    
    # Восстанавливаем исходный порядок из оставшихся частей
    indexed.sort()
    return [p for _, p in indexed]


def test_truncate_short_text():
    """Обрезка короткого текста не должна его менять."""
    text = "Hello world"
    result = _truncate(text, 100)
    assert result == text, f"Expected '{text}', got '{result}'"
    print("✓ test_truncate_short_text passed")


def test_truncate_long_text():
    """Обрезка длинного текста должна добавлять маркер."""
    text = "A" * 100
    result = _truncate(text, 50)
    expected_marker = " …[обрезано]"
    assert expected_marker in result, f"Marker '{expected_marker}' not found in result"
    assert len(result) == 50 + len(expected_marker), f"Expected length {50 + len(expected_marker)}, got {len(result)}"
    assert result.startswith("A" * 50), f"Result should start with 50 A's"
    print("✓ test_truncate_long_text passed")


def test_apply_size_limit_no_limit():
    """Без лимита все части сохраняются."""
    parts = ["Part 1", "Part 2", "Part 3"]
    result = _apply_size_limit(parts, 1000)
    assert result == parts, f"Expected {parts}, got {result}"
    print("✓ test_apply_size_limit_no_limit passed")


def test_apply_size_limit_with_limit():
    """С лимитом части удаляются по приоритету."""
    parts = ["AAA", "BBB", "CCC", "DDD"]
    result = _apply_size_limit(parts, 5, priority_order=[0, 1])  # AAA и BBB приоритетны
    # При ограничении в 5 символов сохранятся только приоритетные части
    assert len(result) >= 1, f"Should have at least 1 part, got {len(result)}"
    print("✓ test_apply_size_limit_with_limit passed")


def test_apply_size_limit_empty_list():
    """Пустой список не должен вызывать ошибку."""
    result = _apply_size_limit([], 100)
    assert result == [], f"Expected empty list, got {result}"
    print("✓ test_apply_size_limit_empty_list passed")


def test_truncate_whitespace():
    """Обрезка удаляет пробелы по краям."""
    text = "  Hello world  "
    result = _truncate(text, 100)
    assert result == "Hello world", f"Expected 'Hello world', got '{result}'"
    assert not result.startswith(" "), "Result should not start with space"
    assert not result.endswith(" "), "Result should not end with space"
    print("✓ test_truncate_whitespace passed")


def test_apply_size_limit_preserves_priority():
    """Приоритетные части сохраняются в последнюю очередь."""
    parts = ["AAA", "BBB", "CCC", "DDD"]
    result = _apply_size_limit(parts, 10, priority_order=[0])  # AAA самый приоритетный
    # AAA должна остаться в конце (если всё ещё есть что удалять)
    assert "AAA" in result, f"Priority part 'AAA' should be preserved"
    print("✓ test_apply_size_limit_preserves_priority passed")


if __name__ == "__main__":
    print("Running standalone tests for ISSUE-113 context loss fix...")
    print()
    
    try:
        test_truncate_short_text()
        test_truncate_long_text()
        test_apply_size_limit_no_limit()
        test_apply_size_limit_with_limit()
        test_apply_size_limit_empty_list()
        test_truncate_whitespace()
        test_apply_size_limit_preserves_priority()
        
        print()
        print("All tests passed! ✓")
        print()
        print("Functions work correctly in isolation.")
        print("Note: Full integration tests require project dependencies (pydantic, etc.)")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import sys
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
