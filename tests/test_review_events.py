"""Событие ревью GitHub → факт для цикла Issue.

Отказ, ради которого написано: `poh-demo-checkout#172`. Человек оставил
ревью со статусом `CHANGES_REQUESTED` и замечанием про регрессию, а контур
дважды объявил «PR готов к слиянию» — событий ревью он не получает вовсе.
"""

from shared import review_events


def _review(state="changes_requested", login="kibarik", kind="User", body="есть замечание"):
    return {
        "action": "submitted",
        "repository": {"full_name": "o/r"},
        "pull_request": {"number": 172, "body": "Closes #171"},
        "review": {"id": 9, "state": state, "body": body,
                   "commit_id": "abc123", "user": {"login": login, "type": kind}},
    }


def test_changes_requested_wakes_the_repair_loop():
    event = review_events.from_review(_review())

    assert event is not None
    assert event.repo == "o/r"
    assert event.phase == "pr-review"
    assert event.status == "started"
    assert event.ref == "172"
    assert event.revision == "abc123", "ревизия входит в ключ идемпотентности"
    assert "есть замечание" in event.detail
    assert "Closes #171" in event.detail, "по нему корреляция найдёт задачу"


def test_a_plain_comment_review_also_wakes_it():
    """`COMMENTED` — тоже замечания, просто без блокировки слияния."""
    assert review_events.from_review(_review(state="commented")) is not None


def test_approval_wakes_nothing():
    """Править по одобрению нечего — круг правок стоил бы прогона агента зря."""
    assert review_events.from_review(_review(state="approved")) is None


def test_a_dismissed_review_wakes_nothing():
    assert review_events.from_review(_review(state="dismissed")) is None


def test_a_bot_review_wakes_nothing():
    """PR-Agent докладывает через `/agent-event` (R4).

    Вторая побудка от него дала бы два круга правок на один доклад — то есть
    двойную цену прогона агента за один и тот же текст.
    """
    assert review_events.from_review(_review(login="poh-harness-demo[bot]",
                                             kind="Bot")) is None


def test_an_empty_review_body_still_wakes_when_changes_are_requested():
    """Пустое тело при `CHANGES_REQUESTED` — замечания в построчных.

    Молчаливое «нечего будить» здесь означало бы ровно тот отказ, ради
    которого всё пишется.
    """
    assert review_events.from_review(_review(body="")) is not None


def test_an_empty_commented_review_wakes_nothing():
    """`COMMENTED` без текста и без блокировки — не замечание."""
    assert review_events.from_review(_review(state="commented", body="")) is None


def test_wrong_action_wakes_nothing():
    payload = _review()
    payload["action"] = "edited"
    assert review_events.from_review(payload) is None


def _review_comment(login="kibarik", kind="User"):
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "pull_request": {"number": 172, "body": "Closes #171"},
        "comment": {"id": 5, "body": "здесь опечатка", "path": "src/a.py",
                    "line": 12, "commit_id": "abc123",
                    "user": {"login": login, "type": kind}},
    }


def test_an_inline_comment_wakes_the_repair_loop():
    """`review_text` построчные замечания читает — оставить их без побудки
    значило бы починить половину (R2)."""
    event = review_events.from_review_comment(_review_comment())

    assert event is not None
    assert event.ref == "172"
    assert "src/a.py:12" in event.detail
    assert "здесь опечатка" in event.detail


def test_an_inline_comment_from_a_bot_wakes_nothing():
    assert review_events.from_review_comment(
        _review_comment(login="pr-agent[bot]", kind="Bot")) is None
