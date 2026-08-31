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

import dataclasses
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

    `announced` — признак «комментарий с этим вопросом человеку уже
    опубликован». Третий круг ревью `ask_question` (`worker/activities.py`)
    искал этот признак перебором ленты комментариев — сначала первой
    страницей (самой старой), потом прыжком на последнюю (которая на длинной
    ленте, где общее число комментариев на единицу больше кратного странице,
    содержит один элемент и роняет маркер с предыдущей страницы), и оба раза
    расходился поведением между GitHub и GitLab. Три захода на одну и ту же
    находку — верный признак того, что чинили не там: у ленты комментариев
    нет дешёвого и надёжного доступа «покажи последние N», и опираться на неё
    как на хранилище признака не стоило вовсе. Признак переехал туда же, где
    живёт остальное состояние вопроса, — в этот же блок тела Issue, который
    читается одним обращением и пагинации не имеет.

    Умолчание `False` — умышленный выбор в пользу того же принципа, которым
    оправдан весь этот модуль (см. докстринг класса и `comment_marker`):
    задать вопрос дважды дёшево, а потерять его молча — недопустимо. Блок,
    записанный ДО этого поля (прежней версией кода), при чтении получит
    `announced=False` по умолчанию (см. `parse_question`) — то есть будет
    считаться ещё не объявленным. Для вопроса, застрявшего в старом дефекте
    круга 1 (тело записано, комментарий так и не ушёл), это ровно то, что
    нужно: комментарий наконец уйдёт. Для вопроса, который под старым кодом
    УЖЕ был полностью объявлен, это даст один лишний комментарий-дубликат при
    первом вызове после обновления — переходная, разовая и ограниченная
    ценой издержка, не постоянно повторяющийся дефект, а после первого же
    вызова признак проставится и дальше активность снова идемпотентна.
    """

    id: str
    kind: str
    text: str
    options: tuple[str, ...] = ()
    announced: bool = False


def comment_marker(question_id: str) -> str:
    """Невидимый маркер комментария, которым задан именно этот вопрос.

    До третьего круга ревью этот маркер был ЕДИНСТВЕННЫМ признаком «комментарий
    с этим вопросом уже опубликован» — `ask_question` перебирала им ленту
    комментариев. Три захода подряд на один и тот же дефект (обзор в
    докстринге `Question.announced`) показали, что у ленты нет дешёвого и
    надёжного доступа «покажи последние N», и опираться на неё как на
    хранилище признака не стоило. Признак переехал в поле `Question.announced`
    в теле Issue; за маркером в комментарии осталась другая, более скромная
    роль — человек-читатель и любой инструмент, листающий ленту, могут по
    невидимому тегу опознать, к какому именно вопросу относится этот
    комментарий (у задачи вопросов бывает несколько, с разными id). Код
    контура маркер обратно из ленты больше не читает.

    HTML-комментарий невидим в отрендеренном Markdown — тем же приёмом, что и
    `agent_comment.MARKER` и маркеры блоков `issue_blocks`.
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
                  "text": question.text, "options": list(question.options),
                  "announced": question.announced},
                 "## Открытый вопрос контура")


def parse_question(payload: str | None) -> Question | None:
    """Вопрос из содержимого ОДНОГО размеченного блока, не из тела Issue целиком.

    `payload` — то, что вернул `issue_blocks.read(body, issue_blocks.QUESTION)`,
    то есть уже вырезанный блок. Тело Issue целиком не годится в аргумент: в
    нём рядом может лежать ещё и блок журнала решений, а тогда заборов кода
    в куске окажется больше одного и `_unwrap` вернёт None как для любой
    другой порчи (ревью, находка 3) — вместо того чтобы гадать, какой забор
    имелся в виду.

    `announced` читается через `.get(..., False)` — как и `options` чуть выше,
    ради обратной совместимости с блоком, который записала версия кода ДО
    этого поля (см. докстринг `Question.announced`): ключа в JSON нет вовсе,
    и это не порча, а просто более старая запись.
    """
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return None
    try:
        return Question(id=str(data["id"]), kind=str(data["kind"]),
                        text=str(data["text"]),
                        options=tuple(str(item) for item in data.get("options", ())),
                        announced=bool(data.get("announced", False)))
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


def mark_announced(body: str | None, question: Question) -> str:
    """Тело с тем же вопросом, но с признаком `announced=True`.

    Третий круг ревью `ask_question` (`worker/activities.py`, см. докстринг
    `Question.announced`). Вызывать ПОСЛЕ того, как комментарий с вопросом
    успешно ушёл человеку, а не раньше и не вместо `write_open` при создании
    вопроса: признак обязан отражать факт, а не намерение.

    `question` здесь — тот же объект, что вернул `read_open`/только что был
    записан `write_open`: `dataclasses.replace` меняет только `announced`,
    id/kind/text/options остаются как были. Если передать за `question`
    вопрос с другим id, в теле молча окажется подмена — вызывающий отвечает
    за то, что это тот же самый вопрос, так же как и у `write_open`.
    """
    return write_open(body, dataclasses.replace(question, announced=True))


def clear_open(body: str | None) -> str:
    return issue_blocks.strip(body, issue_blocks.QUESTION)


@dataclass(frozen=True)
class Draft:
    """Толкование свободного ответа, ожидающее подтверждения человеком.

    Черновик, а не журнал: пока не подтверждён, ни в решения, ни в ANSWERS
    не попадает — второй ответ восстанавливает его отсюда, а не разбором
    прозы предыдущего комментария (тот же принцип, что у остального модуля,
    см. его докстринг).

    Ревью `worker/activities.py:_confirm_free_text`, находки 1 и 2 (обе
    Critical).

    `announced` — признак «комментарий с этим толкованием уже опубликован»,
    заведённый по образцу `Question.announced` (см. её докстринг: та же
    задача — отличить «записано в тело» от «увидено человеком» — решается
    здесь для другой стороны того же протокола вопрос/ответ). Без него
    ретрай `answer_question` после обрыва между записью черновика и
    публикацией комментария находил бы уже лежащий в теле черновик и считал
    ЕГО вторым ответом — толкование фиксировалось бы решением, хотя человек
    его ни разу не видел (находка 1). Подтверждать можно только черновик с
    `announced=True`; для `announced=False` активность обязана доделать
    недостающую публикацию, а не толковать ответ заново и не принимать
    решение — тем же приёмом, каким `ask_question` доделывает недостающий
    комментарий, не создавая вопрос заново.

    `question_id` привязывает черновик к вопросу, для которого он написан.
    Открытый вопрос в теле всегда один, но его id со временем меняется:
    вопрос закрывается решением либо возрождается заново под новым id
    (`answer_question`, ветка "reasked"). Черновик, оставшийся от вопроса,
    который уже закрыт или возрождён, — чужой: подтверждать им ДРУГОЙ,
    ныне открытый вопрос нельзя (находка 2). Без этой привязки забытый
    черновик — человек ответил на свой вопрос номером варианта вместо
    подтверждения показанного толкования, и черновик остался висеть, —
    молча перехватывал бы СЛЕДУЮЩИЙ свободный ответ на СОВЕРШЕННО ДРУГОЙ
    вопрос этой же задачи, не позвав модель и проигнорировав то, что
    человек написал на самом деле.

    `interpretation` — сырой `answer_interpretation.Interpretation.
    model_dump()`, а не сама pydantic-модель: зависимость идёт в обратную
    сторону (`answer_interpretation` импортирует этот модуль, не наоборот),
    и толкование хранится так же, как `Question` хранит kind/text/options —
    обычным JSON-совместимым словарём.
    """

    question_id: str
    interpretation: dict
    announced: bool = False


def render_draft(draft: Draft) -> str:
    return _wrap({"question_id": draft.question_id,
                  "interpretation": draft.interpretation,
                  "announced": draft.announced},
                 "## Ожидает подтверждения")


def parse_draft(payload: str | None) -> Draft | None:
    """Черновик из содержимого ОДНОГО размеченного блока, не из тела Issue целиком.

    Тот же контракт, что у `parse_question`/`parse_journal` (см. их
    докстринги и `_unwrap`): кусок с более чем одним забором кода —
    испорченный вход, результат — None.

    Черновик, записанный ДО поля `question_id` (версией кода задачи 6, где
    в блоке лежал голый `Interpretation.model_dump()` без этого ключа),
    сюда не попадёт: `data["question_id"]` поднимет KeyError, и функция
    вернёт None — «черновика нет», как и для любой другой порчи. Это
    осознанно: такой черновик по построению не мог быть ни объявлен, ни
    привязан к вопросу под новой логикой, и представлять его как валидный
    было бы неверно — второй ответ человека попросту истолкуется заново.
    """
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return None
    try:
        return Draft(question_id=str(data["question_id"]),
                    interpretation=dict(data["interpretation"]),
                    announced=bool(data.get("announced", False)))
    except (KeyError, TypeError):
        return None


def read_draft(body: str | None) -> Draft | None:
    """Толкование, ожидающее подтверждения. Нет или испорчено — None.

    Второй `/harness-answer` на тот же вопрос узнаётся ПО ЭТОМУ черновику
    (`worker/activities.py:_confirm_free_text`), а не разбором текста
    предыдущего комментария — правка формулировки вокруг сломала бы
    восстановление молча (тот же принцип, что у остального модуля, см. его
    докстринг). Порча блока здесь безопасно деградирует до «черновика нет»:
    следующий ответ человека будет истолкован заново, а не потерян.

    Логируем причину тем же приёмом, что и `read_open`/`read_journal`
    (ревью, находка 2 у обеих): порча блока не должна тонуть без следа в
    логе, даже когда для вызывающего это лишь повод истолковать ответ заново.
    """
    try:
        payload = issue_blocks.read(body, issue_blocks.DRAFT)
    except ValueError as exc:
        logger.warning("тело повреждено для блока %s — черновика нет: %s",
                       issue_blocks.DRAFT, exc)
        return None
    return parse_draft(payload)


def write_draft(body: str | None, draft: Draft) -> str:
    return issue_blocks.write(body, issue_blocks.DRAFT, render_draft(draft))


def mark_draft_announced(body: str | None, draft: Draft) -> str:
    """Тело с тем же черновиком, но с признаком `announced=True`.

    Ревью, находка 1 (Critical, см. докстринг `Draft.announced`). Вызывать
    ПОСЛЕ того, как комментарий с толкованием успешно ушёл человеку, а не
    раньше и не вместо `write_draft` при создании черновика — признак обязан
    отражать факт показа, а не намерение его показать. Тот же порядок и то
    же обоснование, что у `mark_announced` для вопроса (см. её докстринг).

    `draft` здесь — тот же объект, что вернул `read_draft`/только что был
    записан `write_draft`: `dataclasses.replace` меняет только `announced`.
    """
    return write_draft(body, dataclasses.replace(draft, announced=True))


def clear_draft(body: str | None) -> str:
    return issue_blocks.strip(body, issue_blocks.DRAFT)


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
