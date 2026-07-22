import asyncio
from pathlib import Path

import pytest

import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="Ревизия", body="текст", comment_id=1)


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Подменяет внешние эффекты, оставляя настоящую оркестрацию стадий."""
    state = {"stages": [], "beats": [], "pushed": None, "comment": None, "clone_dir": None}

    monkeypatch.setattr(activities.activity, "heartbeat",
                        lambda *a: state["beats"].append(a[0] if a else None))

    def fake_clone(repo, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)
        state["clone_dir"] = dest

    def fake_repomix(clone_dir):
        state["stages"].append("repomix")

    def fake_claude(prompt, cwd):
        # первое слово промпта — сама FNR-команда
        state["stages"].append(prompt.split()[0])
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        produced = {
            "/fnr-new-task": "task.md",
            "/fnr-concept": "concept.md",
            "/fnr-system-requirements": "system_requirements.md",
            "/validate-doc": "validation.md",
        }.get(prompt.split()[0])
        if produced:
            (fnr / produced).write_text(f"# {produced}", encoding="utf-8")

    monkeypatch.setattr(activities, "_clone_repo", fake_clone)
    monkeypatch.setattr(activities, "_run_repomix", fake_repomix)
    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda repo, branch, files, message: state.update(pushed=(branch, dict(files))))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: state.update(comment=body))
    return state


def test_runs_all_five_fnr_stages_in_order(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert wired["stages"] == [
        "repomix",
        "/fnr-new-task",
        "/fnr-concept",
        "/fnr-debate",
        "/fnr-system-requirements",
        "/validate-doc",
    ]


def test_heartbeats_at_least_once_per_stage(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))
    # clone + repomix + 5 стадий
    assert len(wired["beats"]) >= 7


def test_pushes_artifacts_to_research_branch(wired):
    branch = asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert branch == "research/issue-5"
    pushed_branch, files = wired["pushed"]
    assert pushed_branch == "research/issue-5"
    assert f"{activities.FNR_DIR}/system_requirements.md" in files
    assert len(files) == 4


def test_summary_comment_links_artifacts(wired):
    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    body = wired["comment"]
    assert "research/issue-5" in body
    assert "system_requirements.md" in body
    assert len(body) <= 65536


def test_missing_expected_artifact_fails_the_stage(monkeypatch, wired):
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)  # ничего не пишет

    with pytest.raises(RuntimeError, match="system_requirements.md|task.md"):
        asyncio.run(activities.run_analysis_pipeline(_analyze()))


def test_workspace_is_removed_even_on_failure(monkeypatch, wired):
    seen = {}
    real_mkdtemp = activities.tempfile.mkdtemp

    def tracking_mkdtemp(*a, **k):
        seen["dir"] = real_mkdtemp(*a, **k)
        return seen["dir"]

    monkeypatch.setattr(activities.tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(activities, "_run_claude",
                        lambda prompt, cwd: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert not Path(seen["dir"]).exists()
