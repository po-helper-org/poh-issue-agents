import github_client


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pr_event(number, title="PR", state="open"):
    return {
        "event": "cross-referenced",
        "source": {"issue": {
            "number": number, "title": title, "state": state,
            "html_url": f"https://github.com/o/r/pull/{number}",
            "pull_request": {"url": f"https://api.github.com/repos/o/r/pulls/{number}"},
        }},
    }


def test_keeps_only_cross_referenced_prs(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "test_token")
    timeline = [
        {"event": "labeled"},                       # не cross-ref — выкинуть
        _pr_event(2, "Ingress", "open"),            # PR — оставить
        {"event": "cross-referenced", "source": {"issue": {  # issue, не PR — выкинуть
            "number": 7, "title": "just issue", "state": "open",
            "html_url": "https://github.com/o/r/issues/7"}}},
    ]
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: _FakeResp(timeline))

    prs = github_client.list_linked_prs("o/r", 1)

    assert prs == [{
        "number": 2, "title": "Ingress", "state": "open",
        "url": "https://github.com/o/r/pull/2",
    }]


def test_dedups_and_respects_limit(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "test_token")
    timeline = [_pr_event(2)] * 3 + [_pr_event(3), _pr_event(4), _pr_event(5)]
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: _FakeResp(timeline))

    prs = github_client.list_linked_prs("o/r", 1, limit=2)

    assert [p["number"] for p in prs] == [2, 3]  # дедуп #2, обрезка до 2


def test_uses_timeline_endpoint_with_preview_header(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "test_token")
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        seen["accept"] = headers.get("Accept", "")
        seen["auth"] = headers.get("Authorization", "")
        return _FakeResp([])

    monkeypatch.setattr(github_client.requests, "get", fake_get)

    github_client.list_linked_prs("o/r", 1)

    assert seen["url"].endswith("/repos/o/r/issues/1/timeline")
    assert "mockingbird" in seen["accept"]
    # Токен уходит через _auth_headers (Authorization), а НЕ в URL: любой сбой
    # git/HTTP рендерит URL в текст исключения, заголовки — нет.
    assert "test_token" in seen["auth"]
    assert "test_token" not in seen["url"]
