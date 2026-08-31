import pytest

from shared import answer_interpretation as ai
from shared import questions


def test_interpretation_requires_a_non_empty_answer():
    """Пустой ответ модели — отказ, а не решение."""
    with pytest.raises(ValueError):
        ai.Interpretation(answer="   ")


def test_amendment_must_name_an_existing_question():
    """Правка ссылается на запись журнала; ссылка в пустоту — отказ."""
    journal = [questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                                  question="q", answer="старое")]
    interpretation = ai.Interpretation(
        answer="новое решение",
        amendments=[ai.Amendment(question_id="mvp-bounds-9", answer="что-то")])
    with pytest.raises(ValueError):
        ai.validate(interpretation, journal)


def test_render_lists_every_change(monkeypatch):
    """Показ обязан перечислить и текущий ответ, и все правки (A21)."""
    journal = [questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                                  question="Чем принимать?", answer="старое")]
    interpretation = ai.Interpretation(
        answer="405 на любой метод кроме POST",
        amendments=[ai.Amendment(question_id="howtodemo-1", answer="наоборот")])
    rendered = ai.render_interpretation(interpretation, journal)

    assert "405 на любой метод кроме POST" in rendered
    assert "howtodemo-1" in rendered
    assert "наоборот" in rendered
    assert "старое" in rendered, "видно, что именно меняется"


def test_user_message_carries_the_whole_journal():
    """Толкование получает журнал целиком — иначе правка прежнего решения
    была бы молча проигнорирована (A20)."""
    question = questions.Question(id="howtodemo-2", kind="howtodemo",
                                  text="А теперь чем?", options=())
    journal = [questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                                  question="Чем принимать?", answer="старое решение")]
    message = ai.build_user_message(question, journal, "делаем наоборот")

    assert "старое решение" in message
    assert "howtodemo-1" in message
    assert "делаем наоборот" in message
    assert "А теперь чем?" in message
