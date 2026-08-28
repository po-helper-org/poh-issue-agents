"""Пустой прогон агента: отличать отказ окружения от бездействия.

Живой случай `poh-demo-checkout#151` (2026-08-25): Repowise был настроен, но
его прокси лежал. Контур записал конфигурацию MCP по флагу, OpenHands умер на
инициализации — каталог событий разговора остался ПУСТ, — а задача получила
«агент не изменил ни одного файла». Человек пошёл разбирать постановку вместо
инфраструктуры.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

from shared import develop  # noqa: E402


def _conversation(task_dir: Path, with_events: bool) -> None:
    events = (task_dir / develop.MCP_CONFIG_DIR / "conversations" / "abc123"
              / "events")
    events.mkdir(parents=True)
    if with_events:
        (events / "0001.json").write_text('{"kind": "message"}', encoding="utf-8")


# --- диагноз ---

def test_agent_that_never_moved_is_not_blamed_for_inaction(tmp_path):
    _conversation(tmp_path, with_events=False)
    reason = develop.empty_run_reason(tmp_path)
    assert reason == develop.NEVER_STARTED
    assert "отказ окружения" in reason


def test_agent_that_worked_and_changed_nothing_is_reported_as_such(tmp_path):
    _conversation(tmp_path, with_events=True)
    assert develop.empty_run_reason(tmp_path) == develop.NO_CHANGES


def test_missing_conversation_counts_as_never_started(tmp_path):
    """Разговора нет вовсе — раннер не дошёл даже до его создания."""
    assert develop.empty_run_reason(tmp_path) == develop.NEVER_STARTED


def test_two_reasons_are_different_texts():
    """Иначе различать их в отчёте человеку нечем."""
    assert develop.NEVER_STARTED != develop.NO_CHANGES


# --- предполётная проверка ресурсов ---

def test_run_is_refused_when_the_host_is_out_of_memory(monkeypatch):
    monkeypatch.setenv("DEVELOP_MIN_FREE_MB", "600")
    monkeypatch.setattr(develop, "free_memory_mb", lambda: 120)
    shortage = develop.resource_shortage()
    assert "120" in shortage and "600" in shortage
    assert "OOM" in shortage


def test_enough_memory_means_no_objection(monkeypatch):
    monkeypatch.setenv("DEVELOP_MIN_FREE_MB", "600")
    monkeypatch.setattr(develop, "free_memory_mb", lambda: 2048)
    assert develop.resource_shortage() == ""


def test_check_is_switched_off_by_zero(monkeypatch):
    """Порог — не догма: на машине с другим профилем его выключают."""
    monkeypatch.setenv("DEVELOP_MIN_FREE_MB", "0")
    monkeypatch.setattr(develop, "free_memory_mb", lambda: 1)
    assert develop.resource_shortage() == ""


def test_unmeasurable_memory_does_not_block_the_run(monkeypatch):
    """Не смогли измерить — не повод отказывать: раньше прогон шёл и так."""
    monkeypatch.setenv("DEVELOP_MIN_FREE_MB", "600")
    monkeypatch.setattr(develop, "free_memory_mb", lambda: -1)
    assert develop.resource_shortage() == ""


def test_broken_threshold_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("DEVELOP_MIN_FREE_MB", "не число")
    assert develop.min_free_mb() == develop.DEFAULT_MIN_FREE_MB


# --- настроенный, но мёртвый Repowise ---

@pytest.fixture
def acts(monkeypatch):
    import activities

    monkeypatch.setattr(activities.repowise, "enabled", lambda: True)
    return activities


def _issue():
    from shared.workflow_types import IssueInput

    return IssueInput(repo="o/r", issue_number=151, title="t", body="b",
                      author_login="human", author_type="User")


def test_dead_proxy_means_no_mcp_config_at_all(acts, monkeypatch, tmp_path):
    """Конфиг по мёртвому адресу убивает раннер на инициализации."""
    monkeypatch.setattr(acts.repowise, "available", lambda timeout=0: False)
    acts._write_runner_mcp_config(_issue(), tmp_path)
    assert not (tmp_path / develop.MCP_CONFIG_DIR / develop.MCP_CONFIG_NAME).exists()


def test_live_proxy_still_gets_its_config(acts, monkeypatch, tmp_path):
    monkeypatch.setattr(acts.repowise, "available", lambda timeout=0: True)
    acts._write_runner_mcp_config(_issue(), tmp_path)
    config = tmp_path / develop.MCP_CONFIG_DIR / develop.MCP_CONFIG_NAME
    assert config.exists() and "mcpServers" in config.read_text(encoding="utf-8")


def test_disabled_integration_writes_nothing_as_before(acts, monkeypatch, tmp_path):
    monkeypatch.setattr(acts.repowise, "enabled", lambda: False)
    monkeypatch.setattr(acts.repowise, "available",
                        lambda timeout=0: pytest.fail("живость не спрашивают"))
    acts._write_runner_mcp_config(_issue(), tmp_path)
    assert not (tmp_path / develop.MCP_CONFIG_DIR).exists()
