"""Клиент Gitea: форма запроса и то, чем он отличается от GitHub-клиента.

Главное отличие — метки: контур ставит их по имени, а API Gitea принимает и
снимает их по id. Клиент разрешает имена сам и заводит недостающую метку, как
это делает GitHub при первом применении.
"""
import importlib

import pytest


class Resp:
    def __init__(self, code=200, payload=None):
        self.status_code = code
        self._payload = payload if payload is not None else {}
        self.text = ""
        self.headers = {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


@pytest.fixture
def gt(monkeypatch):
    monkeypatch.setenv("GITEA_TOKEN", "tok")
    monkeypatch.setenv("GITEA_URL", "http://127.0.0.1:8650")
    monkeypatch.setenv("GITEA_BOT_LOGIN", "bft-bot")
    monkeypatch.delenv("DRY_RUN", raising=False)
    import gitea_client
    return importlib.reload(gitea_client)


@pytest.fixture
def http(gt, monkeypatch):
    """Подделка сервера Gitea: ответы по (метод, хвост пути), журнал запросов."""
    seen, routes = [], {}

    def fake(method, url, **kw):
        seen.append((method, url, kw))
        for (m, tail), resp in routes.items():
            if m == method and url.split("?")[0].endswith(tail):
                return resp
        return Resp(200, {})

    monkeypatch.setattr(gt.requests, "request", fake)
    return seen, routes


def test_комментарий_подписан_и_уходит_в_задачу(gt, http):
    seen, _ = http
    gt.post_comment("bft/requests", 7, "Вопросы CustDev")
    method, url, kw = seen[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8650/api/v1/repos/bft/requests/issues/7/comments")
    assert kw["headers"]["Authorization"] == "token tok"
    assert kw["json"]["body"].startswith("Вопросы CustDev")
    assert kw["json"]["body"] != "Вопросы CustDev", "без подписи вебхук примет свой комментарий за человеческий"


def test_метки_ставятся_по_id_и_снимаются_по_id(gt, http):
    seen, routes = http
    routes[("GET", "/repos/bft/requests/labels")] = Resp(200, [
        {"id": 11, "name": "phase:created"}, {"id": 12, "name": "phase:inbox"}])
    gt.set_labels("bft/requests", 7, add=["phase:created"], remove=["phase:inbox"])
    writes = [(m, u.split("/api/v1")[1], kw.get("json")) for m, u, kw in seen if m != "GET"]
    assert ("POST", "/repos/bft/requests/issues/7/labels", {"labels": [11]}) in writes
    assert ("DELETE", "/repos/bft/requests/issues/7/labels/12", None) in writes


def test_незнакомая_метка_заводится(gt, http):
    seen, routes = http
    routes[("GET", "/repos/bft/requests/labels")] = Resp(200, [])
    routes[("POST", "/repos/bft/requests/labels")] = Resp(201, {"id": 21, "name": "phase:deep"})
    gt.add_label("bft/requests", 7, "phase:deep")
    writes = [(m, u.split("/api/v1")[1], kw.get("json")) for m, u, kw in seen if m != "GET"]
    assert writes[0][0:2] == ("POST", "/repos/bft/requests/labels")
    assert writes[0][2]["name"] == "phase:deep"
    assert writes[1] == ("POST", "/repos/bft/requests/issues/7/labels", {"labels": [21]})


def test_задача_во_внутренней_форме(gt, http):
    _, routes = http
    routes[("GET", "/repos/bft/requests/issues/7")] = Resp(200, {
        "number": 7, "title": "Экспорт", "body": "Вводная", "state": "open",
        "labels": [{"id": 1, "name": "phase:inbox"}], "user": {"login": "aleks"},
        "html_url": "http://127.0.0.1:8650/bft/requests/issues/7"})
    issue = gt.get_issue("bft/requests", 7)
    assert issue == {"number": 7, "title": "Экспорт", "body": "Вводная", "state": "open",
                     "labels": [{"name": "phase:inbox"}], "user": {"login": "aleks", "type": "User"},
                     "html_url": "http://127.0.0.1:8650/bft/requests/issues/7"}
    assert gt.get_issue_body("bft/requests", 7) == "Вводная"


def test_комментарии_сервисного_аккаунта_помечены_ботом(gt, http):
    _, routes = http
    routes[("GET", "/repos/bft/requests/issues/7/comments")] = Resp(200, [
        {"id": 1, "body": "вопрос", "user": {"login": "bft-bot"}, "created_at": "t1"},
        {"id": 2, "body": "ответ", "user": {"login": "aleks"}, "created_at": "t2"}])
    out = gt.list_comments("bft/requests", 7)
    assert [(c["id"], c["user"]["type"]) for c in out] == [(1, "Bot"), (2, "User")]


def test_реакция_на_комментарий(gt, http):
    seen, _ = http
    gt.add_reaction("bft/requests", 42, "eyes")
    method, url, kw = seen[0]
    assert (method, url.split("/api/v1")[1]) == ("POST", "/repos/bft/requests/issues/comments/42/reactions")
    assert kw["json"] == {"content": "eyes"}


def test_кандидаты_в_дубли_в_общей_форме(gt, http):
    """`duplicate_check` строит листинг по `_kind`: без него активность падала на smoke T1 (bft/requests#8)."""
    seen, routes = http
    routes[("GET", "/repos/bft/requests/issues")] = Resp(200, [
        {"number": 3, "title": "Экспорт заказов", "body": "Вводная", "state": "closed",
         "html_url": "http://127.0.0.1:8650/bft/requests/issues/3", "labels": [{"id": 1, "name": "phase:skipped"}],
         "pull_request": None}])
    out = gt.search_candidates("bft/requests", "Экспорт заказов в CSV")
    assert out == [{"number": 3, "title": "Экспорт заказов", "body": "Вводная", "state": "closed",
                    "url": "http://127.0.0.1:8650/bft/requests/issues/3",
                    "labels": [{"name": "phase:skipped"}], "_kind": "issue"}]
    _, url, kw = seen[0]
    assert kw["params"]["q"] == "Экспорт заказов в CSV"
    assert kw["params"]["state"] == "all"
