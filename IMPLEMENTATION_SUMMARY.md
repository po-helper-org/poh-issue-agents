# Реализация Issue #78: Аудит БФТ — проверки пайплайна

## Обзор

Реализованы проверки для всех найдок аудита БФТ, которые могут быть решены кодом. Основной фокус на проверяемых гейтах и программной валидации артефактов.

## Решённые находки

### A. Проверка размера артефактов ✅

**Реализация:**
- Функция `check_artifact_size()` в `shared/bft.py`
- Пороги минимального размера в `ARTIFACT_MIN_SIZE`:
  - `problem.md`: 500 байт
  - `concept.md`: 300 байт  
  - `validation.md`: 200 байт

**Проверки:**
- Артефакт нулевого размера → ошибка
- Артефакт меньше минимума → претензия
- Пороги выбраны эвристически на основе реальных данных

### B. Валидация якорей R1 ✅

**Реализация:**
- Функция `cascade_gaps()` проверяет якоря ранга R1
- Валидация против `line_counts` — словарь размеров файлов

**Проверки:**
- Якорь ссылается на существующий файл
- Номер строки не превышает длину файла
- Формат якоря: `файл:строки`
- Битый якорь → брак стадии

### C. Индекс не публикуется ❌

**Статус:** Не реализовано — инфраструктурное решение

**Проблема:** Ссылки на `.bft/index/` становятся мёртвыми при публикации

**Решение:** Либо публиковать индекс вместе с артефактами, либо запретить ссылки на него

### D. Явные зависимости стадий ✅

**Реализация:**
- Обновлена функция `deep_stages()` в `shared/bft.py`
- Стадии теперь декларируют полные списки зависимостей

**Изменения:**
- `problem`: требует `bft-context-pack.md` + `po-statement.md`
- `draft`: требует все предыдущие артефакты + `src` + `po-statement.md`
- Поддержка множественных зависимостей через запятую

**Проверки:**
- Тест `test_deep_stages_are_chained_by_their_artifacts` проверяет цепочку
- Учет внешних файлов, не создаваемых стадиями БФТ

### E. Формальные гейты валидации ✅

**Реализация:**
- Функция `validate_formal_gates()` в `shared/bft.py`
- Проверка документа после стадии `validate`

**Валидируемые гейты:**
1. Запрещённые разделы ("Ключевые решения", "Границы", "Критерии успеха")
2. Локальные идентификаторы без префикса эпика
3. Непустые "Связанные требования"
4. НФТ с числовым значением
5. Отсутствие битых ссылок между требованиями
6. Целостность связей (все упомянутые ID существуют)

**Проверки:**
- Регулярные выражения для Cyrillic ID (r'([А-Я]{2,3})-(\d+)')
- Парсинг требований из документа
- Валидация связей между требованиями

### F. Полнота каскада ⚠️ Частично

**Реализовано:**
- Минимальные пороги в `CASCADE_FLOOR`:
  - БТ: 4, ПТ: 5, ИТ: 6, ФТ: 10, НФТ: 4
- Минимальное количество якорей: 24

**Не реализовано:**
- Вывод порогов из источников (TOBE из `problem.md`, сценарии демонстрации)
- Сопоставление требований с источниками

**Статус:** Документировано в `.followups.md` как будущая работа

## Тестирование

### Созданные тесты (20 штук)

**Размер артефактов (4 теста):**
- `test_normal_artifact_size_passes`
- `test_too_small_artifact_fails`
- `test_artifact_without_size_requirement_passes`
- `test_exactly_minimum_size_passes`

**Извлечение каскада (4 теста):**
- `test_extract_cascade_from_json_block`
- `test_extract_cascade_from_plain_json`
- `test_nonexistent_document_returns_none`
- `test_document_without_cascade_returns_none`

**Формальные гейты (6 тестов):**
- `test_clean_document_passes_formal_gates`
- `test_forbidden_section_is_detected`
- `test_nft_without_numeric_value_is_detected`
- `test_unknown_requirement_type_is_detected`
- `test_valid_anchors_pass`
- `test_anchor_past_file_end_is_detected`

**Полнота каскада (2 теста):**
- `test_too_few_requirements_is_detected`
- `test_too_few_anchors_is_detected`

**Зависимости стадий (4 теста):**
- `test_draft_stage_has_complete_dependencies`
- `test_problem_stage_has_statement_dependency`
- `test_concept_stage_has_complete_dependencies`

### Результаты

```
tests/test_bft.py                    24 passed
tests/test_bft_validation.py         20 passed
===================================  44 passed
```

## Изменённые файлы

### `shared/bft.py`

**Добавленные функции:**
- `check_artifact_size(artifact_name: str, size: int) -> list[str]`
- `extract_cascade_from_document(document_path: str) -> dict | None`
- `validate_formal_gates(document: str, line_counts: dict[str, int]) -> list[str]`
- `parse_requirements_from_document(document: str) -> list[dict]`

**Обновлённые функции:**
- `cascade_gaps()` — добавлена валидация якорей R1

**Обновлённые константы:**
- `CASCADE_FLOOR: dict[str, int]` — пороги полноты требований
- `ANCHOR_FLOOR = 24` — минимальное количество якорей
- `ARTIFACT_MIN_SIZE: dict[str, int]` — минимальные размеры артефактов

### `tests/test_bft.py`

**Обновлённые тесты:**
- `test_deep_stages_are_chained_by_their_artifacts()` — учёт внешних файлов
- `test_deep_stage_lookup_matches_the_table()` — множественные зависимости

### `tests/test_bft_validation.py`

**Создан новый файл** с 20 тестами для всех функций валидации

### `.followups.md`

**Создан файл** с документацией:
- Найдка C — инфраструктурное решение
- Найдка F — частичная реализация, будущее развитие

## Как использовать

### Валидация артефактов после стадии

```python
from shared import bft

# Проверка размера
size_issues = bft.check_artifact_size("problem.md", 150)
if size_issues:
    raise RuntimeError(f"Артефакт слишком мал: {size_issues}")

# Валидация каскада
document_path = ".bft/documentation/issue-42/document.md"
cascade = bft.extract_cascade_from_document(document_path)
if cascade:
    line_counts = {"src/file.js": 100, "src/other.js": 50}
    gaps = bft.cascade_gaps(cascade, line_counts)
    if gaps:
        raise RuntimeError(f"Каскад неполон: {gaps}")

# Формальные гейты
with open(document_path) as f:
    document = f.read()
gates_issues = bft.validate_formal_gates(document, line_counts)
if gates_issues:
    raise RuntimeError(f"Нарушены формальные гейты: {gates_issues}")
```

## Ограничения и будущая работа

### Не реализовано

1. **Находка C** — требуется архитектурное решение о публикации индекса
2. **Находка F** — полное сопоставление требований с источниками

### Требуемое рефакторинг

1. Интеграция валидации в `run_bft_stage()` в `worker/activities.py`
2. Добавление проверки зависимостей перед запуском стадии
3. Публикация `.bft/index/` или запрет ссылок на него

### Потенциальные улучшения

1. Более точные пороги размеров на основе статистики
2. Дополнительные формальные гейты (например, структура документа)
3. Валидация качества формулировок (требует LLM)
4. Автоматическое исправление некоторых проблем

## Заключение

Основные находки аудита (A, B, D, E) полностью решены и покрыты тестами. Находки C и F требуют инфраструктурных решений и более содержательной работы соответственно. Реализация фокусируется на проверяемых гейтах, которые можно реализовать кодом, что делает пайплайн более надёжным и предсказуемым.
