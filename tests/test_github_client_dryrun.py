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
