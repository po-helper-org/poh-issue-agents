"""PR не называется готовым к слиянию, когда GitHub его слить не даёт.

Отказ: `poh-demo-checkout#172` — контур дважды написал «PR готов к слиянию»,
хотя формальное ревью человека стояло в `CHANGES_REQUESTED` и слияние было
заблокировано.
"""

from shared import pr_closing


def test_a_blocked_pr_is_not_called_ready():
    body = pr_closing.settled_comment(1, verdict="", blocked=True)

    assert "готов к слиянию" not in body
    assert "замечания" in body.lower()


def test_an_unblocked_pr_is_called_ready_as_before():
    body = pr_closing.settled_comment(1, verdict="", blocked=False)

    assert "готов к слиянию" in body


def test_an_unknown_state_says_neither():
    """Спросить не удалось — не повод ни обещать, ни обвинять (R9)."""
    body = pr_closing.settled_comment(1, verdict="", blocked=None)

    assert "готов к слиянию" not in body


def test_the_verdict_still_travels_with_the_result():
    body = pr_closing.settled_comment(2, verdict="замечание отклонено: ...",
                                      blocked=False)
    assert "замечание отклонено" in body


def test_changes_requested_reads_the_latest_review_per_author(monkeypatch):
    """Считается ПОСЛЕДНЕЕ ревью каждого автора.

    Человек мог запросить изменения, а затем одобрить: старое `CHANGES_REQUESTED`
    в списке остаётся, но блокировки больше нет.
    """
    import github_client as gc

    class _Resp:
        ok = True
        def json(self):
            return [
                {"user": {"login": "a"}, "state": "CHANGES_REQUESTED",
                 "submitted_at": "2026-09-03T05:00:00Z"},
                {"user": {"login": "a"}, "state": "APPROVED",
                 "submitted_at": "2026-09-03T06:00:00Z"},
            ]

    monkeypatch.setattr(gc.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})

    assert gc.changes_requested("o/r", 172) is False


def test_changes_requested_when_the_last_one_blocks(monkeypatch):
    import github_client as gc

    class _Resp:
        ok = True
        def json(self):
            return [
                {"user": {"login": "a"}, "state": "APPROVED",
                 "submitted_at": "2026-09-03T05:00:00Z"},
                {"user": {"login": "a"}, "state": "CHANGES_REQUESTED",
                 "submitted_at": "2026-09-03T06:00:00Z"},
            ]

    monkeypatch.setattr(gc.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})

    assert gc.changes_requested("o/r", 172) is True


def test_a_failed_question_is_unknown_not_false(monkeypatch):
    """`None`, а не `False`: молчаливое «не заблокировано» вернуло бы ложное
    обещание готовности ровно в тот момент, когда мы ничего не знаем."""
    import github_client as gc

    class _Resp:
        ok = False
        def json(self):
            return []

    monkeypatch.setattr(gc.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})

    assert gc.changes_requested("o/r", 172) is None
