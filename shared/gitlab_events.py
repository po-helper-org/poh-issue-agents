"""Нормализация вебхуков GitLab во внутреннюю форму события.

GitLab и GitHub описывают одно и то же разными словами: проект против
репозитория, `iid` против `number`, заметка против комментария. Разбирать это
различие в каждой ветке обработчика значило бы размазать провайдера по всему
транспорту.

Поэтому различие снимается здесь, на входе, один раз. Дальше по коду едет тот
же словарь, с которым контур работает сегодня.

**Это не транслятор-прокси.** Отвергнутый дизайном подход подменял вызовы API,
делая вид, что GitLab — это GitHub. Здесь переводится только полезная нагрузка
вебхука, и перевод односторонний: наружу контур ходит драйвером, а не через
подделку.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
"""
from __future__ import annotations

from typing import Any

# `X-Gitlab-Event` несёт человекочитаемое имя с пробелом, а не snake_case.
EVENT_ISSUE = "Issue Hook"
EVENT_NOTE = "Note Hook"
EVENT_MERGE_REQUEST = "Merge Request Hook"

# Внутренние имена событий — те же, что у GitHub: их знает `_handle_delivery`.
_EVENT_MAP = {
    EVENT_ISSUE: "issues",
    EVENT_NOTE: "issue_comment",
    EVENT_MERGE_REQUEST: "pull_request",
}

# `object_attributes.action` у GitLab против `action` у GitHub.
_ISSUE_ACTION_MAP = {
    "open": "opened",
    "close": "closed",
    "reopen": "reopened",
    "update": "edited",
}


class UnsupportedEvent(Exception):
    """Событие, которого контур не ждёт. Не ошибка — повод тихо подтвердить."""


def internal_event(gitlab_event: str) -> str:
    """Имя события во внутренней форме."""
    name = _EVENT_MAP.get((gitlab_event or "").strip())
    if not name:
        raise UnsupportedEvent(f"событие не поддерживается: {gitlab_event!r}")
    return name


def project_path(payload: dict) -> str | None:
    """Полный путь проекта — аналог `repository.full_name`.

    Поле `repository` в payload GitLab тоже есть, но помечено устаревшим и не
    несёт неймспейса: у проекта в подгруппе оттуда пришло бы одно имя без пути,
    и allowlist принял бы чужой проект с таким же именем.
    """
    project = payload.get("project") or {}
    return project.get("path_with_namespace") or None


def project_id(payload: dict) -> int | None:
    """Числовой id проекта. Он переживает переименование и перенос между группами."""
    project = payload.get("project") or {}
    value = project.get("id")
    return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None


def labels_added(payload: dict) -> list[str]:
    """Метки, добавленные этим событием.

    GitHub присылает готовое поле `label.name`. GitLab не присылает вовсе —
    только `changes.labels.previous` и `current`. Дельту считаем сами, иначе
    весь триггерный путь (`run:*`, `research-me`, `bug-me`, `build-me`) не
    работает.
    """
    changes = (payload.get("changes") or {}).get("labels") or {}
    before = {l.get("title") for l in (changes.get("previous") or []) if l.get("title")}
    after = {l.get("title") for l in (changes.get("current") or []) if l.get("title")}
    return sorted(after - before)


def labels_removed(payload: dict) -> list[str]:
    changes = (payload.get("changes") or {}).get("labels") or {}
    before = {l.get("title") for l in (changes.get("previous") or []) if l.get("title")}
    after = {l.get("title") for l in (changes.get("current") or []) if l.get("title")}
    return sorted(before - after)


def _labels(raw) -> list[dict]:
    """Метки во внутренней форме `[{"name": ...}]`.

    GitLab кладёт объекты с полем `title`, но в части хуков встречаются голые
    строки. Принимаем оба вида: разбирать это в каждом вызывающем значило бы
    повторить ошибку в каждом.
    """
    out = []
    for item in raw or []:
        name = item.get("title") if isinstance(item, dict) else item
        if name:
            out.append({"name": str(name)})
    return out


def _actor(payload: dict, bot_login: str | None) -> dict:
    """Автор события во внутренней форме.

    Поля `type` у GitLab нет вовсе, а контур на него местами смотрит. Считаем
    ботом того, чей логин совпадает с логином сервисного аккаунта — это и есть
    единственный признак, доступный на обоих провайдерах. Опознание СВОИХ
    комментариев при этом всё равно держится на маркере в теле, а не на авторе:
    маркер различает происхождение, а логин — только личность.
    """
    user = payload.get("user") or {}
    login = user.get("username") or ""
    return {
        "login": login,
        "type": "Bot" if bot_login and login == bot_login else "User",
        "id": user.get("id"),
    }


def _issue_from_hook(payload: dict, actor: dict) -> dict:
    attrs = payload.get("object_attributes") or {}
    return {
        # `iid` — номер внутри проекта, аналог `number`. Глобальный `id` в пути
        # API не участвует и в качестве номера задачи означал бы чужую задачу.
        "number": attrs.get("iid"),
        "title": attrs.get("title") or "",
        "body": attrs.get("description") or "",
        "state": attrs.get("state"),
        "user": actor,
        "labels": _labels(attrs.get("labels")),
    }


def _issue_from_note(payload: dict) -> dict:
    issue = payload.get("issue") or {}
    author = issue.get("author") or {}
    return {
        "number": issue.get("iid"),
        "title": issue.get("title") or "",
        "body": issue.get("description") or "",
        "state": issue.get("state"),
        # Автор ЗАДАЧИ, не комментария. У GitLab в Note Hook его может не быть —
        # тогда остаётся пустым, а не подставляется автор комментария: подмена
        # одного другим сделала бы чужую задачу своей.
        "user": {"login": author.get("username") or "", "type": "User"},
        "labels": _labels(issue.get("labels")),
    }


def normalize(gitlab_event: str, payload: dict, *, bot_login: str | None = None) -> dict:
    """Payload GitLab во внутренней форме.

    Возвращает словарь той же формы, что приходит от GitHub, плюс служебный
    ключ `_gitlab` с тем, чего у GitHub нет: числовым id проекта и дельтой
    меток. Ключ с подчёркиванием — чтобы было видно, что он наш, а не пришёл
    от трекера.
    """
    event = internal_event(gitlab_event)
    actor = _actor(payload, bot_login)
    attrs = payload.get("object_attributes") or {}

    out: dict[str, Any] = {
        "repository": {"full_name": project_path(payload)},
        "sender": actor,
        "_gitlab": {
            "project_id": project_id(payload),
            "labels_added": labels_added(payload),
            "labels_removed": labels_removed(payload),
        },
    }

    if event == "issues":
        raw_action = (attrs.get("action") or "").lower()
        added = labels_added(payload)
        # Смена меток приезжает действием `update`. Для контура это событие
        # «поставили метку», и оно должно выглядеть как `labeled`, иначе
        # триггерный путь не запустится.
        if raw_action == "update" and added:
            out["action"] = "labeled"
            out["label"] = {"name": added[0]}
        else:
            out["action"] = _ISSUE_ACTION_MAP.get(raw_action, raw_action)
        out["issue"] = _issue_from_hook(payload, actor)
        return out

    if event == "issue_comment":
        if (attrs.get("noteable_type") or "") != "Issue":
            raise UnsupportedEvent(
                f"заметка не к задаче: noteable_type={attrs.get('noteable_type')!r}")
        # У GitLab действие заметки — create/update; контур реагирует только на
        # появление новой.
        out["action"] = "created" if (attrs.get("action") or "create") == "create" else "edited"
        out["issue"] = _issue_from_note(payload)
        out["comment"] = {
            "id": attrs.get("id"),
            "body": attrs.get("note") or "",
            "user": actor,
        }
        return out

    if event == "pull_request":
        out["action"] = (attrs.get("action") or "").lower()
        out["pull_request"] = {
            "number": attrs.get("iid"),
            "title": attrs.get("title") or "",
            "body": attrs.get("description") or "",
            "state": attrs.get("state"),
            "head": {"ref": attrs.get("source_branch")},
            "base": {"ref": attrs.get("target_branch")},
            "user": actor,
        }
        return out

    raise UnsupportedEvent(f"событие без обработчика: {gitlab_event!r}")
