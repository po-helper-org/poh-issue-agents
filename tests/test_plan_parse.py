"""Разбор плана superpowers в шаги.

Зависимость берётся из блока Interfaces: непустой Consumes — объявленное ребро.
Отдельный вызов модели на декомпозицию не нужен.
"""

from pathlib import Path

from shared import plan_parse

ROOT = Path(__file__).resolve().parent.parent

PLAN = """# План

### Task 1: Загрузить версию

**Interfaces:**
- Consumes: ничего.
- Produces: `version` в состоянии сервиса.

### Task 2: Отдать версию

**Interfaces:**
- Consumes: Task 1 — читает `version` из состояния.
- Produces: маршрут GET /version.
"""


def test_titles_are_taken_from_task_headers():
    steps = plan_parse.parse(PLAN)
    assert [s["title"] for s in steps] == ["Загрузить версию", "Отдать версию"]


def test_consumes_nothing_gives_no_edges():
    assert plan_parse.parse(PLAN)[0]["depends_on"] == []


def test_consumes_task_gives_edge_with_reason():
    second = plan_parse.parse(PLAN)[1]
    assert second["depends_on"] == [0]
    assert "version" in second["depends_reason"]["0"]


def test_plan_without_tasks_is_empty():
    assert plan_parse.parse("# План, без задач") == []


# ────────── ревью: F1 — «Task N» резолвится по номеру, а не по позиции ──────────
#
# Прежний код превращал N из «Task N» в индекс N-1 списка заголовков в
# порядке их появления в документе. Совпадает с реальной задачей только
# тогда, когда план пронумерован подряд и по порядку — ниже три
# воспроизведённых ревьюером случая, где это не так.

PLAN_NUMBERED_1_5_9 = """# План

### Task 1: Первая

**Interfaces:**
- Consumes: ничего.

### Task 5: Пятая

**Interfaces:**
- Consumes: ничего.

### Task 9: Девятая

**Interfaces:**
- Consumes: Task 5 — использует результат пятой задачи.
"""


def test_ref_to_a_gap_numbered_task_resolves_by_header_number():
    """Task 9 стоит третьей по счёту, а не девятой — ссылка «Task 5» обязана
    найти задачу с номером 5 в заголовке (вторую по счёту, индекс 1), а не
    индекс 5-1=4, которого в списке из трёх задач не существует. Старый код
    молча терял это ребро (индекс вне диапазона)."""
    steps = plan_parse.parse(PLAN_NUMBERED_1_5_9)
    assert steps[2]["depends_on"] == [1]
    assert "5" in steps[2]["depends_reason"]["1"]


PLAN_OUT_OF_ORDER = """# План

### Task 3: Третья по номеру, первая по документу

**Interfaces:**
- Consumes: Task 3 — опечатка, реальной зависимости нет.

### Task 1: Первая по номеру, вторая по документу

**Interfaces:**
- Consumes: Task 2 — имеется в виду задача, идущая третьей по документу.

### Task 2: Вторая по номеру, третья по документу

**Interfaces:**
- Consumes: ничего.
"""


def test_ref_to_a_later_document_position_is_not_mistaken_for_self_reference():
    """Задача на позиции 1 (заголовок «Task 1») ссылается на «Task 2» — по
    номеру это задача на позиции 2 (третья по документу), настоящее ребро.
    Старый код резолвил «Task 2» в индекс 2-1=1 — совпало с СОБСТВЕННОЙ
    позицией автора ссылки, и фильтр самоссылки молча погасил настоящую
    зависимость."""
    steps = plan_parse.parse(PLAN_OUT_OF_ORDER)
    assert steps[1]["depends_on"] == [2]
    assert "2" in steps[1]["depends_reason"]


def test_typo_self_reference_by_number_is_filtered_not_redirected():
    """Задача на позиции 0 (заголовок «Task 3») по опечатке пишет «Consumes:
    Task 3» — ссылка на СВОЙ ЖЕ номер, то есть зависимости нет. Старый код
    резолвил «Task 3» в индекс 3-1=2 — это НЕ позиция автора (0), фильтр
    самоссылки не сработал, и создавалось ребро на третью задачу с текстом
    обоснования, который дословно говорит «реальной зависимости нет»."""
    steps = plan_parse.parse(PLAN_OUT_OF_ORDER)
    assert steps[0]["depends_on"] == []
    assert steps[0]["depends_reason"] == {}


PLAN_DUPLICATE_NUMBER = """# План

### Task 1: Первая версия шага А

**Interfaces:**
- Consumes: ничего.

### Task 1: Вторая версия шага А, тот же номер по ошибке

**Interfaces:**
- Consumes: ничего.

### Task 2: Использует шаг А

**Interfaces:**
- Consumes: Task 1 — берёт результат шага А.
"""


def test_ambiguous_duplicate_header_number_does_not_resolve_an_edge():
    """Решение по повторяющимся номерам заголовков (план этого репозитория
    их и правда содержит — см. ниже F2): ссылка на номер, который носят ДВЕ
    задачи, не может резолвиться однозначно, и угадывать одну из них — то
    же фабрикование ребра, которого модуль избегает для отсутствующих
    номеров. Обе задачи с номером 1 не становятся целью ребра — ссылка
    молча не резолвится, а не выбирает первую попавшуюся по старой (и
    случайно похожей на верную) индексной арифметике."""
    steps = plan_parse.parse(PLAN_DUPLICATE_NUMBER)
    assert steps[2]["depends_on"] == []
    assert steps[2]["depends_reason"] == {}


# ────────── ревью: F2 — блоки кода не читаются как настоящие шаги/рёбра ──────────

PLAN_WITH_FENCED_EXAMPLE = """# План

### Task 1: Настоящая первая задача

**Interfaces:**
- Consumes: ничего.

Пример из документации, как задачи ссылаются друг на друга:

```markdown
### Task 99: Пример, а не настоящая задача

**Interfaces:**
- Consumes: Task 1
```

### Task 2: Настоящая вторая задача

**Interfaces:**
- Consumes: ничего.
"""


def test_task_header_inside_a_code_fence_is_not_a_real_step():
    """Заголовок «### Task 99» и его Consumes показаны как иллюстрация
    внутри тройных обратных кавычек в теле задачи 1 — не настоящий шаг
    плана. Старый разбор не различал границы блоков кода и добавлял третий,
    выдуманный шаг (и ребро на реальную первую задачу, раз уж «Task 1»
    внутри примера тоже читался буквально)."""
    steps = plan_parse.parse(PLAN_WITH_FENCED_EXAMPLE)
    assert [s["title"] for s in steps] == [
        "Настоящая первая задача", "Настоящая вторая задача",
    ]


# ────────── ревью: F3 — Consumes: отступ и регистр буллета ──────────

PLAN_INDENTED_LOWERCASE_CONSUMES = """# План

### Task 1: Первая

**Interfaces:**
  - consumes: ничего.

### Task 2: Вторая

**Interfaces:**
  - consumes: Task 1 — использует первую.
"""


def test_indented_lowercase_consumes_bullet_is_still_found():
    """Вложенный буллет с отступом и строчная «consumes» — обычная форма, а
    не аномалия. Старый поиск требовал дефис ровно в начале строки и точное
    совпадение регистра «Consumes» — при отступе или строчной букве строка
    не находилась вовсе, и объявленная зависимость молча пропадала,
    неотличимо от Consumes: ничего."""
    steps = plan_parse.parse(PLAN_INDENTED_LOWERCASE_CONSUMES)
    assert steps[1]["depends_on"] == [0]


# ────────── ревью: реальный план репозитория ──────────

def test_real_repo_plan_step_count_matches_real_task_headers():
    """`docs/superpowers/plans/2026-08-26-mvp-decomposition-plan-1.md` несёт
    13 настоящих заголовков «### Task N» (Task 1..13, проверено вручную —
    `grep -n '^### Task'`), плюс два ЛИШНИХ внутри примера-фикстуры,
    процитированного в теле задачи 12 (тот самый PLAN с «Task 1»/«Task 2»
    из этого же тестового файла, показанный там как иллюстрация). До
    находки F2 разбор возвращал 15 шагов вместо 13."""
    path = ROOT / "docs" / "superpowers" / "plans" / "2026-08-26-mvp-decomposition-plan-1.md"
    text = path.read_text(encoding="utf-8")
    steps = plan_parse.parse(text)
    assert len(steps) == 13


# ────────── находка 1: незакрытый забор скрывает последующие задачи ──────────

PLAN_UNCLOSED_FENCE = """# План

### Task 1: Первая задача

Описание с незакрытым забором:

```python
def hello():
    print("hello")

### Task 2: Вторая задача (скрыта незакрытым забором)

**Interfaces:**
- Consumes: ничего.

### Task 3: Третья задача

**Interfaces:**
- Consumes: ничего.
"""


def test_unclosed_fence_in_task_body_causes_parse_error():
    """Незакрытый забор в теле задачи скрывает все последующие задачи в
    маске. Это опасно: результат структурно валиден, но половина плана
    исчезла молча. Должен быть явный отказ разбора."""
    import pytest
    with pytest.raises(ValueError, match="unclosed.*fence|незакрытый.*забор"):
        plan_parse.parse(PLAN_UNCLOSED_FENCE)


# ────────── находка 2: заборы из тильд не распознаются ──────────

PLAN_WITH_TILDES = """# План

### Task 1: Первая задача

Пример:

~~~python
def hello():
    print("hello")
~~~

### Task 2: Вторая задача

**Interfaces:**
- Consumes: Task 1 — использует первую.
"""


def test_tildes_fence_is_recognized():
    """Заборы из трёх или более тильд — валидный Markdown, и примеры внутри
    них не должны читаться как настоящие задачи или зависимости. Старый
    код не распознавал тильды, и заголовок внутри забора из тильд становился
    выдуманной задачей."""
    steps = plan_parse.parse(PLAN_WITH_TILDES)
    # Должны быть ровно две задачи, не три (не было Task внутри примера)
    assert len(steps) == 2
    assert [s["title"] for s in steps] == [
        "Первая задача", "Вторая задача"
    ]
    # Task 2 должна найти Task 1 в своих зависимостях
    assert steps[1]["depends_on"] == [0]
