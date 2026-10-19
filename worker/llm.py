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

# Обе — `glm-5.2`, и это выбор ЗАМЕРА, а не привычки. Прогон всех десяти
# моделей аккаунта на настоящих промптах стадий (`scripts/model_probe.py`,
# 2026-09-09) сломал правило «старее и мельче — дешевле»: при одинаковом входе
# в 5175 токенов `glm-4.5-air` отдал 2633 выходных за 63 с, `glm-4.6` — 2321 за
# 53 с, а `glm-5.2` — 1875 за 31 с. Схему и ветвление ворот держат все десять;
# разница только в многословности и скорости, и по обеим 5.2 впереди.
#
# Переменные оставлены РАЗНЫМИ, хотя значение сейчас одно: у ворот и у
# классификации разная цена ошибки, и разводить их обратно придётся правкой
# `.env`, а не кода.
#
# Умолчания обязаны совпадать с `.env.example` — за этим следит
# `tests/test_model_config.py`. Расходились: здесь стояло `glm-5.2`, там
# `glm-4.6`, на стенде побеждал compose, а всякий прогон мимо него (скрипты,
# локальный воркер, тесты с настоящим ключом) молча уходил на модель дороже.
# Расхождение умолчаний не видно ниоткуда: обе стороны выглядят настроенными.
MODEL_GATE = os.environ.get("MODEL_GATE", "glm-5.2")
MODEL_CLASSIFY = os.environ.get("MODEL_CLASSIFY", "glm-5.2")

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
