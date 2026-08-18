"""Круг правок по замечаниям ревью (H3→H4).

Проверяем то, на чём круг держится: «нечего исправлять» — законный исход, а не
сбой, и у доведения есть предел.
"""

import pytest

from shared import pr_closing


def test_empty_result_is_a_legal_outcome():
    """Постановка обязана разрешать пустой результат явно. Без этого агент
    начнёт править косметику, лишь бы что-то изменить, и следующий круг уйдёт
    в спор с ревьюером."""
    task = pr_closing.build_task(9, review="всё хорошо", round_number=1, max_rounds_=3)

    assert "НЕ МЕНЯЙ НИЧЕГО" in task
    assert "видимость работы" in task   # почему нельзя править ради правки


def test_review_text_goes_in_verbatim():
    """Пересказ своими словами — лишнее звено, в котором теряется именно то,
    что ревьюер счёл важным."""
    review = "Проверь границу: deliveryFee на пороге возвращает 0, а тест ждёт 300"
    task = pr_closing.build_task(9, review=review, round_number=1, max_rounds_=3)

    assert review in task


def test_task_warns_about_review_blind_spot():
    """Ревью видит только дифф и регулярно требует того, что уже есть вне его."""
    task = pr_closing.build_task(9, review="r", round_number=1, max_rounds_=3)

    assert "только дифф" in task


def test_round_number_is_visible_to_the_agent():
    task = pr_closing.build_task(9, review="r", round_number=2, max_rounds_=3)

    assert "Круг 2 из 3" in task


def test_scope_is_limited_to_the_pr():
    """Доведение, а не разработка: новая функциональность в круг не входит."""
    task = pr_closing.build_task(9, review="r", round_number=1, max_rounds_=3)

    assert "новая функциональность сюда не добавляется" in task


@pytest.mark.parametrize("raw,expected", [("", 3), ("5", 5), ("мусор", 3), ("0", 3), ("-2", 3)])
def test_round_cap_falls_back_on_garbage(monkeypatch, raw, expected):
    """Битое значение не должно означать «без предела»: незамкнутый круг
    правок дороже, чем остановленный."""
    monkeypatch.setenv("PR_FIX_MAX_ROUNDS", raw)

    assert pr_closing.max_rounds() == expected


def test_round_comment_asks_for_recheck():
    """Без команды перепроверки круг не замкнётся: PR-Agent сам по пушу не
    просыпается."""
    body = pr_closing.round_comment(9, round_number=1, max_rounds_=3)

    assert pr_closing.REVIEW_COMMAND in body


def test_exhausted_comment_says_what_to_do_next():
    body = pr_closing.exhausted_comment(3)

    assert "нужен человек" in body
    assert "3 кругов" in body


def test_fix_loop_is_on_by_default(monkeypatch):
    monkeypatch.delenv("PR_FIX_ENABLED", raising=False)

    assert pr_closing.enabled() is True


# --- Вердикт: отклонённое замечание должно быть видно ---

def test_task_demands_a_written_verdict():
    """Пустой дифф без объяснения неотличим от сломанного прогона."""
    task = pr_closing.build_task(9, review="r", round_number=1, max_rounds_=3)

    assert pr_closing.VERDICT_FILE in task
    assert "отклонено:" in task


def test_task_lists_what_not_to_fix():
    """Автоматический ревьюер находит к чему придраться всегда. Без явного
    перечня отклоняемого круг будет править косметику и жечь итерации."""
    task = pr_closing.build_task(9, review="r", round_number=1, max_rounds_=3)

    assert "стилистические придирки" in task
    assert "уже сделано ВНЕ диффа" in task
    assert "на будущее" in task
    assert "отклонённого на прошлом круге" in task


def test_verdict_is_published_with_the_settled_outcome():
    body = pr_closing.settled_comment(2, verdict="отклонено: придирка к именам")

    assert "отклонено: придирка к именам" in body
    assert "Разбор замечаний" in body


def test_settled_outcome_without_verdict_stays_readable():
    """Агент мог не написать разбор — комментарий не должен превращаться в
    пустой блок с заголовком."""
    body = pr_closing.settled_comment(1)

    assert "Разбор замечаний" not in body
    assert "готов к слиянию" in body


def test_round_comment_carries_the_verdict_too():
    body = pr_closing.round_comment(9, round_number=1, max_rounds_=3,
                                    verdict="принято: добавил тест границы")

    assert "принято: добавил тест границы" in body
    assert pr_closing.REVIEW_COMMAND in body


def test_exhausted_comment_blames_the_code_not_the_reviewer():
    """Три круга — не признак вредного ревьюера, а признак проблемы в коде."""
    body = pr_closing.exhausted_comment(3)

    assert "проблема в самом коде" in body
