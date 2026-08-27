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
                        lambda url, headers=None, timeout=None:
                            _FakeResponse([{"number": 152}, {"number": 153}]))
    monkeypatch.setattr(github_client, "_auth_headers", lambda repo: {})

    assert [i["number"] for i in github_client.list_sub_issues("o/r", 151)] == [152, 153]


def test_node_id_comes_from_issue(monkeypatch):
    monkeypatch.setattr(github_client, "get_issue",
                        lambda repo, number: {"number": number, "id": 424242})
    assert github_client.issue_node_id("o/r", 152) == 424242
