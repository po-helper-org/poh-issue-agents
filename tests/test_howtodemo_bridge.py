"""Мост к HowToDemo-Agent: что именно Harness даёт приёмщику.

Ровно две вещи — installation-токен GitHub App и клиент модели для трансляции
сценария в план. Вердикт приёмки агент считает сам, кодом.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    (tmp_path / "system_howtodemo_plan.md").write_text(
        "СИСТЕМНЫЙ ПРОМПТ ПЛАНА", encoding="utf-8")
    import howtodemo_bridge

    monkeypatch.setattr(howtodemo_bridge, "PROMPTS_DIR", tmp_path)
    return howtodemo_bridge


def test_token_provider_takes_a_repository(bridge, monkeypatch):
    """Контракт провайдера в контуре — auth_token(repo)."""
    seen = []
    monkeypatch.setattr(bridge.github_client, "auth_token",
                        lambda repo: seen.append(repo) or "ghs_x")
    assert bridge.token_provider("o/r") == "ghs_x"
    assert seen == ["o/r"]


def test_translator_numbers_the_scenario_for_the_model(bridge, monkeypatch):
    calls = {}

    def fake_complete(system, user, *, model, max_tokens=0, temperature=0.2):
        calls.update(system=system, user=user, model=model)
        return '{"steps": []}'

    monkeypatch.setattr(bridge.llm, "complete", fake_complete)
    out = bridge.PlanTranslator().translate(["открываю корзину", "вижу итог"])
    assert out == '{"steps": []}'
    assert calls["system"] == "СИСТЕМНЫЙ ПРОМПТ ПЛАНА"
    assert calls["user"] == "1. открываю корзину\n2. вижу итог"


def test_translator_uses_complete_not_extract(bridge, monkeypatch):
    """`extract` навязал бы схему и ретраи; разбор плана делает сам агент."""
    monkeypatch.setattr(bridge.llm, "extract",
                        lambda *a, **kw: pytest.fail("extract звать нельзя"))
    monkeypatch.setattr(bridge.llm, "complete",
                        lambda *a, **kw: '{"steps": []}')
    bridge.PlanTranslator().translate(["шаг"])
