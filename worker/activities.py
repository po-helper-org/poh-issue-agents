"""
Activities — вся содержательная логика, перенесённая из advisor/gate.py,
classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py
(версия на GitHub Actions). Изменился только транспорт: вместо чтения
GITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-
функции, вызываемые Temporal-воркером напрямую.
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import github_client
import llm
from shared.workflow_types import (
    AnalyzeInput,
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


@activity.defn
async def mark_analyzing(repo: str, issue_number: int) -> None:
    """Видимая метка, что по Issue запущен автономный анализ (/analyze).
    add_label соблюдает DRY_RUN, отдельного гарда не нужно."""
    github_client.add_label(repo, issue_number, "analyzing")


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


# --- Пайплайн SA-helper (FNR) ---

FNR_DIR = "sa_documentation/FNR/FNR_1"
ARTIFACT_FILES = ("task.md", "concept.md", "system_requirements.md", "validation.md")
CLAUDE_STAGE_TIMEOUT_SEC = 900
REPOMIX_TIMEOUT_SEC = 600
CLONE_TIMEOUT_SEC = 300
HEARTBEAT_INTERVAL_SEC = 30.0


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
        "GH_CLONE_TOKEN": github_client.auth_token(),
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


def _run_claude(prompt: str, cwd: str) -> None:
    """Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.

    ANTHROPIC_* берутся из окружения контейнера (env_file .env) и направляют
    claude-code на Anthropic-совместимый эндпоинт z.ai.
    """
    result = subprocess.run(
        # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера
        # работает от root, а тот флаг под root запрещён самим claude-code
        # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).
        ["claude", "-p", prompt, "--permission-mode", "acceptEdits"],
        cwd=cwd, capture_output=True, text=True,
        timeout=CLAUDE_STAGE_TIMEOUT_SEC, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p exit {result.returncode}: {result.stderr[-1000:]}")


def _collect_artifacts(clone_dir: str) -> dict[str, str]:
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


@activity.defn
async def run_analysis_pipeline(analyze: AnalyzeInput) -> str:
    """Полный прогон SA-helper одной activity.

    Одна activity, а не пять: клон, упаковка и стадии делят рабочий каталог на
    локальном диске одного процесса — разбиение по activity потребовало бы
    общего тома. Heartbeat идёт ВНУТРИ каждой долгой стадии через
    _run_with_heartbeat, а не только между ними: одна стадия claude -p может
    занять до CLAUDE_STAGE_TIMEOUT_SEC (900с) при heartbeat_timeout воркфлоу в
    300с — без сигнала изнутри стадии сервер счёл бы activity мёртвой и (при
    maximum_attempts=1) уронил бы весь прогон (та же причина, по которой
    heartbeat вообще нужен — долгие стадии уже приводили к ложным срабатываниям
    детектора дедлоков, worker/worker.py:44-51).

    Каждый блокирующий вызов (git/repomix/claude/REST) идёт через
    asyncio.to_thread (напрямую или через _run_with_heartbeat): воркер крутит
    один event loop с max_concurrent_activities, и синхронный subprocess.run
    на 900с заблокировал бы поток целиком — другие issue встали бы, а
    activity.heartbeat не смог бы уйти на сервер (ему нужен тот же loop).
    Вынос в поток освобождает loop и делает heartbeat реальным.
    """
    workdir = tempfile.mkdtemp(prefix=f"analysis-{analyze.issue_number}-")
    clone_dir = str(Path(workdir) / "repo")
    try:
        await _run_with_heartbeat(_clone_repo, analyze.repo, clone_dir, label="cloning")
        activity.heartbeat("cloned")
        await _run_with_heartbeat(_run_repomix, clone_dir, label="packing")
        activity.heartbeat("packed")

        description = f"{analyze.title}\n\n{analyze.body}"
        for name, prompt, expected in _fnr_stages(description):
            await _run_with_heartbeat(_run_claude, prompt, clone_dir, label=name)
            if expected and not (Path(clone_dir) / expected).exists():
                raise RuntimeError(f"стадия {name}: артефакт {expected} не создан")
            activity.heartbeat(name)

        files = await asyncio.to_thread(_collect_artifacts, clone_dir)
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
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --- Тяжёлые стадии: TODO, те же незакрытые вопросы, что были на Actions ---

@activity.defn
async def run_bug_pipeline(issue: IssueInput) -> None:
    """TODO: перенести содержимое bug-pipeline.yml аналогично."""
    raise NotImplementedError("bug-pipeline: перенести шаги из старого bug-pipeline.yml")


@activity.defn
async def trigger_openhands_resolver(issue: IssueInput) -> None:
    """TODO: вызов OpenHands resolver — остаётся отдельным сервисом со
    своим sandboxing (docker.sock), не частью этого docker-compose."""
    raise NotImplementedError("OpenHands resolver — интеграция ещё не спроектирована")


# --- Слой C: аналитика по запросу (команда /analyze) ---

@activity.defn
async def ack_command(analyze: AnalyzeInput) -> None:
    """Видимое подтверждение приёма команды ДО тяжёлой работы.

    Комментарий — это и есть подтверждение, поэтому он идёт первым и ничем не
    гейтится. Реакция на комментарий-триггер — чисто декоративная добавка;
    если комментарий-триггер к этому моменту удалили (404) или сработал
    rate limit, сбой реакции не должен утопить сам ack.
    """
    github_client.post_comment(
        analyze.repo,
        analyze.issue_number,
        "🔍 Взял `/analyze` в работу — запускаю автономный анализ через SA-helper.\n\n"
        "Прогон занимает несколько минут: артефакты появятся в ветке "
        f"`research/issue-{analyze.issue_number}`, а сводка — следующим комментарием.",
    )
    if analyze.comment_id is not None:
        try:
            github_client.add_reaction(analyze.repo, analyze.comment_id, "eyes")
        except Exception:
            pass  # best-effort: декорация не должна ронять ack или весь прогон


@activity.defn
async def publish_analysis_error(analyze: AnalyzeInput, reason: str) -> None:
    """Не молчать при провале: прогон дорогой и долгий, тихое падение
    неотличимо от «ещё работает»."""
    github_client.post_comment(
        analyze.repo,
        analyze.issue_number,
        f"⚠️ Автономный анализ не удался: {reason}\n\n"
        "Прогон не повторяется автоматически (он недетерминирован и дорог). "
        "Запустить заново — командой `/analyze`.",
    )
