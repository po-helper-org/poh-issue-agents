"""
Webhook receiver: единственная точка входа для GitHub. Проверяет подпись,
транслирует событие в вызов Temporal:
- issues.opened            -> старт нового workflow (ID = repo-issue-N)
- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis,
                               `/estimate` — IssueEstimation; любой другой
                               комментарий — сигнал уже идущему workflow
                               (используется циклом уточнений)
- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и
                               команда в комментарии (run:analyze ->
                               IssueAnalysis, run:estimate -> IssueEstimation);
                               точки решения человека (research-me / bug-me /
                               build-me) идут через signal-with-start: воркфлоу
                               триажа может не существовать, тогда он
                               поднимается тем же вызовом

Ничего из бизнес-логики здесь нет — это чистый транспортный слой.
"""

import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared import sentry_setup
from shared.commands import (
    ANALYZE,
    ESTIMATE,
    build_analyze_input,
    parse_command,
    parse_label_command,
)
from shared.authz import may_trigger, trigger_allowlist
from shared.repos import allowed_specs, is_allowed
from shared.temporal_client import connect_temporal
from shared.workflow_ids import (
    analysis_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
)

_log = logging.getLogger("webhook")

sentry_setup.configure("webhook")  # no-op без SENTRY_DSN; FastAPI инструментируется автоматически

_log = logging.getLogger("webhook")

app = FastAPI()

HUMAN_DECISION_LABELS = {"research-me", "bug-me", "build-me"}


def _log_effective_config() -> None:
    """Один раз на старте — какой конфиг реально действует.

    Секреты не логируются: только режим авторизации. Полная картина —
    `scripts/diag.py` внутри контейнера; эта строка нужна, чтобы после
    передеплоя не гадать, подхватились ли переменные.
    """
    specs = [s for s in allowed_specs() if s.strip()]
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        auth = "PAT (перебивает GitHub App)" if os.environ.get("GITHUB_APP_ID") else "PAT"
    elif os.environ.get("GITHUB_APP_ID"):
        auth = "GitHub App"
    else:
        auth = "НЕ НАСТРОЕНА"
    _log.info(
        "effective config: ISSUE_AGENT_REPOS=%s auth=%s temporal=%s/%s",
        specs or ["(пусто — любой репозиторий)"], auth,
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        os.environ.get("TEMPORAL_NAMESPACE", "default"),
    )


_log_effective_config()

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await connect_temporal()
    return _temporal_client


def verify_signature(body: bytes, signature_header: str | None) -> None:
    secret = os.environ["GITHUB_WEBHOOK_SECRET"].encode()
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


# Формат ID живёт в shared/workflow_ids.py: его же собирают скрипты прямого
# запуска, и разъехавшись, они потеряли бы идемпотентность.
workflow_id_for = issue_workflow_id
estimate_workflow_id_for = estimate_workflow_id


def _may_start_expensive(payload: dict, what: str, repo: str, issue_number: int) -> bool:
    """Гейт на запуск дорогой стадии + аудит того, кто её запустил.

    Проверяем автора события, а не факт наличия метки: метку может поставить
    любой с правами на репозиторий, и это самый дешёвый способ потратить чужие
    токены. Дешёвые пути (issues.opened, обычные комментарии) сюда не приходят —
    триаж обязан работать для всех.

    Отказ только логируем: вебхук — чистый транспорт, GitHub-клиента у него нет,
    и заводить его ради комментария «недостаточно прав» значит дать наружу
    процессу право писать в Issue.
    """
    login = (payload.get("sender") or {}).get("login")
    allowlist = trigger_allowlist()
    if may_trigger(login, allowlist):
        # Аудит: кто и когда запустил дорогую стадию (время ставит логгер).
        _log.info("expensive trigger %s by %s on %s#%s", what, login, repo, issue_number)
        return True
    _log.warning(
        "отклонён запуск %s: %s не входит в AGENT_TRIGGER_ALLOWLIST %s (%s#%s)",
        what, login, allowlist, repo, issue_number,
    )
    return False


async def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None,
                                  repo: str, specs: list[str]) -> None:
    """След в Temporal UI для события, отброшенного по allowlist.

    Единственный молчаливый отказ, о котором иначе неоткуда узнать: workflow не
    создаётся, GitHub получает 200. Аудит-воркфлоу не исполняет ни одной
    activity — его ценность в том, что вход виден там же, где смотрят всё
    остальное: пришло, отклонено, вот причина и вот действовавший allowlist.

    Без заголовка X-GitHub-Delivery (ручной curl, тест) аудит пропускаем: без
    уникального id ретраи GitHub плодили бы дубли. Сбой самого аудита тоже не
    должен ронять обработку — это диагностика, а не путь события.
    """
    if not delivery_id:
        return
    from shared.workflow_types import WebhookAuditInput

    try:
        client = await get_temporal_client()
        await client.start_workflow(
            "WebhookAudit",
            WebhookAuditInput(
                delivery_id=delivery_id,
                event=event,
                action=str(payload.get("action") or ""),
                repo=repo,
                reason="repo_not_allowed",
                allowlist=specs,
            ),
            id=f"webhook-drop-{delivery_id}",
            task_queue="issue-lifecycle",
        )
    except WorkflowAlreadyStartedError:
        pass  # ретрай той же доставки — запись уже есть
    except Exception as exc:
        _log.warning("не удалось записать аудит отброшенной доставки: %s", exc)


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
):
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = await request.json()

    # Allowlist: действуем только на репозитории из ISSUE_AGENT_REPOS (пусто/* —
    # любой установленный). Чужой репозиторий игнорируем до старта workflow.
    repo_full = (payload.get("repository") or {}).get("full_name")
    if repo_full and not is_allowed(repo_full, allowed_specs()):
        specs = [s for s in allowed_specs() if s.strip()]
        # warning, а не info, и вместе с действующим allowlist: строка лога
        # обязана сама говорить, что чинить. Раньше отказ был неотличим от
        # тишины — GitHub видел 200, в Temporal не появлялось ничего.
        _log.warning(
            "ignored repo %s — not in ISSUE_AGENT_REPOS %s; событие отброшено до Temporal",
            repo_full, specs or ["(пусто)"],
        )
        await _audit_dropped_delivery(payload, x_github_event, x_github_delivery,
                                      repo_full, specs)
        return {"ok": True}

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

            # Метка — второй триггер команды, равноправный с комментарием: два
            # тапа в мобильном GitHub вместо набора текста в треде. Ведёт в тот
            # же воркфлоу, что и `/analyze` — таблица соответствия одна
            # (shared/commands.py), поэтому разъехаться им негде.
            command = parse_label_command(label)

            if command == ANALYZE:
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                try:
                    await client.start_workflow(
                        "IssueAnalysis",
                        build_analyze_input(payload),  # без comment_id: триггер — метка
                        id=analysis_workflow_id(repo, issue_number),
                        task_queue="issue-lifecycle",
                    )
                except WorkflowAlreadyStartedError:
                    # Метку сняли и поставили заново, пока прогон идёт: второй
                    # дорогой прогон не нужен, а первый уже подтверждён ack'ом.
                    _log.info("analysis already running for %s#%s", repo, issue_number)
                return {"ok": True}

            if command == ESTIMATE:
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                from shared.workflow_types import EstimateRequest

                try:
                    await client.start_workflow(
                        "IssueEstimation",
                        EstimateRequest(repo=repo, issue_number=issue_number),
                        id=estimate_workflow_id_for(repo, issue_number),
                        task_queue="issue-lifecycle",
                    )
                except WorkflowAlreadyStartedError:
                    _log.info("estimate already running for %s#%s", repo, issue_number)
                return {"ok": True}

            if label in HUMAN_DECISION_LABELS:
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                from shared.workflow_types import IssueInput

                # signal-with-start, а не голый signal: лейбл прилетает и по
                # issue, у которого воркфлоу триажа не существует (issue завели
                # до установки App — `issues.opened` никто не доставил; либо
                # триаж прогнали в обход Temporal). signal() в несуществующий
                # workflow бросает исключение, вебхук отвечает 500, GitHub
                # ретраит и бросает доставку — лейбл остаётся мёртвым молча.
                await client.start_workflow(
                    "IssueLifecycle",
                    IssueInput(
                        repo=repo,
                        issue_number=issue_number,
                        title=payload["issue"]["title"],
                        body=payload["issue"].get("body") or "",
                        author_login=payload["issue"]["user"]["login"],
                        author_type=payload["issue"]["user"]["type"],
                        # Отвечать на уточняющий вопрос тут некому: триггер —
                        # лейбл, а не диалог. VAGUE обязан эскалировать, иначе
                        # цикл уточнений съест только что доставленный сигнал.
                        interactive=False,
                    ),
                    id=wf_id,
                    task_queue="issue-lifecycle",
                    start_signal="human_decision",
                    start_signal_args=[label],
                )

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

        # Единственная точка ветвления «команда против обычного комментария»:
        # команда НЕ уходит в user_comment, иначе её съел бы цикл уточнений
        # intake gate как ответ на уточняющий вопрос.
        command = parse_command(payload["comment"].get("body") or "")

        if command == ESTIMATE:
            if not _may_start_expensive(payload, "/estimate", repo, issue_number):
                return {"ok": True}
            from shared.workflow_types import EstimateRequest

            comment_id = payload["comment"]["id"]
            try:
                await client.start_workflow(
                    "IssueEstimation",
                    EstimateRequest(
                        repo=repo, issue_number=issue_number, comment_id=comment_id
                    ),
                    id=estimate_workflow_id_for(repo, issue_number, comment_id),
                    task_queue="issue-lifecycle",
                )
            except WorkflowAlreadyStartedError:
                # Тот же вебхук доставлен повторно — оценка уже идёт.
                pass
            return {"ok": True}

        if command == ANALYZE:
            if not _may_start_expensive(payload, "/analyze", repo, issue_number):
                return {"ok": True}
            analyze = build_analyze_input(payload)

            # Живому воркфлоу триажа шлём только уведомление — оно повесит метку
            # `analyzing`; исполнителем всегда остаётся выделенный IssueAnalysis.
            lifecycle = client.get_workflow_handle(workflow_id_for(repo, issue_number))
            try:
                await lifecycle.signal("analyze_requested", analyze.comment_id)
            except Exception:
                pass  # триаж уже завершён — уведомлять некого, это не ошибка

            try:
                await client.start_workflow(
                    "IssueAnalysis",
                    analyze,
                    id=analysis_workflow_id(repo, issue_number),
                    task_queue="issue-lifecycle",
                )
            except WorkflowAlreadyStartedError:
                # Прогон по этому Issue уже идёт: пользователь видел ack первого
                # запуска, второй ack был бы шумом. Webhook — чистый транспорт.
                _log.info("analysis already running for %s#%s", repo, issue_number)
            return {"ok": True}

        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", payload["comment"]["body"])
        except Exception:
            # Workflow мог уже завершиться (issue закрыт) — комментарий
            # после этого просто не на что сигналить, это не ошибка.
            pass

    return {"ok": True}
