"""Разбор плана superpowers в шаги исполнения.

Определение шага взято из инструмента, а не выдумано: задача плана несёт блок
Interfaces, и непустой Consumes — объявленная зависимость. Модуль намеренно
чистый: ни сети, ни файлов.
"""

import re

_TASK = re.compile(r"^###\s+Task\s+(\d+)\s*:\s*(.+?)\s*$", re.M)
_CONSUMES = re.compile(r"^-\s*Consumes:\s*(.+?)\s*$", re.M)
_REF = re.compile(r"Task\s+(\d+)", re.I)

_NOTHING = ("ничего", "nothing", "—", "-")


def parse(text: str) -> list[dict]:
    """Шаги плана с объявленными зависимостями."""
    bounds = [(m.start(), m.group(2)) for m in _TASK.finditer(text or "")]
    steps: list[dict] = []
    for position, (start, title) in enumerate(bounds):
        end = bounds[position + 1][0] if position + 1 < len(bounds) else len(text)
        chunk = text[start:end]
        depends_on: list[int] = []
        reason: dict[str, str] = {}
        found = _CONSUMES.search(chunk)
        if found:
            line = found.group(1).strip()
            if line.rstrip(".").lower() not in _NOTHING:
                for ref in _REF.finditer(line):
                    index = int(ref.group(1)) - 1
                    if 0 <= index < len(bounds) and index != position:
                        depends_on.append(index)
                        reason[str(index)] = line
        steps.append({"title": title, "depends_on": depends_on,
                      "depends_reason": reason})
    return steps
