"""Каталог меток контура: имя, цвет, описание.

Собирается из тех же констант, что и рабочий код. Переписанный руками список
разъезжается с контуром на первой же новой фазе — и разъезд этот тихий: метка
всё равно заведётся при первом применении, просто серой и без описания.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
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
                 "existing-functionality", "feature-request")
PRIORITY_LEVELS = ("P0", "P1", "P2", "P3")
TRIGGERS = {"research-me": "аналитика", "bug-me": "багфикс",
            "build-me": "разработка"}
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


def catalog() -> dict[str, LabelSpec]:
    """Все метки, которыми оперирует контур."""
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
        add(f"{commands.RUN_PREFIX}{command}", RUNNING_COLOR,
            f"Команда /{command} выполняется")
        add(f"{commands.DONE_PREFIX}{command}", DONE_COLOR,
            f"Команда /{command} завершена")
        add(f"{commands.FAILED_PREFIX}{command}", FAILED_COLOR,
            f"Команда /{command} сорвалась")
    for legacy in commands._LEGACY_RUNNING_LABELS.get("analyze", ()):
        add(legacy, RUNNING_COLOR, "Legacy-метка выполнения /analyze")

    add(L.NEEDS_HUMAN_TRIAGE, HUMAN_COLOR, "Ход за человеком")
    add(pr_closing.NEEDS_HUMAN_PR, HUMAN_COLOR, "Круг правок PR требует человека")
    add(L.ORIGIN_AGENT, NEUTRAL_COLOR, "Issue или PR заведён агентом")
    add(L.AGENTS_OFF, "#333333", "Контур не трогает этот Issue")
    add(L.READY_FOR_DEV, DONE_COLOR, "Готово к разработке")
    add(develop.IN_DEVELOPMENT_LABEL, RUNNING_COLOR, "У агента разработки")

    for trigger, what in TRIGGERS.items():
        add(trigger, TRIGGER_COLOR, f"Триггер человека: запустить {what}")
    for flat, description in FLAT.items():
        add(flat, NEUTRAL_COLOR, description)
    return out
