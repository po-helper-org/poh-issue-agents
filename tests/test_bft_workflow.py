"""БФТ в Temporal: прогон командой, стадии глубокого пайплайна и триаж.

Поднимается настоящий воркфлоу — проверяется не намерение кода, а то, что
получилось: порядок стадий в истории, метки исхода, комментарий при сбое и
дочерний прогон под циклом Issue.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.api.enums.v1 import ParentClosePolicy as ProtoParentClosePolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import bft, lifecycle
from shared.workflow_ids import bft_workflow_id
from shared.workflow_types import (
    BftRequest,
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueBft, IssueLifecycle

REPO = "o/r"
ISSUE = 7

_calls: list[str] = []
_fail: set[str] = set()


# --- границы прогона БФТ ---

@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="post_agents_off_notice")
async def agents_off_notice(repo: str, issue_number: int, what: str) -> None:
    _calls.append(f"agents-off:{what}")


@activity.defn(name="ack_bft_command")
async def ack_bft(req: BftRequest) -> None:
    _calls.append(f"ack:{req.mode}:{req.comment_id}")


@activity.defn(name="run_bft_fast")
async def bft_fast(req: BftRequest) -> str:
    if "fast" in _fail:
        raise RuntimeError("модель не ответила")
    _calls.append(f"fast:{req.instructions}")
    return "письмо"


@activity.defn(name="prepare_bft_workspace")
async def bft_prepare(req: BftRequest) -> None:
    _calls.append("prepare")


@activity.defn(name="run_bft_stage")
async def bft_stage(req: BftRequest, stage_name: str) -> dict:
    if stage_name in _fail:
        raise RuntimeError(f"стадия {stage_name} упала")
    _calls.append(f"stage:{stage_name}")
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="publish_bft_deep")
async def bft_publish(req: BftRequest) -> str:
    _calls.append("publish")
    return bft.branch(ISSUE)


@activity.defn(name="cleanup_bft_workspace")
async def bft_cleanup(req: BftRequest) -> None:
    _calls.append("cleanup")


@activity.defn(name="publish_bft_error")
async def bft_error(req: BftRequest, reason: str) -> None:
    _calls.append(f"error:{reason[:20]}")


@activity.defn(name="finish_command_labels")
async def finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:
    _calls.append(f"finish:{command}:{ok}")


BFT_ACTIVITIES = [protocol_default, agents_off_notice, ack_bft, bft_fast,
                  bft_prepare, bft_stage, bft_publish, bft_cleanup, bft_error,
                  finish_labels]


def _req(**overrides) -> BftRequest:
    kwargs = dict(repo=REPO, issue_number=ISSUE, title="t", body="b", mode=bft.FAST)
    kwargs.update(overrides)
    return BftRequest(**kwargs)


async def _run_bft(req: BftRequest, extra=()) -> bool:
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueBft],
                          activities=[*BFT_ACTIVITIES, *extra]):
            return await env.client.execute_workflow(
                IssueBft.run, req, id=f"wf-{uuid.uuid4()}", task_queue=tq)


# --- Быстрый проход ---

@pytest.mark.timeout(90)
async def test_fast_run_acks_then_answers_and_marks_the_outcome():
    _fail.clear()
    assert await _run_bft(_req(comment_id=555, instructions="поправь цель")) is True

    assert _calls == ["ack:fast:555", "fast:поправь цель", "finish:bft:True"]


@pytest.mark.timeout(90)
async def test_fast_failure_leaves_a_comment_and_a_failed_label():
    """Требование постановки: при сбое обработки комментарий обязателен.
    Молчащий сбой неотличим от «ещё думает»."""
    _fail.clear()
    _fail.add("fast")
    assert await _run_bft(_req(comment_id=555)) is False

    assert any(c.startswith("error:") for c in _calls), "человек не узнал о сбое"
    assert "finish:bft:False" in _calls


@pytest.mark.timeout(90)
async def test_agents_off_stops_before_any_work():
    """R4: смысл рубильника в том, чтобы не потратить бюджет, а не в том, чтобы
    красиво остановиться посередине."""
    @activity.defn(name="read_protocol_state")
    async def agents_off(repo: str, issue_number: int) -> ProtocolState:
        return ProtocolState(agents_off=True)

    _fail.clear()
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        others = [a for a in BFT_ACTIVITIES if a is not protocol_default]
        async with Worker(env.client, task_queue=tq, workflows=[IssueBft],
                          activities=[*others, agents_off]):
            result = await env.client.execute_workflow(
                IssueBft.run, _req(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

    assert result is False
    assert _calls == ["agents-off:/bft"], "прогон не должен был начаться"


# --- Глубокий прогон ---

@pytest.mark.timeout(120)
async def test_deep_run_walks_the_canonical_pipeline_stage_by_stage():
    """Каждая стадия — свой шаг Event History: одной активностью пайплайн был бы
    чёрным ящиком на десятки минут, и застрявшая стадия не называла бы себя."""
    _fail.clear()
    assert await _run_bft(_req(mode=bft.DEEP, comment_id=9)) is True

    stages = [c.split(":", 1)[1] for c in _calls if c.startswith("stage:")]
    assert stages == list(bft.DEEP_STAGE_NAMES)
    assert _calls.index("prepare") < _calls.index("stage:index")
    assert _calls.index("stage:validate") < _calls.index("publish")
    assert "cleanup" in _calls
    assert "finish:bft-deep:True" in _calls


@pytest.mark.timeout(120)
async def test_a_broken_stage_still_cleans_up_and_reports():
    """Каталог живёт вне Temporal: не сняв его, воркер копил бы клоны репозитория
    на каждом сорвавшемся прогоне."""
    _fail.clear()
    _fail.add("concept")
    assert await _run_bft(_req(mode=bft.DEEP)) is False

    assert "stage:debate" not in _calls, "после сбоя пайплайн обязан остановиться"
    assert any(c.startswith("error:") for c in _calls)
    assert "cleanup" in _calls
    assert "finish:bft-deep:False" in _calls


@pytest.mark.timeout(120)
async def test_a_running_stage_names_itself_in_temporal():
    """Прогон, стоящий сорок минут на `concept`, обязан отличаться в UI от
    зависшего. Без этого значения оба выглядят как `Running`."""
    import asyncio

    _fail.clear()
    _calls.clear()
    seen: list[str] = []

    @activity.defn(name="run_bft_stage")
    async def slow_stage(req: BftRequest, stage_name: str) -> dict:
        if stage_name == "problem":
            await asyncio.sleep(0.4)
        _calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        others = [a for a in BFT_ACTIVITIES if a is not bft_stage]
        async with Worker(env.client, task_queue=tq, workflows=[IssueBft],
                          activities=[*others, slow_stage]):
            handle = await env.client.start_workflow(
                IssueBft.run, _req(mode=bft.DEEP), id=f"wf-{uuid.uuid4()}",
                task_queue=tq)
            for _ in range(200):
                seen.append(await handle.query(IssueBft.stage))
                if "publish" in _calls:
                    break
                await asyncio.sleep(0.01)
            assert await handle.query(IssueBft.mode) == bft.DEEP
            await handle.result()

    # Именно `problem` задержан искусственно — на нём опрос обязан застать
    # прогон. Остальные стадии проскакивают быстрее интервала опроса, и
    # требовать их в выборке значило бы проверять скорость заглушки.
    assert "problem" in seen, f"стадия не назвала себя: {seen}"


@pytest.mark.timeout(90)
async def test_a_failed_cleanup_does_not_flip_a_successful_run():
    """Уборка — best-effort. Её сбой затёр бы реальный исход прогона: человек
    получил бы «БФТ не собрался» на собранный и опубликованный документ."""
    _fail.clear()
    _calls.clear()

    @activity.defn(name="cleanup_bft_workspace")
    async def cleanup_boom(req: BftRequest) -> None:
        raise RuntimeError("каталог занят")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        others = [a for a in BFT_ACTIVITIES if a is not bft_cleanup]
        async with Worker(env.client, task_queue=tq, workflows=[IssueBft],
                          activities=[*others, cleanup_boom]):
            result = await env.client.execute_workflow(
                IssueBft.run, _req(mode=bft.DEEP), id=f"wf-{uuid.uuid4()}",
                task_queue=tq)

    assert result is True
    assert "publish" in _calls
    assert not any(c.startswith("error:") for c in _calls)
    assert "finish:bft-deep:True" in _calls


@pytest.mark.timeout(90)
async def test_a_raw_dict_input_is_normalised():
    """Скрипты прямого запуска шлют сырой словарь. Молча получить dict вместо
    dataclass хуже, чем упасть: сбой вскроется на первом обращении к полю."""
    _fail.clear()
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueBft],
                          activities=BFT_ACTIVITIES):
            result = await env.client.execute_workflow(
                IssueBft.run,
                {"repo": REPO, "issue_number": ISSUE, "title": "t", "body": "b",
                 "mode": bft.FAST},
                id=f"wf-{uuid.uuid4()}", task_queue=tq)

    assert result is True
    assert "finish:bft:True" in _calls


@pytest.mark.timeout(90)
async def test_fast_run_does_not_touch_the_deep_workspace():
    """Быстрый проход — один вызов модели: ни клона, ни уборки ему не нужно."""
    _fail.clear()
    await _run_bft(_req())

    assert "prepare" not in _calls
    assert "cleanup" not in _calls


# --- Под циклом Issue ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None: ...


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_deadlines")
async def deadlines_with_bft() -> Deadlines:
    return Deadlines(decompose_enabled=False, bft_on_triage=True)


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


@activity.defn(name="intake_gate")
async def gate_ok(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    _calls.append(f"classify:bft={bft_on_triage}")
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score_p1(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P1", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None:
    _calls.append("priority")


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="post_error_label")
async def post_error(issue: IssueInput, reason: str) -> None:
    _calls.append(f"triage-failed:{reason[:20]}")


CYCLE_ACTIVITIES = [awaiting_stub, prefilter_ok, protocol_default, deadlines_with_bft,
                    set_phase_stub, gate_ok, classify_feature, duplicate_none,
                    score_p1, post_priority, escalate, post_error, ack_bft, bft_fast,
                    bft_prepare, bft_stage, bft_publish, bft_cleanup, bft_error,
                    finish_labels]


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=ISSUE, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


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
async def test_triage_answers_a_feature_request_with_bft():
    """Определение готовности: новый Issue-запрос функционала получает БФТ, а не
    свободный advisor-ответ, и триаж идёт дальше как прежде."""
    _fail.clear()
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueBft],
                          activities=CYCLE_ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            assert await _await_phase(env, handle, lifecycle.CLASSIFIED) == \
                lifecycle.CLASSIFIED

    assert "classify:bft=True" in _calls, "классификация не узнала о БФТ"
    assert "fast:" in _calls, "БФТ на триаже не собрался"
    # Триаж не оборвался на БФТ: приоритет посчитан, Issue доехал до парковки.
    assert _calls.index("fast:") < _calls.index("priority")
    # Шаг триажа, а не отдельный прогон: метки команды тут ни при чём.
    assert not any(c.startswith("finish:") for c in _calls)


@pytest.mark.timeout(120)
async def test_a_broken_bft_does_not_cost_the_issue_its_triage():
    """Дедуп и приоритет нужны в любом случае. Оставить Issue без приоритета
    из-за несобравшегося письма — худший из двух исходов."""
    _fail.clear()
    _fail.add("fast")
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueBft],
                          activities=CYCLE_ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            assert await _await_phase(env, handle, lifecycle.CLASSIFIED) == \
                lifecycle.CLASSIFIED

    assert any(c.startswith("error:") for c in _calls), "человек не узнал о сбое"
    assert "priority" in _calls
    assert not any(c.startswith("triage-failed") for c in _calls)


@pytest.mark.timeout(120)
async def test_bft_command_runs_as_a_child_without_moving_the_phase():
    """БФТ — боковая команда: она обязана отработать, но состояние Issue не
    двигать. Фаза `business-analysis` принадлежит цепочке FNR, и занять её
    значило бы объявить два разных документа одной стадией."""
    _fail.clear()
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueBft],
                          activities=CYCLE_ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.CLASSIFIED)

            await handle.signal(IssueLifecycle.bft_requested,
                                _req(mode=bft.DEEP, instructions="курс у ЦБ"))
            for _ in range(300):
                if "publish" in _calls:
                    break
                await env.sleep(1)
            phase = await handle.query(IssueLifecycle.phase)
            children = await _child_starts(handle)

    assert phase == lifecycle.CLASSIFIED, "БФТ сдвинул фазу, хотя не должен"
    ids = [c.workflow_id for c in children]
    assert bft_workflow_id(REPO, ISSUE, bft.DEEP) in ids
    assert [c.parent_close_policy for c in children
            if c.workflow_id == bft_workflow_id(REPO, ISSUE, bft.DEEP)] == [
        ProtoParentClosePolicy.PARENT_CLOSE_POLICY_ABANDON
    ], "многоминутный прогон погибнет вместе с родителем"


@pytest.mark.timeout(120)
async def test_the_two_modes_do_not_block_each_other():
    """Быстрый и глубокий — разные прогоны с разными id: человек вправе уточнить
    формулировку и тут же заказать полный документ."""
    assert bft_workflow_id(REPO, ISSUE, bft.FAST) != \
        bft_workflow_id(REPO, ISSUE, bft.DEEP)
