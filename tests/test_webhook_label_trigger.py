"""Метка как триггер команды: `run:<команда>` ведёт в тот же воркфлоу, что и
команда в комментарии, а метки исхода не запускают ничего."""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "test-secret"


class FakeHandle:
    """Ответ цикла на вопрос лаунчера «ведёшь ли ты агентов сам» (#37)."""

    def __init__(self, handles_agents: bool) -> None:
        self._handles_agents = handles_agents

    async def query(self, name, *args):
        assert name == "handles_agents", name
        return self._handles_agents


class FakeClient:
    def __init__(self, already_started: set[str] | None = None,
                 handles_agents: bool = True) -> None:
        self.started: list[dict] = []
        self._already = already_started or set()
        self._handles_agents = handles_agents

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle(self._handles_agents)

    def get_workflow_handle(self, wf_id):
        raise AssertionError("метка не должна слать голый signal")


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main

    from fastapi.testclient import TestClient

    def _build(already_started: set[str] | None = None, handles_agents: bool = True):
        fake = FakeClient(already_started, handles_agents)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig,
                 "Content-Type": "application/json"},
    )


def _labeled(label: str) -> dict:
    return {
        "action": "labeled",
        "label": {"name": label},
        "repository": {"full_name": "acme/widgets"},
        "issue": {
            "number": 7,
            "title": "Тестовая задача",
            "body": "тело",
            "user": {"login": "alice", "type": "User"},
        },
        "sender": {"login": "alice"},
    }


def test_run_analyze_goes_through_the_live_cycle(make_client):
    """Живой цикл ведёт аналитику сам: вебхук только доставляет ему команду,
    а дочерний прогон поднимает он (#37)."""
    fake, app_client = make_client()

    assert _post(app_client, _labeled("run:analyze")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["id"] == "issue-acme/widgets-7"
    assert call["start_signal"] == "analyze_requested"
    # Комментария-триггера нет: реагировать не на что, ack назовёт метку.
    assert call["start_signal_args"] == [None]


def test_run_analyze_falls_back_to_a_root_run_for_an_old_cycle(make_client):
    """Прогон прежнего поколения сигнала на запуск агента не понимает — команда
    была бы принята и потеряна. Для него лаунчер стартует самостоятельный
    прогон, как раньше."""
    fake, app_client = make_client(handles_agents=False)

    assert _post(app_client, _labeled("run:analyze")).status_code == 200

    analysis = next(c for c in fake.started if c["workflow"] == "IssueAnalysis")
    assert analysis["id"] == "analysis-acme/widgets-7"
    assert analysis["arg"].issue_number == 7
    assert analysis["arg"].title == "Тестовая задача"
    assert analysis["arg"].comment_id is None


def test_run_estimate_goes_through_the_live_cycle(make_client):
    fake, app_client = make_client()

    assert _post(app_client, _labeled("run:estimate")).status_code == 200

    assert len(fake.started) == 1
    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["start_signal"] == "estimate_requested"
    assert call["start_signal_args"] == [None]


def test_run_estimate_falls_back_to_a_root_run_for_an_old_cycle(make_client):
    fake, app_client = make_client(handles_agents=False)

    assert _post(app_client, _labeled("run:estimate")).status_code == 200

    call = next(c for c in fake.started if c["workflow"] == "IssueEstimation")
    assert call["id"] == "estimate-acme/widgets-7-label"
    assert call["arg"].comment_id is None


def test_outcome_labels_start_nothing(make_client):
    """Защита от петли: done:/failed: агент ставит себе сам, и они возвращаются
    событием issues.labeled. Запусти они прогон — он запускал бы сам себя."""
    fake, app_client = make_client()

    for label in ("done:analyze", "failed:analyze", "done:estimate", "failed:estimate",
                  "analyzing", "estimated", "priority:P1"):
        assert _post(app_client, _labeled(label)).status_code == 200

    assert fake.started == []


def test_repeated_delivery_does_not_start_a_second_run(make_client):
    """Повторная доставка того же вебхука (или метка, снятая и поставленная
    заново на идущем прогоне) не должна ни падать в 500, ни жечь второй прогон.

    Проверяем путь прежнего поколения: там прогон стартует сам вебхук, и занятый
    id — единственная защита. У живого цикла ту же роль играет его собственный
    guard (см. tests/test_workflow_batch.py)."""
    fake, app_client = make_client(already_started={"IssueAnalysis"},
                                   handles_agents=False)

    assert _post(app_client, _labeled("run:analyze")).status_code == 200
    assert not any(c["workflow"] == "IssueAnalysis" for c in fake.started)


def test_human_decision_labels_still_signal_with_start(make_client):
    """Обратная совместимость: research-me / bug-me / build-me работают как были."""
    fake, app_client = make_client()

    assert _post(app_client, _labeled("research-me")).status_code == 200

    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["start_signal"] == "human_decision"
    assert call["start_signal_args"] == ["research-me"]
