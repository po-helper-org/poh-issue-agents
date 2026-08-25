"""Клиент GitLab: форма запроса и то, чем он отличается от GitHub-клиента."""
import importlib

import pytest


@pytest.fixture
def gl(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("GITLAB_BOT_LOGIN", raising=False)
    import gitlab_client
    return importlib.reload(gitlab_client)


class Resp:
    def __init__(self, code=200, payload=None, text=""):
        self.status_code = code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


@pytest.fixture
def calls(gl, monkeypatch):
    seen = []

    def fake(method, url, **kw):
        seen.append((method, url, kw))
        return fake.response

    fake.response = Resp()
    monkeypatch.setattr(gl.requests, "request", fake)
    return seen, fake


# --- кодирование пути ---

def test_путь_в_подгруппе_кодируется_целиком(gl, calls):
    seen, _ = calls
    gl.get_issue("group/sub/project", 7)
    assert "group%2Fsub%2Fproject" in seen[0][1]
    assert "group/sub" not in seen[0][1]


def test_числовой_id_не_кодируется(gl, calls):
    seen, _ = calls
    gl.get_issue("85686131", 7)
    assert "/projects/85686131/" in seen[0][1]


# --- метки ---

def test_метки_меняются_одним_put(gl, calls):
    seen, _ = calls
    gl.set_labels("g/p", 7, add=["phase:groomed"], remove=["phase:classified"])
    assert len(seen) == 1, "должен быть ровно один запрос"
    method, url, kw = seen[0]
    assert method == "PUT"
    assert url.endswith("/issues/7")
    assert kw["data"]["add_labels"] == "phase:groomed"
    assert kw["data"]["remove_labels"] == "phase:classified"


def test_метка_из_add_не_попадает_в_remove(gl, calls):
    seen, _ = calls
    gl.set_labels("g/p", 7, add=["phase:groomed"], remove=["phase:groomed", "x"])
    assert seen[0][2]["data"]["remove_labels"] == "x"


def test_labels_целиком_не_используется(gl, calls):
    """Параметр labels заменяет набор и затёр бы метки человека."""
    seen, _ = calls
    gl.set_labels("g/p", 7, add=["a"])
    assert "labels" not in seen[0][2]["data"]


def test_пустой_набор_не_шлёт_запрос(gl, calls):
    seen, _ = calls
    gl.set_labels("g/p", 7)
    assert seen == []


# --- реакция ---

def test_реакция_требует_номер_задачи(gl, calls):
    with pytest.raises(ValueError, match="номер задачи"):
        gl.add_reaction("g/p", 42)


def test_реакция_кладёт_iid_в_путь(gl, calls):
    seen, _ = calls
    gl.add_reaction("g/p", 42, "eyes", issue_number=7)
    assert "/issues/7/notes/42/award_emoji" in seen[0][1]


def test_имена_emoji_переводятся(gl, calls):
    seen, _ = calls
    gl.add_reaction("g/p", 42, "+1", issue_number=7)
    assert seen[0][2]["data"]["name"] == "thumbsup"


# --- комментарии ---

def test_комментарий_подписывается(gl, calls):
    seen, _ = calls
    gl.post_comment("g/p", 7, "текст")
    assert "<!-- issue-agent -->" in seen[0][2]["data"]["body"]


def test_системные_заметки_отсекаются(gl, calls, monkeypatch):
    seen, fake = calls
    fake.response = Resp(payload=[
        {"id": 1, "body": "сменил метку", "system": True, "author": {"username": "bot"}},
        {"id": 2, "body": "живая реплика", "system": False, "author": {"username": "human"}},
    ])
    gl.list_comments("g/p", 7)
    assert seen[0][2]["params"]["activity_filter"] == "only_comments"


def test_бот_определяется_логином(gl, calls, monkeypatch):
    seen, fake = calls
    monkeypatch.setenv("GITLAB_BOT_LOGIN", "harness-bot")
    fake.response = Resp(payload=[
        {"id": 1, "body": "a", "author": {"username": "harness-bot"}},
        {"id": 2, "body": "b", "author": {"username": "human"}},
    ])
    out = gl.list_comments("g/p", 7)
    assert [c["user"]["type"] for c in out] == ["Bot", "User"]


# --- ревью ---

def test_ревью_отбирает_по_маркеру_а_не_по_боту(gl, calls):
    """У GitLab нет user.type — фильтр по нему вернул бы пустоту."""
    seen, fake = calls
    fake.response = Resp(payload=[
        {"body": "замечание ревьюера", "system": False},
        {"body": "мой ответ\n\n<!-- issue-agent -->", "system": False},
        {"body": "changed the description", "system": True},
    ])
    text = gl.review_text("g/p", 12)
    assert "замечание ревьюера" in text
    assert "мой ответ" not in text
    assert "changed the description" not in text


# --- merge request ---

def test_дубликат_mr_проверяется_до_создания(gl, calls):
    """Код и текст ошибки при дубликате в документации не описаны."""
    seen, fake = calls
    fake.response = Resp(payload=[{"iid": 5, "title": "уже есть", "state": "opened"}])
    out = gl.open_change_request("g/p", source="research/issue-7", title="t", body="b")
    assert out["number"] == 5
    assert all(m != "POST" for m, _, _ in seen), "MR создавать было не нужно"


def test_связанные_mr_собираются_из_двух_источников(gl, calls, monkeypatch):
    seen = []

    def fake(method, url, **kw):
        seen.append(url)
        if "related_merge_requests" in url:
            return Resp(payload=[{"iid": 3, "title": "a"}])
        if "closed_by" in url:
            return Resp(payload=[{"iid": 3, "title": "a"}, {"iid": 9, "title": "b"}])
        return Resp(payload=[])

    monkeypatch.setattr(gl.requests, "request", fake)
    out = gl.list_linked_prs("g/p", 7)
    assert [m["number"] for m in out] == [3, 9], "дубли должны схлопнуться"


# --- файлы ---

def test_создание_и_обновление_файла_разными_методами(gl, monkeypatch):
    """GitHub PUT /contents делает и то, и другое. GitLab разделяет."""
    seen = []
    state = {"exists": False}

    def fake(method, url, **kw):
        seen.append((method, url))
        if url.endswith("/raw"):
            return Resp(200, text="было") if state["exists"] else Resp(404)
        return Resp(200)

    monkeypatch.setattr(gl.requests, "request", fake)

    gl.put_file("g/p", "a.md", "x", branch="main", message="m")
    assert seen[-1][0] == "POST", "новый файл создаётся POST"

    state["exists"] = True
    seen.clear()
    gl.put_file("g/p", "a.md", "y", branch="main", message="m")
    assert seen[-1][0] == "PUT", "существующий обновляется PUT"


# --- git ---

def test_имя_пользователя_для_git_oauth2(gl):
    user, token = gl.git_credentials("g/p")
    assert user == "oauth2"
    assert token == "tok"


def test_запуск_пайплайна_не_реализуется(gl):
    with pytest.raises(NotImplementedError, match="локальным раннером"):
        gl.dispatch_workflow("g/p", "wf.yml")


# --- DRY_RUN ---

def test_dry_run_не_делает_запросов(gl, monkeypatch, calls):
    seen, _ = calls
    monkeypatch.setenv("DRY_RUN", "1")
    import gitlab_client
    g = importlib.reload(gitlab_client)
    monkeypatch.setattr(g.requests, "request", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("HTTP под DRY_RUN")))
    g.post_comment("g/p", 7, "текст")
    g.set_labels("g/p", 7, add=["a"])
    g.close_issue("g/p", 7)
