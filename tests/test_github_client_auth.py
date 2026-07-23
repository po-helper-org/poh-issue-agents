import base64
import importlib


def _fresh(monkeypatch, **env):
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PRIVATE_KEY_B64",
              "GITHUB_PRIVATE_KEY_PATH", "GITHUB_INSTALLATION_ID"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import github_client
    return importlib.reload(github_client)


def test_pat_header_from_gh_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tok123")
    headers = gc._auth_headers("o/r")
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["Accept"] == "application/vnd.github+json"


def test_pat_header_prefers_gh_token_over_github_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tokA", GITHUB_TOKEN="tokB")
    assert gc._auth_headers("o/r")["Authorization"] == "Bearer tokA"


def test_falls_back_to_app_when_no_pat(monkeypatch):
    gc = _fresh(monkeypatch)
    seen = {}

    def fake_app_headers(repo):
        seen["repo"] = repo
        return {"Authorization": "Bearer app-token", "Accept": "x"}

    monkeypatch.setattr(gc, "_installation_token_headers", fake_app_headers)
    assert gc._auth_headers("o/r")["Authorization"] == "Bearer app-token"
    assert seen["repo"] == "o/r"


def test_app_private_key_from_b64(monkeypatch):
    gc = _fresh(monkeypatch, GITHUB_PRIVATE_KEY_B64=base64.b64encode(b"PEMDATA").decode())
    assert gc._app_private_key() == b"PEMDATA"


def test_app_private_key_falls_back_to_file(monkeypatch, tmp_path):
    pem = tmp_path / "key.pem"
    pem.write_bytes(b"FILEPEM")
    gc = _fresh(monkeypatch, GITHUB_PRIVATE_KEY_PATH=str(pem))
    assert gc._app_private_key() == b"FILEPEM"


def test_per_repo_token_caches_and_exchanges(monkeypatch):
    gc = _fresh(monkeypatch)
    monkeypatch.setattr(gc, "_app_jwt", lambda: "jwt")
    calls = []

    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url))
        return Resp({"id": 42})

    def fake_post(url, headers=None, timeout=None):
        calls.append(("POST", url))
        return Resp({"token": "inst-token"})

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc.requests, "post", fake_post)

    assert gc._installation_token_for("o/r") == "inst-token"
    # второй вызов по тому же репо — из кэша, без новых сетевых обменов
    assert gc._installation_token_for("o/r") == "inst-token"
    assert calls == [
        ("GET", "https://api.github.com/repos/o/r/installation"),
        ("POST", "https://api.github.com/app/installations/42/access_tokens"),
    ]


def test_per_repo_token_separate_per_repo(monkeypatch):
    gc = _fresh(monkeypatch)
    monkeypatch.setattr(gc, "_app_jwt", lambda: "jwt")
    ids = {"o/a": 1, "o/b": 2}

    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        repo = url.split("/repos/", 1)[1].rsplit("/installation", 1)[0]
        return Resp({"id": ids[repo]})

    posted = []

    def fake_post(url, headers=None, timeout=None):
        posted.append(url)
        return Resp({"token": f"tok-{url.split('/installations/')[1].split('/')[0]}"})

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc.requests, "post", fake_post)

    assert gc._installation_token_for("o/a") == "tok-1"
    assert gc._installation_token_for("o/b") == "tok-2"
