"""Правило R3: каждая парковка имеет дедлайн.

Ожидание человека без срока превращается в вечную сессию — ровно ту категорию,
ради управления которой брали Temporal.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import activities as activities_module
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

_calls: list[str] = []


# --- чтение сроков ---

def test_defaults_are_finite(monkeypatch):
    for var in ("PARK_DECISION_HOURS", "PARK_CLARIFICATION_HOURS", "PARK_BUILD_HOURS"):
        monkeypatch.delenv(var, raising=False)

    d = activities_module.read_deadlines()

    assert d.human_decision_hours > 0
    assert d.clarification_hours > 0
    assert d.build_decision_hours > 0


def test_env_overrides_deadlines(monkeypatch):
    monkeypatch.setenv("PARK_DECISION_HOURS", "12")
    monkeypatch.setenv("PARK_CLARIFICATION_HOURS", "6")
    monkeypatch.setenv("PARK_BUILD_HOURS", "24")

    d = activities_module.read_deadlines()

    assert (d.human_decision_hours, d.clarification_hours, d.build_decision_hours) == (12, 6, 24)


def test_garbage_value_falls_back_to_default(monkeypatch):
    """Опечатка в .env не должна ронять обработку Issue."""
    monkeypatch.setenv("PARK_DECISION_HOURS", "три дня")

    assert activities_module.read_deadlines().human_decision_hours == 72


def test_zero_and_negative_fall_back(monkeypatch):
    """0 означал бы «истекло сразу» — почти наверняка опечатка, а не намерение."""
    monkeypatch.setenv("PARK_DECISION_HOURS", "0")
    assert activities_module.read_deadlines().human_decision_hours == 72

    monkeypatch.setenv("PARK_DECISION_HOURS", "-5")
    assert activities_module.read_deadlines().human_decision_hours == 72


# --- поведение воркфлоу на истёкшем сроке ---

@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput):
    return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


def _deadlines_stub(deadlines: Deadlines):
    @activity.defn(name="read_deadlines")
    async def read() -> Deadlines:
        return deadlines

    return read


@activity.defn(name="intake_gate")
async def gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="intake_gate")
async def gate_vague(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="VAGUE", content="нужны детали")


@activity.defn(name="post_clarifying_question")
async def ask(issue: IssueInput, questions: str) -> None:
    _calls.append("asked")


@activity.defn(name="classify_issue")
async def classify(issue: IssueInput) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None:
    _calls.append("priority_posted")


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None:
    _calls.append(f"escalate:{reason}")


def _issue(interactive: bool = True) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=interactive)


async def _run(acts, deadlines: Deadlines) -> str:
    """Прогон БЕЗ сигналов: время в тестовом окружении проматывается само,
    поэтому парковка упирается ровно в дедлайн."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle],
                          activities=[*acts, _deadlines_stub(deadlines)]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.result()
            return await handle.query(IssueLifecycle.stage)


@pytest.mark.timeout(90)
async def test_decision_wait_has_an_exit_in_time():
    """Главный случай: лейбл `research-me` не поставили никогда — сессия обязана
    завершиться сама, а не висеть в списке зависших."""
    stage = await _run(
        [prefilter_ok, protocol_default, gate_sufficient, classify, duplicate,
         score, post_priority, escalate],
        Deadlines(human_decision_hours=1),
    )

    assert stage == "escalated"
    assert any("Решение о тяжёлой стадии" in c for c in _calls)


@pytest.mark.timeout(90)
async def test_deadline_message_names_the_term_and_the_way_back():
    """Человек должен понять, сколько ждали и что делать дальше."""
    await _run(
        [prefilter_ok, protocol_default, gate_sufficient, classify, duplicate,
         score, post_priority, escalate],
        Deadlines(human_decision_hours=5),
    )

    reason = next(c for c in _calls if c.startswith("escalate:"))
    assert "5 ч" in reason
    assert "research-me" in reason


@pytest.mark.timeout(90)
async def test_clarification_wait_has_an_exit_in_time():
    """Уточняющий вопрос задан, ответа нет — цикл не должен ждать вечно."""
    stage = await _run(
        [prefilter_ok, protocol_default, gate_vague, ask, escalate],
        Deadlines(clarification_hours=2),
    )

    assert stage == "escalated"
    assert "asked" in _calls
    assert any("Уточнение не получено" in c for c in _calls)


@pytest.mark.timeout(90)
async def test_priority_is_posted_before_the_deadline_exit():
    """Истёкший срок не должен отменять уже сделанную работу: приоритет
    выставлен, и Issue уходит человеку с ним, а не пустым."""
    await _run(
        [prefilter_ok, protocol_default, gate_sufficient, classify, duplicate,
         score, post_priority, escalate],
        Deadlines(human_decision_hours=1),
    )

    assert _calls.index("priority_posted") < next(
        i for i, c in enumerate(_calls) if c.startswith("escalate:"))
