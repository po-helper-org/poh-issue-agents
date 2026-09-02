"""Наблюдатель за расхождением с историей: опознание, дедупликация, безвредность.

Отказ, ради которого написан (#263, стенд 25.08): выкладка нового образа при
120 незакрытых прогонах убила шедшее воркфлоу, и след остался только строкой в
stdout контейнера. Перехватить изнутри нечем — падает сам реплей, а не тело
активности, — поэтому наблюдение висит на логгере Temporal.

ГЛАВНЫЙ ТЕСТ ЗДЕСЬ — `test_real_nondeterminism_reaches_the_watcher`: он гоняет
НАСТОЯЩИЙ реплей испорченной истории и проверяет, что наблюдатель сработал.
Первая редакция модуля висела на ERROR, а нужная запись приходит на DEBUG — и
все остальные тесты этого файла были зелёными, потому что собирали `LogRecord`
руками, то есть проверяли согласие теста с самим собой. Запись, которую SDK не
выдаёт, проверять бессмысленно; ловушка стоит именно здесь.

Сеть не трогаем: `report` — колбэк, и тесты подставляют список вместо Sentry.
"""
import gzip
import logging
import sys
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

import workflows as wf

from shared import nondeterminism

ROOT = Path(__file__).resolve().parent.parent


# --- Сквозной путь: настоящий недетерминизм доходит до наблюдателя ---

def _workflow_classes() -> list[type]:
    return [getattr(wf, n) for n in dir(wf)
            if n[0].isupper() and hasattr(getattr(wf, n), "__temporal_workflow_definition")]


def _broken_history() -> WorkflowHistory:
    """Настоящая записанная история с подменённым типом активности.

    Подменяем тип, а не портим JSON: расхождение обязано прийти от самого
    Temporal, а не от разбора файла, иначе тест проверял бы не то."""
    path = sorted((ROOT / "tests" / "replay" / "histories").glob("*.json.gz"))[0]
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    data = WorkflowHistory.from_json("issue-broken", raw).to_json_dict()
    for event in data["events"]:
        scheduled = event.get("activityTaskScheduledEventAttributes")
        if scheduled:
            scheduled["activityType"]["name"] = "НетТакойАктивности"
            break
    else:  # pragma: no cover — фикстура без активностей сделала бы тест пустым
        pytest.fail("в фикстуре нет ни одной запланированной активности")
    return WorkflowHistory.from_json("issue-broken", data)


async def test_real_nondeterminism_reaches_the_watcher():
    """Ловушка на устройство SDK: запись об эвикшене живёт на DEBUG, и
    наблюдатель обязан её видеть. Красный тест здесь означает, что «видимый
    след» снова невидим — как было в первой редакции модуля."""
    seen = []
    watcher = nondeterminism.install(lambda run_id, msg: seen.append((run_id, msg)))
    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    try:
        with pytest.raises(Exception):
            await Replayer(workflows=_workflow_classes()).replay_workflow(_broken_history())
        assert len(seen) == 1, "наблюдатель не увидел настоящее расхождение"
        run_id, message = seen[0]
        assert run_id is not None and len(run_id) == 36
        assert "[TMPRL1100]" in message
    finally:
        log.removeFilter(watcher)
        log.setLevel(logging.NOTSET)


def test_watcher_does_not_leak_debug_into_stdout(caplog):
    """Логгер опущен до DEBUG ради одной записи. Если бы фильтр её пропускал,
    в stdout воркера пошёл бы поток отладки эвикшена, которого там не было."""
    watcher = nondeterminism.install(lambda run_id, msg: None)
    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    try:
        with caplog.at_level(logging.DEBUG, logger=nondeterminism.EVICTION_LOGGER):
            log.debug("Evicting workflow with run ID "
                      "9e2083d9-22f5-45da-80a9-4635aa2b364c, message: обычный эвикшен")
        assert caplog.records == []
    finally:
        log.removeFilter(watcher)
        log.setLevel(logging.NOTSET)


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


# --- Разбор ---

def test_extracts_run_id():
    got = nondeterminism.run_id_from(
        "Evicting workflow with run ID 9e2083d9-22f5-45da-80a9-4635aa2b364c, message: …")
    assert got == "9e2083d9-22f5-45da-80a9-4635aa2b364c"


def test_missing_run_id_is_none():
    assert nondeterminism.run_id_from("Nondeterminism error: без идентификатора") is None


def test_reason_is_taken_from_the_head_not_the_tail():
    """Хвост записи — служебная обёртка ядра и стектрейс. Показать последние N
    символов значит показать что угодно, кроме причины."""
    message = ("Evicting workflow with run ID x, message: [TMPRL1100] Nondeterminism "
               "error: Activity machine does not handle this event"
               ', stack_trace: "' + "мусор" * 500 + '" force_cause: NonDeterministicError }')
    reason = nondeterminism.reason_from(message)
    assert reason.startswith("Activity machine does not handle this event")
    assert "мусор" not in reason[:60]


def test_reason_without_marker_falls_back_to_the_head():
    assert nondeterminism.reason_from("что-то пошло не так").startswith("что-то")


def test_operator_line_names_the_cure():
    """Оператору нужно не «что-то сломалось», а что с этим делать: правка
    вперёд не лечит, лечит откат."""
    line = nondeterminism.operator_line("abc-123", "Activity machine …")
    assert "abc-123" in line
    assert "Откат" in line


# --- Наблюдатель на собранных записях ---

def _record(message: str, exc_info=None,
            level: int = logging.DEBUG) -> logging.LogRecord:
    return logging.LogRecord(nondeterminism.EVICTION_LOGGER, level,
                             __file__, 1, message, (), exc_info)


def _watcher(**kwargs):
    seen = []
    return nondeterminism.Watcher(lambda run_id, msg: seen.append((run_id, msg)),
                                  **kwargs), seen


EVICTION = ("Evicting workflow with run ID 9e2083d9-22f5-45da-80a9-4635aa2b364c, "
            "message: Workflow activation completion failed: "
            "[TMPRL1100] Nondeterminism error: Activity machine does not handle this event")


def test_reports_nondeterminism():
    watcher, seen = _watcher()
    watcher.filter(_record(EVICTION))
    assert len(seen) == 1
    assert seen[0][0] == "9e2083d9-22f5-45da-80a9-4635aa2b364c"


def test_reads_marker_from_exception_text():
    """Маркер может жить в тексте ИСКЛЮЧЕНИЯ, а не в строке формата."""
    watcher, seen = _watcher()
    try:
        raise RuntimeError("[TMPRL1100] Nondeterminism error: Activity machine "
                           "does not handle this event")
    except RuntimeError:
        watcher.filter(_record("Failed handling activation on workflow with run ID "
                               "11111111-2222-3333-4444-555555555555", sys.exc_info()))
    assert len(seen) == 1
    assert seen[0][0] == "11111111-2222-3333-4444-555555555555"


def test_ordinary_record_passes_through():
    """Чужие записи наблюдатель не глотает и не докладывает."""
    watcher, seen = _watcher()
    assert watcher.filter(_record("Activity task failed", level=logging.INFO)) is True
    assert seen == []


def test_recognised_record_is_swallowed():
    """Опознанную запись дальше не пускаем: оператору уже сказано понятнее,
    а сырая обёртка ядра в stdout только сбивает."""
    watcher, _ = _watcher()
    assert watcher.filter(_record(EVICTION, level=logging.ERROR)) is False


def test_debug_passes_through_when_operator_asked_for_it():
    """DEBUG глотаем, только если сами его и включили. Отладку, которую
    попросил человек, забирать у него нельзя."""
    watcher, _ = _watcher(swallow_debug=False)
    assert watcher.filter(_record("обычный эвикшен", level=logging.DEBUG)) is True


def test_deduplicates_by_run_id():
    """Workflow task повторяется бесконечно. Без дедупликации один вставший
    прогон дал бы сотни одинаковых событий за час."""
    watcher, seen = _watcher()
    for _ in range(50):
        watcher.filter(_record(EVICTION))
    assert len(seen) == 1


def test_different_runs_report_separately():
    """Дедупликация по прогону, а не глобальная: одна выкладка бьёт по многим
    прогонам, и молчание о втором скрыло бы масштаб."""
    watcher, seen = _watcher()
    for run_id in ("11111111-1111-1111-1111-111111111111",
                   "22222222-2222-2222-2222-222222222222"):
        watcher.filter(_record(f"run ID {run_id} | [TMPRL1100] Nondeterminism error"))
    assert len(seen) == 2


def test_reported_even_without_a_run_id():
    """Без разобранного run_id дедуплицировать нечем — но молчать нельзя:
    отказ, о котором не сказали, ничем не лучше прежней строки в stdout."""
    watcher, seen = _watcher()
    watcher.filter(_record("[TMPRL1100] Nondeterminism error: без идентификатора"))
    assert len(seen) == 1
    assert seen[0][0] is None


def test_window_evicts_oldest_and_keeps_recent():
    """Вытесняется СТАРЕЙШИЙ, окно целиком не чистится: чистка вернула бы в
    отчёт все виденные прогоны разом, а повторы не кончаются — вышел бы ровно
    тот поток событий, ради предотвращения которого дедупликация и заведена."""
    watcher, seen = _watcher()
    newest = None
    for i in range(nondeterminism._MAX_SEEN):
        newest = f"{i:08d}-0000-0000-0000-000000000000"
        watcher.filter(_record(f"run ID {newest} | [TMPRL1100] Nondeterminism error"))
    assert len(seen) == nondeterminism._MAX_SEEN

    # Переполняем окно ровно на один прогон.
    watcher.filter(_record("run ID ffffffff-0000-0000-0000-000000000000 "
                           "| [TMPRL1100] Nondeterminism error"))
    assert len(watcher._seen) <= nondeterminism._MAX_SEEN

    # Недавний прогон всё ещё считается виденным — окно не сбросилось.
    watcher.filter(_record(f"run ID {newest} | [TMPRL1100] Nondeterminism error"))
    assert len(seen) == nondeterminism._MAX_SEEN + 1


def test_failing_report_does_not_break_logging():
    """Наблюдатель не имеет права ронять логирование: он висит на логгере
    Temporal, и его сбой остановил бы вывод воркера."""
    def explode(run_id, message):
        raise RuntimeError("Sentry недоступен")

    watcher = nondeterminism.Watcher(explode)
    watcher.filter(_record(EVICTION))  # не бросает


def test_report_logging_does_not_recurse():
    """`report`, залогировавший собственный сбой, прилетел бы в этот же фильтр
    и позвал `report` снова — уже на своей же ошибке."""
    calls = []

    def report_that_logs(run_id, message):
        calls.append(run_id)
        logging.getLogger(nondeterminism.EVICTION_LOGGER).error(
            "[TMPRL1100] Nondeterminism error: отчёт не ушёл, run ID "
            "44444444-4444-4444-4444-444444444444")

    watcher = nondeterminism.Watcher(report_that_logs)
    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    log.addFilter(watcher)
    try:
        log.error(EVICTION)
    finally:
        log.removeFilter(watcher)
    assert calls == ["9e2083d9-22f5-45da-80a9-4635aa2b364c"]


# --- Установка ---

def test_install_is_idempotent():
    """Ставится побочным эффектом импорта worker.py, а тот импортируется в
    тестах под разными именами модуля. Второй наблюдатель со своим окном
    дедупликации докладывал бы тот же прогон дважды на каждое событие."""
    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    first = nondeterminism.install(lambda run_id, msg: None)
    try:
        second = nondeterminism.install(lambda run_id, msg: None)
        assert first is second
        assert sum(isinstance(f, nondeterminism.Watcher) for f in log.filters) == 1
    finally:
        log.removeFilter(first)
        log.setLevel(logging.NOTSET)


def test_install_lowers_the_logger_to_debug():
    """Без этого `logging` не создаст запись вовсе, и фильтр не позовётся —
    ровно та поломка, из-за которой первая редакция модуля не работала."""
    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    log.setLevel(logging.INFO)
    watcher = nondeterminism.install(lambda run_id, msg: None)
    try:
        assert log.isEnabledFor(logging.DEBUG)
    finally:
        log.removeFilter(watcher)
        log.setLevel(logging.NOTSET)


def test_importing_the_worker_does_not_install_the_watcher():
    """Наблюдатель ставится в `main()`, а не фактом импорта.

    Находка ревью: при установке на уровне модуля любой импорт воркера
    (`tests/test_develop_child.py`) оставлял наблюдателя на глобальном логгере
    до конца прогона тестов — он перехватывал записи чужих проверок, а из-за
    защиты от повторной установки следующий `install()` возвращал ЕГО, с чужим
    колбэком. Сквозной тест выше от этого краснел через раз, в зависимости от
    порядка файлов."""
    import worker as worker_module  # noqa: PLC0415

    log = logging.getLogger(nondeterminism.EVICTION_LOGGER)
    assert not any(isinstance(f, nondeterminism.Watcher) for f in log.filters)
    assert hasattr(worker_module, "_watch_nondeterminism")  # но поставить умеет
