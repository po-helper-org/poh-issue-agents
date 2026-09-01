"""Дефект 2: `_handle_comment_intent` звал не ту активность.

Четыре ветки в `_handle_comment_intent` («продолжаем», «потолок возвратов
исчерпан», «возврат этапа не поддерживается», «подтверждение принято») хотят
ОПУБЛИКОВАТЬ готовый текст в Issue. Вместо этого они звали `ack_comment_seen`
с ДВУМЯ позиционными аргументами (`issue`, текст) — активность, которая
принимает ОДИН датакласс `CommentAckInput` и лишь ставит реакцию `eyes`.
Неверная арность: каждый такой вызов падал `TypeError` в самой активности,
три попытки (RetryPolicy), и без перехвата исключения `ActivityError`
пробрасывался наружу — а он `FailureError`, поэтому ронял весь прогон
`IssueLifecycle` (статус становился FAILED), не давая ответить человеку.

Этот тест проверяет ровно ветку `intent="proceed"` ВНЕ фазы `classified`
(только там `_handle_comment_intent` доходит до вызова активности-ответа,
а не до смены фазы) — то есть боковую парковку (здесь: `duplicate`),
которую ведёт `_phase_park`. Без правки (замены на `post_followup_reply`
под `workflow.patched`) этот тест падает: прогон умирает с TypeError вместо
того, чтобы ответить человеку и остаться в работе.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.workflow_types import (
    ClassificationResult,
    CommentAckInput,
    CommentIntent,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle

_replies: list[tuple[str, int, str]] = []
_ack_calls: list[CommentAckInput] = []
_calls: list[str] = []


# --- заглушки: тот же путь до DUPLICATE, что и в test_duplicate_phase_transitions.py ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    pass


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


@activity.defn(name="duplicate_check")
async def duplicate_detected(issue: IssueInput) -> DuplicateResult:
    """Имитация дубликата — тот же приём, что заводит Issue в phase:duplicate."""
    return DuplicateResult(decision="duplicate", best_match_number=90,
                           probability=0.95, reason="такое же описание",
                           context_branch=None)


@activity.defn(name="post_comment")
async def post_comment_stub(repo: str, issue_number: int, body: str) -> None:
    pass


@activity.defn(name="add_label")
async def add_label_stub(repo: str, issue_number: int, label: str) -> None:
    pass


@activity.defn(name="classify_issue")
async def classify_stub(issue: IssueInput, bft_on_triage: bool = False):
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="score_priority")
async def score_priority_stub(issue: IssueInput, c, d):
    from shared.workflow_types import PriorityResult
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority_stub(issue: IssueInput, p, d):
    pass


# --- заглушки самого диалога ---

@activity.defn(name="interpret_user_comment")
async def interpret_as_proceed(issue: IssueInput, comment_text: str, current_phase: str,
                               classification_label, awaiting_reason,
                               recent_artifacts=None) -> CommentIntent:
    """Человек подтвердил продолжение — намерение `proceed`."""
    return CommentIntent(intent="proceed", reason="Окей, продолжаю в текущей фазе.")


@activity.defn(name="post_followup_reply")
async def post_followup_reply_stub(repo: str, issue_number: int, message: str) -> None:
    _replies.append((repo, issue_number, message))


@activity.defn(name="ack_comment_seen")
async def ack_comment_seen_stub(ack: CommentAckInput) -> None:
    """Зарегистрирована на случай, если код ошибочно пойдёт по старому пути —
    тест проверяет, что до неё дело в живом прогоне не доходит."""
    _ack_calls.append(ack)


ACTIVITIES = [awaiting_stub, prefilter_ok, protocol_default, deadlines_stub,
              set_phase_stub, gate_sufficient, duplicate_detected, post_comment_stub,
              add_label_stub, classify_stub, score_priority_stub, post_priority_stub,
              interpret_as_proceed, post_followup_reply_stub, ack_comment_seen_stub]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=166, title="Чек-аут демо",
                      body="описание", author_login="u", author_type="User",
                      interactive=True)


async def _await_phase(env, handle, expected: str, tries: int = 300) -> str:
    for _ in range(tries):
        if await handle.query(IssueLifecycle.phase) == expected:
            return expected
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


@pytest.mark.timeout(90)
async def test_proceed_reply_reaches_the_end_and_posts_the_message():
    """Отказ #166: подтверждение продолжения в боковой парковке обязано дойти
    до публикации ответа, а не уронить прогон `TypeError`-ом активности.

    Без правки (`ack_comment_seen` вместо `post_followup_reply`) этот тест
    падает: воркфлоу переходит в FAILED, `_replies` остаётся пустым.
    """
    _replies.clear()
    _ack_calls.clear()
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await _await_phase(env, handle, lifecycle.DUPLICATE)
            assert (await handle.describe()).status.name == "RUNNING"

            await handle.signal(IssueLifecycle.user_comment,
                                args=["Продолжай, пожалуйста", 42])

            for _ in range(60):
                if _replies:
                    break
                await env.sleep(1)

            assert _replies == [("o/r", 166, "Окей, продолжаю в текущей фазе.")], (
                "ответ на подтверждение продолжения обязан дойти до публикации"
            )
            assert _ack_calls == [], (
                "старая (неверная) активность не должна вызываться из живого пути"
            )
            # Прогон не уронило: фаза осталась той же боковой парковкой, а не
            # оборвалась исключением из недостроенного вызова активности.
            assert await handle.query(IssueLifecycle.phase) == lifecycle.DUPLICATE
            assert (await handle.describe()).status.name == "RUNNING", (
                "TypeError активности (неверная арность `ack_comment_seen`) "
                "не должен ронять весь цикл Issue"
            )
