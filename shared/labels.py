"""Словарь меток протокола агентов v1.

Источник: po-helper-org/.github → AGENT-PROTOCOL.md, раздел 4. Правило протокола —
**одна метка, один писатель**: метку из чужой зоны агент только читает, иначе два
агента затирают друг друга.

Здесь живут только метки контура (общие для Issue-Agent, PR-Agent, PR-Closer).
Внутренние метки этого сервиса (`advisor:*`, `priority:*`, `duplicate`,
`run:*`/`done:*`/`failed:*`) остаются там, где применяются: их пишет только этот
сервис, и общего словаря им не нужно.

Модуль намеренно без зависимостей: его читают и вебхук, и воркер.
"""

import re

# --- Очередь к человеку: единый префикс на всю организацию ---
# Было врозь: `needs-human-triage` здесь и `pr-closer:needs-human` в PR-Closer.
# Одна выборка `label:needs-human:*` теперь показывает всю очередь к людям.
NEEDS_HUMAN_PREFIX = "needs-human:"
NEEDS_HUMAN_TRIAGE = f"{NEEDS_HUMAN_PREFIX}triage"

# Историческое имя. Оставлено ради поиска по старым Issue: сервис его больше не
# ставит, но выборка по бэклогу до перехода всё ещё им пользуется.
LEGACY_NEEDS_HUMAN_TRIAGE = "needs-human-triage"

# --- Точка передачи задачи разработчику (H1) ---
# Ставит Issue-Agent, читает разработчик. Единственное место, где контур отдаёт
# работу человеку по своей инициативе: качество этой передачи определяет всё
# остальное — плохо подготовленная задача даёт плохой PR, который агенты не спасут.
READY_FOR_DEV = "ready-for-dev"

# --- Рубильник человека (R4) ---
# Ставит человек, читают все агенты. Проверяется раньше первого обращения к LLM:
# смысл в том, чтобы не тратить бюджет на то, что человек уже забрал себе.
AGENTS_OFF = "agents:off"

# --- Провенанс (R6) ---
# Артефакт, созданный агентом. Без него агенты не отличают вход от собственного
# выхода, и контур начинает кормить сам себя.
ORIGIN_AGENT = "origin:agent"

# --- Точки решения человека ---
# Метки, которыми человек отвечает контуру на прямой вопрос: `research-me` /
# `bug-me` — куда вести Issue после триажа, `build-me` — запускать ли
# разработку, `not-duplicate` / `confirm-duplicate` — решение по дублю.
# Единственный список: его читает вебхук (какие лейблы поднимают дорогой
# прогон через signal-with-start) и каталог меток (shared/label_catalog.py).
# Разъехавшись, они тихо теряют одну метку — она всё равно заведётся при
# первом применении, просто серой и без описания, а решение человека до
# контура не дойдёт.
HUMAN_DECISION_LABELS = {"research-me", "bug-me", "build-me", "not-duplicate", "confirm-duplicate"}

# Сквозной ключ цепочки: строка `root-issue: #N` в теле follow-up Issue
# (AGENT-PROTOCOL.md, раздел 3). По ней Issue-Agent находит исходную задачу и
# считает глубину.
_ROOT_ISSUE_RE = re.compile(r"^\s*root-issue:\s*#(\d+)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_root_issue(body: str | None) -> int | None:
    """Номер исходного Issue из тела follow-up, иначе None.

    Отсутствие ключа — штатная ситуация, а не ошибка: PR мог не ссылаться на
    Issue, тогда follow-up вешается на PR и `root-issue` неизвестен.
    """
    if not body:
        return None
    match = _ROOT_ISSUE_RE.search(body)
    return int(match.group(1)) if match else None


def has(labels: list[str], name: str) -> bool:
    """Регистронезависимая проверка наличия метки: GitHub сохраняет регистр,
    но считает `Agents:Off` и `agents:off` одной и той же меткой."""
    return name.lower() in {label.lower() for label in labels}
