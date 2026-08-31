import pytest

import activities as a
from shared import agent_comment, labels, questions
from shared.workflow_types import IssueInput


@pytest.fixture
def issue():
    return IssueInput(repo="o/r", issue_number=7, title="t", body="описание",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def github(monkeypatch, issue):
    """Подменённый GitHub с телом, комментариями, метками и реакциями в памяти.

    `post_comment` сам подписывает тело (`agent_comment.sign`) — так же, как
    настоящий `github_client.post_comment` (единственная точка подписи, см.
    докстринг `answer_question` в `worker/activities.py`). Тот же приём, что
    и в фикстуре `github` из `tests/test_ask_question.py` (находка 5
    ревью): без него фикстура молча расходится с реальным поведением клиента,
    и тест, проверяющий что-то по маркеру подписи в тексте комментария, не
    заметил бы, что код сам подписывать НЕ должен (см. докстринг
    `answer_question`, абзац про `agent_comment.sign`).
    """
    state = {"body": issue.body, "comments": [], "labels": set(), "reactions": []}
    monkeypatch.setattr(a.github_client, "get_issue_body",
                        lambda repo, number: state["body"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, number, body: state.update(body=body))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, number, body: state["comments"].append(agent_comment.sign(body)))
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
    # Находка 4 ревью (Minor): признак `announced` в этой ветке проставляется
    # осознанно (см. комментарий в коде перед `mark_announced`), но раньше
    # это не проверялось ни одним утверждением — непроставленный признак
    # означал бы, что будущий `ask_question` для вопроса того же вида решит,
    # будто комментарий ещё не уходил, и опубликует его снова.
    assert reopened.announced is True


def test_body_write_failure_is_loud(github, issue, monkeypatch):
    """Доложить «принято», не записав, — худший класс отказов (A25)."""
    _open(github)

    def boom(repo, number, body):
        raise RuntimeError("GitHub 500")

    monkeypatch.setattr(a.github_client, "update_issue_body", boom)

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "1", 101)


# --- ревью: находки 1-3 (Important) и 6 (Minor) ---

def test_label_removal_failure_is_recovered_not_reasked(github, issue, monkeypatch):
    """Находка 1 ревью (Important). Запись решения в журнал и очистка блока
    вопроса в `_record_decision` идут одним обращением к телу — там нет
    промежуточного состояния. Снятие метки следом — отдельный сетевой вызов,
    который может упасть уже ПОСЛЕ того, как решение необратимо легло в
    журнал. Без починки следующий вызов с тем же `question_id` увидел бы
    «открытого вопроса нет» и ушёл бы в ветку «вопрос пропал»: опубликовал
    бы комментарий про недействительные варианты и заново повесил метку —
    хотя ответ уже записан. Без правки в `worker/activities.py` этот тест
    падает: вторая попытка возвращает `reasked` и добавляет лишний
    комментарий вместо того, чтобы просто снять метку и доложить «принято»."""
    _open(github)

    def boom(repo, number, label):
        raise RuntimeError("GitHub 500")

    monkeypatch.setattr(a.github_client, "remove_label", boom)

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "1", 101)

    # Решение уже необратимо в журнале, вопрос закрыт, метка ещё висит.
    journal_after_crash = questions.read_journal(github["body"])
    assert [d.answer for d in journal_after_crash] == ["было 404; стало 405"]
    assert questions.read_open(github["body"]) is None
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]

    monkeypatch.setattr(a.github_client, "remove_label",
                        lambda repo, number, label: github["labels"].discard(label))

    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "accepted"

    assert labels.NEEDS_HUMAN_ANSWER not in github["labels"]
    # Журнал не задвоился повторной записью, новый вопрос не завёлся, и про
    # «недействительные варианты» человеку ничего не сказали.
    assert questions.read_journal(github["body"]) == journal_after_crash
    assert questions.read_open(github["body"]) is None
    assert github["comments"] == []


def test_huge_digit_answer_does_not_crash_the_activity(github, issue):
    """Находка 2 ревью (Important). `str.isdigit()` истинен и для строки в
    тысячи цифр, но `int()` на такой строке в Python 3.12 бросает
    `ValueError: Exceeds the limit (4300 digits)...` — проверено прямым
    запуском. У вопроса не бывает больше трёх вариантов, а граница «номер
    против свободного текста» обязана выдерживать любую строку. Без правки
    этот тест падает необработанным `ValueError`, а не одним из объявленных
    исходов активности."""
    _open(github)
    huge = "9" * 5000

    assert a.answer_question(issue, "howtodemo-1", huge, 101) == "confirm"
    assert questions.read_open(github["body"]) is not None
    assert questions.read_journal(github["body"]) == []


def test_stale_question_id_is_not_silently_accepted(github, issue):
    """Находка 3 ревью (Important). Как только в теле нашёлся открытый
    вопрос, код работал с ним, не сверяя id с тем, что пришёл в вызов. Если
    к моменту обработки открыт уже ДРУГОЙ вопрос (например, после
    возрождения, которое меняет id), число из устаревшей команды не должно
    молча зачитываться ответом на текущий вопрос исходом «принято». Сейчас
    это не стреляет только потому, что воркфлоу ещё не зовёт активность
    (при подключении в следующих задачах — выстрелит). Без правки этот тест
    падает: `"1"` тихо принимается как ответ на вопрос "howtodemo-1", хотя
    вызов пришёл со старым id "howtodemo-0"."""
    _open(github)  # открытый вопрос сейчас — "howtodemo-1"

    result = a.answer_question(issue, "howtodemo-0", "1", 101)

    assert result != "accepted"
    assert questions.read_journal(github["body"]) == []
    stored = questions.read_open(github["body"])
    assert stored is not None and stored.id == "howtodemo-1"
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_empty_command_without_comment_id_does_not_crash(github, issue):
    """Находка 6 ревью (Minor). Пустая команда может прийти без comment_id
    (`add_reaction` тогда ставить не на что) — ветка охраняет это условием
    `comment_id is not None`, но до этой правки случай не был покрыт тестом."""
    _open(github)

    assert a.answer_question(issue, "howtodemo-1", "", None) == "empty"

    assert github["reactions"] == []
    assert github["comments"] == []
    assert questions.read_open(github["body"]) is not None
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]


def test_empty_command_delivered_twice_keeps_question_open(github, issue):
    """Находка 6 ревью (Minor). Тот же пустой комментарий доставлен дважды
    (повтор доставки вебхука) — вопрос остаётся открытым оба раза, ветка не
    ломается и не путает состояние при повторном вызове с тем же comment_id."""
    _open(github)

    assert a.answer_question(issue, "howtodemo-1", "", 101) == "empty"
    assert a.answer_question(issue, "howtodemo-1", "", 101) == "empty"

    assert github["reactions"] == ["confused", "-1", "confused", "-1"]
    assert questions.read_open(github["body"]) is not None
    assert labels.NEEDS_HUMAN_ANSWER in github["labels"]
