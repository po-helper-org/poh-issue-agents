# Issue Consolidation Stage (FNR-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Temporal `ConsolidationWorkflow` that clusters the open Issue backlog by shared solution mechanism and emits a PR of unifying-Issue drafts (one per cluster), each requirement anchored to its source Issue.

**Architecture:** Fan-out `extract_solution_profile` per Issue → single `cluster_profiles` reduce (with #111 target-divergence guard) → fan-out `synthesize_unifying_issue` per cluster → `write_consolidation_pr`. All content work lives in sync activities (run in the worker's ThreadPoolExecutor); the workflow is deterministic. Reuses `llm.extract`, `github_client`, and the `DRY_RUN` guard. `IssueLifecycle` and its activities are untouched.

**Tech Stack:** Python 3.12, temporalio, instructor + openai (z.ai GLM, JSON mode), pydantic (extraction schemas), dataclasses (workflow types), pytest.

## Global Constraints

- Workflow types are `@dataclass` in `shared/workflow_types.py`; LLM extraction schemas are `pydantic.BaseModel` in the activity module. (Matches existing `activities.py`.)
- LLM calls go through `llm.extract(system_prompt, user_message, response_model, model=llm.MODEL_CLASSIFY)`. System prompts live in `prompts/system_*.md`, loaded via the existing `_load_prompt` pattern (`Path("/app/prompts")/name`).
- Activities are **sync `def`** decorated with `@activity.defn` (they run in the worker's `ThreadPoolExecutor`; do not use `async def`).
- **Never mutate GitHub Issues** (no comment/label/close/create). The only GitHub write is a branch + PR, and it is guarded by `github_client._dry_run()`.
- **#111 rule (mandatory):** same solution mechanism + divergent target ⇒ separate clusters + a cross-link, never one merged cluster.
- **Zero-hallucination:** every profile field and every synthesized requirement carries a verbatim `anchor` quote from the source Issue; unknowns are the literal string `[УТОЧНИТЬ]`, never invented.
- Tests use `pytest` with `monkeypatch` for `llm`/`github_client`, and `temporalio.testing.WorkflowEnvironment.start_time_skipping()` for the workflow. `tests/conftest.py` already puts `worker/` and repo root on `sys.path`.
- Run the full suite with `.venv/bin/python -m pytest -q` from the repo root.

---

### Task 1: Consolidation data types

**Files:**
- Modify: `shared/workflow_types.py` (append)
- Test: `tests/test_consolidation_types.py`

**Interfaces:**
- Produces: dataclasses `SolutionProfile`, `ClusterMember`, `Cluster`, `ClusterSet`, `UnifyingIssueDraft`, `ConsolidationInput` (field names/types below — later tasks depend on these exactly).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consolidation_types.py
from shared.workflow_types import (
    SolutionProfile, ClusterMember, Cluster, ClusterSet,
    UnifyingIssueDraft, ConsolidationInput,
)


def test_types_construct_and_default():
    p = SolutionProfile(issue_number=59, title="FTS search layer",
                        problem_essence="grep is token-heavy",
                        proposed_mechanism="FTS + dependency graph engine",
                        target="cut context-assembly token cost",
                        domain="memory-core", anchors=["grep/echo"],
                        advisor_label="advisor:feature-request")
    m = ClusterMember(issue_number=59, role="primary",
                      contributed_requirement="FTS over docs")
    c = Cluster(cluster_id="memory-core-search", mechanism="FTS engine",
                target="cut token cost", members=[m], cross_links=[])
    cs = ClusterSet(clusters=[c], orphans=[])
    d = UnifyingIssueDraft(cluster_id="memory-core-search", title="Search engine",
                           body_markdown="# ...", source_issue_numbers=[59])
    cfg = ConsolidationInput(repo="kibarik/po-helper")
    assert cfg.exclude_labels == ["advisor:consultation", "advisor:existing-functionality"]
    assert cs.clusters[0].members[0].role == "primary"
    assert d.source_issue_numbers == [59]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidation_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'SolutionProfile'`

- [ ] **Step 3: Write minimal implementation** (append to `shared/workflow_types.py`)

```python
from dataclasses import dataclass, field


@dataclass
class SolutionProfile:
    issue_number: int
    title: str
    problem_essence: str
    proposed_mechanism: str
    target: str
    domain: str
    anchors: list[str]
    advisor_label: str


@dataclass
class ClusterMember:
    issue_number: int
    role: str  # "primary" | "secondary"
    contributed_requirement: str


@dataclass
class Cluster:
    cluster_id: str
    mechanism: str
    target: str
    members: list[ClusterMember]
    cross_links: list[str]


@dataclass
class ClusterSet:
    clusters: list[Cluster]
    orphans: list[int]


@dataclass
class UnifyingIssueDraft:
    cluster_id: str
    title: str
    body_markdown: str
    source_issue_numbers: list[int]


@dataclass
class ConsolidationInput:
    repo: str
    exclude_labels: list[str] = field(
        default_factory=lambda: ["advisor:consultation", "advisor:existing-functionality"])
    limit: int = 300
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidation_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/workflow_types.py tests/test_consolidation_types.py
git commit -m "feat(consolidation): data types for profiles/clusters/drafts"
```

---

### Task 2: `extract_solution_profile` activity

**Files:**
- Create: `worker/consolidation_activities.py`
- Create: `prompts/system_solution_profile.md`
- Test: `tests/test_consolidation_profile.py`

**Interfaces:**
- Consumes: `SolutionProfile` (Task 1); `llm.extract`.
- Produces: `def extract_solution_profile(issue: IssueInput) -> SolutionProfile` (`@activity.defn`); pydantic `ProfileExtraction`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consolidation_profile.py
import consolidation_activities as ca
from consolidation_activities import ProfileExtraction
from shared.workflow_types import IssueInput


def test_extract_profile_maps_fields(monkeypatch):
    fake = ProfileExtraction(problem_essence="grep costs tokens",
                             proposed_mechanism="FTS engine", target="cut cost",
                             domain="memory-core", anchors=["grep/echo"])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: fake)
    issue = IssueInput(repo="o/r", issue_number=59, title="Search layer",
                       body="replace grep with FTS", author_login="u",
                       author_type="User")
    p = ca.extract_solution_profile(issue)
    assert p.issue_number == 59
    assert p.proposed_mechanism == "FTS engine"
    assert p.target == "cut cost"
    assert p.anchors == ["grep/echo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidation_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'consolidation_activities'`

- [ ] **Step 3: Write the prompt** `prompts/system_solution_profile.md`

```markdown
Ты извлекаешь «профиль решения» из GitHub Issue для последующей кластеризации.

Верни строго поля схемы. Правила:
- `proposed_mechanism` — КАК Issue предлагает решать (движок/подход). Это ключ группировки. Отдели механизм от цели.
- `target` — ЦЕЛЬ/исход, ради которого. Это то, что различает функциональные дубли (запуск vs перевод на архитектуру).
- `domain` — одна область: jira | memory-core | llm-routing | ui | process | other.
- `anchors` — дословные цитаты из тела Issue, подтверждающие поля. Без источника поле не заполняй.
- Неизвестное — строкой `[УТОЧНИТЬ]`, не выдумывай.
```

- [ ] **Step 4: Write minimal implementation** `worker/consolidation_activities.py`

```python
"""Consolidation activities: profile extraction, clustering, synthesis, PR."""
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import github_client
import llm
from shared.workflow_types import (
    Cluster, ClusterMember, ClusterSet, ConsolidationInput,
    IssueInput, SolutionProfile, UnifyingIssueDraft,
)

PROMPTS_DIR = Path("/app/prompts")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


class ProfileExtraction(BaseModel):
    problem_essence: str
    proposed_mechanism: str
    target: str
    domain: str
    anchors: list[str] = Field(default_factory=list)


@activity.defn
def extract_solution_profile(issue: IssueInput) -> SolutionProfile:
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}"
    r = llm.extract(_load_prompt("system_solution_profile.md"), user_message,
                    ProfileExtraction, model=llm.MODEL_CLASSIFY)
    return SolutionProfile(
        issue_number=issue.issue_number, title=issue.title,
        problem_essence=r.problem_essence, proposed_mechanism=r.proposed_mechanism,
        target=r.target, domain=r.domain, anchors=r.anchors,
        advisor_label=getattr(issue, "advisor_label", ""),
    )
```

Note: `IssueInput` has no `advisor_label`; `getattr(..., "")` keeps it optional. The workflow (Task 7) passes the Layer A label in `issue.body` context is not needed — leave `advisor_label` empty for MVP.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidation_profile.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_solution_profile.md tests/test_consolidation_profile.py
git commit -m "feat(consolidation): extract_solution_profile activity"
```

---

### Task 3: `cluster_profiles` activity with #111 guard

**Files:**
- Modify: `worker/consolidation_activities.py`
- Create: `prompts/system_cluster.md`
- Test: `tests/test_consolidation_cluster.py`

**Interfaces:**
- Consumes: `SolutionProfile`, `ClusterSet`, `Cluster`, `ClusterMember` (Task 1); `llm.extract`.
- Produces: `def cluster_profiles(profiles: list[SolutionProfile]) -> ClusterSet` (`@activity.defn`); pydantic `ClusterExtraction`, `ClusterOut`, `MemberOut`; helper `_slug(numbers: list[int]) -> str`.

- [ ] **Step 1: Write the failing test** (the #111 guard is the key case)

```python
# tests/test_consolidation_cluster.py
import consolidation_activities as ca
from consolidation_activities import ClusterExtraction, ClusterOut, MemberOut
from shared.workflow_types import SolutionProfile


def _p(n, mech, target):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target=target, domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


def test_cluster_splits_same_mechanism_divergent_target(monkeypatch):
    # Model returns two clusters: same mechanism, different target (the #111 case)
    ext = ClusterExtraction(
        clusters=[
            ClusterOut(mechanism="graph memory core", target="launch new store",
                       members=[MemberOut(issue_number=1, role="primary",
                                          contributed_requirement="store nodes")],
                       cross_links=[]),
            ClusterOut(mechanism="graph memory core", target="migrate legacy store",
                       members=[MemberOut(issue_number=2, role="primary",
                                          contributed_requirement="migrate data")],
                       cross_links=[]),
        ], orphans=[])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: ext)
    profiles = [_p(1, "graph memory core", "launch new store"),
                _p(2, "graph memory core", "migrate legacy store")]
    cs = ca.cluster_profiles(profiles)
    assert len(cs.clusters) == 2  # NOT merged despite identical mechanism
    ids = {c.cluster_id for c in cs.clusters}
    assert len(ids) == 2  # deterministic distinct slugs


def test_cluster_slug_is_deterministic():
    assert ca._slug([3, 1, 2]) == ca._slug([1, 2, 3])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidation_cluster.py -v`
Expected: FAIL with `ImportError: cannot import name 'ClusterExtraction'`

- [ ] **Step 3: Write the prompt** `prompts/system_cluster.md`

```markdown
Тебе дан список профилей решений (issue_number, mechanism, target, domain).
Сгруппируй их в кластеры, каждый из которых закрывается ОДНИМ техническим решением.

Правила:
1. Ключ группировки — общий `mechanism` (механизм решения), НЕ поверхностная тема.
2. КРИТИЧНО: внутри одного механизма раздели по `target`. Если цели расходятся
   (запуск vs перевод на архитектуру, функция vs цель) — это РАЗНЫЕ кластеры,
   свяжи их через `cross_links`, НЕ объединяй (функциональный дубль ≠ целевой).
3. `role`: primary — механизм это ядро запроса Issue; secondary — механизм лишь
   частично обслуживает Issue (даёт множественное членство/cross_links).
4. `contributed_requirement` — что ИМЕННО этот Issue требует от решения.
5. Issue, не подходящий никуда — в `orphans`, не впихивай силой.
```

- [ ] **Step 4: Write minimal implementation** (append to `consolidation_activities.py`)

```python
class MemberOut(BaseModel):
    issue_number: int
    role: str
    contributed_requirement: str


class ClusterOut(BaseModel):
    mechanism: str
    target: str
    members: list[MemberOut]
    cross_links: list[str] = Field(default_factory=list)


class ClusterExtraction(BaseModel):
    clusters: list[ClusterOut]
    orphans: list[int] = Field(default_factory=list)


def _slug(numbers: list[int]) -> str:
    return "cluster-" + "-".join(str(n) for n in sorted(numbers))


@activity.defn
def cluster_profiles(profiles: list[SolutionProfile]) -> ClusterSet:
    listing = "\n".join(
        f"#{p.issue_number} mechanism={p.proposed_mechanism!r} "
        f"target={p.target!r} domain={p.domain}"
        for p in profiles if p.problem_essence != "[EXTRACTION_FAILED]")
    ext = llm.extract(_load_prompt("system_cluster.md"), listing,
                      ClusterExtraction, model=llm.MODEL_CLASSIFY)
    clusters = []
    for co in ext.clusters:
        members = [ClusterMember(issue_number=m.issue_number, role=m.role,
                                 contributed_requirement=m.contributed_requirement)
                   for m in co.members]
        clusters.append(Cluster(
            cluster_id=_slug([m.issue_number for m in co.members]),
            mechanism=co.mechanism, target=co.target,
            members=members, cross_links=co.cross_links))
    return ClusterSet(clusters=clusters, orphans=ext.orphans)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidation_cluster.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_cluster.md tests/test_consolidation_cluster.py
git commit -m "feat(consolidation): cluster_profiles with #111 target-divergence guard"
```

---

### Task 4: `synthesize_unifying_issue` activity

**Files:**
- Modify: `worker/consolidation_activities.py`
- Create: `prompts/system_unifying_issue.md`
- Test: `tests/test_consolidation_synth.py`

**Interfaces:**
- Consumes: `Cluster`, `SolutionProfile`, `UnifyingIssueDraft` (Task 1); `llm.extract`.
- Produces: `def synthesize_unifying_issue(cluster: Cluster, profiles: list[SolutionProfile]) -> UnifyingIssueDraft` (`@activity.defn`); pydantic `SynthOut`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consolidation_synth.py
import consolidation_activities as ca
from consolidation_activities import SynthOut
from shared.workflow_types import Cluster, ClusterMember, SolutionProfile


def test_synth_builds_draft_with_sources(monkeypatch):
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: SynthOut(title="Unify search",
                                                 body_markdown="# Search\n- req from #1"))
    cluster = Cluster(cluster_id="cluster-1-2", mechanism="FTS", target="cut cost",
                      members=[ClusterMember(1, "primary", "FTS over docs"),
                               ClusterMember(2, "secondary", "index JIRA")],
                      cross_links=[])
    profiles = [SolutionProfile(1, "t1", "p", "FTS", "cut cost", "memory-core",
                                ["a"], "advisor:feature-request")]
    d = ca.synthesize_unifying_issue(cluster, profiles)
    assert d.cluster_id == "cluster-1-2"
    assert d.source_issue_numbers == [1, 2]
    assert d.title == "Unify search"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidation_synth.py -v`
Expected: FAIL with `ImportError: cannot import name 'SynthOut'`

- [ ] **Step 3: Write the prompt** `prompts/system_unifying_issue.md`

```markdown
Тебе дан кластер Issue, которые закрывает ОДНО решение (mechanism), и профили
участников. Сформируй объединяющий Issue.

Верни `title` и `body_markdown`. В body:
- синтез проблемы и механизма решения;
- раздел «Требования (агрегированы)» — по одному пункту на участника, каждый
  подписан источником `— from #N` и его вкладом (contributed_requirement);
- каждый пункт опирается на профиль участника (anchors). Ничего не выдумывай;
  неизвестное — `[УТОЧНИТЬ]`.
```

- [ ] **Step 4: Write minimal implementation** (append)

```python
class SynthOut(BaseModel):
    title: str
    body_markdown: str


@activity.defn
def synthesize_unifying_issue(cluster: Cluster,
                              profiles: list[SolutionProfile]) -> UnifyingIssueDraft:
    by_num = {p.issue_number: p for p in profiles}
    members_block = "\n".join(
        f"#{m.issue_number} [{m.role}] wants={m.contributed_requirement!r} "
        f"anchors={by_num[m.issue_number].anchors if m.issue_number in by_num else []}"
        for m in cluster.members)
    user_message = (f"mechanism={cluster.mechanism!r} target={cluster.target!r}\n"
                    f"members:\n{members_block}")
    r = llm.extract(_load_prompt("system_unifying_issue.md"), user_message,
                    SynthOut, model=llm.MODEL_CLASSIFY)
    return UnifyingIssueDraft(
        cluster_id=cluster.cluster_id, title=r.title, body_markdown=r.body_markdown,
        source_issue_numbers=[m.issue_number for m in cluster.members])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidation_synth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_unifying_issue.md tests/test_consolidation_synth.py
git commit -m "feat(consolidation): synthesize_unifying_issue activity"
```

---

### Task 5: `github_client` PR helpers (branch + files + PR), DRY_RUN-guarded

**Files:**
- Modify: `worker/github_client.py` (append)
- Test: `tests/test_github_client_pr.py`

**Interfaces:**
- Consumes: existing `_auth_headers`, `_dry_run`.
- Produces: `def create_pr_with_files(repo: str, branch: str, base: str, files: dict[str, str], title: str, body: str) -> str | None`. Returns PR URL, or `None` under DRY_RUN. Creates the branch off `base`, PUTs each file, opens the PR — all via `requests` to the GitHub REST API.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_github_client_pr.py
import github_client


def test_create_pr_dry_run_makes_no_calls(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    called = {"n": 0}
    monkeypatch.setattr(github_client.requests, "post",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "put",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    url = github_client.create_pr_with_files(
        "o/r", "consolidation/2026-07-14", "main",
        {"docs/consolidation/overview.md": "# x"}, "Consolidation", "body")
    assert url is None
    assert called["n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_github_client_pr.py -v`
Expected: FAIL with `AttributeError: module 'github_client' has no attribute 'create_pr_with_files'`

- [ ] **Step 3: Write minimal implementation** (append to `github_client.py`)

```python
import base64


def create_pr_with_files(repo: str, branch: str, base: str,
                         files: dict, title: str, body: str):
    if _dry_run():
        _log.info("[DRY_RUN] PR %s <- %s: %d files, title=%s",
                  repo, branch, len(files), title)
        return None
    h = _auth_headers()
    api = f"https://api.github.com/repos/{repo}"
    base_sha = requests.get(f"{api}/git/refs/heads/{base}", headers=h,
                            timeout=30).json()["object"]["sha"]
    requests.post(f"{api}/git/refs", headers=h,
                  json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                  timeout=30).raise_for_status()
    for path, content in files.items():
        requests.put(f"{api}/contents/{path}", headers=h, json={
            "message": f"consolidation: {path}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }, timeout=30).raise_for_status()
    resp = requests.post(f"{api}/pulls", headers=h,
                         json={"title": title, "head": branch, "base": base,
                               "body": body}, timeout=30)
    resp.raise_for_status()
    return resp.json()["html_url"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_github_client_pr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/github_client.py tests/test_github_client_pr.py
git commit -m "feat(consolidation): github_client.create_pr_with_files (DRY_RUN-guarded)"
```

---

### Task 6: `fetch_open_issues` + `write_consolidation_pr` activities

**Files:**
- Modify: `worker/consolidation_activities.py`
- Modify: `worker/github_client.py` (add `list_open_issues`)
- Test: `tests/test_consolidation_write.py`, `tests/test_github_client_list.py`

**Interfaces:**
- Consumes: `ConsolidationInput`, `ClusterSet`, `UnifyingIssueDraft`, `IssueInput` (Task 1); `github_client`.
- Produces:
  - `github_client.list_open_issues(repo: str, limit: int) -> list[dict]` (keys: `number`, `title`, `body`, `labels` list of names).
  - `def fetch_open_issues(cfg: ConsolidationInput) -> list[IssueInput]` (`@activity.defn`) — excludes issues carrying any `cfg.exclude_labels`.
  - `def write_consolidation_pr(clusterset: ClusterSet, drafts: list[UnifyingIssueDraft]) -> str | None` (`@activity.defn`) — composes files, calls `github_client.create_pr_with_files`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_github_client_list.py
import json
import github_client


def test_list_open_issues_parses_labels(monkeypatch):
    class R:
        returncode = 0
        stdout = json.dumps([{"number": 5, "title": "t", "body": "b",
                              "labels": [{"name": "advisor:consultation"}]}])
    monkeypatch.setattr(github_client.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(github_client, "_auth_headers",
                        lambda: {"Authorization": "Bearer x"})
    out = github_client.list_open_issues("o/r", 50)
    assert out[0]["number"] == 5
    assert out[0]["labels"] == ["advisor:consultation"]
```

```python
# tests/test_consolidation_write.py
import consolidation_activities as ca
from shared.workflow_types import ClusterSet, Cluster, ClusterMember, UnifyingIssueDraft


def test_write_pr_composes_overview_and_files(monkeypatch):
    captured = {}
    monkeypatch.setattr(ca.github_client, "create_pr_with_files",
                        lambda repo, branch, base, files, title, body: captured.update(
                            files=files, title=title) or "http://pr/1")
    cs = ClusterSet(clusters=[Cluster("cluster-1", "FTS", "cut cost",
                                      [ClusterMember(1, "primary", "x")], [])],
                    orphans=[9])
    drafts = [UnifyingIssueDraft("cluster-1", "Unify", "# body", [1])]
    url = ca.write_consolidation_pr(cs, drafts, repo="o/r")
    assert url == "http://pr/1"
    assert "docs/consolidation/overview.md" in captured["files"]
    assert "docs/consolidation/unifying/cluster-1.md" in captured["files"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_github_client_list.py tests/test_consolidation_write.py -v`
Expected: FAIL (`list_open_issues` / `write_consolidation_pr` missing)

- [ ] **Step 3: Implement `list_open_issues`** (append to `github_client.py`)

```python
def list_open_issues(repo: str, limit: int = 300) -> list:
    import json
    env = {**os.environ, "GH_TOKEN": _auth_headers()["Authorization"].split(" ")[1]}
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--limit", str(limit), "--json", "number,title,body,labels"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    out = []
    for it in json.loads(result.stdout or "[]"):
        it["labels"] = [l["name"] for l in it.get("labels", [])]
        out.append(it)
    return out
```

- [ ] **Step 4: Implement the two activities** (append to `consolidation_activities.py`)

```python
@activity.defn
def fetch_open_issues(cfg: ConsolidationInput) -> list:
    issues = github_client.list_open_issues(cfg.repo, cfg.limit)
    refs = []
    for it in issues:
        if any(lbl in cfg.exclude_labels for lbl in it.get("labels", [])):
            continue
        refs.append(IssueInput(repo=cfg.repo, issue_number=it["number"],
                               title=it["title"], body=it.get("body") or "",
                               author_login="", author_type="User"))
    return refs


def _render_overview(cs: ClusterSet) -> str:
    lines = ["# Консолидация бэклога\n", "## Кластеры\n"]
    for c in cs.clusters:
        lines.append(f"### {c.cluster_id} — {c.mechanism} (target: {c.target})")
        for m in c.members:
            lines.append(f"- #{m.issue_number} [{m.role}] — {m.contributed_requirement}")
        if c.cross_links:
            lines.append(f"- cross-links: {', '.join(c.cross_links)}")
        lines.append("")
    lines.append(f"## Orphans\n{', '.join('#'+str(n) for n in cs.orphans) or '—'}")
    return "\n".join(lines)


@activity.defn
def write_consolidation_pr(clusterset: ClusterSet,
                           drafts: list, repo: str) -> str | None:
    from datetime import date
    files = {"docs/consolidation/overview.md": _render_overview(clusterset)}
    for d in drafts:
        files[f"docs/consolidation/unifying/{d.cluster_id}.md"] = d.body_markdown
    branch = f"consolidation/{date.today().isoformat()}"
    body = f"Автоконсолидация: {len(clusterset.clusters)} кластеров, " \
           f"{len(drafts)} объединяющих Issue. Предлагает, не мутирует Issue."
    return github_client.create_pr_with_files(
        repo, branch, "main", files, "Консолидация бэклога", body)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_github_client_list.py tests/test_consolidation_write.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py worker/github_client.py tests/test_github_client_list.py tests/test_consolidation_write.py
git commit -m "feat(consolidation): fetch_open_issues + write_consolidation_pr"
```

---

### Task 7: `ConsolidationWorkflow` orchestration + worker registration

**Files:**
- Create: `worker/consolidation_workflow.py`
- Modify: `worker/worker.py` (register workflow + activities)
- Test: `tests/test_consolidation_workflow.py`

**Interfaces:**
- Consumes: all activities (Tasks 2/3/4/6) by name; `ConsolidationInput`, `ClusterSet`.
- Produces: `ConsolidationWorkflow.run(cfg: ConsolidationInput) -> str | None`.

- [ ] **Step 1: Write the failing test** (stub activities by name, time-skipping env)

```python
# tests/test_consolidation_workflow.py
import uuid
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from consolidation_workflow import ConsolidationWorkflow
from shared.workflow_types import (ConsolidationInput, SolutionProfile,
                                    ClusterSet, Cluster, ClusterMember, UnifyingIssueDraft,
                                    IssueInput)


@activity.defn(name="fetch_open_issues")
async def stub_fetch(cfg):
    return [IssueInput("o/r", 1, "t", "b", "", "User")]

@activity.defn(name="extract_solution_profile")
async def stub_profile(issue):
    return SolutionProfile(1, "t", "p", "FTS", "cut", "d", ["a"], "")

@activity.defn(name="cluster_profiles")
async def stub_cluster(profiles):
    return ClusterSet([Cluster("cluster-1", "FTS", "cut",
                               [ClusterMember(1, "primary", "x")], [])], [])

@activity.defn(name="synthesize_unifying_issue")
async def stub_synth(cluster, profiles):
    return UnifyingIssueDraft("cluster-1", "Unify", "# body", [1])

@activity.defn(name="write_consolidation_pr")
async def stub_write(clusterset, drafts, repo):
    return "http://pr/1"


@pytest.mark.timeout(30)
async def test_workflow_runs_end_to_end():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[ConsolidationWorkflow],
                          activities=[stub_fetch, stub_profile, stub_cluster,
                                      stub_synth, stub_write]):
            url = await env.client.execute_workflow(
                ConsolidationWorkflow.run,
                ConsolidationInput(repo="o/r"),
                id=f"c-{uuid.uuid4()}", task_queue="tq")
    assert url == "http://pr/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidation_workflow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'consolidation_workflow'`

- [ ] **Step 3: Write the workflow** `worker/consolidation_workflow.py`

```python
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import consolidation_activities as ca
    from shared.workflow_types import ConsolidationInput


@workflow.defn
class ConsolidationWorkflow:
    @workflow.run
    async def run(self, cfg: ConsolidationInput):
        retry = RetryPolicy(maximum_attempts=3)
        refs = await workflow.execute_activity(
            ca.fetch_open_issues, cfg,
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)

        profiles = await asyncio.gather(*[
            workflow.execute_activity(
                ca.extract_solution_profile, r,
                start_to_close_timeout=timedelta(seconds=180), retry_policy=retry)
            for r in refs])

        clusterset = await workflow.execute_activity(
            ca.cluster_profiles, profiles,
            start_to_close_timeout=timedelta(seconds=300), retry_policy=retry)

        drafts = await asyncio.gather(*[
            workflow.execute_activity(
                ca.synthesize_unifying_issue, args=[c, profiles],
                start_to_close_timeout=timedelta(seconds=240),
                retry_policy=RetryPolicy(maximum_attempts=2))
            for c in clusterset.clusters])

        return await workflow.execute_activity(
            ca.write_consolidation_pr, args=[clusterset, drafts, cfg.repo],
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidation_workflow.py -v`
Expected: PASS

- [ ] **Step 5: Register in `worker/worker.py`**

Add import and extend the lists (do NOT remove existing entries):

```python
from consolidation_workflow import ConsolidationWorkflow
import consolidation_activities as ca
# in Worker(...):
#   workflows=[IssueLifecycle, ConsolidationWorkflow],
#   activities=[... existing ...,
#       ca.fetch_open_issues, ca.extract_solution_profile, ca.cluster_profiles,
#       ca.synthesize_unifying_issue, ca.write_consolidation_pr],
```

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior + new)

- [ ] **Step 7: Commit**

```bash
git add worker/consolidation_workflow.py worker/worker.py tests/test_consolidation_workflow.py
git commit -m "feat(consolidation): ConsolidationWorkflow + worker registration"
```

---

### Task 8: `scripts/consolidate.py` launcher

**Files:**
- Create: `scripts/consolidate.py`
- Test: `tests/test_consolidate_launcher.py`

**Interfaces:**
- Consumes: `ConsolidationInput`; temporalio `Client`.
- Produces: `async def main()` that starts `ConsolidationWorkflow` on task queue `issue-lifecycle` and prints the returned PR URL.

- [ ] **Step 1: Write the failing test** (mirror `tests/test_backfill.py`)

```python
# tests/test_consolidate_launcher.py
import asyncio
import sys
from unittest.mock import AsyncMock, patch

import consolidate


def test_launcher_starts_workflow(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["consolidate", "--repo", "o/r"])
    mock_client = AsyncMock()
    mock_client.execute_workflow = AsyncMock(return_value="http://pr/1")
    with patch("consolidate.Client.connect", AsyncMock(return_value=mock_client)):
        asyncio.run(consolidate.main())
    mock_client.execute_workflow.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_consolidate_launcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'consolidate'`

- [ ] **Step 3: Write** `scripts/consolidate.py`

```python
"""Launch a single ConsolidationWorkflow over the open backlog."""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

from temporalio.client import Client

from shared.workflow_types import ConsolidationInput

TASK_QUEUE = "issue-lifecycle"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    args = parser.parse_args()
    if not args.repo:
        raise SystemExit("set --repo or GITHUB_REPOSITORY")
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))
    url = await client.execute_workflow(
        "ConsolidationWorkflow", ConsolidationInput(repo=args.repo),
        id=f"consolidation-{args.repo}-{uuid.uuid4().hex[:8]}", task_queue=TASK_QUEUE)
    print(f"consolidation PR: {url}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_consolidate_launcher.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add scripts/consolidate.py tests/test_consolidate_launcher.py
git commit -m "feat(consolidation): scripts/consolidate.py launcher"
```

---

### Task 9: Wire into onboarding + docs

**Files:**
- Modify: `Makefile` (add `consolidate` target)
- Modify: `README.md` (short "Consolidation (FNR-2)" note)

**Interfaces:** none (operator ergonomics only).

- [ ] **Step 1: Add Makefile target**

```makefile
consolidate:
	@test -n "$(REPO)" || { echo "no GITHUB_REPOSITORY in .env"; exit 1; }
	GITHUB_REPOSITORY=$(REPO) $(PY) scripts/consolidate.py
```

- [ ] **Step 2: Add a README subsection** under the Layer A quickstart

```markdown
## Consolidation (FNR-2)

`make consolidate` clusters the open backlog by shared solution mechanism and
opens a PR of unifying-Issue drafts (one per cluster). It proposes only — it
never comments on, labels, or closes Issues. Honors `DRY_RUN`.
```

- [ ] **Step 3: Run full suite (guard against accidental breakage)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add Makefile README.md
git commit -m "docs(consolidation): make consolidate target + README note"
```

---

## Rollout (after the plan is implemented)

1. Rebuild the worker so it registers `ConsolidationWorkflow` + the new activities:
   `docker compose up --build -d worker` (from the repo root that holds `.env`).
2. Dry run first: with `DRY_RUN=1`, `make consolidate` — the workflow runs, files
   are composed, `create_pr_with_files` logs `[DRY_RUN] PR ...` and opens nothing.
   Inspect the worker logs / Temporal UI to review clusters.
3. Go live: flip `DRY_RUN=` (empty), recreate the worker, `make consolidate` — a
   real `consolidation/<date>` branch + PR appears. Review and merge by hand.

## Notes for the implementer

- The z.ai backend rate-limits (HTTP 429); the worker caps at
  `max_concurrent_activities=3`, so the Phase-1/3 fan-outs drain in bounded
  batches automatically — no extra throttling code needed.
- Keep activities **sync `def`** — the worker runs them in a `ThreadPoolExecutor`;
  an `async def` here would re-introduce the event-loop-blocking bug fixed in
  commit `383b360`.
- Do not add auto-close / auto-create / auto-label anywhere — the PR is the only
  GitHub write, and it is DRY_RUN-guarded.
