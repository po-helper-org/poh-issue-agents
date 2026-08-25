"""Проводка воркера: активность, которую зовёт воркфлоу, обязана быть
зарегистрирована в worker.py.

Расхождение здесь не ловится ни ревью, ни типами, а падает в рантайме — и не
на старте, а в середине прогона, когда очередь дойдёт до забытой активности.
Для `/analyze` это значит: после клона и repomix, потратив деньги и время.
Дважды за один заход это уже случалось (`finish_command_labels`, затем
`prepare_workspace` в ветке research-me) — оба раза случайно поймали тесты
воркфлоу, поднимающие настоящего воркера.

Проверка статическая: разбор AST, без Temporal и без импорта worker.py (тот на
импорте конфигурирует логирование и Sentry).
"""

import ast
from pathlib import Path

import pytest
from temporalio import activity

import activities as activities_module
import consolidation_activities
import delivery_bridge

WORKER_DIR = Path(__file__).resolve().parent.parent / "worker"


def _is_activity(module, name: str) -> bool:
    """Отсекает обращения к константам модуля (`activities.FNR_STAGE_NAMES`)
    от обращений к самим активностям."""
    fn = getattr(module, name, None)
    return fn is not None and getattr(fn, "__temporal_activity_definition", None) is not None


def _referenced(module_file: str, alias: str, module) -> set[str]:
    """Имена активностей, к которым обращается модуль через `<alias>.<имя>`."""
    tree = ast.parse((WORKER_DIR / module_file).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == alias
                and _is_activity(module, node.attr)):
            found.add(node.attr)
    return found


def _registered() -> set[str]:
    """Имена из списка `activities=[...]` в вызове Worker(...) внутри worker.py."""
    tree = ast.parse((WORKER_DIR / "worker.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "activities" or not isinstance(kw.value, ast.List):
                continue
            return {
                item.attr for item in kw.value.elts
                if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)
            }
    raise AssertionError("в worker.py не найден вызов Worker(activities=[...])")


def test_every_activity_used_by_workflows_is_registered():
    used = _referenced("workflows.py", "activities", activities_module)
    missing = used - _registered()
    assert not missing, (
        "воркфлоу зовут активности, не зарегистрированные в worker.py: "
        f"{sorted(missing)} — прогон упадёт в рантайме на первом же вызове"
    )


def test_every_consolidation_activity_is_registered():
    used = _referenced("consolidation_workflow.py", "ca", consolidation_activities)
    missing = used - _registered()
    assert not missing, f"не зарегистрированы: {sorted(missing)}"


def test_registration_list_has_no_duplicates():
    tree = ast.parse((WORKER_DIR / "worker.py").read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "activities" and isinstance(kw.value, ast.List):
                    names = [i.attr for i in kw.value.elts if isinstance(i, ast.Attribute)]
    assert len(names) == len(set(names)), "дубли в списке регистрации активностей"


def test_registered_names_exist_as_activities():
    """Переименовали активность, а в списке осталось старое имя — импорт
    worker.py упал бы только при запуске воркера, не в тестах."""
    known = set()
    # delivery_bridge — активности Harness, которые зовёт воркфлоу релиза из
    # соседнего репозитория. Тот же класс ошибки: имя в списке регистрации есть,
    # активности за ним нет — падение на старте воркера, а не в тестах.
    for module in (activities_module, consolidation_activities, delivery_bridge):
        known |= {n for n in dir(module) if _is_activity(module, n)}
    unknown = _registered() - known
    assert not unknown, f"в списке регистрации имена, которые не являются активностями: {sorted(unknown)}"


def test_workflow_classes_are_registered():
    """Тот же класс ошибки для воркфлоу: объявлен, но не подключён — событие
    придёт, а обработать его будет некому."""
    workflows_src = (WORKER_DIR / "workflows.py").read_text(encoding="utf-8")
    declared = {
        node.name for node in ast.walk(ast.parse(workflows_src))
        if isinstance(node, ast.ClassDef)
        and any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "defn"
                for d in node.decorator_list)
    }
    worker_src = (WORKER_DIR / "worker.py").read_text(encoding="utf-8")
    missing = {name for name in declared if name not in worker_src}
    assert not missing, f"воркфлоу объявлены, но не зарегистрированы: {sorted(missing)}"


@pytest.mark.parametrize("name", ["finish_command_labels", "prepare_workspace"])
def test_regression_activities_that_were_forgotten(name):
    """Именно эти две уже забывали — пусть останутся под явным присмотром."""
    assert name in _registered()
