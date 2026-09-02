"""Наблюдатель за расхождением с историей: опознание, дедупликация, безвредность.

Отказ, ради которого написан (#263, стенд 25.08): выкладка нового образа при
120 незакрытых прогонах убила шедшее воркфлоу, и след остался только строкой в
stdout контейнера. Перехватить изнутри нечем — падает сам реплей, а не тело
активности, — поэтому наблюдение висит на логгере Temporal.

Сеть не трогаем: `report` — колбэк, и тесты подставляют список вместо Sentry.
"""
import logging

import pytest

from shared import nondeterminism


# --- Опознание ---

def test_recognises_core_code():
    """Код ядра `[TMPRL1100]` — самый стабильный признак: формулировка после
    него менялась между версиями, код — нет."""
    assert nondeterminism.is_nondeterminism(
        "[TMPRL1100] Nondeterminism error: Activity type of scheduled event "
        "'set_phase' does not match activity type of activity command "
        "'trigger_openhands_resolver'")


def test_recognises_english_phrase_without_code():
    """Сборка без проставленного кода — ловим по фразе."""
    assert nondeterminism.is_nondeterminism(
        "Nondeterminism error: Timer machine does not handle this event")


def test_recognises_by_exception_type():
    """Тип из Python SDK — второй независимый признак."""
    assert nondeterminism.is_nondeterminism("что угодно", "NondeterminismError")


def test_ordinary_failure_is_not_nondeterminism():
    """Обычный отказ активности мимо: иначе наблюдатель завалил бы Sentry
    событиями обо всём подряд, и главный отказ утонул бы среди них."""
    assert not nondeterminism.is_nondeterminism(
        "claude -p exit 1: API Error: Request rejected (429)", "RuntimeError")
    assert not nondeterminism.is_nondeterminism(
        "Activity task failed", "ApplicationError")


# --- Разбор run_id ---

def test_extracts_run_id():
    got = nondeterminism.run_id_from(
        "Failed handling activation on workflow with run ID "
        "9e2083d9-22f5-45da-80a9-4635aa2b364c")
    assert got == "9e2083d9-22f5-45da-80a9-4635aa2b364c"


def test_missing_run_id_is_none():
    assert nondeterminism.run_id_from("Nondeterminism error: без идентификатора") is None


def test_operator_line_names_the_cure():
    """Оператору нужно не «что-то сломалось», а что с этим делать: правка
    вперёд не лечит, лечит откат."""
    line = nondeterminism.operator_line("abc-123", "[TMPRL1100] Nondeterminism error")
    assert "abc-123" in line
    assert "Откат" in line


# --- Наблюдатель ---

def _record(message: str, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("temporalio.worker._workflow", logging.ERROR,
                             __file__, 1, message, (), exc_info)


def _watcher():
    seen = []
    return nondeterminism.Watcher(lambda run_id, msg: seen.append((run_id, msg))), seen


def test_reports_nondeterminism():
    watcher, seen = _watcher()
    watcher.emit(_record(
        "Failed handling activation on workflow with run ID "
        "9e2083d9-22f5-45da-80a9-4635aa2b364c | [TMPRL1100] Nondeterminism error"))
    assert seen == [("9e2083d9-22f5-45da-80a9-4635aa2b364c",
                     "Failed handling activation on workflow with run ID "
                     "9e2083d9-22f5-45da-80a9-4635aa2b364c | [TMPRL1100] Nondeterminism error")]


def test_reads_marker_from_exception_text():
    """Маркер ядра живёт в тексте ИСКЛЮЧЕНИЯ, а строка формата SDK — просто
    «Failed handling activation…». Смотреть только на неё значит не опознать
    ничего."""
    watcher, seen = _watcher()
    try:
        raise RuntimeError("[TMPRL1100] Nondeterminism error: Activity machine "
                           "does not handle this event")
    except RuntimeError:
        import sys
        watcher.emit(_record(
            "Failed handling activation on workflow with run ID "
            "11111111-2222-3333-4444-555555555555", sys.exc_info()))
    assert len(seen) == 1
    assert seen[0][0] == "11111111-2222-3333-4444-555555555555"


def test_ignores_ordinary_errors():
    watcher, seen = _watcher()
    watcher.emit(_record("Activity task failed on workflow with run ID "
                         "9e2083d9-22f5-45da-80a9-4635aa2b364c"))
    assert seen == []


def test_deduplicates_by_run_id():
    """Workflow task повторяется бесконечно. Без дедупликации один вставший
    прогон дал бы сотни одинаковых событий за час."""
    watcher, seen = _watcher()
    message = ("Failed handling activation on workflow with run ID "
               "9e2083d9-22f5-45da-80a9-4635aa2b364c | [TMPRL1100] Nondeterminism error")
    for _ in range(50):
        watcher.emit(_record(message))
    assert len(seen) == 1


def test_different_runs_report_separately():
    """Дедупликация по прогону, а не глобальная: одна выкладка бьёт по многим
    прогонам, и молчание о втором скрыло бы масштаб."""
    watcher, seen = _watcher()
    for run_id in ("11111111-1111-1111-1111-111111111111",
                   "22222222-2222-2222-2222-222222222222"):
        watcher.emit(_record(f"run ID {run_id} | [TMPRL1100] Nondeterminism error"))
    assert len(seen) == 2


def test_seen_set_is_bounded():
    """Воркер живёт неделями — неограниченное множество было бы утечкой."""
    watcher, _ = _watcher()
    for i in range(nondeterminism._MAX_SEEN + 10):
        watcher.emit(_record(
            f"run ID {i:08d}-0000-0000-0000-000000000000 | [TMPRL1100] Nondeterminism error"))
    assert len(watcher._seen) <= nondeterminism._MAX_SEEN


def test_failing_report_does_not_break_logging():
    """Наблюдатель не имеет права ронять логирование: он висит на общем логгере
    Temporal, и его сбой остановил бы вывод всего воркера."""
    def explode(run_id, message):
        raise RuntimeError("Sentry недоступен")

    watcher = nondeterminism.Watcher(explode)
    watcher.emit(_record("run ID 33333333-3333-3333-3333-333333333333 "
                         "| [TMPRL1100] Nondeterminism error"))  # не бросает


def test_report_logging_at_error_does_not_recurse():
    """`report`, залогировавший собственный сбой на ERROR, прилетел бы в этот же
    обработчик и позвал `report` снова — на своей же ошибке."""
    calls = []

    def report_that_logs(run_id, message):
        calls.append(run_id)
        logging.getLogger("temporalio.worker._workflow").error(
            "[TMPRL1100] Nondeterminism error: отчёт не ушёл, run ID "
            "44444444-4444-4444-4444-444444444444")

    watcher = nondeterminism.Watcher(report_that_logs)
    log = logging.getLogger("temporalio.worker._workflow")
    log.addHandler(watcher)
    try:
        log.error("run ID 55555555-5555-5555-5555-555555555555 "
                  "| [TMPRL1100] Nondeterminism error")
    finally:
        log.removeHandler(watcher)
    assert calls == ["55555555-5555-5555-5555-555555555555"]


def test_install_attaches_to_temporalio_logger():
    """Логгер именно `temporalio`, а не приватный `temporalio.worker._workflow`:
    имя приватного модуля SDK — не контракт."""
    seen = []
    watcher = nondeterminism.install(lambda run_id, msg: seen.append(run_id))
    log = logging.getLogger("temporalio")
    try:
        assert watcher in log.handlers
        logging.getLogger("temporalio.worker._workflow").error(
            "run ID 66666666-6666-6666-6666-666666666666 "
            "| [TMPRL1100] Nondeterminism error")
        assert seen == ["66666666-6666-6666-6666-666666666666"]
    finally:
        log.removeHandler(watcher)


@pytest.mark.parametrize("level", [logging.INFO, logging.WARNING])
def test_below_error_is_not_reported(level):
    """Уровень обработчика (ERROR) сам отсекает шум — это и позволяет вешать его
    на весь логгер `temporalio`, а не на конкретный модуль."""
    seen = []
    watcher = nondeterminism.install(lambda run_id, msg: seen.append(run_id))
    log = logging.getLogger("temporalio")
    try:
        log.log(level, "run ID 77777777-7777-7777-7777-777777777777 "
                       "| [TMPRL1100] Nondeterminism error")
        assert seen == []
    finally:
        log.removeHandler(watcher)


def test_reported_even_without_a_run_id():
    """Без разобранного run_id дедуплицировать нечем — но молчать нельзя:
    отказ, о котором не сказали, ничем не лучше прежней строки в stdout."""
    watcher, seen = _watcher()
    watcher.emit(_record("[TMPRL1100] Nondeterminism error: без идентификатора"))
    assert len(seen) == 1
    assert seen[0][0] is None
