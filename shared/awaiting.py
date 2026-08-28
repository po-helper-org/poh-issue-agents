"""Ожидание как первоклассное состояние: кого ждём, с какого момента, до какого срока.

Сегодня все ожидания выглядят одинаково — как их отсутствие. Прогон,
припаркованный до решения человека, в Temporal UI просто `Running`; на Issue
видна метка приоритета, из которой не следует, что ход за человеком; а сбой
вообще не был ожиданием — он вешал метку и закрывал прогон.

Фаза (#35) отвечает на вопрос «где Issue», это состояние работы. `Awaiting`
отвечает на другой — «почему он там стоит и кто его сдвинет». Одна фаза может
ждать разного: `failed` ждёт решения человека о перезапуске, `pr-review` — что
внешний агент доведёт ревью. Мешать это в одну ось значило бы либо плодить
фазы под каждую причину, либо терять причину.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub.
"""

from dataclasses import dataclass

from shared import lifecycle

# --- Виды ожидания ---

HUMAN_DECISION = "human-decision"        # ждём метку/команду человека
APPROVAL = "approval"                    # ждём приёмку сделанного
TESTING = "testing"                      # ждём прогон на стенде
EXTERNAL_AGENT = "external-agent"        # ждём соседний сервис контура
FAILURE_RECOVERY = "failure-recovery"    # шаг сорвался, ждём решения человека

KINDS: tuple[str, ...] = (HUMAN_DECISION, APPROVAL, TESTING,
                          EXTERNAL_AGENT, FAILURE_RECOVERY)

# Кого ждём — человека или машину. Разница не косметическая: выборка
# `label:needs-human:*` обязана быть ПОЛНОЙ очередью к людям, а значит метку
# нельзя вешать на ожидание внешнего агента или стенда — иначе очередь
# наполнится задачами, по которым человеку делать нечего.
BLOCKED_ON_HUMAN: frozenset[str] = frozenset({HUMAN_DECISION, APPROVAL, FAILURE_RECOVERY})

# Открытый вопрос постановки: «kind → действие по истечении».
#
# Решение: действие ОДНО для всех видов — передать человеку. Разные исходы
# (пинг, повышение приоритета, автоотмена) требуют знать, кому пинговать и чем
# рискует автоотмена; ни того, ни другого контур сегодня не знает, а
# додумывать политику за владельца процесса — худший вид самодеятельности.
#
# Различается не действие, а СРОК: сколько разумно ждать, прежде чем признать
# ожидание застрявшим. Вот он и вынесен в таблицу.
DEFAULT_DEADLINE_HOURS: dict[str, int] = {
    HUMAN_DECISION: 72,      # решение о тяжёлой стадии: рабочие сутки плюс выходные
    APPROVAL: 72,            # приёмка — то же ожидание человека, что и решение
    TESTING: 48,             # прогон на стенде: дольше суток означает, что он завис
    EXTERNAL_AGENT: 24,      # сосед либо отвечает быстро, либо не отвечает вовсе
    FAILURE_RECOVERY: 168,   # разбор сбоя реже срочный; неделя — чтобы не потерялся
}


class InvalidAwaiting(ValueError):
    """Ожидание описано некорректно.

    Отдельный тип: фаза ожидания без заполненного `Awaiting` — ошибка, а не
    пустое поле. Молчаливое «ждём неизвестно чего» и есть то состояние, ради
    ухода от которого задача ставилась.
    """


@dataclass
class Awaiting:
    """Чего ждёт Issue прямо сейчас.

    `who` — свободная строка намеренно. Открытый вопрос постановки «роль или
    логин» решён в пользу «и то, и другое»: ждать можно и конкретного человека
    (`@kibarik`), и роль (`команда подбора`), и сервис (`pr-agent`). Тип-union
    добавил бы ветвление везде, где эту строку только показывают.

    Время — epoch-секунды, а не datetime: значение переносится через
    continue-as-new и обязано сериализоваться без сюрпризов.
    """

    kind: str
    who: str
    reason: str
    since_epoch: float
    deadline_epoch: float = 0.0  # 0 — ожидание без срока

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise InvalidAwaiting(
                f"вид ожидания {self.kind!r} не из перечня; допустимо: {', '.join(KINDS)}")
        if not str(self.reason).strip():
            raise InvalidAwaiting("ожидание без причины: человек не поймёт, чего от него ждут")
        if not str(self.who).strip():
            raise InvalidAwaiting("ожидание без адресата: непонятно, кто его снимет")

    @property
    def blocks_on_human(self) -> bool:
        return self.kind in BLOCKED_ON_HUMAN

    def waited_hours(self, now_epoch: float) -> float:
        return max(0.0, (now_epoch - self.since_epoch) / 3600)

    def remaining_hours(self, now_epoch: float) -> float | None:
        """Сколько ещё ждать. None — ожидание без срока."""
        if not self.deadline_epoch:
            return None
        return max(0.0, (self.deadline_epoch - now_epoch) / 3600)

    def expired(self, now_epoch: float) -> bool:
        return bool(self.deadline_epoch) and now_epoch >= self.deadline_epoch

    def describe(self, now_epoch: float) -> str:
        """Строка для человека: чего ждём, от кого, сколько уже и сколько осталось."""
        parts = [self.reason, f"ждём: {self.who}", f"уже {self.waited_hours(now_epoch):.0f} ч"]
        left = self.remaining_hours(now_epoch)
        parts.append("без срока" if left is None else f"осталось {left:.0f} ч")
        return "; ".join(parts)


def deadline_hours(kind: str, override: int | None = None) -> int:
    """Срок ожидания: переопределение сильнее таблицы по умолчанию.

    Переопределение нужно там, где срок уже настраивается оператором
    (`PARK_*_HOURS`): две независимые ручки на один таймер разъехались бы при
    первой же правке одной из них.
    """
    if override is not None and override > 0:
        return override
    if kind not in DEFAULT_DEADLINE_HOURS:
        raise InvalidAwaiting(f"нет срока по умолчанию для вида {kind!r}")
    return DEFAULT_DEADLINE_HOURS[kind]


# --- Чего ждёт каждая фаза ---
#
# Явная таблица, а не вывод из инициаторов переходов. Вывод соблазнителен и
# неверен: у `failed` есть внешний переход («работа над PR продолжилась»), но
# ждёт эта фаза человека — решения о перезапуске. Кого ждём и кто теоретически
# способен сдвинуть — разные вопросы, и угадывать второй вместо первого значит
# складывать разбор сбоя в очередь к машинам, где его никто не увидит.

KIND_BY_PHASE: dict[str, str] = {
    lifecycle.CLASSIFIED: HUMAN_DECISION,
    lifecycle.PRODUCT_RESEARCH: EXTERNAL_AGENT,
    lifecycle.READY_FOR_DEV: APPROVAL,
    lifecycle.GROOMED: HUMAN_DECISION,
    lifecycle.IN_DEVELOPMENT: EXTERNAL_AGENT,
    lifecycle.PR_OPEN: EXTERNAL_AGENT,
    lifecycle.PR_REVIEW: EXTERNAL_AGENT,
    lifecycle.MERGED: EXTERNAL_AGENT,
    lifecycle.TESTING: TESTING,
    lifecycle.FAILED: FAILURE_RECOVERY,
    lifecycle.ESCALATED: HUMAN_DECISION,
    lifecycle.SPAM: HUMAN_DECISION,
    lifecycle.DUPLICATE: HUMAN_DECISION,
    lifecycle.ANSWERED: HUMAN_DECISION,
    lifecycle.SKIPPED: HUMAN_DECISION,
}

# Фазы, в которых цикл РАБОТАЕТ, а не ждёт: у них нет точки парковки вовсе.
#
# Метка очереди к людям снимается на парковке — но если следующей парковки нет,
# снимать её некому, и задача, которую прямо сейчас ведёт агент, остаётся в
# выборке `label:needs-human:*`. Раньше это было незаметно: до `business-analysis`
# доходили только из `classified`, где метки и не было. Переход `failed →
# business-analysis` (повторный `/analyze`) сделал путь достижимым из фазы, где
# метка висит.
#
# Список короткий намеренно. `ready-for-dev` сюда не входит: без автостарта он
# честно ждёт человека, а `_enter` не знает, включён ли автостарт, — и снятая
# здесь метка тут же вернулась бы парковкой.
WORKED_BY_AGENT: frozenset[str] = frozenset({
    lifecycle.CREATED, lifecycle.BUSINESS_ANALYSIS, lifecycle.SYSTEM_REQUIREMENTS,
    lifecycle.PRODUCT_RESEARCH,
})

WHO_BY_KIND: dict[str, str] = {
    HUMAN_DECISION: "человек: автор Issue или дежурный по триажу",
    APPROVAL: "разработчик из очереди `ready-for-dev`",
    TESTING: "стенд",
    EXTERNAL_AGENT: "контур: PR-Agent, PR-Closer, CI",
    FAILURE_RECOVERY: "человек: разобрать сорвавшийся шаг",
}

REASON_BY_PHASE: dict[str, str] = {
    lifecycle.CLASSIFIED: "решение о тяжёлой стадии: `research-me` либо `bug-me`",
    lifecycle.PRODUCT_RESEARCH: "продуктовое исследование гипотезы",
    lifecycle.READY_FOR_DEV: "возьмут ли задачу в разработку (`build-me`)",
    lifecycle.GROOMED: "передача задачи в разработку",
    lifecycle.IN_DEVELOPMENT: "открытие PR по задаче",
    lifecycle.PR_OPEN: "начало ревью",
    lifecycle.PR_REVIEW: "исход ревью: влить либо запросить изменения",
    lifecycle.MERGED: "отгрузка на стенд",
    lifecycle.TESTING: "результат прогона на стенде",
    lifecycle.FAILED: "разбор сорвавшегося шага: перезапустить, "
                      "передать человеку или отменить",
    lifecycle.ESCALATED: "ручной разбор: вернуть в работу сигналом `reopen`",
    lifecycle.SPAM: "подтвердить спам либо вернуть Issue в работу",
    lifecycle.DUPLICATE: "подтвердить дубликат либо вернуть Issue в работу",
    lifecycle.ANSWERED: "достаточно ли ответа, или нужна проработка",
    lifecycle.SKIPPED: "обработать вручную либо оставить как есть",
}


def kind_for_phase(phase: str) -> str:
    return KIND_BY_PHASE.get(phase, HUMAN_DECISION)


def who_for_phase(phase: str) -> str:
    return WHO_BY_KIND[kind_for_phase(phase)]


def reason_for_phase(phase: str) -> str:
    return REASON_BY_PHASE.get(phase, f"событие, двигающее фазу `{phase}`")
