"""Разбиение задачи на подзадачи и раскладка по релизам.

Между аналитикой и разработкой лежит шаг, которого в контуре не было: у задачи
есть системные требования, но нет плана исполнения. Агент разработки получал
задачу целиком и решал сам, с чего начать и что считать достаточным, — а это
ровно то решение, которое должно приниматься до кода, а не в процессе.

Три релиза, и граница между ними проверяемая, а не на глаз:

**MVP** — прямой путь пользователя целиком. Критерий: убери подзадачу — путь
перестаёт работать. Осталась рабочей — значит подзадача не MVP.

**GROW** — то, без чего фича работает, но выпускать её нельзя: граничные
случаи, устойчивость к неверному вводу, наблюдаемость.

**SUPPORT** — баги и долги, найденные по ходу разбора.

Порядок внутри MVP задан зависимостями, а не номерами: агент разработки берёт
подзадачи в порядке готовности, и «сначала пункт 1» ничего ему не говорит, если
пункт 3 на самом деле нужен раньше.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub.
"""

import os

MVP = "mvp"
GROW = "grow"
SUPPORT = "support"

RELEASES = (MVP, GROW, SUPPORT)

RELEASE_TITLES = {
    MVP: "MVP — прямой путь",
    GROW: "GROW — до выпуска в production",
    SUPPORT: "SUPPORT — найденное по дороге",
}

# Метка релиза на подзадаче. Префикс тот же, что у остальных словарей контура
# (`phase:`, `advisor:`, `needs-human:`) — одна выборка по `release:*` даёт
# срез всего плана.
RELEASE_PREFIX = "release:"

# Потолок MVP. Больше — значит граница проведена не там: в прямой путь попало
# то, без чего он работает. Не режем молча, а говорим об этом человеку.
MVP_SOFT_CAP = 6

# Потолок на весь план. Декомпозиция, породившая три десятка задач, — это не
# план, а свалка: её никто не разберёт, а контур начнёт кормить сам себя.
TOTAL_CAP = 20


class InvalidPlan(ValueError):
    """План не соответствует контракту — ошибка, а не повод угадывать."""


def enabled() -> bool:
    """Пусто — включено. Явное `0` возвращает прежний путь: после аналитики
    задача идёт в разработку целиком, без разбиения."""
    return os.environ.get("DECOMPOSE_ENABLED", "").strip().lower() not in {"0", "false", "no", "off"}


def release_label(release: str) -> str:
    return f"{RELEASE_PREFIX}{release}"


def normalize_release(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value not in RELEASES:
        raise InvalidPlan(f"неизвестный релиз {raw!r}; допустимо: {', '.join(RELEASES)}")
    return value


def validate(items: list[dict]) -> list[dict]:
    """Проверки, которые дешевле сделать до создания задач в GitHub.

    Созданный SubIssue уже не отменить одной кнопкой: он живёт в бэклоге, его
    видят люди, на него ссылается родитель. Поэтому битый план отвергается
    целиком до первой записи, а не чинится по дороге.
    """
    if not items:
        raise InvalidPlan("план пуст — разбивать было нечего или разбор не удался")
    if len(items) > TOTAL_CAP:
        raise InvalidPlan(
            f"подзадач {len(items)}, потолок {TOTAL_CAP}: это не план, а свалка")

    out = []
    for index, item in enumerate(items):
        title = str(item.get("title") or "").strip()
        if not title:
            raise InvalidPlan(f"подзадача {index}: пустой заголовок")
        depends = item.get("depends_on") or []
        for dep in depends:
            if not isinstance(dep, int) or not 0 <= dep < len(items):
                raise InvalidPlan(f"подзадача {index}: зависимость {dep!r} вне списка")
            if dep == index:
                raise InvalidPlan(f"подзадача {index} зависит от самой себя")
        out.append({
            "title": title,
            "body_markdown": str(item.get("body_markdown") or "").strip(),
            "release": normalize_release(item.get("release", "")),
            "depends_on": list(depends),
            "rationale": str(item.get("rationale") or "").strip(),
        })

    _reject_cycles(out)
    return out


def _reject_cycles(items: list[dict]) -> None:
    """Цикл в зависимостях означает план, который нельзя исполнить: каждая
    подзадача ждёт другую. Ловим здесь — в GitHub это уже неисправимо."""
    state = [0] * len(items)  # 0 — не смотрели, 1 — в обходе, 2 — закрыта

    def walk(node: int, path: list[int]) -> None:
        if state[node] == 1:
            loop = " → ".join(f"#{i}" for i in path[path.index(node):] + [node])
            raise InvalidPlan(f"цикл в зависимостях: {loop}")
        if state[node] == 2:
            return
        state[node] = 1
        for dep in items[node]["depends_on"]:
            walk(dep, path + [node])
        state[node] = 2

    for i in range(len(items)):
        walk(i, [])


def group(items: list[dict]) -> dict[str, list[dict]]:
    """План по релизам, порядок внутри — как вернул разбор."""
    return {release: [i for i in items if i["release"] == release] for release in RELEASES}


def mvp_oversized(items: list[dict]) -> bool:
    return len(group(items)[MVP]) > MVP_SOFT_CAP


def subissue_body(item: dict, *, parent: int, numbers: dict[int, int], index: int) -> str:
    """Тело подзадачи: ключ цепочки, релиз, зависимости уже номерами Issue.

    `root-issue` и `origin:agent` обязательны — по ним контур отличает свой
    выход от входа и не начинает кормить себя (правила R6, R7).
    """
    lines = [f"root-issue: #{parent}", "", f"Родительская задача: #{parent}", ""]
    if item["body_markdown"]:
        lines += [item["body_markdown"], ""]
    lines.append(f"**Релиз:** {RELEASE_TITLES[item['release']]}")
    if item["rationale"]:
        lines.append(f"**Почему здесь:** {item['rationale']}")
    deps = [numbers[d] for d in item["depends_on"] if d in numbers]
    if deps:
        lines.append("**Зависит от:** " + ", ".join(f"#{n}" for n in deps))
    return "\n".join(lines)


def parent_summary(items: list[dict], numbers: dict[int, int], *, summary: str,
                   branch: str) -> str:
    """Сводка в родителе: план исполнения по релизам со ссылками.

    Родитель после декомпозиции — оглавление, а не место работы. Работа
    переезжает в подзадачи, и в родителе должно быть видно всё сразу: что в
    каком релизе, в каком порядке и где требования.
    """
    parts = ["## 🧩 Декомпозиция", ""]
    if summary:
        parts += [summary.strip(), ""]

    by_release = group(items)
    for release in RELEASES:
        bucket = by_release[release]
        parts.append(f"### {RELEASE_TITLES[release]}")
        if not bucket:
            parts += ["", "_пусто_", ""]
            continue
        parts.append("")
        for item in bucket:
            number = numbers.get(items.index(item))
            deps = [numbers[d] for d in item["depends_on"] if d in numbers]
            tail = f" ← после {', '.join(f'#{n}' for n in deps)}" if deps else ""
            parts.append(f"- #{number} — {item['title']}{tail}" if number
                         else f"- {item['title']} _(не создана)_{tail}")
        parts.append("")

    if branch:
        parts += [f"Требования и артефакты — в ветке `{branch}`.", ""]
    if mvp_oversized(items):
        parts += [
            f"> ⚠️ В MVP {len(by_release[MVP])} подзадач при ориентире "
            f"{MVP_SOFT_CAP}. Похоже, граница прямого пути проведена слишком "
            "широко — стоит пересмотреть, что из этого действительно блокирует "
            "базовый сценарий.", ""]
    parts.append("Задача готова к разработке: агент берёт подзадачи MVP в "
                 "порядке зависимостей.")
    return "\n".join(parts)


def needs_subissues(items: list[dict]) -> bool:
    """Разворачивать ли план в под-задачи.

    Шаг существует, только если от него зависит другой шаг. Граф без рёбер —
    это не план, а список правок, который исполнитель сделает за один прогон;
    заводить под каждую строку задачу в трекере значит платить вниманием за
    видимость, которой никто не пользуется.

    Определение взято из инструмента, а не выдумано: задачи планов superpowers
    несят блок Interfaces с Consumes/Produces, и непустой Consumes — это и есть
    объявленное ребро.
    """
    for index, item in enumerate(items):
        depends = item.get("depends_on") or []
        for dep in depends:
            # Ребром считается только зависимость на другой, существующий шаг
            if isinstance(dep, int) and 0 <= dep < len(items) and dep != index:
                return True
    return False


def dependency_reason_missing(items: list[dict]) -> list[str]:
    """Заголовки шагов, где зависимость объявлена без предмета.

    Ребро обязано называть, ЧТО даёт предшественник: «читает version из
    состояния». Без предмета зависимость невозможно ни проверить, ни
    опровергнуть, а модели дешевле выдумать её, чем признать, что плана нет.
    """
    bad = []
    for item_index, item in enumerate(items):
        for index in item.get("depends_on") or []:
            if not (item.get("depends_reason") or {}).get(str(index), "").strip():
                # Используем заголовок, если есть; иначе используем порядковый номер
                title = item.get("title") or f"шаг #{item_index}"
                bad.append(title)
                break
    return bad
