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
    настоящий `github_client.post_comment` (единственная точка подписи).

    Третий круг ревью убрал у `ask_question` последнюю зависимость от ленты
    комментариев: признак «комментарий уже опубликован» с этого круга живёт
    в самом теле (`questions.Question.announced`), а не проверяется
    перебором ленты. Поэтому фикстура НЕ подменяет никакой функции чтения
    комментариев (ни `list_comments`, ни `list_recent_comments` — второй из
    них в клиентах вообще больше нет, см. `worker/github_client.py` и
    `worker/gitlab_client.py`). Если бы код `ask_question` всё же попытался
    прочитать ленту, вызов ушёл бы в диспетчер `forge` и упал бы —
    `list_recent_comments` у настоящего `github_client` удалена, а ничего
    другого он для неподменённого имени не подставит. Тест-фикстура сама
    служит проверкой того, что зависимость от ленты действительно убрана
    целиком, а не спрятана в другом методе с тем же эффектом.
    """
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


def test_question_lands_in_body_comment_and_label(github, issue):
    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?",
                                 ["было 404; стало 405", "то же плюс OPTIONS"])

    assert question_id == "howtodemo-1"
    stored = questions.read_open(github["body"])
    assert stored.id == "howtodemo-1"
    assert stored.kind == "howtodemo"
    assert stored.options == ("было 404; стало 405", "то же плюс OPTIONS")
    assert stored.announced is True
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
    assert questions.comment_marker("howtodemo-1") in comment


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


# --- третий круг ревью: признак «объявлено» в теле, а не в ленте ---

def test_resumes_comment_after_crash_between_body_write_and_comment(monkeypatch, github, issue):
    """Обрыв сразу после записи блока вопроса (шаг 1 из докстринга активности)
    — до самого первого круга правок второй вызов находил блок в теле,
    считал вопрос уже заданным и молча возвращал успех, ни разу не
    опубликовав комментарий. Признак `announced` остаётся `False`, пока
    комментарий не ушёл по-настоящему, — второй вызов обязан доделать
    именно недостающий комментарий, не создавая вопрос заново."""
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: (_ for _ in ()).throw(RuntimeError("сеть моргнула")))

    with pytest.raises(RuntimeError):
        a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    # Тело уже записано — то самое состояние, в котором вопрос раньше терялся.
    stored = questions.read_open(github["body"])
    assert stored is not None
    assert stored.announced is False
    assert github["comments"] == []
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: github["comments"].append(agent_comment.sign(body)))

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert question_id == "howtodemo-1"
    assert len(github["comments"]) == 1  # доделал недостающее, не задвоил тело
    assert questions.read_open(github["body"]).announced is True
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_duplicate_comment_if_crash_between_comment_and_flag(monkeypatch, github, issue):
    """Узкое окно, названное в докстринге `ask_question` (пункт 3): комментарий
    успешно ушёл, а запись признака `announced=True` в тело — следующий
    вызов `update_issue_body` — упала. Признак в сохранённом теле так и
    остался `False`, и повторный вызов, не отличая этот случай от «комментарий
    вообще не публиковался», честно публикует его ВТОРОЙ раз.

    Это ожидаемое, сознательно допущенное поведение, а не задача на починку:
    единственная альтернатива — проставлять признак ДО комментария — переносит
    риск обрыва на шаг раньше и снова прячет вопрос от человека НАВСЕГДА (тот
    самый дефект первого круга). Лишний комментарий в ленте несравнимо дешевле
    потерянного вопроса.
    """
    calls = {"n": 0}
    real_update = a.github_client.update_issue_body

    def flaky_update(repo, number, body):
        calls["n"] += 1
        if calls["n"] == 2:  # 1-й вызов пишет блок вопроса, 2-й — признак announced
            raise RuntimeError("сеть моргнула перед записью признака")
        real_update(repo, number, body)

    monkeypatch.setattr(a.github_client, "update_issue_body", flaky_update)

    with pytest.raises(RuntimeError):
        a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert len(github["comments"]) == 1
    assert questions.read_open(github["body"]).announced is False

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert question_id == "howtodemo-1"
    assert len(github["comments"]) == 2  # окно сработало — второй экземпляр в ленте, это ожидаемо
    assert questions.read_open(github["body"]).announced is True
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_resumes_label_after_crash_between_flag_and_label(monkeypatch, github, issue):
    """Комментарий ушёл, признак `announced=True` успешно записан, но
    `add_label` упал следом. Оба первых следствия уже настоящие — повторный
    вызов обязан доделать ТОЛЬКО метку, не трогая ни тело, ни комментарий."""
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: (_ for _ in ()).throw(RuntimeError("API упал")))

    with pytest.raises(RuntimeError):
        a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert len(github["comments"]) == 1
    assert questions.read_open(github["body"]).announced is True
    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]

    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: github["labels"].add(label))

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать эту задачу?", ["а"])

    assert question_id == "howtodemo-1"
    assert len(github["comments"]) == 1  # announced уже True — не задвоил комментарий
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_fully_completed_question_is_untouched_on_repeat_call(monkeypatch, github, issue):
    """Вопрос уже полностью выполнен — блок с `announced=True`, комментарий,
    метка. Новый вызов активности не должен трогать НИ ОДНО из трёх
    следствий: ни писать тело заново, ни публиковать второй комментарий, ни
    переставлять метку. Проверяется счётчиками вызовов, а не только длиной
    итоговых списков — так подмена не может случайно замаскировать лишний
    вызов, который ничего не изменил по счастливой случайности."""
    a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    assert len(github["comments"]) == 1
    assert questions.read_open(github["body"]).announced is True

    calls = {"body_writes": 0, "comments": 0, "labels": 0}
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: calls.__setitem__("body_writes", calls["body_writes"] + 1))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: calls.__setitem__("comments", calls["comments"] + 1))
    monkeypatch.setattr(a.github_client, "add_label",
                        lambda repo, number, label: calls.__setitem__("labels", calls["labels"] + 1))

    question_id = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])

    assert question_id == "howtodemo-1"
    assert calls == {"body_writes": 0, "comments": 0, "labels": 0}


def test_ask_question_ignores_comment_feed_entirely(github, issue):
    """Третий круг ревью чинил один и тот же дефект дважды именно потому, что
    признак «уже опубликовано» жил в ленте комментариев, а не в теле:
    сначала перебор брал первую (самую старую) страницу, потом прыжок на
    последнюю страницу терял маркер на ленте, где число комментариев на
    единицу больше кратного странице. С этого круга лента не читается
    вовсе — поведение обязано не зависеть от её длины НИКАК, а не просто
    «работать на распространённых длинах».

    500 — специально больше лимитов старой (удалённой) `list_recent_comments`
    (100 у GitHub, где раньше и терялась находка) и любого правдоподобного
    порога пагинации: тест не завязан на конкретное число, а проверяет само
    свойство «независимо от длины ленты».
    """
    github["comments"].extend(f"чужой комментарий №{n}" for n in range(500))

    first = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    assert len(github["comments"]) == 501  # 500 чужих + наш с вопросом

    second = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])

    assert second == first == "howtodemo-1"
    assert len(github["comments"]) == 501  # второй вызов не задвоил комментарий
    marker = questions.comment_marker("howtodemo-1")
    assert sum(marker in c for c in github["comments"]) == 1


def test_open_question_of_a_different_kind_is_a_conflict_not_a_reuse(github, issue):
    """Финальное ревью ветки, находка I5 (Important).

    Ранний возврат срабатывал на ЛЮБОМ открытом вопросе, не сверяя вид: если
    вопрос вида `howtodemo` уже открыт, а вызывают `ask_question` с видом
    `mvp-bounds` (второй потребитель механизма — спека обещает выбор из
    вариантов плана), активность БЕЗ ПРАВКИ молча вернула бы id ЧУЖОГО
    вопроса `howtodemo-1`, ничего не написав про `mvp-bounds` в тело и не
    опубликовав комментарий с его текстом и вариантами. Вызывающий код
    (воркфлоу) поставил бы этот чужой id себе в указатель, будучи уверенным,
    что свой вопрос задан, — а он просто пропал.

    Без правки этот тест падает дважды: `pytest.raises` не срабатывает
    (исключения нет), а `second == "howtodemo-1"` — id вопроса, который
    никто не спрашивал про `mvp-bounds`.
    """
    first = a.ask_question(issue, "howtodemo", "Чем принимать?", ["а"])
    assert first == "howtodemo-1"

    with pytest.raises(a.ConflictingOpenQuestion):
        a.ask_question(issue, "mvp-bounds", "Что входит в MVP?", ["только /quote"])

    # Открытый вопрос — по-прежнему исходный howtodemo, без следов mvp-bounds.
    stored = questions.read_open(github["body"])
    assert stored.id == "howtodemo-1"
    assert stored.kind == "howtodemo"
    assert len(github["comments"]) == 1  # второго комментария (про MVP) не было
