import pytest

import activities as a
from shared import labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="GET /quote отдаёт 404",
                      body="Сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями и метками в памяти."""
    state = {"body": issue.body, "comments": [], "labels": set()}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(body))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    return state


def test_question_lands_in_body_comment_and_label(github, issue):
    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?",
                                 ["было 404; стало 405", "то же плюс OPTIONS"])

    assert question_id == "howtodemo-1"
    stored = questions.read_open(github["body"])
    assert stored.id == "howtodemo-1"
    assert stored.kind == "howtodemo"
    assert stored.options == ("было 404; стало 405", "то же плюс OPTIONS")
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]
    assert len(github["comments"]) == 1


def test_comment_names_the_command_verbatim(github, issue):
    """Комментарий обязан назвать команду ответа дословно (A12).

    Отказ, ради которого это написано: приёмка отвечала «добавьте раздел
    HowToDemo» и не сказала, как отвечать, — это стоило впустую потраченного
    прогона разработки.
    """
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["вариант один"])
    comment = github["comments"][0]
    assert "/harness-answer" in comment
    assert "обычный комментарий" in comment.lower()
    assert "вариант один" in comment
    assert "<!-- issue-agent -->" in comment


def test_open_question_is_not_asked_twice(github, issue):
    """Вопрос уже висит — второй экземпляр в ленте только запутает (A13, A24)."""
    first = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    second = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])

    assert first == second == "howtodemo-1"
    assert len(github["comments"]) == 1


def test_second_question_of_the_same_kind_continues_numbering(github, issue):
    """Нумерация ведётся по журналу и переживает потерю прогона (A11)."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    github["body"] = questions.clear_open(github["body"])
    github["body"] = questions.append_decision(github["body"], questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="Чем принимать?",
        answer="405"))

    assert a.ask_question(issue, "howtodemo", "А теперь?", ["б"]) == "howtodemo-2"


def test_question_without_options_asks_for_free_text(github, issue):
    """Вариантов нет — комментарий всё равно объясняет, как ответить (A10)."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", [])
    comment = github["comments"][0]
    assert "/harness-answer" in comment
    assert questions.read_open(github["body"]).options == ()
