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


def test_free_text_shows_interpretation_and_waits(github, issue, monkeypatch):
    """Свободный текст — толкование предъявлено, решение НЕ записано (A15)."""
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
                        lambda question, journal, answer:
                            a.answer_interpretation.Interpretation(
                                answer="405 на любой метод кроме POST"))

    assert a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101) == "confirm"
    assert "405 на любой метод кроме POST" in github["comments"][0]
    assert questions.read_journal(github["body"]) == []


def test_confirmation_records_answer_and_amendments(github, issue, monkeypatch):
    """Второй ответ применяет и решение, и правки прежних записей (A20, A21)."""
    github["body"] = questions.append_decision(github["body"], questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="Чем принимать?",
        answer="старое решение"))
    github["body"] = questions.write_open(github["body"], questions.Question(
        id="mvp-bounds-1", kind="mvp-bounds", text="Что в MVP?", options=()))
    github["labels"].add(labels.NEEDS_HUMAN_ANSWER)

    monkeypatch.setattr(a, "_interpret_answer",
                        lambda question, journal, answer:
                            a.answer_interpretation.Interpretation(
                                answer="только /quote",
                                amendments=[a.answer_interpretation.Amendment(
                                    question_id="howtodemo-1", answer="наоборот")]))

    assert a.answer_question(issue, "mvp-bounds-1", "только /quote, а то — наоборот", 101) == "confirm"
    assert a.answer_question(issue, "mvp-bounds-1", "да", 102) == "accepted"

    journal = questions.read_journal(github["body"])
    assert len(journal) == 3, "старая запись осталась, добавились две новые"
    live = {d.question_id: d.answer for d in questions.effective(journal)}
    assert live["mvp-bounds-1"] == "только /quote"
    assert "наоборот" in " ".join(live.values())
    assert "старое решение" in " ".join(d.answer for d in journal), \
        "отменённая запись видна в журнале"


def test_model_failure_keeps_the_question_open(github, issue, monkeypatch):
    """Модель отказала — вопрос стоит, человек получает честный текст."""
    _open(github)

    def boom(question, journal, answer):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(a, "_interpret_answer", boom)

    assert a.answer_question(issue, "howtodemo-1", "какой-то текст", 101) == "confirm"
    assert "не смог" in github["comments"][0].lower()
    assert questions.read_open(github["body"]) is not None


def test_superscript_digit_is_free_text_not_option_number(github, issue):
    """Правка 1 ревью (Important). `str.isdigit()` возвращает True для
    надстрочной единицы ¹ (U+00B9), но `int('¹')` бросает ValueError. Замена
    на `str.isdecimal()` отсеивает такие символы, и они трактуются как
    свободный текст, а не как номер варианта. Эти символы приезжают
    копипастом из нумерованных списков сторонних приложений."""
    _open(github)

    # Надстрочная единица, которая проходит isdigit() но не isdecimal()
    assert a.answer_question(issue, "howtodemo-1", "¹", 101) == "confirm"

    # Свободный текст, а не решение: вопрос остаётся открытым, в журнал ничего не записалось
    assert questions.read_open(github["body"]) is not None
    assert questions.read_journal(github["body"]) == []


# --- ревью по итогам brief'а task-6: черновик показан раньше, чем подтверждён (находки 1-3) ---

def test_retry_does_not_apply_unseen_interpretation(github, issue, monkeypatch):
    """Находка 1 (Critical). Ретрай применяет толкование, которого человек не видел.

    Черновик пишется в тело РАНЬШЕ, чем уходит комментарий. Если публикация
    комментария падает (сеть, отказ GitHub), активность падает следом, а
    Temporal повторяет её ТЕМИ ЖЕ аргументами — тем же `question_id` и тем же
    текстом. Без правки повторный вызов находил в теле уже записанный
    черновик и, не различая «черновик показан» и «черновик просто записан»,
    считал это ВТОРЫМ ответом человека — фиксировал решение и закрывал
    вопрос, хотя комментарий с толкованием так и не ушёл ни разу.

    Без правки в `worker/activities.py` этот тест падает: второй вызов
    (ретрай) возвращает `accepted`, журнал не пуст, а комментарий за всё
    время так и не был отправлен.
    """
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
        lambda question, journal, answer:
            a.answer_interpretation.Interpretation(answer="405 на любой метод кроме POST"))
    monkeypatch.setattr(a.github_client, "post_comment",
        lambda repo, number, body: (_ for _ in ()).throw(RuntimeError("сеть моргнула")))

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101)

    # Черновик уже лежит в теле, но человеку он ни разу не показан.
    draft = questions.read_draft(github["body"])
    assert draft is not None and draft.announced is False
    assert github["comments"] == []
    assert questions.read_journal(github["body"]) == []
    assert questions.read_open(github["body"]) is not None

    # "Второй вызов" здесь — ретрай Temporal, не второй ответ человека:
    # аргументы те же самые. Модель на неотправленный черновик звать нельзя —
    # толкование уже посчитано, недостающая часть — публикация.
    def no_model(*args, **kwargs):
        raise AssertionError("на неотправленный черновик модель звать нельзя")

    monkeypatch.setattr(a, "_interpret_answer", no_model)
    monkeypatch.setattr(a.github_client, "post_comment",
        lambda repo, number, body: github["comments"].append(agent_comment.sign(body)))

    result = a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101)

    assert result == "confirm"
    assert len(github["comments"]) == 1
    assert questions.read_journal(github["body"]) == []
    assert questions.read_open(github["body"]) is not None
    assert questions.read_draft(github["body"]).announced is True


def test_duplicate_comment_if_crash_between_comment_and_announce(github, issue, monkeypatch):
    """Узкое окно, названное в докстринге `_announce_draft` (постановка задачи
    прямо требует: назвать окно в комментарии к коду и покрыть тестом, как
    сделано для `ask_question`). Комментарий с толкованием успешно уходит, а
    следующий `update_issue_body` — запись признака `announced=True` — падает.
    В сохранённом теле признак так и остался `False`, и повторный вызов, не
    отличая этот случай от «комментарий вообще не публиковался», честно
    публикует его ВТОРОЙ раз.

    Сознательно допустимое поведение, а не дефект: тот же компромисс, что и
    в `ask_question` (`test_duplicate_comment_if_crash_between_comment_and_flag`
    в `tests/test_ask_question.py`). Альтернатива — проставлять признак ДО
    комментария — переносит риск обрыва на шаг раньше и возвращает дефект
    находки 1 (черновик, применённый без показа), что несравнимо хуже
    лишнего комментария в ленте.
    """
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
        lambda question, journal, answer:
            a.answer_interpretation.Interpretation(answer="405 на любой метод кроме POST"))

    calls = {"n": 0}
    real_update = a.github_client.update_issue_body

    def flaky_update(repo, number, body):
        calls["n"] += 1
        if calls["n"] == 2:  # 1-й вызов пишет черновик непоказанным, 2-й — признак announced
            raise RuntimeError("сеть моргнула перед записью признака")
        real_update(repo, number, body)

    monkeypatch.setattr(a.github_client, "update_issue_body", flaky_update)

    with pytest.raises(RuntimeError):
        a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101)

    assert len(github["comments"]) == 1
    assert questions.read_draft(github["body"]).announced is False

    def no_model(*args, **kwargs):
        raise AssertionError("на уже посчитанное толкование модель звать нельзя")

    monkeypatch.setattr(a, "_interpret_answer", no_model)
    monkeypatch.setattr(a.github_client, "update_issue_body", real_update)

    result = a.answer_question(issue, "howtodemo-1", "405 везде кроме POST", 101)

    assert result == "confirm"
    assert len(github["comments"]) == 2  # окно сработало — второй экземпляр в ленте, это ожидаемо
    assert questions.read_draft(github["body"]).announced is True


def test_direct_number_answer_clears_leftover_draft_of_the_same_question(github, issue, monkeypatch):
    """Находка 2 (Critical), первая защита — очистка черновика при записи
    решения (`_record_decision`). Вопрос сперва получил свободный ответ
    (черновик записан и показан), но вместо подтверждения человек ответил на
    ТОТ ЖЕ вопрос номером варианта — решение уходит в обход черновика.

    Без правки `_record_decision` черновик не трогает вовсе: он остаётся
    висеть в теле уже без открытого вопроса, к которому относился, и готов
    перехватить следующий свободный ответ на любой другой вопрос задачи (см.
    следующий тест). Этот тест проверяет ближний, наблюдаемый прямо здесь
    симптом: без правки черновик переживает решение, записанное в обход него.
    """
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
        lambda question, journal, answer:
            a.answer_interpretation.Interpretation(answer="было 405, а не 404"))

    assert a.answer_question(issue, "howtodemo-1", "какой-то текст", 101) == "confirm"
    assert questions.read_draft(github["body"]) is not None

    # Вместо подтверждения — номер варианта на тот же вопрос.
    assert a.answer_question(issue, "howtodemo-1", "1", 102) == "accepted"

    assert questions.read_draft(github["body"]) is None, \
        "черновик обязан исчезнуть вместе с вопросом, которому он принадлежал"
    journal = questions.read_journal(github["body"])
    assert [d.answer for d in journal] == ["было 404; стало 405"]


def test_stale_draft_does_not_hijack_answer_to_a_different_question(github, issue, monkeypatch):
    """Находка 2 (Critical), вторая защита — привязка черновика к своему
    вопросу (`Draft.question_id`). Она нужна не только как страховка от
    забывчивости `_record_decision`: если вопрос пропадает из тела ДО того,
    как висящий черновик подтверждён (человек стёр раздел руками), вопрос
    возрождается под НОВЫМ id (`answer_question`, ветка "reasked"), а
    решения по старому вопросу так и не было — `_record_decision` тут ни
    разу не срабатывает, чистить черновик некому.

    Без привязки по `question_id` черновик, оставшийся от пропавшего
    вопроса, читался бы как черновик ВОЗРОЖДЁННОГО вопроса просто потому,
    что в теле он один. Без правки этот тест падает: последний вызов
    возвращает `accepted` со СТАРЫМ текстом, модель для НОВОГО свободного
    ответа ни разу не позвана.
    """
    _open(github)
    monkeypatch.setattr(a, "_interpret_answer",
        lambda question, journal, answer:
            a.answer_interpretation.Interpretation(answer="СТАРОЕ толкование пропавшего вопроса"))

    assert a.answer_question(issue, "howtodemo-1", "какой-то текст", 101) == "confirm"
    draft_before = questions.read_draft(github["body"])
    assert draft_before is not None and draft_before.question_id == "howtodemo-1"

    # Раздел вопроса стёрли руками, черновик остался болтаться без него.
    github["body"] = questions.clear_open(github["body"])

    # Активность видит пропажу и возрождает вопрос под НОВЫМ id.
    assert a.answer_question(issue, "howtodemo-1", "1", 101) == "reasked"
    revived = questions.read_open(github["body"])
    assert revived.id != "howtodemo-1"

    monkeypatch.setattr(a, "_interpret_answer",
        lambda question, journal, answer:
            a.answer_interpretation.Interpretation(answer="НОВОЕ толкование возрождённого вопроса"))

    result = a.answer_question(issue, revived.id, "новый ответ", 104)

    assert result == "confirm"
    assert questions.read_journal(github["body"]) == []
    new_draft = questions.read_draft(github["body"])
    assert new_draft.question_id == revived.id
    assert new_draft.interpretation["answer"] == "НОВОЕ толкование возрождённого вопроса"


def test_correction_after_interpretation_is_reinterpreted_not_silently_confirmed(
        github, issue, monkeypatch):
    """Находка 3 (Important). Контур публикует человеку: «Если нет —
    пришлите поправленный текст той же командой». Без правки код это
    обещание не выполнял: ЛЮБОЙ второй ответ на показанный черновик
    применялся как подтверждение, независимо от своего текста, — поправка
    молча терялась, а фиксировалось первое, непроверенное толкование.

    Без правки этот тест падает: второй вызов возвращает `accepted` с
    ПЕРВЫМ толкованием, модель для поправленного текста не звалась, и
    журнал оказывается не пуст в точке, где по сценарию решения ещё быть не
    должно.
    """
    _open(github)
    calls = []

    def fake_interpret(question, journal, answer):
        calls.append(answer)
        if answer == "первый ответ":
            return a.answer_interpretation.Interpretation(answer="ПЕРВОЕ толкование")
        return a.answer_interpretation.Interpretation(answer="ВТОРОЕ толкование (поправленное)")

    monkeypatch.setattr(a, "_interpret_answer", fake_interpret)

    assert a.answer_question(issue, "howtodemo-1", "первый ответ", 101) == "confirm"
    assert "ПЕРВОЕ толкование" in github["comments"][0]
    assert questions.read_draft(github["body"]).interpretation["answer"] == "ПЕРВОЕ толкование"

    # Второй ответ — НЕ согласие, а поправленный текст.
    result = a.answer_question(issue, "howtodemo-1", "нет, я имел в виду другое", 102)

    assert result == "confirm"
    assert calls == ["первый ответ", "нет, я имел в виду другое"], \
        "поправленный текст обязан истолковываться заново, а не игнорироваться"
    assert questions.read_journal(github["body"]) == [], \
        "по непроверенному первому толкованию решение записываться не должно"
    assert "ВТОРОЕ толкование" in github["comments"][-1], \
        "человек обязан увидеть НОВОЕ толкование, а не молчаливую замену"
    draft = questions.read_draft(github["body"])
    assert draft.interpretation["answer"] == "ВТОРОЕ толкование (поправленное)"

    # Короткое согласие подтверждает именно АКТУАЛЬНОЕ (второе) толкование.
    assert a.answer_question(issue, "howtodemo-1", "да", 103) == "accepted"
    journal = questions.read_journal(github["body"])
    assert [d.answer for d in journal] == ["ВТОРОЕ толкование (поправленное)"]
