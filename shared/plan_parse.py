"""Разбор плана superpowers в шаги исполнения.

Определение шага взято из инструмента, а не выдумано: задача плана несёт блок
Interfaces, и непустой Consumes — объявленная зависимость. Модуль намеренно
чистый: ни сети, ни файлов, ни Temporal.
"""

import re

from shared import markdown_fences
from shared.markdown_fences import mask_code_fences

_TASK = re.compile(r"^###\s+Task\s+(\d+)\s*:\s*(.+?)\s*$", re.M)
# Ревью, находка F3: отступ перед буллетом — обычная форма вложенного пункта
# списка внутри блока Interfaces, а не аномалия («-» не обязан начинать
# строку); регистр слова Consumes не несёт смысла, который стоило бы
# проверять. `[ \t]*` перед «-» и `re.I` снимают оба ограничения — раньше
# отступ или строчная буква молча превращали объявленную зависимость в
# отсутствие зависимости, неотличимое от настоящего Consumes: ничего.
_CONSUMES = re.compile(r"^[ \t]*-\s*Consumes:\s*(.+?)\s*$", re.M | re.I)
_REF = re.compile(r"Task\s+(\d+)", re.I)

_NOTHING = ("ничего", "nothing", "—", "-")


def parse(text: str) -> list[dict]:
    """Шаги плана с объявленными зависимостями.

    Блоки кода (тройные и более обратные кавычки/тильды) в разборе не
    участвуют (ревью, находка F2): план часто цитирует сам себя как пример
    внутри описания задачи (см. `docs/superpowers/plans/*`, задача про этот же
    модуль), и такая цитата не должна читаться как настоящий шаг или
    настоящая зависимость. Маскировка общая с `worker.activities` — см.
    `shared.markdown_fences`.

    Незакрытый забор кода — громкий отказ (ревью, находка 1): молчаливая
    потеря всех задач после него опаснее, чем явный отказ разбора.
    """
    text = text or ""
    # Проверка на незакрытый забор перед маскировкой, чтобы явно отказать
    if markdown_fences.has_unclosed_fence(text):
        raise ValueError(
            "Plan contains unclosed code fence (``` or ~~~). "
            "All tasks after unclosed fence are hidden in mask. "
            "Close all code fences before parsing plan."
        )
    haystack = mask_code_fences(text)
    bounds = [(m.start(), int(m.group(1)), m.group(2))
              for m in _TASK.finditer(haystack)]

    # Ссылка «Task N» резолвится по НОМЕРУ из заголовка, а не по позиции в
    # списке заголовков (ревью, находка F1). План не обязан быть пронумерован
    # подряд и по порядку: Task 9 может ссылаться на Task 5, стоящую не
    # пятой по счёту, а задачи в тексте могут идти не по номерам вовсе.
    # Прежний код проецировал N на индекс N-1 этого списка — совпадение с
    # реальной задачей верно только для плана без пропусков и перестановок,
    # а самоссылка (единственный сигнал «зависимости нет», кроме явного
    # Consumes: ничего) проверялась тем же индексом вместо номера.
    #
    # Номер, повторённый в двух и более заголовках, — реальность, которую
    # план не запрещает (ссылка на этот же модуль внутри задачи 12 плана
    # этого репозитория цитирует пример с Task 1/Task 2 — теми же номерами,
    # что и первые настоящие задачи плана, пока не помаскированы находкой
    # F2). Ссылка на такой номер неоднозначна: неясно, какую из одноимённых
    # задач имели в виду, а угадывать одну из них — то же фабрикование
    # ребра, которого модуль намеренно избегает. Поэтому у неоднозначного
    # номера, как и у номера, которого в плане нет вовсе, нет резолвящейся
    # позиции — ссылка молча не становится рёбром, а не падает и не гадает.
    positions_by_number: dict[int, list[int]] = {}
    for position, (_start, number, _title) in enumerate(bounds):
        positions_by_number.setdefault(number, []).append(position)

    steps: list[dict] = []
    for position, (start, _number, title) in enumerate(bounds):
        end = bounds[position + 1][0] if position + 1 < len(bounds) else len(haystack)
        chunk = haystack[start:end]
        depends_on: list[int] = []
        reason: dict[str, str] = {}
        found = _CONSUMES.search(chunk)
        if found:
            line = found.group(1).strip()
            if line.rstrip(".").lower() not in _NOTHING:
                for ref in _REF.finditer(line):
                    targets = positions_by_number.get(int(ref.group(1)), [])
                    if len(targets) != 1:
                        continue  # номера нет в плане, либо он неоднозначен
                    target = targets[0]
                    if target != position:
                        depends_on.append(target)
                        reason[str(target)] = line
        steps.append({"title": title, "depends_on": depends_on,
                      "depends_reason": reason})
    return steps
