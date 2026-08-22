"""Круг правок как дочерний прогон.

Круг обладает всеми признаками дорогой стадии: поднимает тот же образ раннера
тем же `develop.runner_command`, идёт до 2700 с и недетерминирован. Оставить его
активностью значило бы сохранить ровно ту неоднородность, которая породила
исходную проблему.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_ids import pr_fix_workflow_id
from workflows import IssuePrFix

REPO = "o/r"
PR = 41

_rounds: list[int] = []


@activity.defn(name="run_pr_fix_round")
async def round_fixed(repo: str, pr_number: int, round_number: int):
    _rounds.append(round_number)
    return True


@activity.defn(name="run_pr_fix_round")
async def round_nothing_to_do(repo: str, pr_number: int, round_number: int):
    _rounds.append(round_number)
    return "замечаний, требующих правок в коде, нет"


async def _run(env, tq, act, round_number: int):
    async with Worker(env.client, task_queue=tq,
                      workflows=[IssuePrFix], activities=[act]):
        return await env.client.execute_workflow(
            IssuePrFix.run, args=[REPO, PR, round_number],
            id=pr_fix_workflow_id(REPO, PR, round_number), task_queue=tq)


@pytest.mark.timeout(60)
async def test_a_round_that_made_fixes_returns_true():
    """`True` — правки внесены и запрошена перепроверка."""
    _rounds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        assert await _run(env, f"tq-{uuid.uuid4()}", round_fixed, 1) is True
        assert _rounds == [1]


@pytest.mark.timeout(60)
async def test_a_round_with_nothing_to_fix_returns_its_verdict():
    """Строка — правок не потребовалось, и это её разбор. Законный исход, а не
    сбой: сводить его к булеву значению значило бы потерять объяснение."""
    _rounds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        out = await _run(env, f"tq-{uuid.uuid4()}", round_nothing_to_do, 1)

    assert isinstance(out, str) and "нет" in out


@pytest.mark.timeout(60)
async def test_each_round_gets_its_own_id():
    """Круги разделены ожиданием доклада ревью: без номера в ключе второй круг
    упирался бы в id первого, и доводка PR вставала бы после первого же круга."""
    _rounds.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        assert await _run(env, tq, round_fixed, 1) is True
        assert await _run(env, tq, round_fixed, 2) is True

    assert _rounds == [1, 2]
