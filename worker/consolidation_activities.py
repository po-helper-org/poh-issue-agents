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


class MergeAssignment(BaseModel):
    cluster_index: int
    group_key: str  # identical key => same final cluster (same mechanism+target)


class MergeExtraction(BaseModel):
    assignments: list[MergeAssignment]


# One reduce call over the whole backlog degenerates to near-singletons at ~50+
# issues (the model cannot hold that many items). Cluster in batches, then merge
# the batch-local clusters across batches. 12 keeps each map call small enough
# for the model to group meaningfully.
CLUSTER_BATCH_SIZE = 12


def _slug(numbers: list[int]) -> str:
    return "cluster-" + "-".join(str(n) for n in sorted(numbers))


def _cluster_call(profiles: list[SolutionProfile]) -> ClusterExtraction:
    listing = "\n".join(
        f"#{p.issue_number} mechanism={p.proposed_mechanism!r} "
        f"target={p.target!r} domain={p.domain}"
        for p in profiles)
    return llm.extract(_load_prompt("system_cluster.md"), listing,
                       ClusterExtraction, model=llm.MODEL_CLASSIFY)


def _merge_local(local: list[ClusterOut]) -> list[ClusterOut]:
    """Second pass: unify batch-local clusters that share a mechanism+target
    across batches. The model assigns each local cluster a group_key; locals with
    the same key are unioned (members deduped by issue_number). Divergent targets
    get different keys (the #111 split is preserved into the merged set)."""
    if len(local) <= 1:
        return local
    summary = "\n".join(
        f"[{i}] mechanism={c.mechanism!r} target={c.target!r} "
        f"members={[m.issue_number for m in c.members]}"
        for i, c in enumerate(local))
    merge = llm.extract(_load_prompt("system_cluster_merge.md"), summary,
                        MergeExtraction, model=llm.MODEL_CLASSIFY)
    key_by_idx = {a.cluster_index: a.group_key for a in merge.assignments}
    groups: dict[str, list[int]] = {}
    for i in range(len(local)):
        # a local cluster the merge step never assigned stays on its own
        key = key_by_idx.get(i, f"__ungrouped_{i}")
        groups.setdefault(key, []).append(i)
    merged: list[ClusterOut] = []
    for idxs in groups.values():
        seen: dict[int, MemberOut] = {}
        for i in idxs:
            for m in local[i].members:
                seen.setdefault(m.issue_number, m)
        rep = local[idxs[0]]
        merged.append(ClusterOut(
            mechanism=rep.mechanism, target=rep.target,
            members=list(seen.values()),
            cross_links=sorted({cl for i in idxs for cl in local[i].cross_links})))
    return merged


@activity.defn
def cluster_profiles(profiles: list[SolutionProfile]) -> ClusterSet:
    active = [p for p in profiles if p.problem_essence != "[EXTRACTION_FAILED]"]
    orphans: list[int] = []
    if len(active) <= CLUSTER_BATCH_SIZE:
        ext = _cluster_call(active)
        local = list(ext.clusters)
        orphans = list(ext.orphans)
    else:
        local = []
        for start in range(0, len(active), CLUSTER_BATCH_SIZE):
            ext = _cluster_call(active[start:start + CLUSTER_BATCH_SIZE])
            local.extend(ext.clusters)
            orphans.extend(ext.orphans)
        local = _merge_local(local)

    clusters = []
    for co in local:
        members = [ClusterMember(issue_number=m.issue_number, role=m.role,
                                 contributed_requirement=m.contributed_requirement)
                   for m in co.members]
        clusters.append(Cluster(
            cluster_id=_slug([m.issue_number for m in co.members]),
            mechanism=co.mechanism, target=co.target,
            members=members, cross_links=co.cross_links))
    return ClusterSet(clusters=clusters, orphans=sorted(set(orphans)))


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


@activity.defn
def fetch_open_issues(cfg: ConsolidationInput) -> list[IssueInput]:
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
                           drafts: list[UnifyingIssueDraft], repo: str) -> str | None:
    from datetime import date
    files = {"docs/consolidation/overview.md": _render_overview(clusterset)}
    for d in drafts:
        files[f"docs/consolidation/unifying/{d.cluster_id}.md"] = d.body_markdown
    branch = f"consolidation/{date.today().isoformat()}"
    body = f"Автоконсолидация: {len(clusterset.clusters)} кластеров, " \
           f"{len(drafts)} объединяющих Issue. Предлагает, не мутирует Issue."
    return github_client.create_pr_with_files(
        repo, branch, "main", files, "Консолидация бэклога", body)
