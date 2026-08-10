"""#39: ожидание как первоклассное состояние.

Проверяется само описание ожидания: что оно не бывает пустым, что различает
человека и машину, и что считает время так, как его прочитает человек.
"""

import pytest

from shared.awaiting import (
    APPROVAL,
    DEFAULT_DEADLINE_HOURS,
    EXTERNAL_AGENT,
    FAILURE_RECOVERY,
    HUMAN_DECISION,
    KINDS,
    TESTING,
    Awaiting,
    InvalidAwaiting,
    deadline_hours,
)

HOUR = 3600.0
NOW = 1_800_000_000.0


def _awaiting(**over) -> Awaiting:
    base = {"kind": HUMAN_DECISION, "who": "@kibarik",
            "reason": "решение о тяжёлой стадии", "since_epoch": NOW}
    base.update(over)
    return Awaiting(**base)


# --- ожидание не бывает пустым ---

def test_unknown_kind_is_rejected():
    with pytest.raises(InvalidAwaiting) as exc:
        _awaiting(kind="почти-ждём")

    assert "не из перечня" in str(exc.value)


def test_awaiting_without_a_reason_is_an_error():
    """«Ждём неизвестно чего» — ровно то состояние, ради ухода от которого
    задача и ставилась."""
    with pytest.raises(InvalidAwaiting):
        _awaiting(reason="   ")


def test_awaiting_without_an_addressee_is_an_error():
    with pytest.raises(InvalidAwaiting):
        _awaiting(who="")


# --- человек или машина ---

@pytest.mark.parametrize("kind", [HUMAN_DECISION, APPROVAL, FAILURE_RECOVERY])
def test_human_blockers_belong_to_the_human_queue(kind):
    assert _awaiting(kind=kind).blocks_on_human


@pytest.mark.parametrize("kind", [TESTING, EXTERNAL_AGENT])
def test_machine_blockers_do_not_pollute_the_human_queue(kind):
    """Выборка `label:needs-human:*` обязана быть ПОЛНОЙ очередью к людям.
    Задача, ждущая стенд или соседний сервис, человеку делать нечего."""
    assert not _awaiting(kind=kind).blocks_on_human


def test_failure_is_a_kind_of_waiting_not_an_end():
    """Раньше сбой вешал метку и закрывал прогон — ждать было некому и нечего."""
    assert FAILURE_RECOVERY in KINDS
    assert _awaiting(kind=FAILURE_RECOVERY).blocks_on_human


# --- время ---

def test_waited_hours_counts_from_the_start_of_the_wait():
    assert _awaiting().waited_hours(NOW + 5 * HOUR) == pytest.approx(5)


def test_clock_skew_does_not_produce_negative_waiting():
    assert _awaiting().waited_hours(NOW - HOUR) == 0


def test_remaining_is_none_without_a_deadline():
    assert _awaiting().remaining_hours(NOW) is None
    assert _awaiting().expired(NOW + 10_000 * HOUR) is False


def test_remaining_shrinks_towards_the_deadline():
    a = _awaiting(deadline_epoch=NOW + 10 * HOUR)

    assert a.remaining_hours(NOW + 4 * HOUR) == pytest.approx(6)
    assert not a.expired(NOW + 9 * HOUR)


def test_expired_wait_asks_for_no_more_time():
    a = _awaiting(deadline_epoch=NOW + 10 * HOUR)

    assert a.expired(NOW + 10 * HOUR)
    assert a.remaining_hours(NOW + 50 * HOUR) == 0


# --- строка для человека ---

def test_description_answers_all_four_questions():
    """По каждому Issue из очереди видно: чего ждут, от кого, сколько уже ждут
    и когда сгорит дедлайн — это определение готовности задачи."""
    text = _awaiting(deadline_epoch=NOW + 72 * HOUR).describe(NOW + 12 * HOUR)

    assert "решение о тяжёлой стадии" in text
    assert "@kibarik" in text
    assert "уже 12 ч" in text
    assert "осталось 60 ч" in text


def test_description_says_so_when_there_is_no_deadline():
    """Пустое место читалось бы как «забыли посчитать»."""
    assert "без срока" in _awaiting().describe(NOW)


# --- таблица сроков ---

def test_every_kind_has_a_default_deadline():
    """Ожидание без срока по умолчанию означало бы вечную парковку по недосмотру."""
    assert set(DEFAULT_DEADLINE_HOURS) == set(KINDS)
    assert all(v > 0 for v in DEFAULT_DEADLINE_HOURS.values())


def test_operator_override_wins_over_the_table():
    """Срок парковки уже настраивается через PARK_*_HOURS: две независимые
    ручки на один таймер разъехались бы при первой правке одной из них."""
    assert deadline_hours(HUMAN_DECISION, 5) == 5


@pytest.mark.parametrize("bad", [0, -1, None])
def test_broken_override_falls_back_to_the_table(bad):
    assert deadline_hours(HUMAN_DECISION, bad) == DEFAULT_DEADLINE_HOURS[HUMAN_DECISION]


def test_failure_recovery_waits_longer_than_a_decision():
    """Разбор сбоя реже срочный, но потеряться не должен."""
    assert DEFAULT_DEADLINE_HOURS[FAILURE_RECOVERY] > DEFAULT_DEADLINE_HOURS[HUMAN_DECISION]


# --- чего ждёт каждая фаза ---

def test_every_non_terminal_phase_knows_what_it_waits_for():
    """Фаза без описанного ожидания — та самая «просто Running», ради ухода от
    которой задача и ставилась."""
    from shared import lifecycle
    from shared.awaiting import KIND_BY_PHASE, REASON_BY_PHASE

    waiting_phases = {p for p in lifecycle.PHASES
                      if not lifecycle.is_terminal(p) and p != lifecycle.CREATED
                      and p not in (lifecycle.BUSINESS_ANALYSIS,
                                    lifecycle.SYSTEM_REQUIREMENTS)}

    assert not waiting_phases - set(KIND_BY_PHASE), "фаза без вида ожидания"
    assert not waiting_phases - set(REASON_BY_PHASE), "фаза без формулировки ожидания"


def test_failure_waits_for_a_human_despite_having_an_external_way_out():
    """У `failed` есть внешний переход («работа над PR продолжилась»), но ждёт
    он человека. Вывод вида ожидания из инициаторов переходов положил бы разбор
    сбоя в очередь к машинам, где его никто не увидит."""
    from shared import lifecycle
    from shared.awaiting import kind_for_phase

    assert any(t.initiator == lifecycle.EXTERNAL
               for t in lifecycle.allowed(lifecycle.FAILED))
    assert kind_for_phase(lifecycle.FAILED) == FAILURE_RECOVERY


def test_every_kind_has_an_addressee():
    from shared.awaiting import WHO_BY_KIND

    assert set(WHO_BY_KIND) == set(KINDS)
    assert all(v.strip() for v in WHO_BY_KIND.values())


def test_unknown_phase_still_gets_a_usable_description():
    """Новая фаза не должна ронять цикл до того, как её опишут."""
    from shared.awaiting import kind_for_phase, reason_for_phase, who_for_phase

    assert kind_for_phase("совсем-новая") == HUMAN_DECISION
    assert "совсем-новая" in reason_for_phase("совсем-новая")
    assert who_for_phase("совсем-новая")
