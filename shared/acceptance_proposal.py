"""Варианты критерия приёмки, предлагаемые человеку.

Форма варианта — «было / стало» наблюдаемыми признаками. Пересказ задачи
критерием не является: по нему нельзя вынести вердикт.

Модуль чистый: ни сети, ни GitHub, ни модели — как `shared/questions.py` и
`shared/answer_interpretation.py`. Вызов модели (`llm.extract`) живёт в
активности `worker/activities.py:propose_acceptance_options`, этот модуль
только описывает форму ответа и промпт.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AcceptanceOption(BaseModel):
    """Один вариант критерия: наблюдаемое «до» и наблюдаемое «после»."""

    before: str = Field(description="Что наблюдается сейчас, конкретно")
    after: str = Field(description="Что должно наблюдаться после правки")


class AcceptanceOptions(BaseModel):
    options: list[AcceptanceOption]

    @field_validator("options")
    @classmethod
    def _sane_count(cls, value):
        if not value:
            raise ValueError("модель не предложила ни одного варианта")
        if len(value) > 3:
            raise ValueError(f"вариантов не больше трёх, дано {len(value)}")
        return value


def render_option(option: AcceptanceOption) -> str:
    return f"было — {option.before}; стало — {option.after}"


SYSTEM_PROMPT = """Ты помогаешь сформулировать критерий приёмки задачи.

Прочитай задачу и предложи от двух до трёх вариантов критерия. Каждый вариант —
пара наблюдаемых признаков: что наблюдается сейчас и что должно наблюдаться
после правки.

Требования:
- только наблюдаемое: код ответа, текст в интерфейсе, содержимое файла,
  поведение команды. Никакого пересказа задачи и никаких намерений;
- варианты отличаются ГРАНИЦАМИ работы, а не формулировкой: первый — только
  основное поведение, второй — оно же плюс смежный случай;
- конкретика вместо общих слов: «отвечает 405 с заголовком Allow: POST», а не
  «отвечает корректно»;
- пиши на языке задачи."""
