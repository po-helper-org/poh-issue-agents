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
    env = {**os.environ, "GH_TOKEN": _auth_headers()["Authorization"].split(" ")[1]}
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


def create_pr_with_files(repo: str, branch: str, base: str,
                         files: dict, title: str, body: str):
    if _dry_run():
        _log.info("[DRY_RUN] PR %s <- %s: %d files, title=%s",
                  repo, branch, len(files), title)
        return None
    h = _auth_headers()
    api = f"https://api.github.com/repos/{repo}"
    base_sha = requests.get(f"{api}/git/refs/heads/{base}", headers=h,
                            timeout=30).json()["object"]["sha"]
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
    env = {**os.environ, "GH_TOKEN": _auth_headers()["Authorization"].split(" ")[1]}
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--limit", str(limit), "--json", "number,title,body,labels"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    out = []
    for it in json.loads(result.stdout or "[]"):
        it["labels"] = [l["name"] for l in it.get("labels", [])]
        out.append(it)
    return out
