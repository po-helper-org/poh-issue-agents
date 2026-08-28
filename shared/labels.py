"""Словарь меток протокола агентов v1.

Источник: po-helper-org/.github → AGENT-PROTOCOL.md, раздел 4. Правило протокола —
**одна метка, один писатель**: метку из чужой зоны агент только читает, иначе два
агента затирают друг друга.

Здесь живут:
- Метки контура (общие для Issue-Agent, PR-Agent, PR-Closer)
- Внутренние метки Issue-Agent (`advisor:*`, `priority:*`, плоские метки)

Константы живут здесь, чтобы и вебхук, и воркер, и каталог меток читали из
одного источника — иначе новый добавленный в коде label не попадёт в каталог и
разъедется.

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

# --- Внутренние метки Issue-Agent ---
# Эти метки пишет только Issue-Agent; словарь нужен для каталога и проверки
# согласованности. Константы живут здесь, чтобы и вебхук, и воркер, и каталог
# читали из одного источника — иначе новый добавленный в коде label не попадёт
# в каталог и разъедется.

# Advisor: классификация на триаже
ADVISOR_PREFIX = "advisor:"
ADVISOR_EXISTING = f"{ADVISOR_PREFIX}existing-functionality"
ADVISOR_CONSULTATION = f"{ADVISOR_PREFIX}consultation"
ADVISOR_BUG = f"{ADVISOR_PREFIX}bug"
ADVISOR_FEATURE = f"{ADVISOR_PREFIX}feature-request"
ADVISOR_RESEARCH = f"{ADVISOR_PREFIX}product-research"
ADVISOR_ANSWERED = f"{ADVISOR_PREFIX}answered"
ADVISOR_LABELS = frozenset({
    ADVISOR_EXISTING,
    ADVISOR_CONSULTATION,
    ADVISOR_BUG,
    ADVISOR_FEATURE,
    ADVISOR_RESEARCH,
    ADVISOR_ANSWERED,
})

# Приоритеты: рассчитываются по формуле Cost of Delay / Effort
PRIORITY_PREFIX = "priority:"
PRIORITY_P0 = f"{PRIORITY_PREFIX}P0"
PRIORITY_P1 = f"{PRIORITY_PREFIX}P1"
PRIORITY_P2 = f"{PRIORITY_PREFIX}P2"
PRIORITY_P3 = f"{PRIORITY_PREFIX}P3"
PRIORITY_LABELS = frozenset({PRIORITY_P0, PRIORITY_P1, PRIORITY_P2, PRIORITY_P3})

# Плоские метки: используются в разных точках контура
BOT_AUTHORED = "bot-authored"
SECURITY_SENSITIVE = "security-sensitive"
NEEDS_CLARIFICATION = "needs-clarification"
SPAM = "spam"
DUPLICATE = "duplicate"
POSSIBLE_DUPLICATE = "possible-duplicate"
ESTIMATED = "estimated"
FLAT_LABELS = frozenset({
    BOT_AUTHORED,
    SECURITY_SENSITIVE,
    NEEDS_CLARIFICATION,
    SPAM,
    DUPLICATE,
    POSSIBLE_DUPLICATE,
    ESTIMATED,
})
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
