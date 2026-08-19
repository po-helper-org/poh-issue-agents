"""Edge-кейсы, найденные агентом разработки, доезжают до бэклога.

Правило работы агента — «edge-кейс не в эту ветку, а отдельным SubIssue». В
режиме `dispatch` он заводил их сам: в Actions есть и `gh`, и GITHUB_TOKEN. В
режиме `local` ни того, ни другого у раннера нет и быть не должно — токен не
уезжает в контейнер, который исполняет чужой код. Поэтому агент оставляет
находки ФАЙЛОМ, а Issue по ним заводит воркер, уже своими руками.
"""

from shared import develop


def test_findings_file_is_parsed_into_titles_and_bodies():
    text = """## Отрицательная цена позиции проходит в расчёт

`subtotal` проверяет `price < 0`, но `qty` умножается раньше.
Всплывёт при импорте прайса из внешней системы.

## Скидка не логируется

Нет способа объяснить клиенту итог.
"""

    items = develop.parse_followups(text)

    assert [i["title"] for i in items] == [
        "Отрицательная цена позиции проходит в расчёт",
        "Скидка не логируется",
    ]
    assert "subtotal" in items[0]["body"]
    assert "объяснить клиенту" in items[1]["body"]


def test_empty_or_missing_findings_are_not_an_error():
    """«Ничего не нашёл» — законный исход, а не сбой прогона."""
    assert develop.parse_followups("") == []
    assert develop.parse_followups("   \n\n") == []


def test_prose_without_headings_is_not_turned_into_an_issue():
    """Без заголовка не понять, где кончается одна находка и начинается другая.
    Заводить Issue с телом вместо названия хуже, чем не заводить."""
    assert develop.parse_followups("нашёл кое-что, но оформить не смог") == []


def test_findings_are_capped():
    text = "\n".join(f"## находка {i}\n\nтекст\n" for i in range(30))

    assert len(develop.parse_followups(text)) == develop.MAX_FOLLOWUPS


def test_body_carries_the_chain_key_and_the_parent():
    """`root-issue: #N` и ссылка на родителя обязательны: по ключу контур
    отличает свой выход от входа и считает глубину цепочки (правила R6, R7)."""
    body = develop.followup_body({"title": "t", "body": "что не учтено"}, parent=13)

    assert body.splitlines()[0] == "root-issue: #13"
    assert "#13" in body
    assert "что не учтено" in body


# --- Сбор находок после прогона агента ---

import asyncio
import pathlib

import activities as activities_module
from shared.workflow_types import IssueInput


def _issue(number: int = 13) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def _workspace(tmp_path, monkeypatch, findings: str | None):
    monkeypatch.setenv("DEVELOP_WORKSPACE_MOUNT", str(tmp_path))
    clone = tmp_path / develop.task_slug("o/r", 13) / "repo"
    clone.mkdir(parents=True)
    if findings is not None:
        (clone / develop.FOLLOWUPS_FILE).write_text(findings, encoding="utf-8")
    return clone


def test_findings_become_subissues_and_the_file_never_reaches_the_pr(tmp_path, monkeypatch):
    """Файл — постановка для контура, а не часть правки: он снимается до коммита.

    Уехав в PR, он попал бы в ревью как мусор, а на следующем круге правок агент
    прочитал бы собственные прошлые находки как новые.
    """
    clone = _workspace(tmp_path, monkeypatch,
                       "## Отрицательная цена\n\nвсплывёт на импорте прайса\n")
    created: list[tuple] = []
    comments: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "create_issue",
                        lambda repo, title, body, labels=None: created.append(
                            (repo, title, body, labels)) or 101)
    monkeypatch.setattr(activities_module.github_client, "post_comment",
                        lambda repo, n, body: comments.append(body))

    asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert len(created) == 1
    repo, title, body, labels_ = created[0]
    assert title == "Отрицательная цена"
    assert body.splitlines()[0] == "root-issue: #13"
    assert "origin:agent" in labels_
    assert not (clone / develop.FOLLOWUPS_FILE).exists(), "файл находок уехал бы в PR"
    assert "#101" in comments[0], "ссылки на находки не появились в родителе"


def test_no_findings_means_no_comment_and_no_issue(tmp_path, monkeypatch):
    """«Не нашёл» — законный исход. Пустой комментарий про пустой список — шум."""
    _workspace(tmp_path, monkeypatch, None)

    def boom(*a, **k):
        raise AssertionError("нечего заводить и нечего писать")

    monkeypatch.setattr(activities_module.github_client, "create_issue", boom)
    monkeypatch.setattr(activities_module.github_client, "post_comment", boom)

    asyncio.run(activities_module.collect_dev_followups(_issue()))


def test_a_failed_issue_does_not_lose_the_rest(tmp_path, monkeypatch):
    """Прогон уже состоялся: одна невзятая находка не должна отменять остальные
    и уж точно не должна ронять шаг разработки целиком."""
    _workspace(tmp_path, monkeypatch, "## первая\n\nа\n\n## вторая\n\nб\n")
    created: list[str] = []

    def flaky(repo, title, body, labels=None):
        if title == "первая":
            raise RuntimeError("GitHub 422")
        created.append(title)
        return 102

    monkeypatch.setattr(activities_module.github_client, "create_issue", flaky)
    monkeypatch.setattr(activities_module.github_client, "post_comment", lambda *a: None)

    asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert created == ["вторая"]


# --- Постановка не уезжает в PR ---

def test_task_statement_is_not_committed(tmp_path, monkeypatch):
    """`.task.md` — вход контура, а не часть правки.

    Файл лежит в рабочем дереве, и `git add -A` забирает его вместе с кодом. На
    живом прогоне #19 это дало PR из одного файла на 1721 строку — нашей же
    постановки, — и заодно спрятало главное: агент не изменил НИ ОДНОГО файла.
    Гвард «изменений нет — открывать нечего» видел дифф и молчал.
    """
    monkeypatch.setenv("DEVELOP_WORKSPACE_MOUNT", str(tmp_path))
    clone = tmp_path / develop.task_slug("o/r", 19) / "repo"
    clone.mkdir(parents=True)
    (clone / ".task.md").write_text("постановка", encoding="utf-8")
    captured = {}

    def fake_publish(repo, clone_dir, branch, *, title, body, message):
        captured["task_md_exists"] = (pathlib.Path(clone_dir) / ".task.md").exists()
        return 28

    monkeypatch.setattr(activities_module.github_client, "publish_worktree", fake_publish)

    number = activities_module._dev_publish(_issue(19), "research/issue-19")

    assert number == 28
    assert captured["task_md_exists"] is False, "постановка уехала в коммит"
    assert not (clone / ".task.md").exists()


def test_agent_output_reaches_the_log(tmp_path, monkeypatch, caplog):
    """Вывод агента виден и на успешном прогоне.

    Он логировался только в тексте исключения, то есть при ненулевом коде.
    Прогон, который отработал 21 минуту и ничего не сделал, не оставлял ни
    строки — разбираться было не с чем.
    """
    monkeypatch.setenv("DEVELOP_WORKSPACE_MOUNT", str(tmp_path))

    class _Done:
        returncode = 0
        stdout = "AGENT-SAID-THIS"
        stderr = ""

    monkeypatch.setattr(activities_module.subprocess, "run", lambda cmd, **kw: _Done())

    with caplog.at_level("INFO", logger="activities"):
        activities_module._dev_run_agent(_issue(19))

    assert "AGENT-SAID-THIS" in caplog.text
