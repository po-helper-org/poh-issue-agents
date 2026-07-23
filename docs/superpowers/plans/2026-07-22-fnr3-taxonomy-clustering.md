# FNR-3 Taxonomy-First Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mechanism-similarity clustering (`cluster_profiles`, degenerates to singletons) with taxonomy-first delivery-zone clustering: derive a small zone vocabulary, classify each issue into it, slice big zones into iteration increments.

**Architecture:** In `ConsolidationWorkflow` the reduce stage becomes: `derive_taxonomy` (1 call → delivery zones) → fan-out `assign_zone` (per-issue classification) → group by primary zone → `slice_zone` (big zone → MVP/MVP+1 increments) → fan-out `synthesize_unifying_issue` (per increment) → `write_consolidation_pr`. Fetch returns bodyless refs (bodies fetched inside profile extraction) to keep workflow history light.

**Tech Stack:** Python 3.12, temporalio, instructor + openai (z.ai GLM, JSON mode), pydantic (extraction schemas), dataclasses (workflow types), pytest.

## Global Constraints

- Workflow types are `@dataclass` in `shared/workflow_types.py`; LLM extraction schemas are `pydantic.BaseModel` in `worker/consolidation_activities.py`.
- LLM calls: `llm.extract(system_prompt, user_message, response_model, model=llm.MODEL_CLASSIFY)`. System prompts in `prompts/system_*.md`, loaded via `_load_prompt` (`Path("/app/prompts")/name`).
- Activities are **sync `def`** decorated `@activity.defn` (run in the worker ThreadPoolExecutor; never `async def`).
- **Never mutate GitHub Issues.** Only write = branch + PR via `github_client.create_pr_with_files`, guarded by `github_client._dry_run()`.
- **#111 rule** enforced in `slice_zone`: same functional area + divergent target (launch vs migrate) → different increments.
- **Taxonomy determinism (M1):** `derive_taxonomy` accepts an optional `prior` taxonomy; zone `name` is the canonical id (not a member-number slug). Call with `temperature ≤ 0.2` if the client exposes it; otherwise low temperature is a prompt+model concern (leave a NFR note, do not block).
- **Replay (M2):** `fetch_open_issues` returns `IssueInput` WITHOUT body; `extract_solution_profile` fetches its own body via `github_client.get_issue_body`.
- **assign `other` (M3):** `assign_zone` may return `primary_zone == "other"`.
- Test interpreter (repo-root venv): `/Users/aleksishmanov/projects/poh-org/poh-issue-agents/.venv/bin/python -m pytest -q` from the repo root. Tests monkeypatch `ca.llm.extract` and `ca._load_prompt`.
- Reuse the existing test patterns in `tests/test_consolidation_*.py`.

---

### Task 1: Delivery-zone data types

**Files:**
- Modify: `shared/workflow_types.py` (append)
- Test: `tests/test_fnr3_types.py`

**Interfaces:**
- Produces: dataclasses `DeliveryZone{name,boundary,surface}`, `Taxonomy{zones:list[DeliveryZone]}`, `ZoneAssignment{issue_number,primary_zone,secondary_zones}`, `Increment{name,rationale,issue_numbers}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fnr3_types.py
from shared.workflow_types import DeliveryZone, Taxonomy, ZoneAssignment, Increment


def test_fnr3_types_construct():
    z = DeliveryZone(name="jira-engine", boundary="одна итерация JIRA", surface="JIRA-Connector")
    t = Taxonomy(zones=[z])
    a = ZoneAssignment(issue_number=57, primary_zone="jira-engine")
    inc = Increment(name="MVP", rationale="фундамент", issue_numbers=[57, 60])
    assert t.zones[0].name == "jira-engine"
    assert a.secondary_zones == []
    assert inc.issue_numbers == [57, 60]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'DeliveryZone'`

- [ ] **Step 3: Write minimal implementation** (append to `shared/workflow_types.py`)

```python
@dataclass
class DeliveryZone:
    name: str
    boundary: str
    surface: str


@dataclass
class Taxonomy:
    zones: list[DeliveryZone]


@dataclass
class ZoneAssignment:
    issue_number: int
    primary_zone: str
    secondary_zones: list[str] = field(default_factory=list)


@dataclass
class Increment:
    name: str
    rationale: str
    issue_numbers: list[int]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/workflow_types.py tests/test_fnr3_types.py
git commit -m "feat(fnr3): delivery-zone data types"
```

---

### Task 2: `derive_taxonomy` activity

**Files:**
- Modify: `worker/consolidation_activities.py`
- Create: `prompts/system_derive_taxonomy.md`
- Test: `tests/test_fnr3_derive.py`

**Interfaces:**
- Consumes: `SolutionProfile`, `DeliveryZone`, `Taxonomy` (Task 1); `llm.extract`, `_load_prompt`.
- Produces: `def derive_taxonomy(profiles: list[SolutionProfile], prior: Taxonomy | None) -> Taxonomy` (`@activity.defn`); pydantic `ZoneOut`, `TaxonomyExtraction`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fnr3_derive.py
import consolidation_activities as ca
from consolidation_activities import TaxonomyExtraction, ZoneOut
from shared.workflow_types import SolutionProfile


def _p(n, mech):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target="tg", domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


def test_derive_taxonomy_maps_zones(monkeypatch):
    ext = TaxonomyExtraction(zones=[
        ZoneOut(name="jira-engine", boundary="одна итерация JIRA", surface="JIRA-Connector")])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: ext)
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    tax = ca.derive_taxonomy([_p(57, "jira idx"), _p(60, "jira meta")], None)
    assert [z.name for z in tax.zones] == ["jira-engine"]


def test_derive_taxonomy_includes_prior(monkeypatch):
    captured = {}
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda system, user, model, **k: captured.update(user=user) or
                        TaxonomyExtraction(zones=[ZoneOut(name="x", boundary="b", surface="s")]))
    from shared.workflow_types import Taxonomy, DeliveryZone
    ca.derive_taxonomy([_p(1, "m")], Taxonomy(zones=[DeliveryZone("prev-zone", "b", "s")]))
    assert "prev-zone" in captured["user"]  # prior zones fed into the prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_derive.py -v`
Expected: FAIL with `ImportError: cannot import name 'TaxonomyExtraction'`

- [ ] **Step 3: Write the prompt** `prompts/system_derive_taxonomy.md`

```markdown
Ты группируешь бэклог под ПОСТАВКУ. Ось — «реализуется и релизится вместе одной
технической итерацией», НЕ «похожая тема». Выведи 8-12 ЗОН ПОСТАВКИ, где одна
итерация закрывает максимум схожих Issue. Коарс, не дроби на микро-темы.

Каждая зона: name (короткий kebab, канонический id зоны), boundary (что закрывает
одна итерация), surface (движок/модуль).

Если во входе есть блок «ПРОШЛЫЕ ЗОНЫ» — ПЕРЕИСПОЛЬЗУЙ их имена без изменения и
добавь только НОВЫЕ зоны для непокрытых Issue (стабильность таксономии).
```

- [ ] **Step 4: Write minimal implementation** (append to `worker/consolidation_activities.py`)

```python
from shared.workflow_types import DeliveryZone, Taxonomy, ZoneAssignment, Increment


class ZoneOut(BaseModel):
    name: str
    boundary: str
    surface: str


class TaxonomyExtraction(BaseModel):
    zones: list[ZoneOut]


@activity.defn
def derive_taxonomy(profiles: list[SolutionProfile], prior: Taxonomy | None) -> Taxonomy:
    listing = "\n".join(
        f"#{p.issue_number} mechanism={p.proposed_mechanism!r} target={p.target!r} domain={p.domain}"
        for p in profiles if p.problem_essence != "[EXTRACTION_FAILED]")
    if prior and prior.zones:
        listing = ("ПРОШЛЫЕ ЗОНЫ:\n" +
                   "\n".join(f"- {z.name}: {z.boundary}" for z in prior.zones) +
                   "\n\nISSUE:\n" + listing)
    ext = llm.extract(_load_prompt("system_derive_taxonomy.md"), listing,
                      TaxonomyExtraction, model=llm.MODEL_CLASSIFY)
    return Taxonomy(zones=[DeliveryZone(name=z.name, boundary=z.boundary, surface=z.surface)
                           for z in ext.zones])
```

Add `DeliveryZone, Taxonomy, ZoneAssignment, Increment` to the existing `from shared.workflow_types import (...)` block instead of a second import line if one already imports from that module.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_derive.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_derive_taxonomy.md tests/test_fnr3_derive.py
git commit -m "feat(fnr3): derive_taxonomy activity (versioned taxonomy)"
```

---

### Task 3: `assign_zone` activity (per-issue)

**Files:**
- Modify: `worker/consolidation_activities.py`
- Create: `prompts/system_assign_zone.md`
- Test: `tests/test_fnr3_assign.py`

**Interfaces:**
- Consumes: `SolutionProfile`, `Taxonomy`, `ZoneAssignment` (Tasks 1-2).
- Produces: `def assign_zone(profile: SolutionProfile, taxonomy: Taxonomy) -> ZoneAssignment` (`@activity.defn`); pydantic `AssignExtraction`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fnr3_assign.py
import consolidation_activities as ca
from consolidation_activities import AssignExtraction
from shared.workflow_types import SolutionProfile, Taxonomy, DeliveryZone


def _p(n, mech):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target="tg", domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


TAX = Taxonomy(zones=[DeliveryZone("jira-engine", "b", "s"),
                      DeliveryZone("memory-core", "b", "s")])


def test_assign_maps_primary(monkeypatch):
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: AssignExtraction(primary_zone="jira-engine",
                                                         secondary_zones=["memory-core"]))
    a = ca.assign_zone(_p(57, "jira idx"), TAX)
    assert a.issue_number == 57
    assert a.primary_zone == "jira-engine"
    assert a.secondary_zones == ["memory-core"]


def test_assign_other_when_unknown_zone(monkeypatch):
    # model returns a zone not in the taxonomy -> coerce to "other"
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: AssignExtraction(primary_zone="hallucinated", secondary_zones=[]))
    a = ca.assign_zone(_p(99, "weird"), TAX)
    assert a.primary_zone == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_assign.py -v`
Expected: FAIL with `ImportError: cannot import name 'AssignExtraction'`

- [ ] **Step 3: Write the prompt** `prompts/system_assign_zone.md`

```markdown
Дан список ЗОН ПОСТАВКИ и ОДИН Issue (профиль). Отнеси Issue в primary_zone —
строго ОДНО имя из списка зон, в чьей итерации он поставится. secondary_zones —
имена зон, которые Issue частично обслуживает (сквозной). Используй ТОЛЬКО имена
из списка. Если ни одна зона не подходит — primary_zone = "other".
```

- [ ] **Step 4: Write minimal implementation** (append)

```python
class AssignExtraction(BaseModel):
    primary_zone: str
    secondary_zones: list[str] = Field(default_factory=list)


@activity.defn
def assign_zone(profile: SolutionProfile, taxonomy: Taxonomy) -> ZoneAssignment:
    names = {z.name for z in taxonomy.zones}
    zones_block = "ЗОНЫ:\n" + "\n".join(f"- {z.name}: {z.boundary}" for z in taxonomy.zones)
    user = (f"{zones_block}\n\nISSUE #{profile.issue_number}: {profile.title}\n"
            f"mechanism={profile.proposed_mechanism!r} target={profile.target!r} "
            f"domain={profile.domain}")
    r = llm.extract(_load_prompt("system_assign_zone.md"), user, AssignExtraction,
                    model=llm.MODEL_CLASSIFY)
    primary = r.primary_zone if r.primary_zone in names else "other"
    secondary = [s for s in r.secondary_zones if s in names]
    return ZoneAssignment(issue_number=profile.issue_number,
                          primary_zone=primary, secondary_zones=secondary)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_assign.py -v`
Expected: PASS (both)

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_assign_zone.md tests/test_fnr3_assign.py
git commit -m "feat(fnr3): assign_zone activity (per-issue, other-fallback)"
```

---

### Task 4: `slice_zone` activity (#111 guard)

**Files:**
- Modify: `worker/consolidation_activities.py`
- Create: `prompts/system_slice_zone.md`
- Test: `tests/test_fnr3_slice.py`

**Interfaces:**
- Consumes: `DeliveryZone`, `SolutionProfile`, `Increment` (Tasks 1).
- Produces: `def slice_zone(zone: DeliveryZone, members: list[int], profiles: list[SolutionProfile]) -> list[Increment]` (`@activity.defn`); pydantic `IncrementOut`, `SliceExtraction`. Constant `SLICE_MIN = 6` (zones with ≤ this many members are not sliced — returned as one increment).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fnr3_slice.py
import consolidation_activities as ca
from consolidation_activities import SliceExtraction, IncrementOut
from shared.workflow_types import DeliveryZone, SolutionProfile


def _p(n):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism="m", target="tg", domain="d",
                           anchors=["a"], advisor_label="x")


ZONE = DeliveryZone("jira-engine", "b", "s")


def test_slice_big_zone(monkeypatch):
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: SliceExtraction(increments=[
        IncrementOut(name="MVP", rationale="фундамент", issue_numbers=[1, 2, 3]),
        IncrementOut(name="MVP+1", rationale="надстройка", issue_numbers=[4, 5, 6, 7])]))
    members = list(range(1, 8))
    incs = ca.slice_zone(ZONE, members, [_p(n) for n in members])
    assert [i.name for i in incs] == ["MVP", "MVP+1"]
    assert sorted(n for i in incs for n in i.issue_numbers) == members


def test_slice_small_zone_single_increment(monkeypatch):
    # <= SLICE_MIN members -> one increment, no LLM call
    called = {"n": 0}
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: called.__setitem__("n", 1))
    incs = ca.slice_zone(ZONE, [1, 2], [_p(1), _p(2)])
    assert len(incs) == 1
    assert incs[0].issue_numbers == [1, 2]
    assert called["n"] == 0  # no LLM for a small zone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_slice.py -v`
Expected: FAIL with `ImportError: cannot import name 'SliceExtraction'`

- [ ] **Step 3: Write the prompt** `prompts/system_slice_zone.md`

```markdown
Дана ЗОНА ПОСТАВКИ и её Issue. Нарежь на итерации-инкременты (MVP, MVP+1, ...) так,
чтобы КАЖДЫЙ инкремент был одной поставляемой итерацией (~3-6 Issue). Упорядочи по
ЗАВИСИМОСТЯМ: фундамент первым, надстройка сверху. Используй только номера из зоны.

КРИТИЧНО (#111): если внутри зоны у Issue одинаковый функционал, но РАЗНАЯ цель
(запуск vs перевод на архитектуру) — разведи их по РАЗНЫМ инкрементам, не смешивай.
```

- [ ] **Step 4: Write minimal implementation** (append)

```python
SLICE_MIN = 6


class IncrementOut(BaseModel):
    name: str
    rationale: str
    issue_numbers: list[int]


class SliceExtraction(BaseModel):
    increments: list[IncrementOut]


@activity.defn
def slice_zone(zone: DeliveryZone, members: list[int],
               profiles: list[SolutionProfile]) -> list[Increment]:
    if len(members) <= SLICE_MIN:
        return [Increment(name=zone.name, rationale="зона в пределах одной итерации",
                          issue_numbers=sorted(members))]
    by_num = {p.issue_number: p for p in profiles}
    listing = "\n".join(f"#{n} {by_num[n].title}" for n in members if n in by_num)
    r = llm.extract(_load_prompt("system_slice_zone.md"),
                    f"Зона {zone.name} ({zone.boundary}):\n{listing}",
                    SliceExtraction, model=llm.MODEL_CLASSIFY)
    return [Increment(name=f"{zone.name}:{i.name}", rationale=i.rationale,
                      issue_numbers=sorted(i.issue_numbers)) for i in r.increments]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_slice.py -v`
Expected: PASS (both)

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_activities.py prompts/system_slice_zone.md tests/test_fnr3_slice.py
git commit -m "feat(fnr3): slice_zone activity with #111 guard"
```

---

### Task 5: Replay fix — bodyless fetch + profile self-fetch

**Files:**
- Modify: `worker/github_client.py` (add `get_issue_body`)
- Modify: `worker/consolidation_activities.py` (`fetch_open_issues`, `extract_solution_profile`)
- Test: `tests/test_fnr3_replay.py`

**Interfaces:**
- Consumes: `IssueInput`, `github_client`.
- Produces: `github_client.get_issue_body(repo, issue_number) -> str`; `fetch_open_issues` returns `IssueInput` with `body=""`; `extract_solution_profile` fetches the body via `github_client.get_issue_body` when `issue.body` is empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fnr3_replay.py
import consolidation_activities as ca
from consolidation_activities import ProfileExtraction
from shared.workflow_types import IssueInput


def test_fetch_returns_bodyless(monkeypatch):
    monkeypatch.setattr(ca.github_client, "list_open_issues",
                        lambda repo, limit: [{"number": 5, "title": "t", "body": "BIG BODY",
                                              "labels": []}])
    from shared.workflow_types import ConsolidationInput
    refs = ca.fetch_open_issues(ConsolidationInput(repo="o/r"))
    assert refs[0].issue_number == 5
    assert refs[0].body == ""  # body stripped from history payload


def test_extract_self_fetches_body(monkeypatch):
    seen = {}
    monkeypatch.setattr(ca.github_client, "get_issue_body",
                        lambda repo, n: "FETCHED BODY")
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda system, user, model, **k: seen.update(user=user) or
                        ProfileExtraction(problem_essence="e", proposed_mechanism="m",
                                          target="t", domain="d", anchors=["a"]))
    issue = IssueInput(repo="o/r", issue_number=5, title="t", body="",
                       author_login="", author_type="User")
    ca.extract_solution_profile(issue)
    assert "FETCHED BODY" in seen["user"]  # body pulled inside the activity
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_replay.py -v`
Expected: FAIL (`get_issue_body` missing / body not stripped)

- [ ] **Step 3: Add `get_issue_body`** (append to `worker/github_client.py`)

```python
def get_issue_body(repo: str, issue_number: int) -> str:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("body") or ""
```

- [ ] **Step 4: Strip body in `fetch_open_issues`** — change the `IssueInput(...)` construction so `body=""` (drop `body=it.get("body") or ""`, set `body=""`).

- [ ] **Step 5: Self-fetch body in `extract_solution_profile`** — at the top of the function, if `issue.body` is empty pull it:

```python
    body = issue.body or github_client.get_issue_body(issue.repo, issue.issue_number)
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{body}"
```
(replace the existing `user_message` line that used `issue.body`).

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_replay.py -v`
Expected: PASS (both)

- [ ] **Step 7: Commit**

```bash
git add worker/github_client.py worker/consolidation_activities.py tests/test_fnr3_replay.py
git commit -m "fix(fnr3): bodyless fetch + profile self-fetch (replay-scale)"
```

---

### Task 6: Rewrite `ConsolidationWorkflow` (taxonomy pipeline)

**Files:**
- Modify: `worker/consolidation_workflow.py`
- Modify: `worker/worker.py` (register new activities)
- Test: `tests/test_fnr3_workflow.py`

**Interfaces:**
- Consumes: `fetch_open_issues`, `extract_solution_profile`, `derive_taxonomy`, `assign_zone`, `slice_zone`, `synthesize_unifying_issue`, `write_consolidation_pr` (Task 7 adapts the last two).
- Produces: `ConsolidationWorkflow.run(cfg) -> str | None` orchestrating the taxonomy pipeline.

- [ ] **Step 1: Write the failing test** (stub activities by name, time-skipping env)

```python
# tests/test_fnr3_workflow.py
import uuid
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from consolidation_workflow import ConsolidationWorkflow
from shared.workflow_types import (ConsolidationInput, IssueInput, SolutionProfile,
                                    Taxonomy, DeliveryZone, ZoneAssignment, Increment,
                                    UnifyingIssueDraft)


@activity.defn(name="fetch_open_issues")
async def f(cfg): return [IssueInput("o/r", 1, "t", "", "", "User")]
@activity.defn(name="extract_solution_profile")
async def p(issue): return SolutionProfile(1, "t", "e", "m", "tg", "d", ["a"], "")
@activity.defn(name="derive_taxonomy")
async def d(profiles, prior): return Taxonomy([DeliveryZone("z", "b", "s")])
@activity.defn(name="assign_zone")
async def a(profile, taxonomy): return ZoneAssignment(1, "z", [])
@activity.defn(name="slice_zone")
async def s(zone, members, profiles): return [Increment("z", "r", [1])]
@activity.defn(name="synthesize_unifying_issue")
async def sy(increment, profiles): return UnifyingIssueDraft("z", "T", "# b", [1])
@activity.defn(name="write_consolidation_pr")
async def w(taxonomy, increments, drafts, repo): return "http://pr/1"


@pytest.mark.timeout(30)
async def test_fnr3_workflow_end_to_end():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq", workflows=[ConsolidationWorkflow],
                          activities=[f, p, d, a, s, sy, w]):
            url = await env.client.execute_workflow(
                ConsolidationWorkflow.run, ConsolidationInput(repo="o/r"),
                id=f"c-{uuid.uuid4()}", task_queue="tq")
    assert url == "http://pr/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fnr3_workflow.py -v`
Expected: FAIL (workflow still calls `cluster_profiles`/old activities)

- [ ] **Step 3: Rewrite** `worker/consolidation_workflow.py`

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
            workflow.execute_activity(ca.extract_solution_profile, r,
                                      start_to_close_timeout=timedelta(seconds=240),
                                      retry_policy=retry) for r in refs])

        taxonomy = await workflow.execute_activity(
            ca.derive_taxonomy, args=[profiles, None],
            start_to_close_timeout=timedelta(seconds=300), retry_policy=retry)

        assignments = await asyncio.gather(*[
            workflow.execute_activity(ca.assign_zone, args=[p, taxonomy],
                                      start_to_close_timeout=timedelta(seconds=180),
                                      retry_policy=retry) for p in profiles])

        by_zone: dict[str, list[int]] = {}
        for a in assignments:
            by_zone.setdefault(a.primary_zone, []).append(a.issue_number)

        increments = []
        for zone in taxonomy.zones:
            members = by_zone.get(zone.name, [])
            if not members:
                continue
            zi = await workflow.execute_activity(
                ca.slice_zone, args=[zone, members, profiles],
                start_to_close_timeout=timedelta(seconds=360),
                retry_policy=RetryPolicy(maximum_attempts=2))
            increments.extend(zi)

        drafts = await asyncio.gather(*[
            workflow.execute_activity(ca.synthesize_unifying_issue, args=[inc, profiles],
                                      start_to_close_timeout=timedelta(seconds=360),
                                      retry_policy=RetryPolicy(maximum_attempts=2))
            for inc in increments])

        return await workflow.execute_activity(
            ca.write_consolidation_pr, args=[taxonomy, increments, drafts, cfg.repo],
            start_to_close_timeout=timedelta(seconds=120), retry_policy=retry)
```

- [ ] **Step 4: Register in `worker/worker.py`** — extend `activities=[...]` with `ca.derive_taxonomy, ca.assign_zone, ca.slice_zone` (keep all existing; the removed `ca.cluster_profiles` entry is deleted in Task 7). `workflows=[IssueLifecycle, ConsolidationWorkflow]` unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_fnr3_workflow.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/consolidation_workflow.py worker/worker.py tests/test_fnr3_workflow.py
git commit -m "feat(fnr3): taxonomy-pipeline ConsolidationWorkflow"
```

---

### Task 7: Adapt synth/PR to increments; remove old clustering

**Files:**
- Modify: `worker/consolidation_activities.py`
- Modify: `worker/worker.py` (drop `ca.cluster_profiles` registration)
- Delete: `prompts/system_cluster.md`, `prompts/system_cluster_merge.md`
- Modify: `tests/test_consolidation_synth.py`, `tests/test_consolidation_write.py`
- Delete: `tests/test_consolidation_cluster.py`

**Interfaces:**
- Produces: `synthesize_unifying_issue(increment: Increment, profiles) -> UnifyingIssueDraft`; `write_consolidation_pr(taxonomy: Taxonomy, increments: list[Increment], drafts: list[UnifyingIssueDraft], repo) -> str | None`; `_render_overview(taxonomy: Taxonomy, increments: list[Increment]) -> str`.

- [ ] **Step 1: Update the synth test** — in `tests/test_consolidation_synth.py`, replace the `Cluster` construction with `Increment("jira:MVP", "r", [1, 2])` and call `ca.synthesize_unifying_issue(inc, profiles)`; assert `d.source_issue_numbers == [1, 2]` and `d.cluster_id == "jira:MVP"`.

- [ ] **Step 2: Update the write test** — in `tests/test_consolidation_write.py`, build `Taxonomy([DeliveryZone("jira", "b", "s")])` + `[Increment("jira:MVP", "r", [1])]` + drafts, call `ca.write_consolidation_pr(tax, incs, drafts, repo="o/r")`, assert `docs/consolidation/overview.md` and `docs/consolidation/unifying/jira:MVP.md`... (note: sanitize `:` in filenames — see Step 4).

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_consolidation_synth.py tests/test_consolidation_write.py -v`
Expected: FAIL (signatures changed)

- [ ] **Step 4: Rewrite** `synthesize_unifying_issue`, `_render_overview`, `write_consolidation_pr` in `worker/consolidation_activities.py`:

```python
@activity.defn
def synthesize_unifying_issue(increment: Increment,
                              profiles: list[SolutionProfile]) -> UnifyingIssueDraft:
    by_num = {p.issue_number: p for p in profiles}
    members_block = "\n".join(
        f"#{n} {by_num[n].title if n in by_num else ''} "
        f"anchors={by_num[n].anchors if n in by_num else []}"
        for n in increment.issue_numbers)
    user_message = (f"инкремент={increment.name!r} обоснование={increment.rationale!r}\n"
                    f"members:\n{members_block}")
    r = llm.extract(_load_prompt("system_unifying_issue.md"), user_message,
                    SynthOut, model=llm.MODEL_CLASSIFY)
    return UnifyingIssueDraft(cluster_id=increment.name, title=r.title,
                              body_markdown=r.body_markdown,
                              source_issue_numbers=list(increment.issue_numbers))


def _slug_file(name: str) -> str:
    return name.replace(":", "-").replace("/", "-")


def _render_overview(taxonomy: Taxonomy, increments: list[Increment]) -> str:
    lines = ["# Консолидация бэклога\n", "## Зоны поставки\n"]
    for z in taxonomy.zones:
        lines.append(f"### {z.name} — {z.boundary} (surface: {z.surface})")
    lines.append("\n## Инкременты\n")
    for inc in increments:
        nums = ", ".join(f"#{n}" for n in inc.issue_numbers)
        lines.append(f"- **{inc.name}** ({inc.rationale}): {nums}")
    return "\n".join(lines)


@activity.defn
def write_consolidation_pr(taxonomy: Taxonomy, increments: list[Increment],
                           drafts: list[UnifyingIssueDraft], repo: str) -> str | None:
    from datetime import date
    files = {"docs/consolidation/overview.md": _render_overview(taxonomy, increments)}
    for d in drafts:
        files[f"docs/consolidation/unifying/{_slug_file(d.cluster_id)}.md"] = d.body_markdown
    branch = f"consolidation/{date.today().isoformat()}"
    body = (f"Автоконсолидация: {len(taxonomy.zones)} зон, {len(increments)} инкрементов, "
            f"{len(drafts)} объединяющих Issue. Предлагает, не мутирует Issue.")
    return github_client.create_pr_with_files(
        repo, branch, "main", files, "Консолидация бэклога", body)
```

Update the write test's expected path to `docs/consolidation/unifying/jira-MVP.md` (colon sanitized).

- [ ] **Step 5: Remove old clustering** — delete from `worker/consolidation_activities.py`: `cluster_profiles`, `_cluster_call`, `_merge_local`, `_slug`, and schemas `MemberOut`, `ClusterOut`, `ClusterExtraction`, `MergeExtraction`, `MergeAssignment`, `CLUSTER_BATCH_SIZE`. Delete `tests/test_consolidation_cluster.py`. Delete `prompts/system_cluster.md`, `prompts/system_cluster_merge.md`. In `worker/worker.py`, drop the `ca.cluster_profiles` entry from `activities=[...]`.

- [ ] **Step 6: Run the FULL suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all). Confirm no import errors from removed symbols:
Run: `grep -rn "cluster_profiles\|_merge_local\|ClusterExtraction" worker/ tests/`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(fnr3): increments in synth/PR, remove mechanism clustering"
```

---

## Rollout (after implementation)

1. Rebuild worker from the repo root that holds `.env`:
   `docker compose -p po-helper-issues up --build -d worker`.
2. Dry run: `DRY_RUN=1`, `make consolidate` (or `scripts/consolidate.py --repo po-helper-org/poh-helper`) — inspect worker logs / Temporal for zones, PR logged not opened.
3. Go live: flip `DRY_RUN=`, recreate worker, run again — expect ~8 delivery zones + increments + a PR, no `WorkflowTaskTimedOut`.

## Notes for the implementer

- Keep all activities **sync `def`** — an `async def` re-introduces the event-loop-blocking bug (worker runs them in a ThreadPoolExecutor).
- `derive_taxonomy` is called with `prior=None` from the workflow for now; persisting the taxonomy artifact across runs (M1 versioning) is a follow-up — the `prior` param is already in the signature.
- `continue-as-new` (M2) is NOT implemented here; the bodyless-fetch (Task 5) is the concrete replay fix. If a full-backlog run still hits `WorkflowTaskTimedOut`, add `continue-as-new` after `derive_taxonomy` as a follow-up.
- Do not add any GitHub-Issue mutation — the PR is the only write, DRY_RUN-guarded.
