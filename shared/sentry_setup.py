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


def _scrub_event(event: dict, hint=None) -> Optional[dict]:
    """before_send: вычистить секреты из кадров стека, request и extra."""
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


def capture_pipeline_failure(issue, exc_type: str, message: str) -> None:
    """Workflow триажа (IssueLifecycle) поймал исключение и поставил лейбл
    `advisor:error` (workflows.py) — эскалация в Sentry.

    fingerprint по (pipeline_failure, exc_type): аутейдж z.ai даёт одно issue с
    сотней событий, а не сотню отдельных по одному на каждую issue.
    """
    if not _configured:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(issue, "repo", None))
        scope.set_tag("issue", str(getattr(issue, "issue_number", None)))
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["pipeline_failure", exc_type]
        sentry_sdk.capture_message(
            f"pipeline failed: {getattr(issue, 'repo', '?')}"
            f"#{getattr(issue, 'issue_number', '?')} ({exc_type})",
            level="error")


def capture_estimate_failure(req, stage: str, exc_type: str, message: str) -> None:
    """Workflow /estimate (IssueEstimation) упал на стадии `stage`.

    fingerprint по (estimate_failure, stage): группируем по стадии сбоя
    (сбор контекста / извлечение фактов / …), а не по issue.
    """
    if not _configured:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("repo", getattr(req, "repo", None))
        scope.set_tag("issue", str(getattr(req, "issue_number", None)))
        scope.set_tag("stage", stage)
        scope.set_tag("exc_type", exc_type)
        scope.set_extra("message", message)
        scope.fingerprint = ["estimate_failure", stage]
        sentry_sdk.capture_message(
            f"estimate failed at «{stage}»: {getattr(req, 'repo', '?')}"
            f"#{getattr(req, 'issue_number', '?')} ({exc_type})",
            level="error")
