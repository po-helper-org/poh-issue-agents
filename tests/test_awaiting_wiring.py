"""#39: ожидание заполнено на каждой точке парковки и видно снаружи.

Определение готовности: выборка `label:needs-human:*` = полная очередь к людям,
и по каждому Issue из неё видно, чего ждут, от кого, сколько уже и когда сгорит
срок. Здесь это проверяется на настоящем воркфлоу, а не на структуре.
"""

import ast
import uuid
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import awaiting as aw
from shared import lifecycle
from shared.workflow_types import (
    ClassificationResult,
    Deadlines,
    DevelopPlan,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueDevelopment, IssueEstimation, IssueLifecycle

_labels: list[str] = []


@activity.defn(name="mark_awaiting")
async def mark_awaiting_spy(repo: str, issue_number: int, waiting=None) -> None:
    """Без аннотации типа Temporal отдаёт словарь — как и настоящей активности."""
    if waiting is None:
        _labels.append("queue:off")
        return
    kind = waiting["kind"] if isinstance(waiting, dict) else waiting.kind
    # Записываем ЭФФЕКТ, а не полезную нагрузку: настоящая активность решает по
    # виду ожидания, ставить метку очереди к людям или снимать.
    _labels.append(f"queue:on:{kind}" if kind in aw.BLOCKED_ON_HUMAN else "queue:off")


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_bug(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:bug", answer="ok")


@activity.defn(name="classify_issue")
async def classify_answers(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:consultation", answer="вот ответ")


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
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="trigger_openhands_resolver")
async def trigger_build(issue: IssueInput, root_issue: int | None = None,
                        branch: str | None = None) -> None: ...


# Разработка ушла в дочерний воркфлоу `IssueDevelopment` (#FNR-6):
# `_start_development` под маркером патча (в тесте он всегда взведён) зовёт
# его вместо `trigger_openhands_resolver` напрямую. Незарегистрированный
# дочерний воркфлоу не даёт быстрой ошибки — родитель просто ждёт исполнителя,
# которого нет, и тест висит до таймаута. Режим "dispatch" воспроизводит
# прежнее поведение стаба (`None` → работа ушла на чужую сторону).
@activity.defn(name="dev_begin")
async def dev_begin_dispatch(issue: IssueInput) -> DevelopPlan:
    return DevelopPlan(mode="dispatch", branch="")


@activity.defn(name="dev_dispatch")
async def dev_dispatch_stub(issue: IssueInput, branch: str) -> None: ...


BASE = [mark_awaiting_spy, prefilter_ok, protocol_default, deadlines_stub,
        set_phase_stub, gate_ok, duplicate_none, score_p1, post_priority,
        escalate, trigger_build, dev_begin_dispatch, dev_dispatch_stub]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _worker(env, tq, classify=classify_bug):
    return Worker(env.client, task_queue=tq,
                  workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                             IssueDevelopment],
                  activities=[*BASE, classify])


async def _await_phase(env, handle, expected: str) -> str:
    for _ in range(200):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


# --- ожидание видно снаружи ---

@pytest.mark.timeout(120)
async def test_parked_issue_says_what_it_waits_for():
    """Раньше припаркованный прогон и зависший выглядели одинаково."""
    _labels.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            waiting = await handle.query(IssueLifecycle.awaiting)

    assert waiting is not None, "фаза ожидания без заполненного Awaiting"
    assert waiting.kind == aw.HUMAN_DECISION
    assert "research-me" in waiting.reason
    assert waiting.who, "непонятно, кто снимет ожидание"
    assert waiting.deadline_epoch > waiting.since_epoch, "срок не посчитан"


@pytest.mark.timeout(120)
async def test_waiting_for_a_human_puts_the_issue_in_the_human_queue():
    _labels.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

    assert f"queue:on:{aw.HUMAN_DECISION}" in _labels


@pytest.mark.timeout(120)
async def test_waiting_for_a_machine_does_not_pollute_the_human_queue():
    """Задача, ждущая внешнего агента, человеку делать нечего — иначе на саму
    выборку перестают смотреть."""
    _labels.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
            await handle.signal(IssueLifecycle.human_decision, "build-me")
            await _await_phase(env, handle, lifecycle.IN_DEVELOPMENT)

            waiting = await handle.query(IssueLifecycle.awaiting)

    assert waiting.kind == aw.EXTERNAL_AGENT
    assert _labels[-1] == "queue:off", "метка очереди к людям осталась висеть"


@pytest.mark.timeout(120)
async def test_label_is_not_flapped_on_every_transition():
    """Снять и поставить одну и ту же метку на каждом переходе — лишние вызовы
    GitHub и мусор в таймлайне Issue."""
    _labels.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)

    # classified и ready-for-dev оба ждут человека: метка обязана встать один раз.
    assert _labels.count("queue:off") == 0, "метка снималась и ставилась заново"
    assert len(_labels) == 1, f"лишние обращения к GitHub: {_labels}"


# --- сбой как вид ожидания ---

@pytest.mark.timeout(120)
async def test_a_failed_run_stands_in_the_queue_instead_of_vanishing():
    """Раньше сбой вешал метку и закрывал прогон: ждать было некому и нечего.
    Теперь это ожидание решения — перезапустить, отдать человеку или отменить."""
    _labels.clear()

    @activity.defn(name="classify_issue")
    async def classify_breaks(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
        raise RuntimeError("модель недоступна")

    @activity.defn(name="post_error_label")
    async def post_error(issue: IssueInput, reason: str) -> None: ...

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*BASE, classify_breaks, post_error]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.FAILED)

            waiting = await handle.query(IssueLifecycle.awaiting)
            assert (await handle.describe()).status.name == "RUNNING"

    assert waiting.kind == aw.FAILURE_RECOVERY
    assert "перезапустить" in waiting.reason
    assert f"queue:on:{aw.FAILURE_RECOVERY}" in _labels, "сбой не попал в очередь к людям"


# --- статическая проверка полноты ---

def test_every_parking_point_fills_the_waiting():
    """Фаза ожидания без заполненного `Awaiting` — ошибка, а не пустое поле.
    Проверяем по исходнику: каждый `_wait_for_signal` в фазовом цикле обязан
    получать срок из `_park`, который описание и заполняет."""
    src = (Path(__file__).resolve().parent.parent / "worker" / "workflows.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)

    loop_methods = {"_phase_triage", "_phase_await_decision", "_phase_await_build",
                    "_phase_park"}
    unparked = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in loop_methods:
            continue
        for call in ast.walk(node):
            if not (isinstance(call, ast.Call)
                    and getattr(call.func, "attr", "") == "_wait_for_signal"):
                continue
            arg = call.args[0] if call.args else None
            # Допустимы `await self._park(...)` и голое ожидание уточнения,
            # у которого свой срок из intake gate.
            inner = arg.value if isinstance(arg, ast.Await) else arg
            if isinstance(inner, ast.Call) and getattr(inner.func, "attr", "") == "_park":
                continue
            if node.name == "_phase_triage":
                continue  # цикл уточнений: срок свой, ожидание описано вопросом
            unparked.append(node.name)

    assert not unparked, f"парковка без описания ожидания: {sorted(set(unparked))}"


@pytest.mark.timeout(120)
async def test_resumed_work_leaves_the_human_queue():
    """Агент снова работает — метка очереди к людям обязана уйти.

    После сбоя задача стоит в очереди (`failure-recovery`). `/analyze`
    возвращает её в анализ, и дальше до самого PR цикл нигде не паркуется на
    человека: метка снималась бы только на следующей парковке, которой нет.
    В итоге выборка `label:needs-human:*` показывала бы задачу, по которой
    человеку делать нечего, — то есть врала бы ровно там, где обязана быть
    полной.
    """
    _labels.clear()

    @activity.defn(name="classify_issue")
    async def classify_breaks(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
        raise RuntimeError("модель недоступна")

    @activity.defn(name="post_error_label")
    async def post_error(issue: IssueInput, reason: str) -> None: ...

    @activity.defn(name="mark_command_running")
    async def mark_running(repo: str, issue_number: int, command: str) -> None: ...

    @activity.defn(name="finish_command_labels")
    async def finish_labels(repo: str, n: int, command: str, ok: bool) -> None: ...

    @activity.defn(name="ack_command")
    async def ack(analyze) -> None: ...

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze) -> None: ...

    @activity.defn(name="run_fnr_stage")
    async def stage_ok(analyze, stage_name: str) -> dict:
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze) -> str:
        return "research/issue-7"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze) -> None: ...

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze, reason: str) -> None: ...

    @activity.defn(name="mark_ready_for_dev")
    async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None: ...

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*BASE, classify_breaks, post_error, mark_running,
                                      finish_labels, ack, prepare, stage_ok, publish,
                                      cleanup, publish_error, ready]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.FAILED)
            assert f"queue:on:{aw.FAILURE_RECOVERY}" in _labels

            await handle.signal(IssueLifecycle.analyze_requested, None)
            await _await_phase(env, handle, lifecycle.BUSINESS_ANALYSIS)

    assert _labels[-1] == "queue:off", \
        f"метка очереди к людям осталась висеть на работающем агенте: {_labels}"


@pytest.mark.timeout(120)
async def test_plan_subissue_waits_for_its_parent_not_for_a_human():
    """Подзадача плана в очередь к людям не встаёт.

    Исполняет её родитель — одним прогоном на весь объём MVP. Человеку по ней
    делать нечего, а `needs-human:*` обязана быть ПОЛНОЙ очередью к людям: восемь
    подзадач одной фичи в ней означают, что на саму выборку перестанут смотреть.
    """
    _labels.clear()

    @activity.defn(name="read_protocol_state")
    async def subissue_state(repo: str, issue_number: int) -> ProtocolState:
        return ProtocolState(origin_agent=True, root_issue=13)

    @activity.defn(name="read_deadlines")
    async def autostart() -> Deadlines:
        return Deadlines(research_autostart=True, develop_autostart=True)

    @activity.defn(name="read_open_questions")
    async def no_questions(repo: str, branch: str) -> list[str]:
        return []

    @activity.defn(name="mark_ready_for_dev")
    async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None: ...

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[mark_awaiting_spy, prefilter_ok, subissue_state,
                                      autostart, set_phase_stub, gate_ok, classify_bug,
                                      duplicate_none, score_p1, post_priority, escalate,
                                      trigger_build, no_questions, ready]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
            for _ in range(200):
                if _labels:
                    break
                await env.sleep(1)
            waiting = await handle.query(IssueLifecycle.awaiting)

    assert waiting is not None, "фаза ожидания без заполненного Awaiting"
    assert waiting.kind == aw.EXTERNAL_AGENT, (
        f"подзадача ждёт {waiting.kind}, а исполняет её родитель")
    assert not any(l.startswith("queue:on") for l in _labels), (
        f"подзадача попала в очередь к людям: {_labels}")
