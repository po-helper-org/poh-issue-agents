"""Вопрос контура человеку и журнал принятых решений.

Обе структуры живут в теле Issue размеченными блоками, а сериализуются JSON
внутри забора кода. Причина не в красоте: ответы бывают многострочными, с
кавычками и списками, и запись, из которой потом принимаются решения, обязана
возвращаться из тела РОВНО такой, какой ушла. Разбор прозы этого не даёт —
первая же правка формулировки вокруг ломает восстановление молча.

Человеку читаемый вид достаётся комментарием: блок — машинная запись,
комментарий — обращение к человеку. Разделение обязанностей, а не дублирование.

Модуль чистый: ни сети, ни GitHub. Всё, что здесь есть, проверяется без
окружения.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

_FENCE = "```"
_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n(?P<payload>.*?)\n```", re.DOTALL)


@dataclass(frozen=True)
class Question:
    """Открытый вопрос контура.

    `options` пуст — отвечать можно только свободным текстом. Так бывает,
    когда модель не смогла предложить варианты и когда вопрос задан заново
    после пропажи блока из тела.
    """

    id: str
    kind: str
    text: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    """Запись журнала: вопрос и принятое по нему решение.

    `supersedes` — идентификатор записи, которую эта отменяет. Пусто у первой
    записи по поводу. Отменённая запись из журнала НЕ удаляется.
    """

    question_id: str
    kind: str
    question: str
    answer: str
    supersedes: str = ""


def _wrap(payload: object, header: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{header}\n\n{_FENCE}json\n{body}\n{_FENCE}"


def _unwrap(payload: str | None):
    """JSON из забора кода. Ничего не разобралось — None."""
    if not payload:
        return None
    match = _JSON_BLOCK.search(payload)
    if not match:
        return None
    try:
        return json.loads(match.group("payload"))
    except (ValueError, TypeError):
        # Тело Issue правят руками, и обрывок JSON там появится рано или поздно.
        # Это отсутствие записи, а не отказ: вызывающий решит, что делать.
        return None


def render_question(question: Question) -> str:
    return _wrap({"id": question.id, "kind": question.kind,
                  "text": question.text, "options": list(question.options)},
                 "## Открытый вопрос контура")


def parse_question(payload: str | None) -> Question | None:
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return None
    try:
        return Question(id=str(data["id"]), kind=str(data["kind"]),
                        text=str(data["text"]),
                        options=tuple(str(item) for item in data.get("options", ())))
    except (KeyError, TypeError):
        return None


def render_journal(decisions: Sequence[Decision]) -> str:
    return _wrap([{"question_id": d.question_id, "kind": d.kind,
                   "question": d.question, "answer": d.answer,
                   "supersedes": d.supersedes} for d in decisions],
                 "## Решения по задаче")


def parse_journal(payload: str | None) -> list[Decision]:
    data = _unwrap(payload)
    if not isinstance(data, list):
        return []
    result: list[Decision] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            result.append(Decision(question_id=str(item["question_id"]),
                                   kind=str(item["kind"]),
                                   question=str(item["question"]),
                                   answer=str(item["answer"]),
                                   supersedes=str(item.get("supersedes") or "")))
        except (KeyError, TypeError):
            # Битую запись пропускаем, остальные читаем: журнал с одной
            # испорченной строкой полезнее, чем пустой.
            continue
    return result


def next_question_id(decisions: Sequence[Decision], kind: str) -> str:
    """Следующий идентификатор вопроса этого вида.

    Номер берётся из журнала, а не из счётчика в прогоне: прогон теряется,
    журнал остаётся. Идентификатор читаем человеком — он попадает в
    комментарий и в историю задачи.
    """
    used = sum(1 for decision in decisions if decision.kind == kind)
    return f"{kind}-{used + 1}"


def effective(decisions: Sequence[Decision]) -> list[Decision]:
    """Действующие решения: без тех, что кем-то отменены."""
    superseded = {d.supersedes for d in decisions if d.supersedes}
    return [d for d in decisions if d.question_id not in superseded]
