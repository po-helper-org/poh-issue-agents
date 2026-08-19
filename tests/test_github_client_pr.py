import github_client


def test_create_pr_dry_run_makes_no_calls(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    called = {"n": 0}
    monkeypatch.setattr(github_client.requests, "post",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "put",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    url = github_client.create_pr_with_files(
        "o/r", "consolidation/2026-07-14", "main",
        {"docs/consolidation/overview.md": "# x"}, "Consolidation", "body")
    assert url is None
    assert called["n"] == 0


def test_review_text_skips_the_harness_own_comments(monkeypatch):
    """Круг правок отвечает РЕВЬЮЕРУ, а не сам себе.

    Комментарии контура приходят от GitHub App, то есть с `type == "Bot"`, и
    попадали в текст ревью вместе с настоящими замечаниями. На втором круге
    агент читал собственную просьбу «внёс правки, прошу перепроверить» как часть
    замечаний — и правил по ней.
    """
    import github_client as gc
    from shared.agent_comment import MARKER

    class _Resp:
        ok = True

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("/reviews"):
            return _Resp([{"state": "COMMENTED", "body": "PR Reviewer Guide 🔍"}])
        if url.endswith("/pulls/9/comments"):
            return _Resp([])
        return _Resp([
            {"user": {"type": "Bot"}, "body": f"/review\n\nвнёс правки\n\n{MARKER}"},
            {"user": {"type": "Bot"}, "body": "Suggestion: вынести порог в константу"},
            {"user": {"type": "User"}, "body": "а мне и так нравится"},
        ])

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})

    text = gc.review_text("o/r", 9)

    assert "PR Reviewer Guide" in text
    assert "вынести порог в константу" in text
    assert "внёс правки" not in text, "агент кормится своей же просьбой"
    assert "и так нравится" not in text, "реплика человека — не замечание ревью"
