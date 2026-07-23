import pytest

from estimation import (
    EstimationError,
    EstimationFacts,
    WorkUnit,
    compute,
)


def facts(**overrides) -> EstimationFacts:
    """Базовые факты: новая разработка, всё описано, рисков нет.

    Каркас 4 + единицы 6 + интеграция 2 = 12 ч; тесты 30% -> 15.6 ч;
    коэффициент 1.0 -> декомпозиция 15.6 ч.
    FP: 3 FP x 5 ч = 15 ч. Расхождение 4% — cross-check проходит.
    """
    base = dict(
        work_type="new_development",
        artifact_type="new_module",
        scaffolding_hours=4.0,
        work_units=[
            WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут"),
            WorkUnit(name="валидация", hours=2.0, rationale="два правила"),
        ],
        integration_hours=2.0,
        fp_count=3.0,
        fp_hours_per_point=5.0,
        data_sufficiency="complete",
        has_acceptance_criteria=True,
        has_dependencies_listed=True,
        has_api_contract=True,
        has_data_class=True,
        risks=[],
        open_questions=[],
        reasoning="",
    )
    base.update(overrides)
    return EstimationFacts(**base)


def test_decomposition_is_base_plus_tests_times_coefficient(rules):
    result = compute(facts(), rules)
    assert result.base_hours == pytest.approx(12.0)
    assert result.tests_hours == pytest.approx(3.6)
    assert result.decomposition_hours == pytest.approx(15.6)


def test_work_type_coefficient_discounts_copy_work(rules):
    result = compute(facts(work_type="copy_existing", artifact_type="subtask"), rules)
    assert result.work_type_coefficient == pytest.approx(0.35)
    assert result.decomposition_hours == pytest.approx(15.6 * 0.35)
    # Тот же коэффициент применяется и к cross-check, иначе методы
    # разошлись бы искусственно.
    assert result.fp_hours == pytest.approx(15.0 * 0.35)


def test_pert_arithmetic_without_risks(rules):
    result = compute(facts(), rules)
    day = rules["day"]["hours"]
    assert result.optimistic_days == pytest.approx(15.6 * 0.7 / day)
    assert result.realistic_days == pytest.approx(15.6 / day)
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 / day)
    expected = (15.6 * 0.7 + 4 * 15.6 + 15.6 * 1.5) / 6
    assert result.expected_days == pytest.approx(expected / day)


def test_buffer_is_expectation_plus_k_standard_deviations(rules):
    result = compute(facts(), rules)
    sd = (result.pessimistic_days - result.optimistic_days) / 6
    assert result.buffered_days == pytest.approx(result.expected_days + 2 * sd)


def test_invariant_optimistic_below_realistic_below_pessimistic(rules):
    result = compute(facts(), rules)
    assert result.optimistic_days < result.realistic_days < result.pessimistic_days


def test_risk_minimum_moves_realistic_maximum_moves_pessimistic(rules):
    result = compute(facts(risks=["personal_data"]), rules)
    assert result.realistic_days == pytest.approx(15.6 * 1.3 / rules["day"]["hours"])
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 * 1.8 / rules["day"]["hours"])
    assert [risk.key for risk in result.risks] == ["personal_data"]


def test_unknown_risk_from_the_model_is_ignored(rules):
    result = compute(facts(risks=["решил_что_рискованно"]), rules)
    assert result.risks == []
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 / rules["day"]["hours"])


def test_missing_acceptance_criteria_only_inflates_pessimistic(rules):
    result = compute(facts(has_acceptance_criteria=False), rules)
    assert result.realistic_days == pytest.approx(15.6 / rules["day"]["hours"])
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 * 1.2 / rules["day"]["hours"])
    assert [penalty.key for penalty in result.penalties] == ["no_acceptance_criteria"]


def test_all_four_penalties_accumulate(rules):
    result = compute(
        facts(
            has_acceptance_criteria=False,
            has_dependencies_listed=False,
            has_api_contract=False,
            has_data_class=False,
        ),
        rules,
    )
    assert len(result.penalties) == 4
    total = 1 + 0.2 + 0.15 + 0.3 + 0.3
    assert result.pessimistic_days == pytest.approx(
        15.6 * 1.5 * total / rules["day"]["hours"]
    )


def test_cross_check_stops_when_methods_diverge_beyond_threshold(rules):
    # 15.6 ч декомпозиции против 60 ч по FP — расхождение почти 3x.
    result = compute(facts(fp_count=12.0, fp_hours_per_point=5.0), rules)
    assert result.stopped is True
    assert result.divergence > rules["cross_check"]["max_divergence"]
    assert result.expected_days == 0.0
    assert result.story_points == "—"


def test_moderate_divergence_downgrades_confidence(rules):
    # 15.6 ч против 25 ч — расхождение 60%: порог не превышен, но больше половины.
    result = compute(facts(fp_count=5.0, fp_hours_per_point=5.0), rules)
    assert result.stopped is False
    assert result.confidence == "medium"


def test_confidence_follows_data_sufficiency(rules):
    assert compute(facts(data_sufficiency="complete"), rules).confidence == "high"
    assert compute(facts(data_sufficiency="minimal"), rules).confidence == "medium"
    assert compute(facts(data_sufficiency="insufficient"), rules).confidence == "low"


def test_sanity_warning_when_above_corridor(rules):
    big = [WorkUnit(name=f"модуль {i}", hours=20.0, rationale="крупный") for i in range(8)]
    result = compute(
        facts(work_units=big, fp_count=34.0, fp_hours_per_point=5.0),
        rules,
    )
    assert result.sanity_warnings
    assert "декомпозиция" in result.sanity_warnings[0]


def test_sanity_warning_names_the_number_it_is_about(rules):
    """В шапке комментария итогом стоит M, а коридор проверяется по E. Без
    явного числа в тексте читатель видит «Итог 13.16 дн» рядом с «дольше
    пятнадцати дней» и считает это ошибкой расчёта."""
    big = [WorkUnit(name=f"модуль {i}", hours=20.0, rationale="крупный") for i in range(8)]
    result = compute(facts(work_units=big, fp_count=34.0, fp_hours_per_point=5.0), rules)
    warning = result.sanity_warnings[0]
    assert f"{round(result.expected_days, 2):g}" in warning
    assert "15" in warning
    assert "новый модуль с нуля" in warning


def test_no_sanity_warning_inside_corridor(rules):
    assert compute(facts(), rules).sanity_warnings == []


def test_story_points_snap_to_fibonacci(rules):
    result = compute(facts(), rules)
    # M = 15.6 ч -> 3.9 SP -> ближайшее по шкале 3
    assert result.story_points == "3"


def test_story_points_follow_the_realistic_scenario_not_the_expectation(rules):
    """Итог в шапке комментария — это M. Если SP считать от E, рядом окажутся
    два числа про разный объём работы, и это читается как ошибка."""
    result = compute(facts(risks=["personal_data"]), rules)
    # M = 15.6 x 1.3 = 20.28 ч -> 5.07 SP -> 5; от E (30.68 ч) вышло бы 8.
    assert result.story_points == "5"


def test_story_points_above_scale_get_plus(rules):
    huge = [WorkUnit(name=f"часть {i}", hours=40.0, rationale="крупная") for i in range(6)]
    result = compute(
        facts(work_units=huge, fp_count=50.0, fp_hours_per_point=5.5),
        rules,
    )
    assert result.story_points == "20+"


def test_grade_days_scale_the_realistic_scenario(rules):
    result = compute(facts(), rules)
    assert result.grade_days["middle"] == pytest.approx(result.realistic_days)
    assert result.grade_days["senior"] == pytest.approx(result.realistic_days * 0.75)
    assert result.grade_days["senior_ai"] == pytest.approx(result.realistic_days * 0.55)


def test_empty_decomposition_is_an_error(rules):
    with pytest.raises(EstimationError, match="декомпозиция пуста"):
        compute(facts(work_units=[]), rules)


def test_zero_hour_unit_is_dropped_not_fatal(rules):
    """Модель регулярно возвращает единицу с 0 часов. Одна такая строка не
    должна ронять всю оценку — её надо отбросить. Наблюдалось на живом
    прогоне issue #149."""
    units = [
        WorkUnit(name="реальная", hours=6.0, rationale="есть работа"),
        WorkUnit(name="пустышка", hours=0.0, rationale=""),
    ]
    result = compute(facts(work_units=units, fp_count=4.0, fp_hours_per_point=4.0), rules)
    # Каркас 4 + единицы 6 (нулевая не в счёт) + интеграция 2 = 12.
    assert result.base_hours == pytest.approx(12.0)


def test_negative_unit_hours_are_dropped(rules):
    units = [
        WorkUnit(name="реальная", hours=6.0, rationale="есть работа"),
        WorkUnit(name="кривая", hours=-3.0, rationale="шум модели"),
    ]
    result = compute(facts(work_units=units, fp_count=4.0, fp_hours_per_point=4.0), rules)
    assert result.base_hours == pytest.approx(12.0)


def test_negative_scaffolding_is_floored_to_zero(rules):
    result = compute(facts(scaffolding_hours=-4.0, fp_count=2.0, fp_hours_per_point=4.0), rules)
    # Каркас занулён, единицы 6 + интеграция 2 = 8.
    assert result.base_hours == pytest.approx(8.0)


def test_decomposition_of_only_non_positive_units_is_an_error(rules):
    bad = [WorkUnit(name="ничего", hours=0.0, rationale="")]
    with pytest.raises(EstimationError, match="декомпозиция пуста"):
        compute(facts(work_units=bad), rules)


def test_missing_function_points_are_an_error(rules):
    with pytest.raises(EstimationError, match="Function Points"):
        compute(facts(fp_count=0.0), rules)


def test_unknown_work_type_is_an_error(rules):
    with pytest.raises(EstimationError, match="тип работы"):
        compute(facts(work_type="магия"), rules)


def test_unknown_artifact_type_is_an_error(rules):
    with pytest.raises(EstimationError, match="тип артефакта"):
        compute(facts(artifact_type="нечто"), rules)
