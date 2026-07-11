"""
Webhook receiver: единственная точка входа для GitHub. Проверяет подпись,
транслирует событие в вызов Temporal:
- issues.opened            -> старт нового workflow (ID = repo-issue-N)
- issue_comment.created    -> сигнал уже идущему workflow (текст комментария —
                               используется циклом уточнений, если issue
                               в состоянии ожидания ответа)
- issues.labeled           -> сигнал, если лейбл — одна из точек решения
                               человека (research-me / bug-me / build-me)

Ничего из бизнес-логики здесь нет — это чистый транспортный слой.
"""

import hashlib
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client

app = FastAPI()

HUMAN_DECISION_LABELS = {"research-me", "bug-me", "build-me"}

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await Client.connect(os.environ["TEMPORAL_ADDRESS"])
    return _temporal_client


def verify_signature(body: bytes, signature_header: str | None) -> None:
    secret = os.environ["GITHUB_WEBHOOK_SECRET"].encode()
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


def workflow_id_for(repo_full_name: str, issue_number: int) -> str:
    return f"issue-{repo_full_name}-{issue_number}"


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = await request.json()

    client = await get_temporal_client()

    if x_github_event == "issues":
        action = payload["action"]
        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]
        wf_id = workflow_id_for(repo, issue_number)

        if action == "opened":
            from shared.workflow_types import IssueInput

            await client.start_workflow(
                "IssueLifecycle",  # имя workflow строкой — worker зарегистрирует класс под этим именем
                IssueInput(
                    repo=repo,
                    issue_number=issue_number,
                    title=payload["issue"]["title"],
                    body=payload["issue"].get("body") or "",
                    author_login=payload["issue"]["user"]["login"],
                    author_type=payload["issue"]["user"]["type"],
                ),
                id=wf_id,
                task_queue="issue-lifecycle",
            )

        elif action == "labeled":
            label = payload["label"]["name"]
            if label in HUMAN_DECISION_LABELS:
                handle = client.get_workflow_handle(wf_id)
                await handle.signal("human_decision", label)

    elif x_github_event == "issue_comment":
        if payload["action"] != "created":
            return {"ok": True}
        # Комментарии от самого сервиса не должны сигналить сами себя —
        # тот же принцип, что и guard `comment.user.type != 'Bot'` в старой
        # версии на Actions.
        if payload["comment"]["user"]["type"] == "Bot":
            return {"ok": True}

        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]
        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", payload["comment"]["body"])
        except Exception:
            # Workflow мог уже завершиться (issue закрыт) — комментарий
            # после этого просто не на что сигналить, это не ошибка.
            pass

    return {"ok": True}
