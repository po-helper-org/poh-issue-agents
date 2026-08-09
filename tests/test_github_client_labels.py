"""Снятие метки: DRY_RUN, кодирование имени в URL и отсутствующая метка."""

import importlib


def _fresh(monkeypatch, dry):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    import github_client
    return importlib.reload(github_client)


def test_dry_run_removes_nothing(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "delete", boom)
    gc.remove_label("o/r", 1, "run:analyze")


def test_label_name_is_url_encoded(monkeypatch):
    """В схеме меток есть двоеточие; голым оно в пути URL не поедет."""
    gc = _fresh(monkeypatch, dry=False)
    calls = {}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_delete(url, **kwargs):
        calls["url"] = url
        return Resp()

    monkeypatch.setattr(gc.requests, "delete", fake_delete)
    gc.remove_label("o/r", 7, "run:analyze")
    assert calls["url"].endswith("/repos/o/r/issues/7/labels/run%3Aanalyze")


def test_missing_label_is_not_an_error(monkeypatch):
    """Финализация зовётся и для прогона, запущенного командой в комментарии,
    где метку `run:*` никто не вешал."""
    gc = _fresh(monkeypatch, dry=False)

    class Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 на отсутствующей метке — не ошибка")

    monkeypatch.setattr(gc.requests, "delete", lambda url, **kwargs: Resp())
    gc.remove_label("o/r", 7, "run:analyze")


def test_other_http_errors_still_raise(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    raised = {}

    class Resp:
        status_code = 500

        def raise_for_status(self):
            raised["yes"] = True
            raise RuntimeError("500")

    monkeypatch.setattr(gc.requests, "delete", lambda url, **kwargs: Resp())
    try:
        gc.remove_label("o/r", 7, "run:analyze")
    except RuntimeError:
        pass
    assert raised == {"yes": True}
