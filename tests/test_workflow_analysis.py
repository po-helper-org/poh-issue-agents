import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared.workflow_types import AnalyzeInput, ProtocolState
from workflows import IssueAnalysis


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=1)


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    """Рубильник `agents:off` снят — обычный прогон."""
    return ProtocolState()


def _finish_stub(calls):
    """Обратный ход меток: `run:analyze` снимается, вешается исход прогона."""

    @activity.defn(name="finish_command_labels")
    async def finish(repo: str, issue_number: int, command: str, ok: bool) -> None:
        calls.append(f"finish:{command}:{'ok' if ok else 'failed'}")

    return finish


@pytest.mark.asyncio
async def test_orchestrates_all_stages_in_order():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "research/issue-5"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error,
                                      _finish_stub(calls), protocol_default]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert calls == ["ack", "prepare", "stage:task", "stage:concept", "stage:debate",
                     "stage:sysreq", "stage:validate", "publish", "finish:analyze:ok",
                     "cleanup"]


@pytest.mark.asyncio
async def test_stage_failure_publishes_error_and_cleans_up():
    calls = []
    reported = {}

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        if stage_name == "sysreq":
            raise RuntimeError("boom-sysreq")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "b"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        reported["reason"] = reason
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error,
                                      _finish_stub(calls), protocol_default]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert calls[:6] == ["ack", "prepare", "stage:task", "stage:concept", "stage:debate", "stage:sysreq"]
    assert "stage:validate" not in calls          # остановились на sysreq
    assert "publish" not in calls
    assert "error" in calls and "boom-sysreq" in reported["reason"]
    # Сорвавшийся прогон помечается своей меткой: молча снятый run:* неотличим
    # от «никто не запускал».
    assert "finish:analyze:failed" in calls
    assert "finish:analyze:ok" not in calls
    assert calls[-1] == "cleanup"                  # cleanup всегда последним


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_success():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "research/issue-5"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")
        raise RuntimeError("cleanup-boom")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error,
                                      _finish_stub(calls), protocol_default]):
            # завершается без ошибки, несмотря на падение cleanup
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert "publish" in calls       # реальный результат состоялся
    assert "cleanup" in calls       # cleanup вызывался
    assert "error" not in calls     # успех НЕ превратился в ошибку
    assert "finish:analyze:ok" in calls


@pytest.mark.asyncio
async def test_stage_retries_infrastructure_failure_but_not_its_own():
    """Смерть воркера и сбой стадии — разные вещи, и политика ретраев обязана их
    различать.

    Стадия `claude -p` не повторяется намеренно: она недетерминирована, мутирует
    файлы и стоит денег. Но heartbeat timeout — не её сбой: воркер перезапустили
    (например, выкладкой), активность оборвалась, и ничего произведено не было.
    Без второй попытки любая выкладка посреди прогона убивала анализ целиком —
    так и случилось на стенде с Issue #11: контейнер воркера пересобран в
    04:44:31, «activity Heartbeat timeout» пришёл в 04:49:39, ровно через
    heartbeat_timeout.

    Инфраструктурный сбой изображается `ConnectionError`: как и таймаут, он не
    RuntimeError, то есть попадает в ту же (повторяемую) половину политики.
    """
    attempts: list[str] = []
    calls: list[str] = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None: ...

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None: ...

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        attempts.append(stage_name)
        if stage_name == "concept" and attempts.count("concept") == 1:
            raise ConnectionError("воркер перезапущен")
        if stage_name == "debate":
            raise RuntimeError("claude -p exit 1")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        return "b"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None: ...

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error,
                                      _finish_stub(calls), protocol_default]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert attempts.count("concept") == 2, "инфраструктурный сбой не переспросили"
    assert attempts.count("debate") == 1, "сбой самой стадии не должен повторяться"
    assert "error" in calls
