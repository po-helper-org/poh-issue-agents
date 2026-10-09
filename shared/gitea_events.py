"""Нормализация вебхуков Gitea во внутреннюю (GitHub-) форму.

Gitea шлёт почти ту же форму, что GitHub: `action`, `issue`, `comment`,
`repository.full_name`, `sender.login`. Различий три, и все — на входе:

- имя события — в `X-Gitea-Event-Type` (`issues`, `issue_comment`,
  `issue_label`), а не в `X-GitHub-Event`;
- поле `user.type` у Gitea всегда «User»: ботом считаем логин сервисного
  аккаунта, как у GitLab (`shared/gitlab_events._actor`);
- смена меток приезжает действием `label_updated` без поля «какая метка» —
  `labeled` из неё не собрать; сигнал `card_updated` для неё — T2 (#330).
"""
from __future__ import annotations

from typing import Any


class UnsupportedEvent(Exception):
    """Событие, которого контур не ждёт. Не ошибка — повод тихо подтвердить."""


_EVENTS = {"issues": "issues", "issue_comment": "issue_comment"}


def internal_event(gitea_event: str) -> str:
    """Имя события во внутренней форме."""
    name = _EVENTS.get((gitea_event or "").strip())
    if not name:
        raise UnsupportedEvent(f"событие не поддерживается: {gitea_event!r}")
    return name


def _user(raw: dict | None, bot_login: str | None) -> dict:
    raw = raw or {}
    login = raw.get("login") or ""
    return {"login": login, "type": "Bot" if bot_login and login == bot_login else "User", "id": raw.get("id")}


def _issue(raw: dict, bot_login: str | None) -> dict:
    return {
        "number": raw.get("number"),
        "title": raw.get("title") or "",
        "body": raw.get("body") or "",
        "state": raw.get("state"),
        "user": _user(raw.get("user"), bot_login),
        "labels": [{"name": str(lab.get("name"))} for lab in raw.get("labels") or [] if lab.get("name")],
    }


def normalize(gitea_event: str, payload: dict, *, bot_login: str | None = None) -> dict:
    """Payload Gitea в форме GitHub для `_handle_delivery`.

    `gitea_event` — значение `X-Gitea-Event-Type`.
    """
    event = internal_event(gitea_event)
    out: dict[str, Any] = {
        "action": payload.get("action"),
        "repository": {"full_name": (payload.get("repository") or {}).get("full_name")},
        "sender": _user(payload.get("sender"), bot_login),
        "issue": _issue(payload.get("issue") or {}, bot_login),
    }
    if event == "issue_comment":
        c = payload.get("comment") or {}
        out["comment"] = {"id": c.get("id"), "body": c.get("body") or "", "user": _user(c.get("user"), bot_login)}
    return out
