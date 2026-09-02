"""Опознание недетерминизма в логе воркера и превращение его в видимый след.

Зачем отдельный модуль. Прогон, разошедшийся с историей после выкладки, **не
падает**: Temporal валит workflow task и повторяет его бесконечно, а сам прогон
остаётся в `Running`. Снаружи это неотличимо от «задача просто стоит и ждёт
человека» — ни метки, ни комментария, ни события. Единственный след — строка
`logger.exception` из `temporalio.worker._workflow`, живущая в stdout контейнера,
где её никто не читает (#263, живой случай 25.08: 120 прогонов в Running,
старейшие с 19 августа).

Отличие от прочих сбоёв контура в том, что перехватить его **изнутри** нечем:
падает не тело активности, а сам реплей воркфлоу — код, который мог бы поймать
исключение, до выполнения не доходит. Поэтому наблюдение прицепляется снаружи, к
логгеру, а не к воркфлоу.

Модуль намеренно чистый: сеть в него не входит, отправку наружу делает
`report`-колбэк, который передаёт entrypoint (`worker/worker.py` подставляет
`sentry_setup.capture_nondeterminism`). Так логика опознания проверяется прямо,
без Temporal и без Sentry.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

# Опознаём по двум признакам сразу, и достаточно любого.
#
# `NondeterminismError` — тип исключения Python SDK (`temporalio.workflow`).
# Надёжен, но доезжает не всегда: часть расхождений приходит из ядра на Rust
# уже строкой, обёрнутой в общий `RuntimeError`.
#
# `[TMPRL1100]` — код ядра, он же в тексте отказа из #263. Код стабильнее
# формулировки: сама фраза после него менялась между версиями («Activity
# machine does not handle this event», «Activity type of scheduled event … does
# not match…»), а код — нет. Английскую фразу оставляем третьей на случай
# сборки, где код не проставлен.
_TYPE_MARKER = "NondeterminismError"
_TEXT_MARKERS = ("[TMPRL1100]", "Nondeterminism error")

# `run ID` — формат самого SDK: `logger.exception("Failed handling activation on
# workflow with run ID %s", act.run_id)`. Разбираем текст, а не `record.args`:
# позиция аргумента — деталь реализации чужой строки формата, а идентификатор
# в тексте виден и в логе, по которому человек будет искать прогон.
_RUN_ID = re.compile(r"run ID ([0-9a-fA-F-]{36})")

# Потолок памяти дедупликации. Workflow task повторяется бесконечно, и без
# дедупликации один вставший прогон завалил бы Sentry сотнями одинаковых
# событий за час. Множество ограничено сверху: воркер живёт неделями, и
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


def operator_line(run_id: Optional[str], detail: str) -> str:
    """Строка для оператора: что случилось и что с этим делать.

    Отдельно от события Sentry: в stdout она попадает всегда, а Sentry
    необязателен (без `SENTRY_DSN` вся обвязка — no-op).
    """
    where = f"run_id={run_id}" if run_id else "run_id не разобран"
    return (f"НЕДЕТЕРМИНИЗМ: прогон разошёлся с историей и больше не двигается "
            f"({where}). Сам он не восстановится. Откат воркера на прежний образ "
            f"возвращает прогон в строй; правка кода вперёд — нет. "
            f"Причина: {detail}")


class Watcher(logging.Handler):
    """Наблюдатель за логом Temporal, поднимающий недетерминизм до события.

    Вешается на логгер `temporalio` в entrypoint'е воркера. Не фильтрует и не
    глушит чужие записи — только смотрит и, опознав расхождение, зовёт `report`.

    ⚠️ ГРАНИЦА С TEMPORAL. Обработчик живёт в машинерии воркера, а не в коде
    воркфлоу: его вызов в историю не попадает и на реплее не повторяется, так
    что запрет на сетевые вызовы из `workflows.py` его не касается. Ставить его
    из воркфлоу-кода тем не менее нельзя — по той же причине, по которой туда
    не зовут `sentry_setup` (см. докстринг того модуля).
    """

    def __init__(self, report: Callable[[Optional[str], str], None],
                 logger: Optional[logging.Logger] = None):
        super().__init__(level=logging.ERROR)
        self._report = report
        self._log = logger or logging.getLogger("worker")
        self._seen: set[str] = set()
        # Защита от рекурсии: `report` может залогировать собственный сбой на
        # уровне ERROR, запись прилетит в этот же обработчик, и `report`
        # позовётся снова — уже на своей же ошибке.
        self._busy = False

    def _already_reported(self, run_id: Optional[str]) -> bool:
        """Дедупликация по прогону. Без run_id дедуплицировать нечем — пропускаем."""
        if run_id is None:
            return False
        if run_id in self._seen:
            return True
        if len(self._seen) >= _MAX_SEEN:
            self._seen.clear()  # потолок достигнут — начинаем окно заново
        self._seen.add(run_id)
        return False

    def emit(self, record: logging.LogRecord) -> None:
        if self._busy:
            return
        try:
            message = record.getMessage()
            exc_type_name = ""
            if record.exc_info and record.exc_info[0] is not None:
                exc_type_name = record.exc_info[0].__name__
                # Текст самого исключения: маркер ядра `[TMPRL1100]` живёт в
                # нём, а не в строке формата SDK («Failed handling activation…»).
                message = f"{message} | {record.exc_info[1]}"
            if not is_nondeterminism(message, exc_type_name):
                return

            run_id = run_id_from(message)
            if self._already_reported(run_id):
                return

            self._busy = True
            self._log.error(operator_line(run_id, message[-500:]))
            self._report(run_id, message[-2000:])
        except Exception:  # noqa: BLE001 — наблюдатель не имеет права ронять логирование
            self.handleError(record)
        finally:
            self._busy = False


def install(report: Callable[[Optional[str], str], None],
            logger_name: str = "temporalio") -> Watcher:
    """Повесить наблюдателя на логгер Temporal и вернуть его.

    Логгер именно `temporalio`, а не конкретный `temporalio.worker._workflow`:
    имя приватного модуля SDK — не контракт, и переезд записи в соседний модуль
    не должен молча выключать наблюдение. Уровень обработчика (`ERROR`) сам
    отсекает лишнее.
    """
    watcher = Watcher(report)
    logging.getLogger(logger_name).addHandler(watcher)
    return watcher
