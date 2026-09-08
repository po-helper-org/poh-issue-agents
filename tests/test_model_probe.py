"""Замерялка моделей: то, что в ней есть своего.

Сеть здесь не трогается — подменяются `llm.extract` и `llm.complete`. Проверяется
не то, как отвечает модель, а то, как замер читает её ответ: спутанный исход
обязан быть виден, отказ провайдера — стать строкой в отчёте, а не сбоем
скрипта.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("model_probe", ROOT / "scripts" / "model_probe.py")
probe_mod = importlib.util.module_from_spec(_spec)
sys.modules["model_probe"] = probe_mod
_spec.loader.exec_module(probe_mod)

import llm  # noqa: E402


def _answers(monkeypatch, statuses, category="FEATURE", text="ответ"):
    """Модель отвечает заданным исходом на каждые ворота по очереди."""
    seq = iter(statuses)

    def fake_extract(system, message, response_model, model=""):
        obj = types.SimpleNamespace()
        if "status" in getattr(response_model, "model_fields", {}):
            obj.status = next(seq)
        else:
            obj.category = category
        obj._raw_response = types.SimpleNamespace(
            usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5))
        return obj

    monkeypatch.setattr(llm, "extract", fake_extract)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: text)


def test_the_three_gates_cover_the_three_outcomes():
    """Контур ветвится на закрыть / спросить / пропустить. Замер, проверяющий
    два исхода из трёх, пропустил бы модель, которая всегда отвечает одинаково."""
    assert {expected for _, _, expected in probe_mod.GATE_CASES} == {
        "SPAM", "VAGUE", "SUFFICIENT"}


def test_a_model_that_answers_correctly_passes(monkeypatch):
    _answers(monkeypatch, ["SPAM", "VAGUE", "SUFFICIENT"])

    row = probe_mod.probe("модель-хорошая")

    assert row["error"] == ""
    assert [ok for _, _, ok in row["gate"]] == [True, True, True]
    assert row["classify"] == "FEATURE"
    assert row["tokens_in"] == 40 and row["tokens_out"] == 20     # трое ворот + классификация


def test_a_confused_model_is_reported_wrong_not_broken(monkeypatch):
    """Модель ответила, но не то. Это не отказ — это негодность, и в отчёте
    она обязана отличаться от отказа: чинить их надо по-разному."""
    _answers(monkeypatch, ["SUFFICIENT", "VAGUE", "SUFFICIENT"])

    row = probe_mod.probe("модель-путает")

    assert row["error"] == ""
    assert [ok for _, _, ok in row["gate"]] == [False, True, True]


def test_a_refusal_becomes_a_row_not_a_crash(monkeypatch):
    """Недоступная на тарифе модель, отвергнутая схема и таймаут одинаково
    означают «не годится». Уронив скрипт, первый же отказ лишил бы замера всех
    кандидатов после него."""
    def boom(*a, **k):
        raise RuntimeError("model not available on this plan")

    monkeypatch.setattr(llm, "extract", boom)

    row = probe_mod.probe("модель-недоступная")

    assert "RuntimeError" in row["error"]
    assert "not available" in row["error"]
    assert row["gate"] == []


def test_usage_reads_both_shapes():
    """Instructor прячет сырой ответ в `_raw_response`, прямой вызов держит
    usage на себе. Прочитав одну форму, замер молча показал бы ноль токенов."""
    usage = types.SimpleNamespace(prompt_tokens=7, completion_tokens=3)

    wrapped = types.SimpleNamespace(_raw_response=types.SimpleNamespace(usage=usage))
    direct = types.SimpleNamespace(usage=usage)

    assert probe_mod._usage(wrapped) == (7, 3)
    assert probe_mod._usage(direct) == (7, 3)
    assert probe_mod._usage(types.SimpleNamespace()) == (0, 0)


def test_the_prompts_are_the_ones_the_contour_uses():
    """Замер на своём промпте мерил бы не ту работу."""
    assert probe_mod._prompt("system_intake_gate.md") == \
        (ROOT / "prompts" / "system_intake_gate.md").read_text(encoding="utf-8")


def test_an_unknown_prompt_says_so():
    with pytest.raises(SystemExit) as e:
        probe_mod._prompt("нет-такого.md")

    assert "нет-такого.md" in str(e.value)


def test_the_report_names_the_cheapest_that_passed(monkeypatch, capsys):
    """Ответ на вопрос «какую ставить» — это одна строка отчёта, и она обязана
    брать ПЕРВУЮ прошедшую в заданном порядке, а не первую замеренную: порядок
    задаёт человек по своему тарифу, и негодная дешёвая модель ответом не
    является.
    """
    rows = {
        "дешёвая-негодная": {"model": "дешёвая-негодная", "gate": [("a", "SPAM", False)],
                             "classify": "BUG", "complete": "x",
                             "tokens_in": 1, "tokens_out": 1, "seconds": 0.1, "error": ""},
        "средняя-годная": {"model": "средняя-годная",
                           "gate": [(n, e, True) for n, _, e in probe_mod.GATE_CASES],
                           "classify": "FEATURE", "complete": "x",
                           "tokens_in": 20, "tokens_out": 10, "seconds": 0.2, "error": ""},
        "дорогая-годная": {"model": "дорогая-годная",
                           "gate": [(n, e, True) for n, _, e in probe_mod.GATE_CASES],
                           "classify": "FEATURE", "complete": "x",
                           "tokens_in": 99, "tokens_out": 50, "seconds": 0.3, "error": ""},
    }
    monkeypatch.setattr(probe_mod, "probe", lambda m: rows[m])
    monkeypatch.setenv("ZAI_BASE_URL", "http://example.invalid")
    monkeypatch.setenv("ZAI_API_KEY", "не-настоящий")
    monkeypatch.setattr(sys, "argv",
                        ["model_probe.py", "дешёвая-негодная", "средняя-годная", "дорогая-годная"])

    assert probe_mod.main() == 0

    out = capsys.readouterr().out
    assert "Самая дешёвая из прошедших" in out
    assert "средняя-годная" in out.split("Самая дешёвая из прошедших")[1]


def test_without_credentials_the_report_says_what_is_missing(monkeypatch, capsys):
    """Замер без ключа — не пустая таблица, а внятный отказ: иначе он выглядит
    как «все модели не годятся»."""
    monkeypatch.delenv("ZAI_BASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["model_probe.py"])

    assert probe_mod.main() == 2
    assert "ZAI_BASE_URL" in capsys.readouterr().out
