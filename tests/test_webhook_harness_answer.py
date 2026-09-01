"""`/harness-answer` доезжает до цикла сигналом `user_comment` (Task 7).

Спека — `docs/superpowers/specs/2026-08-29-harness-answer-command-design.md`:
A4 (комментарий контура ответом не считается), A8 (прав по
`AGENT_TRIGGER_ALLOWLIST` команда не спрашивает — дорогую стадию не запускает).

Прочие команды в `user_comment` не уходят — их съел бы цикл уточнений. Эта
уходит намеренно: её адресат и есть цикл, который задал вопрос.

Вспомогательные `_fake_client_returning` и `_comment_payload` — по образцу
FakeClient/FakeHandle из `tests/test_webhook_subissue_ignored.py` и
однопараметровой формы `_comment_payload` из `tests/test_howtodemo_webhook.py`
(в `test_webhook_subissue_ignored.py` `_comment_payload` двухпараметровая —
несёт ещё и метки Issue, здесь они не нужны). Фикстура `client` своя: pytest
не делится фикстурами между модулями теста, а готового `client.post(url,
json=..., headers=...)` с автоподписью тела нигде рядом не было — соседние
тесты вебхука либо возвращают голый `TestClient` и подписывают тело сами
через отдельный `_post(client, ...)`, либо (как этот файл) заворачивают
подпись в сам фикстурный объект.
"""

import hashlib
import hmac
import json as _json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "test-secret"


def _fake_client_returning(handle):
    """Клиент Temporal-двойник: `get_workflow_handle` всегда отдаёт `handle`
    независимо от id воркфлоу — тестам важен только результат сигнала."""

    class _Client:
        def get_workflow_handle(self, wf_id):
            return handle

    async def _get_client():
        return _Client()

    return _get_client


def _comment_payload(body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 12, "title": "t", "body": "b", "labels": [],
                  "user": {"login": "human"}, "state": "open"},
        "comment": {"id": 777, "body": body, "user": {"login": "human"}},
        "sender": {"login": "human"},
    }


class _SignedClient:
    """`TestClient`, который сам подписывает тело — как GitHub на реальной
    доставке. Без этого `verify_signature` отвечает 401 раньше, чем запрос
    доходит до разбора команды."""

    def __init__(self, inner):
        self._inner = inner

    def post(self, url, json=None, headers=None):
        body = _json.dumps(json).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        full_headers = dict(headers or {})
        full_headers["X-Hub-Signature-256"] = signature
        full_headers["Content-Type"] = "application/json"
        return self._inner.post(url, content=body, headers=full_headers)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main
    from fastapi.testclient import TestClient

    return _SignedClient(TestClient(main.app))


def test_harness_answer_reaches_the_lifecycle(monkeypatch, client):
    """Ответ доезжает до цикла сигналом user_comment.

    Прочие команды в user_comment не уходят — их съел бы цикл уточнений. Эта
    уходит намеренно: её адресат и есть цикл, который задал вопрос.
    """
    import main

    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client", _fake_client_returning(_Handle()))

    response = client.post("/webhook", json=_comment_payload("/harness-answer 1"),
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled and signalled[0][0] == "user_comment"
    assert "/harness-answer 1" in signalled[0][1][0]


def test_agent_own_comment_is_not_an_answer(monkeypatch, client):
    """Комментарий контура ответом не считается (A4).

    Не про ветку `/harness-answer`: гейт `is_agent_comment` в `main.py`
    стоит РАНЬШЕ разбора команды (`command = parse_command(...)`) и при
    срабатывании возвращает `{"ok": True}` до него — какой бы ни была команда
    в теле. Этот тест проверяет только гейт A4 как таковой; он не касается ни
    ветки `if command == HARNESS_ANSWER`, ни общего пути в конце обработчика,
    ни вынесенного в них `_signal_user_comment` (за это отвечает
    `test_harness_answer_branch_short_circuits_the_generic_path` ниже).
    Под PAT комментарии сервиса возвращаются с `type == "User"`, и без
    проверки подписи контур отвечал бы сам себе.
    """
    import main

    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client", _fake_client_returning(_Handle()))

    payload = _comment_payload("/harness-answer 1\n\n<!-- issue-agent -->")
    response = client.post("/webhook", json=payload,
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert signalled == [], "контур принял собственный комментарий за ответ"


def test_harness_answer_branch_short_circuits_the_generic_path(monkeypatch, client):
    """Ранний `return` в ветке `/harness-answer` — не косметика, а изоляция.

    После выноса общей части в `_signal_user_comment` явная ветка и общий
    путь в конце обработчика делают один и тот же вызов — их нельзя отличить
    ни по имени сигнала, ни по args, ни по коду ответа (см. отчёт задачи 7,
    находка 1: до правки оба теста этого файла были зелёными БЕЗ единой
    строки кода ветки). Единственное, что у ветки есть, а у совпадения по
    коду — нет, это структурная гарантия: `return` не даёт `command ==
    HARNESS_ANSWER` провалиться сквозь все последующие `if command == ...`
    (RELEASE/HOWTODEMO/ESTIMATE/RESEARCH/BFT*/ANALYZE — ни один не совпадёт,
    HARNESS_ANSWER от них отличен) до безусловного вызова в самом низу.

    Убери `return {"ok": True}` из ветки — и `_signal_user_comment` отработает
    ДВАЖДЫ на одном и том же комментарии: один раз из ветки, второй раз из
    общего пути. Это и ловит тест: считает фактические вызовы `signal`, а не
    их содержимое.
    """
    import main

    signalled = []

    class _Handle:
        async def signal(self, name, args=None):
            signalled.append((name, args))

    monkeypatch.setattr(main, "get_temporal_client", _fake_client_returning(_Handle()))

    response = client.post("/webhook", json=_comment_payload("/harness-answer 1"),
                           headers={"X-GitHub-Event": "issue_comment"})

    assert response.status_code == 200
    assert len(signalled) == 1, (
        "сигнал ушёл не один раз — ранний return из ветки /harness-answer "
        "убран или сломан, команда провалилась в общий путь")
