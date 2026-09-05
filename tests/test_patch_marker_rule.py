"""Правило 1 из `AGENTS.md`: маркер патча обязан попадать в историю на КАЖДОМ
прогоне, а не через раз.

`and` в Python вычисляется слева направо и останавливается на первом ложном
значении: в `some_flag and workflow.patched(...)` вызов `patched` пропускается
всякий раз, когда флаг ложен. Маркер, вызываемый через раз, — источник
расхождения на реплее: прогон, где вызова не случилось, не находит его в
истории, а актуальный код уже ждёт другую ветку. Именно так расшился
промежуточный коммит PR #310, и ровно это поймало ревью (`e3d4056`).

Два гварда, потому что правило двухчастное:

1. форма вызова — `workflow.patched(...)` не стоит правее первого операнда
   ни в одной связке `and`/`or`. Запись в локальную переменную разрешена:
   значение вычисляется на каждом прогоне, источник истинности тот же;
2. таблица «Действующие маркеры» в `AGENTS.md` — реестр, а не подборка: её
   строки обязаны совпадать с идентификаторами `workflow.patched(...)`
   из `worker/workflows.py` (1:1, оба направления). Рукописная таблица,
   отставшая от кода на три четверти, хуже отсутствия — ею пользуются
   при переименовании и аудите.

Форма проверяется синтаксическим разбором, а не строковым поиском: вызов
может стоять на любой строке выражения, а grep ловит и докстринги — сам
нарушитель из `_phase_await_build` упоминает «short-circuit and» в
комментарии и проходил бы такой гвард нарушенным.
"""

import ast
import inspect
import re
from pathlib import Path

import workflows  # noqa: F401  (worker/ в образе плоский — sys.path в conftest)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def _is_patched_call(node: object) -> bool:
    """Ровно `workflow.patched(...)`, а не любой `.patched(...)`.

    В модуле `workflow` — объект temporalio (`from temporalio import
    workflow`); сведение проверки к одному суффиксу `attr` цепляло бы
    чужие объекты с тем же именем метода.
    """
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "patched"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "workflow")


def _patched_marker(node: ast.expr) -> str | None:
    """Идентификатор маркера `workflow.patched("...")` либо None."""
    if (_is_patched_call(node)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def _parse_workflows() -> tuple[str, ast.Module]:
    """Исходник воркфлоу и его дерево — тот же файл, что исполняет воркер.

    Путь берём через импортированный модуль: тесты видят его плоским
    `import workflows`, и гвард не должен разойтись с исполняемым кодом,
    даже если раскладка каталогов меняется.
    """
    src = inspect.getsource(workflows)
    return src, ast.parse(src)


def _patched_calls(tree: ast.Module) -> list[ast.Call]:
    found: list[ast.Call] = []
    stack = [ast.walk(tree)]
    for walker in stack:
        for node in walker:
            if _patched_marker(node) is not None:
                found.append(node)
    return found


def _nearest_boolop_parents(tree: ast.Module) -> dict[int, ast.BoolOp]:
    """id(узла) -> ближайший объемлющий BoolOp (для вызовов и любых узлов)."""
    parents: dict[int, ast.BoolOp] = {}
    stack: list[tuple[ast.AST, ast.BoolOp | None]] = [(tree, None)]
    while stack:
        node, boolop = stack.pop()
        if isinstance(node, ast.BoolOp):
            for child in node.values:
                parents[id(child)] = node
                stack.append((child, node))
            continue
        for child in ast.iter_child_nodes(node):
            stack.append((child, boolop))
    return parents


def test_patched_is_never_a_non_first_operand():
    """Ни один маркер не вычисляется вторым операндом связки and/or.

    Разрешение записи в переменную — не поблажка, а требование: переменная
    гарантирует ВЫЧИСЛЕНИЕ маркера на каждом прогоне, чего от связки не
    добиться. Проверяется позиция узла в его непосредственной связке;
    вызов внутри группирующего выражения разберёт его собственная связка
    при следующем заходе обхода.
    """
    _src, tree = _parse_workflows()
    parents = _nearest_boolop_parents(tree)

    offenders = []
    for call in _patched_calls(tree):
        boolop = parents.get(id(call))
        if boolop is None:
            continue
        position = next(i for i, v in enumerate(boolop.values) if v is call)
        if position > 0:
            op = "and" if isinstance(boolop.op, ast.And) else "or"
            offenders.append(
                f"строка {call.lineno}: {_patched_marker(call)!r} — "
                f"{position + 1}-й операнд `{op}`")

    assert not offenders, (
        "`workflow.patched(...)` обязан быть первым операндом связки "
        f"(правило 1 AGENTS.md), нарушено в {len(offenders)} местах:\n"
        + "\n".join(offenders)
        + "\n\nВынеси вызов в локальную переменную перед связкой — "
        "значение обязано вычисляться на каждом прогоне, независимо от "
        "остальных флагов.")


_TABLE_ROW_RE = re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|", re.M)


def _agent_md_table_rows() -> set[str]:
    """Строки таблицы «Действующие маркеры» в AGENTS.md.

    Таблицу находим по заголовку раздела и дальше берём подряд идущие
    строки-бэктики, пока не встретится первая без `|`: между заголовком
    и таблицей стоит пустая строка, а режет таблицу снизу абзац правила —
    граница по пустой строке сверху ловила бы воздух.
    """
    text = AGENTS_MD.read_text(encoding="utf-8")
    after = text[text.index("Действующие маркеры"):]
    rows: set[str] = set()
    in_table = False
    for line in after.splitlines():
        if not in_table:
            in_table = line.startswith("|")
            if not in_table:
                continue
        if not line.startswith("|"):
            break
        match = _TABLE_ROW_RE.match(line)
        if match:
            rows.add(match.group(1))
    return rows


def test_agent_md_table_lists_every_marker_exactly_once():
    """Таблица маркеров в AGENTS.md обязана совпадать с кодом 1:1.

    Меньше — таблица солгала о полноте: аудитор, сверяющийся с ней перед
    переименованием, пропустил бы большинство живых маркеров (так и было:
    9 строк против 40 в коде). Больше — строка без вызова в коде, и её
    «что разводит» не проверить нигде. Дубликат строки — та же ложь:
    в множестве его не видно.
    """
    _src, tree = _parse_workflows()
    in_code = {m for call in _patched_calls(tree)
               if (m := _patched_marker(call)) is not None}
    in_table = _agent_md_table_rows()
    md_lines = AGENTS_MD.read_text(encoding="utf-8").splitlines()
    row_count = len(_TABLE_ROW_RE.findall(
        chr(10).join(line for line in md_lines if line.startswith("|"))))

    missing = sorted(in_code - in_table)
    extra = sorted(in_table - in_code)

    assert not missing, (
        "маркеры, отсутствующие в таблице AGENTS.md "
        "(добавь строку «что разводит»): " + ", ".join(missing))
    assert not extra, (
        "строки таблицы AGENTS.md без вызова в worker/workflows.py "
        "(удали строку или верни вызов): " + ", ".join(extra))
    assert row_count == len(in_table), "в таблице дубликаты маркеров"


def test_marker_helpers_recognise_both_spellings():
    """Помощник gvarda обязан видеть многострочные вызовы и не падать на
    вызовах без литерала — иначе гвард молча ослепнет ровно на ту форму,
    которую правка любит заводить (перенос аргумента на свою строку).
    """
    tree = ast.parse(
        "workflow.patched('x')\n"
        "workflow.patched(\n"
        "    'y')\n"
        "workflow.patched(z)\n"
        "other.patched('w')\n")
    seen = [_patched_marker(n) for n in ast.walk(tree)]
    assert [m for m in seen if m] == ["x", "y"]
