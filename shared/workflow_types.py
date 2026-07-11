from dataclasses import dataclass


@dataclass
class IssueInput:
    repo: str
    issue_number: int
    title: str
    body: str
    author_login: str
    author_type: str  # "Bot" | "User" | ...


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
