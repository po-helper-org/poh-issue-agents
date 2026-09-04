"""Событие ревью GitHub → факт для цикла Issue.

Тип факта — тот же `AgentEvent`, которым докладывают внешние агенты. Заводить
для человека отдельный вид события значило бы два пути к одному действию: круг
правок уже читает замечания любого происхождения (`github_client.review_text`
берёт и тело ревью, и построчные), и различать их ему незачем.

Модуль чистый: ни сети, ни Temporal. Вебхук — транспорт, и разбор конверта
обязан проверяться без него.
"""
from __future__ import annotations

from shared import lifecycle
from shared.agent_events import STARTED, AgentEvent

# Кто оставил ревью — под этим именем факт видно в трассировке.
HUMAN_REVIEW_AGENT = "human-review"

# Состояния, по которым есть что править. `approved` и `dismissed` не будят:
# по одобрению править нечего, а снятое ревью — уже не замечание.
_WAKING_STATES = ("changes_requested", "commented")


def _is_bot(user: dict) -> bool:
    """Ревью бота по этому пути не будит ничего.

    PR-Agent докладывает через `/agent-event`, и вторая побудка дала бы два
    круга правок на один доклад — двойную цену прогона агента за тот же текст.
    """
    return (user.get("type") or "") == "Bot" or (user.get("login") or "").endswith("[bot]")


def from_review(payload: dict) -> AgentEvent | None:
    """Формальное ревью. `None` — будить нечего."""
    if payload.get("action") != "submitted":
        return None
    review = payload.get("review") or {}
    state = (review.get("state") or "").lower()
    if state not in _WAKING_STATES:
        return None
    if _is_bot(review.get("user") or {}):
        return None

    body = (review.get("body") or "").strip()
    # Пустое тело при `changes_requested` — замечания в построчных, и это
    # ровно тот случай, ради которого всё пишется. Пустой `commented` —
    # действительно ничего.
    if not body and state != "changes_requested":
        return None

    pull = payload.get("pull_request") or {}
    return AgentEvent(
        repo=(payload.get("repository") or {}).get("full_name") or "",
        agent=HUMAN_REVIEW_AGENT,
        phase=lifecycle.PR_REVIEW,
        status=STARTED,
        ref=str(pull.get("number") or ""),
        # Тело PR едет в detail: по нему `correlate` находит задачу через
        # `Closes #N`, если номер не пришёл явно.
        detail=f"### Ревью ({state})\n{body}\n\n{pull.get('body') or ''}".strip(),
        # Ревизия входит в ключ идемпотентности: два ревью по одному коммиту —
        # один повод, два по разным — два.
        revision=str(review.get("commit_id") or ""),
    )


def from_review_comment(payload: dict) -> AgentEvent | None:
    """Построчное замечание без формального ревью. `None` — будить нечего."""
    if payload.get("action") != "created":
        return None
    comment = payload.get("comment") or {}
    if _is_bot(comment.get("user") or {}):
        return None
    body = (comment.get("body") or "").strip()
    if not body:
        return None

    pull = payload.get("pull_request") or {}
    where = f"{comment.get('path')}:{comment.get('line') or '?'}"
    return AgentEvent(
        repo=(payload.get("repository") or {}).get("full_name") or "",
        agent=HUMAN_REVIEW_AGENT,
        phase=lifecycle.PR_REVIEW,
        status=STARTED,
        ref=str(pull.get("number") or ""),
        detail=f"### {where}\n{body}\n\n{pull.get('body') or ''}".strip(),
        revision=str(comment.get("commit_id") or ""),
    )
