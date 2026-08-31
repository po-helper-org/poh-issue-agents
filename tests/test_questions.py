import pytest

from shared import issue_blocks, questions


def test_question_roundtrip():
    """Вопрос возвращается из тела ровно таким, каким ушёл."""
    original = questions.Question(
        id="howtodemo-1", kind="howtodemo",
        text="Чем принимать эту задачу?",
        options=("было 404; стало 405", "было 404; стало 405 на любой метод"))
    restored = questions.parse_question(questions.render_question(original))
    assert restored == original


def test_question_roundtrip_carries_announced_flag():
    """Третий круг ревью: `announced` — обычное поле `Question`, участвует в
    сериализации наравне с остальными, а не хранится где-то отдельно."""
    original = questions.Question(id="howtodemo-1", kind="howtodemo",
                                  text="Чем принимать?", options=("а",),
                                  announced=True)
    restored = questions.parse_question(questions.render_question(original))
    assert restored == original
    assert restored.announced is True


def test_parse_question_defaults_announced_false_for_legacy_block():
    """Блок, записанный версией кода ДО поля `announced` (JSON без такого
    ключа вовсе — не порча, а более старая запись), должен читаться как
    `announced=False`, а не падать и не подставлять `True`.

    Умолчание `False`, а не `True`, — умышленный выбор (см. докстринг
    `Question.announced`): вопрос, застрявший в дефекте первого круга (тело
    записано, комментарий так и не ушёл), под старым кодом не имел бы
    никакого признака вовсе, и `False` заставит комментарий наконец уйти.
    `True` по умолчанию сделало бы это молча невозможным — снова спрятало бы
    вопрос от человека, теперь уже насовсем.
    """
    legacy_payload = ("## Открытый вопрос контура\n\n```json\n"
                      '{"id": "howtodemo-1", "kind": "howtodemo", '
                      '"text": "Чем принимать?", "options": []}\n```')
    restored = questions.parse_question(legacy_payload)
    assert restored is not None
    assert restored.announced is False


def test_question_with_multiline_text_survives():
    """Текст вопроса бывает многострочным — форма не должна его портить."""
    original = questions.Question(id="mvp-bounds-1", kind="mvp-bounds",
                                  text="Строка раз\n\nСтрока два", options=())
    assert questions.parse_question(questions.render_question(original)) == original


def test_parse_question_of_garbage_is_none():
    """Порченый блок — отсутствие вопроса, а не исключение наружу.

    Тело Issue правят руками, и обрывок JSON там появится рано или поздно.
    """
    assert questions.parse_question("не json вовсе") is None
    assert questions.parse_question(None) is None
    assert questions.parse_question("") is None


def test_journal_roundtrip():
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="Чем принимать?", answer="405 с Allow: POST"),
        questions.Decision(question_id="mvp-bounds-1", kind="mvp-bounds",
                           question="Что в MVP?", answer="только /quote"),
    ]
    assert questions.parse_journal(questions.render_journal(decisions)) == decisions


def test_parse_journal_of_garbage_is_empty():
    assert questions.parse_journal("мусор") == []
    assert questions.parse_journal(None) == []


def test_next_question_id_counts_within_kind():
    """Нумерация ведётся по журналу и отдельно по каждому виду вопроса.

    Из журнала, а не из счётчика в прогоне: прогон теряется, журнал остаётся.
    """
    assert questions.next_question_id([], "howtodemo") == "howtodemo-1"
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="q", answer="a"),
        questions.Decision(question_id="mvp-bounds-1", kind="mvp-bounds",
                           question="q", answer="a"),
    ]
    assert questions.next_question_id(decisions, "howtodemo") == "howtodemo-2"
    assert questions.next_question_id(decisions, "mvp-bounds") == "mvp-bounds-2"
    assert questions.next_question_id(decisions, "plan-choice") == "plan-choice-1"


def test_effective_drops_superseded_records_but_journal_keeps_them():
    """Отменённое решение остаётся в журнале, но действующим не считается.

    История задачи обязана отвечать на вопрос «что решали раньше и почему
    передумали» — запись, затёртая на месте, этот вопрос уничтожает.
    """
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="q", answer="старое решение"),
        questions.Decision(question_id="howtodemo-2", kind="howtodemo",
                           question="q2", answer="новое решение",
                           supersedes="howtodemo-1"),
    ]
    live = questions.effective(decisions)
    assert [d.answer for d in live] == ["новое решение"]
    assert len(decisions) == 2, "журнал не должен терять записи"


def test_effective_handles_chain_of_supersessions():
    """Отмена отмены: действующей остаётся последняя запись цепочки."""
    decisions = [
        questions.Decision(question_id="a-1", kind="a", question="q", answer="первое"),
        questions.Decision(question_id="a-2", kind="a", question="q", answer="второе",
                           supersedes="a-1"),
        questions.Decision(question_id="a-3", kind="a", question="q", answer="третье",
                           supersedes="a-2"),
    ]
    assert [d.answer for d in questions.effective(decisions)] == ["третье"]


def test_next_question_id_uses_max_number_not_count():
    """Ревью, находка 1 (Critical): номер — максимум среди записей вида, а не их количество.

    Тело Issue правят руками. Если запись `howtodemo-2` из середины журнала
    пропала, счётчик «по количеству» увидит одну запись вида `howtodemo` и
    выдаст `howtodemo-2` — идентификатор, который уже занят записью `-3`.
    Правильный ответ — `howtodemo-4`, следующий за максимальным номером.
    """
    decisions = [
        questions.Decision(question_id="howtodemo-1", kind="howtodemo",
                           question="q", answer="a"),
        questions.Decision(question_id="howtodemo-3", kind="howtodemo",
                           question="q", answer="a"),
    ]
    assert questions.next_question_id(decisions, "howtodemo") == "howtodemo-4"


def test_next_question_id_ignores_ids_without_trailing_number():
    """Запись с id без числового хвоста не участвует в подсчёте номера, но и не роняет функцию.

    Такое бывает после ручной правки тела Issue. Максимум среди пригодных для
    счёта записей — 2, значит следующий номер — 3, а не «мусорный» id ломает
    вычисление.
    """
    decisions = [
        questions.Decision(question_id="howtodemo-руками-испорчено", kind="howtodemo",
                           question="q", answer="a"),
        questions.Decision(question_id="howtodemo-2", kind="howtodemo",
                           question="q", answer="a"),
    ]
    assert questions.next_question_id(decisions, "howtodemo") == "howtodemo-3"


def test_effective_breaks_cycle_of_supersedes_instead_of_dropping_everything():
    """Ревью, находка 2 (Important): цикл ссылок не должен стирать журнал целиком.

    До правки `{a-1 supersedes a-2, a-2 supersedes a-1}` считал отменёнными
    ОБЕ записи — действующего решения не оставалось вовсе, а это молчаливый
    отказ, худший класс дефектов в этом контуре. Журнал только пополняется,
    значит отмена всегда приходит позже отменяемого: `a-1` не может отменить
    `a-2`, если `a-2` записан следом за ней. Значит в силе остаётся именно
    `a-2` (её отменяющая ссылка на `a-1` не в счёт как «вперёд по времени»,
    а вот ссылка `a-2 -> a-1` действует, потому что `a-1` идёт раньше).
    """
    decisions = [
        questions.Decision(question_id="a-1", kind="a", question="q",
                           answer="первое", supersedes="a-2"),
        questions.Decision(question_id="a-2", kind="a", question="q",
                           answer="второе", supersedes="a-1"),
    ]
    live = questions.effective(decisions)
    assert [d.answer for d in live] == ["второе"]
    assert len(decisions) == 2, "журнал не должен терять записи"


def test_effective_ignores_reference_to_nonexistent_record():
    """Ссылка на несуществующую запись и раньше не ломала действующие — не сломать при правке цикла."""
    decisions = [
        questions.Decision(question_id="a-1", kind="a", question="q",
                           answer="единственное", supersedes="a-несуществует"),
    ]
    assert [d.answer for d in questions.effective(decisions)] == ["единственное"]


def test_parse_question_of_two_fences_in_one_chunk_is_none():
    """Ревью, находка 3: в переданном куске больше одного забора кода — это порча, а не выбор первого попавшегося.

    Контракт `parse_question`/`parse_journal` — на вход идёт содержимое ОДНОГО
    размеченного блока (то, что вернул `issue_blocks.read(body, <имя>)`), а не
    тело Issue целиком. Тело, где рядом лежат и блок вопроса, и блок журнала
    (ровно сценарий ревьюера), в эту функцию попадать не должно — но если
    такое всё же случилось, брать первый забор молча означало бы тихо
    подставить чужие данные вместо честного отказа: до правки этот вызов
    возвращал бы настоящий `Question`, собранный из ПЕРВОГО забора (блока
    вопроса), хотя кусок целиком уже испорчен второй записью рядом.
    """
    q = questions.Question(id="a-1", kind="a", text="t")
    chunk = questions.render_question(q) + "\n\n" + questions.render_journal([])
    assert questions.parse_question(chunk) is None


def test_parse_journal_of_two_fences_in_one_chunk_is_empty():
    """Тот же случай, что и test_parse_question_of_two_fences_in_one_chunk_is_none, со стороны журнала.

    До правки первый забор (блок журнала с одной записью) разбирался бы
    успешно, и функция вернула бы непустой список вместо `[]`.
    """
    d = questions.Decision(question_id="a-1", kind="a", question="q", answer="a")
    chunk = questions.render_journal([d]) + "\n\n" + questions.render_question(
        questions.Question(id="b-1", kind="b", text="t"))
    assert questions.parse_journal(chunk) == []


def test_parse_question_of_truncated_json_inside_fence_is_none():
    """Ревью, находка 4: сценарий из докстринга `_unwrap` — обрывок JSON ВНУТРИ валидного забора — не был проверен ни разу.

    `test_parse_question_of_garbage_is_none` гоняет вход без забора кода
    вовсе (`"не json вовсе"`) — там срабатывает ветка «забора нет», и до
    `except (ValueError, TypeError)` в `_unwrap` выполнение не доходит.
    Этот тест доходит: забор есть, `json.loads` внутри него падает.
    """
    payload = "## Открытый вопрос контура\n\n```json\n{\"id\": \"a-1\", \"kind\":\n```"
    assert questions.parse_question(payload) is None


def test_parse_journal_of_truncated_json_inside_fence_is_empty():
    """Тот же обрыв JSON внутри забора, что и у вопроса, со стороны журнала."""
    payload = "## Решения по задаче\n\n```json\n[{\"question_id\": \"a-1\",\n```"
    assert questions.parse_journal(payload) == []


def test_open_question_write_read_clear():
    question = questions.Question(id="howtodemo-1", kind="howtodemo",
                                  text="Чем принимать?", options=("а", "б"))
    body = questions.write_open("описание задачи", question)
    assert questions.read_open(body) == question
    assert "описание задачи" in body

    cleared = questions.clear_open(body)
    assert questions.read_open(cleared) is None
    assert "описание задачи" in cleared


def test_mark_announced_sets_flag_and_keeps_other_fields():
    """`mark_announced` меняет только `announced`, остальные поля вопроса —
    id, kind, text, options — переживают запись без изменений."""
    question = questions.Question(id="howtodemo-1", kind="howtodemo",
                                  text="Чем принимать?", options=("а", "б"))
    body = questions.write_open("описание задачи", question)
    assert questions.read_open(body).announced is False

    body = questions.mark_announced(body, question)
    stored = questions.read_open(body)
    assert stored.announced is True
    assert stored.id == question.id
    assert stored.kind == question.kind
    assert stored.text == question.text
    assert stored.options == question.options
    assert "описание задачи" in body


def test_read_open_of_body_without_block_is_none():
    assert questions.read_open("просто описание") is None
    assert questions.read_open(None) is None


def test_append_decision_accumulates_and_keeps_order():
    """Журнал пополняется, порядок записей сохраняется."""
    body = questions.append_decision("описание", questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q1", answer="a1"))
    body = questions.append_decision(body, questions.Decision(
        question_id="howtodemo-2", kind="howtodemo", question="q2", answer="a2",
        supersedes="howtodemo-1"))
    journal = questions.read_journal(body)
    assert [d.question_id for d in journal] == ["howtodemo-1", "howtodemo-2"]
    assert [d.answer for d in questions.effective(journal)] == ["a2"]
    assert "описание" in body


def test_question_block_and_journal_coexist_with_other_blocks():
    """Четыре блока в одном теле не мешают друг другу."""
    body = issue_blocks.write("описание", issue_blocks.GROW, "- [ ] находка")
    body = issue_blocks.write(body, issue_blocks.HOWTODEMO, "критерий")
    body = questions.write_open(body, questions.Question(
        id="mvp-bounds-1", kind="mvp-bounds", text="Что в MVP?"))
    body = questions.append_decision(body, questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q", answer="a"))

    assert issue_blocks.read(body, issue_blocks.GROW) == "- [ ] находка"
    assert issue_blocks.read(body, issue_blocks.HOWTODEMO) == "критерий"
    assert questions.read_open(body).id == "mvp-bounds-1"
    assert [d.question_id for d in questions.read_journal(body)] == ["howtodemo-1"]


def test_append_decision_refuses_when_answers_block_has_broken_json():
    """Ревью, находка 1 (Critical). Маркеры блока ANSWERS целы, а JSON внутри
    оборван (тело правили руками) — append_decision обязана отказать, а не
    молча переписать журнал единственной новой записью.

    До правки такая порча приходила из `read_journal` пустым списком —
    неотличимо от «журнала никогда не было», и `append_decision` считала
    журнал пустым и переписывала блок одной новой записью: прежнее решение
    исчезало бесследно, без исключения и без строки в логе.
    """
    body = questions.append_decision("описание задачи", questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q",
        answer="старое решение"))
    # Правка руками: обрываю закрывающую скобку JSON-массива внутри целых маркеров.
    broken = body.replace("]\n```", "\n```", 1)
    assert broken != body, "подмена должна была сработать — иначе тест ничего не проверяет"

    with pytest.raises(questions.CorruptedJournal) as excinfo:
        questions.append_decision(broken, questions.Decision(
            question_id="howtodemo-2", kind="howtodemo", question="q2",
            answer="новое решение"))
    # Текст исключения обязан подсказывать, какой блок и какую запись чинить,
    # чтобы человек, увидевший отказ в Sentry, понял, куда идти.
    assert issue_blocks.ANSWERS in str(excinfo.value)
    assert "howtodemo-2" in str(excinfo.value)


def test_read_open_logs_warning_on_corrupted_markers(caplog):
    """Ревью, находка 2 (Important). Порча маркеров блока QUESTION не должна
    тонуть в логе без следа.

    До правки исключение `ValueError` от `issue_blocks.read` гасилось молча:
    в логе не оставалось ничего, что отличило бы «вопроса никогда не было»
    от «тело сломали руками». Тот же приём, что уже применён в
    `worker/activities.py` для блока HOWTODEMO: предупреждение с причиной
    перед деградацией до None.
    """
    start, _end = issue_blocks._markers(issue_blocks.QUESTION)
    corrupted = f"{start}\nоборванный маркер без конца"
    with caplog.at_level("WARNING"):
        result = questions.read_open(corrupted)
    assert result is None
    assert issue_blocks.QUESTION in caplog.text


def test_read_journal_logs_warning_on_corrupted_markers(caplog):
    """Тот же случай, что у read_open (ревью, находка 2), со стороны журнала решений."""
    start, _end = issue_blocks._markers(issue_blocks.ANSWERS)
    corrupted = f"{start}\nоборванный маркер без конца"
    with caplog.at_level("WARNING"):
        result = questions.read_journal(corrupted)
    assert result == []
    assert issue_blocks.ANSWERS in caplog.text


def test_read_journal_is_empty_when_json_broken_inside_intact_markers():
    """Ревью, находка 3 (Minor): порча JSON внутри ЦЕЛЫХ маркеров блока ANSWERS,
    прочитанная полной цепочкой `read_journal` — не голым `parse_journal` на
    payload, как в `test_parse_journal_of_truncated_json_inside_fence_is_empty`.
    Маркеры целы, `issue_blocks.read` не кидает ValueError, разбор просто не
    даёт записей.
    """
    body = questions.append_decision("описание", questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q", answer="a"))
    broken = body.replace("]\n```", "\n```", 1)
    assert questions.read_journal(broken) == []


def test_read_open_is_none_when_json_broken_inside_intact_markers():
    """Тот же случай, что и у журнала (ревью, находка 3), со стороны открытого вопроса."""
    body = questions.write_open("описание", questions.Question(
        id="a-1", kind="a", text="t"))
    broken = body.replace("}\n```", "\n```", 1)
    assert questions.read_open(broken) is None


def test_draft_roundtrip_and_clear():
    draft = questions.Draft(question_id="howtodemo-1",
                            interpretation={"answer": "405 везде кроме POST",
                                           "amendments": []})
    body = questions.write_draft("описание", draft)
    assert questions.read_draft(body) == draft
    assert questions.read_draft(questions.clear_draft(body)) is None


def test_read_draft_logs_warning_on_corrupted_markers(caplog):
    """Тот же случай, что у read_open/read_journal (ревью, находка 2), со
    стороны черновика толкования: порча маркеров не должна тонуть в логе без
    следа, даже когда для вызывающего это лишь повод истолковать ответ заново."""
    start, _end = issue_blocks._markers(issue_blocks.DRAFT)
    corrupted = f"{start}\nоборванный маркер без конца"
    with caplog.at_level("WARNING"):
        result = questions.read_draft(corrupted)
    assert result is None
    assert issue_blocks.DRAFT in caplog.text


# --- ревью правки: черновик привязан к вопросу и признаётся показанным
# отдельно от факта записи (находки 1 и 2, обе Critical) ---

def test_draft_roundtrip_carries_question_id_and_announced_flag():
    """Оба новых поля черновика — обычные поля `Draft`, участвуют в
    сериализации наравне с толкованием, а не хранятся где-то отдельно (тот же
    принцип, что уже проверен для `Question.announced`, см.
    `test_question_roundtrip_carries_announced_flag`)."""
    original = questions.Draft(question_id="mvp-bounds-1",
                               interpretation={"answer": "только /quote",
                                              "amendments": []},
                               announced=True)
    restored = questions.parse_draft(questions.render_draft(original))
    assert restored == original
    assert restored.question_id == "mvp-bounds-1"
    assert restored.announced is True


def test_parse_draft_is_none_for_legacy_block_without_question_id():
    """Черновик, записанный версией кода задачи 6 (голый `Interpretation.
    model_dump()`, без ключа `question_id` вовсе), не подставляется как
    валидный черновик текущего вопроса — `question_id` в нём взять неоткуда,
    и молчаливое угадывание опаснее, чем «черновика нет» (см. докстринг
    `parse_draft`): второй ответ человека просто истолкуется заново."""
    legacy_payload = ('## Ожидает подтверждения\n\n```json\n'
                      '{"answer": "405 везде кроме POST", "amendments": []}\n'
                      '```')
    assert questions.parse_draft(legacy_payload) is None


def test_mark_draft_announced_sets_flag_and_keeps_other_fields():
    """`mark_draft_announced` меняет только `announced`, `question_id` и
    `interpretation` переживают запись без изменений — тот же контракт, что
    у `mark_announced` для вопроса
    (см. `test_mark_announced_sets_flag_and_keeps_other_fields`)."""
    draft = questions.Draft(question_id="howtodemo-1",
                            interpretation={"answer": "405", "amendments": []})
    body = questions.write_draft("описание задачи", draft)
    assert questions.read_draft(body).announced is False

    body = questions.mark_draft_announced(body, draft)
    stored = questions.read_draft(body)
    assert stored.announced is True
    assert stored.question_id == draft.question_id
    assert stored.interpretation == draft.interpretation
    assert "описание задачи" in body


def test_append_decision_refuses_when_answer_contains_marker_like_text():
    """Ревью, находка 3 (Minor). Ответ человека, дословно содержащий маркер
    чужого блока (например, процитированный кусок документации), не должен
    молча пройти запись.

    Защита уже есть в `issue_blocks.write` (проверка содержимого на маркеры
    ВСЕХ известных блоков) и ревьюер проверил её руками — этот тест закрепляет,
    что `append_decision` эту защиту не обходит.
    """
    start, end = issue_blocks._markers(issue_blocks.QUESTION)
    poisoned = questions.Decision(
        question_id="howtodemo-1", kind="howtodemo", question="q",
        answer=f"в документации написано: {start} ... {end}")
    with pytest.raises(ValueError):
        questions.append_decision("описание", poisoned)
