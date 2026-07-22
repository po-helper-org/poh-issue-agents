import importlib


def _fresh(monkeypatch, dry):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    import github_client
    return importlib.reload(github_client)


def test_dry_run_post_comment_makes_no_http_call(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "patch", boom)
    gc.post_comment("o/r", 1, "body")
    gc.add_label("o/r", 1, "priority:P1")
    gc.close_issue("o/r", 1)


def test_non_dry_run_post_comment_calls_http(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    calls = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, **k):
        calls["post"] = url
        return Resp()

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.post_comment("o/r", 1, "body")
    assert "/repos/o/r/issues/1/comments" in calls["post"]


def test_dry_run_reaction_makes_no_http_call(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    gc.add_reaction("o/r", 555, "eyes")


def test_non_dry_run_reaction_posts_to_the_comment(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    calls = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs.get("json")
        return Resp()

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.add_reaction("o/r", 555, "eyes")
    assert calls["url"].endswith("/repos/o/r/issues/comments/555/reactions")
    assert calls["json"] == {"content": "eyes"}


def test_reads_are_not_blocked_by_dry_run(monkeypatch):
    """DRY_RUN защищает от мутаций, а не от чтения: без чтения контекста
    прогон в DRY_RUN не показал бы, что именно система собралась сделать."""
    gc = _fresh(monkeypatch, dry=True)
    calls = {}

    class Resp:
        status_code = 200
        text = "содержимое"

        def raise_for_status(self):
            pass

        def json(self):
            return {"title": "t"}

    def fake_get(url, **kwargs):
        calls["url"] = url
        return Resp()

    monkeypatch.setattr(gc.requests, "get", fake_get)
    assert gc.get_issue("o/r", 7) == {"title": "t"}
    assert gc.get_file("o/r", "docs/x.md", "research/issue-7") == "содержимое"


def test_missing_file_returns_none(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)

    class Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("не должно вызываться на 404")

    monkeypatch.setattr(gc.requests, "get", lambda url, **kwargs: Resp())
    assert gc.get_file("o/r", "docs/missing.md", "research/issue-7") is None
