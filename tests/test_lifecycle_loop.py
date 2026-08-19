"""#36: IssueLifecycle как долгоживущий владелец состояния Issue.

До этого изменения воркфлоу заканчивался на приоритизации или на первом же
боковом исходе — спаме, дубликате, сбое стадии. Дальше состояние Issue не вёл
никто: сигналить было некому, вернуть задачу в работу можно было только заведя
новый прогон, а фаза после `classified` существовала лишь в голове человека.

Здесь проверяется именно то, что изменилось:
  * боковая фаза не закрывает цикл, и `reopen` возвращает Issue в работу;
  * сбой стадии — состояние, а не конец: после перезапуска триаж идёт заново;
  * continue-as-new обрывает историю, не теряя состояния;
  * старые прогоны остаются на прежнем коде (workflow.patched).
"""

import inspect
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

import workflows as workflows_module
from shared import lifecycle
from shared.workflow_types import (
    AnalyzeInput,
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


# --- заглушки границ ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False):
    return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


@activity.defn(name="intake_gate")
async def gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    _calls.append("classify")
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="classify_issue")
async def classify_consultation(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:consultation", answer="вот ответ")


@activity.defn(name="classify_issue")
async def classify_fails_once(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    """Первый прогон срывается, второй проходит: так проверяется именно
    перезапуск обработки, а не бесконечный круг `created → failed → created`."""
    _calls.append("classify")
    if _calls.count("classify") == 1:
        raise ApplicationError("модель недоступна", non_retryable=True)
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


@activity.defn(name="post_error_label")
async def post_error(issue: IssueInput, reason: str) -> None:
    _calls.append("error-label")


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="mark_command_running")
async def mark_running(repo: str, issue_number: int, command: str) -> None: ...


@activity.defn(name="finish_command_labels")
async def finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None: ...


@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None:
    """Подтверждение приёма ставит сам дочерний прогон — тот же код, что и при
    автономном запуске. Здесь важно, ЧЕМ он назван человеку."""
    _calls.append(f"ack:{analyze.trigger}")


@activity.defn(name="prepare_workspace")
async def prepare(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="run_fnr_stage")
async def stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="publish_analysis")
async def publish(analyze: AnalyzeInput) -> str:
    return "research/issue-7"


@activity.defn(name="cleanup_workspace")
async def cleanup(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="publish_analysis_error")
async def publish_error(analyze: AnalyzeInput, reason: str) -> None: ...


@activity.defn(name="mark_ready_for_dev")
async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None:
    _calls.append(f"ready:{priority_tier}:{branch}")


TRIAGE_ACTIVITIES = [prefilter_ok, protocol_default, deadlines_stub, set_phase_stub,
                     gate_sufficient, duplicate_none, score_p1, post_priority,
                     post_error, escalate]

ANALYSIS_ACTIVITIES = [mark_running, finish_labels, ack, prepare, stage_ok, publish,
                       cleanup, publish_error, ready]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _await_phase(env, handle, expected: str, tries: int = 300) -> str:
    """Цикл живёт дальше, поэтому ждать `result()` больше нельзя — ждём фазу."""
    for _ in range(tries):
        phase = await handle.query(IssueLifecycle.phase)
        if phase == expected:
            return phase
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


# --- боковые состояния перестали быть концом ---

@pytest.mark.timeout(90)
async def test_side_state_keeps_the_cycle_alive():
    """`advisor:consultation` раньше завершал воркфлоу. Теперь это фаза
    `answered`, и владелец состояния остаётся на связи."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_consultation]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            assert await _await_phase(env, handle, lifecycle.ANSWERED) == lifecycle.ANSWERED
            assert (await handle.describe()).status.name == "RUNNING", (
                "боковое состояние снова стало концом прогона")


@pytest.mark.timeout(90)
async def test_reopen_returns_a_side_state_to_work():
    """Единственный способ вернуть Issue в работу — сигнал, а для этого прогон
    обязан быть жив. Проверяем сам маршрут возврата, а не только живучесть."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_consultation]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.human_decision, "reopen")

            assert await _await_phase(env, handle, lifecycle.CLASSIFIED) == lifecycle.CLASSIFIED
            assert await handle.query(IssueLifecycle.stage) == "awaiting-human-decision"


@pytest.mark.timeout(90)
async def test_foreign_signal_does_not_move_a_parked_issue():
    """Случайный лейбл на припаркованном Issue не должен выбивать его из фазы:
    иначе любое чужое действие переписывало бы состояние."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_consultation]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.human_decision, "wontfix")
            await env.sleep(1)

            assert await handle.query(IssueLifecycle.phase) == lifecycle.ANSWERED
            assert (await handle.describe()).status.name == "RUNNING"


# --- сбой стадии ---

@pytest.mark.timeout(90)
async def test_failed_stage_becomes_a_phase_not_the_end():
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_fails_once]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            assert await _await_phase(env, handle, lifecycle.FAILED) == lifecycle.FAILED
            assert "error-label" in _calls, "сбой обязан быть виден в GitHub"
            assert (await handle.describe()).status.name == "RUNNING"


@pytest.mark.timeout(90)
async def test_reopen_after_failure_runs_the_triage_again():
    """Смысл фазы `failed` — возможность перезапуска. Без живого цикла человеку
    оставалось бы завести Issue заново."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_fails_once]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.FAILED)

            await handle.signal(IssueLifecycle.human_decision, "reopen")

            assert await _await_phase(env, handle, lifecycle.CLASSIFIED) == lifecycle.CLASSIFIED
            assert _calls.count("classify") == 2, "триаж не пошёл заново"


@pytest.mark.timeout(90)
async def test_analyze_after_a_failed_run_returns_the_issue_to_analysis():
    """`/analyze` по сорвавшемуся анализу — второй заход на ту же стадию.

    Без перехода `failed → business-analysis` команда выполнялась, ветка с
    требованиями появлялась, а фаза оставалась `failed`: задача навсегда
    стояла в очереди к человеку с готовыми требованиями на руках. Ровно это
    и случилось на стенде с #10 и #11.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES,
                                      *ANALYSIS_ACTIVITIES, classify_fails_once]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.FAILED)

            await handle.signal(IssueLifecycle.analyze_requested, None)

            assert await _await_phase(env, handle, lifecycle.READY_FOR_DEV) \
                == lifecycle.READY_FOR_DEV
            assert any(c.startswith("ready:") for c in _calls), \
                "передача разработчику не состоялась"


# --- continue-as-new ---

@pytest.mark.timeout(120)
async def test_continue_as_new_truncates_history_without_losing_state(monkeypatch):
    """Потолок истории — не гипотеза: консолидация уже упиралась в него на ~75
    Issue. Порог опускаем, чтобы проверить сам механизм, а не ждать 800 событий.

    Главное здесь не факт перезапуска, а то, что после него цикл продолжается с
    той же фазы и с тем же приоритетом: триаж не повторяется, а чеклист
    готовности получает посчитанный ранее tier, а не пустую строку.
    """
    _calls.clear()
    monkeypatch.setattr(workflows_module, "HISTORY_EVENT_THRESHOLD", 25)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_feature,
                                      *ANALYSIS_ACTIVITIES],
                          # порог читается из модуля: песочница импортировала бы
                          # его копию, и monkeypatch до воркфлоу не дошёл бы
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            for _ in range(60):
                if await handle.query(IssueLifecycle.generation) > 0:
                    break
                await env.sleep(1)
            assert await handle.query(IssueLifecycle.generation) > 0, "история не оборвалась"

            await handle.signal(IssueLifecycle.human_decision, "research-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)

    assert _calls.count("classify") == 1, "после перезапуска триаж пошёл по второму кругу"
    assert "ready:P1:research/issue-7" in _calls, "приоритет не пережил continue-as-new"


# --- совместимость поколений ---

def test_patch_marker_is_frozen():
    """Идентификатор патча — часть истории уже идущих прогонов. Переименование
    отправило бы припаркованные Issue в новый код на реплее, а это отказ по
    недетерминизму — самый дорогой класс в Temporal. Строка меняется только
    вместе с осознанным `workflow.deprecate_patch`."""
    src = inspect.getsource(IssueLifecycle.run)

    assert 'workflow.patched("issue-lifecycle-phase-loop")' in src


def test_analyze_recovery_is_behind_a_patch_marker():
    """Ход `failed → business-analysis` меняет РЕШЕНИЕ, уже записанное в истории.

    Прогоны, у которых `/analyze` из `failed` однажды отработал мимо пути,
    держат в истории `StartChildWorkflowExecutionInitiated`. Новый код на том же
    месте планирует активность смены фазы — и реплей падает по недетерминизму.
    Именно так на стенде встал воркфлоу Issue #11 после выкладки.
    """
    src = inspect.getsource(IssueLifecycle._analysis_requested)

    assert 'workflow.patched("issue-lifecycle-analyze-recovers-failed")' in src, (
        "новая ветка обязана быть под своим маркером патча")


def test_linear_path_is_still_reachable():
    """Пока в проде есть прогоны прежнего поколения, линейный сценарий обязан
    оставаться в коде: реплей их истории идёт именно по нему."""
    assert hasattr(IssueLifecycle, "_run_linear")
    assert "await self._run_linear(issue)" in inspect.getsource(IssueLifecycle.run)


@workflow.defn(name="IssueLifecycleLegacy")
class _LegacyLifecycle(IssueLifecycle):
    """Прежнее поколение под своим именем.

    Новый прогон всегда получает `patched() == True`, поэтому дотянуться до
    линейного пути обычным запуском нельзя — а проверять его надо: в проде на
    нём висят живые припаркованные Issue. Подкласс зовёт `_run_linear` напрямую,
    ничего в нём не меняя.
    """

    @workflow.run
    async def run(self, issue: IssueInput) -> None:
        self._issue = issue
        await self._run_linear(issue)


@pytest.mark.timeout(90)
async def test_previous_generation_still_completes_its_triage():
    """Изменение не должно ломать прогоны, запущенные до него: тот же триаж,
    тот же исход, та же стадия в query."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[_LegacyLifecycle],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_feature,
                                      *ANALYSIS_ACTIVITIES]):
            handle = await env.client.start_workflow(
                _LegacyLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            await handle.signal(IssueLifecycle.human_decision, "no-build")
            await handle.result()

            assert await handle.query(IssueLifecycle.stage) == "done"
            # Фаза прежнему поколению выводится из стадии, а не ведётся циклом.
            assert await handle.query(IssueLifecycle.phase) == lifecycle.READY_FOR_DEV

    assert "ready:P1:research/issue-7" in _calls
    assert not any(c.startswith("phase:") for c in _calls), (
        "линейный путь не должен писать метки фаз: их ведёт цикл")


@pytest.mark.timeout(120)
async def test_history_of_the_new_generation_replays_cleanly():
    """Реплей текущей истории текущим же кодом: страховка от недетерминизма,
    который иначе всплыл бы только при рестарте воркера в проде."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, *TRIAGE_ACTIVITIES, classify_feature,
                                      *ANALYSIS_ACTIVITIES]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            await _await_phase(env, handle, lifecycle.READY_FOR_DEV)
            history = await handle.fetch_history()

    await Replayer(workflows=[IssueLifecycle]).replay_workflow(history)
