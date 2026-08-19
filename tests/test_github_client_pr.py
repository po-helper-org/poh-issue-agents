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


def test_git_trusts_the_worktree_the_runner_owned(monkeypatch, tmp_path):
    """Коммит идёт от root в каталоге, которым владеет раннер.

    Каталог задачи передаётся раннеру (uid 10001), а коммит и пуш делает воркер
    от root. Git на такое отвечает `fatal: detected dubious ownership in
    repository` и отказывается работать — то есть готовая работа агента не
    доезжает до PR. `safe.directory` объявляет каталог доверенным для этой
    команды, не трогая глобальный конфиг.
    """
    import github_client as gc

    class _Done:
        returncode = 0  # «диффа нет» — до пуша не доходим, нам нужен только env
        stdout = ""
        stderr = ""

    captured: dict = {}

    def fake_run(cmd, **kw):
        captured.setdefault("env", kw.get("env"))
        return _Done()

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc.subprocess, "run", fake_run)

    gc.publish_worktree("o/r", str(tmp_path), "feature/1-x",
                        title="t", body="b", message="m")

    env = captured["env"]
    keys = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
            for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert keys.get("safe.directory") == str(tmp_path)
