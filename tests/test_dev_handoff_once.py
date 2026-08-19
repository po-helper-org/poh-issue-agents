"""Передача в разработку: один прогон, одно объявление, видимая причина отказа.

Живой прогон #39 дал три комментария «Передал задачу в разработку» подряд и три
полных прогона агента: пуш падал на последнем шаге активности, Temporal ретраил
её целиком, а причина отказа git не попадала никуда — `capture_output` съедал
stderr, и в истории оставалось только «returned non-zero exit status 1».
"""

import asyncio

import pytest

import activities
import github_client as gc
from shared import develop
from shared.workflow_types import IssueInput


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=39, title="t", body="b",
                      author_login="u", author_type="User")


# --- Объявление о передаче ---

def test_announce_is_skipped_when_already_in_development(monkeypatch):
    posted = []
    monkeypatch.setattr(activities.github_client, "get_issue",
                        lambda repo, n: {"labels": [{"name": develop.IN_DEVELOPMENT_LABEL}]})
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a: posted.append(a))
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)

    asyncio.run(activities._dev_announce(_issue(), "", where="на своём сервере"))

    assert posted == [], "повторная передача не должна давать второго комментария"


def test_announce_posts_on_the_first_handoff(monkeypatch):
    posted = []
    monkeypatch.setattr(activities.github_client, "get_issue",
                        lambda repo, n: {"labels": [{"name": "priority:P1"}]})
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a: posted.append(a))
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)

    asyncio.run(activities._dev_announce(_issue(), "", where="на своём сервере"))

    assert len(posted) == 1


def test_announce_speaks_up_when_labels_are_unreadable(monkeypatch):
    """Молчание хуже дубля: человек должен знать, что работа идёт."""
    posted = []

    def boom(*a):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(activities.github_client, "get_issue", boom)
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a: posted.append(a))
    monkeypatch.setattr(activities.github_client, "add_label", lambda *a: None)

    asyncio.run(activities._dev_announce(_issue(), "", where="на своём сервере"))

    assert len(posted) == 1


# --- Причина отказа git ---

def test_git_failure_carries_stderr(monkeypatch, tmp_path):
    class _Failed:
        returncode = 1
        stdout = ""
        stderr = "remote: Permission to o/r.git denied to app.\nfatal: unable to access"

    monkeypatch.setattr(gc.subprocess, "run", lambda cmd, **kw: _Failed())
    git = gc._git_runner(str(tmp_path), {"GH_PUSH_TOKEN": "ghs_secret"})

    with pytest.raises(gc.GitCommandError) as exc:
        git("push", "--force-with-lease", "-u", "origin", "feature/39-openhands")

    assert "Permission to o/r.git denied" in str(exc.value)
    assert "push --force-with-lease" in str(exc.value)


def test_git_failure_does_not_leak_the_token(monkeypatch, tmp_path):
    class _Failed:
        returncode = 128
        stdout = ""
        stderr = "fatal: Authentication failed for 'https://x-access-token:ghs_secret@github.com'"

    monkeypatch.setattr(gc.subprocess, "run", lambda cmd, **kw: _Failed())
    git = gc._git_runner(str(tmp_path), {"GH_PUSH_TOKEN": "ghs_secret"})

    with pytest.raises(gc.GitCommandError) as exc:
        git("push", "origin", "HEAD:feature/39")

    assert "ghs_secret" not in str(exc.value)
    assert "[Filtered]" in str(exc.value)


def test_git_returns_result_when_check_is_off(monkeypatch, tmp_path):
    """`diff --cached --quiet` спрашивает про код возврата, а не про отказ."""
    class _Diff:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(gc.subprocess, "run", lambda cmd, **kw: _Diff())
    git = gc._git_runner(str(tmp_path), {})

    assert git("diff", "--cached", "--quiet", check=False).returncode == 1
