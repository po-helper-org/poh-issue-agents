"""
Рендер комментария с оценкой.

Чистая функция: Estimate + факты + контекст -> markdown. Вынесено из
activities.py, потому что это единственная часть, которую придётся править
чаще всего (формулировки), и она не должна тянуть за собой ни Temporal,
ни GitHub, ни LLM.

Комментарий обязан показывать, ОТКУДА взялось число: разбор декомпозиции,
оба метода с расхождением, каждый применённый риск и каждая надбавка,
источники контекста. Число без этого — просто мнение.
"""

from estimation import (
    ARTIFACT_TYPE_RU,
    CONFIDENCE_RU,
    WORK_TYPE_RU,
    Estimate,
    EstimationFacts,
    positive_units,
)
from shared.workflow_types import EstimationContext


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 100 in (11, 12, 13, 14):
        return many
    if count % 10 == 1:
        return one
    if count % 10 in (2, 3, 4):
        return few
    return many


def _number(value: float) -> str:
    """Число без хвостовых нулей: 1.5, 2, 0.8."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _cell(text: str) -> str:
    """Текст, безопасный для ячейки markdown-таблицы. Имена единиц работы и
    обоснования модель извлекает из текста Issue, а там встречаются и `|`
    (схемы, CLI-флаги, pipe-форматы), и переводы строк — без экранирования
    любой из них разваливает таблицу в комментарии."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _days(value: float) -> str:
    return f"{_number(value)} дн"


def _sources_line(context: EstimationContext) -> str:
    parts = ["описание задачи"]
    if context.thread:
        count = len(context.thread)
        word = _plural(count, "комментарий", "комментария", "комментариев")
        parts.append(f"{count} {word} обсуждения")
    if context.branch:
        count = len(context.artifacts)
        word = _plural(count, "файл", "файла", "файлов")
        parts.append(f"ветка `{context.branch}` ({count} {word})")
    line = "Оценка построена на: " + ", ".join(parts) + "."
    if context.truncated:
        line += " Часть контекста обрезана по лимиту объёма."
    return line


def _factors_section(estimate: Estimate) -> list[str]:
    lines = ["### Риски и надбавки", ""]
    if not estimate.risks and not estimate.penalties:
        lines.append("Не применялись: контекстных рисков не выявлено, "
                     "во входных данных ничего не пропущено.")
        return lines
    for risk in estimate.risks:
        lines.append(
            f"- Риск «{risk.label}»: +{_number(risk.min_value)} к реалистичному, "
            f"+{_number(risk.max_value)} к пессимистичному сценарию."
        )
    for penalty in estimate.penalties:
        lines.append(
            f"- Надбавка «{penalty.label}»: +{_number(penalty.value)} "
            f"к пессимистичному сценарию."
        )
    return lines


def _questions_section(facts: EstimationFacts) -> list[str]:
    lines = ["### Что уточнить", ""]
    if not facts.open_questions:
        lines.append("Вопросов нет — входных данных достаточно.")
        return lines
    lines.append("Это сузит диапазон при повторном `/estimate`:")
    lines.append("")
    lines.extend(f"- {question}" for question in facts.open_questions)
    return lines


def _render_stopped(estimate: Estimate, facts: EstimationFacts,
                    context: EstimationContext) -> str:
    lines = [
        "## Оценка задачи: расчёт остановлен",
        "",
        f"Два метода разошлись на {estimate.divergence:.0%} — больше допустимого "
        f"порога. По методологии в этом случае ищется ошибка в расчёте, а не "
        f"выводится среднее, поэтому итоговых чисел здесь нет.",
        "",
        "| Метод | Часы |",
        "|-------|------|",
        f"| Декомпозиция | {_number(estimate.decomposition_hours)} |",
        f"| Function Points | {_number(estimate.fp_hours)} |",
        "",
        f"Тип работы определён как «{WORK_TYPE_RU.get(facts.work_type, facts.work_type)}», "
        f"коэффициент ×{_number(estimate.work_type_coefficient)}.",
        "",
    ]
    lines.extend(_questions_section(facts))
    lines.extend(["", "---", "", _sources_line(context)])
    return "\n".join(lines)


def render(estimate: Estimate, facts: EstimationFacts,
           context: EstimationContext) -> str:
    if estimate.stopped:
        return _render_stopped(estimate, facts, context)

    work_type = WORK_TYPE_RU.get(facts.work_type, facts.work_type)
    artifact_type = ARTIFACT_TYPE_RU.get(facts.artifact_type, facts.artifact_type)
    coefficient = _number(estimate.work_type_coefficient)

    lines = [
        "## Оценка задачи",
        "",
        f"**Итог:** {_days(estimate.realistic_days)} (реалистичный сценарий) · "
        f"**Story Points:** {estimate.story_points} · "
        f"**Уверенность:** {CONFIDENCE_RU.get(estimate.confidence, estimate.confidence)}",
        "",
        "### Два метода",
        "",
        "| Метод | Расчёт | Часы |",
        "|-------|--------|------|",
        f"| Декомпозиция | ({_number(estimate.base_hours)} + тесты "
        f"{_number(estimate.tests_hours)}) × {coefficient} | "
        f"{_number(estimate.decomposition_hours)} |",
        f"| Function Points (cross-check) | {_number(facts.fp_count)} FP × "
        f"{_number(facts.fp_hours_per_point)} ч × {coefficient} | "
        f"{_number(estimate.fp_hours)} |",
        "",
        f"Расхождение методов — {estimate.divergence:.0%}.",
        "",
        "### Декомпозиция",
        "",
        "| Единица работы | Часы | Почему столько |",
        "|----------------|------|----------------|",
        f"| Каркас | {_number(max(0.0, facts.scaffolding_hours))} | базовая обвязка |",
    ]
    # Только положительные единицы — те же, что ушли в расчёт. Нулевые/
    # отрицательные, которые модель иногда возвращает, в таблице не показываем.
    for unit in positive_units(facts):
        lines.append(f"| {_cell(unit.name)} | {_number(unit.hours)} | {_cell(unit.rationale)} |")
    lines.extend([
        f"| Интеграция | {_number(max(0.0, facts.integration_hours))} | сборка воедино |",
        f"| Тесты | {_number(estimate.tests_hours)} | доля от объёма работ |",
        "",
        f"Тип работы — {work_type}, коэффициент ×{coefficient}. "
        f"Тип артефакта — {artifact_type}.",
    ])
    if facts.reasoning:
        lines.extend(["", facts.reasoning])

    lines.extend([
        "",
        "### PERT",
        "",
        "| Сценарий | Дни |",
        "|----------|-----|",
        f"| Оптимистичный (O) | {_number(estimate.optimistic_days)} |",
        f"| Реалистичный (M) | {_number(estimate.realistic_days)} |",
        f"| Пессимистичный (P) | {_number(estimate.pessimistic_days)} |",
        f"| Ожидание E = (O + 4M + P) / 6 | {_number(estimate.expected_days)} |",
        f"| С буфером на риски | {_number(estimate.buffered_days)} |",
        "",
        "### По грейдам",
        "",
        "| Грейд | Дни |",
        "|-------|-----|",
        f"| Middle | {_number(estimate.grade_days.get('middle', 0.0))} |",
        f"| Senior | {_number(estimate.grade_days.get('senior', 0.0))} |",
        f"| Senior с ИИ-ассистентом | {_number(estimate.grade_days.get('senior_ai', 0.0))} |",
        "",
    ])

    lines.extend(_factors_section(estimate))
    lines.append("")

    lines.append("### Проверка коридоров")
    lines.append("")
    if estimate.sanity_warnings:
        lines.extend(f"- ⚠️ {warning}" for warning in estimate.sanity_warnings)
    else:
        lines.append(f"Оценка внутри коридора для типа «{artifact_type}».")
    lines.append("")

    lines.extend(_questions_section(facts))
    lines.extend(["", "---", "", _sources_line(context)])
    return "\n".join(lines)
