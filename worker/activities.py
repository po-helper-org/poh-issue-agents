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
from shared import bft, decomposition, develop, labels, lifecycle, pr_closing, sentry_setup
from shared.awaiting import Awaiting
from shared.commands import (
    ANALYZE,
    BFT,
    BFT_DEEP,
    ESTIMATE,
    done_label,
    failed_label,
    parse_command,
    run_label,
    running_labels,
)
from shared.workflow_types import (
    AnalyzeInput,
    BftRequest,
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

    def _flag(name: str) -> bool:
        return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def _flag_on_by_default(name: str) -> bool:
        raw = os.environ.get(name, "").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    return Deadlines(
        human_decision_hours=_hours("PARK_DECISION_HOURS", 72),
        clarification_hours=_hours("PARK_CLARIFICATION_HOURS", 48),
        build_decision_hours=_hours("PARK_BUILD_HOURS", 72),
        side_state_hours=_hours("PARK_SIDE_STATE_HOURS", 168),
        develop_autostart=_flag("DEVELOP_AUTOSTART"),
        research_autostart=_flag("RESEARCH_AUTOSTART"),
        decompose_enabled=decomposition.enabled(),
        pr_fix_enabled=pr_closing.enabled(),
        pr_fix_max_rounds=pr_closing.max_rounds(),
        # Включён по умолчанию: БФТ на триаже — это НОВЫЙ формат ответа вместо
        # прежнего свободного, а не дополнительная стадия. Тумблер существует
        # ради возможности откатиться, поэтому и читается наоборот — выключение
        # требует явного BFT_ON_TRIAGE=0.
        bft_on_triage=_flag_on_by_default("BFT_ON_TRIAGE"),
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
    outcome = done_label(command) if ok else failed_label(command)
    # Исход ПРЕДЫДУЩЕГО прогона снимается вместе с «идёт»: `done:analyze` рядом
    # с `failed:analyze` — противоречие, а не история. По такой паре нельзя
    # сказать, чем кончился последний прогон, и выборка `label:failed:*`
    # показывает задачи, которые давно починены повторным запуском.
    previous = failed_label(command) if ok else done_label(command)
    for stale in (*running_labels(command), previous):
        try:
            await asyncio.to_thread(github_client.remove_label, repo, issue_number, stale)
        except Exception as exc:
            logger.warning("не снял метку %s с %s#%s: %s", stale, repo, issue_number, exc)
    try:
        await asyncio.to_thread(github_client.add_label, repo, issue_number, outcome)
    except Exception as exc:
        logger.warning("не поставил метку %s на %s#%s: %s", outcome, repo, issue_number, exc)


# --- Классификация ---

@activity.defn
def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:
    """Тип запроса плюс ответ advisor комментарием.

    `bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:
    на него отвечает БФТ, и два комментария подряд означали бы, что первый
    неактуален уже в момент публикации. Для бага, консультации и «уже
    реализовано» ответ публикуется как прежде — БФТ по ним не собирается, и
    молчание оставило бы Issue вообще без содержательного комментария.

    Решение принимается ЗДЕСЬ, а не отдельной активностью публикации, потому что
    зависит от категории — а категорию знает только эта активность. Развести их
    значило бы гонять текст ответа через воркфлоу ради условия, которое здесь
    уже вычислено.

    Аргумент со значением по умолчанию, а не новая activity: прогоны прежнего
    поколения зовут её одним аргументом и обязаны получить прежнее поведение.
    """
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
    if not (bft_on_triage and label == "advisor:feature-request"):
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
def score_priority(issue: IssueInput, classification: ClassificationResult | None,
                   dup: DuplicateResult) -> PriorityResult:
    """Приоритет по формуле. Классификации может не быть — и это штатно.

    Сокращённый триаж (Issue с `origin:agent`, правило R6) классификацию
    пропускает: задачу уже классифицировал тот агент, который её завёл. Приоритет
    ему всё равно нужен — по нему follow-up встаёт в очередь наравне с
    остальными, — поэтому отсутствие типа здесь не сбой, а вход.
    """
    kind = classification.label if classification is not None else "не указан (Issue заведён агентом)"
    user_message = f"Заголовок: {issue.title}\n\nОписание:\n{issue.body}\n\nТип: {kind}"
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


def _clone_repo(repo: str, dest: str, branch: str | None = None) -> None:
    """Shallow-клон целевого репозитория: артефакты FNR обязаны опираться на
    реальный код (`файл:строка`), одного текста Issue недостаточно.

    `branch` — ветка, которую надо получить вместо дефолтной. Нужна повторному
    прогону БФТ: он дорабатывает уже лежащий там документ, а не пишет второй
    рядом. Вызывающий обязан убедиться, что ветка существует, — клон
    несуществующей ветки падает, и падать он должен на понятной проверке, а не
    внутри git.

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
    args = ["git", "clone", "--depth", "1"]
    if branch:
        args += ["--branch", branch]
    subprocess.run(
        [*args, url, dest],
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


DEV_CLONE_TIMEOUT_SEC = 300
DEV_TESTS_TIMEOUT_SEC = 900


def _dev_paths(issue: IssueInput) -> tuple[Path, Path]:
    """Каталог задачи в общем томе и клон внутри него.

    Том общий с раннером и смонтирован в обоих контейнерах по одному пути:
    воркер готовит каталог и читает результат, раннер пишет. Через bind-mount
    так не сделать — путь внутри воркера на хосте не существует.
    """
    root = Path(develop.workspace_mount()) / develop.task_slug(issue.repo, issue.issue_number)
    return root, root / "repo"


def _dev_prepare(issue: IssueInput, branch: str) -> str:
    """Свежий клон + постановка файлом. Возвращает текст постановки.

    Постановка собирается ЗДЕСЬ, а не в промпте агента: то, что уехало в
    работу, должно быть видно дословно. Иначе на разборе «почему агент сделал
    не то» предъявить нечего.
    """
    root, clone_dir = _dev_paths(issue)
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    _clone_repo(issue.repo, str(clone_dir))

    parts = [f"# Задача: реализовать Issue #{issue.issue_number}",
             "", f"## {issue.title}", "", issue.body or "(тело пустое)", ""]

    if branch:
        # Требования идут ПЕРВЫМИ: то, что агент прочитает раньше, весит
        # больше, а task/concept — путь к требованиям, а не сами требования.
        parts.append("## Системные требования (аналитика Issue-Agent)")
        parts.append("")
        for name in ("system_requirements.md", "task.md", "concept.md"):
            text = github_client.get_file(issue.repo, f"{FNR_DIR}/{name}", branch)
            if text:
                parts += [f"### {name}", "", text, ""]
    else:
        parts += ["## Аналитики по задаче нет — работай от тела Issue.", ""]

    rules = (clone_dir / ".openhands" / "task-rules.md")
    parts.append(rules.read_text(encoding="utf-8") if rules.exists() else _DEV_FALLBACK_RULES)

    task = "\n".join(parts)
    (clone_dir / ".task.md").write_text(task, encoding="utf-8")
    return task


_DEV_FALLBACK_RULES = """## Как работать

Правила репозитория — в `AGENTS.md` и `CLAUDE.md`, они обязательны.

1. **MVP первым.** Кратчайший путь к тому, что просят. Не углубляйся в
   надёжность и редкие ветки, пока основное не работает.
2. **Edge-кейс — не в эту ветку.** Найденное по дороге заводи отдельным
   SubIssue и продолжай MVP.
3. **Тесты.** Прогоняй проверки проекта; красный прогон в PR не отдаём.
4. **Коммитить самому не надо** — коммит, пуш и PR делает контур после тебя.
"""


def _dev_run_agent(issue: IssueInput) -> str:
    """Прогон одноразового контейнера. Возвращает хвост вывода."""
    command = develop.runner_command(
        develop.task_slug(issue.repo, issue.issue_number),
        image=develop.runner_image(),
        volume=develop.workspace_volume(),
        mount=develop.workspace_mount(),
    )
    env = {**os.environ, **develop.runner_env(
        os.environ.get("ZAI_API_KEY", ""),
        os.environ.get("ZAI_BASE_URL", ""),
        os.environ.get("DEVELOP_MODEL", "").strip() or "openai/glm-4.6",
    )}
    result = subprocess.run(command, env=env, capture_output=True, text=True,
                            timeout=develop.run_timeout())
    tail = (result.stdout or "")[-4000:] + (result.stderr or "")[-2000:]
    if result.returncode != 0:
        raise RuntimeError(
            f"прогон агента разработки завершился с кодом {result.returncode}: "
            f"{tail[-1500:]}")
    return tail


def _dev_tests(issue: IssueInput) -> str:
    """Прогон проверок проекта. Пусто в конфиге — шаг пропускается.

    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от
    агента CI может и не запуститься (события от токена Actions не порождают
    прогонов).
    """
    command = os.environ.get("DEVELOP_TEST_COMMAND", "").strip()
    if not command:
        return "(проверки не заданы — DEVELOP_TEST_COMMAND пуст)"
    _, clone_dir = _dev_paths(issue)
    result = subprocess.run(command, shell=True, cwd=str(clone_dir),
                            capture_output=True, text=True, timeout=DEV_TESTS_TIMEOUT_SEC)
    out = ((result.stdout or "") + (result.stderr or ""))[-3000:]
    if result.returncode != 0:
        raise RuntimeError(f"проверки не прошли (код {result.returncode}):\n{out[-1500:]}")
    return out


def _dev_publish(issue: IssueInput, branch: str) -> int | None:
    """Коммит, пуш и PR — руками воркера, его токеном.

    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен
    контуру. Возвращает номер PR либо None, если агент ничего не изменил.
    """
    _, clone_dir = _dev_paths(issue)
    work = develop.work_branch(issue.issue_number)
    return github_client.publish_worktree(
        issue.repo, str(clone_dir), work,
        title=f"feat(#{issue.issue_number}): {issue.title}",
        body=develop.pr_body(issue.issue_number, branch=branch),
        message=f"feat(#{issue.issue_number}): реализация по системным требованиям",
    )


@activity.defn
async def trigger_openhands_resolver(issue: IssueInput) -> int | None:
    """Активность Develop: разработка по подготовленному Issue.

    Два режима (`shared/develop.py`). `local` — прогон одноразовым контейнером
    на своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает
    в GitHub Actions, для репозиториев без стенда.

    Возвращает номер PR (режим `local`) либо None (`dispatch`: результат
    придёт событием `pr-open`, прогон идёт на чужой стороне).
    """
    if not develop.enabled():
        raise RuntimeError(
            "DEVELOP_ENABLED выключен — задача остаётся в очереди к разработчику")

    branch = f"research/issue-{issue.issue_number}"
    if not await asyncio.to_thread(github_client.branch_exists, issue.repo, branch):
        # Путь бага: аналитики не было, и ветки с артефактами тоже. Штатно —
        # агент работает от тела Issue, но знать об этом должен явно.
        branch = ""

    if develop.mode() == develop.DISPATCH:
        await asyncio.to_thread(
            github_client.dispatch_workflow,
            issue.repo, develop.workflow_file(), develop.workflow_ref(),
            develop.dispatch_inputs(issue.issue_number, branch=branch),
        )
        await _dev_announce(issue, branch, where="запустил OpenHands Resolver в GitHub Actions")
        return None

    # Порядок не косметический: сначала клон и постановка — они единственные
    # могут не состояться до того, как что-либо сказано человеку.
    task = await _run_with_heartbeat(_dev_prepare, issue, branch, label="dev:prepare")
    logger.info("Develop %s#%s: постановка (%d симв.)\n%s",
                issue.repo, issue.issue_number, len(task), task[:2000])
    await _dev_announce(issue, branch, where="запустил OpenHands на своём сервере")

    await _run_with_heartbeat(_dev_run_agent, issue, label="dev:agent")
    await _run_with_heartbeat(_dev_tests, issue, label="dev:tests")
    number = await _run_with_heartbeat(_dev_publish, issue, branch, label="dev:publish")

    if number is None:
        raise RuntimeError("агент не изменил ни одного файла — открывать нечего")
    return number


async def _dev_announce(issue: IssueInput, branch: str, *, where: str) -> None:
    """Метка и комментарий о начале работы — best-effort.

    Прогон к этому моменту начался; падать из-за непоставленной метки значило
    бы отправить в `failed` задачу, которая на самом деле в работе.
    """
    for step, call in (
        ("метка", lambda: github_client.add_label(
            issue.repo, issue.issue_number, develop.IN_DEVELOPMENT_LABEL)),
        ("комментарий", lambda: github_client.post_comment(
            issue.repo, issue.issue_number,
            develop.handoff_comment(issue.issue_number, repo=issue.repo,
                                    branch=branch, where=where))),
    ):
        try:
            await asyncio.to_thread(call)
        except Exception as exc:
            logger.warning("Develop %s#%s: %s не проставлен (%s) — прогон уже идёт",
                           issue.repo, issue.issue_number, step, exc)


# --- Декомпозиция задачи на подзадачи и релизы ---

class DecomposedItem(BaseModel):
    title: str
    body_markdown: str = ""
    release: str = Field(description="mvp | grow | support")
    depends_on: list[int] = []
    rationale: str = ""


class DecompositionExtraction(BaseModel):
    summary: str
    items: list[DecomposedItem]


@activity.defn
def decompose_issue(issue: IssueInput, branch: str) -> dict:
    """Разбор задачи на подзадачи с раскладкой по релизам.

    Требования читаются из ветки аналитики: разбивать по одному телу Issue —
    значит делить намерение, а не работу. Если аналитики не было, разбор идёт
    от тела, и это честнее, чем притворяться, будто требования есть.
    """
    context = [f"Заголовок: {issue.title}", "", "Описание:", issue.body or "(пусто)"]
    if branch:
        for name in ("system_requirements.md", "concept.md"):
            text = github_client.get_file(issue.repo, f"{FNR_DIR}/{name}", branch)
            if text:
                context += ["", f"--- {name} ---", text]

    result = llm.extract(
        _load_prompt("system_decompose_issue.md"),
        "\n".join(context)[:60000],
        DecompositionExtraction,
        model=llm.MODEL_CLASSIFY,
    )
    items = decomposition.validate([i.model_dump() for i in result.items])
    return {"summary": result.summary, "items": items}


@activity.defn
def publish_decomposition(issue: IssueInput, plan: dict, branch: str) -> list[int]:
    """Создаёт подзадачи и публикует план в родителе.

    Порядок важен: сначала все подзадачи, потом сводка. Сводка ссылается на
    номера, которых до создания не существует, а план с битыми ссылками хуже
    отсутствующего — по нему пойдут и упрутся.

    Зависимости проставляются вторым проходом по той же причине: подзадача
    может зависеть от той, что создаётся позже.
    """
    items = plan["items"]
    numbers: dict[int, int] = {}

    for index, item in enumerate(items):
        number = github_client.create_issue(
            issue.repo, item["title"],
            decomposition.subissue_body(item, parent=issue.issue_number,
                                        numbers=numbers, index=index),
            labels=[labels.ORIGIN_AGENT, decomposition.release_label(item["release"])],
        )
        numbers[index] = number

    # Второй проход: тела с зависимостями, которые теперь известны номерами.
    for index, item in enumerate(items):
        if not item["depends_on"]:
            continue
        try:
            github_client.update_issue_body(
                issue.repo, numbers[index],
                decomposition.subissue_body(item, parent=issue.issue_number,
                                            numbers=numbers, index=index))
        except Exception as exc:
            logger.warning("не дописал зависимости в #%s: %s", numbers[index], exc)

    github_client.post_comment(
        issue.repo, issue.issue_number,
        decomposition.parent_summary(items, numbers, summary=plan.get("summary", ""),
                                     branch=branch))
    return [numbers[i] for i in sorted(numbers)]


# --- Доведение PR по замечаниям ревью (H3→H4) ---

def _prfix_paths(repo: str, pr_number: int) -> tuple[Path, Path]:
    root = Path(develop.workspace_mount()) / pr_closing.task_slug(repo, pr_number)
    return root, root / "repo"


def _prfix_prepare(repo: str, pr_number: int, branch: str, task: str) -> None:
    """Свежий клон ВЕТКИ PR + постановка круга файлом.

    Клонируется именно ветка PR, а не основная: правки ложатся поверх того, что
    ревьюер видел, иначе круг переписывал бы чужую работу.
    """
    root, clone_dir = _prfix_paths(repo, pr_number)
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    _clone_repo(repo, str(clone_dir), branch=branch)
    (clone_dir / ".task.md").write_text(task, encoding="utf-8")


@activity.defn
async def run_pr_fix_round(repo: str, pr_number: int, round_number: int):
    """Один круг правок.

    `True` — правки внесены и запрошена перепроверка. Строка (возможно пустая) —
    правок не потребовалось, и это её разбор: агент не нашёл в ревью того, что
    требует изменений в коде. Законный исход, а не сбой; на нём круг и
    останавливается.

    Разные типы возврата намеренно: «сделали» и «не потребовалось» — разные
    исходы, и сводить их к булеву значению значило бы потерять объяснение,
    ради которого разбор и заводился.
    """
    pr = await asyncio.to_thread(github_client.get_pull, repo, pr_number)
    branch = pr["head"]["ref"]
    review = await asyncio.to_thread(github_client.review_text, repo, pr_number)
    task = pr_closing.build_task(pr_number, review=review, round_number=round_number,
                                 max_rounds_=pr_closing.max_rounds())

    await _run_with_heartbeat(_prfix_prepare, repo, pr_number, branch, task,
                              label="prfix:prepare")

    command = develop.runner_command(
        pr_closing.task_slug(repo, pr_number), image=develop.runner_image(),
        volume=develop.workspace_volume(), mount=develop.workspace_mount())
    env = {**os.environ, **develop.runner_env(
        os.environ.get("ZAI_API_KEY", ""), os.environ.get("ZAI_BASE_URL", ""),
        os.environ.get("DEVELOP_MODEL", "").strip() or "openai/glm-4.6")}

    def _run() -> None:
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=develop.run_timeout())
        if result.returncode != 0:
            tail = ((result.stdout or "") + (result.stderr or ""))[-1500:]
            raise RuntimeError(f"круг правок сорвался (код {result.returncode}): {tail}")

    await _run_with_heartbeat(_run, label="prfix:agent")

    _, clone_dir = _prfix_paths(repo, pr_number)
    verdict_path = clone_dir / pr_closing.VERDICT_FILE
    verdict = verdict_path.read_text(encoding="utf-8") if verdict_path.exists() else ""
    # Разбор не должен уехать в коммит: он живёт в комментарии PR, а не в коде.
    verdict_path.unlink(missing_ok=True)

    pushed = await _run_with_heartbeat(
        github_client.push_fixes, repo, str(clone_dir), branch,
        f"fix(#{pr_number}): правки по замечаниям ревью (круг {round_number})",
        label="prfix:push")
    if not pushed:
        return verdict or ""

    await asyncio.to_thread(
        github_client.post_comment, repo, pr_number,
        pr_closing.round_comment(pr_number, round_number=round_number,
                                 max_rounds_=pr_closing.max_rounds(), verdict=verdict))
    return True


@activity.defn
async def finish_pr_fixing(repo: str, pr_number: int, rounds: int, settled: bool,
                           verdict: str = "") -> None:
    """Итог доведения: либо PR готов, либо он уходит человеку."""
    if settled:
        await asyncio.to_thread(github_client.post_comment, repo, pr_number,
                                pr_closing.settled_comment(rounds, verdict))
        return
    await asyncio.to_thread(github_client.post_comment, repo, pr_number,
                            pr_closing.exhausted_comment(pr_closing.max_rounds()))
    await asyncio.to_thread(github_client.add_label, repo, pr_number,
                            pr_closing.NEEDS_HUMAN_PR)


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


# --- БФТ: быстрый проход (/bft) и глубокая проработка (/bft-deep) ---

# Полный тред уезжает в модель намеренно (постановка задачи: «когда речь идёт о
# БФТ, в ИИ-агента должен уходить полный контекст всей переписки Issue»).
# Потолки всё равно нужны — окно модели конечно, а тред активного Issue растёт
# без ограничений, — но они на порядок шире, чем у брифа `/analyze`.
BFT_THREAD_COMMENTS = 60
BFT_COMMENT_CHARS = 4000
BFT_THREAD_CHARS = 40_000

BFT_STAGE_TIMEOUT_SEC = 900

# Заголовок письма — он же признак прежней редакции. Считать редакции по метке
# нельзя: метка снимается, а комментарии остаются, и именно они образуют историю
# переработок, которую человек видит в треде.
BFT_LETTER_HEADING = "## 📋 БФТ (быстрый проход)"


class BftRequirementExtraction(BaseModel):
    id: str = Field(description="БТ-1 | ПТ-1 | ИТ-1 | ФТ-1 | НФТ-1, без ведущих нулей")
    as_is: str = Field(description="как сейчас; не озвучено — [ASIS не озвучен]")
    to_be: str = Field(description="как должно стать")
    related: str = Field(default="", description="ID связанных требований или пусто")
    source: str = Field(description="дословная цитата из Issue или комментария")


class BftPersonaExtraction(BaseModel):
    name: str
    role: str = Field(default="[роль не подтверждена]")
    unit: str = Field(default="[не указано]")


class BftLetterExtraction(BaseModel):
    goal: str = Field(description="1-2 предложения, WHY вперёд")
    how_to_demo: list[str] = Field(default_factory=list, description="шаги E2E-приёмки")
    open_questions: list[str] = Field(default_factory=list,
                                      description="вопрос/блокер/решение, владелец в скобках")
    scope: str = Field(default="", description="in-scope (out-of-scope — не входит в зону БФТ)")
    documentation: list[str] = Field(default_factory=list)
    requirements: list[BftRequirementExtraction] = Field(default_factory=list)
    personas: list[BftPersonaExtraction] = Field(default_factory=list)


def _bft_thread(req: BftRequest) -> tuple[str, int]:
    """Вся переписка Issue текстом плюс число прежних редакций БФТ.

    В отличие от брифа `/analyze`, комментарии сервиса НЕ отсеиваются: прошлая
    редакция БФТ и есть то, что человек правит командой `/bft`, и без неё
    замечание «во втором пункте не так» повисает в воздухе. По той же причине
    остаются и командные комментарии — в них лежат сами уточнения.

    Сбой чтения не роняет прогон: БФТ соберётся по заголовку и телу Issue, и это
    честнее, чем не собраться вовсе.
    """
    try:
        comments = github_client.list_comments(
            req.repo, req.issue_number, limit=BFT_THREAD_COMMENTS
        )
    except Exception as exc:  # noqa: BLE001 — деградация важнее причины сбоя
        logger.warning("list_comments failed for bft #%s: %s", req.issue_number, exc)
        return "", 1

    revision = 1
    blocks: list[str] = []
    for comment in comments:
        body = comment.get("body") or ""
        if BFT_LETTER_HEADING in body:
            revision += 1
        user = (comment.get("user") or {}).get("login", "?")
        date = (comment.get("created_at") or "")[:10]
        blocks.append(f"**@{user} ({date}):**\n{_truncate(body, BFT_COMMENT_CHARS)}")

    # Обрезаем от САМЫХ СТАРЫХ: свежие реплики — это и есть правки, ради которых
    # прогон запущен, и терять их, сохраняя первый комментарий полугодовой
    # давности, было бы ровно наоборот.
    while blocks and len("\n\n".join(blocks)) > BFT_THREAD_CHARS:
        blocks = blocks[1:]
    return "\n\n".join(blocks), revision


def _bft_user_message(req: BftRequest, thread: str) -> str:
    parts = [f"# Issue {req.repo}#{req.issue_number}: {req.title}", "",
             "## Описание", "", req.body.strip() or "(тело пустое)"]
    if req.instructions.strip():
        parts += ["", "## Замечания и уточнения к этой редакции", "",
                  "> Правки человека к БФТ. Сильнее и текста Issue, и прежней "
                  "редакции: человек уточняет собственный запрос.", "",
                  req.instructions.strip()]
    if thread:
        parts += ["", "## Вся переписка Issue", "", thread]
    return "\n".join(parts)


@activity.defn
async def ack_bft_command(req: BftRequest) -> None:
    """Видимое подтверждение приёма БФТ-команды ДО работы.

    Реакция «глаза» на комментарий-триггер — та же механика, что у `/analyze`, и
    по той же причине best-effort: комментарий могли удалить, а rate limit никто
    не отменял, и декорация не должна ронять приём команды.

    Комментарий пишется только для глубокого прогона и запуска меткой: быстрый
    проход по команде отвечает письмом через считанные секунды, и «взял в работу»
    прямо перед ним было бы шумом.

    Метку `run:*` вешает на себя ТОЛЬКО глубокий прогон. Метка возвращается
    вебхуком как событие `issues.labeled`, то есть как новая команда, — и на
    многоминутном прогоне это безобидно (второй старт упирается в занятый id),
    а на быстром, длящемся секунды, эхо успело бы прилететь уже после
    завершения и запустить второй прогон с дублирующим комментарием. Для
    быстрого прохода подтверждением служит реакция на комментарий-триггер.
    """
    command = BFT_DEEP if req.mode == bft.DEEP else BFT
    if req.mode == bft.DEEP:
        await asyncio.to_thread(
            github_client.add_label, req.repo, req.issue_number, run_label(command)
        )
        trigger = f"`/{command}`" if req.comment_id is not None else f"`{run_label(command)}`"
        await asyncio.to_thread(
            github_client.post_comment, req.repo, req.issue_number,
            f"📚 Взял {trigger} в работу — собираю полный БФТ по канону bft-writer.\n\n"
            "Прогон занимает несколько минут: артефакты появятся в ветке "
            f"`{bft.branch(req.issue_number)}`, а сводка — следующим комментарием.",
        )
    elif req.comment_id is None:
        await asyncio.to_thread(
            github_client.post_comment, req.repo, req.issue_number,
            f"📋 Взял `{run_label(command)}` в работу — пересобираю БФТ быстрого прохода.",
        )
    if req.comment_id is not None:
        try:
            await asyncio.to_thread(
                github_client.add_reaction, req.repo, req.comment_id, "eyes")
        except Exception:
            pass  # best-effort: декорация не должна ронять ack или весь прогон


@activity.defn
async def run_bft_fast(req: BftRequest) -> str:
    """Быстрый проход: письмо БФТ комментарием в Issue.

    Один вызов модели, без клона и без claude-code: формат `/bft-fast` — это
    структурирование уже сказанного, а не исследование кода. Клонировать
    репозиторий ради него значило бы платить минутами за то, что нужно секундами.

    Возвращает опубликованный текст — он же уходит в историю Temporal, поэтому
    разбор «что именно агент отписал» не требует лезть в GitHub.
    """
    thread, revision = await asyncio.to_thread(_bft_thread, req)
    letter = await asyncio.to_thread(
        llm.extract,
        _load_prompt("system_bft_fast.md"),
        _bft_user_message(req, thread),
        BftLetterExtraction,
        llm.MODEL_CLASSIFY,
    )
    body = bft.render_letter(
        goal=letter.goal,
        how_to_demo=letter.how_to_demo,
        open_questions=letter.open_questions,
        scope=letter.scope,
        documentation=letter.documentation,
        requirements=[r.model_dump() for r in letter.requirements],
        personas=[p.model_dump() for p in letter.personas],
        revision=revision,
    )
    await asyncio.to_thread(
        github_client.post_comment, req.repo, req.issue_number, body)
    return body


def _bft_workspace_dir(req: BftRequest) -> Path:
    """Каталог глубокого прогона. Отдельный от каталога `/analyze`: команды
    могут идти одновременно, и общий каталог означал бы, что подготовка одной
    сносит рабочее дерево другой посреди стадии."""
    root = os.environ.get("ANALYSIS_WORKSPACE_ROOT") or tempfile.gettempdir()
    slug = f"bft-{req.repo.replace('/', '__')}-{req.issue_number}"
    return Path(root) / slug


def _bft_clone_dir(req: BftRequest) -> str:
    return str(_bft_workspace_dir(req) / "repo")


def _build_bft_workspace(req: BftRequest) -> str:
    """Клон + repomix + постановка файлом.

    Ветка артефактов забирается, если уже есть: повторный `/bft-deep` — это
    доработка существующего документа, а не второй документ рядом. Пайплайн сам
    распознаёт режим по наличию файлов, и всё, что нужно от подготовки, — дать
    ему увидеть прошлый прогон.
    """
    shutil.rmtree(_bft_workspace_dir(req), ignore_errors=True)
    clone_dir = _bft_clone_dir(req)
    branch = bft.branch(req.issue_number)
    _clone_repo(req.repo, clone_dir,
                branch=branch if github_client.branch_exists(req.repo, branch) else None)
    _run_repomix(clone_dir)

    # Конфиг пайплайна — свой, поверх любого чужого: разъехавшийся `docs_path`
    # увёл бы артефакты туда, где публикация их не ищет.
    (Path(clone_dir) / "bft-config.md").write_text(bft.render_config(),
                                                   encoding="utf-8")

    thread, _ = _bft_thread(req)
    statement = Path(clone_dir) / bft.statement_path(req.issue_number)
    statement.parent.mkdir(parents=True, exist_ok=True)
    statement.write_text(
        bft.render_statement(title=req.title, body=req.body, thread=thread,
                             instructions=req.instructions,
                             issue_number=req.issue_number, repo=req.repo),
        encoding="utf-8",
    )
    return clone_dir


def _require_bft_workspace(req: BftRequest, requires: str | None) -> str:
    """Guard стадии — тот же приём, что и в цепочке FNR: потерянный каталог
    останавливает прогон с внятным сообщением вместо пере-клона, который дал бы
    свежий репозиторий без единого артефакта прежних стадий."""
    clone_dir = _bft_clone_dir(req)
    if not (Path(clone_dir) / "sa_documentation" / "repomix-output.xml").exists():
        raise RuntimeError("рабочий каталог потерян (рестарт воркера?) — повтори /bft-deep")
    if requires and not (Path(clone_dir) / requires).exists():
        raise RuntimeError(
            f"нет входа {requires} (стадия-предшественник не отработала?) — повтори /bft-deep"
        )
    return clone_dir


def _collect_bft_artifacts(clone_dir: str, issue_number: int) -> dict[str, str]:
    """Всё, что пайплайн положил в каталог эпика: документ и служебные артефакты.

    Забираем каталогом, а не списком имён: состав артефактов задаёт скилл, и
    зашитый перечень разъехался бы с ним при первом же его обновлении, молча
    теряя файлы.
    """
    root = Path(clone_dir) / bft.epic_dir(issue_number)
    files: dict[str, str] = {}
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*.md")):
        files[str(path.relative_to(clone_dir))] = path.read_text(encoding="utf-8")
    return files


@activity.defn
async def prepare_bft_workspace(req: BftRequest) -> None:
    """Стадия 0 глубокого прогона: клон (с веткой прошлого БФТ, если есть),
    repomix и постановка файлом. Идемпотентна — сносит остаток и строит заново."""
    await _run_with_heartbeat(_build_bft_workspace, req, label="bft-preparing")


@activity.defn
async def run_bft_stage(req: BftRequest, stage_name: str) -> dict:
    """Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.

    Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной
    активностью весь пайплайн был бы одним баром в Event History на десятки
    минут, и застрявшая стадия не называла бы себя.
    """
    prompt, expected, requires = bft.deep_stage(stage_name, req.issue_number)
    clone_dir = _require_bft_workspace(req, requires)
    await _run_with_heartbeat(_run_claude, prompt, clone_dir, label=f"bft:{stage_name}")
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
async def publish_bft_deep(req: BftRequest) -> str:
    """Финал глубокого прогона: артефакты в ветку, сводка комментарием."""
    clone_dir = _require_bft_workspace(req, None)
    files = await asyncio.to_thread(
        _collect_bft_artifacts, clone_dir, req.issue_number)
    if not files:
        raise RuntimeError("пайплайн БФТ не произвёл ни одного артефакта")
    branch = bft.branch(req.issue_number)
    await asyncio.to_thread(
        github_client.push_artifacts_to_branch,
        req.repo, branch, files,
        f"docs(bft): БФТ по issue #{req.issue_number}",
    )
    await asyncio.to_thread(
        github_client.post_comment, req.repo, req.issue_number,
        bft.render_deep_summary(req.repo, req.issue_number, list(files)),
    )
    return branch


@activity.defn
async def cleanup_bft_workspace(req: BftRequest) -> None:
    """Best-effort снос рабочего каталога прогона."""
    await asyncio.to_thread(
        shutil.rmtree, str(_bft_workspace_dir(req)), ignore_errors=True)


@activity.defn
async def publish_bft_error(req: BftRequest, reason: str) -> None:
    """Не молчать при сбое — требование постановки, а не вежливость.

    Молчащий сбой неотличим от «ещё думает»: человек ждёт БФТ, которого уже не
    будет, и узнаёт об этом, только когда сам придёт спрашивать.
    """
    what = "/bft-deep" if req.mode == bft.DEEP else "/bft"
    await asyncio.to_thread(
        github_client.post_comment, req.repo, req.issue_number,
        f"⚠️ БФТ не собрался: {reason}\n\n"
        f"Прогон не повторяется автоматически. Запустить заново — командой `{what}` "
        "(можно сразу с уточнениями в том же комментарии).",
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
