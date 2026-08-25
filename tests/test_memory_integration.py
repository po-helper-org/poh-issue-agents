"""Подключение слоя саморефлексии к контуру.

Главное свойство, которое здесь закреплено: **слой опционален**. Выключенный он
не меняет ни постановку, ни поведение шагов — побайтово.
"""
import json
from pathlib import Path

import pytest

import activities as a
from shared import develop, memory


@pytest.fixture(autouse=True)
def layer_off(monkeypatch):
    monkeypatch.delenv("MEMORY_BASE_URL", raising=False)
    monkeypatch.delenv("MEMORY_BASE_TOKEN", raising=False)


@pytest.fixture
def layer_on(monkeypatch):
    """Слой включён и отдаёт заранее известный блок."""
    block = "\nПравила и накопленный опыт этой организации:\n- красные тесты не публикуем"
    monkeypatch.setenv("MEMORY_BASE_URL", "http://memory-api:8090")
    monkeypatch.setattr(memory, "rules",
                        lambda agent, repo="", query="", max_items=None:
                        memory.Rules(text=block, ids=["C-001", "D-001"]))
    return block


# ───────────────────── выключенный слой ─────────────────────

def test_disabled_layer_leaves_the_task_byte_identical(monkeypatch):
    """Постановка без слоя обязана совпадать с постановкой при выключенном слое."""
    parts = ["# Задача: реализовать Issue #42", "## Кнопка", "тело задачи",
             a._DEV_FALLBACK_RULES]
    baseline = a._join_sections(a._split_sections(list(parts)))

    with_layer = list(parts)
    rules = memory.rules(memory.DEVELOP, repo="o/r", query="кнопка")
    if rules.text:
        with_layer.append(rules.text)

    assert a._join_sections(a._split_sections(with_layer)) == baseline


def test_disabled_layer_makes_capture_a_noop():
    assert memory.enabled() is False


def test_disabled_layer_returns_no_rule_ids():
    assert memory.rules(memory.DEVELOP, "o/r").ids == []


# ───────────────────── включённый слой ─────────────────────

def test_enabled_layer_block_reaches_the_task(layer_on):
    parts = ["# Задача: реализовать Issue #42", "тело", a._DEV_FALLBACK_RULES]
    rules = memory.rules(memory.DEVELOP, repo="o/r")
    parts.append(rules.text)
    task = a._join_sections(a._split_sections(parts))
    assert "красные тесты не публикуем" in task


def test_block_survives_section_parsing(layer_on):
    """Блок с решётки стал бы именем секции и исчез — этого быть не должно."""
    parts = ["# Задача: реализовать Issue #1", "тело", layer_on]
    assert "красные тесты не публикуем" in a._join_sections(a._split_sections(parts))


def test_rule_ids_are_returned_for_the_episode(layer_on):
    assert memory.rules(memory.DEVELOP, "o/r").ids == ["C-001", "D-001"]


# ───────────────── перечень подсыпанных правил ─────────────────

def test_injected_rules_are_written_outside_the_clone(tmp_path):
    """Файл лежит в корне задачи, а не в клоне: `git add -A` его не видит."""
    a._write_injected_rules(tmp_path, ["C-001", "D-001"])
    assert (tmp_path / a.INJECTED_RULES_FILE).exists()
    assert a._read_injected_rules(tmp_path) == ["C-001", "D-001"]


def test_missing_injected_rules_file_is_not_an_error(tmp_path):
    assert a._read_injected_rules(tmp_path) == []


def test_broken_injected_rules_file_is_not_an_error(tmp_path):
    (tmp_path / a.INJECTED_RULES_FILE).write_text("не json", encoding="utf-8")
    assert a._read_injected_rules(tmp_path) == []


# ───────────────────── файл намерений ─────────────────────

def test_reflect_note_is_parsed(tmp_path):
    (tmp_path / a.REFLECT_NOTE_FILE).write_text(
        "## Намерение\nпочинить обработчик клика\n\n"
        "## Допущения\n- поле всегда приходит\n- порядок не важен\n\n"
        "## Сомнения\n- не проверил на пустом списке\n", encoding="utf-8")
    got = a._read_reflect_note(tmp_path)
    assert got["intent"] == "починить обработчик клика"
    assert got["assumptions"] == ["поле всегда приходит", "порядок не важен"]
    assert got["uncertainty"] == ["не проверил на пустом списке"]


def test_missing_reflect_note_is_not_an_error(tmp_path):
    """Агент не написал файл — запись уходит без намерения, стадия не срывается."""
    assert a._read_reflect_note(tmp_path) == {}


def test_partial_reflect_note_yields_what_there_is(tmp_path):
    (tmp_path / a.REFLECT_NOTE_FILE).write_text("## Намерение\nтолько это\n",
                                                encoding="utf-8")
    got = a._read_reflect_note(tmp_path)
    assert got["intent"] == "только это"
    assert got["assumptions"] == [] and got["uncertainty"] == []


def test_reflect_note_instruction_is_its_own_block():
    """Правила репозитория подменяются его собственными ЦЕЛИКОМ.

    Пока инструкция жила внутри запасных правил, она доходила только до
    репозиториев БЕЗ своих правил — то есть до самых редких. Найдено живым
    прогоном: демо-репозиторий имеет свои правила, и файл намерений не
    появился ни разу.
    """
    assert a.REFLECT_NOTE_FILE in a._DEV_REFLECT_NOTE_RULE
    assert a.REFLECT_NOTE_FILE not in a._DEV_FALLBACK_RULES


def test_reflect_note_block_is_its_own_contour_section():
    """Своей секцией, а не довеском к соседней.

    Приклеенный блок делит судьбу соседа при усечении — так на прогоне #105
    правила организации утащили за собой инструкции контура.
    """
    secs = a._split_sections([a._DEV_REFLECT_NOTE_RULE])
    assert len(secs) == 1
    assert secs[0][0] == "## След решения"
    assert a.REFLECT_NOTE_FILE in a._join_sections(secs)
    assert a._section_rank("## След решения", 1, "T") == a._RANK_CONTOUR


def test_reflect_note_instruction_survives_repo_own_rules():
    """Свои правила репозитория не должны вытеснять требование контура."""
    parts = ["# Задача: реализовать Issue #1", "тело",
             "## Свои правила репозитория\nделай по-нашему",
             a._DEV_REFLECT_NOTE_RULE]
    task = a._join_sections(a._split_sections(parts))
    assert "делай по-нашему" in task
    assert a.REFLECT_NOTE_FILE in task


# ───────────────── перечень служебных файлов ─────────────────

def test_service_files_list_covers_everything_the_harness_creates():
    """Пропущенный здесь файл — тихо испорченный пул-реквест."""
    assert set(develop.SERVICE_FILES) == {
        ".task.md", ".followups.md", ".verdict.md", ".reflect.md"}


def test_followups_file_constant_is_in_the_list():
    assert develop.FOLLOWUPS_FILE in develop.SERVICE_FILES


def test_reflect_note_is_in_the_list():
    assert a.REFLECT_NOTE_FILE in develop.SERVICE_FILES


def test_clear_service_files_removes_all_and_reports(tmp_path):
    for name in develop.SERVICE_FILES:
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "real_code.py").write_text("код", encoding="utf-8")

    removed = develop.clear_service_files(tmp_path)

    assert sorted(removed) == sorted(develop.SERVICE_FILES)
    assert not any((tmp_path / n).exists() for n in develop.SERVICE_FILES)
    assert (tmp_path / "real_code.py").exists(), "код трогать нельзя"


def test_clear_service_files_is_idempotent(tmp_path):
    assert develop.clear_service_files(tmp_path) == []


# ────────── сигналы, измеренные контуром по ходу прогона ──────────

def test_signals_file_lives_outside_the_clone(tmp_path):
    """`git add -A` его не видит: корень задачи лежит вне рабочего дерева."""
    a._write_signal(tmp_path, "tests_passed", True)
    assert (tmp_path / a.SIGNALS_FILE).exists()
    assert a._read_signals(tmp_path) == {"tests_passed": True}


def test_signals_accumulate_not_overwrite(tmp_path):
    a._write_signal(tmp_path, "tests_passed", False)
    a._write_signal(tmp_path, "fix_rounds", 2)
    assert a._read_signals(tmp_path) == {"tests_passed": False, "fix_rounds": 2}


def test_missing_signals_file_is_not_an_error(tmp_path):
    assert a._read_signals(tmp_path) == {}


def test_broken_signals_file_is_not_an_error(tmp_path):
    (tmp_path / a.SIGNALS_FILE).write_text("не json", encoding="utf-8")
    assert a._read_signals(tmp_path) == {}
    a._write_signal(tmp_path, "tests_passed", True)
    assert a._read_signals(tmp_path) == {"tests_passed": True}


def test_skipped_tests_are_unknown_not_passed(tmp_path, monkeypatch):
    """Пропуск — не успех.

    Иначе свёртка сигналов начнёт хвалить прогоны, в которых тесты не гонялись
    вовсе: пустой `DEVELOP_TEST_COMMAND` засчитался бы как зелёный прогон.
    """
    monkeypatch.delenv("DEVELOP_TEST_COMMAND", raising=False)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    class _I:
        repo, issue_number, title = "o/r", 1, "T"

    a._dev_tests(_I())
    assert a._read_signals(tmp_path) == {"tests_passed": None}


def test_red_tests_record_the_outcome_before_raising(tmp_path, monkeypatch):
    """Красный прогон — самый интересный для разбора. Терять о нём запись
    значит собирать статистику только по удачам."""
    import subprocess as sp

    monkeypatch.setenv("DEVELOP_TEST_COMMAND", "какая-то команда")
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    monkeypatch.setattr(a.subprocess, "run",
                        lambda *x, **k: sp.CompletedProcess(x, 1, "провал", ""))

    class _I:
        repo, issue_number, title = "o/r", 1, "T"

    with pytest.raises(RuntimeError, match="проверки не прошли"):
        a._dev_tests(_I())
    assert a._read_signals(tmp_path) == {"tests_passed": False}


def test_green_tests_record_success(tmp_path, monkeypatch):
    import subprocess as sp

    monkeypatch.setenv("DEVELOP_TEST_COMMAND", "какая-то команда")
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    monkeypatch.setattr(a.subprocess, "run",
                        lambda *x, **k: sp.CompletedProcess(x, 0, "всё зелено", ""))

    class _I:
        repo, issue_number, title = "o/r", 1, "T"

    a._dev_tests(_I())
    assert a._read_signals(tmp_path) == {"tests_passed": True}


def test_signals_file_is_not_committed():
    """Лежит в корне задачи, вне клона — но проверим и перечень служебных."""
    assert a.SIGNALS_FILE.startswith(".")
    assert a.INJECTED_RULES_FILE.startswith(".")


def test_capture_runs_even_when_a_step_fails():
    """Запись об итерации стоит в finally.

    Красные тесты и сорвавшийся прогон агента уносили управление мимо неё, и
    слой видел только удачные прогоны.
    """
    import pathlib
    src = pathlib.Path("worker/workflows.py").read_text(encoding="utf-8")
    block = src[src.index("class IssueDevelopment"):src.index('name="IssuePrFix"')]
    assert "finally:" in block
    assert block.index("finally:") < block.index("capture_episode")
    assert "issue-lifecycle-capture-episode-always" in block
