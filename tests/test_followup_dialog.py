"""Диалог после ответа: реплика человека в припаркованный Issue получает ответ.

Найдено на живом прогоне (`poh-demo-checkout#42`): триаж закрыл консультацию
содержательным ответом, человек спросил в том же Issue «а как тогда устроен
Dataflow?» — сигнал `user_comment` доехал до воркфлоу (события 58 и 60 истории),
цикл проснулся, отбросил его как посторонний и встал в ту же парковку. Человек
ждал ответа, которого никто не собирался писать.

Проверяется то, что изменилось: реплика человека в парковке на нём самом —
вопрос к контуру, а не шум; повторная доставка того же комментария вебхуком
(она систематическая — событий-сигналов в истории ровно вдвое) отвечает один
раз; потолок кругов не даёт диалогу молотить моделью бесконечно.
"""

import uuid
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from shared import lifecycle
from shared.workflow_types import (
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)
from workflows import IssueAnalysis, IssueEstimation, IssueLifecycle

_answers: list[str] = []


# --- заглушки границ ---

@activity.defn(name="mark_awaiting")
async def awaiting_stub(repo: str, issue_number: int, waiting=None) -> None: ...


@activity.defn(name="prefilter_bot_and_security")
async def prefilter_ok(issue: IssueInput, origin_agent: bool = False):
    return None


@activity.defn(name="read_protocol_state")
async def protocol_default(repo: str, issue_number: int) -> ProtocolState:
    return ProtocolState()


@activity.defn(name="read_deadlines")
async def deadlines_stub() -> Deadlines:
    return Deadlines()


@activity.defn(name="read_deadlines")
async def deadlines_one_round() -> Deadlines:
    return Deadlines(followup_max_rounds=1)


@activity.defn(name="set_phase")
async def set_phase_stub(repo: str, issue_number: int, phase: str) -> None: ...


@activity.defn(name="intake_gate")
async def gate_sufficient(issue: IssueInput, thread: list[str]) -> GateResult:
    return GateResult(status="SUFFICIENT", content="")


@activity.defn(name="classify_issue")
async def classify_consultation(issue: IssueInput,
                                bft_on_triage: bool = False) -> ClassificationResult:
    return ClassificationResult(label="advisor:consultation", answer="вот ответ")


@activity.defn(name="duplicate_check")
async def duplicate_none(issue: IssueInput) -> DuplicateResult:
    return DuplicateResult(decision="unique", candidates=[])


@activity.defn(name="score_priority")
async def score_p1(issue: IssueInput, classification, dup) -> PriorityResult:
    return PriorityResult(wsjf=1.0, tier="P1", rationale="r")


@activity.defn(name="post_priority_comment")
async def post_priority(issue: IssueInput, priority, dup) -> None: ...


@activity.defn(name="post_error_label")
async def post_error(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="escalate_to_human")
async def escalate(issue: IssueInput, reason: str = "") -> None: ...


@activity.defn(name="answer_followup")
async def answer_followup_stub(issue: IssueInput, question: str) -> None:
    _answers.append(question)


ACTIVITIES = [awaiting_stub, prefilter_ok, protocol_default, set_phase_stub,
              gate_sufficient, classify_consultation, duplicate_none, score_p1,
              post_priority, post_error, escalate, answer_followup_stub]


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=42, title="Устройство Temporal",
                      body="b", author_login="u", author_type="User", interactive=True)


async def _await_phase(env, handle, expected: str, tries: int = 300) -> str:
    for _ in range(tries):
        if await handle.query(IssueLifecycle.phase) == expected:
            return expected
        await env.sleep(1)
    return await handle.query(IssueLifecycle.phase)


async def _await_answers(env, count: int, tries: int = 60) -> list[str]:
    for _ in range(tries):
        if len(_answers) >= count:
            break
        await env.sleep(1)
    return list(_answers)


@pytest.mark.timeout(90)
async def test_question_after_the_answer_gets_answered():
    """Ровно отказ с #42: Issue стоит в `answered`, человек задаёт следующий
    вопрос — контур отвечает, а не молчит."""
    _answers.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*ACTIVITIES, deadlines_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.user_comment,
                                args=["Окей, а как тогда устроен Dataflow?", 100])

            assert await _await_answers(env, 1) == ["Окей, а как тогда устроен Dataflow?"]
            assert await handle.query(IssueLifecycle.phase) == lifecycle.ANSWERED, (
                "ответ на реплику не должен двигать фазу — диалог идёт на месте"
            )
            assert (await handle.describe()).status.name == "RUNNING"


@pytest.mark.timeout(90)
async def test_the_same_comment_delivered_twice_is_answered_once():
    """Вебхук доставляет каждое событие дважды (в истории #42 сигналов ровно
    вдвое). Без ключа комментария человек получал бы два ответа на один вопрос."""
    _answers.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*ACTIVITIES, deadlines_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.user_comment, args=["вопрос", 100])
            await handle.signal(IssueLifecycle.user_comment, args=["вопрос", 100])

            assert await _await_answers(env, 2) == ["вопрос"]


@pytest.mark.timeout(90)
async def test_dialog_stops_at_the_round_limit():
    """Потолок кругов: диалог без конца — это счёт за модель без конца."""
    _answers.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*ACTIVITIES, deadlines_one_round]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.user_comment, args=["первый", 1])
            await _await_answers(env, 1)
            await handle.signal(IssueLifecycle.user_comment, args=["второй", 2])

            assert await _await_answers(env, 2) == ["первый"]
            assert (await handle.describe()).status.name == "RUNNING", (
                "исчерпанный потолок не должен ронять владельца состояния"
            )


@pytest.mark.timeout(90)
async def test_comment_without_an_id_still_gets_an_answer():
    """Прогоны прежнего вебхука шлют сигнал одним аргументом. Ключа у такой
    реплики нет — отвечаем всё равно: молчание хуже возможного повтора."""
    _answers.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=[*ACTIVITIES, deadlines_stub]):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _await_phase(env, handle, lifecycle.ANSWERED)

            await handle.signal(IssueLifecycle.user_comment, "без ключа")

            assert await _await_answers(env, 1) == ["без ключа"]


# --- сама активность: контекст разговора и публикация ---

class FakeGithub:
    def __init__(self, comments=None):
        self.comments = comments or []
        self.posted: list[str] = []
        self.labels: list[str] = []

    def list_comments(self, repo, issue_number, limit=50):
        return self.comments[:limit]

    def post_comment(self, repo, issue_number, body):
        self.posted.append(body)

    def add_label(self, repo, issue_number, label):
        self.labels.append(label)


@pytest.fixture
def acts(monkeypatch):
    import activities as module

    monkeypatch.setattr(module, "PROMPTS_DIR",
                        Path(__file__).resolve().parent.parent / "prompts")
    return module


def _comment(login, body, date="2026-08-19"):
    return {"user": {"login": login}, "body": body, "created_at": f"{date}T13:00:00Z"}


def test_the_answer_is_built_from_the_whole_conversation(acts, monkeypatch):
    """Реплика продолжает разговор: в модель обязаны уехать и прошлый ответ
    контура, и сам вопрос. Иначе ответ пойдёт по исходной заявке заново —
    ровно то, чем плох повторный `classify_issue`."""
    gh = FakeGithub([_comment("poh-harness-demo", "**Ситуация**: устройство Temporal"),
                     _comment("kibarik", "Окей, а как устроен Dataflow?")])
    monkeypatch.setattr(acts, "github_client", gh)
    seen: dict = {}

    def fake_extract(system, user_message, model_cls, model=None):
        seen["system"] = system
        seen["user"] = user_message
        return model_cls(answer="Dataflow устроен так: …")

    monkeypatch.setattr(acts.llm, "extract", fake_extract)

    acts.answer_followup(_issue(), "Окей, а как устроен Dataflow?")

    assert "**Ситуация**: устройство Temporal" in seen["user"], "прошлый ответ не уехал в модель"
    assert seen["user"].rstrip().endswith("Окей, а как устроен Dataflow?")
    assert gh.posted == ["Dataflow устроен так: …"]
    assert gh.labels == [], "ответ на реплику не трогает состояние Issue"


def test_an_empty_answer_is_not_published(acts, monkeypatch):
    """Пустой комментарий выглядит как ответ и закрывает вопрос ничем —
    пусть лучше активность упадёт и уедет в ретрай."""
    gh = FakeGithub()
    monkeypatch.setattr(acts, "github_client", gh)
    monkeypatch.setattr(acts.llm, "extract",
                        lambda system, user, model_cls, model=None: model_cls(answer="  "))

    with pytest.raises(RuntimeError):
        acts.answer_followup(_issue(), "вопрос")

    assert gh.posted == []


def test_a_broken_thread_does_not_cancel_the_answer(acts, monkeypatch):
    """Не прочитали переписку — отвечаем по заголовку и телу: молчание хуже."""
    class Broken(FakeGithub):
        def list_comments(self, repo, issue_number, limit=50):
            raise RuntimeError("502")

    gh = Broken()
    monkeypatch.setattr(acts, "github_client", gh)
    monkeypatch.setattr(acts.llm, "extract",
                        lambda system, user, model_cls, model=None: model_cls(answer="ответ"))

    acts.answer_followup(_issue(), "вопрос")

    assert gh.posted == ["ответ"]
