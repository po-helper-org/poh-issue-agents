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
class WebhookAuditInput:
    """След доставки, отброшенной вебхуком по конфигу.

    Существует только ради видимости: workflow с таким входом — единственный
    способ узнать, что событие приходило и было отклонено (GitHub получает 200,
    ничего другого не остаётся).
    """
    delivery_id: str  # X-GitHub-Delivery: уникален на доставку, даёт идемпотентность
    event: str
    action: str
    repo: str
    reason: str  # пока единственная причина — "repo_not_allowed"
    allowlist: list[str] = field(default_factory=list)


@dataclass
class Deadlines:
    """Сроки ожиданий (правило R3: каждая парковка имеет дедлайн).

    Едут в воркфлоу отдельной activity, а не читаются из окружения прямо в
    коде воркфлоу: результат activity лежит в истории, поэтому реплей после
    смены конфигурации возьмёт то же значение, что и первый прогон. Прочитай
    воркфлоу os.environ напрямую — изменённая переменная дала бы другой таймер
    при воспроизведении и уронила бы прогон недетерминизмом.
    """
    human_decision_hours: int = 72   # ожидание research-me / bug-me
    clarification_hours: int = 48    # ответ на уточняющий вопрос intake gate
    build_decision_hours: int = 72   # ожидание build-me после аналитики
    # Боковые фазы (spam, duplicate, answered, skipped, escalated, failed) —
    # не тупики: человек может вернуть Issue в работу. Но и не вечная сессия.
    side_state_hours: int = 168      # неделя на возврат из бокового состояния


@dataclass
class LifecycleState:
    """Снимок цикла для continue-as-new.

    Переносится КОМПАКТНОЕ состояние — фаза, стадия и то немногое, что нужно
    следующим фазам, — а не тред и не история. Долгоживущий цикл на активном
    Issue иначе упрётся в тот же потолок, который уже словила консолидация:
    на ~75 Issue история превышает ~990 событий и реплей не укладывается в
    workflow-task timeout.
    """
    phase: str = "created"
    stage: str = "intake"
    priority_tier: str = ""              # нужен чеклисту готовности (H1)
    classification_label: str | None = None  # None — сокращённый триаж (R6)
    analysis_done: bool = False
    generation: int = 0                  # сколько раз цикл перезапускался


@dataclass
class ProtocolState:
    """Состояние Issue по протоколу агентов, прочитанное ОДИН раз на старте.

    Правило R2: агент не полагается на порядок вебхуков и не хранит
    предположений о том, чего не проверил сам. Поэтому все три вопроса —
    выключен ли контур, свой ли это вход и не слишком ли глубока цепочка —
    задаются одним чтением, а не размазаны по стадиям.
    """
    agents_off: bool = False       # R4: человек забрал Issue себе
    origin_agent: bool = False     # R6: Issue создан агентом, уже классифицирован
    depth_exceeded: bool = False   # R7: follow-up, порождённый follow-up-ом
    root_issue: int | None = None  # сквозной ключ цепочки из тела


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
    # Комментарий с командой: на него ставится реакция. None — запуск меткой
    # `run:estimate`, реагировать не на что.
    comment_id: int | None = None


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
