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
import time

import jwt
import requests

_log = logging.getLogger("github_client")


def _dry_run() -> bool:
    return bool(os.environ.get("DRY_RUN"))


_installation_token: str | None = None
_token_expires_at: float = 0.0


def _app_jwt() -> str:
    with open(os.environ["GITHUB_PRIVATE_KEY_PATH"], "rb") as f:
        private_key = f.read()
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": os.environ["GITHUB_APP_ID"]}
    return jwt.encode(payload, private_key, algorithm="RS256")


def _installation_token_headers() -> dict:
    global _installation_token, _token_expires_at
    if _installation_token is None or time.time() > _token_expires_at - 60:
        app_jwt = _app_jwt()
        installation_id = os.environ["GITHUB_INSTALLATION_ID"]
        resp = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        _installation_token = data["token"]
        _token_expires_at = time.time() + 55 * 60  # реальный TTL ~1ч, берём с запасом
    return {"Authorization": f"Bearer {_installation_token}", "Accept": "application/vnd.github+json"}


def _auth_headers() -> dict:
    """PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it
    directly and skip the GitHub App flow. Otherwise fall back to App auth."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return _installation_token_headers()


def post_comment(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=_auth_headers(), json={"body": body}, timeout=30)
    resp.raise_for_status()


def add_label(repo: str, issue_number: int, label: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] label %s#%s += %s", repo, issue_number, label)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    resp = requests.post(url, headers=_auth_headers(), json={"labels": [label]}, timeout=30)
    resp.raise_for_status()


def close_issue(repo: str, issue_number: int) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] close %s#%s", repo, issue_number)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.patch(url, headers=_auth_headers(), json={"state": "closed"}, timeout=30)
    resp.raise_for_status()


def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:
    """Через gh CLI — тот же паттерн, что и в версии на Actions, но токен
    для gh нужно прокинуть через переменную окружения перед вызовом."""
    env = {**os.environ, "GH_TOKEN": auth_token()}
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
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    return resp.status_code == 200


def auth_token() -> str:
    """Голый токен для внешних процессов (git clone, gh CLI)."""
    return _auth_headers()["Authorization"].split(" ", 1)[1]


def add_reaction(repo: str, comment_id: int, content: str = "eyes") -> None:
    """Реакция на комментарий — видимое «команда принята» до тяжёлой работы."""
    if _dry_run():
        _log.info("[DRY_RUN] reaction %s comment %s: %s", repo, comment_id, content)
        return
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"
    resp = requests.post(url, headers=_auth_headers(), json={"content": content}, timeout=30)
    resp.raise_for_status()


def ensure_branch(repo: str, branch: str) -> None:
    """Создаёт ветку от дефолтной, если её ещё нет."""
    if branch_exists(repo, branch):
        return
    meta = requests.get(f"https://api.github.com/repos/{repo}", headers=_auth_headers(), timeout=30)
    meta.raise_for_status()
    base = meta.json()["default_branch"]

    ref = requests.get(
        f"https://api.github.com/repos/{repo}/git/ref/heads/{base}",
        headers=_auth_headers(), timeout=30,
    )
    ref.raise_for_status()
    sha = ref.json()["object"]["sha"]

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=_auth_headers(),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=30,
    )
    resp.raise_for_status()


def put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:
    """Создаёт или обновляет файл в ветке через Contents API.

    Contents API, а не `git push`: клон делается shallow (--depth 1), а push из
    такого клона GitHub может отклонить. Здесь ремоут вообще не нужен.
    """
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    existing = requests.get(url, headers=_auth_headers(), params={"ref": branch}, timeout=30)
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]  # перезапись требует sha текущей версии

    resp = requests.put(url, headers=_auth_headers(), json=payload, timeout=30)
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
