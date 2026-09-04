"""Точка подключения HowToDemo-Agent к Harness.

HowToDemo-Agent живёт в своём репозитории (`po-helper-org/poh-howtodemo-agent`)
и ставится в образ воркера пакетом. Harness не знает ни его правил, ни его
вердикта — он даёт ему ровно три вещи:

1. **Токен GitHub** — свой installation-токен GitHub App, тот же, что у
   Delivery-Agent. Второе приложение и второй набор прав здесь не заводятся.
2. **Модель** — тот же клиент z.ai, что и у остальных стадий. Модель нужна
   агенту ровно для одного: перевести текст сценария в машиночитаемый план.
   Решать, сошлось ли ожидание, она не будет — вердикт приёмки агент считает
   кодом.

3. **Тело задачи с критерием на виду** — порт GitHub, обёрнутый так, что
   приёмщик получает критерий в форме, которую сам же признаёт (#301,
   `_CriterionFirst` ниже).

Обратной зависимости нет: `poh_howtodemo` не импортирует ничего из Harness.
"""

import logging
import os

import github_client
import llm

from shared import howtodemo

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


class _CriterionFirst:
    """Порт GitHub приёмщика: тело задачи с критерием в канонической форме.

    Приёмщик ищет сценарий по заголовку и о размеченном блоке
    `harness:howtodemo` не знает: у него своя кодовая база и намеренно нет
    зависимости от Harness. Контур же кладёт подтверждённый человеком критерий
    именно в блок. На `poh-demo-checkout#171` это разошлось (#301): гейт
    разработки нашёл критерий и пропустил задачу за полминуты, а приёмка через
    двадцать минут ответила «проверять нечем» и повесила `demo:no-scenario` —
    на задачу, у которой сценарий есть.

    Чинится в порту, а не копией правил блока в приёмщике: читатель критерия у
    контура один (`shared/howtodemo.py`), и порт отдаёт приёмщику то, что
    прочитал ОН. Расходиться двум читателям больше не на чем — второй читает
    уже разобранное первым.

    Остальная поверхность порта делегируется как есть: `__getattr__` не даст
    новому методу приёмщика пропасть по дороге при обновлении пакета — а
    пропал бы он молча, потому что порт объявлен `Protocol`, и недостающий
    метод обнаружился бы только вызовом в бою.
    """

    def __init__(self, inner):
        self._inner = inner

    def issue_body(self, repo: str, number: int) -> str:
        return howtodemo.expose(self._inner.issue_body(repo, number))

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install() -> None:
    """Сконфигурировать порты агента. Зовётся один раз на старте воркера."""
    from poh_howtodemo import integration, ports

    translator = PlanTranslator()
    integration.install(
        token_provider,
        dry_run=os.environ.get("DRY_RUN", "").strip() not in ("", "0"),
        llm=translator,
    )
    # Порт GitHub оборачивается ПОСЛЕ install: своего входа для него у агента
    # нет. Модель и оболочка передаются ЗАНОВО не для красоты — `ports.configure`
    # присваивает все три порта разом, и вызов с одним лишь `github` обнулил бы
    # модель. Приёмка упала бы не здесь, а много позже, на трансляции сценария:
    # «порт модели не подставлен». `shell=None` — ровно то, что передаёт сам
    # `integration.install`: оболочку Harness приёмщику не даёт.
    ports.configure(github=_CriterionFirst(ports.github()), llm=translator,
                    shell=None)
