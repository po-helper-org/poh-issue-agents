"""Разработка действительно становится дочерним прогоном цикла.

Тест воркфлоу (`test_develop_workflow.py`) проверяет порядок шагов, но не то,
что получилось в Temporal. Здесь поднимается настоящий `IssueLifecycle` и
проверяется результат: разработка видна как child владельца состояния Issue,
несёт канонический id и переживает завершение родителя.
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import ParentClosePolicy as ProtoParentClosePolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.workflow_ids import development_workflow_id
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

REPO = "o/r"
ISSUE = 39

_calls: list[str] = []


# --- границы триажа (та же раскладка, что в test_agents_as_children.py) ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None: ...


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_open_questions")
async def no_open_questions(repo: str, branch: str) -> list[str]: return []


@activity.defn(name="read_deadlines")
async def deadlines_autostart() -> Deadlines:
    """Автостарт включён: тест о том, что разработка стартует дочерним прогоном,
    а не о том, кто принимает решение о сборке."""
    return Deadlines(decompose_enabled=False, develop_autostart=True)


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


# "advisor:bug", а не "advisor:feature-request": без RESEARCH_AUTOSTART (в
# этом тесте он выключен умолчанием Deadlines) feature-запрос идёт в
# business-analysis — пять стадий FNR, свой набор активностей, чужая стадия.
# Классификация "bug" по сигналу `bug-me` ведёт прямиком в `ready-for-dev` —
# ровно туда, откуда начинается то, что здесь проверяется.
@activity.defn(name="classify_issue")
async def classify_bug(issue: IssueInput) -> ClassificationResult:
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
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="post_error_label")
async def post_error(issue: IssueInput, reason: str) -> None:
    _calls.append(f"error:{reason[:40]}")


@activity.defn(name="mark_ready_for_dev")
async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None: ...


# --- границы разработки ---

@activity.defn(name="dev_begin")
async def begin_local(issue: IssueInput) -> DevelopPlan:
    return DevelopPlan(mode="local", branch="research/issue-39")


@activity.defn(name="dev_begin")
async def begin_never_returns(issue: IssueInput) -> DevelopPlan:
    """Никогда не завершается — держит канонический id «занятым» весь тест,
    как держал бы его чужой прогон `IssueDevelopment`, переживший terminate
    своего родителя (`ParentClosePolicy.ABANDON`)."""
    await asyncio.Event().wait()


@activity.defn(name="dev_dispatch")
async def dispatch_stub(issue: IssueInput, branch: str) -> None: ...


@activity.defn(name="dev_prepare")
async def prepare_ok(issue: IssueInput, branch: str) -> int: return 1780


@activity.defn(name="dev_announce")
async def announce_ok(issue: IssueInput, branch: str) -> None:
    _calls.append("announce")


@activity.defn(name="dev_run_agent")
async def agent_ok(issue: IssueInput) -> None:
    _calls.append("agent")


@activity.defn(name="dev_followups")
async def followups_ok(issue: IssueInput) -> list[int]: return []


# Имя НЕ должно начинаться на `test` — иначе pytest подхватит эту async-функцию
# как тестовый кейс сам по себе (у неё нет фикстуры `issue`, и сбор тестов
# всего файла упадёт). На этом уже спотыкались в предыдущей задаче.
@activity.defn(name="dev_tests")
async def checks_ok(issue: IssueInput) -> None: ...


@activity.defn(name="dev_publish")
async def publish_ok(issue: IssueInput, branch: str) -> int | None:
    _calls.append("publish")
    return 101


ALL_ACTIVITIES = [prefilter_ok, protocol_default, deadlines_autostart, set_phase_stub,
                  gate_ok, classify_bug, duplicate_none, score_p1, post_priority,
                  escalate, post_error, ready, no_open_questions, awaiting_stub,
                  begin_local, dispatch_stub, prepare_ok, announce_ok, agent_ok,
                  followups_ok, checks_ok, publish_ok]


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=ISSUE, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _worker(env, tq):
    return Worker(env.client, task_queue=tq,
                  workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                             IssueDevelopment],
                  activities=ALL_ACTIVITIES)


async def _await_phase(env, handle, expected: str) -> str:
    for _ in range(300):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


async def _child_starts(handle) -> list:
    out = []
    async for ev in handle.fetch_history_events():
        if ev.HasField("start_child_workflow_execution_initiated_event_attributes"):
            out.append(ev.start_child_workflow_execution_initiated_event_attributes)
    return out


@pytest.mark.timeout(120)
async def test_development_runs_as_a_child_with_the_canonical_id():
    """Определение готовности FNR-6: разработка видна отдельным прогоном с
    предсказуемым id — по нему и восстанавливается операционная история."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # RESEARCH_AUTOSTART здесь не включён (умолчание Deadlines) — это
            # решение сборки, не решение "что вообще делать с Issue". До
            # `ready-for-dev` доходим тем же путём, что и человек: `bug-me`.
            # Дальше — уже развилка под маркером патча, которая и проверяется.
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            await _await_phase(env, handle, lifecycle.PR_OPEN)
            children = await _child_starts(handle)

    ids = [c.workflow_id for c in children]
    assert development_workflow_id(REPO, ISSUE) in ids, (
        f"разработка не стала дочерним прогоном: {ids}"
    )
    assert "publish" in _calls, "цикл не дождался результата дочернего прогона"


@pytest.mark.timeout(120)
async def test_the_development_child_survives_the_parent():
    """Прогон агента идёт до 45 минут. Ни continue-as-new родителя, ни его
    завершение не должны его убивать — иначе дорогой прогон обрывается по
    причине, к нему не относящейся."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with _worker(env, tq):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # RESEARCH_AUTOSTART здесь не включён (умолчание Deadlines) — это
            # решение сборки, не решение "что вообще делать с Issue". До
            # `ready-for-dev` доходим тем же путём, что и человек: `bug-me`.
            # Дальше — уже развилка под маркером патча, которая и проверяется.
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            await _await_phase(env, handle, lifecycle.PR_OPEN)
            children = await _child_starts(handle)

    develop_children = [c for c in children
                        if c.workflow_id == development_workflow_id(REPO, ISSUE)]
    assert [c.parent_close_policy for c in develop_children] == [
        ProtoParentClosePolicy.PARENT_CLOSE_POLICY_ABANDON
    ], "дочерний прогон разработки погибнет вместе с родителем"


@pytest.mark.timeout(120)
async def test_a_collision_with_an_orphaned_run_parks_instead_of_spinning():
    """Находка 2: чужой прогон занял канонический id — второй `IssueLifecycle`
    не должен вращаться вхолостую.

    Сценарий: человек терминировал зависший `IssueLifecycle`, пока его
    дочерний `develop-*` ещё жив (`ParentClosePolicy.ABANDON` его сохраняет).
    Новый цикл по тому же Issue доходит до автостарта и натыкается на
    `WorkflowAlreadyStartedError` — здесь это смоделировано прогоном
    `IssueDevelopment`, который занимает канонический id напрямую и никогда
    не возвращается (как и держал бы его настоящий осиротевший дочерний
    прогон).

    Раньше обработчик возвращал ТЕКУЩУЮ фазу (`ready-for-dev`), что для
    автостарта означало немедленный повторный заход в `_start_development` на
    следующем же витке цикла — без единой парковки между попытками. Здесь это
    было бы видно как фаза, застрявшая на `ready-for-dev` (или полное
    исчерпание таймаута теста на попытках повторного `start_child_workflow`),
    а не честный переход в `in-development`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        acts = [begin_never_returns if a is begin_local else a for a in ALL_ACTIVITIES]
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation,
                                     IssueDevelopment],
                          activities=acts):
            # Занимаем канонический id НАПРЯМУЮ — как будто прежний
            # `IssueLifecycle` его уже запустил и был снят человеком.
            await env.client.start_workflow(
                IssueDevelopment.run, _issue(),
                id=development_workflow_id(REPO, ISSUE), task_queue=tq)

            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)
            await handle.signal(IssueLifecycle.human_decision, "bug-me")
            phase = await _await_phase(env, handle, lifecycle.IN_DEVELOPMENT)

    assert phase == lifecycle.IN_DEVELOPMENT, (
        f"второй прогон наткнулся на WorkflowAlreadyStarted, но не признал, что "
        f"разработка уже идёт где-то ещё — застрял на {phase!r}"
    )
    assert "publish" not in _calls, (
        "второй прогон не должен был запустить СВОЙ прогон разработки")
