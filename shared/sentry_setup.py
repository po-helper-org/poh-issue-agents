"""Отправка ключевых сбоёв в Sentry (парно к логам в stdout).

Зачем: логи воркера/вебхука живут в stdout контейнера Dokploy и никого не
будят. Главный класс сбоя этого стека — не падение процесса, а *пойманный*
сбой: workflow триажа упал и оставил лейбл `advisor:error` (workflows.py), а
`/estimate` упал на стадии и поставил реакцию `confused`. Оба видны только как
коммент в issue и строка лога. Sentry делает из них адресуемое событие с
тегами service/repo/issue/stage.

`configure()` идемпотентна и НЕОБЯЗАТЕЛЬНА: без SENTRY_DSN — no-op, стек ведёт
себя ровно как до интеграции (это же и процедура отката — убрать переменную из
.env и перезапустить).

⚠️ ГРАНИЦА С TEMPORAL: этот модуль зовётся ТОЛЬКО из entrypoint'ов (worker.py,
webhook/main.py) и из activities. Никогда — из workflow-кода (workflows.py,
consolidation_workflow.py): там сетевой вызов недетерминирован и сломает replay.

⚠️ Скраббер (`_scrub_event`): в кадры стека sentry-sdk кладёт значения локальных
переменных, а по этому коду ходят ZAI_API_KEY, GitHub-токен, GITHUB_PRIVATE_KEY_B64
и тела issue/PR. Денилист имён вырезает значения ДО отправки на sentry.io —
трогать его без нужды нельзя.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_configured = False

# Ключи, значения которых не должны покидать периметр. Сопоставляется по
# ПОДСТРОКЕ имени в нижнем регистре: "github_private_key_b64" ловится по "key",
# "X-Hub-Signature-256" — по "signature", "ZAI_API_KEY" — по "key".
_SECRET_KEY = re.compile(
    r"token|key|secret|password|passwd|private|authorization|auth|cookie|"
    r"signature|dsn|credential",
    re.IGNORECASE,
)
_FILTERED = "[Filtered]"
_MAX_VALUE_LEN = 2048  # длинные значения (тела ответов) режем, а не шлём целиком


def _scrub_mapping(d) -> None:
    """Заменить значения секретных ключей на [Filtered], длинные — обрезать. In-place."""
    if not isinstance(d, dict):
        return
    for k, v in list(d.items()):
        if isinstance(k, str) and _SECRET_KEY.search(k):
            d[k] = _FILTERED
        elif isinstance(v, dict):
            _scrub_mapping(v)
        elif isinstance(v, str) and len(v) > _MAX_VALUE_LEN:
            d[k] = v[:_MAX_VALUE_LEN] + "…[truncated]"


# Отказы чужой стороны, на которые контур повлиять не может: лимит запросов и
# таймауты шлюза z.ai, обрыв связи отправителем вебхука. Их видно в Sentry как
# `handled: no` с уровнем error — вперемешку с настоящими багами, и каждая
# новая формулировка сообщения провайдера заводит ещё одно issue (за 12 дней
# 429-х набралось 15 событий, 524-х — 30).
#
# Не отбрасываем: аутейдж провайдера — причина половины сорванных прогонов, и
# слепота тут дороже шума. Понижаем до warning и склеиваем по типу, чтобы
# внешнее было отличимо от своего с одного взгляда на список.
_EXTERNAL_FAILURES = {
    "RateLimitError",       # 429 от z.ai — один ключ на все стадии контура
    "APITimeoutError",      # провайдер не ответил в срок
    "APIConnectionError",   # до провайдера не дошли
    "InternalServerError",  # 5xx и 524 от шлюза
    "ClientDisconnect",     # отправитель вебхука ушёл, не дослав тело
}


def _classify_external(event: dict) -> None:
    """Пометить отказ чужой стороны: level=warning и общий fingerprint."""
    values = (event.get("exception") or {}).get("values") or []
    if not values:
        return
    exc_type = values[-1].get("type")
    if exc_type in _EXTERNAL_FAILURES:
        event["level"] = "warning"
        event["fingerprint"] = ["external_failure", exc_type]
        event.setdefault("tags", {})["failure_side"] = "external"


def _scrub_event(event: dict, hint=None) -> Optional[dict]:
    """before_send: вычистить секреты из кадров стека, request и extra."""
    _classify_external(event)
    for value in (event.get("exception") or {}).get("values") or []:
        for frame in (value.get("stacktrace") or {}).get("frames") or []:
            _scrub_mapping(frame.get("vars"))
    request = event.get("request")
    if isinstance(request, dict):
        _scrub_mapping(request.get("headers"))
        _scrub_mapping(request.get("cookies"))
        _scrub_mapping(request.get("env"))
        request.pop("data", None)  # тело webhook'а = payload GitHub, наружу не нужно
    _scrub_mapping(event.get("extra"))
    _scrub_mapping(event.get("contexts"))
    return event


def configure(service: str) -> bool:
    """Инициализировать Sentry для процесса `service` (webhook|worker).

    Возвращает True, если Sentry включён. Без SENTRY_DSN — no-op → False.
    Идемпотентна: повторный вызов (реимпорт модуля) не плодит второй клиент.
    """
    global _configured
    if _configured:
        return True
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:  # pragma: no cover — в проде ставится из requirements.txt
        logger.warning("SENTRY_DSN задан, но sentry-sdk не установлен — Sentry выключен")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE") or None,
        # tracing выключен по умолчанию: длительности стадий уже видны в Temporal
        # UI, а трассы на каждый прогон съедят квоту без новой информации.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        before_send=_scrub_event,
        integrations=[LoggingIntegration(level=logging.INFO,        # INFO → breadcrumb
                                         event_level=logging.ERROR)],  # ERROR → событие
    )
    sentry_sdk.set_tag("service", service)
    _configured = True
    logger.info("sentry enabled: service=%s environment=%s", service,
                os.environ.get("SENTRY_ENVIRONMENT", "production"))
    return True


def event_url(event_id: Optional[str]) -> Optional[str]:
    """Ссылка на конкретное событие в Sentry — по id и слагу организации.

    Слаг из DSN не выводится (там только числовой id организации), поэтому
    берётся из `SENTRY_ORG`. Без него ссылки нет — остаётся сам id события,
    по которому оно ищется в UI руками.
    """
    org = os.environ.get("SENTRY_ORG", "").strip()
    if not event_id or not org:
        return None
    # Поиск по id события в списке issue: Sentry разворачивает его в само
    # событие. Прямой ссылки на событие без известного issue_id у API нет.
    return f"https://{org}.sentry.io/issues/?query={event_id}"


def debug_reference(event_id: Optional[str]) -> str:
    """Строка для комментария в Issue: куда смотреть, чтобы разобрать сбой.

    Пустая, если Sentry выключен: обещать человеку ссылку, за которой ничего
    нет, хуже, чем не обещать ничего.
    """
    if not event_id:
        return ""
    url = event_url(event_id)
    if url:
        return f"\n\n🔎 Подробности сбоя: [событие в Sentry]({url}) — `{event_id}`."
    return (f"\n\n🔎 Подробности сбоя: событие Sentry `{event_id}` "
            "(найти по этому id в интерфейсе Sentry).")


def capture_pipeline_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """Workflow триажа (IssueLifecycle) поймал исключение и поставил лейбл
    `advisor:error` (workflows.py) — эскалация в Sentry.

    fingerprint по (pipeline_failure, exc_type): аутейдж z.ai даёт одно issue с
    сотней событий, а не сотню отдельных по одному на каждую issue.

    Возвращает id события: он уезжает в комментарий Issue ссылкой на отладку.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["pipeline_failure", exc_type]
        return sentry_sdk.capture_message(
            f"pipeline failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_analysis_failure(analyze, exc_type: str, message: str) -> Optional[str]:
    """Workflow `/analyze` (IssueAnalysis) не довёл прогон до артефактов.

    fingerprint по (analysis_failure, exc_type): прогон дорогой и падает обычно
    не по своей вине (лимит z.ai, обрыв claude -p), и группировать такие сбои
    по issue значило бы получить новую группу на каждую задачу.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(analyze, "repo", None))
        scope.set_tag("issue", str(getattr(analyze, "issue_number", None)))
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["analysis_failure", exc_type]
        return sentry_sdk.capture_message(
            f"analysis failed: {getattr(analyze, 'repo', '?')}"
            f"#{getattr(analyze, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_estimate_failure(req, stage: str, exc_type: str,
                             message: str) -> Optional[str]:
    """Workflow /estimate (IssueEstimation) упал на стадии `stage`.

    fingerprint по (estimate_failure, stage): группируем по стадии сбоя
    (сбор контекста / извлечение фактов / …), а не по issue.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(req, "repo", None))
        scope.set_tag("issue", str(getattr(req, "issue_number", None)))
        scope.set_tag("stage", stage)
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["estimate_failure", stage]
        return sentry_sdk.capture_message(
            f"estimate failed at «{stage}»: {getattr(req, 'repo', '?')}"
            f"#{getattr(req, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_followups_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """`collect_dev_followups` (worker/activities.py) не записал находки
    агента разработки в секцию GROW тела родителя.

    Сама запись — best-effort и не роняет шаг разработки, но отказ до сих пор
    был виден только строкой `logger.warning` в stdout контейнера: воркер их
    не будит (см. докстринг модуля). warning в событие Sentry не превращается
    (порог `event_level=ERROR` у `LoggingIntegration`), а бесследно потерянная
    находка — это ровно тот класс отказа, который «шаг отработал, доложил
    успех, а результата нет» (ревью, находка 4).

    fingerprint по (followups_failure, exc_type): группируем по типу сбоя, а
    не по issue — иначе один и тот же сетевой аутейдж GitHub заводит по
    отдельной группе на каждую задачу, где он совпал с находкой агента.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "dev:followups")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["followups_failure", exc_type]
        return sentry_sdk.capture_message(
            f"dev followups failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_answer_question_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """`answer_question` (worker/activities.py) не разобрала ответ человека на
    открытый вопрос — после исчерпания ретраев (финальное ревью, находка I1,
    Important).

    Раньше вызов шёл с `maximum_attempts=1` и без перехвата: единственный сбой
    ронял весь `IssueLifecycle`, а без этого события отказ не был виден
    оператору вовсе — та же причина, что и у `capture_criterion_gate_stall`
    выше (`workflow.logger.warning` не поднимается до события Sentry, порог
    `event_level=ERROR`).

    fingerprint по (answer_question_failure, exc_type): аутейдж GitHub,
    повторяющийся на разных Issue, обязан группироваться в одну группу.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "gate:answer-question")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["answer_question_failure", exc_type]
        return sentry_sdk.capture_message(
            f"answer_question failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_criterion_gate_stall(issue, exc_type: str, message: str) -> Optional[str]:
    """Гейт критерия приёмки (`_start_development`, workflows.py) не смог
    прочитать критерий и остался на парковке той же фазы — цикл жив,
    разработка правильно не начинается, но БЕЗ этого события отказ виден
    только `workflow.logger.warning`, который порог `event_level=ERROR` у
    `LoggingIntegration` не поднимает до события (та же причина, что и у
    `capture_followups_failure` выше) — оператор его не увидит.

    fingerprint по (criterion_gate_stall, exc_type): аутейдж GitHub,
    повторяющийся на разных Issue, обязан группироваться в одну группу, а не
    заводить её на каждую задачу отдельно.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "gate:acceptance-criterion")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["criterion_gate_stall", exc_type]
        return sentry_sdk.capture_message(
            f"acceptance criterion gate stalled: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_ask_question_gate_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """`ask_question`, вызванная гейтом критерия приёмки (`_start_development`,
    workflows.py), не смогла задать вопрос — третий круг финального ревью,
    находка G2 (Important).

    Отдельный хелпер, а не переиспользование `capture_criterion_gate_stall`
    рядом: тот сообщает об отказе ЧТЕНИЯ критерия, а здесь критерий уже
    прочитан, отказала ПОСТАНОВКА вопроса — другой шаг стадии
    `gate:acceptance-criterion`, другая типичная причина (запись в GitHub, а
    не чтение), и смешивать их в одном тег `stage` значило бы группировать в
    Sentry два разных отказа под одной и той же историей.

    fingerprint по (ask_question_gate_failure, exc_type): та же причина, что
    и у соседних `capture_*_failure` — группировка по типу сбоя, а не по issue.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "gate:ask-question")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["ask_question_gate_failure", exc_type]
        return sentry_sdk.capture_message(
            f"acceptance criterion gate could not ask a question: "
            f"{getattr(issue, 'repo', '?')}#{getattr(issue, 'issue_number', '?')} "
            f"({exc_type})",
            level="error")


def capture_question_repoint_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """`read_open_question_id` (worker/activities.py) не смогла подтвердить
    актуальный открытый вопрос — воркфлоу зовёт её в двух точках (находки
    C2/F7, финальное ревью): переставить указатель после `reasked` и
    проверить его перед ответом на `/harness-answer` с пустым указателем.

    Указатель в обоих случаях остаётся НЕактуальным, а человек по кругу
    получает «этот вопрос уже устарел» на СВОЙ актуальный ответ — до этого
    события отказ был виден только `workflow.logger.warning` (тот же порог
    `event_level=ERROR`, что и у `capture_criterion_gate_stall` выше).

    fingerprint по (question_repoint_failure, exc_type): группируем по типу
    сбоя, а не по issue — иначе один и тот же сетевой аутейдж GitHub заводит
    отдельную группу на каждую задачу.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "gate:read-open-question-id")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["question_repoint_failure", exc_type]
        return sentry_sdk.capture_message(
            f"read_open_question_id failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_question_close_failure(issue, exc_type: str, message: str) -> Optional[str]:
    """`close_answered_by_body_edit` (worker/activities.py) не смогла снять
    устаревший вопрос гейта критерия при переходе в разработку (находка F6,
    Important, второй круг финального ревью).

    Вызывается ПОСЛЕ того, как решение продолжить в разработку уже принято
    — отказ не условие входа, а сорвавшаяся уборка (блок вопроса и метка
    `NEEDS_HUMAN_ANSWER` могли остаться висеть на задаче, ушедшей в
    разработку), и «следующего прохода», который довершил бы её сам,
    для этой задачи может не быть вовсе — фаза уже уезжает.

    fingerprint по (question_close_failure, exc_type): та же причина, что и
    у соседних `capture_*_failure` — группировка по типу сбоя, а не по issue.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("stage", "gate:close-answered-by-body-edit")
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["question_close_failure", exc_type]
        return sentry_sdk.capture_message(
            f"close_answered_by_body_edit failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_nondeterminism(run_id: Optional[str], message: str) -> Optional[str]:
    """Прогон разошёлся с записанной историей и встал (`shared/nondeterminism.py`).

    Единственный класс сбоя контура, который **нельзя** поймать изнутри: падает
    не тело активности, а реплей воркфлоу — код, который перехватил бы
    исключение, до выполнения не доходит. Поэтому событие поднимается снаружи,
    из наблюдателя за логом Temporal, а не из `except` в `workflows.py`.

    level=error, а не warning: в отличие от аутейджа провайдера (см.
    `_EXTERNAL_FAILURES` выше) это отказ СВОЕЙ стороны, он не рассосётся сам и
    чинится только откатом воркера на прежний образ.

    fingerprint без run_id намеренно: одна выкладка ломает разом все прогоны,
    дошедшие до изменённого места, и в живом случае #263 их было бы до сотни.
    Группировка по run_id завела бы сотню отдельных issue на одну причину —
    а причина у них ровно одна, и разбирается она один раз.
    """
    if not _configured:
        return None
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("stage", "workflow:replay")
        scope.set_tag("run_id", run_id or "unknown")
        scope.set_extra("message", message)
        scope.fingerprint = ["nondeterminism"]
        return sentry_sdk.capture_message(
            f"workflow stuck on nondeterminism (run_id={run_id or '?'})",
            level="error")
