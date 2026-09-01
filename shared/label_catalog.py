"""Единый каталог меток Issue-Agent: имена, цвета и описания.

Имена собираются из тех же констант, что и рабочий код. Это не даёт каталогу
тихо разъехаться с вебхуком или воркером при добавлении новой фазы, команды или
решения человека.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import commands, develop, lifecycle, pr_closing
from . import labels as L

PHASE_COLOR = "#1F75CB"
ADVISOR_COLOR = "#6E49CB"
PRIORITY_COLOR = "#ED9121"
RUNNING_COLOR = "#FC9403"
DONE_COLOR = "#108548"
FAILED_COLOR = "#DD2B0E"
HUMAN_COLOR = "#E24329"
TRIGGER_COLOR = "#2DA160"
NEUTRAL_COLOR = "#666666"

ADVISOR_KINDS = ("answered", "bug", "consultation", "error",
                 "existing-functionality", "feature-request", "product-research")
PRIORITY_LEVELS = ("P0", "P1", "P2", "P3")

_HUMAN_DECISION_DESCRIPTIONS = {
    "research-me": "Триггер человека: запустить аналитику",
    "bug-me": "Триггер человека: запустить багфикс",
    "build-me": "Триггер человека: запустить разработку",
    "not-duplicate": "Человек считает Issue не дубликатом — контур возвращает его в работу",
    "confirm-duplicate": "Человек подтверждает дубликат — контур снимает Issue с обработки, но на GitHub его не закрывает",
}
TRIGGERS = {name: _HUMAN_DECISION_DESCRIPTIONS[name]
            for name in L.HUMAN_DECISION_LABELS}
FLAT = {
    "bot-authored": "Issue заведён ботом",
    "security-sensitive": "Затрагивает безопасность",
    "needs-clarification": "Нужны уточнения от автора",
    "spam": "Отброшен как спам",
    "duplicate": "Дубликат",
    "possible-duplicate": "Возможный дубликат",
    "estimated": "Оценка трудоёмкости опубликована",
}


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str


def _all_phase_labels() -> frozenset[str]:
    return frozenset(lifecycle.phase_label(phase) for phase in lifecycle.PHASES)


def _all_command_labels() -> frozenset[str]:
    result: set[str] = set()
    # _COMMANDS maps slash-command names to the canonical label suffix.
    for command in commands._COMMANDS.values():
        # Команды из NO_RUN_LABEL_COMMANDS не запускают дорогую стадию — меток
        # прогона у них быть не должно, иначе на задачах появится бессмысленная
        # run:harness-answer.
        if command in commands.NO_RUN_LABEL_COMMANDS:
            continue
        result.add(commands.run_label(command))
        result.add(commands.done_label(command))
        result.add(commands.failed_label(command))
    result.update(commands._LEGACY_RUNNING_LABELS.get(commands.ANALYZE, ()))
    return frozenset(result)


def _protocol_labels() -> frozenset[str]:
    return frozenset({
        L.NEEDS_HUMAN_TRIAGE,
        L.LEGACY_NEEDS_HUMAN_TRIAGE,
        L.READY_FOR_DEV,
        L.AGENTS_OFF,
        L.ORIGIN_AGENT,
    })


def _control_labels() -> frozenset[str]:
    return frozenset({pr_closing.NEEDS_HUMAN_PR, develop.IN_DEVELOPMENT_LABEL})


def _all_internal_labels() -> frozenset[str]:
    return L.ADVISOR_LABELS | L.PRIORITY_LABELS | L.FLAT_LABELS


def label_families() -> dict[str, frozenset[str]]:
    """Метки по семействам; каждое семейство неизменяемо."""
    return {
        "phases": _all_phase_labels(),
        "commands": _all_command_labels(),
        "advisors": L.ADVISOR_LABELS,
        "priorities": L.PRIORITY_LABELS,
        "flat": L.FLAT_LABELS,
        "protocol": _protocol_labels(),
        "control": _control_labels(),
        "triggers": frozenset(TRIGGERS),
    }


def all_labels() -> frozenset[str]:
    """Все метки, которыми оперирует контур Issue-Agent."""
    result: set[str] = set()
    for family in label_families().values():
        result.update(family)
    return frozenset(result)


def catalog() -> dict[str, LabelSpec]:
    """Все метки, которыми оперирует контур, с цветом и описанием."""
    out: dict[str, LabelSpec] = {}

    def add(name: str, color: str, description: str) -> None:
        out[name] = LabelSpec(name=name, color=color, description=description)

    for phase in lifecycle.PHASES:
        add(lifecycle.phase_label(phase), PHASE_COLOR, "Фаза жизненного цикла Issue")
    for kind in ADVISOR_KINDS:
        add(f"advisor:{kind}", ADVISOR_COLOR, "Классификация обращения")
    for level in PRIORITY_LEVELS:
        add(f"priority:{level}", PRIORITY_COLOR, "Расчётный приоритет")
    for command in commands._COMMANDS.values():
        # Тот же пропуск, что и в _all_command_labels: этот перебор идёт в
        # bootstrap_labels.py и реально заводит метки в GitHub — без исключения
        # там завелась бы run:harness-answer, даже если её нет в all_labels().
        if command in commands.NO_RUN_LABEL_COMMANDS:
            continue
        add(commands.run_label(command), RUNNING_COLOR,
            f"Команда /{command} выполняется")
        add(commands.done_label(command), DONE_COLOR,
            f"Команда /{command} завершена")
        add(commands.failed_label(command), FAILED_COLOR,
            f"Команда /{command} сорвалась")
    for legacy in commands._LEGACY_RUNNING_LABELS.get(commands.ANALYZE, ()):
        add(legacy, RUNNING_COLOR, "Legacy-метка выполнения /analyze")

    add(L.NEEDS_HUMAN_TRIAGE, HUMAN_COLOR, "Ход за человеком")
    add(L.LEGACY_NEEDS_HUMAN_TRIAGE, HUMAN_COLOR, "Историческая очередь к человеку")
    add(pr_closing.NEEDS_HUMAN_PR, HUMAN_COLOR, "Круг правок PR требует человека")
    add(L.ORIGIN_AGENT, NEUTRAL_COLOR, "Issue или PR заведён агентом")
    add(L.AGENTS_OFF, "#333333", "Контур не трогает этот Issue")
    add(L.READY_FOR_DEV, DONE_COLOR, "Готово к разработке")
    add(develop.IN_DEVELOPMENT_LABEL, RUNNING_COLOR, "У агента разработки")

    for trigger, description in TRIGGERS.items():
        add(trigger, TRIGGER_COLOR, description)
    for flat, description in FLAT.items():
        add(flat, NEUTRAL_COLOR, description)
    return out
