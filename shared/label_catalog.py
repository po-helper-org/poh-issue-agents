"""Каталог меток Issue-Agent — единый список всех меток, которые использует контур.

Каталог собирается из канонических констант — тех же, что использует рабочий код.
Это гарантирует, что новая метка, добавленная в код, не забудется в каталоге:
тесты проверяют, что в каталоге есть ровно те же метки, что и в константах.

Каждый источник истины — одна константа или набор констант в shared/:
- Фазы: shared/lifecycle.PHASES → метки вида "phase:*"
- Команды: shared/commands._COMMANDS → метки вида "run:*", "done:*", "failed:*"
- Внутренние: shared.labels → advisor:*, priority:*, плоские метки

При добавлении новой метки:
1. Добавь константу в соответствующий shared/ модуль
2. Добавь её в набор меток (ADVISOR_LABELS, PRIORITY_LABELS, FLAT_LABELS)
3. Обнови тест, если нужно
4. Каталог автоматически подхватит изменение

Модуль намеренно без зависимостей: его читают и вебхук, и воркер.
"""

from typing import FrozenSet

from shared import commands, labels, lifecycle


def _all_phase_labels() -> FrozenSet[str]:
    """Метки фаз: phase:* по shared/lifecycle.PHASES."""
    return frozenset(f"phase:{phase}" for phase in lifecycle.PHASES)


def _all_command_labels() -> FrozenSet[str]:
    """Метки команд: run:*, done:*, failed:* по shared/commands."""
    result = set()
    for cmd in commands._COMMANDS:
        result.add(commands.run_label(cmd))
        result.add(commands.done_label(cmd))
        result.add(commands.failed_label(cmd))
    # Legacy labels for ANALYZE command
    result.update(commands._LEGACY_RUNNING_LABELS.get(commands.ANALYZE, ()))
    return frozenset(result)


def _all_internal_labels() -> FrozenSet[str]:
    """Внутренние метки Issue-Agent: advisor:*, priority:*, плоские метки."""
    return labels.ADVISOR_LABELS | labels.PRIORITY_LABELS | labels.FLAT_LABELS


# --- Публичное API ---

def all_labels() -> FrozenSet[str]:
    """Все метки, которые использует контур Issue-Agent.
    
    Функция собирает метки из канонических констант и гарантирует, что каталог
    всегда синхронизирован с кодом. Если добавишь новую метку в код, но не
    добавишь её в соответствующий набор констант, она не появится здесь — и
    тесты это заметят.
    """
    return (
        _all_phase_labels() |
        _all_command_labels() |
        _all_internal_labels() |
        # Протокольные метки контура (общие для всех агентов)
        frozenset({
            labels.NEEDS_HUMAN_TRIAGE,
            labels.LEGACY_NEEDS_HUMAN_TRIAGE,
            labels.READY_FOR_DEV,
            labels.AGENTS_OFF,
            labels.ORIGIN_AGENT,
        })
    )


def label_families() -> dict[str, FrozenSet[str]]:
    """Метки по семействам для проверки целостности.
    
    Каждое семейство — frozenset, потому что порядок меток не важен, а
    неизменяемость гарантирует, что тест не будет случайно модифицировать
    каталог.
    """
    return {
        "phases": _all_phase_labels(),
        "commands": _all_command_labels(),
        "advisors": labels.ADVISOR_LABELS,
        "priorities": labels.PRIORITY_LABELS,
        "flat": labels.FLAT_LABELS,
        "protocol": frozenset({
            labels.NEEDS_HUMAN_TRIAGE,
            labels.LEGACY_NEEDS_HUMAN_TRIAGE,
            labels.READY_FOR_DEV,
            labels.AGENTS_OFF,
            labels.ORIGIN_AGENT,
        }),
    }
