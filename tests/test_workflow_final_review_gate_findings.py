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

from activities import ConflictingOpenQuestion
from shared import lifecycle
from shared.agent_events import STARTED, AgentEvent
from shared.workflow_types import (
    ClassificationResult,
    CommentIntent,
    Deadlines,
    DevelopPlan,
    DuplicateResult,
    GateResult,
    IssueInput,
    LifecycleState,
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
# G1 (Critical, третий круг финального ревью). РЕЦИДИВ C1 с другой стороны:
# правка C1 блокирует автостарт признаком «есть указатель на открытый
# вопрос» (`self._open_question` непуст). Но указатель — лишь ОДИН из исходов
# гейта. Устойчивый отказ ЧТЕНИЯ критерия или отказ ПОСТАНОВКИ вопроса
# оставляют указатель пустым точно так же, как если бы гейт не звался вовсе,
# — и автостарт видел «вопроса нет», снова и снова вызывая гейт заново без
# единого таймера, парковки или сигнала между оборотами. Тесты ниже
# воспроизводят оба исхода — гоняются с ВКЛЮЧЁННЫМ автостартом, иначе они
# ничем не отличались бы от уже существующих тестов гейта в
# tests/test_workflow_acceptance_gate.py, где автостарт выключен и находка не
# видна вовсе.
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def g1_criterion_read_fails(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    # non_retryable — тот же приём, что и `criterion_read_fails` в
    # tests/test_workflow_acceptance_gate.py: без него три попытки
    # `RetryPolicy(maximum_attempts=3)` размазали бы счётчик виртуальным
    # временем ретрая внутри ОДНОГО вызова гейта, а тест — про то, повторяется
    # ли САМ вызов гейта на каждом обороте, а не про арифметику ретраев.
    raise ApplicationError("GitHub 503: тело Issue не отдаётся", non_retryable=True)


@activity.defn(name="report_criterion_gate_stall")
async def g1_read_failure_notified(issue: IssueInput, reason: str) -> None:
    _calls.append("stall-notice")


@pytest.mark.asyncio
async def test_autostart_does_not_loop_on_persistent_criterion_read_failure():
    """G1 (Critical) — устойчивый отказ ЧТЕНИЯ критерия под автостартом.

    Без правки: `self._open_question` никогда не становится непустым (отказ
    происходит ДО постановки вопроса), автостарт не видит в этом препятствия
    и на следующем же обороте фазового цикла зовёт `_start_development`
    заново — `read_acceptance_criterion` на КАЖДОМ витке. После `_await_
    quiescence` счётчик уже заметно больше единицы (виток успевает
    повториться много раз за то время, что уходит на стабилизацию `history_
    length`), а получасовой досып ниже только увеличивает разрыв.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      g1_criterion_read_fails, options_stub, ask_stub,
                                      g1_read_failure_notified, dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await _await_calls(env, lambda: "read-criterion" in _calls)
            await _await_quiescence(env, handle)

            assert _calls.count("read-criterion") == 1, (
                "устойчивый отказ чтения критерия обязан парковать цикл, а "
                "не звать гейт заново на каждом витке")
            assert "propose" not in _calls, (
                "модель не должна звать вовсе — отказ ЧТЕНИЯ, до постановки "
                "вопроса дело не доходит")

            # `self._open_question` здесь пуст на всём протяжении (вопрос
            # никогда не задавался) — периодическая перепроверка критерия
            # (`issue-lifecycle-criterion-recheck-while-parked`) в этой ветке
            # не участвует вовсе, так что получасовой досып ничем не должен
            # быть особенным: без правки счётчик вырос бы и без него, с
            # правкой — не должен вырасти и с ним.
            await env.sleep(30 * 60)

            assert _calls.count("read-criterion") == 1, (
                "цикл обязан оставаться на парковке — ни таймер этой парковки "
                "(его тут и нет), ни сигнал не наступали")

            await handle.signal("issue_closed", "тест")
            await handle.result()


@activity.defn(name="read_acceptance_criterion")
async def g1_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="ask_question")
async def g1_ask_question_fails(issue: IssueInput, kind: str, text: str,
                                options: list[str]) -> str:
    _calls.append("ask")
    # non_retryable — по той же причине, что и у `g1_criterion_read_fails`
    # выше: без него `RetryPolicy(maximum_attempts=3)` у `ask_question`
    # размазала бы счётчик тремя попытками НА КАЖДЫЙ оборот витка.
    raise ApplicationError("GitHub 422: тело issue не обновилось", non_retryable=True)


@activity.defn(name="report_ask_question_gate_failure")
async def g1_ask_failure_notified(issue: IssueInput, reason: str) -> None:
    _calls.append("ask-stall-notice")


@pytest.mark.asyncio
async def test_autostart_does_not_loop_on_persistent_ask_question_failure():
    """G1 (Critical) — САМА находка третьего круга финального ревью.

    Устойчивый отказ ПОСТАНОВКИ вопроса (запись в GitHub — 403/422 на
    обновлении тела или публикации комментария) читается прекрасно и не
    пишется никогда: `read_acceptance_criterion` отрабатывает успешно
    (критерия нет), а падает именно `ask_question` — присваивание
    `self._open_question = ...` в `_start_development` не происходит,
    исключение брошено ДО него. `ConflictingOpenQuestion` для воспроизведения
    не нужен: она сегодня недостижима вовсе (см. докстринг у `_phase_await_
    build`) — подойдёт любой устойчивый отказ, переживший ретраи.

    Без правки: `self._open_question` остаётся пустым, автостарт видит
    «вопроса нет» и на каждом обороте зовёт гейт заново — чтение критерия,
    МОДЕЛЬ (`propose_acceptance_options`), снова отказ `ask_question`. Ни
    таймера, ни парковки, ни ожидания сигнала.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      g1_criterion_absent, options_stub,
                                      g1_ask_question_fails, g1_ask_failure_notified,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await _await_calls(env, lambda: "ask" in _calls)
            await _await_quiescence(env, handle)

            assert _calls.count("read-criterion") == 1, (
                "чтение критерия — один раз на заход в гейт, а не на каждый "
                "виток автостарта")
            assert _calls.count("propose") == 1, (
                "модель критерия приёмки должна звать один раз, а не на "
                "каждом витке цикла")
            assert _calls.count("ask") == 1, (
                "постановка вопроса — одна попытка на заход в гейт, а не "
                "оборот за оборотом")

            # Час виртуального времени без единого сигнала — `self._open_
            # question` пуст на всём протяжении (присваивание так и не
            # произошло), периодическая перепроверка критерия здесь тоже не
            # участвует. Без правки счётчики продолжали бы расти и на этом
            # интервале.
            await env.sleep(60 * 60)

            assert _calls.count("ask") == 1, (
                "устойчивый отказ постановки вопроса обязан парковать цикл — "
                "пустой self._open_question не должен пускать автостарт "
                "обратно в гейт")
            assert _calls.count("propose") == 1, (
                "модель не должна звать заново на каждом витке при "
                "устойчивом отказе постановки вопроса")

            await handle.signal("issue_closed", "тест")
            await handle.result()


# ---------------------------------------------------------------------------
# Находка при сквозной проверке всех выходов гейта (задание «проверь сам, нет
# ли ЕЩЁ путей выхода из гейта, ведущих обратно в автостарт без парковки»).
# `verdict == "accepted"` в `_answer_open_question` чистит `self._open_
# question`, но раньше не чистил `self._acceptance_gate_stalled` — а его
# поднимает та же успешная постановка вопроса, что и создала отвечаемый
# вопрос. `IN_DEVELOPMENT -> READY_FOR_DEV` («задача возвращена в очередь») —
# РЕАЛЬНЫЙ переход в таблице `shared/lifecycle.py`, доступный через
# `AgentEvent`, а не гипотетический: без сброса задача, вернувшаяся в очередь
# уже с записанным критерием, наткнулась бы на устаревший `True` в `_phase_
# await_build` и автостарт молча выключился бы для неё до конца жизни.
# ---------------------------------------------------------------------------

_returned_to_queue_criterion_calls = {"n": 0}


@activity.defn(name="read_acceptance_criterion")
async def returned_to_queue_criterion(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    _returned_to_queue_criterion_calls["n"] += 1
    if _returned_to_queue_criterion_calls["n"] == 1:
        return ""  # первый заход — критерия нет, вопрос будет задан
    # Ко второму заходу критерий уже записан — тем же ответом, что принял
    # вопрос гейта.
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="answer_question")
async def returned_to_queue_answer_accepted(
        issue: IssueInput, question_id: str, text: str, comment_id: int | None) -> str:
    _calls.append(f"answer:{question_id}")
    return "accepted"


@pytest.mark.asyncio
async def test_accepted_answer_does_not_leave_a_stale_gate_flag_after_returning_to_queue():
    """Без правки: после `verdict == "accepted"` флаг остаётся `True`.
    Задача уходит в разработку (`in-development`), внешний агент возвращает
    её в очередь — фаза снова `ready-for-dev`, но `_phase_await_build` видит
    устаревший `self._acceptance_gate_stalled == True` (от давно отвеченного
    и решённого вопроса) и НЕ пускает автостарт обратно в гейт — задача,
    которую DEVELOP_AUTOSTART обязан довести до разработки без единого
    касания человека, паркуется и ждёт сигнала, который по замыслу
    автостарта никогда не придёт.
    """
    _calls.clear()
    _returned_to_queue_criterion_calls["n"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      returned_to_queue_criterion, options_stub,
                                      ask_stub, returned_to_queue_answer_accepted,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Автостарт сам доходит до гейта и задаёт вопрос — без единого
            # сигнала.
            await _await_calls(env, lambda: "ask" in _calls)
            # Человек отвечает — гейт пройден, разработка стартует (dispatch:
            # фаза уходит в `in-development` и ждёт события агента).
            await handle.signal("user_comment", args=["/harness-answer 1", 101])
            await _await_calls(env, lambda: "development" in _calls)

            # Внешний агент возвращает задачу в очередь — переход РАЗРЕШЁН
            # таблицей переходов (`IN_DEVELOPMENT -> READY_FOR_DEV`, «задача
            # возвращена в очередь»). Критерий уже записан вторым заходом
            # заглушки — гейт обязан пропустить задачу молча, автостарту
            # спрашивать уже нечего.
            await handle.signal(IssueLifecycle.agent_event, AgentEvent(
                repo="o/r", agent="dev-agent", phase=lifecycle.READY_FOR_DEV,
                status=STARTED, ref="163"))

            await _await_calls(env, lambda: _calls.count("development") >= 2)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("development") == 2, (
        "автостарт обязан снова передать задачу в разработку без единого "
        "сигнала человека — устаревший флаг гейта не должен выключать "
        "автостарт для задачи, вернувшейся в очередь")
    assert _calls.count("ask") == 1, (
        "критерий уже записан ко второму заходу — гейт не должен спрашивать "
        "заново")


# ---------------------------------------------------------------------------
# F3 (Important, второй круг финального ревью): критерий, вписанный руками,
# обязан подхватываться под автостартом БЕЗ единого сигнала от человека.
# ---------------------------------------------------------------------------

_f3_criterion_calls = {"n": 0}


@activity.defn(name="read_acceptance_criterion")
async def f3_criterion_filled_after_a_while(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    _f3_criterion_calls["n"] += 1
    # Первые перепроверки — критерия ещё нет. Человек вписывает его в тело
    # руками ПОЗЖЕ, не отправляя контуру ни одного сигнала (правки тела
    # вебхук не доставляет вовсе).
    if _f3_criterion_calls["n"] < 3:
        return ""
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="close_answered_by_body_edit")
async def f3_close_answered(issue: IssueInput) -> None:
    _calls.append("close-answered")


@pytest.mark.asyncio
async def test_autostart_picks_up_a_hand_edited_criterion_without_any_signal():
    """Без правки: парковка гейта критерия ждёт ТОЛЬКО сигнала — команды,
    `build-me`, события агента. Правки тела Issue вебхук не доставляет
    сигналом вовсе, а под `DEVELOP_AUTOSTART` (чей смысл именно в
    отсутствии действия человека) задача с вписанным руками критерием
    просидела бы весь срок парковки МОЛЧА и закрылась — то самое действие
    человека (`/harness-answer` или повторный `build-me`), которого
    автостарт обязан избегать, стало бы единственной дверью (спека A23
    обещает обратное).

    Тест НИ РАЗУ не посылает `human_decision`/`user_comment` — только
    закрывает Issue в конце, когда разработка уже должна была начаться.
    Без правки `_await_calls(..., "development" in _calls)` не дожидается
    условия за отведённые попытки, и тест падает по таймауту этого цикла
    ожидания.
    """
    _calls.clear()
    _f3_criterion_calls["n"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      f3_criterion_filled_after_a_while,
                                      options_stub, ask_stub, f3_close_answered,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Автостарт сам доходит до гейта, задаёт вопрос и паркуется —
            # без единого сигнала.
            await _await_calls(env, lambda: "ask" in _calls)

            # Три интервала перепроверки (`CRITERION_RECHECK_INTERVAL` =
            # 30 минут) с запасом — ни одного сигнала за всё это время.
            await env.sleep(95 * 60)

            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("propose") == 1, (
        "модель зовётся один раз — на саму постановку вопроса, а не на "
        "каждую перепроверку критерия")
    assert _calls.count("ask") == 1
    assert "close-answered" in _calls, (
        "устаревший вопрос гейта обязан сняться тем же путём, что и при "
        "ответе командой (находка I4)")
    assert "development" in _calls, (
        "критерий, вписанный руками, обязан довести цикл до разработки "
        "БЕЗ единого сигнала от человека")


# ---------------------------------------------------------------------------
# G2 (Important, третий круг финального ревью): отказ ПЕРЕПРОВЕРКИ критерия
# (та же перепроверка, что и в тесте F3 выше, только читающая ничего) обязан
# стать видимым, а не молчать до истечения всего срока парковки. Прежний
# комментарий у этой ветки утверждал, что видимость обеспечит
# `_start_development` — но пока вопрос гейта открыт (а он открыт всё время
# перепроверки по определению — см. условие `issue-lifecycle-criterion-
# recheck-while-parked`), автостарт заблокирован (находка G1 выше) и человек
# не сигналит, значит `_start_development` в это время не позовётся вовсе.
# ---------------------------------------------------------------------------

_g2_criterion_calls = {"n": 0}


@activity.defn(name="read_acceptance_criterion")
async def g2_criterion_fails_after_the_question_is_asked(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    _g2_criterion_calls["n"] += 1
    if _g2_criterion_calls["n"] == 1:
        return ""  # первый заход гейта — критерия нет, вопрос будет задан
    # Все последующие чтения — уже перепроверка внутри парковки. Устойчивый
    # отказ: истёкший токен, отозванные права, переименованный репозиторий.
    raise ApplicationError("GitHub 401: токен отозван", non_retryable=True)


@activity.defn(name="report_criterion_gate_stall")
async def g2_stall_reported(issue: IssueInput, reason: str) -> None:
    _calls.append("stall-notice")


@pytest.mark.asyncio
async def test_recheck_failure_series_is_reported_once_while_parked():
    """G2 (Important). Без правки: `"stall-notice"` не появляется в `_calls`
    вовсе — исключение в перепроверке уходило только в `workflow.logger.
    warning` (хлебная крошка Sentry, порог `event_level=ERROR` её не
    поднимает до события). С наивной правкой (уведомление без дедупликации)
    тест поймал бы копию сообщения на КАЖДУЮ из нескольких перепроверок за
    95 минут — общий с гейтом флаг `self._criterion_gate_notified` держит
    ровно одно уведомление на серию.
    """
    _calls.clear()
    _g2_criterion_calls["n"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, c1_deadlines_autostart,
                                      g2_criterion_fails_after_the_question_is_asked,
                                      options_stub, ask_stub, g2_stall_reported,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Автостарт сам доходит до гейта и задаёт вопрос — без единого
            # сигнала.
            await _await_calls(env, lambda: "ask" in _calls)

            # Три интервала перепроверки (`CRITERION_RECHECK_INTERVAL` = 30
            # минут) с запасом — несколько подряд отказов одной серии.
            await env.sleep(95 * 60)

            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("ask") == 1, (
        "вопрос задаётся один раз на постановку, а не на каждую перепроверку")
    assert _calls.count("read-criterion") >= 4, (
        "перепроверка обязана была случиться несколько раз за 95 минут — "
        f"было {_calls.count('read-criterion')}")
    assert "stall-notice" in _calls, (
        "устойчивый отказ перепроверки обязан стать видимым — Sentry-событие "
        "и комментарий человеку, а не только warning в логе воркера")
    assert _calls.count("stall-notice") == 1, (
        "уведомление — одно на серию подряд идущих отказов, а не на каждую "
        "перепроверку")
    assert "development" not in _calls


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


# ---------------------------------------------------------------------------
# I2 (Important): срок ответа на вопрос — 72 часа, а не остаток парковки.
# ---------------------------------------------------------------------------

@activity.defn(name="read_acceptance_criterion")
async def i2_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@pytest.mark.asyncio
async def test_criterion_question_resets_the_park_deadline():
    """Без правки: вопрос гейта задаётся возвратом в ТУ ЖЕ фазу, а `_enter`
    при совпадении фазы не трогает `_phase_since` (срок парковки считается
    от него). Человек, нажавший «в разработку» под конец исходного
    72-часового окна `awaiting-build-decision`, получил бы на ОТВЕТ по
    вопросу только то, что осталось от СТАРОГО срока, — здесь это доводится
    до почти нуля: `build-me` отправлен, когда до истечения исходного окна
    осталось около часа.

    Без правки второй запрос `awaiting()` покажет `deadline_epoch`, почти
    совпадающий с ПЕРВЫМ (± пара секунд на обработку сигналов), — тест
    падает на `assert new_remaining > 24`, потому что за такой остаток не
    наберётся и часа.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i2_criterion_absent, options_stub, ask_stub,
                                      dev_forbidden],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Дожидаемся исходной парковки READY_FOR_DEV (build_decision_hours
            # = 72 по умолчанию) и почти исчерпываем её срок ПЕРЕД тем, как
            # человек нажмёт «в разработку».
            await _await_quiescence(env, handle)
            initial = await handle.query(IssueLifecycle.awaiting)
            assert initial is not None
            await env.sleep(71 * 3600)

            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)
            await _await_quiescence(env, handle)

            after_question = await handle.query(IssueLifecycle.awaiting)
            assert after_question is not None
            now_epoch = (await env.get_current_time()).timestamp()
            new_remaining_hours = (after_question.deadline_epoch - now_epoch) / 3600

            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert new_remaining_hours > 24, (
        "срок ответа на вопрос обязан отсчитываться заново (72 часа), "
        f"а не от остатка исходной парковки (осталось {new_remaining_hours:.1f} ч)")


# ---------------------------------------------------------------------------
# F2 (Important, второй круг финального ревью) — регресс правки I2 выше.
# Повторный вход в гейт ПРИ УЖЕ ОТКРЫТОМ вопросе не обязан продлевать срок.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reopening_the_gate_with_an_open_question_does_not_reset_the_deadline():
    """Без правки: `self._phase_since = workflow.now()` в ветке «вопрос
    гейта» (`_start_development`) стоит БЕЗУСЛОВНО, а не только при ПЕРВОЙ
    постановке. Повторный `build-me` при уже открытом вопросе (вебхук
    доставляет каждое событие ДВАЖДЫ — см. докстринг `_answer_open_
    question`; дежурный или человек вполне мог прислать решение снова, пока
    критерий не найден) заново заходит в `_start_development`, `ask_
    question` идемпотентно возвращает id ТОГО ЖЕ вопроса (не публикуя
    второй комментарий) — а срок парковки без правки отсчитывается заново
    НА КАЖДЫЙ такой заход. Дедлайн превращается в «N часов с последнего
    шороха» — ровно то, против чего в этом файле заведён абсолютный предел
    парковки (`_park_timeout`, правило R3).

    Без правки второй `awaiting()` покажет `deadline_epoch`, сдвинутый на
    интервал между двумя `build-me` (здесь — вперёд на два часа
    относительно первого), — тест падает на `assert second == first`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i2_criterion_absent, options_stub, ask_stub,
                                      dev_forbidden],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)
            await _await_quiescence(env, handle)
            first = await handle.query(IssueLifecycle.awaiting)
            assert first is not None

            # Пауза между двумя «в разработку» — достаточно большая, чтобы
            # регресс (сброс срока НА КАЖДЫЙ заход) был виден отчётливо, а
            # не потерялся в паре секунд обработки сигналов.
            await env.sleep(2 * 3600)

            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: _calls.count("ask") >= 2)
            await _await_quiescence(env, handle)
            second = await handle.query(IssueLifecycle.awaiting)
            assert second is not None

            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert second.deadline_epoch == first.deadline_epoch, (
        "повторный вход в гейт ПРИ УЖЕ ОТКРЫТОМ вопросе не должен продлевать "
        f"срок парковки (было {first.deadline_epoch}, стало {second.deadline_epoch})")
    assert "development" not in _calls


# ---------------------------------------------------------------------------
# F4 (Important, второй круг финального ревью): конфликт вопросов
# (`ConflictingOpenQuestion`, находка I5) не должен ронять весь цикл.
# ---------------------------------------------------------------------------

_f4_ask_calls = {"n": 0}


@activity.defn(name="read_acceptance_criterion")
async def f4_criterion_absent(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    return ""


@activity.defn(name="ask_question")
async def f4_ask_conflicts(issue: IssueInput, kind: str, text: str,
                           options: list[str]) -> str:
    # Детерминированный конфликт: в теле уже открыт вопрос ДРУГОГО вида
    # (находка I5) — повторный вызов с теми же аргументами получит ТОТ ЖЕ
    # отказ, ретрай его не лечит.
    _f4_ask_calls["n"] += 1
    _calls.append("ask")
    raise ConflictingOpenQuestion(
        f"вопрос вида 'mvp-bounds' (id='mvp-bounds-1') уже открыт — нельзя "
        f"задать поверх него вопрос вида {kind!r}")


@activity.defn(name="report_ask_question_gate_failure")
async def f4_notify(issue: IssueInput, reason: str) -> None:
    # Находка G2 (третий круг финального ревью): для СВЕЖЕГО прогона (без
    # предшествующей истории) `workflow.patched("issue-lifecycle-ask-
    # question-failure-message")` возвращает True, и уведомление об отказе
    # `ask_question` теперь уходит через ОТДЕЛЬНУЮ активность `report_ask_
    # question_gate_failure` — не через `report_criterion_gate_stall`,
    # которая лжёт про причину (см. её докстринг). Здесь всё ещё падает
    # `ask_question`, а не чтение критерия — имя заглушки просто следует за
    # правильной активностью.
    _calls.append("notified")


@pytest.mark.asyncio
async def test_ask_question_conflict_does_not_kill_the_lifecycle():
    """Без правки: вызов `ask_question` в `_start_development` не обёрнут ни
    в try/except, ни в список нерепетируемых типов исключений. Стандартная
    `RetryPolicy(maximum_attempts=3)` трижды дёргает заглушку тем же
    заведомо провальным запросом, а когда попытки исчерпаны — падение уходит
    наружу и роняет ВЕСЬ `IssueLifecycle` (тот же класс отказа, что чинит
    защита `answer_question`, находка I1, и `read_acceptance_criterion`).

    Без правки `handle.result()` ниже бросает `WorkflowFailureError`
    (сценарий даже не доходит до `issue_closed`), а `_f4_ask_calls["n"]`
    доходит до 3 — тест падает и на количестве попыток, и на самом отказе.
    """
    _calls.clear()
    _f4_ask_calls["n"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      f4_criterion_absent, options_stub,
                                      f4_ask_conflicts, f4_notify, dev_forbidden],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "notified" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()  # без правки — WorkflowFailureError здесь

    assert _f4_ask_calls["n"] == 1, (
        "детерминированный конфликт не должен повторяться ретраями — "
        f"заглушка вызвана {_f4_ask_calls['n']} раз(а)")
    assert "notified" in _calls, "отказ обязан стать заметным (Sentry/комментарий)"
    assert "development" not in _calls


# ---------------------------------------------------------------------------
# I4 (Important): критерий, вписанный в тело руками, обязан снять вопрос.
# ---------------------------------------------------------------------------

_i4_criterion_calls = {"n": 0}


@activity.defn(name="read_acceptance_criterion")
async def i4_criterion_then_filled_by_hand(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    _i4_criterion_calls["n"] += 1
    if _i4_criterion_calls["n"] == 1:
        return ""
    # Второй заход — человек вписал критерий в тело САМ, минуя
    # `/harness-answer` (спека A23).
    return "было 404; стало 405 с Allow: POST"


@activity.defn(name="close_answered_by_body_edit")
async def i4_close_answered(issue: IssueInput) -> None:
    _calls.append("close-answered")


@pytest.mark.asyncio
async def test_criterion_filled_by_hand_closes_the_stale_question():
    """Без правки: `_start_development` при непустом критерии сразу зовёт
    `_begin_development`, не трогая ни указатель, ни блок вопроса, ни метку
    ожидания. Вопрос, заданный гейтом РАНЬШЕ (когда критерия ещё не было),
    остаётся висеть на задаче, уже ушедшей в разработку.

    Без правки `"close-answered"` никогда не появляется в `_calls` — тест
    падает на первом же `assert`.
    """
    _i4_criterion_calls["n"] = 0
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i4_criterion_then_filled_by_hand,
                                      options_stub, ask_stub, i4_close_answered,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            # Первый заход: критерия нет, гейт задаёт вопрос.
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)

            # Человек не отвечает командой — вписывает критерий в тело сам и
            # снова нажимает «в разработку» (любой второй `build-me`
            # заново заводит `_start_development`, см. test_criterion_gate_
            # stall_is_reported_once_per_series в tests/test_workflow_
            # acceptance_gate.py — тот же приём).
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "close-answered" in _calls, (
        "критерий, вписанный руками, обязан снять устаревший вопрос гейта")
    assert "development" in _calls


# ---------------------------------------------------------------------------
# F6 (Important, второй круг финального ревью): отказ `close_answered_by_
# body_edit` обязан стать заметным, а не только строкой в логе.
# ---------------------------------------------------------------------------

@activity.defn(name="close_answered_by_body_edit")
async def f6_close_fails(issue: IssueInput) -> None:
    _calls.append("close-attempt")
    raise RuntimeError("GitHub 502: снятие метки не отправилось")


@activity.defn(name="report_question_close_failure")
async def f6_notify(issue: IssueInput, reason: str) -> None:
    _calls.append("close-notified")


@pytest.mark.asyncio
async def test_close_answered_by_body_edit_failure_is_reported_and_does_not_block_development():
    """Без правки: отказ `close_answered_by_body_edit` уходит только в
    `workflow.logger.warning` — событие Sentry не заводится, комментария
    человеку нет. Активности `report_question_close_failure` в этой ветке
    ДО правки не существует вовсе.

    Без правки `"close-notified"` никогда не появляется в `_calls` — тест
    падает на первом `assert`. Разработка при этом обязана начаться в любом
    случае (отказ снятия — уборка состояния, а не условие входа).
    """
    _i4_criterion_calls["n"] = 0
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      i4_criterion_then_filled_by_hand,
                                      options_stub, ask_stub, f6_close_fails,
                                      f6_notify, dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "ask" in _calls)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "development" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()  # отказ снятия не должен ронять цикл

    assert "close-attempt" in _calls
    assert "close-notified" in _calls, (
        "отказ снятия устаревшего вопроса гейта обязан стать заметным")
    assert "development" in _calls, (
        "отказ уборки состояния не должен блокировать передачу в разработку")


# ---------------------------------------------------------------------------
# F7 (Important, второй круг финального ревью): пустой указатель ЭТОГО
# прогона — не то же самое, что «вопроса нет в природе» (спека A24).
# ---------------------------------------------------------------------------

@activity.defn(name="read_open_question_id")
async def f7_read_open_question(issue: IssueInput) -> str:
    _calls.append("read-open-id")
    return "howtodemo-9"


@activity.defn(name="answer_question")
async def f7_answer_by_pointer(issue: IssueInput, question_id: str, text: str,
                               comment_id: int | None) -> str:
    # Реалистичное поведение настоящей активности (см. её докстринг, ветка
    # `question.id != question_id`): при РЕАЛЬНО открытом вопросе пустой
    # или неверный id получает «вопрос устарел», а не разбор ответа.
    _calls.append(f"answer:{question_id!r}")
    return "accepted" if question_id == "howtodemo-9" else "no-question"


@pytest.mark.asyncio
async def test_fresh_run_over_a_live_question_repoints_before_answering():
    """Без правки: пустой `self._open_question` в ветке `/harness-answer`
    без открытого вопроса (находка I3) трактуется как «вопроса нет вовсе».
    Но прогон, поднятый ЗАНОВО поверх ЖИВОЙ задачи (спека A24 — например,
    событие внешнего агента: `webhook/main.py:_lifecycle_args_for` несёт
    снимок с фазой, но БЕЗ указателя на вопрос гейта), стартует с пустым
    указателем, даже если в теле УЖЕ висит открытый вопрос из прошлого
    прогона.

    Без правки `_answer_open_question` зовёт `answer_question` сразу с
    `question_id=""`, минуя `read_open_question_id`, и заглушка (повторяющая
    реальное поведение активности) отвечает `"no-question"` на пустой id при
    РЕАЛЬНО открытом вопросе — человек, ответивший на актуальный вопрос,
    получил бы «этот вопрос уже устарел». Тест падает на
    `assert "read-open-id" in _calls` и на `"answer:'howtodemo-9'"`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_BASE, deadlines_no_autostart,
                                      f7_read_open_question, f7_answer_by_pointer,
                                      dev_started],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            # Снимок несёт фазу READY_FOR_DEV (как после события внешнего
            # агента — A24), но НЕ несёт указателя на открытый вопрос: он
            # заводится только внутри `_start_development` ЭТОГО прогона,
            # которого здесь никогда не было.
            carried = LifecycleState(phase=lifecycle.READY_FOR_DEV,
                                     stage="awaiting-build-decision")
            handle = await env.client.start_workflow(
                IssueLifecycle.run, args=[_issue(), carried],
                id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await handle.signal("user_comment", args=["/harness-answer текст ответа", 101])
            await _await_calls(env, lambda: any(c.startswith("answer:") for c in _calls))
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "read-open-id" in _calls, (
        "указатель обязан проверяться перед ответом, а не считаться пустым "
        "по умолчанию")
    assert "answer:'howtodemo-9'" in _calls, (
        "команда обязана уйти с АКТУАЛЬНЫМ id открытого вопроса, а не с "
        "пустым указателем свежего прогона")
    assert "answer:''" not in _calls
