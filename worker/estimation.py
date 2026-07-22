"""
Детерминированный расчёт оценки задачи.

Чистый модуль: ни сети, ни LLM, ни Temporal. Модель отдаёт только факты
(EstimationFacts), а коэффициенты, надбавки, PERT, cross-check и коридоры
считаются здесь по config/estimation-rules.toml. Тот же принцип, что уже
работает в score_priority: модель извлекает, код считает — иначе одна и та
же задача давала бы разные числа от прогона к прогону.

Поля «итоговая оценка» в схеме фактов нет намеренно: модель структурно не
может вернуть готовое число в обход расчёта.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

RULES_PATH = Path("/app/config/estimation-rules.toml")

_CONFIDENCE_LADDER = ("low", "medium", "high")
_SUFFICIENCY_CONFIDENCE = {
    "complete": "high",
    "sufficient": "high",
    "minimal": "medium",
    "insufficient": "low",
}

WORK_TYPE_RU = {
    "copy_existing": "копирование готового решения",
    "documentation": "документация",
    "research": "исследование",
    "new_development": "новая разработка",
    "enhancement": "доработка существующего",
    "deployment": "развёртывание и интеграция",
}

ARTIFACT_TYPE_RU = {
    "bugfix": "багфикс",
    "validation": "валидация существующего",
    "subtask": "подзадача",
    "new_module": "новый модуль с нуля",
}

RISK_LABELS = {
    "personal_data": "персональные или регуляторные данные",
    "cross_team": "кросс-командная зависимость",
    "undocumented_external_api": "внешний API без документации",
    "unagreed_api_contract": "контракт API не согласован",
    "security_unreviewed": "не согласовано с информационной безопасностью",
}

PENALTY_LABELS = {
    "no_acceptance_criteria": "не заданы критерии приёмки",
    "no_dependencies": "не перечислены зависимости",
    "no_api_contract": "не согласован контракт API",
    "no_data_class": "не указан класс обрабатываемых данных",
}

CONFIDENCE_RU = {"high": "высокая", "medium": "средняя", "low": "низкая"}


class EstimationError(ValueError):
    """Факты не проходят внутренние проверки — расчёт невозможен."""


class WorkUnit(BaseModel):
    name: str = Field(description="Единица работы: эндпоинт, правило, экран, раздел")
    hours: float = Field(description="Часы как для новой разработки с нуля, без скидок за тип работы")
    rationale: str = Field(description="Почему именно столько")


class EstimationFacts(BaseModel):
    work_type: str = Field(description="copy_existing | documentation | research | new_development | enhancement | deployment")
    artifact_type: str = Field(description="bugfix | validation | subtask | new_module")
    scaffolding_hours: float = Field(description="Часы на каркас и базовую обвязку")
    work_units: list[WorkUnit] = Field(description="Декомпозиция снизу-вверх, минимум одна единица")
    integration_hours: float = Field(description="Часы на интеграцию и сборку воедино")
    fp_count: float = Field(description="Количество Function Points, независимый cross-check")
    fp_hours_per_point: float = Field(description="Часов на один Function Point")
    data_sufficiency: str = Field(description="insufficient | minimal | sufficient | complete")
    has_acceptance_criteria: bool
    has_dependencies_listed: bool
    has_api_contract: bool
    has_data_class: bool
    risks: list[str] = Field(default=[], description="Ключи рисков из известного множества")
    open_questions: list[str] = Field(default=[], description="Что уточнить, чтобы сузить диапазон")
    reasoning: str = Field(default="", description="Кратко: на чём построена декомпозиция")


@dataclass
class AppliedRisk:
    key: str
    label: str
    min_value: float
    max_value: float


@dataclass
class AppliedPenalty:
    key: str
    label: str
    value: float


@dataclass
class Estimate:
    stopped: bool
    divergence: float
    base_hours: float
    tests_hours: float
    work_type_coefficient: float
    decomposition_hours: float
    fp_hours: float
    optimistic_days: float
    realistic_days: float
    pessimistic_days: float
    expected_days: float
    buffered_days: float
    story_points: str
    confidence: str
    grade_days: dict[str, float]
    risks: list[AppliedRisk]
    penalties: list[AppliedPenalty]
    sanity_warnings: list[str]


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _validate(facts: EstimationFacts, rules: dict) -> None:
    if facts.work_type not in rules["work_type"]:
        raise EstimationError(f"неизвестный тип работы: {facts.work_type}")
    if facts.artifact_type not in rules["sanity_bounds"]:
        raise EstimationError(f"неизвестный тип артефакта: {facts.artifact_type}")
    if not facts.work_units:
        raise EstimationError("декомпозиция пуста — оценивать нечего")
    if any(unit.hours <= 0 for unit in facts.work_units):
        raise EstimationError("единица работы с неположительными часами")
    if facts.scaffolding_hours < 0 or facts.integration_hours < 0:
        raise EstimationError("отрицательные часы каркаса или интеграции")
    if facts.fp_count <= 0 or facts.fp_hours_per_point <= 0:
        raise EstimationError("Function Points не посчитаны — cross-check невозможен")


def _risks(facts: EstimationFacts, rules: dict) -> list[AppliedRisk]:
    applied = []
    for key in facts.risks:
        rule = rules["risk"].get(key)
        if rule is None:
            # Модель назвала риск, которого нет в конфиге. Молча игнорируем:
            # выдуманный коэффициент хуже отсутствующего.
            continue
        applied.append(AppliedRisk(key, RISK_LABELS.get(key, key), rule["min"], rule["max"]))
    return applied


def _penalties(facts: EstimationFacts, rules: dict) -> list[AppliedPenalty]:
    missing = {
        "no_acceptance_criteria": not facts.has_acceptance_criteria,
        "no_dependencies": not facts.has_dependencies_listed,
        "no_api_contract": not facts.has_api_contract,
        "no_data_class": not facts.has_data_class,
    }
    return [
        AppliedPenalty(key, PENALTY_LABELS[key], rules["missing_data_penalty"][key])
        for key, is_missing in missing.items()
        if is_missing
    ]


def _confidence(facts: EstimationFacts, divergence: float, max_divergence: float) -> str:
    level = _SUFFICIENCY_CONFIDENCE.get(facts.data_sufficiency, "low")
    if divergence > max_divergence / 2:
        # Методы разошлись заметно, хоть и в пределах допустимого — это само
        # по себе повод меньше доверять числу.
        level = _CONFIDENCE_LADDER[max(0, _CONFIDENCE_LADDER.index(level) - 1)]
    return level


def _story_points(expected_hours: float, rules: dict) -> str:
    scale = rules["story_points"]["scale"]
    points = expected_hours / rules["story_points"]["hours_per_point"]
    if points > max(scale):
        return f"{max(scale):g}+"
    return f"{min(scale, key=lambda value: abs(value - points)):g}"


def _sanity_warnings(expected_days: float, artifact_type: str, rules: dict) -> list[str]:
    """Коридор проверяется по ожиданию E, а не по реалистичному сценарию M:
    E учитывает разброс, и задача с умеренным M, но огромным P — как раз тот
    случай, ради которого коридор существует.

    Но в шапке комментария итогом стоит M, поэтому текст обязан назвать
    число, о котором говорит: иначе рядом окажутся «Итог 13.16 дн» и
    «дольше пятнадцати дней», и это читается как ошибка расчёта.
    """
    bounds = rules["sanity_bounds"][artifact_type]
    label = ARTIFACT_TYPE_RU.get(artifact_type, artifact_type)
    if expected_days > bounds["max_days"]:
        return [
            f"ожидание E = {round(expected_days, 2):g} дн выше коридора "
            f"{bounds['max_days']:g} дн для типа «{label}»: {bounds['over']}"
        ]
    if expected_days < bounds["min_days"]:
        return [
            f"ожидание E = {round(expected_days, 2):g} дн ниже коридора "
            f"{bounds['min_days']:g} дн для типа «{label}»: {bounds['under']}"
        ]
    return []


def compute(facts: EstimationFacts, rules: dict) -> Estimate:
    _validate(facts, rules)

    coefficient = rules["work_type"][facts.work_type]
    units_hours = sum(unit.hours for unit in facts.work_units)
    base = facts.scaffolding_hours + units_hours + facts.integration_hours
    tests = base * rules["test_share"]["ratio"]
    decomposition = (base + tests) * coefficient
    fp = facts.fp_count * facts.fp_hours_per_point * coefficient

    divergence = abs(decomposition - fp) / min(decomposition, fp)
    max_divergence = rules["cross_check"]["max_divergence"]

    risks = _risks(facts, rules)
    penalties = _penalties(facts, rules)
    confidence = _confidence(facts, divergence, max_divergence)

    if divergence > max_divergence:
        # Методология требует искать ошибку, а не усреднять. Числа наружу
        # не отдаём вовсе — иначе усреднение произойдёт в голове читающего.
        return Estimate(
            stopped=True,
            divergence=divergence,
            base_hours=base,
            tests_hours=tests,
            work_type_coefficient=coefficient,
            decomposition_hours=decomposition,
            fp_hours=fp,
            optimistic_days=0.0,
            realistic_days=0.0,
            pessimistic_days=0.0,
            expected_days=0.0,
            buffered_days=0.0,
            story_points="—",
            confidence=confidence,
            grade_days={},
            risks=risks,
            penalties=penalties,
            sanity_warnings=[],
        )

    pert = rules["pert"]
    hours_per_day = rules["day"]["hours"]

    optimistic = decomposition * pert["optimistic_factor"]
    realistic = decomposition * (1 + sum(risk.min_value for risk in risks))
    pessimistic = (
        decomposition
        * pert["pessimistic_factor"]
        * (1 + sum(risk.max_value for risk in risks))
        * (1 + sum(penalty.value for penalty in penalties))
    )

    if not optimistic < realistic < pessimistic:
        raise EstimationError(
            f"нарушен инвариант O < M < P: {optimistic:.1f} / {realistic:.1f} / {pessimistic:.1f}"
        )

    expected = (optimistic + 4 * realistic + pessimistic) / 6
    standard_deviation = (pessimistic - optimistic) / 6
    buffered = expected + pert["buffer_k"] * standard_deviation
    expected_days = expected / hours_per_day

    return Estimate(
        stopped=False,
        divergence=divergence,
        base_hours=base,
        tests_hours=tests,
        work_type_coefficient=coefficient,
        decomposition_hours=decomposition,
        fp_hours=fp,
        optimistic_days=optimistic / hours_per_day,
        realistic_days=realistic / hours_per_day,
        pessimistic_days=pessimistic / hours_per_day,
        expected_days=expected_days,
        buffered_days=buffered / hours_per_day,
        # Story Points считаются от реалистичного сценария, а не от E: именно
        # M выводится в шапке комментария как итог, и два разных числа рядом
        # («3.9 дн» и SP, соответствующие 5.6 дн) читались бы как ошибка.
        story_points=_story_points(realistic, rules),
        confidence=confidence,
        grade_days={
            name: (realistic / hours_per_day) * factor
            for name, factor in rules["grade"].items()
        },
        risks=risks,
        penalties=penalties,
        sanity_warnings=_sanity_warnings(expected_days, facts.artifact_type, rules),
    )
