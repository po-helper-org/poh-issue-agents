import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=1, title="Надёжность",
                        body="Ядро платформы.", comment_id=1)


def _comment(login, body, date="2026-07-20T10:00:00Z"):
    return {"user": {"login": login}, "body": body, "created_at": date}


def _wire(monkeypatch, comments=None, prs=None, comments_exc=None, prs_exc=None):
    def fake_comments(repo, n, limit=50):
        if comments_exc:
            raise comments_exc
        return comments or []

    def fake_prs(repo, n, limit=20):
        if prs_exc:
            raise prs_exc
        return prs or []

    monkeypatch.setattr(activities.github_client, "list_comments", fake_comments)
    monkeypatch.setattr(activities.github_client, "list_linked_prs", fake_prs)


def test_includes_title_body_comments_and_prs(monkeypatch):
    _wire(monkeypatch,
          comments=[_comment("kibarik", "Решение: retry-only, один ключ Z.AI")],
          prs=[{"number": 2, "title": "Ingress", "state": "open",
                "url": "https://github.com/o/r/pull/2"}])

    ctx = activities._build_task_context(_analyze())

    assert "Надёжность" in ctx and "Ядро платформы." in ctx
    assert "@kibarik" in ctx and "retry-only" in ctx
    assert "#2 Ingress [open]" in ctx and "pull/2" in ctx


def test_filters_command_comments(monkeypatch):
    _wire(monkeypatch, comments=[
        _comment("kibarik", "/analyze"),
        _comment("kibarik", "/analyze разбери фазу 2"),
        _comment("dev", "Реальный комментарий по существу"),
    ])

    ctx = activities._build_task_context(_analyze())

    assert "по существу" in ctx
    assert "/analyze" not in ctx
    assert "разбери фазу 2" not in ctx


def test_truncates_long_comment(monkeypatch):
    _wire(monkeypatch, comments=[_comment("dev", "x" * 5000)])

    ctx = activities._build_task_context(_analyze())

    assert "…[обрезано]" in ctx
    assert "x" * 5000 not in ctx


def test_caps_total_and_keeps_newest(monkeypatch):
    big = "B" * 2000
    comments = [_comment("dev", f"OLD-{i}-{big}", date=f"2026-07-{10+i:02d}T00:00:00Z")
                for i in range(20)]
    comments[-1] = _comment("dev", "NEWEST-marker-" + big, date="2026-08-01T00:00:00Z")
    _wire(monkeypatch, comments=comments)

    ctx = activities._build_task_context(_analyze())

    assert len(ctx) <= activities.CONTEXT_TOTAL_CHARS
    assert "Надёжность" in ctx           # title/body неприкосновенны
    assert "NEWEST-marker" in ctx        # свежий уцелел
    assert "OLD-0-" not in ctx           # старейший отброшен


def test_degrades_to_body_only_when_comments_fetch_fails(monkeypatch):
    _wire(monkeypatch, comments_exc=RuntimeError("boom"),
          prs=[{"number": 2, "title": "Ingress", "state": "open",
                "url": "https://github.com/o/r/pull/2"}])

    ctx = activities._build_task_context(_analyze())

    assert "Ядро платформы." in ctx       # база на месте
    assert "## Обсуждение" not in ctx      # секция комментариев пропущена
    assert "#2 Ingress" in ctx            # PR-секция уцелела (независимая деградация)


def test_degrades_when_prs_fetch_fails(monkeypatch):
    _wire(monkeypatch, comments=[_comment("dev", "живой контекст")],
          prs_exc=RuntimeError("boom"))

    ctx = activities._build_task_context(_analyze())

    assert "живой контекст" in ctx
    assert "## Связанные PR" not in ctx
