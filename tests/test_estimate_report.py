from estimate_report import render
from estimation import EstimationFacts, WorkUnit, compute
from shared.workflow_types import EstimationContext


def facts(**overrides) -> EstimationFacts:
    base = dict(
        work_type="new_development",
        artifact_type="new_module",
        scaffolding_hours=4.0,
        work_units=[WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут")],
        integration_hours=2.0,
        fp_count=2.0,
        fp_hours_per_point=5.5,
        data_sufficiency="complete",
        has_acceptance_criteria=True,
        has_dependencies_listed=True,
        has_api_contract=True,
        has_data_class=True,
        risks=[],
        open_questions=[],
        reasoning="разбито по маршрутам",
    )
    base.update(overrides)
    return EstimationFacts(**base)


def context(**overrides) -> EstimationContext:
    base = dict(
        title="Заголовок",
        body="Описание",
        labels=["advisor:feature-request"],
        thread=[],
        branch=None,
        artifacts={},
        truncated=False,
    )
    base.update(overrides)
    return EstimationContext(**base)


def test_headline_carries_days_story_points_and_confidence(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "## Оценка задачи" in text
    assert "Story Points" in text
    assert "высокая" in text


def test_both_methods_are_shown_with_divergence(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Декомпозиция" in text
    assert "Function Points" in text
    assert "Расхождение" in text


def test_pipe_in_unit_text_does_not_break_the_table(rules):
    """Имена и обоснования модель берёт из текста Issue, где встречаются `|`
    и переводы строк. Без экранирования таблица в комментарии разъезжается.
    Поймано pr_agent на живом PR."""
    units = [WorkUnit(name="колонка `status | error`", hours=4.0,
                      rationale="две ветки:\nok и fail")]
    given = facts(work_units=units, fp_count=2.0, fp_hours_per_point=4.0)
    text = render(compute(given, rules), given, context())
    row = next(line for line in text.splitlines() if "status" in line)
    # Литеральный разделитель экранирован; перевод строки убран.
    assert "\\|" in row
    assert row.count("\n") == 0
    # Ровно четыре неэкранированных разделителя — три колонки, таблица цела.
    assert row.replace("\\|", "").count("|") == 4


def test_every_work_unit_appears_with_its_rationale(rules):
    units = [
        WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут"),
        WorkUnit(name="миграция", hours=3.0, rationale="одна таблица"),
    ]
    given = facts(work_units=units, fp_count=3.0, fp_hours_per_point=4.0)
    text = render(compute(given, rules), given, context())
    assert "эндпоинт" in text and "один маршрут" in text
    assert "миграция" in text and "одна таблица" in text


def test_applied_risk_is_spelled_out_with_its_coefficients(rules):
    given = facts(risks=["personal_data"])
    text = render(compute(given, rules), given, context())
    assert "персональные или регуляторные данные" in text
    assert "0.3" in text and "0.8" in text


def test_applied_penalty_is_spelled_out(rules):
    given = facts(has_acceptance_criteria=False)
    text = render(compute(given, rules), given, context())
    assert "не заданы критерии приёмки" in text
    assert "0.2" in text


def test_no_risks_and_no_penalties_says_so_explicitly(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Не применялись" in text


def test_all_three_grades_are_listed(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Middle" in text and "Senior" in text and "Senior с ИИ" in text


def test_open_questions_are_listed(rules):
    given = facts(open_questions=["какой объём данных", "кто владелец API"])
    text = render(compute(given, rules), given, context())
    assert "какой объём данных" in text
    assert "кто владелец API" in text


def test_sources_line_mentions_thread_and_branch(rules):
    given_context = context(
        thread=["первый", "второй"],
        branch="research/issue-42",
        artifacts={"docs/bft/issue-42-blueprint.md": "текст"},
    )
    text = render(compute(facts(), rules), facts(), given_context)
    assert "2 комментария" in text
    assert "research/issue-42" in text
    assert "1 файл" in text


def test_sources_line_uses_singular_for_one_comment(rules):
    text = render(compute(facts(), rules), facts(), context(thread=["один"]))
    assert "1 комментарий" in text


def test_sources_line_uses_many_form_for_five_comments(rules):
    text = render(compute(facts(), rules), facts(), context(thread=["к"] * 5))
    assert "5 комментариев" in text


def test_truncation_is_disclosed(rules):
    text = render(compute(facts(), rules), facts(), context(truncated=True))
    assert "обрезан" in text


def test_stopped_estimate_publishes_no_numbers(rules):
    given = facts(fp_count=12.0, fp_hours_per_point=6.0)
    estimate = compute(given, rules)
    assert estimate.stopped is True
    text = render(estimate, given, context())
    assert "расчёт остановлен" in text.lower()
    assert "PERT" not in text
    assert "Story Points" not in text


def test_stopped_estimate_still_lists_open_questions(rules):
    given = facts(fp_count=12.0, fp_hours_per_point=6.0, open_questions=["уточни объём"])
    text = render(compute(given, rules), given, context())
    assert "уточни объём" in text
