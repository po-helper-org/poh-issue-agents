"""Прямые тесты на тела новых уведомляющих активностей второго круга
финального ревью — `report_question_close_failure` (находка F6),
`report_question_repoint_failure` (находка F9) — и (следующим коммитом этой
же ветки) трёх уже существовавших активностей, покрытых только заглушками по
имени в `tests/test_workflow_final_review_gate_findings.py` (находка F5).

Модель здесь не зовётся никогда: все проверяемые активности — сеть (GitHub,
Sentry) и разбор тела, ни одна не обращается к `llm`.
"""

import pytest

import activities as a
from shared import agent_comment
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


# --- report_question_close_failure (F6, новая активность этого круга) ---

def test_report_question_close_failure_posts_a_comment(github, issue):
    a.report_question_close_failure(issue, "RuntimeError: сеть недоступна")
    assert len(github["comments"]) == 1
    comment = github["comments"][0].lower()
    assert "не смог снять устаревший вопрос" in comment
    assert "needs-human:answer" in comment


# --- report_question_repoint_failure (F9, новая активность этого круга) ---

def test_report_question_repoint_failure_is_sentry_only_without_a_comment(github, issue):
    """Находка F9: событие Sentry, БЕЗ второго, спорящего комментария — тот,
    что относится к самому ответу («вопрос пропал» / вердикт активности),
    уже ушёл раньше (см. докстринг активности)."""
    a.report_question_repoint_failure(issue, "RuntimeError: тело недоступно")
    assert github["comments"] == []
