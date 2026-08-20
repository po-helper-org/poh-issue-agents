"""Круг уточнений ПОСЛЕ аналитики: открытые вопросы закрываются, а не переносятся.

Цикл уточнений на входе (intake gate) спрашивает про постановку — «что вообще
нужно». Аналитика задаёт другие вопросы: она разобрала код и знает, чего в
постановке не хватает, чтобы решение было однозначным. До сих пор такие вопросы
просто перечислялись в чеклисте готовности — то есть перекладывались на агента
разработки, который выбрал бы за человека и молча.

Здесь проверяется, что вопрос задаётся и его ждут, а ответ закрывает круг: он
попадает в контекст повторного прогона аналитики (тот читает обсуждение Issue).
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.workflow_types import (
    AnalyzeInput,
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

_calls: list[str] = []


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    _calls.append("awaiting" if waiting is not None else "awaiting:off")


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines(research_autostart=True, develop_autostart=True)


@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


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
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="mark_command_running")
async def mark_running(repo: str, n: int, command: str) -> None: ...


@activity.defn(name="finish_command_labels")
async def finish(repo: str, n: int, command: str, ok: bool) -> None: ...


@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="prepare_workspace")
async def prepare(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="run_fnr_stage")
async def stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    if stage_name == "task":
        _calls.append("analysis")
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
async def develop(issue: IssueInput) -> int | None:
    _calls.append("develop")
    return 42


# Разработка ушла в дочерний воркфлоу `IssueDevelopment` (#FNR-6):
# `_start_development` под маркером патча (в тесте он всегда взведён) зовёт
# его вместо `trigger_openhands_resolver` напрямую. Незарегистрированный
# дочерний воркфлоу не даёт быстрой ошибки — родитель просто ждёт исполнителя,
# которого нет, и тест висит до таймаута. Режим "local" и отметку «develop» на
# прогоне агента воспроизводят прежнее поведение стаба (PR открыт сразу).
@activity.defn(name="dev_begin")
async def dev_begin_local(issue: IssueInput) -> DevelopPlan:
    return DevelopPlan(mode="local", branch=f"research/issue-{issue.issue_number}")


@activity.defn(name="dev_dispatch")
async def dev_dispatch_stub(issue: IssueInput, branch: str) -> None: ...


@activity.defn(name="dev_prepare")
async def dev_prepare_ok(issue: IssueInput, branch: str) -> int: return 1780


@activity.defn(name="dev_announce")
async def dev_announce_ok(issue: IssueInput, branch: str) -> None: ...


@activity.defn(name="dev_run_agent")
async def dev_agent_ok(issue: IssueInput) -> None:
    _calls.append("develop")


@activity.defn(name="dev_followups")
async def dev_followups_ok(issue: IssueInput) -> list[int]: return []


@activity.defn(name="dev_tests")
async def dev_checks_ok(issue: IssueInput) -> None: ...


@activity.defn(name="dev_publish")
async def dev_publish_ok(issue: IssueInput, branch: str) -> int | None: return 42


DEV_STEPS = [dev_begin_local, dev_dispatch_stub, dev_prepare_ok, dev_announce_ok,
             dev_agent_ok, dev_followups_ok, dev_checks_ok, dev_publish_ok]


@activity.defn(name="decompose_issue")
async def decompose(issue: IssueInput, branch: str) -> dict:
    _calls.append("decompose")
    return {"summary": "", "items": []}


@activity.defn(name="publish_decomposition")
async def publish_plan(issue: IssueInput, plan: dict, branch: str) -> list[int]:
    return []


@activity.defn(name="ask_open_questions")
async def ask(issue: IssueInput, questions: list[str], round_number: int) -> None:
    _calls.append(f"ask:{round_number}:{len(questions)}")


def _questions_then_none():
    """Первый прогон оставил вопрос, второй — нет: ответ его закрыл."""
    asked = {"n": 0}

    @activity.defn(name="read_open_questions")
    async def read(repo: str, branch: str) -> list[str]:
        asked["n"] += 1
        return ["system_requirements.md: [УТОЧНИТЬ] округлять вверх или вниз?"] \
            if asked["n"] == 1 else []

    return read


BASE = [awaiting_stub, prefilter_ok, protocol_default, deadlines_stub, phase_stub,
        gate_ok, classify_feature, duplicate_none, score_p1, post_priority, escalate,
        mark_running, finish, ack, prepare, stage_ok, publish, cleanup, publish_error,
        ready, develop, decompose, publish_plan, ask, *DEV_STEPS]


async def _await_phase(env, handle, expected: str, tries: int = 300) -> str:
    for _ in range(tries):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


@pytest.mark.timeout(120)
async def test_open_question_stops_the_handoff_and_is_asked():
    """Пока вопрос открыт, задача не уезжает ни в декомпозицию, ни в разработку."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                                     IssueDevelopment],
                          activities=[*BASE, _questions_then_none()]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            for _ in range(300):
                if any(c.startswith("ask:") for c in _calls):
                    break
                await env.sleep(1)
            phase = await handle.query(IssueLifecycle.phase)
            await handle.terminate()

    assert "ask:1:1" in _calls, f"вопрос не задан: {_calls}"
    assert "decompose" not in _calls, "план построен по неполной постановке"
    assert "ready-for-dev" not in _calls, "задача передана с открытым вопросом"
    assert "develop" not in _calls
    assert phase == lifecycle.SYSTEM_REQUIREMENTS


@pytest.mark.timeout(120)
async def test_answer_closes_the_round_and_the_task_moves_on():
    """Ответ человека возвращает задачу в анализ: повторный прогон читает
    обсуждение Issue, и вопрос закрывается тем же способом, которым возник."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                                     IssueDevelopment],
                          activities=[*BASE, _questions_then_none()]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            for _ in range(300):
                if any(c.startswith("ask:") for c in _calls):
                    break
                await env.sleep(1)

            await handle.signal(IssueLifecycle.user_comment, "округляем вниз")

            for _ in range(300):
                if "develop" in _calls:
                    break
                await env.sleep(1)
            await handle.terminate()

    assert _calls.count("analysis") == 2, f"анализ не пошёл заново: {_calls}"
    assert "decompose" in _calls
    assert "ready-for-dev" in _calls
    assert "develop" in _calls
