import asyncio
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


def test_heartbeat_fires_during_a_long_stage(monkeypatch, wired):
    """Heartbeat обязан идти ВНУТРИ стадии, а не только между ними: одна
    стадия claude -p может занять до CLAUDE_STAGE_TIMEOUT_SEC (900с) при
    heartbeat_timeout воркфлоу в 300с — без периодического сигнала изнутри
    сервер счёл бы activity мёртвой и (при maximum_attempts=1) уронил бы
    весь прогон. Здесь клонирование намеренно длится дольше урезанного
    HEARTBEAT_INTERVAL_SEC, и мы ловим лейбл "cloning" — его шлёт только
    _run_with_heartbeat, пока поток занят (не путать с граничным "cloned"
    после стадии)."""
    monkeypatch.setattr(activities, "HEARTBEAT_INTERVAL_SEC", 0.01)

    def slow_clone(repo, dest):
        time.sleep(0.05)
        Path(dest).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(activities, "_clone_repo", slow_clone)

    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert wired["beats"].count("cloning") >= 1


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


# --- Regression: auth-токен не должен попадать в argv / текст исключения ---
#
# subprocess.CalledProcessError.__str__ и subprocess.TimeoutExpired.__str__
# рендерят cmd целиком. Если токен подставлен прямо в URL как элемент argv,
# ЛЮБОЙ сбой git clone (протухший токен, сетевой сбой, таймаут) унесёт живой
# GitHub-токен в Temporal event history и логи воркера — именно туда, куда
# человек полезет отлаживать сбой.

def test_clone_failure_never_leaks_token_in_calledprocesserror(monkeypatch):
    monkeypatch.setattr(activities.github_client, "auth_token", lambda: _SENTINEL_TOKEN)

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
    monkeypatch.setattr(activities.github_client, "auth_token", lambda: _SENTINEL_TOKEN)

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", activities.CLONE_TIMEOUT_SEC))

    monkeypatch.setattr(activities.subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        activities._clone_repo("o/r", "/tmp/does-not-matter")

    exc = exc_info.value
    assert _SENTINEL_TOKEN not in str(exc)
    assert _SENTINEL_TOKEN not in repr(exc)


def test_blocking_stages_run_off_the_event_loop_thread(wired, monkeypatch):
    """Блокирующие вызовы обязаны идти через asyncio.to_thread.

    Воркер крутит один event loop; синхронный subprocess.run на 900с заблокировал
    бы поток целиком — heartbeat не ушёл бы на сервер, другие issue встали бы.
    asyncio.run() держит loop на главном потоке, поэтому исполнение стадии на
    НЕ-главном потоке доказывает, что вынос в пул реально произошёл."""
    threads = {}

    def record(prompt, cwd):
        threads["claude"] = threading.current_thread()
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

    # Переопределяем поверх фикстуры wired через monkeypatch: последний setattr
    # выигрывает, и обе подмены откатятся чисто после теста.
    monkeypatch.setattr(activities, "_run_claude", record)
    asyncio.run(activities.run_analysis_pipeline(_analyze()))

    assert threads["claude"] is not threading.main_thread()


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


def test_fnr_stage_names_are_the_five_stages():
    assert activities.FNR_STAGE_NAMES == ("task", "concept", "debate", "sysreq", "validate")


def test_fnr_stage_lookup_returns_prompt_expected_and_input():
    prompt, expected, requires = activities._fnr_stage("concept", "Заголовок\n\nтело")
    assert prompt == f"/fnr-concept {activities.FNR_DIR}/task.md"
    assert expected == f"{activities.FNR_DIR}/concept.md"
    assert requires == f"{activities.FNR_DIR}/task.md"


def test_fnr_stage_task_has_no_required_input():
    _, _, requires = activities._fnr_stage("task", "desc")
    assert requires is None


def test_fnr_stage_unknown_raises():
    with pytest.raises(ValueError, match="неизвестная стадия"):
        activities._fnr_stage("nope", "desc")


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
    result = asyncio.run(activities.run_fnr_stage(a, "task"))
    assert result["stage"] == "task"
    assert result["artifact"] == f"{activities.FNR_DIR}/task.md"
    assert result["bytes"] > 0
    assert any(p.startswith("/fnr-new-task") for p in stage_env["claude_prompts"])


def test_stage_without_expected_artifact_reports_none(stage_env):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    asyncio.run(activities.run_fnr_stage(a, "task"))
    asyncio.run(activities.run_fnr_stage(a, "concept"))
    result = asyncio.run(activities.run_fnr_stage(a, "debate"))  # debate: артефакта нет
    assert result == {"stage": "debate", "artifact": None, "bytes": 0}


def test_stage_missing_expected_artifact_raises(stage_env, monkeypatch):
    a = _analyze()
    asyncio.run(activities.prepare_workspace(a))
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)  # ничего не пишет
    with pytest.raises(RuntimeError, match="task.md не создан"):
        asyncio.run(activities.run_fnr_stage(a, "task"))


def test_stage_without_workspace_fails_fast(stage_env):
    with pytest.raises(RuntimeError, match="потерян"):
        asyncio.run(activities.run_fnr_stage(_analyze(), "task"))


def test_stage_without_input_artifact_fails_fast(stage_env):
    asyncio.run(activities.prepare_workspace(_analyze()))
    with pytest.raises(RuntimeError, match="нет входа"):  # concept требует task.md
        asyncio.run(activities.run_fnr_stage(_analyze(), "concept"))


def test_stage_heartbeats_during_long_claude(stage_env, monkeypatch):
    monkeypatch.setattr(activities, "HEARTBEAT_INTERVAL_SEC", 0.01)
    asyncio.run(activities.prepare_workspace(_analyze()))

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
    seen = {}

    def record(prompt, cwd):
        seen["thread"] = threading.current_thread()
        fnr = Path(cwd) / activities.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        (fnr / "task.md").write_text("# task", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", record)
    asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    assert seen["thread"] is not threading.main_thread()
