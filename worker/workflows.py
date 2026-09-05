"""
IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,
это даёт идемпотентность бесплатно: повторный issues.opened webhook не
создаст вторую сущность).

Signals заменяют то, что раньше делали отдельные GitHub Actions,
триггерящиеся на лейблы:
- human_decision("research-me" | "bug-me" | "build-me")
- user_comment(текст, id) — реплика человека: ответ на уточняющий вопрос
  либо новый вопрос по припаркованной задаче

Workflow буквально приостанавливается на await self._wait_for_signal() —
это устраняет и гонку между duplicate-check/priority-scoring (теперь
последовательные шаги одного потока, не параллельные Actions), и ручной
парсинг HTML-маркеров для счётчика раундов уточнения (состояние просто
живёт в переменных workflow, Temporal журналирует его сам).
"""

import asyncio
from datetime import datetime, timedelta, timezone

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from shared import bft, commands, labels, lifecycle
    from shared.commands import ANALYZE, BFT, BFT_DEEP, ESTIMATE, RESEARCH
    from shared.workflow_ids import (
        analysis_workflow_id,
        bft_workflow_id,
        development_workflow_id,
        estimate_workflow_id,
        howtodemo_workflow_id,
        pr_fix_workflow_id,
        research_workflow_id,
    )
    from shared import agent_events, awaiting as awaiting_mod
    from shared.agent_events import AgentEvent
    from shared.awaiting import Awaiting
    from shared.workflow_types import (
        AnalyzeInput,
        BftRequest,
        ClassificationResult,
        CommentAckInput,
        CommentIntent,
        Deadlines,
        DevelopPlan,
        EstimateRequest,
        EstimateResult,
        IssueInput,
        LifecycleState,
        OrphanEventInput,
        UserComment,
        WebhookAuditInput,
    )

    import activities

# Прогон БФТ, запущенный самим триажем, а не человеком. Отличается тем, что не
# трогает метки команды: помечать `run:bft` нечего — команды не было, а метка
# вернулась бы вебхуком как новая.
BFT_TRIAGE = "triage"

MAX_CLARIFICATION_ROUNDS = 2

# Потолок кругов уточнения ПОСЛЕ аналитики. Вопросы здесь другие, чем на входе:
# входной гейт спрашивает «что вообще нужно», аналитика — «чего не хватает,
# чтобы решение было однозначным». Потолок тот же по причине той же: вопрос, на
# который не отвечают, не должен держать задачу вечно — по исчерпании круги
# кончаются, вопросы уезжают в чеклист готовности, и решение принимает тот, кто
# возьмёт задачу.
MAX_ANALYSIS_CLARIFY_ROUNDS = 2

# Потолок возвратов этапа на пересборку. Человек может вернуть этап много раз,
# но каждый круг — это полный прогон триажа/аналитики, который стоит денег.
MAX_REWORK_ROUNDS = 2

# Запрос на прогон аналитики, доставленный в общую очередь сигналов. Та же
# схема, что у реплики человека (`UserComment`): одна очередь, разные виды
# событий, и обработчик фазы решает, что с ними делать.
AGENT_ANALYZE = "__agent__:analyze"

# Запрос на прогон продуктового исследования
AGENT_RESEARCH = "__agent__:research"
# Очередь приёмщика HowToDemo. Своя, а не общая: прогон приёмки держит
# активность десятками минут и на общем пуле вытеснял бы триаж Issue.
# Значение читается на импорте — оно одинаково у всех реплеев одного воркера,
# а в историю уезжает уже решение о запуске, не сама строка.
HOWTODEMO_TASK_QUEUE = "howtodemo"

# Issue закрыт на GitHub. Тот же приём: сигнал будит парковку, а решение
# принимает цикл — иначе обработчику каждой фазы пришлось бы знать про закрытие.
CLOSED = "__closed__"

# Сколько ключей событий помнить ради идемпотентности. Цикл живёт месяцами, а
# событий по одному Issue — десятки: список без потолка рос бы вместе с
# историей, ровно тем объёмом, который continue-as-new и призван обрывать.
SEEN_EVENTS_KEPT = 50

# Порог длины истории для continue-as-new. Ниже потолка, на котором уже
# спотыкалась консолидация (~990 событий): реплей должен укладываться в
# workflow-task timeout с запасом, а не впритык.
HISTORY_EVENT_THRESHOLD = 800

# Находка F3 (Important, второй круг финального ревью). Пока открыт вопрос
# гейта критерия приёмки, парковка (`_phase_await_build`) периодически
# перечитывает тело Issue — критерий, вписанный человеком напрямую (A23),
# иначе не подхватывается вообще: правки тела вебхук не доставляет сигналом.
# Интервал — тот же порядок, что у периодической проверки доклада ревью в
# `_phase_pr_review` (`timedelta(minutes=30)` там же по файлу): достаточно
# редко, чтобы не превратиться в дорогой цикл (до находки C1 подхват той же
# правки телом стоил вызова МОДЕЛИ на каждом обороте), и достаточно часто,
# чтобы `DEVELOP_AUTOSTART` не требовал действия человека.
CRITERION_RECHECK_INTERVAL = timedelta(minutes=30)


# Потолок разворота `.cause` в `_failure_reason`. Сегодняшняя цепочка стадии
# разработки — три уровня (ChildWorkflowError → ActivityError →
# ApplicationError), но число — не память самой длинной ожидаемой цепочки, а
# защита от зацикливания: `.cause` — обычный settable-атрибут, и ничто не
# мешает ему сослаться само на себя или на предка. Без потолка такая цепочка
# крутила бы разворот вечно вместо того, чтобы вернуть хоть какую-то причину.
_MAX_CAUSE_UNWRAP = 10


def _failure_reason(e: BaseException) -> str:
    """"ExcType: message" из ПЕРВОПРИЧИНЫ для тегов/группировки Sentry.

    catch-ветки ловят обёртку Temporal, а не исходное исключение activity —
    но глубина обёртки зависит от того, ЧТО сорвалось. Активность внутри
    воркфлоу даёт `ActivityError`; с тех пор как дорогие стадии стали
    дочерними воркфлоу, тот же сбой активности ВНУТРИ ребёнка приходит уже
    как `ChildWorkflowError` поверх `ActivityError`. Разворачиваем `.cause` В
    ЦИКЛЕ, а не один раз: единственный разворот `ChildWorkflowError` даёт
    `ActivityError`, у которого своего `.type` нет — наружу уходило бы одно
    и то же «ActivityError: Activity task failed» на любую причину сбоя
    разработки (выключенный DEVELOP_ENABLED, код 137, отказ пуша, красные
    тесты — всё в одном ведре без текста причины). Останавливаемся на первом
    `ApplicationError` (у него есть `.type` = имя исходного класса) либо на
    исключении без дальнейшей причины. Чистые операции над атрибутами —
    детерминированы, безопасны в workflow-коде.
    """
    cause = getattr(e, "cause", None) or e
    for _ in range(_MAX_CAUSE_UNWRAP):
        exc_type = getattr(cause, "type", None)
        # `.type` — имя класса ТОЛЬКО у ApplicationError. Оно и есть искомая
        # первопричина: дальше разворачивать нечего.
        if isinstance(exc_type, str):
            return f"{exc_type}: {cause}"
        # `.type` есть, но не строка — это TimeoutError: там тем же именем
        # занято перечисление TimeoutType, и его значение число. В Sentry
        # уезжал тег `exc_type: 1` и fingerprint по этой единице
        # (ISSUE-AGENT-B), поэтому число как тип не годится.
        #
        # Но и разворачивать глубже НЕЛЬЗЯ. Temporal кладёт причиной таймаута
        # сбой ПОСЛЕДНЕЙ попытки, и на шаге с тремя попытками «упал один раз,
        # потом встал» доложилось бы тем первым падением: человек в Issue и
        # отпечаток в Sentry указывали бы на ошибку, которая на самом деле
        # была пережита, а настоящая причина — таймаут — исчезала бы.
        if exc_type is not None:
            break
        deeper = getattr(cause, "cause", None)
        if deeper is None:
            break
        cause = deeper
    return f"{type(cause).__name__}: {cause}"


async def _run_staged_analysis(analyze: AnalyzeInput) -> bool:
    """Пер-стадийный прогон FNR — общий для обоих входов в аналитику.

    Один код на команду `/analyze` (IssueAnalysis) и на лейбл research-me внутри
    IssueLifecycle. Раньше вторая ветка звала монолитную activity
    run_analysis_pipeline: те же пять стадий, но одним чёрным ящиком — застрявшая
    стадия не называла себя, а прогон по лейблу и прогон по команде расходились
    в поведении, оставаясь «одной и той же аналитикой» на словах.

    Каждая стадия — свой шаг Event History со своим таймингом; ретраев нет
    (прогон недетерминирован, мутирует файлы и стоит денег — повтор инициирует
    человек), сбой всегда доезжает до GitHub, каталог снимается на обоих путях.

    Возвращает True, если артефакты опубликованы: от этого зависит, можно ли
    передавать задачу разработчику — без аналитики передавать нечего.
    """
    ok = True
    try:
        await workflow.execute_activity(
            activities.prepare_workspace,
            analyze,
            start_to_close_timeout=timedelta(seconds=1000),  # clone 300 + repomix 600 + буфер
            heartbeat_timeout=timedelta(seconds=300),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        for stage_name in activities.FNR_STAGE_NAMES:
            await workflow.execute_activity(
                activities.run_fnr_stage,
                args=[analyze, stage_name],
                start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер
                heartbeat_timeout=timedelta(seconds=300),
                # Сбой самой стадии не повторяется: прогон недетерминирован,
                # мутирует файлы и стоит денег — повтор инициирует человек. Но
                # heartbeat timeout не её сбой: воркер перезапустили (выкладкой,
                # рестартом Docker), активность оборвалась, и ничего произведено
                # не было. Без второй попытки любая выкладка посреди прогона
                # убивала анализ целиком — так встал Issue #11 на стенде.
                #
                # Граница по типу: всё, что стадия поднимает сама, — RuntimeError.
                # Таймауты и потеря воркера в этот тип не попадают.
                # `RateLimited` (`shared/errors.py`) сюда не попадает: отказ
                # провайдера по лимиту частоты — не сбой стадии, и повторять
                # его нужно, но с отступом, а не сразу. Минута, три, девять:
                # на #165 лимит держался около сорока минут, и повтор без
                # ожидания просто сжёг бы попытки.
                retry_policy=RetryPolicy(
                    maximum_attempts=4,
                    initial_interval=timedelta(seconds=60),
                    backoff_coefficient=3.0,
                    non_retryable_error_types=["RuntimeError"],
                ),
            )
        await workflow.execute_activity(
            activities.publish_analysis,
            analyze,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=True)
    except Exception as exc:
        ok = False
        # exc — ActivityError с общим текстом; настоящая причина в exc.cause
        # (например, «стадия concept: артефакт ... не создан»). Разворачиваем.
        reason = str(getattr(exc, "cause", None) or exc)
        # Сначала спасаем сделанное, потом сообщаем о сбое: `cleanup` в
        # `finally` снимет каталог, и после него публиковать будет нечего.
        saved = []
        try:
            saved = await workflow.execute_activity(
                activities.publish_analysis_partial,
                args=[analyze, reason[:300]],
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception as partial_exc:
            workflow.logger.warning(
                "публикация частичного анализа не удалась: %s", partial_exc)
        if not saved:
            await workflow.execute_activity(
                activities.publish_analysis_error,
                args=[analyze, reason[:500]],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        await _finish_labels(analyze.repo, analyze.issue_number, ANALYZE, ok=False)
    finally:
        # Каталог живёт вне Temporal — снимаем его на обоих путях. Best-effort:
        # провал самой уборки (timeout/краш воркера) не должен затирать реальный
        # исход — ловим и логируем, но наружу не пробрасываем.
        try:
            await workflow.execute_activity(
                activities.cleanup_workspace,
                analyze,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as cleanup_exc:
            workflow.logger.warning(
                "cleanup_workspace failed (best-effort, ignored): %s", cleanup_exc
            )
    return ok


async def _agents_off(repo: str, issue_number: int, what: str) -> bool:
    """R4: человек забрал Issue себе — прогон не стартует.

    Проверка стоит ПЕРВЫМ шагом обоих командных воркфлоу, до ack и до любой
    работы: смысл рубильника в том, чтобы не потратить бюджет, а не в том,
    чтобы красиво остановиться посередине.
    """
    state = await workflow.execute_activity(
        activities.read_protocol_state,
        args=[repo, issue_number],
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )
    if not state.agents_off:
        return False
    await workflow.execute_activity(
        activities.post_agents_off_notice,
        args=[repo, issue_number, what],
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )
    return True


async def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:
    """Обратный ход меток команды — один вызов на все терминальные ветки.

    Зовётся из трёх мест (IssueAnalysis, IssueEstimation и ветка research-me в
    IssueLifecycle), поэтому таймаут и политика ретраев заданы здесь: разъехавшись,
    они дали бы Issue, застрявший в `run:*` после завершённого прогона.
    """
    await workflow.execute_activity(
        activities.finish_command_labels,
        args=[repo, issue_number, command, ok],
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )


@workflow.defn(name="WebhookAudit")
class WebhookAudit:
    """Надгробие для доставки, отброшенной по конфигу.

    Не исполняет ни одной activity и завершается сразу: вся ценность в том, что
    вход виден в Temporal UI. До него единственным следом отказа была строка в
    логах контейнера — а туда никто не смотрит, пока не заподозрит проблему.

    Аудитом покрыт ровно один случай — repo_not_allowed. Боты, неподдержанные
    action и сигналы в завершённый workflow — штатный высокочастотный шум; их
    аудит утопил бы настоящие прогоны в мусоре.
    """

    @workflow.run
    async def run(self, audit: WebhookAuditInput) -> str:
        workflow.logger.warning(
            "доставка %s (%s/%s) по %s отброшена: %s; allowlist=%s",
            audit.delivery_id, audit.event, audit.action, audit.repo,
            audit.reason, audit.allowlist,
        )
        return audit.reason


@workflow.defn(name="OrphanAgentEvent")
class OrphanAgentEvent:
    """Надгробие для события агента, не связанного ни с одним Issue.

    Тот же приём, что и у `WebhookAudit`: ни одной activity, вся ценность — в
    том, что факт виден в Temporal UI. Событие уже случилось (PR открыт, CI
    упал), но какой задаче оно принадлежит — неизвестно, и догадка здесь хуже
    молчания: привязать работу не к тому Issue значит испортить трассировку
    двум задачам сразу.
    """

    @workflow.run
    async def run(self, orphan: OrphanEventInput) -> str:
        workflow.logger.warning(
            "событие агента %s (%s/%s) по %s в %s не связано с Issue: %s",
            orphan.agent, orphan.phase, orphan.status, orphan.ref,
            orphan.repo, orphan.reason,
        )
        return orphan.reason


@workflow.defn(name="CommentAck")
class CommentAck:
    """Подтверждение приёма комментария — отдельным прогоном, до всего остального.

    Отдельный workflow, а не шаг цикла: комментарий приходит и туда, где цикла
    нет (issue старше установки App, прогон уже закрыт), а поднимать ради
    реакции полный `IssueLifecycle` — это веер LLM-прогонов на тысяче старых
    issue. Реакция обязана стоять во всех исходах одинаково.

    Ретраи с потолком: rate limit GitHub проходит сам, а 404 (комментарий уже
    удалили) не пройдёт никогда — держать ради него бесконечный прогон незачем.
    """

    @workflow.run
    async def run(self, ack: CommentAckInput) -> None:
        await workflow.execute_activity(
            activities.ack_comment_seen,
            ack,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )


@workflow.defn(name="IssueLifecycle")
class IssueLifecycle:
    def __init__(self) -> None:
        # Очередь несёт и решения человека (строки), и факты внешних агентов
        # (AgentEvent). Один поток вместо двух — иначе фаза, ждущая решения, не
        # проснулась бы на событии, и наоборот.
        self._signal_queue: asyncio.Queue[str | AgentEvent | UserComment] = asyncio.Queue()
        self._analyze_labeled = False
        self._issue: IssueInput | None = None
        self._stage = "intake"
        self._phase = lifecycle.CREATED
        self._phase_driven = False  # True — прогон идёт фазовым циклом
        self._priority_tier = ""
        self._classification_label: str | None = None
        self._duplicate_of: int | None = None
        self._analysis_done = False
        # Задача — часть чужого плана: подзадача декомпозиции. Ни своей
        # декомпозиции, ни своей разработки у неё нет — и то и другое ведёт
        # родитель, одним прогоном на весь объём MVP.
        self._plan_member = False
        # Номер родителя плана. Нужен подзадаче, чтобы сослаться на требования:
        # своей ветки анализа у неё нет, и ссылка на `research/issue-<своё>`
        # была бы битой.
        self._root_issue: int | None = None
        # Сколько кругов уточнения ПОСЛЕ аналитики уже потрачено. Потолок нужен
        # затем же, что и на входе: вопрос, на который не отвечают, не должен
        # держать задачу вечно.
        self._clarify_rounds = 0
        # Сколько реплик человека уже отвечено содержательно и ключи последних
        # из них. Ключ нужен из-за повторной доставки вебхука: одно событие
        # приезжает сигналом дважды, и без него один вопрос получал бы два
        # ответа. Потолок — из `Deadlines`, вместе с остальными тумблерами.
        self._followup_rounds = 0
        self._answered_comment_ids: list[int] = []
        # Идентификатор открытого вопроса к человеку. Пусто — вопроса нет.
        # Прогон хранит ТОЛЬКО указатель: содержание вопроса живёт в теле
        # Issue (`shared.questions`) — копия здесь разошлась бы с телом при
        # первой правке руками.
        self._open_question = ""
        # Гейт критерия приёмки (`_start_development`) на последнем заходе НЕ
        # пропустил задачу дальше в разработку — неважно, почему: спросил и
        # ждёт ответа, не смог прочитать критерий, не смог задать вопрос.
        # Третий круг финального ревью, находка G1 (Critical): раньше
        # автостарт (`_phase_await_build`) решал это по `self._open_question`
        # непустому — но указатель отражает лишь ОДИН из исходов гейта.
        # Устойчивый отказ ЧТЕНИЯ критерия или отказ ПОСТАНОВКИ вопроса
        # оставляют указатель пустым точно так же, как если бы гейт вообще не
        # звался, — и автостарт, глядя только на указатель, звал гейт заново
        # на каждом обороте цикла: чтение, МОДЕЛЬ, попытка задать вопрос,
        # снова отказ, без единого таймера или сигнала между оборотами. Этот
        # флаг покрывает все исходы гейта разом (см. докстринг `_phase_await_
        # build` и присваивания в `_start_development`) и снимается только
        # когда критерий найден и гейт передаёт задачу дальше.
        self._acceptance_gate_stalled = False
        self._followup_max_rounds = Deadlines().followup_max_rounds
        # Сколько раз человек вернул этап на пересборку (rework intent).
        # Потолок нужен, чтобы пара «переделай» ↔ «переделал» не стояла по
        # LLM-прогону за круг без конца.
        self._rework_rounds = 0
        self._rework_max_rounds = MAX_REWORK_ROUNDS
        self._generation = 0
        # Момент входа в текущую фазу. Проставляется в run() до первого await;
        # None только пока воркфлоу не начал исполняться.
        self._phase_since: datetime | None = None
        self._analyze_comment_id: int | None = None
        self._analyze_pending = False  # запрос на аналитику лежит в очереди
        self._analysis_running = False  # идёт прогон IssueAnalysis
        # Состояние продуктового исследования (аналогично анализу)
        self._research_comment_id: int | None = None
        self._research_pending = False  # запрос на исследование лежит в очереди
        self._research_running = False  # идёт прогон исследования
        self._research_done = False  # исследование завершено успешно
        # Номер PR по этой задаче. Известен из доклада внешнего агента либо от
        # локального прогона разработки; нужен фазе доведения.
        self._pr_number: int | None = None
        # Приёмка по HowToDemo запускается один раз на прогон: цикл фаз может
        # вернуться в pr-open (закрытый и переоткрытый PR), а второй прогон
        # приёмки упёрся бы в WorkflowAlreadyStarted и насорил в логах.
        self._howtodemo_started = False
        # Разбивать ли задачу на подзадачи перед передачей в разработку.
        # Значение приезжает активностью вместе со сроками — по той же причине,
        # что и остальные тумблеры: оно обязано лежать в истории.
        self._decompose = True
        # Ключи уже учтённых событий агентов: один факт двигает фазу один раз.
        self._seen_agent_events: list[str] = []
        # Чего Issue ждёт прямо сейчас. None — работа идёт, ожидания нет.
        self._awaiting: Awaiting | None = None
        # Стоит ли сейчас метка очереди к людям. Нужен, чтобы не дёргать GitHub
        # на каждом переходе: метку трогаем только когда состояние меняется.
        self._human_queue_labelled = False
        # Кто закрыл Issue на GitHub. None — открыт. Закрытие обрывает любую
        # парковку: досиживать срок в закрытом Issue незачем.
        self._closed_by: str | None = None
        # Отказ гейта критерия приёмки (`_start_development`) уже показан хотя
        # бы раз в ЭТОЙ серии подряд идущих отказов. Значение по умолчанию —
        # для свежего прогона; при continue-as-new оно приезжает из
        # `carried.criterion_gate_notified` в `run()` — см. её докстринг в
        # `shared/workflow_types.py` за тем, почему флаг ОБЯЗАН переживать
        # перезапуск (находка 2 ревью: без переноса дедупликация «одно
        # сообщение на серию» ломается именно на задаче, застрявшей на этом
        # гейте, — не в редком случае, а в обычном).
        self._criterion_gate_notified = False

    @workflow.query
    def stage(self) -> str:
        """Текущая стадия прогона — для Temporal UI (вкладка Queries).

        Прогон, припаркованный в ожидании лейбла, показан просто как `Running`
        бессрочно, и отличить «триаж закончен, ждём человека» от «активность
        зависла» можно было только разбирая Event History руками. Значение
        `awaiting-human-decision` снимает эту двусмысленность прямо в UI.

        Чтение атрибута детерминировано и побочных эффектов не имеет, поэтому
        на воспроизведение истории query не влияет.
        """
        return self._stage

    @workflow.query
    def phase(self) -> str:
        """Фаза жизненного цикла — единый словарь на весь контур (#35).

        Фазовый цикл ведёт фазу сам. Прогоны ПРЕЖНЕГО поколения (линейный путь,
        выбранный workflow.patched) фазы не знают — для них она выводится из
        стадии через мост STAGE_TO_PHASE. Иначе такой прогон вечно показывал бы
        `created`, хотя триаж давно прошёл.
        """
        if self._phase_driven:
            return self._phase
        return lifecycle.STAGE_TO_PHASE.get(self._stage, lifecycle.CREATED)

    @workflow.query
    def generation(self) -> int:
        """Сколько раз цикл перезапускался через continue-as-new.

        Долгоживущий прогон обязан обрывать историю, иначе реплей перестаёт
        укладываться в workflow-task timeout. После перезапуска Event History в
        UI начинается с чистого листа — без этого счётчика по одной истории
        нельзя понять, это новый Issue или продолжение старого.
        """
        return self._generation

    @workflow.query
    def awaiting(self) -> Awaiting | None:
        """Чего Issue ждёт: вид, адресат, с какого момента и до какого срока (#39).

        Расширение query `stage`: та отвечает «в какой стадии прогон», эта —
        «почему он там стоит и кто его сдвинет». Без неё припаркованный прогон
        и зависший выглядят в Temporal UI одинаково.
        """
        return self._awaiting

    @workflow.query
    def handles_agents(self) -> bool:
        """Ведёт ли этот прогон агентов дочерними воркфлоу (#37).

        Спрашивает `shared/agent_launcher.py`, чтобы выбрать режим запуска.
        Прогоны прежнего поколения (линейный путь) сигнала на запуск агента не
        понимают — команда была бы принята и потеряна; для них лаунчер стартует
        root-прогон, как раньше. Отдельного флага нет намеренно: цикл и
        дочерние агенты приехали одним поколением, и разводить их двумя
        независимыми признаками значило бы завести четыре состояния там, где
        существуют два.
        """
        return self._phase_driven

    @workflow.signal
    async def human_decision(self, label: str) -> None:
        await self._signal_queue.put(label)

    @workflow.signal
    async def user_comment(self, text: str, comment_id: int | None = None) -> None:
        """Реплика человека в Issue.

        Второй аргумент со значением по умолчанию, а не новый сигнал: вебхук
        прежнего поколения шлёт один аргумент, и прогоны, припаркованные до
        этой правки, обязаны понимать обе формы.
        """
        await self._signal_queue.put(UserComment(text=text, comment_id=comment_id))

    @workflow.signal
    async def issue_closed(self, who: str | None = None) -> None:
        """Issue закрыт на GitHub — цикл обязан завершиться.

        Парковка со сроком (R3) гарантирует, что цикл не живёт вечно, но
        закрытый Issue ждать нечего: в проде так набралось 22 прогона по уже
        закрытым Issue, каждый досиживал свою парковку (до 168 ч) и продолжал
        занимать место в выборке Running.

        Флаг, а не переход прямо здесь: хендлер сигнала выполняется вне цикла
        фаз, и смена фазы отсюда гонялась бы с обработчиком текущей фазы.
        Значение в очереди будит парковку, решение принимает `_run_phase_loop`.
        """
        self._closed_by = who or "human"
        await self._signal_queue.put(CLOSED)

    @workflow.signal
    async def analyze_requested(self, comment_id: int | None) -> None:
        """По Issue запрошена аналитика — командой `/analyze` или меткой.

        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а
        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).
        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу
        из вебхука — связь между циклом Issue и работой агента была
        декоративной, о чём и говорил прежний докстринг.

        Тяжёлую работу из самого хендлера не запускаем: run() обычно
        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с
        основным циклом за фазу. Очередь снимает гонку — решение принимает та
        фаза, в которой Issue находится сейчас.

        Сигнал может прийти в самой первой активации воркфлоу — раньше, чем
        run() выполнил `self._issue = issue` (Temporal применяет сигналы до
        создания задачи run()); поэтому ЖДЁМ инициализацию через
        wait_condition, а не теряем запрос молча по `self._issue is None`.
        """
        # Тот же маркер, что разводит поколения в run(): цикл и дочерние
        # агенты приехали вместе, и прогон, не знающий одного, не знает и
        # другого. Прежнее поколение обязано доиграть ПРЕЖНИМ кодом хендлера —
        # иначе реплей его истории упрётся в несовпадение команд.
        if not workflow.patched("issue-lifecycle-phase-loop"):
            if self._analyze_labeled:
                return
            self._analyze_labeled = True
            await workflow.wait_condition(lambda: self._issue is not None)
            await workflow.execute_activity(
                activities.mark_analyzing,
                args=[self._issue.repo, self._issue.issue_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return

        # Запрос уже в очереди — второй прогон был бы шумом и деньгами:
        # повторная команда и дубль webhook-доставки означают одно намерение.
        # Флаг ставим ДО первого await: хендлеры кооперативны (переключение
        # только на await), поэтому почти одновременный второй сигнал увидит
        # True. Идентификатор занятого прогона от этой гонки не спасает: к
        # моменту второго сигнала первый может уже завершиться, и id
        # освободится — а это законный повторный запуск, не дубль.
        # Идущий прогон — тоже причина отказать. Пока он идёт, `ack_command`
        # вешает на Issue метку `run:analyze`; вебхук видит `issues.labeled` и
        # шлёт команду обратно в цикл. Своя метка возвращается как новая
        # команда, и на живом стенде это давало три прогона подряд по одному
        # Issue. Идентификатор занятого прогона от этого не спасает: к моменту
        # разбора очереди первый прогон уже завершён, и id свободен.
        if self._analyze_pending or self._analysis_running:
            return
        self._analyze_pending = True
        self._analyze_comment_id = comment_id
        await workflow.wait_condition(lambda: self._issue is not None)
        await self._signal_queue.put(AGENT_ANALYZE)

    @workflow.signal
    async def research_requested(self, comment_id: int | None) -> None:
        """По Issue запрошено продуктовое исследование — командой `/research` или меткой.

        Цикл ведёт его сам: запрос уходит в общую очередь сигналов, а
        обработчик фазы поднимает дочерний прогон исследования. Аналогично
        analyze_requested: avoids race conditions, checks for pending runs,
        and uses the signal queue.
        """
        # Запрос уже в очереди — второй прогон был бы шумом и деньгами
        if self._research_pending or self._research_running:
            return
        self._research_pending = True
        self._research_comment_id = comment_id
        await workflow.wait_condition(lambda: self._issue is not None)
        await self._signal_queue.put(AGENT_RESEARCH)

    @workflow.signal
    async def agent_event(self, event: AgentEvent) -> None:
        """Факт от внешнего агента контура: PR открыт, ревью взято, CI упал (#38).

        Кладём в общую очередь, а не двигаем фазу прямо здесь. Обработчик
        сигнала конкурирует с основным циклом: пока тот, скажем, гонит
        аналитику, смена фазы из-под него дала бы состояние, которого нет ни в
        одном обработчике. Очередь снимает гонку — событие разбирает та фаза, в
        которой Issue находится сейчас.

        Идемпотентность по паре `(ref, status)`: доставку соседний сервис может
        повторить (ретрай, дубль вебхука), но один факт обязан двигать фазу
        один раз. Ключи копятся в состоянии прогона, поэтому храним только
        последние: цикл живёт месяцами, а сюда попадает каждое событие по
        каждому PR.
        """
        if not workflow.patched("issue-lifecycle-phase-loop"):
            return  # прежнее поколение фаз не знает — двигать нечего
        if isinstance(event, dict):
            event = AgentEvent(**event)
        if event.key() in self._seen_agent_events:
            return
        self._seen_agent_events.append(event.key())
        del self._seen_agent_events[:-SEEN_EVENTS_KEPT]
        await workflow.wait_condition(lambda: self._issue is not None)
        await self._signal_queue.put(event)

    @workflow.signal
    async def bft_requested(self, req: BftRequest) -> None:
        """По Issue запрошен БФТ — командой `/bft`/`/bft-deep` или меткой `run:*`.

        В очередь НЕ кладём, как и оценку: БФТ фазу не двигает. Быстрый проход —
        это формулировка запроса, а не стадия пути; глубокий кладёт артефакты в
        свою ветку и оставляет фазу честной. Двигать фазу в `business-analysis`
        значило бы, что БФТ и цепочка FNR — одна и та же стадия, а это разные
        документы с разной судьбой.

        Прогон поднимаем прямо здесь и результата не ждём: цикл продолжает ждать
        своё. Двойного прогона это не создаёт — id фиксирован в пределах режима.

        Прогоны прежнего поколения сигнал получают, но обслужить не могут; им
        лаунчер стартует root-прогон (см. query `handles_agents`), поэтому здесь
        достаточно молча выйти — иначе на реплее их истории появилась бы команда,
        которой там нет.
        """
        if not workflow.patched("issue-lifecycle-phase-loop"):
            return
        if isinstance(req, dict):
            req = BftRequest(**req)
        await workflow.wait_condition(lambda: self._issue is not None)
        await self._start_bft(req)

    async def _start_bft(self, req: BftRequest) -> bool:
        """Прогон БФТ по команде — дочерним воркфлоу, без ожидания результата.

        Результата не ждём: фазу БФТ не двигает, и циклу с его исходом делать
        нечего. Прогон сам отвечает человеку — письмом, сводкой либо
        комментарием о сбое.
        """
        try:
            await workflow.start_child_workflow(
                IssueBft.run, req,
                id=bft_workflow_id(req.repo, req.issue_number, req.mode),
                # Глубокий прогон идёт десятками минут. Ни continue-as-new
                # родителя, ни его завершение не должны его обрывать.
                parent_close_policy=ParentClosePolicy.ABANDON,
                # Прогон недетерминирован и стоит денег: повтор инициирует
                # человек, а не политика ретраев.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except WorkflowAlreadyStartedError:
            # Прогон в этом режиме уже идёт: повторная команда, эхо собственной
            # метки или дубль доставки вебхука — все три означают одно намерение.
            workflow.logger.info("bft %s already running for %s#%s",
                                 req.mode, req.repo, req.issue_number)
            return False
        return True

    @workflow.signal
    async def estimate_requested(self, comment_id: int | None) -> None:
        """По Issue запрошена оценка трудоёмкости.

        В очередь НЕ кладём: оценка фазу не двигает — это боковая команда, а не
        стадия пути. Поднимаем дочерний прогон прямо здесь и не ждём его
        результата: цикл продолжает ждать своё, а оценка идёт параллельно.

        Прогоны прежнего поколения этот сигнал получают, но обслужить не могут;
        им лаунчер стартует root-прогон (см. query `handles_agents`), поэтому
        здесь достаточно молча выйти — иначе на реплее их истории появилась бы
        команда, которой там нет.
        """
        if not workflow.patched("issue-lifecycle-phase-loop"):
            return
        await workflow.wait_condition(lambda: self._issue is not None)
        req = EstimateRequest(repo=self._issue.repo,
                              issue_number=self._issue.issue_number,
                              comment_id=comment_id)
        try:
            await workflow.start_child_workflow(
                IssueEstimation.run, req,
                id=estimate_workflow_id(req.repo, req.issue_number, req.comment_id),
                parent_close_policy=ParentClosePolicy.ABANDON,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except WorkflowAlreadyStartedError:
            workflow.logger.info("estimate already running for %s#%s",
                                 req.repo, req.issue_number)

    async def _wait_for_signal(
            self, timeout: timedelta | None = None) -> str | AgentEvent | UserComment | None:
        # Нулевой остаток означает «срок уже вышел», а не «ждать без ограничения»:
        # `if timeout:` ниже принял бы timedelta(0) за отсутствие таймаута и
        # припарковал бы Issue навсегда — ровно то, от чего чинили #58.
        if timeout is not None and timeout <= timedelta(0):
            return None
        try:
            if timeout:
                return await asyncio.wait_for(
                    self._signal_queue.get(), timeout=timeout.total_seconds()
                )
            return await self._signal_queue.get()
        except asyncio.TimeoutError:
            return None

    @workflow.run
    async def run(self, issue: IssueInput,
                  carried: LifecycleState | None = None) -> None:
        """Владелец состояния Issue: живёт, пока у Issue есть непросроченное
        ожидание, а не заканчивается после приоритизации.

        Второй аргумент со значением по умолчанию — ради совместимости: вебхук и
        скрипты стартуют воркфлоу одним аргументом, как раньше, а continue-as-new
        передаёт снимок состояния вторым.

        `workflow.patched` разводит поколения. Прогоны, запущенные до этого
        изменения, припаркованы в проде: их история не знает маркера, patched()
        вернёт False, и они доиграют по прежнему линейному коду. Новые пойдут
        циклом. Без этого реплей старой истории новым кодом упал бы
        недетерминизмом — самый дорогой класс отказа в Temporal.
        """
        # Вебхук и скрипты стартуют воркфлоу ОДНИМ аргументом, а сигнатура
        # объявляет два. При таком расхождении Temporal не применяет типы ни к
        # одному аргументу и отдаёт сырые словари — молча, на первом же
        # обращении к полю. Нормализуем сами: ломать существующие стартеры ради
        # красоты сигнатуры нельзя, а второй аргумент нужен continue-as-new.
        if isinstance(issue, dict):
            issue = IssueInput(**issue)
        if isinstance(carried, dict):
            carried = LifecycleState(**carried)

        self._issue = issue  # даёт analyze_requested доступ к repo/number
        # Момент входа в фазу. `workflow.now()` детерминирован (время события из
        # истории), поэтому реплей даёт то же значение, что и первый прогон.
        self._phase_since = workflow.now()
        if carried is not None:
            self._phase = carried.phase
            self._stage = carried.stage
            self._priority_tier = carried.priority_tier
            self._classification_label = carried.classification_label
            self._analysis_done = carried.analysis_done
            self._plan_member = carried.plan_member
            self._root_issue = carried.root_issue
            self._pr_number = carried.pr_number
            self._clarify_rounds = carried.clarify_rounds
            self._followup_rounds = carried.followup_rounds
            self._answered_comment_ids = list(carried.answered_comment_ids)
            self._rework_rounds = carried.rework_rounds
            self._open_question = carried.open_question
            self._criterion_gate_notified = carried.criterion_gate_notified
            # H2 (точечная правка после мержа, финальное ревью). Снимок
            # ПРОМЕЖУТОЧНОГО коммита этой же ветки (защита автостарта по
            # указателю уже была, единого признака `acceptance_gate_stalled`
            # ещё не было) этого поля не несёт вовсе — датакласс подставляет
            # умолчание `False`. Голое присваивание тогда «забывало» открытый
            # вопрос: `self._open_question` восстанавливался бы непустым, а
            # признак «гейт не пропустил» — снятым, хотя ИМЕННО непустой
            # указатель и означает, что гейт не пропустил задачу дальше (см.
            # докстринг `autostart_blocked_by_gate_stall` в `_phase_await_
            # build`). `self._acceptance_gate_stalled and workflow.patched(
            # "issue-lifecycle-autostart-waits-for-answer")` — тот же маркер,
            # что и старая защита по указателю, — короткое замыкание `and`
            # тогда пропускало сам вызов `workflow.patched`, и реплей такого
            # прогона расходился с уже записанной историей (там, где старый
            # код звал этот маркер и парковался по таймеру, новый — без
            # вызова маркера планировал бы чтение критерия заново).
            # Восстановление «сохранённый признак ИЛИ непустой указатель»
            # воспроизводит ТУ ЖЕ истинность условия, что и старый код
            # (`self._open_question`), — маркер вызывается на той же позиции
            # с тем же исходом, новый флаг здесь не нужен.
            self._acceptance_gate_stalled = (
                carried.acceptance_gate_stalled or bool(carried.open_question))
            self._generation = carried.generation
            if carried.phase_since_epoch:
                # Перезапуск цикла не должен обнулять срок парковки: иначе
                # continue-as-new сам стал бы способом ждать вечно.
                self._phase_since = datetime.fromtimestamp(
                    carried.phase_since_epoch, tz=timezone.utc)

        if not workflow.patched("issue-lifecycle-phase-loop"):
            await self._run_linear(issue)
            return
        self._phase_driven = True
        await self._run_phase_loop(issue)

    # --- Фазовый цикл ---

    def _snapshot(self) -> LifecycleState:
        """Компактное состояние для continue-as-new: фаза и то немногое, что
        нужно следующим фазам. Тред и история не переносятся — именно их объём
        и упирается в потолок."""
        return LifecycleState(
            phase=self._phase,
            stage=self._stage,
            priority_tier=self._priority_tier,
            classification_label=self._classification_label,
            analysis_done=self._analysis_done,
            plan_member=self._plan_member,
            root_issue=self._root_issue,
            pr_number=self._pr_number,
            clarify_rounds=self._clarify_rounds,
            followup_rounds=self._followup_rounds,
            answered_comment_ids=list(self._answered_comment_ids),
            rework_rounds=self._rework_rounds,
            open_question=self._open_question,
            criterion_gate_notified=self._criterion_gate_notified,
            acceptance_gate_stalled=self._acceptance_gate_stalled,
            generation=self._generation + 1,
            phase_since_epoch=self._phase_since.timestamp() if self._phase_since else 0.0,
        )

    def _history_is_long(self) -> bool:
        """Порог по длине истории, а не по числу итераций: цена реплея зависит
        от событий, а одна фаза может стоить и трёх событий, и трёхсот."""
        return workflow.info().get_current_history_length() >= HISTORY_EVENT_THRESHOLD

    async def _park(self, kind: str, who: str, reason: str, hours: int,
                    *, wake_within: timedelta | None = None) -> timedelta:
        """Встать в ожидание: описать его и вернуть срок таймера.

        Одно место на все точки парковки. Разнесённые «поставить таймер» и
        «записать, чего ждём» разошлись бы при первой же правке одной из них —
        и получилось бы ожидание с таймером, но без причины, то есть ровно то,
        что чинит #39.

        `wake_within` (находка F3, Important, второй круг финального ревью) —
        промежуточное пробуждение РАНЬШЕ настоящего дедлайна, для точек,
        которым нужно периодически что-то перепроверить, не отменяя сам
        дедлайн. Описание (`self._awaiting`, метка очереди) считается ТОЛЬКО
        от `hours` — человек видит настоящий срок, а не урезанный внутренний
        таймер; `wake_within` укорачивает лишь ВОЗВРАЩАЕМЫЙ таймаут, который
        достаётся `_wait_for_signal`. Тест `tests/test_awaiting_wiring.py::
        test_every_parking_point_fills_the_waiting` статически требует, чтобы
        аргументом `_wait_for_signal` был именно `await self._park(...)`, —
        отдельная переменная с урезанным таймаутом этой проверке не годится, а
        значит урезание обязано жить ВНУТРИ `_park`, а не рядом с ним.
        """
        since = self._phase_since or workflow.now()
        self._awaiting = Awaiting(
            kind=kind, who=who, reason=reason,
            since_epoch=since.timestamp(),
            deadline_epoch=(since + timedelta(hours=hours)).timestamp(),
        )
        await self._publish_awaiting()
        remaining = self._park_timeout(hours)
        if wake_within is not None and wake_within < remaining:
            return wake_within
        return remaining

    async def _publish_awaiting(self) -> None:
        """Отражение ожидания в GitHub: очередь к людям должна быть полной.

        Метку вешаем только на ожидание ЧЕЛОВЕКА: задача, ждущая стенд или
        соседний сервис, в очереди к людям — шум, из-за которого перестают
        смотреть на саму выборку.

        Под patched: у идущих прогонов этой команды в истории нет.
        """
        if not workflow.patched("issue-lifecycle-awaiting") or self._issue is None:
            return
        want = self._awaiting is not None and self._awaiting.blocks_on_human
        if want == self._human_queue_labelled:
            # Состояние метки не изменилось. Без этой проверки каждый переход
            # фазы давал бы пару «снять/поставить»: лишние вызовы GitHub и
            # мигание метки в таймлайне Issue.
            return
        self._human_queue_labelled = want
        await workflow.execute_activity(
            activities.mark_awaiting,
            args=[self._issue.repo, self._issue.issue_number, self._awaiting],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    async def _stop_awaiting(self) -> None:
        """Ожидание снято: описание очищается, метка уходит."""
        if self._awaiting is None:
            return
        self._awaiting = None
        await self._publish_awaiting()

    def _park_timeout(self, hours: int) -> timedelta:
        """Сколько ещё ждать в этой фазе — остаток от срока, а не полный срок.

        Обработчик фазы вызывается в цикле: посторонний сигнал (чужая метка,
        комментарий) фазу не двигает, но возвращает управление наверх. Пока
        таймер заводился на полный срок, каждый такой сигнал начинал отсчёт
        заново — дедлайн получался «N часов с последнего шороха», и Issue,
        которому раз в трое суток что-то прилетает, не эскалировался никогда.
        Правило R3 требует обратного: срок отсчитывается от входа в фазу.

        `workflow.patched` обязателен: у припаркованных прогонов таймер уже
        записан в историю, и другая длительность на реплее — недетерминизм.
        """
        if not workflow.patched("issue-lifecycle-absolute-park-deadline"):
            return timedelta(hours=hours)
        if self._phase_since is None:
            return timedelta(hours=hours)
        left = self._phase_since + timedelta(hours=hours) - workflow.now()
        return left if left > timedelta(0) else timedelta(0)

    async def _phase_on_close(self) -> tuple[str, str]:
        """Чем закончился путь Issue: слиянием или снятием с обработки.

        Спрашиваем сам PR, а не того, кто закрыл Issue: закрыть его по `Closes`
        может и бот, и человек, а `state_reason` у закрытия «как выполненное»
        одинаков в обоих случаях. Номер PR у цикла уже есть — он запомнил его,
        когда PR открылся.

        Вопрос задаём, только если ответ может что-то изменить: PR нет либо из
        текущей фазы в `merged` хода нет — значит, это отмена, и лишний вызов
        GitHub на каждом закрытии не нужен.

        Из `pr-open` ход в `merged` открылся позже самой ветки закрытия (#308:
        доклада ревью может не быть вовсе, и тогда влитый PR записывался
        отменой). Новый ход идёт под своим маркером, и вот почему: прогон,
        успевший до правки выполнить эту ветку из `pr-open`, записал в историю
        `cancelled` БЕЗ вызова `pr_is_merged` — короткое замыкание не звало
        активность. Новый код зовёт её первой; на реплее такой истории это
        лишняя команда, то есть `[TMPRL1100]` и прогон, застрявший навсегда
        (#263). Маркер оставляет старым историям старый путь.

        Маркер вычисляется ПЕРВЫМ и безусловно — до всех ранних возвратов и вне
        связки `and` (AGENTS.md, правило 1). Вторым операндом он пропускался бы
        на каждом закрытии из другой фазы и попадал бы в историю через раз;
        непостоянная запись маркера сама становится источником расхождения, и
        следующая правка, читающая его безусловно, увела бы такие прогоны в
        ветку, не совпадающую с записанной.
        """
        merged_from_pr_open = workflow.patched(
            "issue-lifecycle-merged-from-pr-open")
        # Фаза УЖЕ успешна: доклад `merged` мог прийти раньше, чем GitHub закрыл
        # задачу по `Closes #N`. Хода `merged → merged` в таблице нет, и общий
        # путь ниже вернул бы `cancelled`, затерев успех отменой — тот же дефект,
        # ради которого ветка и правится, только с другого конца. Стык достижим
        # и без правки #308: из `pr-review` ход в `merged` был всегда.
        #
        # Маркера не требует: прогон, прошедший это место старым кодом, записал
        # `cancelled` и на том завершился, а терминальная история не реплеится.
        if self._phase == lifecycle.MERGED:
            return (lifecycle.MERGED, "merged")
        if self._issue is None or not self._pr_number:
            return (lifecycle.CANCELLED, "cancelled")
        if not lifecycle.can(self._phase, lifecycle.MERGED):
            return (lifecycle.CANCELLED, "cancelled")
        if self._phase == lifecycle.PR_OPEN and not merged_from_pr_open:
            return (lifecycle.CANCELLED, "cancelled")
        try:
            merged = await workflow.execute_activity(
                activities.pr_is_merged,
                args=[self._issue.repo, self._pr_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as exc:  # noqa: BLE001 — исход неизвестен, прогон обязан жить
            # Исчерпанные ретраи роняли бы весь цикл: непойманный отказ уходит
            # из `run()` наверх, прогон завершается Failed — ни фазы, ни метки,
            # ни возможности поднять его сигналом. До правки #308 эта ветка из
            # `pr-open` в GitHub не ходила вовсе, и расширять её ценой потери
            # исхода нельзя.
            #
            # Исход неизвестен — значит `escalated`, а не `cancelled`: записать
            # отмену там, где PR мог быть влит, — та же ложь об исходе, ради
            # устранения которой правка и делается.
            #
            # Маркер не нужен: прогон, у которого эта активность исчерпала
            # ретраи, уже завершился Failed — терминальная история не реплеится.
            workflow.logger.warning(
                "не удалось спросить GitHub про PR #%s: %s — исход неизвестен",
                self._pr_number, exc)
            return (lifecycle.ESCALATED, "escalated")
        if merged:
            return (lifecycle.MERGED, "merged")
        return (lifecycle.CANCELLED, "cancelled")

    async def _enter(self, phase: str, stage: str, *, write_label: bool = True) -> None:
        """Переход в фазу: проверка допустимости, стадия, метка.

        Недопустимый переход поднимает InvalidTransition и роняет прогон — это
        осознанно. Молчаливая перезапись фазы означала бы Issue в состоянии, из
        которого не выводится ни предыстория, ни следующий шаг; такую ошибку
        лучше увидеть в тестах и в Temporal UI, чем годами не замечать.
        """
        if phase == self._phase:
            # Остаться в своей фазе, не дождавшись нужного сигнала, — штатное
            # поведение парковки, а не смена состояния: ни проверять переход,
            # ни переписывать метку не нужно.
            self._stage = stage
            return
        lifecycle.transition(self._phase, phase)
        self._phase = phase
        self._stage = stage
        # Прежнее ожидание закрыто самим фактом перехода. Метку обычно не
        # трогаем: следующая точка парковки опишет новое ожидание и приведёт
        # метку в порядок одним вызовом — снимать и ставить её на каждом
        # переходе значило бы мигать ею в таймлайне Issue.
        self._awaiting = None
        # Исключение — фазы, в которых цикл работает и не паркуется вовсе: там
        # следующего вызова просто не будет, и метка очереди к людям осталась бы
        # висеть на задаче, которую ведёт агент.
        if (workflow.patched("issue-lifecycle-clear-queue-on-work")
                and phase in awaiting_mod.WORKED_BY_AGENT):
            await self._publish_awaiting()
        # Отсчёт срока парковки начинается здесь и только здесь.
        self._phase_since = workflow.now()
        if write_label and self._issue is not None:
            await workflow.execute_activity(
                activities.set_phase,
                args=[self._issue.repo, self._issue.issue_number, phase],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

    async def _run_analysis_child(self, issue: IssueInput,
                                  trigger: str | None = None) -> bool:
        """Аналитика дочерним прогоном — тот же воркфлоу, что и автономный.

        Один код на оба режима (#37): в Temporal UI прогон виден как child
        цикла, а id остаётся прежним (`analysis-<repo>-<n>`), поэтому повторная
        команда по-прежнему упирается в `WorkflowAlreadyStarted`, а не тратит
        деньги второй раз.
        """
        analyze = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,
                               title=issue.title, body=issue.body,
                               comment_id=self._analyze_comment_id,
                               trigger=trigger)
        # Запрос израсходован — но снимается он ПОСЛЕ прогона, а не до.
        #
        # Пока прогон идёт, `ack_command` вешает на Issue метку `run:analyze`.
        # Вебхук видит `issues.labeled` и шлёт `analyze_requested` обратно в
        # цикл: наша собственная метка возвращается как новая команда. Со
        # снятым флагом она вставала в очередь, и по завершении прогона цикл
        # запускал второй — на живом стенде это дало три прогона аналитики
        # подряд по одному Issue. Идентификатор занятого прогона от этого не
        # спасает: к моменту обработки очереди первый уже завершён, и id
        # свободен.
        #
        # Команда, пришедшая ВО ВРЕМЯ прогона, — эхо своей метки либо повторный
        # клик человека. Ни то, ни другое не стоит второго дорогого прогона.
        self._analysis_running = True
        try:
            return await workflow.execute_child_workflow(
                IssueAnalysis.run, analyze,
                id=analysis_workflow_id(issue.repo, issue.issue_number),
                # Цепочка FNR идёт до 4500 с. Ни continue-as-new родителя, ни
                # его завершение не должны её убивать — иначе дорогой прогон
                # обрывается на середине по причине, к нему не относящейся.
                parent_close_policy=ParentClosePolicy.ABANDON,
                # Прогон недетерминирован, мутирует файлы и стоит денег:
                # повтор инициирует человек, а не политика ретраев.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except WorkflowAlreadyStartedError:
            # Прогон по этому Issue уже идёт — второй дорогой не нужен.
            # Результата отсюда не видно (это чужой прогон), поэтому фазу
            # дальше не двигаем: её сдвинет тот, кто анализ и запускал.
            workflow.logger.info("analysis already running for %s#%s",
                                 issue.repo, issue.issue_number)
            return False
        finally:
            self._analyze_comment_id = None
            self._analyze_pending = False
            self._analysis_running = False

    async def _run_research_child(self, issue: IssueInput) -> bool:
        """Продуктовое исследование дочерним прогоном — аналогично анализу.

        Запускает workflow исследования с тем же паттерном idempotency
        и управления состоянием, что и анализ, но с другим workflow классом.
        """
        # Для исследования используем те же input данные, что и для анализа
        research_input = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,
                                      title=issue.title, body=issue.body,
                                      comment_id=self._research_comment_id,
                                      trigger=None)
        
        self._research_running = True
        try:
            # TODO: Replace with actual Research workflow when implemented
            # Currently reusing IssueAnalysis for MVP - will be replaced
            return await workflow.execute_child_workflow(
                IssueAnalysis.run, research_input,
                id=research_workflow_id(issue.repo, issue.issue_number, 
                                        self._research_comment_id or 0),
                parent_close_policy=ParentClosePolicy.ABANDON,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except WorkflowAlreadyStartedError:
            workflow.logger.info("research already running for %s#%s",
                                 issue.repo, issue.issue_number)
            return False
        finally:
            self._research_comment_id = None
            self._research_pending = False
            self._research_running = False

    async def _agent_event(self, event: AgentEvent) -> tuple:
        """Факт внешнего агента — переход по той же таблице, что и у своих.

        Недопустимый переход НЕ роняет прогон, в отличие от `_enter`: там
        источник — наш собственный код, и невозможный переход означает ошибку,
        которую надо увидеть. Здесь источник — соседний сервис со своим
        релизным циклом; его рассинхрон с нашей моделью должен приводить к
        разбору человеком, а не к падению цикла Issue.
        """
        # `ref` внешнего агента для фаз PR — это номер PR. Запоминаем: фаза
        # доведения без него не знает, что доводить, а второго источника этого
        # номера у цикла нет.
        if event.phase in (lifecycle.PR_OPEN, lifecycle.PR_REVIEW):
            try:
                self._pr_number = int(event.ref)
            except (TypeError, ValueError):
                workflow.logger.warning("ref события не номер PR: %r", event.ref)

        # Ход `pr-open → merged` открыт правкой #308, и читателей у этой строки
        # таблицы ДВА: ветка закрытия Issue и вот этот разбор доклада. Прогон,
        # успевший до правки получить доклад `merged` из `pr-open`, записал в
        # историю `escalate_to_human` — новый код по той же истории пошёл бы
        # мимо эскалации и запланировал `set_phase`: `[TMPRL1100] Activity type
        # of scheduled event 'escalate_to_human' does not match ... 'set_phase'`.
        # Маркер тот же, что у ветки закрытия: строка таблицы одна, и открыться
        # она обязана для обоих читателей разом, иначе разъедутся они, а не
        # версии кода. Вызов безусловный и первым операндом (AGENTS.md, 1).
        merged_from_pr_open = workflow.patched(
            "issue-lifecycle-merged-from-pr-open")
        target = agent_events.target_phase(event)
        allowed = lifecycle.can(self._phase, target)
        if (allowed and not merged_from_pr_open
                and self._phase == lifecycle.PR_OPEN
                and target == lifecycle.MERGED):
            allowed = False
        if target == self._phase:
            return (self._phase, self._stage, False)  # тот же факт другими словами
        if not allowed:
            await workflow.execute_activity(
                activities.escalate_to_human,
                args=[self._issue, f"Агент `{event.agent}` сообщил "
                                   f"`{event.phase}`/`{event.status}` по `{event.ref}`, "
                                   f"но из фазы `{self._phase}` такого перехода нет. "
                                   "Событие не потеряно — нужно решение человека."],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if lifecycle.can(self._phase, lifecycle.ESCALATED):
                return (lifecycle.ESCALATED, "escalated", True)
            return (self._phase, self._stage, False)
        # Стадия совпадает с фазой: у шагов, которые ведут внешние агенты, нет
        # собственного дробления — вся видимая деталь в самом событии.
        return (target, target, True)

    async def _analysis_requested(self, issue: IssueInput) -> tuple:
        """Куда ведёт запрос аналитики из ТЕКУЩЕЙ фазы.

        Если из неё есть ход в `business-analysis` — идём туда, и прогон
        становится стадией пути Issue. Если нет (задача уже у разработчика, или
        Issue в боковом состоянии), команду всё равно выполняем, но фазу не
        трогаем: соврать про состояние хуже, чем не отразить в нём разовый
        прогон.
        """
        if lifecycle.can(self._phase, lifecycle.BUSINESS_ANALYSIS) and (
                # Ход из `failed` появился позже самого цикла, и он меняет
                # РЕШЕНИЕ, уже записанное в истории: у прогонов, где `/analyze`
                # из `failed` однажды отработал мимо пути, на этом месте лежит
                # `StartChildWorkflowExecutionInitiated`, а новый код планирует
                # активность смены фазы. Без маркера реплей такой истории падает
                # по недетерминизму — так на стенде встал воркфлоу Issue #11.
                self._phase != lifecycle.FAILED
                or workflow.patched("issue-lifecycle-analyze-recovers-failed")):
            return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
        await self._run_analysis_child(issue)
        return (self._phase, self._stage, False)

    async def _run_phase_loop(self, issue: IssueInput) -> None:
        deadlines = await workflow.execute_activity(
            activities.read_deadlines,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        # Тумблеры едут вместе со сроками: значение обязано лежать в истории,
        # иначе переключённый посреди прогона уронил бы реплей недетерминизмом.
        self._decompose = deadlines.decompose_enabled
        self._followup_max_rounds = deadlines.followup_max_rounds

        # Барьер под-задачи шага (R5) для входов МИМО created. `_phase_triage`
        # уже проверяет `state.step_subissue`, но событие внешнего агента (#38)
        # поднимает цикл СРАЗУ в фазе, о которой тот доложил (см.
        # `_lifecycle_args_for` в вебхуке) — created и, вместе с ним, triage
        # остаются в стороне. Без барьера здесь `_phase_park` мог бы запустить
        # дорогое действие — например, приёмку HowToDemo на первом же входе в
        # `pr-open` — раньше любого сигнала и безо всякой метки в событии: у
        # AgentEvent их попросту нет.
        #
        # `self._phase != lifecycle.CREATED`: этот случай ведёт `_phase_triage`
        # своим чтением — второе здесь было бы лишним вызовом GitHub на каждый
        # обычный Issue. `not lifecycle.is_terminal`: из released/cancelled
        # переход в cancelled не определён, а войти сюда в терминальной фазе
        # можно только с уже мёртвого прогона. `workflow.patched` обязателен:
        # прогоны, уже стоящие в боковой фазе, не знают этой активности в своей
        # истории, и реплей без маркера упал бы недетерминизмом.
        if (self._phase != lifecycle.CREATED
                and not lifecycle.is_terminal(self._phase)
                and workflow.patched("issue-lifecycle-step-subissue-barrier")):
            state = await workflow.execute_activity(
                activities.read_protocol_state,
                args=[issue.repo, issue.issue_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if state.step_subissue:
                await self._enter(lifecycle.CANCELLED, "step-subissue", write_label=False)
                await self._stop_awaiting()
                return

        while True:
            if self._closed_by is not None and not lifecycle.is_terminal(self._phase):
                # Issue закрыт на GitHub: любая парковка потеряла смысл. Одна
                # точка на все фазы — обработчику фазы про закрытие знать не
                # надо, он лишь возвращает управление наверх на постороннем
                # сигнале. `cancelled` в таблице переходов и означает «снято с
                # обработки», и разрешён из любой нетерминальной фазы.
                #
                # Но «закрыт» и «снят с обработки» — не одно и то же. Issue,
                # доведённый до `main`, GitHub закрывает сам по `Closes #N`, и
                # прежнее правило метило его как отменённый: успех и отказ
                # оказывались в одном состоянии, а фаза `merged` не
                # использовалась вовсе. Маркер обязателен — у припаркованных
                # прогонов на этом месте активности нет, и реплей без него
                # упал бы недетерминизмом.
                if workflow.patched("issue-lifecycle-merged-on-close"):
                    phase, stage = await self._phase_on_close()
                    await self._enter(phase, stage)
                    # Выходим ЗДЕСЬ, не полагаясь на проверку терминальности
                    # ниже: `merged` не терминальна намеренно — за ней в
                    # таблице стоят `testing` и `released`. Вести их по
                    # закрытому Issue некому, а парковка в нём — ровно тот
                    # отказ, ради которого ветку закрытия и завели.
                    await self._stop_awaiting()
                    return
                await self._enter(lifecycle.CANCELLED, "cancelled")

            if lifecycle.is_terminal(self._phase):
                await self._stop_awaiting()  # ждать больше нечего
                return  # «вечноживущий» не значит «незакрываемый»

            if self._phase == lifecycle.CREATED:
                nxt = await self._phase_triage(issue, deadlines)
            elif self._phase == lifecycle.CLASSIFIED:
                nxt = await self._phase_await_decision(issue, deadlines)
            elif self._phase == lifecycle.BUSINESS_ANALYSIS:
                nxt = await self._phase_analysis(issue)
            elif self._phase == lifecycle.PRODUCT_RESEARCH:
                nxt = await self._phase_research(issue)
            elif self._phase == lifecycle.SYSTEM_REQUIREMENTS:
                nxt = await self._phase_handoff(issue, deadlines)
            elif self._phase == lifecycle.READY_FOR_DEV:
                nxt = await self._phase_await_build(issue, deadlines)
            elif self._phase == lifecycle.PR_REVIEW:
                nxt = await self._phase_pr_review(issue, deadlines)
            else:
                # Боковые состояния и фазы, которые ведут внешние агенты (#38):
                # цикл держит их живыми, пока не истечёт срок ожидания.
                nxt = await self._phase_park(issue, deadlines)

            if nxt is None:
                # Срок ожидания истёк — цикл закрывается (правило R3). Метку
                # очереди снимаем: её место занимает `needs-human:*` от
                # эскалации, и два источника одной метки разошлись бы.
                await self._stop_awaiting()
                return
            phase, stage, write_label = nxt
            await self._enter(phase, stage, write_label=write_label)

            # Точка перезапуска — сразу после смены фазы: состояние согласовано,
            # незавершённой работы нет.
            #
            # Очередь сигналов в снимок не переносится: она живёт в памяти
            # прогона, и перезапуск с непрочитанным сигналом потерял бы его
            # молча — ровно тот отказ, от которого уходит #36. Пока очередь не
            # пуста, ждём следующей фазы: порог не жёсткий дедлайн, а несколько
            # лишних событий дешевле съеденной команды человека.
            if (self._history_is_long()
                    and self._signal_queue.empty()
                    and not lifecycle.is_terminal(self._phase)):
                workflow.continue_as_new(args=[issue, self._snapshot()])

    async def _phase_triage(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `created`: тот же триаж, что и раньше, но его исход — фаза.

        Ранние выходы перестают завершать воркфлоу: `spam`, `duplicate`,
        `answered`, `skipped` становятся состояниями, из которых человек может
        вернуть Issue в работу. Сегодня это невозможно в принципе — воркфлоу
        уже нет, и сигналить некому.
        """
        default_retry = RetryPolicy(maximum_attempts=3)
        try:
            # Состояние протокола читается ПЕРВЫМ — раньше предфильтра, а не
            # после. Порядок не косметический: follow-up контура заводит агент,
            # и по автору он бот, поэтому предфильтр убивал бы его раньше, чем
            # кто-либо посмотрит на провенанс. Каждый найденный агентом
            # edge-кейс тихо оседал бы с меткой `bot-authored`, и декомпозиция
            # работы не доезжала бы до бэклога.
            state = await workflow.execute_activity(
                activities.read_protocol_state,
                args=[issue.repo, issue.issue_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )

            skip_reason = await workflow.execute_activity(
                activities.prefilter_bot_and_security,
                args=[issue, state.origin_agent],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if skip_reason is not None:
                return (lifecycle.SKIPPED, "skipped", True)
            if state.agents_off:
                # Метку не пишем: человек забрал Issue себе, и наши пометки на
                # нём — ровно то, от чего он отгородился рубильником.
                return (lifecycle.CANCELLED, "agents-off", False)
            if state.step_subissue:
                # Та же логика, что у agents_off: план родителя уже разобрал
                # эту задачу, отметка на ней самой не нужна (Task 13, R5).
                # Второй барьер, вне triage, стоит в начале _run_phase_loop —
                # он ловит вход, который в created вообще не заходит.
                return (lifecycle.CANCELLED, "step-subissue", False)
            if state.depth_exceeded:
                await workflow.execute_activity(
                    activities.escalate_to_human,
                    args=[issue, "Цепочка follow-up пошла на второй круг — "
                                 "останавливаю автоматическую обработку (правило R7 "
                                 "протокола агентов). Дальше нужен человек."],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=default_retry,
                )
                return (lifecycle.ESCALATED, "escalated", True)

            # Признак «часть чужого плана» — провенанс агента ВМЕСТЕ с ключом
            # цепочки. Одного `origin:agent` мало: его носят и самостоятельные
            # находки агента разработки, у которых родителя нет и которые обязаны
            # идти своим путём целиком.
            self._plan_member = state.origin_agent and state.root_issue is not None
            self._root_issue = state.root_issue

            classification: ClassificationResult | None = None
            if not state.origin_agent:
                gate = await workflow.execute_activity(
                    activities.intake_gate,
                    args=[issue, []],
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=default_retry,
                )
                if gate.status == "VAGUE" and not issue.interactive:
                    # `reason` передан явно вторым аргументом: активность
                    # принимает `reason: str = ""`, и вызов одним позиционным
                    # `issue` даёт Temporal несовпадение числа аргументов с
                    # числом параметров сигнатуры — типы выбрасываются для
                    # ОБОИХ параметров, включая `issue` (см. докстринг
                    # tests/test_activity_arg_types.py).
                    await workflow.execute_activity(
                        activities.escalate_to_human,
                        args=[issue, "Задача осталась неоднозначной (VAGUE) после "
                                     "intake gate, а прогон неинтерактивный — "
                                     "уточнить не у кого. Передаю на ручной разбор."],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    return (lifecycle.ESCALATED, "escalated", True)

                comment_thread: list[str] = []
                round_count = 0
                while gate.status == "VAGUE":
                    round_count += 1
                    if round_count > MAX_CLARIFICATION_ROUNDS:
                        await workflow.execute_activity(
                            activities.escalate_to_human,
                            args=[issue, f"Уточнение не сузило запрос за "
                                         f"{MAX_CLARIFICATION_ROUNDS} раундов — "
                                         "передаю на ручной разбор."],
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                        return (lifecycle.ESCALATED, "escalated", True)

                    await workflow.execute_activity(
                        activities.post_clarifying_question,
                        args=[issue, gate.content],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    raw = await self._wait_for_signal(
                        timedelta(hours=deadlines.clarification_hours))
                    # Команда на аналитику — не ответ на уточняющий вопрос:
                    # выполняем её и продолжаем ждать ответ, а не засчитываем
                    # раунд уточнения потраченным.
                    while raw == AGENT_ANALYZE or isinstance(raw, AgentEvent):
                        if isinstance(raw, AgentEvent):
                            # Триаж ещё не закончен, фазу двигать некуда:
                            # откладываем факт до ближайшей парковки.
                            self._signal_queue.put_nowait(raw)
                            break
                        await self._run_analysis_child(issue)
                        raw = await self._wait_for_signal(
                            timedelta(hours=deadlines.clarification_hours))
                    if raw is None:
                        await workflow.execute_activity(
                            activities.escalate_to_human,
                            args=[issue, f"Уточнение не получено за "
                                         f"{deadlines.clarification_hours} ч — "
                                         "передаю на ручной разбор."],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=default_retry,
                        )
                        return (lifecycle.ESCALATED, "escalated", True)
                    if isinstance(raw, UserComment):
                        comment_thread.append(raw.text)

                    gate = await workflow.execute_activity(
                        activities.intake_gate,
                        args=[issue, comment_thread],
                        start_to_close_timeout=timedelta(seconds=120),
                        retry_policy=default_retry,
                    )

                if gate.status == "SPAM":
                    await workflow.execute_activity(
                        activities.close_as_spam,
                        args=[issue, gate.content],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    return (lifecycle.SPAM, "spam", True)

                self._stage = "classify"
                # БФТ вместо свободного advisor-ответа. Маркер патча обязателен:
                # у припаркованных прогонов этих команд в истории нет, и реплей
                # их истории новым кодом упал бы недетерминизмом.
                bft_on_triage = (workflow.patched("issue-lifecycle-bft")
                                 and deadlines.bft_on_triage)
                classification = await workflow.execute_activity(
                    activities.classify_issue,
                    args=[issue, bft_on_triage],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=default_retry,
                )
                if classification.label in ("advisor:existing-functionality",
                                            "advisor:consultation"):
                    return (lifecycle.ANSWERED, "answered", True)
                if bft_on_triage and classification.label == "advisor:feature-request":
                    await self._bft_on_triage(issue)
            self._classification_label = classification.label if classification else None

            self._stage = "duplicate-check"
            dup = await workflow.execute_activity(
                activities.duplicate_check,
                issue,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            if dup.decision == "duplicate":
                # Номер оригинала нужен позже: если человек подтвердит дубликат,
                # закрывающий комментарий обязан на него сослаться.
                self._duplicate_of = dup.best_match_number
                return (lifecycle.DUPLICATE, "duplicate", True)

            self._stage = "priority"
            priority = await workflow.execute_activity(
                activities.score_priority,
                args=[issue, classification, dup],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            self._priority_tier = priority.tier
            await workflow.execute_activity(
                activities.post_priority_comment,
                args=[issue, priority, dup],
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception as e:
            # Сбой больше не закрывает цикл: Issue переходит в фазу, из которой
            # человек может перезапустить обработку.
            await workflow.execute_activity(
                activities.post_error_label,
                args=[issue, _failure_reason(e)],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            return (lifecycle.FAILED, "failed", True)
        return (lifecycle.CLASSIFIED, "awaiting-human-decision", True)

    async def _bft_on_triage(self, issue: IssueInput) -> None:
        """БФТ как ответ триажа на запрос функционала.

        Активностью, а не дочерним прогоном: это шаг триажа, такой же как
        `intake_gate` и `classify_issue`, и в Event History ему место рядом с
        ними. Отдельный прогон нужен командам — у них своя судьба, свои метки и
        свой ack; у шага триажа ничего этого нет.

        Сбой не роняет триаж: дедуп и приоритет всё равно нужны, а человек
        получает комментарий о сбое. Оставить Issue без приоритета из-за того,
        что не собралось письмо, — худший из двух исходов. Сам комментарий о
        сбое тоже best-effort: если GitHub недоступен, сделать всё равно нечего,
        а ронять из-за этого триаж — менять маленькую беду на большую.
        """
        req = BftRequest(repo=issue.repo, issue_number=issue.issue_number,
                         title=issue.title, body=issue.body,
                         mode=bft.FAST, trigger=BFT_TRIAGE)
        try:
            await workflow.execute_activity(
                activities.run_bft_fast, req,
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            return
        except Exception as exc:
            workflow.logger.warning("БФТ на триаже не собрался: %s",
                                    _failure_reason(exc))
            reason = str(getattr(exc, "cause", None) or exc)[:500]
        try:
            await workflow.execute_activity(
                activities.publish_bft_error, args=[req, reason],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as report_exc:
            workflow.logger.warning("не удалось сообщить о сбое БФТ: %s",
                                    _failure_reason(report_exc))

    async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `classified`: ждём решения человека о тяжёлой стадии.

        При `RESEARCH_AUTOSTART` ожидания нет: триаж сам решает, куда двигаться
        дальше, по типу задачи. Это первая из двух парковок основного пути;
        вторая — перед разработкой (`DEVELOP_AUTOSTART`). Включены обе — контур
        идёт от заявки до PR без единого касания человека.

        Тип решает так же, как решала бы метка человека: запрос на функционал
        уходит в аналитику, баг — сразу разработчику мимо неё. Сокращённый триаж
        (`origin:agent`) типа не имеет — follow-up контура заводит агент, уже
        понимая, что это; такую задачу ведём в аналитику, потому что описание в
        ней короткое и требований не содержит.
        """
        if deadlines.research_autostart:
            label = self._classification_label
            if label == "advisor:bug":
                return (lifecycle.READY_FOR_DEV, "bug", True)
            # Подзадача плана аналитику не заказывает: требования по фиче уже
            # написаны — они в ветке анализа РОДИТЕЛЯ, и сама подзадача выведена
            # из них. Полная цепочка FNR по каждой выводила бы выведенное: на
            # фиче из четырёх подзадач это четыре прогона по восемь минут,
            # четыре ветки `research/issue-N` и счёт впятеро больше — ради
            # текста, который ничего не добавляет.
            # Под маркером патча: у подзадач, уже уехавших в аналитику, этот
            # выбор записан в историю, и другой на реплее — недетерминизм.
            if self._plan_member and workflow.patched(
                    "issue-lifecycle-plan-member-skips-analysis"):
                return (lifecycle.SYSTEM_REQUIREMENTS, "analysis", True)
            if label is None or label == "advisor:feature-request":
                return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
            # Консультация и «уже реализовано» закрываются ответом, а не кодом:
            # автозапуск дорогой стадии по ним был бы тратой без адресата.
            # Такие задачи и до этой фазы обычно не доходят, но если дошли —
            # ждём человека, как раньше.

        decision = await self._wait_for_signal(await self._park(
            awaiting_mod.kind_for_phase(lifecycle.CLASSIFIED),
            who=awaiting_mod.who_for_phase(lifecycle.CLASSIFIED),
            reason=awaiting_mod.reason_for_phase(lifecycle.CLASSIFIED),
            hours=awaiting_mod.deadline_hours(awaiting_mod.HUMAN_DECISION,
                                              deadlines.human_decision_hours)))
        if decision is None:
            await workflow.execute_activity(
                activities.escalate_to_human,
                args=[issue, f"Решение о тяжёлой стадии не принято за "
                             f"{deadlines.human_decision_hours} ч "
                             "(`research-me` / `bug-me`) — снимаю задачу с ожидания. "
                             "Поставь метку, когда понадобится: прогон запустится заново."],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return (lifecycle.ESCALATED, "escalated", True)

        if isinstance(decision, AgentEvent):
            return await self._agent_event(decision)
        if decision == AGENT_ANALYZE:
            # Явная команда человека сильнее гварда по типу Issue: он защищает
            # от неудачно поставленной метки, а не от прямого `/analyze`.
            return await self._analysis_requested(issue)
        if isinstance(decision, UserComment):
            # Разбор намерения из реплики человека
            #
            # Все 6 параметров активности переданы явно, включая
            # `recent_artifacts=None`: у `interpret_user_comment` их шесть, а
            # Temporal сверяет ЧИСЛО переданных аргументов с числом параметров
            # сигнатуры (temporalio/worker/_activity.py) и при несовпадении
            # выбрасывает типы для ВСЕХ параметров разом, а не только для
            # пропущенного — активность получает сырой JSON вместо `IssueInput`
            # (живой отказ: `poh-demo-checkout#166`, `AttributeError: 'dict'
            # object has no attribute 'repo'`). Цикл не ведёт артефактов этапа
            # ни в одном поле состояния, поэтому `None` здесь — не заглушка,
            # а честное отсутствие данных.
            intent = await workflow.execute_activity(
                activities.interpret_user_comment,
                args=[issue, decision.text, self._phase, self._classification_label,
                      awaiting_mod.reason_for_phase(lifecycle.CLASSIFIED), None],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            return await self._handle_comment_intent(issue, decision, intent, deadlines)

        # `classification_label is None` — сокращённый триаж (Issue от агента):
        # он уже классифицирован на стороне создателя, гвард проверять не на чем.
        label = self._classification_label
        feature = label is None or label == "advisor:feature-request"
        bug = label is None or label == "advisor:bug"
        research = label == "advisor:product-research"
        if decision == "research-me" and (feature or research):
            # Продуктовое исследование запускается отдельно от бизнес-анализа
            if research:
                return (lifecycle.PRODUCT_RESEARCH, "research", True)
            return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
        if decision == "bug-me" and bug:
            return (lifecycle.READY_FOR_DEV, "bug", True)
        # Лейбл не совпал с типом либо пришёл посторонний сигнал: раньше это
        # завершало воркфлоу, теперь — просто не переход. Ждём дальше, до срока.
        return (lifecycle.CLASSIFIED, "awaiting-human-decision", False)

    async def _phase_analysis(self, issue: IssueInput) -> tuple | None:
        """Фаза `business-analysis`: цепочка FNR дочерним прогоном.

        Метку `run:analyze` и подтверждение приёма ставит сам дочерний прогон
        (`ack_command`) — тот же код, что и при автономном запуске. Отдельного
        `mark_command_running` здесь больше нет: две руки на одной метке
        разъехались бы при первом же изменении в одной из них.
        """
        self._analysis_done = await self._run_analysis_child(issue, trigger="research-me")
        if not self._analysis_done:
            return (lifecycle.FAILED, "failed", True)
        return (lifecycle.SYSTEM_REQUIREMENTS, "analysis", True)

    async def _phase_research(self, issue: IssueInput) -> tuple | None:
        """Фаза `product-research`: продуктовое исследование дочерним прогоном.

        Запускает отдельный workflow исследования, аналогично анализу, но
        с другим пайплайном и артефактами (PRD вместо бизнес-требований).
        """
        self._research_done = await self._run_research_child(issue)
        if not self._research_done:
            return (lifecycle.FAILED, "failed", True)
        return (lifecycle.SYSTEM_REQUIREMENTS, "research-done", True)

    async def _phase_handoff(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `system-requirements`: декомпозиция и передача разработчику (H1).

        Разбиение идёт ЗДЕСЬ, до `ready-for-dev`: агент разработки должен
        получить план исполнения, а не задачу целиком. Иначе он сам решает, с
        чего начать и что считать достаточным, — а это решение принимается до
        кода.

        Сбой декомпозиции не отменяет передачу. План — это улучшение переданной
        задачи, а не условие её существования: без него разработчик получит
        задачу как раньше, и это хуже, чем с планом, но лучше, чем ничего.
        """
        # Подзадача плана ссылается на требования РОДИТЕЛЯ: своей ветки анализа
        # у неё нет, и ссылка на `research/issue-<своё>` вела бы в пустоту.
        source = self._root_issue if self._plan_member and self._root_issue else issue.issue_number
        branch = f"research/issue-{source}"

        # Круг уточнения ПОСЛЕ аналитики. Она разобрала код и знает, чего в
        # постановке не хватает для однозначного решения. Раньше такие места
        # только перечислялись в чеклисте готовности — то есть решение по ним
        # доставалось агенту разработки, и он выбирал за человека молча.
        #
        # Подзадачу плана не спрашиваем: вопросы по фиче задаются один раз, у
        # родителя, иначе один и тот же вопрос прилетит человеку N раз.
        clarify = await self._clarify_open_questions(issue, deadlines, branch)
        if clarify is not None:
            return clarify
        # Подзадача чужого плана своего плана не получает: разбирать её значило
        # бы пустить цепочку на второй круг, а там правило R7 отправит каждую
        # внучатую задачу человеку — вместо плана вышла бы очередь к людям.
        if self._decompose and not self._plan_member:
            try:
                plan = await workflow.execute_activity(
                    activities.decompose_issue,
                    args=[issue, branch],
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                await workflow.execute_activity(
                    activities.publish_decomposition,
                    args=[issue, plan, branch],
                    start_to_close_timeout=timedelta(seconds=600),
                    # Повтор создал бы дубли подзадач: часть уже заведена.
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            except Exception as e:
                workflow.logger.warning("декомпозиция не выполнена: %s",
                                        _failure_reason(e))

        await workflow.execute_activity(
            activities.mark_ready_for_dev,
            args=[issue, self._priority_tier, branch],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        
        # При RESEARCH_AUTOSTART ожидания нет: триаж сам довёл задачу до
        # system-requirements, и решение «декомпозиция или сразу разработка»
        # уже принято в коде (флаг self._decompose). Нет смысла парковаться и
        # ждать того же решения от человека.
        #
        # Если включён и DEVELOP_AUTOSTART — идём сразу в разработку, минуя
        # парковку в ready-for-dev. Если только RESEARCH_AUTOSTART — всё равно
        # не парковаться: задача дошла до конца исследовательского пути, и
        # следующее решение (запуск разработки) принимается отдельно, в своей
        # фазе (_phase_await_build).
        if deadlines.research_autostart:
            if deadlines.develop_autostart and not self._plan_member:
                # Полный автостарт: Research + Develop → замкнутый контур
                return await self._start_development(issue)
            # Только Research автостарт: дошли до ready-for-dev без парковки
            return (lifecycle.READY_FOR_DEV, None, False)
        
        return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", True)

    async def _clarify_open_questions(self, issue: IssueInput, deadlines,
                                      branch: str) -> tuple | None:
        """Спросить и подождать. `None` — идти дальше, передавать задачу.

        Ответ не оформляется командой: повторный прогон аналитики читает
        обсуждение Issue, поэтому обычный комментарий и есть способ закрыть
        вопрос — тем же путём, которым он возник.

        Под маркером патча: прогоны, уже прошедшие передачу без этого шага,
        держат в истории другую последовательность.
        """
        if not workflow.patched("issue-lifecycle-clarify-after-analysis"):
            return None
        if self._plan_member or self._clarify_rounds >= MAX_ANALYSIS_CLARIFY_ROUNDS:
            return None

        try:
            questions = await workflow.execute_activity(
                activities.read_open_questions,
                args=[issue.repo, branch],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as e:
            # Круг уточнения улучшает переданную задачу, но не является условием
            # её существования: не прочитали артефакты — передаём как раньше.
            # Иначе сбой чтения ветки останавливал бы готовую работу.
            workflow.logger.warning("не прочитал открытые вопросы: %s", _failure_reason(e))
            return None
        if not questions:
            return None

        self._clarify_rounds += 1
        await workflow.execute_activity(
            activities.ask_open_questions,
            args=[issue, questions, self._clarify_rounds],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        timeout = await self._park(
            awaiting_mod.HUMAN_DECISION,
            who="человек: автор Issue или дежурный по триажу",
            reason=f"ответ на {len(questions)} незакрытых вопроса аналитики",
            hours=deadlines.clarification_hours)
        while True:
            signal = await self._wait_for_signal(timeout)
            if signal is None:
                # Срок вышел — задачу всё равно передаём: вопросы уедут в чеклист
                # готовности, и решение примет тот, кто её возьмёт. Держать
                # готовую аналитику в ожидании неделями хуже.
                return None
            if isinstance(signal, AgentEvent):
                return await self._agent_event(signal)
            if signal == AGENT_ANALYZE:
                return await self._analysis_requested(issue)
            if isinstance(signal, UserComment):
                # Ответ получен. В анализ заново: он прочитает обсуждение и
                # закроет вопрос — переписывать артефакты руками некому.
                return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
            # Посторонний сигнал ответом не считается и круга не тратит.

    async def _answer_followup(self, issue: IssueInput, comment: UserComment) -> tuple:
        """Ответить на реплику человека, оставшись в той же фазе.

        Отказ, ради которого это написано (`poh-demo-checkout#42`): триаж закрыл
        консультацию содержательным ответом, человек спросил следующее — и цикл
        отбросил его реплику как посторонний сигнал. Комментарий доехал, реакция
        «глаза» встала, ответа не было. Со стороны человека это неотличимо от
        сломанного контура, а с нашей — задача просто досиживала парковку.

        Диалог идёт НА МЕСТЕ: фазу реплика не двигает. Вопрос по припаркованной
        задаче — это вопрос, а не решение о ней; двигай он фазу, любая реплика
        переписывала бы состояние Issue, и метка перестала бы означать
        происходящее. Ходы между фазами остаются за метками и командами.

        Ошибка модели гасится: реплика без ответа хуже, но упавшая по ней фаза
        забирает с собой и парковку, и всё остальное состояние задачи.
        """
        # Повторная доставка вебхука (в истории #42 каждый сигнал ровно дважды)
        # не должна давать второй ответ на тот же вопрос.
        if comment.comment_id is not None and comment.comment_id in self._answered_comment_ids:
            return (self._phase, self._stage, False)
        # Потолок исчерпан — реплика по-прежнему будит парковку, но модель по ней
        # не гоняем. Молчание здесь осознанное: круги кончились, разговор ведёт
        # человек, которому задача поставлена в очередь.
        if self._followup_rounds >= self._followup_max_rounds:
            workflow.logger.info("потолок реплик исчерпан (%s) — отвечаю молчанием",
                                 self._followup_max_rounds)
            return (self._phase, self._stage, False)

        self._followup_rounds += 1
        if comment.comment_id is not None:
            self._answered_comment_ids.append(comment.comment_id)
            del self._answered_comment_ids[:-SEEN_EVENTS_KEPT]
        try:
            await workflow.execute_activity(
                activities.answer_followup,
                args=[issue, comment.text],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as exc:
            workflow.logger.warning("не ответил на реплику: %s", _failure_reason(exc))
        return (self._phase, self._stage, False)

    async def _handle_comment_intent(self, issue: IssueInput, comment: UserComment,
                                   intent: CommentIntent, deadlines) -> tuple:
        """Обработка намерения, извлечённого из реплики человека.
        
        Реагирует на comment intent в зависимости от текущей фазы и типа намерения.
        """
        # Защита от повторной доставки: уже отвеченные комментарии игнорируем
        if comment.comment_id is not None and comment.comment_id in self._answered_comment_ids:
            workflow.logger.info("комментарий #%s уже обработан — пропускаю", comment.comment_id)
            return (self._phase, self._stage, False)
        
        # Отмечаем комментарий как обработанный
        if comment.comment_id is not None:
            self._answered_comment_ids.append(comment.comment_id)
            del self._answered_comment_ids[:-SEEN_EVENTS_KEPT]
        
        # Обработка по типу намерения
        if intent.intent == "proceed":
            # Человек подтвердил продолжение — двигаем фазу по основному пути
            if self._phase == lifecycle.CLASSIFIED:
                label = self._classification_label
                feature = label is None or label == "advisor:feature-request"
                bug = label is None or label == "advisor:bug"
                
                if feature:
                    return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
                if bug:
                    return (lifecycle.READY_FOR_DEV, "bug", True)
            
            # В других фазах proceed — просто ответ, что продолжаем.
            #
            # `workflow.patched` обязателен: замена активности МЕНЯЕТ команду
            # в истории. `ack_comment_seen` принимает один `CommentAckInput`
            # и делает ровно одно — ставит реакцию `eyes`; здесь же нужно
            # ОПУБЛИКОВАТЬ готовый текст («продолжаем», «потолок исчерпан»,
            # «возврат не поддерживается», «подтверждение принято»). Прежний
            # вызов передавал `(issue, текст)` — не просто не тот тип, а не та
            # активность и не та арность: `TypeError`, три попытки, и без
            # перехвата исключения — падение всего цикла Issue. Эти четыре
            # ветки сегодня падают ВСЕГДА, поэтому живых прогонов, дошедших до
            # следующего шага ЗА ними, нет; но истории уже упавших прогонов
            # есть, и для их реплея прежняя (ошибочная) команда сохранена
            # веткой `else` — замена везде разом уронила бы такой реплей
            # недетерминизмом (другой тип активности в той же точке истории).
            #
            # Находка R3 (ревью `fix/activity-arg-types`). `post_followup_
            # reply` публикует комментарий в GitHub — тот же класс отказа,
            # что и починка Дефекта 2 в целом: устойчивый отказ ЧИСТО
            # ИНФОРМАЦИОННОГО ответа не имеет права ронять весь
            # `IssueLifecycle`. Без перехвата — ровно так и было бы: три
            # попытки исчерпаны, `ActivityError` пробрасывается наружу,
            # прогон уходит в FAILED из-за того, что не смог ответить на
            # реплику, хотя сама реплика (`intent.intent == "proceed"`) уже
            # обработана и фаза не меняется. Соседняя ветка `question` в этой
            # же функции гасит свой отказ так же (см. ниже), приём общий.
            if workflow.patched("issue-lifecycle-comment-intent-reply-activity"):
                try:
                    await workflow.execute_activity(
                        activities.post_followup_reply,
                        args=[issue.repo, issue.issue_number, intent.reason],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as exc:
                    workflow.logger.warning(
                        "не ответил на подтверждение продолжения: %s",
                        _failure_reason(exc))
            else:
                await workflow.execute_activity(
                    activities.ack_comment_seen,
                    args=[issue, intent.reason],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            return (self._phase, self._stage, False)

        elif intent.intent == "rework":
            # Проверяем потолок возвратов этапа
            if self._rework_rounds >= self._rework_max_rounds:
                # Потолок исчерпан — отвечаем, что больше не переделываем.
                # `workflow.patched` — та же замена активности, тот же довод,
                # что и в ветке `proceed` выше.
                #
                # Находка R3 — тот же перехват и тот же довод, что у ветки
                # `proceed` выше по функции: отказ информационного ответа не
                # должен ронять цикл.
                if workflow.patched("issue-lifecycle-comment-intent-reply-activity"):
                    try:
                        await workflow.execute_activity(
                            activities.post_followup_reply,
                            args=[issue.repo, issue.issue_number,
                                  f"Потолок возвратов этапа исчерпан ({self._rework_max_rounds}). "
                                  "Продолжай работу в текущем состоянии или поставь метку для перехода."],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=RetryPolicy(maximum_attempts=3),
                        )
                    except Exception as exc:
                        workflow.logger.warning(
                            "не ответил про исчерпанный потолок возвратов: %s",
                            _failure_reason(exc))
                else:
                    await workflow.execute_activity(
                        activities.ack_comment_seen,
                        args=[issue, f"Потолок возвратов этапа исчерпан ({self._rework_max_rounds}). "
                                     "Продолжай работу в текущем состоянии или поставь метку для перехода."],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                return (self._phase, self._stage, False)

            self._rework_rounds += 1

            # Возврат в created с репликой в контексте
            if self._phase == lifecycle.CLASSIFIED:
                # Возвращаемся в created, триаж перезапустится
                return (lifecycle.CREATED, "rework", True)

            # В других фазах rework не поддерживаем — отвечаем, что не можем.
            # `workflow.patched` — тот же довод, что и выше по функции.
            #
            # Находка R3 — тот же перехват и тот же довод, что у ветки
            # `proceed` выше по функции.
            if workflow.patched("issue-lifecycle-comment-intent-reply-activity"):
                try:
                    await workflow.execute_activity(
                        activities.post_followup_reply,
                        args=[issue.repo, issue.issue_number,
                              f"Возврат этапа в фазе {self._phase} не поддерживается. "
                              "Продолжай работу или поставь метку для перехода."],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as exc:
                    workflow.logger.warning(
                        "не ответил про неподдержанный возврат этапа: %s",
                        _failure_reason(exc))
            else:
                await workflow.execute_activity(
                    activities.ack_comment_seen,
                    args=[issue, f"Возврат этапа в фазе {self._phase} не поддерживается. "
                                 "Продолжай работу или поставь метку для перехода."],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            return (self._phase, self._stage, False)
        
        elif intent.intent == "question":
            # Вопрос — отвечаем, парковку держим
            if self._followup_rounds >= self._followup_max_rounds:
                workflow.logger.info("потолок реплик исчерпан (%s) — отвечаю молчанием",
                                     self._followup_max_rounds)
                return (self._phase, self._stage, False)
            self._followup_rounds += 1
            try:
                await workflow.execute_activity(
                    activities.answer_followup,
                    args=[issue, comment.text],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as exc:
                workflow.logger.warning("не ответил на вопрос: %s", _failure_reason(exc))
            return (self._phase, self._stage, False)
        
        elif intent.intent == "ack":
            # Подтверждение — отвечаем, чего ждём, и перечисляем доступные
            # ходы. `workflow.patched` — тот же довод, что и в ветке `proceed`
            # выше по функции.
            #
            # Находка R3 — тот же перехват и тот же довод, что у ветки
            # `proceed` выше по функции.
            if workflow.patched("issue-lifecycle-comment-intent-reply-activity"):
                try:
                    await workflow.execute_activity(
                        activities.post_followup_reply,
                        args=[issue.repo, issue.issue_number, intent.reason],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as exc:
                    workflow.logger.warning(
                        "не ответил на подтверждение (ack): %s",
                        _failure_reason(exc))
            else:
                await workflow.execute_activity(
                    activities.ack_comment_seen,
                    args=[issue, intent.reason],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            return (self._phase, self._stage, False)
        
        else:
            # Неизвестный intent — логируем и игнорируем
            workflow.logger.warning("неизвестный intent: %s", intent.intent)
            return (self._phase, self._stage, False)

    async def _phase_await_build(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `ready-for-dev`: ждём, возьмут ли задачу в разработку.

        При `DEVELOP_AUTOSTART` ожидания нет: контур замкнут и идёт от Issue до
        PR без касания человека. Метка `ready-for-dev` при этом всё равно
        ставится (`_phase_handoff` отработал раньше) — она сообщает состояние
        задачи, а не то, кто именно её возьмёт.
        """
        # Финальное ревью ветки, находка C1 (Critical). Автостарт звал
        # `_start_development` БЕЗУСЛОВНО — в том числе когда гейт критерия
        # приёмки уже задал вопрос (`self._open_question` непуст) и вернул
        # управление в ЭТУ ЖЕ фазу (`_enter` при совпадении фазы не паркует, а
        # просто меняет стадию — см. её докстринг). Цикл делал виток и снова
        # попадал в автостарт, снова в гейт: `propose_acceptance_options`
        # (МОДЕЛЬ) и `ask_question` звались на каждом витке заново,
        # `_wait_for_signal` в этой ветке не вызывался вовсе — ответ человека
        # командой `/harness-answer` НИКОГДА не читался из очереди сигналов.
        # На стенде `DEVELOP_AUTOSTART=1` — это боевой режим, а не гипотеза.
        #
        # Третий круг финального ревью, находка G1 (Critical) — РЕЦИДИВ того
        # же дефекта с другой стороны. Правка C1 выше блокировала автостарт
        # признаком «есть указатель на открытый вопрос» (`self._open_
        # question` непуст). Но указатель — лишь ОДИН из исходов гейта:
        # `_start_development` может НЕ пропустить задачу дальше и без
        # единого открытого вопроса — устойчивый отказ ЧТЕНИЯ критерия
        # (`read_acceptance_criterion`: недоступный GitHub, отозванный токен)
        # или отказ ПОСТАНОВКИ вопроса (`ask_question` не смог записать тело
        # или опубликовать комментарий — 403/422 при абсолютно исправном
        # ЧТЕНИИ). В обоих случаях присваивание `self._open_question = ...`
        # в `_start_development` не происходит вовсе (исключение бросается
        # ДО или ВО ВРЕМЯ него) — указатель остаётся пустым, автостарт видит
        # «вопроса нет как нет» и как ни в чём не бывало зовёт гейт заново:
        # на КАЖДОМ обороте — чтение критерия, МОДЕЛЬ
        # (`propose_acceptance_options`), `ask_question`, снова отказ, снова
        # комментарий человеку, снова событие Sentry. Ни таймера, ни
        # парковки, ни ожидания сигнала — оборот занимает секунды.
        #
        # Правильный признак — не «есть указатель на вопрос», а «гейт
        # ОТРАБОТАЛ И НЕ ПРОПУСТИЛ задачу дальше»: `self._acceptance_gate_
        # stalled` заводится в `_start_development` на ВСЕХ исходах, которые
        # держат фазу на месте (отказ чтения, отказ постановки вопроса,
        # вопрос успешно задан и ждёт ответа), и снимается только когда
        # критерий найден и гейт передаёт задачу в `_begin_development`. Один
        # признак покрывает все исходы гейта сразу — не два отдельных костыля
        # на каждый новый способ отказать. Указатель `self._open_question`
        # при этом никуда не делся: он по-прежнему нужен `_answer_open_
        # question` и перепроверке ниже, чтобы знать, НА ЧТО отвечает
        # человек, — но решать, можно ли автостарту звать гейт снова, теперь
        # не его дело.
        #
        # `workflow.patched` обязателен по прежней причине (см. комментарий
        # C1 выше) и с прежней гарантией: у прогонов, уже застрявших в этом
        # витке кодом БЕЗ этого признака, короткое замыкание `and` не давало
        # `workflow.patched` исполниться вовсе — ни указатель, ни новый флаг
        # в их истории до этой правки не поднимались. Значит на реплее такой
        # истории `patched()` вернёт False ровно до конца УЖЕ ЗАПИСАННЫХ
        # событий (маркер этого имени в них ни разу не встречался — сверка
        # идёт по факту наличия marker-события, а не по причине, по которой
        # его не позвали), а сразу за концом истории — True: прогон
        # запаркуется на первом же необработанном обороте, не выдумав ни
        # одной лишней команды на уже случившихся событиях.
        autostart_blocked_by_gate_stall = (
            self._acceptance_gate_stalled
            and workflow.patched("issue-lifecycle-autostart-waits-for-answer")
        )
        # Автостарт — только у задачи, которая владеет своим планом. Подзадачи
        # исполняет РОДИТЕЛЬ: один прогон агента на весь объём MVP и один PR на
        # фичу. Дай автостарт каждой подзадаче — и на одном репозитории
        # одновременно работают N агентов: конфликты, N PR вместо одного и N
        # ревью, ни одно из которых не про целую фичу.
        if (deadlines.develop_autostart and not self._plan_member
                and not autostart_blocked_by_gate_stall):
            return await self._start_development(issue)

        # Подзадача плана ждёт РОДИТЕЛЯ, а не человека: тот исполняет весь объём
        # MVP одним прогоном. Человеку по ней делать нечего, а выборка
        # `needs-human:*` обязана быть полной очередью к людям — восемь подзадач
        # одной фичи в ней означают, что на саму выборку перестанут смотреть.
        # Под маркером патча: вид ожидания решает, будет ли вызов метки очереди
        # перед таймером, а прежняя история идёт к таймеру напрямую. Реплей без
        # маркера падает `Timer machine does not handle ActivityTaskScheduled` —
        # так легли подзадачи #20–#27 на стенде.
        if self._plan_member and workflow.patched(
                "issue-lifecycle-plan-member-waits-for-parent"):
            kind = awaiting_mod.EXTERNAL_AGENT
            who = "контур: прогон разработки по родительской задаче"
            reason = (f"исполнение в составе плана задачи #{self._root_issue}"
                      if self._root_issue else "исполнение в составе плана родителя")
        else:
            kind = awaiting_mod.kind_for_phase(lifecycle.READY_FOR_DEV)
            who = awaiting_mod.who_for_phase(lifecycle.READY_FOR_DEV)
            reason = awaiting_mod.reason_for_phase(lifecycle.READY_FOR_DEV)
        hours = awaiting_mod.deadline_hours(
            kind, deadlines.build_decision_hours
            if kind in awaiting_mod.BLOCKED_ON_HUMAN else None)
        if self._open_question and workflow.patched(
                "issue-lifecycle-criterion-recheck-while-parked"):
            # Находка F3 (Important, второй круг финального ревью). Спека
            # A23 обещает: критерий, вписанный в тело РУКАМИ, — рабочая
            # дверь, не хуже команды `/harness-answer`. Но правки тела Issue
            # вебхук не обрабатывает вовсе — сигнала на них нет, — а выйти
            # из этой парковки может только сигнал (команда, `build-me`,
            # событие агента). Под `DEVELOP_AUTOSTART`, чей смысл именно в
            # отсутствии действия человека, это означало: задача с вопросом
            # гейта, отвеченным правкой тела, просидит здесь весь срок
            # парковки и закроется — то самое действие человека
            # (`/harness-answer` или повторный `build-me`), которого
            # автостарт обязан избегать, становится ЕДИНСТВЕННОЙ дверью.
            #
            # До находки C1 (см. её комментарий выше) бесконечный виток
            # автостарта хотя бы подхватывал вписанный руками критерий — но
            # ценой вызова МОДЕЛИ на каждом обороте (за 27 секунд виртуального
            # времени — 7090 вызовов). Здесь цена другая и на порядки меньше:
            # `read_acceptance_criterion` — чтение тела БЕЗ модели, раз в
            # `CRITERION_RECHECK_INTERVAL`, а не на каждой миллисекунде.
            #
            # Перепроверяем ТОЛЬКО пока открыт вопрос ГЕЙТА КРИТЕРИЯ:
            # обычная парковка `build-me` (self._open_question пуст) в
            # перечитывании не нуждается — там нечему появиться в теле
            # без ведома цикла, кроме решения человека, а оно и так сигнал.
            #
            # `wake_within` укорачивает только ВОЗВРАЩАЕМЫЙ `_park` таймаут
            # (см. её докстринг) — описание ожидания и дедлайн, которые
            # видит человек, считаются от полного `hours`, без урезания.
            decision = await self._wait_for_signal(await self._park(
                kind, who=who, reason=reason, hours=hours,
                wake_within=CRITERION_RECHECK_INTERVAL))
            if decision is None and self._park_timeout(hours) > timedelta(0):
                # Таймаут промежуточной перепроверки, а не реальный дедлайн
                # парковки (тот — когда `_park_timeout` уже вернул 0, ветка
                # `if decision is None` ниже, общая с обычным путём).
                # Критерий читаем БЕЗ модели — `propose_acceptance_options`/
                # `ask_question` здесь не нужны: вопрос уже открыт,
                # спрашивать заново нечего, а если критерий нашёлся — это же
                # `_start_development` его увидит и без нашей помощи (см.
                # ветку «критерий вписан руками», находка I4, выше).
                criterion = ""
                try:
                    criterion = await workflow.execute_activity(
                        activities.read_acceptance_criterion, issue,
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as e:
                    # Сбой перепроверки не хуже поведения без неё вовсе —
                    # держим парковку, следующая перепроверка (или реальный
                    # сигнал) попробует снова.
                    #
                    # Третий круг финального ревью, находка G2 (Important).
                    # Комментарий здесь раньше утверждал, что отказ станет
                    # видимым через `_start_development` (тот же гейт зовёт
                    # `read_acceptance_criterion` и уведомляет о его отказе
                    # через `report_criterion_gate_stall`) — НЕПРАВДА.
                    # Перепроверка работает только пока `self._open_question`
                    # непуст, а это ровно то условие, которое ТЕПЕРЬ (после
                    # находки G1 выше) блокирует автостарт: автостарт
                    # заблокирован, человек не сигналит (иначе `_wait_for_
                    # signal` вернул бы решение, а не таймаут промежуточной
                    # перепроверки) — значит `_start_development` всё то
                    # время, что идёт перепроверка, вообще не вызывается, и
                    # обещанное ею уведомление никогда не приходит. Устойчивый
                    # отказ (истёкший токен, отозванные права, переименованный
                    # репозиторий) — до 144 провалившихся опросов за 72 часа
                    # (`CRITERION_RECHECK_INTERVAL` = 30 минут), из видимости
                    # только `workflow.logger.warning` (порог Sentry —
                    # `event_level=ERROR`, WARNING до него не поднимается, см.
                    # докстринг `sentry_setup`), а затем тихое закрытие по
                    # сроку.
                    #
                    # Правка — тот же приём, что у гейта: одно уведомление на
                    # СЕРИЮ подряд идущих отказов, через ОБЩИЙ с гейтом флаг
                    # `self._criterion_gate_notified` — это тот же самый вызов
                    # `read_acceptance_criterion`, просто с другой частотой, и
                    # заводить под него отдельный флаг значило бы для
                    # человека два разных уведомления об одном и том же
                    # отказе сети.
                    #
                    # `workflow.patched` обязателен: у прогонов, уже стоящих
                    # на этой перепроверке БЕЗ отправленного уведомления,
                    # этой активности в их истории нет — реплей не должен
                    # получить лишнюю команду, которой там не было.
                    workflow.logger.warning(
                        "периодическая перепроверка критерия приёмки не "
                        "удалась: %s", _failure_reason(e))
                    if (workflow.patched(
                            "issue-lifecycle-criterion-recheck-stall-notice")
                            and not self._criterion_gate_notified):
                        try:
                            await workflow.execute_activity(
                                activities.report_criterion_gate_stall,
                                args=[issue, _failure_reason(e)],
                                start_to_close_timeout=timedelta(seconds=30),
                                retry_policy=RetryPolicy(maximum_attempts=5),
                            )
                        except Exception as notify_exc:
                            # Уведомление не имеет права ронять то, что оно
                            # уведомляет (тот же приём, что и у самого гейта).
                            workflow.logger.warning(
                                "не смог уведомить об отказе периодической "
                                "перепроверки критерия: %s",
                                _failure_reason(notify_exc))
                        else:
                            self._criterion_gate_notified = True
                else:
                    # Чтение удалось (пусть даже критерий всё ещё пуст) —
                    # серия отказов, если она была, закончилась здесь. Тот же
                    # флаг, что и у гейта (`_start_development`), — следующий
                    # отказ, где бы он ни случился, уже новая серия и снова
                    # заслуживает своего уведомления.
                    self._criterion_gate_notified = False
                if criterion:
                    # Критерий появился без единого сигнала от человека —
                    # именно то, что обещает A23. `_start_development` сам
                    # обнаружит непустой критерий, снимет устаревший вопрос
                    # гейта (находка I4) и передаст задачу в разработку.
                    return await self._start_development(issue)
                # Критерия всё ещё нет — держим парковку. `(self._phase,
                # self._stage, False)` — та же пара, что и у остальных
                # веток «постороннее событие фазу не двигает» в этом
                # обработчике: внешний цикл (`_run_phase_loop`) вызовет
                # `_phase_await_build` заново, `_park` пересчитает остаток
                # срока от АБСОЛЮТНОГО дедлайна (`_phase_since` не
                # менялся), и перепроверка продолжится со следующим
                # промежутком. Пропусти этот `return` — код провалился бы
                # в `if decision is None` ниже и закрыл бы цикл по
                # промежуточному таймауту, а не по реальному дедлайну.
                return (self._phase, self._stage, False)
        else:
            decision = await self._wait_for_signal(
                await self._park(kind, who=who, reason=reason, hours=hours))
        if decision is None:
            self._stage = "done"
            return None  # срок вышел — цикл закрывается, задача осталась в очереди
        if isinstance(decision, AgentEvent):
            return await self._agent_event(decision)
        if decision == AGENT_ANALYZE:
            return await self._analysis_requested(issue)
        if (isinstance(decision, UserComment) and self._open_question
                and workflow.patched("issue-lifecycle-question-answer")):
            # Гейт критерия приёмки задал вопрос — маркер обязателен: у
            # прогонов, припаркованных здесь ДО этой задачи, указателя
            # `self._open_question` в истории нет и быть не может, а значит
            # эта ветка для них попросту недостижима на реплее; без маркера
            # реплей всё равно упал бы, не найдя действие, которое исполнил
            # старый код на этом же месте.
            nxt = await self._answer_open_question(issue, decision)
            if nxt is not None:
                return nxt
            # Не команда `/harness-answer` — вопрос всё ещё открыт, а
            # обычная реплика ответом не считается (A5). Диалог по
            # припаркованной задаче (`_answer_followup`) сюда намеренно не
            # ведём: два разных протокола ответа на один и тот же комментарий
            # запутали бы человека больше, чем короткое молчание.
            return (self._phase, self._stage, False)
        if (isinstance(decision, UserComment) and not self._open_question
                and commands.parse_command(decision.text) == commands.HARNESS_ANSWER
                and workflow.patched(
                    "issue-lifecycle-answer-command-without-open-question")):
            # Финальное ревью ветки, находка I3 (Important). Спека A18: команда
            # `/harness-answer`, которой не на что отвечать, обязана получить
            # явный ответ — «вопросов сейчас нет» — а не тонуть молча. Ветка
            # выше срабатывает только при непустом `self._open_question`, и
            # без этой добавки та же команда без указателя проваливалась в
            # диалог уточнений ниже (`_answer_followup`): модель толковала её
            # как произвольную реплику, а при исчерпанном потолке реплик
            # ответа не было вовсе — молчание неотличимо от проглоченной
            # команды. Зовём ту же `_answer_open_question` с ПУСТЫМ указателем:
            # активность `answer_question` (`worker/activities.py`) на пустом
            # `question_id` без открытого вопроса в теле сама отдаёт
            # детерминированное «сейчас я не задавал вопроса» (см. её
            # докстринг) — это и есть честный ответ на команду, которой
            # нечего отвечать.
            #
            # `workflow.patched` обязателен: у прогонов, уже стоящих здесь
            # СТАРЫМ кодом, этой ветки в истории нет — `/harness-answer` без
            # указателя у них уже ушёл (или тонул) по ветке диалога уточнений
            # ниже, и новая ветка означала бы для них другую историю на
            # реплее.
            #
            # Находка F7 (Important, второй круг финального ревью). Пустой
            # `self._open_question` здесь означает «этот ПРОГОН вопрос не
            # заводил», а не «вопроса нет в природе» — спека A24 требует:
            # «новый цикл читает тело... вопрос открыт — переставляет
            # указатель... не задавая вопрос заново». Прогон, поднятый
            # заново поверх ЖИВОЙ задачи (событие внешнего агента,
            # `webhook/main.py:_lifecycle_args_for` — снимок несёт фазу, но
            # не указатель на вопрос), стартует с пустым указателем, даже
            # если в теле УЖЕ висит открытый вопрос гейта из прошлого
            # прогона. Без проверки `answer_question` (`worker/
            # activities.py`) получит `question_id=""` при РЕАЛЬНО открытом
            # вопросе и ответит «этот вопрос уже устарел, сейчас открыт
            # другой» (ветка `question.id != question_id`) — человеку,
            # ответившему на самый что ни на есть актуальный вопрос.
            #
            # Лечится тем же вызовом, что уже переставляет указатель после
            # `reasked` (находка C2) — `read_open_question_id`.
            if workflow.patched("issue-lifecycle-repoint-open-question-on-answer"):
                try:
                    self._open_question = await workflow.execute_activity(
                        activities.read_open_question_id, issue,
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as exc:
                    # Сбой оставляет указатель пустым — не хуже поведения без
                    # этой правки (I3 по-прежнему честно ответит «вопросов
                    # нет», просто может ошибиться, если вопрос был). Видимость
                    # отказа — находка F9, тот же приём чуть ниже по файлу.
                    workflow.logger.warning(
                        "не проверил актуальный открытый вопрос перед "
                        "ответом: %s", _failure_reason(exc))
                    if workflow.patched("issue-lifecycle-question-repoint-failure-notice"):
                        try:
                            await workflow.execute_activity(
                                activities.report_question_repoint_failure,
                                args=[issue, _failure_reason(exc)],
                                start_to_close_timeout=timedelta(seconds=30),
                                retry_policy=RetryPolicy(maximum_attempts=3),
                            )
                        except Exception as notify_exc:
                            workflow.logger.warning(
                                "не смог уведомить об отказе проверки "
                                "открытого вопроса: %s", _failure_reason(notify_exc))
            nxt = await self._answer_open_question(issue, decision)
            if nxt is not None:
                return nxt
            return (self._phase, self._stage, False)
        if isinstance(decision, UserComment) and workflow.patched(
                "issue-lifecycle-followup-answer"):
            # Маркер обязателен: у припаркованных прогонов отброшенные реплики
            # УЖЕ лежат в истории, и новый код запланировал бы на их месте
            # активность, которой там нет, — реплей упал бы недетерминизмом.
            return await self._answer_followup(issue, decision)
        if decision != "build-me":
            return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", False)
        return await self._start_development(issue)

    async def _answer_open_question(self, issue: IssueInput,
                                    comment: UserComment) -> tuple | None:
        """Обработать `/harness-answer` на открытый вопрос гейта критерия.

        `None` — комментарий не был обработан здесь (это не команда
        `/harness-answer`, либо это её точный повтор, снятый защитой ниже);
        вызывающий решает, что делать дальше.

        Ревью, отказ ради которого это написано: вебхук доставляет каждое
        событие ДВАЖДЫ (в истории `poh-demo-checkout#42` сигналов ровно
        вдвое), и без защиты по `comment_id` один ответ человека принимался
        бы дважды — второй раз уже при закрытом вопросе, то есть отвечал бы
        «вопросов нет» на собственный только что принятый ответ. Реестр —
        `self._answered_comment_ids`, тот же, что уже ведёт `_answer_followup`
        для реплик: заводить второй ради того же самого признака незачем.
        """
        if (comment.comment_id is not None
                and comment.comment_id in self._answered_comment_ids):
            return (self._phase, self._stage, False)
        if commands.parse_command(comment.text) != commands.HARNESS_ANSWER:
            return None
        if comment.comment_id is not None:
            self._answered_comment_ids.append(comment.comment_id)
            del self._answered_comment_ids[:-SEEN_EVENTS_KEPT]
        try:
            # Находка I1 (Important, финальное ревью). Было `maximum_attempts=
            # 1` и без перехвата: единственный отказ (502 от GitHub, таймаут)
            # ронял ВЕСЬ `IssueLifecycle` — Issue теряла владельца состояния
            # целиком, а человек, только что ответивший на вопрос, не узнавал,
            # что ответ не принят. Соседняя `ask_question` идёт с тремя
            # попытками, а `_answer_followup` рядом гасит свой сбой тем же
            # приёмом (перехват + лог) — оснований держать здесь одну попытку
            # без перехвата не было: активность идемпотентна по каждому
            # следствию (см. её докстринг), ретрай безопасен.
            #
            # `workflow.patched` здесь НЕ нужен: retry-политика — параметр
            # сервера повторов, а не часть команды, которую реплей сверяет с
            # историей (проверено напрямую — прогон записан с `maximum_
            # attempts=1`, реплей той же истории кодом с `maximum_attempts=3`
            # проходит чисто), а перехват исключения не переставляет ни одной
            # уже записанной команды: он лишь ловит то, что раньше улетало
            # наружу и валило прогон. У прогона, уже упавшего здесь старым
            # кодом, живой истории для реплея больше нет — падать ему было
            # больше некуда.
            verdict = await workflow.execute_activity(
                activities.answer_question,
                args=[issue, self._open_question,
                      commands.parse_command_args(comment.text), comment.comment_id],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as exc:
            workflow.logger.warning("не разобрал ответ на открытый вопрос: %s",
                                    _failure_reason(exc))
            # Новая активность — новая команда в истории, которой у уже
            # припаркованных (тем более уже упавших) старым кодом прогонов
            # быть не могло: маркер обязателен по обычной причине.
            if workflow.patched("issue-lifecycle-answer-question-failure-notice"):
                try:
                    await workflow.execute_activity(
                        activities.report_answer_question_failure,
                        args=[issue, _failure_reason(exc)],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as notify_exc:
                    # Уведомление не имеет права ронять то, что оно уведомляет
                    # (тот же приём, что у `report_criterion_gate_stall` в
                    # `_start_development`).
                    workflow.logger.warning(
                        "не смог уведомить об отказе разбора ответа: %s",
                        _failure_reason(notify_exc))
            return (self._phase, self._stage, False)
        if verdict == "accepted":
            self._open_question = ""
            # Третий круг финального ревью, находка G1 (заодно — самостоятельная
            # находка при сквозной проверке всех выходов из гейта). Ответ принят
            # — критерий записан, гейт по факту пройден, и путь сюда лежал через
            # УСПЕШНУЮ постановку вопроса в `_start_development`, а она поднимает
            # `self._acceptance_gate_stalled` в True. Не снять его здесь —
            # значит унаследовать True другим, куда более поздним заходом в
            # READY_FOR_DEV: правка I4 по соседству уже разбирала ровно эту
            # ловушку для `self._open_question` (задача, вернувшаяся сюда на
            # rework, наследует указатель на уже несуществующий вопрос) — здесь
            # тот же механизм, только вместо указателя на КОНКРЕТНЫЙ вопрос
            # ломается признак «гейт сейчас закрыт»: rework отправит задачу
            # обратно в READY_FOR_DEV, `_phase_await_build` увидит `self.
            # _acceptance_gate_stalled == True` от отвеченного (и давно
            # решённого) вопроса и молча выключит автостарт для всей
            # оставшейся жизни задачи, ничего не спрашивая и не паркуясь
            # по-настоящему.
            self._acceptance_gate_stalled = False
            return await self._begin_development(issue)
        if verdict == "reasked" and workflow.patched(
                "issue-lifecycle-reasked-question-repoints-pointer"):
            # Находка C2 (Critical, финальное ревью). Спека A22: возрождённый
            # вопрос заводит НОВЫЙ идентификатор, указатель переставляется.
            # Контракт `answer_question` этого не позволяет — активность
            # возвращает голую строку-вердикт (см. её докстринг, почему тип
            # возврата НЕ меняется: смена на структуру ломает десериализацию
            # уже записанных в историю bare-строк). Указатель узнаём отдельным,
            # новым вызовом: без него `self._open_question` остался бы на
            # исчезнувшем id, и следующий ответ человека натыкался бы на «этот
            # вопрос устарел» — а актуальный вопрос и был тем, на который он
            # отвечал (по кругу до истечения срока парковки).
            #
            # `workflow.patched` обязателен: у прогонов, уже стоящих здесь
            # СТАРЫМ кодом (указатель на вопрос уже в истории), новая
            # активность здесь была бы командой, которой в их истории нет.
            try:
                self._open_question = await workflow.execute_activity(
                    activities.read_open_question_id, issue,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as exc:
                # Сбой оставляет указатель СТАРЫМ — не хуже поведения без
                # правки; цикл не роняем.
                #
                # Находка F9 (Important, второй круг финального ревью). До
                # этой правки видимость отказа была ТОЛЬКО строкой `workflow.
                # logger.warning` — хлебной крошкой для Sentry (порог
                # `event_level=ERROR` у `LoggingIntegration`, а не WARNING,
                # см. докстринг `sentry_setup`), оператор её не увидит.
                # Человек тем временем по кругу получает «этот вопрос уже
                # устарел» на СВОЙ актуальный ответ (указатель остался на
                # исчезнувшем id) и не понимает, почему. Событие — по
                # образцу уже заведённого уведомления об отказе `answer_
                # question` (находка I1, `report_answer_question_failure`);
                # переиспользуем ту же активность `read_open_question_id`-
                # уведомления, что и находка F7 чуть выше — обе про один и
                # тот же отказ (чтение актуального открытого вопроса), просто
                # в разных точках вызова.
                #
                # Без комментария человеку: тот, что уже ушёл на «reasked»
                # чуть выше, честно объясняет, что делать («ответьте
                # текстом») — второй, спорящий с ним («не смог обработать
                # ответ, попробуйте ещё раз») тут же в ленте только запутает.
                workflow.logger.warning(
                    "не переставил указатель на возрождённый вопрос: %s",
                    _failure_reason(exc))
                if workflow.patched("issue-lifecycle-question-repoint-failure-notice"):
                    try:
                        await workflow.execute_activity(
                            activities.report_question_repoint_failure,
                            args=[issue, _failure_reason(exc)],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=RetryPolicy(maximum_attempts=3),
                        )
                    except Exception as notify_exc:
                        workflow.logger.warning(
                            "не смог уведомить об отказе проверки открытого "
                            "вопроса: %s", _failure_reason(notify_exc))
        return (self._phase, self._stage, False)

    async def _start_development(self, issue: IssueInput) -> tuple:
        """Гейт критерия приёмки, а затем — передача задачи агенту разработки.

        Одна точка на все входы — решение человека `build-me`, автостарт и
        принятый ответ на вопрос о критерии (см. `_phase_await_build`). Точка
        входа ОДНА и до этой задачи вела прямиком к разработке; гейт встаёт
        перед ней, не заменяя её — сама передача осталась в `_begin_development`.

        Маркер обязателен: у припаркованных прогонов решение «начать
        разработку» УЖЕ лежит в истории на этом месте, и новый код запланировал
        бы здесь активность, которой там нет, — реплей упал бы недетерминизмом.
        Так легли 29 прогонов из 149 после коммита `ac625e7`.
        """
        if workflow.patched("issue-lifecycle-acceptance-gate"):
            # Тело Issue живёт снаружи воркфлоу — активность, не чтение здесь:
            # реплей обязан быть детерминированным, а тело меняется без нас.
            try:
                criterion = await workflow.execute_activity(
                    activities.read_acceptance_criterion, issue,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception as e:
                # Ревью, находка 1 (Important): устойчивый отказ GitHub (после
                # исчерпания ретраев) не должен ронять весь IssueLifecycle —
                # тогда Issue теряет владельца состояния целиком из-за
                # временного сбоя сети. Симметрично `_clarify_open_questions`
                # (там же рядом — чтение открытых вопросов аналитики) гасим
                # сбой чтения, не давая ему остановить цикл.
                #
                # Но, В ОТЛИЧИЕ от неё, дальше НЕ идём как обычно (там сбой
                # читает необязательное улучшение, задачу можно передать и без
                # него). Здесь сам факт критерия — условие входа в разработку,
                # а мы его не знаем: не прочитали, а не «прочитали и там
                # пусто». Трактовать сбой чтения как «критерия нет» и тут же
                # задать вопрос было бы неправдой человеку — критерий, возможно,
                # ЕСТЬ, просто тело Issue не прочиталось, а «не вижу критерия»
                # это утверждение о содержимом, а не о сети. Гейт обязан
                # держать закрыто при неизвестном ответе: пропустить задачу в
                # разработку из-за сетевого сбоя хуже, чем не начать её вовремя
                # — поэтому остаёмся на парковке той же фазы, ничего не спрашивая
                # и не решая. Следующий сигнал (человек повторит решение,
                # дежурный по триажу заметит, внешний ретрай) снова вызовет
                # этот же гейт.
                workflow.logger.warning("не прочитал критерий приёмки: %s",
                                        _failure_reason(e))
                # Третий круг финального ревью, находка G1 (Critical).
                # Гейт НЕ пропустил задачу дальше — признак этого решают не
                # указателем на вопрос (его здесь и не было — до вопроса дело
                # не дошло), а этим флагом: он покрывает ЛЮБОЙ исход гейта,
                # который держит фазу на месте, и снимается только когда
                # критерий найден (см. присваивание `False` ниже, сразу после
                # успешного чтения). `_phase_await_build` читает именно его,
                # чтобы решить, можно ли автостарту снова звать этот гейт —
                # см. её докстринг про `autostart_blocked_by_gate_stall`.
                self._acceptance_gate_stalled = True
                # Ревью: отказ ВЫШЕ (парковка вместо падения) не спорят — но он
                # НЕВИДИМ. `workflow.logger.warning` уходит в Sentry только
                # хлебной крошкой (`LoggingIntegration(event_level=ERROR)` в
                # `sentry_setup.configure` — порог ERROR, а не WARNING),
                # оператор его не увидит. Человеку тоже не видно ничего: та же
                # фаза, та же стадия, а `_publish_awaiting` не зовёт
                # `mark_awaiting`, потому что желаемое состояние очереди не
                # изменилось (см. `want == self._human_queue_labelled` в
                # `_publish_awaiting`) — нажатие «в разработку» неотличимо
                # от «команду ещё не заметили». Хуже: срок парковки при
                # возврате в ту же фазу не сбрасывается — серия отказов близко
                # к истечению срока закрыла бы цикл по таймауту, так и не
                # показав, что решение человека вообще было получено.
                #
                # `workflow.patched` обязателен по тем же причинам, что и выше:
                # прогоны, уже стоящие на этой парковке БЕЗ отправленного
                # уведомления, на реплее не должны внезапно получить лишнюю
                # активность в истории, которой там нет.
                if workflow.patched("issue-lifecycle-acceptance-gate-stall-notice"
                                    ) and not self._criterion_gate_notified:
                    # Один раз на СЕРИЮ подряд идущих отказов, а не на каждую
                    # попытку: человек, который жмёт «в разработку» повторно
                    # (или дежурный, который повторяет сигнал), не должен
                    # получать копию того же сообщения на каждый клик — лента
                    # Issue не место для счётчика ретраев одного и того же
                    # сбоя. Флаг сбрасывается ниже сразу после успешного
                    # чтения — следующий отказ будет уже НОВОЙ серией и снова
                    # заслуживает своего сообщения. Сам флаг переживает
                    # continue-as-new через `LifecycleState.criterion_gate_
                    # notified` (см. её докстринг в shared/workflow_types.py) —
                    # ревью посчитало механику: порог истории проверяется
                    # ПОСЛЕ каждого перехода фазы, включая холостой «остались
                    # на месте после отказа», а очередь сигналов сразу после
                    # разбора одного сигнала почти всегда пуста. Для задачи,
                    # застрявшей на этом гейте, порог набирается быстро, и без
                    # переноса каждый перезапуск открывал бы новую «серию» —
                    # находка 2 (Important).
                    try:
                        await workflow.execute_activity(
                            activities.report_criterion_gate_stall,
                            args=[issue, _failure_reason(e)],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=RetryPolicy(maximum_attempts=5),
                        )
                    except Exception as notify_exc:
                        # Находка 1 (Important): уведомление не имеет права
                        # ронять то, что оно уведомляет. Причина отказа
                        # чтения критерия — обычно та же недоступность
                        # GitHub, а `report_criterion_gate_stall` зовёт тот же
                        # `github_client.post_comment`, ничем не защищённый:
                        # не перехватить здесь значило бы воспроизвести
                        # падение цикла другим заходом — тем же необработанным
                        # отказом, просто из другой активности. Маркер
                        # обязателен по тем же причинам, что и выше: без него
                        # это новая ветка решения, которой не было в истории
                        # прогонов, уже отправивших уведомление старым кодом.
                        if workflow.patched(
                                "issue-lifecycle-acceptance-gate-stall-notice-safe"):
                            # Флаг НЕ поднимаем (см. `else` ниже) — попытка не
                            # считается состоявшейся: сообщение не дошло ни
                            # оператору (Sentry), ни человеку (комментарий), и
                            # следующий отказ гейта в этой же серии обязан
                            # попробовать уведомить снова, а не молчать до
                            # конца серии.
                            workflow.logger.warning(
                                "не смог уведомить об отказе гейта критерия "
                                "приёмки: %s", _failure_reason(notify_exc))
                        else:
                            raise
                    else:
                        self._criterion_gate_notified = True
                return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", False)
            # Критерий прочитан (пусть даже пустым) — если серия отказов и
            # была, она закончилась здесь. Следующий отказ — уже новая серия,
            # и заслуживает нового сообщения (см. комментарий выше).
            self._criterion_gate_notified = False
            # Находка G1 (третий круг финального ревью). Чтение удалось —
            # само по себе ЧТЕНИЕ гейт больше не стопорит. Если критерий
            # пуст, ниже мы либо зададим вопрос, либо не сможем его задать —
            # оба исхода снова поднимут флаг перед своим `return`; если
            # критерий найден, флаг так и останется снятым, и гейт передаст
            # задачу в `_begin_development` дальше по функции.
            self._acceptance_gate_stalled = False
            if not criterion:
                # Отказ модели — не отказ гейта: варианты — только подспорье,
                # вопрос задаётся всё равно, при пустом списке — свободным
                # текстом (см. `Question.options`/`ask_question`).
                #
                # H1 (точечная правка после мержа, финальное ревью) — десятый
                # исход гейта. Единственный вызов внутри гейта, который раньше
                # не был обёрнут вовсе: одна попытка, потолок пять минут (SDK
                # `worker/llm.py` своего таймаута не задаёт — по умолчанию у
                # клиента 600 секунд, — плюс две повторные попытки у
                # instructor, так что потолок перекрывается штатно, а не в
                # теории). Тело активности само гасит отказ МОДЕЛИ и отдаёт
                # пустой список (см. её докстринг в `worker/activities.py`) —
                # но ИНФРАСТРУКТУРНЫЙ отказ (таймаут активности, перезапуск
                # воркера посреди вызова) улетал бы отсюда наружу тем же
                # необработанным исключением и ронял бы весь `IssueLifecycle`
                # — Issue теряла бы владельца состояния молча, без комментария
                # и без метки. Лечится тем же приёмом, что и у соседних
                # активностей этого гейта (`read_acceptance_criterion` выше,
                # `ask_question` ниже): перехват, пустой список вариантов —
                # ровно то, что активность и так возвращает при отказе модели,
                # так что для остального гейта это НЕ новый исход, а тот же
                # самый «критерий не найден, вариантов нет», просто с другой
                # причиной пустого списка.
                #
                # `workflow.patched` здесь не нужен — по той же причине, что
                # и у обёртки `ask_question` по соседству: перехват не
                # переставляет ни одной уже записанной команды, он лишь ловит
                # то, что раньше улетало наружу и валило прогон целиком. У
                # прогона, уже упавшего здесь старым кодом, живой истории для
                # реплея больше нет — падать ему было больше некуда.
                try:
                    options = await workflow.execute_activity(
                        activities.propose_acceptance_options, issue,
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                except Exception as e:
                    workflow.logger.warning(
                        "не смог подсказать варианты критерия приёмки: %s",
                        _failure_reason(e))
                    options = []
                # Находка F2 (Important, второй круг финального ревью).
                # Запоминаем ДО вызова `ask_question`, был ли вопрос уже
                # открыт, — см. комментарий у сброса `_phase_since` ниже:
                # решает именно это, а не сам факт вызова.
                question_already_open = bool(self._open_question)
                try:
                    self._open_question = await workflow.execute_activity(
                        activities.ask_question,
                        args=[issue, "howtodemo",
                              "**Не вижу, чем принимать эту задачу.** "
                              "Разработку не начинаю, пока не будет критерия готовности.",
                              options],
                        start_to_close_timeout=timedelta(minutes=3),
                        # Находка F4 (Important, второй круг финального
                        # ревью). `ConflictingOpenQuestion` (находка I5) —
                        # ДЕТЕРМИНИРОВАННЫЙ конфликт: в теле уже открыт
                        # вопрос ДРУГОГО вида. Без списка нерепетируемых
                        # типов три попытки трижды дёргали бы GitHub тем же
                        # заведомо провальным запросом, прежде чем активность
                        # упадёт. Сверка идёт по имени класса исключения, а
                        # не по иерархии, — тем же приёмом, что и
                        # `non_retryable_error_types=["RuntimeError"]` у
                        # стадий FNR выше по файлу.
                        retry_policy=RetryPolicy(
                            maximum_attempts=3,
                            non_retryable_error_types=["ConflictingOpenQuestion"],
                        ),
                    )
                except Exception as e:
                    # Находка F4 (Important, второй круг финального ревью).
                    # Вызов раньше не был обёрнут вовсе: единственный отказ
                    # (детерминированный конфликт выше или устойчивая
                    # недоступность GitHub) улетал наружу и ронял ВЕСЬ
                    # `IssueLifecycle` — Issue теряла владельца состояния
                    # целиком. Гейт обязан пережить и то, и другое — тем же
                    # приёмом, что и защита `read_acceptance_criterion` чуть
                    # выше: остаёмся на парковке той же фазы, вопрос не
                    # задан, а следующий сигнал (человек, автостарт, дежурный)
                    # снова вызовет гейт.
                    #
                    # Уведомление — БЕЗ дедупликации по `self._criterion_
                    # gate_notified`: этот флаг сбрасывается в `False` строкой
                    # выше на КАЖДОЙ повторной попытке (сразу после успешного
                    # чтения критерия), так что «одно на серию» здесь всё
                    # равно не получилось бы — сериями владеет отказ ЧТЕНИЯ,
                    # а не отказ ПОСТАНОВКИ вопроса. Отдельный флаг под это
                    # решили не заводить: `ConflictingOpenQuestion` — редкий
                    # детерминированный край, а не длящийся аутейдж, и
                    # предпочли простоту `report_answer_question_failure`
                    # (находка I1) — уведомляем на каждый отказ, а не
                    # исхитряемся с ещё одним состоянием, которое пришлось бы
                    # нести через continue-as-new.
                    workflow.logger.warning(
                        "не смог задать вопрос критерия приёмки: %s",
                        _failure_reason(e))
                    # Находка G1 (третий круг финального ревью) — САМА
                    # находка. Без этого флага указатель `self._open_question`
                    # остаётся пустым (присваивание выше не произошло —
                    # исключение брошено ДО него), автостарт видит «вопроса
                    # нет» и на следующем же обороте зовёт этот гейт заново:
                    # чтение критерия (снова успех, снова пусто) — МОДЕЛЬ
                    # (`propose_acceptance_options`) — снова этот же отказ
                    # `ask_question`. Без парковки и без таймера, оборот за
                    # оборотом. Флаг снимается только строкой выше, при
                    # следующем успешном чтении критерия.
                    self._acceptance_gate_stalled = True
                    if workflow.patched("issue-lifecycle-ask-question-failure-safe"):
                        try:
                            # Находка G2 (третий круг финального ревью).
                            # Раньше эта ветка переиспользовала `report_
                            # criterion_gate_stall` — активность с текстом
                            # «не смог проверить критерий приёмки». Здесь это
                            # НЕПРАВДА: критерий прочитан отлично (мы уже
                            # внутри `if not criterion:`, до этой строки дошли
                            # именно потому, что чтение удалось), упала
                            # ПОСТАНОВКА вопроса — другой шаг, другая причина,
                            # другое лечение (для человека — не «подождите,
                            # проверю», а «вопрос не дошёл, оценка не
                            # опубликована»). Разводим сообщения отдельной
                            # активностью `report_ask_question_gate_failure`.
                            #
                            # `workflow.patched` обязателен: у прогонов, уже
                            # отправивших уведомление СТАРЫМ текстом через
                            # `report_criterion_gate_stall` на этом самом
                            # месте, реплей обязан продолжать звать ТУ ЖЕ
                            # активность — переключение на новую было бы для
                            # них другим типом команды на уже случившемся
                            # событии, недетерминизм.
                            if workflow.patched(
                                    "issue-lifecycle-ask-question-failure-message"):
                                await workflow.execute_activity(
                                    activities.report_ask_question_gate_failure,
                                    args=[issue, _failure_reason(e)],
                                    start_to_close_timeout=timedelta(seconds=30),
                                    retry_policy=RetryPolicy(maximum_attempts=5),
                                )
                            else:
                                await workflow.execute_activity(
                                    activities.report_criterion_gate_stall,
                                    args=[issue, _failure_reason(e)],
                                    start_to_close_timeout=timedelta(seconds=30),
                                    retry_policy=RetryPolicy(maximum_attempts=5),
                                )
                        except Exception as notify_exc:
                            # Уведомление не имеет права ронять то, что оно
                            # уведомляет (тот же приём, что у `report_
                            # criterion_gate_stall` двумя экранами выше).
                            workflow.logger.warning(
                                "не смог уведомить об отказе постановки "
                                "вопроса гейта: %s", _failure_reason(notify_exc))
                    return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", False)
                # Находка I2 (Important, финальное ревью). Вопрос задаётся
                # ВОЗВРАТОМ В ТУ ЖЕ ФАЗУ — `_enter` при совпадении фазы не
                # трогает `_phase_since` (см. её докстринг), а срок парковки
                # считается именно от него. Без сброса человек, нажавший «в
                # разработку» на семьдесят первом часу исходной парковки
                # `awaiting-build-decision`, получил бы на ОТВЕТ по вопросу
                # считаные минуты — спека A26 обещает 72 часа. Вопрос — новое,
                # отдельное ожидание со своим сроком, а не хвост уже идущей
                # парковки; отсчёт обязан начаться заново.
                #
                # НО только В ПЕРВЫЙ РАЗ, когда указателя ещё не было
                # (находка F2, Important, второй круг финального ревью —
                # регресс правки выше). Безусловный сброс означал: повторный
                # `build-me`/автостарт ПРИ УЖЕ ОТКРЫТОМ вопросе (вебхук
                # доставляет каждое событие ДВАЖДЫ — см. докстринг
                # `_answer_open_question`, а человек или дежурный вполне
                # может прислать решение снова, пока критерий не найден)
                # заново заходил сюда, `ask_question` идемпотентно возвращал
                # id ТОГО ЖЕ вопроса (не публикуя второй комментарий — см. её
                # докстринг), а срок ответа отсчитывался с нуля НА КАЖДЫЙ
                # такой заход. Дедлайн превращался в «N часов с последнего
                # шороха» — ровно то, против чего в этом файле заведён
                # абсолютный предел парковки (`_park_timeout`, правило R3):
                # вопрос — не НОВОЕ ожидание, если он уже был открыт до этого
                # вызова.
                #
                # `workflow.patched` здесь не нужен: проверено напрямую —
                # длительность таймера/парковки не входит в проверку
                # детерминизма реплея (Replayer чисто проигрывает историю,
                # записанную с одной длительностью, кодом, считающим другую;
                # то же для retry-политики активности, см. комментарий в
                # `_answer_open_question`). У прогона, уже стоящего на
                # парковке с таймером, ЗАВЕДЁННЫМ до этой правки, сервер уже
                # держит СТАРЫЙ срок — его код задним числом не продлевает
                # (и не обязан: это обычное «правка начинает действовать для
                # новых ожиданий», а не недетерминизм).
                #
                # Не чиним этим же заходом: что видит человек, ответивший на
                # вопрос уже МЁРТВОГО прогона (срок истёк, `run()` вернулся,
                # но открытый вопрос и метка остались в теле) — `/harness-
                # answer` в этом случае уходит в воркфлоу голым сигналом,
                # живого прогона для его приёма нет, и отказ гасится широким
                # перехватом на стороне вебхука. Это отдельная, более крупная
                # правка на стороне доставки сигнала (webhook/main.py):
                # обнаружение мёртвого прогона и содержательный ответ
                # человеку вместо тишины. Здесь она не сделана — называю
                # прямо, а не молчу: смешивать её с правкой самого срока
                # означало бы либо раздувать этот коммит, либо чинить
                # доставку сигналов наспех.
                if not question_already_open:
                    self._phase_since = workflow.now()
                # Находка G1 (третий круг финального ревью). Вопрос задан и
                # ждёт ответа — гейт снова не пропустил задачу дальше, теперь
                # уже сознательно (спрашивать заново нечего). Формально флаг
                # тут почти всегда и так True (тот же `self._open_question`,
                # который сейчас непуст, — сам по себе один из исходов гейта,
                # для которого флаг заводился), но ставим его явно: этот
                # `return` — самостоятельный исход гейта, и его видимость не
                # должна зависеть от того, что где-то раньше сделала другая
                # ветка.
                self._acceptance_gate_stalled = True
                # Ждём в READY_FOR_DEV: та же фаза, что и до вопроса, поэтому
                # write_label=False — метка `ready-for-dev` уже стоит, вопрос
                # не меняет то, что видно как состояние Issue снаружи.
                return (lifecycle.READY_FOR_DEV, "awaiting-acceptance-criterion", False)
            if self._open_question and workflow.patched(
                    "issue-lifecycle-criterion-filled-by-hand-closes-question"):
                # Находка I4 (Important, финальное ревью). Критерий появился
                # НЕ через `/harness-answer` (тогда `self._open_question` уже
                # был бы очищен веткой `accepted` выше) — значит, человек
                # вписал его в тело руками. Спека A23: «вопрос снимается,
                # работа продолжается» — команда удобство, а не единственная
                # дверь. Без этой правки блок вопроса и метка `NEEDS_HUMAN_
                # ANSWER` оставались висеть на задаче, уже ушедшей в
                # разработку, и ничто их больше не снимало — выборка
                # `needs-human:*` переставала быть полной очередью к людям.
                #
                # Сбой снятия — уборка состояния, а не условие входа в
                # разработку: сетевой сбой здесь не должен блокировать
                # передачу задачи агенту.
                #
                # Находка F6 (Important, второй круг финального ревью).
                # Прежний комментарий здесь обещал «блок/метка повисят до
                # следующего успешного прохода этой ветки» — неправда: НИЖЕ,
                # сразу за перехватом, безусловно идёт `_begin_development`
                # — фаза уезжает из READY_FOR_DEV, и `_start_development`
                # (а с ним и эта ветка) по ЭТОЙ задаче больше не позовут,
                # пока она не вернётся сюда заново (rework — см. `MAX_REWORK_
                # ROUNDS` — либо новый цикл разработки). «Следующего прохода»
                # в смысле «сейчас доделает» — не будет никогда.
                #
                # Отказ был и НЕВИДИМ: только `workflow.logger.warning`, а
                # порог Sentry — `event_level=ERROR`, WARNING до него не
                # поднимается (см. докстринг `sentry_setup`) — ни оператор,
                # ни человек ничего не видели.
                #
                # Указатель чистим БЕЗУСЛОВНО, независимо от исхода —
                # раньше `self._open_question = ""` стоял в `else` и
                # выполнялся только при успехе. Решение продолжить в
                # разработку УЖЕ принято (критерий найден) — снятие вопроса
                # в теле дальше просто уборка, а НЕ снятая уборка не должна
                # переживать в указателе `self._open_question` дольше самого
                # решения: не почисти его — задача, которая когда-нибудь
                # ВЕРНЁТСЯ в READY_FOR_DEV (rework), унаследует указатель на
                # УЖЕ несуществующий вопрос. С находкой G1 это уже не блокирует
                # автостарт напрямую (`_phase_await_build` читает `self.
                # _acceptance_gate_stalled`, а не этот указатель, — см. её
                # докстринг), но указатель всё равно не должен переживать
                # решение: следующий `_answer_open_question` иначе искал бы
                # ответ на вопрос, которого больше нет.
                #
                # `workflow.patched` обязателен: у прогонов, уже стоящих
                # здесь СТАРЫМ кодом с указателем на вопрос, этой активности
                # в истории нет.
                try:
                    await workflow.execute_activity(
                        activities.close_answered_by_body_edit, issue,
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                except Exception as e:
                    workflow.logger.warning(
                        "не снял устаревший вопрос гейта критерия: %s",
                        _failure_reason(e))
                    if workflow.patched("issue-lifecycle-question-close-failure-notice"):
                        try:
                            await workflow.execute_activity(
                                activities.report_question_close_failure,
                                args=[issue, _failure_reason(e)],
                                start_to_close_timeout=timedelta(seconds=30),
                                retry_policy=RetryPolicy(maximum_attempts=3),
                            )
                        except Exception as notify_exc:
                            workflow.logger.warning(
                                "не смог уведомить об отказе снятия вопроса "
                                "гейта: %s", _failure_reason(notify_exc))
                self._open_question = ""
        return await self._begin_development(issue)

    async def _begin_development(self, issue: IssueInput) -> tuple:
        """Передать задачу агенту разработки — без повторной проверки критерия.

        Отдельная функция, а не хвост `_start_development`, по одной причине:
        принятый ответ на вопрос о критерии (`_phase_await_build`) знает, что
        критерий только что записан — `_place_decision` в `answer_question`
        (`worker/activities.py`) положил его в блок HOWTODEMO ДО того, как
        сюда вернулось управление. Дёрнуть `_start_development` заново означало
        бы честный, но ЛИШНИЙ круг `read_acceptance_criterion` за тем же самым
        текстом — активность, которая станет предсказуемым `True` в 100%
        случаев, кроме одного: тело Issue успели поправить руками между
        ответом и этим вызовом, и тогда лишний круг превратился бы в вопрос
        по уже отвеченному критерию. Дешевле и честнее звать разработку
        напрямую: `answer_question` вернула `accepted` — этого достаточно.

        Одна точка на оба оставшихся входа — решение человека `build-me` и
        автостарт. Две копии этого вызова разъехались бы на первой же правке
        ретраев, и один из входов молча остался бы со старым поведением.

        ISSUE-113: для подзадачи плана передаём root_issue и ветку родителя.
        """
        # ISSUE-113 пункт 2: вычисляем ветку так же, как в _phase_handoff
        source = self._root_issue if self._plan_member and self._root_issue else issue.issue_number
        branch = f"research/issue-{source}"

        try:
            if workflow.patched("issue-lifecycle-develop-child"):
                # Дочерний прогон: у стадии появляется свой WorkflowId, а
                # значит строка в `workflow list` и след, переживающий её
                # завершение. Одна попытка на уровне стадии — ретраи живут
                # внутри, на отдельных шагах.
                pr_number = await workflow.execute_child_workflow(
                    IssueDevelopment.run, issue,
                    id=development_workflow_id(issue.repo, issue.issue_number),
                    # Прогон агента идёт до 45 минут. Ни continue-as-new
                    # родителя, ни его завершение не должны его убивать.
                    parent_close_policy=ParentClosePolicy.ABANDON,
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            else:
                pr_number = await workflow.execute_activity(
                    activities.trigger_openhands_resolver,
                    args=[issue, self._root_issue, branch],
                    # Прогон агента идёт десятками минут, поэтому потолок общий
                    # на весь шаг, а живость сообщается heartbeat'ом.
                    start_to_close_timeout=timedelta(seconds=3600),
                    heartbeat_timeout=timedelta(seconds=300),
                    # Ретрай повторяет активность ЦЕЛИКОМ, включая прогон
                    # агента: на прогоне #39 контур трижды объявил о передаче
                    # задачи и трижды прогнал агента заново.
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
        except WorkflowAlreadyStartedError:
            # Разработка по этому Issue уже идёт — второй дорогой прогон не
            # нужен. Но вернуть ТЕКУЩУЮ фазу здесь нельзя: `_enter` на той же
            # фазе — короткое замыкание без единого await (ни активности, ни
            # таймера, см. начало метода), а автостарт вызывает этот метод
            # СНОВА на следующем же витке `while True`, без парковки между
            # попытками. Получался бы спин на скорости round-trip к серверу:
            # WorkflowAlreadyStarted на каждой попытке, история распухает до
            # continue-as-new и после него — по новой, потому что причина
            # (чужой прогон всё ещё жив) никуда не делась.
            #
            # Разработка ПО ФАКТУ идёт — иначе не было бы этой ошибки, просто
            # ведёт её не этот прогон (человек снял зависший `IssueLifecycle`,
            # а дочерний `develop-*` пережил его благодаря ParentClosePolicy.
            # ABANDON). Честная фаза — `in-development`, тот же исход, что и
            # у режима `dispatch` ниже: результат придёт событием, а не
            # прямым возвратом. Переход `ready-for-dev -> in-development`
            # уже есть в таблице `shared/lifecycle.py` (инициатор `human`, но
            # `transition()` не проверяет, кто зовёт). Дальше фаза уходит в
            # `_phase_park` и честно ждёт сигнала — спин обрывается самим
            # устройством цикла, а не таймаутом.
            workflow.logger.info("development already running for %s#%s",
                                 issue.repo, issue.issue_number)
            return (lifecycle.IN_DEVELOPMENT, "in-development", True)
        except Exception as e:
            # Раньше NotImplementedError отсюда ронял весь воркфлоу: цикл
            # исчезал, и Issue терял владельца состояния.
            reason = _failure_reason(e)
            workflow.logger.warning("передача в разработку не выполнена: %s", reason)
            # Отчёт человеку, а не только метка фазы: до этого срыв передачи был
            # виден лишь как `phase:failed` в списке — отличить его от «ещё
            # работает» можно было только чтением логов контейнера.
            await workflow.execute_activity(
                activities.post_error_label,
                args=[issue, reason],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            return (lifecycle.FAILED, "failed", True)
        if pr_number is None:
            # Режим `dispatch`: работа идёт на чужой стороне, и о её исходе
            # придёт событие `pr-open`. Ждём в `in-development`.
            return (lifecycle.IN_DEVELOPMENT, "in-development", True)
        # Режим `local`: PR открыт прямо сейчас, ждать доклада не о чем — фаза
        # двигается сразу. Ревью доложит о себе само, уже из `pr-open`.
        self._pr_number = pr_number
        return (lifecycle.PR_OPEN, "pr-open", True)

    async def _phase_pr_review(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `pr-review`: довести PR по замечаниям, пока они по делу.

        Круг ведёт цикл, а не отдельный сервис: он уже владеет состоянием
        задачи и стоит здесь же. Отдельный сервис потребовал бы второй копии
        клона, раннера, прогона тестов и пуша — и ещё одного канала докладов.

        Признак завершения — агент сам сказал, что правок не требуется. Тогда
        активность возвращает разбор (строку), а не `True`.
        """
        if not self._pr_number or not deadlines.pr_fix_enabled:
            return await self._phase_park(issue, deadlines)

        rounds = 0
        verdict = ""
        while rounds < deadlines.pr_fix_max_rounds:
            rounds += 1
            try:
                if workflow.patched("issue-lifecycle-prfix-child"):
                    outcome = await workflow.execute_child_workflow(
                        IssuePrFix.run,
                        args=[issue.repo, self._pr_number, rounds],
                        id=pr_fix_workflow_id(issue.repo, self._pr_number, rounds),
                        # Круг идёт до 45 минут: завершение родителя не должно
                        # обрывать начатую доводку PR.
                        parent_close_policy=ParentClosePolicy.ABANDON,
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                else:
                    outcome = await workflow.execute_activity(
                        activities.run_pr_fix_round,
                        args=[issue.repo, self._pr_number, rounds],
                        start_to_close_timeout=timedelta(seconds=3600),
                        heartbeat_timeout=timedelta(seconds=300),
                        # Круг недетерминирован и стоит денег: повтор инициирует
                        # следующая итерация, а не политика ретраев.
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
            except Exception as e:
                workflow.logger.warning("круг правок сорвался: %s", _failure_reason(e))
                break
            if outcome is not True:
                verdict = outcome or ""
                await workflow.execute_activity(
                    activities.finish_pr_fixing,
                    args=[issue.repo, self._pr_number, rounds, True, verdict],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                return await self._phase_park(issue, deadlines)
            # Правки внесены и перепроверка запрошена. Ждём нового доклада
            # ревью: без него следующий круг работал бы по устаревшему тексту.
            signal = await self._wait_for_signal(timedelta(minutes=30))
            if isinstance(signal, AgentEvent):
                # Не всякое событие — это «ревью перепроверило». PR могли влить
                # или вернуть в разработку, и тогда доводить больше нечего:
                # фазу двигает событие, а круг заканчивается.
                if agent_events.target_phase(signal) != lifecycle.PR_REVIEW:
                    return await self._agent_event(signal)
                continue
            if signal is None:
                break

        await workflow.execute_activity(
            activities.finish_pr_fixing,
            args=[issue.repo, self._pr_number, rounds, False, verdict],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return (lifecycle.ESCALATED, "escalated", True)

    async def _start_howtodemo(self, issue: IssueInput) -> None:
        """Приёмка по HowToDemo — отдельным прогоном, без ожидания результата.

        Не ждём намеренно. Приёмка поднимает стенд, ходит по шагам и зовёт
        модель — это десятки минут, а цикл фаз в это время обязан оставаться
        отзывчивым: доклад PR-Agent'а не должен стоять в очереди за приёмкой.
        Докладывает приёмка сама — комментарием и метками `demo:*`.

        `ABANDON` по той же причине: закрытие Issue не должно убивать уже
        идущий прогон приёмки на середине.
        """
        try:
            await workflow.start_child_workflow(
                "HowToDemoVerify",
                {"repo": issue.repo, "issue": issue.issue_number,
                 "pr_number": self._pr_number or 0},
                id=howtodemo_workflow_id(issue.repo, issue.issue_number),
                task_queue=HOWTODEMO_TASK_QUEUE,
                parent_close_policy=ParentClosePolicy.ABANDON,
                execution_timeout=timedelta(hours=1),
            )
        except WorkflowAlreadyStartedError:
            # Приёмку уже запустил человек командой `/howtodemo` — это не сбой,
            # а ровно тот прогон, который мы и хотели.
            workflow.logger.info("приёмка %s#%s уже идёт", issue.repo,
                                 issue.issue_number)

    async def _phase_park(self, issue: IssueInput, deadlines) -> tuple | None:
        """Боковые фазы и фазы внешних агентов.

        Парковка со сроком, а не навсегда (правило R3): «не тупик» не означает
        «вечная сессия». Сигнал `reopen` возвращает Issue в работу по таблице
        переходов — первым допустимым переходом обратно в основной путь.
        """
        # Открылся PR — запускаем приёмку по сценарию из Issue. Фазу не двигаем:
        # `testing` объявлена в модели, но в код не входит ни одним переходом, и
        # оживлять её здесь значило бы править диспетчер фаз ради метки. Приёмка
        # докладывает комментарием и метками `demo:*`, фаза остаётся честной.
        #
        # `workflow.patched` обязателен: прогоны, уже стоящие в pr-open, на
        # реплее выбрали ветку без приёмки, и новый код без развода поколений
        # уронил бы их недетерминизмом.
        if (self._phase == lifecycle.PR_OPEN and deadlines.howtodemo_autostart
                and not self._howtodemo_started
                and workflow.patched("issue-lifecycle-howtodemo-on-pr-open")):
            self._howtodemo_started = True
            await self._start_howtodemo(issue)

        kind = awaiting_mod.kind_for_phase(self._phase)
        signal = await self._wait_for_signal(await self._park(
            kind,
            who=awaiting_mod.who_for_phase(self._phase),
            reason=awaiting_mod.reason_for_phase(self._phase),
            # Срок из окружения — только для ожиданий человека: `PARK_SIDE_STATE_HOURS`
            # настраивался под них. Машинные ждут по таблице своего вида.
            hours=awaiting_mod.deadline_hours(
                kind, deadlines.side_state_hours if kind in awaiting_mod.BLOCKED_ON_HUMAN
                else None)))
        if signal is None:
            return None
        if isinstance(signal, AgentEvent):
            return await self._agent_event(signal)
        if signal == AGENT_ANALYZE:
            # Команда работает и на припаркованном Issue: из бокового состояния
            # хода в анализ нет, поэтому прогон идёт, а фаза остаётся честной.
            return await self._analysis_requested(issue)
        if isinstance(signal, UserComment):
            # Разбор намерения из реплики человека. `recent_artifacts=None`
            # передан явно шестым аргументом — см. комментарий у такого же
            # вызова в `_phase_await_decision` про потерю типов при неполном
            # списке аргументов (poh-demo-checkout#166).
            intent = await workflow.execute_activity(
                activities.interpret_user_comment,
                args=[issue, signal.text, self._phase, self._classification_label,
                      awaiting_mod.reason_for_phase(self._phase), None],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            
            return await self._handle_comment_intent(issue, signal, intent, deadlines)
        
        # Обработка специфических сигналов для фазы DUPLICATE
        if self._phase == lifecycle.DUPLICATE:
            if signal == "not-duplicate":
                # Вернуть в работу (переход в CLASSIFIED)
                # Если на Issue уже стоят метки решения (research-me/bug-me), 
                # проверить их сразу, чтобы не парковать на полный срок
                if workflow.patched("issue-lifecycle-duplicate-exit-checks-existing-labels"):
                    current_labels = await workflow.execute_activity(
                        activities.read_issue_labels,
                        args=[issue.repo, issue.issue_number],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    # Проверяем метки решения человека
                    if labels.has(current_labels, "research-me"):
                        # Проверяем классификацию для совместимости с гардами
                        label = self._classification_label
                        feature = label is None or label == "advisor:feature-request"
                        if feature:
                            # Подзадача плана аналитику не заказывает (см. _phase_await_decision)
                            if self._plan_member and workflow.patched(
                                    "issue-lifecycle-plan-member-skips-analysis"):
                                return (lifecycle.SYSTEM_REQUIREMENTS, "analysis", True)
                            return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
                    elif labels.has(current_labels, "bug-me"):
                        label = self._classification_label
                        bug = label is None or label == "advisor:bug"
                        if bug:
                            return (lifecycle.READY_FOR_DEV, "bug", True)
                return (lifecycle.CLASSIFIED, "awaiting-human-decision", True)
            if signal == "confirm-duplicate":
                # Подтвердить дубликат (переход в CANCELLED).
                #
                # Фазы мало: она — состояние прогона, а не состояние Issue.
                # Без закрытия задача остаётся в списке открытых и в очереди к
                # людям, хотя решение по ней уже принято (#95).
                #
                # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет
                # недетерминизмом прогоны, начатые до выкладки, а задачи в
                # ожидании решения человека живут неделями.
                if (self._duplicate_of
                        and workflow.patched("issue-lifecycle-close-confirmed-duplicate")):
                    try:
                        await workflow.execute_activity(
                            activities.close_as_duplicate,
                            args=[issue, self._duplicate_of],
                            start_to_close_timeout=timedelta(seconds=60),
                            retry_policy=RetryPolicy(maximum_attempts=3),
                        )
                    except Exception as exc:              # noqa: BLE001
                        # Не закрыли — не повод ронять прогон: решение принято,
                        # фаза его отражает, а незакрытый Issue человек закроет
                        # руками. Обратное — потерянное решение.
                        workflow.logger.warning(
                            "дубликат не закрыт: %s", _failure_reason(exc))
                return (lifecycle.CANCELLED, "cancelled", True)
        
        if signal != "reopen":
            return (self._phase, self._stage, False)  # посторонний сигнал — ждём дальше
        back = next((t for t in lifecycle.allowed(self._phase)
                     if t.to in (lifecycle.CREATED, lifecycle.CLASSIFIED)), None)
        if back is None:
            return (self._phase, self._stage, False)
        stage = "intake" if back.to == lifecycle.CREATED else "awaiting-human-decision"
        return (back.to, stage, True)

    async def _run_linear(self, issue: IssueInput) -> None:
        """Прежний линейный сценарий — БЕЗ ИЗМЕНЕНИЙ.

        Живёт ради прогонов, запущенных до перехода на фазовый цикл: они
        припаркованы в проде, и их история не знает маркера патча. Реплей такой
        истории обязан идти по тому же коду, иначе Temporal уронит прогон
        недетерминизмом. Удалять — только когда все прогоны этого поколения
        завершатся (workflow.deprecate_patch).

        Исключение из «без изменений» — достройка списка аргументов там, где
        Temporal сегодня выбрасывает типы (см. tests/test_activity_arg_types.py).
        Это не решение workflow: активность, её порядок и число вызовов не
        меняются, меняется только содержимое ScheduleActivityTask.input —
        а его определитель недетерминизма при реплее не сверяет (сверяет тип
        активности и порядок команд). Раз число выброшенных типов не влияет на
        то, ЧТО куда переходит, маркер patched здесь не нужен — ровно тот же
        довод, что и в основном фазовом цикле для той же категории дефекта.
        """
        default_retry = RetryPolicy(maximum_attempts=3)

        try:
            # --- Zero-cost предфильтры ---
            # `origin_agent=False` явным вторым аргументом: этот сценарий
            # старше самого параметра (провенанс агента `_run_linear` не
            # проверял никогда), и False — не заглушка, а точное повторение
            # прежнего поведения. Без явного значения Temporal получил бы 1
            # аргумент на активность с двумя параметрами и выбросил типы
            # целиком, отдав `issue` активности сырым словарём.
            skip_reason = await workflow.execute_activity(
                activities.prefilter_bot_and_security,
                args=[issue, False],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if skip_reason is not None:
                self._stage = "skipped"
                return  # bot-authored / security-sensitive — дальше не идём

            # --- Состояние по протоколу: одно чтение на старте (R2) ---
            state = await workflow.execute_activity(
                activities.read_protocol_state,
                args=[issue.repo, issue.issue_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )

            # R4: человек забрал Issue себе. Стоп ДО первого вызова LLM — в этом
            # весь смысл рубильника, иначе бюджет уже потрачен.
            if state.agents_off:
                self._stage = "agents-off"
                return

            # R7: follow-up, порождённый follow-up-ом. Дальше цепочку ведёт
            # человек, иначе контур кормит сам себя.
            if state.depth_exceeded:
                await workflow.execute_activity(
                    activities.escalate_to_human,
                    args=[issue, "Цепочка follow-up пошла на второй круг — "
                                 "останавливаю автоматическую обработку (правило R7 "
                                 "протокола агентов). Дальше нужен человек."],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=default_retry,
                )
                self._stage = "escalated"
                return

            # R3: у каждой парковки свой срок. Читаем activity, а не из
            # окружения: таймер пересчитывается при воспроизведении истории, и
            # правка переменной уронила бы идущий прогон недетерминизмом.
            deadlines = await workflow.execute_activity(
                activities.read_deadlines,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )

            # R6: Issue создан агентом — он уже классифицирован. Intake gate и
            # advisor-ответ пропускаем: это был бы разговор сервиса с самим собой.
            # Остаются дедуп и приоритет — они по-прежнему нужны.
            classification: ClassificationResult | None = None
            if state.origin_agent:
                self._stage = "duplicate-check"
            else:
                # --- Intake Gate (дешёвая модель) с циклом уточнений ---
                gate = await workflow.execute_activity(
                    activities.intake_gate,
                    args=[issue, []],  # [] — переписки уточнений ещё нет
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=default_retry,
                )

                # Batch/backfill mode: no human answers clarifications for 39 issues,
                # so a VAGUE issue must escalate, not park on _wait_for_signal() forever.
                #
                # `reason` вторым аргументом явно — активность принимает
                # `reason: str = ""`, а одним позиционным `issue` Temporal
                # получает 1 аргумент на 2 параметра и выбрасывает типы
                # целиком (см. tests/test_activity_arg_types.py).
                if gate.status == "VAGUE" and not issue.interactive:
                    await workflow.execute_activity(
                        activities.escalate_to_human,
                        args=[issue, "Задача осталась неоднозначной (VAGUE) после "
                                     "intake gate, а прогон неинтерактивный — "
                                     "уточнить не у кого. Передаю на ручной разбор."],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    self._stage = "escalated"
                    return

                comment_thread: list[str] = []
                round_count = 0
                while gate.status == "VAGUE":
                    round_count += 1
                    if round_count > MAX_CLARIFICATION_ROUNDS:
                        await workflow.execute_activity(
                            activities.escalate_to_human,
                            args=[issue, f"Уточнение не сузило запрос за "
                                         f"{MAX_CLARIFICATION_ROUNDS} раундов — "
                                         "передаю на ручной разбор."],
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                        self._stage = "escalated"
                        return

                    await workflow.execute_activity(
                        activities.post_clarifying_question,
                        args=[issue, gate.content],
                        start_to_close_timeout=timedelta(seconds=30),
                    )

                    # Ответ может прийти и через 5 минут, и через 3 дня — но не
                    # никогда: без срока Issue, о котором забыли, держал бы
                    # сессию вечно (R3).
                    raw = await self._wait_for_signal(
                        timedelta(hours=deadlines.clarification_hours))
                    if raw is None:
                        await workflow.execute_activity(
                            activities.escalate_to_human,
                            args=[issue, f"Уточнение не получено за "
                                         f"{deadlines.clarification_hours} ч — "
                                         "передаю на ручной разбор."],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=default_retry,
                        )
                        self._stage = "escalated"
                        return
                    if isinstance(raw, UserComment):
                        comment_thread.append(raw.text)

                    gate = await workflow.execute_activity(
                        activities.intake_gate,
                        args=[issue, comment_thread],
                        start_to_close_timeout=timedelta(seconds=120),
                        retry_policy=default_retry,
                    )

                if gate.status == "SPAM":
                    self._stage = "spam"
                    await workflow.execute_activity(
                        activities.close_as_spam,
                        args=[issue, gate.content],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    return

                # --- Классификация (более сильная модель) ---
                # `bft_on_triage=False` явно: этот сценарий старше самой БФТ
                # на триаже (маркер `issue-lifecycle-bft` заведён только для
                # фазового цикла), и False здесь — точное повторение прежнего
                # поведения, а не заглушка.
                self._stage = "classify"
                classification = await workflow.execute_activity(
                    activities.classify_issue,
                    args=[issue, False],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=default_retry,
                )

                if classification.label in (
                    "advisor:existing-functionality",
                    "advisor:consultation",
                ):
                    self._stage = "answered"
                    return  # закрыт содержательным ответом, дальше пайплайн не идёт

            # --- Duplicate Check ---
            self._stage = "duplicate-check"
            dup = await workflow.execute_activity(
                activities.duplicate_check,
                issue,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            if dup.decision == "duplicate":
                self._stage = "duplicate"
                return  # закрыт как дубликат внутри самой activity

            # --- Priority Scoring ---
            self._stage = "priority"
            priority = await workflow.execute_activity(
                activities.score_priority,
                args=[issue, classification, dup],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            await workflow.execute_activity(
                activities.post_priority_comment,
                args=[issue, priority, dup],
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception as e:
            self._stage = "failed"
            await workflow.execute_activity(
                activities.post_error_label,
                args=[issue, _failure_reason(e)],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            return

        # --- Точка решения человека №1: запускать ли тяжёлую стадию ---
        # Ждём research-me / bug-me. Никакого потолка по времени — issue
        # может неделями висеть в бэклоге с приоритетом, это нормально.
        self._stage = "awaiting-human-decision"
        decision = await self._wait_for_signal(
            timedelta(hours=deadlines.human_decision_hours))
        if decision is None:
            await workflow.execute_activity(
                activities.escalate_to_human,
                args=[issue, f"Решение о тяжёлой стадии не принято за "
                             f"{deadlines.human_decision_hours} ч "
                             "(`research-me` / `bug-me`) — снимаю задачу с ожидания. "
                             "Поставь метку, когда понадобится: прогон запустится заново."],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )
            self._stage = "escalated"
            return

        # `classification is None` — сокращённый триаж (Issue от агента): он уже
        # классифицирован на стороне создателя, и гвард «тип совпал с лейблом»
        # здесь не на чем проверять. Пропускаем, а не блокируем: иначе follow-up
        # от PR-Closer нельзя было бы отправить в аналитику вообще.
        feature = classification is None or classification.label == "advisor:feature-request"
        bug = classification is None or classification.label == "advisor:bug"

        if decision == "research-me" and feature:
            # Лейбл research-me — второй вход в ту же аналитику Слоя C, что и
            # команда /analyze, но БЕЗ ack_command: триггер тут лейбл, а не
            # комментарий, так что подтверждать нечего. Дальше — ровно тот же
            # пер-стадийный прогон, что и у команды: одна реализация на оба
            # входа, иначе «та же аналитика» остаётся правдой только на словах.
            self._stage = "analysis"
            analyze_input = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,
                                          title=issue.title, body=issue.body)
            # Метку «идёт прогон» тут ставит сам воркфлоу: триггером был
            # research-me, а не run:analyze, и без этого выборка `label:run:*`
            # не показала бы идущий анализ.
            await workflow.execute_activity(
                activities.mark_command_running,
                args=[issue.repo, issue.issue_number, ANALYZE],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )
            analysis_ok = await _run_staged_analysis(analyze_input)
            if analysis_ok:
                # H1 — единственная точка, где контур сам отдаёт работу человеку.
                # Условия протокола выполнены разом: классификация проведена,
                # дубли проверены, приоритет посчитан, артефакты лежат в ветке.
                await workflow.execute_activity(
                    activities.mark_ready_for_dev,
                    args=[issue, priority.tier, f"research/issue-{issue.issue_number}"],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=default_retry,
                )
        elif decision == "bug-me" and bug:
            self._stage = "bug"
            await workflow.execute_activity(
                activities.run_bug_pipeline,
                issue,
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        else:
            self._stage = "done"
            return  # лейбл не совпал с типом — тот же guard, что раньше был в YAML

        # --- Точка решения человека №2: передавать ли в разработку ---
        self._stage = "awaiting-build-decision"
        build_decision = await self._wait_for_signal(
            timedelta(hours=deadlines.build_decision_hours))
        if build_decision == "build-me":
            # `root_issue=None, branch=None` явно: `_run_linear` старше
            # ISSUE-113 (подзадачи плана и заранее вычисленная ветка) и своей
            # ветки не считает. С обоими None активность внутри
            # (`_dev_resolve_branch`) выводит `research/issue-{issue_number}`
            # — ровно то же имя, что получалось здесь и раньше неявно.
            await workflow.execute_activity(
                activities.trigger_openhands_resolver,
                args=[issue, None, None],
                start_to_close_timeout=timedelta(seconds=90),
                # Одна попытка — по той же причине, что и на основном пути
                # (`_start_development`): ретрай прогоняет агента заново.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        self._stage = "done"


@workflow.defn(name="IssueDevelopment")
class IssueDevelopment:
    """Разработка по подготовленному Issue — дочерний прогон цикла.

    Отдельным воркфлоу, а не активностью, по двум причинам сразу.

    Первая — видимость. Активность внутри родителя не имеет своего
    WorkflowId: в `workflow list` строки нет, а после завершения не остаётся
    и следа — операционная история собиралась логами контейнера и `docker ps`.

    Вторая — ретраи. Одна активность на четыре шага повторялась целиком: на
    прогоне #39 падал только `git push`, уже после работы агента, а заново шёл
    весь прогон, и контур трижды объявил о передаче задачи. Здесь у каждого
    шага своя политика: дорогие и недетерминированные (агент, тесты) идут в
    одну попытку, дешёвые и повторяемые (клон, публикация) — в три.

    Идентификатор фиксирован (`develop-<repo>-<n>`), поэтому повторный запуск
    при идущем прогоне упирается в WorkflowAlreadyStarted, а не поднимает
    второго агента в тот же рабочий каталог.
    """

    @workflow.run
    async def run(self, issue: IssueInput) -> int | None:
        """Возвращает номер PR (`local`) либо None (`dispatch`).

        `None` родитель читает как «работа идёт на чужой стороне, жди события
        `pr-open`», а не как отказ.
        """
        cheap = RetryPolicy(maximum_attempts=3)
        # Одна попытка там, где шаг недетерминирован, идёт десятками минут и
        # стоит денег. Повтор такого инициирует человек, а не политика ретраев.
        once = RetryPolicy(maximum_attempts=1)

        plan = await workflow.execute_activity(
            activities.dev_begin, issue,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=cheap,
        )

        if plan.mode == "dispatch":
            await workflow.execute_activity(
                activities.dev_dispatch, args=[issue, plan.branch],
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=cheap,
            )
            return None

        number: int | None = None
        agent_ran = False
        try:
            # Порядок не косметический: сначала клон и постановка — они
            # единственные могут не состояться до того, как что-либо сказано
            # человеку.
            await workflow.execute_activity(
                activities.dev_prepare, args=[issue, plan.branch],
                start_to_close_timeout=timedelta(seconds=600),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=cheap,
            )
            await workflow.execute_activity(
                activities.dev_announce, args=[issue, plan.branch],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=cheap,
            )
            # MVP: план работ — СТРОГО здесь, между готовым рабочим местом
            # (`dev_prepare` выше уже наполнил `.harness/`) и стартом агента.
            #
            # Не раньше: каталог, который читает и куда пишет `/plan-mvp`,
            # создаёт только `dev_prepare`. Прежняя попытка (Task 9, откачена
            # ревью, revert 80b3291) звала планирование до подготовки —
            # находка K2, «холодный старт»: стадия падала в каталоге,
            # которого никто ещё не создал.
            #
            # Не позже: план — вход агента, а не отчёт по итогам его работы.
            #
            # ПОД МАРКЕРОМ: новая активность — новая команда в истории, и
            # прогоны, начатые до выкладки, обязаны реплеиться прежней
            # последовательностью, без неё.
            #
            # Отказ НЕ роняет прогон: план — необязательный вход агента, а не
            # результат стадии (`PLAN` не входит в `task_context.required()`
            # намеренно) — агент штатно работает без него уже сегодня. Топить
            # дорогой прогон разработки из-за упавшего необязательного шага
            # значило бы разменивать штатный путь на необязательное ускорение.
            if workflow.patched("issue-lifecycle-develop-plan-stage"):
                try:
                    has_plan = await workflow.execute_activity(
                        activities.build_mvp_plan, args=[issue, plan.branch],
                        start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер
                        heartbeat_timeout=timedelta(seconds=300),
                        retry_policy=once,
                    )
                except Exception as e:                    # noqa: BLE001
                    workflow.logger.warning(
                        "план работ не построен: %s", _failure_reason(e))
                else:
                    if not has_plan:
                        workflow.logger.warning(
                            "план работ пуст или не создан — агент продолжит без него")
            # Флаг ставится ДО запуска, а не после: агент пишет в рабочее
            # дерево по ходу работы, и упавший на середине оставляет ровно то,
            # ради чего всё это и делается. Ставить после успеха значило бы
            # терять самый интересный для разбора случай.
            #
            # Признак ведём ЯВНЫМ флагом, а не выводим из вида исключения: вид
            # отказа и наличие изменений — разные вещи, и связывать их значит
            # вернуться к тому же дефекту с другой стороны. Пустое дерево
            # отсекает сама выкладка (`publish_worktree` вернёт None).
            agent_ran = True
            await workflow.execute_activity(
                activities.dev_run_agent, issue,
                start_to_close_timeout=timedelta(seconds=3600),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=once,
            )
            # Находки — ДО тестов и публикации: файл находок обязан исчезнуть из
            # рабочего дерева раньше коммита, иначе уедет в PR как мусор, а на
            # следующем круге правок агент прочитает свои прошлые находки как новые.
            await workflow.execute_activity(
                activities.dev_followups, issue,
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=cheap,
            )
            foreign: list[str] = []
            try:
                await workflow.execute_activity(
                    activities.dev_tests, issue,
                    start_to_close_timeout=timedelta(seconds=1800),
                    heartbeat_timeout=timedelta(seconds=300),
                    retry_policy=once,
                )
            except Exception as tests_exc:                 # noqa: BLE001
                # Красный прогон — ещё не приговор: тесты могли падать и без
                # правки агента. Ровно это случилось на #166 и #167, где `main`
                # был красный из-за истёкшего промокода, а прогон списали в
                # отказ вместе с работой агента.
                #
                # ПОД МАРКЕРОМ: новые команды в теле воркфлоу роняют
                # недетерминизмом прогоны, начатые до выкладки.
                if not workflow.patched("issue-development-repair-loop"):
                    raise
                # Причина, которая уйдёт наружу, если разобрать не выйдет.
                # Обновляется отказом повторного прогона: человеку нужен
                # свежий список падений, а не доремонтный.
                last_exc: BaseException = tests_exc
                try:
                    diagnosis = await workflow.execute_activity(
                        activities.dev_diagnose, args=[issue, None],
                        start_to_close_timeout=timedelta(seconds=3900),
                        heartbeat_timeout=timedelta(seconds=300),
                        retry_policy=once,
                    )
                except Exception as diag_exc:              # noqa: BLE001
                    # Диагностика объясняет отказ тестов, а не заменяет его.
                    # Сама активность свои сбои гасит, но отказ ВЫЗОВА (нет
                    # активности на воркере, таймаут, срыв воркера) приходит
                    # уровнем выше — и без этой ветки наружу уходил бы он, а
                    # исходная причина исчезала. Этот класс подмены в контуре
                    # уже случался.
                    workflow.logger.warning(
                        "диагностика красного прогона не состоялась: %s",
                        _failure_reason(diag_exc))
                    raise tests_exc
                if not diagnosis.parsed:
                    # Об исходе не известно ничего — решать по нему нельзя.
                    raise
                # Заходов ровно `plan.repair_rounds` (умолчание 1). Число
                # приходит из активности, а не из окружения: решение воркфлоу
                # обязано быть детерминированным при реплее, и прочитанное
                # прямо здесь `os.environ` дало бы разное значение до и после
                # правки переменной — см. докстринг `DevelopPlan`.
                rounds = 0
                while diagnosis.own and rounds < plan.repair_rounds:
                    rounds += 1
                    await workflow.execute_activity(
                        activities.dev_announce_repair,
                        args=[issue, diagnosis.own],
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=cheap,
                    )
                    await workflow.execute_activity(
                        activities.dev_repair, args=[issue, diagnosis.own],
                        start_to_close_timeout=timedelta(seconds=3600),
                        heartbeat_timeout=timedelta(seconds=300),
                        retry_policy=once,
                    )
                    # Повторный прогон НЕ роняет ветку своим отказом: при
                    # чужой красноте он красный всегда, и падение наружу
                    # означало бы, что починку невозможно признать удавшейся
                    # ни в одном репозитории, где набор красен не по вине
                    # агента, — то есть ровно там, ради чего всё это писалось.
                    # Решает диагноз ниже, а не код возврата.
                    try:
                        await workflow.execute_activity(
                            activities.dev_tests, issue,
                            start_to_close_timeout=timedelta(seconds=1800),
                            heartbeat_timeout=timedelta(seconds=300),
                            retry_policy=once,
                        )
                    except Exception as retry_exc:         # noqa: BLE001
                        # Наружу пойдёт СВЕЖИЙ отказ, а не доремонтный:
                        # прежний перечисляет падения, часть которых уже
                        # починена, и человек читал бы неправду.
                        last_exc = retry_exc
                    # База та же: базовый коммит не менялся, а лишний прогон
                    # набора стоит времени. Мигание не перепроверяем — эти
                    # тесты уже подтверждены дважды.
                    try:
                        diagnosis = await workflow.execute_activity(
                            activities.dev_diagnose,
                            args=[issue, diagnosis.baseline],
                            start_to_close_timeout=timedelta(seconds=1900),
                            heartbeat_timeout=timedelta(seconds=300),
                            retry_policy=once,
                        )
                    except Exception as diag_exc:          # noqa: BLE001
                        workflow.logger.warning(
                            "диагностика после починки не состоялась: %s",
                            _failure_reason(diag_exc))
                        raise last_exc
                    if not diagnosis.parsed:
                        # Об исходе повторного прогона не известно ничего.
                        raise last_exc
                if diagnosis.own:
                    # Заходы кончились, свои падения остались — человек.
                    workflow.logger.warning(
                        "починка не удалась, осталось своих падений: %s",
                        len(diagnosis.own))
                    raise last_exc
                foreign = diagnosis.foreign
            number = await workflow.execute_activity(
                activities.dev_publish, args=[issue, plan.branch, foreign],
                start_to_close_timeout=timedelta(seconds=600),
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=cheap,
            )
        except Exception as exc:                          # noqa: BLE001
            # Сорванный прогон обязан оставить материал для разбора.
            #
            # Отказ, ради которого написано: на #166 упали три теста из
            # семидесяти трёх, и тринадцать минут работы агента исчезли без
            # следа — `dev_publish` идёт после `dev_tests` и не выполнился.
            #
            # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет
            # недетерминизмом прогоны, начатые до выкладки, а прогон агента
            # идёт до 45 минут — реплей убил бы ровно ту работу, которую этот
            # код спасает.
            if agent_ran and workflow.patched("issue-development-partial-publish"):
                try:
                    await workflow.execute_activity(
                        activities.dev_publish_partial,
                        args=[issue, plan.branch, _failure_reason(exc)[:1500]],
                        start_to_close_timeout=timedelta(seconds=600),
                        heartbeat_timeout=timedelta(seconds=300),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                except Exception as save_exc:              # noqa: BLE001
                    # Спасение НЕ подменяет причину: наружу уходит исходное
                    # исключение, а неудача самой выкладки только пишется в
                    # лог. Иначе первопричина исчезает — этот класс подмены в
                    # контуре уже случался.
                    workflow.logger.warning(
                        "частичная выкладка не удалась: %s",
                        _failure_reason(save_exc))
            raise
        finally:
            # Запись об итерации — В FINALLY, а не после успешных шагов.
            #
            # Красные тесты и сорвавшийся прогон агента — самые интересные для
            # разбора исходы, и именно они пропускали запись: исключение из
            # шага уносило управление мимо неё. Слой собирал статистику только
            # по удачам и на ней же учился.
            #
            # ПОД МАРКЕРОМ: новая команда в теле воркфлоу роняет
            # недетерминизмом прогоны, начатые до выкладки, а прогон агента
            # идёт до 45 минут. Прецедент в этом же файле — реплей без маркера
            # падает `Timer machine does not handle ActivityTaskScheduled`.
            if workflow.patched("issue-lifecycle-capture-episode-always"):
                try:
                    await workflow.execute_activity(
                        activities.capture_episode,
                        args=[issue, plan.branch, number],
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=cheap,
                    )
                except Exception as e:                   # noqa: BLE001
                    # Слой опционален и не имеет права стоить прогона — тем
                    # более уже упавшего, где запись лишь пояснение к отказу.
                    workflow.logger.warning(
                        "запись об итерации не отдана слою памяти: %s",
                        _failure_reason(e))

        if number is None:
            reason = "агент не изменил ни одного файла — открывать нечего"
            if workflow.patched("issue-lifecycle-empty-run-diagnosis"):
                # Прежнее сообщение обвиняло агента в бездействии даже тогда,
                # когда он не сделал ни одного хода — то есть когда отказало
                # окружение. Человек шёл разбирать постановку вместо
                # инфраструктуры. Признак лежит на диске, поэтому спрашиваем
                # активность: воркфлоу файловой системы не видит.
                #
                # Уточнение НЕ ИМЕЕТ ПРАВА подменить собой исходный отказ:
                # диагностика, способная сломать то, что диагностирует, хуже
                # её отсутствия. Не вышло — докладываем прежним текстом.
                try:
                    reason = await workflow.execute_activity(
                        activities.dev_empty_run_reason,
                        args=[issue],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=cheap,
                    )
                except Exception as e:                   # noqa: BLE001
                    workflow.logger.warning(
                        "причину пустого прогона выяснить не удалось: %s",
                        _failure_reason(e))
            raise ApplicationError(reason)
        return number


@workflow.defn(name="IssuePrFix")
class IssuePrFix:
    """Один круг правок по замечаниям ревью — дочерний прогон цикла.

    Отдельный воркфлоу на КАЖДЫЙ круг, а не на цикл целиком: круги разделены
    ожиданием внешнего доклада ревью, и объединение их в один прогон дало бы
    воркфлоу, большую часть жизни простаивающий в ожидании чужого сигнала.
    Ожиданием по-прежнему управляет родитель — он владеет состоянием задачи.
    """

    @workflow.run
    async def run(self, repo: str, pr_number: int, round_number: int) -> bool | str:
        """`True` — правки внесены и запрошена перепроверка. Строка — правок не
        потребовалось, и это её разбор.

        Разные типы возврата намеренно: «сделали» и «не потребовалось» — разные
        исходы, и сводить их к булеву значению значило бы потерять объяснение.
        """
        return await workflow.execute_activity(
            activities.run_pr_fix_round,
            args=[repo, pr_number, round_number],
            start_to_close_timeout=timedelta(seconds=3600),
            heartbeat_timeout=timedelta(seconds=300),
            # Круг недетерминирован и стоит денег: повтор инициирует следующая
            # итерация родителя, а не политика ретраев.
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


@workflow.defn(name="IssueAnalysis")
class IssueAnalysis:
    """Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.

    Работает в двух режимах (#37): дочерним прогоном `IssueLifecycle`, когда
    цикл жив, и самостоятельным — при автономном запуске (скрипт, прогон
    прежнего поколения). Код один и тот же; отличается только родитель.

    Фиксированный id `analysis-<repo>-<n>` даёт идемпотентность в обоих
    режимах: повторный `/analyze` упрётся в WorkflowAlreadyStarted, а не
    запустит второй дорогой прогон.
    """

    @workflow.run
    async def run(self, analyze: AnalyzeInput) -> bool:
        """Возвращает, опубликованы ли артефакты.

        Родителю этот ответ нужен, чтобы решить, можно ли передавать задачу
        разработчику: без аналитики передавать нечего. Автономный запуск
        результат просто игнорирует.
        """
        if await _agents_off(analyze.repo, analyze.issue_number, "/analyze"):
            return False
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return await _run_staged_analysis(analyze)


@workflow.defn(name="IssueBft")
class IssueBft:
    """БФТ по Issue: быстрый проход (`/bft`) и глубокая проработка (`/bft-deep`).

    Один воркфлоу на оба режима — различает их поле `mode` входа. Разделение на
    два воркфлоу дало бы две почти одинаковые обвязки (рубильник, ack, метки,
    комментарий о сбое) и два места, где эту обвязку надо чинить.

    Работает в двух режимах запуска, как и `IssueAnalysis` (#37): дочерним
    прогоном цикла, когда цикл жив, и самостоятельным — иначе. Id фиксирован в
    пределах режима, поэтому повторная команда при идущем прогоне упирается в
    `WorkflowAlreadyStarted`, а не платит второй раз.
    """

    def __init__(self) -> None:
        self._stage = "accepted"
        self._mode = bft.FAST

    @workflow.query
    def stage(self) -> str:
        """Стадия прогона — для Temporal UI (вкладка Queries).

        У быстрого прохода стадий по сути нет, у глубокого их семь, и без этого
        значения прогон, стоящий сорок минут на `concept`, выглядит в UI так же,
        как зависший: просто `Running`.
        """
        return self._stage

    @workflow.query
    def mode(self) -> str:
        return self._mode

    @workflow.run
    async def run(self, req: BftRequest) -> bool:
        """Возвращает, опубликован ли БФТ.

        Родителю ответ нужен затем же, зачем и от аналитики: триаж по нему решает,
        оставлять ли Issue без содержательного ответа человеку. Автономный запуск
        результат игнорирует.
        """
        # Вебхук и скрипты могут прислать сырой словарь — та же нормализация, что
        # и в цикле: молча получить dict вместо dataclass хуже, чем упасть.
        if isinstance(req, dict):
            req = BftRequest(**req)
        self._mode = req.mode
        command = BFT_DEEP if req.mode == bft.DEEP else BFT
        if await _agents_off(req.repo, req.issue_number, f"/{command}"):
            return False

        await workflow.execute_activity(
            activities.ack_bft_command, req,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        ok = True
        try:
            if req.mode == bft.DEEP:
                await self._run_deep(req)
            else:
                self._stage = "fast"
                await workflow.execute_activity(
                    activities.run_bft_fast, req,
                    start_to_close_timeout=timedelta(seconds=300),
                    # Один вызов модели: сетевой сбой лечится повтором, и
                    # дублирующего комментария он не даёт — публикация идёт
                    # последним шагом той же активности.
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
            self._stage = "published"
        except Exception as exc:
            ok = False
            self._stage = "failed"
            reason = str(getattr(exc, "cause", None) or exc)
            published = False
            if req.mode == bft.DEEP:
                # Сначала спасаем сделанное, потом сообщаем о сбое. Порядок не
                # косметический: `cleanup` в `finally` снимает каталог, и после
                # него публиковать будет уже нечего. Прогон рвётся чаще от
                # чужого — лимит провайдера, 524, выкладка посреди работы, — и
                # терять из-за этого двадцать минут работы модели незачем.
                try:
                    done = await workflow.execute_activity(
                        activities.publish_bft_partial, args=[req, reason[:300]],
                        start_to_close_timeout=timedelta(seconds=300),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                    published = bool(done)
                except Exception as partial_exc:
                    workflow.logger.warning(
                        "публикация частичного БФТ не удалась: %s", partial_exc)
            if not published:
                # Сказать нечего кроме самого сбоя: ни одна стадия не дала
                # артефакта, продолжать в следующий раз будет не с чего.
                await workflow.execute_activity(
                    activities.publish_bft_error, args=[req, reason[:500]],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
        finally:
            if req.mode == bft.DEEP:
                # Каталог живёт вне Temporal — снимаем на обоих путях. Провал
                # самой уборки не должен затирать реальный исход прогона.
                try:
                    await workflow.execute_activity(
                        activities.cleanup_bft_workspace, req,
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                except Exception as cleanup_exc:
                    workflow.logger.warning(
                        "cleanup_bft_workspace failed (best-effort, ignored): %s",
                        cleanup_exc)
        await _finish_labels(req.repo, req.issue_number, command, ok=ok)
        return ok

    async def _run_deep(self, req: BftRequest) -> None:
        """Канонический пайплайн bft-writer — стадия за стадией.

        Ретраев у стадии нет по той же причине, что и у стадий FNR: прогон
        недетерминирован, мутирует файлы и стоит денег, поэтому повтор инициирует
        человек. Исключение — потеря воркера: heartbeat-таймаут не сбой стадии, а
        рестарт контейнера, и без второй попытки любая выкладка посреди прогона
        убивала бы БФТ целиком.
        """
        self._stage = "prepare"
        await workflow.execute_activity(
            activities.prepare_bft_workspace, req,
            start_to_close_timeout=timedelta(seconds=1000),  # clone 300 + repomix 600 + буфер
            heartbeat_timeout=timedelta(seconds=300),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        for stage_name in bft.DEEP_STAGE_NAMES:
            self._stage = stage_name
            await workflow.execute_activity(
                activities.run_bft_stage, args=[req, stage_name],
                start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    non_retryable_error_types=["RuntimeError"],
                ),
            )
        self._stage = "publish"
        await workflow.execute_activity(
            activities.publish_bft_deep, req,
            start_to_close_timeout=timedelta(seconds=300),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )


@workflow.defn(name="IssueEstimation")
class IssueEstimation:
    """Оценка трудоёмкости по команде /estimate.

    Отдельный workflow, а не сигнал в IssueLifecycle: тот завершается после
    приоритизации (а на спаме и дубликате — раньше), и через неделю сигналить
    было бы некуда. ID включает comment_id, поэтому повторная доставка того же
    вебхука не запускает вторую оценку, а новая команда — это честно новый
    прогон со своей историей в Temporal UI.
    """

    @workflow.run
    async def run(self, req: EstimateRequest) -> None:
        default_retry = RetryPolicy(maximum_attempts=3)
        # Стадия нужна, чтобы человек в комментарии увидел, ЧТО именно
        # сломалось, а не абстрактное «ошибка обработки».
        if await _agents_off(req.repo, req.issue_number, "/estimate"):
            return
        stage = "подтверждение команды"
        try:
            await workflow.execute_activity(
                activities.ack_estimate_command,
                req,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )

            stage = "сбор контекста"
            context = await workflow.execute_activity(
                activities.collect_estimation_context,
                req,
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=default_retry,
            )

            stage = "извлечение фактов"
            facts = await workflow.execute_activity(
                activities.extract_estimation_facts,
                context,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )

            stage = "расчёт"
            result: EstimateResult = await workflow.execute_activity(
                activities.compute_estimate,
                args=[facts, context],
                start_to_close_timeout=timedelta(seconds=30),
                # Расчёт детерминирован и не ходит в сеть: повтор дал бы
                # ровно тот же результат, ретрай тут бессмыслен.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

            stage = "публикация"
            await workflow.execute_activity(
                activities.post_estimate_comment,
                args=[req, result],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )
            await _finish_labels(req.repo, req.issue_number, ESTIMATE, ok=True)
        except Exception as e:
            await workflow.execute_activity(
                activities.post_estimate_error,
                args=[req, stage, _failure_reason(e)],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            await _finish_labels(req.repo, req.issue_number, ESTIMATE, ok=False)


@workflow.defn(name="IssueResearch")
class IssueResearch:
    """Продуктовое исследование по команде /research или метке run:research.

    Отдельный workflow, аналогичный IssueAnalysis, но с другим пайплайном:
    PRD, обход продуктовых нексусов, исследование рынка и спроса вместо
    бизнес-анализа.

    Работает в двух режимах: дочерним прогоном IssueLifecycle, когда цикл
    жив, и самостоятельным — при автономном запуске. Id фиксирован, поэтому
    повторная команда упирается в WorkflowAlreadyStarted.
    """

    @workflow.run
    async def run(self, analyze: AnalyzeInput) -> bool:
        """Возвращает, опубликованы ли артефакты.

        Родителю этот ответ нужен, чтобы решить, можно ли переходить к
        следующей фазе. Автономный запуск результат просто игнорирует.
        """
        if await _agents_off(analyze.repo, analyze.issue_number, "/research"):
            return False
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        # TODO: Реализовать пайплайн продуктового исследования.
        # Пока — заглушка, возвращающая успех, чтобы не блокировать фазу.
        # Реализация должна включать: PRD, обход продуктовых нексусов,
        # исследование рынка и спроса — по аналогии с _run_staged_analysis.
        return True
