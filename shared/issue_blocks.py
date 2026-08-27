"""Размеченные блоки тела Issue — граница между текстом человека и контура.

Контур правит ТОЛЬКО то, что лежит между своими маркерами. Всё остальное тело
принадлежит человеку и не трогается: дописывание в конец плодило бы дубли
разделов при каждом обновлении плана, а перезапись целиком уносила бы
постановку.

Модуль намеренно чистый: ни сети, ни GitHub — как `lifecycle.py`.
"""

import re

MVP_PLAN = "mvp-plan"
GROW = "grow"


def _markers(name: str) -> tuple[str, str]:
    return f"<!-- harness:{name}:start -->", f"<!-- harness:{name}:end -->"


def read(body: str, name: str) -> str | None:
    """Содержимое блока либо None, если блока нет."""
    start, end = _markers(name)
    pattern = re.compile(re.escape(start) + r"\n(.*?)\n" + re.escape(end), re.S)
    found = pattern.search(body or "")
    return found.group(1) if found else None


def write(body: str, name: str, content: str) -> str:
    """Тело с заменённым (или добавленным) блоком."""
    start, end = _markers(name)
    block = f"{start}\n{content}\n{end}"
    pattern = re.compile(re.escape(start) + r"\n.*?\n" + re.escape(end), re.S)
    if pattern.search(body or ""):
        return pattern.sub(lambda _: block, body, count=1)
    tail = "" if (body or "").endswith("\n") else "\n"
    return f"{body or ''}{tail}\n{block}\n"
