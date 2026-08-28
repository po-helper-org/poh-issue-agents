from dataclasses import dataclass, field
from typing import Literal


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
class UserComment:
    """Реплика человека в Issue, доехавшая до цикла сигналом.

    Отдельный тип, а не строка с префиксом: вместе с текстом обязан ехать ключ
    комментария. Вебхук доставляет каждое событие ДВАЖДЫ (в истории прогона по
    `poh-demo-checkout#42` сигналов ровно вдвое), и без ключа один вопрос
    человека получал бы два ответа.

    `comment_id is None` — реплика от вебхука прежнего поколения, который слал
    сигнал одним аргументом. Такую отвечаем без защиты от повтора: молчание
    хуже возможного дубля.
    """
    text: str
    comment_id: int | None = None


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
    # Парковаться ли на `ready-for-dev` вообще. Живёт здесь, а не отдельным
    # чтением окружения в воркфлоу, ровно по причине из docstring: значение
    # обязано лежать в истории, иначе переключённый посреди прогона тумблер
    # уронил бы реплей недетерминизмом.
    #
    # False (умолчание) — протокол в чистом виде: H1 отдаёт задачу человеку, и
    # разработку начинает его решение `build-me`. True — контур замкнут и идёт
    # от Issue до PR без единого касания.
    develop_autostart: bool = False
    # Парковаться ли на `classified` — то есть ждать ли решения человека о
    # запуске аналитики (`research-me` / `bug-me`).
    #
    # Парковок на основном пути ровно две, и снимаются они РАЗНЫМИ тумблерами:
    # эта — перед дорогой аналитикой, `develop_autostart` — перед разработкой.
    # Один общий тумблер не годится: «пусть сам исследует, но код я запущу
    # руками» — рабочий режим, а не половинчатая настройка. Замкнутый контур —
    # это обе включённые.
    research_autostart: bool = False
    # Доведение PR по замечаниям ревью. Живёт здесь по той же причине, что и
    # остальное: значение обязано лежать в истории, иначе переключённый посреди
    # прогона тумблер уронил бы реплей недетерминизмом.
    pr_fix_enabled: bool = True
    # Потолок кругов. Больше трёх — это уже не придирки ревьюера: так выглядит
    # проблема в самом коде, и лечится она разбором, а не следующим кругом.
    pr_fix_max_rounds: int = 3
    # Разбивать ли задачу на подзадачи перед передачей в разработку.
    decompose_enabled: bool = True
    # Отписывать ли БФТ вместо свободного advisor-ответа на триаже запроса
    # функционала. Живёт здесь по той же причине, что и остальные тумблеры:
    # значение обязано лежать в истории, иначе переключённый посреди прогона
    # тумблер уронил бы реплей недетерминизмом.
    #
    # Умолчание здесь означает «не сконфигурировано», а не «выключено в проде»:
    # продуктовое умолчание задаёт `read_deadlines`, и там БФТ ВКЛЮЧЁН — гасится
    # только явным `BFT_ON_TRIAGE=0`. Так же устроены `develop_autostart` и
    # `research_autostart`. Разница между этим полем и переменной окружения
    # существует ради одного: `Deadlines()` в тестах не должен незаметно
    # затаскивать в прогон стадию, о которой тест не знает.
    bft_on_triage: bool = False
    # Сколько реплик человека в припаркованном Issue контур отвечает содержательно.
    # Потолок нужен затем же, что и у кругов уточнения: диалог без конца — это
    # счёт за модель без конца. Исчерпан — реплики снова просто будят парковку.
    followup_max_rounds: int = 10
    # Приёмка по HowToDemo при открытии PR. ВЫКЛЮЧЕНА по умолчанию, включается
    # явным `HOWTODEMO_AUTOSTART=1`: стадия новая, поднимает контейнер на хосте
    # и зовёт модель, и включать её молча на всех наблюдаемых репозиториях
    # значило бы поставить эксперимент на чужих задачах.
    howtodemo_autostart: bool = False


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
    # Момент входа в текущую фазу, epoch-секунды. Дедлайн парковки отсчитывается
    # от него, а не от последнего сигнала, — иначе любой посторонний комментарий
    # продлевал бы ожидание, и правило R3 переставало бы что-либо гарантировать.
    # Переносится через continue-as-new: перезапуск цикла не должен обнулять срок.
    phase_since_epoch: float = 0.0
    # Задача — часть чужого плана (подзадача декомпозиции). Ни своей
    # декомпозиции, ни своей разработки у неё нет: и то и другое ведёт родитель.
    plan_member: bool = False
    root_issue: int | None = None        # родитель плана, если это подзадача
    # Номер PR по задаче. Без него фаза доведения не знает, что доводить, и
    # вместо круга правок молча уходит в парковку: PR открыт, ревью прошло,
    # замечания не исправляются.
    pr_number: int | None = None
    # Сколько кругов уточнения после аналитики потрачено: потолок обязан
    # переживать перезапуск, иначе continue-as-new обнулял бы его и вопросы
    # могли задаваться заново без конца.
    clarify_rounds: int = 0
    # Сколько реплик человека уже отвечено содержательно и ключи последних из
    # них. Переносятся по той же причине, что и `clarify_rounds`: перезапуск
    # цикла не должен ни обнулять потолок, ни терять защиту от повторной
    # доставки вебхука — иначе первый же continue-as-new отвечает дважды.
    followup_rounds: int = 0
    answered_comment_ids: list[int] = field(default_factory=list)
    # Сколько раз человек вернул этап на пересборку (rework intent).
    # Переносится по той же причине, что и `clarify_rounds`: перезапуск
    # не должен обнулять потолок, иначе «переделай» ↔ «переделал» будет
    # повторяться бесконечно.
    rework_rounds: int = 0


@dataclass
class OrphanEventInput:
    """Событие агента, которое не удалось связать ни с одним Issue.

    Существует ради видимости, как и `WebhookAuditInput`: связать работу с
    задачей не вышло, ни одна фаза не сдвинется, и единственное, что остаётся, —
    не потерять факт. Тишина здесь означала бы ровно тот обрыв трассировки,
    ради которого задача #38 и ставилась.
    """
    repo: str
    agent: str
    phase: str
    status: str
    ref: str
    reason: str   # чем именно не удалось опознать Issue
    detail: str = ""


@dataclass
class CommentAckInput:
    """Комментарий, приём которого надо подтвердить реакцией.

    Отдельный вход, а не поле в `IssueInput`: подтверждение приёма не знает ни
    заголовка, ни тела, ни автора — оно ставится по факту доставки и ничем не
    гейтится.
    """
    repo: str
    issue_number: int
    comment_id: int


@dataclass
class ProtocolState:
    """Состояние Issue по протоколу агентов, прочитанное ОДИН раз на старте.

    Правило R2: агент не полагается на порядок вебхуков и не хранит
    предположений о том, чего не проверил сам. Поэтому все четыре вопроса —
    выключен ли контур, свой ли это вход, не подзадача ли это шага плана и не
    слишком ли глубока цепочка — задаются одним чтением, а не размазаны по
    стадиям.
    """
    agents_off: bool = False       # R4: человек забрал Issue себе
    origin_agent: bool = False     # R6: Issue создан агентом, уже классифицирован
    depth_exceeded: bool = False   # R7: follow-up, порождённый follow-up-ом
    root_issue: int | None = None  # сквозной ключ цепочки из тела
    step_subissue: bool = False    # R5: под-задача шага плана, свой цикл не поднимает


@dataclass
class GateResult:
    status: str  # "SPAM" | "VAGUE" | "SUFFICIENT"
    content: str


@dataclass
class ClassificationResult:
    label: str  # "advisor:existing-functionality" | "advisor:consultation" | "advisor:bug" | "advisor:feature-request" | "advisor:product-research"
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
    priority_label: str = ""  # Full label name, e.g. "priority:P0"


@dataclass
class AnalyzeInput:
    repo: str
    issue_number: int
    title: str
    body: str
    comment_id: int | None = None  # комментарий-триггер, на него ставится реакция
    # Чем прогон вызван — для подтверждения приёма. Пусто означает `/analyze`
    # либо метку `run:analyze`; цикл ставит сюда `research-me`, чтобы ack не
    # называл человеку метку, которую тот не ставил.
    trigger: str | None = None


@dataclass
class DevelopPlan:
    """Решения, принятые на входе в разработку, — один раз на стадию.

    Режим и ветка аналитики определяются активностью, а не воркфлоу: и то и
    другое читается из окружения и из GitHub, а решение воркфлоу обязано быть
    детерминированным при реплее. Результат активности лежит в истории, поэтому
    повтор возьмёт то же значение, что и первый прогон.
    """
    mode: str    # "local" | "dispatch" (`shared/develop.py`)
    branch: str  # ветка артефактов аналитики; "" — аналитики не было


@dataclass
class BftRequest:
    """Вход воркфлоу БФТ. Один тип на оба режима — различает их поле `mode`.

    Раздельные типы под `fast` и `deep` дали бы два почти одинаковых входа и две
    ветки в вебхуке; разница между режимами вся в пайплайне, а не во входе.
    """
    repo: str
    issue_number: int
    title: str
    body: str
    mode: str = "fast"  # shared.bft.FAST | shared.bft.DEEP
    # Хвост команды: замечания к формулировке (`/bft`) либо ответы на открытые
    # вопросы (`/bft-deep`). Пусто при запуске меткой и на триаже.
    instructions: str = ""
    comment_id: int | None = None  # комментарий-триггер, на него ставится реакция
    # Id сессии entire из `/bft-deep <id>`: продолжение оборванного прогона.
    # Пусто — обычный запуск, прогон поднимает ветку артефактов по номеру Issue.
    session_id: str = ""
    # Чем прогон вызван — для подтверждения приёма. Пусто означает команду либо
    # метку `run:*`; триаж ставит сюда `triage`, чтобы ack не называл человеку
    # команду, которую тот не вводил.
    trigger: str | None = None


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


@dataclass
class CommentIntent:
    """Намерение, извлечённое из реплики человека.
    
    Активность `interpret_user_comment` возвращает этот тип — по нему цикл
    принимает решение о том, что делать с комментарием.
    """
    intent: str  # "proceed" | "rework" | "question" | "ack"
    reason: str  # обоснование для комментария-ответа
    rework_note: str = ""  # что именно переделывать (только для intent="rework")
