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
    from shared.workflow_types import (
        AnalyzeInput,
        EstimateRequest,
        EstimateResult,
        IssueInput,
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


@workflow.defn(name="IssueLifecycle")
class IssueLifecycle:
    def __init__(self) -> None:
        self._signal_queue: asyncio.Queue[str] = asyncio.Queue()
        self._analyze_labeled = False
        self._issue: IssueInput | None = None

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
                return  # bot-authored / security-sensitive — дальше не идём

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
                    return

                await workflow.execute_activity(
                    activities.post_clarifying_question,
                    args=[issue, gate.content],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Ждём ответ пользователя без таймаута — это может быть и через
                # 5 минут, и через 3 дня, Temporal не против.
                raw = await self._wait_for_signal()
                if raw and raw.startswith("__comment__:"):
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
                return

            # --- Классификация (более сильная модель) ---
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
                return  # закрыт содержательным ответом, дальше пайплайн не идёт

            # --- Duplicate Check ---
            dup = await workflow.execute_activity(
                activities.duplicate_check,
                issue,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=default_retry,
            )
            if dup.decision == "duplicate":
                return  # закрыт как дубликат внутри самой activity

            # --- Priority Scoring ---
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
        decision = await self._wait_for_signal()

        if decision == "research-me" and classification.label == "advisor:feature-request":
            # Лейбл research-me — второй вход в ту же аналитику Слоя C, что и
            # команда /analyze, но БЕЗ ack_command: триггер тут лейбл, а не
            # комментарий, так что подтверждать нечего. Сам прогон и обработка
            # сбоя — как в IssueAnalysis.run: пайплайн дорогой и недетерминиро-
            # ванный, вслепую не ретраим, а падение обязано быть видно в
            # GitHub через publish_analysis_error, а не просто уронить этот
            # workflow молча.
            analyze_input = AnalyzeInput(repo=issue.repo, issue_number=issue.issue_number,
                                          title=issue.title, body=issue.body)
            try:
                await workflow.execute_activity(
                    activities.run_analysis_pipeline,
                    analyze_input,
                    start_to_close_timeout=timedelta(seconds=4500),
                    heartbeat_timeout=timedelta(seconds=300),
                    retry_policy=RetryPolicy(maximum_attempts=1),  # не ретраим дорогой прогон вслепую
                )
            except Exception as exc:
                # exc — ActivityError с общим текстом Temporal-core, настоящая
                # причина лежит в exc.cause (см. тот же разбор в IssueAnalysis.run).
                reason = str(getattr(exc, "cause", None) or exc)
                await workflow.execute_activity(
                    activities.publish_analysis_error,
                    args=[analyze_input, reason[:500]],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
        elif decision == "bug-me" and classification.label == "advisor:bug":
            await workflow.execute_activity(
                activities.run_bug_pipeline,
                issue,
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        else:
            return  # лейбл не совпал с типом — тот же guard, что раньше был в YAML

        # --- Точка решения человека №2: передавать ли в разработку ---
        build_decision = await self._wait_for_signal()
        if build_decision == "build-me":
            await workflow.execute_activity(
                activities.trigger_openhands_resolver,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )


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
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        try:
            await workflow.execute_activity(
                activities.run_analysis_pipeline,
                analyze,
                start_to_close_timeout=timedelta(seconds=4500),  # 75 минут на 5 стадий
                heartbeat_timeout=timedelta(seconds=300),
                # Прогон недетерминирован и дорог — слепой авторетрай сжёг бы
                # бюджет впустую. Повтор инициирует человек командой /analyze.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:
            # exc здесь — ActivityError с общим текстом Temporal-core
            # ("Activity task failed"); настоящая причина (наш RuntimeError
            # из run_analysis_pipeline) лежит в exc.cause. Без разворачивания
            # в GitHub-комментарий ушла бы бесполезная обёртка вместо
            # диагностики (например, «стадия ...: артефакт ... не создан»).
            reason = str(getattr(exc, "cause", None) or exc)
            await workflow.execute_activity(
                activities.publish_analysis_error,
                args=[analyze, reason[:500]],
                start_to_close_timeout=timedelta(seconds=60),
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
        except Exception as e:
            await workflow.execute_activity(
                activities.post_estimate_error,
                args=[req, stage, _failure_reason(e)],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
