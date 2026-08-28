"""Стадия построения плана: артефакт проверяется существованием, не словом модели.

Стадия `validate` цепочки FNR объявлена с ожидаемым артефактом None — проверять
нечего, и вердикт пишет сама модель. Здесь так нельзя: план — вход исполнителя.
"""

import asyncio
import time
from pathlib import Path

import pytest

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


def test_plan_file_with_only_invisible_chars_counts_as_failure(monkeypatch, tmp_path):
    """BOM и zero-width space `.strip()` не берёт — тем же способом файл из
    одних невидимых символов проскочил бы как «план написан». Проверка
    обязана распознавать это так же, как состав каталога распознаёт
    остальные файлы `.harness/` (`task_context.missing`)."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)
    monkeypatch.setattr(
        a, "_run_claude",
        lambda prompt, cwd, mcp=None:
            (harness / task_context.PLAN).write_text("﻿​", encoding="utf-8"))
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is False


def test_plan_stage_raises_when_claude_call_fails(monkeypatch, tmp_path):
    """Отказ вызова модели обязан долететь исключением, а не превратиться в
    тихое `False`: если сама попытка не состоялась, писать план некому, и
    явный отказ стадии честнее молчаливого «плана нет»."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)

    def failing_claude(prompt, cwd, mcp=None):
        raise RuntimeError("claude -p exit 1: rate limited")

    monkeypatch.setattr(a, "_run_claude", failing_claude)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    with pytest.raises(RuntimeError, match="rate limited"):
        asyncio.run(a.build_mvp_plan(issue, "research/issue-3"))


def test_plan_stage_heartbeats_during_long_claude(monkeypatch, tmp_path):
    """Долгий `claude -p` обязан слать heartbeat изнутри стадии: сервер
    Temporal считает activity мёртвой по `heartbeat_timeout` воркфлоу (в этом
    файле — 300с), а один прогон модели идёт до `CLAUDE_STAGE_TIMEOUT_SEC`
    (900с). Без периодического сигнала долгий, но живой прогон роняет весь
    цикл — см. докстринг `_run_with_heartbeat`."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)
    beats = []
    monkeypatch.setattr(a.activity, "heartbeat",
                        lambda *args: beats.append(args[0] if args else None))
    monkeypatch.setattr(a, "HEARTBEAT_INTERVAL_SEC", 0.01)

    def slow_claude(prompt, cwd, mcp=None):
        time.sleep(0.05)
        (harness / task_context.PLAN).write_text("# План\n\n### Task 1\n", encoding="utf-8")

    monkeypatch.setattr(a, "_run_claude", slow_claude)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is True
    assert beats  # heartbeat ушёл хотя бы раз, пока claude -p шёл в потоке
