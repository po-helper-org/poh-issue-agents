"""Разработка как дочерний воркфлоу: границы шагов.

Прежде разработка была ОДНОЙ активностью из четырёх внутренних шагов, и её
ретрай повторял всё целиком. На живом прогоне #39 падал только `git push` —
а заново шёл двадцатиминутный прогон агента, и контур трижды объявил о
передаче задачи. Здесь проверяются границы, по которым стадия разрезана.
"""

import pytest

import activities as activities_module
from shared.workflow_types import DevelopPlan, IssueInput


def _issue(number: int = 39) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def gh(monkeypatch):
    """GitHub подменён целиком: активности не ходят в сеть в тестах."""
    calls: dict = {"dispatch": [], "labels": [], "comments": [], "branches": True}
    monkeypatch.setattr(activities_module.github_client, "dispatch_workflow",
                        lambda repo, wf, ref, inputs:
                            calls["dispatch"].append((repo, wf, ref, inputs)))
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: calls["labels"].append(label))
    monkeypatch.setattr(activities_module.github_client, "post_comment",
                        lambda repo, n, body: calls["comments"].append(body))
    monkeypatch.setattr(activities_module.github_client, "branch_exists",
                        lambda repo, branch: calls["branches"])
    monkeypatch.setattr(activities_module.github_client, "get_issue",
                        lambda repo, n: {"labels": []})
    return calls


async def test_begin_reports_local_mode_and_the_analysis_branch(gh, monkeypatch):
    """Ветка аналитики — вход агента. Она определяется ОДИН раз на входе в
    стадию, а не заново на каждом шаге: иначе удалённая по дороге ветка дала
    бы шагам разный контекст."""
    monkeypatch.setenv("DEVELOP_MODE", "local")
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    plan = await activities_module.dev_begin(_issue(39))

    assert plan == DevelopPlan(mode="local", branch="research/issue-39")


async def test_begin_reports_an_empty_branch_when_there_was_no_analysis(gh, monkeypatch):
    """Аналитики не было — агент работает от тела Issue. Пустая строка, а не
    отсутствие поля: «работаем без требований» это решение, и оно обязано быть
    видно в истории воркфлоу."""
    monkeypatch.setenv("DEVELOP_MODE", "local")
    gh["branches"] = False

    plan = await activities_module.dev_begin(_issue(39))

    assert plan.branch == ""


async def test_begin_refuses_when_the_switch_is_off(gh, monkeypatch):
    """Явное `0` оставляет Issue в очереди к живому разработчику. Отказ громкий:
    молча пропущенная стадия неотличима от исправной работы."""
    monkeypatch.setenv("DEVELOP_ENABLED", "0")

    with pytest.raises(RuntimeError, match="DEVELOP_ENABLED"):
        await activities_module.dev_begin(_issue(39))


async def test_begin_reports_dispatch_mode(gh, monkeypatch):
    monkeypatch.setenv("DEVELOP_MODE", "dispatch")
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    plan = await activities_module.dev_begin(_issue(39))

    assert plan.mode == "dispatch"


async def test_dispatch_sends_strings_only_and_announces(gh, monkeypatch):
    """`workflow_dispatch` принимает только строки — число молча уронит прогон
    на стороне GitHub, где мы его уже не увидим."""
    monkeypatch.setenv("DEVELOP_MODE", "dispatch")

    await activities_module.dev_dispatch(_issue(39), "research/issue-39")

    assert len(gh["dispatch"]) == 1
    _, _, _, inputs = gh["dispatch"][0]
    assert all(isinstance(v, str) for v in inputs.values())
    assert gh["labels"] == ["in-development"]
