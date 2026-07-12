import importlib


def _fresh(monkeypatch, **env):
    for k in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import github_client
    return importlib.reload(github_client)


def test_pat_header_from_gh_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tok123")
    headers = gc._auth_headers()
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["Accept"] == "application/vnd.github+json"


def test_pat_header_prefers_gh_token_over_github_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tokA", GITHUB_TOKEN="tokB")
    assert gc._auth_headers()["Authorization"] == "Bearer tokA"


def test_falls_back_to_app_when_no_pat(monkeypatch):
    gc = _fresh(monkeypatch)
    called = {}

    def fake_app_headers():
        called["app"] = True
        return {"Authorization": "Bearer app-token", "Accept": "x"}

    monkeypatch.setattr(gc, "_installation_token_headers", fake_app_headers)
    assert gc._auth_headers()["Authorization"] == "Bearer app-token"
    assert called["app"] is True
