"""Точка передачи задачи разработчику (H1).

Единственное место, где контур сам отдаёт работу человеку. Проверяем, что взяв
задачу из выборки `label:ready-for-dev`, разработчик получает ответ на «что
известно и чего не хватает», а не набор меток, по которым надо догадываться.
"""

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
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


# --- сама activity ---

def _spy(monkeypatch, files: dict[str, str] | None = None):
    posted = {}
    monkeypatch.setattr(activities_module.github_client, "post_comment",
                        lambda repo, n, body: posted.update(body=body, repo=repo, n=n))
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: posted.setdefault("labels", []).append(label))
    monkeypatch.setattr(activities_module.github_client, "get_file",
                        lambda repo, path, ref: (files or {}).get(path))
    return posted


def test_checklist_answers_what_is_known(monkeypatch):
    posted = _spy(monkeypatch)

    activities_module.mark_ready_for_dev(_issue(), "P1", "research/issue-7")

    body = posted["body"]
    assert "P1" in body                          # приоритет посчитан
    assert "Дубли проверены" in body
    assert "research/issue-7" in body            # где лежат артефакты
    assert "system_requirements.md" in body      # с чего начать
    assert "Closes #7" in body                   # сквозной ключ цепочки


def test_label_makes_it_a_developer_queue(monkeypatch):
    posted = _spy(monkeypatch)

    activities_module.mark_ready_for_dev(_issue(), "P2", "research/issue-7")

    assert "ready-for-dev" in posted["labels"]


def test_open_questions_are_surfaced_from_artifacts(monkeypatch):
    """Незакрытые вопросы разработчик должен увидеть ДО того, как возьмёт
    задачу, а не наткнуться на них в середине реализации."""
    fnr = activities_module.FNR_DIR
    posted = _spy(monkeypatch, {
        f"{fnr}/system_requirements.md":
            "## Требования\n- [УТОЧНИТЬ] формат идентификатора заказа\nобычная строка\n",
        f"{fnr}/task.md": "- [УТОЧНИТЬ] нужен ли фолбэк на старый API\n",
    })

    activities_module.mark_ready_for_dev(_issue(), "P1", "research/issue-7")

    body = posted["body"]
    assert "формат идентификатора заказа" in body
    assert "нужен ли фолбэк на старый API" in body


def test_absence_of_open_questions_is_stated_explicitly(monkeypatch):
    """Пустой раздел читался бы как «забыли заполнить»."""
    fnr = activities_module.FNR_DIR
    posted = _spy(monkeypatch, {f"{fnr}/system_requirements.md": "всё определено\n"})

    activities_module.mark_ready_for_dev(_issue(), "P1", "research/issue-7")

    assert "не осталось" in posted["body"]


def test_open_questions_are_capped(monkeypatch):
    """Сотня маркеров превратила бы чеклист в стену текста."""
    fnr = activities_module.FNR_DIR
    many = "\n".join(f"- [УТОЧНИТЬ] вопрос {i}" for i in range(50))
    posted = _spy(monkeypatch, {f"{fnr}/task.md": many})

    activities_module.mark_ready_for_dev(_issue(), "P1", "research/issue-7")

    assert posted["body"].count("[УТОЧНИТЬ]") <= activities_module.MAX_OPEN_QUESTIONS


# --- место вызова в воркфлоу ---

_calls: list[str] = []


@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None:
    """Метка ожидания: инвариант проверяется в test_awaiting_wiring, здесь — шум."""


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False): return None

@activity.defn(name="set_phase")
async def phase_stub(repo: str, issue_number: int, phase: str) -> None:
    """Метка фазы: инвариант проверяется в test_lifecycle_phases, здесь — шум."""



@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


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
async def post_priority(issue: IssueInput, p, d) -> None: ...


@activity.defn(name="mark_command_running")
async def mark_running(repo: str, issue_number: int, command: str) -> None: ...


@activity.defn(name="finish_command_labels")
async def finish(repo: str, issue_number: int, command: str, ok: bool) -> None: ...


@activity.defn(name="ack_command")
async def ack(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="prepare_workspace")
async def prepare(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="publish_analysis")
async def publish(analyze: AnalyzeInput) -> str:
    return "research/issue-7"


@activity.defn(name="cleanup_workspace")
async def cleanup(analyze: AnalyzeInput) -> None: ...


@activity.defn(name="publish_analysis_error")
async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
    _calls.append("analysis_error")


@activity.defn(name="mark_ready_for_dev")
async def ready(issue: IssueInput, priority_tier: str, branch: str) -> None:
    _calls.append(f"ready:{priority_tier}:{branch}")


@activity.defn(name="run_fnr_stage")
async def stage_ok(analyze: AnalyzeInput, stage_name: str) -> dict:
    return {"stage": stage_name, "artifact": None, "bytes": 0}


@activity.defn(name="run_fnr_stage")
async def stage_fails(analyze: AnalyzeInput, stage_name: str) -> dict:
    raise RuntimeError("стадия concept сорвалась")


async def _run_research(stage_activity) -> None:
    _calls.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[awaiting_stub, prefilter_ok, protocol_default, deadlines_stub, gate,
                                      classify, duplicate, score, post_priority,
                                      mark_running, finish, ack, prepare, stage_activity,
                                      publish, cleanup, publish_error, ready, phase_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await handle.signal(IssueLifecycle.human_decision, "research-me")
            await handle.signal(IssueLifecycle.human_decision, "no-build")
            await handle.result()


@pytest.mark.timeout(90)
async def test_handoff_happens_after_a_successful_analysis():
    await _run_research(stage_ok)

    assert "ready:P1:research/issue-7" in _calls


@pytest.mark.timeout(90)
async def test_no_handoff_when_analysis_failed():
    """Без артефактов передавать нечего: `ready-for-dev` на сорвавшемся прогоне
    отправил бы разработчика к несуществующей ветке."""
    await _run_research(stage_fails)

    assert "analysis_error" in _calls
    assert not any(c.startswith("ready:") for c in _calls)
