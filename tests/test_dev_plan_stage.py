"""Стадия построения плана подключена к обычному прогону разработки.

Task 9 (воркфлоу MvpDelivery, per-step под-задачи) откачена ревью: среди
находок — K2, холодный старт. Стадия планирования запускалась в каталоге,
который создаёт только подготовка (`_dev_prepare`) — а подготовка в том
дизайне шла ВНУТРИ самого прогона разработки, то есть позже. План строился
в пустоте.

Здесь — узкий остаток задачи без per-step деления: план подключается К
ОБЫЧНОМУ ПРОГОНУ разработки, `trigger_openhands_resolver`, строго между
готовым рабочим местом и стартом агента. Порядок несущий и проверяется
буквально: и последовательностью вызовов, и файлом на диске в момент вызова
соседних шагов — совпадения меток недостаточно, если реальный побочный
эффект (каталог, файл плана) мог бы не поспеть.

Второй пласт — отказ планирования не обязан ронять разработку (план — вход
агента, а не результат работы; агент и без него работает штатно уже сегодня).
Третий — план обязан пережить путь до коммита: `.harness/` — единственный
служебный каталог, который `develop.clear_service_files` не снимает, и
`_dev_publish` включает его в коммит принудительно (`force_include`)
независимо от `.gitignore` целевого репозитория. Тест здесь гоняет
НАСТОЯЩИЙ `_dev_publish` (мокая только транспорт `github_client.publish_worktree`
под ним), чтобы не поверить на слово, а увидеть файл плана на диске в момент
самого вызова, что готовит коммит.
"""

import asyncio

import pytest

import activities as a
from shared import task_context
from shared.workflow_types import IssueInput


def _issue(number: int = 42) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User")


def _async(value=None):
    """Двойник асинхронной зависимости, безразличный к её сигнатуре."""
    async def _fn(*_args, **_kwargs):
        return value
    return _fn


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    """Все тесты файла — про локальный прогон, не про dispatch."""
    monkeypatch.delenv("DEVELOP_MODE", raising=False)
    monkeypatch.setattr(a, "_dev_resolve_branch", _async("research/issue-42"))


# --- Порядок: каталог готов -> план построен -> агент работает ---

def test_plan_is_built_after_prepare_and_before_the_agent_runs(monkeypatch, tmp_path):
    clone_dir = tmp_path / "repo"
    harness = clone_dir / task_context.DIR
    order: list[str] = []

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))

    def fake_prepare(issue, branch):
        order.append("prepare")
        # То же самое, что делает настоящая _dev_prepare: каталог контекста
        # появляется только здесь, а не раньше.
        harness.mkdir(parents=True)
        return "постановка", []

    monkeypatch.setattr(a, "_dev_prepare", fake_prepare)

    async def fake_announce(issue, branch, *, where):
        order.append("announce")

    monkeypatch.setattr(a, "_dev_announce", fake_announce)

    def fake_run_claude(prompt, cwd, mcp=None):
        # Момент запуска планирования: каталог обязан уже существовать — его
        # создаёт только _dev_prepare выше. Воспроизводит K2 (Task 9, revert
        # 80b3291), если проверка когда-нибудь перестанет быть верной.
        assert harness.exists(), (
            "план строится раньше, чем подготовка создала .harness/")
        order.append("plan")
        (harness / task_context.PLAN).write_text(
            "# План\n\n### Task 1\nDo: что-то.\n", encoding="utf-8")

    monkeypatch.setattr(a, "_run_claude", fake_run_claude)

    def fake_run_agent(issue):
        # Момент старта агента: план обязан уже лежать на диске, а не только
        # значиться вызванным где-то раньше по списку.
        assert (harness / task_context.PLAN).exists(), (
            "агент запустился раньше, чем план долетел до диска")
        order.append("agent")
        return "вывод агента"

    monkeypatch.setattr(a, "_dev_run_agent", fake_run_agent)
    monkeypatch.setattr(a, "_publish_dev_dialog_sync", lambda issue, branch: None)
    monkeypatch.setattr(a, "collect_dev_followups", _async([]))
    monkeypatch.setattr(a, "_dev_tests", lambda issue: "ok")
    monkeypatch.setattr(a, "_dev_publish", lambda issue, branch: 101)

    asyncio.run(a.trigger_openhands_resolver(_issue()))

    assert order == ["prepare", "announce", "plan", "agent"], (
        "порядок стадий разошёлся с «каталог готов -> план построен -> "
        f"агент работает»: получили {order}")


# --- Отказ планирования не роняет разработку ---

def test_plan_build_exception_does_not_stop_the_agent(monkeypatch, tmp_path):
    """`claude -p` для /plan-mvp упал (лимит частоты, как уже бывало у FNR) —
    build_mvp_plan бросает исключение (test_plan_stage_raises_when_claude_call_fails).
    Разработка не должна отказывать: план — вход агента, а не её результат, и
    агент уже сегодня штатно работает без него."""
    clone_dir = tmp_path / "repo"

    def fake_prepare(issue, branch):
        (clone_dir / task_context.DIR).mkdir(parents=True)
        return "постановка", []

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))
    monkeypatch.setattr(a, "_dev_prepare", fake_prepare)
    monkeypatch.setattr(a, "_dev_announce", _async())

    def boom_claude(prompt, cwd, mcp=None):
        raise RuntimeError("claude -p exit 1: rate limited")

    monkeypatch.setattr(a, "_run_claude", boom_claude)

    agent_calls = []
    monkeypatch.setattr(a, "_dev_run_agent",
                        lambda issue: agent_calls.append(1) or "ok")
    monkeypatch.setattr(a, "_publish_dev_dialog_sync", lambda issue, branch: None)
    monkeypatch.setattr(a, "collect_dev_followups", _async([]))
    monkeypatch.setattr(a, "_dev_tests", lambda issue: "ok")
    monkeypatch.setattr(a, "_dev_publish", lambda issue, branch: 303)

    number = asyncio.run(a.trigger_openhands_resolver(_issue()))

    assert agent_calls == [1], "агент не запустился после отказа планирования"
    assert number == 303


def test_empty_plan_file_does_not_stop_the_agent(monkeypatch, tmp_path):
    """`claude -p` не упал, но файла не оставил — build_mvp_plan вернёт False,
    не исключение (test_plan_stage_fails_when_file_not_created). Тот же
    штатный путь «работаем без плана», что и при исключении."""
    clone_dir = tmp_path / "repo"

    def fake_prepare(issue, branch):
        (clone_dir / task_context.DIR).mkdir(parents=True)
        return "постановка", []

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))
    monkeypatch.setattr(a, "_dev_prepare", fake_prepare)
    monkeypatch.setattr(a, "_dev_announce", _async())
    monkeypatch.setattr(a, "_run_claude", lambda prompt, cwd, mcp=None: None)

    agent_calls = []
    monkeypatch.setattr(a, "_dev_run_agent",
                        lambda issue: agent_calls.append(1) or "ok")
    monkeypatch.setattr(a, "_publish_dev_dialog_sync", lambda issue, branch: None)
    monkeypatch.setattr(a, "collect_dev_followups", _async([]))
    monkeypatch.setattr(a, "_dev_tests", lambda issue: "ok")
    monkeypatch.setattr(a, "_dev_publish", lambda issue, branch: 404)

    number = asyncio.run(a.trigger_openhands_resolver(_issue()))

    assert agent_calls == [1], "агент не запустился, хотя план лишь не создался"
    assert number == 404


# --- План обязан пережить путь до коммита ---

def test_plan_survives_the_full_local_run_up_to_the_commit(monkeypatch, tmp_path):
    """Гоняет НАСТОЯЩИЙ `_dev_publish` (мок только под ним, на транспорте
    `github_client.publish_worktree`), чтобы увидеть на диске в момент вызова,
    что готовит коммит: план не снят `clear_service_files` (в её перечне
    `SERVICE_FILES` `.harness/` не значится) и передан `force_include`."""
    clone_dir = tmp_path / "repo"
    harness = clone_dir / task_context.DIR

    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, clone_dir))

    def fake_prepare(issue, branch):
        harness.mkdir(parents=True)
        (harness / task_context.CONTEXT_MAP).write_text(
            "# Контекст задачи\n", encoding="utf-8")
        return "постановка", []

    monkeypatch.setattr(a, "_dev_prepare", fake_prepare)
    monkeypatch.setattr(a, "_dev_announce", _async())

    def fake_run_claude(prompt, cwd, mcp=None):
        (harness / task_context.PLAN).write_text(
            "# План\n\n### Task 1\nDo: что-то.\n", encoding="utf-8")

    monkeypatch.setattr(a, "_run_claude", fake_run_claude)
    monkeypatch.setattr(a, "_dev_run_agent", lambda issue: "вывод агента")
    monkeypatch.setattr(a, "_publish_dev_dialog_sync", lambda issue, branch: None)
    monkeypatch.setattr(a, "collect_dev_followups", _async([]))
    monkeypatch.setattr(a, "_dev_tests", lambda issue: "ok")

    captured = {}

    def fake_publish_worktree(repo, clone_dir_arg, branch, *, title, body, message,
                              ignore_for_empty_check=(), force_include=()):
        captured["harness_files"] = sorted(p.name for p in harness.iterdir())
        captured["force_include"] = force_include
        captured["ignore_for_empty_check"] = ignore_for_empty_check
        return 202

    monkeypatch.setattr(a.github_client, "publish_worktree", fake_publish_worktree)

    number = asyncio.run(a.trigger_openhands_resolver(_issue()))

    assert number == 202
    assert task_context.PLAN in captured["harness_files"], (
        "план не дожил до вызова, который готовит коммит — "
        f"в .harness/ на этот момент лежало: {captured['harness_files']}")
    assert task_context.DIR in captured["force_include"], (
        ".harness/ обязан быть в force_include — иначе .gitignore целевого "
        "репозитория может молча его съесть (M3, ревью задачи 7)")
