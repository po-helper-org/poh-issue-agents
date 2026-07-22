"""Проверяется сборка контекста: что попадает в модель, а что отсекается,
и как срабатывают лимиты. Сетевые вызовы подменяются целиком."""

import pytest

import activities
from shared.workflow_types import EstimateRequest, EstimateResult, EstimationContext


class FakeGitHub:
    def __init__(self, issue=None, comments=None, branches=(), files=None):
        self.issue = issue or {"title": "Заголовок", "body": "Описание", "labels": []}
        self.comments = comments or []
        self.branches = set(branches)
        self.files = files or {}
        self.reactions = []
        self.posted = []
        self.labels = []

    def get_issue(self, repo, number):
        return self.issue

    def list_comments(self, repo, number, limit=50):
        return self.comments[:limit]

    def branch_exists(self, repo, branch):
        return branch in self.branches

    def get_file(self, repo, path, ref):
        return self.files.get(path)

    def add_reaction(self, repo, comment_id, content="eyes"):
        self.reactions.append((comment_id, content))

    def post_comment(self, repo, number, body):
        self.posted.append(body)

    def add_label(self, repo, number, label):
        self.labels.append(label)


def comment(body, user_type="User"):
    return {"body": body, "user": {"type": user_type}}


@pytest.fixture
def fake(monkeypatch):
    stub = FakeGitHub()
    monkeypatch.setattr(activities, "github_client", stub)
    return stub


REQ = EstimateRequest(repo="o/r", issue_number=7, comment_id=555)


async def test_ack_puts_eyes_on_the_command_comment(fake):
    activities.ack_estimate_command(REQ)
    assert fake.reactions == [(555, "eyes")]


async def test_context_carries_title_body_and_labels(fake):
    fake.issue = {"title": "Т", "body": "О", "labels": [{"name": "advisor:bug"}]}
    context = activities.collect_estimation_context(REQ)
    assert context.title == "Т"
    assert context.body == "О"
    assert context.labels == ["advisor:bug"]


async def test_bot_comments_and_commands_are_excluded_from_the_thread(fake):
    fake.comments = [
        comment("живой контекст"),
        comment("прошлая оценка", user_type="Bot"),
        comment("/estimate"),
    ]
    context = activities.collect_estimation_context(REQ)
    assert context.thread == ["живой контекст"]


async def test_thread_is_capped_by_character_budget(fake, monkeypatch):
    monkeypatch.setattr(activities, "MAX_THREAD_CHARS", 10)
    fake.comments = [comment("12345"), comment("67890"), comment("перебор")]
    context = activities.collect_estimation_context(REQ)
    assert context.thread == ["12345", "67890"]
    assert context.truncated is True


async def test_research_branch_artifacts_are_pulled(fake):
    fake.branches = {"research/issue-7"}
    fake.files = {"docs/bft/issue-7-blueprint.md": "план"}
    context = activities.collect_estimation_context(REQ)
    assert context.branch == "research/issue-7"
    assert context.artifacts == {"docs/bft/issue-7-blueprint.md": "план"}


async def test_bug_branch_is_used_when_there_is_no_research_branch(fake):
    fake.branches = {"bug/issue-7"}
    fake.files = {"docs/bugs/issue-7-diagnosis.md": "диагноз"}
    context = activities.collect_estimation_context(REQ)
    assert context.branch == "bug/issue-7"
    assert "docs/bugs/issue-7-diagnosis.md" in context.artifacts


async def test_no_branch_means_no_artifacts_and_is_not_an_error(fake):
    context = activities.collect_estimation_context(REQ)
    assert context.branch is None
    assert context.artifacts == {}


async def test_oversized_artifact_is_truncated(fake, monkeypatch):
    monkeypatch.setattr(activities, "MAX_ARTIFACT_CHARS", 5)
    fake.branches = {"research/issue-7"}
    fake.files = {"docs/bft/issue-7-blueprint.md": "1234567890"}
    context = activities.collect_estimation_context(REQ)
    assert context.artifacts["docs/bft/issue-7-blueprint.md"] == "12345"
    assert context.truncated is True


def _context(**overrides) -> EstimationContext:
    base = dict(title="Т", body="О", labels=[], thread=[], branch=None,
                artifacts={}, truncated=False)
    base.update(overrides)
    return EstimationContext(**base)


FACTS_PAYLOAD = {
    "work_type": "new_development",
    "artifact_type": "new_module",
    "scaffolding_hours": 4.0,
    "work_units": [{"name": "эндпоинт", "hours": 4.0, "rationale": "маршрут"}],
    "integration_hours": 2.0,
    "fp_count": 2.0,
    "fp_hours_per_point": 5.5,
    "data_sufficiency": "complete",
    "has_acceptance_criteria": True,
    "has_dependencies_listed": True,
    "has_api_contract": True,
    "has_data_class": True,
    "risks": [],
    "open_questions": [],
    "reasoning": "по маршрутам",
}


async def test_compute_activity_returns_rendered_markdown(fake, monkeypatch, rules):
    monkeypatch.setattr(activities.estimation, "load_rules", lambda *a, **k: rules)
    result = activities.compute_estimate(FACTS_PAYLOAD, _context())
    assert result.stopped is False
    assert "## Оценка задачи" in result.markdown


async def test_posting_adds_the_estimated_label(fake):
    activities.post_estimate_comment(REQ, EstimateResult(markdown="текст", stopped=False))
    assert fake.posted == ["текст"]
    assert fake.labels == ["estimated"]


async def test_stopped_estimate_is_posted_without_the_label(fake):
    activities.post_estimate_comment(REQ, EstimateResult(markdown="стоп", stopped=True))
    assert fake.posted == ["стоп"]
    assert fake.labels == []


async def test_error_reports_the_stage_and_reacts(fake):
    activities.post_estimate_error(REQ, "сбор контекста")
    assert "сбор контекста" in fake.posted[0]
    assert fake.reactions == [(555, "confused")]
