from dataclasses import dataclass, field


@dataclass
class IssueInput:
    repo: str
    issue_number: int
    title: str
    body: str
    author_login: str
    author_type: str  # "Bot" | "User" | ...
    interactive: bool = True  # False in batch backfill: VAGUE escalates, no wait


@dataclass
class GateResult:
    status: str  # "SPAM" | "VAGUE" | "SUFFICIENT"
    content: str


@dataclass
class ClassificationResult:
    label: str  # "advisor:existing-functionality" | "advisor:consultation" | "advisor:bug" | "advisor:feature-request"
    answer: str


@dataclass
class DuplicateResult:
    decision: str  # "duplicate" | "possible" | "none"
    best_match_number: int | None
    probability: float
    reason: str
    context_branch: str | None


@dataclass
class PriorityResult:
    tier: str  # "P0" | "P1" | "P2" | "P3"
    breakdown_markdown: str


@dataclass
class AnalyzeInput:
    repo: str
    issue_number: int
    title: str
    body: str
    comment_id: int | None = None  # комментарий-триггер, на него ставится реакция


@dataclass
class EstimateRequest:
    repo: str
    issue_number: int
    comment_id: int  # комментарий с командой: на него ставится реакция


@dataclass
class EstimationContext:
    title: str
    body: str
    labels: list[str]
    thread: list[str]
    branch: str | None  # research/issue-<n> или bug/issue-<n>, если есть
    artifacts: dict[str, str]  # путь в ветке -> содержимое
    truncated: bool  # часть контекста не влезла в лимиты


@dataclass
class EstimateResult:
    markdown: str
    stopped: bool  # cross-check развалился, итоговых чисел нет


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
