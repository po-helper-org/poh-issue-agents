import importlib


def _fresh(monkeypatch, dry):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    import github_client
    return importlib.reload(github_client)


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_auth_token_strips_bearer_prefix(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    assert gc.auth_token() == "tok"


def test_dry_run_makes_no_http_calls(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "put", boom)
    monkeypatch.setattr(gc.requests, "get", boom)

    gc.add_reaction("o/r", 42)
    gc.push_artifacts_to_branch("o/r", "research/issue-5", {"a/b.md": "x"}, "msg")


def test_add_reaction_posts_to_comment_reactions_endpoint(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        return Resp(201)

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.add_reaction("o/r", 42)

    assert seen["url"].endswith("/repos/o/r/issues/comments/42/reactions")
    assert seen["json"] == {"content": "eyes"}


def test_ensure_branch_creates_ref_from_default_branch(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    posted = {}

    def fake_get(url, **kwargs):
        if url.endswith("/repos/o/r"):
            return Resp(200, {"default_branch": "main"})
        if url.endswith("/git/ref/heads/main"):
            return Resp(200, {"object": {"sha": "deadbeef"}})
        return Resp(404)  # ветки ещё нет

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        return Resp(201)

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.ensure_branch("o/r", "research/issue-5")

    assert posted["json"]["ref"] == "refs/heads/research/issue-5"
    assert posted["json"]["sha"] == "deadbeef"


def test_ensure_branch_is_noop_when_branch_exists(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(200, {}))

    def boom(*a, **k):
        raise AssertionError("branch re-created though it already exists")

    monkeypatch.setattr(gc.requests, "post", boom)
    gc.ensure_branch("o/r", "research/issue-5")


def test_push_artifacts_puts_each_file_base64_encoded(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    puts = []

    monkeypatch.setattr(gc, "ensure_branch", lambda repo, branch: None)
    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(404))

    def fake_put(url, **kwargs):
        puts.append((url, kwargs.get("json")))
        return Resp(201)

    monkeypatch.setattr(gc.requests, "put", fake_put)
    gc.push_artifacts_to_branch(
        "o/r", "research/issue-5", {"docs/a.md": "hello", "docs/b.md": "world"}, "msg",
    )

    assert len(puts) == 2
    url, body = puts[0]
    assert "/repos/o/r/contents/docs/a.md" in url
    assert body["branch"] == "research/issue-5"
    import base64
    assert base64.b64decode(body["content"]).decode() == "hello"


def test_put_file_includes_sha_when_file_already_exists(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    captured = {}

    monkeypatch.setattr(gc.requests, "get", lambda url, **k: Resp(200, {"sha": "oldsha"}))

    def fake_put(url, **kwargs):
        captured["json"] = kwargs.get("json")
        return Resp(200)

    monkeypatch.setattr(gc.requests, "put", fake_put)
    gc.put_file("o/r", "research/issue-5", "docs/a.md", "new", "msg")

    assert captured["json"]["sha"] == "oldsha"
