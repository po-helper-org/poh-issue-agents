"""Финальное ревью всей ветки `spec/harness-answer-command`: находки,
видимые только на ЦЕЛОМ (гейт критерия приёмки + автостарт + `/harness-
answer` вместе), а не на отдельной задаче.

Заглушки цикла — тот же приём, что в `tests/test_workflow_acceptance_gate.py`
(см. её докстринг и комментарий у `_COMMON` там): свой набор здесь нужен,
потому что каждый тест этого файла заглушает `read_acceptance_criterion` и
`answer_question` (иногда — с внутренним состоянием между вызовами) по-своему,
и делить общий `_COMMON` с тем файлом означало бы либо тащить туда чужие
находки, либо развести на дублирующиеся модули с одинаковыми именами
активностей — Temporal Worker не разрешает регистрировать одно имя дважды.

Модель НИКОГДА не зовётся: все активности — заглушки без единого обращения к
`llm`.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from shared.workflow_types import (
    ClassificationResult,
    CommentIntent,
    Deadlines,
    DevelopPlan,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueDevelopment, IssueLifecycle

_calls: list[str] = []


# --- заглушки, общие для всех сценариев этого файла (по образцу _COMMON из
# tests/test_workflow_acceptance_gate.py) ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    pass


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


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
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="trigger_openhands_resolver")
async def trigger_build(issue: IssueInput, root_issue: int | None = None,
                        branch: str | None = None) -> None: ...


@activity.defn(name="dev_dispatch")
async def dev_dispatch_stub(issue: IssueInput, branch: str) -> None: ...


@activity.defn(name="interpret_user_comment")
async def interpret_ack(issue: IssueInput, comment_text: str, current_phase: str,
                        classification_label, awaiting_reason) -> CommentIntent:
    return CommentIntent(intent="ack", reason="")


@activity.defn(name="ack_comment_seen")
async def ack_seen_stub(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="propose_acceptance_options")
async def options_stub(issue: IssueInput) -> list[str]:
    _calls.append("propose")
    return ["было 404; стало 405"]


@activity.defn(name="ask_question")
async def ask_stub(issue: IssueInput, kind: str, text: str, options: list[str]) -> str:
    _calls.append("ask")
    return "howtodemo-1"


@activity.defn(name="answer_followup")
async def answer_followup_stub(issue: IssueInput, question: str) -> None:
    # Наблюдаемый маркер «команда упала в диалог уточнений» — находка I3
    # именно про то, что `/harness-answer` без открытого вопроса раньше
    # проваливался сюда вместо детерминированного ответа «вопросов нет».
    _calls.append(f"followup:{question}")


@activity.defn(name="dev_begin")
async def dev_forbidden(issue: IssueInput) -> DevelopPlan:
    _calls.append("development")
    raise AssertionError("разработка началась без критерия приёмки")


@activity.defn(name="dev_begin")
async def dev_started(issue: IssueInput) -> DevelopPlan:
    _calls.append("development")
    return DevelopPlan(mode="dispatch", branch="")


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=163, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


_BASE = [awaiting_stub, prefilter_ok, protocol_default, set_phase_stub, gate_ok,
         classify_bug, duplicate_none, score_p1, post_priority, escalate,
         trigger_build, dev_dispatch_stub, interpret_ack, ack_seen_stub,
         answer_followup_stub]


async def _await_calls(env, predicate, tries: int = 200) -> bool:
    """См. докстринг одноимённой функции в tests/test_workflow_acceptance_
    gate.py — тот же приём, тот же повод (гонка `issue_closed` с сигналами
    решения/ответа, читаемыми из общей очереди)."""
    for _ in range(tries):
        if predicate():
            return True
        await env.sleep(1)
    return predicate()


async def _await_quiescence(env, handle, tries: int = 50) -> None:
    """См. докстринг одноимённой функции в tests/test_workflow_acceptance_
    gate.py — стабилизация `history_length` как признак «сигнал разобран», а
    не сон на фиксированное время."""
    prev = -1
    for _ in range(tries):
        cur = (await handle.describe()).history_length
        if cur == prev:
            return
        prev = cur
        await env.sleep(1)


# ---------------------------------------------------------------------------
# C1 (Critical): автостарт и гейт спорят за одну точку входа.
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def c1_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="read_deadlines")
async def c1_deadlines_autostart() -> Deadlines:
    return Deadlines(pr_fix_enabled=False, research_autostart=True,
                     develop_autostart=True)


@activity.defn(name="answer_question")
async def c1_answer_accepted(issue: IssueInput, question_id: str, text: str,
                             comment_id: int | None) -> str:
    _calls.append(f"answer:{question_id}")
    return "accepted"


@pytest.mark.asyncio
async def test_autostart_waits_for_answer_instead_of_looping_forever():
    """Без правки: `_phase_await_build` при `DEVELOP_AUTOSTART` зовёт
    `_start_development` БЕЗУСЛОВНО. Гейт не находит критерия, зовёт модель
    (здесь — заглушку `propose`) и `ask_question`, задаёт вопрос и
    возвращается в ТУ ЖЕ фазу; `_enter` при совпадении фазы не паркует, цикл
    делает виток — и снова попадает в автостарт, снова в гейт: `propose`/
    `ask` звались бы на КАЖДОМ витке, `_wait_for_signal` в этой ветке не
    вызывался бы вовсе, а `/harness-answer` не читался бы из очереди сигналов
    никогда (ровно находка C1 из финального ревью).

    Без правки этот тест либо падает на `_calls.count("propose") == 1`
    (счётчик заведомо больше единицы — виток успевает повториться много раз
    за то время, что уходит на стабилизацию `history_length`), либо не
    доходит до принятия ответа вовсе.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      c1_criterion_absent, options_stub, ask_stub,
                                      c1_answer_accepted, dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Автостарт — без единого сигнала решения человека: задача сама
            # доходит до READY_FOR_DEV и сама зовёт `_start_development`.
            await _await_calls(env, lambda: "ask" in _calls)
            # Даём циклу время «покрутиться», если правки нет — без неё за
            # это время виток повторится многократно.
            await _await_quiescence(env, handle)

            assert _calls.count("propose") == 1, (
                "модель критерия приёмки должна звать один раз, а не на "
                "каждом витке цикла")
            assert _calls.count("ask") == 1, (
                "вопрос должен задаваться один раз, а не на каждом витке")

            # Прогон обязан ЖДАТЬ сигнала — а не крутиться. Ответ номером
            # варианта на открытый вопрос гейта.
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "development" in _calls, "ответ на вопрос обязан довести цикл до разработки"
