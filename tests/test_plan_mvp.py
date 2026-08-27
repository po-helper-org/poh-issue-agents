"""Стадия построения плана: артефакт проверяется существованием, не словом модели.

Стадия `validate` цепочки FNR объявлена с ожидаемым артефактом None — проверять
нечего, и вердикт пишет сама модель. Здесь так нельзя: план — вход исполнителя.
"""

import asyncio
from pathlib import Path

import activities as a
from shared import task_context


def test_plan_stage_fails_when_file_not_created(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "_run_claude", lambda prompt, cwd, mcp=None: None)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    (tmp_path / "repo" / task_context.DIR).mkdir(parents=True)

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is False


def test_plan_stage_succeeds_when_file_written(monkeypatch, tmp_path):
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)

    def fake_claude(prompt, cwd, mcp=None):
        (harness / task_context.PLAN).write_text("# План\n\n### Task 1\n", encoding="utf-8")

    monkeypatch.setattr(a, "_run_claude", fake_claude)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is True


def test_empty_plan_file_counts_as_failure(monkeypatch, tmp_path):
    """Пустой файл выглядит доставленным — самый дорогой вид отказа."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)
    monkeypatch.setattr(a, "_run_claude",
                        lambda prompt, cwd, mcp=None:
                            (harness / task_context.PLAN).write_text("  \n", encoding="utf-8"))
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is False
