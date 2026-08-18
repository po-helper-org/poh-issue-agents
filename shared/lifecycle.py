"""Модель фаз жизненного цикла Issue — единственный источник правды.

Сегодня состояние Issue размазано по четырём независимым представлениям (метки,
переменные воркфлоу, комментарии, Event History), и ни одно не покрывает путь
дальше приоритизации. Этот модуль вводит один перечень фаз и одну таблицу
переходов; из них выводятся значения query, метки в GitHub, search attribute и
строки таймлайна. Иначе каждая подзадача эпика заведёт свои названия, и
трассировка будет собирать таймлайн из несовместимых кусков.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как `estimation.py`.
Логика состояний проверяется напрямую, а не через прогон воркфлоу.

Именование согласовано с уже внедрёнными словарями: namespace через двоеточие,
как `needs-human:*` и `run:*`/`done:*` (протокол агентов v1, задачи #30 и #33).
Фаза в GitHub — метка `phase:<имя>`.
"""

from dataclasses import dataclass

# --- Основной путь: от создания до прода ---

CREATED = "created"
CLASSIFIED = "classified"
BUSINESS_ANALYSIS = "business-analysis"
SYSTEM_REQUIREMENTS = "system-requirements"
GROOMED = "groomed"
READY_FOR_DEV = "ready-for-dev"
IN_DEVELOPMENT = "in-development"
PR_OPEN = "pr-open"
PR_REVIEW = "pr-review"
MERGED = "merged"
TESTING = "testing"
RELEASED = "released"

# --- Боковые состояния: сегодня существуют де-факто, но нигде не названы ---

SPAM = "spam"                # intake gate распознал спам, issue закрыт
DUPLICATE = "duplicate"      # дубликат: решение о закрытии за человеком
ANSWERED = "answered"        # классификация закрыла содержательным ответом
SKIPPED = "skipped"          # предфильтр: бот или security-sensitive
ESCALATED = "escalated"      # ушло человеку (needs-human:*)
FAILED = "failed"            # стадия сорвалась, нужен разбор
CANCELLED = "cancelled"      # снято с обработки решением человека

# Кто инициирует переход. Различать обязательно: «ждём агента» и «ждём человека» —
# это разные состояния для того, кто смотрит на очередь.
AGENT = "agent"        # сам Issue-Agent по завершении своей стадии
HUMAN = "human"        # метка или команда человека
EXTERNAL = "external"  # PR-Agent, PR-Closer, CI — внешняя система контура


@dataclass(frozen=True)
class Transition:
    to: str
    initiator: str
    trigger: str  # чем инициируется: метка, команда, событие


# Терминальные фазы: из них своим ходом выйти нельзя. `released` — успешный
# конец пути; остальные — состояния, из которых человек может вернуть Issue в
# работу, но только явным действием (см. таблицу).
TERMINAL = frozenset({RELEASED, CANCELLED})

# Таблица переходов. Пустой кортеж означает: дальше только терминальность.
#
# Решение по открытому вопросу «ветвление по типу»: один перечень с пропусками,
# а не два подмножества. Путь бага короче — он идёт `classified → ready-for-dev`
# мимо аналитики; кодировать это отдельным перечнем значило бы дублировать все
# боковые состояния.
TRANSITIONS: dict[str, tuple[Transition, ...]] = {
    CREATED: (
        Transition(CLASSIFIED, AGENT, "триаж завершён"),
        Transition(SKIPPED, AGENT, "предфильтр: бот или security-sensitive"),
        Transition(SPAM, AGENT, "intake gate: спам"),
        # Дедуп и advisor-ответ — шаги ВНУТРИ триажа, поэтому их исход виден из
        # `created`, а не только из `classified`: до конца триажа Issue ещё не
        # классифицирован формально.
        Transition(DUPLICATE, AGENT, "duplicate-check"),
        Transition(ANSWERED, AGENT, "advisor:consultation / existing-functionality"),
        Transition(ESCALATED, AGENT, "не удалось сузить запрос"),
        Transition(FAILED, AGENT, "сбой стадии"),
        Transition(CANCELLED, HUMAN, "agents:off"),
    ),
    CLASSIFIED: (
        Transition(BUSINESS_ANALYSIS, HUMAN, "run:analyze / research-me"),
        # Путь бага: аналитика не нужна, задача готова к разработке сразу.
        Transition(READY_FOR_DEV, HUMAN, "bug-me"),
        Transition(DUPLICATE, AGENT, "duplicate-check"),
        Transition(ANSWERED, AGENT, "advisor:consultation / existing-functionality"),
        Transition(ESCALATED, AGENT, "дедлайн парковки истёк"),
        Transition(FAILED, AGENT, "сбой стадии"),
        Transition(CANCELLED, HUMAN, "agents:off"),
    ),
    BUSINESS_ANALYSIS: (
        Transition(SYSTEM_REQUIREMENTS, AGENT, "цепочка FNR дошла до sysreq"),
        Transition(FAILED, AGENT, "прогон анализа сорвался"),
        Transition(ESCALATED, HUMAN, "разбор вручную"),
        Transition(CANCELLED, HUMAN, "agents:off"),
    ),
    SYSTEM_REQUIREMENTS: (
        Transition(GROOMED, HUMAN, "требования приняты"),
        # Груминг — необязательный шаг: сегодня агент публикует чеклист
        # готовности сразу после аналитики и передаёт задачу разработчику.
        # Явная приёмка требований остаётся возможностью, а не условием.
        Transition(READY_FOR_DEV, AGENT, "чеклист готовности опубликован"),
        Transition(BUSINESS_ANALYSIS, HUMAN, "актуализация: вернуть в анализ"),
        Transition(FAILED, AGENT, "сбой стадии"),
        Transition(CANCELLED, HUMAN, "agents:off"),
    ),
    GROOMED: (
        Transition(READY_FOR_DEV, AGENT, "чеклист готовности опубликован"),
        Transition(SYSTEM_REQUIREMENTS, HUMAN, "актуализация: требования изменились"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    READY_FOR_DEV: (
        Transition(IN_DEVELOPMENT, HUMAN, "разработчик взял задачу"),
        # Агент разработки на своём сервере проходит путь целиком за один шаг:
        # клон, код, проверки, пуш и PR — внутри одной активности. Промежуточной
        # фазы `in-development` у такого прогона нет не потому, что её забыли, а
        # потому, что ждать в ней нечего: результат уже здесь. Прогон в чужих
        # Actions — наоборот, уходит в `in-development` и ждёт события.
        Transition(PR_OPEN, AGENT, "агент разработки открыл PR за один шаг"),
        Transition(GROOMED, HUMAN, "актуализация постановки"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    IN_DEVELOPMENT: (
        Transition(PR_OPEN, EXTERNAL, "открыт PR с Closes #N"),
        Transition(READY_FOR_DEV, HUMAN, "задача возвращена в очередь"),
        Transition(FAILED, EXTERNAL, "шаг внешнего агента сорвался"),
        Transition(ESCALATED, EXTERNAL, "нужен человек"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    PR_OPEN: (
        Transition(PR_REVIEW, EXTERNAL, "PR-Agent начал ревью"),
        Transition(IN_DEVELOPMENT, EXTERNAL, "PR закрыт без слияния"),
        Transition(FAILED, EXTERNAL, "CI красный"),
        Transition(ESCALATED, EXTERNAL, "нужен человек"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    PR_REVIEW: (
        Transition(MERGED, EXTERNAL, "PR влит"),
        Transition(IN_DEVELOPMENT, EXTERNAL, "запрошены изменения"),
        Transition(ESCALATED, EXTERNAL, "needs-human:pr — доведение не удалось"),
        Transition(FAILED, EXTERNAL, "CI красный"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    MERGED: (
        Transition(TESTING, EXTERNAL, "отгрузка на стенд"),
        Transition(FAILED, EXTERNAL, "отгрузка сорвалась"),
        Transition(ESCALATED, EXTERNAL, "нужен человек"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    TESTING: (
        Transition(RELEASED, EXTERNAL, "выкатано в прод"),
        Transition(IN_DEVELOPMENT, HUMAN, "тестирование выявило дефект"),
        Transition(FAILED, EXTERNAL, "прогон на стенде сорвался"),
        Transition(ESCALATED, EXTERNAL, "нужен человек"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    RELEASED: (),
    # Боковые состояния — не тупики: человек возвращает Issue в работу явным
    # действием. Сегодня это невозможно в принципе (воркфлоу уже завершён), и
    # именно это чинит #36.
    SPAM: (
        Transition(CREATED, HUMAN, "разблокировать: не спам"),
        Transition(CANCELLED, HUMAN, "подтвердить спам"),
    ),
    DUPLICATE: (
        Transition(CLASSIFIED, HUMAN, "не дубликат, вернуть в работу"),
        Transition(CANCELLED, HUMAN, "подтвердить дубликат"),
    ),
    ANSWERED: (
        Transition(CLASSIFIED, HUMAN, "ответа недостаточно, нужна проработка"),
        Transition(CANCELLED, HUMAN, "вопрос закрыт"),
    ),
    SKIPPED: (
        Transition(CREATED, HUMAN, "обработать вручную"),
        Transition(CANCELLED, HUMAN, "оставить как есть"),
    ),
    ESCALATED: (
        Transition(CLASSIFIED, HUMAN, "человек разобрал и вернул в контур"),
        # Работа могла уйти человеку уже из PR-части пути: возвращать её оттуда
        # в начало значило бы потерять всё, что уже сделано.
        Transition(IN_DEVELOPMENT, HUMAN, "человек вернул задачу в разработку"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    FAILED: (
        Transition(CREATED, HUMAN, "перезапустить обработку"),
        Transition(ESCALATED, HUMAN, "разбирать вручную"),
        # Сорваться мог и шаг в PR-части: следующее событие агента (починили CI,
        # ревью продолжилось) обязано находить дорогу обратно, иначе каждое
        # такое событие уходило бы человеку заново.
        Transition(IN_DEVELOPMENT, EXTERNAL, "работа над PR продолжилась"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
    CANCELLED: (),
}

PHASES: tuple[str, ...] = tuple(TRANSITIONS)

# Метка фазы в GitHub. Инвариант: одна фаза — ровно одна метка `phase:*`, при
# переходе предыдущая снимается. Без этого по меткам нельзя восстановить
# состояние: два `phase:*` на Issue означали бы противоречие, а не историю.
PHASE_PREFIX = "phase:"

# Мост от значений query `stage` (#29) к фазам. Нужен на время перехода: пока
# `IssueLifecycle` линейный (#36 ещё не сделана), стадия — единственное, что
# воркфлоу знает о себе.
STAGE_TO_PHASE: dict[str, str] = {
    "intake": CREATED,
    "classify": CREATED,
    "duplicate-check": CLASSIFIED,
    "priority": CLASSIFIED,
    "awaiting-human-decision": CLASSIFIED,
    "analysis": BUSINESS_ANALYSIS,
    "bug": READY_FOR_DEV,
    "awaiting-build-decision": READY_FOR_DEV,
    "done": READY_FOR_DEV,
    "skipped": SKIPPED,
    "spam": SPAM,
    "duplicate": DUPLICATE,
    "answered": ANSWERED,
    "escalated": ESCALATED,
    "failed": FAILED,
    "agents-off": CANCELLED,
    # Шаги, которые ведут внешние агенты (#38). Своего дробления у них нет:
    # вся видимая деталь лежит в самом событии, поэтому стадия совпадает с
    # фазой. Мост остаётся полным — иначе query `stage` таких прогонов не
    # переводился бы в фазу обратно.
    GROOMED: GROOMED,
    IN_DEVELOPMENT: IN_DEVELOPMENT,
    PR_OPEN: PR_OPEN,
    PR_REVIEW: PR_REVIEW,
    MERGED: MERGED,
    TESTING: TESTING,
    RELEASED: RELEASED,
}


class InvalidTransition(ValueError):
    """Недопустимый переход — ошибка, а не молчаливая перезапись фазы.

    Молчаливая запись любой фазы поверх любой означала бы, что модель ничего не
    гарантирует: Issue оказывался бы в состоянии, из которого не выводится ни
    предыстория, ни следующий шаг.
    """


def phase_label(phase: str) -> str:
    return f"{PHASE_PREFIX}{phase}"


def phase_from_labels(labels: list[str]) -> str | None:
    """Фаза по набору меток Issue, иначе None.

    Инвариант «одна фаза — одна метка» проверяется здесь же: две метки `phase:*`
    означают противоречие, и мы отказываемся угадывать, какая из них настоящая.
    """
    found = [name[len(PHASE_PREFIX):].lower() for name in labels
             if name.lower().startswith(PHASE_PREFIX)]
    known = [name for name in found if name in TRANSITIONS]
    if len(known) != 1:
        return None
    return known[0]


def is_terminal(phase: str) -> bool:
    return phase in TERMINAL


def allowed(phase: str) -> tuple[Transition, ...]:
    """Переходы, возможные из фазы. Неизвестная фаза — ошибка модели."""
    if phase not in TRANSITIONS:
        raise InvalidTransition(f"неизвестная фаза: {phase!r}")
    return TRANSITIONS[phase]


def can(source: str, target: str) -> bool:
    return any(t.to == target for t in allowed(source))


def transition(source: str, target: str) -> Transition:
    """Переход или InvalidTransition с перечнем допустимых — сообщение должно
    само говорить, что было возможно вместо этого."""
    for candidate in allowed(source):
        if candidate.to == target:
            return candidate
    options = ", ".join(t.to for t in allowed(source)) or "—"
    raise InvalidTransition(
        f"переход {source} → {target} не предусмотрен; допустимо: {options}")


def initiator(source: str, target: str) -> str:
    return transition(source, target).initiator


def reachable_from(start: str = CREATED) -> set[str]:
    """Фазы, достижимые из start. Используется тестом полноты: фаза, до которой
    нельзя дойти, — мёртвая запись в словаре."""
    seen: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(t.to for t in allowed(current))
    return seen
