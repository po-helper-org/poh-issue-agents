"""Под-задача шага не поднимает свой жизненный цикл.

Она живёт часы, закрывается вместе со своим шагом, и триаж ей не нужен: задачу
уже разобрал план родителя. Каждый лишний цикл — вечный воркфлоу и вызов модели
на приоритет.

Гейт по метке `harness:step` стоит ОДИН раз на входе `_handle_delivery`, но
поднять цикл умеют четыре разных ветки вебхука: `issues.opened`, лейбл-решение
человека (`research-me` и т.п.), лейбл-команда (`run:analyze` и т.п.) и команда
комментарием (`/analyze` и т.п.) — все они бьют по одному Issue тем же
signal-with-start. Каждая проверена отдельно здесь: гейт держится не на том,
что ветки написаны похоже, а на том, что метка проверяется РАНЬШЕ, чем вебхук
вообще смотрит, какая это ветка.

Пятый путь — эндпоинт `/agent-event`: он не разбирает `issues`/`issue_comment`
вовсе и меток в событии не несёт, поэтому гейт здесь его не ловит и ловить не
может. Барьер для него стоит в воркере (`_run_phase_loop`, до входа в первую
фазу) и проверен в tests/test_agent_event_workflow.py.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "s3cret"


class FakeHandle:
    """Ответ цикла на вопрос лаунчера «ведёшь ли ты агентов сам» (#37).

    Нужен только веткам `run:*` / командам комментарием: `request_analysis` и
    соседи спрашивают его после signal-with-start, чтобы решить child-vs-root.
    """

    def __init__(self):
        self.signals: list[dict] = []

    async def signal(self, name, args=None):
        self.signals.append({"name": name, "args": args})

    async def query(self, name, *args):
        assert name == "handles_agents", name
        return True


class FakeClient:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.handles: dict[str, FakeHandle] = {}

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return FakeHandle()

    def get_workflow_handle(self, wf_id):
        if wf_id not in self.handles:
            self.handles[wf_id] = FakeHandle()
        return self.handles[wf_id]


def _issue(number, label_names, body="тело"):
    return {"number": number, "title": "Шаг 2", "body": body,
            "user": {"login": "bot", "type": "Bot"},
            "labels": [{"name": name} for name in label_names]}


def _payload(label_names):
    """`issues.opened` — вектор из исходного коммита Task 13."""
    return {
        "action": "opened",
        "repository": {"full_name": "o/r"},
        "issue": _issue(152, label_names),
    }


def _labeled_payload(trigger_label, issue_label_names):
    """`issues.labeled` — общая форма для лейбла-решения (research-me) и
    лейбла-команды (run:analyze): различает их только имя `trigger_label`,
    вебхук ведёт их в разные воркфлоу, но гейт — до этого разбора."""
    return {
        "action": "labeled",
        "label": {"name": trigger_label},
        "repository": {"full_name": "o/r"},
        "issue": _issue(152, issue_label_names),
        "sender": {"login": "alice"},
    }


def _comment_payload(body, issue_label_names):
    """`issue_comment.created` — команда в треде (`/analyze` и т.п.)."""
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": _issue(152, issue_label_names),
        "comment": {"id": 555, "body": body, "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def _post(client, payload, event="issues"):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body,
                       headers={"X-GitHub-Event": event,
                                "X-Hub-Signature-256": sig,
                                "Content-Type": "application/json"})


def _webhook(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main
    from fastapi.testclient import TestClient

    fake = FakeClient()

    async def _get_client():
        return fake

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    return fake, TestClient(main.app)


def test_step_subissue_starts_nothing(monkeypatch):
    fake, client = _webhook(monkeypatch)

    assert _post(client, _payload(["harness:step"])).status_code == 200
    assert fake.started == [], "под-задача подняла цикл"

    assert _post(client, _payload([])).status_code == 200
    assert fake.started, "обычный Issue перестал подниматься"


def test_issue_with_unrelated_labels_starts_normally(monkeypatch):
    """Находка 2: гейт — точное совпадение метки, а не «есть хоть что-то».
    Обычные метки, не имеющие отношения к шагу, не должны его глушить."""
    fake, client = _webhook(monkeypatch)

    assert _post(client, _payload(["bug", "priority:P1"])).status_code == 200

    assert fake.started, "Issue с обычными метками перестал подниматься"


def test_issue_with_a_similar_label_starts_normally(monkeypatch):
    """Находка 2: `labels.has` — точное совпадение множества, не префикс и не
    подстрока. Похожая, но другая метка не обязана вести себя как `harness:step`."""
    fake, client = _webhook(monkeypatch)

    assert _post(client, _payload(["harness:steps"])).status_code == 200

    assert fake.started, "похожая метка ошибочно опознана как harness:step"


def test_step_subissue_ignores_human_decision_label(monkeypatch):
    """Подтверждённый вектор ревью: лейбл-решение (`research-me`) делает
    signal-with-start прямо в вебхуке, минуя гейт `issues.opened`."""
    fake, client = _webhook(monkeypatch)

    payload = _labeled_payload("research-me", ["harness:step", "research-me"])
    assert _post(client, payload, event="issues").status_code == 200

    assert fake.started == [], "под-задача подняла цикл по лейблу-решению"


def test_step_subissue_ignores_run_command_label(monkeypatch):
    """Подтверждённый вектор ревью: лейбл-команда (`run:analyze`) идёт через
    `agent_launcher.request_analysis` — тоже signal-with-start, и отдельный
    воркфлоу IssueAnalysis, если цикл прежнего поколения."""
    fake, client = _webhook(monkeypatch)

    payload = _labeled_payload("run:analyze", ["harness:step", "run:analyze"])
    assert _post(client, payload, event="issues").status_code == 200

    assert fake.started == [], "под-задача подняла цикл по лейблу-команде"


def test_step_subissue_ignores_comment_command(monkeypatch):
    """Подтверждённый вектор ревью: команда комментарием (`/analyze`) —
    тот же launcher, тот же signal-with-start, что и у лейбла-команды.

    Гейт стоит до `get_temporal_client()`, поэтому и CommentAck (реакция
    `eyes` на приём комментария) тоже не должен уйти."""
    fake, client = _webhook(monkeypatch)

    payload = _comment_payload("/analyze", ["harness:step"])
    assert _post(client, payload, event="issue_comment").status_code == 200

    assert fake.started == [], "под-задача подняла цикл по команде комментарием"


def test_step_subissue_closed_signals_lifecycle(monkeypatch):
    """Гейт НЕ должен гасить закрытие Issue.

    Закрытие Issue — это signal в СУЩЕСТВУЮЩИЙ цикл, а не старт нового.
    Он уже поднят и живёт на этом Issue. До правки гейт гасил закрытие,
    и цикл оставался висеть запаркованным: сигнал о закрытии никогда не уходил.

    Найденная ошибка (Medium): Issue с меткой шага получает закрытие →
    сигнал обязан уйти в живой workflow."""
    fake, client = _webhook(monkeypatch)

    # Payload закрытого Issue с меткой step
    payload = {
        "action": "closed",
        "repository": {"full_name": "o/r"},
        "issue": _issue(152, ["harness:step"]),
        "sender": {"login": "alice"},
    }

    assert _post(client, payload, event="issues").status_code == 200

    # Гейт не должен был гасить это событие
    handle = fake.handles.get("issue-o/r-152")
    assert handle is not None, "вебхук не получил handle для цикла"
    assert len(handle.signals) > 0, "signal закрытия не уходил"
    assert handle.signals[0]["name"] == "issue_closed"


def test_step_subissue_regular_comment_signals_lifecycle(monkeypatch):
    """Гейт НЕ должен гасить обычные комментарии.

    Обычный комментарий (не команда) — это signal в СУЩЕСТВУЮЩИЙ цикл,
    используется циклом уточнений. До правки гейт гасил такие комментарии,
    и они молча теряли информацию.

    Найденная ошибка (Medium): Issue с меткой шага получает обычный
    комментарий → сигнал обязан уйти в живой workflow."""
    fake, client = _webhook(monkeypatch)

    payload = _comment_payload("Это простой текст, не команда", ["harness:step"])
    assert _post(client, payload, event="issue_comment").status_code == 200

    # Гейт не должен был гасить это событие
    handle = fake.handles.get("issue-o/r-152")
    assert handle is not None, "вебхук не получил handle для цикла"
    assert len(handle.signals) > 0, "signal комментария не уходил"
    assert handle.signals[0]["name"] == "user_comment"
