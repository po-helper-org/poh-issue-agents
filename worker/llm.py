"""
LLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/
priority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт
типобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON,
вместо ручного json.loads()+try/except, как было в исходной версии на
Actions.

Для po-helper/SA-helper (Claude Code skills) используется ДРУГОЙ путь —
Anthropic-совместимый эндпоинт z.ai через переменные окружения ANTHROPIC_*,
см. activities.run_research_pipeline/run_bug_pipeline (запускают `claude -p`
как subprocess, а не через этот клиент).
"""

import os

import instructor
from openai import OpenAI

MODEL_GATE = os.environ.get("MODEL_GATE", "glm-4.5-air")
MODEL_CLASSIFY = os.environ.get("MODEL_CLASSIFY", "glm-5.2")

_client: instructor.Instructor | None = None


def get_client() -> instructor.Instructor:
    global _client
    if _client is None:
        _client = instructor.from_openai(
            OpenAI(
                base_url=os.environ["ZAI_BASE_URL"],
                api_key=os.environ["ZAI_API_KEY"],
            )
        )
    return _client


def extract(system_prompt: str, user_message: str, response_model, model: str = MODEL_GATE):
    """Структурированное извлечение — LLM обязана вернуть response_model,
    Instructor сам ретраит при несоответствии схеме."""
    client = get_client()
    return client.chat.completions.create(
        model=model,
        response_model=response_model,
        max_retries=2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
