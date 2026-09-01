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

Уточнение (Дефект 2, `_handle_comment_intent`): ЧЕТЫРЕ конкретных вызова
`ack_comment_seen` в ветке `else` под `if workflow.patched(
"issue-lifecycle-comment-intent-reply-activity"):` в разбор не идут — они
нарочно хранят СТАРУЮ форму вызова ради детерминизма реплея историй, уже
записавших её, и сигнатура, актуальная сейчас, к ним не относится.

Исключение точечное — пара (имя активности, идентификатор маркера), а не
«эта ветка `else` целиком» и уж тем более не «любая ветка `else` под любым
`workflow.patched(...)` в файле». См. `_LEGACY_ELSE_EXEMPTIONS` и докстринг
`_walk_tagging_legacy_else` ниже — там же разбор, почему более широкое
исключение (было в прежней редакции этого гварда) само по себе дефект: оно
успело ослепить ещё три места, никак не связанных с Дефектом 2.
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
_CALLER_FILES = ("workflows.py", "consolidation_workflow.py")

# Точечный список мест, которым разрешено хранить СТАРУЮ форму вызова в
# ветке `else` под `workflow.patched(...)` — пара «имя активности,
# идентификатор маркера». Не «эта форма if/else вообще», а РОВНО эти места:
# в файле десятки веток `else` под patched-проверкой, и почти везде обе
# ветки актуальны и обязаны проверяться наравне — см. докстринг
# `_walk_tagging_legacy_else`.
_LEGACY_ELSE_EXEMPTIONS = {
    ("ack_comment_seen", "issue-lifecycle-comment-intent-reply-activity"),
}


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


def _is_workflow_patched_call(node: ast.expr) -> bool:
    """True для `workflow.patched(...)` — проверка поколения истории прогона."""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "patched")


def _patched_marker(node: ast.expr) -> str | None:
    """Строковый идентификатор маркера `workflow.patched("...")`, если он
    есть и задан строковым литералом. `None` — не patched-вызов либо маркер
    вычисляется динамически (в файле такого не встречается, но раз уж
    сверяем статически — не гадаем)."""
    if (_is_workflow_patched_call(node) and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def _walk_tagging_legacy_else(root: ast.AST):
    """Как `ast.walk`, но вместе с узлом отдаёт маркер `workflow.patched(...)`
    той ветки `else`, внутри которой этот узел лежит (`None` — узел вне
    такой ветки, в том числе если он лежит в самой ветке `if`).

    До этой правки исключение выкидывало из разбора ЛЮБУЮ ветку `else` под
    ЛЮБЫМ `if workflow.patched(...):` — единым решением на весь файл, хотя
    обоснование (детерминизм реплея СТАРОЙ формы вызова) касалось ровно
    четырёх мест (`_handle_comment_intent`, Дефект 2). Ревью нашло ещё три
    вызова, ослеплённых тем же широким исключением — `report_criterion_
    gate_stall`, `trigger_openhands_resolver`, `run_pr_fix_round` — сегодня
    верных, но добавь кто-нибудь параметр с умолчанием, и проверять их
    станет некому: гвард молчал бы о них точно так же, как молчал о
    `ack_comment_seen` три месяца.

    Довод старой версии докстринга — «в `else` попадает только реплей уже
    закрытой историей, живьём эта ветка не исполняется» — неверен как ОБЩЕЕ
    утверждение о семантике `workflow.patched`. Докстринг `_run_linear`
    (`worker/workflows.py`) описывает ровно противоположный, штатный
    случай: `if not workflow.patched("issue-lifecycle-phase-loop"):
    await self._run_linear(issue)` — код, выбираемый этим же маркером,
    который СТАРЫЕ, ЖИВЫЕ прогоны, годами припаркованные в проде,
    «доиграют» — то есть продолжают исполнять и получают через него НОВЫЕ
    команды в свою историю, а не только реплеят уже записанные старые.

    Для четырёх мест Дефекта 2 итоговый вывод («не сверять с текущей
    сигнатурой») всё равно верен, но по другой, узкой причине: старая форма
    вызова (`ack_comment_seen(issue, текст)`) в самой активности падает
    `TypeError`-ом при любом исполнении и без перехвата валит весь прогон
    (см. `tests/test_comment_intent_reply_activity.py`) — то есть у истории,
    где эта ветка вообще была пройдена, исхода кроме отказа на этом самом
    месте не было, и живого продолжения ЗА ней, которое эта ветка могла бы
    обслуживать, не существует ни для одного прогона. Это утверждение про
    КОНКРЕТНЫЕ четыре места, а не общее свойство формы `if patched/else`.

    Поэтому исключение здесь — точечное: не «эта ветка `else` не
    проверяется», а «эта ПАРА (имя активности, идентификатор маркера) из
    `_LEGACY_ELSE_EXEMPTIONS` не проверяется». Любой другой вызов в любом
    `else`, включая под ДРУГИМ маркером той же формы `if/else`, по-прежнему
    разбирается наравне с `if`.
    """
    stack: list[tuple[ast.AST, str | None]] = [(root, None)]
    while stack:
        node, marker = stack.pop()
        yield node, marker
        if isinstance(node, ast.If):
            own_marker = _patched_marker(node.test)
            stack.append((node.test, marker))
            for child in node.body:
                stack.append((child, marker))
            for child in node.orelse:
                # Маркер СВОЕГО patched-теста важнее унаследованного снаружи
                # — если этот `if` сам проверяет другой маркер, его `else`
                # относится к нему, а не к маркеру объемлющей ветки.
                stack.append((child, own_marker if own_marker is not None else marker))
            continue
        for child in ast.iter_child_nodes(node):
            stack.append((child, marker))


def _call_sites() -> tuple[list[tuple[str, str, int, int]], int]:
    """Места планирования активностей: файл, имя, строка, сколько передано.

    Второй элемент — сколько вызовов освобождены точечным исключением
    `_LEGACY_ELSE_EXEMPTIONS` (считается, а не отбрасывается молча: канарейка
    `test_legacy_else_exemption_matches_expected_count` проверяет, что их
    ровно столько, сколько ожидается).
    """
    sites: list[tuple[str, str, int, int]] = []
    exempted = 0
    for filename in _CALLER_FILES:
        path = WORKER_DIR / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node, marker in _walk_tagging_legacy_else(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr in ("execute_activity", "start_activity",
                                      "execute_local_activity")):
                continue
            if not node.args or not isinstance(node.args[0], ast.Attribute):
                continue
            name = node.args[0].attr
            if marker is not None and (name, marker) in _LEGACY_ELSE_EXEMPTIONS:
                exempted += 1
                continue
            passed = _passed_count(node)
            if passed is None:
                continue
            sites.append((filename, name, node.lineno, passed))
    return sites, exempted


def test_every_activity_call_passes_all_arguments():
    """Пропущенный необязательный аргумент ломает типы у ВСЕХ аргументов.

    Если тест упал — не добавляй активности умолчание и не убирай проверку.
    Передай аргумент явно в месте вызова: явное значение по умолчанию читается
    там, где принимается решение, а не там, где оно применяется.
    """
    signatures = _activity_signatures()
    assert signatures, "не нашли ни одной активности — разбор сломан"

    sites, _exempted = _call_sites()
    broken = []
    for filename, name, line, passed in sites:
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
    sites, _exempted = _call_sites()
    assert len(sites) > 20, f"нашли всего {len(sites)} вызовов — разбор сломан"
    signatures = _activity_signatures()
    known = [s for s in sites if s[1] in signatures]
    assert len(known) > 20, f"сопоставили всего {len(known)} вызовов с активностями"


# Число мест, освобождённых `_LEGACY_ELSE_EXEMPTIONS`, сегодня — ровно
# четыре: все четыре ветки `_handle_comment_intent`, где `workflow.patched(
# "issue-lifecycle-comment-intent-reply-activity")` разводит новый вызов
# `post_followup_reply` (ветка `if`) и старый `ack_comment_seen` (ветка
# `else`). Число зашито здесь же, рядом с тестом, а не вычислено — канарейка
# и обязана быть жёстким числом, иначе она освободит место молча, точно так
# же, как молчало прежнее исключение на всю ветку `else`.
_EXPECTED_LEGACY_ELSE_EXEMPTION_COUNT = 4


def test_legacy_else_exemption_matches_expected_count():
    """Канарейка точечного исключения (находка R1, ревью `fix/activity-arg-
    types`): число освобождённых мест обязано совпасть с ожидаемым.

    Стало БОЛЬШЕ — кто-то спрятал за уже существующей парой (активность,
    маркер) ещё один вызов вместо того, чтобы завести под него свою пару и
    объяснить, почему старая форма ему тоже не грозит. Стало МЕНЬШЕ — одна
    из четырёх веток `_handle_comment_intent` изменилась (например, маркер
    сняли через `workflow.deprecate_patch`), и запись в
    `_LEGACY_ELSE_EXEMPTIONS` пора убрать, а не оставлять мёртвым грузом.
    Число, продиктованное самим кодом, а не жёстко зашитое здесь, тихо
    выросло бы вместе с новым дефектом — это ровно та ошибка, которую чинит
    вся эта правка.
    """
    _sites, exempted = _call_sites()
    assert exempted == _EXPECTED_LEGACY_ELSE_EXEMPTION_COUNT, (
        f"освобождённых мест {exempted}, ожидалось "
        f"{_EXPECTED_LEGACY_ELSE_EXEMPTION_COUNT} — пересчитай "
        "_LEGACY_ELSE_EXEMPTIONS и объясни расхождение явно, не подгоняй "
        "число под факт")
