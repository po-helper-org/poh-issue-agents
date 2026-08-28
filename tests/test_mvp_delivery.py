"""MvpDelivery: шаги плана, под-задачи на время шага.

Проверяется ПОРЯДОК внешних действий, а не арифметика: релиз и доставка
ошибаются в последовательности. Тот же приём, что у тестов Delivery-Agent.

Активности подставляются подделками, зарегистрированными под ИМЕНЕМ реальной
активности (`@activity.defn(name=...)`), а не именем python-функции — тот же
приём, что в `tests/test_agents_as_children.py`. Без `result_type=` на
вызове конвертер Temporal отдал бы голый словарь вместо dataclass; здесь это
не проверяется напрямую (все активности отдают `int`/`list`, не dataclass),
но воркфлоу всё равно задаёт `result_type=` на каждом вызове — той же
дисциплины ради.
"""

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import mvp_delivery
from shared.workflow_types import IssueInput


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                      author_login="u", author_type="User")


@pytest.mark.timeout(60)
async def test_plan_without_dependencies_runs_once_without_subissues():
    """Граф без рёбер — под-задач ноль, один прогон разработки."""
    calls = []

    @activity.defn(name="mvp_read_plan")
    async def fake_read_plan(issue):
        return [{"title": "Одна правка", "depends_on": [], "depends_reason": {}}]

    @activity.defn(name="mvp_open_substep")
    async def fake_open(issue, index, title):
        calls.append(("open", index))
        return 0

    @activity.defn(name="mvp_develop_step")
    async def fake_develop(issue, step_index):
        calls.append(("develop", step_index))
        return 101

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[mvp_delivery.MvpDelivery],
                          activities=[fake_read_plan, fake_open, fake_develop]):
            pr = await env.client.execute_workflow(
                mvp_delivery.MvpDelivery.run, _issue(),
                id="mvp-1", task_queue="tq")

    assert pr == 101
    assert ("open", 0) not in calls, "под-задача заведена там, где делить нечего"
    assert calls.count(("develop", 0)) == 1


@pytest.mark.timeout(60)
async def test_plan_with_dependency_opens_and_closes_subissue_per_step():
    """Граф с ребром — под-задача на время каждого шага, в порядке шагов."""
    calls = []

    @activity.defn(name="mvp_read_plan")
    async def fake_read_plan(issue):
        return [
            {"title": "Первый", "depends_on": [], "depends_reason": {}},
            {"title": "Второй", "depends_on": [0], "depends_reason": {"0": "берёт parse()"}},
        ]

    @activity.defn(name="mvp_open_substep")
    async def fake_open(issue, index, title):
        calls.append(("open", index))
        return 200 + index

    @activity.defn(name="mvp_develop_step")
    async def fake_develop(issue, step_index):
        calls.append(("develop", step_index))
        return 300 + step_index

    @activity.defn(name="mvp_close_substep")
    async def fake_close(issue, number, index):
        calls.append(("close", number))

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[mvp_delivery.MvpDelivery],
                          activities=[fake_read_plan, fake_open, fake_develop, fake_close]):
            pr = await env.client.execute_workflow(
                mvp_delivery.MvpDelivery.run, _issue(),
                id="mvp-2", task_queue="tq")

    assert calls == [("open", 0), ("develop", 0), ("close", 200),
                     ("open", 1), ("develop", 1), ("close", 201)]
    assert pr == 301, "результат — PR последнего шага"


@pytest.mark.timeout(60)
async def test_empty_plan_returns_none_without_touching_github():
    """Пустой план (`plan_parse.parse` не нашёл ни одной задачи) — не отказ:
    воркфлоу отдаёт `None`, ничего не заводя и не разрабатывая."""
    calls = []

    @activity.defn(name="mvp_read_plan")
    async def fake_read_plan(issue):
        return []

    @activity.defn(name="mvp_open_substep")
    async def fake_open(issue, index, title):
        calls.append(("open", index))
        return 0

    @activity.defn(name="mvp_develop_step")
    async def fake_develop(issue, step_index):
        calls.append(("develop", step_index))
        return 101

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[mvp_delivery.MvpDelivery],
                          activities=[fake_read_plan, fake_open, fake_develop]):
            pr = await env.client.execute_workflow(
                mvp_delivery.MvpDelivery.run, _issue(),
                id="mvp-3", task_queue="tq")

    assert pr is None
    assert calls == []
