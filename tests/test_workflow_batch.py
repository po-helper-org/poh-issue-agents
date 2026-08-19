import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle
from shared.workflow_types import (
    AnalyzeInput,
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)

_state = {}


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def stub_prefilter(issue, origin_agent: bool = False): return None

@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    """Метка фазы: инвариант проверяется в test_lifecycle_phases, здесь — шум."""



@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    """Сроки по умолчанию: тесты проверяют маршруты, а не сами таймеры."""
    return Deadlines()


@activity.defn(name="read_protocol_state")
async def stub_protocol(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="intake_gate")
async def stub_gate_vague(issue, thread):
    return GateResult(status="VAGUE", content="need details")


@activity.defn(name="escalate_to_human")
async def stub_escalate(issue):
    _state["escalated"] = True


@pytest.mark.timeout(30)
async def test_batch_vague_escalates_without_hanging():
    _state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq", workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
            activities=[awaiting_stub, stub_prefilter, stub_gate_vague, stub_escalate, stub_protocol, deadlines_stub, phase_stub],
        ):
            await env.client.execute_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                           author_login="u", author_type="User", interactive=False),
                id=f"wf-{uuid.uuid4()}", task_queue="tq",
            )
    assert _state.get("escalated") is True


# --- research-me: сбой тяжёлого пайплайна не должен молча ронять IssueLifecycle ---
#
# До фикса ветка research-me звала run_analysis_pipeline без try/except: сбой
# валил бы весь workflow с нулевой видимостью в GitHub — в отличие от команды
# /analyze (IssueAnalysis.run), у которой сбой всегда уходит в
# publish_analysis_error. Прогоняем весь IssueLifecycle от префильтра до
# второй точки решения человека, чтобы доказать: после фикса гарантия та же.

_research_state = {}


@activity.defn(name="prefilter_bot_and_security")
async def stub_prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None


@activity.defn(name="intake_gate")
async def stub_gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def stub_classify_feature(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def stub_duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                            probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def stub_score_priority(issue: IssueInput, classification: ClassificationResult,
                               dup: DuplicateResult) -> PriorityResult:
    return PriorityResult(tier="P2", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def stub_post_priority_comment(issue: IssueInput, priority: PriorityResult,
                                      dup: DuplicateResult) -> None:
    pass


@activity.defn(name="ack_command")
async def stub_ack(analyze: AnalyzeInput) -> None:
    _research_state["acked"] = analyze.trigger


@activity.defn(name="prepare_workspace")
async def stub_prepare(analyze: AnalyzeInput) -> None:
    _research_state["prepared"] = True


@activity.defn(name="run_fnr_stage")
async def stub_stage_fails(analyze: AnalyzeInput, stage_name: str) -> dict:
    """Ветка research-me идёт теми же пер-стадийными activity, что и /analyze:
    падение конкретной стадии обязано называть себя, а не прятаться под общим
    потолком монолита."""
    _research_state.setdefault("stages", []).append(stage_name)
    if stage_name == "concept":
        _research_state.setdefault("attempts", []).append(1)
        raise RuntimeError("boom-research-me")
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="publish_analysis")
async def stub_publish(analyze: AnalyzeInput) -> str:
    _research_state["published"] = True
    return "research/issue-7"


@activity.defn(name="cleanup_workspace")
async def stub_cleanup(analyze: AnalyzeInput) -> None:
    _research_state["cleaned"] = True


@activity.defn(name="publish_analysis_error")
async def stub_publish_error(analyze: AnalyzeInput, reason: str) -> None:
    _research_state["reason"] = reason


@activity.defn(name="mark_command_running")
async def stub_mark_running(repo: str, issue_number: int, command: str) -> None:
    _research_state["running"] = command


@activity.defn(name="finish_command_labels")
async def stub_finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:
    _research_state["finished"] = (command, ok)


@pytest.mark.timeout(30)
async def test_research_me_label_surfaces_pipeline_failure():
    """label-триггер research-me обязан давать ту же гарантию, что и команда
    /analyze: сбой дорогого прогона обязан дойти до GitHub через
    publish_analysis_error, а не тихо уронить весь IssueLifecycle."""
    _research_state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq-research", workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
            activities=[awaiting_stub, stub_prefilter_ok, stub_gate_sufficient, stub_classify_feature,
                        stub_duplicate_none, stub_score_priority, stub_post_priority_comment,
                        stub_ack, stub_prepare, stub_stage_fails, stub_publish, stub_cleanup,
                        stub_publish_error, stub_mark_running, stub_finish_labels,
                        stub_protocol, deadlines_stub, phase_stub],
        ):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                           author_login="u", author_type="User", interactive=True),
                id=f"wf-{uuid.uuid4()}", task_queue="tq-research",
            )
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            # Сбой пойман внутри: цикл не падает, а уходит в фазу `failed`,
            # из которой человек может перезапустить обработку (#36).
            for _ in range(300):
                if await handle.query(IssueLifecycle.phase) == "failed":
                    break
                await env.sleep(1)
            assert await handle.query(IssueLifecycle.phase) == "failed"

    assert _research_state["attempts"] == [1], "дорогой прогон не должен ретраиться"
    assert "boom-research-me" in _research_state["reason"]
    # Остановились на сорвавшейся стадии и не пошли дальше по цепочке.
    assert _research_state["stages"] == ["task", "concept"]
    assert "published" not in _research_state
    # Каталог прогона снимается на обоих путях.
    assert _research_state["cleaned"] is True
    # Прогон по метке research-me виден в выборке `label:run:*`, пока идёт, и
    # получает метку исхода, когда закончился, — как и запуск через run:analyze.
    # Метку ставит сам дочерний прогон (ack_command), и называет он её тем
    # триггером, который был на самом деле.
    assert _research_state["acked"] == "research-me"
    assert _research_state["finished"] == ("analyze", False)


# --- analyze_requested: команда не теряется и не плодит дорогих прогонов ---
#
# Раньше хендлер вешал косметическую метку, а работу нёс независимый воркфлоу
# из вебхука. Теперь аналитику ведёт сам цикл дочерним прогоном (#37), поэтому
# проверять надо не число меток, а число прогонов: id фиксирован
# (`analysis-<repo>-<n>`), и повторная команда обязана упереться в него.

_analyze_state: dict = {}


@activity.defn(name="ack_command")
async def stub_ack_once(analyze: AnalyzeInput) -> None:
    _analyze_state.setdefault("runs", []).append(analyze.comment_id)


@activity.defn(name="run_fnr_stage")
async def stub_stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="prepare_workspace")
async def stub_prepare_ok(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="publish_analysis")
async def stub_publish_ok(analyze: AnalyzeInput) -> str:
    return "research/issue-42"


@activity.defn(name="cleanup_workspace")
async def stub_cleanup_ok(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="mark_ready_for_dev")
async def stub_ready(issue: IssueInput, priority_tier: str, branch: str) -> None:
    _analyze_state["handed-off"] = True


@activity.defn(name="escalate_to_human")
async def stub_escalate_any(issue: IssueInput, reason: str = "") -> None:
    """Цикл больше не завершается на несовпавшем лейбле — он ждёт до срока и
    эскалирует. Заглушка нужна всем прогонам, доходящим до дедлайна."""


ANALYZE_STUBS = [stub_prefilter_ok, stub_gate_sufficient, stub_classify_feature,
                 stub_duplicate_none, stub_score_priority, stub_post_priority_comment,
                 stub_protocol, deadlines_stub, phase_stub, stub_escalate_any,
                 stub_ack_once, stub_prepare_ok, stub_stage_ok, stub_publish_ok,
                 stub_cleanup_ok, stub_finish_labels, stub_publish_error, stub_ready]


async def _await_phase(env, handle, expected: str) -> str:
    for _ in range(300):
        if await handle.query(IssueLifecycle.phase) == expected:
            break
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


@pytest.mark.timeout(60)
async def test_repeated_analyze_does_not_start_a_second_expensive_run():
    """Два `/analyze` подряд (повторная команда, дубль webhook-доставки) — это
    один прогон, а не два: второй упирается в занятый id."""
    _analyze_state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq-analyze-once",
            workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
            activities=[*ANALYZE_STUBS, awaiting_stub],
        ):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=42, title="t", body="b",
                           author_login="u", author_type="User", interactive=True),
                id=f"wf-{uuid.uuid4()}", task_queue="tq-analyze-once",
            )
            await handle.signal(IssueLifecycle.analyze_requested, 111)
            await handle.signal(IssueLifecycle.analyze_requested, 222)

            assert await _await_phase(env, handle, "ready-for-dev") == "ready-for-dev"

    assert _analyze_state["runs"] == [111], "повторная команда завела второй дорогой прогон"


@pytest.mark.timeout(60)
async def test_analyze_requested_in_the_first_activation_is_not_lost():
    """Сигнал в САМОЙ ПЕРВОЙ активации воркфлоу (start_signal) приходит раньше,
    чем run() выполнил `self._issue = issue` — Temporal применяет сигналы до
    создания задачи run(). Хендлер обязан ДОЖДАТЬСЯ инициализации через
    wait_condition, а не выйти молча по `self._issue is None`: без этого
    команда пропадала бы бесследно."""
    _analyze_state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq-analyze-init",
            workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
            activities=[*ANALYZE_STUBS, awaiting_stub],
        ):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=42, title="t", body="b",
                           author_login="u", author_type="User", interactive=True),
                id=f"wf-{uuid.uuid4()}", task_queue="tq-analyze-init",
                # доставляет analyze_requested в первой активации — вместе со
                # стартом, раньше первой строки run()
                start_signal="analyze_requested", start_signal_args=[111],
            )

            assert await _await_phase(env, handle, "ready-for-dev") == "ready-for-dev"

    assert _analyze_state["runs"] == [111], "команда потеряна: сигнал до init не дождался self._issue"
    assert _analyze_state.get("handed-off") is True
