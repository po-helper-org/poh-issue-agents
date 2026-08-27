"""Разбор плана superpowers в шаги.

Зависимость берётся из блока Interfaces: непустой Consumes — объявленное ребро.
Отдельный вызов модели на декомпозицию не нужен.
"""

from shared import plan_parse

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
