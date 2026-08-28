"""Нативные под-задачи GitHub: связь без строки в теле.

`root-issue: #N` в теле давало связь, которую GitHub не понимает: подзадача
оставалась обычным Issue в общем списке. Нативная связь убирает её оттуда и
даёт счётчик готовности у родителя.
"""

import github_client


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


def test_link_posts_child_id_not_number(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        return _FakeResponse({}, 201)

    monkeypatch.setattr(github_client.requests, "post", fake_post)
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    github_client.link_sub_issue("o/r", 151, 987654)

    assert seen["url"].endswith("/repos/o/r/issues/151/sub_issues")
    assert seen["json"] == {"sub_issue_id": 987654}


def test_list_returns_children(monkeypatch):
    monkeypatch.setattr(github_client.requests, "get",
                        lambda url, headers=None, params=None, timeout=None:
                            _FakeResponse([{"number": 152}, {"number": 153}]))
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    assert [i["number"] for i in github_client.list_sub_issues("o/r", 151)] == [152, 153]


def test_node_id_comes_from_issue(monkeypatch):
    monkeypatch.setattr(github_client, "get_issue",
                        lambda repo, number: {"number": number, "id": 424242})
    assert github_client.issue_node_id("o/r", 152) == 424242


def test_link_already_linked_is_idempotent(monkeypatch):
    """Повторная привязка (422 «already added») не ошибка — идемпотентна.
    Сценарий: POST дошёл до GitHub, связь создана, ответ потерян по сети.
    Ретрай зовёт функцию снова, GitHub отвечает 422, прогон не должен упасть."""
    calls = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["count"] = calls.get("count", 0) + 1
        # Повторная привязка: GitHub возвращает 422 на уже существующую связь
        return _FakeResponse({"message": "This issue is already added to the parent issue"}, 422)

    monkeypatch.setattr(github_client.requests, "post", fake_post)
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    # Не должно быть отказа
    github_client.link_sub_issue("o/r", 151, 987654)
    assert calls["count"] == 1


def test_list_sub_issues_paginates_all_pages(monkeypatch):
    """Пагинация: список из 150+ элементов (две неполные страницы).
    Без пагинации функция молча отдаст только первые 30, и счётчик готовности
    будет неполным — это ошибка класса «шаг отработал, результата нет»."""
    page_responses = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        page = params.get("page", 1) if params else 1
        # Первая страница: 100 элементов
        if page == 1:
            return _FakeResponse([{"number": i, "id": 1000 + i} for i in range(1, 101)])
        # Вторая страница: 50 элементов (неполная, признак конца)
        elif page == 2:
            return _FakeResponse([{"number": i, "id": 1000 + i} for i in range(101, 151)])
        else:
            return _FakeResponse([])

    monkeypatch.setattr(github_client.requests, "get", fake_get)
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    result = github_client.list_sub_issues("o/r", 151)
    # Должны получить все 150 элементов (100 + 50)
    assert len(result) == 150
    assert result[0]["number"] == 1
    assert result[99]["number"] == 100
    assert result[100]["number"] == 101
    assert result[149]["number"] == 150
