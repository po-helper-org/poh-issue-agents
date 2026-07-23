# AI-агент оценки задач (`/estimate`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** По команде `/estimate` в комментарии Issue агент публикует оценку трудоёмкости с полным обоснованием, посчитанную по единому набору правил.

**Architecture:** Отдельный Temporal-workflow `IssueEstimation` (ID включает `comment_id`, что даёт идемпотентность при повторной доставке вебхука и переоценку без сигналов). LLM извлекает только факты по Pydantic-схеме; коэффициенты, PERT, cross-check, границы и Story Points считает чистый Python-модуль по `config/estimation-rules.toml` — тот же принцип, что уже применён в `score_priority`.

**Tech Stack:** Python 3.12, Temporal (`temporalio` 1.9.0), Instructor + OpenAI-клиент поверх z.ai, FastAPI (вебхук), `requests` (GitHub REST), pytest + pytest-asyncio.

## Global Constraints

- Все пользовательские тексты — на русском, орфографически корректные (включая «ё» там, где она уже используется в проекте).
- Комментарии в коде — на русском, в стиле существующих модулей: объясняют «почему», а не «что».
- Ни одна новая мутация в GitHub не выполняется при выставленном `DRY_RUN` (комментарии, лейблы, реакции). Чтение (`GET`) под `DRY_RUN` не блокируется.
- Расчётный модуль не делает сетевых вызовов и не импортирует `temporalio`, `instructor`, `github_client`.
- LLM не возвращает готовых чисел оценки: в схеме нет поля с итогом и нет поля со свободным множителем.
- Существующий поток `IssueLifecycle` не меняется по смыслу.
- Task queue для нового workflow — существующая `issue-lifecycle`, отдельный воркер не заводится.
- Запуск тестов: `.venv/bin/pytest -q` из корня репозитория (или `make test`).

---

## File Structure

| Файл | Ответственность |
|------|-----------------|
| `docs/methodology/task-estimation.md` | создать — обезличенная методология, человекочитаемый источник |
| `config/estimation-rules.toml` | создать — все числовые параметры, источник правды для расчёта |
| `shared/commands.py` | создать — разбор slash-команд, доступен и вебхуку, и воркеру |
| `worker/estimation.py` | создать — Pydantic-схема фактов + чистый расчёт |
| `worker/estimate_report.py` | создать — рендер markdown-комментария |
| `prompts/system_estimate_extract.md` | создать — промпт извлечения фактов |
| `shared/workflow_types.py` | дополнить — `EstimateRequest`, `EstimationContext`, `EstimateResult` |
| `worker/github_client.py` | дополнить — `add_reaction`, `get_issue`, `list_comments`, `get_file` |
| `worker/activities.py` | дополнить — шесть activity стадии оценки |
| `worker/workflows.py` | дополнить — класс `IssueEstimation` |
| `worker/worker.py` | дополнить — регистрация workflow и activity |
| `webhook/main.py` | дополнить — распознавание команды и старт workflow |
| `tests/conftest.py` | дополнить — фикстура `rules` |

Расчёт и рендер разнесены в два модуля намеренно: `activities.py` уже 300 строк, а обе новые части чистые и тестируются без Temporal и без сети.

---

## Task 1: Обезличенная методология и конфиг

**Files:**
- Create: `docs/methodology/task-estimation.md`
- Create: `config/estimation-rules.toml`
- Test: `tests/test_estimation_rules_doc_sync.py`

**Interfaces:**
- Consumes: ничего.
- Produces: TOML со структурой, которую читает `estimation.load_rules()` в Task 3: секции `work_type`, `test_share`, `missing_data_penalty`, `risk.<key>.{min,max}`, `sanity_bounds.<type>.{min_days,max_days,over,under}`, `pert.{optimistic_factor,pessimistic_factor,buffer_k}`, `cross_check.max_divergence`, `grade.{middle,senior,senior_ai}`, `day.hours`, `story_points.{hours_per_point,scale}`.

- [ ] **Step 1: Написать падающий тест синхронизации документа и конфига**

Создать `tests/test_estimation_rules_doc_sync.py`:

```python
"""Числа живут в двух местах: config/estimation-rules.toml (источник правды
для расчёта) и таблицы docs/methodology/task-estimation.md (для чтения
человеком). Этот тест не даёт копиям разъехаться.

Соглашение по формату: в таблице методологии ячейка с точечным путём ключа
TOML, а следом за ней — ячейка с числом. Строки без такой пары тест
пропускает, поэтому пояснительные таблицы ничего не ломают.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "methodology" / "task-estimation.md"
RULES = ROOT / "config" / "estimation-rules.toml"

KEY_PATH = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _lookup(rules: dict, dotted: str):
    node = rules
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _pairs_from_doc() -> list[tuple[str, float]]:
    pairs = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        for left, right in zip(cells, cells[1:]):
            if not KEY_PATH.match(left):
                continue
            try:
                pairs.append((left, float(right.replace(",", "."))))
            except ValueError:
                continue
    return pairs


def test_doc_declares_at_least_the_core_keys():
    keys = {key for key, _ in _pairs_from_doc()}
    assert "work_type.new_development" in keys
    assert "pert.buffer_k" in keys
    assert len(keys) >= 20


def test_every_number_in_doc_matches_config():
    with open(RULES, "rb") as f:
        rules = tomllib.load(f)
    mismatched = []
    for key, value in _pairs_from_doc():
        actual = _lookup(rules, key)
        if actual is None or float(actual) != value:
            mismatched.append((key, value, actual))
    assert not mismatched, f"расходятся с TOML: {mismatched}"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_estimation_rules_doc_sync.py -q`
Expected: FAIL — `FileNotFoundError` на `docs/methodology/task-estimation.md`.

- [ ] **Step 3: Создать `config/estimation-rules.toml`**

```toml
# Численные параметры методологии оценки задач.
#
# Этот файл — источник правды для расчёта (worker/estimation.py). Те же числа
# продублированы в docs/methodology/task-estimation.md для чтения человеком;
# tests/test_estimation_rules_doc_sync.py следит, чтобы копии не разъехались.
#
# Меняя коэффициенты здесь, не трогаешь ни промпт, ни код расчёта.

[work_type]
# Коэффициент к объёму работ по типу задачи. Модель проставляет часы так,
# как если бы это была новая разработка с нуля; скидку накладывает код —
# иначе она применилась бы дважды.
copy_existing = 0.35
documentation = 0.5
research = 0.6
new_development = 1.0
enhancement = 0.9
deployment = 0.75

[test_share]
# Тесты как доля от объёма работ (каркас + единицы + интеграция).
ratio = 0.3

[missing_data_penalty]
# Надбавки к пессимистичному сценарию за то, чего нет в описании.
# Применяются только те, чей флаг в фактах ложен.
no_acceptance_criteria = 0.2
no_dependencies = 0.15
no_api_contract = 0.3
no_data_class = 0.3

# Риски применяются контекстно: min идёт в реалистичный сценарий,
# max — в пессимистичный. Риск, не перечисленный здесь, игнорируется,
# даже если модель его назвала.
[risk.personal_data]
min = 0.3
max = 0.8

[risk.cross_team]
min = 0.2
max = 0.5

[risk.undocumented_external_api]
min = 0.4
max = 0.6

[risk.unagreed_api_contract]
min = 0.2
max = 0.3

[risk.security_unreviewed]
min = 0.5
max = 1.0

# Коридоры реалистичности. Выход за границу НЕ меняет число — поднимается
# флаг с рекомендацией, что перепроверить.
[sanity_bounds.bugfix]
min_days = 0.5
max_days = 3
over = "дольше трёх дней — это уже не багфикс, а доработка"
under = "меньше половины дня — проверь, самостоятельная ли это задача"

[sanity_bounds.validation]
min_days = 0.5
max_days = 5
over = "дольше пяти дней — вероятно, неверно посчитан объём обрабатываемых данных"
under = "меньше половины дня — проверь, самостоятельная ли это задача"

[sanity_bounds.subtask]
min_days = 0.5
max_days = 5
over = "дольше пяти дней — родительская задача разбита неправильно"
under = "меньше половины дня — проверь, самостоятельная ли это задача"

[sanity_bounds.new_module]
min_days = 1
max_days = 15
over = "дольше пятнадцати дней — нужна декомпозиция"
under = "меньше дня на новый модуль — проверь, всё ли учтено"

[pert]
# O = база × optimistic_factor, P = база × pessimistic_factor × риски × надбавки.
# Множители выведены из соотношения O/M/P в исходной методологии.
optimistic_factor = 0.7
pessimistic_factor = 1.5
# Буфер на риски: E + buffer_k × SD.
buffer_k = 2

[cross_check]
# Расхождение декомпозиции и Function Points больше этого порога означает
# ошибку в расчёте. Числа не публикуются — публикуется само расхождение.
max_divergence = 1.0

[grade]
# Нормировка труда по грейдам относительно middle.
middle = 1.0
senior = 0.75
senior_ai = 0.55

[day]
hours = 8

[story_points]
hours_per_point = 4
scale = [0.5, 1, 2, 3, 5, 8, 13, 20]
```

- [ ] **Step 4: Создать `docs/methodology/task-estimation.md`**

Документ обезличен: без названий компании и её продуктов, без фамилий, без ссылок на корпоративные системы, без номеров тикетов-примеров, без внутренней статистики и без раздела о бизнес-эффекте.

````markdown
# Методология оценки трудоёмкости задач

Единый набор правил, по которым оценивается трудоёмкость задачи. Цель —
чтобы две оценки одной задачи, сделанные в разное время, отличались из-за
изменившегося контекста, а не из-за настроения оценивающего.

Числовые значения в таблицах ниже дублируют `config/estimation-rules.toml`.
Источник правды для расчёта — TOML; синхронность проверяется тестом
`tests/test_estimation_rules_doc_sync.py`.

## Два режима оценки

**Атомарно, «в вакууме».** Оценивается только текст задачи, без внешнего
контекста. Минимальный вход — заголовок и два-три предложения описания.

**С обогащением контекста.** К описанию добавляются обсуждение и уже
подготовленные аналитические артефакты. Точность выше просто потому, что
входных данных больше.

Всё, чего нет во входных данных, учитывается надбавками на риск. Чем полнее
описание — тем точнее оценка и тем меньше надбавки.

## Уровни достаточности данных

| Уровень | Что означает |
|---------|--------------|
| `insufficient` | есть только заголовок или пара строк без существа |
| `minimal` | понятно, что делать, но не понятно, где границы |
| `sufficient` | описана суть, есть критерии приёмки или явные границы |
| `complete` | есть критерии приёмки, зависимости, контракты и класс данных |

Уровень определяет уверенность в оценке и напрямую влияет на надбавки.

## Классификация типа работы

Тип работы определяется до расчёта и задаёт коэффициент к объёму. Это
защита от завышения: копирование готового решения не должно оцениваться
как новая разработка.

| Тип работы | Ключ | Коэффициент | Признак |
|------------|------|-------------|---------|
| Копирование готового решения | `work_type.copy_existing` | 0.35 | «по аналогии с уже сделанным» |
| Документация, инструкция | `work_type.documentation` | 0.5 | «опиши», «составь гайдлайн» |
| Исследование, анализ | `work_type.research` | 0.6 | «изучи варианты», «сравни подходы» |
| Новая разработка | `work_type.new_development` | 1.0 | «создай сервис», «реализуй API» |
| Доработка существующего | `work_type.enhancement` | 0.9 | «добавь», «расширь» |
| Развёртывание, интеграция | `work_type.deployment` | 0.75 | «подключи», «разверни в контуре» |

Часы по единицам работы проставляются **как для новой разработки с нуля**.
Коэффициент накладывается один раз, на итог — иначе скидка удвоится.

## Декомпозиция снизу-вверх — основной метод

Задача разбивается на мелкие единицы работы: эндпоинт, правило валидации,
экран, раздел документа. Каждая единица оценивается в часах отдельно, со
своим обоснованием.

```
объём = каркас + Σ(единицы работы) + интеграция
тесты = объём × test_share.ratio
итог  = (объём + тесты) × коэффициент типа работы
```

| Параметр | Ключ | Значение |
|----------|------|----------|
| Доля тестов от объёма | `test_share.ratio` | 0.3 |

## Function Points — только cross-check

Function Points считаются независимо и служат исключительно контролем
основного метода, а не самостоятельной оценкой.

```
FP-оценка  = количество FP × часов на FP × коэффициент типа работы
расхождение = |декомпозиция − FP| / min(декомпозиция, FP)
```

| Параметр | Ключ | Значение |
|----------|------|----------|
| Порог расхождения | `cross_check.max_divergence` | 1.0 |

Если расхождение превышает порог, расчёт **останавливается**: ищется ошибка
в одном из методов, а не выводится среднее. Это защищает от грубых промахов,
где один метод завышает на порядок.

## Надбавки за недостающие данные

Применяются только к пессимистичному сценарию и только те, чей признак
отсутствует во входных данных.

| Чего нет | Ключ | Надбавка |
|----------|------|----------|
| Критериев приёмки | `missing_data_penalty.no_acceptance_criteria` | 0.2 |
| Перечня зависимостей | `missing_data_penalty.no_dependencies` | 0.15 |
| Согласованного контракта API | `missing_data_penalty.no_api_contract` | 0.3 |
| Указания класса данных | `missing_data_penalty.no_data_class` | 0.3 |

## Коэффициенты рисков

Применяются контекстно — только те риски, которые действительно относятся к
типу задачи. Нижняя граница уходит в реалистичный сценарий, верхняя — в
пессимистичный.

| Риск | Ключ минимума | Мин. | Ключ максимума | Макс. |
|------|---------------|------|----------------|-------|
| Персональные или регуляторные данные | `risk.personal_data.min` | 0.3 | `risk.personal_data.max` | 0.8 |
| Кросс-командная зависимость | `risk.cross_team.min` | 0.2 | `risk.cross_team.max` | 0.5 |
| Внешний API без документации | `risk.undocumented_external_api.min` | 0.4 | `risk.undocumented_external_api.max` | 0.6 |
| Контракт API не согласован | `risk.unagreed_api_contract.min` | 0.2 | `risk.unagreed_api_contract.max` | 0.3 |
| Не согласовано с информационной безопасностью | `risk.security_unreviewed.min` | 0.5 | `risk.security_unreviewed.max` | 1.0 |

## PERT

Три сценария и ожидание по классической формуле.

```
O = база × optimistic_factor
M = база × (1 + Σ минимумов применённых рисков)
P = база × pessimistic_factor × (1 + Σ максимумов рисков) × (1 + Σ надбавок)

E  = (O + 4×M + P) / 6
SD = (P − O) / 6
буфер = E + buffer_k × SD
```

| Параметр | Ключ | Значение |
|----------|------|----------|
| Оптимистичный множитель | `pert.optimistic_factor` | 0.7 |
| Пессимистичный множитель | `pert.pessimistic_factor` | 1.5 |
| Множитель буфера | `pert.buffer_k` | 2 |

## Коридоры реалистичности

Финальная проверка по типу артефакта. Выход за коридор не меняет оценку —
он поднимает флаг: скорее всего, тип задачи определён неверно или
декомпозиция родительской задачи неправильная.

| Тип артефакта | Ключ нижней границы | Мин., дн | Ключ верхней границы | Макс., дн | Если выше |
|---------------|---------------------|----------|----------------------|-----------|-----------|
| Багфикс | `sanity_bounds.bugfix.min_days` | 0.5 | `sanity_bounds.bugfix.max_days` | 3 | это уже не багфикс, а доработка |
| Валидация существующего | `sanity_bounds.validation.min_days` | 0.5 | `sanity_bounds.validation.max_days` | 5 | неверно посчитан объём данных |
| Подзадача | `sanity_bounds.subtask.min_days` | 0.5 | `sanity_bounds.subtask.max_days` | 5 | родительская задача разбита неправильно |
| Новый модуль с нуля | `sanity_bounds.new_module.min_days` | 1 | `sanity_bounds.new_module.max_days` | 15 | нужна декомпозиция |

## Нормировка по грейдам

Базовая оценка соответствует уровню middle.

| Грейд | Ключ | Коэффициент |
|-------|------|-------------|
| Middle | `grade.middle` | 1.0 |
| Senior | `grade.senior` | 0.75 |
| Senior с ИИ-ассистентом | `grade.senior_ai` | 0.55 |

## Story Points и рабочий день

| Параметр | Ключ | Значение |
|----------|------|----------|
| Часов в рабочем дне | `day.hours` | 8 |
| Идеальных часов в одном Story Point | `story_points.hours_per_point` | 4 |

Шкала Story Points — Фибоначчи: 0.5, 1, 2, 3, 5, 8, 13, 20. Оценка выше
верхнего значения шкалы выводится как «20+» и означает, что задачу пора
декомпозировать.

## Внутренние проверки перед выводом

- Соблюдается `O < M < P`.
- Все часы строго положительны, декомпозиция непуста.
- Function Points посчитаны — без них cross-check невозможен.
- Тип работы и тип артефакта принадлежат известным множествам.
- Произвольных множителей «для подгонки результата» не существует: такого
  входа нет ни в схеме извлечения фактов, ни в конфиге.

## Что на выходе

- Диапазон O / M / P и ожидание E.
- Уверенность: высокая, средняя или низкая — производная от уровня
  достаточности данных, понижается при повышенном расхождении методов.
- Story Points по шкале Фибоначчи.
- Расшифровка каждого применённого коэффициента, риска и надбавки.
- Список того, что стоит уточнить, чтобы сузить диапазон.

## Оценка эпика

*Вне текущей реализации, приведено для полноты методологии.*

Оценка эпика — сумма оценок вложенных задач плюс надбавка на координацию,
зависящая от количества задач и количества вовлечённых команд.

| Задач в эпике | Команд | Надбавка |
|---------------|--------|----------|
| 2–4 | одна | 15% |
| 5–8 | одна | 20% |
| 2–4 | несколько | 25% |
| 5 и более | несколько | 30% |

Дополнительно анализируется критический путь — самая длинная цепочка
зависимостей между вложенными задачами.

## Смежные методологии

Приведены для ориентации; в расчёте выше не используются.

- **RICE** — `(Reach × Impact × Confidence) / Effort`. Приоритизация, а не
  оценка трудоёмкости.
- **WSJF** — `Cost of delay / Job size`. Сначала делается то, что быстрее и
  дороже в простое.
- **ROI** — `(прибыль − затраты) / затраты × 100%`. Экономическое
  обоснование, а не планирование.
- **Story Points по Фибоначчи** — относительная оценка через объём,
  сложность и риски; используется здесь как форма представления итога.
````

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `.venv/bin/pytest tests/test_estimation_rules_doc_sync.py -q`
Expected: PASS, 2 passed.

- [ ] **Step 6: Коммит**

```bash
git add docs/methodology/task-estimation.md config/estimation-rules.toml tests/test_estimation_rules_doc_sync.py
git commit -m "feat(estimate): обезличенная методология оценки и её исполняемый конфиг"
```

---

## Task 2: Парсер команды `/estimate`

**Files:**
- Create: `shared/commands.py`
- Test: `tests/test_estimate_command_parse.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `shared.commands.parse_command(comment_body: str) -> str | None` и константа `ESTIMATE = "estimate"`. Используется вебхуком (Task 8) и фильтрацией треда в `collect_estimation_context` (Task 6).

Модуль лежит в `shared/`, потому что оба Dockerfile (`webhook/Dockerfile`, `worker/Dockerfile`) копируют `shared/` в образ, а `tests/conftest.py` уже добавляет корень репозитория в `sys.path`.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_estimate_command_parse.py`:

```python
from shared.commands import ESTIMATE, parse_command


def test_plain_command():
    assert parse_command("/estimate") == ESTIMATE


def test_case_insensitive():
    assert parse_command("/Estimate") == ESTIMATE


def test_leading_and_trailing_whitespace():
    assert parse_command("   /estimate  \n") == ESTIMATE


def test_leading_blank_lines_are_skipped():
    assert parse_command("\n\n/estimate") == ESTIMATE


def test_trailing_argument_is_ignored_in_v1():
    assert parse_command("/estimate заново") == ESTIMATE


def test_command_in_the_middle_of_text_is_not_a_command():
    assert parse_command("посмотри и потом /estimate") is None


def test_command_on_second_line_is_not_a_command():
    assert parse_command("контекст добавлен\n/estimate") is None


def test_quoted_command_is_not_a_command():
    assert parse_command("> /estimate\n\nуже запускал") is None


def test_similar_word_is_not_a_command():
    assert parse_command("/estimated") is None


def test_empty_body():
    assert parse_command("") is None


def test_unknown_command():
    assert parse_command("/deploy") is None
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_estimate_command_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.commands'`.

- [ ] **Step 3: Реализовать `shared/commands.py`**

```python
"""
Разбор slash-команд из комментариев Issue.

Живёт в shared/, потому что распознаёт команду вебхук, а тот же разбор нужен
воркеру — чтобы исключить сами команды из треда, который уходит в модель.
Оба Dockerfile копируют shared/ в образ.
"""

ESTIMATE = "estimate"

_COMMANDS = {"/estimate": ESTIMATE}


def parse_command(comment_body: str) -> str | None:
    """Имя команды, если комментарий — вызов команды, иначе None.

    Командой считается только комментарий, ПЕРВАЯ непустая строка которого
    начинается с самого вызова. Цитата (строка с '>') командой не считается:
    иначе ответ с процитированной командой запускал бы её повторно. Хвост
    после имени команды игнорируется — аргументов в этой версии нет.
    """
    for raw_line in comment_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            return None
        return _COMMANDS.get(line.split()[0].lower())
    return None
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `.venv/bin/pytest tests/test_estimate_command_parse.py -q`
Expected: PASS, 11 passed.

- [ ] **Step 5: Коммит**

```bash
git add shared/commands.py tests/test_estimate_command_parse.py
git commit -m "feat(estimate): разбор slash-команды /estimate из комментария"
```

---

## Task 3: Расчётное ядро

**Files:**
- Create: `worker/estimation.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_estimation_compute.py`

**Interfaces:**
- Consumes: структура `config/estimation-rules.toml` из Task 1.
- Produces:
  - `estimation.EstimationFacts` — Pydantic-модель, используется как `response_model` в Task 6.
  - `estimation.WorkUnit(name: str, hours: float, rationale: str)`.
  - `estimation.load_rules(path: Path = RULES_PATH) -> dict`.
  - `estimation.compute(facts: EstimationFacts, rules: dict) -> Estimate`.
  - `estimation.Estimate` — dataclass со всеми числами, списками `risks: list[AppliedRisk]`, `penalties: list[AppliedPenalty]`, `sanity_warnings: list[str]`.
  - `estimation.EstimationError` — исключение при непроходимых фактах.
  - Словари подписей `WORK_TYPE_RU`, `ARTIFACT_TYPE_RU`, `RISK_LABELS`, `PENALTY_LABELS`, `CONFIDENCE_RU` — используются рендером в Task 4.

- [ ] **Step 1: Добавить фикстуру `rules` в `tests/conftest.py`**

Дописать в конец файла:

```python
import pytest

RULES_PATH = ROOT / "config" / "estimation-rules.toml"


@pytest.fixture
def rules():
    """Правила расчёта из репозитория. В контейнере тот же файл лежит по
    /app/config — тесты берут его из исходников."""
    import estimation

    return estimation.load_rules(RULES_PATH)
```

- [ ] **Step 2: Написать падающий тест расчёта**

Создать `tests/test_estimation_compute.py`:

```python
import pytest

from estimation import (
    EstimationError,
    EstimationFacts,
    WorkUnit,
    compute,
)


def facts(**overrides) -> EstimationFacts:
    """Базовые факты: новая разработка, всё описано, рисков нет.

    Каркас 4 + единицы 6 + интеграция 2 = 12 ч; тесты 30% -> 15.6 ч;
    коэффициент 1.0 -> декомпозиция 15.6 ч.
    FP: 3 FP x 5 ч = 15 ч. Расхождение 4% — cross-check проходит.
    """
    base = dict(
        work_type="new_development",
        artifact_type="new_module",
        scaffolding_hours=4.0,
        work_units=[
            WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут"),
            WorkUnit(name="валидация", hours=2.0, rationale="два правила"),
        ],
        integration_hours=2.0,
        fp_count=3.0,
        fp_hours_per_point=5.0,
        data_sufficiency="complete",
        has_acceptance_criteria=True,
        has_dependencies_listed=True,
        has_api_contract=True,
        has_data_class=True,
        risks=[],
        open_questions=[],
        reasoning="",
    )
    base.update(overrides)
    return EstimationFacts(**base)


def test_decomposition_is_base_plus_tests_times_coefficient(rules):
    result = compute(facts(), rules)
    assert result.base_hours == pytest.approx(12.0)
    assert result.tests_hours == pytest.approx(3.6)
    assert result.decomposition_hours == pytest.approx(15.6)


def test_work_type_coefficient_discounts_copy_work(rules):
    result = compute(facts(work_type="copy_existing", artifact_type="subtask"), rules)
    assert result.work_type_coefficient == pytest.approx(0.35)
    assert result.decomposition_hours == pytest.approx(15.6 * 0.35)
    # Тот же коэффициент применяется и к cross-check, иначе методы
    # разошлись бы искусственно.
    assert result.fp_hours == pytest.approx(15.0 * 0.35)


def test_pert_arithmetic_without_risks(rules):
    result = compute(facts(), rules)
    day = rules["day"]["hours"]
    assert result.optimistic_days == pytest.approx(15.6 * 0.7 / day)
    assert result.realistic_days == pytest.approx(15.6 / day)
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 / day)
    expected = (15.6 * 0.7 + 4 * 15.6 + 15.6 * 1.5) / 6
    assert result.expected_days == pytest.approx(expected / day)


def test_buffer_is_expectation_plus_k_standard_deviations(rules):
    result = compute(facts(), rules)
    sd = (result.pessimistic_days - result.optimistic_days) / 6
    assert result.buffered_days == pytest.approx(result.expected_days + 2 * sd)


def test_invariant_optimistic_below_realistic_below_pessimistic(rules):
    result = compute(facts(), rules)
    assert result.optimistic_days < result.realistic_days < result.pessimistic_days


def test_risk_minimum_moves_realistic_maximum_moves_pessimistic(rules):
    result = compute(facts(risks=["personal_data"]), rules)
    assert result.realistic_days == pytest.approx(15.6 * 1.3 / rules["day"]["hours"])
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 * 1.8 / rules["day"]["hours"])
    assert [risk.key for risk in result.risks] == ["personal_data"]


def test_unknown_risk_from_the_model_is_ignored(rules):
    result = compute(facts(risks=["решил_что_рискованно"]), rules)
    assert result.risks == []
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 / rules["day"]["hours"])


def test_missing_acceptance_criteria_only_inflates_pessimistic(rules):
    result = compute(facts(has_acceptance_criteria=False), rules)
    assert result.realistic_days == pytest.approx(15.6 / rules["day"]["hours"])
    assert result.pessimistic_days == pytest.approx(15.6 * 1.5 * 1.2 / rules["day"]["hours"])
    assert [penalty.key for penalty in result.penalties] == ["no_acceptance_criteria"]


def test_all_four_penalties_accumulate(rules):
    result = compute(
        facts(
            has_acceptance_criteria=False,
            has_dependencies_listed=False,
            has_api_contract=False,
            has_data_class=False,
        ),
        rules,
    )
    assert len(result.penalties) == 4
    total = 1 + 0.2 + 0.15 + 0.3 + 0.3
    assert result.pessimistic_days == pytest.approx(
        15.6 * 1.5 * total / rules["day"]["hours"]
    )


def test_cross_check_stops_when_methods_diverge_beyond_threshold(rules):
    # 15.6 ч декомпозиции против 60 ч по FP — расхождение почти 3x.
    result = compute(facts(fp_count=12.0, fp_hours_per_point=5.0), rules)
    assert result.stopped is True
    assert result.divergence > rules["cross_check"]["max_divergence"]
    assert result.expected_days == 0.0
    assert result.story_points == "—"


def test_moderate_divergence_downgrades_confidence(rules):
    # 15.6 ч против 25 ч — расхождение 60%: порог не превышен, но больше половины.
    result = compute(facts(fp_count=5.0, fp_hours_per_point=5.0), rules)
    assert result.stopped is False
    assert result.confidence == "medium"


def test_confidence_follows_data_sufficiency(rules):
    assert compute(facts(data_sufficiency="complete"), rules).confidence == "high"
    assert compute(facts(data_sufficiency="minimal"), rules).confidence == "medium"
    assert compute(facts(data_sufficiency="insufficient"), rules).confidence == "low"


def test_sanity_warning_when_above_corridor(rules):
    big = [WorkUnit(name=f"модуль {i}", hours=20.0, rationale="крупный") for i in range(8)]
    result = compute(
        facts(work_units=big, fp_count=34.0, fp_hours_per_point=5.0),
        rules,
    )
    assert result.sanity_warnings
    assert "декомпозиция" in result.sanity_warnings[0]


def test_no_sanity_warning_inside_corridor(rules):
    assert compute(facts(), rules).sanity_warnings == []


def test_story_points_snap_to_fibonacci(rules):
    result = compute(facts(), rules)
    # E = (10.92 + 4x15.6 + 23.4)/6 = 16.12 ч -> 4.03 SP -> ближайшее по шкале 5
    assert result.story_points == "5"


def test_story_points_above_scale_get_plus(rules):
    huge = [WorkUnit(name=f"часть {i}", hours=40.0, rationale="крупная") for i in range(6)]
    result = compute(
        facts(work_units=huge, fp_count=50.0, fp_hours_per_point=5.5),
        rules,
    )
    assert result.story_points == "20+"


def test_grade_days_scale_the_realistic_scenario(rules):
    result = compute(facts(), rules)
    assert result.grade_days["middle"] == pytest.approx(result.realistic_days)
    assert result.grade_days["senior"] == pytest.approx(result.realistic_days * 0.75)
    assert result.grade_days["senior_ai"] == pytest.approx(result.realistic_days * 0.55)


def test_empty_decomposition_is_an_error(rules):
    with pytest.raises(EstimationError, match="декомпозиция пуста"):
        compute(facts(work_units=[]), rules)


def test_non_positive_unit_hours_are_an_error(rules):
    bad = [WorkUnit(name="ничего", hours=0.0, rationale="")]
    with pytest.raises(EstimationError, match="неположительными часами"):
        compute(facts(work_units=bad), rules)


def test_missing_function_points_are_an_error(rules):
    with pytest.raises(EstimationError, match="Function Points"):
        compute(facts(fp_count=0.0), rules)


def test_unknown_work_type_is_an_error(rules):
    with pytest.raises(EstimationError, match="тип работы"):
        compute(facts(work_type="магия"), rules)


def test_unknown_artifact_type_is_an_error(rules):
    with pytest.raises(EstimationError, match="тип артефакта"):
        compute(facts(artifact_type="нечто"), rules)
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_estimation_compute.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'estimation'`.

- [ ] **Step 4: Реализовать `worker/estimation.py`**

```python
"""
Детерминированный расчёт оценки задачи.

Чистый модуль: ни сети, ни LLM, ни Temporal. Модель отдаёт только факты
(EstimationFacts), а коэффициенты, надбавки, PERT, cross-check и коридоры
считаются здесь по config/estimation-rules.toml. Тот же принцип, что уже
работает в score_priority: модель извлекает, код считает — иначе одна и та
же задача давала бы разные числа от прогона к прогону.

Поля «итоговая оценка» в схеме фактов нет намеренно: модель структурно не
может вернуть готовое число в обход расчёта.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

RULES_PATH = Path("/app/config/estimation-rules.toml")

_CONFIDENCE_LADDER = ("low", "medium", "high")
_SUFFICIENCY_CONFIDENCE = {
    "complete": "high",
    "sufficient": "high",
    "minimal": "medium",
    "insufficient": "low",
}

WORK_TYPE_RU = {
    "copy_existing": "копирование готового решения",
    "documentation": "документация",
    "research": "исследование",
    "new_development": "новая разработка",
    "enhancement": "доработка существующего",
    "deployment": "развёртывание и интеграция",
}

ARTIFACT_TYPE_RU = {
    "bugfix": "багфикс",
    "validation": "валидация существующего",
    "subtask": "подзадача",
    "new_module": "новый модуль с нуля",
}

RISK_LABELS = {
    "personal_data": "персональные или регуляторные данные",
    "cross_team": "кросс-командная зависимость",
    "undocumented_external_api": "внешний API без документации",
    "unagreed_api_contract": "контракт API не согласован",
    "security_unreviewed": "не согласовано с информационной безопасностью",
}

PENALTY_LABELS = {
    "no_acceptance_criteria": "не заданы критерии приёмки",
    "no_dependencies": "не перечислены зависимости",
    "no_api_contract": "не согласован контракт API",
    "no_data_class": "не указан класс обрабатываемых данных",
}

CONFIDENCE_RU = {"high": "высокая", "medium": "средняя", "low": "низкая"}


class EstimationError(ValueError):
    """Факты не проходят внутренние проверки — расчёт невозможен."""


class WorkUnit(BaseModel):
    name: str = Field(description="Единица работы: эндпоинт, правило, экран, раздел")
    hours: float = Field(description="Часы как для новой разработки с нуля, без скидок за тип работы")
    rationale: str = Field(description="Почему именно столько")


class EstimationFacts(BaseModel):
    work_type: str = Field(description="copy_existing | documentation | research | new_development | enhancement | deployment")
    artifact_type: str = Field(description="bugfix | validation | subtask | new_module")
    scaffolding_hours: float = Field(description="Часы на каркас и базовую обвязку")
    work_units: list[WorkUnit] = Field(description="Декомпозиция снизу-вверх, минимум одна единица")
    integration_hours: float = Field(description="Часы на интеграцию и сборку воедино")
    fp_count: float = Field(description="Количество Function Points, независимый cross-check")
    fp_hours_per_point: float = Field(description="Часов на один Function Point")
    data_sufficiency: str = Field(description="insufficient | minimal | sufficient | complete")
    has_acceptance_criteria: bool
    has_dependencies_listed: bool
    has_api_contract: bool
    has_data_class: bool
    risks: list[str] = Field(default=[], description="Ключи рисков из известного множества")
    open_questions: list[str] = Field(default=[], description="Что уточнить, чтобы сузить диапазон")
    reasoning: str = Field(default="", description="Кратко: на чём построена декомпозиция")


@dataclass
class AppliedRisk:
    key: str
    label: str
    min_value: float
    max_value: float


@dataclass
class AppliedPenalty:
    key: str
    label: str
    value: float


@dataclass
class Estimate:
    stopped: bool
    divergence: float
    base_hours: float
    tests_hours: float
    work_type_coefficient: float
    decomposition_hours: float
    fp_hours: float
    optimistic_days: float
    realistic_days: float
    pessimistic_days: float
    expected_days: float
    buffered_days: float
    story_points: str
    confidence: str
    grade_days: dict[str, float]
    risks: list[AppliedRisk]
    penalties: list[AppliedPenalty]
    sanity_warnings: list[str]


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _validate(facts: EstimationFacts, rules: dict) -> None:
    if facts.work_type not in rules["work_type"]:
        raise EstimationError(f"неизвестный тип работы: {facts.work_type}")
    if facts.artifact_type not in rules["sanity_bounds"]:
        raise EstimationError(f"неизвестный тип артефакта: {facts.artifact_type}")
    if not facts.work_units:
        raise EstimationError("декомпозиция пуста — оценивать нечего")
    if any(unit.hours <= 0 for unit in facts.work_units):
        raise EstimationError("единица работы с неположительными часами")
    if facts.scaffolding_hours < 0 or facts.integration_hours < 0:
        raise EstimationError("отрицательные часы каркаса или интеграции")
    if facts.fp_count <= 0 or facts.fp_hours_per_point <= 0:
        raise EstimationError("Function Points не посчитаны — cross-check невозможен")


def _risks(facts: EstimationFacts, rules: dict) -> list[AppliedRisk]:
    applied = []
    for key in facts.risks:
        rule = rules["risk"].get(key)
        if rule is None:
            # Модель назвала риск, которого нет в конфиге. Молча игнорируем:
            # выдуманный коэффициент хуже отсутствующего.
            continue
        applied.append(AppliedRisk(key, RISK_LABELS.get(key, key), rule["min"], rule["max"]))
    return applied


def _penalties(facts: EstimationFacts, rules: dict) -> list[AppliedPenalty]:
    missing = {
        "no_acceptance_criteria": not facts.has_acceptance_criteria,
        "no_dependencies": not facts.has_dependencies_listed,
        "no_api_contract": not facts.has_api_contract,
        "no_data_class": not facts.has_data_class,
    }
    return [
        AppliedPenalty(key, PENALTY_LABELS[key], rules["missing_data_penalty"][key])
        for key, is_missing in missing.items()
        if is_missing
    ]


def _confidence(facts: EstimationFacts, divergence: float, max_divergence: float) -> str:
    level = _SUFFICIENCY_CONFIDENCE.get(facts.data_sufficiency, "low")
    if divergence > max_divergence / 2:
        # Методы разошлись заметно, хоть и в пределах допустимого — это само
        # по себе повод меньше доверять числу.
        level = _CONFIDENCE_LADDER[max(0, _CONFIDENCE_LADDER.index(level) - 1)]
    return level


def _story_points(expected_hours: float, rules: dict) -> str:
    scale = rules["story_points"]["scale"]
    points = expected_hours / rules["story_points"]["hours_per_point"]
    if points > max(scale):
        return f"{max(scale):g}+"
    return f"{min(scale, key=lambda value: abs(value - points)):g}"


def _sanity_warnings(expected_days: float, artifact_type: str, rules: dict) -> list[str]:
    bounds = rules["sanity_bounds"][artifact_type]
    if expected_days > bounds["max_days"]:
        return [bounds["over"]]
    if expected_days < bounds["min_days"]:
        return [bounds["under"]]
    return []


def compute(facts: EstimationFacts, rules: dict) -> Estimate:
    _validate(facts, rules)

    coefficient = rules["work_type"][facts.work_type]
    units_hours = sum(unit.hours for unit in facts.work_units)
    base = facts.scaffolding_hours + units_hours + facts.integration_hours
    tests = base * rules["test_share"]["ratio"]
    decomposition = (base + tests) * coefficient
    fp = facts.fp_count * facts.fp_hours_per_point * coefficient

    divergence = abs(decomposition - fp) / min(decomposition, fp)
    max_divergence = rules["cross_check"]["max_divergence"]

    risks = _risks(facts, rules)
    penalties = _penalties(facts, rules)
    confidence = _confidence(facts, divergence, max_divergence)

    if divergence > max_divergence:
        # Методология требует искать ошибку, а не усреднять. Числа наружу
        # не отдаём вовсе — иначе усреднение произойдёт в голове читающего.
        return Estimate(
            stopped=True,
            divergence=divergence,
            base_hours=base,
            tests_hours=tests,
            work_type_coefficient=coefficient,
            decomposition_hours=decomposition,
            fp_hours=fp,
            optimistic_days=0.0,
            realistic_days=0.0,
            pessimistic_days=0.0,
            expected_days=0.0,
            buffered_days=0.0,
            story_points="—",
            confidence=confidence,
            grade_days={},
            risks=risks,
            penalties=penalties,
            sanity_warnings=[],
        )

    pert = rules["pert"]
    hours_per_day = rules["day"]["hours"]

    optimistic = decomposition * pert["optimistic_factor"]
    realistic = decomposition * (1 + sum(risk.min_value for risk in risks))
    pessimistic = (
        decomposition
        * pert["pessimistic_factor"]
        * (1 + sum(risk.max_value for risk in risks))
        * (1 + sum(penalty.value for penalty in penalties))
    )

    if not optimistic < realistic < pessimistic:
        raise EstimationError(
            f"нарушен инвариант O < M < P: {optimistic:.1f} / {realistic:.1f} / {pessimistic:.1f}"
        )

    expected = (optimistic + 4 * realistic + pessimistic) / 6
    standard_deviation = (pessimistic - optimistic) / 6
    buffered = expected + pert["buffer_k"] * standard_deviation
    expected_days = expected / hours_per_day

    return Estimate(
        stopped=False,
        divergence=divergence,
        base_hours=base,
        tests_hours=tests,
        work_type_coefficient=coefficient,
        decomposition_hours=decomposition,
        fp_hours=fp,
        optimistic_days=optimistic / hours_per_day,
        realistic_days=realistic / hours_per_day,
        pessimistic_days=pessimistic / hours_per_day,
        expected_days=expected_days,
        buffered_days=buffered / hours_per_day,
        story_points=_story_points(expected, rules),
        confidence=confidence,
        grade_days={
            name: (realistic / hours_per_day) * factor
            for name, factor in rules["grade"].items()
        },
        risks=risks,
        penalties=penalties,
        sanity_warnings=_sanity_warnings(expected_days, facts.artifact_type, rules),
    )
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `.venv/bin/pytest tests/test_estimation_compute.py -q`
Expected: PASS, 21 passed.

Если `test_sanity_warning_when_above_corridor` или `test_story_points_above_scale_get_plus` падают из-за расхождения методов — подгони `fp_count` в тесте так, чтобы `fp_count × fp_hours_per_point` был близок к `(каркас + единицы + интеграция) × 1.3`; коэффициенты трогать нельзя.

- [ ] **Step 6: Коммит**

```bash
git add worker/estimation.py tests/test_estimation_compute.py tests/conftest.py
git commit -m "feat(estimate): детерминированное расчётное ядро оценки"
```

---

## Task 4: Рендер комментария с обоснованием

**Files:**
- Create: `worker/estimate_report.py`
- Modify: `shared/workflow_types.py`
- Test: `tests/test_estimate_report.py`

**Interfaces:**
- Consumes: `estimation.Estimate`, `estimation.EstimationFacts` (Task 3).
- Produces:
  - `estimate_report.render(estimate: Estimate, facts: EstimationFacts, context: EstimationContext) -> str`.
  - `shared.workflow_types.EstimateRequest(repo: str, issue_number: int, comment_id: int)`.
  - `shared.workflow_types.EstimationContext(title, body, labels, thread, branch, artifacts, truncated)`.
  - `shared.workflow_types.EstimateResult(markdown: str, stopped: bool)`.

- [ ] **Step 1: Дописать типы в `shared/workflow_types.py`**

Добавить в конец файла:

```python
@dataclass
class EstimateRequest:
    repo: str
    issue_number: int
    comment_id: int  # комментарий с командой: на него ставится реакция


@dataclass
class EstimationContext:
    title: str
    body: str
    labels: list[str]
    thread: list[str]
    branch: str | None  # research/issue-<n> или bug/issue-<n>, если есть
    artifacts: dict[str, str]  # путь в ветке -> содержимое
    truncated: bool  # часть контекста не влезла в лимиты


@dataclass
class EstimateResult:
    markdown: str
    stopped: bool  # cross-check развалился, итоговых чисел нет
```

- [ ] **Step 2: Написать падающий тест рендера**

Создать `tests/test_estimate_report.py`:

```python
import pytest

from estimate_report import render
from estimation import EstimationFacts, WorkUnit, compute
from shared.workflow_types import EstimationContext


def facts(**overrides) -> EstimationFacts:
    base = dict(
        work_type="new_development",
        artifact_type="new_module",
        scaffolding_hours=4.0,
        work_units=[WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут")],
        integration_hours=2.0,
        fp_count=2.0,
        fp_hours_per_point=5.5,
        data_sufficiency="complete",
        has_acceptance_criteria=True,
        has_dependencies_listed=True,
        has_api_contract=True,
        has_data_class=True,
        risks=[],
        open_questions=[],
        reasoning="разбито по маршрутам",
    )
    base.update(overrides)
    return EstimationFacts(**base)


def context(**overrides) -> EstimationContext:
    base = dict(
        title="Заголовок",
        body="Описание",
        labels=["advisor:feature-request"],
        thread=[],
        branch=None,
        artifacts={},
        truncated=False,
    )
    base.update(overrides)
    return EstimationContext(**base)


def test_headline_carries_days_story_points_and_confidence(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "## Оценка задачи" in text
    assert "Story Points" in text
    assert "высокая" in text


def test_both_methods_are_shown_with_divergence(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Декомпозиция" in text
    assert "Function Points" in text
    assert "Расхождение" in text


def test_every_work_unit_appears_with_its_rationale(rules):
    units = [
        WorkUnit(name="эндпоинт", hours=4.0, rationale="один маршрут"),
        WorkUnit(name="миграция", hours=3.0, rationale="одна таблица"),
    ]
    given = facts(work_units=units, fp_count=3.0, fp_hours_per_point=4.0)
    text = render(compute(given, rules), given, context())
    assert "эндпоинт" in text and "один маршрут" in text
    assert "миграция" in text and "одна таблица" in text


def test_applied_risk_is_spelled_out_with_its_coefficients(rules):
    given = facts(risks=["personal_data"])
    text = render(compute(given, rules), given, context())
    assert "персональные или регуляторные данные" in text
    assert "0.3" in text and "0.8" in text


def test_applied_penalty_is_spelled_out(rules):
    given = facts(has_acceptance_criteria=False)
    text = render(compute(given, rules), given, context())
    assert "не заданы критерии приёмки" in text
    assert "0.2" in text


def test_no_risks_and_no_penalties_says_so_explicitly(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Не применялись" in text


def test_all_three_grades_are_listed(rules):
    text = render(compute(facts(), rules), facts(), context())
    assert "Middle" in text and "Senior" in text and "Senior с ИИ" in text


def test_open_questions_are_listed(rules):
    given = facts(open_questions=["какой объём данных", "кто владелец API"])
    text = render(compute(given, rules), given, context())
    assert "какой объём данных" in text
    assert "кто владелец API" in text


def test_sources_line_mentions_thread_and_branch(rules):
    given_context = context(
        thread=["первый", "второй"],
        branch="research/issue-42",
        artifacts={"docs/bft/issue-42-blueprint.md": "текст"},
    )
    text = render(compute(facts(), rules), facts(), given_context)
    assert "2 комментария" in text
    assert "research/issue-42" in text
    assert "1 файл" in text


def test_sources_line_uses_singular_for_one_comment(rules):
    text = render(compute(facts(), rules), facts(), context(thread=["один"]))
    assert "1 комментарий" in text


def test_sources_line_uses_many_form_for_five_comments(rules):
    text = render(compute(facts(), rules), facts(), context(thread=["к"] * 5))
    assert "5 комментариев" in text


def test_truncation_is_disclosed(rules):
    text = render(compute(facts(), rules), facts(), context(truncated=True))
    assert "обрезан" in text


def test_stopped_estimate_publishes_no_numbers(rules):
    given = facts(fp_count=12.0, fp_hours_per_point=6.0)
    estimate = compute(given, rules)
    assert estimate.stopped is True
    text = render(estimate, given, context())
    assert "расчёт остановлен" in text.lower()
    assert "PERT" not in text
    assert "Story Points" not in text


def test_stopped_estimate_still_lists_open_questions(rules):
    given = facts(fp_count=12.0, fp_hours_per_point=6.0, open_questions=["уточни объём"])
    text = render(compute(given, rules), given, context())
    assert "уточни объём" in text
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_estimate_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'estimate_report'`.

- [ ] **Step 4: Реализовать `worker/estimate_report.py`**

```python
"""
Рендер комментария с оценкой.

Чистая функция: Estimate + факты + контекст -> markdown. Вынесено из
activities.py, потому что это единственная часть, которую придётся править
чаще всего (формулировки), и она не должна тянуть за собой ни Temporal,
ни GitHub, ни LLM.

Комментарий обязан показывать, ОТКУДА взялось число: разбор декомпозиции,
оба метода с расхождением, каждый применённый риск и каждая надбавка,
источники контекста. Число без этого — просто мнение.
"""

from estimation import (
    ARTIFACT_TYPE_RU,
    CONFIDENCE_RU,
    WORK_TYPE_RU,
    Estimate,
    EstimationFacts,
)
from shared.workflow_types import EstimationContext


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 100 in (11, 12, 13, 14):
        return many
    if count % 10 == 1:
        return one
    if count % 10 in (2, 3, 4):
        return few
    return many


def _number(value: float) -> str:
    """Число без хвостовых нулей: 1.5, 2, 0.8."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _days(value: float) -> str:
    return f"{_number(value)} дн"


def _sources_line(context: EstimationContext) -> str:
    parts = ["описание задачи"]
    if context.thread:
        count = len(context.thread)
        word = _plural(count, "комментарий", "комментария", "комментариев")
        parts.append(f"{count} {word} обсуждения")
    if context.branch:
        count = len(context.artifacts)
        word = _plural(count, "файл", "файла", "файлов")
        parts.append(f"ветка `{context.branch}` ({count} {word})")
    line = "Оценка построена на: " + ", ".join(parts) + "."
    if context.truncated:
        line += " Часть контекста обрезана по лимиту объёма."
    return line


def _factors_section(estimate: Estimate) -> list[str]:
    lines = ["### Риски и надбавки", ""]
    if not estimate.risks and not estimate.penalties:
        lines.append("Не применялись: контекстных рисков не выявлено, "
                     "во входных данных ничего не пропущено.")
        return lines
    for risk in estimate.risks:
        lines.append(
            f"- Риск «{risk.label}»: +{_number(risk.min_value)} к реалистичному, "
            f"+{_number(risk.max_value)} к пессимистичному сценарию."
        )
    for penalty in estimate.penalties:
        lines.append(
            f"- Надбавка «{penalty.label}»: +{_number(penalty.value)} "
            f"к пессимистичному сценарию."
        )
    return lines


def _questions_section(facts: EstimationFacts) -> list[str]:
    lines = ["### Что уточнить", ""]
    if not facts.open_questions:
        lines.append("Вопросов нет — входных данных достаточно.")
        return lines
    lines.append("Это сузит диапазон при повторном `/estimate`:")
    lines.append("")
    lines.extend(f"- {question}" for question in facts.open_questions)
    return lines


def _render_stopped(estimate: Estimate, facts: EstimationFacts,
                    context: EstimationContext) -> str:
    lines = [
        "## Оценка задачи: расчёт остановлен",
        "",
        f"Два метода разошлись на {estimate.divergence:.0%} — больше допустимого "
        f"порога. По методологии в этом случае ищется ошибка в расчёте, а не "
        f"выводится среднее, поэтому итоговых чисел здесь нет.",
        "",
        "| Метод | Часы |",
        "|-------|------|",
        f"| Декомпозиция | {_number(estimate.decomposition_hours)} |",
        f"| Function Points | {_number(estimate.fp_hours)} |",
        "",
        f"Тип работы определён как «{WORK_TYPE_RU.get(facts.work_type, facts.work_type)}», "
        f"коэффициент ×{_number(estimate.work_type_coefficient)}.",
        "",
    ]
    lines.extend(_questions_section(facts))
    lines.extend(["", "---", "", _sources_line(context)])
    return "\n".join(lines)


def render(estimate: Estimate, facts: EstimationFacts,
           context: EstimationContext) -> str:
    if estimate.stopped:
        return _render_stopped(estimate, facts, context)

    work_type = WORK_TYPE_RU.get(facts.work_type, facts.work_type)
    artifact_type = ARTIFACT_TYPE_RU.get(facts.artifact_type, facts.artifact_type)
    coefficient = _number(estimate.work_type_coefficient)

    lines = [
        "## Оценка задачи",
        "",
        f"**Итог:** {_days(estimate.realistic_days)} (реалистичный сценарий) · "
        f"**Story Points:** {estimate.story_points} · "
        f"**Уверенность:** {CONFIDENCE_RU.get(estimate.confidence, estimate.confidence)}",
        "",
        "### Два метода",
        "",
        "| Метод | Расчёт | Часы |",
        "|-------|--------|------|",
        f"| Декомпозиция | ({_number(estimate.base_hours)} + тесты "
        f"{_number(estimate.tests_hours)}) × {coefficient} | "
        f"{_number(estimate.decomposition_hours)} |",
        f"| Function Points (cross-check) | {_number(facts.fp_count)} FP × "
        f"{_number(facts.fp_hours_per_point)} ч × {coefficient} | "
        f"{_number(estimate.fp_hours)} |",
        "",
        f"Расхождение методов — {estimate.divergence:.0%}.",
        "",
        "### Декомпозиция",
        "",
        "| Единица работы | Часы | Почему столько |",
        "|----------------|------|----------------|",
        f"| Каркас | {_number(facts.scaffolding_hours)} | базовая обвязка |",
    ]
    for unit in facts.work_units:
        lines.append(f"| {unit.name} | {_number(unit.hours)} | {unit.rationale} |")
    lines.extend([
        f"| Интеграция | {_number(facts.integration_hours)} | сборка воедино |",
        f"| Тесты | {_number(estimate.tests_hours)} | доля от объёма работ |",
        "",
        f"Тип работы — {work_type}, коэффициент ×{coefficient}. "
        f"Тип артефакта — {artifact_type}.",
    ])
    if facts.reasoning:
        lines.extend(["", facts.reasoning])

    lines.extend([
        "",
        "### PERT",
        "",
        "| Сценарий | Дни |",
        "|----------|-----|",
        f"| Оптимистичный (O) | {_number(estimate.optimistic_days)} |",
        f"| Реалистичный (M) | {_number(estimate.realistic_days)} |",
        f"| Пессимистичный (P) | {_number(estimate.pessimistic_days)} |",
        f"| Ожидание E = (O + 4M + P) / 6 | {_number(estimate.expected_days)} |",
        f"| С буфером на риски | {_number(estimate.buffered_days)} |",
        "",
        "### По грейдам",
        "",
        "| Грейд | Дни |",
        "|-------|-----|",
        f"| Middle | {_number(estimate.grade_days.get('middle', 0.0))} |",
        f"| Senior | {_number(estimate.grade_days.get('senior', 0.0))} |",
        f"| Senior с ИИ-ассистентом | {_number(estimate.grade_days.get('senior_ai', 0.0))} |",
        "",
    ])

    lines.extend(_factors_section(estimate))
    lines.append("")

    lines.append("### Проверка коридоров")
    lines.append("")
    if estimate.sanity_warnings:
        lines.extend(f"- ⚠️ {warning}" for warning in estimate.sanity_warnings)
    else:
        lines.append(f"Оценка внутри коридора для типа «{artifact_type}».")
    lines.append("")

    lines.extend(_questions_section(facts))
    lines.extend(["", "---", "", _sources_line(context)])
    return "\n".join(lines)
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `.venv/bin/pytest tests/test_estimate_report.py -q`
Expected: PASS, 14 passed.

- [ ] **Step 6: Коммит**

```bash
git add worker/estimate_report.py shared/workflow_types.py tests/test_estimate_report.py
git commit -m "feat(estimate): рендер комментария с полным обоснованием оценки"
```

---

## Task 5: GitHub-клиент — реакции и чтение контекста

**Files:**
- Modify: `worker/github_client.py`
- Test: `tests/test_github_client_dryrun.py`

**Interfaces:**
- Consumes: существующие `_auth_headers()`, `_dry_run()`.
- Produces:
  - `github_client.add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None`
  - `github_client.get_issue(repo: str, issue_number: int) -> dict`
  - `github_client.list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]`
  - `github_client.get_file(repo: str, path: str, ref: str) -> str | None`

- [ ] **Step 1: Дописать падающие тесты в `tests/test_github_client_dryrun.py`**

Добавить в конец файла:

```python
def test_dry_run_reaction_makes_no_http_call(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    gc.add_reaction("o/r", 555, "eyes")


def test_non_dry_run_reaction_posts_to_the_comment(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    calls = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs.get("json")
        return Resp()

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.add_reaction("o/r", 555, "eyes")
    assert calls["url"].endswith("/repos/o/r/issues/comments/555/reactions")
    assert calls["json"] == {"content": "eyes"}


def test_reads_are_not_blocked_by_dry_run(monkeypatch):
    """DRY_RUN защищает от мутаций, а не от чтения: без чтения контекста
    прогон в DRY_RUN не показал бы, что именно система собралась сделать."""
    gc = _fresh(monkeypatch, dry=True)
    calls = {}

    class Resp:
        status_code = 200
        text = "содержимое"

        def raise_for_status(self):
            pass

        def json(self):
            return {"title": "t"}

    def fake_get(url, **kwargs):
        calls["url"] = url
        return Resp()

    monkeypatch.setattr(gc.requests, "get", fake_get)
    assert gc.get_issue("o/r", 7) == {"title": "t"}
    assert gc.get_file("o/r", "docs/x.md", "research/issue-7") == "содержимое"


def test_missing_file_returns_none(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)

    class Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("не должно вызываться на 404")

    monkeypatch.setattr(gc.requests, "get", lambda url, **kwargs: Resp())
    assert gc.get_file("o/r", "docs/missing.md", "research/issue-7") is None
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_github_client_dryrun.py -q`
Expected: FAIL — `AttributeError: module 'github_client' has no attribute 'add_reaction'`.

- [ ] **Step 3: Дописать функции в `worker/github_client.py`**

Добавить после `branch_exists`:

```python
def add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None:
    """Реакция на комментарий — подтверждение, что команда увидена, до того
    как начнётся долгий расчёт. GitHub отвечает 200 на уже поставленную
    реакцию, поэтому повторный вызов безвреден."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s on %s comment %s", content, repo, comment_id)
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"
    resp = requests.post(url, headers=_auth_headers(), json={"content": content}, timeout=30)
    resp.raise_for_status()


def get_issue(repo: str, issue_number: int) -> dict:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.get(
        url, headers=_auth_headers(), params={"per_page": min(limit, 100)}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()[:limit]


def get_file(repo: str, path: str, ref: str) -> str | None:
    """Содержимое файла из ветки. None — файла нет; для артефактов это
    штатная ситуация, а не ошибка."""
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers={**_auth_headers(), "Accept": "application/vnd.github.raw"},
        params={"ref": ref},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `.venv/bin/pytest tests/test_github_client_dryrun.py -q`
Expected: PASS, 6 passed.

- [ ] **Step 5: Коммит**

```bash
git add worker/github_client.py tests/test_github_client_dryrun.py
git commit -m "feat(estimate): реакции и чтение контекста в GitHub-клиенте"
```

---

## Task 6: Activities стадии оценки и промпт

**Files:**
- Create: `prompts/system_estimate_extract.md`
- Modify: `worker/activities.py`
- Test: `tests/test_estimate_activities.py`

**Interfaces:**
- Consumes: `shared.commands.parse_command`, `shared.workflow_types.{EstimateRequest, EstimationContext, EstimateResult}`, `estimation.{EstimationFacts, compute, load_rules}`, `estimate_report.render`, новые функции `github_client`.
- Produces (сигнатуры, на которые опирается Task 7):
  - `ack_estimate_command(req: EstimateRequest) -> None`
  - `collect_estimation_context(req: EstimateRequest) -> EstimationContext`
  - `extract_estimation_facts(context: EstimationContext) -> dict`
  - `compute_estimate(facts_payload: dict, context: EstimationContext) -> EstimateResult`
  - `post_estimate_comment(req: EstimateRequest, result: EstimateResult) -> None`
  - `post_estimate_error(req: EstimateRequest, stage: str) -> None`

Факты идут между activity как `dict` (`facts.model_dump()`), а не как Pydantic-объект: штатный JSON-конвертер Temporal умеет dataclass'ы и обычные типы, но не модели Pydantic. Схема при этом остаётся одна — `EstimationFacts`.

- [ ] **Step 1: Создать промпт `prompts/system_estimate_extract.md`**

```markdown
Ты оцениваешь трудоёмкость задачи разработки. Твоя работа — не выдать число,
а извлечь ФАКТЫ, по которым число посчитает детерминированный код.

Никаких итоговых оценок, коэффициентов, множителей и процентов в ответе быть
не должно — только перечисленные ниже поля.

## Часы

Часы по каждой единице работы проставляй так, как если бы это была НОВАЯ
разработка с нуля, силами разработчика уровня middle, без ИИ-ассистента.
Скидку за тип работы (копирование готового, документация, исследование)
накладывает код после тебя. Если ты применишь её сам, она применится дважды.

Один рабочий день — восемь часов.

## Тип работы (work_type)

- `copy_existing` — делается по аналогии с уже существующим решением
- `documentation` — описание, инструкция, гайдлайн
- `research` — изучение вариантов, сравнение подходов, без production-кода
- `new_development` — новый функционал с нуля
- `enhancement` — доработка или расширение существующего
- `deployment` — подключение, развёртывание, интеграция готовых компонентов

## Тип артефакта (artifact_type)

- `bugfix` — исправление дефекта
- `validation` — проверка или валидация существующих данных и структур
- `subtask` — подзадача внутри более крупной работы
- `new_module` — самостоятельный новый модуль или сервис

## Декомпозиция (work_units)

Разбей работу на мелкие единицы: отдельный эндпоинт, отдельное правило
валидации, отдельный экран, отдельный раздел документа. Для каждой — часы и
короткое обоснование, почему именно столько.

Отдельно укажи `scaffolding_hours` (каркас, обвязка, заготовки) и
`integration_hours` (сборка воедино, подключение к существующему).

Тесты в единицы работы НЕ включай — их долю добавит код.

## Function Points (fp_count, fp_hours_per_point)

Посчитай Function Points НЕЗАВИСИМО от декомпозиции: по числу входов,
выходов, запросов, внутренних и внешних наборов данных. Не подгоняй результат
под декомпозицию — расхождение двух методов и есть полезный сигнал, ради
которого этот блок существует. Если расхождение выйдет большим, код сам
остановит расчёт.

## Достаточность данных (data_sufficiency)

- `insufficient` — есть только заголовок или пара строк без существа
- `minimal` — понятно что делать, но не понятно где границы
- `sufficient` — описана суть, есть критерии приёмки или явные границы
- `complete` — есть критерии приёмки, зависимости, контракты и класс данных

## Флаги наличия

Четыре булевых поля отвечают на вопрос «есть ли это во входных данных»:

- `has_acceptance_criteria` — заданы критерии приёмки или условия готовности
- `has_dependencies_listed` — перечислены зависимости от других систем и команд
- `has_api_contract` — контракт взаимодействия зафиксирован и согласован
- `has_data_class` — указан класс обрабатываемых данных (в том числе есть ли
  персональные или регуляторно значимые)

Отвечай честно: `false` не наказывает автора задачи, а лишь расширяет
пессимистичный сценарий.

## Риски (risks)

Перечисляй ТОЛЬКО ключи из этого списка и только те, что действительно
относятся к задаче:

- `personal_data` — обрабатываются персональные или регуляторные данные
- `cross_team` — требуется работа или согласование другой команды
- `undocumented_external_api` — внешний API без документации
- `unagreed_api_contract` — контракт API ещё не согласован
- `security_unreviewed` — требуется не пройденное согласование с ИБ

Придуманные ключи будут отброшены.

## Открытые вопросы (open_questions)

Что нужно уточнить, чтобы диапазон сузился. Конкретные вопросы, а не
пожелания «описать подробнее».

## Обоснование (reasoning)

Два-три предложения: по какому принципу разбита работа.
```

- [ ] **Step 2: Написать падающий тест activity**

Создать `tests/test_estimate_activities.py`:

```python
"""Проверяется сборка контекста: что попадает в модель, а что отсекается,
и как срабатывают лимиты. Сетевые вызовы подменяются целиком."""

import pytest

import activities
from shared.workflow_types import EstimateRequest, EstimationContext


class FakeGitHub:
    def __init__(self, issue=None, comments=None, branches=(), files=None):
        self.issue = issue or {"title": "Заголовок", "body": "Описание", "labels": []}
        self.comments = comments or []
        self.branches = set(branches)
        self.files = files or {}
        self.reactions = []
        self.posted = []
        self.labels = []

    def get_issue(self, repo, number):
        return self.issue

    def list_comments(self, repo, number, limit=50):
        return self.comments[:limit]

    def branch_exists(self, repo, branch):
        return branch in self.branches

    def get_file(self, repo, path, ref):
        return self.files.get(path)

    def add_reaction(self, repo, comment_id, content="eyes"):
        self.reactions.append((comment_id, content))

    def post_comment(self, repo, number, body):
        self.posted.append(body)

    def add_label(self, repo, number, label):
        self.labels.append(label)


def comment(body, user_type="User"):
    return {"body": body, "user": {"type": user_type}}


@pytest.fixture
def fake(monkeypatch):
    stub = FakeGitHub()
    monkeypatch.setattr(activities, "github_client", stub)
    return stub


REQ = EstimateRequest(repo="o/r", issue_number=7, comment_id=555)


async def test_ack_puts_eyes_on_the_command_comment(fake):
    await activities.ack_estimate_command(REQ)
    assert fake.reactions == [(555, "eyes")]


async def test_context_carries_title_body_and_labels(fake):
    fake.issue = {"title": "Т", "body": "О", "labels": [{"name": "advisor:bug"}]}
    context = await activities.collect_estimation_context(REQ)
    assert context.title == "Т"
    assert context.body == "О"
    assert context.labels == ["advisor:bug"]


async def test_bot_comments_and_commands_are_excluded_from_the_thread(fake):
    fake.comments = [
        comment("живой контекст"),
        comment("прошлая оценка", user_type="Bot"),
        comment("/estimate"),
    ]
    context = await activities.collect_estimation_context(REQ)
    assert context.thread == ["живой контекст"]


async def test_thread_is_capped_by_character_budget(fake, monkeypatch):
    monkeypatch.setattr(activities, "MAX_THREAD_CHARS", 10)
    fake.comments = [comment("12345"), comment("67890"), comment("перебор")]
    context = await activities.collect_estimation_context(REQ)
    assert context.thread == ["12345", "67890"]
    assert context.truncated is True


async def test_research_branch_artifacts_are_pulled(fake):
    fake.branches = {"research/issue-7"}
    fake.files = {"docs/bft/issue-7-blueprint.md": "план"}
    context = await activities.collect_estimation_context(REQ)
    assert context.branch == "research/issue-7"
    assert context.artifacts == {"docs/bft/issue-7-blueprint.md": "план"}


async def test_bug_branch_is_used_when_there_is_no_research_branch(fake):
    fake.branches = {"bug/issue-7"}
    fake.files = {"docs/bugs/issue-7-diagnosis.md": "диагноз"}
    context = await activities.collect_estimation_context(REQ)
    assert context.branch == "bug/issue-7"
    assert "docs/bugs/issue-7-diagnosis.md" in context.artifacts


async def test_no_branch_means_no_artifacts_and_is_not_an_error(fake):
    context = await activities.collect_estimation_context(REQ)
    assert context.branch is None
    assert context.artifacts == {}


async def test_oversized_artifact_is_truncated(fake, monkeypatch):
    monkeypatch.setattr(activities, "MAX_ARTIFACT_CHARS", 5)
    fake.branches = {"research/issue-7"}
    fake.files = {"docs/bft/issue-7-blueprint.md": "1234567890"}
    context = await activities.collect_estimation_context(REQ)
    assert context.artifacts["docs/bft/issue-7-blueprint.md"] == "12345"
    assert context.truncated is True


def _context(**overrides) -> EstimationContext:
    base = dict(title="Т", body="О", labels=[], thread=[], branch=None,
                artifacts={}, truncated=False)
    base.update(overrides)
    return EstimationContext(**base)


FACTS_PAYLOAD = {
    "work_type": "new_development",
    "artifact_type": "new_module",
    "scaffolding_hours": 4.0,
    "work_units": [{"name": "эндпоинт", "hours": 4.0, "rationale": "маршрут"}],
    "integration_hours": 2.0,
    "fp_count": 2.0,
    "fp_hours_per_point": 5.5,
    "data_sufficiency": "complete",
    "has_acceptance_criteria": True,
    "has_dependencies_listed": True,
    "has_api_contract": True,
    "has_data_class": True,
    "risks": [],
    "open_questions": [],
    "reasoning": "по маршрутам",
}


async def test_compute_activity_returns_rendered_markdown(fake, monkeypatch, rules):
    monkeypatch.setattr(activities.estimation, "load_rules", lambda *a, **k: rules)
    result = await activities.compute_estimate(FACTS_PAYLOAD, _context())
    assert result.stopped is False
    assert "## Оценка задачи" in result.markdown


async def test_posting_adds_the_estimated_label(fake):
    from shared.workflow_types import EstimateResult

    await activities.post_estimate_comment(REQ, EstimateResult(markdown="текст", stopped=False))
    assert fake.posted == ["текст"]
    assert fake.labels == ["estimated"]


async def test_stopped_estimate_is_posted_without_the_label(fake):
    from shared.workflow_types import EstimateResult

    await activities.post_estimate_comment(REQ, EstimateResult(markdown="стоп", stopped=True))
    assert fake.posted == ["стоп"]
    assert fake.labels == []


async def test_error_reports_the_stage_and_reacts(fake):
    await activities.post_estimate_error(REQ, "сбор контекста")
    assert "сбор контекста" in fake.posted[0]
    assert fake.reactions == [(555, "confused")]
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_estimate_activities.py -q`
Expected: FAIL — `AttributeError: module 'activities' has no attribute 'ack_estimate_command'`.

- [ ] **Step 4: Дописать `worker/activities.py`**

Добавить к существующим импортам:

```python
import estimate_report
import estimation
from shared.commands import parse_command
from shared.workflow_types import (
    EstimateRequest,
    EstimateResult,
    EstimationContext,
)
```

Добавить в конец файла:

```python
# --- Оценка трудоёмкости по команде /estimate ---

# Лимиты контекста: без них длинный тред или большой blueprint съедают
# окно модели целиком и вытесняют само описание задачи.
MAX_THREAD_COMMENTS = 50
MAX_THREAD_CHARS = 20_000
MAX_ARTIFACT_CHARS = 20_000
MAX_ARTIFACTS_TOTAL_CHARS = 60_000

# Пути артефактов из модели данных (docs/ARCHITECTURE.md). Отсутствующий
# файл — штатная ситуация: research-пайплайн мог не дойти до этой стадии.
ARTIFACT_PATHS = (
    "docs/bft/issue-{n}-blueprint.md",
    "docs/bft/issue-{n}-debate.md",
    "docs/bft/issue-{n}-recommendations.md",
    "docs/research/issue-{n}-sa-spec.md",
    "docs/bugs/issue-{n}-diagnosis.md",
)


@activity.defn
async def ack_estimate_command(req: EstimateRequest) -> None:
    github_client.add_reaction(req.repo, req.comment_id, "eyes")


def _collect_thread(req: EstimateRequest) -> tuple[list[str], bool]:
    raw = github_client.list_comments(req.repo, req.issue_number, MAX_THREAD_COMMENTS)
    truncated = len(raw) >= MAX_THREAD_COMMENTS
    thread: list[str] = []
    used = 0
    for comment in raw:
        # Прошлые оценки постит сам сервис, значит они уже отсеяны как Bot —
        # иначе модель начала бы оценивать собственный предыдущий вывод.
        if comment.get("user", {}).get("type") == "Bot":
            continue
        body = (comment.get("body") or "").strip()
        if not body or parse_command(body):
            continue
        if used + len(body) > MAX_THREAD_CHARS:
            truncated = True
            break
        thread.append(body)
        used += len(body)
    return thread, truncated


def _collect_artifacts(req: EstimateRequest) -> tuple[str | None, dict[str, str], bool]:
    branch = None
    for prefix in ("research", "bug"):
        candidate = f"{prefix}/issue-{req.issue_number}"
        if github_client.branch_exists(req.repo, candidate):
            branch = candidate
            break
    if branch is None:
        return None, {}, False

    artifacts: dict[str, str] = {}
    truncated = False
    total = 0
    for template in ARTIFACT_PATHS:
        path = template.format(n=req.issue_number)
        content = github_client.get_file(req.repo, path, branch)
        if content is None:
            continue
        if len(content) > MAX_ARTIFACT_CHARS:
            content = content[:MAX_ARTIFACT_CHARS]
            truncated = True
        if total + len(content) > MAX_ARTIFACTS_TOTAL_CHARS:
            truncated = True
            break
        artifacts[path] = content
        total += len(content)
    return branch, artifacts, truncated


@activity.defn
async def collect_estimation_context(req: EstimateRequest) -> EstimationContext:
    issue = github_client.get_issue(req.repo, req.issue_number)
    thread, thread_truncated = _collect_thread(req)
    branch, artifacts, artifacts_truncated = _collect_artifacts(req)
    return EstimationContext(
        title=issue.get("title") or "",
        body=issue.get("body") or "",
        labels=[label["name"] for label in issue.get("labels", [])],
        thread=thread,
        branch=branch,
        artifacts=artifacts,
        truncated=thread_truncated or artifacts_truncated,
    )


@activity.defn
async def extract_estimation_facts(context: EstimationContext) -> dict:
    parts = [f"Заголовок: {context.title}", f"Описание:\n{context.body}"]
    if context.labels:
        parts.append("Лейблы: " + ", ".join(context.labels))
    if context.thread:
        parts.append("Обсуждение:\n" + "\n---\n".join(context.thread))
    for path, content in context.artifacts.items():
        parts.append(f"Артефакт {path}:\n{content}")

    facts = llm.extract(
        _load_prompt("system_estimate_extract.md"),
        "\n\n".join(parts),
        estimation.EstimationFacts,
        model=llm.MODEL_CLASSIFY,
    )
    # Между activity ездит dict: штатный JSON-конвертер Temporal знает
    # dataclass'ы, но не модели Pydantic. Схема при этом одна.
    return facts.model_dump()


@activity.defn
async def compute_estimate(facts_payload: dict, context: EstimationContext) -> EstimateResult:
    facts = estimation.EstimationFacts.model_validate(facts_payload)
    estimate = estimation.compute(facts, estimation.load_rules())
    return EstimateResult(
        markdown=estimate_report.render(estimate, facts, context),
        stopped=estimate.stopped,
    )


@activity.defn
async def post_estimate_comment(req: EstimateRequest, result: EstimateResult) -> None:
    github_client.post_comment(req.repo, req.issue_number, result.markdown)
    if not result.stopped:
        github_client.add_label(req.repo, req.issue_number, "estimated")


@activity.defn
async def post_estimate_error(req: EstimateRequest, stage: str) -> None:
    github_client.post_comment(
        req.repo,
        req.issue_number,
        f"⚠️ Оценка не удалась на стадии «{stage}». Повтори `/estimate` позже — "
        f"подробности прогона видны в Temporal UI.",
    )
    github_client.add_reaction(req.repo, req.comment_id, "confused")
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `.venv/bin/pytest tests/test_estimate_activities.py -q`
Expected: PASS, 13 passed.

- [ ] **Step 6: Коммит**

```bash
git add prompts/system_estimate_extract.md worker/activities.py tests/test_estimate_activities.py
git commit -m "feat(estimate): activity сбора контекста, извлечения фактов и публикации"
```

---

## Task 7: Workflow `IssueEstimation`

**Files:**
- Modify: `worker/workflows.py`
- Modify: `worker/worker.py`
- Test: `tests/test_workflow_estimation.py`

**Interfaces:**
- Consumes: шесть activity из Task 6.
- Produces: workflow, зарегистрированный под именем `IssueEstimation` на очереди `issue-lifecycle`, принимающий один аргумент `EstimateRequest`. Стартует его вебхук в Task 8.

- [ ] **Step 1: Написать падающий тест workflow**

Создать `tests/test_workflow_estimation.py`:

```python
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import EstimateRequest, EstimateResult, EstimationContext
from workflows import IssueEstimation

_state: dict = {}

REQ = EstimateRequest(repo="o/r", issue_number=7, comment_id=555)

CONTEXT = EstimationContext(
    title="Т", body="О", labels=[], thread=[], branch=None, artifacts={}, truncated=False
)


@activity.defn(name="ack_estimate_command")
async def stub_ack(req):
    _state["acked"] = req.comment_id


@activity.defn(name="collect_estimation_context")
async def stub_context(req):
    _state["collected"] = True
    return CONTEXT


@activity.defn(name="extract_estimation_facts")
async def stub_facts(context):
    return {"work_type": "new_development"}


@activity.defn(name="compute_estimate")
async def stub_compute(facts, context):
    _state["computed_from"] = facts
    return EstimateResult(markdown="## Оценка задачи", stopped=False)


@activity.defn(name="post_estimate_comment")
async def stub_post(req, result):
    _state["posted"] = result.markdown


@activity.defn(name="post_estimate_error")
async def stub_error(req, stage):
    _state["error_stage"] = stage


@activity.defn(name="collect_estimation_context")
async def stub_context_boom(req):
    raise RuntimeError("GitHub недоступен")


ALL_STUBS = [stub_ack, stub_context, stub_facts, stub_compute, stub_post, stub_error]


async def _run(activities_list):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="tq",
            workflows=[IssueEstimation],
            activities=activities_list,
        ):
            await env.client.execute_workflow(
                IssueEstimation.run, REQ, id=f"wf-{uuid.uuid4()}", task_queue="tq"
            )


@pytest.mark.timeout(60)
async def test_happy_path_acks_then_posts():
    _state.clear()
    await _run(ALL_STUBS)
    assert _state["acked"] == 555
    assert _state["collected"] is True
    assert _state["computed_from"] == {"work_type": "new_development"}
    assert _state["posted"] == "## Оценка задачи"
    assert "error_stage" not in _state


@pytest.mark.timeout(60)
async def test_failure_reports_the_stage_it_broke_on():
    _state.clear()
    await _run([stub_ack, stub_context_boom, stub_facts, stub_compute, stub_post, stub_error])
    assert _state["error_stage"] == "сбор контекста"
    assert "posted" not in _state
```

Замечание: `stub_context_boom` регистрируется под тем же именем `collect_estimation_context`, поэтому в один `Worker` их нельзя передавать одновременно — второй набор передаётся отдельным списком, как в тесте выше.

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_workflow_estimation.py -q`
Expected: FAIL — `ImportError: cannot import name 'IssueEstimation' from 'workflows'`.

- [ ] **Step 3: Дописать `worker/workflows.py`**

Заменить блок импортов:

```python
with workflow.unsafe.imports_passed_through():
    from shared.workflow_types import EstimateRequest, EstimateResult, IssueInput

    import activities
```

Добавить в конец файла:

```python
@workflow.defn(name="IssueEstimation")
class IssueEstimation:
    """Оценка трудоёмкости по команде /estimate.

    Отдельный workflow, а не сигнал в IssueLifecycle: тот завершается после
    приоритизации (а на спаме и дубликате — раньше), и через неделю сигналить
    было бы некуда. ID включает comment_id, поэтому повторная доставка того же
    вебхука не запускает вторую оценку, а новая команда — это честно новый
    прогон со своей историей в Temporal UI.
    """

    @workflow.run
    async def run(self, req: EstimateRequest) -> None:
        default_retry = RetryPolicy(maximum_attempts=3)
        # Стадия нужна, чтобы человек в комментарии увидел, ЧТО именно
        # сломалось, а не абстрактное «ошибка обработки».
        stage = "подтверждение команды"
        try:
            await workflow.execute_activity(
                activities.ack_estimate_command,
                req,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )

            stage = "сбор контекста"
            context = await workflow.execute_activity(
                activities.collect_estimation_context,
                req,
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=default_retry,
            )

            stage = "извлечение фактов"
            facts = await workflow.execute_activity(
                activities.extract_estimation_facts,
                context,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )

            stage = "расчёт"
            result: EstimateResult = await workflow.execute_activity(
                activities.compute_estimate,
                args=[facts, context],
                start_to_close_timeout=timedelta(seconds=30),
                # Расчёт детерминирован и не ходит в сеть: повтор дал бы
                # ровно тот же результат, ретрай тут бессмыслен.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

            stage = "публикация"
            await workflow.execute_activity(
                activities.post_estimate_comment,
                args=[req, result],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )
        except Exception:
            await workflow.execute_activity(
                activities.post_estimate_error,
                args=[req, stage],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `.venv/bin/pytest tests/test_workflow_estimation.py -q`
Expected: PASS, 2 passed.

- [ ] **Step 5: Зарегистрировать workflow и activity в `worker/worker.py`**

Заменить импорт:

```python
from workflows import IssueEstimation, IssueLifecycle
```

В конструкторе `Worker` заменить `workflows=[IssueLifecycle]` на:

```python
        workflows=[IssueLifecycle, IssueEstimation],
```

И дописать в конец списка `activities`:

```python
            activities.ack_estimate_command,
            activities.collect_estimation_context,
            activities.extract_estimation_facts,
            activities.compute_estimate,
            activities.post_estimate_comment,
            activities.post_estimate_error,
```

- [ ] **Step 6: Проверить, что воркер импортируется без ошибок**

Run: `.venv/bin/python -c "import sys; sys.path[:0]=['worker','.']; import worker; print('OK')"`
Expected: `OK`. `main()` под `if __name__ == "__main__"`, поэтому подключение к Temporal при импорте не происходит и `TEMPORAL_ADDRESS` не нужен. `ImportError` или `AttributeError` означают ошибку в регистрации.

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `.venv/bin/pytest -q`
Expected: PASS, все тесты зелёные.

- [ ] **Step 8: Коммит**

```bash
git add worker/workflows.py worker/worker.py tests/test_workflow_estimation.py
git commit -m "feat(estimate): workflow IssueEstimation и его регистрация в воркере"
```

---

## Task 8: Вебхук — распознавание команды и старт оценки

**Files:**
- Modify: `webhook/main.py`

**Interfaces:**
- Consumes: `shared.commands.{ESTIMATE, parse_command}`, `shared.workflow_types.EstimateRequest`, workflow `IssueEstimation` из Task 7.
- Produces: старт workflow с ID `estimate-{repo}-{issue}-{comment_id}` на очереди `issue-lifecycle`.

Автотестов у вебхука нет — `fastapi` не входит в тестовое окружение (`scripts/setup.sh` ставит только `worker/requirements.txt` и `requirements-dev.txt`). Поэтому вся логика решения вынесена в `shared/commands.py` и покрыта в Task 2, а здесь остаётся транспортная склейка, проверяемая вручную по чеклисту в конце задачи.

- [ ] **Step 1: Дописать импорты в `webhook/main.py`**

Заменить блок импортов на:

```python
import hashlib
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared.commands import ESTIMATE, parse_command
```

- [ ] **Step 2: Добавить генератор ID оценки**

Рядом с `workflow_id_for` добавить:

```python
def estimate_workflow_id_for(repo_full_name: str, issue_number: int, comment_id: int) -> str:
    """comment_id в ID даёт две вещи сразу: повторная доставка одного и того
    же вебхука не запускает вторую оценку, а новая команда — это честно
    новый прогон, а не сигнал в старый."""
    return f"estimate-{repo_full_name}-{issue_number}-{comment_id}"
```

- [ ] **Step 3: Развести команду и обычный комментарий**

В обработчике `issue_comment` заменить всё после guard'а на бота:

```python
        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]

        if parse_command(payload["comment"].get("body") or "") == ESTIMATE:
            from shared.workflow_types import EstimateRequest

            comment_id = payload["comment"]["id"]
            try:
                await client.start_workflow(
                    "IssueEstimation",
                    EstimateRequest(
                        repo=repo, issue_number=issue_number, comment_id=comment_id
                    ),
                    id=estimate_workflow_id_for(repo, issue_number, comment_id),
                    task_queue="issue-lifecycle",
                )
            except WorkflowAlreadyStartedError:
                # Тот же вебхук доставлен повторно — оценка уже идёт.
                pass
            # Команда — не ответ на уточняющий вопрос intake gate, поэтому
            # сигнал user_comment по ней не шлётся.
            return {"ok": True}

        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", payload["comment"]["body"])
        except Exception:
            # Workflow мог уже завершиться (issue закрыт) — комментарий
            # после этого просто не на что сигналить, это не ошибка.
            pass
```

- [ ] **Step 4: Обновить docstring модуля**

В шапке `webhook/main.py` в перечислении событий заменить строку про `issue_comment.created` на две:

```
- issue_comment.created    -> сигнал уже идущему workflow (текст комментария —
                              используется циклом уточнений, если issue
                              в состоянии ожидания ответа)
- issue_comment с /estimate -> старт отдельного workflow IssueEstimation
                              (ID включает id комментария: повторная доставка
                              вебхука не запускает вторую оценку)
```

- [ ] **Step 5: Проверить синтаксис**

Run: `.venv/bin/python -m py_compile webhook/main.py && echo OK`
Expected: `OK`.

- [ ] **Step 6: Прогнать весь набор тестов**

Run: `.venv/bin/pytest -q`
Expected: PASS, все тесты зелёные.

- [ ] **Step 7: Коммит**

```bash
git add webhook/main.py
git commit -m "feat(estimate): вебхук распознаёт /estimate и стартует оценку"
```

---

## Task 9: Документация

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: описание команды для оператора.

- [ ] **Step 1: Добавить раздел в `README.md`**

Вставить перед разделом «## Что перенесено 1:1, что требует доработки»:

```markdown
## Оценка трудоёмкости — команда `/estimate`

Комментарий `/estimate` в любом Issue запускает оценку. Агент ставит 👀 на
комментарий, собирает контекст (описание, обсуждение, артефакты ветки
`research/issue-<n>` или `bug/issue-<n>`, если она есть) и публикует оценку
с обоснованием: декомпозиция по единицам работы, Function Points как
cross-check, PERT, разбивка по грейдам, каждый применённый риск и каждая
надбавка отдельной строкой.

Повторный `/estimate` — новая оценка с учётом контекста, появившегося с
прошлого раза. Прошлые прогоны остаются в Temporal UI.

Методология — `docs/methodology/task-estimation.md`. Все коэффициенты
вынесены в `config/estimation-rules.toml`: меняя их, не трогаешь ни промпт,
ни код расчёта. Модель извлекает только факты, все числа считает Python.

Требует Layer B (вебхук + GitHub App): команда приходит событием
`issue_comment.created`.
```

- [ ] **Step 2: Добавить раздел в `docs/ARCHITECTURE.md`**

Вставить перед разделом «## Модель данных (артефакты в git-ветках)»:

```markdown
## Второй workflow: `IssueEstimation`

Оценка трудоёмкости живёт в отдельном workflow, а не в `IssueLifecycle`.
Причина: `IssueLifecycle` завершается после приоритизации (а на спаме,
дубликате и консультации — раньше), поэтому команда `/estimate`, поданная
через неделю, не имела бы адресата для сигнала.

Workflow ID = `estimate-<repo>-<n>-<comment_id>`. Включение id комментария
даёт идемпотентность при повторной доставке вебхука и делает переоценку
обычным новым прогоном — без сигналов, очередей и вечноживущих workflow.

Стадии: реакция 👀 → сбор контекста (Issue, тред, артефакты ветки) →
извлечение фактов моделью → детерминированный расчёт → публикация.
Расчёт вынесен в `worker/estimation.py` (чистый модуль без сети и Temporal),
рендер — в `worker/estimate_report.py`. Числовые параметры —
`config/estimation-rules.toml`, тот же приём, что и с
`config/priority-weights.toml`.

Обе очереди задач общие (`issue-lifecycle`) — отдельный воркер не нужен.
```

- [ ] **Step 3: Финальный прогон тестов**

Run: `.venv/bin/pytest -q`
Expected: PASS, все тесты зелёные.

- [ ] **Step 4: Коммит**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs(estimate): описание команды /estimate в README и архитектуре"
```

---

## Ручная проверка сценария демонстрации

Выполняется после Task 9, при поднятом Layer B (вебхук + GitHub App) и
`DRY_RUN=1` на первом прогоне.

1. `docker compose up --build -d` — поднять все пять сервисов.
2. В тестовом Issue написать комментарий `/estimate`.
3. Убедиться, что в течение нескольких секунд на комментарии появилась 👀
   (при `DRY_RUN=1` — строка `[DRY_RUN] reaction eyes` в `make logs`).
4. В Temporal UI (`localhost:8080`) найти workflow
   `estimate-<repo>-<n>-<comment_id>` и пройти по стадиям.
5. Убедиться, что опубликован комментарий с оценкой (при `DRY_RUN=1` — его
   текст в логах), и что в нём присутствуют: итог с Story Points и
   уверенностью, таблица двух методов с расхождением, разбор декомпозиции,
   PERT, грейды, расшифровка рисков и надбавок, строка источников контекста.
6. Дописать в Issue критерии приёмки, снова вызвать `/estimate` — убедиться,
   что появился второй workflow с другим ID, а в новой оценке пропала
   надбавка «не заданы критерии приёмки».
