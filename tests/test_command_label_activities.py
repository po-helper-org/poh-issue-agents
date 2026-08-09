"""Обратный ход меток: `run:<cmd>` снимается, исход вешается своей меткой."""

import asyncio

import activities
from shared.commands import ANALYZE, ESTIMATE
from shared.workflow_types import AnalyzeInput, EstimateRequest


def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append(("+", repo, n, label)))
    monkeypatch.setattr(activities.github_client, "remove_label",
                        lambda repo, n, label: calls.append(("-", repo, n, label)))
    return calls


def test_success_swaps_run_for_done(monkeypatch):
    calls = _spy(monkeypatch)

    asyncio.run(activities.finish_command_labels("o/r", 7, ANALYZE, True))

    assert ("-", "o/r", 7, "run:analyze") in calls
    assert ("+", "o/r", 7, "done:analyze") in calls
    assert ("+", "o/r", 7, "failed:analyze") not in calls


def test_failure_gets_its_own_label(monkeypatch):
    """Молча снятый `run:*` неотличим от «никто не запускал» — нужен failed:*."""
    calls = _spy(monkeypatch)

    asyncio.run(activities.finish_command_labels("o/r", 7, ESTIMATE, False))

    assert ("-", "o/r", 7, "run:estimate") in calls
    assert ("+", "o/r", 7, "failed:estimate") in calls
    assert ("+", "o/r", 7, "done:estimate") not in calls


def test_legacy_analyzing_label_is_cleared_too(monkeypatch):
    calls = _spy(monkeypatch)

    asyncio.run(activities.finish_command_labels("o/r", 7, ANALYZE, True))

    assert ("-", "o/r", 7, "analyzing") in calls


def test_outcome_label_survives_a_failed_removal(monkeypatch):
    """Прогон уже состоялся: сбой косметики не должен стереть его исход."""
    calls = []

    def boom_remove(repo, n, label):
        raise RuntimeError("GitHub 503")

    monkeypatch.setattr(activities.github_client, "remove_label", boom_remove)
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append(label))

    asyncio.run(activities.finish_command_labels("o/r", 7, ANALYZE, True))

    assert calls == ["done:analyze"]


def test_failed_outcome_label_does_not_break_the_workflow(monkeypatch):
    monkeypatch.setattr(activities.github_client, "remove_label", lambda *a: None)

    def boom_add(repo, n, label):
        raise RuntimeError("GitHub 503")

    monkeypatch.setattr(activities.github_client, "add_label", boom_add)

    asyncio.run(activities.finish_command_labels("o/r", 7, ANALYZE, True))  # не бросает


def test_mark_command_running_labels_the_issue(monkeypatch):
    calls = _spy(monkeypatch)

    asyncio.run(activities.mark_command_running("o/r", 5, ANALYZE))

    assert calls == [("+", "o/r", 5, "run:analyze")]


def test_ack_command_marks_running_whatever_the_trigger(monkeypatch):
    """Выборка `label:run:*` обязана быть честной и для запуска командой."""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    monkeypatch.setattr(activities.github_client, "add_reaction", lambda *a: None)

    asyncio.run(activities.ack_command(
        AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b", comment_id=42)))

    assert ("+", "o/r", 5, "run:analyze") in calls


def test_ack_command_from_label_names_the_label_and_skips_reaction(monkeypatch):
    _spy(monkeypatch)
    posted = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body))

    def boom(*a):
        raise AssertionError("реагировать не на что: триггер — метка")

    monkeypatch.setattr(activities.github_client, "add_reaction", boom)

    asyncio.run(activities.ack_command(
        AnalyzeInput(repo="o/r", issue_number=5, title="t", body="b")))

    assert "run:analyze" in posted["body"]


def test_ack_estimate_from_label_comments_instead_of_reacting(monkeypatch):
    calls = _spy(monkeypatch)
    posted = {}
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body))

    def boom(*a):
        raise AssertionError("у метки нет комментария-триггера")

    monkeypatch.setattr(activities.github_client, "add_reaction", boom)

    activities.ack_estimate_command(EstimateRequest(repo="o/r", issue_number=5))

    assert ("+", "o/r", 5, "run:estimate") in calls
    assert "run:estimate" in posted["body"]


def test_ack_estimate_from_comment_still_reacts(monkeypatch):
    _spy(monkeypatch)
    reactions = []
    monkeypatch.setattr(activities.github_client, "add_reaction",
                        lambda repo, cid, content: reactions.append((cid, content)))

    def boom(*a):
        raise AssertionError("на команду в комментарии отвечаем реакцией, а не шумом")

    monkeypatch.setattr(activities.github_client, "post_comment", boom)

    activities.ack_estimate_command(
        EstimateRequest(repo="o/r", issue_number=5, comment_id=99))

    assert reactions == [(99, "eyes")]


def test_estimate_error_without_comment_skips_reaction(monkeypatch):
    monkeypatch.setattr(activities.github_client, "post_comment", lambda *a: None)
    monkeypatch.setattr(activities.sentry_setup, "capture_estimate_failure", lambda *a: None)

    def boom(*a):
        raise AssertionError("реакции без комментария-триггера быть не может")

    monkeypatch.setattr(activities.github_client, "add_reaction", boom)

    activities.post_estimate_error(
        EstimateRequest(repo="o/r", issue_number=5), "расчёт", "RuntimeError: boom")
