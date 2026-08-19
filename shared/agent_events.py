"""Контракт «событие внешнего агента → факт в жизни Issue».

Публичный интерфейс для соседних сервисов контура (PR-Agent, PR-Closer, CI).
Это не общая шина и не общий код: у них свой релизный цикл и своя
ответственность, а здесь — один типизированный конверт и одно правило
корреляции.

Почему HTTP, а не прямая сигнализация по Temporal-handle. `poh-pr-agents` —
сервис поверх GitHub App, Temporal он не использует вовсе. Общий namespace
потребовал бы втащить в него SDK, сетевой доступ к кластеру и знание наших
workflow id; это ровно та связность, ради ухода от которой задача и ставилась.
HTTP с подписью — транспорт, на котором соседний сервис уже говорит.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub. Разбор и корреляция
проверяются напрямую, как в `shared/lifecycle.py` и `worker/estimation.py`.
"""

import re
from dataclasses import dataclass, field

from shared import lifecycle

# --- Статусы события. Фазу называет агент, статус уточняет её исход ---

STARTED = "started"      # работа началась: PR открыт, ревью взято в работу
SUCCEEDED = "succeeded"  # шаг закрыт успешно: PR влит, тесты зелёные
FAILED = "failed"        # шаг не удался: CI красный, доведение не получилось
BLOCKED = "blocked"      # нужен человек: ревью запросило решение

STATUSES = frozenset({STARTED, SUCCEEDED, FAILED, BLOCKED})


class InvalidAgentEvent(ValueError):
    """Событие не соответствует контракту.

    Отдельный тип, а не голый ValueError: вебхук отвечает на него 400, и от
    ошибок обработки его надо отличать — иначе соседний сервис будет ретраить
    заведомо некорректный конверт.
    """


@dataclass
class AgentEvent:
    """Факт, о котором внешний агент докладывает циклу Issue.

    `phase` — из общего словаря фаз (#35). Это единственное место, где контракт
    касается нашей внутренней модели, и касается намеренно: словарь заявлен
    общим на весь контур, иначе трассировка собиралась бы из несовместимых
    кусков.

    `ref` — то, о чём событие: номер PR, имя ветки, идентификатор прогона CI.
    Он же ключ идемпотентности вместе со статусом: повторная доставка одного
    факта не должна двигать фазу дважды.
    """

    repo: str
    agent: str
    phase: str
    status: str
    ref: str
    root_issue: int | None = None
    detail: str = ""
    # Ревизия, о которой факт: коммит, по которому шло ревью или прогон CI.
    # Входит в ключ идемпотентности — без неё каждый круг правок докладывал одну
    # и ту же тройку `(ref, phase, status)`, и второй доклад отбрасывался как
    # повторная доставка. Круг правок физически не мог пройти дважды.
    #
    # Необязательна намеренно: соседи со своим релизным циклом её не присылают, и
    # для них ключ остаётся прежним.
    revision: str = ""
    # Заполняется корреляцией, а не отправителем: как именно опознали Issue.
    # Нужно человеку, когда он разбирает спорный случай.
    correlation: str = field(default="", compare=False)

    def key(self) -> str:
        """Ключ идемпотентности: один факт — один переход.

        Фаза входит в ключ, хотя постановка называла пару `(ref, status)`. Без
        неё `pr-open/started` и `pr-review/started` по одному PR — один ключ, и
        начало ревью потерялось бы как «повторная доставка открытия». Статуса
        мало: `started` сопровождает каждый шаг пути.
        """
        base = f"{self.ref}:{self.phase}:{self.status}"
        return f"{base}:{self.revision}" if self.revision else base


def parse_event(payload: dict) -> AgentEvent:
    """Разбор конверта с проверками, которые дешевле сделать на входе.

    Проверяем ровно то, от чего зависит дальнейшая обработка: фаза обязана быть
    из словаря, статус — из перечня. Всё остальное (кто агент, что в detail)
    контур не интерпретирует и потому не валидирует: лишняя строгость на
    публичном контракте ломает соседей на каждой их правке.
    """
    if not isinstance(payload, dict):
        raise InvalidAgentEvent("ожидается объект")

    missing = [f for f in ("repo", "agent", "phase", "status", "ref")
               if not str(payload.get(f) or "").strip()]
    if missing:
        raise InvalidAgentEvent(f"не заполнено: {', '.join(missing)}")

    phase = str(payload["phase"]).strip()
    if phase not in lifecycle.TRANSITIONS:
        raise InvalidAgentEvent(
            f"фаза {phase!r} не из словаря; допустимо: {', '.join(lifecycle.PHASES)}")

    status = str(payload["status"]).strip()
    if status not in STATUSES:
        raise InvalidAgentEvent(
            f"статус {status!r} не из перечня; допустимо: {', '.join(sorted(STATUSES))}")

    root = payload.get("root_issue")
    if root is not None:
        try:
            root = int(root)
        except (TypeError, ValueError):
            raise InvalidAgentEvent(f"root_issue не число: {root!r}") from None
        if root <= 0:
            raise InvalidAgentEvent(f"root_issue должен быть положительным: {root}")

    return AgentEvent(
        repo=str(payload["repo"]).strip(),
        agent=str(payload["agent"]).strip(),
        phase=phase,
        status=status,
        ref=str(payload["ref"]).strip(),
        root_issue=root,
        detail=str(payload.get("detail") or ""),
        revision=str(payload.get("revision") or "").strip(),
    )


# --- Корреляция «работа → Issue» ---

# `Closes #12`, `fixes #12`, `resolved #12` — формы, которые GitHub считает
# закрывающими. Держим их же: расхождение означало бы, что PR закрывает Issue,
# а контур этого не видит.
_CLOSES_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)", re.IGNORECASE)

# Конвенция веток артефактов — та же, что у аналитики и багфикса.
_BRANCH_RE = re.compile(r"\b(?:research|bug)/issue-(\d+)\b")


def parse_closes(text: str | None) -> list[int]:
    """Все номера, которые текст объявляет закрываемыми."""
    if not text:
        return []
    seen: list[int] = []
    for raw in _CLOSES_RE.findall(text):
        number = int(raw)
        if number not in seen:
            seen.append(number)
    return seen


def issue_from_branch(ref: str | None) -> int | None:
    """Номер Issue из имени ветки артефактов, иначе None."""
    if not ref:
        return None
    match = _BRANCH_RE.search(ref)
    return int(match.group(1)) if match else None


def correlate(event: AgentEvent) -> tuple[int | None, str]:
    """Какому Issue принадлежит работа. Возвращает (номер, чем опознали).

    Источники по убыванию надёжности: явное поле → `Closes #N` в теле →
    конвенция имени ветки. Первый сработавший выигрывает: смешивать их
    голосованием нельзя, у них разная достоверность.

    Неоднозначность НЕ разрешается догадкой. Если тело объявляет закрываемыми
    несколько Issue, выбирать «первый попавшийся» значит молча привязать работу
    не к той задаче — а именно на этой связи держится вся трассировка. Такой
    случай уходит человеку.
    """
    if event.root_issue is not None:
        return event.root_issue, "поле root_issue"

    closes = parse_closes(event.detail)
    if len(closes) == 1:
        return closes[0], "Closes #N в теле"
    if len(closes) > 1:
        listed = ", ".join(f"#{n}" for n in closes)
        return None, f"тело закрывает несколько Issue ({listed}) — какой из них, решает человек"

    from_branch = issue_from_branch(event.ref)
    if from_branch is not None:
        return from_branch, "конвенция имени ветки"

    return None, "ни root_issue, ни Closes #N, ни ветки вида research|bug/issue-N"


# --- Отображение события в переход фазы ---

def target_phase(event: AgentEvent) -> str:
    """В какую фазу событие переводит Issue.

    Провалившийся или заблокированный шаг — не та фаза, которую агент назвал:
    он сообщает, ГДЕ работа, а исход решает, куда двигаться дальше. `failed`
    ведёт в `failed`, `blocked` — к человеку; обе фазы возвратные, и человек
    вернёт Issue в работу сигналом.
    """
    if event.status == FAILED:
        return lifecycle.FAILED
    if event.status == BLOCKED:
        return lifecycle.ESCALATED
    return event.phase
