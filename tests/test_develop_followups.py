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
