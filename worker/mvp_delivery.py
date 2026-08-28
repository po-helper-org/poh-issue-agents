"""MvpDelivery — доведение одного MVP от плана до готовности к приёмке.

Почему отдельный воркфлоу, а не фаза `IssueLifecycle`: своя история для
разбора, свой `workflow list`, шаги переживают рестарт воркера, а ошибка в
логике шагов правится без риска для живых прогонов цикла Issue. Тот же приём,
что у `IssueDevelopment` и `IssuePrFix` (`worker/workflows.py`).

Чего не делает: не ревьюит, не мержит, не выкатывает, не заводит GROW-Issue.
Врезка в цикл Issue (кто и когда запускает этот воркфлоу) — не эта задача.

Активности вызываются по СТРОКОВОМУ имени, а не ссылкой `activities.*`: модуль
не импортирует тяжёлый `worker/activities.py` (249 КБ, тянет instructor/openai/
pydantic на одном лишь импорте) — тот же приём, что уже в
`consolidation_workflow.py`. Оборотная сторона приёма — конвертер Temporal без
`result_type=` отдаёт голый словарь вместо того типа, что описан сигнатурой
активности: на этом уже зацикливался воркфлоу приёмки. Поэтому каждый вызов
ниже задаёт `result_type=` явно, даже когда тип простой (`int`, `list`) —
дисциплины ради, а не только там, где без него упало бы прямо сейчас.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared import decomposition
    from shared.workflow_types import IssueInput

# `mvp_develop_step`, `mvp_open_substep`, `mvp_close_substep` — одна попытка,
# по двум разным доводам.
#
# `mvp_develop_step` — недетерминированная дорогая работа (прогон агента, до
# 45 минут, `develop.DEFAULT_RUN_TIMEOUT_SEC`): повтор re-запускает её целиком
# и стоит денег, поэтому инициирует человек, а не политика ретраев. Не приём
# «по аналогии», а ТЕ ЖЕ параметры (3600 c потолок / heartbeat 300 c /
# maximum_attempts=1), что у прямого вызова `activities.trigger_openhands_
# resolver` в `IssueLifecycle._start_development` (`worker/workflows.py`) —
# `mvp_develop_step` оборачивает ту же активность `trigger_openhands_resolver`.
#
# `mvp_open_substep`/`mvp_close_substep` — по другому доводу тот же вывод:
# `create_issue`/`close_issue` не идемпотентны так, как `link_sub_issue`
# (у него 422 «already added» — штатный путь); повторный `create_issue` завёл
# бы вторую под-задачу на тот же шаг, а не обнаружил первую.
_ONE_ATTEMPT = RetryPolicy(maximum_attempts=1)

# `mvp_read_plan` — та же порода активности, что `run_fnr_stage`/`run_bft_stage`
# (`worker/workflows.py`): один вызов `_run_with_heartbeat(_run_claude, ...)` на
# ~900 с CLAUDE_STAGE_TIMEOUT_SEC (потолок ниже — 1200 c, «claude до 900 +
# буфер», комментарий оттуда скопирован дословно), тот же идиом отказа (`raise
# RuntimeError(f"стадия ... не создан")`). У НИХ политика повторов — не
# плоский `maximum_attempts=1`, а `maximum_attempts=2` с исключением
# собственных явных отказов стадии из ретраев: отказ ПО ЛОГИКЕ стадии не
# повторяется (недетерминировано и стоит денег — тот же довод, что и у
# `_ONE_ATTEMPT` выше), а вот обрыв активности выкладкой посреди вызова claude
# (воркер убит, heartbeat не успел дойти) — не решение стадии, а авария
# инфраструктуры, и без второй попытки съедает готовый прогон целиком: так на
# стенде был потерян анализ по Issue #11 (см. комментарий у `run_fnr_stage` в
# `worker/workflows.py`). `mvp_read_plan` собрана из тех же кубиков и стоит
# перед тем же выбором — плоский `_ONE_ATTEMPT` здесь был бы СТРОЖЕ этого
# соседа на равном по устройству вызове, а не так же строг.
#
# Три типа в списке исключений — три исключения, которые кидает сама
# `mvp_read_plan` (см. `worker/activities.py`): `RuntimeError` (план не
# построен), `decomposition.InvalidPlan` (нечестное ребро, требование 1) и
# голый `ValueError` (`plan_parse.parse` — незакрытый забор кода). Temporal
# сравнивает `non_retryable_error_types` с `exception.__class__.__name__`
# буквально (`temporalio/converter.py:DefaultFailureConverter.to_failure`), не
# по иерархии классов — поэтому `InvalidPlan`, будучи подклассом `ValueError`,
# перечислена отдельной строкой, а не унаследована от записи `"ValueError"`.
# Всё, что НЕ входит в список (таймаут, обрыв воркера, что угодно ещё из
# инфраструктуры) — получает вторую попытку.
_READ_PLAN_RETRY = RetryPolicy(
    maximum_attempts=2,
    non_retryable_error_types=["RuntimeError", "InvalidPlan", "ValueError"],
)


@workflow.defn(name="MvpDelivery")
class MvpDelivery:
    @workflow.run
    async def run(self, issue: IssueInput) -> int | None:
        # Потолок и heartbeat — НЕ «пять минут на чтение файла»: активность
        # сама строит план навыком writing-plans (до 900 с вызова claude,
        # `CLAUDE_STAGE_TIMEOUT_SEC` в `worker/activities.py`) и шлёт
        # heartbeat, пока строит (`_run_with_heartbeat`, такт 30 с). 1200 с —
        # тот же запас (900 + 300 буфера), что у одностадийных вызовов claude
        # в FNR/BFT (`worker/workflows.py`); heartbeat_timeout=300 с — тот же
        # десятикратный запас над тридцатисекундным тактом, что и у каждого
        # соседнего вызова такой природы там же. Потолок короче — и активность
        # не переживёт собственное построение плана раньше, чем оно кончится.
        # Политика повторов — `_READ_PLAN_RETRY` (см. докстринг константы
        # выше): те же два соседа FNR/BFT, а не плоский `_ONE_ATTEMPT`.
        items = await workflow.execute_activity(
            "mvp_read_plan", issue, result_type=list,
            start_to_close_timeout=timedelta(seconds=1200),
            heartbeat_timeout=timedelta(seconds=300),
            retry_policy=_READ_PLAN_RETRY,
        )
        if not items:
            # `plan_parse.parse` не нашла ни одной задачи — план есть, но в
            # нём нечего делать по шагам. Не отказ: воркфлоу не заводит
            # под-задач и не разрабатывает, отдаёт `None`, как и «работа
            # ведётся в другом месте» читают соседние воркфлоу цикла.
            return None

        if not decomposition.needs_subissues(items):
            # Делить нечего: план без объявленных зависимостей — список
            # правок, который исполнитель сделает за один прогон. Заводить
            # под каждую строку задачу в трекере значит платить вниманием за
            # видимость, которой никто не пользуется (`decomposition.
            # needs_subissues`). Потолок и heartbeat — как у `dev_run_agent`
            # (`worker/workflows.py`): 3600 с запаса над задокументированными
            # 45 минутами прогона агента (`develop.DEFAULT_RUN_TIMEOUT_SEC`),
            # heartbeat 300 с.
            return await workflow.execute_activity(
                "mvp_develop_step", args=[issue, 0], result_type=int,
                start_to_close_timeout=timedelta(seconds=3600),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=_ONE_ATTEMPT,
            )

        pr_number: int | None = None
        for index, item in enumerate(items):
            # Открыть под-задачу шага. Метки `origin:agent` + `harness:step`
            # ставит сама активность (Task 13) — без `STEP` вебхук поднял бы
            # на под-задаче полноценный цикл с триажом.
            number = await workflow.execute_activity(
                "mvp_open_substep", args=[issue, index, item["title"]], result_type=int,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_ONE_ATTEMPT,
            )
            # Разработать шаг — тот же потолок, что у одностепенного пути выше.
            pr_number = await workflow.execute_activity(
                "mvp_develop_step", args=[issue, index], result_type=int,
                start_to_close_timeout=timedelta(seconds=3600),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=_ONE_ATTEMPT,
            )
            # Закрыть под-задачу шага — она живёт ровно время шага (R5).
            await workflow.execute_activity(
                "mvp_close_substep", args=[issue, number, index],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_ONE_ATTEMPT,
            )
        return pr_number
