import pytest

import activities as a
from shared import acceptance_proposal as ap
from shared.workflow_types import IssueInput


def test_render_option_is_before_and_after():
    option = ap.AcceptanceOption(
        before='GET /quote отвечает 404 {"error":"не найдено"}',
        after="GET /quote отвечает 405 с заголовком Allow: POST")
    rendered = ap.render_option(option)
    assert "было" in rendered.lower() and "стало" in rendered.lower()
    assert "404" in rendered and "405" in rendered


def test_empty_option_list_is_a_refusal():
    """Вопрос без вариантов бесполезен человеку — это отказ модели."""
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=[])


def test_more_than_three_options_is_rejected():
    """Больше трёх человек не читает, он их пролистывает."""
    many = [ap.AcceptanceOption(before=f"было {i}", after=f"стало {i}")
            for i in range(5)]
    with pytest.raises(ValueError):
        ap.AcceptanceOptions(options=many)


def test_prompt_demands_observable_signs():
    assert "наблюдаем" in ap.SYSTEM_PROMPT.lower()


# --- активность propose_acceptance_options: реальное тело, не заглушка ---
#
# Ревью, находка 2 (Important): во всех тестах воркфлоу и активностей
# `propose_acceptance_options` подменена стабом с тем же именем (см.
# `tests/test_workflow_acceptance_gate.py:options_stub`,
# `tests/test_answer_question.py`) — тело самой активности (перехват вокруг
# вызова модели и сборка строк вариантов через `render_option`) до этих
# тестов не исполнялось нигде. Мокаем `llm.extract`, как уже сделано для
# толкования свободного ответа человека в `tests/test_followup_dialog.py`
# (`test_the_answer_is_built_from_the_whole_conversation` и соседние —
# `monkeypatch.setattr(acts.llm, "extract", ...)`), и зовём саму активность
# напрямую: `@activity.defn` не мешает обычному вызову функции вне контекста
# Temporal.


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=1, title="GET /quote отдаёт 404",
                      body="сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


def test_propose_acceptance_options_renders_the_models_options(monkeypatch):
    """Модель ответила — активность возвращает отрендеренные строки
    (`render_option`), а не сырые объекты и не переспрашивает модель."""
    seen: dict = {}

    def fake_extract(system, user_message, model_cls, model=None):
        seen["system"] = system
        seen["user"] = user_message
        seen["model"] = model
        return model_cls(options=[
            ap.AcceptanceOption(before="GET /quote отвечает 404",
                                after="GET /quote отвечает 405 с Allow: POST"),
            ap.AcceptanceOption(before="404 без заголовка Allow",
                                after="405 с заголовком Allow: POST"),
        ])

    monkeypatch.setattr(a.llm, "extract", fake_extract)

    result = a.propose_acceptance_options(_issue())

    assert result == [
        "было — GET /quote отвечает 404; стало — GET /quote отвечает 405 с Allow: POST",
        "было — 404 без заголовка Allow; стало — 405 с заголовком Allow: POST",
    ]
    assert seen["system"] == ap.SYSTEM_PROMPT
    assert "GET /quote отдаёт 404" in seen["user"]
    assert "сейчас 404, ожидается 405" in seen["user"]
    assert seen["model"] == a.llm.MODEL_GATE


def test_propose_acceptance_options_model_failure_is_an_empty_list(monkeypatch):
    """Докстринг активности объявляет это критичным: отказ модели — пустой
    список, а не исключение наружу. Пустой список не топит гейт — вопрос
    задаётся всё равно, свободным текстом (ответственность вызывающего кода
    в `_start_development`), но САМА активность обязана вернуть `[]`, а не
    уронить прогон необработанным исключением."""
    def boom(system, user_message, model_cls, model=None):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(a.llm, "extract", boom)

    assert a.propose_acceptance_options(_issue()) == []


def test_propose_acceptance_options_uses_title_and_body(monkeypatch):
    """Модель получает и заголовок, и тело — критерий часто уточняется
    именно в теле, а не в заголовке."""
    seen: dict = {}

    def fake_extract(system, user_message, model_cls, model=None):
        seen["user"] = user_message
        return model_cls(options=[ap.AcceptanceOption(before="a", after="b")])

    monkeypatch.setattr(a.llm, "extract", fake_extract)

    issue = IssueInput(repo="o/r", issue_number=2, title="Заголовок задачи",
                       body="Подробности критерия здесь", author_login="u",
                       author_type="User", interactive=True)
    a.propose_acceptance_options(issue)

    assert "Заголовок задачи" in seen["user"]
    assert "Подробности критерия здесь" in seen["user"]
