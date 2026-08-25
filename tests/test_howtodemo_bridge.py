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
def bridge():
    import howtodemo_bridge

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
    assert calls["user"] == "1. открываю корзину\n2. вижу итог"


def test_prompt_comes_from_the_agent_package_not_from_this_repository(bridge,
                                                                     monkeypatch):
    """Промпт — часть договора агента с моделью. Копия здесь отстанет."""
    from poh_howtodemo import plan

    calls = {}
    monkeypatch.setattr(bridge.llm, "complete",
                        lambda system, user, **kw: calls.update(system=system)
                        or '{"steps": []}')
    bridge.PlanTranslator().translate(["шаг"])
    assert calls["system"] == plan.system_prompt()
    assert not (ROOT / "prompts" / "system_howtodemo_plan.md").exists(), \
        "копия промпта в этом репозитории должна быть удалена"


def test_translator_uses_complete_not_extract(bridge, monkeypatch):
    """`extract` навязал бы схему и ретраи; разбор плана делает сам агент."""
    monkeypatch.setattr(bridge.llm, "extract",
                        lambda *a, **kw: pytest.fail("extract звать нельзя"))
    monkeypatch.setattr(bridge.llm, "complete",
                        lambda *a, **kw: '{"steps": []}')
    bridge.PlanTranslator().translate(["шаг"])
