"""Закрытие Issue слиянием PR — не то же самое, что снятие с обработки.

До этой правки любое закрытие на GitHub уводило цикл в `cancelled`. Issue,
доведённый до `main`, и Issue, закрытый руками, оказывались в одном состоянии:
«сколько задач дошло до main» по меткам не считалось вовсе, а фаза `merged` не
использовалась нигде — `grep -rn MERGED worker/` не находил ни одного вхождения.

Найдено живым прогоном 2026-08-20: `po-helper-org/poh-demo-checkout#74` прошёл
путь целиком, PR #81 влит в `main`, GitHub закрыл Issue по `Closes #74` — и
контур поставил `phase:cancelled`. Цикл при этом стоял в `pr-review`, то есть
ровно в той фазе, из которой переход в `merged` объявлен.

Признак берём у самого PR, а не из полезной нагрузки закрытия: `state_reason`
одинаков и у закрытия по `Closes`, и у закрытия руками «как выполненное», а
доставки `issues.closed` и `pull_request.closed` идут наперегонки. Номер PR
цикл уже знает — он запомнил его, когда PR открылся.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowExecutionStatus
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.agent_events import AgentEvent
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

_phases: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None: ...


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _phases.append(phase)


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
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
    _phases.append("escalated-activity")


@activity.defn(name="read_deadlines")
async def deadlines_long() -> Deadlines:
    # Срок заведомо больше времени теста: цикл обязан закрыться по сигналу, а
    # не по дедлайну парковки — иначе тест доказывал бы не то.
    #
    # Круг правок выключен: он не про эту границу, а его активности пришлось бы
    # подменять все до одной, чтобы добраться до закрытия. С выключенным кругом
    # фаза `pr-review` просто паркуется — ровно то состояние, в котором Issue
    # застаёт слияние.
    return Deadlines(human_decision_hours=720, pr_fix_enabled=False)


BASE_ACTIVITIES = [awaiting_stub, prefilter_ok, protocol_default, set_phase_stub,
                   gate_ok, classify_feature, duplicate_none, score_p1,
                   post_priority, escalate, deadlines_long]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _wait_for_park(env, handle) -> None:
    for _ in range(300):
        if await handle.query(IssueLifecycle.stage) == "awaiting-human-decision":
            return
        await env.sleep(1)
    raise AssertionError("цикл не дошёл до парковки в ожидании решения человека")

# Что ответит GitHub про PR. Тест переставляет перед прогоном.
_merged = {"value": False}
_asked: list[tuple[str, int]] = []


@activity.defn(name="pr_is_merged")
async def pr_is_merged_stub(repo: str, pr_number: int) -> bool:
    _asked.append((repo, pr_number))
    return _merged["value"]


ACTIVITIES = [*BASE_ACTIVITIES, pr_is_merged_stub]


def _event(phase: str, ref: str = "81") -> AgentEvent:
    return AgentEvent(repo="o/r", agent="openhands", phase=phase,
                      status="started", ref=ref)


async def _drive_to(env, handle, stop_at: str = "pr-review") -> None:
    """Довести цикл до `stop_at` фактами внешнего агента.

    Остановка на `pr-open` — не искусственная: именно там задача и стоит, пока
    доклад ревью не пришёл, а он приходит не всегда (#103, #308).
    """
    await _wait_for_park(env, handle)
    path = ("ready-for-dev", "pr-open", "pr-review")
    for phase in path[:path.index(stop_at) + 1]:
        await handle.signal(IssueLifecycle.agent_event, _event(phase))
        for _ in range(300):
            if await handle.query(IssueLifecycle.phase) == phase:
                break
            await env.sleep(1)
        assert await handle.query(IssueLifecycle.phase) == phase, \
            f"цикл не дошёл до {phase}"


async def _run(merged: bool, stop_at: str = "pr-review") -> tuple[str, list[str]]:
    _phases.clear()
    _asked.clear()
    _merged["value"] = merged
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _drive_to(env, handle, stop_at)

            await handle.signal(IssueLifecycle.issue_closed, "github-actions[bot]")

            await handle.result()
            phase = await handle.query(IssueLifecycle.phase)
            desc = await handle.describe()
            assert desc.status == WorkflowExecutionStatus.COMPLETED, \
                "закрытый Issue обязан завершить цикл в любом исходе"
    return phase, list(_phases)


@pytest.mark.timeout(180)
async def test_merged_pr_closes_the_issue_as_merged():
    phase, phases = await _run(merged=True)
    assert phase == "merged", "доведённый до main Issue помечен как снятый с обработки"
    assert phases[-1] == "merged", f"метка фазы не доехала: {phases}"
    assert _asked == [("o/r", 81)], "цикл не спросил GitHub про свой PR"


@pytest.mark.timeout(180)
async def test_unmerged_pr_still_closes_as_cancelled():
    # Закрыть Issue можно и руками, не сливая PR. Тогда прежнее правило
    # остаётся в силе: это снятие с обработки, а не успех.
    phase, phases = await _run(merged=False)
    assert phase == "cancelled"
    assert phases[-1] == "cancelled", f"метка фазы не доехала: {phases}"


@pytest.mark.timeout(120)
async def test_no_pr_no_question_to_github():
    # Issue, закрытый до всякой разработки, PR не имеет — спрашивать не о чем,
    # и лишний вызов GitHub на каждом закрытии не нужен.
    _phases.clear()
    _asked.clear()
    _merged["value"] = True
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _wait_for_park(env, handle)

            await handle.signal(IssueLifecycle.issue_closed, "alice")

            await handle.result()
            assert await handle.query(IssueLifecycle.phase) == "cancelled"
    assert _asked == [], "цикл спросил про PR, которого у него нет"


@pytest.mark.timeout(180)
async def test_merged_pr_closes_as_merged_even_without_a_review_report():
    """Задача, влитая из `pr-open`, — успех, а не снятие с обработки (#308).

    Ход `pr-open → pr-review` объявлен внешним: его приносит доклад PR-Agent.
    Пока доклад не идёт (#103), цикл стоит в `pr-open` — и до этой правки
    закрытие влитым PR писало `cancelled`, даже не спросив GitHub, влит ли PR.
    Успех и отказ снова оказывались в одном состоянии.
    """
    phase, phases = await _run(merged=True, stop_at="pr-open")
    assert phase == "merged", "влитый из pr-open Issue помечен как снятый с обработки"
    assert phases[-1] == "merged", f"метка фазы не доехала: {phases}"
    assert _asked == [("o/r", 81)], "цикл не спросил GitHub про свой PR"


@pytest.mark.timeout(180)
async def test_unmerged_pr_from_pr_open_is_still_cancelled():
    """Новый ход не отменяет прежнего правила: не влит — значит снят."""
    phase, phases = await _run(merged=False, stop_at="pr-open")
    assert phase == "cancelled"
    assert phases[-1] == "cancelled", f"метка фазы не доехала: {phases}"
