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


# --- границы шагов: что уезжает в историю воркфлоу ---

async def test_prepare_returns_a_size_not_the_task_text(gh, monkeypatch):
    """Между шагами едут числа и пути, не содержимое.

    Постановка уже лежит файлом в общем томе (`.task.md`), и дублировать её в
    payload Temporal незачем: на большой задаче требования дают сотни килобайт,
    а история воркфлоу — не хранилище документов. НФТ-01: потолок 4 КБ.
    """
    monkeypatch.setattr(activities_module, "_dev_prepare",
                        lambda issue, branch: ("x" * 5000, ["R-1", "R-2"]))

    size = await activities_module.dev_prepare(_issue(39), "research/issue-39")

    assert size == 5000
    assert isinstance(size, int)


async def test_publish_returns_the_pr_number(gh, monkeypatch):
    monkeypatch.setattr(activities_module, "_dev_publish",
                        lambda issue, branch: 101)

    assert await activities_module.dev_publish(_issue(39), "b") == 101


async def test_publish_returns_none_when_the_agent_changed_nothing(gh, monkeypatch):
    """`None` — не сбой шага, а его честный результат. Решение «открывать
    нечего» принимает воркфлоу: у него есть контекст стадии, у активности нет."""
    monkeypatch.setattr(activities_module, "_dev_publish",
                        lambda issue, branch: None)

    assert await activities_module.dev_publish(_issue(39), "b") is None


async def test_run_agent_raises_on_a_failed_run(gh, monkeypatch):
    """Ненулевой код раннера — сбой шага. Он обязан долететь до воркфлоу
    исключением: проглоченный, он дал бы пустой PR при доложенном успехе."""
    def boom(issue):
        raise RuntimeError("прогон агента разработки завершился с кодом 137")

    monkeypatch.setattr(activities_module, "_dev_run_agent", boom)

    with pytest.raises(RuntimeError, match="137"):
        await activities_module.dev_run_agent(_issue(39))


def test_all_dev_steps_are_registered_activities():
    """Шаг, не зарегистрированный в воркере, не вызовется из воркфлоу — и
    обнаружится это на живом прогоне, а не здесь."""
    import worker as worker_module

    names = worker_module.DEVELOP_ACTIVITIES
    expected = [activities_module.dev_begin, activities_module.dev_dispatch,
                activities_module.dev_prepare, activities_module.dev_announce,
                # План работ (Task 10) — под маркером патча, между готовым
                # рабочим местом и стартом агента; отказ не роняет прогон.
                activities_module.build_mvp_plan,
                activities_module.dev_run_agent, activities_module.dev_followups,
                activities_module.dev_tests,
                # Диагностика красного прогона: зовётся не по порядку, а из
                # обработчика отказа тестов — регистрация нужна та же.
                activities_module.dev_diagnose,
                activities_module.dev_publish,
                # Спасение работы сорвавшегося прогона: зовётся не по порядку,
                # а из обработчика отказа — но регистрация нужна та же, и без
                # неё дефект вылезет ровно там, где спасать уже нечем.
                activities_module.dev_publish_partial,
                # Запись об итерации слою саморефлексии. Шаг опционален по
                # действию (без MEMORY_BASE_URL он ничего не делает), но
                # зарегистрирован всегда: воркфлоу зовёт его под маркером.
                activities_module.capture_episode]
    assert names == expected
