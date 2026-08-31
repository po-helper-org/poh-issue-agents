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
from temporalio.exceptions import ApplicationError
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


# ---------------------------------------------------------------------------
# Общая заглушка срока для сценариев без автостарта (C2, I1, I3, I4).
# ---------------------------------------------------------------------------

@activity.defn(name="read_deadlines")
async def deadlines_no_autostart() -> Deadlines:
    return Deadlines(pr_fix_enabled=False, research_autostart=True)


# ---------------------------------------------------------------------------
# C2 (Critical): возрождение вопроса не переставляет указатель.
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def c2_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="answer_question")
async def c2_answer_reasked_then_gate_by_pointer(
        issue: IssueInput, question_id: str, text: str, comment_id: int | None) -> str:
    """Симулирует РЕАЛЬНОЕ поведение активности: вопрос "howtodemo-1" отвечен
    первым ответом, но пропал из тела (человек стёр раздел руками) — вопрос
    возрождается под НОВЫМ id "howtodemo-2" (A22). Второй ответ засчитывается
    "accepted", ТОЛЬКО если он пришёл с АКТУАЛЬНЫМ id "howtodemo-2" — то есть
    только если воркфлоу успел переставить свой указатель. Со СТАРЫМ id
    "howtodemo-1" второй (и любой следующий) вызов застрял бы на "reasked"
    же — ровно тот дефект C2 описывает: «по кругу до истечения срока».
    """
    _calls.append(f"answer:{question_id}")
    if question_id == "howtodemo-1":
        return "reasked"
    if question_id == "howtodemo-2":
        return "accepted"
    return "no-question"


@activity.defn(name="read_open_question_id")
async def c2_read_open_question_id(issue: IssueInput) -> str:
    _calls.append("read-open-id")
    return "howtodemo-2"


@pytest.mark.asyncio
async def test_reasked_question_repoints_the_workflow_pointer():
    """Без правки: контракт `answer_question` — голая строка-вердикт, и
    воркфлоу очищает `self._open_question` только на `accepted`. После
    `reasked` указатель остаётся на СТАРОМ, уже недействительном id — а
    активность (см. заглушку выше) реалистично засчитывает только ответ с
    АКТУАЛЬНЫМ id. Без правки второй ответ human'а уйдёт со СТАРЫМ id,
    получит СНОВА "reasked", и `"development"` в `_calls` не появится
    никогда — тест падает на ожидании `"development" in _calls`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      c2_criterion_absent, options_stub, ask_stub,
                                      c2_answer_reasked_then_gate_by_pointer,
                                      c2_read_open_question_id, dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)

            # Первый ответ — на исходный вопрос "howtodemo-1". Активность
            # (заглушка) отвечает "reasked": вопрос «пропал и возродился».
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "answer:howtodemo-1" in _calls)

            # Второй ответ человека — на ЛЮБОЙ (уже неважно какой) текст.
            # Указатель воркфлоу решает, с каким id уйдёт вызов активности.
            await handle.signal("user_comment", args=["/harness-answer 1", 102])
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "answer:howtodemo-2" in _calls, (
        "второй вызов активности обязан уйти с АКТУАЛЬНЫМ id вопроса, "
        "а не с указателем, оставшимся от возрождённого")
    assert "development" in _calls


# ---------------------------------------------------------------------------
# I3 (Important): `/harness-answer` без открытого вопроса не должен тонуть в
# диалоге уточнений — спека A18 требует явного «вопросов нет».
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def i3_criterion_present(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="answer_question")
async def i3_answer_no_question(issue: IssueInput, question_id: str, text: str,
                                comment_id: int | None) -> str:
    _calls.append(f"answer:{question_id!r}")
    assert question_id == "", "указатель обязан быть пустым — вопроса не было"
    return "no-question"


@pytest.mark.asyncio
async def test_harness_answer_without_open_question_gets_explicit_reply():
    """Без правки: ветка разбора ответа в `_phase_await_build` заходит
    ТОЛЬКО при непустом `self._open_question`. Команда `/harness-answer`,
    когда указателя нет (гейт даже не спрашивал — критерий уже есть),
    проваливается в `_answer_followup` — диалог уточнений, а не
    детерминированный ответ «вопросов нет» (спека A18: молчание
    недопустимо).

    Без правки `_calls` содержит `"followup:/harness-answer 1"` вместо
    `"answer:''"`, и тест падает на `assert "followup" not in ...`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i3_criterion_present, i3_answer_no_question,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # Критерий уже есть — гейт молчит, вопроса не было и не будет
            # (см. test_development_starts_when_criterion_is_present в
            # tests/test_workflow_acceptance_gate.py). Команда `/harness-
            # answer` отправлена ПЕРЕД решением `build-me` — оба сигнала
            # читаются из общей очереди в порядке отправки (FIFO), поэтому
            # команда обязана дойти до `_phase_await_build` РАНЬШЕ, чем
            # решение сдвинет фазу.
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "answer:''" in _calls
                               or any(c.startswith("followup:") for c in _calls))
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert not any(c.startswith("followup:") for c in _calls), (
        "команда без вопроса не должна попадать в диалог уточнений")
    assert "answer:''" in _calls, (
        "команда без вопроса обязана дойти до answer_question с пустым "
        "указателем и получить детерминированный ответ «вопросов нет»")


# ---------------------------------------------------------------------------
# I1 (Important): сбой `answer_question` не должен убивать весь цикл.
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def i1_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="answer_question")
async def i1_answer_fails(issue: IssueInput, question_id: str, text: str,
                          comment_id: int | None) -> str:
    _calls.append("answer-attempt")
    # non_retryable — падает на первой же попытке, не выжидая всю
    # retry-политику виртуальным временем (тот же приём, что в
    # tests/test_workflow_acceptance_gate.py::criterion_read_fails).
    raise ApplicationError("GitHub 502: комментарий не отправился", non_retryable=True)


@activity.defn(name="report_answer_question_failure")
async def i1_notify(issue: IssueInput, reason: str) -> None:
    _calls.append("notified")


@pytest.mark.asyncio
async def test_answer_question_failure_does_not_kill_the_lifecycle():
    """Без правки: `worker/workflows.py` зовёт `answer_question` с
    `maximum_attempts=1` и без перехвата. Единственный сбой активности
    (здесь — устойчивый `ApplicationError`) улетает наружу и роняет ВЕСЬ
    `IssueLifecycle` в Failed — Issue теряет владельца состояния целиком.

    Без правки `handle.result()` ниже бросает `WorkflowFailureError`, и тест
    падает на этой строке. Человек, ответивший на вопрос, ничего не узнаёт о
    том, что ответ не принят, — находка I1 требует и перехвата, и заметного
    сообщения (здесь — вызов `report_answer_question_failure`).
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i1_criterion_absent, options_stub, ask_stub,
                                      i1_answer_fails, i1_notify, dev_forbidden],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "notified" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()  # без правки — WorkflowFailureError здесь

    assert "notified" in _calls, "человек обязан получить заметное сообщение об отказе"
    assert "development" not in _calls

