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
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import workflows as workflows_module
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
# незарегистрированной активности либо на несовпадении сигнатуры (шестой
# параметр `recent_artifacts` — та же история, что чинит
# tests/test_activity_arg_types.py: воркфлоу обязан передавать его явно).
@activity.defn(name="interpret_user_comment")
async def interpret_ack(issue: IssueInput, comment_text: str, current_phase: str,
                        classification_label, awaiting_reason,
                        recent_artifacts=None) -> CommentIntent:
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


# Ревью, находка 1 (Important): устойчивый отказ GitHub (после исчерпания
# ретраев) не должен ронять весь IssueLifecycle. `non_retryable=True` —
# активность падает на первой же попытке, не выжидая всю ретрай-политику
# `read_acceptance_criterion` (3 попытки) виртуальным временем, — тот же
# приём, что уже есть в `tests/test_lifecycle_loop.py` для аналогичной цели.
@activity.defn(name="read_acceptance_criterion")
async def criterion_read_fails(issue: IssueInput) -> str:
    _calls.append("read-criterion")
    raise ApplicationError("GitHub 503: тело Issue не отдаётся", non_retryable=True)


# Ревью, находка (Important): отказ чтения критерия, ради которого воркфлоу
# держит гейт закрытым, до правки не был виден никому — только
# `workflow.logger.warning` (хлебная крошка Sentry, порог `event_level=ERROR`
# её не поднимает до события). Стаб под именем реальной активности —
# `report_criterion_gate_stall` (worker/activities.py) — так тест проверяет
# именно факт вызова воркфлоу этой активности, а не устройство Sentry/GitHub
# внутри неё.
@activity.defn(name="report_criterion_gate_stall")
async def stall_reported(issue: IssueInput, reason: str) -> None:
    _calls.append("stall-notice")


# Ревью, находка 1 (Important): уведомление об отказе гейта само не должно
# ронять цикл, который оно уведомляет. Воспроизводит РЕАЛЬНУЮ причину отказа
# из ревью — недоступность GitHub роняет и чтение критерия, и
# `github_client.post_comment` внутри `report_criterion_gate_stall` одним и
# тем же способом, `non_retryable=True` — по той же причине, что и у
# `criterion_read_fails`: падает на первой же попытке, не выжидая всю
# ретрай-политику (5 попыток) виртуальным временем.
@activity.defn(name="report_criterion_gate_stall")
async def stall_report_fails(issue: IssueInput, reason: str) -> None:
    _calls.append("stall-notice-failed")
    raise ApplicationError("GitHub 503: комментарий не отправился", non_retryable=True)


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


async def _await_quiescence(env, handle, tries: int = 50) -> None:
    """Ждёт, пока прогон полностью разберёт уже отправленные сигналы —
    признак наблюдаемый, но не деловой: длина истории (`history_length`)
    не растёт два опроса подряд.

    Ревью, находка 4 (Minor): у обычной реплики при открытом вопросе гейта
    нет НАБЛЮДАЕМОГО ДЕЛОВОГО следствия — `_answer_open_question` возвращает
    `None`, ветка гейта в `_phase_await_build` отвечает молчанием, ни одна
    активность не зовётся (см. докстрины обеих). Ждать появления записи в
    `_calls`, как остальные тесты этого файла (`_await_calls`), здесь
    буквально нечего — предиката, который стал бы истинным, не существует.

    Но «нечем доказать эффект» не значит «сгодится любой тайм-аут»: сон на
    фиксированное время доказывает только «эффекта не было за N секунд», а не
    «эффекта не будет» — гонка между отправкой сигнала и тем, успеет ли
    локальный воркер его разобрать до истечения тайм-аута, никуда не девается,
    просто становится маловероятной. Здесь используется другой наблюдаемый
    признак: `handle.describe().history_length` — сколько событий Event
    History прогона видно снаружи. Доставка сигнала ВСЕГДА добавляет запись
    (`WorkflowExecutionSignaled`), а её разбор воркером — минимум ещё три
    (`WorkflowTaskScheduled`/`Started`/`Completed`), вне зависимости от того,
    вызвала ли реплика хоть одну активность. Как только длина истории
    перестаёт расти между двумя опросами подряд, воркеру больше нечего
    обработать по этому сигналу прямо сейчас — то есть либо эффект уже
    случился (и виден в `_calls`), либо не случится вовсе. Это утверждение
    про КОНКРЕТНЫЙ момент, а не предположение о достаточности произвольного
    интервала.
    """
    prev = -1
    for _ in range(tries):
        cur = (await handle.describe()).history_length
        if cur == prev:
            return
        prev = cur
        await env.sleep(1)


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=163, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


_COMMON = [awaiting_stub, prefilter_ok, protocol_default, deadlines_stub,
           set_phase_stub, gate_ok, classify_bug, duplicate_none, score_p1,
           post_priority, escalate, trigger_build, dev_dispatch_stub,
           interpret_ack, ack_seen_stub, options_stub, ask_stub, answer_accepted,
           stall_reported]

# Тем же именем активности `report_criterion_gate_stall` в одном Worker'е
# нельзя зарегистрировать дважды — тестам про отказ УВЕДОМЛЕНИЯ (находка 1)
# нужен стенд без `stall_reported`, но с остальными заглушками `_COMMON`.
_COMMON_SANS_STALL_STUB = [a for a in _COMMON if a is not stall_reported]


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
async def test_criterion_read_failure_does_not_kill_the_lifecycle():
    """Ревью, находка 1 (Important): устойчивый отказ чтения критерия не
    должен ронять весь `IssueLifecycle` в `Failed`.

    До правки `read_acceptance_criterion` в `_start_development` ничем не
    защищён: ошибка активности после исчерпания попыток пролетает через
    `_start_development`, `_phase_await_build` и диспетчеризацию фаз в
    `_run_phase_loop` (там перехвата тоже нет) — и роняет весь прогон. Issue
    теряет владельца состояния целиком. Без правки `handle.result()` ниже
    бросает `WorkflowFailureError`, и тест падает уже на этой строке.

    Гейт при этом обязан держать закрыто: разработка не начинается — мы не
    знаем, есть критерий или нет, а пропустить задачу в разработку из-за
    сетевого сбоя хуже, чем не начать её вовремя (см. комментарий в самом
    `_start_development`, откуда взят и выбор — park, а не «нет критерия»).
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_read_fails, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "read-criterion" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()  # без правки — WorkflowFailureError здесь

    assert "ask" not in _calls, "сбой чтения не «критерий отсутствует» — вопрос не задаём"
    assert "development" not in _calls
    # Ревью (Important): отказ должен быть виден хотя бы одной аудитории —
    # здесь это Sentry-событие и комментарий человеку, оба за одним вызовом
    # `report_criterion_gate_stall` (см. её докстринг в worker/activities.py).
    # До правки этой активности не существовало вовсе — воркфлоу звал только
    # `workflow.logger.warning`, и эта строка падала бы на `assert "stall-notice"
    # in _calls`, потому что `_calls` о ней ничего не знает.
    assert "stall-notice" in _calls


@pytest.mark.asyncio
async def test_criterion_gate_stall_is_reported_once_per_series():
    """Отказ виден — но не на каждую попытку, а один раз на серию подряд
    идущих отказов.

    Без правки в `_start_development` нет вообще никакого наблюдаемого следа
    (см. `test_criterion_read_failure_does_not_kill_the_lifecycle` выше) — этот
    тест ловит СОСЕДНИЙ отказ: если правку сделать наивно (звать
    `report_criterion_gate_stall` без дедупликации, на каждый отказ), лента
    Issue получала бы копию одного и того же предупреждения на каждый повтор
    решения человека. Это ровно тот шум, которого требование явно просит
    избежать: "повторные отказы не засыпают ленту".

    Сценарий — человек дважды подряд нажимает «в разработку» (тот самый
    случай, ради которого видимость и нужна: первый клик не дал видимого
    эффекта, и человек нажимает снова). Обе попытки отказывают одинаково.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_read_fails, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: _calls.count("read-criterion") >= 1)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: _calls.count("read-criterion") >= 2)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("read-criterion") == 2, "гейт должен был отказать дважды подряд"
    assert _calls.count("stall-notice") == 1, (
        "сообщение — одно на серию отказов, а не на каждую попытку")


@pytest.mark.asyncio
async def test_notification_failure_does_not_kill_the_lifecycle():
    """Ревью, находка 1 (Important): уведомление об отказе гейта не должно
    само ронять цикл, который оно уведомляет.

    Причина отказа `read_acceptance_criterion` — обычно та же недоступность
    GitHub, а `report_criterion_gate_stall` (`worker/activities.py`) зовёт тот
    же `github_client.post_comment`, ничем не защищённый. Без перехвата в
    `_start_development` ретраи уведомления (5 попыток) тоже отказывают, и
    необработанная ошибка вылетает из `except`-блока наружу — правка,
    чинившая падение цикла на отказе чтения критерия, воспроизводит его же
    падение с другого захода.

    До правки `handle.result()` ниже бросает `WorkflowFailureError`, а
    заглушка уведомления в остальных тестах файла (`stall_reported`) никогда
    не бросает — поэтому ни один из них этот путь не ловит.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON_SANS_STALL_STUB, criterion_read_fails,
                                      stall_report_fails, dev_forbidden]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: "stall-notice-failed" in _calls)
            await handle.signal("issue_closed", "тест")
            await handle.result()  # без правки — WorkflowFailureError здесь

    assert "development" not in _calls, "разработка не должна была начаться"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_stall_notice_dedup_survives_continue_as_new(monkeypatch):
    """Ревью, находка 2 (Important): флаг «уже уведомили» обязан пережить
    continue-as-new, иначе дедупликация «одно сообщение на серию» ломается
    ровно там, ради чего писалась.

    Ревьюер разобрал механику: проверка порога истории в `_run_phase_loop`
    стоит ПОСЛЕ КАЖДОГО перехода фазы — включая холостой переход "остались на
    месте после отказа гейта", — а очередь сигналов сразу после разбора
    одного сигнала почти всегда пуста. Для задачи, уже прошедшей триаж и
    застрявшей на этом гейте (ровно целевой сценарий этой правки), порог
    набирается быстро. Порог опущен искусственно (`HISTORY_EVENT_THRESHOLD`),
    чтобы не растягивать тест на сотни реальных событий — сама механика
    сценария от боевого не отличается (см. `test_continue_as_new_truncates_
    history_without_losing_state` в tests/test_lifecycle_loop.py, тот же
    приём). `workflow_runner=UnsandboxedWorkflowRunner()` обязателен по той
    же причине, что и там: песочница импортирует свою копию модуля, и
    monkeypatch порога до воркфлоу не доехал бы.

    Сценарий: первый отказ гейта уведомляет и поднимает флаг, затем прогон
    обязан хотя бы раз перезапуститься (continue-as-new) ПОСЛЕ этого — важен
    именно порядок, — и только тогда приходит второй отказ той же серии. Без
    переноса флага в `LifecycleState.criterion_gate_notified` `__init__`
    после перезапуска снова ставит `False`, и второй отказ шлёт ВТОРОЕ
    сообщение о той же самой серии.
    """
    _calls.clear()
    monkeypatch.setattr(workflows_module, "HISTORY_EVENT_THRESHOLD", 15)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueDevelopment],
                          activities=[*_COMMON, criterion_read_fails, dev_forbidden],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: _calls.count("stall-notice") == 1)
            gen_at_notice = await handle.query(IssueLifecycle.generation)

            # Безобидный сигнал (любое решение, кроме "build-me", —
            # `_phase_await_build` возвращает "остались на месте" молча, см.
            # `if decision != "build-me"`) даёт ЕЩЁ ОДИН холостой переход
            # фазы ПОСЛЕ уведомления — ровно тот момент, когда в реальности
            # continue-as-new и получает свой шанс: очередь сигналов пуста
            # сразу после разбора, порог истории уже набран. Ждём именно
            # перезапуска, случившегося ПОСЛЕ уведомления, — важен порядок, а
            # не сам факт, что флаг когда-то был True.
            await handle.signal("human_decision", "no-build")
            await _await_quiescence(env, handle)
            assert await handle.query(IssueLifecycle.generation) > gen_at_notice, (
                "перезапуск после уведомления не случился — порог не сработал")

            await handle.signal("human_decision", "build-me")
            await _await_calls(env, lambda: _calls.count("read-criterion") >= 2)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert _calls.count("read-criterion") == 2, "гейт должен был отказать дважды подряд"
    assert _calls.count("stall-notice") == 1, (
        "флаг дедупликации не пережил continue-as-new — сообщение продублировалось")


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
            # Ревью, находка 4 (Minor): у обычной реплики нет наблюдаемого
            # ДЕЛОВОГО следствия (никакая активность не зовётся, см.
            # `_answer_open_question`) — ждать появления записи в `_calls`,
            # как в остальных тестах файла, здесь нечего. Вместо фиксированного
            # сна на «скорее всего достаточно» ждём наблюдаемый, но другой
            # признак — стабилизацию длины истории прогона (см. докстринг
            # `_await_quiescence`): она доказывает, что сигнал РАЗОБРАН, а не
            # что прошло сколько-то виртуального времени.
            await _await_quiescence(env, handle)
            await handle.signal("issue_closed", "тест")
            await handle.result()

    assert "answer" not in _calls
    assert "development" not in _calls
