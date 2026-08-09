import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows import IssueLifecycle
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


@activity.defn(name="prefilter_bot_and_security")
async def stub_prefilter(issue): return None


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
            env.client, task_queue="tq", workflows=[IssueLifecycle],
            activities=[stub_prefilter, stub_gate_vague, stub_escalate, stub_protocol, deadlines_stub],
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
async def stub_prefilter_ok(issue: IssueInput): return None


@activity.defn(name="intake_gate")
async def stub_gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def stub_classify_feature(issue: IssueInput) -> ClassificationResult:
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
            env.client, task_queue="tq-research", workflows=[IssueLifecycle],
            activities=[stub_prefilter_ok, stub_gate_sufficient, stub_classify_feature,
                        stub_duplicate_none, stub_score_priority, stub_post_priority_comment,
                        stub_prepare, stub_stage_fails, stub_publish, stub_cleanup,
                        stub_publish_error, stub_mark_running, stub_finish_labels,
                        stub_protocol, deadlines_stub],
        ):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                           author_login="u", author_type="User", interactive=True),
                id=f"wf-{uuid.uuid4()}", task_queue="tq-research",
            )
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            # Вторая точка решения (build-me) иначе ждала бы сигнал вечно —
            # шлём что угодно, кроме "build-me", просто чтобы workflow дошёл до конца.
            await handle.signal(IssueLifecycle.human_decision, "skip")
            await handle.result()  # не должно поднять исключение — сбой пойман внутри

    assert _research_state["attempts"] == [1], "дорогой прогон не должен ретраиться"
    assert "boom-research-me" in _research_state["reason"]
    # Остановились на сорвавшейся стадии и не пошли дальше по цепочке.
    assert _research_state["stages"] == ["task", "concept"]
    assert "published" not in _research_state
    # Каталог прогона снимается на обоих путях.
    assert _research_state["cleaned"] is True
    # Прогон по метке research-me виден в выборке `label:run:*`, пока идёт, и
    # получает метку исхода, когда закончился, — как и запуск через run:analyze.
    assert _research_state["running"] == "analyze"
    assert _research_state["finished"] == ("analyze", False)


# --- analyze_requested: лейбл ставится ровно один раз ---
#
# Хендлер сигнала теперь не просто пишет поле — он вызывает activity
# mark_analyzing. Guard (self._analyze_labeled) обязан держаться даже если
# /analyze прилетает дважды (повторная команда, дубль webhook-доставки):
# лейбл должен появиться один раз, а не на каждый сигнал.

_analyze_signal_state = {"count": 0}


@activity.defn(name="mark_analyzing")
async def stub_mark_analyzing(repo: str, issue_number: int) -> None:
    _analyze_signal_state["count"] += 1


@pytest.mark.timeout(30)
async def test_analyze_requested_labels_only_once():
    """Два сигнала analyze_requested подряд обязаны дать ровно один вызов
    mark_analyzing: run() устанавливает self._issue первой же строкой (до
    какого-либо await), так что к моменту, когда обработчики сигналов
    получают своё исполнение, self._issue уже не None — guard проверяет
    именно однократность лейбла, а не гонку за его инициализацию."""
    _analyze_signal_state["count"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq-analyze-once", workflows=[IssueLifecycle],
            activities=[stub_prefilter_ok, stub_gate_sufficient, stub_classify_feature,
                        stub_duplicate_none, stub_score_priority, stub_post_priority_comment,
                        stub_mark_analyzing, stub_protocol, deadlines_stub],
        ):
            handle = await env.client.start_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=42, title="t", body="b",
                           author_login="u", author_type="User", interactive=True),
                id=f"wf-{uuid.uuid4()}", task_queue="tq-analyze-once",
            )
            await handle.signal(IssueLifecycle.analyze_requested, 111)
            await handle.signal(IssueLifecycle.analyze_requested, 222)
            # "no-match" не совпадает ни с research-me, ни с bug-me — run()
            # уходит в ветку else: return, не запуская тяжёлый пайплайн, так
            # что для завершения теста лишних стабов (пайплайна и т.п.) не нужно.
            await handle.signal(IssueLifecycle.human_decision, "no-match")
            await handle.result()

    assert _analyze_signal_state["count"] == 1, "повторный /analyze не должен плодить лейблы"


@pytest.mark.asyncio
async def test_analyze_requested_before_run_init_still_labels():
    """Сигнал в САМОЙ ПЕРВОЙ активации воркфлоу (start_signal) приходит раньше,
    чем run() выполнил `self._issue = issue` — Temporal применяет сигналы до
    создания задачи run(). Хендлер обязан ДОЖДАТЬСЯ инициализации через
    wait_condition, а не молча выйти по `self._issue is None`. Без фикса
    mark_analyzing не вызвался бы ни разу (count == 0)."""
    _analyze_signal_state["count"] = 0
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq-analyze-init", workflows=[IssueLifecycle],
            activities=[stub_prefilter_ok, stub_gate_sufficient, stub_classify_feature,
                        stub_duplicate_none, stub_score_priority, stub_post_priority_comment,
                        stub_mark_analyzing, stub_protocol, deadlines_stub],
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
            await handle.signal(IssueLifecycle.human_decision, "no-match")
            await handle.result()

    assert _analyze_signal_state["count"] == 1, "метка потеряна: сигнал до init не дождался self._issue"
