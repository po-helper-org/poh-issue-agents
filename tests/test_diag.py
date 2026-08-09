"""Диагностика конфига: разбор allowlist, вердикт по репозиторию, конфликт
PAT+App и главное — отсутствие значений секретов в выводе."""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import diag  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ISSUE_AGENT_REPOS", "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_APP_ID",
                "GITHUB_PRIVATE_KEY_B64", "GITHUB_PRIVATE_KEY_PATH",
                "GITHUB_WEBHOOK_SECRET", "ZAI_API_KEY", "DRY_RUN"):
        monkeypatch.delenv(var, raising=False)


def _text(repo=None) -> str:
    lines, _ = diag.build_report(repo)
    return "\n".join(lines)


# --- allowlist ---

def test_empty_allowlist_means_everything(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "")
    assert "ЛЮБОЙ репозиторий" in _text()


def test_concrete_and_mask_entries_are_listed(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "acme/widgets,other-org/*")
    text = _text()
    assert "acme/widgets" in text
    assert "other-org" in text


# --- вердикт по репозиторию: исходный вопрос «доедет или нет» ---

def test_repo_outside_allowlist_is_reported_as_filtered(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "acme/widgets")
    text = _text("other/thing")
    assert "ОТФИЛЬТРУЕТСЯ" in text
    assert "ISSUE_AGENT_REPOS" in text  # сказано, что чинить


def test_repo_matched_by_exact_entry(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "acme/widgets")
    text = _text("acme/widgets")
    assert "ДОЕДЕТ" in text
    assert "точная запись" in text


def test_repo_matched_by_owner_mask(monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "acme/*")
    text = _text("acme/anything")
    assert "ДОЕДЕТ" in text
    assert "маска acme/*" in text


# --- авторизация ---

def test_pat_over_app_conflict_is_loud(monkeypatch):
    """Молчаливая подмена App личным токеном — та самая причина, по которой
    комментарии уходят от чужого имени."""
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_value")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    lines, ok = diag.auth_lines()
    text = "\n".join(lines)
    assert "ПЕРЕБИВАЕТ" in text
    assert ok is True  # авторизация рабочая, просто не та, что ожидали


def test_lone_pat_is_not_a_warning(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_value")
    lines, ok = diag.auth_lines()
    assert ok is True
    assert "⚠" not in "\n".join(lines)


def test_app_without_key_is_broken(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    lines, ok = diag.auth_lines()
    assert ok is False
    assert "приватного ключа нет" in "\n".join(lines)


def test_no_auth_at_all_fails(monkeypatch):
    lines, ok = diag.auth_lines()
    assert ok is False
    assert "НЕ НАСТРОЕН" in "\n".join(lines)


# --- секреты ---

def test_secret_values_never_appear_in_output(monkeypatch):
    """Вывод уходит в тикеты и чаты: значения не печатаются никогда."""
    secrets = {
        "GH_TOKEN": "ghp_AAAAAAAAAAAAAAAAAAAA",
        "GITHUB_WEBHOOK_SECRET": "whsec_BBBBBBBBBBBB",
        "GITHUB_PRIVATE_KEY_B64": "LS0tLS1CRUdJTiBSU0E=",
        "ZAI_API_KEY": "zai_CCCCCCCCCCCC",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)

    text = _text("acme/widgets")

    for value in secrets.values():
        assert value not in text
    assert "GH_TOKEN: задан" in text
    assert "ZAI_API_KEY: задан" in text


def test_missing_secrets_are_reported_as_absent():
    assert "GITHUB_WEBHOOK_SECRET: НЕ задан" in _text()


# --- коды возврата ---

def test_exit_code_zero_when_config_is_workable(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    code = asyncio.run(diag.main(["--no-temporal"]))
    assert code == 0


def test_exit_code_one_without_any_auth():
    code = asyncio.run(diag.main(["--no-temporal"]))
    assert code == 1


def test_exit_code_one_when_temporal_unreachable(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")

    async def unreachable():
        return (["  связь: НЕТ — ConnectionError: refused"], False)

    monkeypatch.setattr(diag, "temporal_check_lines", unreachable)
    assert asyncio.run(diag.main([])) == 1
