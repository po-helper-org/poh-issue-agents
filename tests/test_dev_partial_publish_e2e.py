"""Сквозной путь: срыв — черновик — честный комментарий.

Отказ, ради которого написано: на `poh-demo-checkout#166` после красных
тестов не осталось ни ветки, ни диффа, ни причины — только метка `failed`.

Воркфлоу проверено отдельно (`test_dev_partial_publish_workflow.py`); здесь
важно, что человек получает связный результат — от рабочего дерева до
комментария в ленте, через настоящий git и настоящую сборку тела PR.
"""

import subprocess

import activities as a
import github_client as gc
from shared.workflow_types import IssueInput

# `a.github_client` — диспетчер `forge`, выбирающий клиент по репозиторию.
# Здесь подменяется именно клиент GitHub: сквозной путь должен пройти через
# настоящую сборку запроса, а не через подставленный на её место диспетчер.


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=166, title="Корзина теряет позиции",
                      body="b", author_login="u", author_type="User",
                      interactive=True)


def _worktree(tmp_path):
    """Рабочее дерево, каким его оставляет сорвавшийся прогон.

    Настоящий git, а не заглушка: проверка «есть ли что публиковать» и
    попадание `.harness/` в коммит — это поведение git, и подменять его
    значит проверять собственную выдумку.
    """
    origin = tmp_path / "origin.git"
    clone_dir = tmp_path / "clone"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True,
                   capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(clone_dir)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.name", "t"],
                   check=True)
    (clone_dir / "README.md").write_text("baseline")
    subprocess.run(["git", "-C", str(clone_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "seed"],
                   check=True, capture_output=True)
    # Постановка: её пишет `dev_prepare` ДО агента, и она обязана дойти до PR.
    harness = clone_dir / a.task_context.DIR
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")
    return clone_dir


async def test_a_failed_run_leaves_a_draft_and_an_honest_comment(monkeypatch, tmp_path):
    """Четыре факта одним прогоном:

    1. открыт ЧЕРНОВОЙ PR, а не обычный;
    2. в коммит уехала работа агента вместе с постановкой;
    3. комментарий называет прогон сорванным и несёт причину;
    4. комментарий даёт ссылку на черновик — человеку есть куда смотреть.
    """
    clone_dir = _worktree(tmp_path)
    (clone_dir / "cart.py").write_text("# правка агента\n")

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))
    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _Created:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 42}

    sent: dict = {}
    comments: list = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda *args, **kw: sent.update(body=kw.get("json")) or _Created())
    monkeypatch.setattr(gc, "post_comment",
                        lambda repo, number, body: comments.append(body))

    number = await a.dev_publish_partial(
        _issue(), "research/issue-166",
        "проверки не прошли (код 1):\n# fail 3")

    assert number == 42
    assert sent["body"]["draft"] is True, "сорванная работа ушла обычным PR"

    show = subprocess.run(
        ["git", "-C", str(clone_dir), "show", "--stat", "HEAD"],
        check=True, capture_output=True, text=True).stdout
    assert "cart.py" in show, "работа агента не доехала до коммита"
    assert f"{a.task_context.DIR}/context.md" in show, "постановка потерялась"

    comment = comments[0]
    assert "сорва" in comment.lower()
    assert "fail 3" in comment
    assert "42" in comment
    assert "готово к ревью" not in comment.lower()


async def test_a_run_that_wrote_nothing_leaves_no_trace(monkeypatch, tmp_path):
    """Агент не тронул код — ни черновика, ни комментария.

    Постановка в рабочем дереве есть всегда (её пишет `dev_prepare`), и без
    исключения её из проверки пустоты контур открывал бы черновик на каждом
    прогоне, где агент не сделал ни одного хода.
    """
    clone_dir = _worktree(tmp_path)  # только постановка, кода агента нет

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))
    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")

    posts: list = []
    comments: list = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda *args, **kw: posts.append(kw))
    monkeypatch.setattr(gc, "post_comment",
                        lambda repo, number, body: comments.append(body))

    number = await a.dev_publish_partial(_issue(), "research/issue-166", "причина")

    assert number is None
    assert posts == [], "PR открывать нечем"
    assert comments == [], "сообщать человеку не о чем"
