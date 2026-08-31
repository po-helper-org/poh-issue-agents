"""Гейт критерия приёмки: без критерия разработка не начинается.

Отказ, ради которого написано: poh-demo-checkout#163 прошёл разработку, PR и
мерж, а приёмка всё это время отвечала «проверять нечем».

Правка — в РЕШЕНИИ воркфлоу (`_start_development` в `worker/workflows.py`), не
в активности: новая ветка обязана стоять под `workflow.patched(
"issue-lifecycle-acceptance-gate")`, иначе прогоны, у которых решение «начать
разработку» уже лежит в истории на этом месте, падают на реплее
недетерминизмом (см. `tests/test_workflow_replay.py` — отдельный гвард именно
на этот класс отказа).
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

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

# --- заглушки цикла, скопированные вербатим из tests/test_agent_event_workflow.py ---
#
# ЕДИНСТВЕННОЕ отличие от оригинала — `deadlines_stub` ниже: там
# `Deadlines(pr_fix_enabled=False)`, здесь ещё и `research_autostart=True`.
# Без этого тумблера классификация «advisor:bug» паркуется в CLASSIFIED и ждёт
# метку `bug-me`, а не `build-me` — единственный сигнал решения, которым
# пользуются тесты этого файла (совпадение имени сигнала важно: `/harness-
# answer` в этих тестах должен быть ЕДИНСТВЕННЫМ дополнительным событием после
# `build-me`, иначе гейт нечем было бы проверить одним прогоном).

_calls: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    # `research_autostart=True` — единственное отличие от оригинала (см.
    # комментарий выше блока стабов): без него один `build-me` не доводит
    # прогон до READY_FOR_DEV.
    return Deadlines(pr_fix_enabled=False, research_autostart=True)


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
async def escalate(issue: IssueInput, reason: str = "") -> None:
    _calls.append(f"escalate:{reason}")


@activity.defn(name="trigger_openhands_resolver")
async def trigger_build(issue: IssueInput, root_issue: int | None = None,
                        branch: str | None = None) -> None: ...


@activity.defn(name="dev_dispatch")
async def dev_dispatch_stub(issue: IssueInput, branch: str) -> None: ...


# `interpret_user_comment`/`ack_comment_seen` — подстраховка на случай, если в
# конкретном прогоне тестовой среды сигнал `issue_closed` будет применён
# ПОЗЖЕ, чем прогон дойдёт до парковки `_phase_park` в `in-development` (после
# того как разработка стартовала): тогда следующий, уже отвеченный или лишний
# комментарий попадёт в общий путь `_phase_park`, а не в гейт (у гейта
# указатель `self._open_question` к этому моменту уже пуст). Оба пути этого
# файла не проверяют — активности здесь только не дают упасть на
# незарегистрированной активности.
@activity.defn(name="interpret_user_comment")
async def interpret_ack(issue: IssueInput, comment_text: str, current_phase: str,
                        classification_label, awaiting_reason) -> CommentIntent:
    return CommentIntent(intent="ack", reason="")


@activity.defn(name="ack_comment_seen")
async def ack_seen_stub(issue: IssueInput, reason: str = "") -> None: ...


# --- заглушки задачи 8 ---

@activity.defn(name="read_acceptance_criterion")
async def criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="read_acceptance_criterion")
async def criterion_present(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="propose_acceptance_options")
async def options_stub(issue: IssueInput) -> list[str]:
    _calls.append("propose")
    return ["было 404; стало 405"]


@activity.defn(name="ask_question")
async def ask_stub(issue: IssueInput, kind: str, text: str,
                   options: list[str]) -> str:
    _calls.append("ask")
    return "howtodemo-1"


@activity.defn(name="answer_question")
async def answer_accepted(issue: IssueInput, question_id: str, text: str,
                          comment_id: int | None) -> str:
    _calls.append("answer")
    return "accepted"


@activity.defn(name="dev_begin")
async def dev_forbidden(issue: IssueInput) -> DevelopPlan:
    _calls.append("development")
    raise AssertionError("разработка началась без критерия приёмки")


# Режим "dispatch" — тот же приём, что и `dev_begin_dispatch` в
# `tests/test_agent_event_workflow.py`: этот файл проверяет гейт, а не сам
# прогон разработки, и дочерний `IssueDevelopment` обязан завершиться, а не
# повиснуть на незарегистрированном шаге или упасть незарегистрированной
# активностью `post_error_label`.
@activity.defn(name="dev_begin")
async def dev_started(issue: IssueInput) -> DevelopPlan:
    _calls.append("development")
    return DevelopPlan(mode="dispatch", branch="")


async def _await_calls(env, predicate, tries: int = 200) -> bool:
    """Ждёт, пока `predicate()` над `_calls` не станет истинным.

    По образцу `_await_phase`/`_await_answers` из `tests/test_followup_dialog.py`.
    Нужен по причине, которую тот файл уже решал для реплик: `issue_closed`
    будит парковку по СОБСТВЕННОМУ признаку (`self._closed_by`), который
    прогон проверяет в НАЧАЛЕ каждого витка цикла фаз — независимо от того,
    успел ли он до этого разобрать более ранние, но ещё не прочитанные сигналы
    из очереди (`human_decision`, `user_comment`). Отправка `issue_closed`
    сразу вслед за остальными сигналами, без ожидания наблюдаемого следствия
    первых, гонится с их обработкой: цикл может закрыться раньше, чем дойдёт
    до `build-me` или до `/harness-answer`, — ровно то, что показал первый
    прогон этого файла (все пять тестов гейта падали с `_calls ==
    ['phase:cancelled']`, то есть с закрытием ДО триажа). Ждём здесь только
    `issue_closed` — сигналы решения и ответа отправляются вплотную друг за
    другом, как в брифе: они читаются из общей очереди в порядке отправки, и
    гонки с закрытием у них нет.
    """
    for _ in range(tries):
        if predicate():
            return True
        await env.sleep(1)
    return predicate()


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=163, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


_COMMON = [awaiting_stub, prefilter_ok, protocol_default, deadlines_stub,
           set_phase_stub, gate_ok, classify_bug, duplicate_none, score_p1,
           post_priority, escalate, trigger_build, dev_dispatch_stub,
           interpret_ack, ack_seen_stub, options_stub, ask_stub, answer_accepted]


@pytest.mark.asyncio
async def test_development_does_not_start_without_criterion():
    """Без критерия разработка не начинается, вопрос задан."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_absent, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "ask" in _calls
    assert "development" not in _calls


@pytest.mark.asyncio
async def test_development_starts_when_criterion_is_present():
    """Критерий есть — гейт пропускает молча, вопроса нет (A23)."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_present, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "development" in _calls
    assert "ask" not in _calls


@pytest.mark.asyncio
async def test_answer_unblocks_development():
    """Ответ принят — разработка начинается тем же прогоном."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_absent, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("ask") == 1
    assert "answer" in _calls
    assert "development" in _calls


@pytest.mark.asyncio
async def test_the_same_comment_delivered_twice_answers_once():
    """Вебхук доставляет каждое событие дважды (A6).

    Без защиты второй экземпляр приняли бы уже при закрытом вопросе — то есть
    ответили бы «вопросов нет» на собственный только что принятый ответ.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_absent, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("answer") == 1


@pytest.mark.asyncio
async def test_second_answer_from_another_person_finds_no_question():
    """Два ответа подряд: первый принят, второму отвечать не на что (A27).

    Порядок задаётся очередью сигналов прогона и детерминирован.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_absent, dev_started]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("user_comment", args=["/harness-answer 2", 202])
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    # Первый ответ снял указатель; второй в ветку ответа уже не попадает.
    assert _calls.count("answer") == 1


@pytest.mark.asyncio
async def test_comment_without_command_does_not_answer():
    """Разговор ответом не считается (A5)."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_absent, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            # Ждём открытого вопроса ПЕРЕД репликой: иначе реплика может
            # доехать раньше гейта (см. докстринг `_await_calls`) и обработаться
            # веткой `_answer_followup` вместо гейта, а тест — про сам гейт.
            await _await_calls(env, lambda: "ask" in _calls)
            await handle.signal("user_comment", args=["а нам это вообще надо?", 102])
            # У обычной реплики нет наблюдаемого следствия (никакая активность
            # не зовётся, см. `_answer_open_question`) — ждём фиксированный
            # запас виртуального времени, чтобы очередь сигналов гарантированно
            # опустела до отправки `issue_closed`.
            await env.sleep(5)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "answer" not in _calls
    assert "development" not in _calls
