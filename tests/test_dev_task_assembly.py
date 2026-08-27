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
