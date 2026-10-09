"""Клиент Gitea — хранилище карточек харнесса БФТ (docs/BFT-HARNESS.md, ADR-21).

Повторяет операции `github_client`/`gitlab_client`, которые вызывает контур, по
тому же первому аргументу — репозиторию. Выбирает его `forge.provider_for` по
переменной `GITEA_REPOS`.

Чем Gitea отличается от GitHub для контура:
- метки в API — по id, контур же ставит их по имени: имена разрешаются здесь, а
  незнакомая метка заводится, как GitHub заводит её при первом применении;
- `user.type` всегда «User»: ботом считаем логин сервисного аккаунта
  (`GITEA_BOT_LOGIN`), как у GitLab.
Полный набор операций (ветки, файлы, поиск) — T2 (#330).
"""
from __future__ import annotations

import logging
import os
import urllib.parse

import requests

from shared.agent_comment import sign

_log = logging.getLogger("gitea_client")

TIMEOUT = 30


def _base() -> str:
    return os.environ.get("GITEA_URL", "http://127.0.0.1:8650").rstrip("/") + "/api/v1"


def _dry_run() -> bool:
    return bool(os.environ.get("DRY_RUN"))


def _token() -> str:
    token = os.environ.get("GITEA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITEA_TOKEN не задан")
    return token


def bot_login() -> str:
    return os.environ.get("GITEA_BOT_LOGIN", "").strip()


def _url(repo: str, path: str) -> str:
    owner, _, name = str(repo).strip().strip("/").partition("/")
    return f"{_base()}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}{path}"


def _request(method: str, url: str, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("headers", {"Authorization": f"token {_token()}"})
    resp = requests.request(method, url, **kwargs)
    if resp.status_code == 429:
        raise RuntimeError(f"429 от Gitea, Retry-After={resp.headers.get('Retry-After') or '?'}")
    return resp


def _ok(resp, *, allow=()):
    if resp.status_code in allow:
        return resp
    resp.raise_for_status()
    return resp


def _user(raw: dict | None) -> dict:
    login = (raw or {}).get("login") or ""
    return {"login": login, "type": "Bot" if bot_login() and login == bot_login() else "User"}


# --- комментарии ---

def post_comment(repo: str, issue_number: int, body: str) -> None:
    """Комментарий сервиса — всегда подписанный: без подписи вебхук примет его за реплику человека."""
    body = sign(body)
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    _ok(_request("POST", _url(repo, f"/issues/{issue_number}/comments"), json={"body": body}))


def list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:
    resp = _ok(_request("GET", _url(repo, f"/issues/{issue_number}/comments")))
    return [{"id": c.get("id"), "body": c.get("body") or "", "user": _user(c.get("user")),
             "created_at": c.get("created_at")} for c in resp.json()[:limit]]


def add_reaction(repo: str, comment_id: int, content: str = "eyes",
                 issue_number: int | None = None) -> None:
    """Реакция на комментарий. Имена emoji у Gitea те же, что у GitHub."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s %s/%s", content, repo, comment_id)
        return
    # Повторная реакция — не ошибка: доставка могла продублироваться.
    _ok(_request("POST", _url(repo, f"/issues/comments/{comment_id}/reactions"),
                 json={"content": content}), allow=(403, 409))


# --- метки ---

def _label_ids(repo: str) -> dict:
    resp = _ok(_request("GET", _url(repo, "/labels"), params={"limit": 200}))
    return {item["name"]: item["id"] for item in resp.json()}


def _create_label(repo: str, name: str, color: str = "cccccc", description: str = ""):
    """Единственное место заведения метки: Gitea ждёт цвет с «#», спеки контура — без."""
    return _request("POST", _url(repo, "/labels"),
                    json={"name": name, "color": "#" + str(color).lstrip("#"), "description": description})


def _ensure_label(repo: str, ids: dict, name: str) -> int:
    if name not in ids:
        ids[name] = _ok(_create_label(repo, name)).json()["id"]
    return ids[name]


def set_labels(repo: str, issue_number: int, *, add=(), remove=()) -> None:
    add = [label for label in add if label]
    remove = [label for label in remove if label and label not in set(add)]
    if not add and not remove:
        return
    if _dry_run():
        _log.info("[DRY_RUN] labels %s#%s += %s -= %s", repo, issue_number, add, remove)
        return
    ids = _label_ids(repo)
    if add:
        _ok(_request("POST", _url(repo, f"/issues/{issue_number}/labels"),
                     json={"labels": [_ensure_label(repo, ids, name) for name in add]}))
    for name in remove:
        if name in ids:   # снимать нечего — метки в репозитории нет вовсе
            _ok(_request("DELETE", _url(repo, f"/issues/{issue_number}/labels/{ids[name]}")),
                allow=(404,))


def add_label(repo: str, issue_number: int, label: str) -> None:
    set_labels(repo, issue_number, add=[label])


def remove_label(repo: str, issue_number: int, label: str) -> None:
    set_labels(repo, issue_number, remove=[label])


def ensure_labels_exist(repo: str, specs) -> int:
    """Заводит недостающие метки с цветом и описанием. Возвращает число созданных."""
    if _dry_run():
        return 0
    ids, created = _label_ids(repo), 0
    for spec in specs:
        if spec.name in ids:
            continue
        resp = _create_label(repo, spec.name, spec.color, spec.description)
        if resp.status_code == 409:
            continue  # завелась параллельно
        _ok(resp)
        created += 1
    return created


# --- задачи ---

def get_issue(repo: str, issue_number: int) -> dict:
    raw = _ok(_request("GET", _url(repo, f"/issues/{issue_number}"))).json()
    return {
        "number": raw.get("number"),
        "title": raw.get("title") or "",
        "body": raw.get("body") or "",
        "state": "closed" if raw.get("state") == "closed" else "open",
        "labels": [{"name": lab.get("name")} for lab in raw.get("labels") or []],
        "user": _user(raw.get("user")),
        "html_url": raw.get("html_url"),
    }


def get_issue_body(repo: str, issue_number: int) -> str:
    return get_issue(repo, issue_number)["body"]


def update_issue_body(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] update body %s#%s", repo, issue_number)
        return
    _ok(_request("PATCH", _url(repo, f"/issues/{issue_number}"), json={"body": body}))


def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:
    """Кандидаты в дубликаты в форме GitHub/GitLab-клиента, с `_kind`.

    У харнесса БФТ в репозитории только задачи-карточки: PR там не открываются, поэтому
    ищутся задачи (`type=issues`), открытые и закрытые. Поиск Gitea — по заголовку и телу.
    """
    resp = _ok(_request("GET", _url(repo, "/issues"),
                        params={"q": query, "type": "issues", "state": "all", "limit": min(limit, 50)}))
    return [{
        "number": item.get("number"),
        "title": item.get("title") or "",
        "body": item.get("body") or "",
        "state": item.get("state"),
        "url": item.get("html_url"),
        "labels": [{"name": lab.get("name")} for lab in item.get("labels") or []],
        "_kind": "issue",
    } for item in resp.json()[:limit]]
