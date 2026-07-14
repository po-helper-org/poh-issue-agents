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
