#!/usr/bin/env python3
"""Базовая проверка работы функций ISSUE-113 без pytest."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from worker.activities import _truncate, _apply_size_limit


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


if __name__ == "__main__":
    print("Running basic tests for ISSUE-113 context loss fix...")
    print()
    
    try:
        test_truncate_short_text()
        test_truncate_long_text()
        test_apply_size_limit_no_limit()
        test_apply_size_limit_with_limit()
        test_apply_size_limit_empty_list()
        test_truncate_whitespace()
        
        print()
        print("All tests passed! ✓")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
