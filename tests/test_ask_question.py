import pytest

import activities as a
from shared import agent_comment, labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="GET /quote отдаёт 404",
                      body="Сейчас 404, ожидается 405", author_login="u",
                      author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями и метками в памяти.

    `post_comment` сам подписывает тело (`agent_comment.sign`) — так же, как
    настоящий `github_client.post_comment` (единственная точка подписи,
    ревью, находка 3). Подмена целиком, без этого шага, не заметила бы
    пропажи явной подписи в самой активности, и тест на подпись комментария
    проверял бы то, чего в проде не происходит.

    `list_recent_comments`/`get_issue` читают ту же память: активность
    сверяется по ним, чтобы не задвоить комментарий и метку при повторном
    вызове (ревью, находки 1 и 2).

    Повторное ревью, находка (Important). Раньше здесь стоял мок
    `list_comments`, игнорировавший `limit` и всегда возвращавший ВСЮ
    историю — то есть расходившийся с настоящей функцией именно в том
    поведении (усечение по странице), от которого зависит корректность
    проверки «комментарий уже есть». Такой мок не мог поймать находку про
    длинную ленту: он был честнее прода. Активность теперь зовёт
    `list_recent_comments`, и подмена усекает список так же, как настоящая
    функция читает последнюю страницу ленты — отдаёт ПОСЛЕДНИЕ `limit`
    комментариев, а не весь список.
    """
    state = {"body": issue.body, "comments": [], "labels": set()}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(agent_comment.sign(body)))
    monkeypatch.setattr(a.github_client, "list_recent_comments",
                        lambda repo, number, limit=100: [{"body": c} for c in state["comments"]][-limit:])
    monkeypatch.setattr(a.github_client, "get_issue",
                        lambda repo, number: {"labels": [{"name": l} for l in state["labels"]]})
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


# --- ревью: обрыв между следствиями не должен прятать вопрос навсегда ---

def test_resumes_comment_after_crash_between_body_write_and_comment(monkeypatch, github, issue):
    """Находка 1 (Critical). Обрыв сразу после записи тела — до правки второй
    вызов находил блок вопроса в теле, считал вопрос уже заданным и молча
    возвращал успех, ни разу не опубликовав комментарий. Человек не видел
    вообще ничего: тело с сырым JSON ему не адресовано, метки нет, задача
    выпала из очереди — и не находилась в ней уже никогда."""
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: (_ for _ in ()).throw(RuntimeError("сеть моргнула")))

    with pytest.raises(RuntimeError):
        a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    # Тело уже записано — то самое состояние, в котором вопрос раньше терялся.
    assert questions.read_open(github["body"]) is not None
    assert github["comments"] == []
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: github["comments"].append(agent_comment.sign(body)))

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert question_id == "howtodemo-1"
    assert len(github["comments"]) == 1  # доделал недостающее, не задвоил тело
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_resumes_label_after_crash_between_comment_and_label(monkeypatch, github, issue):
    """Находка 2 (Important). Комментарий ушёл, `add_label` упал — до правки
    метка не появлялась никогда: второй вызов находил блок вопроса в теле и
    возвращался, не пытаясь ни поставить метку, ни (по счастью здесь) выслать
    второй комментарий. Задача выпадает из выборки `label:needs-human:*`,
    которая обязана быть полной очередью к людям."""
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: (_ for _ in ()).throw(RuntimeError("API упал")))

    with pytest.raises(RuntimeError):
        a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert len(github["comments"]) == 1
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: github["labels"].add(label))

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert question_id == "howtodemo-1"
    assert len(github["comments"]) == 1  # не задвоил комментарий
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_open_question_not_reasked_on_issue_with_long_comment_history(github, issue):
    """Повторное ревью, находка (Important). `github_client.list_comments` без
    пагинации читает страницу 1 — то есть самые СТАРЫЕ комментарии ленты.
    На задаче, где до вопроса накопилось больше её лимита чужих комментариев,
    свежий комментарий с вопросом в эту выборку никогда не попадёт — и
    повторный вызов `ask_question`, не найдя его, опубликует вопрос ВТОРОЙ
    раз. Это подрывает ровно то свойство, которое чинила прошлая правка
    (находки 1 и 2): идемпотентность по следствию «комментарий».

    Число чужих комментариев (120) нарочно больше и лимита `list_comments`
    (50), и лимита `list_recent_comments` (100) — тест не завязан на
    конкретное число, а проверяет само свойство «независимо от длины ленты»."""
    github["comments"].extend(f"чужой комментарий №{n}" for n in range(120))

    first = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    assert len(github["comments"]) == 121  # 120 чужих + наш с вопросом

    second = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])

    assert second == first == "howtodemo-1"
    assert len(github["comments"]) == 121  # второй вызов не задвоил комментарий
    marker = questions.comment_marker("howtodemo-1")
    assert sum(marker in c for c in github["comments"]) == 1
