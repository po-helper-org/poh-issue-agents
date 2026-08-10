"""#38: контракт события внешнего агента и корреляция работы с Issue.

Модуль публичный — его читают соседние сервисы контура, поэтому проверяется не
только «работает», но и «не строже необходимого»: лишняя валидация на общем
контракте ломает соседей на каждой их правке.
"""

import pytest

from shared import lifecycle
from shared.agent_events import (
    BLOCKED,
    FAILED,
    STARTED,
    SUCCEEDED,
    AgentEvent,
    InvalidAgentEvent,
    correlate,
    issue_from_branch,
    parse_closes,
    parse_event,
    target_phase,
)


def _payload(**over) -> dict:
    base = {"repo": "o/r", "agent": "pr-agent", "phase": lifecycle.PR_OPEN,
            "status": STARTED, "ref": "42"}
    base.update(over)
    return base


# --- разбор конверта ---

def test_minimal_event_is_accepted():
    event = parse_event(_payload())

    assert event.repo == "o/r"
    assert event.phase == lifecycle.PR_OPEN
    assert event.root_issue is None


def test_phase_must_come_from_the_shared_vocabulary():
    """Своя фаза у соседнего сервиса означала бы трассировку из несовместимых
    кусков — ровно то, ради чего заводился общий словарь (#35)."""
    with pytest.raises(InvalidAgentEvent) as exc:
        parse_event(_payload(phase="почти-готово"))

    assert "не из словаря" in str(exc.value)


def test_error_names_what_was_allowed():
    """Сообщение читает разработчик соседнего сервиса, у которого нет наших
    исходников под рукой."""
    with pytest.raises(InvalidAgentEvent) as exc:
        parse_event(_payload(status="ок"))

    assert lifecycle.PR_OPEN not in str(exc.value)  # перечисляем статусы, не фазы
    assert SUCCEEDED in str(exc.value)


@pytest.mark.parametrize("field", ["repo", "agent", "phase", "status", "ref"])
def test_empty_required_field_is_rejected(field):
    with pytest.raises(InvalidAgentEvent) as exc:
        parse_event(_payload(**{field: "   "}))

    assert field in str(exc.value)


def test_unknown_fields_do_not_break_the_contract():
    """Соседний сервис вправе добавить своё поле, не согласуя релиз с нами."""
    event = parse_event(_payload(their_own_field={"nested": 1}))

    assert event.phase == lifecycle.PR_OPEN


def test_root_issue_accepts_a_numeric_string():
    """JSON от соседа может прислать номер строкой — это не повод отказать."""
    assert parse_event(_payload(root_issue="17")).root_issue == 17


@pytest.mark.parametrize("bad", ["не число", 0, -3])
def test_broken_root_issue_is_an_error_not_a_guess(bad):
    with pytest.raises(InvalidAgentEvent):
        parse_event(_payload(root_issue=bad))


def test_non_object_payload_is_rejected():
    with pytest.raises(InvalidAgentEvent):
        parse_event(["событие"])


# --- разбор ссылок на Issue ---

@pytest.mark.parametrize("text", [
    "Closes #12", "closes #12", "Fixes #12", "fixed #12",
    "Resolves #12", "resolve: #12", "\n\nCloses #12\n",
])
def test_closing_keywords_github_honours_are_honoured_here_too(text):
    assert parse_closes(text) == [12]


def test_repeated_mention_is_one_issue():
    assert parse_closes("Closes #12\nCloses #12") == [12]


def test_several_issues_are_all_reported():
    assert parse_closes("Closes #12, fixes #34") == [12, 34]


def test_plain_mention_is_not_a_closing_link():
    """`#12` в тексте — ссылка, а не обязательство закрыть."""
    assert parse_closes("см. также #12") == []


@pytest.mark.parametrize("ref, expected", [
    ("research/issue-7", 7),
    ("bug/issue-19", 19),
    ("refs/heads/research/issue-7", 7),
    ("feature/whatever", None),
    ("", None),
])
def test_branch_convention_is_read(ref, expected):
    assert issue_from_branch(ref) == expected


# --- корреляция ---

def test_explicit_field_wins():
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                       status=STARTED, ref="research/issue-7",
                       root_issue=42, detail="Closes #99")

    assert correlate(event) == (42, "поле root_issue")


def test_closes_beats_the_branch_name():
    """Ветку можно назвать как угодно, `Closes #N` — обязательство автора PR."""
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                       status=STARTED, ref="research/issue-7", detail="Closes #99")

    assert correlate(event) == (99, "Closes #N в теле")


def test_branch_is_the_last_resort():
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                       status=STARTED, ref="bug/issue-19")

    number, how = correlate(event)
    assert number == 19
    assert "ветк" in how


def test_ambiguity_is_not_resolved_by_guessing():
    """Привязать работу не к той задаче хуже, чем не привязать: на этой связи
    держится вся трассировка."""
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                       status=STARTED, ref="research/issue-7",
                       detail="Closes #12, closes #34")

    number, why = correlate(event)
    assert number is None
    assert "#12" in why and "#34" in why


def test_nothing_to_correlate_says_what_was_looked_for():
    event = AgentEvent(repo="o/r", agent="ci", phase=lifecycle.PR_OPEN,
                       status=STARTED, ref="build-881")

    number, why = correlate(event)
    assert number is None
    assert "root_issue" in why and "Closes" in why


# --- исход события против названной фазы ---

def test_successful_step_lands_in_the_named_phase():
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.MERGED,
                       status=SUCCEEDED, ref="42")

    assert target_phase(event) == lifecycle.MERGED


def test_failed_step_lands_in_failed_not_in_the_named_phase():
    """Агент сообщает, ГДЕ работа, а исход решает, куда двигаться."""
    event = AgentEvent(repo="o/r", agent="ci", phase=lifecycle.TESTING,
                       status=FAILED, ref="build-881")

    assert target_phase(event) == lifecycle.FAILED


def test_blocked_step_goes_to_a_human():
    event = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_REVIEW,
                       status=BLOCKED, ref="42")

    assert target_phase(event) == lifecycle.ESCALATED


def test_both_outcome_phases_can_be_returned_to_work():
    """Исход не должен быть тупиком: человек возвращает Issue сигналом."""
    for phase in (lifecycle.FAILED, lifecycle.ESCALATED):
        assert lifecycle.allowed(phase), f"{phase} стал тупиком"


# --- ключ идемпотентности ---

def test_same_fact_has_the_same_key():
    a = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                   status=STARTED, ref="42", detail="первая доставка")
    b = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                   status=STARTED, ref="42", detail="повтор с другим текстом")

    assert a.key() == b.key()


def test_next_status_on_the_same_ref_is_a_different_fact():
    started = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                         status=STARTED, ref="42")
    merged = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.MERGED,
                        status=SUCCEEDED, ref="42")

    assert started.key() != merged.key()


def test_next_phase_with_the_same_status_is_a_different_fact():
    """Один PR проходит несколько шагов, и каждый начинается со `started`.
    Ключ без фазы схлопнул бы начало ревью в повтор открытия PR."""
    opened = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_OPEN,
                        status=STARTED, ref="42")
    review = AgentEvent(repo="o/r", agent="pr-agent", phase=lifecycle.PR_REVIEW,
                        status=STARTED, ref="42")

    assert opened.key() != review.key()
