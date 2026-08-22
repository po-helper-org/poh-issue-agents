"""
LLM-клиент для дешёвых/структурированных стадий (gate/classify/duplicate/
priority). Instructor поверх OpenAI-совместимого эндпоинта z.ai — даёт
типобезопасные Pydantic-ответы с автоматическим retry при невалидном JSON,
вместо ручного json.loads()+try/except, как было в исходной версии на
Actions.

Для po-helper/SA-helper (Claude Code skills) используется ДРУГОЙ путь —
Anthropic-совместимый эндпоинт z.ai через переменные окружения ANTHROPIC_*,
см. activities.run_fnr_stage (запускает `claude -p` как subprocess,
а не через этот клиент).
"""

import os

import instructor
from openai import OpenAI

MODEL_GATE = os.environ.get("MODEL_GATE", "glm-4.5-air")
MODEL_CLASSIFY = os.environ.get("MODEL_CLASSIFY", "glm-5.2")

# Per-stage модели для FNR (Layer C - глубокий анализ).
# Каждая стадия может использовать свою модель для оптимизации затрат/скорости.
# Дефолты основаны на сложности стадии:
# - repowise: сбор контекста, относительно простая задача
# - task: структурирование постановки, средняя сложность
# - concept: архитектурные концепты, нужна хорошая модель
# - debate: архитектурные дебаты, нужна сильная модель
# - sysreq: генерация системных требований, нужна сильная модель
# - validate: валидация, можно использовать модель средней силы
MODEL_FNR_REPOWISE = os.environ.get("MODEL_FNR_REPOWISE", "glm-4.6")
MODEL_FNR_TASK = os.environ.get("MODEL_FNR_TASK", "glm-4.6")
MODEL_FNR_CONCEPT = os.environ.get("MODEL_FNR_CONCEPT", "glm-4.6")
MODEL_FNR_DEBATE = os.environ.get("MODEL_FNR_DEBATE", "glm-5.2")
MODEL_FNR_SYSREQ = os.environ.get("MODEL_FNR_SYSREQ", "glm-4.6")
MODEL_FNR_VALIDATE = os.environ.get("MODEL_FNR_VALIDATE", "glm-4.6")

# Маппинг имён стадий к переменным модели
FNR_STAGE_MODELS = {
    "repowise": MODEL_FNR_REPOWISE,
    "task": MODEL_FNR_TASK,
    "concept": MODEL_FNR_CONCEPT,
    "debate": MODEL_FNR_DEBATE,
    "sysreq": MODEL_FNR_SYSREQ,
    "validate": MODEL_FNR_VALIDATE,
}

_client: instructor.Instructor | None = None


def get_client() -> instructor.Instructor:
    global _client
    if _client is None:
        # z.ai GLM rejects OpenAI tool-calling (400 "Invalid API parameter" —
        # instructor's default Mode.TOOLS). JSON mode works: the model returns
        # a JSON object matching the Pydantic schema.
        _client = instructor.from_openai(
            OpenAI(
                base_url=os.environ["ZAI_BASE_URL"],
                api_key=os.environ["ZAI_API_KEY"],
            ),
            mode=instructor.Mode.JSON,
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


def complete(system_prompt: str, user_message: str, *, model: str,
             max_tokens: int = 16000, temperature: float = 0.2) -> str:
    """Сырой ответ модели текстом — без Pydantic-схемы.

    `extract` рядом требует response_model и годится для коротких структур.
    Стадии БФТ возвращают либо большой JSON каскада, либо готовый markdown на
    двадцать килобайт: схемой это не описать, а Instructor на таком объёме
    только мешает ретраями по несоответствию.
    """
    resp = get_client().client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""
