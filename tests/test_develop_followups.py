"""Edge-кейсы, найденные агентом разработки, ждут решения человека в теле Issue.

Правило работы агента — «edge-кейс не в эту ветку, а отдельной находкой». В
режиме `dispatch` он заводил их сам: в Actions есть и `gh`, и GITHUB_TOKEN. В
режиме `local` ни того, ни другого у раннера нет и быть не должно — токен не
уезжает в контейнер, который исполняет чужой код. Поэтому агент оставляет
находки ФАЙЛОМ, а секцию GROW тела родителя ими пополняет воркер, уже своими
руками: Issue по отмеченной находке заведёт человек сам, после гейта приёмки.
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
from shared import issue_blocks
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


def test_followups_go_to_grow_section_not_issues(monkeypatch, tmp_path):
    """Находка становится строкой в теле родителя, а не новой задачей.

    221 из 267 открытых задач организации завёл контур; большая часть — именно
    находки. Каждая поднимала свой вечный цикл и проходила триаж.
    """
    import asyncio
    import activities as a
    from shared import issue_blocks

    created = []
    body = {"text": "Постановка от человека."}

    monkeypatch.setattr(a.github_client, "create_issue",
                        lambda *args, **kwargs: created.append(args) or 999)
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda repo, n: body["text"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, n, new: body.__setitem__("text", new))
    monkeypatch.setattr(a.github_client, "post_comment", lambda *a_, **k_: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    root, clone = a._dev_paths(issue_stub := a.IssueInput(
        repo="o/r", issue_number=42, title="t", body="b",
        author_login="u", author_type="User"))
    clone.mkdir(parents=True, exist_ok=True)
    (clone / a.develop.FOLLOWUPS_FILE).write_text(
        "## Отрицательная цена проходит в расчёт\n\n"
        "`subtotal` проверяет price < 0 после умножения (src/pricing.mjs:26).\n",
        encoding="utf-8")

    result = asyncio.run(a.collect_dev_followups(issue_stub))

    assert created == [], "находка всё ещё заводит Issue"
    assert result == ["Отрицательная цена проходит в расчёт"]
    section = issue_blocks.read(body["text"], issue_blocks.GROW)
    assert section is not None and "Отрицательная цена" in section
    assert "Постановка от человека." in body["text"]


def test_findings_go_to_grow_section_and_the_file_never_reaches_the_pr(tmp_path, monkeypatch):
    """Файл — постановка для контура, а не часть правки: он снимается до коммита.

    Уехав в PR, он попал бы в ревью как мусор, а на следующем круге правок агент
    прочитал бы собственные прошлые находки как новые. Раньше этот тест
    закреплял создание отдельного Issue по находке — теперь находка остаётся
    строкой в секции GROW тела родителя.
    """
    clone = _workspace(tmp_path, monkeypatch,
                       "## Отрицательная цена\n\nвсплывёт на импорте прайса\n")
    created: list[tuple] = []
    bodies = {13: "Постановка от человека."}
    monkeypatch.setattr(activities_module.github_client, "create_issue",
                        lambda repo, title, body, labels=None: created.append(
                            (repo, title, body, labels)) or 101)
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: bodies[n])
    monkeypatch.setattr(activities_module.github_client, "update_issue_body",
                        lambda repo, n, new: bodies.__setitem__(n, new))

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert created == [], "находка больше не заводит Issue"
    assert result == ["Отрицательная цена"]
    assert not (clone / develop.FOLLOWUPS_FILE).exists(), "файл находок уехал бы в PR"
    section = issue_blocks.read(bodies[13], issue_blocks.GROW)
    assert section is not None and "Отрицательная цена" in section


def test_no_findings_means_no_github_calls_at_all(tmp_path, monkeypatch):
    """«Не нашёл» — законный исход. Ни записи в тело, ни сети — комментировать
    нечего и трогать родителя незачем."""
    _workspace(tmp_path, monkeypatch, None)

    def boom(*a, **k):
        raise AssertionError("нечего заводить и нечего писать")

    monkeypatch.setattr(activities_module.github_client, "create_issue", boom)
    monkeypatch.setattr(activities_module.github_client, "post_comment", boom)
    monkeypatch.setattr(activities_module.github_client, "get_issue_body", boom)
    monkeypatch.setattr(activities_module.github_client, "update_issue_body", boom)

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == []


def test_prose_without_headings_leaves_nothing_to_retry(tmp_path, monkeypatch):
    """Файл без заголовков не разбирается в находки — сохранять и повторять
    нечего, и файл снимается сразу, не дожидаясь сетевой записи (которой в
    этом случае и не будет)."""
    clone = _workspace(tmp_path, monkeypatch, "нашёл кое-что, но оформить не смог\n")

    def boom(*a, **k):
        raise AssertionError("находок нет — сети тут делать нечего")

    monkeypatch.setattr(activities_module.github_client, "get_issue_body", boom)
    monkeypatch.setattr(activities_module.github_client, "update_issue_body", boom)

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == []
    assert not (clone / develop.FOLLOWUPS_FILE).exists()


def test_second_run_keeps_earlier_grow_candidates(tmp_path, monkeypatch):
    """GROW копится за несколько прогонов разработки одной задачи, а не
    перезаписывается: до вердикта приёмки, который публикует секцию (Task 11),
    таких прогонов может быть не один."""
    clone = _workspace(tmp_path, monkeypatch, "## Вторая находка\n\nдетали\n")
    bodies = {13: (
        "Постановка.\n\n"
        "<!-- harness:grow:start -->\n"
        "## GROW — после прохождения HowToDemo\n\n"
        "- [ ] Первая находка — детали прошлого прогона\n"
        "<!-- harness:grow:end -->\n"
    )}
    created: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "create_issue",
                        lambda repo, title, body, labels=None: created.append(title) or 999)
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: bodies[n])
    monkeypatch.setattr(activities_module.github_client, "update_issue_body",
                        lambda repo, n, new: bodies.__setitem__(n, new))

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert created == []
    assert result == ["Вторая находка"]
    section = issue_blocks.read(bodies[13], issue_blocks.GROW)
    assert "Первая находка" in section, "прошлый прогон нельзя терять"
    assert "Вторая находка" in section


def test_second_run_keeps_a_multiline_finding_from_the_first_run(tmp_path, monkeypatch):
    """Многострочная находка не должна обрезаться до заголовка на втором
    прогоне (ревью, находка 1).

    Воспроизводит живой сценарий целиком, двумя настоящими прогонами:
    прогон 1 пишет находку с телом в три строки, прогон 2 приносит другую
    находку. Раньше накопление разбирало прежнее содержимое блока построчно
    и оставляло только строки, начинающиеся с `- [` — продолжения
    многострочного тела под это правило не подходили и терялись молча.
    """
    clone = _workspace(
        tmp_path, monkeypatch,
        "## Отрицательная цена позиции проходит в расчёт\n\n"
        "`subtotal` проверяет price < 0 уже после того, как qty умножен.\n"
        "Всплывёт при импорте прайса из внешней системы.\n"
        "Похоже на баг в src/pricing.mjs:26 — проверка стоит не в начале.\n")
    bodies = {13: "Постановка."}
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: bodies[n])
    monkeypatch.setattr(activities_module.github_client, "update_issue_body",
                        lambda repo, n, new: bodies.__setitem__(n, new))

    result_1 = asyncio.run(activities_module.collect_dev_followups(_issue()))
    assert result_1 == ["Отрицательная цена позиции проходит в расчёт"]

    (clone / develop.FOLLOWUPS_FILE).write_text(
        "## Скидка не логируется\n\nНет способа объяснить клиенту итог.\n",
        encoding="utf-8")
    result_2 = asyncio.run(activities_module.collect_dev_followups(_issue()))
    assert result_2 == ["Скидка не логируется"]

    section = issue_blocks.read(bodies[13], issue_blocks.GROW)
    assert "Отрицательная цена позиции проходит в расчёт" in section
    assert "Всплывёт при импорте прайса из внешней системы" in section, (
        "вторая строка тела первой находки потеряна после второго прогона")
    assert "Похоже на баг в src/pricing.mjs:26" in section, (
        "третья строка тела первой находки потеряна после второго прогона")
    assert "Скидка не логируется" in section


def test_a_failed_body_write_does_not_crash_the_step(tmp_path, monkeypatch, caplog):
    """Прогон уже состоялся: сбой записи находок в тело родителя (сеть,
    недоступный Issue) не должен ронять шаг разработки — только находки
    этого прогона, которые честно не засчитываются как записанные."""
    _workspace(tmp_path, monkeypatch, "## первая\n\nа\n\n## вторая\n\nб\n")
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: "Постановка.")

    def boom_update(repo, n, new):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(activities_module.github_client, "update_issue_body", boom_update)

    with caplog.at_level("WARNING", logger="activities"):
        result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == [], "не записанные находки нельзя выдавать за записанные"
    assert "не записал находки" in caplog.text


def test_a_failed_body_write_keeps_the_file_for_a_retry(tmp_path, monkeypatch):
    """Отказ записи не должен снимать файл находок с диска: файл, снятый ДО
    сетевой записи, лишает следующую попытку активности всего, что можно было
    бы перечитать — она увидит пустое место и молча доложит «находок нет»
    (ревью, находка 3)."""
    clone = _workspace(tmp_path, monkeypatch, "## первая\n\nа\n\n## вторая\n\nб\n")
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: "Постановка.")

    def boom_update(repo, n, new):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(activities_module.github_client, "update_issue_body", boom_update)

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == []
    assert (clone / develop.FOLLOWUPS_FILE).exists(), (
        "файл находок нельзя терять при неудавшейся записи — иначе ретрай бессмыслен")


def test_a_failed_body_write_is_reported_to_sentry(tmp_path, monkeypatch):
    """`logger.warning` живёт в stdout контейнера и никого не будит (см.
    докстринг `shared/sentry_setup.py`) — отказ записи находок обязан
    добираться и до Sentry, а не только до лога (ревью, находка 4)."""
    _workspace(tmp_path, monkeypatch, "## первая\n\nа\n")
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: "Постановка.")

    def boom_update(repo, n, new):
        raise RuntimeError("GitHub 502")

    monkeypatch.setattr(activities_module.github_client, "update_issue_body", boom_update)
    captured: list[tuple] = []
    monkeypatch.setattr(
        activities_module.sentry_setup, "capture_followups_failure",
        lambda issue, exc_type, message: captured.append(
            (issue.issue_number, exc_type, message)) or "evt-1")

    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == []
    assert captured == [(13, "RuntimeError", "GitHub 502")]


def test_finding_that_quotes_a_block_marker_does_not_corrupt_the_body(tmp_path, monkeypatch, caplog):
    """Находка приходит от модели и может дословно процитировать разметку блока
    (например, разбирая баг в самом `issue_blocks.py`). `write()` тогда честно
    отказывает `ValueError`, а не молча портит соседний блок или тело целиком —
    шаг обязан пережить этот отказ, не отправив тело на запись."""
    _workspace(
        tmp_path, monkeypatch,
        "## Маркер блока протекает в шаблон\n\n"
        "Буквально `<!-- harness:mvp-plan:start -->` встретился в шаблоне, "
        "и это ломает write().\n")
    update_calls: list[tuple] = []
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: "Постановка от человека.")
    monkeypatch.setattr(activities_module.github_client, "update_issue_body",
                        lambda repo, n, new: update_calls.append((repo, n, new)))

    with caplog.at_level("WARNING", logger="activities"):
        result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    assert result == [], "не записанную находку нельзя выдавать за записанную"
    assert update_calls == [], "тело не должно уйти на запись при отказе write()"
    assert "не записал находки" in caplog.text


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

    def fake_publish(repo, clone_dir, branch, *, title, body, message,
                     ignore_for_empty_check=(), force_include=()):
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


def test_duplicate_findings_are_not_accumulated(tmp_path, monkeypatch):
    """Находка, которая уже в GROW, не должна дублироваться на следующем прогоне.

    Контекст агента разработки не содержит текущего состояния секции GROW —
    он видит только репозиторий. Непочиненный edge case он доложит снова на
    следующем прогоне, и это правильно. Но найденная дважды одна и та же
    находка должна остаться записью одной, а не двумя.

    Сравнивается по заголовку: тело может отличаться формулировкой.
    """
    clone = _workspace(
        tmp_path, monkeypatch,
        "## Отрицательная цена позиции проходит в расчёт\n\n"
        "`subtotal` проверяет price < 0 уже после того, как qty умножен.\n")

    bodies = {13: (
        "Постановка.\n\n"
        "<!-- harness:grow:start -->\n"
        "## GROW — после прохождения HowToDemo\n\n"
        "- [ ] Отрицательная цена позиции проходит в расчёт — прежний вариант формулировки\n"
        "<!-- harness:grow:end -->\n"
    )}
    monkeypatch.setattr(activities_module.github_client, "get_issue_body",
                        lambda repo, n: bodies[n])
    monkeypatch.setattr(activities_module.github_client, "update_issue_body",
                        lambda repo, n, new: bodies.__setitem__(n, new))

    # Первый прогон (находка уже в GROW, но с другой формулировкой)
    result = asyncio.run(activities_module.collect_dev_followups(_issue()))

    # Функция должна вернуть пустой список, потому что находка уже записана
    # (по заголовку совпадает с тем, что в GROW)
    assert result == [], f"найденная дважды находка должна быть отброшена, но вернулась: {result}"

    section = issue_blocks.read(bodies[13], issue_blocks.GROW)
    # Проверяем, что заголовок есть только один раз
    count = section.count("Отрицательная цена позиции проходит в расчёт")
    assert count == 1, f"заголовок должен встречаться один раз, но встречается {count} раз(а)"
