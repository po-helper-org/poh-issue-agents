"""Доступ одноразового контейнера разработки к индексу.

Проверяем ровно ту границу, которую нельзя ослабить: контейнер получает адрес
прокси и токен на чтение индекса — и ничего сверх того. Токен при этом не
должен попасть в постановку: она собирается дословно и публикуется артефактом.

Способ доставки конфигурации выбран по спайку FR-16
(`docs/spikes/2026-08-19-openhands-mcp-config.md`): агент читает
`$HOME/.openhands/mcp.json`, поэтому HOME переставляется в каталог задачи на
общем томе — образ при этом не трогается и обёртка над ENTRYPOINT не нужна.
"""

import json

import pytest

from shared import develop, repowise


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch):
    monkeypatch.setenv("REPOWISE_PROXY_URL", "http://proxy:7400")
    monkeypatch.setenv("REPOWISE_AGENT_TOKEN", "tok-secret")


def test_runner_joins_proxy_network():
    command = develop.runner_command("slug", image="i", volume="v", mount="/m",
                                     network="poh-harness-net")
    assert "--network" in command
    assert "poh-harness-net" in command


def test_no_network_flag_without_setting():
    command = develop.runner_command("slug", image="i", volume="v", mount="/m")
    assert "--network" not in command


def test_home_points_at_task_dir_when_given():
    command = develop.runner_command("slug", image="i", volume="v", mount="/m",
                                     home="/m/slug")
    assert "HOME=/m/slug" in command


def test_home_absent_by_default():
    # Без интеграции поведение раннера не меняется вовсе: HOME остаётся тем,
    # что задан образом.
    command = develop.runner_command("slug", image="i", volume="v", mount="/m")
    assert not any(str(a).startswith("HOME=") for a in command)


def test_config_path_matches_spike():
    assert develop.MCP_CONFIG_DIR == ".openhands"
    assert develop.MCP_CONFIG_NAME == "mcp.json"


def test_proxy_network_from_env(monkeypatch):
    monkeypatch.setenv("REPOWISE_NETWORK", "  poh-harness-net  ")
    assert develop.proxy_network() == "poh-harness-net"
    monkeypatch.delenv("REPOWISE_NETWORK")
    assert develop.proxy_network() == ""


def test_token_lives_in_config_not_in_statement():
    # Постановка собирается воркером и публикуется дословно — токену там не
    # место. В конфигурации он есть, и это единственное место, где он есть.
    config = repowise.openhands_mcp_config("o/r", 42, repowise.DEVELOP)
    statement = "# Задача: реализовать Issue #42\n\nтело\n"
    assert "tok-secret" in json.dumps(config)
    assert "tok-secret" not in statement


def test_runner_still_gets_no_github_token():
    # Граница, которую задача не должна ослабить: ключ GitHub раннеру не
    # передаётся ни при каких настройках Repowise.
    command = develop.runner_command("slug", image="i", volume="v", mount="/m",
                                     network="net", home="/m/slug")
    joined = " ".join(command)
    assert "GITHUB" not in joined
    assert "GH_TOKEN" not in joined
