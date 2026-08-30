"""list_recent_comments: должен находить СВЕЖИЕ комментарии независимо от
длины ленты, прыгая сразу на последнюю страницу по Link-заголовку — а не
читая страницу 1, как это делает list_comments (см. docstring в
worker/github_client.py и ask_question в worker/activities.py, которая
из-за этого путала «комментария нет» с «комментарий за пределами первой
страницы»).
"""

import github_client


class _Resp:
    """Минимальная замена requests.Response: .json() и .links (без реального
    парсинга заголовка — сами кладём то, что вернул бы requests)."""

    def __init__(self, payload, links=None):
        self._payload = payload
        self.links = links or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _auth(monkeypatch):
    monkeypatch.setattr(github_client, "_auth_headers",
                        lambda repo: {"Authorization": "Bearer x"})


def test_single_page_needs_one_request(monkeypatch):
    """Лента короче limit — Link-заголовка с rel="last" нет (GitHub кладёт его,
    только когда страниц больше одной), второй запрос не нужен."""
    _auth(monkeypatch)
    calls = []

    def fake_get(url, **kwargs):
        calls.append(dict(kwargs["params"]))
        return _Resp([{"body": "a"}, {"body": "b"}])

    monkeypatch.setattr(github_client.requests, "get", fake_get)
    out = github_client.list_recent_comments("o/r", 7, limit=50)

    assert out == [{"body": "a"}, {"body": "b"}]
    assert calls == [{"per_page": 50, "page": 1}]


def test_multi_page_jumps_to_last_page_via_link_header(monkeypatch):
    """Длинная лента: первый запрос читает Link-заголовок и определяет номер
    последней страницы, второй идёт СРАЗУ на неё — старый комментарий с
    первой страницы в результат не попадает, свежий с последней попадает."""
    _auth(monkeypatch)
    calls = []
    last_url = "https://api.github.com/repos/o/r/issues/7/comments?per_page=100&page=3"

    def fake_get(url, **kwargs):
        calls.append(dict(kwargs["params"]))
        if kwargs["params"]["page"] == 1:
            return _Resp([{"body": "старый"}],
                        links={"last": {"url": last_url, "rel": "last"}})
        return _Resp([{"body": "свежий"}])

    monkeypatch.setattr(github_client.requests, "get", fake_get)
    out = github_client.list_recent_comments("o/r", 7, limit=100)

    assert out == [{"body": "свежий"}]
    assert calls == [{"per_page": 100, "page": 1}, {"per_page": 100, "page": 3}]


def test_limit_caps_per_page_at_github_maximum(monkeypatch):
    """GitHub не отдаёт больше 100 элементов на страницу — limit сверх этого
    ограничивает per_page запроса, а не размер ответа."""
    _auth(monkeypatch)
    calls = []

    def fake_get(url, **kwargs):
        calls.append(dict(kwargs["params"]))
        return _Resp([])

    monkeypatch.setattr(github_client.requests, "get", fake_get)
    github_client.list_recent_comments("o/r", 7, limit=500)

    assert calls[0]["per_page"] == 100
