# Команда `/harness-answer` — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Контур умеет задать человеку вопрос и принять на него ответ одной общей командой — так, что вопрос переживает потерю прогона, а принятые решения накапливаются в задаче и участвуют в толковании следующих ответов.

**Architecture:** Содержание вопроса и журнал решений живут размеченными блоками в теле Issue (`shared/issue_blocks.py`), сериализованные JSON внутри забора кода — ответы бывают многострочными, и запись обязана возвращаться из тела ровно такой, какой ушла. Прогон хранит только указатель на идентификатор открытого вопроса. Разбор и рендер вынесены в чистый модуль `shared/questions.py`, активности только ходят в GitHub, воркфлоу только маршрутизирует.

**Tech Stack:** Python 3.12, Temporal Python SDK, pytest, `worker/llm.py` (instructor) для толкования свободного ответа, GitHub REST через `worker/github_client.py`.

## Global Constraints

- Тесты гонять командой репозитория: `python -m pytest -q`. Порог покрытия — 83%, проверяется в том же прогоне; красный прогон в PR не отдаём.
- **Раскладка:** `worker/` и `webhook/` НЕ пакеты — Dockerfile расплющивает их в `/app`. Импорт `from worker.X import ...` падает в контейнере. Внутри воркера — `import activities`, `import github_client`. Общий код — только `shared/` (AGENTS.md, правило 7).
- **Фикстура pytest из чужого тестового модуля не видна** — `conftest.py` либо своя копия (AGENTS.md, правило 8).
- **Правка решения воркфлоу требует `workflow.patched(...)`.** Ветка, которую прогон уже выбрал, записана в его историю; новый код на реплее выберет другую и уронит прогон `Nondeterminism error`. Активности маркера не требуют.
- Гвард реплея `tests/test_workflow_replay.py` обязан оставаться зелёным.
- Комментарии контура подписываются `shared/agent_comment.sign(body)` — иначе вебхук примет собственный комментарий за реплику человека.
- **Права на ответ не ограничиваются** (A8). Проверки `AGENT_TRIGGER_ALLOWLIST` для этой команды НЕ добавлять.
- Спецификация: `docs/superpowers/specs/2026-08-29-harness-answer-command-design.md`, требования A1–A28.

## Что уже сделано

В `main` (коммит `107a14a`) лежит: русские формы заголовка сценария приёмки, блок `issue_blocks.HOWTODEMO`, приоритет утверждённого блока над разделом, публичная `issue_blocks.strip(body, name)`. Эти вещи заново не делать.

---

### Task 1: Модель вопроса и журнала решений

Закрывает A10, A11, A19 в части структуры данных. Чистый модуль без сети — самая проверяемая часть механизма.

**Files:**
- Create: `shared/questions.py`
- Test: `tests/test_questions.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `@dataclass(frozen=True) Question` с полями `id: str`, `kind: str`, `text: str`, `options: tuple[str, ...] = ()`
  - `@dataclass(frozen=True) Decision` с полями `question_id: str`, `kind: str`, `question: str`, `answer: str`, `supersedes: str = ""`
  - `render_question(question: Question) -> str` и `parse_question(payload: str | None) -> Question | None`
  - `render_journal(decisions: Sequence[Decision]) -> str` и `parse_journal(payload: str | None) -> list[Decision]`
  - `next_question_id(decisions: Sequence[Decision], kind: str) -> str`
  - `effective(decisions: Sequence[Decision]) -> list[Decision]`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_questions.py`:

```python
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
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_questions.py -q -p no:randomly --no-cov`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.questions'`

- [ ] **Step 3: Написать модуль**

```python
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
```

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_questions.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add shared/questions.py tests/test_questions.py
git commit -m "feat(questions): модель вопроса контура и журнала решений"
```

---

### Task 2: Вопрос и журнал в теле Issue

Закрывает A10, A19 в части хранения.

**Files:**
- Modify: `shared/issue_blocks.py`
- Modify: `shared/questions.py`
- Test: `tests/test_issue_blocks.py`, `tests/test_questions.py`

**Interfaces:**
- Consumes: `Question`, `Decision`, `render_*`, `parse_*` из Task 1; `issue_blocks.read/write/strip` из `main`
- Produces:
  - `issue_blocks.QUESTION = "question"`, `issue_blocks.ANSWERS = "answers"`, оба в `_ALL_BLOCKS`
  - `questions.read_open(body: str | None) -> Question | None`
  - `questions.write_open(body: str | None, question: Question) -> str`
  - `questions.clear_open(body: str | None) -> str`
  - `questions.read_journal(body: str | None) -> list[Decision]`
  - `questions.append_decision(body: str | None, decision: Decision) -> str`

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_issue_blocks.py`:

```python
def test_question_and_answers_blocks_are_known():
    """Оба блока в реестре: порча тела даёт громкую ошибку, а не перезапись."""
    assert issue_blocks.QUESTION in issue_blocks._ALL_BLOCKS
    assert issue_blocks.ANSWERS in issue_blocks._ALL_BLOCKS
```

В `tests/test_questions.py`:

```python
def test_open_question_write_read_clear():
    question = questions.Question(id="howtodemo-1", kind="howtodemo",
                                  text="Чем принимать?", options=("а", "б"))
    body = questions.write_open("описание задачи", question)
    assert questions.read_open(body) == question
    assert "описание задачи" in body

    cleared = questions.clear_open(body)
    assert questions.read_open(cleared) is None
    assert "описание задачи" in cleared


def test_read_open_of_body_without_block_is_none():
    assert questions.read_open("просто описание") is None
    assert questions.read_open(None) is None


def test_append_decision_accumulates_and_keeps_order():
    """Журнал пополняется, порядок записей сохраняется."""
    body = questions.append_decision("описание", questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q1", answer="a1"))
    body = questions.append_decision(body, questions.Decision(
        question_id="howtodemo-2", kind="howtodemo", question="q2", answer="a2",
        supersedes="howtodemo-1"))
    journal = questions.read_journal(body)
    assert [d.question_id for d in journal] == ["howtodemo-1", "howtodemo-2"]
    assert [d.answer for d in questions.effective(journal)] == ["a2"]
    assert "описание" in body


def test_question_block_and_journal_coexist_with_other_blocks():
    """Четыре блока в одном теле не мешают друг другу."""
    body = issue_blocks.write("описание", issue_blocks.GROW, "- [ ] находка")
    body = issue_blocks.write(body, issue_blocks.HOWTODEMO, "критерий")
    body = questions.write_open(body, questions.Question(
        id="mvp-bounds-1", kind="mvp-bounds", text="Что в MVP?"))
    body = questions.append_decision(body, questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q", answer="a"))

    assert issue_blocks.read(body, issue_blocks.GROW) == "- [ ] находка"
    assert issue_blocks.read(body, issue_blocks.HOWTODEMO) == "критерий"
    assert questions.read_open(body).id == "mvp-bounds-1"
    assert [d.question_id for d in questions.read_journal(body)] == ["howtodemo-1"]
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_questions.py tests/test_issue_blocks.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'shared.issue_blocks' has no attribute 'QUESTION'`

- [ ] **Step 3: Завести блоки**

В `shared/issue_blocks.py` рядом с существующими именами:

```python
# Открытый вопрос контура к человеку: идентификатор, текст, варианты.
# Машинная запись; человеку тот же вопрос достаётся комментарием.
QUESTION = "question"

# Журнал принятых решений. Только пополняется: отменённая запись остаётся
# видимой, иначе история задачи перестаёт отвечать на вопрос «что решали
# раньше и почему передумали».
ANSWERS = "answers"
```

и в реестр:

```python
_ALL_BLOCKS = (MVP_PLAN, GROW, HOWTODEMO, QUESTION, ANSWERS)
```

- [ ] **Step 4: Написать доступ из `shared/questions.py`**

Дописать в конец `shared/questions.py`:

```python
from shared import issue_blocks  # noqa: E402  (внизу — модуль выше не зависит от блоков)


def read_open(body: str | None) -> Question | None:
    """Открытый вопрос из тела Issue. Нет блока или он испорчен — None."""
    try:
        return parse_question(issue_blocks.read(body, issue_blocks.QUESTION))
    except ValueError:
        # Тело повреждено непарным маркером. Для вызывающего это «вопроса
        # нет»: решать, что делать с повреждённым телом, — не наша забота.
        return None


def write_open(body: str | None, question: Question) -> str:
    return issue_blocks.write(body, issue_blocks.QUESTION, render_question(question))


def clear_open(body: str | None) -> str:
    return issue_blocks.strip(body, issue_blocks.QUESTION)


def read_journal(body: str | None) -> list[Decision]:
    try:
        return parse_journal(issue_blocks.read(body, issue_blocks.ANSWERS))
    except ValueError:
        return []


def append_decision(body: str | None, decision: Decision) -> str:
    """Дописать решение в журнал. Журнал только пополняется."""
    journal = read_journal(body)
    journal.append(decision)
    return issue_blocks.write(body, issue_blocks.ANSWERS, render_journal(journal))
```

Импорт стоит внизу файла намеренно: верхняя половина модуля — чистые структуры и сериализация, они не зависят от способа хранения. Если импорт мешает линтеру, перенеси его наверх — на поведение это не влияет.

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_questions.py tests/test_issue_blocks.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 6: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 7: Коммит**

```bash
git add shared/issue_blocks.py shared/questions.py tests/test_issue_blocks.py tests/test_questions.py
git commit -m "feat(questions): вопрос и журнал решений живут блоками в теле Issue"
```

---

### Task 3: Команда `/harness-answer`

Закрывает A1, A2, A3, A7.

**Files:**
- Modify: `shared/commands.py`
- Modify: `shared/label_catalog.py`
- Test: тесты команд и каталога меток (найди существующие файлы этих тестов, новые не заводи)

**Interfaces:**
- Consumes: ничего
- Produces: `commands.HARNESS_ANSWER = "harness-answer"`; `commands.NO_RUN_LABEL_COMMANDS: frozenset[str]`; `parse_command("/harness-answer 1") == HARNESS_ANSWER`; `parse_command_args` отдаёт хвост многострочно

- [ ] **Step 1: Написать падающие тесты**

```python
def test_harness_answer_is_a_command_with_multiline_tail():
    """Ответ человека — команда с многострочным хвостом.

    Сценарий приёмки в одну строку не пишут, поэтому хвост забирается
    целиком, как у /bft-deep.
    """
    body = "/harness-answer 405 на любой метод кроме POST\nREADME не трогаем"
    assert commands.parse_command(body) == commands.HARNESS_ANSWER
    assert commands.parse_command_args(body) == \
        "405 на любой метод кроме POST\nREADME не трогаем"


def test_harness_answer_with_number_only():
    assert commands.parse_command("/harness-answer 1") == commands.HARNESS_ANSWER
    assert commands.parse_command_args("/harness-answer 1") == "1"


def test_harness_answer_with_empty_tail():
    """Пустой хвост — команда есть, содержания нет. Разбирает вызывающий."""
    assert commands.parse_command("/harness-answer") == commands.HARNESS_ANSWER
    assert commands.parse_command_args("/harness-answer") == ""


def test_quoted_harness_answer_is_not_a_command():
    assert commands.parse_command("> /harness-answer 1") is None
```

и в тестах каталога меток:

```python
def test_harness_answer_does_not_produce_run_labels():
    """Ответ человека — не дорогая стадия, меток прогона у него нет.

    Каталог выводит run:/done:/failed: из перечня команд автоматически;
    без исключения на задачах появилось бы `run:harness-answer`.
    """
    known = label_catalog.all_labels()
    for label in ("run:harness-answer", "done:harness-answer",
                  "failed:harness-answer"):
        assert label not in known, label
```

Если функция каталога называется не `all_labels`, возьми существующее имя из `shared/label_catalog.py`.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest -q -p no:randomly --no-cov -k "harness_answer"`
Expected: FAIL с `AttributeError: module 'shared.commands' has no attribute 'HARNESS_ANSWER'`

- [ ] **Step 3: Завести команду**

В `shared/commands.py`:

```python
# Ответ человека на вопрос, заданный контуром. Команда ОБЩАЯ, не привязанная к
# поводу: тем же способом контур спрашивает про критерий приёмки, про границы
# MVP, про выбор из вариантов плана. Один способ ответа на любой вопрос лучше
# выводка команд под каждый повод.
#
# Дорогую стадию не запускает — меток прогона у неё быть не должно, см.
# NO_RUN_LABEL_COMMANDS и исключение в shared/label_catalog.py.
HARNESS_ANSWER = "harness-answer"
```

в перечень:

```python
_COMMANDS = {"/estimate": ESTIMATE, "/analyze": ANALYZE, "/research": RESEARCH,
             "/bft": BFT, "/bft-deep": BFT_DEEP, "/release": RELEASE,
             "/howtodemo": HOWTODEMO, "/harness-answer": HARNESS_ANSWER}

# Команды, не запускающие дорогую стадию: у них нет прогона, а значит нет и
# меток его состояния.
NO_RUN_LABEL_COMMANDS = frozenset({HARNESS_ANSWER})
```

- [ ] **Step 4: Исключить из каталога меток**

В `shared/label_catalog.py`, функция `_all_command_labels`, добавить пропуск:

```python
    for command in commands._COMMANDS.values():
        if command in commands.NO_RUN_LABEL_COMMANDS:
            continue
        result.add(commands.run_label(command))
        result.add(commands.done_label(command))
        result.add(commands.failed_label(command))
```

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 6: Коммит**

```bash
git add shared/commands.py shared/label_catalog.py tests/
git commit -m "feat(commands): /harness-answer — ответ человека на вопрос контура"
```

---

### Task 4: Активность «задать вопрос»

Закрывает A9, A12, A13, A24.

**Files:**
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Modify: `shared/labels.py`
- Test: `tests/test_ask_question.py`

**Interfaces:**
- Consumes: `shared.questions` из Task 1 и 2
- Produces: активность `ask_question(issue, kind: str, text: str, options: list[str]) -> str` — возвращает идентификатор ОТКРЫТОГО вопроса: только что заданного либо уже висевшего. Имя для `execute_activity` — `activities.ask_question`. Метка `labels.NEEDS_HUMAN_ANSWER`.

- [ ] **Step 1: Метка ожидания**

В `shared/labels.py` рядом с `NEEDS_HUMAN_TRIAGE`:

```python
# Ждём ответа человека на заданный контуром вопрос.
NEEDS_HUMAN_ANSWER = f"{NEEDS_HUMAN_PREFIX}answer"
```

- [ ] **Step 2: Написать падающие тесты**

`tests/test_ask_question.py`:

```python
import pytest

import activities as a
from shared import labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="GET /quote отдаёт 404",
                      body="Сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями и метками в памяти."""
    state = {"body": issue.body, "comments": [], "labels": set()}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(body))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    return state


def test_question_lands_in_body_comment_and_label(github, issue):
    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?",
                                 ["было 404; стало 405", "то же плюс OPTIONS"])

    assert question_id == "howtodemo-1"
    stored = questions.read_open(github["body"])
    assert stored.id == "howtodemo-1"
    assert stored.kind == "howtodemo"
    assert stored.options == ("было 404; стало 405", "то же плюс OPTIONS")
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]
    assert len(github["comments"]) == 1


def test_comment_names_the_command_verbatim(github, issue):
    """Комментарий обязан назвать команду ответа дословно (A12).

    Отказ, ради которого это написано: приёмка отвечала «добавьте раздел
    HowToDemo» и не сказала, как отвечать, — это стоило впустую потраченного
    прогона разработки.
    """
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["вариант один"])
    comment = github["comments"][0]
    assert "/harness-answer" in comment
    assert "обычный комментарий" in comment.lower()
    assert "вариант один" in comment
    assert "<!-- issue-agent -->" in comment


def test_open_question_is_not_asked_twice(github, issue):
    """Вопрос уже висит — второй экземпляр в ленте только запутает (A13, A24)."""
    first = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    second = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])

    assert first == second == "howtodemo-1"
    assert len(github["comments"]) == 1


def test_second_question_of_the_same_kind_continues_numbering(github, issue):
    """Нумерация ведётся по журналу и переживает потерю прогона (A11)."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    github["body"] = questions.clear_open(github["body"])
    github["body"] = questions.append_decision(github["body"], questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="Чем принимать?",
        answer="405"))

    assert a.ask_question(issue, "howtodemo", "А теперь?", ["б"]) == "howtodemo-2"


def test_question_without_options_asks_for_free_text(github, issue):
    """Вариантов нет — комментарий всё равно объясняет, как ответить (A10)."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", [])
    comment = github["comments"][0]
    assert "/harness-answer" in comment
    assert questions.read_open(github["body"]).options == ()
```

- [ ] **Step 3: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_ask_question.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'ask_question'`

- [ ] **Step 4: Написать активность**

В `worker/activities.py`:

```python
@activity.defn
def ask_question(issue, kind: str, text: str, options: list[str]) -> str:
    """Задать человеку вопрос и повесить метку ожидания.

    Возвращает идентификатор ОТКРЫТОГО вопроса — только что заданного либо уже
    висевшего. Повторный вызов второго комментария не даёт: вопрос уже в ленте,
    и второй его экземпляр человека только запутает. Это же делает активность
    безопасной после перезапуска прогона, когда задача жива, а прогон нет.
    """
    body = github_client.get_issue_body(issue.repo, issue.issue_number)

    already = questions.read_open(body)
    if already is not None:
        return already.id

    question = questions.Question(
        id=questions.next_question_id(questions.read_journal(body), kind),
        kind=kind, text=text, options=tuple(options))

    github_client.update_issue_body(issue.repo, issue.issue_number,
                                    questions.write_open(body, question))

    lines = [question.text, ""]
    if question.options:
        for number, option in enumerate(question.options, start=1):
            lines.append(f"**{number}.** {option}")
        lines.append("")
        lines.append("**Отвечать нужно командой** — обычный комментарий я не читаю:")
        lines.append("")
        lines.append(f"```\n/harness-answer 1\n```")
        lines.append("")
        lines.append("или своим текстом:")
    else:
        lines.append("**Отвечать нужно командой** — обычный комментарий я не читаю:")
    lines.append("")
    lines.append("```\n/harness-answer здесь ваш ответ\n```")

    github_client.post_comment(issue.repo, issue.issue_number,
                               agent_comment.sign("\n".join(lines)))
    github_client.add_label(issue.repo, issue.issue_number,
                            labels.NEEDS_HUMAN_ANSWER)
    return question.id
```

Проверь, что `questions` и `agent_comment` импортированы в модуле среди прочих `shared`; если нет — добавь к существующему блоку импортов.

- [ ] **Step 5: Зарегистрировать активность**

В `worker/worker.py` дописать `activities.ask_question` в перечень активностей.

- [ ] **Step 6: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_ask_question.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 7: Коммит**

```bash
git add worker/activities.py worker/worker.py shared/labels.py tests/test_ask_question.py
git commit -m "feat(questions): активность ask_question — вопрос в тело, комментарий, метка"
```

---

### Task 5: Активность «принять ответ» — простые пути

Закрывает A14, A16, A17, A18, A22, A25. Толкование свободного текста моделью — следующая задача; здесь оно заменяется прямой записью текста.

**Files:**
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Test: `tests/test_answer_question.py`

**Interfaces:**
- Consumes: `ask_question` из Task 4, `shared.questions`
- Produces: активность `answer_question(issue, question_id: str, text: str, comment_id: int | None) -> str`. Возвращает одно из: `"accepted"` (решение записано, ожидание снято), `"confirm"` (толкование показано, ждём подтверждения), `"empty"` (пустая команда, вопрос открыт), `"no-question"` (вопроса не было), `"reasked"` (блок пропал, вопрос задан заново). Имя — `activities.answer_question`.

- [ ] **Step 1: Написать падающие тесты**

`tests/test_answer_question.py`:

```python
import pytest

import activities as a
from shared import labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="t", body="описание",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    state = {"body": issue.body, "comments": [], "labels": set(), "reactions": []}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(body))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    monkeypatch.setattr(a.github_client, "add_reaction",
                        lambda repo, comment_id, content:
                            state["reactions"].append(content))
    return state


def _open(github, options=("было 404; стало 405", "то же плюс OPTIONS")):
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="howtodemo-1", kind="howtodemo", text="Чем принимать?", options=options))
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)


def test_number_records_the_decision_immediately(github, issue):
    """Номер — толкования не было, подтверждать нечего (A14)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "accepted"

    journal = questions.read_journal(github["body"])
    assert [d.answer for d in journal] == ["было 404; стало 405"]
    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]


def test_number_out_of_range_is_free_text(github, issue):
    """`/harness-answer 7` при двух вариантах — это не выбор (A16)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "7", 101) == "confirm"
    assert questions.read_open(github["body"]) is not None


def test_empty_command_reacts_and_keeps_the_question_open(github, issue):
    """Пустая команда — оговорка. Реакции, не абзац (A17)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "", 101) == "empty"

    assert set(github["reactions"]) == {"confused", "-1"}
    assert github["comments"] == []
    assert questions.read_open(github["body"]) is not None
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_answer_without_open_question_says_so(github, issue):
    """Молчание неотличимо от проглоченной команды (A18)."""
    assert a.answer_question(issue, "", "1", 101) == "no-question"
    assert len(github["comments"]) == 1
    assert "вопрос" in github["comments"][0].lower()


def test_missing_block_reasks_without_the_model(github, issue, monkeypatch):
    """Блок стёрт руками — новый вопрос свободным текстом, без модели (A22)."""
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)

    def no_model(*args, **kwargs):
        raise AssertionError("модель звать нельзя")

    monkeypatch.setattr(a, "_interpret_answer", no_model, raising=False)

    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "reasked"

    reopened = questions.read_open(github["body"])
    assert reopened is not None
    assert reopened.id != "howtodemo-1", "новый вопрос — новый идентификатор"
    assert reopened.options == (), "варианты не перегенерируются"
    assert "недействительн" in github["comments"][0].lower()


def test_body_write_failure_is_loud(github, issue, monkeypatch):
    """Доложить «принято», не записав, — худший класс отказов (A25)."""
    _open(github)

    def boom(repo, number, body):
        raise RuntimeError("GitHub 500")

    monkeypatch.setattr(a.github_client, "update_issue_body", boom)

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "1", 101)
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_answer_question.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'answer_question'`

- [ ] **Step 3: Написать активность**

В `worker/activities.py`:

```python
# Реакции на пустую команду: «?!» и «Отказ» в наборе GitHub. Реакции, а не
# комментарий: пустая команда — оговорка, и отвечать на неё абзацем значит
# засорять ленту задачи.
_EMPTY_ANSWER_REACTIONS = ("confused", "-1")


def _record_decision(issue, body: str, question, answer: str,
                     supersedes: str = "") -> None:
    """Записать решение в журнал, закрыть вопрос, снять метку ожидания."""
    body = questions.append_decision(body, questions.Decision(
        question_id=question.id, kind=question.kind, question=question.text,
        answer=answer, supersedes=supersedes))
    github_client.update_issue_body(issue.repo, issue.issue_number,
                                    questions.clear_open(body))
    github_client.remove_label(issue.repo, issue.issue_number,
                               labels.NEEDS_HUMAN_ANSWER)


@activity.defn
def answer_question(issue, question_id: str, text: str,
                    comment_id: int | None) -> str:
    """Принять ответ человека на открытый вопрос.

    `accepted`    — решение записано, ожидание снято.
    `confirm`     — толкование показано, ждём второго ответа.
    `empty`       — команда без содержания, вопрос остался открытым.
    `no-question` — вопроса не задавали.
    `reasked`     — блок вопроса пропал из тела, вопрос задан заново.

    Номер и свободный текст разведены намеренно: выбирая номер, человек
    утверждает текст, который прочитал дословно, — толковать нечего. Свободный
    текст контур истолковал заново, и это толкование должно быть предъявлено
    прежде, чем за него заплатят прогоном разработки.
    """
    answer = (text or "").strip()
    body = github_client.get_issue_body(issue.repo, issue.issue_number)
    question = questions.read_open(body)

    if question is None:
        if not question_id:
            # Вопроса не задавали вовсе. Молчание здесь неотличимо от
            # проглоченной команды.
            github_client.post_comment(
                issue.repo, issue.issue_number,
                agent_comment.sign("Сейчас я ничего не спрашивал — отвечать не на что."))
            return "no-question"

        # Прогон ждёт ответа, а блока в теле нет: его стёрли или переписали
        # тело руками. Варианты НЕ перегенерируем: старый комментарий с
        # нумерацией остался в ленте, и новая нумерация сделала бы ответ «2»
        # двусмысленным.
        journal = questions.read_journal(body)
        kind = question_id.rsplit("-", 1)[0] or "answer"
        revived = questions.Question(
            id=questions.next_question_id(journal, kind), kind=kind,
            text="Вопрос пропал из тела задачи — прежние варианты недействительны.",
            options=())
        github_client.update_issue_body(issue.repo, issue.issue_number,
                                        questions.write_open(body, revived))
        github_client.post_comment(issue.repo, issue.issue_number, agent_comment.sign(
            "Вопрос пропал из тела задачи, прежние варианты **недействительны**.\n\n"
            "Ответьте своим текстом:\n\n```\n/harness-answer здесь ваш ответ\n```"))
        github_client.add_label(issue.repo, issue.issue_number,
                                labels.NEEDS_HUMAN_ANSWER)
        return "reasked"

    if not answer:
        if comment_id is not None:
            for reaction in _EMPTY_ANSWER_REACTIONS:
                github_client.add_reaction(issue.repo, comment_id, reaction)
        return "empty"

    if answer.isdigit() and 1 <= int(answer) <= len(question.options):
        _record_decision(issue, body, question, question.options[int(answer) - 1])
        return "accepted"

    return _confirm_free_text(issue, body, question, answer)


def _confirm_free_text(issue, body: str, question, answer: str) -> str:
    """Показать, что понял, и ждать подтверждения. Толкование — в Task 6."""
    github_client.post_comment(issue.repo, issue.issue_number, agent_comment.sign(
        f"Записал так:\n\n{answer}\n\n"
        "Если верно — подтвердите:\n\n```\n/harness-answer да\n```\n\n"
        "Если нет — пришлите поправленный текст той же командой."))
    return "confirm"
```

- [ ] **Step 4: Зарегистрировать активность**

В `worker/worker.py` дописать `activities.answer_question`.

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_answer_question.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 6: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 7: Коммит**

```bash
git add worker/activities.py worker/worker.py tests/test_answer_question.py
git commit -m "feat(questions): приём ответа — номер, пустая команда, пропавший вопрос"
```

---

### Task 6: Толкование свободного ответа с журналом

Закрывает A15, A20, A21.

**Files:**
- Create: `shared/answer_interpretation.py`
- Modify: `worker/activities.py` (`_confirm_free_text`, подтверждение)
- Test: `tests/test_answer_interpretation.py`, `tests/test_answer_question.py`

**Interfaces:**
- Consumes: `shared.questions`, `worker/llm.py`
- Produces:
  - `class Amendment(BaseModel)` с полями `question_id: str`, `answer: str`
  - `class Interpretation(BaseModel)` с полями `answer: str`, `amendments: list[Amendment] = []`
  - `render_interpretation(interpretation, journal) -> str` — человекочитаемый перечень всех изменений
  - `SYSTEM_PROMPT: str`
  - `build_user_message(question, journal, answer) -> str`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_answer_interpretation.py`:

```python
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
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_answer_interpretation.py -q -p no:randomly --no-cov`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.answer_interpretation'`

- [ ] **Step 3: Написать модуль**

```python
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
```

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_answer_interpretation.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Написать падающие тесты подключения**

Дописать в `tests/test_answer_question.py`:

```python
def test_free_text_shows_interpretation_and_waits(github, issue, monkeypatch):
    """Свободный текст — толкование предъявлено, решение НЕ записано (A15)."""
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
                        lambda question, journal, answer:
                            a.answer_interpretation.Interpretation(
                                answer="405 на любой метод кроме POST"))

    assert a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101) == "confirm"
    assert "405 на любой метод кроме POST" in github["comments"][0]
    assert questions.read_journal(github["body"]) == []


def test_confirmation_records_answer_and_amendments(github, issue, monkeypatch):
    """Второй ответ применяет и решение, и правки прежних записей (A20, A21)."""
    github["body"] = questions.append_decision(github["body"], questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="Чем принимать?",
        answer="старое решение"))
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="mvp-bounds-1", kind="mvp-bounds", text="Что в MVP?", options=()))
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)

    monkeypatch.setattr(a, "_interpret_answer",
                        lambda question, journal, answer:
                            a.answer_interpretation.Interpretation(
                                answer="только /quote",
                                amendments=[a.answer_interpretation.Amendment(
                                    question_id="howtodemo-1", answer="наоборот")]))

    assert a.answer_question(issue, "mvp-bounds-1", "только /quote, а то — наоборот", 101) == "confirm"
    assert a.answer_question(issue, "mvp-bounds-1", "да", 102) == "accepted"

    journal = questions.read_journal(github["body"])
    assert len(journal) == 3, "старая запись осталась, добавились две новые"
    live = {d.question_id: d.answer for d in questions.effective(journal)}
    assert live["mvp-bounds-1"] == "только /quote"
    assert "наоборот" in " ".join(live.values())
    assert "старое решение" in " ".join(d.answer for d in journal), \
        "отменённая запись видна в журнале"


def test_model_failure_keeps_the_question_open(github, issue, monkeypatch):
    """Модель отказала — вопрос стоит, человек получает честный текст."""
    _open(github)

    def boom(question, journal, answer):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(a, "_interpret_answer", boom)

    assert a.answer_question(issue, "howtodemo-1", "какой-то текст", 101) == "confirm"
    assert "не смог" in github["comments"][0].lower()
    assert questions.read_open(github["body"]) is not None
```

- [ ] **Step 6: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_answer_question.py -q -p no:randomly --no-cov -k "free_text or confirmation or model_failure"`
Expected: FAIL — `_interpret_answer` не существует, подтверждение не реализовано.

- [ ] **Step 7: Черновик толкования в теле**

В `shared/issue_blocks.py` добавить блок и внести его в реестр:

```python
# Толкование свободного ответа, ожидающее подтверждения человеком.
DRAFT = "answer-draft"
```

```python
_ALL_BLOCKS = (MVP_PLAN, GROW, HOWTODEMO, QUESTION, ANSWERS, DRAFT)
```

и в `shared/questions.py`:

```python
def read_draft(body: str | None) -> dict | None:
    """Толкование, ожидающее подтверждения. Нет или испорчено — None."""
    try:
        payload = _unwrap(issue_blocks.read(body, issue_blocks.DRAFT))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def write_draft(body: str | None, payload: dict) -> str:
    return issue_blocks.write(body, issue_blocks.DRAFT,
                              _wrap(payload, "## Ожидает подтверждения"))


def clear_draft(body: str | None) -> str:
    return issue_blocks.strip(body, issue_blocks.DRAFT)
```

Дописать в `tests/test_questions.py`:

```python
def test_draft_roundtrip_and_clear():
    payload = {"answer": "405 везде кроме POST", "amendments": []}
    body = questions.write_draft("описание", payload)
    assert questions.read_draft(body) == payload
    assert questions.read_draft(questions.clear_draft(body)) is None
```

- [ ] **Step 8: Подключить толкование**

В `worker/activities.py` заменить `_confirm_free_text` и дописать подтверждение:

```python
# Маркер комментария «вот что я записал». По нему активность отличает второй
# ответ (подтверждение) от первого, а толкование восстанавливается из ЖУРНАЛА
# ЧЕРНОВИКОВ, а не разрезанием прозы комментария: правка формулировки вокруг
# ломала бы восстановление молча.
ACCEPTANCE_ECHO_MARKER = "<!-- harness:answer-echo -->"


def _interpret_answer(question, journal, answer):
    """Толкование свободного ответа моделью. Бросает — значит не вышло."""
    interpretation = llm.extract(
        answer_interpretation.SYSTEM_PROMPT,
        answer_interpretation.build_user_message(question, journal, answer),
        answer_interpretation.Interpretation,
        model=llm.MODEL_GATE,
    )
    answer_interpretation.validate(interpretation, journal)
    return interpretation


def _confirm_free_text(issue, body: str, question, answer: str) -> str:
    journal = questions.read_journal(body)

    pending = questions.read_draft(body)
    if pending is not None:
        # Второй ответ при висящем черновике — подтверждение.
        _apply_interpretation(issue, body, question, pending)
        return "accepted"

    try:
        interpretation = _interpret_answer(question, journal, answer)
    except Exception as err:
        activity.logger.warning("толкование ответа не вышло: %s", err)
        github_client.post_comment(issue.repo, issue.issue_number, agent_comment.sign(
            "Разобрать ответ не смог — попробуйте сформулировать иначе:\n\n"
            "```\n/harness-answer здесь ваш ответ\n```"))
        return "confirm"

    github_client.update_issue_body(
        issue.repo, issue.issue_number,
        questions.write_draft(body, interpretation.model_dump()))
    github_client.post_comment(issue.repo, issue.issue_number, agent_comment.sign(
        answer_interpretation.render_interpretation(interpretation, journal)
        + "\n\nЕсли верно — подтвердите:\n\n```\n/harness-answer да\n```\n\n"
          "Если нет — пришлите поправленный текст той же командой.\n\n"
        + ACCEPTANCE_ECHO_MARKER))
    return "confirm"


def _apply_interpretation(issue, body: str, question, payload: dict) -> None:
    """Записать подтверждённое толкование: решение и все правки."""
    interpretation = answer_interpretation.Interpretation(**payload)
    body = questions.clear_draft(body)
    body = questions.append_decision(body, questions.Decision(
        question_id=question.id, kind=question.kind, question=question.text,
        answer=interpretation.answer))
    journal = questions.read_journal(body)
    for amendment in interpretation.amendments:
        previous = next((d for d in journal
                         if d.question_id == amendment.question_id), None)
        if previous is None:
            continue
        body = questions.append_decision(body, questions.Decision(
            question_id=questions.next_question_id(questions.read_journal(body),
                                                   previous.kind),
            kind=previous.kind, question=previous.question,
            answer=amendment.answer, supersedes=amendment.question_id))
    github_client.update_issue_body(issue.repo, issue.issue_number,
                                    questions.clear_open(body))
    github_client.remove_label(issue.repo, issue.issue_number,
                               labels.NEEDS_HUMAN_ANSWER)
```

- [ ] **Step 9: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_answer_question.py tests/test_questions.py tests/test_answer_interpretation.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 10: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 11: Коммит**

```bash
git add shared/answer_interpretation.py shared/questions.py shared/issue_blocks.py worker/activities.py tests/
git commit -m "feat(questions): толкование свободного ответа с журналом и подтверждением"
```

---

### Task 7: Команда доезжает до цикла

Закрывает A4, A5, A6 со стороны вебхука.

**Files:**
- Modify: `webhook/main.py`
- Test: `tests/test_webhook_harness_answer.py`

**Interfaces:**
- Consumes: `commands.HARNESS_ANSWER` из Task 3
- Produces: `/harness-answer` уезжает сигналом `user_comment` с полным телом комментария и `comment_id`

- [ ] **Step 1: Написать падающие тесты**

```python
def test_harness_answer_reaches_the_lifecycle(monkeypatch, client):
    """Ответ доезжает до цикла сигналом user_comment.

    Прочие команды в user_comment не уходят — их съел бы цикл уточнений. Эта
    уходит намеренно: её адресат и есть цикл, который задал вопрос.
    """
    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client", _fake_client_returning(_Handle()))

    response = client.post("/webhook", json=_comment_payload("/harness-answer 1"),
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled and signalled[0][0] == "user_comment"
    assert "/harness-answer 1" in signalled[0][1][0]


def test_agent_own_comment_is_not_an_answer(monkeypatch, client):
    """Комментарий контура ответом не считается (A4).

    Под PAT комментарии сервиса возвращаются с `type == "User"`, и без
    проверки подписи контур отвечал бы сам себе.
    """
    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client", _fake_client_returning(_Handle()))

    payload = _comment_payload("/harness-answer 1\n\n<!-- issue-agent -->")
    response = client.post("/webhook", json=payload,
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled == [], "контур принял собственный комментарий за ответ"
```

Вспомогательные `_fake_client_returning` и `_comment_payload` скопировать из существующего теста вебхука (`tests/test_webhook_subissue_ignored.py`) — фикстура из чужого модуля не видна.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_webhook_harness_answer.py -q -p no:randomly --no-cov`
Expected: FAIL — сигнала нет либо он не тот.

- [ ] **Step 3: Провести команду до сигнала**

В `webhook/main.py`, среди разбора команд `issue_comment`, ПЕРЕД ветками дорогих стадий:

```python
        if command == HARNESS_ANSWER:
            # Единственная команда, которая идёт в `user_comment`: её адресат —
            # цикл, задавший вопрос, а не отдельный workflow. Дорогую стадию
            # она не запускает, поэтому прав по AGENT_TRIGGER_ALLOWLIST здесь
            # не спрашиваем — так решено спекой A8.
            wf_id = workflow_id_for(repo, issue_number)
            handle = client.get_workflow_handle(wf_id)
            try:
                await handle.signal("user_comment",
                                    args=[payload["comment"]["body"],
                                          payload["comment"]["id"]])
            except Exception:
                # Цикла нет — отвечать некому. Поднимать его ответом на
                # незаданный вопрос смысла нет.
                logger.info("ответ без живого цикла: %s#%s", repo, issue_number)
            return {"ok": True}
```

`HARNESS_ANSWER` добавить к импорту имён команд в шапке модуля.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_webhook_harness_answer.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add webhook/main.py tests/test_webhook_harness_answer.py
git commit -m "feat(webhook): /harness-answer доезжает до цикла сигналом"
```

---

### Task 8: Указатель в прогоне и гейт критерия приёмки

Закрывает A6, A9 со стороны прогона, A23, A26, A27 и подключает механизм к первому потребителю. **Правка решения воркфлоу — обязателен `workflow.patched`.**

**Files:**
- Create: `shared/acceptance_proposal.py`
- Modify: `worker/workflows.py`
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Test: `tests/test_acceptance_proposal.py`, `tests/test_workflow_acceptance_gate.py`

**Interfaces:**
- Consumes: `ask_question`, `answer_question` из Task 4 и 5; `commands.HARNESS_ANSWER`, `parse_command`, `parse_command_args`
- Produces:
  - `shared/acceptance_proposal.py`: `AcceptanceOption(before: str, after: str)`, `AcceptanceOptions(options: list[AcceptanceOption])` (от одного до трёх), `render_option(option) -> str`, `SYSTEM_PROMPT`
  - активность `propose_acceptance_options(issue) -> list[str]`
  - активность `read_acceptance_criterion(issue) -> str`
  - поле цикла `self._open_question: str` — идентификатор открытого вопроса, пусто = вопроса нет

- [ ] **Step 1: Написать падающие тесты вариантов**

`tests/test_acceptance_proposal.py`:

```python
import pytest

from shared import acceptance_proposal as ap


def test_render_option_is_before_and_after():
    option = ap.AcceptanceOption(
        before='GET /quote отвечает 404 {"error":"не найдено"}',
        after="GET /quote отвечает 405 с заголовком Allow: POST")
    rendered = ap.render_option(option)
    assert "было" in rendered.lower() and "стало" in rendered.lower()
    assert "404" in rendered and "405" in rendered


def test_empty_option_list_is_a_refusal():
    """Вопрос без вариантов бесполезен человеку — это отказ модели."""
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=[])


def test_more_than_three_options_is_rejected():
    """Больше трёх человек не читает, он их пролистывает."""
    many = [ap.AcceptanceOption(before=f"было {i}", after=f"стало {i}")
            for i in range(5)]
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=many)


def test_prompt_demands_observable_signs():
    assert "наблюдаем" in ap.SYSTEM_PROMPT.lower()
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_acceptance_proposal.py -q -p no:randomly --no-cov`
Expected: FAIL с `ModuleNotFoundError`

- [ ] **Step 3: Написать модуль вариантов**

```python
"""Варианты критерия приёмки, предлагаемые человеку.

Форма варианта — «было / стало» наблюдаемыми признаками. Пересказ задачи
критерием не является: по нему нельзя вынести вердикт.
"""
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
```

- [ ] **Step 4: Активности вариантов и чтения критерия**

В `worker/activities.py`:

```python
@activity.defn
def propose_acceptance_options(issue) -> list[str]:
    """Варианты критерия приёмки от модели. Отказала — пустой список.

    Пустой список НЕ пропускает задачу дальше: вопрос всё равно задаётся,
    просто без вариантов, свободным текстом.
    """
    try:
        options = llm.extract(
            acceptance_proposal.SYSTEM_PROMPT,
            f"# {issue.title}\n\n{issue.body or ''}",
            acceptance_proposal.AcceptanceOptions,
            model=llm.MODEL_GATE,
        )
    except Exception as err:
        activity.logger.warning("варианты критерия не построились: %s", err)
        return []
    return [acceptance_proposal.render_option(option) for option in options.options]


@activity.defn
def read_acceptance_criterion(issue) -> str:
    """Критерий приёмки: утверждённый блок либо раздел в теле Issue.

    Отдельная активность, а не чтение в воркфлоу: тело Issue живёт снаружи, и
    ходить за ним из воркфлоу нельзя — реплей обязан быть детерминированным.
    """
    body = github_client.get_issue_body(issue.repo, issue.issue_number)
    return _howtodemo_block(body)
```

Обе зарегистрировать в `worker/worker.py`.

- [ ] **Step 5: Решение о критерии попадает в блок HOWTODEMO**

В `worker/activities.py`, в `_record_decision` и `_apply_interpretation`, после записи в журнал добавить назначение по виду вопроса:

```python
# Помимо журнала, решение уходит туда, где его ждёт механизм, задавший вопрос
# (A28). Журнал общий; назначение объявляет вид вопроса. Без этого правила
# журнал стал бы вторым источником правды о критерии.
_DECISION_DESTINATION = {"howtodemo": issue_blocks.HOWTODEMO}


def _place_decision(body: str, kind: str, answer: str) -> str:
    block = _DECISION_DESTINATION.get(kind)
    return issue_blocks.write(body, block, answer) if block else body
```

и звать `_place_decision` внутри обеих функций перед записью тела.

Тест в `tests/test_answer_question.py`:

```python
def test_acceptance_decision_lands_in_the_howtodemo_block(github, issue):
    """Решение по критерию приёмки читает подготовка задачи — из блока (A28)."""
    _open(github)
    a.answer_question(issue, "howtodemo-1", "1", 101)

    from shared import issue_blocks
    assert issue_blocks.read(github["body"], issue_blocks.HOWTODEMO) == \
        "было 404; стало 405"
```

- [ ] **Step 6: Написать падающие тесты гейта**

`tests/test_workflow_acceptance_gate.py`. Заглушки активностей цикла (`awaiting_stub`, `prefilter_ok`, `protocol_default`, `read_deadlines` и прочие) скопировать ВЕРБАТИМ из `tests/test_agent_event_workflow.py` — фикстуры чужого модуля не видны.

```python
"""Гейт критерия приёмки: без критерия разработка не начинается.

Отказ, ради которого написано: poh-demo-checkout#163 прошёл разработку, PR и
мерж, а приёмка всё это время отвечала «проверять нечем».
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import IssueInput
from workflows import IssueDevelopment, IssueLifecycle

# --- сюда скопировать блок заглушек из tests/test_agent_event_workflow.py ---

_calls: list[str] = []


@activity.defn(name="read_acceptance_criterion")
async def criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="read_acceptance_criterion")
async def criterion_present(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="propose_acceptance_options")
async def options_stub(issue: IssueInput) -> list[str]:
    _calls.append("propose")
    return ["было 404; стало 405"]


@activity.defn(name="ask_question")
async def ask_stub(issue: IssueInput, kind: str, text: str,
                   options: list[str]) -> str:
    _calls.append("ask")
    return "howtodemo-1"


@activity.defn(name="answer_question")
async def answer_accepted(issue: IssueInput, question_id: str, text: str,
                          comment_id: int | None) -> str:
    _calls.append("answer")
    return "accepted"


@activity.defn(name="dev_begin")
async def dev_forbidden(issue: IssueInput):
    _calls.append("development")
    raise AssertionError("разработка началась без критерия приёмки")


@activity.defn(name="dev_begin")
async def dev_started(issue: IssueInput):
    _calls.append("development")
    raise RuntimeError("дальше разработка не нужна — факт старта записан")


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=163, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.mark.asyncio
async def test_development_does_not_start_without_criterion():
    """Без критерия разработка не начинается, вопрос задан."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, options_stub, ask_stub,
                                      answer_accepted, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "ask" in _calls
    assert "development" not in _calls


@pytest.mark.asyncio
async def test_development_starts_when_criterion_is_present():
    """Критерий есть — гейт пропускает молча, вопроса нет (A23)."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_present, options_stub, ask_stub,
                                      answer_accepted, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "development" in _calls
    assert "ask" not in _calls


@pytest.mark.asyncio
async def test_answer_unblocks_development():
    """Ответ принят — разработка начинается тем же прогоном."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, options_stub, ask_stub,
                                      answer_accepted, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("ask") == 1
    assert "answer" in _calls
    assert "development" in _calls


@pytest.mark.asyncio
async def test_the_same_comment_delivered_twice_answers_once():
    """Вебхук доставляет каждое событие дважды (A6).

    Без защиты второй экземпляр приняли бы уже при закрытом вопросе — то есть
    ответили бы «вопросов нет» на собственный только что принятый ответ.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, options_stub, ask_stub,
                                      answer_accepted, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("answer") == 1


@pytest.mark.asyncio
async def test_second_answer_from_another_person_finds_no_question():
    """Два ответа подряд: первый принят, второму отвечать не на что (A27).

    Порядок задаётся очередью сигналов прогона и детерминирован.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, options_stub, ask_stub,
                                      answer_accepted, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("user_comment", args=["/harness-answer 2", 202])
            await handle.signal("issue_closed", "тест")
            await handle.result()

    # Первый ответ снял указатель; второй в ветку ответа уже не попадает.
    assert _calls.count("answer") == 1


@pytest.mark.asyncio
async def test_comment_without_command_does_not_answer():
    """Разговор ответом не считается (A5)."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, options_stub, ask_stub,
                                      answer_accepted, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["а нам это вообще надо?", 102])
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "answer" not in _calls
    assert "development" not in _calls
```

- [ ] **Step 7: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_workflow_acceptance_gate.py -q -p no:randomly --no-cov`
Expected: FAIL — разработка стартует без критерия.

- [ ] **Step 8: Поставить гейт и указатель**

В `worker/workflows.py`, в `__init__` цикла рядом с прочим состоянием:

```python
        # Идентификатор открытого вопроса к человеку. Пусто — вопроса нет.
        # Прогон хранит ТОЛЬКО указатель: содержание вопроса живёт в теле
        # Issue. Копия здесь разошлась бы с телом при первой правке руками.
        self._open_question = ""
```

В начало `_start_development`:

```python
        # Гейт критерия приёмки. Маркер обязателен: у припаркованных прогонов
        # решение «начать разработку» УЖЕ лежит в истории, и новый код
        # запланировал бы на его месте активность, которой там нет, — реплей
        # упал бы недетерминизмом. Так легли 29 прогонов после ac625e7.
        if workflow.patched("issue-lifecycle-acceptance-gate"):
            criterion = await workflow.execute_activity(
                activities.read_acceptance_criterion, issue,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if not criterion:
                options = await workflow.execute_activity(
                    activities.propose_acceptance_options, issue,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                self._open_question = await workflow.execute_activity(
                    activities.ask_question,
                    args=[issue, "howtodemo",
                          "**Не вижу, чем принимать эту задачу.** "
                          "Разработку не начинаю, пока не будет критерия готовности.",
                          options],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                return (lifecycle.READY_FOR_DEV, "awaiting-acceptance-criterion", False)
```

В `_phase_await_build`, в ветке разбора `UserComment`, ПЕРЕД вызовом `_answer_followup`:

```python
            if self._open_question and workflow.patched(
                    "issue-lifecycle-question-answer"):
                if commands.parse_command(decision.text) == commands.HARNESS_ANSWER:
                    verdict = await workflow.execute_activity(
                        activities.answer_question,
                        args=[issue, self._open_question,
                              commands.parse_command_args(decision.text),
                              decision.comment_id],
                        start_to_close_timeout=timedelta(minutes=3),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    if verdict == "accepted":
                        self._open_question = ""
                        return await self._start_development(issue)
                    return (self._phase, self._stage, False)
```

Перед вызовом активности — защита от повторной доставки. Вебхук доставляет
каждое событие ДВАЖДЫ (в истории прогона по `poh-demo-checkout#42` сигналов
ровно вдвое), и без неё один ответ человека принимался бы дважды: второй раз
уже при закрытом вопросе, то есть комментарием «вопросов нет» на собственный
принятый ответ.

Цикл уже ведёт `self._answered_comment_ids` для реплик — переиспользуй его,
второго реестра не заводи:

```python
            if self._open_question and workflow.patched(
                    "issue-lifecycle-question-answer"):
                if commands.parse_command(decision.text) == commands.HARNESS_ANSWER:
                    if (decision.comment_id is not None
                            and decision.comment_id in self._answered_comment_ids):
                        return (self._phase, self._stage, False)
                    if decision.comment_id is not None:
                        self._answered_comment_ids.add(decision.comment_id)
                    verdict = await workflow.execute_activity(
```

то есть две проверки встают ПЕРЕД `execute_activity`, остальное тело ветки не
меняется.

`commands` импортировать в `worker/workflows.py` среди прочих `shared`, если его там ещё нет.

- [ ] **Step 9: Прогнать тесты гейта**

Run: `python -m pytest tests/test_workflow_acceptance_gate.py tests/test_answer_question.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 10: Прогнать гвард реплея — главная проверка задачи**

Run: `python -m pytest tests/test_workflow_replay.py -q -p no:randomly --no-cov`
Expected: PASS. Красный гвард означает, что маркер поставлен не там или не поставлен вовсе, и выкладка убьёт припаркованные прогоны. Чинить, а не обходить.

- [ ] **Step 11: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 12: Коммит**

```bash
git add shared/acceptance_proposal.py worker/workflows.py worker/activities.py worker/worker.py tests/
git commit -m "feat(gate): разработка не начинается без критерия приёмки

Маркер issue-lifecycle-acceptance-gate обязателен: решение «начать
разработку» уже лежит в историях припаркованных прогонов."
```

---

### Task 9: Сквозной путь

**Files:**
- Test: `tests/test_harness_answer_e2e.py`

**Interfaces:**
- Consumes: всё предыдущее
- Produces: ничего

- [ ] **Step 1: Написать сквозной тест**

Идёт по активностям, а не по воркфлоу: цикл проверен в Task 8, здесь важно, что решение доезжает до потребителя и накапливается в задаче.

```python
"""Сквозной путь: вопрос, ответ, журнал, критерий у исполнителя.

Отказ, ради которого написано: poh-demo-checkout#163 прошёл разработку целиком,
а критерий приёмки так и не доехал — сценарий в теле был, но контур его не
увидел и никого не спросил.
"""

import pytest

import activities as a
from shared import issue_blocks, labels, questions, task_context
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=163,
                      title="GET /quote отдаёт 404 вместо 405",
                      body="Сейчас 404 про файл, ожидается 405 с Allow: POST",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    state = {"body": issue.body, "comments": [], "labels": set(), "reactions": []}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(body))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    monkeypatch.setattr(a.github_client, "add_reaction",
                        lambda repo, comment_id, content:
                            state["reactions"].append(content))
    return state


def test_full_path_question_answer_journal_criterion(github, issue, tmp_path):
    """Пять фактов одним прогоном:

    1. до ответа критерия нет — гейт задачу не пропустил бы;
    2. вопрос задан, назвал команду, повесил метку;
    3. пустая команда получила реакции и вопрос не закрыла;
    4. ответ номером записал решение в журнал И в блок критерия;
    5. критерий пригоден для записи в `.harness/howtodemo.md`.
    """
    assert a.read_acceptance_criterion(issue) == ""

    question_id = a.ask_question(
        issue, "howtodemo",
        "Не вижу, чем принимать эту задачу.",
        ["было — 404 про файл; стало — 405 с Allow: POST",
         "было — 404 про файл; стало — 405 на любой метод кроме POST"])

    assert question_id == "howtodemo-1"
    assert "/harness-answer" in github["comments"][0]
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]

    assert a.answer_question(issue, question_id, "", 101) == "empty"
    assert set(github["reactions"]) == {"confused", "-1"}
    assert questions.read_open(github["body"]) is not None

    assert a.answer_question(issue, question_id, "1", 102) == "accepted"

    journal = questions.read_journal(github["body"])
    assert [d.question_id for d in journal] == ["howtodemo-1"]
    assert "405 с Allow: POST" in journal[0].answer
    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    criterion = a.read_acceptance_criterion(issue)
    assert "405 с Allow: POST" in criterion
    assert issue_blocks.read(github["body"], issue_blocks.HOWTODEMO) == criterion

    harness = tmp_path / task_context.DIR
    harness.mkdir()
    (harness / task_context.HOWTODEMO).write_text(criterion, encoding="utf-8")
    assert "405 с Allow: POST" in (harness / task_context.HOWTODEMO).read_text()


def test_second_question_after_the_first_is_closed(github, issue):
    """Один открытый вопрос за раз; нумерация продолжается (A9, A11)."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["вариант"])
    a.answer_question(issue, "howtodemo-1", "1", 101)

    second = a.ask_question(issue, "mvp-bounds", "Что входит в MVP?", ["только /quote"])
    assert second == "mvp-bounds-1"
    assert questions.read_open(github["body"]).id == "mvp-bounds-1"
    assert len(questions.read_journal(github["body"])) == 1
```

- [ ] **Step 2: Прогнать**

Run: `python -m pytest tests/test_harness_answer_e2e.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 3: Прогнать весь набор и гвард реплея**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 4: Коммит**

```bash
git add tests/test_harness_answer_e2e.py
git commit -m "test(questions): сквозной путь — вопрос, ответ, журнал, критерий"
```

---

## Что остаётся человеку после плана

- **Документация.** `docs/HOWTODEMO.md` описывает поиск сценария по четырём английским формам и не знает ни про русские, ни про блок, ни про входной гейт, ни про команду. Правится одним проходом по факту сделанного.
- **Живой прогон.** План закрывается модульными проверками и гвардом реплея; работает ли механизм на стенде, покажет только живая задача.
- **Отменённые задачи прежнего плана.** Задачи 6 и 7 из `2026-08-28-howtodemo-intake-gate.md` заменены этим планом целиком: они хранили вопрос в комментариях по маркеру. Исполнять их нельзя.
- **Дублирующая ветка в вебхуке.** В `webhook/main.py` разбор `if command == RESEARCH` встречается дважды, вторая недостижима. К задаче отношения не имеет — вынести отдельно.
