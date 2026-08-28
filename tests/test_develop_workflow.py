"""IssueDevelopment: порядок шагов и раздельные ретраи.

Стадия разрезана на активности ради двух вещей сразу — видимости в Temporal и
осмысленных ретраев. Здесь проверяется вторая: срыв публикации повторяет
публикацию, а не двадцатиминутный прогон агента.
"""

import inspect
import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import DevelopPlan, IssueInput
from workflows import IssueDevelopment

REPO = "o/r"
ISSUE = 39

_calls: list[str] = []
_fail_publish_times = 0


@activity.defn(name="dev_begin")
async def begin_local(issue: IssueInput) -> DevelopPlan:
    _calls.append("begin")
    return DevelopPlan(mode="local", branch="research/issue-39")


@activity.defn(name="dev_dispatch")
async def dispatch_stub(issue: IssueInput, branch: str) -> None:
    _calls.append("dispatch")


@activity.defn(name="dev_prepare")
async def prepare_ok(issue: IssueInput, branch: str) -> int:
    _calls.append("prepare")
    return 1780


@activity.defn(name="dev_announce")
async def announce_ok(issue: IssueInput, branch: str) -> None:
    _calls.append("announce")


@activity.defn(name="build_mvp_plan")
async def plan_ok(issue: IssueInput, branch: str) -> bool:
    _calls.append("plan")
    return True


@activity.defn(name="build_mvp_plan")
async def plan_fails(issue: IssueInput, branch: str) -> bool:
    """`claude -p` для /plan-mvp упал (лимит частоты, как уже бывало у FNR) —
    построение плана обязано быть прозрачным для остального прогона."""
    _calls.append("plan")
    raise RuntimeError("claude -p exit 1: rate limited")


@activity.defn(name="dev_run_agent")
async def agent_ok(issue: IssueInput) -> None:
    _calls.append("agent")


@activity.defn(name="dev_run_agent")
async def agent_fails_once(issue: IssueInput) -> None:
    """Всегда падает — дефект #39 в чистом виде, если у этого шага когда-нибудь
    заведутся ретраи по ошибке (`cheap` вместо `once`)."""
    _calls.append("agent")
    raise RuntimeError("прогон агента разработки завершился с кодом 137")


@activity.defn(name="dev_followups")
async def followups_ok(issue: IssueInput) -> list[int]:
    _calls.append("followups")
    return []


@activity.defn(name="dev_tests")
async def checks_ok(issue: IssueInput) -> None:
    # Не `tests_ok`: имя, начинающееся на "test", pytest подбирает как тестовую
    # функцию (по умолчанию `python_functions` матчит любой префикс "test") и
    # роняет сбор с "fixture 'issue' not found" — это активность, а не тест.
    _calls.append("tests")


@activity.defn(name="dev_tests")
async def checks_fail_once(issue: IssueInput) -> None:
    _calls.append("tests")
    raise RuntimeError("проверки не прошли (код 1): red")


@activity.defn(name="dev_publish")
async def publish_ok(issue: IssueInput, branch: str) -> int | None:
    _calls.append("publish")
    return 101


@activity.defn(name="dev_publish")
async def publish_flaky(issue: IssueInput, branch: str) -> int | None:
    """Публикация срывается дважды и удаётся с третьей — случай прогона #39."""
    global _fail_publish_times
    _calls.append("publish")
    _fail_publish_times += 1
    if _fail_publish_times < 3:
        raise RuntimeError("git push → код 1: protected branch")
    return 101


@activity.defn(name="dev_publish")
async def publish_empty(issue: IssueInput, branch: str) -> int | None:
    _calls.append("publish")
    return None


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=ISSUE, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


async def _run(env, tq, acts) -> int | None:
    async with Worker(env.client, task_queue=tq,
                      workflows=[IssueDevelopment], activities=acts):
        return await env.client.execute_workflow(
            IssueDevelopment.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)


@pytest.mark.timeout(60)
async def test_steps_run_in_the_order_that_protects_the_pr():
    """Находки собираются ПОСЛЕ агента и ДО тестов и публикации: файл находок
    обязан исчезнуть из рабочего дерева раньше коммита, иначе уедет в PR."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        number = await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                      announce_ok, agent_ok, followups_ok,
                                      checks_ok, publish_ok])

    assert number == 101
    assert _calls == ["begin", "prepare", "announce", "agent",
                      "followups", "tests", "publish"]


@pytest.mark.timeout(60)
async def test_plan_is_built_after_prepare_and_before_the_agent_runs():
    """Task 10: план — вход агента, не отчёт по его работе.

    Не раньше подготовки: `.harness/`, который читает и куда пишет
    `/plan-mvp`, наполняет только `dev_prepare` — до него каталога не
    существует (K2, ревью Task 9, revert 80b3291: холодный старт, стадия
    планирования падала в каталоге, которого никто ещё не создал).

    Не позже старта агента: план — вход, который агент читает, а не отчёт по
    итогам его работы.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        number = await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                      announce_ok, plan_ok, agent_ok, followups_ok,
                                      checks_ok, publish_ok])

    assert number == 101
    assert _calls.index("prepare") < _calls.index("plan") < _calls.index("agent"), (
        f"план обязан строиться после подготовки и до агента: {_calls}")


@pytest.mark.timeout(60)
async def test_a_failed_plan_build_does_not_stop_the_agent():
    """Отказ построения плана — не отказ разработки: план необязателен, агент
    штатно работает без него уже сегодня. Топить дорогой прогон разработки
    из-за необязательного шага значило бы разменивать штатный путь на
    необязательное ускорение."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        number = await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                      announce_ok, plan_fails, agent_ok, followups_ok,
                                      checks_ok, publish_ok])

    assert number == 101
    assert _calls == ["begin", "prepare", "announce", "plan", "agent",
                      "followups", "tests", "publish"], (
        "агент не запустился после отказа построения плана")


def test_plan_stage_patch_marker_is_frozen():
    """Идентификатор патча — часть истории уже идущих прогонов разработки:
    переименование увело бы их на реплее в новую ветку (недетерминизм, самый
    дорогой класс отказов в Temporal). Строка меняется только вместе с
    осознанным `workflow.deprecate_patch`."""
    src = inspect.getsource(IssueDevelopment.run)
    assert 'workflow.patched("issue-lifecycle-develop-plan-stage")' in src


@pytest.mark.timeout(60)
async def test_a_failed_push_retries_only_the_push():
    """Прогон #39: пуш падал на последнем шаге, а повторялась вся стадия вместе
    с агентом, и контур трижды объявил о передаче задачи."""
    global _fail_publish_times
    _calls.clear()
    _fail_publish_times = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        number = await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                      announce_ok, agent_ok, followups_ok,
                                      checks_ok, publish_flaky])

    assert number == 101
    assert _calls.count("publish") == 3, "публикация не повторилась"
    assert _calls.count("agent") == 1, "агент прогнан заново — ровно дефект #39"
    assert _calls.count("announce") == 1, "контур объявил о передаче дважды"


@pytest.mark.timeout(60)
async def test_a_failed_agent_run_is_not_retried():
    """Находка 4: `test_a_failed_push_retries_only_the_push` доказывает, что
    публикация повторяется, но стаб агента там ни разу не падает — замена
    `once` на `cheap` у `dev_run_agent` вернула бы дефект #39 (двадцать минут
    прогона трижды подряд) и осталась бы незамеченной этим набором.

    Здесь падает сам агент: он обязан быть вызван РОВНО один раз, а не три —
    ретрай такого шага инициирует человек, а не политика ретраев.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        with pytest.raises(WorkflowFailureError) as exc_info:
            await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                 announce_ok, agent_fails_once, followups_ok,
                                 checks_ok, publish_ok])

    assert _calls.count("agent") == 1, "прогон агента повторился — вернулся дефект #39"
    # Два уровня обёртки: WorkflowFailureError.cause — ActivityError
    # («Activity task failed», без текста причины), причина — уровнем глубже,
    # в его собственном .cause (ApplicationError от RuntimeError активности).
    assert "137" in str(exc_info.value.cause.cause)
    assert "publish" not in _calls, "до публикации после срыва агента доходить не должны"


@pytest.mark.timeout(60)
async def test_a_failed_test_run_is_not_retried():
    """Того же заслуживает шаг тестов (находка 4): он тоже недетерминирован и
    стоит времени, а ретраить красный прогон — значит просто ждать того же
    результата ещё раз."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        with pytest.raises(WorkflowFailureError):
            await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                 announce_ok, agent_ok, followups_ok,
                                 checks_fail_once, publish_ok])

    assert _calls.count("tests") == 1, "прогон тестов повторился"
    assert _calls.count("agent") == 1, "агент перезапущен из-за срыва тестов"
    assert "publish" not in _calls, "до публикации после красных тестов доходить не должны"


@pytest.mark.timeout(60)
async def test_an_empty_run_is_a_loud_failure():
    """Прогон без единой правки — не успех: открывать нечего, и человек должен
    об этом узнать. Молчание здесь неотличимо от исправной работы.

    Temporal оборачивает исключение воркфлоу в `WorkflowFailureError` — его
    `str()` это просто "Workflow execution failed", без текста первопричины.
    Причина лежит в `.cause` (Python-цепочка `__cause__`, которую сам класс
    выставляет в `__init__`, см. `temporalio.client.WorkflowFailureError`).
    Здесь исключение рождается прямо в коде воркфлоу (`raise ApplicationError`
    после `dev_publish`), а не внутри активности, поэтому `.cause` — сразу
    искомый `ApplicationError`, без промежуточного `ActivityError`.
    """
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        with pytest.raises(WorkflowFailureError) as exc_info:
            await _run(env, tq, [begin_local, dispatch_stub, prepare_ok,
                                 announce_ok, agent_ok, followups_ok,
                                 checks_ok, publish_empty])

    assert "ни одного файла" in str(exc_info.value.cause)


@pytest.mark.timeout(60)
async def test_dispatch_mode_skips_the_local_steps():
    """Режим `dispatch`: работа идёт на чужой стороне, шагов здесь нет.
    `None` — не сбой, а «жди события pr-open»."""
    _calls.clear()

    @activity.defn(name="dev_begin")
    async def begin_dispatch(issue: IssueInput) -> DevelopPlan:
        _calls.append("begin")
        return DevelopPlan(mode="dispatch", branch="research/issue-39")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        number = await _run(env, tq, [begin_dispatch, dispatch_stub, prepare_ok,
                                      announce_ok, agent_ok, followups_ok,
                                      checks_ok, publish_ok])

    assert number is None
    assert _calls == ["begin", "dispatch"]
