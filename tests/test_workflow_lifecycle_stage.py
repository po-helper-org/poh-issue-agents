"""Query `stage`: припаркованный прогон обязан быть отличим от зависшего.

Прогон, ждущий лейбла, в UI выглядит как `Running` бессрочно. До query понять,
жив он или встал, можно было только разбирая Event History руками.
"""

import uuid

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
from workflows import IssueLifecycle


def _issue(interactive: bool = True) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=interactive)


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput): return None


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    """Сроки по умолчанию: тесты проверяют маршруты, а не сами таймеры."""
    return Deadlines()


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    """Обычный Issue от человека: рубильник выключен, цепочки нет."""
    return ProtocolState()


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_skip(issue: IssueInput): return "bot-authored"


@activity.defn(name="intake_gate")
async def gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="intake_gate")
async def gate_spam(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SPAM", content="реклама")


@activity.defn(name="intake_gate")
async def gate_vague(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="VAGUE", content="нужны детали")


@activity.defn(name="close_as_spam")
async def close_as_spam(issue: IssueInput, reason: str) -> None: ...


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput) -> None: ...


@activity.defn(name="classify_issue")
async def classify_feature(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="classify_issue")
async def classify_consultation(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:consultation", answer="ответ")


@activity.defn(name="duplicate_check")
async def duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="duplicate_check")
async def duplicate_found(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="duplicate", best_match_number=3,
                           probability=0.9, reason="дубль", context_branch=None)


@activity.defn(name="score_priority")
async def score(issue: IssueInput, c: ClassificationResult, d: DuplicateResult) -> PriorityResult:
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p: PriorityResult, d: DuplicateResult) -> None: ...


async def _run_to_completion(activities_list, issue: IssueInput) -> str:
    """Гоняет workflow до конца и возвращает финальную стадию."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[*activities_list, protocol_default, deadlines_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, issue, id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.result()
            return await handle.query(IssueLifecycle.stage)


@pytest.mark.timeout(60)
async def test_parked_run_says_it_waits_for_a_human():
    """Главный случай: прогон жив и ждёт лейбла, а не завис."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[prefilter_ok, gate_sufficient, classify_feature,
                                      duplicate_none, score, post_priority,
                                      protocol_default, deadlines_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            async def parked() -> bool:
                return await handle.query(IssueLifecycle.stage) == "awaiting-human-decision"

            # Триаж отрабатывает и паркуется; ждём именно этого состояния.
            for _ in range(200):
                if await parked():
                    break
                await env.sleep(1)

            assert await handle.query(IssueLifecycle.stage) == "awaiting-human-decision"
            # Прогон при этом действительно жив — принимает сигнал и идёт дальше.
            await handle.signal(IssueLifecycle.human_decision, "не-тот-лейбл")
            await handle.result()


@pytest.mark.timeout(60)
async def test_prefiltered_run_reports_skipped():
    stage = await _run_to_completion([prefilter_skip], _issue())
    assert stage == "skipped"


@pytest.mark.timeout(60)
async def test_spam_is_terminal_and_named():
    stage = await _run_to_completion([prefilter_ok, gate_spam, close_as_spam], _issue())
    assert stage == "spam"


@pytest.mark.timeout(60)
async def test_batch_vague_reports_escalated():
    stage = await _run_to_completion([prefilter_ok, gate_vague, escalate],
                                     _issue(interactive=False))
    assert stage == "escalated"


@pytest.mark.timeout(60)
async def test_substantive_answer_reports_answered():
    stage = await _run_to_completion(
        [prefilter_ok, gate_sufficient, classify_consultation], _issue())
    assert stage == "answered"


@pytest.mark.timeout(60)
async def test_duplicate_is_terminal_and_named():
    stage = await _run_to_completion(
        [prefilter_ok, gate_sufficient, classify_feature, duplicate_found], _issue())
    assert stage == "duplicate"


@pytest.mark.timeout(60)
async def test_stage_starts_at_intake():
    """До первого шага стадия уже осмысленна, а не пустая строка."""
    assert IssueLifecycle().stage() == "intake"
