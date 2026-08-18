"""
Activities — вся содержательная логика, перенесённая из advisor/gate.py,
classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py
(версия на GitHub Actions). Изменился только транспорт: вместо чтения
GITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-
функции, вызываемые Temporal-воркером напрямую.
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import estimate_report
import estimation
import github_client
import llm
from shared import develop, labels, lifecycle, sentry_setup
from shared.awaiting import Awaiting
from shared.commands import (
    ANALYZE,
    ESTIMATE,
    done_label,
    failed_label,
    parse_command,
    run_label,
    running_labels,
)
from shared.workflow_types import (
    AnalyzeInput,
    ClassificationResult,
    Deadlines,
    DuplicateResult,
    EstimateRequest,
    EstimateResult,
    EstimationContext,
    GateResult,
    IssueInput,
    PriorityResult,
    ProtocolState,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path("/app/prompts")
CONFIG_DIR = Path("/app/config")
WORKSPACE_DIR = Path("/app/workspace")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# --- Pydantic-схемы для Instructor (заменяют ручной парсинг [[MARKER]]) ---

class GateExtraction(BaseModel):
    status: str = Field(description="SPAM | VAGUE | SUFFICIENT")
    content: str = Field(description="Причина (SPAM) или уточняющие вопросы (VAGUE) или подтверждение (SUFFICIENT)")


class ClassificationExtraction(BaseModel):
    category: str = Field(description="EXISTING | CONSULTATION | BUG | FEATURE")
    answer: str


class DuplicateCandidate(BaseModel):
    number: int
    probability: float
    reason: str


class DuplicateExtraction(BaseModel):
    candidates: list[DuplicateCandidate]


class PriorityExtraction(BaseModel):
    impact: int
    time_criticality: int
    risk_reduction: int
    effort: int
    okr_alignment: str  # unrelated | supports_okr | direct_top_priority
    okr_key_result: str | None = None
    bug_severity: str = "none"  # none | high | critical
    affected_domains: list[str] = []
    who: str = ""
    risks: list[str] = []
    goal_impact: str = ""


# --- Zero-cost предфильтры ---

@activity.defn
def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str | None:
    """Возвращает причину пропуска, если стоит остановиться, иначе None.

    `origin_agent` снимает ТОЛЬКО проверку на бота. Follow-up контура заводит
    агент — под токеном Actions либо под своим App, — и по автору он бот. Но
    провенанс `origin:agent` означает ровно обратное тому, ради чего фильтр
    заведён: это не шум от dependabot, а собственный выход контура, которому
    протокол (R6) предписывает сокращённый триаж, а не пропуск. Без этого
    исключения каждый найденный агентом edge-кейс тихо умирал бы с меткой
    `bot-authored`, и декомпозиция работы не доезжала бы до бэклога.

    Проверка на безопасность остаётся: она о содержимом, а не об авторе, и
    репорт об уязвимости не становится безопаснее оттого, что его завёл агент.
    """
    if not origin_agent:
        if issue.author_type == "Bot":
            github_client.add_label(issue.repo, issue.issue_number, "bot-authored")
            return "bot"

        KNOWN_BOT_LOGINS = {"dependabot", "renovate", "snyk-bot", "github-actions"}
        if issue.author_login.lower().removesuffix("[bot]") in KNOWN_BOT_LOGINS:
            github_client.add_label(issue.repo, issue.issue_number, "bot-authored")
            return "bot"

    # Latin terms must match whole words: the substring "rce" otherwise fires on
    # "source"/"resource"/"ресурс" and false-flags most feature issues as
    # security-sensitive. Cyrillic stems stay as substrings (morphology).
    SECURITY_PATTERNS = (r"\bvulnerabilit\w*", r"\bcve-\d", r"\bexploit\w*",
                          r"\bsql injection\b", r"\brce\b", r"\bremote code execution\b")
    SECURITY_SUBSTRINGS = ("уязвимост", "эксплойт", "утечка данных")
    text = f"{issue.title} {issue.body}".lower()
    if any(re.search(p, text) for p in SECURITY_PATTERNS) or \
       any(term in text for term in SECURITY_SUBSTRINGS):
        github_client.post_comment(
            issue.repo, issue.issue_number,
            "🔒 Похоже, это может касаться уязвимости безопасности. "
            "Автоматическая обработка приостановлена. Если включён Private "
            "Vulnerability Reporting — перенеси репорт туда.",
        )
        github_client.add_label(issue.repo, issue.issue_number, "security-sensitive")
        return "security"

    return None


# --- Intake Gate ---

@activity.defn
def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult:
    thread_text = "\n\n".join(f"Пользователь: {c}" for c in comment_thread)
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}\n\n{thread_text}"
    result = llm.extract(
        _load_prompt("system_intake_gate.md"), user_message, GateExtraction, model=llm.MODEL_GATE,
    )
    return GateResult(status=result.status, content=result.content)


@activity.defn
def post_clarifying_question(issue: IssueInput, questions: str) -> None:
    github_client.post_comment(issue.repo, issue.issue_number, questions)
    github_client.add_label(issue.repo, issue.issue_number, "needs-clarification")


@activity.defn
def close_as_spam(issue: IssueInput, reason: str) -> None:
    github_client.post_comment(issue.repo, issue.issue_number, f"🚫 Похоже на спам: {reason}")
    github_client.add_label(issue.repo, issue.issue_number, "spam")
    github_client.close_issue(issue.repo, issue.issue_number)


@activity.defn
def escalate_to_human(issue: IssueInput, reason: str = "") -> None:
    """Передача человеку. Метка — из общего словаря контура (`needs-human:*`),
    чтобы одна выборка по организации показывала всю очередь к людям."""
    github_client.post_comment(
        issue.repo, issue.issue_number,
        reason or "Не удалось сузить запрос за отведённое число уточнений. "
                  "Передаю на ручной разбор.",
    )
    github_client.add_label(issue.repo, issue.issue_number, labels.NEEDS_HUMAN_TRIAGE)


@activity.defn
def set_phase(repo: str, issue_number: int, phase: str) -> None:
    """Метка фазы с соблюдением инварианта «одна фаза — одна метка».

    Две метки `phase:*` на Issue — противоречие, а не история: по ним нельзя
    восстановить состояние. Поэтому предыдущая снимается, а не остаётся рядом.

    Допустимость самого перехода проверяет воркфлоу (у него есть предыдущая
    фаза); здесь — только запись, идемпотентная по построению.
    """
    target = lifecycle.phase_label(phase)
    stale_labels = [lifecycle.phase_label(other) for other in lifecycle.PHASES]
    # Индикатор разработки — не фаза, но живёт по тому же правилу: он сообщает
    # «задача у агента разработки», и после открытия PR это уже неправда.
    # Снимать его в самой активности Develop нельзя — она к тому моменту давно
    # завершилась; единственная точка, которая знает о смене состояния, — здесь.
    if phase != lifecycle.IN_DEVELOPMENT:
        stale_labels.append(develop.IN_DEVELOPMENT_LABEL)
    for stale in stale_labels:
        if stale != target:
            try:
                github_client.remove_label(repo, issue_number, stale)
            except Exception as exc:
                logger.warning("не снял метку фазы %s с %s#%s: %s",
                               stale, repo, issue_number, exc)
    github_client.add_label(repo, issue_number, target)


@activity.defn
def mark_awaiting(repo: str, issue_number: int, waiting=None) -> None:
    """Отражение ожидания в GitHub: очередь к людям обязана быть полной (#39).

    Метка ставится, пока ход за человеком, и снимается, как только ожидание
    закрыто. До этого `needs-human:*` появлялась только по истечении дедлайна —
    то есть выборка показывала не очередь, а её просроченный хвост.

    Ожидание машины (стенд, соседний сервис) метку НЕ ставит: задача, по которой
    человеку делать нечего, в его очереди — шум, из-за которого перестают
    смотреть на саму выборку.
    """
    if waiting is not None and isinstance(waiting, dict):
        waiting = Awaiting(**waiting)
    if waiting is not None and waiting.blocks_on_human:
        github_client.add_label(repo, issue_number, labels.NEEDS_HUMAN_TRIAGE)
        return
    try:
        github_client.remove_label(repo, issue_number, labels.NEEDS_HUMAN_TRIAGE)
    except Exception as exc:
        logger.warning("не снял метку ожидания с %s#%s: %s", repo, issue_number, exc)


@activity.defn
def read_deadlines() -> Deadlines:
    """Сроки ожиданий из окружения (R3). Читаются activity, а не воркфлоу.

    Воркфлоу не может брать их из os.environ напрямую: таймер вычисляется при
    КАЖДОМ воспроизведении истории, и правка переменной сломала бы уже идущий
    прогон недетерминизмом. Результат activity лежит в истории — реплей берёт
    ровно то значение, с которым прогон начинался.
    """
    def _hours(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        try:
            value = int(raw) if raw else default
        except ValueError:
            logger.warning("%s=%r не число, беру значение по умолчанию %s", name, raw, default)
            return default
        # 0 или отрицательное значение означало бы «истекло сразу» — почти
        # наверняка опечатка, а не намерение выключить ожидание.
        return value if value > 0 else default

    return Deadlines(
        human_decision_hours=_hours("PARK_DECISION_HOURS", 72),
        clarification_hours=_hours("PARK_CLARIFICATION_HOURS", 48),
        build_decision_hours=_hours("PARK_BUILD_HOURS", 72),
        side_state_hours=_hours("PARK_SIDE_STATE_HOURS", 168),
        develop_autostart=os.environ.get(
            "DEVELOP_AUTOSTART", "").strip().lower() in {"1", "true", "yes", "on"},
    )


# Маркер незакрытого вопроса в артефактах анализа: то, что разработчику
# придётся решать самому. Выносится в чеклист готовности отдельным списком.
OPEN_QUESTION_MARKER = "[УТОЧНИТЬ]"
MAX_OPEN_QUESTIONS = 15


def _open_questions(repo: str, branch: str) -> list[str]:
    """Строки с маркером `[УТОЧНИТЬ]` из артефактов анализа.

    Разработчик должен увидеть незакрытые вопросы ДО того, как возьмёт задачу,
    а не наткнуться на них в середине реализации.
    """
    found: list[str] = []
    for name in ARTIFACT_FILES:
        path = f"{FNR_DIR}/{name}"
        content = github_client.get_file(repo, path, branch)
        if not content:
            continue
        for line in content.splitlines():
            if OPEN_QUESTION_MARKER in line:
                found.append(f"{name}: {line.strip()[:200]}")
                if len(found) >= MAX_OPEN_QUESTIONS:
                    return found
    return found


@activity.defn
def mark_ready_for_dev(issue: IssueInput, priority_tier: str, branch: str) -> None:
    """Точка передачи задачи разработчику (H1 протокола).

    Единственное место, где контур отдаёт работу человеку по своей инициативе.
    Метка `ready-for-dev` делает выборку рабочей очередью разработчика, а
    комментарий отвечает на вопрос «что известно и чего не хватает», чтобы
    задачу можно было взять, не задавая уточняющих вопросов о постановке.
    """
    base = f"https://github.com/{issue.repo}/blob/{branch}"
    questions = _open_questions(issue.repo, branch)
    open_block = (
        "\n".join(f"- {q}" for q in questions)
        if questions
        else "- не осталось: анализ не оставил незакрытых вопросов"
    )
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "## ✅ Задача готова к разработке\n\n"
        "**Что известно:**\n"
        f"- Классификация проведена, приоритет — `{priority_tier}`\n"
        "- Дубли проверены\n"
        f"- Аналитика прогнана, артефакты в ветке [`{branch}`]({base}/{FNR_DIR})\n\n"
        "**С чего начать:** "
        f"[`system_requirements.md`]({base}/{FNR_DIR}/system_requirements.md) — "
        "разбор текущего поведения на код-доказательствах, план работ с критериями "
        "приёмки и риски.\n\n"
        "**Осталось неопределённым:**\n"
        f"{open_block}\n\n"
        f"Открывая PR, поставь `Closes #{issue.issue_number}` — по этой ссылке "
        "цепочка связывается сквозным ключом, и агенты доведения увидят исходную задачу.",
    )
    github_client.add_label(issue.repo, issue.issue_number, labels.READY_FOR_DEV)


@activity.defn
def post_agents_off_notice(repo: str, issue_number: int, what: str) -> None:
    """Короткий ответ на явную команду человека при поднятом рубильнике.

    Молча проигнорировать нельзя: команду набрал человек и ждёт результата, а
    тишина неотличима от поломки. Комментарий бюджета не стоит — правило R4
    защищает от вызовов LLM, а не от одной строки в треде.
    """
    github_client.post_comment(
        repo, issue_number,
        f"⏸️ На Issue стоит `{labels.AGENTS_OFF}` — `{what}` не запускаю. "
        "Сними метку, если работа агентов снова нужна.",
    )


@activity.defn
def read_protocol_state(repo: str, issue_number: int) -> ProtocolState:
    """Состояние Issue по протоколу — одно чтение на старте (правило R2).

    Три вопроса сразу, потому что каждый меняет маршрут целиком:

    - `agents:off` — человек забрал Issue себе. Проверяется здесь, ДО первого
      обращения к LLM: смысл рубильника в том, чтобы не тратить бюджет (R4).
    - `origin:agent` — Issue создал агент, значит он уже классифицирован, и
      advisor-ответ был бы разговором сервиса с самим собой (R6).
    - глубина цепочки — follow-up, порождённый follow-up-ом. Родителя ищем по
      строке `root-issue: #N` в теле; если у родителя тоже `origin:agent`,
      цепочка пошла на второй круг и дальше её ведёт человек (R7). Иначе контур
      начинает кормить сам себя: каждый PR рождает Issue, каждый Issue — PR.

    Родитель читается ТОЛЬКО когда сам Issue от агента: для обычной задачи это
    лишний вызов GitHub на каждом прогоне.
    """
    issue = github_client.get_issue(repo, issue_number)
    names = [label["name"] for label in issue.get("labels", [])]
    origin_agent = labels.has(names, labels.ORIGIN_AGENT)
    root_issue = labels.parse_root_issue(issue.get("body"))

    depth_exceeded = False
    if origin_agent and root_issue is not None:
        try:
            parent = github_client.get_issue(repo, root_issue)
            parent_names = [label["name"] for label in parent.get("labels", [])]
            depth_exceeded = labels.has(parent_names, labels.ORIGIN_AGENT)
        except Exception as exc:
            # Родителя могли удалить или он в другом репозитории. Это не повод
            # ронять триаж: без доказательства второго круга считаем глубину
            # допустимой — ложный стоп дороже лишнего прогона.
            logger.warning("не прочитал родительский issue #%s: %s", root_issue, exc)

    return ProtocolState(
        agents_off=labels.has(names, labels.AGENTS_OFF),
        origin_agent=origin_agent,
        depth_exceeded=depth_exceeded,
        root_issue=root_issue,
    )


@activity.defn
def post_error_label(issue: IssueInput, reason: str = "") -> None:
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "⚠️ Автоматическая обработка не удалась. Ожидай ручного разбора.",
    )
    github_client.add_label(issue.repo, issue.issue_number, "advisor:error")
    # `reason` = "ExcType: message" из catch-ветки workflow'а (workflows.py).
    # Без него (прямой вызов/старые тесты) exc_type пуст — событие всё равно
    # уходит, просто с менее точной группировкой.
    exc_type, _, message = reason.partition(": ")
    sentry_setup.capture_pipeline_failure(issue, exc_type or "unknown", message or reason)


@activity.defn
async def mark_analyzing(repo: str, issue_number: int) -> None:
    """Видимая метка, что по Issue запущен автономный анализ (/analyze).
    add_label соблюдает DRY_RUN, отдельного гарда не нужно."""
    await asyncio.to_thread(github_client.add_label, repo, issue_number, "analyzing")


# --- Метки состояния команды: run:<cmd> → done:<cmd> | failed:<cmd> ---

@activity.defn
async def mark_command_running(repo: str, issue_number: int, command: str) -> None:
    """Метка «прогон идёт» ставится САМИМ прогоном, а не только триггером.

    Иначе выборка `label:run:*` врала бы: запуск командой в комментарии не
    оставлял бы следа в ленте Issue. Повторная установка той же метки для
    GitHub безопасна — при запуске лейблом она уже висит."""
    await asyncio.to_thread(github_client.add_label, repo, issue_number, run_label(command))


@activity.defn
async def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None:
    """Обратный ход: снять метки «идёт», повесить исход.

    Неуспех получает СВОЮ метку, а не просто снятый `run:*`: молча снятая метка
    неотличима от «никто не запускал», а именно это и нужно увидеть в ленте.

    Best-effort по каждой метке: прогон уже состоялся, и провал косметики не
    должен превращать успешный анализ в проваленный. Ошибка уходит в лог, но
    наружу не пробрасывается — activity зовётся из терминальных веток воркфлоу.
    """
    for stale in running_labels(command):
        try:
            await asyncio.to_thread(github_client.remove_label, repo, issue_number, stale)
        except Exception as exc:
            logger.warning("не снял метку %s с %s#%s: %s", stale, repo, issue_number, exc)
    outcome = done_label(command) if ok else failed_label(command)
    try:
        await asyncio.to_thread(github_client.add_label, repo, issue_number, outcome)
    except Exception as exc:
        logger.warning("не поставил метку %s на %s#%s: %s", outcome, repo, issue_number, exc)


# --- Классификация ---

@activity.defn
def classify_issue(issue: IssueInput) -> ClassificationResult:
    capabilities = (WORKSPACE_DIR / "capabilities.md").read_text(encoding="utf-8") \
        if (WORKSPACE_DIR / "capabilities.md").exists() else "(пусто)"
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}\n\nИзвестный функционал:\n{capabilities}"
    result = llm.extract(
        _load_prompt("system_advisor.md"), user_message, ClassificationExtraction, model=llm.MODEL_CLASSIFY,
    )
    label_map = {
        "EXISTING": "advisor:existing-functionality",
        "CONSULTATION": "advisor:consultation",
        "BUG": "advisor:bug",
        "FEATURE": "advisor:feature-request",
    }
    label = label_map.get(result.category, "advisor:answered")
    # The advisor prompt still asks the model to prefix its answer with a
    # legacy [[MARKER]] (from the pre-Instructor text-parsing era). The
    # category is now carried structurally, so strip that marker line before
    # posting — it must not appear in the user-facing comment.
    answer = re.sub(r"^\s*\[\[[^\]]+\]\]\s*", "", result.answer)
    github_client.post_comment(issue.repo, issue.issue_number, answer)
    github_client.add_label(issue.repo, issue.issue_number, label)
    return ClassificationResult(label=label, answer=answer)


# --- Duplicate Check ---

@activity.defn
def duplicate_check(issue: IssueInput) -> DuplicateResult:
    candidates = github_client.search_candidates(issue.repo, issue.title)
    candidates = [c for c in candidates if c["number"] != issue.issue_number]
    if not candidates:
        return DuplicateResult(decision="none", best_match_number=None, probability=0.0, reason="", context_branch=None)

    listing = "\n\n".join(
        f"#{c['number']} [{c['_kind']}, {c['state']}] {c['title']}\n{(c.get('body') or '')[:300]}"
        for c in candidates
    )
    system_prompt = (
        "Оцени вероятность (0.0-1.0), что текущий issue — дубликат каждого "
        "кандидата. Не завышай: 0.85+ только при уверенности, что это тот же запрос."
    )
    user_message = f"Текущий issue #{issue.issue_number}: {issue.title}\n\n{issue.body}\n\nКандидаты:\n\n{listing}"
    result = llm.extract(system_prompt, user_message, DuplicateExtraction, model=llm.MODEL_GATE)

    if not result.candidates:
        return DuplicateResult(decision="none", best_match_number=None, probability=0.0, reason="", context_branch=None)

    best = max(result.candidates, key=lambda c: c.probability)

    if best.probability >= 0.85:
        branch = None
        for prefix in ("research", "bug"):
            candidate_branch = f"{prefix}/issue-{best.number}"
            if github_client.branch_exists(issue.repo, candidate_branch):
                branch = candidate_branch
                break
        reuse_note = f"\n\nВ ветке `{branch}` уже есть наработки." if branch else ""
        github_client.post_comment(
            issue.repo, issue.issue_number,
            f"🔁 Вероятный дубликат #{best.number} ({best.probability:.0%}): {best.reason}{reuse_note}"
            f"\n\n⚠️ Не закрыт автоматически — нужно решение человека "
            f"(функциональный дубль ≠ целевой, см. #111).",
        )
        github_client.add_label(issue.repo, issue.issue_number, "duplicate")
        return DuplicateResult(decision="duplicate", best_match_number=best.number,
                                probability=best.probability, reason=best.reason, context_branch=branch)

    if best.probability >= 0.5:
        github_client.add_label(issue.repo, issue.issue_number, "possible-duplicate")
        return DuplicateResult(decision="possible", best_match_number=best.number,
                                probability=best.probability, reason=best.reason, context_branch=None)

    return DuplicateResult(decision="none", best_match_number=None, probability=0.0, reason="", context_branch=None)


# --- Priority Scoring ---

@activity.defn
def score_priority(issue: IssueInput, classification: ClassificationResult, dup: DuplicateResult) -> PriorityResult:
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}\n\nТип: {classification.label}"
    extracted = llm.extract(
        _load_prompt("system_priority_extract.md"), user_message, PriorityExtraction, model=llm.MODEL_GATE,
    )

    with open(CONFIG_DIR / "priority-weights.toml", "rb") as f:
        config = tomllib.load(f)

    multiplier = config["okr_multiplier"][extracted.okr_alignment]
    cost_of_delay = extracted.impact + extracted.time_criticality + extracted.risk_reduction
    raw_score = (cost_of_delay * multiplier) / max(extracted.effort, 1)

    thresholds = config["thresholds"]
    if raw_score >= thresholds["p0_min"]:
        tier = "P0"
    elif raw_score >= thresholds["p1_min"]:
        tier = "P1"
    elif raw_score >= thresholds["p2_min"]:
        tier = "P2"
    else:
        tier = "P3"

    if extracted.bug_severity == "critical":
        tier = config["bug_severity_override"]["critical_forces_priority"]

    breakdown = (
        f"## Приоритет: {tier}\n\n"
        f"- Impact: {extracted.impact}/5, Time criticality: {extracted.time_criticality}/5, "
        f"Risk reduction: {extracted.risk_reduction}/5\n"
        f"- OKR alignment: {extracted.okr_alignment} (×{multiplier})\n"
        f"- Effort: {extracted.effort}/10\n"
        f"- Score = ({cost_of_delay} × {multiplier}) / {extracted.effort} = {round(raw_score, 2)}\n\n"
        f"**Кто исполняет:** {extracted.who}\n"
        f"**Риски:** {', '.join(extracted.risks) or '—'}\n"
        f"**Влияние на цели:** {extracted.goal_impact}"
    )
    return PriorityResult(tier=tier, breakdown_markdown=breakdown)


@activity.defn
def post_priority_comment(issue: IssueInput, priority: PriorityResult, dup: DuplicateResult) -> None:
    body = priority.breakdown_markdown
    if dup.decision == "possible":
        body += (
            f"\n\n⚠️ Также похоже на возможный дубликат #{dup.best_match_number} "
            f"({dup.probability:.0%}) — стоит проверить перед запуском тяжёлой стадии."
        )
    github_client.post_comment(issue.repo, issue.issue_number, body)
    github_client.add_label(issue.repo, issue.issue_number, f"priority:{priority.tier}")


# --- Пайплайн SA-helper (FNR) ---

FNR_DIR = "sa_documentation/FNR/FNR_1"
ARTIFACT_FILES = ("task.md", "concept.md", "system_requirements.md", "validation.md")
CLAUDE_STAGE_TIMEOUT_SEC = 900
REPOMIX_TIMEOUT_SEC = 600
CLONE_TIMEOUT_SEC = 300
HEARTBEAT_INTERVAL_SEC = 30.0

# Обогащение контекста /analyze (спека 2026-07-24). Двигаются без правки логики.
CONTEXT_COMMENT_LIMIT = 20      # свежих комментариев в бриф
CONTEXT_COMMENT_CHARS = 1500    # обрезка одного комментария
CONTEXT_PR_LIMIT = 20           # связанных PR
CONTEXT_TOTAL_CHARS = 16000     # потолок брифа (title+body неприкосновенны)


def _fnr_stages(description: str) -> list[tuple[str, str, str | None]]:
    """Стадии цепочки FNR: (имя, промпт, ожидаемый артефакт).

    У `debate` и `validate` ожидаемого файла нет: дебаты дописываются в
    concept.md, а валидация может остаться отчётом в выводе.
    """
    return [
        ("task", f"/fnr-new-task {description}", f"{FNR_DIR}/task.md"),
        ("concept", f"/fnr-concept {FNR_DIR}/task.md", f"{FNR_DIR}/concept.md"),
        ("debate", f"/fnr-debate {FNR_DIR}/concept.md", None),
        ("sysreq", f"/fnr-system-requirements {FNR_DIR}/concept.md",
         f"{FNR_DIR}/system_requirements.md"),
        ("validate", f"/validate-doc {FNR_DIR}/system_requirements.md", None),
    ]


FNR_STAGE_NAMES = ("task", "concept", "debate", "sysreq", "validate")

# Входной артефакт каждой стадии — что уже должно лежать в рабочем каталоге,
# чтобы стадия имела смысл (используется guard'ом _require_workspace).
_FNR_STAGE_REQUIRES = {
    "task": None,
    "concept": f"{FNR_DIR}/task.md",
    "debate": f"{FNR_DIR}/concept.md",
    "sysreq": f"{FNR_DIR}/concept.md",
    "validate": f"{FNR_DIR}/system_requirements.md",
}


def _fnr_stage(name: str, description: str) -> tuple[str, str | None, str | None]:
    """(промпт, ожидаемый артефакт, требуемый вход) для стадии по имени."""
    for n, prompt, expected in _fnr_stages(description):
        if n == name:
            return prompt, expected, _FNR_STAGE_REQUIRES[name]
    raise ValueError(f"неизвестная стадия FNR: {name}")


def _workspace_dir(analyze: AnalyzeInput) -> Path:
    """Детерминированный рабочий каталог прогона (переживает activity в пределах
    жизни контейнера). База — ANALYSIS_WORKSPACE_ROOT или системный temp."""
    root = os.environ.get("ANALYSIS_WORKSPACE_ROOT") or tempfile.gettempdir()
    slug = f"analysis-{analyze.repo.replace('/', '__')}-{analyze.issue_number}"
    return Path(root) / slug


def _clone_dir(analyze: AnalyzeInput) -> str:
    return str(_workspace_dir(analyze) / "repo")


def _build_workspace(analyze: AnalyzeInput) -> str:
    """Свежий каталог: снести остаток прежнего прогона, clone, repomix."""
    shutil.rmtree(_workspace_dir(analyze), ignore_errors=True)
    clone_dir = _clone_dir(analyze)
    _clone_repo(analyze.repo, clone_dir)
    _run_repomix(clone_dir)
    return clone_dir


def _require_workspace(analyze: AnalyzeInput, requires: str | None) -> str:
    """Guard стадии: каталог+repomix на месте? требуемый вход на месте? Иначе
    fail-fast (без пере-клона — он дал бы свежий репозиторий без артефактов)."""
    clone_dir = _clone_dir(analyze)
    if not (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists():
        raise RuntimeError("рабочий каталог потерян (рестарт воркера?) — повтори /analyze")
    if requires and not (Path(clone_dir) / requires).exists():
        raise RuntimeError(
            f"нет входа {requires} (стадия-предшественник не отработала?) — повтори /analyze"
        )
    return clone_dir


def _clone_repo(repo: str, dest: str) -> None:
    """Shallow-клон целевого репозитория: артефакты FNR обязаны опираться на
    реальный код (`файл:строка`), одного текста Issue недостаточно.

    Токен идёт через credential.helper в env, а НЕ вклеен в URL: argv команды
    целиком рендерится в текст subprocess.CalledProcessError/TimeoutExpired,
    и без этого любой сбой клонирования (протухший токен, сетевой сбой,
    таймаут) унёс бы живой GitHub-токен прямо в Temporal event history и
    логи воркера — ровно туда, куда человек полезет отлаживать сбой.
    """
    url = f"https://github.com/{repo}.git"
    env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "!f() { echo username=x-access-token; echo password=$GH_CLONE_TOKEN; }; f",
        "GH_CLONE_TOKEN": github_client.auth_token(repo),
    }
    subprocess.run(
        ["git", "clone", "--depth", "1", url, dest],
        env=env, check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT_SEC,
    )


def _run_repomix(clone_dir: str) -> None:
    """Упаковка кода один раз: 5 стадий переиспользуют один файл вместо того,
    чтобы каждая заново обходила репозиторий."""
    out = Path(clone_dir) / "sa_documentation" / "repomix-output.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["repomix", "--output", str(out)],
        cwd=clone_dir, check=True, capture_output=True, text=True,
        timeout=REPOMIX_TIMEOUT_SEC,
    )


def _claude_anthropic_creds() -> tuple[str, str]:
    """Креды для `claude -p` из тех же ZAI_*, что и Python-стадии (единый ключ
    z.ai). claude-code говорит по протоколу Anthropic, поэтому нужен другой ПУТЬ
    эндпоинта того же хоста: ZAI_BASE_URL = .../coding/paas/v4 (OpenAI-формат),
    Anthropic-формат живёт на .../api/anthropic. Отдельные ANTHROPIC_* задавать
    не нужно, но если заданы — приоритетнее (явный override)."""
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ZAI_API_KEY", "")
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not base:
        zai = os.environ.get("ZAI_BASE_URL", "")
        if zai:
            from urllib.parse import urlsplit
            p = urlsplit(zai)
            base = f"{p.scheme}://{p.netloc}/api/anthropic"
    return token, base


def _run_claude(prompt: str, cwd: str) -> None:
    """Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.

    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его
    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.
    """
    token, base = _claude_anthropic_creds()
    # Понятная ошибка вместо голого "exit 1", если z.ai не сконфигурирован:
    # без креды claude-code уходит на дефолтный Anthropic API и падает.
    if not token or not base:
        raise RuntimeError(
            "claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL "
            "(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера."
        )
    result = subprocess.run(
        # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера
        # работает от root, а тот флаг под root запрещён самим claude-code
        # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).
        ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
        cwd=cwd, capture_output=True, text=True,
        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,
        # claude-code читает креды из своих ANTHROPIC_*; выводим их из ZAI_*.
        env={**os.environ, "ANTHROPIC_AUTH_TOKEN": token, "ANTHROPIC_BASE_URL": base},
    )
    if result.returncode != 0:
        # claude-code часто пишет диагностику в stdout, а не stderr — берём оба
        # (stderr приоритетнее), иначе сообщение об ошибке оказывается пустым.
        detail = result.stderr.strip() or result.stdout.strip() or "(пустой вывод)"
        raise RuntimeError(f"claude -p exit {result.returncode}: {detail[-1500:]}")


def _collect_fnr_artifacts(clone_dir: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for name in ARTIFACT_FILES:
        path = Path(clone_dir) / FNR_DIR / name
        if path.exists():
            files[f"{FNR_DIR}/{name}"] = path.read_text(encoding="utf-8")
    return files


def _build_summary(analyze: AnalyzeInput, branch: str, files: dict[str, str]) -> str:
    base = f"https://github.com/{analyze.repo}/blob/{branch}"
    links = "\n".join(f"- [`{path.rsplit('/', 1)[-1]}`]({base}/{path})" for path in sorted(files))
    return (
        "## 🤖 Автономный анализ (SA-helper)\n\n"
        f"Прогнал полную цепочку FNR по этой задаче. Артефакты — в ветке `{branch}`:\n\n"
        f"{links}\n\n"
        "Начни с `system_requirements.md` — это ответ на вопрос «как реализовать эту "
        "задачу»: разбор текущего поведения на код-доказательствах, план миграции с "
        "откатами, задачи с критериями приёмки и риски с митигацией.\n\n"
        "Повторить анализ — командой `/analyze`."
    )


async def _run_with_heartbeat(fn, *args, label: str):
    """Гоняет блокирующий fn в потоке и шлёт heartbeat каждые
    HEARTBEAT_INTERVAL_SEC, пока он не завершится.

    Heartbeat только между стадиями недостаточен: одна стадия claude -p идёт
    до CLAUDE_STAGE_TIMEOUT_SEC (900с), а heartbeat_timeout воркфлоу — 300с;
    без периодического сигнала внутри стадии сервер счёл бы activity мёртвой и
    (при maximum_attempts=1) уронил бы весь прогон. to_thread освобождает event
    loop, но сам по себе не бьёт — поэтому бьём здесь, пока поток занят.
    """
    task = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    while True:
        done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_INTERVAL_SEC)
        if task in done:
            return task.result()  # переброс исключения из потока, если было
        activity.heartbeat(label)


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …[обрезано]"


def _fetch_comment_blocks(analyze: AnalyzeInput) -> list[str]:
    """Свежие комментарии обсуждения (старые→свежие) без командного шума.

    Командные комментарии (`/analyze`, `/estimate` и с хвостом) отсекаются
    через parse_command — тот же разбор, что и в вебхуке. Сбой fetch ИЛИ
    разбора ответа (неожиданная форма payload) → пустой список: анализ
    продолжается на title+body. Фильтрация и сборка блоков нарочно внутри
    того же try, что и сам fetch — некорректный элемент payload не должен
    пробрасывать исключение мимо этого хелпера.
    """
    try:
        comments = github_client.list_comments(
            analyze.repo, analyze.issue_number, limit=50
        )
        kept = [c for c in comments if parse_command(c.get("body") or "") is None]
        kept = kept[-CONTEXT_COMMENT_LIMIT:]
        blocks: list[str] = []
        for c in kept:
            user = (c.get("user") or {}).get("login", "?")
            date = (c.get("created_at") or "")[:10]
            body = _truncate(c.get("body") or "", CONTEXT_COMMENT_CHARS)
            blocks.append(f"**@{user} ({date}):**\n{body}")
        return blocks
    except Exception as exc:  # noqa: BLE001 — деградация важнее причины сбоя
        logger.warning("list_comments failed for #%s: %s", analyze.issue_number, exc)
        return []


def _fetch_prs_section(analyze: AnalyzeInput) -> str:
    """Секция связанных PR. Сбой fetch → пустая строка (прогон не падает)."""
    try:
        prs = github_client.list_linked_prs(
            analyze.repo, analyze.issue_number, limit=CONTEXT_PR_LIMIT
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_linked_prs failed for #%s: %s", analyze.issue_number, exc)
        return ""
    if not prs:
        return ""
    lines = ["## Связанные PR"]
    for pr in prs:
        lines.append(f"- #{pr['number']} {pr['title']} [{pr['state']}] {pr['url']}")
    return "\n".join(lines)


def _build_task_context(analyze: AnalyzeInput) -> str:
    """Обогащённый бриф задачи для /fnr-new-task.

    Живое состояние issue (обсуждение, связанные PR) поверх title+body: тело
    issue — статичный снимок, решения и прогресс живут в комментариях и PR.

    title+body — неприкосновенный пол, никогда не обрезается. Обогащение
    (PR-секция и комментарии) бюджетируется остатком CONTEXT_TOTAL_CHARS
    после title+body: PR-секция входит только целиком, если помещается —
    частично не режется; комментарии отбрасываются от самых старых к свежим,
    пока не влезут в то, что осталось от бюджета. Итог превышает
    CONTEXT_TOTAL_CHARS только тогда, когда сам title+body уже больше
    потолка — это принятый пол. Любой сбой fetch деградирует независимо.
    """
    base = f"# {analyze.title}\n\n{analyze.body}".strip()
    prs = _fetch_prs_section(analyze)
    blocks = _fetch_comment_blocks(analyze)

    budget = CONTEXT_TOTAL_CHARS - len(base)
    if budget <= 0:
        return base  # title+body уже на потолке или за ним — пол есть пол

    if prs and len(prs) + 2 <= budget:  # +2 — разделитель "\n\n" перед PR
        budget -= len(prs) + 2
    else:
        prs = ""

    while blocks:
        section = "## Обсуждение\n" + "\n\n".join(blocks)
        if len(section) + 2 <= budget:  # +2 — разделитель "\n\n" перед секцией
            break
        blocks = blocks[1:]  # выкинуть старейший комментарий
    comments = "## Обсуждение\n" + "\n\n".join(blocks) if blocks else ""

    parts = [base]
    if comments:
        parts.append(comments)
    if prs:
        parts.append(prs)
    return "\n\n".join(parts)


@activity.defn
async def prepare_workspace(analyze: AnalyzeInput) -> None:
    """Стадия 0 пайплайна /analyze: свежий clone + repomix в детерминированный
    каталог. Идемпотентна (сносит остаток и строит заново)."""
    await _run_with_heartbeat(_build_workspace, analyze, label="preparing")


@activity.defn
async def run_fnr_stage(analyze: AnalyzeInput, stage_name: str) -> dict:
    """Одна стадия FNR — отдельный `claude -p`. Guard рабочего каталога,
    затем стадия, затем проверка ожидаемого артефакта. Возвращает компактный
    отчёт {stage, artifact, bytes}; статус/тайминг Temporal фиксирует сам."""
    # Бриф с обсуждением и связанными PR нужен ровно стадии `task`: только её
    # промпт несёт описание задачи, остальные ссылаются на уже готовые артефакты.
    # Регрессия, из-за которой это место и появилось: при переходе на
    # пер-стадийные activity обогащение осталось в монолите, и `/analyze`
    # уезжал в модель с одними title+body — агент переоткрывал вопросы,
    # закрытые в комментариях.
    description = (
        await asyncio.to_thread(_build_task_context, analyze)
        if stage_name == "task"
        else f"{analyze.title}\n\n{analyze.body}"
    )
    prompt, expected, requires = _fnr_stage(stage_name, description)
    clone_dir = _require_workspace(analyze, requires)
    await _run_with_heartbeat(_run_claude, prompt, clone_dir, label=stage_name)
    artifact: str | None = None
    size = 0
    if expected:
        path = Path(clone_dir) / expected
        if not path.exists():
            raise RuntimeError(f"стадия {stage_name}: артефакт {expected} не создан")
        artifact = expected
        size = path.stat().st_size
    return {"stage": stage_name, "artifact": artifact, "bytes": size}


@activity.defn
async def publish_analysis(analyze: AnalyzeInput) -> str:
    """Финал пайплайна: собрать артефакты, push ветки research/issue-N,
    итоговый коммент. Мутации GitHub гейтятся DRY_RUN внутри github_client."""
    clone_dir = _require_workspace(analyze, None)
    files = await asyncio.to_thread(_collect_fnr_artifacts, clone_dir)
    if not files:
        raise RuntimeError("пайплайн не произвёл ни одного артефакта")
    branch = f"research/issue-{analyze.issue_number}"
    await asyncio.to_thread(
        github_client.push_artifacts_to_branch,
        analyze.repo, branch, files,
        f"docs(sa): анализ issue #{analyze.issue_number} через SA-helper",
    )
    await asyncio.to_thread(
        github_client.post_comment,
        analyze.repo, analyze.issue_number, _build_summary(analyze, branch, files),
    )
    return branch


@activity.defn
async def cleanup_workspace(analyze: AnalyzeInput) -> None:
    """Best-effort снос рабочего каталога прогона."""
    await asyncio.to_thread(shutil.rmtree, str(_workspace_dir(analyze)), ignore_errors=True)


# --- Тяжёлые стадии: TODO, те же незакрытые вопросы, что были на Actions ---

@activity.defn
def run_bug_pipeline(issue: IssueInput) -> None:
    """TODO: перенести содержимое bug-pipeline.yml аналогично."""
    raise NotImplementedError("bug-pipeline: перенести шаги из старого bug-pipeline.yml")


@activity.defn
def trigger_openhands_resolver(issue: IssueInput) -> None:
    """Активность Develop: передать подготовленный Issue агенту разработки.

    Агент живёт в GitHub Actions репозитория-цели (OpenHands Resolver) — своё
    окружение, свой sandboxing, свой релизный цикл; в этот compose он не
    втаскивается. Граница между ним и циклом описана в `shared/develop.py`.

    Порядок здесь не косметический. Сначала диспатч: он единственный может не
    состояться (нет файла workflow, выключены Actions), и тогда ни метки, ни
    комментария о начале работы быть не должно — соврать про запуск хуже, чем
    не запустить. Метка и комментарий идут после и уже best-effort: прогон к
    этому моменту начался, и падать из-за не поставленной метки значило бы
    отправить в `failed` задачу, которая на самом деле в работе.
    """
    if not develop.enabled():
        raise RuntimeError(
            "DEVELOP_ENABLED выключен — задача остаётся в очереди к разработчику")

    branch = f"research/issue-{issue.issue_number}"
    if not github_client.branch_exists(issue.repo, branch):
        # Путь бага: аналитики не было, и ветки с артефактами тоже. Это штатно —
        # агент работает от тела Issue, но знать об этом он должен явно.
        branch = ""

    github_client.dispatch_workflow(
        issue.repo,
        develop.workflow_file(),
        develop.workflow_ref(),
        develop.dispatch_inputs(issue.issue_number, branch=branch),
    )

    for step, call in (
        ("метка", lambda: github_client.add_label(
            issue.repo, issue.issue_number, develop.IN_DEVELOPMENT_LABEL)),
        ("комментарий", lambda: github_client.post_comment(
            issue.repo, issue.issue_number,
            develop.handoff_comment(issue.issue_number, repo=issue.repo, branch=branch))),
    ):
        try:
            call()
        except Exception as exc:
            logger.warning("Develop %s#%s: %s не проставлен (%s) — прогон уже идёт",
                           issue.repo, issue.issue_number, step, exc)


# --- Слой C: аналитика по запросу (команда /analyze) ---

@activity.defn
async def ack_command(analyze: AnalyzeInput) -> None:
    """Видимое подтверждение приёма команды ДО тяжёлой работы.

    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не
    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;
    если комментарий-триггер к этому моменту удалили (404) или сработал
    rate limit, сбой реакции не должен утопить сам ack.

    Триггер виден по comment_id: он есть у команды в комментарии и пуст у
    запуска меткой — реагировать там не на что, и подтверждение называет
    метку, а не команду. Явно переданный `trigger` перекрывает эту догадку:
    аналитику запускает и цикл по метке `research-me`, и назвать её
    `run:analyze` значило бы указать человеку на метку, которой он не ставил.
    """
    trigger = (f"`{analyze.trigger}`" if analyze.trigger
               else f"`{run_label(ANALYZE)}`" if analyze.comment_id is None
               else "`/analyze`")
    await asyncio.to_thread(
        github_client.post_comment,
        analyze.repo,
        analyze.issue_number,
        f"🔍 Взял {trigger} в работу — запускаю автономный анализ через SA-helper.\n\n"
        "Прогон занимает несколько минут: артефакты появятся в ветке "
        f"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.",
    )
    await asyncio.to_thread(
        github_client.add_label, analyze.repo, analyze.issue_number, run_label(ANALYZE)
    )
    if analyze.comment_id is not None:
        try:
            await asyncio.to_thread(github_client.add_reaction, analyze.repo, analyze.comment_id, "eyes")
        except Exception:
            pass  # best-effort: декорация не должна ронять ack или весь прогон


@activity.defn
async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:
    """Не молчать при провале: прогон дорогой и долгий, тихое падение
    неотличимо от «ещё работает»."""
    await asyncio.to_thread(
        github_client.post_comment,
        analyze.repo,
        analyze.issue_number,
        f"⚠️ Автономный анализ не удался: {reason}\n\n"
        "Прогон не повторяется автоматически (он недетерминирован и дорог). "
        "Запустить заново — командой `/analyze`.",
    )


# --- Оценка трудоёмкости по команде /estimate ---

# Лимиты контекста: без них длинный тред или большой blueprint съедают
# окно модели целиком и вытесняют само описание задачи.
MAX_THREAD_COMMENTS = 50
MAX_THREAD_CHARS = 20_000
MAX_ARTIFACT_CHARS = 20_000
MAX_ARTIFACTS_TOTAL_CHARS = 60_000

# Пути артефактов из модели данных (docs/ARCHITECTURE.md). Отсутствующий
# файл — штатная ситуация: research-пайплайн мог не дойти до этой стадии.
ARTIFACT_PATHS = (
    "docs/bft/issue-{n}-blueprint.md",
    "docs/bft/issue-{n}-debate.md",
    "docs/bft/issue-{n}-recommendations.md",
    "docs/research/issue-{n}-sa-spec.md",
    "docs/bugs/issue-{n}-diagnosis.md",
)


@activity.defn
def ack_estimate_command(req: EstimateRequest) -> None:
    """Подтверждение приёма. У команды в комментарии это реакция на него; у
    запуска меткой реагировать не на что, поэтому подтверждением служит сама
    метка `run:estimate` плюс короткий комментарий — иначе с телефона не видно,
    что метка вообще доехала."""
    github_client.add_label(req.repo, req.issue_number, run_label(ESTIMATE))
    if req.comment_id is None:
        github_client.post_comment(
            req.repo, req.issue_number,
            f"🧮 Взял `{run_label(ESTIMATE)}` в работу — считаю трудоёмкость по методологии. "
            "Результат придёт следующим комментарием.",
        )
        return
    github_client.add_reaction(req.repo, req.comment_id, "eyes")


def _collect_thread(req: EstimateRequest) -> tuple[list[str], bool]:
    raw = github_client.list_comments(req.repo, req.issue_number, MAX_THREAD_COMMENTS)
    truncated = len(raw) >= MAX_THREAD_COMMENTS
    thread: list[str] = []
    used = 0
    for comment in raw:
        # Прошлые оценки постит сам сервис, значит они уже отсеяны как Bot —
        # иначе модель начала бы оценивать собственный предыдущий вывод.
        if comment.get("user", {}).get("type") == "Bot":
            continue
        body = (comment.get("body") or "").strip()
        if not body or parse_command(body):
            continue
        if used + len(body) > MAX_THREAD_CHARS:
            truncated = True
            break
        thread.append(body)
        used += len(body)
    return thread, truncated


def _collect_artifacts(req: EstimateRequest) -> tuple[str | None, dict[str, str], bool]:
    branch = None
    for prefix in ("research", "bug"):
        candidate = f"{prefix}/issue-{req.issue_number}"
        if github_client.branch_exists(req.repo, candidate):
            branch = candidate
            break
    if branch is None:
        return None, {}, False

    artifacts: dict[str, str] = {}
    truncated = False
    total = 0
    for template in ARTIFACT_PATHS:
        path = template.format(n=req.issue_number)
        content = github_client.get_file(req.repo, path, branch)
        if content is None:
            continue
        if len(content) > MAX_ARTIFACT_CHARS:
            content = content[:MAX_ARTIFACT_CHARS]
            truncated = True
        if total + len(content) > MAX_ARTIFACTS_TOTAL_CHARS:
            truncated = True
            break
        artifacts[path] = content
        total += len(content)
    return branch, artifacts, truncated


@activity.defn
def collect_estimation_context(req: EstimateRequest) -> EstimationContext:
    issue = github_client.get_issue(req.repo, req.issue_number)
    thread, thread_truncated = _collect_thread(req)
    branch, artifacts, artifacts_truncated = _collect_artifacts(req)
    return EstimationContext(
        title=issue.get("title") or "",
        body=issue.get("body") or "",
        labels=[label["name"] for label in issue.get("labels", [])],
        thread=thread,
        branch=branch,
        artifacts=artifacts,
        truncated=thread_truncated or artifacts_truncated,
    )


@activity.defn
def extract_estimation_facts(context: EstimationContext) -> dict:
    parts = [f"Заголовок: {context.title}", f"Описание:\n{context.body}"]
    if context.labels:
        parts.append("Лейблы: " + ", ".join(context.labels))
    if context.thread:
        parts.append("Обсуждение:\n" + "\n---\n".join(context.thread))
    for path, content in context.artifacts.items():
        parts.append(f"Артефакт {path}:\n{content}")

    facts = llm.extract(
        _load_prompt("system_estimate_extract.md"),
        "\n\n".join(parts),
        estimation.EstimationFacts,
        model=llm.MODEL_CLASSIFY,
    )
    # Между activity ездит dict: штатный JSON-конвертер Temporal знает
    # dataclass'ы, но не модели Pydantic. Схема при этом одна.
    return facts.model_dump()


@activity.defn
def compute_estimate(facts_payload: dict, context: EstimationContext) -> EstimateResult:
    facts = estimation.EstimationFacts.model_validate(facts_payload)
    estimate = estimation.compute(facts, estimation.load_rules())
    return EstimateResult(
        markdown=estimate_report.render(estimate, facts, context),
        stopped=estimate.stopped,
    )


@activity.defn
def post_estimate_comment(req: EstimateRequest, result: EstimateResult) -> None:
    github_client.post_comment(req.repo, req.issue_number, result.markdown)
    if not result.stopped:
        github_client.add_label(req.repo, req.issue_number, "estimated")


@activity.defn
def post_estimate_error(req: EstimateRequest, stage: str, reason: str = "") -> None:
    github_client.post_comment(
        req.repo,
        req.issue_number,
        f"⚠️ Оценка не удалась на стадии «{stage}». Повтори `/estimate` позже — "
        f"подробности прогона видны в Temporal UI.",
    )
    if req.comment_id is not None:
        github_client.add_reaction(req.repo, req.comment_id, "confused")
    exc_type, _, message = reason.partition(": ")
    sentry_setup.capture_estimate_failure(req, stage, exc_type or "unknown", message or reason)
