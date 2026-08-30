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
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

# Логгер по правилам shared/ (см. shared/task_context.py): модуль остаётся
# чистым — логирование не сеть и не GitHub, а без него порча тела тонет без
# следа (ревью, находка 2).
logger = logging.getLogger(__name__)

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


def comment_marker(question_id: str) -> str:
    """Невидимый маркер комментария, которым задан именно этот вопрос.

    Ревью, находка 1 (Critical) и находка 2 (Important) для `ask_question`.
    Активность обязана быть идемпотентной по КАЖДОМУ из своих следствий (блок
    в теле, комментарий, метка), а не только по первому — иначе обрыв между
    записью тела и публикацией комментария прячет вопрос от человека
    навсегда: тело переживает перезапуск прогона, следующий вызов видит блок
    и молча считает вопрос уже заданным.

    Чтобы сверить «комментарий с ЭТИМ вопросом уже есть», а не просто «наш
    комментарий где-то есть», нужен признак, привязанный к идентификатору
    вопроса, а не к одному общему `agent_comment.MARKER`: у задачи вопросов
    бывает несколько, и по общей подписи второй вопрос счёл бы себя уже
    опубликованным из-за комментария первого. HTML-комментарий невидим в
    отрендеренном Markdown — тем же приёмом, что и `agent_comment.MARKER` и
    маркеры блоков `issue_blocks`.
    """
    return f"<!-- harness:question-comment:{question_id} -->"


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
    """JSON из ЕДИНСТВЕННОГО забора кода.

    На вход — содержимое ОДНОГО размеченного блока (то, что возвращает
    `issue_blocks.read(body, <имя блока>)`), а не тело Issue целиком: у
    журнала и у вопроса свои отдельные блоки, и смешивать их не
    предполагается.

    Ничего не разобралось — None. Заборов кода в переданном куске БОЛЬШЕ
    ОДНОГО — тоже None (ревью, находка 3, Critical): это признак испорченного
    входа (например, вызвали не на содержимом блока, а на теле целиком, где
    рядом лежит ещё один блок), и выбор первого попавшегося забора молча
    подставил бы чужую запись вместо честного отказа.
    """
    if not payload:
        return None
    matches = list(_JSON_BLOCK.finditer(payload))
    if len(matches) != 1:
        return None
    try:
        return json.loads(matches[0].group("payload"))
    except (ValueError, TypeError):
        # Тело Issue правят руками, и обрывок JSON там появится рано или поздно.
        # Это отсутствие записи, а не отказ: вызывающий решит, что делать.
        return None


def render_question(question: Question) -> str:
    return _wrap({"id": question.id, "kind": question.kind,
                  "text": question.text, "options": list(question.options)},
                 "## Открытый вопрос контура")


def parse_question(payload: str | None) -> Question | None:
    """Вопрос из содержимого ОДНОГО размеченного блока, не из тела Issue целиком.

    `payload` — то, что вернул `issue_blocks.read(body, issue_blocks.QUESTION)`,
    то есть уже вырезанный блок. Тело Issue целиком не годится в аргумент: в
    нём рядом может лежать ещё и блок журнала решений, а тогда заборов кода
    в куске окажется больше одного и `_unwrap` вернёт None как для любой
    другой порчи (ревью, находка 3) — вместо того чтобы гадать, какой забор
    имелся в виду.
    """
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
    """Журнал из содержимого ОДНОГО размеченного блока, не из тела Issue целиком.

    `payload` — то, что вернул `issue_blocks.read(body, issue_blocks.ANSWERS)`.
    Тот же контракт, что у `parse_question` (см. её докстринг и `_unwrap`):
    кусок с более чем одним забором кода — испорченный вход, результат — []
    (ревью, находка 3), а не журнал, собранный из первого попавшегося забора.
    """
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


_TRAILING_NUMBER = re.compile(r"-(\d+)$")


def next_question_id(decisions: Sequence[Decision], kind: str) -> str:
    """Следующий идентификатор вопроса этого вида.

    Номер берётся из журнала, а не из счётчика в прогоне: прогон теряется,
    журнал остаётся. Идентификатор читаем человеком — он попадает в
    комментарий и в историю задачи.

    Ревью, находка 1 (Critical). Номер — МАКСИМАЛЬНЫЙ среди записей этого
    вида плюс единица, а не количество таких записей: тело Issue правят
    руками, и если запись из середины журнала пропала, счёт «по количеству»
    выдал бы уже занятый идентификатор (два `howtodemo-3` в журнале ломают
    уникальность `question_id`, на которой держатся `effective()`, сам
    журнал и указатель текущего вопроса в прогоне). Записи, чей id не
    оканчивается на `-<число>` (испорчены вручную или принадлежат другому
    формату), в подсчёте номера не участвуют, но из журнала не выбрасываются
    — это забота `parse_journal`, не этой функции.
    """
    max_used = 0
    for decision in decisions:
        if decision.kind != kind:
            continue
        match = _TRAILING_NUMBER.search(decision.question_id)
        if match:
            max_used = max(max_used, int(match.group(1)))
    return f"{kind}-{max_used + 1}"


def effective(decisions: Sequence[Decision]) -> list[Decision]:
    """Действующие решения: без тех, что кем-то отменены.

    Ревью, находка 2 (Important). Журнал только пополняется, значит отмена
    ВСЕГДА приходит позже отменяемого во времени. Поэтому запись считается
    отменённой, только если ссылающаяся на неё запись `supersedes` стоит
    ПОЗЖЕ неё в журнале (по индексу), а не просто существует где-то рядом.
    До правки простое множество идентификаторов-целей не смотрело на
    порядок: цикл ссылок (`a-1 supersedes a-2`, `a-2 supersedes a-1`) отменял
    ОБЕ записи разом, и действующего решения не оставалось вовсе — молчаливый
    отказ, худший класс дефектов в этом контуре. С учётом порядка цикл рвётся
    сам собой: ссылка «вперёд по времени» просто не в счёт, отдельная защита
    от циклов не нужна. Ссылка на несуществующую запись по-прежнему ни на что
    не влияет — такого id нет среди индексов, и вычёркивать нечего.
    """
    index_by_id = {d.question_id: i for i, d in enumerate(decisions)}
    superseded_indices: set[int] = set()
    for i, d in enumerate(decisions):
        if not d.supersedes:
            continue
        target_index = index_by_id.get(d.supersedes)
        if target_index is not None and target_index < i:
            superseded_indices.add(target_index)
    return [d for i, d in enumerate(decisions) if i not in superseded_indices]


from shared import issue_blocks  # noqa: E402  (внизу — модуль выше не зависит от блоков)


class CorruptedJournal(RuntimeError):
    """Блок журнала решений (`ANSWERS`) в теле Issue есть, но JSON внутри не разбирается.

    Ревью, находка 1 (Critical). Не тот же случай, что ValueError из
    `issue_blocks.read`: там порчены МАРКЕРЫ (парная разметка сломана), а
    здесь маркеры целы — испорчено содержимое между ними (тело правили
    руками, JSON внутри оборван). `append_decision`, увидев такое, обязана
    отказать, а не молча переписать блок единственной новой записью — иначе
    вся прежняя история решений исчезает без следа, без исключения и без
    строки в логе.

    RuntimeError, а не ValueError или голый `Exception`: в `worker/workflows.py`
    (комментарий «Граница по типу») именно RuntimeError размечает сбои стадии
    как невосстановимые ретраем — повторный вызов активности не починит
    испорченный JSON в теле Issue, чинить может только человек, а значит
    ошибка обязана дойти до него, а не тонуть в автоматическом повторе.
    """


def read_open(body: str | None) -> Question | None:
    """Открытый вопрос из тела Issue. Нет блока или он испорчен — None.

    Ревью, находка 2 (Important). Порча МАРКЕРОВ раньше проглатывалась молча:
    `ValueError` гасился без единого следа в логе, неотличимо от «блока
    никогда не было». Логируем причину тем же приёмом, что и
    `worker/activities.py` для блока HOWTODEMO (`_howtodemo_block`), и только
    потом деградируем до None.
    """
    try:
        return parse_question(issue_blocks.read(body, issue_blocks.QUESTION))
    except ValueError as exc:
        logger.warning("тело повреждено для блока %s — вопроса нет: %s",
                       issue_blocks.QUESTION, exc)
        return None


def write_open(body: str | None, question: Question) -> str:
    return issue_blocks.write(body, issue_blocks.QUESTION, render_question(question))


def clear_open(body: str | None) -> str:
    return issue_blocks.strip(body, issue_blocks.QUESTION)


def read_journal(body: str | None) -> list[Decision]:
    """Журнал решений из тела Issue. Нет блока или он испорчен — [].

    Ревью, находка 2 (Important), тот же случай, что у `read_open`: порча
    маркеров раньше проглатывалась молча, теперь — с предупреждением в лог.
    """
    try:
        return parse_journal(issue_blocks.read(body, issue_blocks.ANSWERS))
    except ValueError as exc:
        logger.warning("тело повреждено для блока %s — журнал пуст: %s",
                       issue_blocks.ANSWERS, exc)
        return []


def append_decision(body: str | None, decision: Decision) -> str:
    """Дописать решение в журнал. Журнал только пополняется.

    Ревью, находка 1 (Critical). Раньше запись шла через `read_journal`,
    которая ЛЮБУЮ порчу блока — включая «маркеры целы, JSON внутри оборван»
    — превращала в пустой список, неотличимый от «журнала никогда не было».
    `append_decision` в этом случае считала журнал пустым и переписывала блок
    одной новой записью: прежние решения исчезали бесследно.

    Чтобы отличить два случая, читаем блок сами (`issue_blocks.read`, не
    `read_journal`) и проверяем: содержимое непустое, а `_unwrap` не вернул
    список — значит разобрать его не удалось, это порча, и двигаться дальше
    нельзя. Легитимный пустой журнал (блок с `[]`) от порчи так отличается:
    там `_unwrap` успешно возвращает пустой список, а не None и не что-то
    другое. Тело при отказе не меняется — `issue_blocks.write` до него не
    доходит.
    """
    raw = issue_blocks.read(body, issue_blocks.ANSWERS)
    if raw is not None and raw.strip() and not isinstance(_unwrap(raw), list):
        raise CorruptedJournal(
            f"журнал решений повреждён: блок {issue_blocks.ANSWERS!r} в теле Issue "
            "есть, но JSON внутри не разбирается (похоже на ручную правку тела, "
            "оборвавшую запись). Отказываю дописывать решение "
            f"{decision.question_id!r} ({decision.kind!r}), чтобы не переписать блок "
            "единственной новой записью и не стереть прежнюю историю решений. "
            "Почини JSON в блоке ANSWERS в теле Issue вручную (или восстанови его "
            "из истории правок Issue) и повтори команду. Начало испорченного "
            f"содержимого блока: {raw.strip()[:200]!r}"
        )
    journal = parse_journal(raw)
    journal.append(decision)
    return issue_blocks.write(body, issue_blocks.ANSWERS, render_journal(journal))
