"""
Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила
на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис
аутентифицируется как GitHub App — токен инсталляции нужно генерировать
и обновлять самостоятельно (живёт ~1 час).
"""

import base64
import logging
import os
import subprocess
import threading
import time
import urllib.parse
from collections.abc import Sequence

import jwt
import requests

from shared.agent_comment import is_agent_comment, sign
from shared.labels import ORIGIN_AGENT

_log = logging.getLogger("github_client")


def _dry_run() -> bool:
    return bool(os.environ.get("DRY_RUN"))


# Installation-токен кэшируется ПО РЕПОЗИТОРИЮ: у App может быть несколько
# установок (разные орг/аккаунты), у каждой — свой токен. Lock сериализует
# выпуск, чтобы конкурентный промах не породил дубли обменов и не бил по
# rate-limit GitHub.
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def _app_private_key() -> bytes:
    """Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла
    GITHUB_PRIVATE_KEY_PATH (обратная совместимость)."""
    b64 = os.environ.get("GITHUB_PRIVATE_KEY_B64")
    if b64:
        return base64.b64decode(b64)
    with open(os.environ["GITHUB_PRIVATE_KEY_PATH"], "rb") as f:
        return f.read()


def _app_jwt() -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": os.environ["GITHUB_APP_ID"]}
    return jwt.encode(payload, _app_private_key(), algorithm="RS256")


def _cached_token(repo: str) -> str | None:
    cached = _token_cache.get(repo)  # dict.get атомарен под GIL
    if cached and cached[1] - 60 > time.time():
        return cached[0]
    return None


def _installation_token_for(repo: str) -> str:
    """Installation-токен под установку App на данный репозиторий. Установка
    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →
    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.

    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому
    cache-hit по одному репо не блокируется за token-обменом другого. Lock
    сериализует только сам обмен (редкий — раз в ~55 мин на репо)."""
    hot = _cached_token(repo)
    if hot is not None:
        return hot
    with _token_lock:
        warm = _cached_token(repo)  # перепроверка под lock: конкурент мог уже выпустить
        if warm is not None:
            return warm
        app_headers = {"Authorization": f"Bearer {_app_jwt()}",
                       "Accept": "application/vnd.github+json"}
        inst = requests.get(
            f"https://api.github.com/repos/{repo}/installation",
            headers=app_headers, timeout=30)
        inst.raise_for_status()
        installation_id = inst.json()["id"]
        resp = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=app_headers, timeout=30)
        resp.raise_for_status()
        token = resp.json()["token"]
        _token_cache[repo] = (token, time.time() + 55 * 60)  # реальный TTL ~1ч, с запасом
        return token


def _installation_token_headers(repo: str) -> dict:
    return {"Authorization": f"Bearer {_installation_token_for(repo)}",
            "Accept": "application/vnd.github+json"}


_pat_over_app_warned = False


def _warn_pat_over_app() -> None:
    """Один раз на процесс: PAT задан вместе с App и молча его отключает.

    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от
    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный
    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.
    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.
    """
    global _pat_over_app_warned
    if _pat_over_app_warned:
        return
    _pat_over_app_warned = True
    _log.warning(
        "GH_TOKEN/GITHUB_TOKEN задан одновременно с GITHUB_APP_ID: GitHub App НЕ "
        "используется, все действия идут от имени владельца токена. Убери PAT, "
        "если ожидаешь работу от приложения (см. scripts/diag.py)."
    )


def _auth_headers(repo: str) -> dict:
    """PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly
    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        if os.environ.get("GITHUB_APP_ID"):
            _warn_pat_over_app()
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return _installation_token_headers(repo)


def post_comment(repo: str, issue_number: int, body: str) -> None:
    """Комментарий сервиса — всегда подписанный.

    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,
    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш
    комментарий за ответ человека и накормит им цикл уточнений (см.
    shared/agent_comment.py).
    """
    body = sign(body)
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=_auth_headers(repo), json={"body": body}, timeout=30)
    resp.raise_for_status()


def _post_labels(repo: str, issue_number: int, labels: list[str]) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    resp = requests.post(url, headers=_auth_headers(repo), json={"labels": labels}, timeout=30)
    resp.raise_for_status()


def add_label(repo: str, issue_number: int, label: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] label %s#%s += %s", repo, issue_number, label)
        return
    _post_labels(repo, issue_number, [label])


def remove_label(repo: str, issue_number: int, label: str) -> None:
    """Снимает метку. Отсутствующая метка (404) — штатная ситуация, а не ошибка:
    финализация зовётся и после прогона, запущенного командой в комментарии, где
    метки `run:*` никто не ставил, и после того, как человек снял её руками.

    Имя метки уходит в путь URL, поэтому кодируется: в схеме `run:analyze` есть
    двоеточие, а в метках вида `advisor:feature-request` — ещё и дефисы.
    """
    if _dry_run():
        _log.info("[DRY_RUN] label %s#%s -= %s", repo, issue_number, label)
        return
    quoted = urllib.parse.quote(label, safe="")
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels/{quoted}"
    resp = requests.delete(url, headers=_auth_headers(repo), timeout=30)
    if resp.status_code == 404:
        return
    resp.raise_for_status()


def set_labels(repo: str, issue_number: int, *,
               add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Приводит набор меток к нужному виду одной операцией.

    Порядок намеренный: сначала ставим целевые, потом снимаем лишние. При
    обратном порядке между двумя запросами есть окно, в котором меток `phase:*`
    нет вовсе — `lifecycle.phase_from_labels` вернёт None, и Issue будет
    выглядеть как не входивший в жизненный цикл. Две метки в том же окне
    противоречивы, но видны и восстановимы.

    Снятие выполняется В ЛЮБОМ СЛУЧАЕ — даже если постановка упала. Раньше
    сбой POST обрывал функцию до снятия, и 5xx на постановке итоговой метки
    оставлял `run:analyze` на Issue навсегда: выборка «прогон идёт» показывала
    завершённый прогон, а activity тем временем рапортовала успех. Постановка
    и снятие всё равно различаются по строгости, и это не случайность.
    Непоставленная метка — потерянное состояние, поэтому её ошибка
    поднимается — но только ПОСЛЕ того, как снятие отработало. Неснятая —
    мусор в выборке, из-за которого не стоит ронять прогон; она уходит в лог,
    как это делал `set_phase`.

    У второго провайдера операция схлопывается в один запрос: GitLab
    обновляет метки одним `PUT` с `add_labels` / `remove_labels`. Здесь она
    описана одним местом ровно для того, чтобы драйверу было что реализовать.
    """
    add = [label for label in add if label]
    keep = set(add)
    remove = [label for label in remove if label and label not in keep]
    if not add and not remove:
        return
    if _dry_run():
        _log.info("[DRY_RUN] labels %s#%s += %s -= %s", repo, issue_number, add, remove)
        return
    add_error: Exception | None = None
    if add:
        try:
            _post_labels(repo, issue_number, add)
        except Exception as exc:
            add_error = exc
    for label in remove:
        try:
            remove_label(repo, issue_number, label)
        except Exception as exc:
            _log.warning("не снял метку %s с %s#%s: %s", label, repo, issue_number, exc)
    if add_error is not None:
        raise add_error


def ensure_labels_exist(repo: str, specs) -> int:
    """Заводит недостающие метки. Возвращает число созданных.

    Трекеры создают метку сами при первом применении — и GitHub, и GitLab
    (проверено 2026-08-21). Проблема не в отказе, а в тишине: опечатка в имени
    оседает новой меткой вместо ошибки, и выборка тихо перестаёт находить то,
    что искала. Явное заведение делает набор конечным и заодно даёт цвета.

    Идемпотентна: существующая метка не трогается, цвет ей не переписывается —
    человек мог поправить его руками, и спорить с ним незачем.
    """
    if _dry_run():
        _log.info("[DRY_RUN] ensure labels %s: %s", repo, [s.name for s in specs])
        return 0
    url = f"https://api.github.com/repos/{repo}/labels"
    existing: set[str] = set()
    page = 1
    while True:
        resp = requests.get(url, headers=_auth_headers(repo),
                            params={"per_page": 100, "page": page}, timeout=30)
        resp.raise_for_status()
        chunk = resp.json()
        existing.update(item["name"] for item in chunk)
        if len(chunk) < 100:
            break
        page += 1

    created = 0
    for spec in specs:
        if spec.name in existing:
            continue
        resp = requests.post(url, headers=_auth_headers(repo), timeout=30, json={
            "name": spec.name,
            "color": spec.color.lstrip("#"),
            "description": spec.description,
        })
        if resp.status_code == 422:
            continue  # завелась параллельно — не наша забота
        resp.raise_for_status()
        created += 1
    return created


def create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:
    """Создаёт Issue и возвращает его номер.

    Нужно живому E2E: проверка контура начинается с появления задачи, а
    подкладывать её руками — значит проверять не тот путь. В обычном пайплайне
    сервис Issue не создаёт (их заводит человек либо PR-Closer).
    """
    if _dry_run():
        _log.info("[DRY_RUN] create issue %s: %s", repo, title)
        return 0
    url = f"https://api.github.com/repos/{repo}/issues"
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    resp = requests.post(url, headers=_auth_headers(repo), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["number"]


def issue_node_id(repo: str, issue_number: int) -> int:
    """Внутренний id задачи. Привязка под-задач идёт по нему, а не по номеру."""
    return int(get_issue(repo, issue_number)["id"])


def link_sub_issue(repo: str, parent: int, child_id: int) -> None:
    """Привязать задачу к родителю нативной связью GitHub.

    `child_id` — внутренний id (см. `issue_node_id`), НЕ номер. Передача номера
    даёт 422 с невнятным телом, и отличить её от прочих отказов трудно.

    Холостой режим (`DRY_RUN`): сетевой вызов не выполняется, связь не создаётся.
    """
    if _dry_run():
        _log.info("[DRY_RUN] link sub_issue %s#%s -> %d", repo, parent, child_id)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{parent}/sub_issues"
    resp = requests.post(url, headers=_auth_headers(repo), json={"sub_issue_id": child_id}, timeout=30)
    resp.raise_for_status()


def list_sub_issues(repo: str, parent: int) -> list[dict]:
    """Под-задачи родителя.

    Холостой режим не влияет на читающие функции: DRY_RUN защищает от мутаций,
    а не от чтения. Без доступа к контексту прогон в DRY_RUN не показал бы,
    что именно система собралась сделать.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{parent}/sub_issues"
    resp = requests.get(url, headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json()


def close_issue(repo: str, issue_number: int) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] close %s#%s", repo, issue_number)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.patch(url, headers=_auth_headers(repo), json={"state": "closed"}, timeout=30)
    resp.raise_for_status()


def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:
    """Через gh CLI — тот же паттерн, что и в версии на Actions, но токен
    для gh нужно прокинуть через переменную окружения перед вызовом."""
    env = {**os.environ, "GH_TOKEN": auth_token(repo)}
    candidates = []
    for kind in ("issue", "pr"):
        fields = "number,title,body,url,state,labels" if kind == "issue" else "number,title,body,url,state"
        cmd = ["gh", kind, "list", "--repo", repo, "--state", "all", "--search", query, "--limit", str(limit), "--json", fields]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            continue
        import json
        for item in json.loads(result.stdout or "[]"):
            item["_kind"] = kind
            candidates.append(item)
    return candidates[:limit]


def branch_exists(repo: str, branch: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/branches/{branch}"
    resp = requests.get(url, headers=_auth_headers(repo), timeout=30)
    return resp.status_code == 200


def auth_token(repo: str) -> str:
    """Голый токен для внешних процессов (git clone, gh CLI).

    Токен per-repo: под GitHub App у каждой установки своя пара, поэтому
    репозиторий обязателен. PAT-путь всё равно вернёт один и тот же токен."""
    return _auth_headers(repo)["Authorization"].split(" ", 1)[1]


def add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None:
    """Реакция на комментарий — видимое «команда принята» до тяжёлой работы.
    GitHub отвечает 200 на уже поставленную реакцию, повторный вызов безвреден."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s comment %s: %s", repo, comment_id, content)
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"
    resp = requests.post(url, headers=_auth_headers(repo), json={"content": content}, timeout=30)
    resp.raise_for_status()


def ensure_branch(repo: str, branch: str) -> None:
    """Создаёт ветку от дефолтной, если её ещё нет."""
    if _dry_run():
        _log.info("[DRY_RUN] create branch %s in %s", branch, repo)
        return
    if branch_exists(repo, branch):
        return
    meta = requests.get(f"https://api.github.com/repos/{repo}", headers=_auth_headers(repo), timeout=30)
    meta.raise_for_status()
    base = meta.json()["default_branch"]

    ref = requests.get(
        f"https://api.github.com/repos/{repo}/git/ref/heads/{base}",
        headers=_auth_headers(repo), timeout=30,
    )
    ref.raise_for_status()
    sha = ref.json()["object"]["sha"]

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=_auth_headers(repo),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=30,
    )
    resp.raise_for_status()


def put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:
    """Создаёт или обновляет файл в ветке через Contents API.

    Contents API, а не `git push`: клон делается shallow (--depth 1), а push из
    такого клона GitHub может отклонить. Здесь ремоут вообще не нужен.
    """
    if _dry_run():
        _log.info("[DRY_RUN] put file %s in %s:%s", path, repo, branch)
        return
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    existing = requests.get(url, headers=_auth_headers(repo), params={"ref": branch}, timeout=30)
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]  # перезапись требует sha текущей версии

    resp = requests.put(url, headers=_auth_headers(repo), json=payload, timeout=30)
    resp.raise_for_status()


def push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:
    """Публикует артефакты (путь -> содержимое) в ветку одним проходом."""
    if _dry_run():
        _log.info("[DRY_RUN] push %s files to %s#%s: %s",
                  len(files), repo, branch, sorted(files))
        return
    ensure_branch(repo, branch)
    for path, content in files.items():
        put_file(repo, branch, path, content, message)


def get_issue(repo: str, issue_number: int) -> dict:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.get(
        url, headers=_auth_headers(repo), params={"per_page": min(limit, 100)}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()[:limit]


def list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:
    """PR, кросс-ссылающиеся на issue (Timeline API).

    Трекинг-issue связан с PR событиями cross-referenced; тело issue их не
    содержит. Оставляем только ссылки на PR (source.issue с ключом
    pull_request), не на другие issue, и убираем дубли.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/timeline"
    resp = requests.get(
        url,
        headers={**_auth_headers(repo),
                 "Accept": "application/vnd.github.mockingbird-preview+json"},
        params={"per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    seen: set[int] = set()
    prs: list[dict] = []
    for event in resp.json():
        if event.get("event") != "cross-referenced":
            continue
        src = (event.get("source") or {}).get("issue") or {}
        if "pull_request" not in src:
            continue
        number = src.get("number")
        if number is None or number in seen:
            continue
        seen.add(number)
        prs.append({
            "number": number,
            "title": src.get("title", ""),
            "state": src.get("state", ""),
            "url": src.get("html_url", ""),
        })
        if len(prs) >= limit:
            break
    return prs


def get_file(repo: str, path: str, ref: str) -> str | None:
    """Содержимое файла из ветки. None — файла нет; для артефактов это
    штатная ситуация, а не ошибка."""
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers={**_auth_headers(repo), "Accept": "application/vnd.github.raw"},
        params={"ref": ref},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def create_pr_with_files(repo: str, branch: str, base: str,
                         files: dict, title: str, body: str):
    if _dry_run():
        _log.info("[DRY_RUN] PR %s <- %s: %d files, title=%s",
                  repo, branch, len(files), title)
        return None
    h = _auth_headers(repo)
    api = f"https://api.github.com/repos/{repo}"
    base_resp = requests.get(f"{api}/git/refs/heads/{base}", headers=h, timeout=30)
    base_resp.raise_for_status()
    base_sha = base_resp.json()["object"]["sha"]
    requests.post(f"{api}/git/refs", headers=h,
                  json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                  timeout=30).raise_for_status()
    for path, content in files.items():
        requests.put(f"{api}/contents/{path}", headers=h, json={
            "message": f"consolidation: {path}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }, timeout=30).raise_for_status()
    resp = requests.post(f"{api}/pulls", headers=h,
                         json={"title": title, "head": branch, "base": base,
                               "body": body}, timeout=30)
    resp.raise_for_status()
    pr = resp.json()
    # R6 протокола: артефакт, созданный агентом, помечается провенансом. PR
    # консолидации — единственное, что этот сервис создаёт сам, и без метки
    # агенты не отличают его от работы человека. Best-effort: PR уже создан, и
    # сбой пометки не должен превратить успешный прогон в ошибку.
    try:
        add_label(repo, pr["number"], ORIGIN_AGENT)
    except Exception as exc:
        _log.warning("PR %s создан, но не помечен %s: %s", pr["number"], ORIGIN_AGENT, exc)
    return pr["html_url"]


def list_open_issues(repo: str, limit: int = 300) -> list:
    import json
    env = {**os.environ, "GH_TOKEN": _auth_headers(repo)["Authorization"].split(" ")[1]}
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--limit", str(limit), "--json", "number,title,body,labels"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    # Do NOT swallow a gh failure: an empty stdout would silently become an empty
    # backlog, and consolidation would open a PR that consolidates nothing.
    if result.returncode != 0:
        raise RuntimeError(
            f"gh issue list failed for {repo} (exit {result.returncode}): "
            f"{result.stderr.strip()[:300]}")
    out = []
    for it in json.loads(result.stdout or "[]"):
        it["labels"] = [l["name"] for l in it.get("labels", [])]
        out.append(it)
    return out


def get_issue_body(repo: str, issue_number: int) -> str:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json().get("body") or ""


def dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:
    """Запускает workflow репозитория-цели через `workflow_dispatch`.

    Отсутствующий файл workflow, ветка без него и отключённые Actions — всё это
    GitHub возвращает как 404/422, и все три означают одно: прогон НЕ начался.
    Поднимаем ошибку с текстом ответа, а не глотаем: цикл на ней уходит в
    `failed`, и человек видит причину, вместо Issue, который «уехал в
    разработку» и там растворился.
    """
    if _dry_run():
        _log.info("[DRY_RUN] dispatch %s %s@%s inputs=%s", repo, workflow_file, ref, inputs)
        return
    quoted = urllib.parse.quote(workflow_file, safe="")
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{quoted}/dispatches"
    resp = requests.post(url, headers=_auth_headers(repo),
                         json={"ref": ref, "inputs": inputs}, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"workflow_dispatch {workflow_file}@{ref} в {repo} не принят "
            f"({resp.status_code}): {resp.text.strip()[:300]}")


class GitCommandError(RuntimeError):
    """Отказ git с сохранённой причиной.

    `subprocess.run(check=True)` бросает `CalledProcessError`, чей текст — только
    команда и код возврата: stderr остаётся в проглоченном `capture_output`. На
    живом прогоне #39 это дало три одинаковых «returned non-zero exit status 1»
    в истории Temporal и ни слова о том, ЧТО отверг GitHub.
    """


def _git_runner(clone_dir: str, env: dict):
    """git по рабочему дереву задачи, с видимой причиной отказа.

    Токен живёт в окружении (`GH_PUSH_TOKEN`), а не в argv, и в stderr git его
    не печатает — но текст ошибки уезжает в историю Temporal и в комментарий
    Issue, поэтому подстраховка стоит дешевле разбирательства.
    """
    token = env.get("GH_PUSH_TOKEN") or ""

    def git(*args: str, check: bool = True):
        proc = subprocess.run(["git", "-C", clone_dir, *args], env=env,
                              capture_output=True, text=True, timeout=300)
        if check and proc.returncode:
            detail = (proc.stderr or proc.stdout or "").strip()[:800]
            if token:
                detail = detail.replace(token, "[Filtered]")
            raise GitCommandError(
                f"git {' '.join(args)} → код {proc.returncode}: {detail}")
        return proc

    return git


def publish_worktree(repo: str, clone_dir: str, branch: str, *,
                     title: str, body: str, message: str) -> int | None:
    """Коммит рабочего дерева в ветку и PR. None — изменений нет.

    Делает это ВОРКЕР, а не агент разработки: агенту токен не давали намеренно,
    он исполняет код чужого репозитория. Здесь токен уже нужен не агенту, а
    контуру — и живёт он ровно в этом процессе.

    Токен идёт через credential.helper в env, а не в URL: argv команды целиком
    попадает в текст CalledProcessError, и вклеенный токен уехал бы в историю
    Temporal при первом же сбое пуша.
    """
    if _dry_run():
        _log.info("[DRY_RUN] publish %s -> %s: %s", clone_dir, branch, title)
        return None

    token = auth_token(repo)
    env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "4",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f",
        "GIT_CONFIG_KEY_1": "user.name",
        "GIT_CONFIG_VALUE_1": "openhands-agent",
        "GIT_CONFIG_KEY_2": "user.email",
        "GIT_CONFIG_VALUE_2": "openhands-agent@users.noreply.github.com",
        # Каталог задачи передан раннеру (uid 10001), а коммит и пуш делает воркер
        # от root. Git на такое отвечает `fatal: detected dubious ownership` и
        # отказывается работать — готовая работа агента не доехала бы до PR.
        # Объявляем каталог доверенным для этой команды, не трогая общий конфиг.
        "GIT_CONFIG_KEY_3": "safe.directory",
        "GIT_CONFIG_VALUE_3": clone_dir,
        "GH_PUSH_TOKEN": token,
    }

    git = _git_runner(clone_dir, env)

    # ДО checkout: ветка уже существует ЛОКАЛЬНО только если по этому же
    # clone_dir сюда уже заходил предыдущий вызов этой функции. `dev_prepare`
    # клонирует репозиторий заново на каждый прогон СТАДИИ (а не на каждую
    # попытку публикации), поэтому в пределах ретраев `dev_publish` рабочее
    # дерево — то же самое: если ветка уже есть, коммит на ней, скорее всего,
    # уже сделан прошлой попыткой, и упал только пуш (или сам PR). На старом
    # линейном пути (`trigger_openhands_resolver`, ретраев нет) `dev_prepare`
    # отрабатывает заново при каждом вызове — там ветки здесь никогда не будет,
    # и поведение не меняется.
    branch_existed = git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
                         check=False).returncode == 0

    git("checkout", "-B", branch)
    git("add", "-A")
    # Пустой ИНДЕКС — не то же самое, что «агент ничего не менял»: если ветка
    # уже существовала до этого вызова, значит, коммит уехал в прошлой попытке,
    # а сорвался только пуш (или создание PR) — публикацию нужно довести, а не
    # объявлять «нет диффа». Пустой коммит по-прежнему не делаем: PR без диффа
    # ревьюить нечего, а фаза задачи от него сдвинулась бы как от настоящей
    # работы — это по-прежнему верно для ПЕРВОЙ попытки на новой ветке.
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        if not branch_existed:
            _log.warning("%s: агент не изменил ни одного файла", repo)
            return None
    else:
        git("commit", "-m", message, "-m",
            "Автор изменений — OpenHands, запущен активностью Develop.")
    git("push", "--force-with-lease", "-u", "origin", branch)

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/pulls",
        headers=_auth_headers(repo),
        json={"title": title, "head": branch, "base": _default_branch(repo), "body": body},
        timeout=30,
    )
    if resp.status_code == 422 and "already exists" in resp.text:
        # Ветку переоткрыли поверх существующего PR — это повтор прогона, а не
        # сбой: возвращаем номер уже открытого.
        existing = requests.get(
            f"https://api.github.com/repos/{repo}/pulls",
            headers=_auth_headers(repo),
            params={"head": f"{repo.split('/')[0]}:{branch}", "state": "open"},
            timeout=30,
        )
        existing.raise_for_status()
        items = existing.json()
        if items:
            return items[0]["number"]
    resp.raise_for_status()
    return resp.json()["number"]


def _default_branch(repo: str) -> str:
    resp = requests.get(f"https://api.github.com/repos/{repo}",
                        headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json().get("default_branch") or "main"


def get_pull(repo: str, number: int) -> dict:
    resp = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}",
                        headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_commit_timestamp(repo: str, commit_sha: str) -> str:
    """Время создания коммита в формате ISO 8601.

    Используется для сравнения с временем ревю при определении свежести.
    """
    url = f"https://api.github.com/repos/{repo}/commits/{commit_sha}"
    resp = requests.get(url, headers=_auth_headers(repo), timeout=30)
    resp.raise_for_status()
    return resp.json()["commit"]["committer"]["date"]


def list_reviews(repo: str, pull_number: int, limit: int = 50) -> list[dict]:
    """Список ревью PR с временными метками.

    Возвращает список ревью с полями id, user, body, submitted_at,
    state, commit_id. Используется для определения свежести ревю по времени
    и commit_id.
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pull_number}/reviews"
    resp = requests.get(
        url, headers=_auth_headers(repo), params={"per_page": min(limit, 100)}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()[:limit]

def list_pull_request_comments(repo: str, pull_number: int, limit: int = 50) -> list[dict]:
    """Список построчных комментариев PR с привязкой к коммитам.

    Возвращает список построчных комментариев с полями id, user, body, 
    created_at, commit_id, path. Используется для определения свежести 
    ревью по commit_id.
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pull_number}/comments"
    resp = requests.get(
        url, headers=_auth_headers(repo), params={"per_page": min(limit, 100)}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()[:limit]




def review_text(repo: str, number: int, limit: int = 12000) -> str:
    """Замечания ревью одним текстом: обзорные комментарии + построчные.

    Берутся комментарии БОТОВ и построчные замечания — они и есть ревью.
    Реплики людей в тред сюда не попадают: круг правок отвечает ревьюеру, а не
    участвует в обсуждении, и подмешивать туда чужие реплики значит кормить
    агента спором вместо задачи.
    """
    parts: list[str] = []

    reviews = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}/reviews",
                           headers=_auth_headers(repo), params={"per_page": 50}, timeout=30)
    if reviews.ok:
        for item in reviews.json():
            body = (item.get("body") or "").strip()
            if body:
                parts.append(f"### Ревью ({item.get('state','')})\n{body}")

    inline = requests.get(f"https://api.github.com/repos/{repo}/pulls/{number}/comments",
                          headers=_auth_headers(repo), params={"per_page": 100}, timeout=30)
    if inline.ok:
        for item in inline.json():
            body = (item.get("body") or "").strip()
            if body:
                where = f"{item.get('path')}:{item.get('line') or item.get('original_line') or '?'}"
                parts.append(f"### {where}\n{body}")

    issue_comments = requests.get(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        headers=_auth_headers(repo), params={"per_page": 100}, timeout=30)
    if issue_comments.ok:
        for item in issue_comments.json():
            if (item.get("user") or {}).get("type") != "Bot":
                continue
            body = (item.get("body") or "").strip()
            # Комментарии контура — тоже от бота: он ходит в GitHub как App.
            # Без этого фильтра на втором круге агент читал собственную просьбу
            # «внёс правки, прошу перепроверить» как часть замечаний и правил по
            # ней — то есть спорил сам с собой вместо ревьюера.
            if body and not is_agent_comment(body):
                parts.append(body)

    text = "\n\n".join(parts)
    return text[-limit:] if len(text) > limit else text


def push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:
    """Коммит правок в ветку PR. False — агент ничего не изменил.

    Пустой коммит не делаем: он выглядел бы как круг работы и заставил бы
    ревьюера смотреть на PR заново без единой правки.
    """
    if _dry_run():
        _log.info("[DRY_RUN] push fixes %s -> %s", clone_dir, branch)
        return False

    env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "4",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f",
        "GIT_CONFIG_KEY_1": "user.name",
        "GIT_CONFIG_VALUE_1": "openhands-agent",
        "GIT_CONFIG_KEY_2": "user.email",
        "GIT_CONFIG_VALUE_2": "openhands-agent@users.noreply.github.com",
        # См. publish_worktree: каталог круга правок тоже принадлежит раннеру.
        "GIT_CONFIG_KEY_3": "safe.directory",
        "GIT_CONFIG_VALUE_3": clone_dir,
        "GH_PUSH_TOKEN": auth_token(repo),
    }

    git = _git_runner(clone_dir, env)

    git("add", "-A")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git("commit", "-m", message)
    git("push", "origin", f"HEAD:{branch}")
    return True


def update_issue_body(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] update body %s#%s", repo, issue_number)
        return
    resp = requests.patch(f"https://api.github.com/repos/{repo}/issues/{issue_number}",
                          headers=_auth_headers(repo), json={"body": body}, timeout=30)
    resp.raise_for_status()
