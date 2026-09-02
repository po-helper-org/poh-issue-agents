"""Опознание недетерминизма в логе воркера и превращение его в видимый след.

Зачем отдельный модуль. Прогон, разошедшийся с историей после выкладки, **не
падает**: Temporal валит workflow task и повторяет его бесконечно, а сам прогон
остаётся в `Running`. Снаружи это неотличимо от «задача просто стоит и ждёт
человека» — ни метки, ни комментария, ни события (#263, живой случай 25.08: 120
прогонов в Running, старейшие с 19 августа).

Отличие от прочих сбоёв контура в том, что перехватить его **изнутри** нечем:
падает не тело активности, а сам реплей воркфлоу — код, который мог бы поймать
исключение, до выполнения не доходит. Поэтому наблюдение прицепляется снаружи, к
логгеру, а не к воркфлоу.

ГДЕ ИМЕННО ЛОВИМ (проверено экспериментом на temporalio 1.9.0, а не выведено
из чтения SDK — первая редакция этого модуля ошиблась ровно здесь и не
срабатывала вовсе). Расхождение порождает две записи, и только одна из них
доезжает до Python:

1. `[TMPRL1100] Nondeterminism error: …` — это ядро на Rust, оно пишет **мимо**
   `logging`, своим трейсинг-подписчиком прямо в stderr. Пересылка в Python
   выключена по умолчанию (`LoggingConfig.forwarding=None`), так что повесить
   обработчик на эту строку нельзя.
2. `Evicting workflow with run ID <uuid>, message: … [TMPRL1100] …` — вот эта
   запись приходит в Python, от логгера `temporalio.worker._workflow`, и несёт
   в себе и идентификатор прогона, и маркер ядра. Но пишется она на **DEBUG**.

Отсюда два следствия, определяющие устройство модуля. Уровень наблюдателя —
DEBUG, а не ERROR. И раз логгер приходится опускать до DEBUG ради одной записи,
наблюдатель сделан ФИЛЬТРОМ, а не обработчиком: фильтр логгера видит запись до
обработчиков и, вернув False, не пускает её дальше. Так мы читаем нужное, а в
stdout не появляется поток отладки эвикшена, которого там раньше не было.

Модуль намеренно чистый: сеть в него не входит, отправку наружу делает
`report`-колбэк, который передаёт entrypoint (`worker/worker.py` подставляет
`sentry_setup.capture_nondeterminism`). Так логика опознания проверяется прямо,
без Temporal и без Sentry.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from typing import Callable, Optional

# Логгер, на котором живёт запись об эвикшене. Имя приватного модуля SDK — не
# контракт, поэтому оно вынесено сюда одной константой: переезд записи в
# соседний модуль обязан чиниться правкой одной строки, а тест
# `test_real_nondeterminism_reaches_the_watcher` обязан на такой переезд
# краснеть (он гоняет настоящий реплей, а не выдуманную запись).
EVICTION_LOGGER = "temporalio.worker._workflow"

# Опознаём по двум признакам сразу, и достаточно любого.
#
# `NondeterminismError` — тип исключения Python SDK (`temporalio.workflow`).
# В записи об эвикшене исключения нет, но тип доезжает там, где SDK логирует
# отказ активации с `exc_info`.
#
# `[TMPRL1100]` — код ядра, он же в тексте отказа из #263 и в тексте записи об
# эвикшене. Код стабильнее формулировки: сама фраза после него менялась между
# версиями («Activity machine does not handle this event», «Activity type of
# scheduled event … does not match…»), а код — нет. Английскую фразу оставляем
# третьей на случай сборки, где код не проставлен.
_TYPE_MARKER = "NondeterminismError"
_TEXT_MARKERS = ("[TMPRL1100]", "Nondeterminism error")

# `run ID` — формат самого SDK (`Evicting workflow with run ID <uuid>, …`).
# Разбираем текст, а не `record.args`: позиция аргумента — деталь реализации
# чужой строки формата, а идентификатор в тексте виден и в логе, по которому
# человек будет искать прогон.
_RUN_ID = re.compile(r"run ID ([0-9a-fA-F-]{36})")

# Начало причины в тексте: всё, что дальше, — различающая часть. Хвост записи
# занят служебной обёрткой ядра (`force_cause: NonDeterministicError }`) и, при
# отказе со стороны языка, стектрейсом на тысячи символов, поэтому оператору
# показываем ГОЛОВУ после маркера, а не конец строки.
_REASON_AT = "Nondeterminism error: "
_REASON_LEN = 300

# Потолок памяти дедупликации. Workflow task повторяется бесконечно, и без
# дедупликации один вставший прогон завалил бы Sentry сотнями одинаковых
# событий за час. Окно ограничено сверху: воркер живёт неделями, и
# неограниченное — это утечка на длинном аптайме.
_MAX_SEEN = 512


def is_nondeterminism(message: str, exc_type_name: str = "") -> bool:
    """Похож ли отказ на расхождение с историей.

    Оба признака необязательны по отдельности — см. комментарий у маркеров.
    """
    if exc_type_name and _TYPE_MARKER in exc_type_name:
        return True
    return any(marker in message for marker in _TEXT_MARKERS)


def run_id_from(message: str) -> Optional[str]:
    """Идентификатор прогона из текста отказа, иначе None."""
    found = _RUN_ID.search(message)
    return found.group(1) if found else None


def reason_from(message: str) -> str:
    """Причина расхождения — голова после маркера, а не хвост записи.

    Хвост — служебная обёртка ядра и, у отказов со стороны языка, стектрейс:
    показать последние N символов значит показать что угодно, кроме причины.
    """
    if _REASON_AT in message:
        return message.split(_REASON_AT, 1)[1][:_REASON_LEN]
    return message[:_REASON_LEN]


def operator_line(run_id: Optional[str], reason: str) -> str:
    """Строка для оператора: что случилось и что с этим делать.

    Отдельно от события Sentry: в stdout она попадает всегда, а Sentry
    необязателен (без `SENTRY_DSN` вся обвязка — no-op).
    """
    where = f"run_id={run_id}" if run_id else "run_id не разобран"
    return (f"НЕДЕТЕРМИНИЗМ: прогон разошёлся с историей и больше не двигается "
            f"({where}). Сам он не восстановится. Откат воркера на прежний образ "
            f"возвращает прогон в строй; правка кода вперёд — нет. "
            f"Причина: {reason}")


class Watcher(logging.Filter):
    """Наблюдатель за логом Temporal, поднимающий недетерминизм до события.

    Фильтр, а не обработчик: см. докстринг модуля — запись об эвикшене живёт на
    DEBUG, логгер ради неё приходится опускать, и фильтр позволяет прочитать её,
    не выпуская поток отладки в stdout.

    ⚠️ ГРАНИЦА С TEMPORAL. Фильтр живёт в машинерии воркера, а не в коде
    воркфлоу: его вызов в историю не попадает и на реплее не повторяется, так
    что запрет на сетевые вызовы из `workflows.py` его не касается. Ставить его
    из воркфлоу-кода тем не менее нельзя — по той же причине, по которой туда
    не зовут `sentry_setup` (см. докстринг того модуля).
    """

    def __init__(self, report: Callable[[Optional[str], str], None], *,
                 swallow_debug: bool = False):
        super().__init__()
        self._report = report
        # `swallow_debug` ставит `install()`, и только когда САМ опустил логгер
        # до DEBUG. Если DEBUG включил человек — он его и просил, глотать
        # чужую отладку мы не вправе.
        self._swallow_debug = swallow_debug
        self._log = logging.getLogger("worker")
        self._seen: deque[str] = deque()
        self._seen_set: set[str] = set()
        # Защита от рекурсии: `report` может залогировать собственный сбой,
        # запись прилетит в этот же фильтр, и `report` позовётся снова — уже на
        # своей же ошибке.
        self._busy = False

    def _already_reported(self, run_id: Optional[str]) -> bool:
        """Дедупликация по прогону. Без run_id дедуплицировать нечем — пропускаем."""
        if run_id is None:
            return False
        if run_id in self._seen_set:
            return True
        if len(self._seen) >= _MAX_SEEN:
            # Вытесняем СТАРЕЙШИЙ, а не чистим окно целиком: чистка вернула бы
            # в отчёт все ранее виденные прогоны разом, а workflow task
            # повторяется бесконечно — получился бы ровно тот поток событий,
            # ради предотвращения которого дедупликация и заведена.
            self._seen_set.discard(self._seen.popleft())
        self._seen.append(run_id)
        self._seen_set.add(run_id)
        return False

    def filter(self, record: logging.LogRecord) -> bool:
        recognised = False
        try:
            message = record.getMessage()
            exc_type_name = ""
            if record.exc_info and record.exc_info[0] is not None:
                exc_type_name = record.exc_info[0].__name__
                message = f"{message} | {record.exc_info[1]}"
            recognised = is_nondeterminism(message, exc_type_name)
            if recognised and not self._busy:
                run_id = run_id_from(message)
                if not self._already_reported(run_id):
                    reason = reason_from(message)
                    self._busy = True
                    self._log.error(operator_line(run_id, reason))
                    self._report(run_id, message[:2000])
        except Exception:  # noqa: BLE001 — наблюдатель не имеет права ронять логирование
            pass
        finally:
            self._busy = False

        # Запись пропускаем дальше, кроме отладки, которую сами же и включили:
        # до наблюдателя её в stdout не было, и появиться она не должна.
        # Опознанную запись глотаем всегда — оператору уже сказано понятнее.
        if self._swallow_debug and record.levelno <= logging.DEBUG:
            return False
        return not recognised


def install(report: Callable[[Optional[str], str], None],
            logger_name: str = EVICTION_LOGGER) -> Watcher:
    """Повесить наблюдателя на логгер Temporal и вернуть его.

    Опускает логгер до DEBUG, если он выше: нужная запись живёт там (см.
    докстринг модуля), и без этого фильтр не позовётся вовсе — `logging` не
    создаёт запись, отсечённую уровнем логгера.

    Идемпотентна. Ставится побочным эффектом импорта `worker/worker.py`, а тот
    импортируется в тестах под разными именами модуля; без защиты второй импорт
    вешал бы второго наблюдателя со своим окном дедупликации, и один вставший
    прогон докладывался бы дважды на каждое событие — ровно то, против чего
    дедупликация и написана.
    """
    log = logging.getLogger(logger_name)
    for existing in log.filters:
        if isinstance(existing, Watcher):
            return existing

    raised = not log.isEnabledFor(logging.DEBUG)
    if raised:
        log.setLevel(logging.DEBUG)
    watcher = Watcher(report, swallow_debug=raised)
    log.addFilter(watcher)
    return watcher
