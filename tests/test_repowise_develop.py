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


# --- Забор транскрипта воркером (FR-18) ---
#
# Забор возложен на воркер, а не на раннер, именно потому, что раннер к этому
# моменту мёртв: файл, записанный им, при аварийном завершении был бы потерян —
# а диалог полезен ровно тогда, когда разбирают неудачный прогон.

import activities
from shared.workflow_types import IssueInput


def _issue(number: int = 42) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def test_transcript_fetched_by_session_of_develop_agent(monkeypatch):
    fetched = []

    def fake_transcript(session):
        fetched.append(session)
        return "# Диалог\n\nход 1\n"

    monkeypatch.setattr(activities.repowise, "transcript", fake_transcript)
    text = activities._collect_dev_dialog("o/r", 42, run_failed=True)
    assert fetched == [repowise.session_id("o/r", 42, repowise.DEVELOP)]
    assert "ход 1" in text


def test_empty_session_yields_marked_artifact(monkeypatch):
    monkeypatch.setattr(activities.repowise, "transcript", lambda session: None)
    text = activities._collect_dev_dialog("o/r", 42, run_failed=False)
    assert "обращений к индексу не было" in text
    assert "o/r#42" in text


def test_failed_run_is_named_in_empty_artifact(monkeypatch):
    # Разбирающему прогон важно отличить «агент не спросил» от «агент упал
    # раньше, чем успел спросить».
    monkeypatch.setattr(activities.repowise, "transcript", lambda session: None)
    text = activities._collect_dev_dialog("o/r", 42, run_failed=True)
    assert "аварийно" in text


def test_publication_never_masks_agent_failure(monkeypatch):
    """Публикация диалога — best-effort и не подменяет собой исход прогона.

    Иначе сбой публикации артефакта выглядел бы как сбой разработки, и разбор
    начинали бы не с того места.
    """
    monkeypatch.setattr(activities.repowise, "enabled", lambda: True)
    monkeypatch.setattr(activities.repowise, "transcript", lambda session: "# Диалог\n")

    def boom(*a, **k):
        raise RuntimeError("GitHub недоступен")

    monkeypatch.setattr(activities.github_client, "post_comment", boom)
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch", boom)

    # Не поднимает — значит исход прогона агента останется тем, чем был.
    activities._publish_dev_dialog_sync(_issue(), "research/issue-42")


def test_publication_skipped_when_integration_disabled(monkeypatch):
    monkeypatch.setattr(activities.repowise, "enabled", lambda: False)
    called = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a, **k: called.append("comment"))
    activities._publish_dev_dialog_sync(_issue(), "")
    assert called == []


# --- Правила обращения к индексу в постановке (FR-19) ---

def test_rules_tell_agent_to_ask_before_and_when_stuck():
    text = activities._DEV_REPOWISE_RULES
    assert "До начала работы" in text
    assert "При затруднении" in text
    # Недоступный индекс не должен читаться агентом как повод остановиться.
    assert "штатный режим" in text


def test_rules_do_not_ask_agent_to_retell_the_dialog():
    # Транскрипт ведёт прокси. Просьба пересказать его вернула бы ровно тот
    # класс отказов, ради которого журнал и вынесен наружу.
    assert "пересказывать" in activities._DEV_REPOWISE_RULES
