"""Толкование свободного ответа человека.

Отдельный модуль, а не функция в activities: файл активностей уже за четыре
тысячи строк, и промпт с моделью данных там теряется.

Ответ человека может касаться не только текущего вопроса. Одной командой он
вправе ответить на заданное и заодно поправить решение, принятое раньше — «а
вот про то, что раньше спрашивал, делаем наоборот». Поэтому толкование
получает журнал целиком, а не один открытый вопрос.
"""
from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, field_validator

from shared import questions


class Amendment(BaseModel):
    """Правка решения, принятого по прежнему вопросу."""

    question_id: str = Field(description="Идентификатор записи журнала")
    answer: str = Field(description="Новое решение по этому вопросу")


class Interpretation(BaseModel):
    """Что контур понял из свободного ответа человека."""

    answer: str = Field(description="Решение по текущему вопросу")
    amendments: list[Amendment] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("толкование без решения по текущему вопросу")
        return value


def validate(interpretation: Interpretation,
             journal: Sequence[questions.Decision]) -> None:
    """Правки обязаны ссылаться на существующие записи журнала.

    Ссылка в пустоту означает, что модель выдумала идентификатор. Записать
    такую правку значит завести решение по вопросу, которого не было.
    """
    known = {decision.question_id for decision in journal}
    for amendment in interpretation.amendments:
        if amendment.question_id not in known:
            raise ValueError(
                f"правка ссылается на неизвестную запись {amendment.question_id!r}")


def render_interpretation(interpretation: Interpretation,
                          journal: Sequence[questions.Decision]) -> str:
    """Человекочитаемый перечень ВСЕХ изменений — до подтверждения.

    Показываем и старое значение тоже: «меняю X на Y» проверяется взглядом, а
    «теперь будет Y» требует помнить, что было.
    """
    was = {decision.question_id: decision.answer for decision in journal}
    lines = ["Записал так:", "", interpretation.answer]
    if interpretation.amendments:
        lines += ["", "И меняю прежние решения:", ""]
        for amendment in interpretation.amendments:
            lines.append(f"- `{amendment.question_id}`: "
                         f"было «{was.get(amendment.question_id, '—')}», "
                         f"станет «{amendment.answer}»")
    return "\n".join(lines)


SYSTEM_PROMPT = """Ты разбираешь ответ человека на вопрос, заданный системой.

Верни решение по ТЕКУЩЕМУ вопросу. Если человек в том же сообщении меняет
решение, принятое раньше по другому вопросу, верни это отдельной правкой с
идентификатором той записи.

Правила:
- решение формулируй наблюдаемыми признаками, а не пересказом намерений;
- ничего не додумывай: чего человек не сказал, того в решении нет;
- правку заводи только если человек ЯВНО меняет прежнее решение. Упоминание
  прошлого решения без указания менять — не правка;
- идентификаторы бери из журнала дословно, не выдумывай;
- пиши на языке вопроса."""


def build_user_message(question: questions.Question,
                       journal: Sequence[questions.Decision],
                       answer: str) -> str:
    lines = [f"# Текущий вопрос ({question.id})", "", question.text, ""]
    if question.options:
        lines.append("Предложенные варианты:")
        for number, option in enumerate(question.options, start=1):
            lines.append(f"{number}. {option}")
        lines.append("")
    if journal:
        lines += ["# Решения, принятые раньше", ""]
        for decision in questions.effective(journal):
            lines.append(f"- `{decision.question_id}` — {decision.question}: "
                         f"{decision.answer}")
        lines.append("")
    lines += ["# Ответ человека", "", answer]
    return "\n".join(lines)
