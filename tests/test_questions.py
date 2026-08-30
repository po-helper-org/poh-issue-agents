import pytest

from shared import questions


def test_question_roundtrip():
    """Вопрос возвращается из тела ровно таким, каким ушёл."""
    original = questions.Question(
        id="howtodemo-1", kind="howtodemo",
        text="Чем принимать эту задачу?",
        options=("было 404; стало 405", "было 404; стало 405 на любой метод"))
    restored = questions.parse_question(questions.render_question(original))
    assert restored == original


def test_question_with_multiline_text_survives():
    """Текст вопроса бывает многострочным — форма не должна его портить."""
    original = questions.Question(id="mvp-bounds-1", kind="mvp-bounds",
                                  text="Строка раз\n\nСтрока два", options=())
    assert questions.parse_question(questions.render_question(original)) == original


def test_parse_question_of_garbage_is_none():
    """Порченый блок — отсутствие вопроса, а не исключение наружу.

    Тело Issue правят руками, и обрывок JSON там появится рано или поздно.
    """
    assert questions.parse_question("не json вовсе") is None
    assert questions.parse_question(None) is None
    assert questions.parse_question("") is None


def test_journal_roundtrip():
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="Чем принимать?", answer="405 с Allow: POST"),
        questions.Decision(question_id="mvp-bounds-1", kind="mvp-bounds",
                           question="Что в MVP?", answer="только /quote"),
    ]
    assert questions.parse_journal(questions.render_journal(decisions)) == decisions


def test_parse_journal_of_garbage_is_empty():
    assert questions.parse_journal("мусор") == []
    assert questions.parse_journal(None) == []


def test_next_question_id_counts_within_kind():
    """Нумерация ведётся по журналу и отдельно по каждому виду вопроса.

    Из журнала, а не из счётчика в прогоне: прогон теряется, журнал остаётся.
    """
    assert questions.next_question_id([], "howtodemo") == "howtodemo-1"
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="q", answer="a"),
        questions.Decision(question_id="mvp-bounds-1", kind="mvp-bounds",
                           question="q", answer="a"),
    ]
    assert questions.next_question_id(decisions, "howtodemo") == "howtodemo-2"
    assert questions.next_question_id(decisions, "mvp-bounds") == "mvp-bounds-2"
    assert questions.next_question_id(decisions, "plan-choice") == "plan-choice-1"


def test_effective_drops_superseded_records_but_journal_keeps_them():
    """Отменённое решение остаётся в журнале, но действующим не считается.

    История задачи обязана отвечать на вопрос «что решали раньше и почему
    передумали» — запись, затёртая на месте, этот вопрос уничтожает.
    """
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="q", answer="старое решение"),
        questions.Decision(question_id="howtodemo-2", kind="howtodemo",
                           question="q2", answer="новое решение",
                           supersedes="howtodemo-1"),
    ]
    live = questions.effective(decisions)
    assert [d.answer for d in live] == ["новое решение"]
    assert len(decisions) == 2, "журнал не должен терять записи"


def test_effective_handles_chain_of_supersessions():
    """Отмена отмены: действующей остаётся последняя запись цепочки."""
    decisions = [
        questions.Decision(question_id="a-1", kind="a", question="q", answer="первое"),
        questions.Decision(question_id="a-2", kind="a", question="q", answer="второе",
                           supersedes="a-1"),
        questions.Decision(question_id="a-3", kind="a", question="q", answer="третье",
                           supersedes="a-2"),
    ]
    assert [d.answer for d in questions.effective(decisions)] == ["третье"]
