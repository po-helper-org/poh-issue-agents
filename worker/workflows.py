"""
IssueLifecycle — один Temporal-workflow на один issue (ID = issue-<repo>-<n>,
это даёт идемпотентность бесплатно: повторный issues.opened webhook не
создаст вторую сущность).

Signals заменяют то, что раньше делали отдельные GitHub Actions,
триггерящиеся на лейблы:
- human_decision("research-me" | "bug-me" | "build-me")
- user_comment(текст) — ответ на уточняющий вопрос intake gate

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
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from shared import lifecycle
    from shared.commands import ANALYZE, ESTIMATE
    from shared.workflow_ids import analysis_workflow_id, estimate_workflow_id
    from shared import agent_events
    from shared.agent_events import AgentEvent
    from shared.workflow_types import (
        AnalyzeInput,
        ClassificationResult,
        EstimateRequest,
        EstimateResult,
        IssueInput,
        LifecycleState,
        OrphanEventInput,
        WebhookAuditInput,
    )

    import activities

MAX_CLARIFICATION_ROUNDS = 2

# Запрос на прогон аналитики, доставленный в общую очередь сигналов. Префикс —
# та же схема, что у `__comment__:`: одна очередь, разные виды событий, и
# обработчик фазы решает, что с ними делать.
AGENT_ANALYZE = "__agent__:analyze"

# Сколько ключей событий помнить ради идемпотентности. Цикл живёт месяцами, а
# событий по одному Issue — десятки: список без потолка рос бы вместе с
# историей, ровно тем объёмом, который continue-as-new и призван обрывать.
SEEN_EVENTS_KEPT = 50

# Порог длины истории для continue-as-new. Ниже потолка, на котором уже
# спотыкалась консолидация (~990 событий): реплей должен укладываться в
# workflow-task timeout с запасом, а не впритык.
HISTORY_EVENT_THRESHOLD = 800


def _failure_reason(e: BaseException) -> str:
    """"ExcType: message" из ПЕРВОПРИЧИНЫ для тегов/группировки Sentry.

    catch-ветки ловят обёртку Temporal (ActivityError «Activity task failed»),
    а не исходное исключение activity. Разворачиваем `.cause`: у ApplicationError
    есть `.type` = имя исходного класса (RuntimeError/ValidationError/…), это и
    даёт осмысленный fingerprint вместо единственного «ActivityError» на всё.
    Чистые операции над атрибутами — детерминированы, безопасны в workflow-коде.
    """
    cause = getattr(e, "cause", None) or e
    exc_type = getattr(cause, "type", None) or type(cause).__name__
    return f"{exc_type}: {cause}"


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
                retry_policy=RetryPolicy(maximum_attempts=1),
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


@workflow.defn(name="IssueLifecycle")
class IssueLifecycle:
    def __init__(self) -> None:
        # Очередь несёт и решения человека (строки), и факты внешних агентов
        # (AgentEvent). Один поток вместо двух — иначе фаза, ждущая решения, не
        # проснулась бы на событии, и наоборот.
        self._signal_queue: asyncio.Queue[str | AgentEvent] = asyncio.Queue()
        self._analyze_labeled = False
        self._issue: IssueInput | None = None
        self._stage = "intake"
        self._phase = lifecycle.CREATED
        self._phase_driven = False  # True — прогон идёт фазовым циклом
        self._priority_tier = ""
        self._classification_label: str | None = None
        self._analysis_done = False
        self._generation = 0
        # Момент входа в текущую фазу. Проставляется в run() до первого await;
        # None только пока воркфлоу не начал исполняться.
        self._phase_since: datetime | None = None
        self._analyze_comment_id: int | None = None
        self._analyze_pending = False  # запрос на аналитику лежит в очереди
        # Ключи уже учтённых событий агентов: один факт двигает фазу один раз.
        self._seen_agent_events: list[str] = []

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
    async def user_comment(self, text: str) -> None:
        await self._signal_queue.put(f"__comment__:{text}")

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
        if self._analyze_pending:
            return
        self._analyze_pending = True
        self._analyze_comment_id = comment_id
        await workflow.wait_condition(lambda: self._issue is not None)
        await self._signal_queue.put(AGENT_ANALYZE)

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
                id=estimate_workflow_id(req.repo, req.issue_number, comment_id),
                # Родитель переживёт continue-as-new и завершение цикла, а
                # оценка — нет: ABANDON оставляет её доигрывать саму.
                parent_close_policy=ParentClosePolicy.ABANDON,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except WorkflowAlreadyStartedError:
            # Тот же вебхук доставлен повторно — оценка уже идёт.
            workflow.logger.info("estimate already running for %s#%s",
                                 req.repo, req.issue_number)

    async def _wait_for_signal(self, timeout: timedelta | None = None) -> str | AgentEvent | None:
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
            generation=self._generation + 1,
            phase_since_epoch=self._phase_since.timestamp() if self._phase_since else 0.0,
        )

    def _history_is_long(self) -> bool:
        """Порог по длине истории, а не по числу итераций: цена реплея зависит
        от событий, а одна фаза может стоить и трёх событий, и трёхсот."""
        return workflow.info().get_current_history_length() >= HISTORY_EVENT_THRESHOLD

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
        # Запрос израсходован: следующий прогон не должен реагировать на
        # комментарий, к которому он отношения не имеет, а новая команда
        # обязана снова доехать до цикла.
        self._analyze_comment_id = None
        self._analyze_pending = False
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

    async def _agent_event(self, event: AgentEvent) -> tuple:
        """Факт внешнего агента — переход по той же таблице, что и у своих.

        Недопустимый переход НЕ роняет прогон, в отличие от `_enter`: там
        источник — наш собственный код, и невозможный переход означает ошибку,
        которую надо увидеть. Здесь источник — соседний сервис со своим
        релизным циклом; его рассинхрон с нашей моделью должен приводить к
        разбору человеком, а не к падению цикла Issue.
        """
        target = agent_events.target_phase(event)
        if target == self._phase:
            return (self._phase, self._stage, False)  # тот же факт другими словами
        if not lifecycle.can(self._phase, target):
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
        if lifecycle.can(self._phase, lifecycle.BUSINESS_ANALYSIS):
            return (lifecycle.BUSINESS_ANALYSIS, "analysis", True)
        await self._run_analysis_child(issue)
        return (self._phase, self._stage, False)

    async def _run_phase_loop(self, issue: IssueInput) -> None:
        deadlines = await workflow.execute_activity(
            activities.read_deadlines,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        while True:
            if lifecycle.is_terminal(self._phase):
                return  # «вечноживущий» не значит «незакрываемый»

            if self._phase == lifecycle.CREATED:
                nxt = await self._phase_triage(issue, deadlines)
            elif self._phase == lifecycle.CLASSIFIED:
                nxt = await self._phase_await_decision(issue, deadlines)
            elif self._phase == lifecycle.BUSINESS_ANALYSIS:
                nxt = await self._phase_analysis(issue)
            elif self._phase == lifecycle.SYSTEM_REQUIREMENTS:
                nxt = await self._phase_handoff(issue)
            elif self._phase == lifecycle.READY_FOR_DEV:
                nxt = await self._phase_await_build(issue, deadlines)
            else:
                # Боковые состояния и фазы, которые ведут внешние агенты (#38):
                # цикл держит их живыми, пока не истечёт срок ожидания.
                nxt = await self._phase_park(issue, deadlines)

            if nxt is None:
                return  # срок ожидания истёк — цикл закрывается (правило R3)
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
            skip_reason = await workflow.execute_activity(
                activities.prefilter_bot_and_security,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )
            if skip_reason is not None:
                return (lifecycle.SKIPPED, "skipped", True)

            state = await workflow.execute_activity(
                activities.read_protocol_state,
                args=[issue.repo, issue.issue_number],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=default_retry,
            )
            if state.agents_off:
                # Метку не пишем: человек забрал Issue себе, и наши пометки на
                # нём — ровно то, от чего он отгородился рубильником.
                return (lifecycle.CANCELLED, "agents-off", False)
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

            classification: ClassificationResult | None = None
            if not state.origin_agent:
                gate = await workflow.execute_activity(
                    activities.intake_gate,
                    args=[issue, []],
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=default_retry,
                )
                if gate.status == "VAGUE" and not issue.interactive:
                    await workflow.execute_activity(
                        activities.escalate_to_human,
                        issue,
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
                            issue,
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
                    if isinstance(raw, str) and raw.startswith("__comment__:"):
                        comment_thread.append(raw[len("__comment__:"):])

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
                classification = await workflow.execute_activity(
                    activities.classify_issue,
                    issue,
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=default_retry,
                )
                if classification.label in ("advisor:existing-functionality",
                                            "advisor:consultation"):
                    return (lifecycle.ANSWERED, "answered", True)
            self._classification_label = classification.label if classification else None

            self._stage = "duplicate-check"
            dup = await workflow.execute_activity(
                activities.duplicate_check,
                issue,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            if dup.decision == "duplicate":
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

    async def _phase_await_decision(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `classified`: ждём решения человека о тяжёлой стадии."""
        decision = await self._wait_for_signal(
            self._park_timeout(deadlines.human_decision_hours))
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

        # `classification_label is None` — сокращённый триаж (Issue от агента):
        # он уже классифицирован на стороне создателя, гвард проверять не на чем.
        label = self._classification_label
        feature = label is None or label == "advisor:feature-request"
        bug = label is None or label == "advisor:bug"
        if decision == "research-me" and feature:
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

    async def _phase_handoff(self, issue: IssueInput) -> tuple | None:
        """Фаза `system-requirements`: передача разработчику (H1)."""
        await workflow.execute_activity(
            activities.mark_ready_for_dev,
            args=[issue, self._priority_tier, f"research/issue-{issue.issue_number}"],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", True)

    async def _phase_await_build(self, issue: IssueInput, deadlines) -> tuple | None:
        """Фаза `ready-for-dev`: ждём, возьмут ли задачу в разработку."""
        decision = await self._wait_for_signal(
            self._park_timeout(deadlines.build_decision_hours))
        if decision is None:
            self._stage = "done"
            return None  # срок вышел — цикл закрывается, задача осталась в очереди
        if isinstance(decision, AgentEvent):
            return await self._agent_event(decision)
        if decision == AGENT_ANALYZE:
            return await self._analysis_requested(issue)
        if decision != "build-me":
            return (lifecycle.READY_FOR_DEV, "awaiting-build-decision", False)
        try:
            await workflow.execute_activity(
                activities.trigger_openhands_resolver,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception as e:
            # Раньше NotImplementedError отсюда ронял весь воркфлоу: цикл
            # исчезал, и Issue терял владельца состояния.
            workflow.logger.warning("build-me не выполнен: %s", _failure_reason(e))
            return (lifecycle.FAILED, "failed", True)
        return (lifecycle.IN_DEVELOPMENT, "in-development", True)

    async def _phase_park(self, issue: IssueInput, deadlines) -> tuple | None:
        """Боковые фазы и фазы внешних агентов.

        Парковка со сроком, а не навсегда (правило R3): «не тупик» не означает
        «вечная сессия». Сигнал `reopen` возвращает Issue в работу по таблице
        переходов — первым допустимым переходом обратно в основной путь.
        """
        signal = await self._wait_for_signal(self._park_timeout(deadlines.side_state_hours))
        if signal is None:
            return None
        if isinstance(signal, AgentEvent):
            return await self._agent_event(signal)
        if signal == AGENT_ANALYZE:
            # Команда работает и на припаркованном Issue: из бокового состояния
            # хода в анализ нет, поэтому прогон идёт, а фаза остаётся честной.
            return await self._analysis_requested(issue)
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
        """
        default_retry = RetryPolicy(maximum_attempts=3)

        try:
            # --- Zero-cost предфильтры ---
            skip_reason = await workflow.execute_activity(
                activities.prefilter_bot_and_security,
                issue,
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
                if gate.status == "VAGUE" and not issue.interactive:
                    await workflow.execute_activity(
                        activities.escalate_to_human,
                        issue,
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
                            issue,
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
                    if raw.startswith("__comment__:"):
                        comment_thread.append(raw[len("__comment__:"):])

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
                self._stage = "classify"
                classification = await workflow.execute_activity(
                    activities.classify_issue,
                    issue,
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
            await workflow.execute_activity(
                activities.trigger_openhands_resolver,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )
        self._stage = "done"


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
