"""Контракт клиента MCP-прокси Repowise.

Проверяем ровно те свойства, на которых стоит остальная интеграция:
идентификатор сессии воспроизводим и различает агентов, конфигурация MCP несёт
токен, а сам модуль остаётся чистым — без Temporal и GitHub. Последнее не
придирка к стилю: модуль вызывается и из воркера, и из подготовки каталога
разработки, и лишний импорт втащил бы туда клиент GitHub вместе с токеном.
"""

import pathlib

import pytest

from shared import repowise


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch):
    monkeypatch.setenv("REPOWISE_PROXY_URL", "http://proxy:7400")
    monkeypatch.setenv("REPOWISE_AGENT_TOKEN", "tok-test")
    monkeypatch.setenv("REPOWISE_CONTOUR_REPOS", "po-helper-org/poh-issue-agents")


def test_session_id_is_reproducible():
    a = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    b = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    assert a == b


def test_session_id_distinguishes_agents():
    analysis = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    develop = repowise.session_id("o/r", 42, repowise.DEVELOP)
    assert analysis != develop


def test_session_id_has_no_slash():
    # Идентификатор уезжает в query-параметр прокси; слэш из полного имени
    # репозитория там пришлось бы кодировать на каждой стороне.
    assert "/" not in repowise.session_id("o/r", 42, repowise.ANALYSIS)


def test_workspace_contour_by_mask():
    assert repowise.workspace_for("po-helper-org/poh-issue-agents") == repowise.CONTOUR


def test_workspace_product_is_default():
    assert repowise.workspace_for("po-helper-org/poh-demo-checkout") == repowise.PRODUCT


def test_empty_contour_list_means_everything_is_product(monkeypatch):
    # Пустой список у shared.repos.is_allowed означает «разрешено всё»; для
    # выбора workspace это ровно противоположный смысл, и guard обязателен.
    monkeypatch.setenv("REPOWISE_CONTOUR_REPOS", "")
    assert repowise.workspace_for("po-helper-org/poh-issue-agents") == repowise.PRODUCT


def test_claude_config_carries_token_and_session():
    cfg = repowise.claude_mcp_config("o/r", 42, repowise.ANALYSIS)
    server = cfg["mcpServers"]["repowise"]
    assert server["headers"]["Authorization"] == "Bearer tok-test"
    assert repowise.session_id("o/r", 42, repowise.ANALYSIS) in server["url"]


def test_openhands_config_matches_runner_format():
    # Формат снят со спайка FR-16: docs/spikes/2026-08-19-openhands-mcp-config.md
    cfg = repowise.openhands_mcp_config("o/r", 42, repowise.DEVELOP)
    server = cfg["mcpServers"]["repowise"]
    assert server["transport"] == "http"
    assert server["enabled"] is True
    assert server["headers"]["Authorization"] == "Bearer tok-test"


def test_disabled_without_proxy_url(monkeypatch):
    monkeypatch.delenv("REPOWISE_PROXY_URL")
    assert repowise.enabled() is False


def test_available_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("сеть недоступна")
    monkeypatch.setattr(repowise.urllib.request, "urlopen", boom)
    assert repowise.available() is False


def test_transcript_returns_none_on_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("сеть недоступна")
    monkeypatch.setattr(repowise.urllib.request, "urlopen", boom)
    assert repowise.transcript("rw-analysis-o__r-42") is None


def test_unavailable_artifact_is_not_empty_and_names_reason():
    text = repowise.unavailable_artifact("o/r", 42, repowise.ANALYSIS, "нет соединения")
    assert "нет соединения" in text
    assert "o/r#42" in text
    assert len(text) > 200


def test_module_stays_pure():
    source = pathlib.Path(repowise.__file__).read_text(encoding="utf-8")
    assert "temporalio" not in source
    assert "github_client" not in source


def test_token_absent_from_artifact():
    text = repowise.unavailable_artifact("o/r", 42, repowise.ANALYSIS, "нет соединения")
    assert "tok-test" not in text


def test_max_turns_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("REPOWISE_MAX_TURNS", raising=False)
    assert repowise.max_turns() == repowise.DEFAULT_MAX_TURNS
    monkeypatch.setenv("REPOWISE_MAX_TURNS", "5")
    assert repowise.max_turns() == 5
    # Мусор в переменной не должен снимать потолок вовсе: неограниченный цикл
    # вопросов — это и деньги, и зависший прогон.
    monkeypatch.setenv("REPOWISE_MAX_TURNS", "не число")
    assert repowise.max_turns() == repowise.DEFAULT_MAX_TURNS
