"""Сорванный анализ отдаёт сделанное, а повтор продолжает с места обрыва.

Цепочка FNR стоит тех же денег, что БФТ, и рвётся по тем же причинам: лимит
провайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу.
"""

import pytest

import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=11, title="t", body="b")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    clone = root / "repo"
    (clone / "sa_documentation" / "FNR" / "FNR_1").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")
    # Вход стадии `task` — артефакт предшественника: без него guard остановит
    # прогон раньше, чем дело дойдёт до проверки пропуска.
    (clone / "sa_documentation" / "FNR" / "FNR_1" / "repowise-dialog.md").write_text("диалог")
    monkeypatch.setattr(activities, "_workspace_dir", lambda a: root)
    monkeypatch.setattr(activities, "_clone_dir", lambda a: str(clone))
    return clone


@pytest.mark.timeout(30)
async def test_partial_publish_pushes_surviving_artifacts(workspace, monkeypatch):
    (workspace / "sa_documentation" / "FNR" / "FNR_1" / "task.md").write_text("задача")
    pushed, commented = {}, []
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda repo, branch, files, msg: pushed.update(files))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: commented.append(body))
    monkeypatch.setattr(activities, "_entire_session", lambda d: ("", ""))

    saved = await activities.publish_analysis_partial(_analyze(), "524")

    assert saved, "уцелевшие артефакты не собраны"
    assert pushed, "ничего не отправлено в ветку"
    assert "⏸" in commented[0] and "524" in commented[0]
    assert "продолжит с места обрыва" in commented[0]


@pytest.mark.timeout(30)
async def test_partial_publish_is_silent_without_artifacts(workspace, monkeypatch):
    # Ни одна стадия не успела: каталог пуст, хвалиться нечем.
    (workspace / "sa_documentation" / "FNR" / "FNR_1" / "repowise-dialog.md").unlink()
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda *a: pytest.fail("пустую ветку не публикуем"))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda *a: pytest.fail("хвалиться нечем"))

    assert await activities.publish_analysis_partial(_analyze(), "524") == []


@pytest.mark.timeout(30)
async def test_partial_publish_survives_a_missing_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(activities, "_workspace_dir", lambda a: tmp_path / "нет")
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda *a: pytest.fail("публиковать нечего"))

    assert await activities.publish_analysis_partial(_analyze(), "524") == []


@pytest.mark.timeout(30)
async def test_ready_stage_is_skipped_without_calling_the_agent(workspace, monkeypatch):
    prompt, expected, _ = activities._fnr_stage("task", "описание")
    ready = workspace / expected
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.write_text("документ прошлого прогона")
    monkeypatch.setattr(activities, "_build_task_context", lambda a: "описание")
    monkeypatch.setattr(activities, "_write_repowise_config", lambda a, d: None)
    monkeypatch.setattr(activities, "_run_claude", lambda *a, **kw: pytest.fail(
        "готовая стадия прогналась заново — прогон платит второй раз"))

    result = await activities.run_fnr_stage(_analyze(), "task")

    assert result["outcome"] == "skipped"
    assert ready.read_text() == "документ прошлого прогона"


@pytest.mark.timeout(30)
async def test_empty_artifact_does_not_count_as_done(workspace, monkeypatch):
    prompt, expected, _ = activities._fnr_stage("task", "описание")
    ready = workspace / expected
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.write_text("")
    ran = []

    def fake_claude(prompt, cwd, mcp=None):
        ran.append(prompt)
        ready.write_text("свежий документ")

    monkeypatch.setattr(activities, "_build_task_context", lambda a: "описание")
    monkeypatch.setattr(activities, "_write_repowise_config", lambda a, d: None)
    monkeypatch.setattr(activities, "_run_claude", fake_claude)

    await activities.run_fnr_stage(_analyze(), "task")

    assert ran, "пустой артефакт принят за готовую стадию"
