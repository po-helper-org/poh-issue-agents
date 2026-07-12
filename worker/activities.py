"""
Activities — вся содержательная логика, перенесённая из advisor/gate.py,
classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py
(версия на GitHub Actions). Изменился только транспорт: вместо чтения
GITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-
функции, вызываемые Temporal-воркером напрямую.
"""

import re
import subprocess
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import github_client
import llm
from shared.workflow_types import (
    ClassificationResult,
    DuplicateResult,
    GateResult,
    IssueInput,
    PriorityResult,
)

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
async def prefilter_bot_and_security(issue: IssueInput) -> str | None:
    """Возвращает причину пропуска, если стоит остановиться, иначе None."""
    if issue.author_type == "Bot":
        github_client.add_label(issue.repo, issue.issue_number, "bot-authored")
        return "bot"

    KNOWN_BOT_LOGINS = {"dependabot", "renovate", "snyk-bot", "github-actions"}
    if issue.author_login.lower().removesuffix("[bot]") in KNOWN_BOT_LOGINS:
        github_client.add_label(issue.repo, issue.issue_number, "bot-authored")
        return "bot"

    SECURITY_TERMS = ("vulnerability", "cve-", "exploit", "sql injection", "rce",
                       "уязвимост", "эксплойт", "утечка данных")
    text = f"{issue.title} {issue.body}".lower()
    if any(term in text for term in SECURITY_TERMS):
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
async def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult:
    thread_text = "\n\n".join(f"Пользователь: {c}" for c in comment_thread)
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}\n\n{thread_text}"
    result = llm.extract(
        _load_prompt("system_intake_gate.md"), user_message, GateExtraction, model=llm.MODEL_GATE,
    )
    return GateResult(status=result.status, content=result.content)


@activity.defn
async def post_clarifying_question(issue: IssueInput, questions: str) -> None:
    github_client.post_comment(issue.repo, issue.issue_number, questions)
    github_client.add_label(issue.repo, issue.issue_number, "needs-clarification")


@activity.defn
async def close_as_spam(issue: IssueInput, reason: str) -> None:
    github_client.post_comment(issue.repo, issue.issue_number, f"🚫 Похоже на спам: {reason}")
    github_client.add_label(issue.repo, issue.issue_number, "spam")
    github_client.close_issue(issue.repo, issue.issue_number)


@activity.defn
async def escalate_to_human(issue: IssueInput) -> None:
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "Не удалось сузить запрос за отведённое число уточнений. Передаю на ручной разбор.",
    )
    github_client.add_label(issue.repo, issue.issue_number, "needs-human-triage")


@activity.defn
async def post_error_label(issue: IssueInput) -> None:
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "⚠️ Автоматическая обработка не удалась. Ожидай ручного разбора.",
    )
    github_client.add_label(issue.repo, issue.issue_number, "advisor:error")


# --- Классификация ---

@activity.defn
async def classify_issue(issue: IssueInput) -> ClassificationResult:
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
async def duplicate_check(issue: IssueInput) -> DuplicateResult:
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
            f"🔁 Дубликат #{best.number} (вероятность {best.probability:.0%}): {best.reason}{reuse_note}",
        )
        github_client.add_label(issue.repo, issue.issue_number, "duplicate")
        github_client.close_issue(issue.repo, issue.issue_number)
        return DuplicateResult(decision="duplicate", best_match_number=best.number,
                                probability=best.probability, reason=best.reason, context_branch=branch)

    if best.probability >= 0.5:
        github_client.add_label(issue.repo, issue.issue_number, "possible-duplicate")
        return DuplicateResult(decision="possible", best_match_number=best.number,
                                probability=best.probability, reason=best.reason, context_branch=None)

    return DuplicateResult(decision="none", best_match_number=None, probability=0.0, reason="", context_branch=None)


# --- Priority Scoring ---

@activity.defn
async def score_priority(issue: IssueInput, classification: ClassificationResult, dup: DuplicateResult) -> PriorityResult:
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
async def post_priority_comment(issue: IssueInput, priority: PriorityResult, dup: DuplicateResult) -> None:
    body = priority.breakdown_markdown
    if dup.decision == "possible":
        body += (
            f"\n\n⚠️ Также похоже на возможный дубликат #{dup.best_match_number} "
            f"({dup.probability:.0%}) — стоит проверить перед запуском тяжёлой стадии."
        )
    github_client.post_comment(issue.repo, issue.issue_number, body)
    github_client.add_label(issue.repo, issue.issue_number, f"priority:{priority.tier}")


# --- Тяжёлые стадии: TODO, те же незакрытые вопросы, что были на Actions ---

@activity.defn
async def run_research_pipeline(issue: IssueInput) -> None:
    """TODO: перенести сюда содержимое research-pipeline.yml как
    последовательность subprocess-вызовов (claude -p с ANTHROPIC_BASE_URL=
    z.ai для po-helper/Repowise/SA-helper, deb8flow как CLI). Незакрытые
    вопросы те же, что были на Actions: механизм загрузки скиллов,
    точный синтаксис deb8flow, MCP-подключение Repowise к headless-среде.
    """
    raise NotImplementedError("research-pipeline: перенести шаги из старого research-pipeline.yml")


@activity.defn
async def run_bug_pipeline(issue: IssueInput) -> None:
    """TODO: перенести содержимое bug-pipeline.yml аналогично."""
    raise NotImplementedError("bug-pipeline: перенести шаги из старого bug-pipeline.yml")


@activity.defn
async def trigger_openhands_resolver(issue: IssueInput) -> None:
    """TODO: вызов OpenHands resolver — остаётся отдельным сервисом со
    своим sandboxing (docker.sock), не частью этого docker-compose."""
    raise NotImplementedError("OpenHands resolver — интеграция ещё не спроектирована")
