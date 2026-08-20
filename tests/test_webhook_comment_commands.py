"""Путь issue_comment в вебхуке: на нём держатся обе команды, а тестов на
уровне HTTP у него не было вовсе (покрытие webhook/main.py — 72%)."""

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
    def __init__(self, sink: list, fail: bool = False,
                 handles_agents: bool = True) -> None:
        self._sink = sink
        self._fail = fail
        self._handles_agents = handles_agents

    async def signal(self, name, *args, **kwargs):
        if self._fail:
            raise RuntimeError("workflow уже завершён")
        # Реальный хендл принимает и одиночный аргумент, и `args=[...]`: реплика
        # человека едет вторым способом, вместе с ключом комментария.
        self._sink.append((name, tuple(kwargs.get("args", args))))

    async def query(self, name, *args):
        """Ответ цикла на вопрос лаунчера «ведёшь ли ты агентов сам» (#37)."""
        assert name == "handles_agents", name
        return self._handles_agents


class FakeClient:
    def __init__(self, already: set[str] | None = None, signal_fails: bool = False,
                 handles_agents: bool = True) -> None:
        self.started: list[dict] = []
        self.signals: list = []
        self._already = already or set()
        self._signal_fails = signal_fails
        self._handles_agents = handles_agents

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle(self.signals, handles_agents=self._handles_agents)

    def get_workflow_handle(self, wf_id):
        self.signals.append(wf_id)
        return FakeHandle(self.signals, fail=self._signal_fails,
                          handles_agents=self._handles_agents)


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)

    import main

    from fastapi.testclient import TestClient

    def _build(**kwargs):
        fake = FakeClient(**kwargs)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _post(app_client, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return app_client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "issue_comment", "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": "dlv-1", "Content-Type": "application/json"})


def _comment(body: str, user_type: str = "User", comment_id: int = 555) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "acme/widgets"},
        "issue": {"number": 7, "title": "Тестовая задача", "body": "тело",
                  "user": {"login": "alice", "type": "User"}},
        "comment": {"id": comment_id, "body": body,
                    "user": {"login": "alice", "type": user_type}},
        "sender": {"login": "alice"},
    }


def test_estimate_command_goes_through_the_live_cycle(webhook):
    """Живой цикл поднимает оценку дочерним прогоном сам — вебхук только
    доставляет ему команду вместе с комментарием-триггером (#37)."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("/estimate")).status_code == 200

    # Подтверждение приёма идёт ПЕРВЫМ, до разбора команды.
    assert [c["workflow"] for c in fake.started] == ["CommentAck", "IssueLifecycle"]
    call = fake.started[1]
    assert call["id"] == "issue-acme/widgets-7"
    assert call["start_signal"] == "estimate_requested"
    assert call["start_signal_args"] == [555]


def test_estimate_falls_back_to_a_root_run_for_an_old_cycle(webhook):
    fake, app_client = webhook(handles_agents=False)

    assert _post(app_client, _comment("/estimate")).status_code == 200

    call = next(c for c in fake.started if c["workflow"] == "IssueEstimation")
    # comment_id в id прогона: повторная доставка того же вебхука не запустит вторую оценку.
    assert call["id"] == "estimate-acme/widgets-7-555"
    assert call["arg"].comment_id == 555


def test_analyze_command_goes_through_the_live_cycle(webhook):
    """Раньше здесь стартовал самостоятельный IssueAnalysis, а циклу уходило
    лишь косметическое уведомление. Теперь работу ведёт владелец состояния."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("/analyze")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["CommentAck", "IssueLifecycle"]
    cycle = fake.started[1]
    assert cycle["id"] == "issue-acme/widgets-7"
    assert cycle["start_signal"] == "analyze_requested"
    assert cycle["start_signal_args"] == [555]
    assert cycle["arg"].interactive is True, (
        "команда пришла из треда — цикл уточнений здесь уместен")


def test_analyze_falls_back_to_a_root_run_for_an_old_cycle(webhook):
    """Прогон прежнего поколения сигнала не понимает: команда была бы принята и
    потеряна. Лаунчер стартует ему самостоятельный прогон, как раньше."""
    fake, app_client = webhook(handles_agents=False)

    assert _post(app_client, _comment("/analyze")).status_code == 200

    # Голого signal() на этом пути больше нет — только signal-with-start.
    assert fake.signals == []
    assert {c["workflow"] for c in fake.started} == {
        "CommentAck", "IssueLifecycle", "IssueAnalysis"}
    analysis = next(c for c in fake.started if c["workflow"] == "IssueAnalysis")
    assert analysis["id"] == "analysis-acme/widgets-7"
    assert analysis["arg"].comment_id == 555


def test_repeated_analyze_does_not_start_a_second_run(webhook):
    fake, app_client = webhook(already={"IssueAnalysis"}, handles_agents=False)

    assert _post(app_client, _comment("/analyze")).status_code == 200
    assert not any(c["workflow"] == "IssueAnalysis" for c in fake.started)


def test_repeated_estimate_delivery_is_swallowed(webhook):
    fake, app_client = webhook(already={"IssueEstimation"}, handles_agents=False)

    assert _post(app_client, _comment("/estimate")).status_code == 200
    assert not any(c["workflow"] == "IssueEstimation" for c in fake.started)


def test_plain_comment_feeds_the_clarification_loop(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _comment("да, речь про мобильный клиент")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["CommentAck"]
    assert fake.signals[0] == "issue-acme/widgets-7"
    assert ("user_comment", ("да, речь про мобильный клиент", 555)) in fake.signals


def test_comment_after_workflow_finished_is_not_an_error(webhook):
    """Issue закрыт, воркфлоу завершён — комментарий просто некуда сигналить."""
    fake, app_client = webhook(signal_fails=True)

    assert _post(app_client, _comment("обычный текст")).status_code == 200


def test_any_human_comment_is_acknowledged_first(webhook):
    """Реакция «увидел» не ветвится ни на чём: она заказывается до разбора
    команды, до гейта прав и до всякого пайплайна."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("просто мысль вслух")).status_code == 200

    ack = fake.started[0]
    assert ack["workflow"] == "CommentAck"
    # Ключ по id комментария: ретрай доставки не просит вторую реакцию.
    assert ack["id"] == "comment-ack-acme/widgets-555"
    assert (ack["arg"].repo, ack["arg"].issue_number, ack["arg"].comment_id) == (
        "acme/widgets", 7, 555)


def test_repeated_delivery_does_not_ask_for_a_second_reaction(webhook):
    fake, app_client = webhook(already={"CommentAck"})

    assert _post(app_client, _comment("обычный текст")).status_code == 200

    assert not any(c["workflow"] == "CommentAck" for c in fake.started)
    # Обработка самого комментария при этом идёт своим чередом.
    assert ("user_comment", ("обычный текст", 555)) in fake.signals


def test_comment_is_processed_even_if_the_reaction_fails(webhook, monkeypatch):
    """Подтверждение приёма — украшение основного пути, а не условие его работы."""
    fake, app_client = webhook()
    original = fake.start_workflow

    async def flaky(workflow, arg, **kwargs):
        if workflow == "CommentAck":
            raise RuntimeError("Temporal недоступен")
        return await original(workflow, arg, **kwargs)

    monkeypatch.setattr(fake, "start_workflow", flaky)

    assert _post(app_client, _comment("обычный текст")).status_code == 200
    assert ("user_comment", ("обычный текст", 555)) in fake.signals


def test_command_from_a_forbidden_user_is_still_acknowledged(webhook, monkeypatch):
    """Гейт прав отсекает дорогую стадию, но не факт приёма: человек должен
    видеть разницу между «не увидели» и «увидели и отказали»."""
    monkeypatch.setenv("AGENT_TRIGGER_ALLOWLIST", "bob")
    fake, app_client = webhook()

    assert _post(app_client, _comment("/analyze")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["CommentAck"]


def test_bot_comments_are_ignored(webhook):
    """Сервис не должен сигналить сам себе: свои же комментарии приходят обратно."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("/analyze", user_type="Bot")).status_code == 200
    assert fake.started == []
    assert fake.signals == []


def test_non_created_actions_are_ignored(webhook):
    fake, app_client = webhook()
    payload = _comment("/analyze")
    payload["action"] = "edited"

    assert _post(app_client, payload).status_code == 200
    assert fake.started == []


def test_quoted_command_does_not_run(webhook):
    """Ответ с процитированной командой не должен запускать её повторно."""
    fake, app_client = webhook()

    assert _post(app_client, _comment("> /analyze\n\nсогласен")).status_code == 200

    assert [c["workflow"] for c in fake.started] == ["CommentAck"]
    assert ("user_comment", ("> /analyze\n\nсогласен", 555)) in fake.signals
