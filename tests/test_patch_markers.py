"""Реестр маркеров версий — проверкой, а не обещанием.

Переименование маркера означает отказ по недетерминизму на живых прогонах, и
`AGENTS.md` называет действующие маркеры прямо. Рукописный список разъезжается
молча: к 5 сентября он знал девять маркеров из сорока (#311), и сверявшийся с
ним перед переименованием пропустил бы три четверти.

Здесь список держится кодом: он собирается разбором AST по всем модулям с
воркфлоу и сверяется с размеченным реестром в `AGENTS.md` в обе стороны — и по
именам, и по месту вызова.

Чего этот файл НЕ проверяет и почему. Проверки «`patched` идёт первым операндом»
здесь нет намеренно: она подталкивает к подъёму вызова, а подъём через `await`
ломает реплей (`Non-deprecated patch marker encountered … no corresponding
change command`). Разбор — в `AGENTS.md`, правило 1.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Все модули, где живут воркфлоу: маркер, заведённый в любом из них, обязан
# попасть в реестр. Иначе повторится та же тихая слепота, только по файлам.
SOURCES = (ROOT / "worker" / "workflows.py",
           ROOT / "worker" / "consolidation_workflow.py")
AGENTS = ROOT / "AGENTS.md"

# Реестр размечен, как блоки в теле Issue: разбирается разметка, а не соседство
# с заголовком. Таблица с пояснениями выше живёт своей жизнью, и её строки
# попадать сюда не должны.
REGISTRY_START = "<!-- markers:start -->"
REGISTRY_END = "<!-- markers:end -->"


def _is_patched(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "patched")


def _qualified_names(tree: ast.Module) -> dict[ast.AST, str]:
    """Функция → `Класс.метод`, чтобы `run` двух воркфлоу не слились в одно имя."""
    names: dict[ast.AST, str] = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names[child] = f"{prefix}{child.name}"
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree)
    return names


def markers_in_code() -> dict[str, set[str]]:
    """Маркер → места вызова вида `Класс.метод`."""
    found: dict[str, set[str]] = {}
    for source in SOURCES:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = _qualified_names(tree)
        for node in ast.walk(tree):
            if not (_is_patched(node) and node.args):
                continue
            assert isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str), (
                f"{source.name}:{node.lineno}: имя маркера обязано быть строкой-"
                "константой, иначе реестр по нему не собрать")
            inside = [fn for fn, _ in names.items()
                      if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno)]
            assert inside, (
                f"{source.name}:{node.lineno}: workflow.patched вне функции — "
                "реестру нечего записать как место вызова")
            nearest = min(inside, key=lambda f: (f.end_lineno or f.lineno) - f.lineno)
            found.setdefault(node.args[0].value, set()).add(names[nearest])
    return found


def registry_block() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    start, end = text.find(REGISTRY_START), text.find(REGISTRY_END)
    assert start != -1 and end > start, (
        f"в AGENTS.md нет размеченного реестра маркеров "
        f"({REGISTRY_START} … {REGISTRY_END})")
    return text[start:end]


def markers_in_registry() -> dict[str, set[str]]:
    rows = re.findall(r"^\| `([a-z0-9-]+)` \| ([^|]+) \|$",
                      registry_block(), re.MULTILINE)
    return {mid: {f.strip(" `") for f in where.split(",")} for mid, where in rows}


def test_registry_knows_every_marker():
    """Реестр обязан совпадать с кодом в обе стороны."""
    code, registry = markers_in_code(), markers_in_registry()
    assert registry, "реестр маркеров в AGENTS.md не найден или не разобран"
    assert set(code) - set(registry) == set(), (
        "маркеры есть в коде, но не в реестре AGENTS.md: "
        f"{sorted(set(code) - set(registry))}")
    assert set(registry) - set(code) == set(), (
        "реестр AGENTS.md называет маркеры, которых в коде нет: "
        f"{sorted(set(registry) - set(code))}")


def test_registry_points_at_the_right_place():
    """Не только имя маркера, но и место: по нему его и ищут в коде.

    Место записано как `Класс.метод`: `run` есть и у `IssueLifecycle`, и у
    `IssueDevelopment`, и переезд маркера между ними обязан быть виден.
    """
    code, registry = markers_in_code(), markers_in_registry()
    wrong = {mid: {"код": sorted(code[mid]), "реестр": sorted(registry[mid])}
             for mid in code if mid in registry and code[mid] != registry[mid]}
    assert not wrong, f"реестр указывает не на те функции: {wrong}"
