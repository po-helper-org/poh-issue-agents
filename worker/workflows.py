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
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared.commands import ANALYZE, ESTIMATE
    from shared.workflow_types import (
        AnalyzeInput,
        ClassificationResult,
        EstimateRequest,
        EstimateResult,
        IssueInput,
        WebhookAuditInput,
    )

    import activities

MAX_CLARIFICATION_ROUNDS = 2


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


@workflow.defn(name="IssueLifecycle")
class IssueLifecycle:
    def __init__(self) -> None:
        self._signal_queue: asyncio.Queue[str] = asyncio.Queue()
        self._analyze_labeled = False
        self._issue: IssueInput | None = None
        self._stage = "intake"

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

    @workflow.signal
    async def human_decision(self, label: str) -> None:
        await self._signal_queue.put(label)

    @workflow.signal
    async def user_comment(self, text: str) -> None:
        await self._signal_queue.put(f"__comment__:{text}")

    @workflow.signal
    async def analyze_requested(self, comment_id: int) -> None:
        """По Issue запрошен автономный анализ командой /analyze.

        Вешаем видимую метку `analyzing`, чтобы в ленте триажа было понятно, что
        прогон идёт; сам анализ несёт отдельный воркфлоу IssueAnalysis (из
        webhook), здесь — только метка, и ставим её один раз (повторный /analyze
        не плодит лейблы). Тяжёлую работу из хендлера не запускаем: run() обычно
        припаркован в _wait_for_signal(), спавн оттуда гонялся бы с основным
        циклом; лёгкая activity add_label безопасна.

        `_analyze_labeled` ставим ДО первого await: хендлеры кооперативны
        (переключение только на await), поэтому второй почти одновременный
        сигнал увидит True и не поставит второй лейбл. Сигнал может прийти в
        самой первой активации воркфлоу — раньше, чем run() выполнил
        `self._issue = issue` (Temporal применяет сигналы до создания задачи
        run()); поэтому ЖДЁМ инициализацию через wait_condition, а не роняем
        метку молча по `self._issue is None`.

        Известный компромисс: политика незавершённых хендлеров по умолчанию —
        WARN_AND_ABANDON. Если run() успеет завершиться (например, через
        `else: return` без await), пока mark_analyzing лишь запланирована, метка
        не встанет, а в лог уйдёт warning. Метка косметическая (её никто не
        читает), гарантировать её ожиданием all_handlers_finished в run() не
        стоит — само-лечится при следующем /analyze в припаркованном состоянии.
        """
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

    async def _wait_for_signal(self, timeout: timedelta | None = None) -> str | None:
        try:
            if timeout:
                return await asyncio.wait_for(
                    self._signal_queue.get(), timeout=timeout.total_seconds()
                )
            return await self._signal_queue.get()
        except asyncio.TimeoutError:
            return None

    @workflow.run
    async def run(self, issue: IssueInput) -> None:
        self._issue = issue  # даёт analyze_requested доступ к repo/number
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
    """Аналитика по запросу (Слой C) — отдельный воркфлоу на команду /analyze.

    Отдельный, а не часть IssueLifecycle: команда приходит в произвольный
    момент, когда воркфлоу триажа уже завершён (advisor-ответ) или припаркован
    в ожидании лейбла. Фиксированный id `analysis-<repo>-<n>` даёт
    идемпотентность: повторный /analyze упрётся в WorkflowAlreadyStarted.
    """

    @workflow.run
    async def run(self, analyze: AnalyzeInput) -> None:
        if await _agents_off(analyze.repo, analyze.issue_number, "/analyze"):
            return
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await _run_staged_analysis(analyze)


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
