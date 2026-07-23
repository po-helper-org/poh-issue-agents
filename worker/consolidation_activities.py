"""Consolidation activities: profile extraction, taxonomy/increments, synthesis, PR."""
import re
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import github_client
import llm
from shared.workflow_types import (
    ConsolidationInput, DeliveryZone, Increment, IssueInput, SolutionProfile,
    Taxonomy, UnifyingIssueDraft, ZoneAssignment,
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
    body = issue.body or github_client.get_issue_body(issue.repo, issue.issue_number)
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{body}"
    r = llm.extract(_load_prompt("system_solution_profile.md"), user_message,
                    ProfileExtraction, model=llm.MODEL_CLASSIFY)
    return SolutionProfile(
        issue_number=issue.issue_number, title=issue.title,
        problem_essence=r.problem_essence, proposed_mechanism=r.proposed_mechanism,
        target=r.target, domain=r.domain, anchors=r.anchors,
        advisor_label=getattr(issue, "advisor_label", ""),
    )


class SynthOut(BaseModel):
    title: str
    body_markdown: str


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
    """Increment names become file paths, so collapse everything that is not a
    word char / dot / dash — `:`, `/`, spaces and `&` all appear in real
    increment names (e.g. `jira-bus:MVP: Discovery & Indexing`)."""
    return re.sub(r"[^\w.-]+", "-", name, flags=re.UNICODE).strip("-") or "increment"


@activity.defn
def fetch_open_issues(cfg: ConsolidationInput) -> list[IssueInput]:
    issues = github_client.list_open_issues(cfg.repo, cfg.limit)
    refs = []
    for it in issues:
        if any(lbl in cfg.exclude_labels for lbl in it.get("labels", [])):
            continue
        refs.append(IssueInput(repo=cfg.repo, issue_number=it["number"],
                               title=it["title"], body="",
                               author_login="", author_type="User"))
    return refs


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
