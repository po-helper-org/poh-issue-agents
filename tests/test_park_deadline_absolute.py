"""#58: дедлайн парковки отсчитывается от входа в фазу, а не от последнего сигнала.

Найдено на живом прогоне после раскатки #36. Обработчик фазы вызывается в цикле:
посторонний сигнал фазу не двигает, но возвращает управление наверх — и таймер
заводился заново. Дедлайн получался «N часов с последнего шороха», то есть
правило R3 («каждая парковка имеет дедлайн») переставало что-либо гарантировать.

Сценарий не гипотетический: сервис под PAT пишет комментарии от имени человека,
и они возвращались вебхуком как `user_comment`. Достаточно было одного
комментария раз в трое суток, чтобы Issue не эскалировался никогда.
"""

import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import (
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle

_calls: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score_p1(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P1", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None: ...


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None:
    _calls.append("escalated")


def _deadlines(hours: int):
    @activity.defn(name="read_deadlines")
    async def read() -> Deadlines:
        return Deadlines(human_decision_hours=hours)
    return read


ACTIVITIES = [prefilter_ok, protocol_default, set_phase_stub, gate_ok,
              classify_feature, duplicate_none, score_p1, post_priority, escalate]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _park_then_poke(env, handle, pokes: int, gap_hours: int) -> None:
    """Ждём входа в парковку и шлём посторонние сигналы с заданным интервалом."""
    for _ in range(300):
        if await handle.query(IssueLifecycle.stage) == "awaiting-human-decision":
            break
        await env.sleep(1)
    for i in range(pokes):
        await env.sleep(timedelta(hours=gap_hours))
        # Комментарий — не решение о тяжёлой стадии: фазу он не двигает.
        await handle.signal(IssueLifecycle.user_comment, f"посторонний {i}")


@pytest.mark.timeout(120)
async def test_stray_signals_do_not_extend_the_park():
    """Главный случай. Срок 10 ч, каждые 6 ч прилетает комментарий. Пока таймер
    заводился заново, эскалация не наступала никогда; теперь она обязана
    случиться на 10-м часу от ВХОДА в фазу."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *ACTIVITIES, _deadlines(10)]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _park_then_poke(env, handle, pokes=4, gap_hours=6)

            # 4 сигнала × 6 ч = 24 ч > 10 ч: срок обязан был истечь по дороге.
            for _ in range(300):
                if _calls:
                    break
                await env.sleep(timedelta(hours=1))

    assert "escalated" in _calls, "посторонние сигналы продлевают парковку бесконечно"


@pytest.mark.timeout(120)
async def test_park_still_ends_without_any_signal():
    """Контроль: без сигналов поведение прежнее — эскалация по сроку.

    Ждём наблюдаемый исход, а не `handle.result()`: цикл после эскалации уходит
    в боковую фазу и живёт там до своего срока, а автопромотка времени под
    `result()` на длинной парковке срабатывает не всегда.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *ACTIVITIES, _deadlines(3)]):
            await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            for _ in range(60):
                if _calls:
                    break
                await env.sleep(timedelta(hours=1))

    assert "escalated" in _calls


@pytest.mark.timeout(120)
async def test_a_real_decision_still_gets_through():
    """Абсолютный срок не должен глотать настоящее решение: `research-me`,
    пришедший в пределах срока, обязан двинуть фазу."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *ACTIVITIES, _deadlines(48)]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _park_then_poke(env, handle, pokes=2, gap_hours=1)
            await handle.signal(IssueLifecycle.human_decision, "research-me")

            for _ in range(60):
                if await handle.query(IssueLifecycle.phase) != "classified":
                    break
                await env.sleep(1)
            assert await handle.query(IssueLifecycle.phase) == "business-analysis"

    assert "escalated" not in _calls


# --- сам расчёт остатка ---

def test_timeout_shrinks_as_the_phase_ages():
    """Единичная проверка формулы, без Temporal: остаток обязан убывать."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    wf = IssueLifecycle()
    entered = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wf._phase_since = entered

    with patch("workflows.workflow.patched", return_value=True), \
         patch("workflows.workflow.now", return_value=entered + timedelta(hours=30)):
        assert wf._park_timeout(72) == timedelta(hours=42)


def test_expired_phase_asks_for_no_wait_at_all():
    """Просроченная фаза не должна ждать ни секунды — иначе перезапуск цикла
    (continue-as-new) дарил бы Issue ещё один полный срок."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    wf = IssueLifecycle()
    entered = datetime(2026, 1, 1, tzinfo=timezone.utc)
    wf._phase_since = entered

    with patch("workflows.workflow.patched", return_value=True), \
         patch("workflows.workflow.now", return_value=entered + timedelta(hours=100)):
        assert wf._park_timeout(72) == timedelta(0)


def test_old_generation_keeps_the_previous_timer():
    """Прогоны, припаркованные до этого изменения, обязаны доиграть с прежней
    длительностью: их таймер уже записан в историю, и другая длительность на
    реплее — недетерминизм."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    wf = IssueLifecycle()
    wf._phase_since = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with patch("workflows.workflow.patched", return_value=False):
        assert wf._park_timeout(72) == timedelta(hours=72)
