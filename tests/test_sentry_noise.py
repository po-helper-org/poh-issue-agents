"""Шум в Sentry: отменённые стадии, разрыв связи и отказы чужой стороны.

Все три разобраны по живым событиям проекта issue-agent: ISSUE-AGENT-C
(«Task exception was never retrieved» после намеренного terminate),
ISSUE-AGENT-8 (ClientDisconnect как 500) и ISSUE-AGENT-7/A (429 и 524 от z.ai
вперемешку с настоящими багами).
"""

import asyncio
import logging

import pytest

import activities
from shared import sentry_setup


# --- Отменённая стадия не оставляет непрочитанного исключения ---

@pytest.mark.timeout(30)
async def test_cancelled_stage_retrieves_the_thread_exception(caplog):
    started = asyncio.Event()

    def blocking():
        # Поток не прерывается отменой: доигрывает и падает — как docker-прогон
        # агента, чей контейнер сняли снаружи (код 137).
        asyncio.run(asyncio.sleep(0))  # отдельный цикл, чтобы не трогать текущий
        raise RuntimeError("прогон агента разработки завершился с кодом 137")

    async def run():
        started.set()
        await activities._run_with_heartbeat(blocking, label="dev:agent")

    task = asyncio.ensure_future(run())
    await started.wait()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with caplog.at_level(logging.INFO):
        # Даём колбэку сработать на завершении потока.
        for _ in range(50):
            await asyncio.sleep(0.02)

    # Главное: исключение забрано, поэтому asyncio не пишет о нём ERROR'ом.
    assert not [r for r in caplog.records
                if "never retrieved" in r.getMessage()], "исключение осталось непрочитанным"


# --- Отказы чужой стороны отличимы от своих ---

def _event(exc_type: str) -> dict:
    return {"exception": {"values": [{"type": exc_type, "value": "..."}]}, "level": "error"}


@pytest.mark.parametrize("exc_type", ["RateLimitError", "InternalServerError",
                                      "APITimeoutError", "ClientDisconnect"])
def test_external_failure_is_downgraded_and_grouped(exc_type):
    event = sentry_setup._scrub_event(_event(exc_type))

    assert event["level"] == "warning"
    assert event["fingerprint"] == ["external_failure", exc_type]
    assert event["tags"]["failure_side"] == "external"


def test_our_own_bug_keeps_its_level():
    event = sentry_setup._scrub_event(_event("KeyError"))

    assert event["level"] == "error"
    assert "fingerprint" not in event
    assert "failure_side" not in (event.get("tags") or {})


def test_classification_does_not_break_events_without_exception():
    event = sentry_setup._scrub_event({"message": "pipeline failed", "level": "error"})

    assert event["level"] == "error"


def test_secrets_are_still_scrubbed_alongside_classification():
    """Классификация встроена в тот же before_send — скраббер обязан работать."""
    event = sentry_setup._scrub_event({
        "exception": {"values": [{"type": "RateLimitError", "value": "429", "stacktrace": {
            "frames": [{"vars": {"ZAI_API_KEY": "секрет", "repo": "o/r"}}]}}]},
        "level": "error",
    })

    frame_vars = event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame_vars["ZAI_API_KEY"] == "[Filtered]"
    assert frame_vars["repo"] == "o/r"
    assert event["level"] == "warning"


# --- Разрыв связи отправителем не 500 ---

def test_client_disconnect_answers_quietly():
    """ISSUE-AGENT-8: пять событий уровня error за один разрыв связи с прокси."""
    import sys
    sys.path.insert(0, "webhook")
    import main as webhook_main
    from starlette.requests import ClientDisconnect

    class _Req:
        headers = {"x-github-delivery": "ccdcc290"}

    response = asyncio.run(
        webhook_main._client_disconnect(_Req(), ClientDisconnect()))

    assert response.status_code == 204


# --- Причина сбоя, по которой группируются события ---

def test_failure_reason_names_the_class_when_type_is_not_a_string():
    """ISSUE-AGENT-B: в Sentry уезжал тег `exc_type: 1`.

    У `ApplicationError` атрибут `.type` — имя исходного класса, и по нему
    строится fingerprint. У `TimeoutError` то же имя занято перечислением
    `TimeoutType`, чьё значение — число: группировка шла по единице.
    """
    import enum

    from workflows import _failure_reason

    class TimeoutType(enum.IntEnum):
        START_TO_CLOSE = 1

    class FakeTimeout(Exception):
        type = TimeoutType.START_TO_CLOSE

        def __str__(self):
            return "activity StartToClose timeout"

    class FakeActivityError(Exception):
        def __init__(self, cause):
            self.cause = cause

    reason = _failure_reason(FakeActivityError(FakeTimeout()))

    assert reason == "FakeTimeout: activity StartToClose timeout"


def test_failure_reason_keeps_the_application_error_type():
    from workflows import _failure_reason

    class FakeApplicationError(Exception):
        type = "ValidationError"

        def __str__(self):
            return "поле не заполнено"

    class FakeActivityError(Exception):
        def __init__(self, cause):
            self.cause = cause

    assert _failure_reason(FakeActivityError(FakeApplicationError())) == (
        "ValidationError: поле не заполнено")
