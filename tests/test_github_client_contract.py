"""Контракт транспорта: метод, путь и тело каждого вызова к трекеру.

Эти тесты не проверяют логику — они фиксируют форму HTTP-запроса. Смысл
появляется при втором провайдере: без них рефакторинг клиента проходит
зелёным даже когда пути поехали, потому что 31 тест из 33 подменяют модуль
целиком, а не HTTP.

Проверяется ровно то, что нельзя изменить, не сломав интеграцию: метод,
полный URL и полезная нагрузка.
"""

import importlib

import pytest

from shared.label_catalog import LabelSpec


def _fresh(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    import github_client
    return importlib.reload(github_client)


class _Resp:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    @property
    def ok(self):
        return True


@pytest.fixture
def capture(monkeypatch):
    """Перехватывает вызовы requests и возвращает список (метод, url, kwargs)."""
    gc = _fresh(monkeypatch)
    calls = []

    def record(method, payload=None):
        def fake(url, **kwargs):
            calls.append((method, url, kwargs))
            return _Resp(payload)
        return fake

    monkeypatch.setattr(gc.requests, "post", record("POST", {"number": 42}))
    monkeypatch.setattr(gc.requests, "get", record("GET", {"default_branch": "main"}))
    monkeypatch.setattr(gc.requests, "patch", record("PATCH"))
    monkeypatch.setattr(gc.requests, "delete", record("DELETE"))
    monkeypatch.setattr(gc.requests, "put", record("PUT"))
    return gc, calls


B = "https://api.github.com"


def test_post_comment_contract(capture):
    gc, calls = capture
    gc.post_comment("o/r", 7, "текст")
    method, url, kwargs = calls[0]
    assert (method, url) == ("POST", f"{B}/repos/o/r/issues/7/comments")
    assert kwargs["json"]["body"].startswith("текст")
    assert "<!-- issue-agent -->" in kwargs["json"]["body"]


def test_add_label_contract(capture):
    gc, calls = capture
    gc.add_label("o/r", 7, "phase:classified")
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues/7/labels")
    assert calls[0][2]["json"] == {"labels": ["phase:classified"]}


def test_set_labels_contract(capture):
    gc, calls = capture
    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues/7/labels")
    assert calls[0][2]["json"] == {"labels": ["phase:groomed"]}
    assert calls[1][:2] == ("DELETE", f"{B}/repos/o/r/issues/7/labels/phase%3Aclassified")


def test_remove_label_contract(capture):
    gc, calls = capture
    gc.remove_label("o/r", 7, "run:analyze")
    assert calls[0][:2] == ("DELETE", f"{B}/repos/o/r/issues/7/labels/run%3Aanalyze")


def test_create_issue_contract(capture):
    gc, calls = capture
    number = gc.create_issue("o/r", "заголовок", "тело", ["origin:agent"])
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues")
    assert calls[0][2]["json"] == {
        "title": "заголовок", "body": "тело", "labels": ["origin:agent"]}
    assert number == 42


def test_close_issue_contract(capture):
    gc, calls = capture
    gc.close_issue("o/r", 7)
    assert calls[0][:2] == ("PATCH", f"{B}/repos/o/r/issues/7")
    assert calls[0][2]["json"] == {"state": "closed"}


def test_branch_exists_contract(capture):
    gc, calls = capture
    gc.branch_exists("o/r", "research/issue-7")
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/branches/research/issue-7")


def test_get_issue_contract(capture):
    gc, calls = capture
    gc.get_issue("o/r", 7)
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/issues/7")


def test_list_comments_contract(capture, monkeypatch):
    gc, calls = capture

    # list_comments срезает resp.json() как список (`[:limit]`) — фикстура
    # capture по умолчанию отдаёт на GET словарь (годится для branch_exists,
    # get_issue), здесь подменяем именно на список.
    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return _Resp([])

    monkeypatch.setattr(gc.requests, "get", fake_get)
    gc.list_comments("o/r", 7)
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/issues/7/comments")
    assert calls[0][2]["params"]["per_page"]


def test_add_reaction_contract(capture):
    gc, calls = capture
    gc.add_reaction("o/r", 99)
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues/comments/99/reactions")
    assert calls[0][2]["json"] == {"content": "eyes"}


def test_pat_beats_app_in_auth_header(capture):
    gc, _ = capture
    headers = gc._auth_headers("o/r")
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Accept"] == "application/vnd.github+json"


def test_ensure_labels_exist_contract(monkeypatch):
    """`ensure_labels_exist` бьёт в /labels проекта — другой ресурс, чем
    `_post_labels` (метки НА Issue). Опечатка в этом URL проходила бы весь
    набор зелёным без этого теста: остальные тесты клиента мокают
    `ensure_labels_exist` целиком, а не транспорт.

    Закрепляем: постраничный GET списка меток проекта, и POST с телом
    `name`/`color` (без решётки)/`description`; существующая метка не
    перепосится — идемпотентность видна уже на форме запросов."""
    gc = _fresh(monkeypatch)

    get_calls = []
    page1 = [{"name": f"l{i}"} for i in range(100)]  # полная страница → ждём вторую
    page2 = [{"name": "existing"}]                    # неполная → это последняя

    def fake_get(url, **kwargs):
        get_calls.append((url, kwargs))
        page = kwargs["params"]["page"]
        return _Resp(page1 if page == 1 else page2)

    post_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return _Resp({})

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc.requests, "post", fake_post)

    specs = [
        LabelSpec(name="existing", color="#ABCDEF", description="уже есть"),
        LabelSpec(name="new-one", color="#123456", description="новая"),
    ]
    created = gc.ensure_labels_exist("o/r", specs)

    assert [c[0] for c in get_calls] == [f"{B}/repos/o/r/labels"] * 2
    assert get_calls[0][1]["params"] == {"per_page": 100, "page": 1}
    assert get_calls[1][1]["params"] == {"per_page": 100, "page": 2}

    assert len(post_calls) == 1  # существующая метка не перепосилась
    assert post_calls[0][0] == f"{B}/repos/o/r/labels"
    assert post_calls[0][1]["json"] == {
        "name": "new-one", "color": "123456", "description": "новая",
    }
    assert created == 1
