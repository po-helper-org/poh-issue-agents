"""
Webhook receiver: единственная точка входа для GitHub. Проверяет подпись,
транслирует событие в вызов Temporal:
- issues.opened            -> старт нового workflow (ID = repo-issue-N)
- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и
                               через signal-with-start поднимает цикл-владелец
                               состояния, `/estimate` — IssueEstimation,
                               `/bft` и `/bft-deep` — IssueBft (хвост команды
                               уезжает в прогон как замечания/уточнения); любой
                               другой комментарий — сигнал уже идущему workflow
                               (используется циклом уточнений)
- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и
                               команда в комментарии (run:analyze ->
                               IssueAnalysis, run:estimate -> IssueEstimation,
                               run:bft / run:bft-deep -> IssueBft);
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

from fastapi import FastAPI, Header, HTTPException, Request, Response
from starlette.requests import ClientDisconnect
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared import sentry_setup
from shared.commands import (
    ANALYZE,
    BFT,
    BFT_DEEP,
    ESTIMATE,
    bft_mode,
    build_analyze_input,
    build_bft_request,
    parse_command,
    parse_label_command,
)
from shared.agent_comment import is_agent_comment
from shared.agent_launcher import request_analysis, request_bft, request_estimate
from shared.authz import may_trigger, trigger_allowlist
from shared.labels import HUMAN_DECISION_LABELS, parse_root_issue
from shared.repos import allowed_specs, is_allowed
from shared.temporal_client import connect_temporal
from shared.workflow_ids import (
    comment_ack_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
)

_log = logging.getLogger("webhook")

sentry_setup.configure("webhook")  # no-op без SENTRY_DSN; FastAPI инструментируется автоматически

_log = logging.getLogger("webhook")

app = FastAPI()


@app.exception_handler(ClientDisconnect)
async def _client_disconnect(request: Request, exc: ClientDisconnect):
    """Отправитель ушёл, не дослав тело.

    Отвечать 500 некому: соединения уже нет, а событие уезжает в Sentry как
    сбой вебхука (ISSUE-AGENT-8, пять штук за один разрыв связи с прокси).
    Доставка не потеряна: GitHub повторит её сам. У GitLab ретраев нет — там
    оборванная доставка теряется, поэтому обработчик ниже принимает всё, что
    прошло подпись, и разбирается внутри. 204 закрывает запрос тихо и
    оставляет след в логе.
    """
    _log.info("отправитель разорвал соединение до конца тела (%s) — доставка будет повторена",
              request.headers.get("x-github-delivery", "без id"))
    return Response(status_code=204)


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


def _search_attributes(repo: str, payload: dict, issue_number: int) -> dict | None:
    """Сквозной ключ цепочки в Temporal: `RootIssue` и `Repo`.

    Они дают одну ленту на всю цепочку от триажа Issue до стоп-слова на PR —
    ради этого протокол и предпочитает централизованный кластер трём
    изолированным.

    За флагом TEMPORAL_SEARCH_ATTRIBUTES, потому что атрибут, не
    зарегистрированный на кластере, роняет САМ старт воркфлоу:

        temporal operator search-attribute create --name RootIssue --type Int
        temporal operator search-attribute create --name Repo --type Keyword

    Пока оператор их не завёл, включение сломало бы обработку целиком — цена
    ошибки конфигурации несопоставима с пользой от фильтра в UI.
    """
    if not os.environ.get("TEMPORAL_SEARCH_ATTRIBUTES", "").strip():
        return None
    # Для обычного Issue корень — он сам; у follow-up он указан в теле строкой
    # `root-issue: #N` (AGENT-PROTOCOL.md, раздел 3).
    root = parse_root_issue((payload.get("issue") or {}).get("body")) or issue_number
    return {"Repo": [repo], "RootIssue": [root]}


def _issue_input(payload: dict, *, interactive: bool):
    """`IssueInput` из полезной нагрузки вебхука.

    Импорт внутри функции — как и в остальных ветках: shared/ подтягивается
    лениво, чтобы старт вебхука не зависел от воркерных зависимостей.
    """
    from shared.workflow_types import IssueInput

    issue = payload["issue"]
    return IssueInput(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        author_login=issue["user"]["login"],
        author_type=(issue.get("user") or {}).get("type") or "User",
        interactive=interactive,
    )


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


async def _ack_comment_seen(client, repo: str, issue_number: int,
                            comment_id: int) -> None:
    """Реакция `eyes` на принятый комментарий — отдельным прогоном.

    Ставит её воркер, а не вебхук: GitHub-клиента здесь нет намеренно (см.
    `_may_start_expensive`), и заводить его ради реакции значило бы дать
    смотрящему наружу процессу право писать в Issue. Вебхук лишь просит.

    Сбой самого запроса не должен ронять обработку комментария: подтверждение
    приёма дороже своей стоимости только пока оно бесплатно для основного пути.
    """
    from shared.workflow_types import CommentAckInput

    try:
        await client.start_workflow(
            "CommentAck",
            CommentAckInput(repo=repo, issue_number=issue_number,
                            comment_id=comment_id),
            id=comment_ack_workflow_id(repo, comment_id),
            task_queue="issue-lifecycle",
        )
    except WorkflowAlreadyStartedError:
        pass  # повторная доставка того же комментария — реакция уже заказана
    except Exception as exc:
        _log.warning("не удалось подтвердить приём комментария %s#%s (%s): %s",
                     repo, issue_number, comment_id, exc)


def verify_agent_signature(body: bytes, signature_header: str | None) -> None:
    """Подпись входящего события агента — своим секретом, не гитхабовским.

    Сигнал, двигающий фазу Issue, не может приходить анонимно. Секрет отдельный:
    у соседних сервисов свои права, и утечка одного не должна открывать второй
    канал. Без переменной эндпоинт закрыт (503, а не «пропускаем всех») —
    молчаливо открытый приём фазовых событий хуже, чем выключенный.
    """
    secret = os.environ.get("AGENT_EVENT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="AGENT_EVENT_SECRET не задан")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def _report_orphan(client, event, reason: str) -> None:
    """Событие, которое не удалось связать с Issue, не пропадает молча.

    Опознать работу не получилось — значит, ни одна фаза не сдвинется, и
    единственное, что мы можем, — сделать это видимым. Тишина здесь означала бы
    ровно тот обрыв трассировки, ради которого задача и ставилась.
    """
    from shared.workflow_types import OrphanEventInput

    try:
        await client.start_workflow(
            "OrphanAgentEvent",
            OrphanEventInput(repo=event.repo, agent=event.agent, phase=event.phase,
                             status=event.status, ref=event.ref, reason=reason,
                             detail=event.detail[:2000]),
            # Тот же ключ, что и у идемпотентности в цикле: один факт — одна запись.
            id=f"orphan-{event.repo}-{event.key()}",
            task_queue="issue-lifecycle",
        )
    except WorkflowAlreadyStartedError:
        pass  # повторная доставка того же факта — запись уже есть
    except Exception as exc:
        _log.warning("не удалось записать событие-сироту от %s: %s", event.agent, exc)


@app.post("/agent-event")
async def agent_event(
    request: Request,
    x_agent_signature_256: str | None = Header(None),
):
    """Приём фактов от внешних агентов контура (#38).

    Транспорт узкий намеренно: соседние сервисы (PR-Agent, PR-Closer, CI) живут
    своим релизным циклом и Temporal не используют. Общий namespace потребовал
    бы втащить в них SDK и знание наших workflow id — связность, ради ухода от
    которой задача и ставилась.
    """
    from shared.agent_events import InvalidAgentEvent, correlate, parse_event

    body = await request.body()
    verify_agent_signature(body, x_agent_signature_256)
    try:
        event = parse_event(await request.json())
    except InvalidAgentEvent as exc:
        # 400, а не 500: конверт некорректен, и ретраить его бессмысленно.
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if not is_allowed(event.repo, allowed_specs()):
        _log.warning("событие агента %s по чужому репозиторию %s отброшено",
                     event.agent, event.repo)
        return {"ok": True, "correlated": False}

    client = await get_temporal_client()
    issue_number, how = correlate(event)
    if issue_number is None:
        await _report_orphan(client, event, how)
        return {"ok": True, "correlated": False, "reason": how}

    event.correlation = how
    await client.start_workflow(
        "IssueLifecycle",
        args=_lifecycle_args_for(event, issue_number),
        id=issue_workflow_id(event.repo, issue_number),
        task_queue="issue-lifecycle",
        start_signal="agent_event",
        start_signal_args=[event],
    )
    return {"ok": True, "correlated": True, "issue": issue_number, "by": how}


def _lifecycle_args_for(event, issue_number: int) -> list:
    """Аргументы старта цикла для события агента.

    Цикла может не быть: Issue завели до установки App, либо его прогон уже
    закрылся по сроку. Поднимать его обычным путём нельзя — триаж пошёл бы по
    пустым заголовку и телу, задал бы человеку уточняющий вопрос и потратил
    вызовы модели на задачу, которая давно в разработке.

    Поэтому цикл поднимается СРАЗУ в той фазе, о которой доложил агент, через
    тот же снимок состояния, что используется для continue-as-new (#36).
    Триажу тут делать нечего: работа уже в PR.
    """
    from shared.agent_events import target_phase
    from shared.workflow_types import IssueInput, LifecycleState

    phase = target_phase(event)
    return [
        IssueInput(repo=event.repo, issue_number=issue_number,
                   # Заголовок и тело в фазах внешних агентов не используются;
                   # запрашивать их у GitHub значило бы завести в вебхуке
                   # второй клиент ради полей, которые никто не прочитает.
                   title="", body="", author_login="", author_type="User",
                   interactive=False),
        LifecycleState(phase=phase, stage=phase),
    ]


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
):
    """Приём доставки. Отказать может только подпись.

    Всё остальное — включая payload, который мы не сумели разобрать, — уезжает
    в аудит и подтверждается 200. Причина: у GitLab автоматических ретраев нет,
    доставка теряется навсегда, а четыре подряд провала отключают вебхук на
    срок до суток. 500 отсюда стоит дороже, чем необработанное событие.
    """
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = await request.json()
    try:
        return await _handle_delivery(payload, x_github_event, x_github_delivery)
    except HTTPException:
        raise
    except Exception:
        _log.exception(
            "не разобрал доставку %s (%s) — принимаю и ухожу в аудит",
            x_github_delivery or "без id", x_github_event)
        await _audit_dropped_delivery(
            payload, x_github_event, x_github_delivery,
            (payload.get("repository") or {}).get("full_name"),
            ["(ошибка разбора)"])
        return {"ok": True}


async def _handle_delivery(payload: dict, x_github_event: str,
                           x_github_delivery: str | None):
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
            try:
                await client.start_workflow(
                    "IssueLifecycle",  # имя workflow строкой — worker зарегистрирует класс под этим именем
                    _issue_input(payload, interactive=True),
                    id=wf_id,
                    task_queue="issue-lifecycle",
                    search_attributes=_search_attributes(repo, payload, issue_number),
                )
            except WorkflowAlreadyStartedError:
                # Повторная доставка того же события — норма, а не сбой: GitHub
                # ретраит, если не дождался ответа, и оба раза просит одного и
                # того же. Цикл по этому Issue уже существует, то есть нужное
                # состояние достигнуто.
                #
                # 500 здесь был хуже, чем бесполезен: GitHub на нём ретраит
                # снова, каждый ретрай снова падает, и вебхук отвечает ошибкой
                # на штатную ситуацию, пока доставка не будет брошена насовсем.
                _log.info("цикл %s#%s уже запущен — повторная доставка",
                          repo, issue_number)

        elif action == "closed":
            # Закрытый Issue не ждут. Голый signal, а НЕ signal-with-start:
            # поднимать цикл по Issue, которым никто не занимался, чтобы тут же
            # его закрыть, — лишний прогон в истории и лишние вызовы GitHub.
            handle = client.get_workflow_handle(wf_id)
            try:
                await handle.signal(
                    "issue_closed", (payload.get("sender") or {}).get("login"))
            except Exception:
                # Цикла нет или он уже завершён — сигналить некому. Это штатно:
                # на 500 GitHub ретраит доставку и в итоге бросает её насовсем.
                _log.info("no live cycle for closed %s#%s", repo, issue_number)

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
                # Режим (child цикла или самостоятельный прогон) выбирает
                # лаунчер — одна точка решения на все входы.
                await request_analysis(
                    client,
                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.
                    _issue_input(payload, interactive=False),
                    build_analyze_input(payload),  # без comment_id: триггер — метка
                    search_attributes=_search_attributes(repo, payload, issue_number),
                )
                return {"ok": True}

            if command == ESTIMATE:
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                from shared.workflow_types import EstimateRequest

                await request_estimate(
                    client,
                    _issue_input(payload, interactive=False),
                    EstimateRequest(repo=repo, issue_number=issue_number),
                    search_attributes=_search_attributes(repo, payload, issue_number),
                )
                return {"ok": True}

            if command in (BFT, BFT_DEEP):
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                await request_bft(
                    client,
                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.
                    _issue_input(payload, interactive=False),
                    # Без comment_id и без уточнений: метка несёт только сам факт
                    # запуска, и это законно — «пересобери по тому, что в Issue».
                    build_bft_request(payload, bft_mode(command)),
                    search_attributes=_search_attributes(repo, payload, issue_number),
                )
                return {"ok": True}

            if label in HUMAN_DECISION_LABELS:
                if not _may_start_expensive(payload, label, repo, issue_number):
                    return {"ok": True}
                # signal-with-start, а не голый signal: лейбл прилетает и по
                # issue, у которого воркфлоу триажа не существует (issue завели
                # до установки App — `issues.opened` никто не доставил; либо
                # триаж прогнали в обход Temporal). signal() в несуществующий
                # workflow бросает исключение, вебхук отвечает 500, GitHub
                # ретраит и бросает доставку — лейбл остаётся мёртвым молча.
                await client.start_workflow(
                    "IssueLifecycle",
                    # Отвечать на уточняющий вопрос тут некому: триггер —
                    # лейбл, а не диалог. VAGUE обязан эскалировать, иначе цикл
                    # уточнений съест только что доставленный сигнал.
                    _issue_input(payload, interactive=False),
                    id=wf_id,
                    task_queue="issue-lifecycle",
                    search_attributes=_search_attributes(repo, payload, issue_number),
                    start_signal="human_decision",
                    start_signal_args=[label],
                )

    elif x_github_event == "issue_comment":
        if payload["action"] != "created":
            return {"ok": True}
        # Комментарии от самого сервиса не должны сигналить сами себя —
        # тот же принцип, что и guard `comment.user.type != 'Bot'` в старой
        # версии на Actions.
        # `.get`, а не индексация: поле есть только у GitHub. Основную работу
        # всё равно делает подпись ниже — она различает происхождение, а не
        # автора, и работает у любого провайдера.
        if (payload["comment"].get("user") or {}).get("type") == "Bot":
            return {"ok": True}
        # Гейта по типу автора мало: под PAT сервис пишет от имени человека, и
        # его комментарии возвращаются с `type == "User"`. На живом прогоне
        # именно так advisor-ответ и разбор приоритета приезжали обратно как
        # `user_comment`. Различаем по подписи, а не по логину: владелец токена
        # — тот же человек, чьи настоящие ответы кормят цикл уточнений.
        if is_agent_comment(payload["comment"].get("body")):
            return {"ok": True}

        repo = payload["repository"]["full_name"]
        issue_number = payload["issue"]["number"]

        # Подтверждение приёма — ДО разбора команды и до любого пайплайна.
        # Всё, что ниже, ветвится и гейтится (права, живой цикл, лимиты LLM);
        # реакция не ветвится ни на чём: комментарий доставлен, значит система
        # его увидела, и это должно быть видно человеку сразу.
        await _ack_comment_seen(client, repo, issue_number,
                                payload["comment"]["id"])

        # Единственная точка ветвления «команда против обычного комментария»:
        # команда НЕ уходит в user_comment, иначе её съел бы цикл уточнений
        # intake gate как ответ на уточняющий вопрос.
        command = parse_command(payload["comment"].get("body") or "")

        if command == ESTIMATE:
            if not _may_start_expensive(payload, "/estimate", repo, issue_number):
                return {"ok": True}
            from shared.workflow_types import EstimateRequest

            comment_id = payload["comment"]["id"]
            await request_estimate(
                client,
                _issue_input(payload, interactive=True),
                EstimateRequest(repo=repo, issue_number=issue_number,
                                comment_id=comment_id),
                search_attributes=_search_attributes(repo, payload, issue_number),
            )
            return {"ok": True}

        if command in (BFT, BFT_DEEP):
            if not _may_start_expensive(payload, f"/{command}", repo, issue_number):
                return {"ok": True}
            await request_bft(
                client,
                _issue_input(payload, interactive=True),
                build_bft_request(payload, bft_mode(command)),
                search_attributes=_search_attributes(repo, payload, issue_number),
            )
            return {"ok": True}

        if command == ANALYZE:
            if not _may_start_expensive(payload, "/analyze", repo, issue_number):
                return {"ok": True}
            # Одна точка решения child-vs-root: раньше здесь стартовал
            # самостоятельный IssueAnalysis, а циклу уходило лишь косметическое
            # уведомление — связь между владельцем состояния Issue и работой
            # агента была декоративной (#37).
            await request_analysis(
                client,
                _issue_input(payload, interactive=True),
                build_analyze_input(payload),
                search_attributes=_search_attributes(repo, payload, issue_number),
            )
            return {"ok": True}

        wf_id = workflow_id_for(repo, issue_number)
        handle = client.get_workflow_handle(wf_id)
        try:
            await handle.signal("user_comment", args=[payload["comment"]["body"],
                                                       payload["comment"]["id"]])
        except Exception:
            # Сознательное исключение из правила «сигнал поднимает цикл».
            # Команды (`/analyze`, `/estimate`, метки решения) идут через
            # signal-with-start и проходят гейт на дорогую стадию; обычный
            # комментарий гейта не проходит — им можно завести триаж на любом
            # Issue репозитория, включая тысячи старых. Цена ошибки здесь —
            # веер LLM-прогонов, а польза — доставка реплики в цикл, которого
            # нет; поэтому комментарий по-прежнему best-effort.
            _log.info("no live lifecycle for %s#%s — комментарий не доставлен",
                      repo, issue_number)

    return {"ok": True}
