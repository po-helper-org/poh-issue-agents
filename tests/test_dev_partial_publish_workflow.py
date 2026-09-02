"""Сорванный прогон разработки выкладывает то, что успел написать агент.

Отказ, ради которого написано: `poh-demo-checkout#166` — три красных теста из
семидесяти трёх, и тринадцать минут работы агента исчезли без следа. Ветки
нет, PR нет, диффа нет: `dev_publish` идёт ПОСЛЕ `dev_tests`, а `finally`
делает только запись эпизода.
"""

import inspect
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import DevelopPlan, IssueInput
from workflows import IssueDevelopment

REPO = "o/r"
ISSUE = 166

_calls: list[str] = []
_partial: list[tuple[str, str]] = []


# ────────── штатные шаги: доводят прогон до места, где он срывается ──────────


@activity.defn(name="dev_begin")
async def begin_local(issue: IssueInput) -> DevelopPlan:
    _calls.append("begin")
    return DevelopPlan(mode="local", branch="research/issue-166")


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


@activity.defn(name="dev_run_agent")
async def agent_ok(issue: IssueInput) -> None:
    _calls.append("agent")


@activity.defn(name="dev_followups")
async def followups_ok(issue: IssueInput) -> list[int]:
    _calls.append("followups")
    return []


@activity.defn(name="dev_tests")
async def checks_ok(issue: IssueInput) -> None:
    _calls.append("tests")


@activity.defn(name="dev_publish")
async def publish_ok(issue: IssueInput, branch: str) -> int | None:
    _calls.append("publish")
    return 101


@activity.defn(name="capture_episode")
async def episode_ok(issue: IssueInput, branch: str, pr_number: int | None) -> bool:
    _calls.append("capture_episode")
    return True


BASE = [begin_local, dispatch_stub, prepare_ok, announce_ok, plan_ok, agent_ok,
        followups_ok, checks_ok, publish_ok, episode_ok]


# ────────── срывы ──────────


@activity.defn(name="dev_tests")
async def checks_fail(issue: IssueInput) -> None:
    """Ровно случай #166: три красных теста из семидесяти трёх."""
    _calls.append("tests")
    raise RuntimeError("проверки не прошли (код 1):\n# fail 3")


@activity.defn(name="dev_followups")
async def followups_fail(issue: IssueInput) -> list[int]:
    _calls.append("followups")
    raise RuntimeError("сбор находок сорвался")


@activity.defn(name="dev_run_agent")
async def agent_fails(issue: IssueInput) -> None:
    _calls.append("agent")
    raise RuntimeError("прогон агента разработки завершился с кодом 137")


@activity.defn(name="dev_prepare")
async def prepare_fails(issue: IssueInput, branch: str) -> int:
    _calls.append("prepare")
    raise RuntimeError("клон не удался")


@activity.defn(name="dev_publish")
async def publish_fails(issue: IssueInput, branch: str) -> int | None:
    _calls.append("publish")
    raise RuntimeError("git push отказал")


@activity.defn(name="dev_publish_partial")
async def partial_stub(issue: IssueInput, branch: str, reason: str) -> int | None:
    _calls.append("partial")
    _partial.append((branch, reason))
    return 42


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=ISSUE, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _acts(*overrides):
    """Штатный набор, в котором подменены названные шаги.

    Подмена именно ЗАМЕНОЙ, а не добавлением: Temporal отвергает две
    активности с одним именем («More than one activity named ...»), и набор
    с дублем не доходит даже до прогона.
    """
    def _name(fn):
        return activity._Definition.must_from_callable(fn).name

    replaced = {_name(fn): fn for fn in overrides}
    base = [replaced.pop(_name(fn), fn) for fn in (*BASE, partial_stub)]
    return [*base, *replaced.values()]


def _reason(err: BaseException) -> str:
    """Текст всей цепочки причин.

    `str(WorkflowFailureError)` — это «Workflow execution failed» и ничего
    больше: настоящая причина лежит в `__cause__`, а проверяем мы именно её.
    """
    parts: list[str] = []
    cur: BaseException | None = err
    while cur is not None:
        parts.append(str(cur))
        cur = cur.__cause__
    return "\n".join(parts)


async def _run_expecting_failure(env, acts) -> Exception:
    tq = f"tq-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=tq, workflows=[IssueDevelopment],
                      activities=acts):
        with pytest.raises(Exception) as excinfo:
            await env.client.execute_workflow(
                IssueDevelopment.run, _issue(), id=f"wf-{uuid.uuid4()}",
                task_queue=tq)
    return excinfo.value


@pytest.mark.timeout(60)
async def test_red_tests_still_leave_the_work_behind():
    """Случай #166: тесты красные — ветка и черновик всё равно появляются."""
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run_expecting_failure(env, _acts(checks_fail))

    assert "partial" in _calls, "работа агента снова потеряна"
    assert "fail 3" in _partial[0][1], "причина обязана доехать до выкладки"


@pytest.mark.timeout(60)
async def test_a_failed_followups_step_saves_the_work_too():
    """Сбор находок сорвался — агент уже написал, спасать есть что."""
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run_expecting_failure(env, _acts(followups_fail))

    assert "partial" in _calls


@pytest.mark.timeout(60)
async def test_a_failed_agent_run_saves_what_it_managed_to_write():
    """Агент упал посреди правки — написанное всё равно материал для разбора."""
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run_expecting_failure(env, _acts(agent_fails))

    assert "partial" in _calls


@pytest.mark.timeout(60)
async def test_a_failure_before_the_agent_saves_nothing():
    """До агента изменений нет — публиковать нечего.

    Иначе контур открывал бы пустой черновик на каждый отказ подготовки.
    """
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run_expecting_failure(env, _acts(prepare_fails))

    assert "partial" not in _calls


@pytest.mark.timeout(60)
async def test_a_failed_publish_step_still_saves_the_work():
    """Сорвалась сама публикация — то, что написал агент, всё равно спасаем."""
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        await _run_expecting_failure(env, _acts(publish_fails))

    assert "partial" in _calls


@pytest.mark.timeout(60)
async def test_a_failed_rescue_does_not_replace_the_real_reason():
    """Отказ выкладки не подменяет исходную причину.

    Прогон обязан упасть с ТОЙ ЖЕ ошибкой, что случилась на самом деле, а не
    с ошибкой спасательного шага — иначе первопричина исчезает, а этот класс
    подмены в контуре уже случался.
    """
    _calls.clear()

    @activity.defn(name="dev_publish_partial")
    async def partial_fails(issue: IssueInput, branch: str,
                            reason: str) -> int | None:
        _calls.append("partial")
        raise RuntimeError("выкладка тоже отказала")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        err = await _run_expecting_failure(env, _acts(checks_fail, partial_fails))

    assert "partial" in _calls
    assert "fail 3" in _reason(err), \
        "наружу ушла ошибка спасательного шага вместо исходной причины"
    assert "выкладка тоже отказала" not in _reason(err), \
        "отказ спасательного шага подменил собой первопричину"


@pytest.mark.timeout(60)
async def test_a_draft_does_not_mean_the_task_moved_forward():
    """Черновик не двигает задачу вперёд: прогон падает, эпизод пишется.

    Иначе спасение работы превратилось бы в тихое «всё хорошо» — а именно
    этот класс подмены в контуре уже случался.
    """
    _calls.clear()
    _partial.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        err = await _run_expecting_failure(env, _acts(checks_fail))

    assert "fail 3" in _reason(err), "прогон обязан остаться отказом — фаза `failed`"
    assert _calls.count("capture_episode") == 1, \
        "запись эпизода делается ровно один раз, спасение её не дублирует"
    assert _calls.index("partial") < _calls.index("capture_episode"), \
        "выкладка идёт до записи эпизода: эпизод пишется в finally"


def test_partial_publish_patch_marker_is_frozen():
    """Идентификатор патча — часть истории уже идущих прогонов разработки.

    Переименование увело бы их на реплее в новую ветку, а прогон агента идёт
    до 45 минут: недетерминизм убил бы работу, которую этот же код спасает.
    """
    src = inspect.getsource(IssueDevelopment.run)
    assert 'workflow.patched("issue-development-partial-publish")' in src
