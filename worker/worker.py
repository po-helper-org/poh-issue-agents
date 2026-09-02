import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import UnsandboxedWorkflowRunner, Worker

# Surface INFO logs — notably github_client's [DRY_RUN] lines, which are the
# operator's audit of what the pipeline WOULD do before going live. Without
# this the root logger defaults to WARNING and swallows them.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,  # temporalio configures the root logger on import; reset it
)

import activities
import consolidation_activities as ca
import delivery_bridge
import howtodemo_bridge
from consolidation_workflow import ConsolidationWorkflow
from shared import sentry_setup
from shared.temporal_client import connect_temporal
from workflows import (
    CommentAck,
    IssueAnalysis,
    IssueBft,
    IssueDevelopment,
    IssueEstimation,
    IssueLifecycle,
    IssuePrFix,
    IssueResearch,
    OrphanAgentEvent,
    WebhookAudit,
)

sentry_setup.configure("worker")  # no-op без SENTRY_DSN

# Список-манифест шести-восьми шагов разработки: test_develop_child.py сверяет
# его целиком с активностями worker'а, и незарегистрированный шаг обнаружится
# здесь, а не на живом прогоне. В конструктор Worker ниже эти же активности
# идут явными именами (`activities.dev_*`), а не звёздочкой от этого списка —
# test_worker_wiring.py находит использованные воркфлоу активности разбором
# AST и умеет узнавать только `activities.<имя>` прямо в списке elts.
DEVELOP_ACTIVITIES = [
    activities.dev_begin,
    activities.dev_dispatch,
    activities.dev_prepare,
    activities.dev_announce,
    # Не `dev_*`: план работ навыком writing-plans, а не шаг, рождённый
    # разрезанием монолитной активности (см. `activities.build_mvp_plan`).
    activities.build_mvp_plan,
    activities.dev_run_agent,
    activities.dev_followups,
    activities.dev_tests,
    activities.dev_publish,
    activities.dev_publish_partial,
    activities.capture_episode,
]


_log = logging.getLogger("worker")


def _delivery_worker(client) -> Worker | None:
    """Воркер Delivery-Agent — отдельная очередь и отдельный пул потоков.

    Отдельная очередь, а не общая: один шаг релиза держит активность минутами
    (мерж, выкатка, проверки живого сервиса), и на общем пуле из трёх слотов
    релиз вытеснял бы триаж Issue. Разводка по очередям решает это без
    приоритетов и без настроек.

    Нет пакета — не отказ старта: контур обязан подниматься и без Delivery-Agent,
    иначе несобравшийся модуль-сосед останавливает всю обработку Issue.
    """
    try:
        from poh_delivery import integration as delivery
    except ImportError:
        _log.warning("poh_delivery не установлен — релизы отключены, остальной контур работает")
        return None

    delivery_bridge.install()
    return Worker(
        client,
        task_queue=delivery.TASK_QUEUE,
        workflows=delivery.WORKFLOWS,
        activities=delivery.ACTIVITIES,
        workflow_runner=UnsandboxedWorkflowRunner(),
        activity_executor=ThreadPoolExecutor(max_workers=2),
        max_concurrent_activities=2,
        debug_mode=True,
    )


def _howtodemo_worker(client) -> Worker | None:
    """Воркер HowToDemo-Agent — отдельная очередь и отдельный пул потоков.

    Отдельная очередь по той же причине, что у релиза: один прогон приёмки
    держит активность десятками минут (подъём стенда, проходка по шагам,
    сбор улик), и на общем пуле из трёх слотов он вытеснял бы триаж Issue.

    Нет пакета — не отказ старта: контур обязан подниматься и без приёмщика.

    Слот ровно один: приёмка поднимает контейнер со стендом, а на хосте
    свободной памяти меньше гигабайта и нет свопа — две одновременные приёмки
    выбрали бы её вместе с чужим прод-сервисом, живущим рядом.
    """
    try:
        from poh_howtodemo import integration as howtodemo
    except ImportError:
        _log.warning("poh_howtodemo не установлен — приёмка отключена, "
                     "остальной контур работает")
        return None

    howtodemo_bridge.install()
    return Worker(
        client,
        task_queue=howtodemo.TASK_QUEUE,
        workflows=howtodemo.WORKFLOWS,
        activities=howtodemo.ACTIVITIES,
        workflow_runner=UnsandboxedWorkflowRunner(),
        activity_executor=ThreadPoolExecutor(max_workers=1),
        max_concurrent_activities=1,
        debug_mode=True,
    )


async def main() -> None:
    client = await connect_temporal()
    worker = Worker(
        client,
        task_queue="issue-lifecycle",
        workflows=[IssueLifecycle, IssueAnalysis, IssueBft, IssueDevelopment,
                   IssueEstimation, IssuePrFix, IssueResearch, ConsolidationWorkflow, WebhookAudit,
                   OrphanAgentEvent, CommentAck],
        activities=[
            activities.prefilter_bot_and_security,
            activities.read_protocol_state,
            activities.read_deadlines,
            activities.set_phase,
            activities.mark_awaiting,
            activities.mark_ready_for_dev,
            activities.read_open_questions,
            activities.ask_open_questions,
            activities.post_agents_off_notice,
            activities.intake_gate,
            activities.post_clarifying_question,
            activities.close_as_spam,
            activities.escalate_to_human,
            activities.ask_question,
            activities.answer_question,
            activities.propose_acceptance_options,
            activities.read_acceptance_criterion,
            activities.read_open_question_id,
            activities.close_answered_by_body_edit,
            activities.report_criterion_gate_stall,
            activities.report_ask_question_gate_failure,
            activities.report_answer_question_failure,
            activities.report_question_repoint_failure,
            activities.report_question_close_failure,
            activities.post_error_label,
            activities.ack_comment_seen,
            activities.post_followup_reply,
            activities.mark_analyzing,
            activities.mark_command_running,
            activities.finish_command_labels,
            activities.decompose_issue,
            activities.publish_decomposition,
            activities.run_pr_fix_round,
            activities.finish_pr_fixing,
            activities.pr_is_merged,
            activities.classify_issue,
            activities.interpret_user_comment,
            activities.answer_followup,
            activities.ack_bft_command,
            activities.run_bft_fast,
            activities.prepare_bft_workspace,
            activities.run_bft_stage,
            activities.publish_bft_deep,
            activities.cleanup_bft_workspace,
            activities.publish_bft_partial,
            activities.publish_bft_error,
            activities.duplicate_check,
            activities.read_issue_labels,
            activities.score_priority,
            activities.post_priority_comment,
            activities.prepare_workspace,
            activities.run_fnr_stage,
            activities.publish_analysis,
            activities.cleanup_workspace,
            activities.ack_command,
            activities.publish_analysis_partial,
            activities.publish_analysis_error,
            activities.run_bug_pipeline,
            activities.trigger_openhands_resolver,
            # DEVELOP_ACTIVITIES не разворачиваем звёздочкой: test_worker_wiring.py
            # ищет использованные воркфлоу активности разбором AST и видит только
            # `activities.<имя>` прямо в списке — `*DEVELOP_ACTIVITIES` для него
            # непрозрачен, и шаги IssueDevelopment ушли бы из-под проверки.
            activities.dev_begin,
            activities.dev_dispatch,
            activities.dev_prepare,
            activities.dev_announce,
            activities.build_mvp_plan,
            activities.dev_run_agent,
            activities.dev_followups,
            activities.dev_empty_run_reason,
            activities.dev_tests,
            activities.dev_publish,
            activities.dev_publish_partial,
            activities.capture_episode,
            activities.ack_estimate_command,
            activities.collect_estimation_context,
            activities.extract_estimation_facts,
            activities.compute_estimate,
            activities.post_estimate_comment,
            activities.post_estimate_error,
            ca.fetch_open_issues,
            ca.extract_solution_profile,
            ca.derive_taxonomy,
            ca.assign_zone,
            ca.slice_zone,
            ca.synthesize_unifying_issue,
            ca.write_consolidation_pr,
            # Активности Harness, которые зовёт воркфлоу релиза: конфликт в
            # ветке и круг правок по ревью ведёт тот же агент разработки, что
            # пишет код по задачам.
            delivery_bridge.fix_conflicts,
            delivery_bridge.review_round,
            delivery_bridge.review_exhausted,
        ],
        # Our workflow code is trusted first-party code; unsandboxed avoids the
        # per-task re-import of heavy modules (instructor/openai/pydantic).
        workflow_runner=UnsandboxedWorkflowRunner(),
        # The activities are now SYNC defs doing BLOCKING LLM/HTTP + CPU-heavy
        # pydantic parsing. Running them in a ThreadPoolExecutor keeps the
        # blocking work OFF the workflow event-loop thread, so under a backfill
        # burst the loop stays free to process workflow tasks (no task-timeout
        # churn) and up to `max_workers` activities run truly concurrently.
        activity_executor=ThreadPoolExecutor(max_workers=3),
        # debug_mode still disables the deadlock detector (TMPRL1101); with the
        # blocking work offloaded it should rarely trigger, but it is safe for
        # trusted, deterministic first-party workflows.
        debug_mode=True,
        # Capped at 3: the z.ai backend rate-limits (HTTP 429) under an 8-wide
        # fan-out, and Instructor's own retries multiply the request rate. 3
        # concurrent activities keeps the backfill under the limit while still
        # draining meaningfully faster than serial.
        max_concurrent_activities=3,
    )
    # Модули-соседи необязательны поштучно: несобравшийся сосед не должен
    # останавливать обработку Issue, поэтому каждый отсутствующий просто не
    # попадает в список очередей.
    side = [w for w in (_delivery_worker(client), _howtodemo_worker(client))
            if w is not None]
    queues = ", ".join(f"'{w.task_queue}'" for w in [worker, *side])
    print(f"Worker started, listening on task queues {queues}")
    await asyncio.gather(worker.run(), *(w.run() for w in side))


if __name__ == "__main__":
    asyncio.run(main())
