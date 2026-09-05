"""Правило маркеров версий — проверкой, а не обещанием.

`AGENTS.md`, правило 1 требует двух вещей: `workflow.patched(...)` идёт первым
операндом связки (иначе маркер попадает в историю через раз, и непостоянная
запись сама становится источником расхождения), и действующие маркеры известны —
переименование любого из них означает отказ по недетерминизму на живых прогонах.

Обе проверялись глазами, и обе разъезжались: к 5 сентября `patched` стоял вторым
операндом в пятнадцати местах, а таблица в `AGENTS.md` знала девять маркеров из
сорока (#311). Здесь они держатся кодом.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / "worker" / "workflows.py"
AGENTS = ROOT / "AGENTS.md"


def _tree() -> ast.Module:
    return ast.parse(WORKFLOWS.read_text())


def _is_patched(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "patched")


def _enclosing_functions(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def markers_in_code() -> dict[str, set[str]]:
    """Маркер → имена функций, где он вызывается."""
    tree = _tree()
    funcs = _enclosing_functions(tree)
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not (_is_patched(node) and node.args
                and isinstance(node.args[0], ast.Constant)):
            continue
        inside = [f for f in funcs
                  if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
        nearest = min(inside, key=lambda f: (f.end_lineno or f.lineno) - f.lineno)
        found.setdefault(node.args[0].value, set()).add(nearest.name)
    return found


# Реестр размечен так же, как блоки в теле Issue: разбирается разметка, а не
# соседство с заголовком. Прозаическая таблица выше живёт своей жизнью, и
# случайно попасть в реестр её строки не должны.
REGISTRY_START = "<!-- markers:start -->"
REGISTRY_END = "<!-- markers:end -->"


def registry_block() -> str:
    text = AGENTS.read_text()
    start, end = text.find(REGISTRY_START), text.find(REGISTRY_END)
    assert start != -1 and end > start, (
        f"в AGENTS.md нет размеченного реестра маркеров "
        f"({REGISTRY_START} … {REGISTRY_END})")
    return text[start:end]


def markers_in_registry() -> dict[str, set[str]]:
    """Маркер → функции по реестру в AGENTS.md."""
    rows = re.findall(r"^\| `([a-z0-9-]+)` \| ([^|]+) \|$",
                      registry_block(), re.MULTILINE)
    return {mid: {f.strip(" `") for f in where.split(",")} for mid, where in rows}


def test_no_marker_is_short_circuited():
    """`patched` вторым операндом связки записывает маркер через раз.

    Прогон, у которого первый операнд решил исход, маркера в историю не пишет —
    и следующая правка, читающая маркер безусловно, уводит такой прогон в ветку,
    не совпадающую с записанной. Корпус 149 историй, 29 мёртвых прогонов.
    """
    guilty = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.BoolOp):
            continue
        for position, value in enumerate(node.values):
            if position == 0:
                continue
            for sub in ast.walk(value):
                if _is_patched(sub):
                    guilty.append(sub.lineno)
    assert not guilty, (
        "workflow.patched вызывается не первым операндом в строках "
        f"{sorted(set(guilty))} — маркер попадёт в историю через раз")


def test_registry_knows_every_marker():
    """Реестр в AGENTS.md обязан совпадать с кодом в обе стороны.

    Рукописная таблица разъезжается молча: она знала девять маркеров из сорока,
    и сверявшийся с ней перед переименованием пропустил бы три четверти.
    """
    code, registry = markers_in_code(), markers_in_registry()
    assert registry, "реестр маркеров в AGENTS.md не найден или не разобран"
    assert set(code) - set(registry) == set(), (
        "маркеры есть в коде, но не в реестре AGENTS.md: "
        f"{sorted(set(code) - set(registry))}")
    assert set(registry) - set(code) == set(), (
        "реестр AGENTS.md называет маркеры, которых в коде нет: "
        f"{sorted(set(registry) - set(code))}")


def test_registry_points_at_the_right_place():
    """Не только имя маркера, но и место: по нему его и ищут в коде."""
    code, registry = markers_in_code(), markers_in_registry()
    wrong = {mid: (sorted(code[mid]), sorted(registry[mid]))
             for mid in code if mid in registry and code[mid] != registry[mid]}
    assert not wrong, f"реестр указывает не на те функции: {wrong}"
