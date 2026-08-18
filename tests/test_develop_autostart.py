"""Замкнутый контур: от Issue до PR без касания человека.

`DEVELOP_AUTOSTART` снимает единственную парковку, оставшуюся на основном пути
после аналитики. Проверяем, что снимается именно она и только она: задача сама
уезжает в разработку, а без флага по-прежнему ждёт решения человека (H1).
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import activities as activities_module
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


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


# --- чтение тумблера ---

@pytest.mark.parametrize("raw", ["1", "true", "YES", "on"])
def test_autostart_reads_as_on(monkeypatch, raw):
    monkeypatch.setenv("DEVELOP_AUTOSTART", raw)

    assert activities_module.read_deadlines().develop_autostart is True


def test_autostart_is_off_by_default(monkeypatch):
    """Умолчание — протокол в чистом виде: разработку начинает решение человека.
    Замкнутый контур включают осознанно, а не забыв переменную."""
    monkeypatch.delenv("DEVELOP_AUTOSTART", raising=False)

    assert activities_module.read_deadlines().develop_autostart is False


# --- заглушки контура ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    _calls.append("awaiting")


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="intake_gate")
async def gate(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P1", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None: ...


@activity.defn(name="mark_command_running")
async def mark_running(repo: str, issue_number: int, command: str) -> None: ...


@activity.defn(name="finish_command_labels")
async def finish(repo: str, issue_number: int, command: str, ok: bool) -> None: ...


@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None: ...


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
    _calls.append("ready-for-dev")


@activity.defn(name="trigger_openhands_resolver")
async def develop(issue: IssueInput) -> None:
    _calls.append("develop")


def _deadlines(autostart: bool):
    @activity.defn(name="read_deadlines")
    async def stub() -> Deadlines:
        return Deadlines(develop_autostart=autostart)
    return stub


async def _run_until_parked(autostart: bool) -> None:
    """Гоняет цикл до парковки после аналитики и снимает его.

    Прогон намеренно не доводится до конца: при автостарте цикл уходит в
    `in-development` и ждёт события от внешнего агента, которого в тесте нет.
    Проверяем то, что произошло ДО парковки.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, protocol_default,
                                      _deadlines(autostart), gate, classify, duplicate,
                                      score, post_priority, mark_running, finish, ack,
                                      prepare, stage_ok, publish, cleanup, publish_error,
                                      ready, develop, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            for _ in range(100):
                if "develop" in _calls or _calls.count("awaiting") >= 2:
                    break
                await asyncio.sleep(0.05)
            await handle.terminate()


@pytest.mark.timeout(120)
async def test_autostart_sends_the_task_to_development_itself():
    await _run_until_parked(autostart=True)

    assert "develop" in _calls
    # Метка передачи ставится всё равно: она сообщает состояние задачи, а не то,
    # кто именно её возьмёт.
    assert _calls.index("ready-for-dev") < _calls.index("develop")


@pytest.mark.timeout(120)
async def test_without_autostart_the_task_waits_for_a_human():
    await _run_until_parked(autostart=False)

    assert "ready-for-dev" in _calls
    assert "develop" not in _calls


# --- Своя метка не заводит второй прогон ---

@activity.defn(name="trigger_openhands_resolver")
async def develop_noop(issue: IssueInput) -> None: ...


@pytest.mark.timeout(120)
async def test_own_run_label_does_not_start_a_second_analysis():
    """Пока прогон идёт, `ack_command` вешает `run:analyze`. Вебхук видит
    `issues.labeled` и шлёт команду обратно в цикл — своя метка возвращается
    как новая команда. На живом стенде это дало три прогона подряд по одному
    Issue."""
    started: list[str] = []

    @activity.defn(name="ack_command")
    async def slow_ack(analyze: AnalyzeInput) -> None:
        started.append("run")
        # Пока прогон идёт, прилетает эхо своей метки.
        await asyncio.sleep(1.0)

    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, protocol_default,
                                      _deadlines(False), gate, classify, duplicate,
                                      score, post_priority, mark_running, finish,
                                      slow_ack, prepare, stage_ok, publish, cleanup,
                                      publish_error, ready, develop_noop, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            # Ждём, пока прогон реально начнётся: иначе сигнал прилетает до
            # него, и второй прогон — законный повтор, а не эхо.
            for _ in range(200):
                if started:
                    break
                await asyncio.sleep(0.02)
            # эхо метки: три доставки подряд, пока прогон ещё идёт
            for _ in range(3):
                await handle.signal(IssueLifecycle.analyze_requested, None)
            for _ in range(100):
                if "ready-for-dev" in _calls:
                    break
                await asyncio.sleep(0.05)
            await handle.terminate()

    assert len(started) == 1, f"прогонов аналитики: {len(started)}, ожидался один"
