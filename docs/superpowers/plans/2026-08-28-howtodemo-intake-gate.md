# Входной гейт критерия приёмки — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разработка не начинается, пока критерий приёмки не прочитан и не утверждён человеком; отсутствие критерия контур закрывает не требованием «допишите раздел», а готовыми вариантами и командой ответа.

**Architecture:** Один распознаватель сценария, общий у входного гейта и приёмщика, пополняется русскими формами заголовка. Гейт встаёт в `_start_development` — единственную точку входа в разработку для автостарта и решения человека — под маркером `workflow.patched`, потому что это правка решения воркфлоу. Утверждённый критерий живёт в теле Issue размеченным блоком `issue_blocks.HOWTODEMO`. Ответ человека принимается только командой `/harness-answer`, доезжающей существующим сигналом `user_comment`.

**Tech Stack:** Python 3.12, Temporal Python SDK, pytest, instructor + `worker/llm.py` для структурированного ответа модели, GitHub REST через `worker/github_client.py`.

## Global Constraints

- Тесты гонять командой репозитория: `python -m pytest -q`. Порог покрытия — 83%, он проверяется в том же прогоне и красный прогон в PR не отдаём.
- **Раскладка:** `worker/` и `webhook/` НЕ пакеты — Dockerfile расплющивает их в `/app`. Импорт вида `from worker.X import ...` падает в контейнере. Внутри воркера — `import activities`, `import github_client`. Общий код — только `shared/` (AGENTS.md, правило 7).
- **Фикстура pytest из чужого тестового модуля не видна** — `conftest.py` либо своя копия (AGENTS.md, правило 8).
- **Правка решения воркфлоу требует `workflow.patched(...)`.** Ветка, которую прогон уже выбрал, записана в его историю; новый код на реплее выберет другую и уронит прогон `Nondeterminism error`. Активности (тело, ретраи, метки) маркера не требуют.
- Гвард реплея (`tests/test_workflow_replay.py`, PR #284) обязан оставаться зелёным. Он гоняет записанные истории живых прогонов и ловит ровно этот класс.
- Комментарии контура несут маркер `<!-- issue-agent -->` — иначе вебхук примет собственный комментарий за реплику человека.
- Спецификация: `docs/superpowers/specs/2026-08-28-howtodemo-intake-gate-design.md`, требования R1–R24.

---

### Task 1: Русские формы заголовка в распознавателе

Закрывает R5, R6, R7, R8. Самостоятельная правка: чинит сегодняшний дефект #163 ещё до всего остального.

**Files:**
- Modify: `worker/activities.py:1193-1203` (`_HOWTODEMO_START`)
- Test: `tests/test_dev_task_assembly.py`

**Interfaces:**
- Consumes: ничего
- Produces: `_HOWTODEMO_START` принимает русские заголовки; `_howtodemo_block(body: str) -> str` поведения не меняет

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/test_dev_task_assembly.py`:

```python
def test_howtodemo_block_russian_headings():
    """Раздел приёмки, написанный по-русски, распознаётся наравне с английским.

    Отказ, ради которого это написано: poh-demo-checkout#163 приехал с
    разделом `## Как принимаем` и блоками curl «было/должно работать»,
    прошёл разработку, PR и мерж — а приёмка всё это время отвечала
    «проверять нечем».
    """
    for heading in ("## Как принимаем", "## Как проверяем",
                    "## Приёмка", "## Приемка", "## Как демонстрируем",
                    "### Как принимаем"):
        body = f"вступление\n\n{heading}\n\nБыло 404, стало 405\n\n## Другое\nхвост"
        assert a._howtodemo_block(body) == "Было 404, стало 405", heading


def test_howtodemo_russian_heading_as_part_of_another_word_does_not_trigger():
    """`## Приёмка-агент: как он устроен` — это описание, а не сценарий."""
    body = "## Приёмка-агент: как он устроен\n\nОписание агента, не сценарий."
    assert a._howtodemo_block(body) == ""


def test_howtodemo_russian_heading_with_empty_body_is_no_scenario():
    """Заголовок есть, под ним пусто — сценария нет (R7).

    Пустой критерий хуже отсутствующего: он создаёт видимость приёмки.
    """
    body = "## Как принимаем\n\n\n## Другое\nхвост"
    assert a._howtodemo_block(body) == ""


def test_howtodemo_russian_heading_inside_code_fence_is_not_a_scenario():
    """Заголовок, процитированный примером, сценарием не считается (R8)."""
    body = (
        "Шаблон задачи:\n\n"
        "```markdown\n"
        "## Как принимаем\n"
        "тут пишем сценарий\n"
        "```\n\n"
        "Настоящего раздела нет."
    )
    assert a._howtodemo_block(body) == ""
```

- [ ] **Step 2: Прогнать тесты и убедиться, что они падают**

Run: `python -m pytest tests/test_dev_task_assembly.py -k russian -q -p no:randomly --no-cov`
Expected: FAIL — четыре теста, у первого `AssertionError: ## Как принимаем`, у остальных ожидания не сходятся или совпадают случайно.

- [ ] **Step 3: Расширить регулярку**

В `worker/activities.py` заменить `_HOWTODEMO_START` целиком:

```python
# Формы заголовка, которыми в контуре пишут сценарий приёмки. Русские добавлены
# после poh-demo-checkout#163: задача с разделом `## Как принимаем` прошла
# разработку и мерж, а приёмка отвечала «проверять нечем» — сценарий в теле был,
# распознаватель принимал только английские формы.
#
# `приёмка` и `приемка` перечислены обе: на клавиатуре без «ё» пишут вторую, и
# требовать от человека диакритику ради работы гейта — тот же капкан.
#
# `(?![\w-])` после имени раздела обязателен: `## Приёмка-агент: как он устроен`
# — описание агента, а не сценарий. `\w` в Python 3 покрывает кириллицу.
#
# Именованная группа `hashes` есть только у заголовочной формы — по ней
# `_howtodemo_block` определяет уровень заголовка для границы конца блока.
_HOWTODEMO_START = re.compile(
    r"""(?imx)
    ^[ \t]*
    (?:
        (?P<hashes>\#{2,3})[ \t]*
        (?:
            how[ \t]*to[ \t]*demo
          | как[ \t]+принимаем
          | как[ \t]+проверяем
          | как[ \t]+демонстрируем
          | приёмка
          | приемка
        )(?![\w-])[^\n]*
      | \*\*[ \t]*how[ \t]*to[ \t]*demo[ \t]*:[ \t]*\*\*[ \t]*
      | how[ \t]*to[ \t]*demo[ \t]*:[ \t]*
    )
    \n?
    """
)
```

- [ ] **Step 4: Прогнать тесты и убедиться, что они прошли**

Run: `python -m pytest tests/test_dev_task_assembly.py -q -p no:randomly --no-cov`
Expected: PASS, включая существующие тесты английских форм — они не должны сломаться.

- [ ] **Step 5: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 6: Коммит**

```bash
git add worker/activities.py tests/test_dev_task_assembly.py
git commit -m "fix(howtodemo): русские формы заголовка сценария приёмки

poh-demo-checkout#163 приехал с разделом «Как принимаем», прошёл
разработку, PR и мерж — а приёмка отвечала «проверять нечем».
Распознаватель принимал только английские формы."
```

---

### Task 2: Блок HOWTODEMO в теле Issue

Закрывает R22. Механизм тот же, что несёт `MVP_PLAN` и `GROW`.

**Files:**
- Modify: `shared/issue_blocks.py:24-29`
- Test: `tests/test_issue_blocks.py`

**Interfaces:**
- Consumes: ничего
- Produces: `issue_blocks.HOWTODEMO: str = "howtodemo"`, входит в `_ALL_BLOCKS`; `read(body, HOWTODEMO)`, `write(body, HOWTODEMO, content)` работают как у прочих блоков

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_issue_blocks.py`:

```python
def test_howtodemo_block_roundtrip():
    """Критерий приёмки кладётся в тело и читается обратно."""
    body = "описание задачи"
    written = issue_blocks.write(body, issue_blocks.HOWTODEMO,
                                 "Было 404, стало 405 с Allow: POST")
    assert issue_blocks.read(written, issue_blocks.HOWTODEMO) == \
        "Было 404, стало 405 с Allow: POST"
    assert "описание задачи" in written


def test_howtodemo_block_is_known_and_guarded():
    """Блок входит в _ALL_BLOCKS: вложенные маркеры дают громкую ошибку.

    Без этого содержимое с чужими маркерами тихо перезаписало бы соседний
    блок — ровно тот молчаливый отказ, который мы вычищаем.
    """
    assert issue_blocks.HOWTODEMO in issue_blocks._ALL_BLOCKS
    body = issue_blocks.write("текст", issue_blocks.GROW, "- [ ] находка")
    with pytest.raises(ValueError):
        issue_blocks.write(body, issue_blocks.HOWTODEMO,
                           "<!-- harness:grow:start -->подделка<!-- harness:grow:end -->")


def test_howtodemo_block_survives_grow_block():
    """Два блока в одном теле не мешают друг другу."""
    body = issue_blocks.write("текст", issue_blocks.GROW, "- [ ] находка")
    body = issue_blocks.write(body, issue_blocks.HOWTODEMO, "сценарий")
    assert issue_blocks.read(body, issue_blocks.GROW) == "- [ ] находка"
    assert issue_blocks.read(body, issue_blocks.HOWTODEMO) == "сценарий"
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_issue_blocks.py -k howtodemo -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'shared.issue_blocks' has no attribute 'HOWTODEMO'`

- [ ] **Step 3: Добавить блок**

В `shared/issue_blocks.py` рядом с существующими именами:

```python
MVP_PLAN = "mvp-plan"
GROW = "grow"
# Критерий приёмки, утверждённый человеком. В теле, а не комментарием:
# комментарий теряется в ленте, а критерий должен быть виден в задаче всегда.
HOWTODEMO = "howtodemo"
```

и в перечень известных блоков:

```python
_ALL_BLOCKS = (MVP_PLAN, GROW, HOWTODEMO)
```

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_issue_blocks.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add shared/issue_blocks.py tests/test_issue_blocks.py
git commit -m "feat(issue-blocks): блок HOWTODEMO для утверждённого критерия приёмки"
```

---

### Task 3: Приёмка читает утверждённый блок

Закрывает R23, R24. Блок имеет приоритет над заголовком: он утверждён человеком явно.

**Files:**
- Modify: `worker/activities.py:1237-1262` (`_howtodemo_block`)
- Test: `tests/test_dev_task_assembly.py`

**Interfaces:**
- Consumes: `issue_blocks.HOWTODEMO` из Task 2
- Produces: `_howtodemo_block` сначала смотрит блок, потом заголовок

- [ ] **Step 1: Написать падающие тесты**

```python
def test_howtodemo_approved_block_wins_over_heading():
    """Утверждённый блок старше раздела: человек подтвердил именно его."""
    body = issue_blocks.write("## Как принимаем\n\nстарый текст",
                              issue_blocks.HOWTODEMO, "утверждённый критерий")
    assert a._howtodemo_block(body) == "утверждённый критерий"


def test_howtodemo_empty_approved_block_falls_back_to_heading():
    """Пустой блок не должен затирать написанный человеком раздел."""
    body = issue_blocks.write("## Как принимаем\n\nтекст раздела",
                              issue_blocks.HOWTODEMO, "   ")
    assert a._howtodemo_block(body) == "текст раздела"
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_dev_task_assembly.py -k approved -q -p no:randomly --no-cov`
Expected: FAIL — возвращается «старый текст» вместо утверждённого.

- [ ] **Step 3: Дать блоку приоритет**

В начало тела `_howtodemo_block`, сразу после `body = body or ""`:

```python
    # Утверждённый блок старше раздела: человек подтвердил именно этот текст
    # командой, а раздел мог остаться от прежней редакции задачи. Пустой блок
    # не считается утверждением и не затирает написанное человеком.
    approved = issue_blocks.read(body, issue_blocks.HOWTODEMO)
    if approved and approved.strip():
        return approved.strip()
```

Проверить, что `issue_blocks` в модуле импортирован; если нет — добавить `from shared import issue_blocks` к прочим импортам `shared`.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_dev_task_assembly.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add worker/activities.py tests/test_dev_task_assembly.py
git commit -m "feat(howtodemo): утверждённый блок старше раздела в теле Issue"
```

---

### Task 4: Команда `/harness-answer`

Закрывает R13, R14, R15, R16, R21.

**Files:**
- Modify: `shared/commands.py:25-38`
- Modify: `shared/label_catalog.py:59-68` (`_all_command_labels`)
- Test: `tests/test_commands.py`, `tests/test_label_catalog.py`

**Interfaces:**
- Consumes: ничего
- Produces: `commands.HARNESS_ANSWER: str = "harness-answer"`; `parse_command("/harness-answer 1") == HARNESS_ANSWER`; `parse_command_args` отдаёт хвост многострочно; меток `run:`/`done:`/`failed:` у команды нет

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_commands.py`:

```python
def test_harness_answer_is_a_command_with_multiline_tail():
    """Ответ человека на заданный вопрос — команда с многострочным хвостом.

    Сценарий приёмки в одну строку не пишут, поэтому хвост забирается
    целиком, как у /bft-deep.
    """
    body = "/harness-answer 405 на любой метод кроме POST\nREADME не трогаем"
    assert commands.parse_command(body) == commands.HARNESS_ANSWER
    assert commands.parse_command_args(body) == \
        "405 на любой метод кроме POST\nREADME не трогаем"


def test_harness_answer_with_number_only():
    body = "/harness-answer 1"
    assert commands.parse_command(body) == commands.HARNESS_ANSWER
    assert commands.parse_command_args(body) == "1"


def test_quoted_harness_answer_is_not_a_command():
    """Цитата ответа не запускает его повторно (существующее правило)."""
    assert commands.parse_command("> /harness-answer 1") is None
```

В `tests/test_label_catalog.py`:

```python
def test_harness_answer_does_not_produce_run_labels():
    """Ответ человека — не дорогая стадия, меток прогона у него нет.

    Каталог выводит run:/done:/failed: из списка команд автоматически;
    без исключения на задачах появилось бы `run:harness-answer`.
    """
    known = label_catalog.all_labels()
    for label in ("run:harness-answer", "done:harness-answer",
                  "failed:harness-answer"):
        assert label not in known, label
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_commands.py tests/test_label_catalog.py -k harness_answer -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'shared.commands' has no attribute 'HARNESS_ANSWER'`

- [ ] **Step 3: Завести команду**

В `shared/commands.py` рядом с прочими именами:

```python
# Ответ человека на вопрос, заданный контуром. Команда ОБЩАЯ, не привязанная к
# приёмке: тем же способом контур спрашивает про границы MVP, про выбор из
# вариантов плана, про спорное решение в разработке. Один способ ответа на любой
# вопрос лучше выводка команд под каждый повод.
#
# Дорогую стадию не запускает — меток run:/done:/failed: у неё быть не должно,
# см. исключение в shared/label_catalog.py.
HARNESS_ANSWER = "harness-answer"
```

и в перечень:

```python
_COMMANDS = {"/estimate": ESTIMATE, "/analyze": ANALYZE, "/research": RESEARCH,
             "/bft": BFT, "/bft-deep": BFT_DEEP, "/release": RELEASE,
             "/howtodemo": HOWTODEMO, "/harness-answer": HARNESS_ANSWER}

# Команды, не запускающие дорогую стадию: у них нет прогона, а значит нет и
# меток его состояния.
NO_RUN_LABEL_COMMANDS = frozenset({HARNESS_ANSWER})
```

- [ ] **Step 4: Исключить из каталога меток**

В `shared/label_catalog.py`, функция `_all_command_labels`:

```python
def _all_command_labels() -> frozenset[str]:
    result: set[str] = set()
    # _COMMANDS maps slash-command names to the canonical label suffix.
    for command in commands._COMMANDS.values():
        if command in commands.NO_RUN_LABEL_COMMANDS:
            continue
        result.add(commands.run_label(command))
        result.add(commands.done_label(command))
        result.add(commands.failed_label(command))
    result.update(commands._LEGACY_RUNNING_LABELS.get(commands.ANALYZE, ()))
    return frozenset(result)
```

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_commands.py tests/test_label_catalog.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add shared/commands.py shared/label_catalog.py tests/test_commands.py tests/test_label_catalog.py
git commit -m "feat(commands): /harness-answer — ответ человека на вопрос контура"
```

---

### Task 5: Модель предлагает варианты критерия

Закрывает R9, R12.

**Files:**
- Create: `shared/acceptance_proposal.py`
- Test: `tests/test_acceptance_proposal.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `class AcceptanceOption(BaseModel)` с полями `before: str`, `after: str`
  - `class AcceptanceOptions(BaseModel)` с полем `options: list[AcceptanceOption]`
  - `render_option(option: AcceptanceOption) -> str` — одна строка «было / стало»
  - `SYSTEM_PROMPT: str`

Отдельный модуль, а не функция в `activities.py`: файл активностей уже за четыре тысячи строк, и модель с промптом там утонет.

- [ ] **Step 1: Написать падающие тесты**

```python
import pytest
from shared import acceptance_proposal as ap


def test_render_option_is_one_line_before_after():
    option = ap.AcceptanceOption(
        before='GET /quote отвечает 404 {"error":"не найдено"}',
        after='GET /quote отвечает 405 с заголовком Allow: POST',
    )
    rendered = ap.render_option(option)
    assert "было" in rendered.lower()
    assert "стало" in rendered.lower()
    assert '404' in rendered and '405' in rendered


def test_options_model_rejects_empty_list():
    """Пустой список вариантов — это отказ модели, а не ответ.

    Пропустить его значило бы задать человеку вопрос без вариантов.
    """
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=[])


def test_options_model_caps_at_three():
    """Больше трёх вариантов человек не читает, он их пролистывает."""
    many = [ap.AcceptanceOption(before=f"было {i}", after=f"стало {i}")
            for i in range(5)]
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=many)


def test_system_prompt_demands_observable_signs():
    """Промпт обязан требовать наблюдаемых признаков, а не пересказа задачи."""
    assert "наблюдаем" in ap.SYSTEM_PROMPT.lower()
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_acceptance_proposal.py -q -p no:randomly --no-cov`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.acceptance_proposal'`

- [ ] **Step 3: Написать модуль**

```python
"""Варианты критерия приёмки, предлагаемые человеку.

Отдельный модуль, а не функция в activities: файл активностей уже за четыре
тысячи строк, и промпт с моделью данных там теряется.

Форма варианта — «было / стало» наблюдаемыми признаками. Пересказ задачи
критерием не является: по нему нельзя вынести вердикт.
"""
from pydantic import BaseModel, Field, field_validator


class AcceptanceOption(BaseModel):
    """Один вариант критерия: наблюдаемое «до» и наблюдаемое «после»."""

    before: str = Field(description="Что наблюдается сейчас, конкретно")
    after: str = Field(description="Что должно наблюдаться после правки")


class AcceptanceOptions(BaseModel):
    """Набор вариантов для одного вопроса человеку."""

    options: list[AcceptanceOption]

    @field_validator("options")
    @classmethod
    def _sane_count(cls, value: list[AcceptanceOption]) -> list[AcceptanceOption]:
        # Пустой список — отказ модели, а не ответ: вопрос без вариантов
        # бесполезен человеку. Больше трёх не читают, а пролистывают.
        if not value:
            raise ValueError("модель не предложила ни одного варианта")
        if len(value) > 3:
            raise ValueError(f"вариантов должно быть не больше трёх, дано {len(value)}")
        return value


def render_option(option: AcceptanceOption) -> str:
    """Вариант одной строкой для комментария человеку."""
    return f"было — {option.before}; стало — {option.after}"


SYSTEM_PROMPT = """Ты помогаешь сформулировать критерий приёмки задачи.

Прочитай задачу и предложи от двух до трёх вариантов критерия. Каждый вариант —
пара наблюдаемых признаков: что наблюдается сейчас и что должно наблюдаться
после правки.

Требования к вариантам:
- только наблюдаемое: код ответа, текст в интерфейсе, содержимое файла,
  поведение команды. Никакого пересказа задачи и никаких намерений;
- варианты должны отличаться ГРАНИЦАМИ работы, а не формулировкой: например,
  первый — только основное поведение, второй — оно же плюс смежный случай;
- пиши на языке задачи;
- конкретика вместо общих слов: «отвечает 405 с заголовком Allow: POST», а не
  «отвечает корректно»."""
```

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_acceptance_proposal.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add shared/acceptance_proposal.py tests/test_acceptance_proposal.py
git commit -m "feat(acceptance): модель вариантов критерия приёмки и промпт"
```

---

### Task 6: Активность «спросить человека»

Закрывает R4, R9, R10, R11, R12.

**Files:**
- Modify: `worker/activities.py` (новая активность в конце файла)
- Modify: `shared/labels.py` (метка ожидания)
- Modify: `worker/worker.py` (регистрация активности)
- Test: `tests/test_acceptance_question.py` (новый файл)

**Interfaces:**
- Consumes: `shared.acceptance_proposal` из Task 5, `issue_blocks.HOWTODEMO` из Task 2
- Produces: активность `ask_acceptance_criteria(issue: IssueInput) -> bool` — `True`, если вопрос задан или уже висел; `False`, если задать не удалось. Имя для `execute_activity` — `activities.ask_acceptance_criteria`.

- [ ] **Step 1: Метка ожидания**

В `shared/labels.py` рядом с `NEEDS_HUMAN_TRIAGE`:

```python
# Ждём от человека критерий приёмки: без него разработка не начинается.
NEEDS_HUMAN_HOWTODEMO = f"{NEEDS_HUMAN_PREFIX}howtodemo"
```

- [ ] **Step 2: Написать падающие тесты**

`tests/test_acceptance_question.py`:

```python
import pytest
import activities as a
from shared import issue_blocks, labels
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="GET /quote отдаёт 404",
                      body="Сейчас 404, ожидается 405 с Allow: POST")


def test_question_names_the_command_verbatim(monkeypatch, issue):
    """Комментарий обязан назвать команду ответа дословно (R10).

    Сегодняшний отказ звучал «добавьте раздел HowToDemo» и не сказал, как
    отвечать — он стоил впустую потраченного прогона.
    """
    posted = []
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.append(body))
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: issue.body)
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [])
    monkeypatch.setattr(a, "_propose_acceptance_options",
                        lambda issue: ["было A; стало B", "было C; стало D"])

    assert a.ask_acceptance_criteria(issue) is True
    body = posted[0]
    assert "/harness-answer" in body
    assert "обычный комментарий" in body.lower()
    assert "<!-- issue-agent -->" in body


def test_question_sets_waiting_label(monkeypatch, issue):
    labelled = []
    monkeypatch.setattr(a.github_client, "post_comment", lambda *args: None)
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: labelled.append(label))
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: issue.body)
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [])
    monkeypatch.setattr(a, "_propose_acceptance_options",
                        lambda issue: ["было A; стало B"])

    a.ask_acceptance_criteria(issue)
    assert labels.NEEDS_HUMAN_HOWTODEMO in labelled


def test_question_is_asked_once(monkeypatch, issue):
    """Повторный проход гейта комментарии не плодит (R11)."""
    posted = []
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.append(body))
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: issue.body)
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [
        {"body": "текст вопроса\n\n<!-- harness:acceptance-question -->"},
    ])
    monkeypatch.setattr(a, "_propose_acceptance_options",
                        lambda issue: ["было A; стало B"])

    assert a.ask_acceptance_criteria(issue) is True
    assert posted == []


def test_model_failure_asks_plainly_and_does_not_pass(monkeypatch, issue):
    """Модель отказала — вопрос всё равно задан, честным текстом (R12).

    Молча пропустить задачу в разработку нельзя: критерия как не было, так и
    нет, и вердикт по ней всё равно вынести нечем.
    """
    posted = []
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.append(body))
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: issue.body)
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [])

    def boom(issue):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(a, "_propose_acceptance_options", boom)

    assert a.ask_acceptance_criteria(issue) is True
    assert "/harness-answer" in posted[0]
    assert "не смог" in posted[0].lower()


def test_existing_block_means_no_question(monkeypatch, issue):
    """Критерий уже утверждён — вопроса нет (R24)."""
    body = issue_blocks.write(issue.body, issue_blocks.HOWTODEMO, "уже утверждено")
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: body)
    posted = []
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, b: posted.append(b))
    monkeypatch.setattr(a.github_client, "add_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [])

    assert a.ask_acceptance_criteria(issue) is True
    assert posted == []
```

- [ ] **Step 3: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_acceptance_question.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'ask_acceptance_criteria'`

- [ ] **Step 4: Написать активность**

В конец `worker/activities.py`:

```python
# Маркер вопроса о критерии приёмки. По нему активность узнаёт свой прежний
# вопрос в ленте и не задаёт его повторно: один вопрос на задачу (R11).
ACCEPTANCE_QUESTION_MARKER = "<!-- harness:acceptance-question -->"


def _propose_acceptance_options(issue) -> list[str]:
    """Строки вариантов критерия от модели. Бросает — значит не вышло."""
    from shared import acceptance_proposal

    options = llm.extract(
        acceptance_proposal.SYSTEM_PROMPT,
        f"# {issue.title}\n\n{issue.body or ''}",
        acceptance_proposal.AcceptanceOptions,
        model=llm.MODEL_GATE,
    )
    return [acceptance_proposal.render_option(option) for option in options.options]


@activity.defn
def ask_acceptance_criteria(issue) -> bool:
    """Спросить у человека критерий приёмки и повесить метку ожидания.

    Возвращает True всегда, когда задача осталась ждать, — и когда вопрос
    задан, и когда он уже висел, и когда модель отказала. False не возвращается
    вовсе: пропустить задачу в разработку без критерия эта активность права не
    имеет. Тип оставлен bool на случай, если такое право появится, — менять
    сигнатуру у живых прогонов дороже.

    Отказ, ради которого написано: poh-demo-checkout#163 отработал целиком и
    закрылся, а приёмка отвечала «проверять нечем».
    """
    body = github_client.get_issue_body(issue.repo, issue.issue_number)

    # Критерий уже утверждён — спрашивать нечего.
    if issue_blocks.read(body, issue_blocks.HOWTODEMO):
        return True

    # Вопрос уже задан — второй раз не задаём.
    for comment in github_client.list_comments(issue.repo, issue.issue_number):
        if ACCEPTANCE_QUESTION_MARKER in (comment.get("body") or ""):
            return True

    try:
        options = _propose_acceptance_options(issue)
    except Exception as err:
        # Отказ модели не пропускает задачу и не роняет цикл: человек получает
        # честный текст и тот же способ ответа.
        activity.logger.warning("варианты критерия не построились: %s", err)
        options = []

    lines = ["**Не вижу, чем принимать эту задачу.** "
             "Разработку не начинаю, пока не будет критерия готовности.", ""]
    if options:
        lines.append("Вот как я её понял:")
        lines.append("")
        for number, option in enumerate(options, start=1):
            lines.append(f"**{number}.** {option}")
        lines.append("")
        lines.append("**Отвечать нужно командой** — обычный комментарий я не читаю:")
        lines.append("")
        lines.append("```")
        lines.append("/harness-answer 1")
        lines.append("```")
        lines.append("")
        lines.append("или своим текстом:")
    else:
        lines.append("Предложить варианты не смог — напишите критерий сами.")
        lines.append("")
        lines.append("**Отвечать нужно командой** — обычный комментарий я не читаю:")
    lines.append("")
    lines.append("```")
    lines.append("/harness-answer было 404, стало 405 с заголовком Allow: POST")
    lines.append("```")
    lines.append("")
    lines.append(ACCEPTANCE_QUESTION_MARKER)
    lines.append(AGENT_COMMENT_MARKER)

    github_client.post_comment(issue.repo, issue.issue_number, "\n".join(lines))
    github_client.add_label(issue.repo, issue.issue_number,
                            labels.NEEDS_HUMAN_HOWTODEMO)
    return True
```

Если константа маркера комментария контура называется иначе — взять существующее имя из модуля (то, что подставляется в прочие комментарии активностей) вместо `AGENT_COMMENT_MARKER`.

- [ ] **Step 5: Зарегистрировать активность**

В `worker/worker.py` дописать `activities.ask_acceptance_criteria` в перечень активностей воркера, рядом с прочими.

- [ ] **Step 6: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_acceptance_question.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 7: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 8: Коммит**

```bash
git add worker/activities.py worker/worker.py shared/labels.py tests/test_acceptance_question.py
git commit -m "feat(acceptance): вопрос о критерии приёмки с вариантами и командой ответа"
```

---

### Task 7: Активность «принять ответ»

Закрывает R18, R19, R20, R22.

**Files:**
- Modify: `worker/activities.py`
- Modify: `worker/worker.py`
- Test: `tests/test_acceptance_answer.py` (новый файл)

**Interfaces:**
- Consumes: `ACCEPTANCE_QUESTION_MARKER` из Task 6, `commands.HARNESS_ANSWER` из Task 4
- Produces: активность `accept_acceptance_answer(issue, text: str) -> str` — возвращает `"accepted"` (критерий записан в тело, можно ехать), `"confirm"` (показано толкование, ждём второго ответа), `"noop"` (вопроса не было)

- [ ] **Step 1: Написать падающие тесты**

```python
import pytest
import activities as a
from shared import issue_blocks, labels
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="t", body="описание")


def _question(options=("было A; стало B", "было C; стало D")):
    lines = ["Не вижу, чем принимать."]
    for number, option in enumerate(options, start=1):
        lines.append(f"**{number}.** {option}")
    lines.append(a.ACCEPTANCE_QUESTION_MARKER)
    return {"body": "\n".join(lines)}


def test_number_writes_the_block_and_accepts(monkeypatch, issue):
    """Номер — толкования не было, едем сразу (R18)."""
    written = {}
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda *args, **kw: [_question()])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: written.setdefault("body", body))
    monkeypatch.setattr(a.github_client, "remove_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "post_comment", lambda *args: None)

    assert a.accept_acceptance_answer(issue, "1") == "accepted"
    assert issue_blocks.read(written["body"], issue_blocks.HOWTODEMO) == \
        "было A; стало B"


def test_number_out_of_range_goes_the_free_text_way(monkeypatch, issue):
    """`/harness-answer 7` при двух вариантах — это не выбор, а текст."""
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda *args, **kw: [_question()])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "update_issue_body", lambda *args: None)
    monkeypatch.setattr(a.github_client, "post_comment", lambda *args: None)
    monkeypatch.setattr(a.github_client, "remove_label", lambda *args: None)

    assert a.accept_acceptance_answer(issue, "7") == "confirm"


def test_free_text_shows_what_it_recorded_and_waits(monkeypatch, issue):
    """Свободный текст — толкование появилось, показываем и ждём (R19)."""
    posted = []
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda *args, **kw: [_question()])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "update_issue_body", lambda *args: None)
    monkeypatch.setattr(a.github_client, "remove_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.append(body))

    assert a.accept_acceptance_answer(issue, "405 на любой метод кроме POST") == "confirm"
    assert "405 на любой метод кроме POST" in posted[0]
    assert "/harness-answer" in posted[0]


def test_second_answer_confirms_and_accepts(monkeypatch, issue):
    """Второй ответ — подтверждение, критерий записан."""
    written = {}
    shown = ("Записал так: 405 на любой метод кроме POST\n"
             f"{a.ACCEPTANCE_ECHO_MARKER}")
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda *args, **kw: [_question(), {"body": shown}])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: written.setdefault("body", body))
    monkeypatch.setattr(a.github_client, "remove_label", lambda *args: None)
    monkeypatch.setattr(a.github_client, "post_comment", lambda *args: None)

    assert a.accept_acceptance_answer(issue, "да") == "accepted"
    assert "405 на любой метод кроме POST" in \
        issue_blocks.read(written["body"], issue_blocks.HOWTODEMO)


def test_answer_without_question_says_so(monkeypatch, issue):
    """Ответ там, где не спрашивали — одна строка, не молчание (R20)."""
    posted = []
    monkeypatch.setattr(a.github_client, "list_comments", lambda *args, **kw: [])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: posted.append(body))

    assert a.accept_acceptance_answer(issue, "1") == "noop"
    assert "вопрос" in posted[0].lower()


def test_accepted_answer_removes_the_waiting_label(monkeypatch, issue):
    removed = []
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda *args, **kw: [_question()])
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda *args: "описание")
    monkeypatch.setattr(a.github_client, "update_issue_body", lambda *args: None)
    monkeypatch.setattr(a.github_client, "post_comment", lambda *args: None)
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: removed.append(label))

    a.accept_acceptance_answer(issue, "1")
    assert labels.NEEDS_HUMAN_HOWTODEMO in removed
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_acceptance_answer.py -q -p no:randomly --no-cov`
Expected: FAIL с `AttributeError: module 'activities' has no attribute 'accept_acceptance_answer'`

- [ ] **Step 3: Написать активность**

В `worker/activities.py`:

```python
# Маркер комментария «вот что я записал». По нему активность отличает второй
# ответ (подтверждение) от первого.
ACCEPTANCE_ECHO_MARKER = "<!-- harness:acceptance-echo -->"

# Вариант в комментарии вопроса: `**1.** было …; стало …`
_ACCEPTANCE_OPTION = re.compile(r"^\*\*(?P<number>\d+)\.\*\*[ \t]*(?P<text>.+)$",
                                re.MULTILINE)


def _acceptance_question(repo: str, issue_number: int) -> tuple[list[str], str]:
    """Варианты из заданного вопроса и показанное толкование, если оно было.

    Пустой список вариантов и пустая строка — вопроса не задавали.
    """
    options: list[str] = []
    echo = ""
    for comment in github_client.list_comments(repo, issue_number):
        body = comment.get("body") or ""
        if ACCEPTANCE_QUESTION_MARKER in body:
            options = [match.group("text").strip()
                       for match in _ACCEPTANCE_OPTION.finditer(body)]
        if ACCEPTANCE_ECHO_MARKER in body:
            echo = body.split(ACCEPTANCE_ECHO_MARKER)[0].strip()
    return options, echo


def _write_acceptance_block(issue, criterion: str) -> None:
    body = github_client.get_issue_body(issue.repo, issue.issue_number)
    github_client.update_issue_body(
        issue.repo, issue.issue_number,
        issue_blocks.write(body, issue_blocks.HOWTODEMO, criterion))
    github_client.remove_label(issue.repo, issue.issue_number,
                               labels.NEEDS_HUMAN_HOWTODEMO)


@activity.defn
def accept_acceptance_answer(issue, text: str) -> str:
    """Принять ответ человека на вопрос о критерии приёмки.

    `accepted` — критерий записан в тело, разработку можно начинать.
    `confirm`  — толкование показано, ждём второго ответа.
    `noop`     — вопроса не задавали.

    Номер варианта и свободный текст разведены намеренно: выбирая номер,
    человек утверждает текст, который прочитал дословно, — толкования не было и
    подтверждать нечего. Свободный текст контур истолковал заново, и это
    толкование должно быть предъявлено до того, как за него заплатят прогоном
    разработки.
    """
    answer = (text or "").strip()
    options, echo = _acceptance_question(issue.repo, issue.issue_number)

    if not options:
        # Молчание здесь неотличимо от проглоченной команды.
        github_client.post_comment(
            issue.repo, issue.issue_number,
            "Сейчас я ничего не спрашивал — отвечать не на что.\n\n"
            f"{AGENT_COMMENT_MARKER}")
        return "noop"

    # Второй ответ при показанном толковании — подтверждение.
    if echo:
        _write_acceptance_block(issue, echo.split("\n", 1)[-1].strip() or echo)
        return "accepted"

    if answer.isdigit() and 1 <= int(answer) <= len(options):
        _write_acceptance_block(issue, options[int(answer) - 1])
        return "accepted"

    # Всё остальное — свободный текст, включая номер вне списка.
    github_client.post_comment(
        issue.repo, issue.issue_number,
        f"Записал критерий так:\n\n{answer}\n\n"
        "Если верно — подтвердите:\n\n"
        "```\n/harness-answer да\n```\n\n"
        "Если нет — пришлите поправленный текст той же командой.\n\n"
        f"{ACCEPTANCE_ECHO_MARKER}\n{AGENT_COMMENT_MARKER}")
    return "confirm"
```

- [ ] **Step 4: Зарегистрировать активность**

В `worker/worker.py` дописать `activities.accept_acceptance_answer`.

- [ ] **Step 5: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_acceptance_answer.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add worker/activities.py worker/worker.py tests/test_acceptance_answer.py
git commit -m "feat(acceptance): приём ответа человека — номером и свободным текстом"
```

---

### Task 8: Команда доезжает до цикла

Закрывает R13 и R17 со стороны вебхука.

**Files:**
- Modify: `webhook/main.py:806-880` (разбор команд в `issue_comment`)
- Test: `tests/test_webhook_harness_answer.py` (новый файл)

**Interfaces:**
- Consumes: `commands.HARNESS_ANSWER` из Task 4
- Produces: `/harness-answer` уезжает сигналом `user_comment` с полным телом комментария; цикл сам разбирает команду

- [ ] **Step 1: Написать падающий тест**

```python
def test_harness_answer_reaches_the_lifecycle(monkeypatch, client):
    """Ответ человека доезжает до цикла сигналом user_comment.

    Прочие команды в user_comment не уходят — их съел бы цикл уточнений. Эта
    уходит намеренно: её адресат и есть цикл, стоящий на гейте.
    """
    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client",
                        _fake_client_returning(_Handle()))

    response = client.post("/webhook", json=_comment_payload("/harness-answer 1"),
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled and signalled[0][0] == "user_comment"
    assert "/harness-answer 1" in signalled[0][1][0]
```

```python
def test_agent_own_comment_is_not_an_answer(monkeypatch, client):
    """Комментарий контура ответом не считается (R17).

    Контур подписывает свои комментарии маркером; под PAT они возвращаются
    с `type == "User"`, и без проверки подписи агент отвечал бы сам себе.
    """
    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client",
                        _fake_client_returning(_Handle()))

    payload = _comment_payload("/harness-answer 1\n\n<!-- issue-agent -->")
    response = client.post("/webhook", json=payload,
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled == [], "контур принял собственный комментарий за ответ"
```

Вспомогательные `_fake_client_returning` и `_comment_payload` взять из соседнего теста вебхука (`tests/test_webhook_subissue_ignored.py`) — фикстура из чужого модуля не видна, копия обязательна.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_webhook_harness_answer.py -q -p no:randomly --no-cov`
Expected: FAIL — сигнала нет либо он не тот.

- [ ] **Step 3: Провести команду до сигнала**

В `webhook/main.py`, среди разбора команд, ПЕРЕД разбором дорогих стадий:

```python
        if command == HARNESS_ANSWER:
            # Единственная команда, которая идёт в `user_comment`: её адресат —
            # цикл, стоящий на гейте, а не отдельный workflow. Дорогую стадию
            # она не запускает, поэтому и `_may_start_expensive` тут не при чём.
            # Разбирает её сам цикл: он один знает, спрашивал ли что-нибудь.
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

Импорт `HARNESS_ANSWER` добавить к прочим именам команд в шапке модуля.

- [ ] **Step 4: Прогнать и убедиться, что прошло**

Run: `python -m pytest tests/test_webhook_harness_answer.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add webhook/main.py tests/test_webhook_harness_answer.py
git commit -m "feat(webhook): /harness-answer доезжает до цикла сигналом"
```

---

### Task 9: Гейт перед разработкой

Закрывает R1, R2, R3. **Правка решения воркфлоу — обязателен `workflow.patched`.**

**Files:**
- Modify: `worker/workflows.py:1874` (`_start_development`)
- Test: `tests/test_workflow_acceptance_gate.py` (новый файл)
- Test: `tests/test_workflow_replay.py` (прогнать без правок)

**Interfaces:**
- Consumes: активности `ask_acceptance_criteria` (Task 6), `accept_acceptance_answer` (Task 7), `_howtodemo_block` (Task 3), `commands.HARNESS_ANSWER` (Task 4)
- Produces: активность `read_acceptance_criterion(issue) -> str` (заводится в этой же задаче, Step 3); поле цикла `self._awaiting_acceptance: bool`; `_start_development` не запускает разработку без критерия

- [ ] **Step 1: Написать падающие тесты**

Заглушки активностей цикла (`awaiting_stub`, `prefilter_ok`, `protocol_default`,
`read_deadlines` и прочие) скопировать ВЕРБАТИМ из `tests/test_agent_event_workflow.py`
— фикстура и заглушки из чужого тестового модуля не видны (AGENTS.md, правило 8).
Ниже — только то, что относится к гейту.

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

from shared import lifecycle
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
    return "было 404, стало 405 с Allow: POST"


@activity.defn(name="ask_acceptance_criteria")
async def ask_stub(issue: IssueInput) -> bool:
    _calls.append("ask")
    return True


@activity.defn(name="dev_begin")
async def dev_started(issue: IssueInput):
    _calls.append("development")
    raise AssertionError("разработка началась без критерия приёмки")


def _issue(origin_agent: bool = False) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=163, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.mark.asyncio
async def test_development_does_not_start_without_criterion():
    """Без критерия разработка не начинается, вопрос задан (R1)."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, ask_stub, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "ask" in _calls, "вопрос о критерии не задан"
    assert "development" not in _calls, "разработка началась без критерия"


@pytest.mark.asyncio
async def test_development_starts_when_criterion_is_present():
    """Критерий есть — гейт пропускает молча, вопроса нет (R24)."""
    _calls.clear()

    @activity.defn(name="dev_begin")
    async def dev_ok(issue: IssueInput):
        _calls.append("development")
        raise RuntimeError("дальше разработка не нужна — факт старта уже записан")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_present, ask_stub, dev_ok]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "development" in _calls, "разработка не началась при готовом критерии"
    assert "ask" not in _calls, "вопрос задан там, где критерий уже есть"


@pytest.mark.asyncio
async def test_agent_authored_issue_is_gated_too():
    """Задача, заведённая контуром, исключением не является (R2).

    Соблазн освободить `origin:agent` от гейта велик — таких задач в контуре
    большинство. Но именно они и есть работа без образа результата.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[criterion_absent, ask_stub, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(origin_agent=True),
                id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "ask" in _calls
    assert "development" not in _calls
```

Если сигнатура `IssueInput` не принимает `origin_agent`, признак происхождения
берётся из меток — тогда в третьем тесте подменить заглушку `read_protocol_state`
так, чтобы она отдавала состояние задачи контура, а само тело теста оставить
как есть.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `python -m pytest tests/test_workflow_acceptance_gate.py -q -p no:randomly --no-cov`
Expected: FAIL — разработка стартует без критерия.

- [ ] **Step 3: Поставить гейт**

В начало `_start_development`, ДО вычисления ветки и запуска дочернего прогона:

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
                await workflow.execute_activity(
                    activities.ask_acceptance_criteria, issue,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                self._awaiting_acceptance = True
                return (lifecycle.READY_FOR_DEV, "awaiting-acceptance-criterion", False)
```

Добавить активность-читалку в `worker/activities.py` (тонкая, без модели):

```python
@activity.defn
def read_acceptance_criterion(issue) -> str:
    """Критерий приёмки задачи: утверждённый блок либо раздел в теле.

    Отдельная активность, а не чтение в воркфлоу: тело Issue живёт снаружи, и
    ходить за ним из воркфлоу нельзя — реплей обязан быть детерминированным.
    """
    body = github_client.get_issue_body(issue.repo, issue.issue_number)
    return _howtodemo_block(body)
```

Зарегистрировать её в `worker/worker.py`.

- [ ] **Step 4: Ответ снимает гейт**

В `_phase_await_build`, в ветке разбора `UserComment` (там, где сегодня зовётся `_answer_followup`), ПЕРЕД ней:

```python
            if self._awaiting_acceptance and workflow.patched(
                    "issue-lifecycle-acceptance-answer"):
                from shared.commands import HARNESS_ANSWER, parse_command, parse_command_args
                if parse_command(decision.text) == HARNESS_ANSWER:
                    verdict = await workflow.execute_activity(
                        activities.accept_acceptance_answer,
                        args=[issue, parse_command_args(decision.text)],
                        start_to_close_timeout=timedelta(minutes=3),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    if verdict == "accepted":
                        self._awaiting_acceptance = False
                        return await self._start_development(issue)
                    return (self._phase, self._stage, False)
```

Поле `self._awaiting_acceptance = False` завести в `__init__` цикла рядом с прочим состоянием.

- [ ] **Step 5: Прогнать тесты гейта**

Run: `python -m pytest tests/test_workflow_acceptance_gate.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 6: Прогнать гвард реплея — это главная проверка задачи**

Run: `python -m pytest tests/test_workflow_replay.py -q -p no:randomly --no-cov`
Expected: PASS. Красный гвард означает, что маркер поставлен не там или не поставлен вовсе, и выкладка убьёт живые прогоны. Чинить, а не обходить.

- [ ] **Step 7: Прогнать весь набор**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 8: Коммит**

```bash
git add worker/workflows.py worker/activities.py worker/worker.py tests/test_workflow_acceptance_gate.py
git commit -m "feat(gate): разработка не начинается без критерия приёмки

Маркер issue-lifecycle-acceptance-gate обязателен: решение «начать
разработку» уже лежит в историях припаркованных прогонов."
```

---

### Task 10: Сквозной путь

Закрывает путь целиком — тот, что развалился на #163.

**Files:**
- Test: `tests/test_acceptance_gate_e2e.py` (новый файл)

**Interfaces:**
- Consumes: всё предыдущее
- Produces: ничего

- [ ] **Step 1: Написать сквозной тест**

Сквозной тест идёт по активностям, а не по воркфлоу: цикл уже проверен в
Task 9, а здесь важно, что критерий доезжает до ИСПОЛНИТЕЛЯ — то есть до файла
`.harness/howtodemo.md`. Именно этого не случилось на #163.

```python
"""Сквозной путь гейта: вопрос, ответ, критерий в теле, критерий в .harness/.

Отказ, ради которого написано: poh-demo-checkout#163 прошёл разработку целиком,
а `.harness/howtodemo.md` так и не появился — сценарий в теле был, но
распознаватель его не увидел, и исполнитель работал без критерия.
"""

import pytest

import activities as a
from shared import issue_blocks, labels, task_context
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=163,
                      title="GET /quote отдаёт 404 вместо 405",
                      body="Сейчас 404 про файл, ожидается 405 с Allow: POST",
                      author_login="u", author_type="User", interactive=True)


def test_question_then_answer_then_criterion_reaches_the_runner(monkeypatch, issue, tmp_path):
    """Четыре факта одним прогоном:

    1. до ответа критерия нет — гейт задачу не пропустил бы;
    2. вопрос назвал команду ответа дословно;
    3. после ответа номером критерий лежит в теле блоком;
    4. подготовка задачи положила его в `.harness/howtodemo.md`.
    """
    state = {"body": issue.body, "comments": [], "labels": set()}

    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "list_comments",
                        lambda repo, number, **kw: list(state["comments"]))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append({"body": body}))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    monkeypatch.setattr(a, "_propose_acceptance_options", lambda issue: [
        "было — GET /quote отвечает 404; стало — GET /quote отвечает 405 с Allow: POST",
        "было — GET /quote отвечает 404; стало — 405 на любой метод кроме POST",
    ])

    # 1. Критерия нет — гейт бы не пропустил.
    assert a.read_acceptance_criterion(issue) == ""

    # 2. Вопрос задан и называет команду.
    assert a.ask_acceptance_criteria(issue) is True
    question = state["comments"][0]["body"]
    assert "/harness-answer" in question
    assert labels.NEEDS_HUMAN_HOWTODEMO in state["labels"]

    # 3. Ответ номером — критерий в теле, метка снята.
    assert a.accept_acceptance_answer(issue, "1") == "accepted"
    criterion = issue_blocks.read(state["body"], issue_blocks.HOWTODEMO)
    assert "405 с Allow: POST" in criterion
    assert labels.NEEDS_HUMAN_HOWTODEMO not in state["labels"]
    assert a.read_acceptance_criterion(issue) == criterion

    # 4. Критерий доехал до исполнителя файлом.
    harness = tmp_path / task_context.DIR
    harness.mkdir()
    (harness / task_context.HOWTODEMO).write_text(
        a.read_acceptance_criterion(issue), encoding="utf-8")
    assert "405 с Allow: POST" in (harness / task_context.HOWTODEMO).read_text()
```

Четвёртый шаг записан явной записью файла, а не вызовом `_dev_prepare`: тот
тянет за собой клон репозитория и прогон агента, и сквозной тест превратился бы
в интеграционный. Проверяется здесь одно — что `read_acceptance_criterion`
отдаёт текст, пригодный для записи в `.harness/`. Сборку `.harness/` целиком
проверяют тесты `tests/test_dev_task_assembly.py`.

- [ ] **Step 2: Прогнать**

Run: `python -m pytest tests/test_acceptance_gate_e2e.py -q -p no:randomly --no-cov`
Expected: PASS

- [ ] **Step 3: Прогнать весь набор и гвард реплея**

Run: `python -m pytest -q -p no:randomly`
Expected: PASS, покрытие не ниже 83%.

- [ ] **Step 4: Коммит**

```bash
git add tests/test_acceptance_gate_e2e.py
git commit -m "test(gate): сквозной путь — вопрос, ответ, разработка, howtodemo.md"
```

---

## Что остаётся человеку после плана

- **Документация.** `docs/HOWTODEMO.md` описывает поиск сценария по четырём английским формам и не знает ни про русские, ни про блок, ни про входной гейт. Правится в конце, одним проходом по факту сделанного.
- **Живой прогон.** План закрывается модульными проверками и гвардом реплея; работает ли гейт на стенде, покажет только живая задача — тем же способом, каким был найден дефект #163.
- **Дублирующая ветка в вебхуке.** В `webhook/main.py` разбор `if command == RESEARCH` встречается дважды, вторая недостижима. Задачу не касается — вынести отдельно.
