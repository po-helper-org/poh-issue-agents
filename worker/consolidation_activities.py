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
