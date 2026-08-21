"""Метки одной операцией: порядок вызовов, терпимость к 404, DRY_RUN."""

import importlib


def _fresh(monkeypatch, dry=False):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    import github_client
    return importlib.reload(github_client)


class _Resp:
    def __init__(self, code=200):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


def test_add_goes_before_remove(monkeypatch):
    """Целевая метка ставится раньше снятия соседних.

    Иначе есть окно, в котором меток `phase:*` нет вовсе, и
    `lifecycle.phase_from_labels` возвращает None — Issue выглядит как никогда
    не входивший в жизненный цикл. Две метки в том же окне хотя бы видны.
    """
    gc = _fresh(monkeypatch)
    order = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda url, **kw: order.append("add") or _Resp())
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: order.append("remove") or _Resp())

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])
    assert order == ["add", "remove"]


def test_add_is_a_single_request(monkeypatch):
    """Несколько меток уезжают одним POST, а не по одной."""
    gc = _fresh(monkeypatch)
    posts = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda url, **kw: posts.append(kw["json"]) or _Resp())
    monkeypatch.setattr(gc.requests, "delete", lambda url, **kw: _Resp())

    gc.set_labels("o/r", 7, add=["a", "b", "c"])
    assert posts == [{"labels": ["a", "b", "c"]}]


def test_failed_removal_is_logged_not_raised(monkeypatch):
    """Снятие метки — best-effort, как было в set_phase."""
    gc = _fresh(monkeypatch)
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp())
    monkeypatch.setattr(gc.requests, "delete", lambda url, **kw: _Resp(500))

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])


def test_failed_add_still_raises(monkeypatch):
    """Непоставленная метка — потерянное состояние, это ошибка.

    Но снятие всё равно должно было отработать: иначе 5xx на постановке
    итоговой метки оставляет `run:*` на Issue навсегда, а прогон при этом уже
    состоялся (успешно или нет) — выборка «прогон идёт» лжёт бессрочно.
    """
    gc = _fresh(monkeypatch)
    removed = []
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp(500))
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: removed.append(url) or _Resp())

    try:
        gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("ошибка постановки метки должна подниматься")

    assert len(removed) == 1 and removed[0].endswith("/labels/phase%3Aclassified"), (
        "снятие должно было выполниться, несмотря на сбой постановки")


def test_removal_order_survives_a_failed_add(monkeypatch):
    """Порядок «постановка → снятие» не нарушается сбоем: снятие не
    пропускается, просто ошибка постановки поднимается уже после него."""
    gc = _fresh(monkeypatch)
    order = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda url, **kw: order.append("add") or _Resp(500))
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: order.append("remove") or _Resp())

    try:
        gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("ошибка постановки метки должна подниматься")

    assert order == ["add", "remove"]


def test_label_being_added_is_never_removed(monkeypatch):
    """Защита от вызова, где имя есть и в add, и в remove."""
    gc = _fresh(monkeypatch)
    removed = []
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp())
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: removed.append(url) or _Resp())

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:groomed", "x"])
    assert len(removed) == 1 and removed[0].endswith("/labels/x")


def test_nothing_to_do_makes_no_requests(monkeypatch):
    gc = _fresh(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("HTTP на пустом наборе меток")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "delete", boom)
    gc.set_labels("o/r", 7)


def test_dry_run_makes_no_requests(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP под DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "delete", boom)
    gc.set_labels("o/r", 7, add=["a"], remove=["b"])
