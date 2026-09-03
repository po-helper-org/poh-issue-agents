"""Клиент GitLab: та же поверхность, что у `github_client`.

Имена и сигнатуры повторяют GitHub-клиент намеренно — activities не должны
знать, с каким провайдером работают. Различие живёт здесь.

Чего у GitLab нет и как это восполняется:

* **Аналога GitHub App.** Токен статический, из окружения. Короткоживущих
  installation-токенов не существует ни в одном документированном механизме.
* **Timeline API с событием `cross-referenced`.** Связь задачи и MR
  пересобирается из `related_merge_requests`, `closed_by` и системных нот.
* **Сущности Review с состояниями.** У GitLab это approvals (бинарно) и
  заметки (текст) — два независимых механизма.
* **Поля `user.type`.** Ботов различаем по логину сервисного аккаунта.
* **`workflow_dispatch`.** Не реализуется: решением дизайна стадия разработки
  для GitLab идёт локальным раннером.

Пути проекта URL-кодируются целиком, включая слэши: у GitLab проект может
лежать во вложенной подгруппе, и `group/sub/project` в пути API — это
`group%2Fsub%2Fproject`.
"""
from __future__ import annotations

import logging
import os
import subprocess
import urllib.parse

import requests

import worktree

from shared.agent_comment import is_agent_comment, sign

_log = logging.getLogger("gitlab_client")

BASE = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/") + "/api/v4"
TIMEOUT = 30


def _dry_run() -> bool:
    return bool(os.environ.get("DRY_RUN"))


def _token() -> str:
    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITLAB_TOKEN не задан")
    return token


def _headers() -> dict:
    # PRIVATE-TOKEN — рекомендуемый способ для PAT, Project и Group Access
    # Token. Bearer тоже работает, но у него другая семантика для OAuth.
    return {"PRIVATE-TOKEN": _token()}


def bot_login() -> str:
    return os.environ.get("GITLAB_BOT_LOGIN", "").strip()


def _seg(repo: str) -> str:
    """Сегмент проекта в пути API.

    Числовой id, если дали его, иначе путь, закодированный целиком. Без
    кодирования слэшей запрос к проекту в подгруппе уходит не туда — и это
    именно тот класс ошибки, из-за которого repo нигде не кодировался в
    GitHub-клиенте: там кодировать было нечего.
    """
    repo = str(repo).strip().strip("/")
    return repo if repo.isdigit() else urllib.parse.quote(repo, safe="")


def _url(repo: str, path: str) -> str:
    return f"{BASE}/projects/{_seg(repo)}{path}"


def _request(method: str, url: str, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("headers", _headers())
    resp = requests.request(method, url, **kwargs)
    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After") or resp.headers.get("RateLimit-Reset") or "?"
        raise RuntimeError(f"429 от GitLab, Retry-After={retry}")
    return resp


def _ok(resp, *, allow=()):
    if resp.status_code in allow:
        return resp
    resp.raise_for_status()
    return resp


# --- комментарии ---

def post_comment(repo: str, issue_number: int, body: str) -> None:
    """Комментарий сервиса — всегда подписанный.

    Подпись ставится здесь, в единственной точке отправки: без неё вебхук
    примет собственный комментарий за реплику человека. У GitLab это ещё
    важнее, чем у GitHub, — поля `user.type` нет, и маркер остаётся основным
    признаком происхождения.
    """
    body = sign(body)
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    _ok(_request("POST", _url(repo, f"/issues/{issue_number}/notes"),
                 data={"body": body}))


def list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:
    """Комментарии задачи во внутренней форме.

    `activity_filter=only_comments` отсекает системные заметки: смена меток и
    статуса приезжают такими же нотами, и без фильтра они попали бы в тред как
    реплики.
    """
    resp = _ok(_request("GET", _url(repo, f"/issues/{issue_number}/notes"),
                        params={"per_page": min(limit, 100),
                                "sort": "asc", "activity_filter": "only_comments"}))
    out = []
    for note in resp.json()[:limit]:
        author = note.get("author") or {}
        login = author.get("username") or ""
        out.append({
            "id": note.get("id"),
            "body": note.get("body") or "",
            "user": {
                "login": login,
                # У GitLab признака бота нет — выводим из логина сервисного
                # аккаунта, чтобы форма совпала с GitHub.
                "type": "Bot" if bot_login() and login == bot_login() else "User",
            },
            "created_at": note.get("created_at"),
        })
    return out


def add_reaction(repo: str, comment_id: int, content: str = "eyes",
                 issue_number: int | None = None) -> None:
    """Реакция на комментарий.

    У GitHub реакция адресуется одним `comment_id`. GitLab требует в пути ещё и
    номер задачи, поэтому он здесь обязателен по факту, хотя в сигнатуре стоит
    последним ради совпадения с GitHub-клиентом.

    Имена emoji расходятся: `eyes` и `confused` есть у обоих, а `+1`, `-1` и
    `hooray` у GitLab отсутствуют.
    """
    if issue_number is None:
        raise ValueError("GitLab требует номер задачи для реакции на комментарий")
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s %s#%s/%s", content, repo, issue_number, comment_id)
        return
    name = {"+1": "thumbsup", "-1": "thumbsdown", "hooray": "tada"}.get(content, content)
    resp = _request("POST", _url(repo, f"/issues/{issue_number}/notes/{comment_id}/award_emoji"),
                    data={"name": name})
    # Повторная реакция — не ошибка: доставка могла продублироваться.
    _ok(resp, allow=(404, 409))


# --- метки ---

def set_labels(repo: str, issue_number: int, *, add=(), remove=()) -> None:
    """Смена набора меток одним запросом.

    Здесь GitLab лучше GitHub: `add_labels` и `remove_labels` инкрементальны и
    безопасны для гонок, тогда как у GitHub это POST плюс серия DELETE с окном
    между ними. Параметр `labels` не используется намеренно — он заменяет весь
    набор целиком и затёр бы метки, поставленные человеком.
    """
    add = [l for l in add if l]
    keep = set(add)
    remove = [l for l in remove if l and l not in keep]
    if not add and not remove:
        return
    if _dry_run():
        _log.info("[DRY_RUN] labels %s#%s += %s -= %s", repo, issue_number, add, remove)
        return
    data = {}
    if add:
        data["add_labels"] = ",".join(add)
    if remove:
        data["remove_labels"] = ",".join(remove)
    _ok(_request("PUT", _url(repo, f"/issues/{issue_number}"), data=data))


def add_label(repo: str, issue_number: int, label: str) -> None:
    set_labels(repo, issue_number, add=[label])


def remove_label(repo: str, issue_number: int, label: str) -> None:
    set_labels(repo, issue_number, remove=[label])


def ensure_labels_exist(repo: str, specs) -> int:
    """Заводит недостающие метки проекта. Возвращает число созданных.

    GitLab, как и GitHub, создаёт метку сам при первом применении — проверено
    на живом проекте. Явное заведение нужно ради цветов и описаний и как защита
    от опечаток: неверное имя иначе оседает новой серой меткой вместо ошибки.
    """
    if _dry_run():
        _log.info("[DRY_RUN] ensure labels %s: %s", repo, [s.name for s in specs])
        return 0
    existing, page = set(), 1
    while True:
        resp = _ok(_request("GET", _url(repo, "/labels"),
                            params={"per_page": 100, "page": page}))
        chunk = resp.json()
        existing.update(item["name"] for item in chunk)
        if len(chunk) < 100:
            break
        page += 1

    created = 0
    for spec in specs:
        if spec.name in existing:
            continue
        resp = _request("POST", _url(repo, "/labels"), data={
            "name": spec.name, "color": spec.color, "description": spec.description})
        if resp.status_code == 409:
            continue  # завелась параллельно
        _ok(resp)
        created += 1
    return created


# --- задачи ---

def get_issue(repo: str, issue_number: int) -> dict:
    resp = _ok(_request("GET", _url(repo, f"/issues/{issue_number}")))
    raw = resp.json()
    author = raw.get("author") or {}
    return {
        "number": raw.get("iid"),
        "title": raw.get("title") or "",
        "body": raw.get("description") or "",
        "state": "closed" if raw.get("state") == "closed" else "open",
        "labels": [{"name": n} for n in (raw.get("labels") or [])],
        "user": {"login": author.get("username") or "", "type": "User"},
        "html_url": raw.get("web_url"),
    }


def get_issue_body(repo: str, issue_number: int) -> str:
    return get_issue(repo, issue_number)["body"]


def update_issue_body(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] update body %s#%s", repo, issue_number)
        return
    _ok(_request("PUT", _url(repo, f"/issues/{issue_number}"), data={"description": body}))


def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:
    if _dry_run():
        _log.info("[DRY_RUN] create issue %s: %s", repo, title)
        return 0
    data = {"title": title, "description": body}
    if labels:
        data["labels"] = ",".join(labels)
    resp = _ok(_request("POST", _url(repo, "/issues"), data=data))
    return resp.json()["iid"]


def close_issue(repo: str, issue_number: int) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] close %s#%s", repo, issue_number)
        return
    _ok(_request("PUT", _url(repo, f"/issues/{issue_number}"), data={"state_event": "close"}))


def list_open_issues(repo: str) -> list[dict]:
    resp = _ok(_request("GET", _url(repo, "/issues"),
                        params={"state": "opened", "per_page": 100}))
    return [{"number": i.get("iid"), "title": i.get("title") or "",
             "body": i.get("description") or "",
             "labels": [{"name": n} for n in (i.get("labels") or [])]}
            for i in resp.json()]


def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:
    """Кандидаты в дубликаты — задачи И merge request'ы.

    Ищутся оба вида, как у GitHub-клиента, и каждый помечается `_kind`.
    Потребитель (`activities.duplicate_check`) строит по этому полю листинг для
    модели, и его отсутствие роняет активность — расхождение формы между
    клиентами обходится дороже, чем недостающая операция: недостающая падает
    сразу и внятно, а разошедшаяся форма падает позже и в чужом коде.

    Basic search доступен на бесплатном тарифе; Advanced Search, то есть поиск
    по коду и комментариям, требует Premium — но для дубликата хватает
    заголовка и описания.
    """
    out: list[dict] = []
    for kind, path in (("issue", "/issues"), ("pr", "/merge_requests")):
        resp = _request("GET", _url(repo, path),
                        params={"search": query, "in": "title,description",
                                "per_page": min(limit, 100)})
        if not resp.ok:
            # Один вид не нашёлся — не повод терять второй.
            _log.warning("поиск %s в %s не удался: %s", kind, repo, resp.status_code)
            continue
        for item in resp.json():
            out.append({
                "number": item.get("iid"),
                "title": item.get("title") or "",
                "body": item.get("description") or "",
                "state": item.get("state"),
                "url": item.get("web_url"),
                "labels": [{"name": n} for n in (item.get("labels") or [])],
                "_kind": kind,
            })
    return out[:limit]


# --- ветки и файлы ---

def _default_branch(repo: str) -> str:
    resp = _ok(_request("GET", f"{BASE}/projects/{_seg(repo)}"))
    return resp.json().get("default_branch") or "main"


def branch_exists(repo: str, branch: str) -> bool:
    resp = _request("GET", _url(repo, f"/repository/branches/{urllib.parse.quote(branch, safe='')}"))
    if resp.status_code == 404:
        return False
    _ok(resp)
    return True


def ensure_branch(repo: str, branch: str, base: str | None = None) -> None:
    if branch_exists(repo, branch):
        return
    if _dry_run():
        _log.info("[DRY_RUN] branch %s:%s", repo, branch)
        return
    _ok(_request("POST", _url(repo, "/repository/branches"),
                 data={"branch": branch, "ref": base or _default_branch(repo)}))


def get_file(repo: str, path: str, ref: str) -> str | None:
    """Содержимое файла или None, если его нет."""
    quoted = urllib.parse.quote(path, safe="")
    resp = _request("GET", _url(repo, f"/repository/files/{quoted}/raw"),
                    params={"ref": ref})
    if resp.status_code == 404:
        return None
    _ok(resp)
    return resp.text


def put_file(repo: str, path: str, content: str, *, branch: str, message: str) -> None:
    """Запись файла.

    Здесь семантика расходится с GitHub принципиально. `PUT /contents` у GitHub
    и создаёт, и обновляет. GitLab разделяет: `POST` создать, `PUT` обновить —
    и вызывающему приходится знать, существует ли файл. Узнаём запросом, а не
    угадыванием по коду ответа: 400 у GitLab означает и «уже есть», и «нет
    такой ветки», и разбирать это по тексту ошибки ненадёжно.
    """
    if _dry_run():
        _log.info("[DRY_RUN] put file %s:%s@%s", repo, path, branch)
        return
    quoted = urllib.parse.quote(path, safe="")
    exists = get_file(repo, path, branch) is not None
    method = "PUT" if exists else "POST"
    _ok(_request(method, _url(repo, f"/repository/files/{quoted}"),
                 data={"branch": branch, "content": content, "commit_message": message}))


def push_artifacts_to_branch(repo: str, branch: str, files: dict, message: str) -> None:
    for path, content in files.items():
        put_file(repo, path, content, branch=branch, message=message)


# --- merge request ---

def _mr(raw: dict) -> dict:
    return {
        "number": raw.get("iid"),
        "title": raw.get("title") or "",
        "body": raw.get("description") or "",
        "state": raw.get("state"),
        "html_url": raw.get("web_url"),
        "head": {"ref": raw.get("source_branch")},
        "base": {"ref": raw.get("target_branch")},
        "draft": bool(raw.get("draft")),
    }


def get_pull(repo: str, number: int) -> dict:
    return _mr(_ok(_request("GET", _url(repo, f"/merge_requests/{number}"))).json())


def find_change_request(repo: str, source_branch: str) -> dict | None:
    resp = _ok(_request("GET", _url(repo, "/merge_requests"),
                        params={"source_branch": source_branch, "state": "opened"}))
    rows = resp.json()
    return _mr(rows[0]) if rows else None


def open_change_request(repo: str, *, source: str, target: str | None = None,
                        title: str, body: str) -> dict:
    """Открывает MR либо возвращает уже существующий.

    Проверка «уже есть» идёт запросом ДО создания, а не ловлей ошибки: ни код
    409, ни текст ответа при дубликате MR в документации GitLab не описаны, и
    строить на них контракт нельзя.
    """
    existing = find_change_request(repo, source)
    if existing:
        return existing
    if _dry_run():
        _log.info("[DRY_RUN] MR %s: %s -> %s", repo, source, target)
        return {"number": 0, "head": {"ref": source}}
    resp = _ok(_request("POST", _url(repo, "/merge_requests"), data={
        "source_branch": source, "target_branch": target or _default_branch(repo),
        "title": title, "description": body, "remove_source_branch": True}))
    return _mr(resp.json())


def blob_base(repo: str, branch: str) -> str:
    """Префикс ссылки на файл в ветке — для комментариев в Issue.

    У GitLab между проектом и `blob` стоит `/-/`: без него адрес неотличим от
    пути к подгруппе и отдаёт 404.
    """
    host = BASE.rsplit("/api/v4", 1)[0]
    return f"{host}/{str(repo).strip('/')}/-/blob/{branch}"


def publish_worktree(repo: str, clone_dir: str, branch: str, *,
                     title: str, body: str, message: str,
                     ignore_for_empty_check: tuple[str, ...] = (),
                     force_include: tuple[str, ...] = (),
                     draft: bool = False) -> int | None:
    """Коммит рабочего дерева в ветку и MR. None — изменений нет.

    Парная к `github_client.publish_worktree`: git-механика у них общая
    (`worker/worktree.py`), различаются только имя пользователя для
    credential-хелпера (`oauth2` против `x-access-token`), почта коммиттера и
    то, чем открывается запрос на изменения.

    Существует потому, что диспетчер `forge` резолвит метод по репозиторию, и
    без этой функции стадия разработки на GitLab-репозитории падала
    `NotImplementedError: gitlab-клиент не умеет «publish_worktree»` — то есть
    громко и честно, но до MR не доходила вовсе.

    Черновик у GitLab задаётся ПРЕФИКСОМ заголовка, а не полем запроса: поля
    `draft` у POST /merge_requests нет, и `Draft:` — единственный
    задокументированный способ. Префикс не дублируется, если заголовок его уже
    несёт: повторный прогон сорванной разработки иначе накапливал бы
    `Draft: Draft: …`.
    """
    if _dry_run():
        _log.info("[DRY_RUN] publish %s -> %s: %s", clone_dir, branch, title)
        return None

    if not worktree.commit_and_push(
            repo, clone_dir, branch, message=message,
            credentials=git_credentials(repo),
            committer_email="openhands-agent@users.noreply.gitlab.com",
            ignore_for_empty_check=ignore_for_empty_check,
            force_include=force_include):
        return None

    if draft and not title.lstrip().lower().startswith("draft:"):
        title = f"Draft: {title}"

    # Повторный прогон по той же ветке не плодит второй MR: `open_change_request`
    # сначала ищет существующий и возвращает его (`find_change_request`).
    return open_change_request(repo, source=branch, title=title, body=body)["number"]


def list_linked_prs(repo: str, issue_number: int) -> list[dict]:
    """MR, связанные с задачей.

    Аналога Timeline API с событием `cross-referenced` у GitLab нет. Граф
    собирается из двух источников: `related_merge_requests` (упоминания) и
    `closed_by` (закрывающие ключевые слова). Дубли снимаются по номеру.
    """
    found: dict[int, dict] = {}
    for path in ("/related_merge_requests", "/closed_by"):
        resp = _request("GET", _url(repo, f"/issues/{issue_number}{path}"))
        if resp.status_code == 404:
            continue
        _ok(resp)
        for raw in resp.json():
            mr = _mr(raw)
            if mr["number"] is not None:
                found[mr["number"]] = mr
    return [found[k] for k in sorted(found)]


def review_text(repo: str, number: int, limit: int = 12000) -> str:
    """Замечания ревью одним текстом.

    У GitLab нет сущности Review с состояниями — есть заметки и approvals,
    два независимых механизма. Берём заметки, кроме системных и кроме своих
    собственных.

    Отбор идёт по МАРКЕРУ, а не по признаку бота. У GitHub-клиента здесь стоит
    обратный фильтр `type != "Bot" -> continue`, потому что ревью пишет контур,
    и он ходит как App. На GitLab поля `type` нет вовсе: тот же фильтр стал бы
    истинным всегда и молча вернул бы пустоту.
    """
    resp = _ok(_request("GET", _url(repo, f"/merge_requests/{number}/notes"),
                        params={"per_page": 100, "sort": "asc"}))
    parts = []
    for note in resp.json():
        if note.get("system"):
            continue
        body = (note.get("body") or "").strip()
        if not body or is_agent_comment(body):
            continue
        pos = note.get("position") or {}
        where = pos.get("new_path")
        line = pos.get("new_line")
        parts.append(f"### {where}:{line}\n{body}" if where else body)
    text = "\n\n".join(parts)
    return text[-limit:] if len(text) > limit else text


# --- git ---

def auth_token(repo: str = "") -> str:
    return _token()


def git_username(repo: str = "") -> str:
    """Имя пользователя для credential helper. Парная к `github_client`.

    Отдельно от токена: имя — константа провайдера, добывается без обращения
    к настройкам, а `_token()` без `GITLAB_TOKEN` бросает.
    """
    return "oauth2"


def git_credentials(repo: str = "") -> tuple[str, str]:
    """Пара для credential helper.

    Имя пользователя у GitLab не проверяется для PAT, Project и Group Access
    Token — документация прямо говорит «any non-blank value». Берём `oauth2`:
    он совместим со всеми перечисленными типами и встречается в примерах самой документации.
    Единственный обязательный литерал — `gitlab-ci-token`, и он нам не нужен.
    """
    return git_username(repo), _token()


def clone_url(repo: str) -> str:
    host = BASE.rsplit("/api/v4", 1)[0]
    return f"{host}/{str(repo).strip('/')}.git"


def dispatch_workflow(*args, **kwargs):
    """Не реализуется намеренно.

    Решением дизайна стадия разработки для GitLab идёт локальным
    docker-раннером: так не нужен runner у заказчика, LLM-ключ в его
    CI-переменных и отдельное согласование безопасности.
    """
    raise NotImplementedError(
        "запуск пайплайна GitLab не реализуется — стадия разработки идёт локальным раннером")
