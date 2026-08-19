import asyncio
import pathlib
import subprocess
import threading
import time
from pathlib import Path

import pytest

import activities
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=5, title="Ревизия", body="текст", comment_id=1)


# Заведомо отличимый токен: если он всплывёт хоть где-то в тексте исключения,
# assert укажет ровно на него, а не на случайное совпадение подстроки.
_SENTINEL_TOKEN = "ghs_SENTINELTOKENDONOTLEAK000000000000"


# --- Regression: auth-токен не должен попадать в argv / текст исключения ---
#
# subprocess.CalledProcessError.__str__ и subprocess.TimeoutExpired.__str__
# рендерят cmd целиком. Если токен подставлен прямо в URL как элемент argv,
# ЛЮБОЙ сбой git clone (протухший токен, сетевой сбой, таймаут) унесёт живой
# GitHub-токен в Temporal event history и логи воркера — именно туда, куда
# человек полезет отлаживать сбой.

def test_clone_failure_never_leaks_token_in_calledprocesserror(monkeypatch):
    monkeypatch.setattr(activities.github_client, "auth_token", lambda repo: _SENTINEL_TOKEN)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        # реалистичный провал git clone: неверные/протухшие учётные данные
        raise subprocess.CalledProcessError(
            128, cmd, output="", stderr="fatal: Authentication failed\n",
        )

    monkeypatch.setattr(activities.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        activities._clone_repo("o/r", "/tmp/does-not-matter")

    exc = exc_info.value
    assert _SENTINEL_TOKEN not in str(exc)
    assert _SENTINEL_TOKEN not in repr(exc)
    assert _SENTINEL_TOKEN not in " ".join(str(a) for a in captured["cmd"])
    assert _SENTINEL_TOKEN not in (exc.output or "")
    assert _SENTINEL_TOKEN not in (exc.stderr or "")


def test_clone_timeout_never_leaks_token(monkeypatch):
    monkeypatch.setattr(activities.github_client, "auth_token", lambda repo: _SENTINEL_TOKEN)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", activities.CLONE_TIMEOUT_SEC))

    monkeypatch.setattr(activities.subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        activities._clone_repo("o/r", "/tmp/does-not-matter")

    exc = exc_info.value
    assert _SENTINEL_TOKEN not in str(exc)
    assert _SENTINEL_TOKEN not in repr(exc)


# --- claude креды выводятся из ZAI_* (единый ключ z.ai, как в main) ---

def test_claude_creds_derived_from_zai(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "zkey")
    monkeypatch.setenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")

    token, base = activities._claude_anthropic_creds()

    assert token == "zkey"
    # тот же хост, Anthropic-путь
    assert base == "https://api.z.ai/api/anthropic"


def test_explicit_anthropic_overrides_zai(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zkey")
    monkeypatch.setenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "atok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://custom/anthropic")

    token, base = activities._claude_anthropic_creds()

    assert (token, base) == ("atok", "https://custom/anthropic")


def test_claude_creds_empty_when_nothing_set(monkeypatch):
    for v in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ZAI_API_KEY", "ZAI_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    assert activities._claude_anthropic_creds() == ("", "")




def test_fnr_stage_names_are_the_six_stages():
    assert activities.FNR_STAGE_NAMES == (
        "repowise", "task", "concept", "debate", "sysreq", "validate")


def test_fnr_stage_lookup_returns_prompt_expected_and_input():
    prompt, expected, requires = activities._fnr_stage("concept", "Заголовок\n\nтело")
    assert prompt == f"/fnr-concept {activities.FNR_DIR}/task.md"
    assert expected == f"{activities.FNR_DIR}/concept.md"
    assert requires == f"{activities.FNR_DIR}/task.md"


def test_fnr_stage_repowise_has_no_required_input():
    # Первая стадия конвейера: требовать от неё чего-либо на входе не с чего.
    _, _, requires = activities._fnr_stage("repowise", "desc")
    assert requires is None


def test_fnr_stage_task_requires_dialog_artifact():
    # Пропустить сбор контекста незаметно нельзя. Артефакт создаётся и при
    # недоступном Repowise, поэтому guard не делает сервис обязательным.
    _, _, requires = activities._fnr_stage("task", "desc")
    assert requires == f"{activities.FNR_DIR}/repowise-dialog.md"


def test_fnr_stage_unknown_raises():
    with pytest.raises(ValueError, match="неизвестная стадия"):
        activities._fnr_stage("nope", "desc")


def test_fnr_stage_sources_stay_consistent():
    # Имена стадий живут в трёх местах (_fnr_stages, FNR_STAGE_NAMES,
    # _FNR_STAGE_REQUIRES). Рассинхрон превратил бы чистый ValueError из
    # _fnr_stage в сырой KeyError — ловим его здесь, а не в проде.
    names = {n for n, _, _ in activities._fnr_stages("desc")}
    assert names == set(activities.FNR_STAGE_NAMES) == set(activities._FNR_STAGE_REQUIRES)


def _seed_dialog(analyze):
    """Стадия repowise уже отработала: её артефакт — вход стадии `task`.

    Тесты ниже начинают с `task`, а в живом прогоне к этому моменту диалог уже
    состоялся либо деградировал — в обоих случаях файл на месте.
    """
    fnr = pathlib.Path(activities._clone_dir(analyze)) / activities.FNR_DIR
    fnr.mkdir(parents=True, exist_ok=True)
    (fnr / "repowise-dialog.md").write_text("# Диалог\n", encoding="utf-8")


@pytest.fixture
def stage_env(monkeypatch, tmp_path):
    """Реальный каталог под ANALYSIS_WORKSPACE_ROOT; внешние эффекты — заглушки."""
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    state = {"beats": [], "claude_prompts": [], "pushed": None, "comment": None}

    monkeypatch.setattr(activities.activity, "heartbeat",
                        lambda *a: state["beats"].append(a[0] if a else None))

    def fake_clone(repo, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)

    def fake_repomix(clone_dir):
        out = Path(clone_dir) / "sa_documentation" / "repomix-output.xml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<repo/>", encoding="utf-8")

    def fake_claude(prompt, cwd):
        state["claude_prompts"].append(prompt)
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        produced = {
            "/repowise-context": "repowise-dialog.md",
            "/fnr-new-task": "task.md",
            "/fnr-concept": "concept.md",
            "/fnr-system-requirements": "system_requirements.md",
            "/validate-doc": "validation.md",
        }.get(prompt.split()[0])
        if produced:
            (fnr / produced).write_text(f"# {produced}\n", encoding="utf-8")

    monkeypatch.setattr(activities, "_clone_repo", fake_clone)
    monkeypatch.setattr(activities, "_run_repomix", fake_repomix)
    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    monkeypatch.setattr(activities.github_client, "push_artifacts_to_branch",
                        lambda repo, branch, files, message: state.update(pushed=(branch, dict(files))))
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: state.update(comment=body))
    return state


def test_workspace_dir_is_deterministic_under_root(stage_env, tmp_path):
    d1 = activities._workspace_dir(_analyze())
    d2 = activities._workspace_dir(_analyze())
    assert d1 == d2
    assert str(tmp_path) in str(d1)
    assert d1.name == "analysis-o__r-5"


def test_build_workspace_clones_and_packs(stage_env):
    clone_dir = activities._build_workspace(_analyze())
    assert (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists()


def test_build_workspace_wipes_prior_remnant(stage_env):
    stale = activities._workspace_dir(_analyze()) / "repo" / "STALE.txt"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("old", encoding="utf-8")
    activities._build_workspace(_analyze())
    assert not stale.exists()


def test_require_workspace_missing_repomix_fails_fast(stage_env):
    with pytest.raises(RuntimeError, match="потерян"):
        activities._require_workspace(_analyze(), None)


def test_require_workspace_missing_input_fails_fast(stage_env):
    activities._build_workspace(_analyze())  # repomix есть, task.md нет
    with pytest.raises(RuntimeError, match="нет входа"):
        activities._require_workspace(_analyze(), f"{activities.FNR_DIR}/task.md")


def test_prepare_workspace_builds_clone_and_repomix(stage_env):
    asyncio.run(activities.prepare_workspace(_analyze()))
    clone_dir = activities._clone_dir(_analyze())
    assert Path(clone_dir).exists()
    assert (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists()


def test_stage_reports_stage_artifact_and_size(stage_env):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    _seed_dialog(a)
    result = asyncio.run(activities.run_fnr_stage(a, "task"))
    assert result["stage"] == "task"
    assert result["artifact"] == f"{activities.FNR_DIR}/task.md"
    assert result["bytes"] > 0
    assert any(p.startswith("/fnr-new-task") for p in stage_env["claude_prompts"])


def test_stage_without_expected_artifact_reports_none(stage_env):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    _seed_dialog(a)
    asyncio.run(activities.run_fnr_stage(a, "task"))
    asyncio.run(activities.run_fnr_stage(a, "concept"))
    result = asyncio.run(activities.run_fnr_stage(a, "debate"))  # debate: артефакта нет
    assert result == {"stage": "debate", "artifact": None, "bytes": 0}


def test_stage_missing_expected_artifact_raises(stage_env, monkeypatch):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    _seed_dialog(a)
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)  # ничего не пишет
    with pytest.raises(RuntimeError, match="task.md не создан"):
        asyncio.run(activities.run_fnr_stage(a, "task"))


def test_stage_without_workspace_fails_fast(stage_env):
    with pytest.raises(RuntimeError, match="потерян"):
        asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    # Fail-fast обязан сработать ДО дорогого claude -p, не после.
    assert stage_env["claude_prompts"] == []


def test_stage_without_input_artifact_fails_fast(stage_env):
    asyncio.run(activities.prepare_workspace(_analyze()))
    with pytest.raises(RuntimeError, match="нет входа"):  # concept требует task.md
        asyncio.run(activities.run_fnr_stage(_analyze(), "concept"))
    # Guard входа тоже до claude: пропущенный предшественник не жжёт вызов.
    assert stage_env["claude_prompts"] == []


def test_stage_heartbeats_during_long_claude(stage_env, monkeypatch):
    monkeypatch.setattr(activities, "HEARTBEAT_INTERVAL_SEC", 0.01)
    asyncio.run(activities.prepare_workspace(_analyze()))
    _seed_dialog(_analyze())

    def slow_claude(prompt, cwd):
        time.sleep(0.05)
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        (fnr / "task.md").write_text("# task", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", slow_claude)
    asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    assert stage_env["beats"].count("task") >= 1


def test_stage_runs_claude_off_event_loop_thread(stage_env, monkeypatch):
    asyncio.run(activities.prepare_workspace(_analyze()))
    _seed_dialog(_analyze())
    seen = {}

    def record(prompt, cwd):
        seen["thread"] = threading.current_thread()
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        (fnr / "task.md").write_text("# task", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", record)
    asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    assert seen["thread"] is not threading.main_thread()


def test_publish_pushes_branch_and_comments(stage_env):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    for name in activities.FNR_STAGE_NAMES:
        asyncio.run(activities.run_fnr_stage(a, name))
    branch = asyncio.run(activities.publish_analysis(a))
    assert branch == "research/issue-5"
    pushed_branch, files = stage_env["pushed"]
    assert pushed_branch == "research/issue-5"
    assert f"{activities.FNR_DIR}/system_requirements.md" in files
    assert "research/issue-5" in stage_env["comment"]
    assert "system_requirements.md" in stage_env["comment"]


def test_publish_without_artifacts_raises(stage_env, monkeypatch):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    monkeypatch.setattr(activities, "_collect_fnr_artifacts", lambda clone_dir: {})
    with pytest.raises(RuntimeError, match="ни одного артефакта"):
        asyncio.run(activities.publish_analysis(a))


def test_cleanup_removes_workspace(stage_env):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    assert activities._workspace_dir(a).exists()
    asyncio.run(activities.cleanup_workspace(a))
    assert not activities._workspace_dir(a).exists()


def test_cleanup_is_idempotent_when_absent(stage_env):
    # каталога нет — cleanup не должен падать
    asyncio.run(activities.cleanup_workspace(_analyze()))


def test_enriched_context_reaches_task_stage(monkeypatch, stage_env):
    """Контекст обсуждения обязан долетать до стадии /fnr-new-task, а не
    оставаться в title+body."""
    monkeypatch.setattr(
        activities.github_client, "list_comments",
        lambda repo, n, limit=50: [
            {"user": {"login": "kibarik"},
             "body": "Зафиксировано: retry-only",
             "created_at": "2026-07-20T10:00:00Z"}
        ],
    )
    monkeypatch.setattr(activities.github_client, "list_linked_prs",
                        lambda repo, n, limit=20: [])

    asyncio.run(activities.prepare_workspace(_analyze()))
    _seed_dialog(_analyze())
    asyncio.run(activities.run_fnr_stage(_analyze(), "task"))

    task_prompt = stage_env["claude_prompts"][0]
    assert task_prompt.startswith("/fnr-new-task")
    assert "Зафиксировано: retry-only" in task_prompt
