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

import jwt
import requests

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


def _installation_token_for(repo: str) -> str:
    """Installation-токен под установку App на данный репозиторий. Установка
    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →
    GET /repos/{repo}/installation вернёт 404 и вызов упадёт."""
    with _token_lock:
        cached = _token_cache.get(repo)
        if cached and cached[1] - 60 > time.time():
            return cached[0]
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


def _auth_headers(repo: str) -> dict:
    """PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly
    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return _installation_token_headers(repo)


def post_comment(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=_auth_headers(repo), json={"body": body}, timeout=30)
    resp.raise_for_status()


def add_label(repo: str, issue_number: int, label: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] label %s#%s += %s", repo, issue_number, label)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    resp = requests.post(url, headers=_auth_headers(repo), json={"labels": [label]}, timeout=30)
    resp.raise_for_status()


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
    env = {**os.environ, "GH_TOKEN": _auth_headers(repo)["Authorization"].split(" ")[1]}
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


def add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None:
    """Реакция на комментарий — подтверждение, что команда увидена, до того
    как начнётся долгий расчёт. GitHub отвечает 200 на уже поставленную
    реакцию, поэтому повторный вызов безвреден."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s on %s comment %s", content, repo, comment_id)
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"
    resp = requests.post(url, headers=_auth_headers(repo), json={"content": content}, timeout=30)
    resp.raise_for_status()


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
    return resp.json()["html_url"]


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
