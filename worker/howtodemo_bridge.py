"""Точка подключения HowToDemo-Agent к Harness.

HowToDemo-Agent живёт в своём репозитории (`po-helper-org/poh-howtodemo-agent`)
и ставится в образ воркера пакетом. Harness не знает ни его правил, ни его
вердикта — он даёт ему ровно две вещи:

1. **Токен GitHub** — свой installation-токен GitHub App, тот же, что у
   Delivery-Agent. Второе приложение и второй набор прав здесь не заводятся.
2. **Модель** — тот же клиент z.ai, что и у остальных стадий. Модель нужна
   агенту ровно для одного: перевести текст сценария в машиночитаемый план.
   Решать, сошлось ли ожидание, она не будет — вердикт приёмки агент считает
   кодом.

Обратной зависимости нет: `poh_howtodemo` не импортирует ничего из Harness.
"""

import logging
import os

import github_client
import llm

_log = logging.getLogger(__name__)


def token_provider(repo: str) -> str:
    """Токен для HowToDemo-Agent — тот же installation-токен GitHub App."""
    return github_client.auth_token(repo)


class PlanTranslator:
    """Порт модели: сценарий текстом → план JSON.

    `complete`, а не `extract`: план — вложенная структура переменной глубины,
    а Instructor на таком только мешает ретраями по несоответствию схеме.
    Разбор и валидацию делает сам агент (`poh_howtodemo.plan`), и невалидный
    ответ там становится внятной ошибкой, а не молча пустым планом.
    """

    def translate(self, scenario: list[str]) -> str:
        # Промпт берётся ИЗ ПАКЕТА агента, а не из prompts/ этого репозитория:
        # он часть договора агента с моделью наравне с форматом плана, их
        # правят вместе. Копия у потребителя рано или поздно отстаёт — в
        # контуре так уже отстала копия скилла bft-writer.
        from poh_howtodemo import plan

        system = plan.system_prompt()
        numbered = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(scenario))
        return llm.complete(system, numbered, model=llm.MODEL_CLASSIFY,
                            max_tokens=8000)


def install() -> None:
    """Сконфигурировать порты агента. Зовётся один раз на старте воркера."""
    from poh_howtodemo import integration

    integration.install(
        token_provider,
        dry_run=os.environ.get("DRY_RUN", "").strip() not in ("", "0"),
        llm=PlanTranslator(),
    )
