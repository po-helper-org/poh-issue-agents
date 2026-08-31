"""Сквозной путь: вопрос, ответ, журнал, критерий у исполнителя.

Отказ, ради которого затеяна работа: poh-demo-checkout#163 прошёл разработку
целиком, а критерий приёмки так и не доехал — сценарий в теле был, но контур
его не увидел и никого не спросил. Там причиной был конкретно распознаватель
заголовка (не узнавал русское «## Как принимаем») — это закрыто отдельно, и
тело задачи ниже вообще без заголовка. Этот тест воспроизводит более общую
часть того же отказа — страховочный путь: когда сценарий не находится НИКАК,
гейт обязан спросить человека, а не пропустить задачу молча.

Тест идёт по активностям, а не по воркфлоу: цикл проверен в Task 8, здесь
важно, что решение доезжает до потребителя и накапливается в задаче.

Фикстуры `issue`/`github` — своя копия, а не импорт из `tests/test_ask_
question.py` или `tests/test_answer_question.py` (там те же по смыслу, но
pytest не подтягивает фикстуры между тестовыми модулями сам по себе).
"""

import pytest

import activities as a
from shared import agent_comment, issue_blocks, labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=163,
                      title="GET /quote отдаёт 404 вместо 405",
                      body="Сейчас 404 про файл, ожидается 405 с Allow: POST",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями, метками и реакциями в памяти.

    `post_comment` подписывает тело `agent_comment.sign(...)`, как настоящий
    `github_client.post_comment` (единственная точка подписи, см. докстринг
    `ask_question`/`answer_question` в `worker/activities.py`) — тот же приём,
    что в фикстурах `tests/test_ask_question.py` и `tests/test_answer_
    question.py`: без него фикстура молча разошлась бы с реальным клиентом.

    `get_issue` обязателен: `ask_question` читает ТЕКУЩИЙ список меток именно
    через него (`github_client.get_issue(...).get("labels", [])`), а не через
    множество `state["labels"]` напрямую. Черновик задачи в
    `.superpowers/sdd/task-9-brief.md` этот мок не подменял — со сквозным
    прогоном по нынешней `ask_question` (задачи 4-8 её с тех пор дважды
    правили) тест падал бы `AttributeError`/сетевым вызовом на самом первом
    `ask_question`, а не там, где написан замысел проверки.
    """
    state = {"body": issue.body, "comments": [], "labels": set(), "reactions": []}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body:
                            state["comments"].append(agent_comment.sign(body)))
    monkeypatch.setattr(a.github_client, "get_issue",
                        lambda repo, number:
                            {"labels": [{"name": l} for l in state["labels"]]})
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: state["labels"].add(label))
    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: state["labels"].discard(label))
    monkeypatch.setattr(a.github_client, "add_reaction",
                        lambda repo, comment_id, content, issue_number=None:
                            state["reactions"].append(content))
    return state


def test_full_path_question_answer_journal_criterion(github, issue):
    """Четыре факта одним прогоном:

    1. до ответа критерия нет — гейт задачу не пропустил бы;
    2. вопрос задан, назвал команду, повесил метку;
    3. пустая команда получила реакции и вопрос не закрыла;
    4. ответ номером записал решение в журнал И в блок критерия.
    """
    assert a.read_acceptance_criterion(issue) == ""

    question_id = a.ask_question(
        issue, "howtodemo",
        "Не вижу, чем принимать эту задачу.",
        ["было — 404 про файл; стало — 405 с Allow: POST",
         "было — 404 про файл; стало — 405 на любой метод кроме POST"])

    assert question_id == "howtodemo-1"
    assert "/harness-answer" in github["comments"][0]
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]

    assert a.answer_question(issue, question_id, "", 101) == "empty"
    assert set(github["reactions"]) == {"confused", "-1"}
    assert questions.read_open(github["body"]) is not None

    assert a.answer_question(issue, question_id, "1", 102) == "accepted"

    journal = questions.read_journal(github["body"])
    assert [d.question_id for d in journal] == ["howtodemo-1"]
    assert "405 с Allow: POST" in journal[0].answer
    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    criterion = a.read_acceptance_criterion(issue)
    assert "405 с Allow: POST" in criterion
    assert issue_blocks.read(github["body"], issue_blocks.HOWTODEMO) == criterion

    # Дальше по пути критерий должен доехать до `.harness/howtodemo.md` у
    # исполнителя — но эту запись делает `_dev_prepare` (`worker/
    # activities.py`) поверх настоящего git-клона задачи, а не активности
    # вопроса/ответа, проверяемые здесь. Гонять здесь `_dev_prepare` ради
    # одной строки значило бы тащить в этот тест клон репозитория и всю его
    # подготовку — дублирование другого теста, а не проверка. Этот шаг уже
    # проверен по-настоящему (реальный вызов `_dev_prepare`, реальный файл в
    # клоне): tests/test_dev_task_assembly.py::
    # test_howtodemo_scenario_reaches_the_harness_file.


def test_second_question_after_the_first_is_closed(github, issue):
    """Один открытый вопрос за раз; счётчик номера — свой у каждого вида
    вопроса (`shared.questions.next_question_id` считает максимум ПО ЭТОМУ
    `kind` в журнале, а не сквозную нумерацию всех вопросов задачи), поэтому
    первый вопрос вида `mvp-bounds` получает `-1`, а не продолжает номер
    вопроса вида `howtodemo`."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["вариант"])
    a.answer_question(issue, "howtodemo-1", "1", 101)

    second = a.ask_question(issue, "mvp-bounds", "Что входит в MVP?", ["только /quote"])
    assert second == "mvp-bounds-1"
    assert questions.read_open(github["body"]).id == "mvp-bounds-1"
    assert len(questions.read_journal(github["body"])) == 1
