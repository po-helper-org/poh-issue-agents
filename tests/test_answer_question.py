import pytest

import activities as a
from shared import labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="t", body="описание",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    state = {"body": issue.body, "comments": [], "labels": set(), "reactions": []}
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
    monkeypatch.setattr(a.github_client, "add_reaction",
                        lambda repo, comment_id, content:
                            state["reactions"].append(content))
    return state


def _open(github, options=("было 404; стало 405", "то же плюс OPTIONS")):
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="howtodemo-1", kind="howtodemo", text="Чем принимать?", options=options))
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)


def test_number_records_the_decision_immediately(github, issue):
    """Номер — толкования не было, подтверждать нечего (A14)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "accepted"

    journal = questions.read_journal(github["body"])
    assert [d.answer for d in journal] == ["было 404; стало 405"]
    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]


def test_number_out_of_range_is_free_text(github, issue):
    """`/harness-answer 7` при двух вариантах — это не выбор (A16)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "7", 101) == "confirm"
    assert questions.read_open(github["body"]) is not None


def test_empty_command_reacts_and_keeps_the_question_open(github, issue):
    """Пустая команда — оговорка. Реакции, не абзац (A17)."""
    _open(github)
    assert a.answer_question(issue, "howtodemo-1", "", 101) == "empty"

    assert set(github["reactions"]) == {"confused", "-1"}
    assert github["comments"] == []
    assert questions.read_open(github["body"]) is not None
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_answer_without_open_question_says_so(github, issue):
    """Молчание неотличимо от проглоченной команды (A18)."""
    assert a.answer_question(issue, "", "1", 101) == "no-question"
    assert len(github["comments"]) == 1
    assert "вопрос" in github["comments"][0].lower()


def test_missing_block_reasks_without_the_model(github, issue, monkeypatch):
    """Блок стёрт руками — новый вопрос свободным текстом, без модели (A22)."""
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)

    def no_model(*args, **kwargs):
        raise AssertionError("модель звать нельзя")

    monkeypatch.setattr(a, "_interpret_answer", no_model, raising=False)

    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "reasked"

    reopened = questions.read_open(github["body"])
    assert reopened is not None
    assert reopened.id != "howtodemo-1", "новый вопрос — новый идентификатор"
    assert reopened.options == (), "варианты не перегенерируются"
    assert "недействительн" in github["comments"][0].lower()


def test_body_write_failure_is_loud(github, issue, monkeypatch):
    """Доложить «принято», не записав, — худший класс отказов (A25)."""
    _open(github)

    def boom(repo, number, body):
        raise RuntimeError("GitHub 500")

    monkeypatch.setattr(a.github_client, "update_issue_body", boom)

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "1", 101)
