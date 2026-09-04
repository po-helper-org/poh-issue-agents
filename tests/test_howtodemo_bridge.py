"""Мост к HowToDemo-Agent: что именно Harness даёт приёмщику.

Три вещи — installation-токен GitHub App, клиент модели для трансляции сценария
в план и тело задачи с критерием в форме, которую приёмщик признаёт (#301).
Вердикт приёмки агент считает сам, кодом.
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


class _FakePort:
    """Подделка порта GitHub: помнит вызовы и отдаёт заданное тело."""

    def __init__(self, body: str = ""):
        self.body = body
        self.calls: list[tuple] = []

    def issue_body(self, repo, number):
        self.calls.append(("issue_body", repo, number))
        return self.body

    def add_label(self, repo, number, label):
        self.calls.append(("add_label", repo, number, label))


def test_issue_body_reaches_the_agent_with_the_criterion_exposed(bridge):
    """Ради этого мост и трогает порт: приёмщик о размеченном блоке не знает."""
    from poh_howtodemo import anchor

    from shared import issue_blocks

    raw = issue_blocks.write("## Что происходит\n\nОписание.",
                             issue_blocks.HOWTODEMO, "было — А; стало — Б")
    inner = _FakePort(raw)
    port = bridge._CriterionFirst(inner)

    assert anchor.extract_block(raw) is None
    assert anchor.extract_block(port.issue_body("o/r", 171)) == "было — А; стало — Б"
    assert inner.calls == [("issue_body", "o/r", 171)]


def test_body_without_a_criterion_passes_through_unchanged(bridge):
    inner = _FakePort("Обычное тело без сценария.")
    assert bridge._CriterionFirst(inner).issue_body("o/r", 1) == \
        "Обычное тело без сценария."


def test_other_port_methods_are_delegated(bridge):
    """Оборачивается ОДИН метод; остальную поверхность порта терять нельзя."""
    inner = _FakePort()
    port = bridge._CriterionFirst(inner)
    port.add_label("o/r", 1, "demo:ok")
    assert inner.calls == [("add_label", "o/r", 1, "demo:ok")]


def test_install_wraps_the_github_port_and_keeps_the_model(bridge, monkeypatch):
    """`ports.configure` присваивает все три порта разом.

    Вызов с одним лишь `github` обнулил бы модель, и приёмка упала бы не на
    установке, а много позже — на трансляции сценария, «порт модели не
    подставлен». Проверяем оба порта после `install`, а не один.
    """
    from poh_howtodemo import ports

    saved = (ports._github, ports._llm, ports._shell)
    monkeypatch.setattr(bridge.github_client, "auth_token", lambda repo: "ghs_x")
    try:
        bridge.install()
        assert isinstance(ports.github(), bridge._CriterionFirst)
        assert isinstance(ports.llm(), bridge.PlanTranslator)
    finally:
        ports.configure(*saved)
