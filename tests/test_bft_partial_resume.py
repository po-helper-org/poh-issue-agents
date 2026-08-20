"""Сорванный БФТ отдаёт сделанное, а повтор продолжает с места обрыва.

Прогон рвётся чаще от чужого: провайдер отвечает 524, кончается лимит, стенд
передеплоивают посреди работы. Раньше это стоило всей работы — артефакты жили в
каталоге, который `cleanup` снимал на любом исходе.
"""

import asyncio

import pytest

import activities
from shared import bft
from shared.workflow_types import BftRequest


def _req():
    return BftRequest(repo="o/r", issue_number=41, title="t", body="b",
                      mode=bft.DEEP, instructions="")


# --- Карта стадий и остатка ---

def test_stages_without_artifact_are_not_in_the_map():
    """`index` строит каталог, `debate` дописывает вердикт — файла у них нет."""
    mapped = bft.stage_artifacts(41)
    assert "index" not in mapped and "debate" not in mapped
    assert set(mapped) == {"context", "problem", "concept", "draft", "validate"}


def test_done_stages_reads_only_existing_artifacts():
    have = {bft.stage_artifacts(41)["context"], bft.stage_artifacts(41)["problem"]}
    done = bft.done_stages(41, lambda path: path in have)
    assert done == ["context", "problem"]


def test_remaining_keeps_canonical_order_and_includes_fileless_stages():
    left = bft.remaining_stages(41, ["context", "problem"])
    assert left == ["index", "concept", "debate", "draft", "validate"]


# --- Комментарий о частичном прогоне ---

def test_partial_summary_names_loss_survivors_and_next_step():
    text = bft.render_partial_summary(
        "o/r", 41, [bft.document_path(41)], ["context", "problem", "concept", "draft"],
        "InternalServerError: Error code: 524")

    assert "524" in text, "человек должен видеть, что именно оборвало прогон"
    assert "issue-41.md" in text, "уцелевшие артефакты не названы"
    assert "`validate`" in text, "не сказано, что осталось прогнать"
    assert "продолжит с места обрыва" in text


def test_partial_summary_is_honest_when_nothing_survived():
    text = bft.render_partial_summary("o/r", 41, [], [], "rate limit")
    assert "Ни одна стадия не успела дать артефакт" in text


# --- Публикация сделанного ---

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    clone = tmp_path / "repo"
    (clone / bft.artefacts_dir(41)).mkdir(parents=True)
    (clone / bft.artefacts_dir(41) / "problem.md").write_text("проблема")
    (clone / bft.artefacts_dir(41) / "bft-context-pack.md").write_text("пак")
    monkeypatch.setattr(activities, "_bft_clone_dir", lambda req: str(clone))
    return clone


@pytest.mark.timeout(30)
async def test_partial_publish_pushes_what_exists(workspace, monkeypatch):
    pushed, commented = {}, []
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda repo, branch, files, msg: pushed.update(files))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: commented.append(body))

    done = await activities.publish_bft_partial(_req(), "524")

    assert done == ["context", "problem"], "стадии по артефактам определены неверно"
    assert any(name.endswith("problem.md") for name in pushed)
    assert "⏸" in commented[0] and "524" in commented[0]


@pytest.mark.timeout(30)
async def test_partial_publish_survives_a_missing_workspace(tmp_path, monkeypatch):
    """Каталог мог уже уйти вместе с воркером — это не повод падать поверх сбоя."""
    monkeypatch.setattr(activities, "_bft_clone_dir",
                        lambda req: str(tmp_path / "нет-такого"))
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda *a: pytest.fail("публиковать нечего"))

    assert await activities.publish_bft_partial(_req(), "524") == []


@pytest.mark.timeout(30)
async def test_partial_publish_says_nothing_when_no_artifacts(tmp_path, monkeypatch):
    clone = tmp_path / "repo"
    (clone / bft.artefacts_dir(41)).mkdir(parents=True)
    monkeypatch.setattr(activities, "_bft_clone_dir", lambda req: str(clone))
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda *a: pytest.fail("пустую ветку не публикуем"))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a: pytest.fail("хвалиться нечем"))

    assert await activities.publish_bft_partial(_req(), "524") == []


# --- Продолжение с места обрыва ---

@pytest.fixture
def ready_workspace(tmp_path, monkeypatch):
    clone = tmp_path / "repo"
    (clone / "sa_documentation").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")
    (clone / bft.artefacts_dir(41)).mkdir(parents=True)
    (clone / bft.artefacts_dir(41) / "concept.md").write_text("концепт")
    monkeypatch.setattr(activities, "_bft_clone_dir", lambda req: str(clone))
    return clone


@pytest.mark.timeout(30)
async def test_stage_with_ready_artifact_is_skipped(ready_workspace, monkeypatch):
    document = ready_workspace / bft.document_path(41)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("документ прошлого прогона")
    monkeypatch.setattr(activities, "_run_claude", lambda *a, **kw: pytest.fail(
        "готовая стадия прогналась заново — прогон платит второй раз"))

    result = await activities.run_bft_stage(_req(), "draft")

    assert result["skipped"] is True
    assert document.read_text() == "документ прошлого прогона", "артефакт переписан"


@pytest.mark.timeout(30)
async def test_empty_artifact_does_not_count_as_done(ready_workspace, monkeypatch):
    """Файл нулевого размера — оборванная запись, а не сделанная работа."""
    document = ready_workspace / bft.document_path(41)
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("")
    ran = []

    def fake_claude(prompt, cwd):
        ran.append(prompt)
        document.write_text("свежий документ")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)

    await activities.run_bft_stage(_req(), "draft")

    assert ran, "пустой артефакт принят за готовую стадию"


# --- Журнал прогона ---

def test_dialog_log_lives_next_to_artifacts():
    """Журнал уезжает в ту же ветку — отдельного хранилища не заводим."""
    assert bft.dialog_log_path(41).startswith(bft.artefacts_dir(41))


def test_dialog_entry_is_a_table_row_with_the_essentials():
    row = bft.render_dialog_entry(
        stage="draft", actor="прямой вызов (glm-4.6)", step="каскад требований",
        outcome="добор", detail="якорей 20 из 24", elapsed=129.4, tokens="43k/8k")

    assert row.startswith("|") and row.endswith("|")
    for cell in ("draft", "прямой вызов (glm-4.6)", "добор", "129 с", "43k/8k",
                 "якорей 20 из 24"):
        assert cell in row


def test_dialog_entry_does_not_break_the_table():
    row = bft.render_dialog_entry(stage="draft", actor="claude -p", step="/bft-draft",
                                  outcome="сбой",
                                  detail="строка с | трубой\nи переводом строки")
    assert row.count("\n") == 0, "перевод строки разорвал бы таблицу"
    assert "\\|" in row, "труба в тексте не экранирована"


def test_dialog_log_starts_with_a_header_then_appends(tmp_path):
    clone = tmp_path / "repo"
    activities._append_dialog(str(clone), 41, "| a | b | c | d | e | f | g |")
    activities._append_dialog(str(clone), 41, "| h | i | j | k | l | m | n |")

    text = (clone / bft.dialog_log_path(41)).read_text()
    assert text.startswith("# Журнал прогона БФТ")
    assert text.count("| a |") == 1 and text.count("| h |") == 1


def test_dialog_log_failure_does_not_break_the_stage(monkeypatch, tmp_path):
    """Журнал вспомогательный: из-за него не падает стадия, которая отработала."""
    def boom(*a, **kw):
        raise OSError("диск кончился")

    monkeypatch.setattr(activities.Path, "mkdir", boom)
    activities._append_dialog(str(tmp_path), 41, "| строка |")  # не бросает


@pytest.mark.timeout(30)
async def test_agent_stage_leaves_the_log_to_entire(ready_workspace, monkeypatch):
    """У стадии агента есть сессия entire — вторая запись о ней не нужна."""
    def fake_claude(prompt, cwd):
        (ready_workspace / bft.document_path(41)).parent.mkdir(parents=True, exist_ok=True)
        (ready_workspace / bft.document_path(41)).write_text("документ")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)

    await activities.run_bft_stage(_req(), "draft")

    assert not (ready_workspace / bft.dialog_log_path(41)).exists()
