"""Подтверждение приёма комментария: реакция раньше любой работы.

Смысл проверок — в порядке и безусловности. Реакция ставится на любой
человеческий комментарий, а не только на команду, и до всего, что может
отказать: разбора команды, гейта прав, лимитов модели.
"""

import asyncio
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

import activities
from shared.workflow_ids import comment_ack_workflow_id
from shared.workflow_types import CommentAckInput
from workflows import CommentAck


def test_ack_comment_seen_reacts_with_eyes(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "add_reaction",
                        lambda repo, comment_id, content: calls.append(
                            (repo, comment_id, content)))

    asyncio.run(activities.ack_comment_seen(
        CommentAckInput(repo="o/r", issue_number=7, comment_id=555)))

    assert calls == [("o/r", 555, "eyes")]


def test_workflow_id_is_keyed_by_comment():
    assert comment_ack_workflow_id("o/r", 555) == "comment-ack-o/r-555"


@pytest.mark.timeout(120)
async def test_workflow_runs_the_reaction_activity():
    """Прогон целиком: воркфлоу существует, зарегистрирован и делает ровно один
    шаг. Без этого «реакция заказана» означало бы лишь запись в Temporal."""
    seen = []

    @activity.defn(name="ack_comment_seen")
    async def fake_ack(ack: CommentAckInput) -> None:
        seen.append(ack)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        client: Client = env.client
        async with Worker(client, task_queue="ack-test", workflows=[CommentAck],
                          activities=[fake_ack],
                          workflow_runner=UnsandboxedWorkflowRunner()):
            await client.execute_workflow(
                CommentAck.run,
                CommentAckInput(repo="o/r", issue_number=7, comment_id=555),
                id=comment_ack_workflow_id("o/r", 555),
                task_queue="ack-test",
                execution_timeout=timedelta(seconds=30),
            )

    assert [(a.repo, a.comment_id) for a in seen] == [("o/r", 555)]
