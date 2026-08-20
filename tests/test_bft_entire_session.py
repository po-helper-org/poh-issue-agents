"""Диалог прогона живёт сессией entire, а `/bft-deep <id>` её продолжает.

Проверено на стенде спайком: `entire enable --agent claude-code` отрабатывает в
контейнере без TTY и без аккаунта, после `claude -p` появляется чекпоинт, а
чекпоинты складываются в ветку `entire/<hash>` — то есть в сам репозиторий.
"""

import subprocess

import pytest

import activities
from shared import bft, commands
from shared.workflow_types import BftRequest


def _req(session_id: str = ""):
    return BftRequest(repo="o/r", issue_number=41, title="t", body="b",
                      mode=bft.DEEP, instructions="", session_id=session_id)


# --- Разбор вывода CLI ---

def test_session_id_is_read_from_listing():
    listing = ("── Sessions ──\n\n"
               "Claude Code · entire-spike · session "
               "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89\n"
               '> "Создай файл hello.md"\nended · tokens 45.2k')
    assert bft.parse_session_id(listing) == "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89"


def test_missing_session_reads_as_empty():
    assert bft.parse_session_id("No sessions found.") == ""


def test_checkpoint_branch_is_found_among_refs():
    refs = "refs/heads/main\nrefs/heads/entire/d5f8977-e3b0c4\nrefs/heads/bft-research/issue-41"
    assert bft.parse_session_branch(refs) == "entire/d5f8977-e3b0c4"


def test_no_checkpoint_branch_reads_as_empty():
    assert bft.parse_session_branch("refs/heads/main\nrefs/heads/dev") == ""


# --- Аргумент команды ---

@pytest.mark.parametrize("tail,expected_id,expected_rest", [
    ("3c6eccc7-c0f6-48a1-afd6-38399b4f1f89", "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89", ""),
    ("3c6eccc7-c0f6-48a1-afd6-38399b4f1f89 и ещё: телефон обязателен",
     "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89", "и ещё: телефон обязателен"),
    ("телефон обязателен", "", "телефон обязателен"),
    ("", "", ""),
])
def test_session_argument_splits_from_instructions(tail, expected_id, expected_rest):
    assert bft.split_session_arg(tail) == (expected_id, expected_rest)


def test_uuid_inside_text_is_not_taken_for_a_command_argument():
    """Цитата прошлого комментария не должна включать режим продолжения."""
    tail = "как в прогоне 3c6eccc7-c0f6-48a1-afd6-38399b4f1f89, только с телефоном"
    session_id, rest = bft.split_session_arg(tail)
    assert session_id == "" and rest == tail


def test_command_builder_puts_session_id_in_its_own_field():
    payload = {
        "repository": {"full_name": "o/r"},
        "issue": {"number": 41, "title": "t", "body": "b"},
        "comment": {"id": 7, "body": "/bft-deep 3c6eccc7-c0f6-48a1-afd6-38399b4f1f89\n"
                                     "телефон обязателен"},
    }
    req = commands.build_bft_request(payload, bft.DEEP)

    assert req.session_id == "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89"
    assert req.instructions == "телефон обязателен", (
        "идентификатор уехал в постановку как требование заказчика")


# --- Блок про сессию в комментарии ---

def test_session_hint_names_branch_and_the_command_to_continue():
    hint = bft.render_session_hint("o/r", "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89",
                                   "entire/d5f8977-e3b0c4")

    assert "entire/d5f8977-e3b0c4" in hint
    assert "/bft-deep 3c6eccc7-c0f6-48a1-afd6-38399b4f1f89" in hint


def test_session_hint_is_empty_without_an_id():
    """Обещать продолжение по идентификатору, которого нет, нельзя."""
    assert bft.render_session_hint("o/r", "", "entire/abc") == ""


# --- Поведение при отказах трекера ---

def test_enable_failure_does_not_break_the_run(monkeypatch, tmp_path, caplog):
    def failing(*a, **kw):
        return subprocess.CompletedProcess(a, 1, "", "entire: not configured")

    monkeypatch.setattr(activities.subprocess, "run", failing)
    activities._enable_entire(str(tmp_path))  # не бросает


def test_missing_binary_does_not_break_the_run(monkeypatch, tmp_path):
    def missing(*a, **kw):
        raise FileNotFoundError("entire")

    monkeypatch.setattr(activities.subprocess, "run", missing)
    activities._enable_entire(str(tmp_path))
    assert activities._entire_session(str(tmp_path)) == ("", "")


def test_session_is_read_from_cli_and_refs(monkeypatch, tmp_path):
    def fake_run(cmd, **kw):
        if cmd[0] == "entire":
            return subprocess.CompletedProcess(
                cmd, 0, "Claude Code · x · session "
                        "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89", "")
        return subprocess.CompletedProcess(cmd, 0, "refs/heads/entire/d5f8977-e3b0c4", "")

    monkeypatch.setattr(activities.subprocess, "run", fake_run)

    assert activities._entire_session(str(tmp_path)) == (
        "3c6eccc7-c0f6-48a1-afd6-38399b4f1f89", "entire/d5f8977-e3b0c4")


def test_branch_push_is_skipped_without_a_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(activities.subprocess, "run",
                        lambda *a, **kw: pytest.fail("пушить нечего"))
    activities._push_entire_branch("o/r", str(tmp_path), "")


def test_resume_survives_a_failing_cli(monkeypatch, tmp_path, caplog):
    """Не поднялась сессия — прогон идёт дальше, но говорит об этом в лог."""
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "session not found")

    monkeypatch.setattr(activities.subprocess, "run", fake_run)
    with caplog.at_level("WARNING"):
        activities._resume_entire_session("o/r", str(tmp_path), "не-та-сессия")

    assert any("не поднята" in r.getMessage() for r in caplog.records)
