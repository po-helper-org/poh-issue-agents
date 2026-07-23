#!/usr/bin/env python3
"""End-to-end проверка централизованного Temporal: коннект, namespace и очередь.

Запускать С ХОСТА, где реально крутится worker (у него есть сетевой доступ к
кластеру). Не с локальной машины — публичный эндпоинт может быть за allowlist.

    set -a; . .env; set +a          # подхватить TEMPORAL_ADDRESS/NAMESPACE
    python scripts/smoke_temporal.py

Что делает:
  1) Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
  2) describe_namespace — namespace существует и REGISTERED
  3) поднимает временный worker на task-queue `poh-smoke-test`, запускает
     тривиальный workflow (activity возвращает pong) и ждёт результат —
     это доказывает, что очередь принимает задачи и worker их исполняет.

Ничего в целевом репозитории не трогает — отдельная task-queue и workflow.
"""
import asyncio
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio import activity, workflow
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from shared.temporal_client import connect_temporal

ADDR = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
NS = os.environ.get("TEMPORAL_NAMESPACE", "default")
TQ = "poh-smoke-test"


@activity.defn
async def echo(x: str) -> str:
    return f"pong:{x}"


@workflow.defn
class SmokeWorkflow:
    @workflow.run
    async def run(self, x: str) -> str:
        return await workflow.execute_activity(
            echo, x, start_to_close_timeout=timedelta(seconds=10)
        )


async def main() -> None:
    print(f"target: {ADDR}  namespace: {NS}")
    try:
        client = await connect_temporal()
    except Exception as e:  # noqa: BLE001 — диагностика, печатаем как есть
        print(f"CONNECT_FAIL: {type(e).__name__}: {e}")
        sys.exit(1)
    print("[1/3] CONNECT_OK")

    desc = await client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=NS)
    )
    print(f"[2/3] NAMESPACE_OK: name={desc.namespace_info.name!r} "
          f"state={desc.namespace_info.state}")

    wf_id = f"poh-smoke-{int(time.time())}"
    async with Worker(
        client,
        task_queue=TQ,
        workflows=[SmokeWorkflow],
        activities=[echo],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        result = await asyncio.wait_for(
            client.execute_workflow(
                SmokeWorkflow.run, "hello", id=wf_id, task_queue=TQ
            ),
            timeout=60,
        )
    ok = result == "pong:hello"
    print(f"[3/3] QUEUE_ROUNDTRIP {'OK' if ok else 'MISMATCH'}: "
          f"result={result!r} (id={wf_id} tq={TQ})")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    asyncio.run(main())
