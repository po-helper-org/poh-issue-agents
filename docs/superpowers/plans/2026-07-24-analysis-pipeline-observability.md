# Прозрачность пайплайна /analyze — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Разбить монолитную activity `run_analysis_pipeline` на оркеструемые воркфлоу пер-стадийные activity, чтобы каждая стадия FNR была отдельным шагом Temporal Event History с таймингом и именем артефакта.

**Architecture:** `IssueAnalysis.run` перестаёт звать один монолит и последовательно вызывает `prepare_workspace` → 5× `run_fnr_stage` (по константе `FNR_STAGE_NAMES`) → `publish_analysis`, с `cleanup_workspace` в `finally`. Все activity делят детерминированный рабочий каталог, выведенный из `repo`+`issue_number`; repomix пакуется один раз. Стадия без своего входного артефакта падает fail-fast (без тихого пере-клона).

**Tech Stack:** Python 3.11+, temporalio (Worker/Workflow/activity), pytest + pytest-asyncio, `temporalio.testing.WorkflowEnvironment`, `claude -p`, repomix.

## Global Constraints

- Прогон тестов: `.venv/bin/python -m pytest` из корня воркта b6c73c (`make test` и `.venv/bin/pytest` сломаны — память проекта).
- Все правки — в воркте `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.claude/worktrees/issue-agents-solution-generation-b6c73c`. Пути в задачах — репо-относительные от этого корня.
- DRY_RUN не трогаем: мутации GitHub гейтятся внутри `github_client` (`push_artifacts_to_branch`/`post_comment`).
- Токен клонирования никогда не в argv: `_clone_repo` переиспользуется как есть (credential.helper через env).
- Heartbeat идёт ВНУТРИ каждого долгого вызова через существующий `_run_with_heartbeat(fn, *args, label=...)`.
- Воркфлоу-код детерминирован: итерируем модульную константу-tuple, никаких wall-clock/IO.
- Допущение: одна реплика воркера (`max_concurrent_activities=3`) — все activity одного прогона попадают в один контейнер.
- Существующие константы в `worker/activities.py`: `FNR_DIR = "sa_documentation/FNR/FNR_1"`, `ARTIFACT_FILES = ("task.md","concept.md","system_requirements.md","validation.md")`, `CLAUDE_STAGE_TIMEOUT_SEC=900`, `REPOMIX_TIMEOUT_SEC=600`, `CLONE_TIMEOUT_SEC=300`, `HEARTBEAT_INTERVAL_SEC=30.0`. repomix пишет в `<clone_dir>/sa_documentation/repomix-output.xml`.
- `AnalyzeInput` (shared/workflow_types.py) поля: `repo`, `issue_number`, `title`, `body`, `comment_id`.

---

## Карта файлов

- **Modify** `worker/activities.py` — новые константы/хелперы + 4 activity; в конце (Task 7) удаление монолита `run_analysis_pipeline`.
- **Modify** `worker/workflows.py` — переписать тело `IssueAnalysis.run`.
- **Modify** `worker/worker.py:44` — заменить регистрацию `run_analysis_pipeline` на 4 новые activity.
- **Modify** `tests/test_analysis_pipeline.py` — новые тесты activity; в Task 7 удалить мёртвые тесты монолита.
- **Modify** `tests/test_workflow_analysis.py` — тесты оркестрации.

---

### Task 1: Метаданные стадий — имена, входы, поиск по имени

**Files:**
- Modify: `worker/activities.py` (рядом с `_fnr_stages`, ~317-330)
- Test: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Produces: `activities.FNR_STAGE_NAMES: tuple[str, ...]`; `activities._fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]` возвращает `(prompt, expected_artifact, required_input)`.

- [ ] **Step 1: Написать падающий тест**

В конец `tests/test_analysis_pipeline.py` добавить:

```python
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
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_fnr_stage_names_are_the_five_stages -v`
Expected: FAIL (`AttributeError: module 'activities' has no attribute 'FNR_STAGE_NAMES'`)

- [ ] **Step 3: Реализовать**

В `worker/activities.py` сразу ПОСЛЕ функции `_fnr_stages` (не меняя её 3-элементную сигнатуру — её ещё зовёт монолит) добавить:

```python
FNR_STAGE_NAMES = ("task", "concept", "debate", "sysreq", "validate")

# Входной артефакт каждой стадии — что уже должно лежать в рабочем каталоге,
# чтобы стадия имела смысл (используется guard'ом _require_workspace).
_FNR_STAGE_REQUIRES = {
    "task": None,
    "concept": f"{FNR_DIR}/task.md",
    "debate": f"{FNR_DIR}/concept.md",
    "sysreq": f"{FNR_DIR}/concept.md",
    "validate": f"{FNR_DIR}/system_requirements.md",
}


def _fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]:
    """(промпт, ожидаемый артефакт, требуемый вход) для стадии по имени."""
    for n, prompt, expected in _fnr_stages(description):
        if n == name:
            return prompt, expected, _FNR_STAGE_REQUIRES[name]
    raise ValueError(f"неизвестная стадия FNR: {name}")
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py -k "fnr_stage" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(analyze): stage metadata — FNR_STAGE_NAMES + per-stage input map"
```

---

### Task 2: Хелперы рабочего каталога

**Files:**
- Modify: `worker/activities.py` (рядом с хелперами FNR)
- Test: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: `_clone_repo`, `_run_repomix` (существуют).
- Produces: `_workspace_dir(analyze) -> Path`; `_clone_dir(analyze) -> str`; `_build_workspace(analyze) -> str`; `_require_workspace(analyze, requires: str | None) -> str`.

- [ ] **Step 1: Написать падающий тест**

В конец `tests/test_analysis_pipeline.py` добавить фикстуру и тесты:

```python
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
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_workspace_dir_is_deterministic_under_root -v`
Expected: FAIL (`AttributeError: ... '_workspace_dir'`)

- [ ] **Step 3: Реализовать**

В `worker/activities.py` после Task-1 блока добавить:

```python
def _workspace_dir(analyze: AnalyzeInput) -> Path:
    """Детерминированный рабочий каталог прогона (переживает activity в пределах
    жизни контейнера). База — ANALYSIS_WORKSPACE_ROOT или системный temp."""
    root = os.environ.get("ANALYSIS_WORKSPACE_ROOT") or tempfile.gettempdir()
    slug = f"analysis-{analyze.repo.replace('/', '__')}-{analyze.issue_number}"
    return Path(root) / slug


def _clone_dir(analyze: AnalyzeInput) -> str:
    return str(_workspace_dir(analyze) / "repo")


def _build_workspace(analyze: AnalyzeInput) -> str:
    """Свежий каталог: снести остаток прежнего прогона, clone, repomix."""
    shutil.rmtree(_workspace_dir(analyze), ignore_errors=True)
    clone_dir = _clone_dir(analyze)
    _clone_repo(analyze.repo, clone_dir)
    _run_repomix(clone_dir)
    return clone_dir


def _require_workspace(analyze: AnalyzeInput, requires: str | None) -> str:
    """Guard стадии: каталог+repomix на месте? требуемый вход на месте? Иначе
    fail-fast (без пере-клона — он дал бы свежий репозиторий без артефактов)."""
    clone_dir = _clone_dir(analyze)
    if not (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists():
        raise RuntimeError("рабочий каталог потерян (рестарт воркера?) — повтори /analyze")
    if requires and not (Path(clone_dir) / requires).exists():
        raise RuntimeError(
            f"нет входа {requires} (стадия-предшественник не отработала?) — повтори /analyze"
        )
    return clone_dir
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py -k "workspace" -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(analyze): deterministic workspace helpers + fail-fast guard"
```

---

### Task 3: Activity `prepare_workspace`

**Files:**
- Modify: `worker/activities.py`
- Test: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: `_build_workspace`, `_run_with_heartbeat`.
- Produces: `async prepare_workspace(analyze: AnalyzeInput) -> None` (activity).

- [ ] **Step 1: Написать падающий тест**

```python
def test_prepare_workspace_builds_clone_and_repomix(stage_env):
    asyncio.run(activities.prepare_workspace(_analyze()))
    clone_dir = activities._clone_dir(_analyze())
    assert Path(clone_dir).exists()
    assert (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists()
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_prepare_workspace_builds_clone_and_repomix -v`
Expected: FAIL (`AttributeError: ... 'prepare_workspace'`)

- [ ] **Step 3: Реализовать**

В `worker/activities.py` (после хелперов, рядом с будущими activity) добавить:

```python
@activity.defn
async def prepare_workspace(analyze: AnalyzeInput) -> None:
    """Стадия 0 пайплайна /analyze: свежий clone + repomix в детерминированный
    каталог. Идемпотентна (сносит остаток и строит заново)."""
    await _run_with_heartbeat(_build_workspace, analyze, label="preparing")
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_prepare_workspace_builds_clone_and_repomix -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(analyze): prepare_workspace activity (clone+repomix once)"
```

---

### Task 4: Activity `run_fnr_stage`

**Files:**
- Modify: `worker/activities.py`
- Test: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: `_fnr_stage`, `_require_workspace`, `_run_claude`, `_run_with_heartbeat`.
- Produces: `async run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict` → `{"stage": str, "artifact": str | None, "bytes": int}`.

- [ ] **Step 1: Написать падающие тесты**

```python
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
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_stage_reports_stage_artifact_and_size -v`
Expected: FAIL (`AttributeError: ... 'run_fnr_stage'`)

- [ ] **Step 3: Реализовать**

В `worker/activities.py` после `prepare_workspace` добавить:

```python
@activity.defn
async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:
    """Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,
    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный
    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам."""
    description = f"{analyze.title}\n\n{analyze.body}"
    prompt, expected, requires = _fnr_stage(stage_name, description)
    clone_dir = _require_workspace(analyze, requires)
    await _run_with_heartbeat(_run_claude, prompt, clone_dir, label=stage_name)
    artifact: str | None = None
    size = 0
    if expected:
        path = Path(clone_dir) / expected
        if not path.exists():
            raise RuntimeError(f"стадия {stage_name}: артефакт {expected} не создан")
        artifact = expected
        size = path.stat().st_size
    return {"stage": stage_name, "artifact": artifact, "bytes": size}
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py -k "stage" -v`
Expected: 7 passed (все `test_stage_*`)

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(analyze): run_fnr_stage activity — one claude -p per stage"
```

---

### Task 5: Activity `publish_analysis` и `cleanup_workspace`

**Files:**
- Modify: `worker/activities.py`
- Test: `tests/test_analysis_pipeline.py`

**Interfaces:**
- Consumes: `_require_workspace`, `_collect_fnr_artifacts`, `_build_summary`, `github_client.push_artifacts_to_branch`, `github_client.post_comment`, `_workspace_dir`.
- Produces: `async publish_analysis(analyze: AnalyzeInput) -> str` (возвращает ветку `research/issue-N`); `async cleanup_workspace(analyze: AnalyzeInput) -> None`.

- [ ] **Step 1: Написать падающие тесты**

```python
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
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py::test_publish_pushes_branch_and_comments -v`
Expected: FAIL (`AttributeError: ... 'publish_analysis'`)

- [ ] **Step 3: Реализовать**

В `worker/activities.py` после `run_fnr_stage` добавить:

```python
@activity.defn
async def publish_analysis(analyze: AnalyzeInput) -> str:
    """Финал пайплайна: собрать артефакты, push ветки research/issue-N,
    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client."""
    clone_dir = _require_workspace(analyze, None)
    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)
    if not files:
        raise RuntimeError("пайплайн не произвёл ни одного артефакта")
    branch = f"research/issue-{analyze.issue_number}"
    await asyncio.to_thread(
        github_client.push_artifacts_to_branch,
        analyze.repo, branch, files,
        f"docs(sa): анализ issue #{analyze.issue_number} через SA-helper",
    )
    await asyncio.to_thread(
        github_client.post_comment,
        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),
    )
    return branch


@activity.defn
async def cleanup_workspace(analyze: AnalyzeInput) -> None:
    """Best-effort снос рабочего каталога прогона."""
    await asyncio.to_thread(shutil.rmtree, str(_workspace_dir(analyze)), ignore_errors=True)
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv/bin/python -m pytest tests/test_analysis_pipeline.py -k "publish or cleanup" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py tests/test_analysis_pipeline.py
git commit -m "feat(analyze): publish_analysis + cleanup_workspace activities"
```

---

### Task 6: Оркестрация в `IssueAnalysis.run` + регистрация activity

**Files:**
- Modify: `worker/workflows.py:293-324` (тело `IssueAnalysis.run`)
- Modify: `worker/worker.py:44`
- Test: `tests/test_workflow_analysis.py`

**Interfaces:**
- Consumes: `activities.ack_command`, `activities.prepare_workspace`, `activities.run_fnr_stage`, `activities.publish_analysis`, `activities.cleanup_workspace`, `activities.publish_analysis_error`, `activities.FNR_STAGE_NAMES`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_workflow_analysis.py` добавить два теста (не трогая существующие пока — они звали stub `run_analysis_pipeline`, их заменим в Step 3):

```python
@pytest.mark.asyncio
async def test_orchestrates_all_stages_in_order():
    calls = []

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "research/issue-5"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert calls == ["ack", "prepare", "stage:task", "stage:concept", "stage:debate",
                     "stage:sysreq", "stage:validate", "publish", "cleanup"]


@pytest.mark.asyncio
async def test_stage_failure_publishes_error_and_cleans_up():
    calls = []
    reported = {}

    @activity.defn(name="ack_command")
    async def ack(analyze: AnalyzeInput) -> None:
        calls.append("ack")

    @activity.defn(name="prepare_workspace")
    async def prepare(analyze: AnalyzeInput) -> None:
        calls.append("prepare")

    @activity.defn(name="run_fnr_stage")
    async def stage(analyze: AnalyzeInput, stage_name: str) -> dict:
        calls.append(f"stage:{stage_name}")
        if stage_name == "sysreq":
            raise RuntimeError("boom-sysreq")
        return {"stage": stage_name, "artifact": None, "bytes": 0}

    @activity.defn(name="publish_analysis")
    async def publish(analyze: AnalyzeInput) -> str:
        calls.append("publish")
        return "b"

    @activity.defn(name="cleanup_workspace")
    async def cleanup(analyze: AnalyzeInput) -> None:
        calls.append("cleanup")

    @activity.defn(name="publish_analysis_error")
    async def publish_error(analyze: AnalyzeInput, reason: str) -> None:
        reported["reason"] = reason
        calls.append("error")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq, workflows=[IssueAnalysis],
                          activities=[ack, prepare, stage, publish, cleanup, publish_error]):
            await env.client.execute_workflow(
                IssueAnalysis.run, _analyze(), id=f"analysis-{uuid.uuid4()}", task_queue=tq)

    assert "stage:validate" not in calls          # остановились на sysreq
    assert "publish" not in calls
    assert "error" in calls and "boom-sysreq" in reported["reason"]
    assert calls[-1] == "cleanup"                  # cleanup всегда последним
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv/bin/python -m pytest tests/test_workflow_analysis.py::test_orchestrates_all_stages_in_order -v`
Expected: FAIL (воркфлоу ещё зовёт `run_analysis_pipeline`; активити `prepare_workspace` не зарегистрирована на тест-воркере → workflow висит/падает по таймауту)

- [ ] **Step 3: Реализовать — переписать тело воркфлоу**

В `worker/workflows.py` заменить тело `IssueAnalysis.run` (текущие строки 293-324, от `@workflow.run` до конца `run`) на:

```python
    @workflow.run
    async def run(self, analyze: AnalyzeInput) -> None:
        await workflow.execute_activity(
            activities.ack_command,
            analyze,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        try:
            await workflow.execute_activity(
                activities.prepare_workspace,
                analyze,
                start_to_close_timeout=timedelta(seconds=1000),  # clone 300 + repomix 600 + буфер
                heartbeat_timeout=timedelta(seconds=300),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            # Пер-стадийные activity: каждая — свой шаг Event History со своим
            # таймингом. Застрявшая стадия падает по СВОЕМУ start_to_close, а не
            # прячется под общим потолком, и называет себя в ошибке.
            for stage_name in activities.FNR_STAGE_NAMES:
                await workflow.execute_activity(
                    activities.run_fnr_stage,
                    args=[analyze, stage_name],
                    start_to_close_timeout=timedelta(seconds=1200),  # claude до 900 + буфер
                    heartbeat_timeout=timedelta(seconds=300),
                    # Прогон недетерминирован и мутирует файлы — авторетрай сжёг бы
                    # бюджет и мог бы задвоить артефакт. Повтор инициирует человек.
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            await workflow.execute_activity(
                activities.publish_analysis,
                analyze,
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as exc:
            # exc — ActivityError с общим текстом; настоящая причина в exc.cause
            # (например, «стадия concept: артефакт ... не создан»). Разворачиваем.
            reason = str(getattr(exc, "cause", None) or exc)
            await workflow.execute_activity(
                activities.publish_analysis_error,
                args=[analyze, reason[:500]],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        finally:
            # Каталог живёт вне Temporal — снимаем его на обоих путях. Best-effort:
            # провал уборки не должен затирать реальный исход.
            await workflow.execute_activity(
                activities.cleanup_workspace,
                analyze,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
```

- [ ] **Step 4: Зарегистрировать новые activity в воркере**

В `worker/worker.py` строку 44 (`            activities.run_analysis_pipeline,`) **оставить на месте** (монолит ещё определён — удалим в Task 7) и сразу ПОД ней добавить четыре строки. Итог — блок из пяти строк:

```python
            activities.run_analysis_pipeline,
            activities.prepare_workspace,
            activities.run_fnr_stage,
            activities.publish_analysis,
            activities.cleanup_workspace,
```

(Дубля имён нет: все пять — разные activity. `run_analysis_pipeline` пока просто зарегистрирована, но воркфлоу её больше не зовёт.)

- [ ] **Step 5: Прогнать — зелено (новые тесты оркестрации)**

Run: `.venv/bin/python -m pytest tests/test_workflow_analysis.py -k "orchestrates or cleans_up" -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add worker/workflows.py worker/worker.py tests/test_workflow_analysis.py
git commit -m "feat(analyze): orchestrate FNR stages as per-stage Temporal activities"
```

---

### Task 7: Удалить монолит и мёртвые тесты, финальная зелень

> ⚠️ **ОТМЕНЕНО (2026-07-24).** Обнаружено при исполнении: `run_analysis_pipeline` НЕ мёртв — второй живой вызыватель `IssueLifecycle.run` (ветка `research-me`, worker/workflows.py:247). Удаление сломало бы research-me. Монолит и его 8 тестов остаются. Миграция research-me на пер-стадийные activity отложена отдельной задачей.

**Files:**
- Modify: `worker/activities.py` (удалить `run_analysis_pipeline`, строки ~458-510)
- Modify: `worker/worker.py` (удалить строку `activities.run_analysis_pipeline,`)
- Modify: `tests/test_analysis_pipeline.py` (удалить мёртвый монолитный тест-код)
- Modify: `tests/test_workflow_analysis.py` (удалить два старых теста, звавших stub `run_analysis_pipeline`)

**Interfaces:** —

- [ ] **Step 1: Удалить монолит-activity**

В `worker/activities.py` удалить функцию `async def run_analysis_pipeline(...)` целиком (от `@activity.defn` перед ней до `finally: shutil.rmtree(workdir, ignore_errors=True)` включительно). НЕ трогать переиспользуемые хелперы (`_clone_repo`, `_run_repomix`, `_run_claude`, `_claude_anthropic_creds`, `_collect_fnr_artifacts`, `_build_summary`, `_run_with_heartbeat`, `_fnr_stages`).

- [ ] **Step 2: Снять регистрацию монолита**

В `worker/worker.py` удалить строку `            activities.run_analysis_pipeline,`.

- [ ] **Step 3: Удалить мёртвые тесты монолита**

В `tests/test_analysis_pipeline.py` удалить старую фикстуру `wired` и все тесты, обращающиеся к `activities.run_analysis_pipeline`:
Удалить ровно эти восемь (все зовут монолит): `test_runs_all_five_fnr_stages_in_order`, `test_heartbeats_at_least_once_per_stage`, `test_heartbeat_fires_during_a_long_stage`, `test_pushes_artifacts_to_research_branch`, `test_summary_comment_links_artifacts`, `test_missing_expected_artifact_fails_the_stage`, `test_workspace_is_removed_even_on_failure`, `test_blocking_stages_run_off_the_event_loop_thread`. Больше из этого файла не удалять ничего.

Сохранить: `test_clone_failure_never_leaks_token_in_calledprocesserror`, `test_clone_timeout_never_leaks_token` (целят `_clone_repo`), `test_claude_creds_derived_from_zai`, `test_explicit_anthropic_overrides_zai`, `test_claude_creds_empty_when_nothing_set` (целят `_claude_anthropic_creds`), и все новые `test_fnr_stage_*` / `test_workspace_*` / `test_stage_*` / `test_prepare_*` / `test_publish_*` / `test_cleanup_*` из Task 1-5.

В `tests/test_workflow_analysis.py` удалить `test_happy_path_acks_then_runs_pipeline` и `test_pipeline_failure_publishes_error_and_does_not_retry` (звали stub `run_analysis_pipeline`; их роль закрыли тесты Task 6).

- [ ] **Step 4: Убедиться, что мёртвых ссылок не осталось**

Run: `grep -rn "run_analysis_pipeline" worker/ tests/`
Expected: пусто (0 совпадений)

- [ ] **Step 5: Прогнать весь сьют**

Run: `.venv/bin/python -m pytest -q`
Expected: all passed (число тестов = прежние минус удалённые монолитные плюс новые)

- [ ] **Step 6: Commit**

```bash
git add worker/activities.py worker/worker.py tests/test_analysis_pipeline.py tests/test_workflow_analysis.py
git commit -m "refactor(analyze): drop monolithic run_analysis_pipeline (replaced by per-stage activities)"
```

---

## Проверка охвата спеки

- Пер-стадийные шаги Event History → Task 6 (воркфлоу зовёт `run_fnr_stage` в цикле).
- Статус+тайминг+артефакт на стадию → Task 4 (`run_fnr_stage` возвращает `{stage, artifact, bytes}`; тайминг/статус — сам Temporal).
- repomix один раз → Task 3 (`prepare_workspace`) + Task 2 (`_build_workspace`).
- Общий детерминированный каталог → Task 2.
- Fail-fast guard (без пере-клона) → Task 2 (`_require_workspace`) + Task 4 (стадии) + Task 5 (publish).
- Свой таймаут на стадию → Task 6 (`start_to_close=1200` на стадию).
- Ошибка разворачивает `.cause` + `publish_analysis_error` → Task 6.
- `cleanup` на обоих путях → Task 6 (`finally`).
- DRY_RUN не тронут → Task 5 (мутации через `github_client`).
- Токен-leak регрессия сохранена → Task 7 Step 3 (тесты `_clone_repo` не удаляются).
- Монолит удалён → Task 7.

## Заметки по реализации

- Импорты в тестах: `asyncio`, `subprocess`, `threading`, `time`, `Path`, `pytest`, `activities`, `AnalyzeInput` — уже есть в шапке `tests/test_analysis_pipeline.py` (проверить `threading`/`time` — есть). В `tests/test_workflow_analysis.py` уже импортированы `uuid`, `pytest`, `activity`, `WorkflowEnvironment`, `Worker`, `AnalyzeInput`, `IssueAnalysis`.
- `_analyze()` в `tests/test_analysis_pipeline.py` даёт `AnalyzeInput(repo="o/r", issue_number=5, ...)` → slug `analysis-o__r-5`.
- Каждая activity — `async def`, чтобы heartbeat реально уходил на том же event loop (как в текущем монолите).
