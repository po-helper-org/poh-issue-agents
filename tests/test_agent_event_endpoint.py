"""#38: приём событий внешних агентов вебхуком.

Сигнал, двигающий фазу Issue, не может приходить анонимно — поэтому половина
файла про подпись. Вторая половина про то, что событие не теряется: ни при
неопознанной работе, ни при отсутствующем цикле.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

from shared import lifecycle  # noqa: E402
from shared.agent_events import STARTED, SUCCEEDED  # noqa: E402

SECRET = "agent-secret"


class FakeClient:
    def __init__(self, already: set[str] | None = None) -> None:
        self.started: list[dict] = []
        self._already = already or set()

    async def start_workflow(self, workflow, *args, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "args": args, **kwargs})
        return None


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "gh-secret")
    monkeypatch.setenv("AGENT_EVENT_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main
    from fastapi.testclient import TestClient

    def _build(already: set[str] | None = None):
        fake = FakeClient(already)

        async def _get_client():
            return fake

        monkeypatch.setattr(main, "get_temporal_client", _get_client)
        return fake, TestClient(main.app)

    return _build


def _event(**over) -> dict:
    base = {"repo": "acme/widgets", "agent": "pr-agent", "phase": lifecycle.PR_OPEN,
            "status": STARTED, "ref": "research/issue-7"}
    base.update(over)
    return base


def _post(app_client, payload: dict, secret: str = SECRET, sign: bool = True):
    raw = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-Agent-Signature-256"] = (
            "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest())
    return app_client.post("/agent-event", content=raw, headers=headers)


# --- авторизация ---

def test_unsigned_event_is_rejected(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _event(), sign=False).status_code == 401
    assert fake.started == []


def test_event_signed_with_a_wrong_secret_is_rejected(webhook):
    fake, app_client = webhook()

    assert _post(app_client, _event(), secret="чужой").status_code == 401
    assert fake.started == []


def test_github_secret_does_not_open_this_channel(webhook):
    """Секреты разведены намеренно: утечка одного не должна открывать второй
    канал, тем более двигающий фазы Issue."""
    fake, app_client = webhook()

    assert _post(app_client, _event(), secret="gh-secret").status_code == 401


def test_endpoint_is_closed_when_the_secret_is_not_configured(webhook, monkeypatch):
    """Fail-closed: молчаливо открытый приём фазовых событий хуже выключенного."""
    monkeypatch.delenv("AGENT_EVENT_SECRET", raising=False)
    fake, app_client = webhook()

    assert _post(app_client, _event()).status_code == 503
    assert fake.started == []


# --- разбор конверта ---

def test_broken_envelope_is_a_client_error(webhook):
    """400, а не 500: ретраить некорректный конверт бессмысленно, и соседний
    сервис должен это понять по коду."""
    fake, app_client = webhook()

    resp = _post(app_client, _event(phase="почти-готово"))

    assert resp.status_code == 400
    assert "не из словаря" in resp.json()["detail"]
    assert fake.started == []


def test_foreign_repo_is_dropped(webhook, monkeypatch):
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "acme/widgets")
    fake, app_client = webhook()

    resp = _post(app_client, _event(repo="other/thing"))

    assert resp.status_code == 200
    assert fake.started == []


# --- доставка в цикл ---

def test_correlated_event_reaches_the_cycle(webhook):
    fake, app_client = webhook()

    resp = _post(app_client, _event(root_issue=7))

    assert resp.json() == {"ok": True, "correlated": True, "issue": 7,
                           "by": "поле root_issue"}
    call = fake.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["id"] == "issue-acme/widgets-7"
    assert call["start_signal"] == "agent_event"


def test_branch_convention_is_enough_to_correlate(webhook):
    fake, app_client = webhook()

    resp = _post(app_client, _event())

    assert resp.json()["issue"] == 7
    assert fake.started[0]["id"] == "issue-acme/widgets-7"


def test_cycle_is_raised_straight_into_the_reported_phase(webhook):
    """Цикла может не быть: Issue завели до установки App либо его прогон
    закрылся по сроку. Обычный старт погнал бы триаж по пустым заголовку и телу
    — уточняющий вопрос человеку и потраченные вызовы модели по задаче, которая
    давно в разработке."""
    fake, app_client = webhook()

    _post(app_client, _event(root_issue=7, phase=lifecycle.PR_REVIEW))

    issue_input, carried = fake.started[0]["args"]
    assert issue_input.issue_number == 7
    assert issue_input.interactive is False, "уточнять по PR-фазе не у кого"
    assert carried.phase == lifecycle.PR_REVIEW
    assert carried.stage == lifecycle.PR_REVIEW


def test_failed_status_raises_the_cycle_in_failed_not_in_the_named_phase(webhook):
    fake, app_client = webhook()

    _post(app_client, _event(root_issue=7, phase=lifecycle.TESTING, status="failed"))

    _, carried = fake.started[0]["args"]
    assert carried.phase == lifecycle.FAILED


# --- событие-сирота ---

def test_unidentified_work_is_recorded_not_dropped(webhook):
    """Тишина здесь означала бы ровно тот обрыв трассировки, ради которого
    задача и ставилась."""
    fake, app_client = webhook()

    resp = _post(app_client, _event(ref="build-881"))

    assert resp.json()["correlated"] is False
    call = fake.started[0]
    assert call["workflow"] == "OrphanAgentEvent"
    assert call["args"][0].ref == "build-881"
    assert "root_issue" in call["args"][0].reason


def test_ambiguous_work_goes_to_a_human_instead_of_a_guess(webhook):
    fake, app_client = webhook()

    resp = _post(app_client, _event(ref="feature/x", detail="Closes #12, fixes #34"))

    assert resp.json()["correlated"] is False
    assert fake.started[0]["workflow"] == "OrphanAgentEvent"
    assert "#12" in fake.started[0]["args"][0].reason


def test_repeated_orphan_delivery_is_swallowed(webhook):
    """Повторная доставка того же факта не должна ни падать в 500, ни плодить
    вторую запись."""
    fake, app_client = webhook(already={"OrphanAgentEvent"})

    resp = _post(app_client, _event(ref="build-881"))

    assert resp.status_code == 200
    assert fake.started == []


def test_orphan_record_id_is_stable_for_the_same_fact(webhook):
    fake, app_client = webhook()

    _post(app_client, _event(ref="build-881", status=SUCCEEDED))

    assert fake.started[0]["id"] == "orphan-acme/widgets-build-881:pr-open:succeeded"
