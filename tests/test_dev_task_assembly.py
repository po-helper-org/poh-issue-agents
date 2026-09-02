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
from shared import issue_blocks, task_context


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
    маркера — если он всё же попал в исходный текст требований.

    L2 (ревью задачи 7): сообщение обязано подсказывать человеку выход, а не
    только называть находку — попади маркер цитатой в требования, отказ без
    подсказки повторялся бы на каждой разработке по этой задаче."""
    marked = f"требования {task_context.TRUNCATION_MARKER}"
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None:
                    marked if path.endswith("system_requirements.md") else "")

    issue = a.IssueInput(repo="o/r", issue_number=14, title="t", body="b",
                         author_login="u", author_type="User")

    with pytest.raises(RuntimeError, match="след усечения") as excinfo:
        a._dev_prepare(issue, "research/issue-14")
    message = str(excinfo.value)
    assert task_context.REQUIREMENTS in message, "сообщение не называет файл с находкой"
    assert any(word in message for word in ("branch", "ветк", "исправ", "перепиш", "убер")), \
        "сообщение не подсказывает человеку выход"


def test_no_analysis_branch_does_not_require_a_requirements_file(monkeypatch, tmp_path):
    """Аналитики нет вовсе — штатный путь «работай от тела Issue», не отказ."""
    _prepare_kwargs(monkeypatch, tmp_path, lambda repo, path, ref=None: "")

    issue = a.IssueInput(repo="o/r", issue_number=10, title="t", body="b",
                         author_login="u", author_type="User")

    task, _ = a._dev_prepare(issue, "")  # ветки аналитики нет
    assert "Аналитики по задаче нет" in task


# ───────────────── M2 (ревью задачи 7): DECISIONS из concept.md, не из .reflect.md ─────────────────
#
# Постановка обещает агенту дословно: «Файл в коммит не попадёт, его снимает
# контур» (`.reflect.md` — намерения, допущения, СОМНЕНИЯ) — а старая версия
# копировала этот файл в decisions.md, который коммитится и уезжает в PR:
# обещание нарушалось кодом же, который его давал. Источник поменян на
# `concept.md` с ветки аналитики — там вердикт дебатов, то есть принятые
# решения и их причины; это не намерения агента, а факт из git, который
# коммититься уже не боится ничего нарушить.

def _get_file_double(**by_suffix):
    """github_client.get_file, отвечающий по суффиксу пути. Отсутствующий в
    словаре суффикс — пустая строка (файла на ветке нет)."""
    def get_file(repo, path, ref=None):
        for suffix, content in by_suffix.items():
            if path.endswith(suffix):
                return content
        return ""
    return get_file


def test_decisions_come_from_the_analysis_branch_concept_md(monkeypatch, tmp_path):
    """Источник поменян: decisions.md — это concept.md ветки аналитики, а не
    файл намерений локального диска."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(
        **{"system_requirements.md": "требования",
           "concept.md": "## Решение\nделаем через адаптер, не патчим ядро"}))

    issue = a.IssueInput(repo="o/r", issue_number=11, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-11")

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert (harness / task_context.DECISIONS).read_text(encoding="utf-8") == \
        "## Решение\nделаем через адаптер, не патчим ядро"


def test_no_concept_on_the_analysis_branch_is_not_an_error(monkeypatch, tmp_path):
    """concept.md на ветке нет (или он пуст) — DECISIONS не пишется, отказа
    нет: `task_context.required()` его никогда не требует."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(
        **{"system_requirements.md": "требования"}))

    issue = a.IssueInput(repo="o/r", issue_number=12, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-12")

    _root, clone = a._dev_paths(issue)
    assert not (clone / task_context.DIR / task_context.DECISIONS).exists()


def test_reflect_note_no_longer_reaches_decisions(monkeypatch, tmp_path):
    """Регрессия на само нарушение обещания: даже если `.reflect.md`
    предыдущей попытки лежит в корне задачи (унаследован от старого кода или
    оставлен другим механизмом), его текст не должен попасть в decisions.md —
    контур обязан сдержать обещание «файл в коммит не попадёт»."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(
        **{"system_requirements.md": "требования",
           "concept.md": "## Решение\nвердикт дебатов"}))

    issue = a.IssueInput(repo="o/r", issue_number=13, title="t", body="b",
                         author_login="u", author_type="User")
    root, _clone = a._dev_paths(issue)
    root.mkdir(parents=True, exist_ok=True)
    (root / a.REFLECT_NOTE_FILE).write_text(
        "## Намерение\nэто НЕ должно попасть в PR\n", encoding="utf-8")

    a._dev_prepare(issue, "research/issue-13")

    _root, clone = a._dev_paths(issue)
    decisions = (clone / task_context.DIR / task_context.DECISIONS).read_text(encoding="utf-8")
    assert "НЕ должно попасть" not in decisions
    assert decisions == "## Решение\nвердикт дебатов"


def test_decisions_are_retry_safe_since_they_now_come_from_git_not_local_disk(
        monkeypatch, tmp_path):
    """L1: раньше решения приходили из `.reflect.md`, прочитанного из
    каталога задачи ДО его сноса — упавшая первая попытка, дошедшая до
    чтения файла, оставляла вторую и третью попытку без него (каталог уже
    снесён предыдущим вызовом `_dev_prepare`, а новый файл взяться неоткуда
    без свежего прогона агента). concept.md приходит через git на КАЖДОМ
    вызове независимо от локального состояния каталога — повторный вызов
    (как повторная попытка Temporal) получает те же решения, что и первый."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(
        **{"system_requirements.md": "требования",
           "concept.md": "## Решение\nделаем через адаптер"}))

    issue = a.IssueInput(repo="o/r", issue_number=14, title="t", body="b",
                         author_login="u", author_type="User")

    a._dev_prepare(issue, "research/issue-14")  # «первая попытка»
    _root, clone = a._dev_paths(issue)
    first = (clone / task_context.DIR / task_context.DECISIONS).read_text(encoding="utf-8")

    a._dev_prepare(issue, "research/issue-14")  # «повторная попытка» — тот же каталог
    _root, clone = a._dev_paths(issue)
    second = (clone / task_context.DIR / task_context.DECISIONS).read_text(encoding="utf-8")

    assert first == second == "## Решение\nделаем через адаптер"


# ───────────────── M4 (ревью задачи 7): остальные артефакты цепочки FNR ─────────────────
#
# Прежняя сборка тянула пять артефактов FNR в постановку; задача 7 оставила
# только требования. concept.md, task.md, repowise-dialog.md и validation.md
# выпали без упоминания — возвращаются файлами в каталог. Не обязательны:
# обязательны только требования, отсутствующий артефакт просто не попадает в
# карту.

def test_optional_analysis_artifacts_reach_the_harness_directory(monkeypatch, tmp_path):
    """N3 (повторное ревью): concept.md больше НЕ становится вторым файлом
    каталога под своим именем — тот же текст уже лежит в decisions.md (M2).
    Запись под именем concept.md отдельно проверяет
    `test_concept_md_is_not_written_as_a_separate_file_from_decisions`
    (регрессия на дублирование, ниже)."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(**{
        "system_requirements.md": "требования",
        "concept.md": "концепт",
        "task.md": "постановка FNR",
        "repowise-dialog.md": "диалог с индексом",
        "validation.md": "отчёт валидации",
    }))

    issue = a.IssueInput(repo="o/r", issue_number=17, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-17")

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert (harness / task_context.TASK).read_text(encoding="utf-8") == "постановка FNR"
    assert (harness / task_context.REPOWISE_DIALOG).read_text(encoding="utf-8") == \
        "диалог с индексом"
    assert (harness / task_context.VALIDATION).read_text(encoding="utf-8") == "отчёт валидации"

    context_map = (harness / task_context.CONTEXT_MAP).read_text(encoding="utf-8")
    for name in (task_context.TASK, task_context.REPOWISE_DIALOG, task_context.VALIDATION):
        assert name in context_map


def test_concept_md_is_not_written_as_a_separate_file_from_decisions(monkeypatch, tmp_path):
    """N3 (повторное ревью): до этой правки concept.md писался ДВАЖДЫ — как
    decisions.md (M2, роль «принятые решения и их причины») и как concept.md
    отдельным артефактом (M4) — байт в байт тот же текст под двумя разными
    подписями в карте контекста, как будто это разные срезы. Исполнитель
    тратил бюджет чтения дважды на один и тот же текст. Теперь единственный
    файл с этим содержимым — decisions.md; concept.md как имя файла в
    каталоге не появляется вовсе, а его имя в карте контекста не значится."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(**{
        "system_requirements.md": "требования",
        "concept.md": "вердикт дебатов: делаем через адаптер",
    }))

    issue = a.IssueInput(repo="o/r", issue_number=20, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-20")

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert (harness / task_context.DECISIONS).read_text(encoding="utf-8") == \
        "вердикт дебатов: делаем через адаптер"
    assert not (harness / task_context.CONCEPT).exists(), \
        "concept.md не должен становиться вторым файлом с тем же текстом"

    context_map = (harness / task_context.CONTEXT_MAP).read_text(encoding="utf-8")
    assert task_context.DECISIONS in context_map
    assert task_context.CONCEPT not in context_map, \
        "имя concept.md не должно попадать в карту — файла с этим именем нет"


def test_missing_optional_artifact_is_absent_from_the_map_not_an_error(monkeypatch, tmp_path):
    """task.md и validation.md отсутствуют на ветке (сорванный анализ мог не
    дойти до этих стадий) — не отказ, просто не попадают в карту."""
    _prepare_kwargs(monkeypatch, tmp_path, _get_file_double(**{
        "system_requirements.md": "требования",
        "concept.md": "концепт",
        "repowise-dialog.md": "диалог с индексом",
    }))

    issue = a.IssueInput(repo="o/r", issue_number=18, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-18")

    _root, clone = a._dev_paths(issue)
    harness = clone / task_context.DIR
    assert not (harness / task_context.TASK).exists()
    assert not (harness / task_context.VALIDATION).exists()
    context_map = (harness / task_context.CONTEXT_MAP).read_text(encoding="utf-8")
    assert task_context.TASK not in context_map
    assert task_context.VALIDATION not in context_map


def test_optional_artifact_fetch_failure_degrades_instead_of_failing_the_stage(
        monkeypatch, tmp_path):
    """Сетевой сбой на ОДНОМ необязательном артефакте не должен ронять всю
    подготовку — деградация, как и у остальных источников контура, а не
    отказ стадии (эти файлы не входят в `task_context.required()`)."""
    def get_file(repo, path, ref=None):
        if path.endswith("system_requirements.md"):
            return "требования"
        if path.endswith("validation.md"):
            raise RuntimeError("имитация сетевого сбоя")
        return ""
    _prepare_kwargs(monkeypatch, tmp_path, get_file)

    issue = a.IssueInput(repo="o/r", issue_number=19, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-19")  # не должно бросить исключение

    _root, clone = a._dev_paths(issue)
    assert not (clone / task_context.DIR / task_context.VALIDATION).exists()


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


# ────────── N1 (повторное ревью): маскировка не держит две формы забора ──────────
#
# `_CODE_FENCE` понимал только РОВНО три обратные кавычки на границе — забор
# из четырёх и более (стандартный способ процитировать текст, где уже есть
# тройные кавычки) не совпадал с закрывающей частью паттерна вовсе, и
# `_mask_code_fences` оставлял такой блок непомаскированным. Тот же исход у
# незакрытого забора: без закрывающей строки `.sub` не находит совпадения, и
# маскировки не происходит. Хуже прежнего: граница конца блока (H2) теперь —
# заголовок того же уровня или крупнее, поэтому ложное совпадение внутри
# такого забора утаскивает всё до конца тела Issue, а не до ближайшего
# постороннего заголовка.

def test_howtodemo_block_quoted_inside_a_four_backtick_fence_is_not_a_real_scenario():
    """Ревьюер воспроизвёл лично: шаблон с заголовком сценария внутри забора
    из четырёх кавычек (нужен, когда цитируемый текст сам содержит тройные
    кавычки) возвращал хвост шаблона, закрывающие кавычки и весь следующий
    кусок тела — вместо пустого сценария."""
    body = (
        "Шаблон для заполнения:\n\n"
        "````markdown\n"
        "Пример: тройные кавычки ```внутри``` тоже возможны.\n"
        "## HowToDemo\n"
        "1. Шаг из шаблона\n"
        "````\n\n"
        "Остальной текст без настоящего сценария."
    )
    assert a._howtodemo_block(body) == ""


def test_howtodemo_block_unclosed_fence_does_not_leak_a_scenario():
    """Ревьюер воспроизвёл лично: незакрытый забор с маркером внутри
    возвращал строку из середины забора как «сценарий». Незакрытый забор
    обязан читаться как открытый до конца текста, а не как отсутствие
    маскировки вовсе."""
    body = (
        "intro text\n\n"
        "```\n"
        "some code\n"
        "## HowToDemo\n"
        "leaked line as scenario\n"
        "more code, fence never closes\n"
    )
    assert a._howtodemo_block(body) == ""


def test_howtodemo_block_preserves_a_four_backtick_fence_legitimately_inside_it():
    """Симметрично `..._preserves_a_code_fence_that_is_legitimately_inside_it`
    (тот тест — для трёх кавычек, этот — для четырёх): маскировка нужна
    только для ПОИСКА границ. Настоящий забор из четырёх кавычек, легитимно
    лежащий внутри настоящего сценария (например, цитата markdown-примера с
    собственным заголовком), обязан дойти до исполнителя дословно — а
    вложенный заголовок внутри него не должен считаться границей конца
    блока."""
    body = (
        "## HowToDemo\n\nОткрываю страницу и вижу шаблон:\n"
        "````\n"
        "```markdown\n"
        "## Пример\n"
        "```\n"
        "````\n\n"
        "## Другое\nхвост, сюда сценарий заходить не должен"
    )
    result = a._howtodemo_block(body)
    assert result == (
        "Открываю страницу и вижу шаблон:\n"
        "````\n"
        "```markdown\n"
        "## Пример\n"
        "```\n"
        "````"
    )
    assert "хвост" not in result


def test_howtodemo_approved_block_wins_over_heading():
    """Утверждённый блок старше раздела: человек подтвердил именно его."""
    body = issue_blocks.write("## Как принимаем\n\nстарый текст",
                              issue_blocks.HOWTODEMO, "утверждённый критерий")
    assert a._howtodemo_block(body) == "утверждённый критерий"


def test_howtodemo_empty_approved_block_falls_back_to_heading():
    """Пустой блок не должен затирать написанный человеком раздел."""
    body = issue_blocks.write("## Как принимаем\n\nтекст раздела",
                              issue_blocks.HOWTODEMO, "   ")
    assert a._howtodemo_block(body) == "текст раздела"


def test_howtodemo_empty_block_removal_follows_issue_blocks_marker_format(monkeypatch):
    """Ревью, находка 1 (Important). Вырезание пустого утверждённого блока
    должно идти через `issue_blocks.strip`, который берёт формат маркеров из
    `_markers()`, а не через самодельную регэксп-строку с захардкоженными
    `<!-- harness:{name}:start -->` / `:end -->` прямо в `worker/activities.py`.

    Тест меняет формат маркеров подменой `issue_blocks._markers` — ровно то,
    что случится при следующей правке формата в одном настоящем месте. Если
    `worker/activities.py` вырезает блок СВОЕЙ копией формата, а не вызовом
    `issue_blocks.strip`, вырезание после подмены молча перестаёт совпадать:
    маркеры нового формата остаются в теле и текстом попадают в сценарий
    приёмки. С вызовом `issue_blocks.strip` вырезание следует за одним
    источником формата и продолжает работать.
    """
    def custom_markers(name: str) -> tuple[str, str]:
        return f"<!-- custom:{name}:begin -->", f"<!-- custom:{name}:finish -->"

    monkeypatch.setattr(issue_blocks, "_markers", custom_markers)
    body = issue_blocks.write("## Как принимаем\n\nтекст раздела",
                              issue_blocks.HOWTODEMO, "   ")
    assert a._howtodemo_block(body) == "текст раздела"


def test_howtodemo_corrupted_approved_block_does_not_crash_the_stage(caplog):
    """Ревью, находка 2 (Important). Непарный маркер в теле Issue — например,
    буквально скопированный человеком из примера в документации, — раньше был
    инертным текстом. С приоритетом утверждённого блока над разделом
    `issue_blocks.read` кидает ValueError на такой структуре, и непойманное
    исключение уронило бы стадию `_dev_prepare` целиком. Проверяем: тело с
    одиночным непарным маркером не роняет разбор, критерий приёмки берётся из
    заголовка, а в лог уходит предупреждение о повреждённом теле — молчаливый
    отказ здесь хуже открытого.
    """
    body = "<!-- harness:howtodemo:start -->\n## Как принимаем\n\nтекст раздела"
    with caplog.at_level("WARNING", logger="activities"):
        result = a._howtodemo_block(body)
    assert result == "текст раздела"
    assert "тело повреждено" in caplog.text


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

    number = a._dev_publish(issue, "research/issue-15", [])

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

    number = a._dev_publish(issue, "research/issue-16", [])

    assert number is None, "агент не тронул ни файла — пустой прогон, PR не открывается"
    assert posts == [], "запрос на создание PR не должен был уйти"


# ────────── N2 (повторное ревью): force_include на МЕСТЕ ВЫЗОВА ──────────
#
# `force_include=(task_context.DIR,)` в `_dev_publish` (M3, ревью задачи 7) —
# СОСЕДНИЙ аргумент того же вызова `publish_worktree`, что и
# `ignore_for_empty_check` выше (M1). Тот аргумент прошлая правка закрыла
# тестом на месте вызова; этот — нет, хотя дыра ровно того же рода:
# `tests/test_github_client_pr.py` проверяет саму `publish_worktree` с
# аргументом, переданным ВРУЧНУЮ тестом, но ни один тест не проверял, что
# `_dev_publish` его действительно передаёт. Удаление строки в
# `worker/activities.py` не роняло НИ ОДНОГО из 1333 тестов.

def test_dev_publish_forces_the_harness_directory_past_the_target_repos_gitignore(
        monkeypatch, tmp_path):
    """Сквозная проверка настоящим git через `_dev_publish` (не через
    `publish_worktree` напрямую, по тому же доводу, что и у соседнего теста
    выше): `.gitignore` ЦЕЛЕВОГО репозитория игнорирует `.harness/`. Без
    `force_include` на месте вызова голый `git add -A` внутри
    `publish_worktree` молча пропустил бы каталог — PR ушёл бы с кодом
    агента, но без контекста, и без единого предупреждения."""
    import subprocess
    import github_client as gc

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)

    def fake_clone(repo, dest, branch=None):
        subprocess.run(["git", "clone", str(origin), dest], check=True, capture_output=True)
        subprocess.run(["git", "-C", dest, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", dest, "config", "user.name", "t"], check=True)
        (Path(dest) / "README.md").write_text("baseline")
        # Ровно предпосылка M3: целевой репозиторий игнорирует каталог контекста.
        (Path(dest) / ".gitignore").write_text(f"{task_context.DIR}/\n")
        subprocess.run(["git", "-C", dest, "add", "README.md", ".gitignore"], check=True)
        subprocess.run(["git", "-C", dest, "commit", "-m", "seed"],
                       check=True, capture_output=True)

    monkeypatch.setattr(a, "_clone_repo", fake_clone)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))
    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            "требования" if path.endswith("system_requirements.md") else "")

    issue = a.IssueInput(repo="o/r", issue_number=21, title="t", body="b",
                         author_login="u", author_type="User")
    a._dev_prepare(issue, "research/issue-21")

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
            return {"number": 89}

    monkeypatch.setattr(gc.requests, "post", lambda *args, **kw: _FakeResp())

    number = a._dev_publish(issue, "research/issue-21", [])

    assert number == 89
    show = subprocess.run(["git", "-C", str(clone), "show", "--stat", "HEAD"],
                          check=True, capture_output=True, text=True).stdout
    assert "app.py" in show, "код агента не доехал до коммита"
    assert ".harness/context.md" in show, (
        ".harness проигнорирован .gitignore целевого репозитория, несмотря на "
        "force_include"
    )


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


def test_howtodemo_block_russian_headings():
    """Раздел приёмки, написанный по-русски, распознаётся наравне с английским.

    Отказ, ради которого это написано: poh-demo-checkout#163 приехал с
    разделом `## Как принимаем` и блоками curl «было/должно работать»,
    прошёл разработку, PR и мерж — а приёмка всё это время отвечала
    «проверять нечем».
    """
    for heading in ("## Как принимаем", "## Как проверяем",
                    "## Приёмка", "## Приемка", "## Как демонстрируем",
                    "### Как принимаем"):
        body = f"вступление\n\n{heading}\n\nБыло 404, стало 405\n\n## Другое\nхвост"
        assert a._howtodemo_block(body) == "Было 404, стало 405", heading


def test_howtodemo_russian_heading_as_part_of_another_word_does_not_trigger():
    """`## Приёмка-агент: как он устроен` — это описание, а не сценарий."""
    body = "## Приёмка-агент: как он устроен\n\nОписание агента, не сценарий."
    assert a._howtodemo_block(body) == ""


def test_howtodemo_russian_heading_with_empty_body_is_no_scenario():
    """Заголовок есть, под ним пусто — сценария нет (R7).

    Пустой критерий хуже отсутствующего: он создаёт видимость приёмки.
    """
    body = "## Как принимаем\n\n\n## Другое\nхвост"
    assert a._howtodemo_block(body) == ""


def test_howtodemo_russian_heading_inside_code_fence_is_not_a_scenario():
    """Заголовок, процитированный примером, сценарием не считается (R8)."""
    body = (
        "Шаблон задачи:\n\n"
        "```markdown\n"
        "## Как принимаем\n"
        "тут пишем сценарий\n"
        "```\n\n"
        "Настоящего раздела нет."
    )
    assert a._howtodemo_block(body) == ""
