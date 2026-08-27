"""Тесты маскировки блоков кода в Markdown."""

import pytest
from shared import markdown_fences


def test_backticks_fence_is_masked():
    """Блок кода из тройных обратных кавычек маскируется пробелами."""
    text = """Some text
```python
def hello():
    print("hello")
```
More text"""
    masked = markdown_fences.mask_code_fences(text)
    # Содержимое забора должно быть пробелами
    assert "hello" not in masked
    assert "python" not in masked
    # Текст вне забора сохранённ
    assert "Some text" in masked
    assert "More text" in masked
    # Переводы строк сохранены
    assert masked.count("\n") == text.count("\n")


def test_tildes_fence_is_masked():
    """Блок кода из тройных тильд маскируется пробелами."""
    text = """Some text
~~~python
def hello():
    print("hello")
~~~
More text"""
    masked = markdown_fences.mask_code_fences(text)
    # Содержимое забора должно быть пробелами
    assert "hello" not in masked
    assert "python" not in masked
    # Текст вне забора сохранён
    assert "Some text" in masked
    assert "More text" in masked
    # Переводы строк сохранены
    assert masked.count("\n") == text.count("\n")


def test_four_backticks_fence_is_masked():
    """Блок кода из четырёх обратных кавычек маскируется."""
    text = """Text
````
code with three backticks inside: ```
````
More"""
    masked = markdown_fences.mask_code_fences(text)
    assert "code with three" not in masked
    assert "More" in masked


def test_four_tildes_fence_is_masked():
    """Блок кода из четырёх тильд маскируется."""
    text = """Text
~~~~
code with three tildes inside: ~~~
~~~~
More"""
    masked = markdown_fences.mask_code_fences(text)
    assert "code with three" not in masked
    assert "More" in masked


def test_closing_fence_must_be_same_symbol():
    """Заборы не должны смешиваться: backticks не закрывают tildes."""
    text = """Text
~~~python
code
```
More"""
    masked = markdown_fences.mask_code_fences(text)
    # Backticks внутри tildes-забора считаются частью кода, не закрытием
    # Забор остаётся открытым до конца или до настоящего закрывающего ~~~
    # В этом тексте забор не закрыт
    assert masked.count("More") == 0  # "More" маскирован, т.к. забор открыт


def test_closing_fence_must_be_not_shorter():
    """Закрывающий забор должен быть не короче открывающего."""
    text = """Text
````python
content
```
More text"""
    masked = markdown_fences.mask_code_fences(text)
    # Три backticks внутри четырёхбэковского забора не закрывают его
    assert "More text" not in masked  # забор ещё открыт


def test_unclosed_fence_masks_to_end_of_text():
    """Незакрытый забор считается открытым до конца текста."""
    text = """Text
```python
code
### Task 1
More text"""
    masked = markdown_fences.mask_code_fences(text)
    # Всё после открывающего забора маскируется
    assert "### Task 1" not in masked
    assert "More text" not in masked


def test_has_unclosed_fence_detects_unclosed_backticks():
    """Функция обнаруживает незакрытый забор из backticks."""
    text = """Text
```python
code
### Task 1
More"""
    assert markdown_fences.has_unclosed_fence(text) is True


def test_has_unclosed_fence_detects_unclosed_tildes():
    """Функция обнаруживает незакрытый забор из tildes."""
    text = """Text
~~~python
code
### Task 1
More"""
    assert markdown_fences.has_unclosed_fence(text) is True


def test_has_unclosed_fence_returns_false_for_closed_fences():
    """Функция возвращает False, если все заборы закрыты."""
    text = """Text
```python
code
```
More
~~~
code2
~~~
End"""
    assert markdown_fences.has_unclosed_fence(text) is False


def test_has_unclosed_fence_empty_text():
    """Функция возвращает False для пустого текста."""
    assert markdown_fences.has_unclosed_fence("") is False
    assert markdown_fences.has_unclosed_fence(None) is False
