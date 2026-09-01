"""Вызов активности обязан передавать ВСЕ её аргументы, включая те, у которых
есть значение по умолчанию.

Отказ, ради которого написано (стенд, 1 сентября 2026, poh-demo-checkout#166):
`interpret_user_comment` получила `issue` СЛОВАРЁМ вместо `IssueInput` и упала
`AttributeError: 'dict' object has no attribute 'repo'` — трижды, по числу
попыток. Причина не в сигнатуре: она аннотирована верно.

Причина в Temporal. `temporalio/worker/_activity.py`:

    elif arg_types is not None and len(arg_types) != len(start.input):
        arg_types = None

`arg_types` считается по ВСЕМ параметрам, включая параметры с умолчанием
(проверено на живом воркере: у `interpret_user_comment` их шесть). Вызывающий
передал пять. Числа не совпали — Temporal ВЫБРОСИЛ типы целиком и отдал сырой
JSON во все параметры сразу, а не только в пропущенный.

То есть один пропущенный необязательный аргумент ломает преобразование типов у
всех остальных. Ошибка при этом выглядит как дефект в теле активности, и
искать её приходится не там.

Проверка статическая: разбор AST, без Temporal и без импорта воркера.
"""

import ast
from pathlib import Path

import pytest

WORKER_DIR = Path(__file__).resolve().parent.parent / "worker"

# Модули, где живут активности, и алиас, под которым их зовёт воркфлоу.
_ACTIVITY_MODULES = {
    "activities": "activities.py",
    "consolidation_activities": "consolidation_activities.py",
    "delivery_bridge": "delivery_bridge.py",
}

# Файлы, где воркфлоу планирует активности.
_CALLER_FILES = ("workflows.py",)


def _activity_signatures() -> dict[str, int]:
    """Имя активности → сколько у неё параметров всего."""
    signatures: dict[str, int] = {}
    for _alias, filename in _ACTIVITY_MODULES.items():
        path = WORKER_DIR / filename
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorated = any(
                (isinstance(d, ast.Attribute) and d.attr == "defn")
                or (isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "defn")
                for d in node.decorator_list)
            if decorated:
                signatures[node.name] = len(node.args.posonlyargs) + len(node.args.args)
    return signatures


def _passed_count(call: ast.Call) -> int | None:
    """Сколько аргументов передаёт вызов. None — посчитать нельзя.

    У Temporal два способа: `args=[...]` списком либо один позиционный
    аргумент вторым параметром. Списком, собранным не литералом (звёздочкой,
    переменной), посчитать нельзя — такие вызовы пропускаем и говорим об этом
    вслух, а не делаем вид, что проверили.
    """
    for keyword in call.keywords:
        if keyword.arg == "args":
            if isinstance(keyword.value, ast.List):
                return len(keyword.value.elts)
            return None
    # Второй позиционный — единственный аргумент активности.
    return 1 if len(call.args) > 1 else 0


def _call_sites() -> list[tuple[str, str, int, int]]:
    """Места планирования активностей: файл, имя, строка, сколько передано."""
    sites: list[tuple[str, str, int, int]] = []
    for filename in _CALLER_FILES:
        path = WORKER_DIR / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr in ("execute_activity", "start_activity",
                                      "execute_local_activity")):
                continue
            if not node.args or not isinstance(node.args[0], ast.Attribute):
                continue
            passed = _passed_count(node)
            if passed is None:
                continue
            sites.append((filename, node.args[0].attr, node.lineno, passed))
    return sites


def test_every_activity_call_passes_all_arguments():
    """Пропущенный необязательный аргумент ломает типы у ВСЕХ аргументов.

    Если тест упал — не добавляй активности умолчание и не убирай проверку.
    Передай аргумент явно в месте вызова: явное значение по умолчанию читается
    там, где принимается решение, а не там, где оно применяется.
    """
    signatures = _activity_signatures()
    assert signatures, "не нашли ни одной активности — разбор сломан"

    broken = []
    for filename, name, line, passed in _call_sites():
        expected = signatures.get(name)
        if expected is None:
            continue  # не активность (константа модуля) либо чужой модуль
        if passed != expected:
            broken.append(f"worker/{filename}:{line} — {name}: "
                          f"передано {passed}, параметров {expected}")

    assert not broken, (
        "Вызовы активностей с неполным списком аргументов — Temporal выбросит "
        "типы и отдаст словари вместо объектов:\n  " + "\n  ".join(broken))


def test_guard_itself_finds_the_calls():
    """Гвард обязан что-то находить: пустой разбор проходил бы всегда.

    Тест, который не может упасть, не проверяет ничего — а именно так этот
    дефект и прожил три месяца незамеченным.
    """
    sites = _call_sites()
    assert len(sites) > 20, f"нашли всего {len(sites)} вызовов — разбор сломан"
    signatures = _activity_signatures()
    known = [s for s in sites if s[1] in signatures]
    assert len(known) > 20, f"сопоставили всего {len(known)} вызовов с активностями"
