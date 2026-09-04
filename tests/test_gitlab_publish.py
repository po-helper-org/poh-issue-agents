"""Выкладка рабочего дерева на GitLab: диспетчер, черновик, общая git-механика.

Отказ, ради которого написано (#275): стадия разработки на GitLab-репозитории
падала `NotImplementedError: gitlab-клиент не умеет «publish_worktree»` —
диспетчер `forge` резолвит метод по репозиторию, а метода не было. Клонирование
при этом уходило на github.com с именем пользователя `x-access-token`, потому
что адрес и пара были вписаны в активность жёстко.

Сеть не трогаем: git-механика подменяется, HTTP — двойником транспорта.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

import gitlab_client as gl  # noqa: E402
import worktree  # noqa: E402


@pytest.fixture(autouse=True)
def gitlab_env(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test")
    monkeypatch.setenv("GITLAB_REPOS", "gl-org/*")
    monkeypatch.delenv("DRY_RUN", raising=False)
    # `BASE` вычисляется на ИМПОРТЕ модуля, а не на вызове: соседний тест,
    # выставивший `GITLAB_URL` до первого импорта, менял бы ожидаемый адрес, и
    # эти проверки падали бы от порядка файлов, а не от кода. Задаём явно.
    monkeypatch.setattr(gl, "BASE", "https://gitlab.com/api/v4")


# --- Диспетчер больше не отказывает ---

def test_dispatcher_resolves_publish_for_a_gitlab_repo(monkeypatch):
    """Тот самый отказ из #275: до правки здесь был NotImplementedError."""
    import forge

    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: False)
    assert forge.publish_worktree("gl-org/demo", "/tmp/x", "feature/1-openhands",
                                  title="t", body="b", message="m") is None


def test_github_repo_still_goes_to_github(monkeypatch):
    """Разводка по провайдеру не должна съехать: репозиторий вне GITLAB_REPOS
    обязан по-прежнему обслуживаться GitHub-клиентом."""
    import forge

    monkeypatch.setenv("GH_TOKEN", "ghp-test")   # пилотный путь без GitHub App
    assert forge.provider_for("gh-org/app") == forge.GITHUB
    assert forge.git_credentials("gh-org/app") == ("x-access-token", "ghp-test")


# --- Что уходит в git ---

def test_gitlab_pushes_as_oauth2(monkeypatch):
    """Имя пользователя у GitLab — `oauth2`; `x-access-token` там не работает."""
    seen = {}

    def fake_push(repo, clone_dir, branch, **kwargs):
        seen.update(kwargs)
        return True

    monkeypatch.setattr(worktree, "commit_and_push", fake_push)
    monkeypatch.setattr(gl, "open_change_request", lambda *a, **k: {"number": 7})

    gl.publish_worktree("gl-org/demo", "/tmp/x", "feature/1-openhands",
                        title="t", body="b", message="m")
    assert seen["credentials"][0] == "oauth2"
    assert seen["credentials"][1] == "glpat-test"
    assert "gitlab.com" in seen["committer_email"]


def test_empty_worktree_publishes_nothing(monkeypatch):
    """Агент ничего не написал — не отказ и не повод открывать пустой MR."""
    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: False)
    monkeypatch.setattr(gl, "open_change_request", lambda *a, **k: pytest.fail(
        "MR не должен открываться на пустом дереве"))

    assert gl.publish_worktree("gl-org/demo", "/tmp/x", "b",
                               title="t", body="b", message="m") is None


def test_flags_reach_the_shared_mechanics(monkeypatch):
    """`ignore_for_empty_check` и `force_include` несут разборы инцидентов M1/M3
    — потерять их по дороге к общей механике значит вернуть те дефекты."""
    seen = {}
    monkeypatch.setattr(worktree, "commit_and_push",
                        lambda *a, **k: seen.update(k) or True)
    monkeypatch.setattr(gl, "open_change_request", lambda *a, **k: {"number": 1})

    gl.publish_worktree("gl-org/demo", "/tmp/x", "b", title="t", body="b",
                        message="m", ignore_for_empty_check=(".harness/**",),
                        force_include=(".harness",))
    assert seen["ignore_for_empty_check"] == (".harness/**",)
    assert seen["force_include"] == (".harness",)


# --- Черновик ---

def test_draft_is_marked_by_title_prefix(monkeypatch):
    """У POST /merge_requests нет поля `draft`: единственный документированный
    способ — префикс заголовка."""
    seen = {}
    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: True)
    monkeypatch.setattr(gl, "open_change_request",
                        lambda repo, **k: seen.update(k) or {"number": 3})

    gl.publish_worktree("gl-org/demo", "/tmp/x", "b", title="СОРВАЛОСЬ feat(#1)",
                        body="b", message="m", draft=True)
    assert seen["title"] == "Draft: СОРВАЛОСЬ feat(#1)"


def test_draft_prefix_is_not_doubled(monkeypatch):
    """Повторный прогон сорванной разработки иначе копил бы `Draft: Draft: …`."""
    seen = {}
    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: True)
    monkeypatch.setattr(gl, "open_change_request",
                        lambda repo, **k: seen.update(k) or {"number": 3})

    gl.publish_worktree("gl-org/demo", "/tmp/x", "b", title="Draft: feat(#1)",
                        body="b", message="m", draft=True)
    assert seen["title"] == "Draft: feat(#1)"


def test_ordinary_publish_is_not_a_draft(monkeypatch):
    seen = {}
    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: True)
    monkeypatch.setattr(gl, "open_change_request",
                        lambda repo, **k: seen.update(k) or {"number": 3})

    gl.publish_worktree("gl-org/demo", "/tmp/x", "b", title="feat(#1)",
                        body="b", message="m")
    assert seen["title"] == "feat(#1)"


def test_dry_run_publishes_nothing(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(worktree, "commit_and_push", lambda *a, **k: pytest.fail(
        "в DRY_RUN git трогать нельзя"))
    assert gl.publish_worktree("gl-org/demo", "/tmp/x", "b",
                               title="t", body="b", message="m") is None


# --- Ссылки на файлы ---

def test_gitlab_blob_url_has_the_dash_segment():
    """Без `/-/` адрес неотличим от пути к подгруппе и отдаёт 404."""
    assert gl.blob_base("gl-org/demo", "research/issue-1") == (
        "https://gitlab.com/gl-org/demo/-/blob/research/issue-1")


def test_github_blob_url_keeps_its_shape():
    import github_client as gh

    assert gh.blob_base("gh-org/app", "b") == "https://github.com/gh-org/app/blob/b"


def test_clone_url_is_provider_specific():
    import forge

    assert forge.clone_url("gl-org/demo") == "https://gitlab.com/gl-org/demo.git"
    assert forge.clone_url("gh-org/app") == "https://github.com/gh-org/app.git"
