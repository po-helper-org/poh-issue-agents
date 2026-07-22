# Issue Consolidation Stage (FNR-2) — Design

> **Date:** 2026-07-14
> **Branch:** claude/issue-helper-validation-71ddbb
> **Status:** Draft for review
> **Depends on:** Layer A triage (merged) — supplies `advisor:*` labels + priorities as input signal.

---

## 1. Problem

Layer A triages each Issue in isolation (classify → dedup pairwise → priority). It
does **not** group Issues that a **single technological solution** would close
together. The po-helper backlog (67 open) is a dense cluster of feature requests
where one engine (e.g. a graph memory core, a JIRA write-API layer, an LLM
tiering scheme) satisfies 5–15–50 Issues at once. The owner's goal:

> Find those clusters, collect the complaints, and form **one unifying Issue**
> taken into work. Each source Issue becomes a **supplier of requirements** that
> the unifying Issue's implementation must satisfy.

Layer A's `duplicate_check` is the wrong tool: it is pairwise, lexical
(`gh --search` on the title), and only fires on near-identical duplicates
(≥0.85). It cannot see "different surface, same solution mechanism," and Issue
**#111** explicitly warns that a **functional duplicate ≠ a target duplicate**
(same business function, different goal — e.g. "launch X" vs "migrate X to new
architecture" — must NOT be merged).

## 2. Goal & non-goals

**Goal:** an autonomous stage that reads the whole open backlog, clusters Issues
by *shared problem + shared solution mechanism*, and produces a **PR** containing
(a) a consolidation overview and (b) one **unifying-Issue draft per cluster** that
aggregates the requirements contributed by each member Issue, each anchored to its
source. A human reviews the PR; only on merge are real GitHub Issues created and
sources linked. The tool **never mutates GitHub Issues** itself.

**Non-goals:**
- No auto-close, no auto-creation of Issues, no auto-linking (all deferred to the
  human PR merge).
- Not a replacement for Layer A dedup — this is a separate, global stage.
- Does not run the heavy research/bug pipelines (FNR-1 scope).

## 3. Key decisions (locked in brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Output = a git branch + PR**, not GitHub-Issue mutations | Human approves before anything is created/closed; zero irreversible action. |
| D2 | **PR proposes, human approves** | Source Issues created/linked/closed only after a human merges the PR. |
| D3 | **Multi-membership with roles** (`primary` / `secondary`) | An Issue often supplies requirements to 2–3 solutions; a single-cluster model loses cross-cutting requirements. |
| D4 | **Temporal `ConsolidationWorkflow`** alongside `IssueLifecycle` | Durable fan-out/reduce; reuses the existing worker, `llm`, `github_client`. |
| D5 | **Approach A**: two-phase profile→cluster (not embeddings, not single-shot) | Cluster on *solution mechanism*, cheap reduce over compact profiles, provenance via anchors, #111 handled by an explicit `target` field. |
| D6 | **#111 target-divergence guard** in the cluster step | Same mechanism + divergent target ⇒ separate clusters, never merged. |

## 4. Architecture

One-shot `scripts/consolidate.py` starts `ConsolidationWorkflow(repo, filter)`.
The workflow is deterministic; all LLM/IO work is in activities (Temporal rule).

```
scripts/consolidate.py
  └─ start ConsolidationWorkflow(repo, filter=open, exclude=advisor:consultation|existing)
        │
   ── Phase 1: FAN-OUT (profile extraction) ─────────────────
   fetch_open_issues → [IssueRef...]
   for each: execute_activity(extract_solution_profile)   # parallel, retry 3
   → List[SolutionProfile]
        │
   ── Phase 2: REDUCE (clustering) ──────────────────────────
   cluster_profiles(profiles) → one activity, strong model, compact profiles
   → ClusterSet (clusters w/ roles, cross-links, orphans) + #111 target guard
        │
   ── Phase 3: FAN-OUT (synthesis) ──────────────────────────
   for each cluster: execute_activity(synthesize_unifying_issue)
   → List[UnifyingIssueDraft]   # aggregated requirements + per-source anchors
        │
   ── Phase 4: WRITE ────────────────────────────────────────
   write_consolidation_pr(clusterset, drafts)
   → git branch `consolidation/<date>` + PR (proposes; no Issue mutation)
```

**Reuse:** `llm.extract` (Instructor + z.ai), `github_client` (list/branch/PR via
gh + requests), the sync-activity + `ThreadPoolExecutor` worker pattern, and the
`MODEL_GATE` / `MODEL_CLASSIFY` split. New code is additive; `IssueLifecycle` and
its activities are untouched.

## 5. Data model (`shared/workflow_types.py`, additive)

```python
class SolutionProfile:
    issue_number: int
    title: str
    problem_essence: str        # the pain, 1-2 sentences, source-anchored
    proposed_mechanism: str     # HOW the issue proposes to solve it (the cluster key)
    target: str                 # the GOAL/outcome — the #111 discriminator
    domain: str                 # e.g. jira | memory-core | llm-routing | ui | process
    anchors: list[str]          # verbatim quotes from the issue body (provenance)
    advisor_label: str          # carried from Layer A (feature-request/consultation/...)

class ClusterMember:
    issue_number: int
    role: str                   # "primary" | "secondary"
    contributed_requirement: str  # what THIS issue demands of the solution

class Cluster:
    cluster_id: str             # slug, e.g. "memory-core-provenance"
    mechanism: str              # the shared solution mechanism (why they group)
    target: str                 # the shared goal (must be consistent — #111)
    members: list[ClusterMember]
    cross_links: list[str]      # ids of adjacent clusters ("also touches ...")

class ClusterSet:
    clusters: list[Cluster]
    orphans: list[int]          # issues that cluster with nothing (kept standalone)

class UnifyingIssueDraft:
    cluster_id: str
    title: str
    body_markdown: str          # problem synthesis + aggregated requirements w/ anchors
    source_issue_numbers: list[int]
```

## 6. Activities

### 6.1 `extract_solution_profile(issue) -> SolutionProfile`  (Phase 1)
Feeds `{title, body}` to `MODEL_CLASSIFY` via `llm.extract` with a strict schema.
Prompt (`prompts/system_solution_profile.md`) demands: name the *proposed
mechanism* separately from the *target*; every field carries a verbatim anchor;
mark unknowns `[УТОЧНИТЬ]` rather than inventing (zero-hallucination bar from the
BFT reference). Fan-out over all issues; per-issue retry.

### 6.2 `cluster_profiles(profiles) -> ClusterSet`  (Phase 2)
Single activity. Feeds the **compact profiles** (not full bodies) to a strong
model. Instructions:
1. Group by **shared `proposed_mechanism`** (the cluster key), not surface topic.
2. **#111 guard:** within a mechanism-group, split by `target`; profiles whose
   goals diverge (launch vs migrate, function vs objective) go to **separate
   clusters** and are recorded as `cross_links`, never merged.
3. Assign `role`: `primary` = the mechanism is this issue's core ask; `secondary`
   = the mechanism only partly serves it (feeds `cross_links` / multi-membership).
4. Issues that match nothing → `orphans` (kept standalone, not force-fit).
Deterministic tie-breaks (stable slug from sorted member numbers) so re-runs are
reproducible.

### 6.3 `synthesize_unifying_issue(cluster, profiles) -> UnifyingIssueDraft`  (Phase 3)
Per cluster. Produces the unifying-Issue markdown: problem synthesis, the solution
mechanism, and an **aggregated requirements list** where each requirement is
attributed to its source Issue (`— from #N`) with the member's
`contributed_requirement`. Fan-out over clusters; retry per cluster.

### 6.4 `write_consolidation_pr(clusterset, drafts) -> str`  (Phase 4)
Writes to a new branch `consolidation/<YYYY-MM-DD>`:
- `docs/consolidation/overview.md` — cluster map, membership table (roles),
  orphans, cross-links.
- `docs/consolidation/unifying/<cluster_id>.md` — one file per unifying-Issue
  draft.
Opens a PR via `gh pr create` (title, body = overview summary). Returns the PR
URL. **No GitHub-Issue mutation.** Guarded by the existing `DRY_RUN` flag: under
`DRY_RUN` it writes files + logs the intended PR but does not push/open it.

## 7. Workflow orchestration (`worker/consolidation_workflow.py`)

```python
@workflow.defn
class ConsolidationWorkflow:
    @workflow.run
    async def run(self, cfg: ConsolidationInput) -> str:
        refs = await execute_activity(fetch_open_issues, cfg, ...)
        profiles = await asyncio.gather(*[
            execute_activity(extract_solution_profile, r, retry=3, sts=180s)
            for r in refs])
        clusterset = await execute_activity(cluster_profiles, profiles,
                                            retry=3, sts=300s)
        drafts = await asyncio.gather(*[
            execute_activity(synthesize_unifying_issue, (c, profiles),
                             retry=2, sts=240s)
            for c in clusterset.clusters])
        return await execute_activity(write_consolidation_pr,
                                      (clusterset, drafts), retry=3, sts=120s)
```

Concurrency respects the worker's `max_concurrent_activities=3` (z.ai rate limit),
so the Phase-1/3 fan-outs drain in bounded batches automatically. Register the new
workflow + activities in `worker/worker.py`; add task queue `consolidation`
(separate queue so a consolidation run does not starve live `IssueLifecycle`
triage, or reuse `issue-lifecycle` with the shared 3-slot pool — **decision for
the plan**, default = separate queue + a second `Worker` in the same process).

## 8. Error handling

- Per-issue profile failure retries 3×; a profile that still fails is emitted as a
  `SolutionProfile` with `problem_essence="[EXTRACTION_FAILED]"` and excluded from
  clustering (logged), so one bad issue never sinks the run.
- Cluster step failure retries; on final failure the workflow fails loudly (no
  partial PR).
- z.ai 429 is absorbed by Instructor + activity retries (as in Layer A).
- All GitHub writes honor `DRY_RUN`.

## 9. Testing

- **Unit (mock LLM):** `extract_solution_profile` schema round-trip; `cluster_profiles`
  #111 guard — a fixture with same-mechanism/different-target profiles must yield
  **two** clusters + a cross-link, not one merged cluster.
- **Unit:** role assignment (primary vs secondary), orphan handling, deterministic
  slug/tie-break (re-run → identical `cluster_id`s).
- **Unit:** `write_consolidation_pr` under `DRY_RUN` writes files, opens no PR.
- **Integration (recorded fixtures):** a 6-issue mini-backlog → expected cluster
  map; anchors present on every requirement (no un-sourced claims).

## 10. Open questions (for the plan / calibration)

- **Q1** Separate `consolidation` task queue + second Worker, or reuse
  `issue-lifecycle`? (default: separate.)
- **Q2** Cluster granularity threshold — how coarse before a cluster is "too big
  to be one solution"? Likely a soft cap (~15 members) that splits by sub-mechanism.
- **Q3** Should Layer A priorities weight cluster ordering in the overview
  (highest-priority member sets cluster priority)? (default: yes, max of members.)
- **Q4** Compact-profile token budget for the single reduce call at ~67 issues —
  measure; if it overflows, map-reduce clustering in 2 passes.

## 11. Relationship to FNR pipeline

This design doubles as the **concept input** for FNR-2 if the owner wants the
formal БФТ/СТ artifacts: feed it to `/fnr-concept` → `/fnr-system-requirements`.
Implementing directly from this spec (via writing-plans) is the faster path;
FNR-2 formalization is an optional parallel track for documentation parity with
FNR-1.
