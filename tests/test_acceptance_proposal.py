import pytest

from shared import acceptance_proposal as ap


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
