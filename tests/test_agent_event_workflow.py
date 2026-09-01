"""#38: факт внешнего агента двигает фазу Issue.

Определение готовности задачи: PR, открытый PR-Agent'ом, двигает фазу этого
Issue и попадает в его трассировку — без ручной связи и без правок под каждый
новый тип события. Здесь это проверяется на настоящем воркфлоу.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.agent_events import BLOCKED, FAILED, STARTED, SUCCEEDED, AgentEvent
from shared.workflow_types import (
    ClassificationResult,
    Deadlines,
    DevelopPlan,
    DuplicateResult,
    GateResult,
    IssueInput,
    LifecycleState,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueDevelopment, IssueEstimation, IssueLifecycle

_calls: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_protocol_state")
async def protocol_step_subissue(repo: str, issue_number: int) -> ProtocolState:
    """Под-задача шага (R5): барьер в `_run_phase_loop` читает это же
    состояние, только не через `_phase_triage` — тот здесь не выполняется."""
    _calls.append("read_state")
    return ProtocolState(step_subissue=True)


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    # Круг правок здесь выключен намеренно: тест про цепочку событий, а не про
    # доведение PR. С включённым кругом фаза `pr-review` уходила бы работать, и
    # проверялся бы уже не тот путь.
    return Deadlines(pr_fix_enabled=False)


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_bug(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:bug", answer="ok")


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
    _calls.append(f"escalate:{reason}")


@activity.defn(name="trigger_openhands_resolver")
async def trigger_build(issue: IssueInput, root_issue: int | None = None,
                        branch: str | None = None) -> None: ...


# Разработка ушла в дочерний воркфлоу `IssueDevelopment` (#FNR-6):
# `_start_development` под маркером патча (в тесте он всегда взведён) зовёт
# его вместо `trigger_openhands_resolver` напрямую. Незарегистрированный
# дочерний воркфлоу не даёт быстрой ошибки — родитель просто ждёт исполнителя,
# которого нет, и тест висит до таймаута. Режим "dispatch" воспроизводит
# прежнее поведение стаба (`None` → работа ушла на чужую сторону, ждём
# `in-development`) — этот файл проверяет цепочку событий ВНЕШНЕГО агента, а
# не сам прогон разработки.
@activity.defn(name="dev_begin")
async def dev_begin_dispatch(issue: IssueInput) -> DevelopPlan:
    return DevelopPlan(mode="dispatch", branch="")


@activity.defn(name="dev_dispatch")
async def dev_dispatch_stub(issue: IssueInput, branch: str) -> None: ...


# Гейт критерия приёмки (задача 8): `_start_development` перед передачей в
# разработку читает критерий из тела Issue. Этот файл проверяет цепочку
# событий внешнего агента, а не гейт — критерий уже есть, чтобы разработка
# стартовала молча, без вопроса.
@activity.defn(name="read_acceptance_criterion")
async def criterion_present(issue: IssueInput) -> str:
    return "было 404; стало 405"


ACTIVITIES = [prefilter_ok, protocol_default, deadlines_stub, set_phase_stub,
              gate_ok, classify_bug, duplicate_none, score_p1, post_priority,
              escalate, trigger_build, dev_begin_dispatch, dev_dispatch_stub,
              criterion_present]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _event(phase: str, status: str = STARTED, ref: str = "42",
           agent: str = "pr-agent") -> AgentEvent:
    return AgentEvent(repo="o/r", agent=agent, phase=phase, status=status, ref=ref)


def _worker(env, tq):
    return Worker(env.client, task_queue=tq,
                  workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                             IssueDevelopment],
                  activities=[*ACTIVITIES, awaiting_stub])


async def _await_phase(env, handle, expected: str, tries: int = 200) -> str:
    for _ in range(tries):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


async def _in_development(env, handle):
    """Доводит цикл до фазы, из которой начинается работа внешних агентов."""
    await _await_phase(env, handle, lifecycle.CLASSIFIED)
    await handle.signal(IssueLifecycle.human_decision, "bug-me")
    await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
    await handle.signal(IssueLifecycle.human_decision, "build-me")
    return await _await_phase(env, handle, lifecycle.IN_DEVELOPMENT)


@pytest.mark.timeout(120)
async def test_pr_opened_moves_the_issue_phase():
    """Определение готовности #38: PR от внешнего агента двигает фазу Issue."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            assert await _in_development(env, handle) == lifecycle.IN_DEVELOPMENT

            await handle.signal(IssueLifecycle.agent_event, _event(lifecycle.PR_OPEN))

            assert await _await_phase(env, handle, lifecycle.PR_OPEN) == lifecycle.PR_OPEN

    assert f"phase:{lifecycle.PR_OPEN}" in _calls, "метка фазы не доехала до GitHub"


@pytest.mark.timeout(120)
async def test_a_chain_of_events_walks_the_issue_to_merged():
    """Несколько агентов подряд ведут одну задачу — и код под каждый новый тип
    события менять не нужно: маршрут задаёт таблица переходов."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _in_development(env, handle)

            for phase in (lifecycle.PR_OPEN, lifecycle.PR_REVIEW, lifecycle.MERGED):
                await handle.signal(IssueLifecycle.agent_event, _event(phase))
                assert await _await_phase(env, handle, phase) == phase


@pytest.mark.timeout(120)
async def test_repeated_delivery_does_not_move_the_phase_twice():
    """Соседний сервис вправе повторить доставку. Один факт — один переход."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _in_development(env, handle)

            event = _event(lifecycle.PR_OPEN)
            await handle.signal(IssueLifecycle.agent_event, event)
            await _await_phase(env, handle, lifecycle.PR_OPEN)
            await handle.signal(IssueLifecycle.agent_event, event)
            await env.sleep(2)

            assert await handle.query(IssueLifecycle.phase) == lifecycle.PR_OPEN

    assert _calls.count(f"phase:{lifecycle.PR_OPEN}") == 1, "повтор двинул фазу дважды"


@pytest.mark.timeout(120)
async def test_ci_failure_lands_in_failed_and_keeps_the_cycle_alive():
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _in_development(env, handle)

            await handle.signal(IssueLifecycle.agent_event,
                                _event(lifecycle.PR_OPEN, status=FAILED,
                                       ref="build-881", agent="ci"))

            assert await _await_phase(env, handle, lifecycle.FAILED) == lifecycle.FAILED
            assert (await handle.describe()).status.name == "RUNNING"


@pytest.mark.timeout(120)
async def test_blocked_review_goes_to_a_human():
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _in_development(env, handle)
            await handle.signal(IssueLifecycle.agent_event, _event(lifecycle.PR_OPEN))
            await _await_phase(env, handle, lifecycle.PR_OPEN)

            await handle.signal(IssueLifecycle.agent_event,
                                _event(lifecycle.PR_REVIEW, status=BLOCKED))

            assert await _await_phase(env, handle, lifecycle.ESCALATED) == lifecycle.ESCALATED


@pytest.mark.timeout(120)
async def test_impossible_transition_asks_a_human_instead_of_killing_the_cycle():
    """Соседний сервис живёт своим релизным циклом. Его рассинхрон с нашей
    моделью обязан приводить к разбору человеком, а не к падению цикла Issue —
    в отличие от нашего собственного кода, где невозможный переход это баг."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            # Из `classified` в `merged` хода нет: работа ещё не начиналась.
            await handle.signal(IssueLifecycle.agent_event,
                                _event(lifecycle.MERGED, status=SUCCEEDED))

            assert await _await_phase(env, handle, lifecycle.ESCALATED) == lifecycle.ESCALATED
            assert (await handle.describe()).status.name == "RUNNING"

    reason = next(c for c in _calls if c.startswith("escalate:"))
    assert lifecycle.MERGED in reason and "classified" in reason, (
        "человек должен увидеть, что именно сообщил агент и откуда")


@pytest.mark.timeout(120)
async def test_cycle_raised_by_an_event_skips_triage():
    """Цикл, поднятый событием агента, стартует сразу в доложенной фазе: триажу
    нечего делать по задаче, которая уже в PR."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                args=[IssueInput(repo="o/r", issue_number=7, title="", body="",
                                 author_login="", author_type="User", interactive=False),
                      LifecycleState(phase=lifecycle.PR_OPEN, stage=lifecycle.PR_OPEN)],
                id=f"wf-{uuid.uuid4()}", task_queue=tq,
                start_signal="agent_event",
                start_signal_args=[_event(lifecycle.PR_OPEN)],
            )

            assert await _await_phase(env, handle, lifecycle.PR_OPEN) == lifecycle.PR_OPEN

    assert not any(c.startswith("phase:classified") for c in _calls), "триаж всё же пошёл"


@pytest.mark.timeout(30)
async def test_step_subissue_barrier_catches_a_cycle_raised_by_an_event():
    """Правка по ревью (Task 13, R5): под-задача шага закрывается своим PR —
    `Closes #N` в его теле корректно указывает на неё, — поэтому PR-Agent
    доложит о ней агентским событием так же, как о любой другой задаче. Такое
    событие поднимает цикл СРАЗУ в доложенной фазе (см. предыдущий тест) —
    мимо `created`, а с ним и мимо `_phase_triage`, где стоит основная
    проверка `state.step_subissue`. У самого AgentEvent меток не бывает
    вовсе — гейт вебхука по `harness:step` тут физически нечем поднять.

    Без отдельного барьера в начале `_run_phase_loop` цикл дошёл бы до
    `_phase_park` и встал там ждать сигнала — а включи кто-нибудь
    HOWTODEMO_AUTOSTART, поднял бы дорогой child-воркфлоу приёмки на первом же
    входе в `pr-open`, до какого-либо сигнала и без единой метки в событии.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        activities = [a for a in ACTIVITIES if a is not protocol_default]
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                                     IssueDevelopment],
                          activities=[*activities, protocol_step_subissue, awaiting_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                args=[IssueInput(repo="o/r", issue_number=7, title="", body="",
                                 author_login="", author_type="User", interactive=False),
                      LifecycleState(phase=lifecycle.PR_OPEN, stage=lifecycle.PR_OPEN)],
                id=f"wf-{uuid.uuid4()}", task_queue=tq,
                start_signal="agent_event",
                start_signal_args=[_event(lifecycle.PR_OPEN)],
            )
            await handle.result()

            assert await handle.query(IssueLifecycle.stage) == "step-subissue"

    assert "read_state" in _calls, "барьер не прочитал состояние протокола"
    # Метку не пишем — тот же приём, что и у agents_off: план родителя уже
    # разобрал эту задачу, отметка на подзадаче никому не нужна.
    assert not any(c.startswith("phase:") for c in _calls), "метка фазы не должна ставиться"
