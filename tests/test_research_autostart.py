"""Research autostart: от заявки до ready-for-dev без касания человека.

`RESEARCH_AUTOSTART` снимает парковку после system-requirements:Issue #106
Был баг: все Issue, прошедшие исследовательский путь, застревали в 
`phase:system-requirements` + `needs-human:triage`, несмотря на `RESEARCH_AUTOSTART=1`.

Проверяем, что:
1. С RESEARCH_AUTOSTART Issue доходит до ready-for-dev без парковки
2. С RESEARCH_AUTOSTART + DEVELOP_AUTOSTART Issue сразу уходит в разработку
3. Без RESEARCH_AUTOSTART поведение не меняется — Issue ждёт человека
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import activities as activities_module
from shared.workflow_types import (
    AnalyzeInput,
    ClassificationResult,
    Deadlines,
    DevelopPlan,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueDevelopment, IssueEstimation, IssueLifecycle

_calls: list[str] = []


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


# --- Activity stubs ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    _calls.append("awaiting")


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): 
    return None


@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    _calls.append(f"phase:{phase}")


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="intake_gate")
async def gate(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:feature-request", answer="ok")


@activity.defn(name="duplicate_check")
async def duplicate(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="none", best_match_number=None,
                           probability=0.0, reason="", context_branch=None)


@activity.defn(name="score_priority")
async def score(issue: IssueInput, c, d) -> PriorityResult:
    return PriorityResult(tier="P1", breakdown_markdown="разбор")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, p, d) -> None: 
    ...


@activity.defn(name="mark_command_running")
async def mark_running(repo: str, issue_number: int, command: str) -> None: 
    ...


@activity.defn(name="finish_command_labels")
async def finish(repo: str, issue_number: int, command: str, ok: bool) -> None: 
    ...


@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None: 
    ...


@activity.defn(name="prepare_workspace")
async def prepare(analyze: AnalyzeInput) -> None: 
    ...


@activity.defn(name="run_fnr_stage")
async def stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="publish_analysis")
async def publish(analyze: AnalyzeInput) -> str:
    return "research/issue-7"


@activity.defn(name="cleanup_workspace")
async def cleanup(analyze: AnalyzeInput) -> None: 
    ...


@activity.defn(name="publish_analysis_error")
async def publish_error(analyze: AnalyzeInput, reason: str) -> None: 
    ...


@activity.defn(name="mark_ready_for_dev")
async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None:
    _calls.append(f"ready-for-dev:{branch}")


@activity.defn(name="trigger_openhands_resolver")
async def develop(issue: IssueInput, root_issue: int | None = None,
                   branch: str | None = None) -> None:
    _calls.append("develop")


@activity.defn(name="decompose_issue")
async def decompose(issue: IssueInput, branch: str) -> dict:
    _calls.append("decompose")
    return {"items": [], "summary": ""}


@activity.defn(name="publish_decomposition")
async def publish_plan(issue: IssueInput, plan: dict, branch: str) -> list[int]:
    return []


@activity.defn(name="read_open_questions")
async def no_questions(repo: str, branch: str) -> list[str]:
    return []


@activity.defn(name="dev_begin")
async def child_develop_begin(issue: IssueInput) -> DevelopPlan:
    return DevelopPlan(mode="dispatch", branch="")


@activity.defn(name="dev_dispatch")
async def child_develop_dispatch(issue: IssueInput, branch: str) -> None:
    _calls.append("develop")


# Гейт критерия приёмки (задача 8): `_start_development` перед передачей в
# разработку читает критерий из тела Issue. Этот файл проверяет автостарт
# исследования, а не гейт — критерий уже есть, чтобы разработка (там, где до
# неё вообще доходит — `develop_autostart=True`) стартовала молча, без вопроса.
@activity.defn(name="read_acceptance_criterion")
async def criterion_present(issue: IssueInput) -> str:
    return "было 404; стало 405"


def _deadlines(research: bool, develop: bool = False):
    @activity.defn(name="read_deadlines")
    async def stub() -> Deadlines:
        return Deadlines(research_autostart=research, develop_autostart=develop)
    return stub


async def _run_until_phase(research_autostart: bool, develop_autostart: bool = False) -> tuple:
    """Гоняет цикл до готового состояния и возвращает фазу и вызовы."""
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueDevelopment,
                                     IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, protocol_default,
                                      _deadlines(research_autostart, develop_autostart), 
                                      gate, classify, duplicate,
                                      score, post_priority, mark_running, finish, ack,
                                      prepare, stage_ok, publish, cleanup, publish_error,
                                      ready, develop, decompose, publish_plan,
                                      phase_stub, no_questions, child_develop_begin,
                                      child_develop_dispatch, criterion_present]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Таймскип отключаем на время наблюдения: план ready-for-dev/develop
            # паркуется на 24ч (EXTERNAL_AGENT) сразу после нужного нам события,
            # а таймскип-клиент авто-продвигает время на КАЖДОМ query — гонка
            # между продвижением и самим запросом валит его RPCError'ом
            # "query deadline exceeded".
            with env.auto_time_skipping_disabled():
                # Ждём либо до парковки, либо до запуска разработки
                for _ in range(600):
                    # Развилась ли до готовности к разработке
                    if any(c.startswith("ready-for-dev") for c in _calls):
                        # Проверим, парковка ли это
                        if _calls[-1] == "awaiting":
                            # Это парковка — ждём человека
                            phase = await handle.query(IssueLifecycle.phase)
                            awaiting = await handle.query(IssueLifecycle.awaiting)
                            await handle.terminate()
                            return phase, awaiting, _calls.copy()
                        else:
                            # Не парковка — либо идёт дальше, либо ждёт в ready-for-dev
                            await asyncio.sleep(0.05)  # Даём время на следующий шаг
                            if "develop" in _calls:
                                # Ушла в разработку
                                phase = await handle.query(IssueLifecycle.phase)
                                await handle.terminate()
                                return phase, None, _calls.copy()
                            # Иначе ждём в ready-for-dev без парковки
                            phase = await handle.query(IssueLifecycle.phase)
                            await handle.terminate()
                            return phase, None, _calls.copy()

                    # Если ушла в разработку (полный автостарт)
                    if "develop" in _calls:
                        phase = await handle.query(IssueLifecycle.phase)
                        await handle.terminate()
                        return phase, None, _calls.copy()

                    await asyncio.sleep(0.05)

                # Таймаут — вернём текущее состояние
                phase = await handle.query(IssueLifecycle.phase)
                awaiting = await handle.query(IssueLifecycle.awaiting)
                await handle.terminate()
            return phase, awaiting, _calls.copy()


# --- Основные тесты ---

@pytest.mark.timeout(120)
async def test_research_autostart_reaches_ready_for_dev_without_parking():
    """Issue #106: С RESEARCH_AUTOSTART Issue доходит до ready-for-dev без вечной парковки.

    Был баг: Issue застревали в `phase:system-requirements` + `needs-human:triage`,
    несмотря на `RESEARCH_AUTOSTART=1` — решение "декомпозиция или сразу
    разработка" после аналитики принималось только человеком.

    После исправления Issue доходит до `ready-for-dev` без этой парковки. Там
    он ждёт ОТДЕЛЬНОГО решения — брать ли задачу в разработку (`build-me`),
    см. `_phase_await_build`, — это уже не #106, а следующая, штатная точка
    ожидания, снимаемая `DEVELOP_AUTOSTART`.
    """
    phase, awaiting, calls = await _run_until_phase(research_autostart=True, develop_autostart=False)

    # Должна дойти до ready-for-dev
    assert phase == "ready-for-dev", f"Ожидали ready-for-dev, получили {phase}"

    # Проверка по вызовам: система-requirements не паркуется сама по себе —
    # к моменту ready-for-dev не было НИ ОДНОЙ парковки до него.
    assert any(c.startswith("ready-for-dev") for c in calls), "Должна быть вызвана mark_ready_for_dev"

    ready_idx = next(i for i, c in enumerate(calls) if c.startswith("ready-for-dev"))
    calls_before_ready = calls[:ready_idx]

    assert "awaiting" not in calls_before_ready, (
        f"До ready-for-dev не должно быть парковки (#106). Вызовы: {calls_before_ready}")


@pytest.mark.timeout(120)
async def test_full_autostart_goes_directly_to_development():
    """С RESEARCH_AUTOSTART + DEVELOP_AUTOSTART Issue уходит сразу в разработку."""
    phase, awaiting, calls = await _run_until_phase(research_autostart=True, develop_autostart=True)
    
    # Должна уйти в разработку
    assert phase in ["in-development", "pr-open"], f"Ожидали in-development или pr-open, получили {phase}"
    
    # Не должна парковаться вообще
    assert awaiting is None, f"При полном автостарте не должно быть ожиданий, но awaiting={awaiting}"
    
    # Должен быть вызван develop
    assert "develop" in calls, "Должна быть вызвана разработка"
    
    # ready-for-dev всё равно ставится (сообщает состояние)
    assert any(c.startswith("ready-for-dev") for c in calls), "Должна быть вызвана mark_ready_for_dev"


@pytest.mark.timeout(120)
async def test_without_research_autostart_waits_for_human():
    """Без RESEARCH_AUTOSTART поведение не меняется — Issue ждёт человека.

    Без автостарта триаж по-прежнему паркуется в `classified` (см.
    `_phase_await_decision`): решение "аналитика или сразу разработка"
    принимает человек меткой `research-me`/`bug-me`. Дальше, до
    `ready-for-dev`, Issue без этой метки не доходит вовсе — это отдельная,
    более ранняя парковка, чем та, что #106 чинит на `system-requirements`.
    """
    phase, awaiting, calls = await _run_until_phase(research_autostart=False, develop_autostart=False)

    # Без автостарта дальше classified не уходит
    assert phase == "classified", f"Ожидали classified, получили {phase}"

    # И ДОЛЖНА парковаться с awaiting
    assert awaiting is not None, f"Без флага автостарта Issue должен ждать человека, но awaiting={awaiting}"
    assert "awaiting" in calls, f"Без автостарта должна быть парковка. Вызовы: {calls}"

    # ready-for-dev в этом сценарии не достигается вовсе
    assert not any(c.startswith("ready-for-dev") for c in calls), (
        f"Без автостарта Issue не должен доходить до ready-for-dev. Вызовы: {calls}")


# --- Декомпозиция ---

@pytest.mark.timeout(120)
async def test_research_autostart_with_decomposition_enabled():
    """С RESEARCH_AUTOSTART и декомпозицией Issue доходит до ready-for-dev без
    парковки НА system-requirements (#106) — декомпозиция не заменяет её
    отдельную, штатную парковку на build-me в ready-for-dev."""
    _calls.clear()

    @activity.defn(name="decompose_issue")
    async def decompose_with_items(issue: IssueInput, branch: str) -> dict:
        _calls.append("decompose")
        return {"items": [{"title": "подзадача 1"}], "summary": "план"}

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, protocol_default,
                                      _deadlines(True, False), gate, classify, duplicate,
                                      score, post_priority, mark_running, finish, ack,
                                      prepare, stage_ok, publish, cleanup, publish_error,
                                      ready, develop, decompose_with_items, publish_plan,
                                      phase_stub, no_questions]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)

            # Таймскип отключаем на время наблюдения — та же гонка запрос/автопродвижение,
            # что и в `_run_until_phase` (park на ready-for-dev начинается сразу).
            with env.auto_time_skipping_disabled():
                # Ждём до ready-for-dev
                for _ in range(200):
                    if any(c.startswith("ready-for-dev") for c in _calls):
                        phase = await handle.query(IssueLifecycle.phase)
                        await handle.terminate()

                        # Проверки
                        assert phase == "ready-for-dev", f"Ожидали ready-for-dev, получили {phase}"
                        assert "decompose" in _calls, "Должна быть вызвана декомпозиция"

                        # Парковки НЕ должно быть до ready-for-dev (#106) — то,
                        # что происходит НА ready-for-dev (ожидание build-me),
                        # это отдельная, штатная точка ожидания.
                        ready_idx = next(i for i, c in enumerate(_calls) if c.startswith("ready-for-dev"))
                        calls_before_ready = _calls[:ready_idx]
                        assert "awaiting" not in calls_before_ready, (
                            f"До ready-for-dev не должно быть парковки (#106). Вызовы: {calls_before_ready}")
                        return
                    await asyncio.sleep(0.05)
                
                await asyncio.sleep(0.05)
            
            await handle.terminate()
            pytest.fail("Не дождались ready-for-dev")


# --- Подзадачи плана ---

@pytest.mark.timeout(120)
async def test_plan_member_respects_parent_with_research_autostart():
    """Подзадача плана с RESEARCH_AUTOSTART не заводит свою разработку.
    
    Подзадача ждёт родителя, а не человека, и не должна парковаться.
    """
    _calls.clear()
    
    @activity.defn(name="read_protocol_state")
    async def subissue_state(repo: str, issue_number: int) -> ProtocolState:
        return ProtocolState(origin_agent=True, root_issue=13)
    
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, subissue_state,
                                      _deadlines(True, False), gate, classify, duplicate,
                                      score, post_priority, mark_running, finish, ack,
                                      prepare, stage_ok, publish, cleanup, publish_error,
                                      ready, develop, decompose, publish_plan, 
                                      phase_stub, no_questions]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            
            # Ждём до ready-for-dev
            for _ in range(200):
                if any(c.startswith("ready-for-dev") for c in _calls):
                    await asyncio.sleep(0.05)
                    phase = await handle.query(IssueLifecycle.phase)
                    awaiting = await handle.query(IssueLifecycle.awaiting)
                    await handle.terminate()
                    
                    # Подзадача доходит до ready-for-dev
                    assert phase == "ready-for-dev", f"Ожидали ready-for-dev, получили {phase}"
                    
                    # Не парковаться на человека, а ждать родителя
                    assert awaiting is not None, "Подзадача должна ждать родителя"
                    assert awaiting.kind == "external-agent", f"Подзадача должна ждать external-agent, а не {awaiting.kind}"
                    
                    # Ссылка на родительскую ветку
                    assert "ready-for-dev:research/issue-13" in _calls, "Подзадача должна ссылаться на ветку родителя"
                    
                    # Не должна декомпозироваться
                    assert "decompose" not in _calls, "Подзадача не должна разбиваться дальше"
                    
                    # Не должна начинать разработку
                    assert "develop" not in _calls, "Подзадача не должна начинать свою разработку"
                    return
                
                await asyncio.sleep(0.05)
            
            await handle.terminate()
            pytest.fail("Не дождались ready-for-dev")
