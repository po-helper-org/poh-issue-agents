"""Клиент LLM — единственная точка, через которую ходят все структурированные
стадии (gate, classify, duplicate, priority). Сеть не трогаем: проверяем
параметры вызова и поведение на сбое провайдера."""

import importlib

import pytest


@pytest.fixture
def llm_module(monkeypatch):
    """Свежий модуль с очищенным кэшем клиента и без реальных кредов."""
    monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    import llm

    module = importlib.reload(llm)
    module._client = None
    return module


class FakeCompletions:
    def __init__(self, sink: dict, error: Exception | None = None) -> None:
        self._sink = sink
        self._error = error

    def create(self, **kwargs):
        self._sink.update(kwargs)
        if self._error:
            raise self._error
        return {"ok": True}


class FakeInstructor:
    def __init__(self, sink: dict, error: Exception | None = None) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions(sink, error)})()


def _wire(monkeypatch, llm_module, sink, error=None):
    created = []

    def fake_from_openai(client, mode=None):
        created.append(mode)
        return FakeInstructor(sink, error)

    monkeypatch.setattr(llm_module.instructor, "from_openai", fake_from_openai)
    monkeypatch.setattr(llm_module, "OpenAI", lambda **kwargs: kwargs)
    return created


def test_extract_passes_prompt_and_model(monkeypatch, llm_module):
    sink: dict = {}
    _wire(monkeypatch, llm_module, sink)

    llm_module.extract("системный", "пользовательский", dict, model="glm-test")

    assert sink["model"] == "glm-test"
    assert sink["response_model"] is dict
    assert sink["messages"][0] == {"role": "system", "content": "системный"}
    assert sink["messages"][1] == {"role": "user", "content": "пользовательский"}


def test_extract_retries_on_schema_mismatch(monkeypatch, llm_module):
    """max_retries — единственная защита от невалидного ответа модели: без него
    стадия падала бы на первом же нарушении схемы."""
    sink: dict = {}
    _wire(monkeypatch, llm_module, sink)

    llm_module.extract("s", "u", dict)

    assert sink["max_retries"] == 2


def test_client_uses_json_mode(monkeypatch, llm_module):
    """z.ai GLM отвергает OpenAI tool-calling (400 Invalid API parameter) —
    режим JSON тут не стилистический выбор, а условие работоспособности."""
    sink: dict = {}
    created = _wire(monkeypatch, llm_module, sink)

    llm_module.extract("s", "u", dict)

    assert created == [llm_module.instructor.Mode.JSON]


def test_client_is_built_once(monkeypatch, llm_module):
    """Клиент кэшируется: на бэкфилле стадии зовутся сотни раз."""
    sink: dict = {}
    created = _wire(monkeypatch, llm_module, sink)

    llm_module.extract("s", "u", dict)
    llm_module.extract("s", "u", dict)

    assert len(created) == 1


def test_provider_error_propagates(monkeypatch, llm_module):
    """Сбой провайдера обязан дойти до activity: её ретраит Temporal, а
    проглоченная ошибка превратилась бы в пустой результат стадии."""
    sink: dict = {}
    _wire(monkeypatch, llm_module, sink, error=RuntimeError("429 rate limit"))

    with pytest.raises(RuntimeError, match="429"):
        llm_module.extract("s", "u", dict)


def test_default_model_is_the_cheap_one(monkeypatch, llm_module):
    """Умолчание — дешёвая модель: gate прогоняется по каждому Issue."""
    sink: dict = {}
    _wire(monkeypatch, llm_module, sink)

    llm_module.extract("s", "u", dict)

    assert sink["model"] == llm_module.MODEL_GATE


def test_missing_credentials_fail_loudly(monkeypatch):
    """Пустой ZAI_API_KEY — конфигурационная ошибка, и она обязана называть
    себя, а не превращаться в невнятный сбой стадии."""
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_BASE_URL", raising=False)
    import llm

    module = importlib.reload(llm)
    module._client = None

    with pytest.raises(KeyError):
        module.get_client()
