"""Сборка постановки разработки: заголовки секций и контекст файлами.

До задачи 7 здесь же жили тесты на усечение постановки по приоритету: общий
потолок 50000 знаков и 10000 на артефакт, с вытеснением секций при
переполнении. Докстринг того кода признавал «переполнение достижимо штатно» —
и это было заложенным поведением, а не риском. Задача 7 сняла весь механизм
(`_apply_size_limit`, `_section_rank`, ранги, `CONTOUR_SECTIONS`) вместе с
тестами, которые его закрепляли: тяжёлый контекст (требования, сценарий
приёмки, решения прошлых шагов) теперь лежит файлами каталога `.harness/`
(`shared/task_context.py`), а постановка агента — короткий указатель на них.

Разбор постановки на секции (`_split_sections`/`_join_sections`) остаётся:
он больше не служит вытеснению, но по-прежнему нужен, чтобы заголовки при
сборке не терялись, а блоки не приклеивались к чужим соседям.
"""
from pathlib import Path

import pytest

import activities as a
from shared import task_context


TITLE = "Починить кнопку"
ISSUE_N = 42
MAIN = f"# Задача: реализовать Issue #{ISSUE_N}"


# ───────────────────── разбор на секции ─────────────────────

def test_heading_is_the_first_line_not_the_whole_block():
    """Раньше весь кусок становился именем секции, и содержимое исчезало."""
    secs = a._split_sections(["## Как работать\nнаходки пиши в .followups.md"])
    assert secs == [("## Как работать", "находки пиши в .followups.md")]


def test_rules_block_reaches_the_agent():
    """Блок правил репозитория терялся целиком вместе с этой инструкцией."""
    parts = [MAIN, f"## {TITLE}", "тело", a._DEV_FALLBACK_RULES]
    task = a._join_sections(a._split_sections(parts))
    assert ".followups.md" in task


def test_joined_task_keeps_section_headings():
    parts = [MAIN, f"## {TITLE}", "тело", "## Системные требования", "требования"]
    task = a._join_sections(a._split_sections(parts))
    assert MAIN in task
    assert "## Системные требования" in task


def test_block_starting_with_newline_survives():
    """Единственный блок, переживавший прежний разбор, обязан пережить и новый."""
    parts = [MAIN, "тело", "\nПравила организации:\n- пункт"]
    assert "- пункт" in a._join_sections(a._split_sections(parts))


def test_empty_sections_do_not_produce_blank_blocks():
    task = a._join_sections([("", ""), ("## Пусто", "")])
    assert task.strip() == "## Пусто"


# ───────────────────── контекст файлами, без потолка (задача 7) ─────────────────────

def test_context_goes_to_files_without_truncation(monkeypatch, tmp_path):
    """Контекст доезжает файлами, а не упаковкой с потолком.

    Прежде постановка паковалась в один файл: 50000 знаков на всё, 10000 на
    артефакт, лишние секции вытеснялись целиком. Докстринг того кода признавал:
    «Переполнение достижимо штатно».
    """
    import activities as a
    from shared import task_context

    long_requirements = "требование\n" * 5000   # заведомо больше прежнего потолка

    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            long_requirements if path.endswith("system_requirements.md") else "")
    monkeypatch.setattr(a, "_clone_repo", lambda repo, dest, branch=None: None)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-7")

    root, clone = a._dev_paths(issue)
    harness = Path(clone) / task_context.DIR

    assert (harness / task_context.CONTEXT_MAP).exists(), "карты контекста нет"
    assert task_context.missing(harness, {task_context.REQUIREMENTS: "требования"}) == []
    assert task_context.truncation_markers(harness) == [], "контекст обрезан"
    assert (harness / task_context.REQUIREMENTS).read_text(encoding="utf-8").count("требование") == 5000
    assert task_context.DIR in task, "постановка не указывает на каталог контекста"
    assert len(task) < 5000, "постановка снова пересказывает контекст вместо ссылки"


# ───────────────── обязательный набор: отказ стадии, а не слепой прогон ─────────────────

def _prepare_kwargs(monkeypatch, tmp_path, get_file):
    monkeypatch.setattr(a.github_client, "get_file", get_file)
    monkeypatch.setattr(a, "_clone_repo", lambda repo, dest, branch=None: None)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))


def test_missing_requirements_with_analysis_branch_fails_the_stage(monkeypatch, tmp_path):
    """Ветка аналитики есть, а требования не собрались — отказ стадии.

    `task_context.missing()` проверяет только то, что ей передали. Если бы
    проверка шла по факту записанного (`entries`), молчаливый провал записи
    выглядел бы как «всё доставлено» — ровно то, от чего защищает
    `task_context.required()`.
    """
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")

    issue = a.IssueInput(repo="o/r", issue_number=9, title="t", body="b",
                         author_login="u", author_type="User")

    with pytest.raises(RuntimeError, match="requirements.md"):
        a._dev_prepare(issue, "research/issue-9")


def test_truncation_marker_in_fetched_content_fails_the_stage(monkeypatch, tmp_path):
    """След старого усечения, унаследованный от источника, — тоже отказ, а не
    тихий провоз испорченного контекста исполнителю.

    В норме этот путь недостижим: задача 7 убрала единственный код, что
    дописывал маркер (`_apply_size_limit`). Проверка защищает от УНАСЛЕДОВАННОГО
    маркера — если он всё же попал в исходный текст требований."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None:
                    "требования …[обрезано]" if path.endswith("system_requirements.md") else "")

    issue = a.IssueInput(repo="o/r", issue_number=14, title="t", body="b",
                         author_login="u", author_type="User")

    with pytest.raises(RuntimeError, match="след усечения"):
        a._dev_prepare(issue, "research/issue-14")


def test_no_analysis_branch_does_not_require_a_requirements_file(monkeypatch, tmp_path):
    """Аналитики нет вовсе — штатный путь «работай от тела Issue», не отказ."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")

    issue = a.IssueInput(repo="o/r", issue_number=10, title="t", body="b",
                         author_login="u", author_type="User")

    task, _ = a._dev_prepare(issue, "")  # ветки аналитики нет
    assert "Аналитики по задаче нет" in task


# ───────────────── решения прошлой попытки (задача 7) ─────────────────

def test_decisions_carry_over_from_a_previous_attempts_reflect_note(monkeypatch, tmp_path):
    """`.reflect.md` предыдущей попытки этой же задачи не пропадает при
    повторном /develop — он лежит в корне задачи ДО того, как `_dev_prepare`
    снесёт корень заново, и это единственное окно, где решения можно
    перенести дальше следующему прогону."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")

    issue = a.IssueInput(repo="o/r", issue_number=11, title="t", body="b",
                         author_login="u", author_type="User")
    root, _clone = a._dev_paths(issue)
    root.mkdir(parents=True, exist_ok=True)
    (root / a.REFLECT_NOTE_FILE).write_text(
        "## Намерение\nсделал минимально необходимое для сценария\n", encoding="utf-8")

    a._dev_prepare(issue, "")  # без ветки аналитики — решения проверяем изолированно

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert "сделал минимально необходимое" in \
        (harness / task_context.DECISIONS).read_text(encoding="utf-8")


def test_no_previous_reflect_note_is_not_an_error(monkeypatch, tmp_path):
    """Первый прогон по задаче — файла намерений нет, и это не отказ."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")

    issue = a.IssueInput(repo="o/r", issue_number=12, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "")

    _root, clone = a._dev_paths(issue)
    assert not (clone / task_context.DIR / task_context.DECISIONS).exists()


# ───────────── H1: каталог не наследует чужую задачу (ревью) ─────────────
#
# `.harness/` коммитится в main, поэтому следующий клон того же репозитория
# приезжает с каталогом ПРЕДЫДУЩЕЙ задачи. `harness.mkdir(exist_ok=True)` без
# очистки оставлял чужие файлы на месте: если сбор ЭТОЙ задачи молча вернул
# пусто (истёк токен, переименован артефакт, sysreq не дописан), проверка
# обязательного набора видела унаследованный файл прошлой задачи и засчитывала
# его — отказа не было, а исполнитель работал по требованиям и сценарию чужого
# Issue, которые затем уезжали в PR как контекст этой задачи.

def _clone_with_stale_harness(stale_files: dict[str, str]):
    """Двойник `_clone_repo`, кладущий в клон файлы `.harness/` — как будто
    их принёс настоящий `git clone` репозитория, где `.harness/` от
    ПРЕДЫДУЩЕЙ задачи уже вмержен в основную ветку. `root` (родитель
    `clone_dir`) `_dev_prepare` сносит и создаёт заново на КАЖДОМ вызове
    независимо от H1 — если положить чужие файлы в клон ДО вызова
    `_dev_prepare`, этот снос уберёт их сам, и тест ничего не проверит. Файлы
    обязаны появиться так же, как в реальности: ВНУТРИ самого клонирования."""
    def clone(repo, dest, branch=None):
        harness = Path(dest) / task_context.DIR
        harness.mkdir(parents=True, exist_ok=True)
        for name, content in stale_files.items():
            (harness / name).write_text(content, encoding="utf-8")
    return clone


def test_stale_harness_from_a_previous_issue_does_not_survive_a_fresh_run(monkeypatch, tmp_path):
    """Сценарий H1 дословно: требования этой задачи не собрались (токен истёк
    / артефакт переименован / sysreq не дописан), а клон приносит требования и
    сценарий ЧУЖОЙ задачи — унаследованные из main, куда `.harness/`
    предыдущей задачи вмержили вместе с кодом. Ожидается отказ стадии, а не
    тихий провоз чужого контекста."""
    monkeypatch.setattr(a.github_client, "get_file", lambda repo, path, ref=None: "")
    monkeypatch.setattr(a, "_clone_repo", _clone_with_stale_harness({
        task_context.REQUIREMENTS: "требования ЧУЖОЙ задачи из предыдущего прогона",
        task_context.HOWTODEMO: "сценарий ЧУЖОЙ задачи",
    }))
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=20, title="t", body="b",
                         author_login="u", author_type="User")

    with pytest.raises(RuntimeError, match="requirements.md"):
        a._dev_prepare(issue, "research/issue-20")


def test_harness_directory_is_rebuilt_from_scratch_every_run(monkeypatch, tmp_path):
    """Унаследованный файл, вообще не входящий в объявленный набор, обязан
    пропасть при пересборке — каталог собирается с нуля, а не дополняется
    поверх того, что принёс клон."""
    monkeypatch.setattr(a.github_client, "get_file", lambda repo, path, ref=None: "")
    monkeypatch.setattr(a, "_clone_repo", _clone_with_stale_harness({
        "leftover-from-another-issue.md": "чужой файл",
    }))
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=21, title="t", body="b",
                         author_login="u", author_type="User")

    a._dev_prepare(issue, "")  # без ветки — не наткнёмся на обязательный набор

    _root, clone = a._dev_paths(issue)
    assert not (clone / task_context.DIR / "leftover-from-another-issue.md").exists(), \
        "унаследованный файл пережил пересборку каталога"


def test_empty_context_fails_even_if_required_set_is_patched_to_demand_nothing(
        monkeypatch, tmp_path):
    """H1, вторая половина чинки: пустая карта контекста при живой ветке
    аналитики — самостоятельный повод для отказа, а не только следствие
    `task_context.required()`. Сегодня `required()` уже ловит этот случай
    (REQUIREMENTS обязателен при has_analysis), но полагаться ТОЛЬКО на него
    значит терять защиту, если его определение изменится независимо от этой
    проверки — поэтому патчим `required()`, чтобы он перестал требовать
    что-либо, и убеждаемся, что отказ всё равно происходит."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")
    monkeypatch.setattr(task_context, "required", lambda *, has_analysis: {})

    issue = a.IssueInput(repo="o/r", issue_number=22, title="t", body="b",
                         author_login="u", author_type="User")

    with pytest.raises(RuntimeError, match="контекст не собран"):
        a._dev_prepare(issue, "research/issue-22")


# ───────────────── вырезка блока HowToDemo из тела Issue (задача 7) ─────────────────
#
# Формы заголовка — те же четыре, что признаёт HowToDemo-Agent при поиске
# сценария (`docs/HOWTODEMO.md`, «Как агент находит сценарий»).

def test_howtodemo_block_heading_form():
    body = "intro\n\n## HowToDemo\n\n1. Открываю корзину\n2. Вижу итог\n\n## Другое\nхвост"
    assert a._howtodemo_block(body) == "1. Открываю корзину\n2. Вижу итог"


def test_howtodemo_block_h3_form():
    assert a._howtodemo_block("### How to demo\nШаг") == "Шаг"


def test_howtodemo_block_bold_label_form():
    body = "текст\n\n**How to demo:**\nШаг1\nШаг2\n\n**Открытые вопросы:**\nвопрос"
    assert a._howtodemo_block(body) == "Шаг1\nШаг2"


def test_howtodemo_block_plain_label_form():
    assert a._howtodemo_block("How to demo: просто одна строка сценария") == \
        "просто одна строка сценария"


def test_howtodemo_block_absent_is_not_a_failure():
    """Сценарий может лежать в письме БФТ — приёмщик найдёт его сам."""
    assert a._howtodemo_block("просто текст Issue без сценария вообще") == ""


def test_howtodemo_block_empty_body_is_not_a_failure():
    assert a._howtodemo_block("") == ""


def test_howtodemo_scenario_reaches_the_harness_file(monkeypatch, tmp_path):
    """Сквозная проверка: сценарий из тела Issue доезжает до
    `.harness/howtodemo.md`, а не остаётся только в регэкспе."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")
    monkeypatch.setattr(a, "_refresh_issue_body",
                        lambda issue: "## HowToDemo\n\nОткрываю страницу и вижу цену")

    issue = a.IssueInput(repo="o/r", issue_number=13, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "")

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert (harness / task_context.HOWTODEMO).read_text(encoding="utf-8") == \
        "Открываю страницу и вижу цену"
    assert task_context.HOWTODEMO in (harness / task_context.CONTEXT_MAP).read_text(encoding="utf-8")


# ───────────── H2: вырезка сценария приёмки теряет и портит его (ревью) ─────────────
#
# Все четыре случая воспроизведены ревьюером на живом коде: старая граница
# конца блока — ЛЮБОЙ заголовок 1-6 уровня либо ЛЮБАЯ жирная метка — путала
# структуру внутри сценария с концом сценария и ложно срабатывала на заголовки,
# где «HowToDemo» лишь часть другого слова.

def test_howtodemo_heading_then_blank_line_then_bold_label_keeps_the_label_as_content():
    """Случай 1, самый дорогой: после заголовка пустая строка, затем жирная
    метка. Старая граница конца блока считала ЛЮБУЮ жирную метку концом
    сценария — обрезка происходила на первой же строке содержимого, сценарий
    оказывался пустым, и файл `.harness/howtodemo.md` не писался вовсе (не
    обязателен — в лог тоже ничего не уходило)."""
    body = "## HowToDemo\n\n**Шаги:**\n1. Открываю корзину\n2. Вижу итог\n\n## Другое\nхвост"
    assert a._howtodemo_block(body) == "**Шаги:**\n1. Открываю корзину\n2. Вижу итог"


def test_howtodemo_block_survives_a_nested_h3_subheading():
    """Случай 2: подзаголовок третьего уровня ВНУТРИ блока, начатого `##`
    (второй уровень), — часть сценария, а не соседняя секция. Старая граница
    обрезала блок на первом же вложенном подзаголовке."""
    body = ("## HowToDemo\n\n"
            "### Шаг 1: открыть страницу\nтекст шага 1\n\n"
            "### Шаг 2: оформить заказ\nтекст шага 2\n\n"
            "## Другое\nхвост")
    result = a._howtodemo_block(body)
    assert "### Шаг 1" in result and "### Шаг 2" in result and "текст шага 2" in result
    assert "хвост" not in result


def test_howtodemo_h3_start_still_ends_at_a_sibling_h3():
    """Зеркальный случай: блок, начатый `###` (третий уровень), обязан
    заканчиваться на СЛЕДУЮЩЕМ заголовке того же уровня или крупнее — а не
    поглощать всё до конца тела."""
    body = "### How to demo\nШаг1\n\n### Другой раздел\nхвост"
    assert a._howtodemo_block(body) == "Шаг1"


def test_howtodemo_heading_where_the_word_is_part_of_another_word_does_not_trigger():
    """Случай 3: заголовок вида `## HowToDemo-Agent: как он работает» — это
    заголовок ПРО агента с таким именем, а не раздел сценария. Старый регэксп
    матчил по `\\b` после «demo», а «-» — граница слова, поэтому ложно
    срабатывал и утаскивал в сценарий чужой текст."""
    body = "## HowToDemo-Agent: как он работает\n\nОписание агента, не сценарий приёмки."
    assert a._howtodemo_block(body) == ""


def test_howtodemo_block_quoted_inside_a_code_fence_is_not_a_real_scenario():
    """Случай 4: раздел процитирован внутри тройных обратных кавычек —
    например, как пример/шаблон для заполнения. Это НЕ настоящий сценарий этой
    задачи; старый разбор находил его внутри блока кода и утаскивал в
    сценарий шаблон вместе с хвостом кавычек."""
    body = (
        "Шаблон для заполнения:\n\n"
        "```markdown\n"
        "## HowToDemo\n"
        "1. Шаг из шаблона\n"
        "```\n\n"
        "Остальной текст без настоящего сценария."
    )
    assert a._howtodemo_block(body) == ""


def test_howtodemo_block_preserves_a_code_fence_that_is_legitimately_inside_it():
    """Маскировка нужна только для ПОИСКА границ — не должна портить
    содержимое настоящего сценария: пример (например, curl-команда в шаге
    демонстрации), легитимно лежащий ВНУТРИ блока, обязан дойти до
    исполнителя дословно, вместе с обратными кавычками."""
    body = (
        "## HowToDemo\n\nОткрываю страницу и вижу цену:\n"
        "```\ncurl https://example.com\n```\n\n"
        "## Другое\nхвост, сюда сценарий заходить не должен"
    )
    result = a._howtodemo_block(body)
    assert result == "Открываю страницу и вижу цену:\n```\ncurl https://example.com\n```"
    assert "хвост" not in result


# ────────── требование 3: `.harness/` реально доезжает до PR ──────────

def test_harness_directory_reaches_the_actual_commit_end_to_end(monkeypatch, tmp_path):
    """Сквозная проверка настоящим git, а не моком: `_dev_prepare` кладёт
    каталог контекста, «агент» дописывает код, `_dev_publish` коммитит и
    пушит — и в получившемся коммите обязаны быть оба, код и контекст.

    Мок здесь рискует подтвердить не то, что происходит на самом деле (тот же
    довод, что и в `tests/test_github_client_pr.py`): именно взаимодействие
    `clear_service_files` (снимает служебные файлы, но НЕ `.harness/`) и
    `git add -A` в `publish_worktree` решает, доедет каталог или нет.
    """
    import subprocess
    import github_client as gc

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)

    def fake_clone(repo, dest, branch=None):
        subprocess.run(["git", "clone", str(origin), dest], check=True, capture_output=True)
        subprocess.run(["git", "-C", dest, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", dest, "config", "user.name", "t"], check=True)
        (Path(dest) / "README.md").write_text("baseline")
        subprocess.run(["git", "-C", dest, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", dest, "commit", "-m", "seed"],
                       check=True, capture_output=True)

    monkeypatch.setattr(a, "_clone_repo", fake_clone)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))
    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            "требования" if path.endswith("system_requirements.md") else "")

    issue = a.IssueInput(repo="o/r", issue_number=15, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-15")

    _root, clone = a._dev_paths(issue)
    assert (clone / task_context.DIR / task_context.CONTEXT_MAP).exists(), \
        "готовка не положила каталог контекста — дальше проверять нечего"
    # «Агент» дописывает код уже ПОСЛЕ подготовки контекста, как в реальном прогоне.
    (clone / "app.py").write_text("print('done')")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _FakeResp:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 77}

    monkeypatch.setattr(gc.requests, "post", lambda *args, **kw: _FakeResp())

    number = a._dev_publish(issue, "research/issue-15")

    assert number == 77
    show = subprocess.run(["git", "-C", str(clone), "show", "--stat", "HEAD"],
                          check=True, capture_output=True, text=True).stdout
    assert "app.py" in show, "код агента не доехал до коммита"
    assert ".harness/context.md" in show, ".harness не доехал до коммита"


# ────────── M1 (ревью задачи 7): гвард пустого прогона на МЕСТЕ ВЫЗОВА ──────────
#
# `ignore_for_empty_check=(f"{task_context.DIR}/**",)` в `_dev_publish` —
# единственная строка, исключающая `.harness/` из проверки «есть ли
# изменения». `tests/test_github_client_pr.py` проверяет саму функцию
# `publish_worktree` с аргументом, переданным ВРУЧНУЮ тестом, — но ни один
# тест не проверял, что `_dev_publish` этот аргумент ДЕЙСТВИТЕЛЬНО передаёт.
# Удаление строки в `worker/activities.py` не роняло ни одного из 1317
# тестов до этой правки.

def test_dev_publish_treats_context_only_changes_as_an_empty_run(monkeypatch, tmp_path):
    """Сквозная проверка настоящим git через `_dev_publish` (не через
    `publish_worktree` напрямую): агент не тронул ни одного файла, в рабочем
    дереве только `.harness/`, положенный `_dev_prepare`. Без исключения
    аргумента на месте вызова это читалось бы как «агент кое-что сделал» —
    PR открылся бы с одним каталогом контекста внутри."""
    import subprocess
    import github_client as gc

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)

    def fake_clone(repo, dest, branch=None):
        subprocess.run(["git", "clone", str(origin), dest], check=True, capture_output=True)
        subprocess.run(["git", "-C", dest, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", dest, "config", "user.name", "t"], check=True)
        (Path(dest) / "README.md").write_text("baseline")
        subprocess.run(["git", "-C", dest, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", dest, "commit", "-m", "seed"],
                       check=True, capture_output=True)

    monkeypatch.setattr(a, "_clone_repo", fake_clone)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))
    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            "требования" if path.endswith("system_requirements.md") else "")

    issue = a.IssueInput(repo="o/r", issue_number=16, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-16")
    # «Агент» не трогает рабочее дерево вовсе — единственная правка внутри
    # него это `.harness/`, положенный подготовкой ДО прогона агента.

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")
    posts: list = []
    monkeypatch.setattr(gc.requests, "post", lambda *args, **kw: posts.append((args, kw)))

    number = a._dev_publish(issue, "research/issue-16")

    assert number is None, "агент не тронул ни файла — пустой прогон, PR не открывается"
    assert posts == [], "запрос на создание PR не должен был уйти"


# ────────── правило фокуса переживает свои правила репозитория ──────────

def test_focus_rule_survives_repository_own_rules(monkeypatch, tmp_path):
    """Правило фокуса обязано доехать и в репозиторий со своими правилами.

    Свой `.openhands/task-rules.md` целевого репозитория вытесняет запасные
    правила контура ЦЕЛИКОМ. Это уже стоило потери блока правил и инструкции
    про файл находок: они жили внутри запасных правил и исчезали в самых
    обычных репозиториях — тех, у кого свои правила есть.
    """
    import activities as a

    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            "## Свои правила репозитория" if path.endswith("task-rules.md")
                            else "требования" if path.endswith("system_requirements.md")
                            else "")

    def _fake_clone(repo, dest, branch=None):
        # `_dev_prepare` читает `.openhands/task-rules.md` локальным файлом
        # клона (`rules.exists()` / `rules.read_text()`), а не через
        # `github_client.get_file` — двойник обязан положить файл НА ДИСК,
        # иначе `rules.exists()` всегда False и репозиторий со своими
        # правилами неотличим в тесте от репозитория без них.
        rules_dir = Path(dest) / ".openhands"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "task-rules.md").write_text(
            "## Свои правила репозитория", encoding="utf-8")

    monkeypatch.setattr(a, "_clone_repo", _fake_clone)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-1")

    assert "Свои правила репозитория" in task, "правила репозитория потерялись"
    assert "пройдёт ли сценарий без этого" in task, "правило фокуса не доехало"
