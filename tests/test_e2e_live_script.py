"""Логика живого E2E-скрипта.

Сам прогон требует настоящих GitHub, Temporal и модели, поэтому в CI не идёт.
Но решения скрипта — что считать успехом, когда прекращать ожидание, куда
смотреть при отказе — обязаны быть проверены здесь: упасть на собственной
ошибке вместо проблемы сервиса значит потратить живой прогон впустую.
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import e2e_live  # noqa: E402


# --- выбор репозитория ---

def test_explicit_repo_wins(monkeypatch):
    monkeypatch.setenv("E2E_REPO", "from/env")
    assert e2e_live.resolve_repo("owner/name") == "owner/name"


def test_falls_back_to_e2e_repo(monkeypatch):
    monkeypatch.setenv("E2E_REPO", "momento-box-org/cortex")
    monkeypatch.setenv("GITHUB_REPOSITORY", "other/thing")
    assert e2e_live.resolve_repo(None) == "momento-box-org/cortex"


def test_falls_back_to_github_repository(monkeypatch):
    monkeypatch.delenv("E2E_REPO", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    assert e2e_live.resolve_repo(None) == "acme/widgets"


def test_no_repo_configured(monkeypatch):
    monkeypatch.delenv("E2E_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert e2e_live.resolve_repo(None) == ""


# --- ожидания сценариев ---

def test_triage_expects_classification_and_priority():
    scenario = e2e_live.triage_scenario()

    assert e2e_live.unmet(scenario, []) == scenario.expectations
    assert e2e_live.unmet(scenario, ["advisor:feature-request"])  # приоритета ещё нет
    assert not e2e_live.unmet(scenario, ["advisor:feature-request", "priority:P2"])


def test_label_command_expects_done_and_removed_run_label():
    scenario = e2e_live.label_command_scenario()

    # прогон идёт: метка запуска ещё висит, исхода нет
    assert len(e2e_live.unmet(scenario, ["run:estimate"])) == 2
    # прогон закончился: исход есть, метка снята
    assert not e2e_live.unmet(scenario, ["done:estimate", "estimated"])


def test_label_matching_is_case_insensitive():
    scenario = e2e_live.triage_scenario()
    assert not e2e_live.unmet(scenario, ["Advisor:Bug", "Priority:P1"])


# --- ранний выход по метке неуспеха ---

def test_failed_run_stops_waiting():
    """Ждать до таймаута бессмысленно: ответ получен, просто отрицательный."""
    scenario = e2e_live.label_command_scenario()

    assert e2e_live.failure_detected(scenario, ["failed:estimate"]) is not None


def test_triage_error_stops_waiting():
    scenario = e2e_live.triage_scenario()

    assert e2e_live.failure_detected(scenario, ["advisor:error"]) is not None


def test_normal_progress_is_not_a_failure():
    scenario = e2e_live.triage_scenario()

    assert e2e_live.failure_detected(scenario, ["advisor:feature-request"]) is None


# --- цикл ожидания ---

def _github_returning(sequences: list[list[str]], monkeypatch):
    """Отдаёт метки по шагам: имитирует постепенную разметку Issue."""
    calls = {"n": 0}

    def fake_get_issue(repo, number):
        index = min(calls["n"], len(sequences) - 1)
        calls["n"] += 1
        return {"labels": [{"name": name} for name in sequences[index]]}

    monkeypatch.setattr(e2e_live.github_client, "get_issue", fake_get_issue)
    monkeypatch.setattr(e2e_live.time, "sleep", lambda _: None)
    return calls


def test_wait_succeeds_once_labels_appear(monkeypatch):
    scenario = e2e_live.triage_scenario()
    _github_returning([[], ["advisor:bug"], ["advisor:bug", "priority:P1"]], monkeypatch)

    ok, labels = e2e_live.wait_for("o/r", 1, scenario, timeout_sec=60, poll_sec=0,
                                   log=lambda _: None)

    assert ok is True
    assert "priority:P1" in labels


def test_wait_gives_up_and_reports_last_state(monkeypatch):
    """Таймаут обязан вернуть фактические метки: по ним и ставится диагноз."""
    scenario = e2e_live.triage_scenario()
    _github_returning([["advisor:bug"]], monkeypatch)

    ok, labels = e2e_live.wait_for("o/r", 1, scenario, timeout_sec=0, poll_sec=0,
                                   log=lambda _: None)

    assert ok is False
    assert labels == [] or "advisor:bug" in labels


def test_wait_stops_early_on_failure_label(monkeypatch):
    scenario = e2e_live.label_command_scenario()
    calls = _github_returning([["run:estimate"], ["failed:estimate"]], monkeypatch)

    ok, labels = e2e_live.wait_for("o/r", 1, scenario, timeout_sec=600, poll_sec=0,
                                   log=lambda _: None)

    assert ok is False
    assert calls["n"] == 2, "после метки неуспеха опрос должен прекратиться"


# --- защита от бессмысленных запусков ---

def test_refuses_without_repo(monkeypatch, capsys):
    monkeypatch.delenv("E2E_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert asyncio.run(e2e_live.main(["triage"])) == 2


def test_refuses_under_dry_run(monkeypatch):
    """DRY_RUN подавляет мутации: прогон был бы зелёным ни о чём."""
    monkeypatch.setenv("E2E_REPO", "acme/widgets")
    monkeypatch.setenv("DRY_RUN", "1")

    assert asyncio.run(e2e_live.main(["triage"])) == 2


def test_stops_when_temporal_is_unreachable(monkeypatch):
    """Без кластера прогон не стартует, а симптом в GitHub — просто тишина."""
    monkeypatch.setenv("E2E_REPO", "acme/widgets")
    monkeypatch.delenv("DRY_RUN", raising=False)

    async def boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(e2e_live, "check_temporal", boom)

    def no_issue(*a, **k):
        raise AssertionError("Issue не должен заводиться до проверки Temporal")

    monkeypatch.setattr(e2e_live.github_client, "create_issue", no_issue)

    assert asyncio.run(e2e_live.main(["triage"])) == 2


@pytest.mark.timeout(30)
def test_service_issue_is_closed_even_when_run_fails(monkeypatch):
    """Служебная задача не должна оставаться в бэклоге после неудачи."""
    monkeypatch.setenv("E2E_REPO", "acme/widgets")
    monkeypatch.delenv("DRY_RUN", raising=False)
    closed = []

    async def ok():
        return "temporal:7233/default"

    async def start(*a, **k):
        return "issue-acme/widgets-42"

    monkeypatch.setattr(e2e_live, "check_temporal", ok)
    monkeypatch.setattr(e2e_live, "start_triage", start)
    monkeypatch.setattr(e2e_live.github_client, "create_issue", lambda *a, **k: 42)
    monkeypatch.setattr(e2e_live.github_client, "close_issue",
                        lambda repo, n: closed.append(n))
    monkeypatch.setattr(e2e_live, "wait_for", lambda *a, **k: (False, ["advisor:bug"]))

    assert asyncio.run(e2e_live.main(["triage"])) == 1
    assert closed == [42]


@pytest.mark.timeout(30)
def test_keep_flag_leaves_the_issue_open(monkeypatch):
    monkeypatch.setenv("E2E_REPO", "acme/widgets")
    monkeypatch.delenv("DRY_RUN", raising=False)

    async def ok():
        return "temporal:7233/default"

    async def start(*a, **k):
        return "issue-acme/widgets-42"

    monkeypatch.setattr(e2e_live, "check_temporal", ok)
    monkeypatch.setattr(e2e_live, "start_triage", start)
    monkeypatch.setattr(e2e_live.github_client, "create_issue", lambda *a, **k: 42)

    def no_close(*a, **k):
        raise AssertionError("с --keep задача должна остаться открытой")

    monkeypatch.setattr(e2e_live.github_client, "close_issue", no_close)
    monkeypatch.setattr(e2e_live, "wait_for", lambda *a, **k: (True, ["priority:P2"]))

    assert asyncio.run(e2e_live.main(["triage", "--keep"])) == 0
