from dataclasses import dataclass


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
