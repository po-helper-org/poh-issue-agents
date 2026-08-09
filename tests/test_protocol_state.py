"""Чтение состояния по протоколу — одно на старте (правило R2)."""

import activities


def _issue(labels_list, body=""):
    return {"labels": [{"name": name} for name in labels_list], "body": body}


def _wire(monkeypatch, issues: dict):
    """issues: {номер: ответ get_issue}. Считает обращения, чтобы проверить,
    что родитель читается только когда нужен."""
    calls = []

    def fake_get_issue(repo, number):
        calls.append(number)
        if number not in issues:
            raise RuntimeError(f"404 {number}")
        return issues[number]

    monkeypatch.setattr(activities.github_client, "get_issue", fake_get_issue)
    return calls


def test_clean_issue_has_nothing_set(monkeypatch):
    _wire(monkeypatch, {7: _issue([])})

    state = activities.read_protocol_state("o/r", 7)

    assert state.agents_off is False
    assert state.origin_agent is False
    assert state.depth_exceeded is False


def test_agents_off_is_detected(monkeypatch):
    _wire(monkeypatch, {7: _issue(["agents:off", "priority:P1"])})

    assert activities.read_protocol_state("o/r", 7).agents_off is True


def test_origin_agent_is_detected(monkeypatch):
    _wire(monkeypatch, {7: _issue(["origin:agent"])})

    state = activities.read_protocol_state("o/r", 7)

    assert state.origin_agent is True
    assert state.depth_exceeded is False  # без root-issue глубину не считаем


def test_root_issue_is_extracted_from_body(monkeypatch):
    _wire(monkeypatch, {7: _issue(["origin:agent"], "root-issue: #42"),
                        42: _issue([])})

    assert activities.read_protocol_state("o/r", 7).root_issue == 42


def test_second_round_of_follow_ups_is_capped(monkeypatch):
    """R7: follow-up, порождённый follow-up-ом. Родитель тоже от агента —
    цепочка пошла на второй круг, дальше её ведёт человек."""
    _wire(monkeypatch, {7: _issue(["origin:agent"], "root-issue: #42"),
                        42: _issue(["origin:agent"])})

    assert activities.read_protocol_state("o/r", 7).depth_exceeded is True


def test_follow_up_from_human_issue_is_allowed(monkeypatch):
    """Первый круг — штатный путь контура, останавливать его нечего."""
    _wire(monkeypatch, {7: _issue(["origin:agent"], "root-issue: #42"),
                        42: _issue(["enhancement"])})

    assert activities.read_protocol_state("o/r", 7).depth_exceeded is False


def test_parent_is_not_read_for_a_human_issue(monkeypatch):
    """Лишний вызов GitHub на каждом обычном прогоне — заметная цена на бэкфилле."""
    calls = _wire(monkeypatch, {7: _issue([], "root-issue: #42"), 42: _issue([])})

    activities.read_protocol_state("o/r", 7)

    assert calls == [7]


def test_unreadable_parent_does_not_break_triage(monkeypatch):
    """Родителя удалили или он в другом репозитории: ложный стоп дороже
    лишнего прогона, поэтому считаем глубину допустимой."""
    _wire(monkeypatch, {7: _issue(["origin:agent"], "root-issue: #999")})

    state = activities.read_protocol_state("o/r", 7)

    assert state.depth_exceeded is False
    assert state.root_issue == 999
