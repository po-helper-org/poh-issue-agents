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
    from shared.workflow_types import IssueInput

    import activities

MAX_CLARIFICATION_ROUNDS = 2


@workflow.defn(name="IssueLifecycle")
class IssueLifecycle:
    def __init__(self) -> None:
        self._signal_queue: asyncio.Queue[str] = asyncio.Queue()

    @workflow.signal
    async def human_decision(self, label: str) -> None:
        await self._signal_queue.put(label)

    @workflow.signal
    async def user_comment(self, text: str) -> None:
        await self._signal_queue.put(f"__comment__:{text}")

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
                start_to_close_timeout=timedelta(seconds=60),
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
                    start_to_close_timeout=timedelta(seconds=60),
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
                start_to_close_timeout=timedelta(seconds=90),
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
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=default_retry,
            )
            if dup.decision == "duplicate":
                return  # закрыт как дубликат внутри самой activity

            # --- Priority Scoring ---
            priority = await workflow.execute_activity(
                activities.score_priority,
                args=[issue, classification, dup],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=default_retry,
            )
            await workflow.execute_activity(
                activities.post_priority_comment,
                args=[issue, priority, dup],
                start_to_close_timeout=timedelta(seconds=30),
            )
        except Exception:
            await workflow.execute_activity(
                activities.post_error_label,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
            return

        # --- Точка решения человека №1: запускать ли тяжёлую стадию ---
        # Ждём research-me / bug-me. Никакого потолка по времени — issue
        # может неделями висеть в бэклоге с приоритетом, это нормально.
        decision = await self._wait_for_signal()

        if decision == "research-me" and classification.label == "advisor:feature-request":
            await workflow.execute_activity(
                activities.run_research_pipeline,
                issue,
                start_to_close_timeout=timedelta(minutes=60),
                retry_policy=RetryPolicy(maximum_attempts=1),  # не ретраим дорогой мультиагентный прогон вслепую
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
