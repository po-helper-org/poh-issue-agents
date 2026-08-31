"""Прямые тесты на тела активностей, которые второй круг финального ревью
нашёл ПОКРЫТЫМИ ТОЛЬКО заглушками по имени в `tests/test_workflow_final_
review_gate_findings.py` (находка F5, Important): `read_open_question_id`,
`report_answer_question_failure`, `close_answered_by_body_edit` — их
настоящие тела не исполнялись НИ РАЗУ, только имя активности регистрировалось
в Worker'е тестового окружения под заглушкой. Находка F1 — прямое следствие:
прямой тест на частичный отказ `close_answered_by_body_edit` (см. ниже) его
бы поймал сразу.

Заодно — `report_question_repoint_failure` и `report_question_close_failure`
(новые активности этого же круга правок, находки F9 и F6).

Модель здесь не зовётся никогда: все проверяемые активности — сеть (GitHub,
Sentry) и разбор тела, ни одна не обращается к `llm`.
"""

import pytest

import activities as a
from shared import agent_comment, issue_blocks, labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="GET /quote отдаёт 404",
                      body="Сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями и метками в памяти — тот же
    приём, что в `tests/test_ask_question.py` (см. её докстринг фикстуры)."""
    state = {"body": issue.body, "comments": [], "labels": set()}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(agent_comment.sign(body)))
    monkeypatch.setattr(a.github_client, "get_issue",
                        lambda repo, number: {"labels": [{"name": l} for l in state["labels"]]})
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    return state


# --- read_open_question_id (F5) ---

def test_read_open_question_id_reports_the_currently_open_question(github, issue):
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="howtodemo-3", kind="howtodemo", text="Чем принимать?", options=()))
    assert a.read_open_question_id(issue) == "howtodemo-3"


def test_read_open_question_id_is_empty_without_an_open_question(github, issue):
    assert a.read_open_question_id(issue) == ""


# --- report_answer_question_failure (F5) ---

def test_report_answer_question_failure_posts_a_comment_with_retry_hint(github, issue):
    a.report_answer_question_failure(issue, "TimeoutError: GitHub API недоступен")
    assert len(github["comments"]) == 1
    assert "Не смог обработать ответ на вопрос" in github["comments"][0]
    assert "ещё раз" in github["comments"][0]


# --- close_answered_by_body_edit: обычный путь + F8 ---

def test_close_answered_by_body_edit_closes_the_question_and_records_the_criterion(
        github, issue):
    """Критерий вписан ЗАГОЛОВКОМ (не командой `/harness-answer`) — путь A23.

    Граница `## Конец` после сценария — иначе секция HowToDemo без соседнего
    заголовка того же уровня утянула бы в себя весь ХВОСТ тела, дописанный
    НИЖЕ (сырой HTML-блок открытого вопроса), и «критерием» стал бы кусок
    разметки, а не сам сценарий — граница ищется по заголовку, а не по
    HTML-маркерам блока вопроса (см. `_howtodemo_heading_end`).
    """
    github["body"] += ("\n\n## HowToDemo\n\nОткрываю /quote, вижу 405 с Allow: POST"
                       "\n\n## Конец")
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="howtodemo-1", kind="howtodemo", text="Чем принимать?", options=()))
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)

    a.close_answered_by_body_edit(issue)

    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]
    journal = questions.read_journal(github["body"])
    assert len(journal) == 1
    assert journal[0].answer == "Открываю /quote, вижу 405 с Allow: POST"
    # Находка F8 (Minor): критерий взят из заголовка, а не из размеченного
    # блока, — запись не обязана (и не должна) создавать второй, размеченный
    # экземпляр того же текста, иначе он получил бы приоритет над заголовком
    # при следующем чтении (`_howtodemo_block` смотрит на блок ПЕРВЫМ), и
    # дальнейшие правки заголовка человеком молча перестали бы учитываться.
    assert issue_blocks.read(github["body"], issue_blocks.HOWTODEMO) is None


def test_close_answered_by_body_edit_is_a_noop_without_open_question_or_label(
        github, issue):
    calls = []
    a.github_client.update_issue_body = lambda repo, number, body: calls.append(body)

    a.close_answered_by_body_edit(issue)

    assert calls == []
    assert github["labels"] == set()


def test_close_answered_by_body_edit_finishes_a_dangling_label_after_partial_failure(
        github, issue):
    """Находка F1 (Important, второй круг финального ревью) — тест падает
    БЕЗ правки.

    `_record_decision` пишет тело ОДНИМ обращением и снимает метку
    `NEEDS_HUMAN_ANSWER` СЛЕДУЮЩИМ, отдельным сетевым вызовом. Тело здесь
    уже в состоянии «после записи» (открытого вопроса нет), а метка — в
    состоянии «до снятия» (ещё висит), то есть ровно то, что осталось бы
    после обрыва предыдущей попытки МЕЖДУ этими двумя вызовами.

    Без правки функция видит `question is None` и молча возвращается — метка
    остаётся висеть НАВСЕГДА, потому что `_start_development` эту активность
    для этой задачи больше не позовёт (задача уже ушла в разработку). Тест
    падает на `assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]`.
    """
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)  # тело уже «закрыто», метка — нет

    a.close_answered_by_body_edit(issue)

    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]


# --- report_question_repoint_failure (F9, новая активность этого круга) ---

def test_report_question_repoint_failure_is_sentry_only_without_a_comment(github, issue):
    """Находка F9: событие Sentry, БЕЗ второго, спорящего комментария — тот,
    что относится к самому ответу («вопрос пропал» / вердикт активности),
    уже ушёл раньше (см. докстринг активности)."""
    a.report_question_repoint_failure(issue, "RuntimeError: тело недоступно")
    assert github["comments"] == []


# --- report_question_close_failure (F6, новая активность этого круга) ---

def test_report_question_close_failure_posts_a_comment(github, issue):
    a.report_question_close_failure(issue, "RuntimeError: сеть недоступна")
    assert len(github["comments"]) == 1
    comment = github["comments"][0].lower()
    assert "не смог снять устаревший вопрос" in comment
    assert "needs-human:answer" in comment
