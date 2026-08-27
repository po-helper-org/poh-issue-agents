"""
Activities — вся содержательная логика, перенесённая из advisor/gate.py,
classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py
(версия на GitHub Actions). Изменился только транспорт: вместо чтения
GITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-
функции, вызываемые Temporal-воркером напрямую.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

import estimate_report
import estimation
import forge
# Историческое имя: его знают 118 вызовов в этом файле и три десятка тестовых
# файлов. Переименование — отдельная механическая правка; смешивать её с
# включением второго провайдера значило бы спрятать одно изменение в шуме
# другого.
github_client = forge
import llm
from shared import (
    bft,
    decomposition,
    develop,
    issue_blocks,
    labels,
    lifecycle,
    memory,
    pr_closing,
    repowise,
    sentry_setup,
    task_context,
)
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
    CommentAckInput,
    CommentIntent,
    Deadlines,
    DevelopPlan,
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


class CommentIntentExtraction(BaseModel):
    intent: str = Field(description="proceed | rework | question | ack")
    reason: str = Field(description="обоснование для комментария-ответа")
    rework_note: str = Field(description="что именно переделывать (только для rework)", default="")


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
            github_client.add_label(issue.repo, issue.issue_number, labels.BOT_AUTHORED)
            return "bot"

        KNOWN_BOT_LOGINS = {"dependabot", "renovate", "snyk-bot", "github-actions"}
        if issue.author_login.lower().removesuffix("[bot]") in KNOWN_BOT_LOGINS:
            github_client.add_label(issue.repo, issue.issue_number, labels.BOT_AUTHORED)
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
        github_client.add_label(issue.repo, issue.issue_number, labels.SECURITY_SENSITIVE)
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
    github_client.add_label(issue.repo, issue.issue_number, labels.NEEDS_CLARIFICATION)


@activity.defn
def close_as_spam(issue: IssueInput, reason: str) -> None:
    github_client.post_comment(issue.repo, issue.issue_number, f"🚫 Похоже на спам: {reason}")
    github_client.add_label(issue.repo, issue.issue_number, labels.SPAM)
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

    Целевая метка ставится раньше снятия прежних: окно, в котором меток
    `phase:*` нет вовсе, хуже окна, в котором их две. Атомарно это делается
    только на провайдере, умеющем менять набор одним запросом.
    """
    target = lifecycle.phase_label(phase)
    stale_labels = [lifecycle.phase_label(other) for other in lifecycle.PHASES]
    # Индикатор разработки — не фаза, но живёт по тому же правилу: он сообщает
    # «задача у агента разработки», и после открытия PR это уже неправда.
    # Снимать его в самой активности Develop нельзя — она к тому моменту давно
    # завершилась; единственная точка, которая знает о смене состояния, — здесь.
    if phase != lifecycle.IN_DEVELOPMENT:
        stale_labels.append(develop.IN_DEVELOPMENT_LABEL)
    github_client.set_labels(repo, issue_number, add=[target], remove=stale_labels)


@activity.defn
def mark_awaiting(repo: str, issue_number: int, waiting=None) -> None:
    """Отражение ожидания в GitHub: очередь к людям обязана быть полной (#39).

    Метка ставится, пока ход за человеком, и снимается, как только ожидание
    закрыто. До этого `needs-human:*` появлялась только по истечении дедлайна —
    то есть выборка показывала не очередь, а её просроченный хвост.

    Ожидание машины (стенд, соседний сервис) метку НЕ ставит: задача, по которой
    человеку делать нечего, в его очереди — шум, из-за которого перестают
    смотреть на саму выборку.

    Асимметрия обработки ошибок: постановка метки падает при сбое, снятие
    проглатывается (ошибка уходит в лог, но наружу не пробрасывается). Это
    поведение гарантирует, что неудачное снятие не заблокирует продолжение
    потока, который уже ушёл дальше.
    """
    if waiting is not None and isinstance(waiting, dict):
        waiting = Awaiting(**waiting)
    if waiting is not None and waiting.blocks_on_human:
        github_client.set_labels(repo, issue_number, add=[labels.NEEDS_HUMAN_TRIAGE])
        return
    github_client.set_labels(repo, issue_number, remove=[labels.NEEDS_HUMAN_TRIAGE])


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
        howtodemo_autostart=_flag("HOWTODEMO_AUTOSTART"),
        decompose_enabled=decomposition.enabled(),
        pr_fix_enabled=pr_closing.enabled(),
        pr_fix_max_rounds=pr_closing.max_rounds(),
        # Включён по умолчанию: БФТ на триаже — это НОВЫЙ формат ответа вместо
        # прежнего свободного, а не дополнительная стадия. Тумблер существует
        # ради возможности откатиться, поэтому и читается наоборот — выключение
        # требует явного BFT_ON_TRIAGE=0.
        bft_on_triage=_flag_on_by_default("BFT_ON_TRIAGE"),
        followup_max_rounds=_hours("FOLLOWUP_MAX_ROUNDS", 10),
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
def read_open_questions(repo: str, branch: str) -> list[str]:
    """Незакрытые вопросы из артефактов анализа — отдельным чтением.

    Аналитика разобрала код и знает, чего в постановке не хватает для
    однозначного решения; такие места она помечает `[УТОЧНИТЬ]`. Раньше они
    только перечислялись в чеклисте готовности — то есть решение по ним
    перекладывалось на агента разработки, и он выбирал за человека молча.
    """
    return _open_questions(repo, branch)


@activity.defn
def ask_open_questions(issue: IssueInput, questions: list[str],
                       round_number: int) -> None:
    """Вопросы аналитики — комментарием, чтобы на них можно было ответить.

    Ответ не надо оформлять командой: повторный прогон аналитики читает
    обсуждение Issue, поэтому обычный комментарий и есть способ закрыть вопрос.
    """
    listed = "\n".join(f"- {q}" for q in questions)
    github_client.post_comment(
        issue.repo, issue.issue_number,
        f"## ❓ Нужен ответ, чтобы идти дальше (круг {round_number})\n\n"
        "Аналитика разобрала код и упёрлась в то, чего в постановке нет. Пока "
        "это не закрыто, план исполнения строить не на чем — решение выбрал бы "
        "агент разработки, и выбрал бы молча.\n\n"
        f"{listed}\n\n"
        "Ответь обычным комментарием — этого достаточно: повторный прогон "
        "аналитики читает обсуждение задачи и закроет вопрос сам.",
    )


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
def read_issue_labels(repo: str, issue_number: int) -> list[str]:
    """Читает текущие метки Issue для проверки уже стоящих решений.
    
    Используется в сценариях, когда Issue приходит в фазу с уже проставленными
    метками (например, `research-me` на Issue, который вернулся из DUPLICATE),
    чтобы не ждать нового сигнала человека, а сразу продолжить обработку.
    """
    issue = github_client.get_issue(repo, issue_number)
    return [label["name"] for label in issue.get("labels", [])]


@activity.defn
def post_error_label(issue: IssueInput, reason: str = "") -> None:
    # Sentry ПЕРЕД комментарием, а не после: id события уезжает в тот же
    # комментарий ссылкой, иначе человек видит «не удалось» и не знает, где
    # смотреть, — а логи контейнера ему недоступны.
    #
    # `reason` = "ExcType: message" из catch-ветки workflow'а (workflows.py).
    # Без него (прямой вызов/старые тесты) exc_type пуст — событие всё равно
    # уходит, просто с менее точной группировкой.
    exc_type, _, message = reason.partition(": ")
    event_id = sentry_setup.capture_pipeline_failure(
        issue, exc_type or "unknown", message or reason)
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "⚠️ Автоматическая обработка не удалась. Ожидай ручного разбора."
        + sentry_setup.debug_reference(event_id),
    )
    github_client.add_label(issue.repo, issue.issue_number, "advisor:error")


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

    Best-effort по операции целиком, а не по каждой метке отдельно:
    `set_labels` снимает `run:*` и предыдущий исход даже если постановка новой
    метки исхода упала — иначе 5xx на POST оставлял бы `run:analyze` на Issue
    навсегда. Ошибка от `set_labels` (если постановка всё же не удалась)
    гасится здесь же: прогон уже состоялся, и провал косметики не должен
    превращать успешный анализ в проваленный. Наружу не пробрасывается —
    activity зовётся из терминальных веток воркфлоу.
    """
    outcome = done_label(command) if ok else failed_label(command)
    # Исход ПРЕДЫДУЩЕГО прогона снимается вместе с «идёт»: `done:analyze` рядом
    # с `failed:analyze` — противоречие, а не история. По такой паре нельзя
    # сказать, чем кончился последний прогон, и выборка `label:failed:*`
    # показывает задачи, которые давно починены повторным запуском.
    previous = failed_label(command) if ok else done_label(command)
    try:
        await asyncio.to_thread(
            github_client.set_labels, repo, issue_number,
            add=[outcome], remove=[*running_labels(command), previous])
    except Exception as exc:
        logger.warning("не привёл метки команды на %s#%s к виду %s: %s",
                       repo, issue_number, outcome, exc)


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
        "EXISTING": labels.ADVISOR_EXISTING,
        "CONSULTATION": labels.ADVISOR_CONSULTATION,
        "BUG": labels.ADVISOR_BUG,
        "FEATURE": labels.ADVISOR_FEATURE,
    }
    label = label_map.get(result.category, labels.ADVISOR_ANSWERED)
    # The advisor prompt still asks the model to prefix its answer with a
    # legacy [[MARKER]] (from the pre-Instructor text-parsing era). The
    # category is now carried structurally, so strip that marker line before
    # posting — it must not appear in the user-facing comment.
    answer = re.sub(r"^\s*\[\[[^\]]+\]\]\s*", "", result.answer)
    if not (bft_on_triage and label == labels.ADVISOR_FEATURE):
        github_client.post_comment(issue.repo, issue.issue_number, answer)
    github_client.add_label(issue.repo, issue.issue_number, label)
    return ClassificationResult(label=label, answer=answer)


# --- Диалог по припаркованной задаче ---

# Реплика приходит по уже обработанному Issue, и отвечать на неё надо в
# контексте всего разговора — включая прошлые ответы контура: именно к ним
# человек и обращается. Поэтому комментарии сервиса тут НЕ отсеиваются, как и
# в `/bft`.
FOLLOWUP_THREAD_COMMENTS = 40
FOLLOWUP_COMMENT_CHARS = 4000
FOLLOWUP_THREAD_CHARS = 30_000


class FollowupExtraction(BaseModel):
    answer: str = Field(description="Ответ человеку, готовый к публикации комментарием")


def _followup_thread(repo: str, issue_number: int) -> str:
    """Переписка Issue текстом. Сбой чтения не отменяет ответа.

    Без переписки модель ответит хуже — но ответит, а альтернатива здесь —
    молчание, то есть ровно тот отказ, который эта активность и чинит.
    """
    try:
        comments = github_client.list_comments(repo, issue_number,
                                               limit=FOLLOWUP_THREAD_COMMENTS)
    except Exception as exc:  # noqa: BLE001 — деградация важнее причины сбоя
        logger.warning("list_comments failed for followup #%s: %s", issue_number, exc)
        return ""

    blocks: list[str] = []
    for comment in comments:
        user = (comment.get("user") or {}).get("login", "?")
        date = (comment.get("created_at") or "")[:10]
        body = _truncate(comment.get("body") or "", FOLLOWUP_COMMENT_CHARS)
        blocks.append(f"**@{user} ({date}):**\n{body}")

    # Обрезаем от самых старых: разговор идёт с конца, и свежие реплики нужнее
    # первого комментария полугодовой давности.
    while blocks and len("\n\n".join(blocks)) > FOLLOWUP_THREAD_CHARS:
        blocks = blocks[1:]
    return "\n\n".join(blocks)


@activity.defn
def answer_followup(issue: IssueInput, question: str) -> None:
    """Ответ на реплику человека в припаркованном Issue.

    Отдельная активность, а не повторный `classify_issue`: тот отвечает по
    заголовку и телу Issue и ничего не знает о разговоре — на вопрос «а как
    тогда устроен Dataflow?» он ответил бы заново на исходную заявку и заодно
    переписал бы метку классификации. Здесь ответ идёт по всей переписке, а
    состояние Issue не трогается вовсе: метки и фазу двигают метки и команды.
    """
    capabilities = (WORKSPACE_DIR / "capabilities.md").read_text(encoding="utf-8") \
        if (WORKSPACE_DIR / "capabilities.md").exists() else "(пусто)"
    thread = _followup_thread(issue.repo, issue.issue_number)
    parts = [f"# Issue {issue.repo}#{issue.issue_number}: {issue.title}", "",
             "## Описание", "", issue.body.strip() or "(тело пустое)", "",
             "## Известный функционал", "", capabilities]
    if thread:
        parts += ["", "## Переписка Issue", "", thread]
    parts += ["", "## Реплика, на которую нужно ответить", "", question.strip()]

    result = llm.extract(
        _load_prompt("system_followup.md"), "\n".join(parts), FollowupExtraction,
        model=llm.MODEL_CLASSIFY,
    )
    answer = result.answer.strip()
    if not answer:
        # Пустой ответ модели — не повод публиковать пустой комментарий: он
        # выглядел бы как ответ и закрывал бы вопрос ничем.
        raise RuntimeError("модель вернула пустой ответ на реплику")
    github_client.post_comment(issue.repo, issue.issue_number, answer)


@activity.defn
def interpret_user_comment(issue: IssueInput, comment_text: str, current_phase: str,
                          classification_label: str | None, awaiting_reason: str | None,
                          recent_artifacts: dict[str, str] | None = None) -> CommentIntent:
    """Разбор намерения из реплики человека.
    
    Анализирует комментарий и определяет, чего хочет человек: продолжить работу,
    переделать этап, задать вопрос или просто подтвердить получение.
    """
    capabilities = (WORKSPACE_DIR / "capabilities.md").read_text(encoding="utf-8") \
        if (WORKSPACE_DIR / "capabilities.md").exists() else "(пусто)"
    
    thread = _followup_thread(issue.repo, issue.issue_number)
    
    parts = [
        f"# Issue {issue.repo}#{issue.issue_number}: {issue.title}", "",
        "## Описание", "", issue.body.strip() or "(тело пустое)", "",
        "## Текущая фаза", "", current_phase, "",
        "## Метка классификации", "", classification_label or "(нет)", "",
        "## Чего ждёт Issue", "", awaiting_reason or "(ожидания нет)", "",
        "## Известный функционал", "", capabilities
    ]
    
    if thread:
        parts += ["", "## Переписка Issue", "", thread]
    
    if recent_artifacts:
        parts += ["", "## Последние артефакты этапа", ""]
        for name, content in recent_artifacts.items():
            parts += [f"### {name}", "", content[:1000]]  # Ограничиваем размер
    
    parts += ["", "## Реплика для разбора", "", comment_text.strip()]
    
    result = llm.extract(
        _load_prompt("system_comment_intent.md"), "\n".join(parts), CommentIntentExtraction,
        model=llm.MODEL_GATE,
    )
    
    return CommentIntent(
        intent=result.intent,
        reason=result.reason,
        rework_note=result.rework_note or ""
    )


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
        github_client.add_label(issue.repo, issue.issue_number, labels.DUPLICATE)
        return DuplicateResult(decision="duplicate", best_match_number=best.number,
                                probability=best.probability, reason=best.reason, context_branch=branch)

    if best.probability >= 0.5:
        github_client.add_label(issue.repo, issue.issue_number, labels.POSSIBLE_DUPLICATE)
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

    priority_label = f"{labels.PRIORITY_PREFIX}{tier}"
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
    return PriorityResult(tier=tier, breakdown_markdown=breakdown, priority_label=priority_label)


@activity.defn
def post_priority_comment(issue: IssueInput, priority: PriorityResult, dup: DuplicateResult) -> None:
    body = priority.breakdown_markdown
    if dup.decision == "possible":
        body += (
            f"\n\n⚠️ Также похоже на возможный дубликат #{dup.best_match_number} "
            f"({dup.probability:.0%}) — стоит проверить перед запуском тяжёлой стадии."
        )
    github_client.post_comment(issue.repo, issue.issue_number, body)
    github_client.add_label(
        issue.repo, issue.issue_number,
        priority.priority_label or f"{labels.PRIORITY_PREFIX}{priority.tier}",
    )


# --- Пайплайн SA-helper (FNR) ---

FNR_DIR = "sa_documentation/FNR/FNR_1"
ARTIFACT_FILES = ("repowise-dialog.md", "task.md", "concept.md",
                  "system_requirements.md", "validation.md")
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

    `repowise` идёт ПЕРВОЙ: её результат — вход для постановки задачи, и
    обращаться к индексу после написания task.md уже поздно.
    """
    return [
        ("repowise", f"/repowise-context {description}",
         f"{FNR_DIR}/repowise-dialog.md"),
        ("task", f"/fnr-new-task {description}", f"{FNR_DIR}/task.md"),
        ("concept", f"/fnr-concept {FNR_DIR}/task.md", f"{FNR_DIR}/concept.md"),
        ("debate", f"/fnr-debate {FNR_DIR}/concept.md", None),
        ("sysreq", f"/fnr-system-requirements {FNR_DIR}/concept.md",
         f"{FNR_DIR}/system_requirements.md"),
        ("validate", f"/validate-doc {FNR_DIR}/system_requirements.md", None),
    ]


# Имя стадии сбора контекста — константой: на него ссылается ветвь деградации,
# и разъехавшийся литерал означал бы стадию, которая деградировать не умеет.
REPOWISE_STAGE = "repowise"

FNR_STAGE_NAMES = (REPOWISE_STAGE, "task", "concept", "debate", "sysreq", "validate")

# Входной артефакт каждой стадии — что уже должно лежать в рабочем каталоге,
# чтобы стадия имела смысл (используется guard'ом _require_workspace).
#
# У `task` вход — артефакт диалога: пропустить сбор контекста незаметно нельзя.
# Артефакт создаётся и при недоступном Repowise (деградация, см. run_fnr_stage),
# поэтому guard не превращает сервис в обязательную зависимость конвейера.
_FNR_STAGE_REQUIRES = {
    "repowise": None,
    "task": f"{FNR_DIR}/repowise-dialog.md",
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


def _existing_branch(repo: str, branch: str) -> str | None:
    """Имя ветки, если она есть в origin, иначе None.

    Проверка вспомогательная: её задача — подобрать артефакты прошлого прогона,
    а не решить, состоится ли анализ. Недоступный GitHub (нет авторизации,
    сеть, лимит) означает «продолжать не с чего», а не «прогон отменяется».
    """
    try:
        return branch if github_client.branch_exists(repo, branch) else None
    except Exception as exc:  # noqa: BLE001 — вспомогательная проверка
        logger.warning("ветка %s не проверена (%s) — клон с дефолтной", branch, exc)
        return None


def _build_workspace(analyze: AnalyzeInput) -> str:
    """Свежий каталог: снести остаток прежнего прогона, clone, repomix.

    Ветка артефактов забирается, если уже есть: повторный `/analyze` после
    обрыва — это продолжение, а не второй анализ рядом. Стадия с готовым
    артефактом тогда пропускается, и прогон не платит второй раз за уже
    написанный документ. Без этого пропуск не сработал бы вовсе: в свежем
    клоне дефолтной ветки прошлых артефактов нет.
    """
    shutil.rmtree(_workspace_dir(analyze), ignore_errors=True)
    clone_dir = _clone_dir(analyze)
    previous = _existing_branch(analyze.repo, f"research/issue-{analyze.issue_number}")
    # Аргумент передаём только когда ветка есть: вызов без него — прежний путь,
    # и подменять его в тестах существующим способом по-прежнему можно.
    if previous:
        _clone_repo(analyze.repo, clone_dir, branch=previous)
    else:
        _clone_repo(analyze.repo, clone_dir)
    _run_repomix(clone_dir)
    # Трекер диалога — до первой стадии: хуки живут в клоне, а он пересоздаётся.
    _enable_entire(clone_dir)
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

    `branch` — ветка вместо дефолтной; её просят два вызывающих по разным
    причинам. Круг правок работает поверх ветки PR, иначе правки ложились бы не
    на то, что видел ревьюер. Повторный прогон БФТ забирает ветку прошлого
    прогона, потому что дорабатывает уже лежащий там документ, а не пишет второй
    рядом. Пусто — ветка по умолчанию, как для анализа и разработки.

    Вызывающий обязан убедиться, что ветка существует: клон несуществующей
    падает внутри git, а падать это должно на понятной проверке.

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
    command = ["git", "clone", "--depth", "1"]
    if branch:
        command += ["--branch", branch]
    subprocess.run(
        [*command, url, dest],
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


def _run_claude(prompt: str, cwd: str, mcp_config: str | None = None) -> None:
    """Одна стадия FNR — отдельный процесс `claude -p` с чистым контекстом.

    Креды берутся из ZAI_* (как в main) и прокидываются в claude-code через его
    ANTHROPIC_* — единый ключ z.ai, отдельную пару переменных заводить не нужно.

    `mcp_config` — путь к файлу с описанием MCP-серверов. Передаётся ЯВНО, и это
    не перестраховка: `claude -p` НЕ подхватывает проектный `.mcp.json` сам.
    Положить файл в каталог прогона и надеяться — ровно то, что провалилось на
    первом живом Issue: стадия отработала за минуту, вышла с нулём, инструментов
    не увидела и артефакта не создала.
    """
    token, base = _claude_anthropic_creds()
    # Понятная ошибка вместо голого "exit 1", если z.ai не сконфигурирован:
    # без креды claude-code уходит на дефолтный Anthropic API и падает.
    if not token or not base:
        raise RuntimeError(
            "claude -p не сконфигурирован: задай ZAI_API_KEY и ZAI_BASE_URL "
            "(или явные ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN) в окружении воркера."
        )
    # acceptEdits, а НЕ --dangerously-skip-permissions: контейнер воркера
    # работает от root, а тот флаг под root запрещён самим claude-code
    # (проверено спайком, docs/spikes/2026-07-22-claude-p-zai-tool-calling.md).
    command = ["claude", "-p", prompt, "--permission-mode", "acceptEdits"]
    if mcp_config:
        # --strict-mcp-config: брать ТОЛЬКО этот файл. Иначе в сессию могли бы
        # затесаться серверы из окружения образа, и стадия ходила бы не туда,
        # куда её послали.
        #
        # --allowedTools по имени сервера: без него вызов инструмента ждёт
        # подтверждения, которого в неинтерактивном режиме не будет, и диалог
        # молча не состоится.
        command += ["--mcp-config", mcp_config, "--strict-mcp-config",
                    "--allowedTools", f"mcp__{repowise.SERVER_NAME}"]
    result = subprocess.run(
        command,
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
    # Артефакт диалога называется отдельно: без пояснения он выглядит служебным
    # мусором рядом с документами FNR, а это источник, из которого выведена
    # часть постановки, — и повод перечитать её критически, если диалог пуст.
    dialog = ""
    if any(p.endswith("repowise-dialog.md") for p in files):
        dialog = (
            "\n`repowise-dialog.md` — диалог с **Repowise**, постоянным индексом кода: "
            "что уже было известно о затронутых компонентах до постановки задачи. "
            "Пустой диалог означает, что индекс был недоступен, и остальные документы "
            "написаны без него.\n"
        )
    return (
        "## 🤖 Автономный анализ (SA-helper)\n\n"
        f"Прогнал полную цепочку FNR по этой задаче. Артефакты — в ветке `{branch}`:\n\n"
        f"{links}\n"
        f"{dialog}\n"
        "Начни с `system_requirements.md` — это ответ на вопрос «как реализовать эту "
        "задачу»: разбор текущего поведения на код-доказательствах, план миграции с "
        "откатами, задачи с критериями приёмки и риски с митигацией.\n\n"
        "Повторить анализ — командой `/analyze`."
    )


def _swallow_after_cancel(task: "asyncio.Task") -> None:
    """Забрать исключение задачи, брошенной отменой, и сказать это в лог.

    Молча глотать нельзя: поток мог упасть по настоящей причине, и она —
    единственный след того, чем закончилась оборванная стадия.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.info("стадия оборвана отменой, поток завершился ошибкой: %s", exc)


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
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_INTERVAL_SEC)
            if task in done:
                return task.result()  # переброс исключения из потока, если было
            activity.heartbeat(label)
    except asyncio.CancelledError:
        # Отмена активности (terminate воркфлоу, таймаут) обрывает ожидание, но
        # НЕ поток: `to_thread` не прерывается, docker-прогон доигрывает и
        # кладёт исключение в задачу, которую уже никто не ждёт. asyncio на
        # сборке такой задачи пишет «Task exception was never retrieved»
        # уровнем ERROR — и это уезжает в Sentry как сбой контура
        # (ISSUE-AGENT-C: код 137 у контейнера агента, снятого намеренно).
        # Колбэк забирает исключение, поэтому предупреждения не будет.
        task.add_done_callback(_swallow_after_cancel)
        raise


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " " + task_context.TRUNCATION_MARKER


def _refresh_issue_body(issue: IssueInput) -> str:
    """Перечитывает тело Issue из GitHub вместо устаревшего снимка.
    
    Снимок в `IssueInput` создается вебхуком один раз и устаревает для
    долгоживущих задач в `ready-for-dev`.
    """
    try:
        fresh = github_client.get_issue(issue.repo, issue.issue_number)
        return fresh.get("body") or ""
    except Exception as exc:  # noqa: BLE001 — деградация к старому снимку
        logger.warning("не удалось обновить тело #%s, используется снимок: %s",
                       issue.issue_number, exc)
        return issue.body


# Форма заголовка блока HowToDemo в теле Issue — те же четыре, что признаёт
# HowToDemo-Agent при поиске сценария (`docs/HOWTODEMO.md`, «Как агент находит
# сценарий»): `## HowToDemo`, `### How to demo`, `**How to demo:**`,
# `How to demo:`. Один гибкий шаблон вместо четырёх литеральных: пробелы между
# словами необязательны, поэтому он же покрывает слитное «HowToDemo».
#
# `(?![\w-])` сразу после «demo» — граница, которую `\b` не давал (ревью
# задачи 7, находка H2, случай 3): `\b` считает «-» границей слова наравне с
# пробелом, поэтому `## HowToDemo-Agent: как он работает` (заголовок ПРО
# агента с таким именем, не раздел сценария) матчился как начало блока, и в
# сценарий уезжал чужой текст. Новый запрет на «\w» и «-» сразу после «demo»
# не даёт сработать ни на слитном продолжении слова (`HowToDemoBot`), ни на
# дефисном (`HowToDemo-Agent`), но по-прежнему разрешает заголовок с хвостом
# через двоеточие или пробел (`## HowToDemo: оформление заказа`).
#
# Именованная группа `hashes` есть только у заголовочной формы — по ней
# `_howtodemo_block` определяет уровень заголовка для границы конца блока.
_HOWTODEMO_START = re.compile(
    r"""(?imx)
    ^[ \t]*
    (?:
        (?P<hashes>\#{2,3})[ \t]*how[ \t]*to[ \t]*demo(?![\w-])[^\n]*  # ## HowToDemo / ### How to demo
      | \*\*[ \t]*how[ \t]*to[ \t]*demo[ \t]*:[ \t]*\*\*[ \t]*           # **How to demo:**
      | how[ \t]*to[ \t]*demo[ \t]*:[ \t]*                               # How to demo:
    )
    \n?
    """
)

# Граница конца блока, начатого МЕТКОЙ письма БФТ (`**How to demo:**` /
# `How to demo:`), а не заголовком Markdown: следующий заголовок любого
# уровня либо следующая жирная метка-лейбл (`**Открытые вопросы:**` и т.п.) —
# ровно тот плоский формат письма, где секции размечены метками, а не `#`.
_HOWTODEMO_LABEL_END = re.compile(r"(?m)^[ \t]*(?:#{1,6}[ \t]|\*\*[^\n*]{1,80}:[ \t]*\*\*[ \t]*$)")


def _howtodemo_heading_end(level: int) -> re.Pattern[str]:
    """Граница конца блока, начатого ЗАГОЛОВКОМ Markdown уровня `level`.

    Ревью задачи 7, находка H2, случай 2: старая граница обрывала блок на
    ЛЮБОМ вложенном подзаголовке (`### Шаг 1` внутри `## HowToDemo` читался
    как конец сценария, а не как его часть). Заголовок того же уровня или
    крупнее (меньше решёток) — настоящая соседняя секция; более глубокий
    подзаголовок — содержимое сценария, а не граница.
    """
    return re.compile(rf"(?m)^[ \t]*#{{1,{level}}}[ \t]")


# Блок кода в обратных кавычках. Ревью, находка H2, случай 4: пример или
# шаблон для заполнения, процитированный в теле Issue обратными кавычками, не
# должен читаться как настоящий раздел сценария этой задачи.
#
# N1 (повторное ревью): забор — РОВНО три кавычки — не понимал ни забор из
# четырёх и более (стандартный способ процитировать текст, где уже есть
# тройные кавычки — иначе цитата закрылась бы раньше своей внутренней тройной
# кавычки), ни незакрытый забор. Обе формы оставались НЕ помаскированными
# (у первой — потому что паттерн требовал закрытия РОВНО тремя кавычками, а
# такой строки в тексте могло не быть вовсе; у второй — потому что `.sub` не
# находит совпадение без закрывающей части и не трогает текст), и вырезка
# сценария снова читала текст изнутри блока кода. Хуже прежнего: граница
# конца блока (H2) — заголовок того же уровня или крупнее, поэтому ложное
# совпадение внутри такого забора утаскивало всё до конца тела Issue, а не
# до ближайшего постороннего заголовка.
#
# `(?P<fence>`{3,})` — открывающий забор ЛЮБОЙ длины от трёх кавычек, а не
# фиксированной. Закрывающий — обратная ссылка на тот же символ `(?P=fence)`
# плюс `` `* `` следом: ровно то же требование, что и у Markdown-спеки —
# «не короче открывающего», а не «столько же». Короткий забор ПОСЕРЕДИНЕ
# блока (например, тройные кавычки внутри забора из четырёх) под это
# требование не подходит и закрытием не считается — блок остаётся открытым.
# `|\Z` — единственная альтернатива, которая гарантированно совпадёт, если
# закрывающего забора в тексте больше не найдётся: незакрытый забор считается
# открытым до конца текста, а не пропускается маскировкой вовсе.
_CODE_FENCE = re.compile(
    r"(?ms)^[ \t]*(?P<fence>`{3,})[^\n]*\n"
    r".*?"
    r"(?:^[ \t]*(?P=fence)`*[ \t]*$|\Z)"
)


def _mask_code_fences(body: str) -> str:
    """Стирает содержимое ``` блоков пробелами той же длины (переводы строк
    сохраняются), чтобы смещения символов не съезжали. Маска нужна только для
    ПОИСКА границ блока — содержимое сценария вырезается из исходного текста,
    поэтому реальный пример внутри настоящего сценария (например, curl-запрос
    в шаге демонстрации) не теряется."""
    return _CODE_FENCE.sub(
        lambda m: "".join(ch if ch == "\n" else " " for ch in m.group(0)), body)


def _howtodemo_block(body: str) -> str:
    """Сценарий приёмки из тела Issue: раздел HowToDemo, если он там есть.

    Блока нет — это НЕ отказ подготовки: сценарий мог остаться только в
    первом письме БФТ треда, и приёмщик (HowToDemo-Agent) умеет забирать его
    оттуда сам — тем же приоритетом, что описан в `docs/HOWTODEMO.md`. Здесь
    проверяется только тело Issue, письмо БФТ этой функции не видно.

    Поиск идёт по телу с замаскированными блоками кода (H2, случай 4): пример
    или шаблон, процитированный в тройных обратных кавычках, не считается
    настоящим разделом. Граница конца блока зависит от формы начала (H2,
    случай 1 и 2): у заголовка — следующий заголовок того же уровня или
    крупнее, у метки письма БФТ — следующий заголовок любого уровня либо
    следующая жирная метка.
    """
    body = body or ""
    haystack = _mask_code_fences(body)
    match = _HOWTODEMO_START.search(haystack)
    if not match:
        return ""
    start = match.end()
    hashes = match.group("hashes")
    end_pattern = _howtodemo_heading_end(len(hashes)) if hashes else _HOWTODEMO_LABEL_END
    end = end_pattern.search(haystack, start)
    content = body[start:end.start() if end else len(body)]
    return content.strip()


def _split_sections(parts: list[str]) -> list[tuple[str, str]]:
    """Разложить куски постановки на секции `(заголовок, содержимое)`.

    Заголовком считается ПЕРВАЯ СТРОКА куска, начинающегося с решётки, а не
    весь кусок. Раньше весь кусок целиком становился именем секции, и его
    содержимое исчезало: так терялся весь блок правил репозитория
    (`_DEV_FALLBACK_RULES`) вместе с инструкцией писать находки в
    `.followups.md`, которую `collect_dev_followups` затем честно читал.
    Уцелевал ровно один блок — тот, что начинается с перевода строки.
    """
    sections: list[tuple[str, str]] = []
    name = ""
    body: list[str] = []

    def flush() -> None:
        if name or body:
            sections.append((name, "\n".join(body).strip("\n")))

    for part in parts:
        if part.startswith("#"):
            flush()
            head, _, rest = part.partition("\n")
            name, body = head.strip(), ([rest] if rest.strip() else [])
        else:
            body.append(part)
    flush()
    return sections


ORG_RULES_HEADING = "## Накопленный опыт этой организации"
"""Заголовок блока правил от слоя саморефлексии.

Отдельной секцией, а НЕ довеском к предыдущей: приклеенный к соседней секции
блок неотличим при парсинге от её продолжения, и заголовок соседней секции
подписывался бы под чужой текст.

До задачи 7 у отдельной секции была ВТОРАЯ причина: усечение по приоритету
вытесняло секции целиком, и приклеенный блок делил бы судьбу соседа при
вытеснении. Усечения больше нет (см. `_dev_prepare`), но первая причина —
корректность самого разбора на секции — осталась, и заголовок остаётся
своим.
"""


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """Собрать постановку обратно, СОХРАНЯЯ заголовки секций.

    Заголовки нужны агенту: без них постановка превращается в поток текста, где
    неотличимы тело задачи, артефакты аналитики и правила работы.
    """
    out: list[str] = []
    for name, content in sections:
        block = "\n".join(x for x in (name, content) if x)
        if block.strip():
            out.append(block)
    return "\n\n".join(out)


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

    # Правила организации для роли исследования и аналитики: как формулировать
    # требования, как считать приоритет, что уточнять до разработки. Блок
    # дописывается последним и не начинается с заголовка — так же, как в
    # постановке разработки. Слой выключен — текст пуст, контекст не меняется.
    org_rules = memory.rules(memory.ISSUE, repo=analyze.repo,
                             query=f"{analyze.title}\n{analyze.body or ''}")
    if org_rules.text:
        parts.append(org_rules.text)

    return "\n\n".join(parts)


@activity.defn
async def prepare_workspace(analyze: AnalyzeInput) -> None:
    """Стадия 0 пайплайна /analyze: свежий clone + repomix в детерминированный
    каталог. Идемпотентна (сносит остаток и строит заново)."""
    await _run_with_heartbeat(_build_workspace, analyze, label="preparing")


def _write_repowise_config(analyze: AnalyzeInput, clone_dir: str) -> str | None:
    """Конфигурация MCP в рабочий каталог прогона. Возвращает путь к файлу.

    Не в образ: адрес прокси и идентификатор сессии зависят от Issue, и вшить
    их в образ нельзя. Пишется на КАЖДОЙ стадии, а не однажды: каталог прогона
    пересоздаётся стадией 0 (`_build_workspace`), и файл, положенный до неё,
    молча исчезнет — а выглядело бы это как агент, забывший про индекс.

    Путь возвращается, потому что файл надо ПЕРЕДАТЬ явно: `claude -p`
    проектный `.mcp.json` сам не читает (см. `_run_claude`).
    """
    if not repowise.enabled():
        return None
    config = repowise.claude_mcp_config(
        analyze.repo, analyze.issue_number, repowise.ANALYSIS)
    path = Path(clone_dir) / ".mcp.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return str(path)


def _ensure_dialog_artifact(analyze: AnalyzeInput, clone_dir: str,
                            expected: str) -> str:
    """Дописать артефакт диалога транскриптом из журнала прокси.

    Артефакт НЕ должен зависеть от того, вспомнила ли модель его записать. На
    первом живом прогоне она не вспомнила, стадия упала на guard'е, и весь
    конвейер встал — при исправном сервисе и состоявшемся, возможно, диалоге.

    Транскрипт берётся у прокси, как и для агента разработки: там журнал, и он
    полон по построению. Модель отвечает только за «Итог» — если она его
    написала, он сохраняется выше транскрипта.

    Возвращает исход: `ok` — ходы были, `no-turns` — сервис отвечал, но агент
    к нему не обратился.
    """
    session = repowise.session_id(analyze.repo, analyze.issue_number,
                                 repowise.ANALYSIS)
    transcript = repowise.transcript(session)
    path = Path(clone_dir) / expected
    path.parent.mkdir(parents=True, exist_ok=True)

    written = path.read_text(encoding="utf-8") if path.exists() else ""
    if transcript:
        path.write_text(f"{written}\n\n{transcript}" if written else transcript,
                        encoding="utf-8")
        return "ok"

    if not written:
        path.write_text(
            f"---\nissue: {analyze.repo}#{analyze.issue_number}\n"
            f"session: {session}\nagent: {repowise.ANALYSIS}\n"
            f"outcome: no-turns\nturns: 0\n---\n\n"
            f"# Итог\n\nАгент не обратился к индексу ни разу, хотя сервис был "
            f"доступен.\n\nЭто не отказ сервиса: постановка ниже написана без "
            f"дополнительного контекста, и перечитать её стоит критически.\n",
            encoding="utf-8")
    return "no-turns"


def _degrade_repowise_stage(analyze: AnalyzeInput, clone_dir: str,
                            expected: str | None) -> dict | None:
    """Артефакт-заглушка, если источник недоступен. None — источник на месте.

    Модификация M1 вердикта дебатов (`sa_documentation/FNR/FNR_5/concept.md`).
    Без неё прокси становится обязательной зависимостью на пути, который
    сегодня остановить нечему: `_build_workspace` зависит только от `git` и
    `repomix` внутри того же контейнера.

    Артефакт создаётся ВСЕГДА, поэтому guard стадии `task` остаётся без
    изменений и по-прежнему ловит молчаливый пропуск. Дорогой процесс диалога
    при этом не запускается — платить за заведомо недоступный источник незачем.
    """
    if not repowise.enabled():
        reason = "REPOWISE_PROXY_URL не задан — интеграция выключена"
    elif not repowise.available(timeout=repowise.PROBE_TIMEOUT_SEC):
        reason = "прокси не отвечает на проверку живости"
    else:
        return None

    path = Path(clone_dir) / expected
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        repowise.unavailable_artifact(
            analyze.repo, analyze.issue_number, repowise.ANALYSIS, reason),
        encoding="utf-8",
    )
    # WARNING, а не ERROR: это штатная деградация, а не отказ. Считать её долю
    # положено снаружи (FR-9), и ошибкой в Sentry она быть не должна — иначе
    # выключенная интеграция превратится в поток ложных сбоев.
    logger.warning("стадия %s деградировала (%s#%s): %s", REPOWISE_STAGE,
                analyze.repo, analyze.issue_number, reason)
    return {"stage": REPOWISE_STAGE, "artifact": expected,
            "bytes": path.stat().st_size, "outcome": "degraded"}


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
    if expected:
        ready = Path(clone_dir) / expected
        if ready.is_file() and ready.stat().st_size > 0:
            # Артефакт приехал с веткой прошлого прогона: стадия сделана, и
            # повторять её — платить второй раз за тот же документ.
            logger.info("FNR %s#%s: стадия %s уже сделана — пропускаю",
                        analyze.repo, analyze.issue_number, stage_name)
            return {"stage": stage_name, "artifact": expected,
                    "bytes": ready.stat().st_size, "outcome": "skipped"}
    mcp_config = _write_repowise_config(analyze, clone_dir)
    if stage_name == REPOWISE_STAGE:
        degraded = await asyncio.to_thread(_degrade_repowise_stage, analyze, clone_dir, expected)
        if degraded is not None:
            return degraded
    # Конфигурация MCP передаётся ТОЛЬКО стадии сбора контекста: остальным
    # стадиям индекс не нужен, а лишние инструменты в сессии — лишние соблазны
    # и лишние деньги.
    await _run_with_heartbeat(
        _run_claude, prompt, clone_dir,
        mcp_config if stage_name == REPOWISE_STAGE else None,
        label=stage_name)

    outcome = "ok"
    if stage_name == REPOWISE_STAGE and expected:
        # Артефакт дописывается транскриптом из журнала прокси и потому не
        # зависит от того, вспомнила ли модель его записать.
        outcome = await asyncio.to_thread(
            _ensure_dialog_artifact, analyze, clone_dir, expected)

    artifact: str | None = None
    size = 0
    if expected:
        path = Path(clone_dir) / expected
        if not path.exists():
            raise RuntimeError(f"стадия {stage_name}: артефакт {expected} не создан")
        artifact = expected
        size = path.stat().st_size
    return {"stage": stage_name, "artifact": artifact, "bytes": size,
            "outcome": outcome}


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
async def publish_analysis_partial(analyze: AnalyzeInput, reason: str) -> list[str]:
    """Сорванный анализ отдаёт то, что успел собрать — как и БФТ.

    Цепочка FNR стоит тех же денег и рвётся по тем же причинам: лимит
    провайдера, 524, выкладка посреди прогона. Раньше это списывало всю работу:
    артефакты жили в каталоге, который `cleanup_workspace` снимал на любом
    исходе, а публикация случалась только после последней стадии.

    Возвращает имена уцелевших артефактов: воркфлоу называет их человеку, а
    следующий `/analyze` по ним понимает, какие стадии можно не повторять.
    """
    clone_dir = _workspace_dir(analyze) / "repo"
    if not clone_dir.is_dir():
        logger.warning("FNR %s#%s: каталог уже снят — публиковать нечего",
                       analyze.repo, analyze.issue_number)
        return []
    files = await asyncio.to_thread(_collect_fnr_artifacts, str(clone_dir))
    if not files:
        return []
    branch = f"research/issue-{analyze.issue_number}"
    await asyncio.to_thread(
        github_client.push_artifacts_to_branch,
        analyze.repo, branch, files,
        f"docs(sa): частичный анализ issue #{analyze.issue_number}",
    )
    session_id, session_branch = await asyncio.to_thread(_entire_session, str(clone_dir))
    await asyncio.to_thread(_push_entire_branch, analyze.repo, str(clone_dir),
                            session_branch)
    links = "\n".join(
        f"- [`{path.rsplit('/', 1)[-1]}`]"
        f"(https://github.com/{analyze.repo}/blob/{branch}/{path})"
        for path in sorted(files))
    await asyncio.to_thread(
        github_client.post_comment, analyze.repo, analyze.issue_number,
        f"## ⏸ Анализ собран частично\n\nПрогон оборвался: {reason}\n\n"
        f"Что успели — в ветке `{branch}`:\n\n{links}\n\n"
        "Работа не потеряна: повторный `/analyze` поднимет эту ветку и продолжит "
        "с места обрыва — готовые стадии заново не считаются."
        + bft.render_session_hint(analyze.repo, session_id, session_branch),
    )
    return sorted(files)


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


def _runner_home(slug: str) -> str:
    """Домашний каталог раннера — каталог задачи, но только при живой интеграции.

    Агент ищет конфигурацию MCP в `$HOME/.openhands/mcp.json` (спайк FR-16), а
    общий том смонтирован в другом месте. Переставить HOME дешевле, чем
    оборачивать ENTRYPOINT образа.

    Интеграция выключена — возвращаем пусто, и HOME остаётся тем, что задан
    образом: поведение прогонов без Repowise не меняется вовсе.
    """
    if not repowise.enabled():
        return ""
    return f"{develop.workspace_mount()}/{slug}"


def _write_runner_mcp_config(issue: IssueInput, root: Path) -> None:
    """Конфигурация MCP в каталог задачи, откуда её прочитает раннер.

    Каталог лежит на общем томе и виден обоим контейнерам; права выставляются
    вместе с остальным содержимым каталога задачи — раннер работает от
    непривилегированного пользователя и в чужой каталог писать не сможет.
    """
    if not repowise.enabled():
        return
    if not repowise.available(timeout=repowise.PROBE_TIMEOUT_SEC):
        # НАСТРОЕННЫЙ, но недоступный прокси — не то же самое, что выключенная
        # интеграция, и раньше эти случаи не различались: конфиг писался по
        # флагу, агент шёл поднимать по нему MCP и умирал на инициализации, не
        # сделав ни одного хода. Контур при этом докладывал «агент не изменил
        # ни одного файла» — то есть обвинял агента в отказе инфраструктуры.
        # Живой случай: poh-demo-checkout#151, 2026-08-25.
        #
        # Работа без индекса — штатный режим, он же обещан документацией.
        logger.warning(
            "Develop %s#%s: Repowise настроен, но прокси не отвечает — "
            "конфигурацию MCP не пишу, агент пойдёт без индекса",
            issue.repo, issue.issue_number)
        return
    config_dir = root / develop.MCP_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / develop.MCP_CONFIG_NAME).write_text(
        json.dumps(repowise.openhands_mcp_config(
            issue.repo, issue.issue_number, repowise.DEVELOP),
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _dev_paths(issue: IssueInput) -> tuple[Path, Path]:
    """Каталог задачи в общем томе и клон внутри него.

    Том общий с раннером и смонтирован в обоих контейнерах по одному пути:
    воркер готовит каталог и читает результат, раннер пишет. Через bind-mount
    так не сделать — путь внутри воркера на хосте не существует.
    """
    root = Path(develop.workspace_mount()) / develop.task_slug(issue.repo, issue.issue_number)
    return root, root / "repo"


# M4 (ревью задачи 7): артефакты цепочки FNR сверх требований. Прежняя
# сборка (до задачи 7) тянула все пять в постановку; задача 7 оставила
# только требования — concept.md, task.md, repowise-dialog.md и
# validation.md выпали без упоминания. Возвращаются файлами в каталог: он
# для того и заведён, чтобы объём перестал быть поводом выбрасывать
# контекст. НЕ обязательны — `task_context.required()` их не требует.
_OPTIONAL_ANALYSIS_ARTIFACTS = (
    (task_context.TASK, "постановка, с которой начинался анализ FNR"),
    (task_context.REPOWISE_DIALOG, "диалог с индексом кода на старте анализа"),
    (task_context.VALIDATION, "проверка требований на этапе анализа"),
)


def _fetch_optional_artifact(repo: str, name: str, branch: str) -> str:
    """Один необязательный артефакт цепочки FNR с ветки аналитики (M4).

    Деградация, а не отказ, при ЛЮБОМ сбое (не только 404 — `get_file`
    бросает исключение на прочих кодах ответа): эти артефакты никогда не
    входят в `task_context.required()`, и сетевой сбой на одном из них не
    должен ронять всю подготовку контекста, которая уже прошла обязательные
    требования.
    """
    try:
        return github_client.get_file(repo, f"{FNR_DIR}/{name}", branch) or ""
    except Exception as exc:  # noqa: BLE001 — деградация, а не отказ
        logger.warning("не удалось прочитать %s с ветки %s: %s", name, branch, exc)
        return ""


def _dev_prepare(issue: IssueInput, branch: str) -> tuple[str, list[str]]:
    """Свежий клон + контекст каталогом `.harness/` + короткая постановка.

    Возвращает текст постановки и перечень идентификаторов правил, подсыпанных
    слоем саморефлексии. Перечень нужен записи об итерации: без него нельзя
    отличить «правило сработало» от «правило не читали», и счётчики
    подтверждения на стороне слоя теряют смысл.

    Постановка собирается ЗДЕСЬ, а не в промпте агента: то, что уехало в
    работу, должно быть видно дословно. Иначе на разборе «почему агент сделал
    не то» предъявить нечего. Но сама постановка (`.task.md`, снимается перед
    коммитом) больше НЕ несёт содержательный контекст — до задачи 7 она
    паковала требования, артефакты аналитики, обсуждение и план декомпозиции
    в один файл с потолком 50000 знаков на всё и 10000 на артефакт; докстринг
    того кода признавал «переполнение достижимо штатно». Контекст теперь
    лежит файлами каталога `.harness/` (`shared/task_context.py`) — он
    коммитится вместе с кодом, виден в PR и читается через полгода, а
    исполнитель открывает файлы из git по мере надобности, без потолка на
    объём и без усечения.

    Обязательный набор файлов контекста объявлен в `task_context.required()` и
    проверяется здесь ЖЁСТКО: отсутствие обязательного файла — отказ стадии
    (`RuntimeError`), а не предупреждение в лог. Молчаливая неполная сборка
    хуже упавшей стадии — исполнитель работал бы вслепую, не зная, что
    контекста не хватает.
    """
    root, clone_dir = _dev_paths(issue)
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    _clone_repo(issue.repo, str(clone_dir))
    _write_runner_mcp_config(issue, root)

    # Свежее тело Issue вместо устаревшего снимка вебхука.
    fresh_body = _refresh_issue_body(issue)

    parts = [f"# Задача: реализовать Issue #{issue.issue_number}",
             "", f"## {issue.title}", "", fresh_body or "(тело пустое)", ""]

    # --- Контекст каталогом: исполнитель читает файлы из git, не пересказ ---
    harness = clone_dir / task_context.DIR
    # H1 (ревью задачи 7): `.harness/` коммитится в main, поэтому клон того же
    # репозитория приезжает с каталогом ПРЕДЫДУЩЕЙ задачи, если она мержилась
    # раньше. `mkdir(exist_ok=True)` без очистки оставлял унаследованные файлы
    # на месте: молчаливый провал сборки ЭТОЙ задачи (токен истёк, артефакт
    # переименован, sysreq не дописан) не создавал отказа — проверка
    # обязательного набора видела чужой файл прошлой задачи и засчитывала его,
    # а исполнитель получал требования и сценарий чужого Issue. Каталог
    # обязан собираться с нуля на каждом прогоне, а не дополняться.
    shutil.rmtree(harness, ignore_errors=True)
    harness.mkdir(parents=True, exist_ok=True)
    entries: dict[str, str] = {}

    requirements = ""
    concept = ""
    if branch:
        requirements = github_client.get_file(
            issue.repo, f"{FNR_DIR}/system_requirements.md", branch) or ""
        if requirements:
            (harness / task_context.REQUIREMENTS).write_text(
                requirements, encoding="utf-8")
            entries[task_context.REQUIREMENTS] = "системные требования (ветка аналитики)"
        # N3 (повторное ревью): concept.md читается один раз и используется
        # ОДИН раз — только как источник DECISIONS (M2, ниже). До этой правки
        # то же содержимое дополнительно писалось СВОИМ именем (M4) — байт в
        # байт та же строка дважды под разными подписями в карте контекста,
        # будто это разные срезы; исполнитель тратил бюджет чтения дважды на
        # один и тот же текст.
        concept = _fetch_optional_artifact(issue.repo, task_context.CONCEPT, branch)

    scenario = _howtodemo_block(fresh_body or "")
    if scenario:
        (harness / task_context.HOWTODEMO).write_text(scenario, encoding="utf-8")
        entries[task_context.HOWTODEMO] = "сценарий приёмки: им проверяется результат"

    # M2 (ревью задачи 7): DECISIONS больше НЕ копия `.reflect.md`. Постановка
    # обещает агенту дословно «файл в коммит не попадёт, его снимает контур»
    # — под это обещание агент пишет намерение, допущения и СОМНЕНИЯ, а копия
    # в decisions.md коммитилась и уезжала в PR: обещание нарушалось кодом
    # же, который его давал. Источник — concept.md ветки аналитики: там
    # вердикт дебатов, то есть принятые решения и их причины, а не намерения
    # агента. Заодно (L1) это делает DECISIONS ретрай-устойчивым: файл
    # приходит через git на каждом вызове независимо от локального состояния
    # каталога задачи, а не из файла, который снесла же предыдущая попытка.
    if concept:
        (harness / task_context.DECISIONS).write_text(concept, encoding="utf-8")
        entries[task_context.DECISIONS] = (
            "источник — вердикт дебатов цепочки аналитики: принятые решения "
            "и их причины"
        )

    # M4: остальные артефакты цепочки FNR — опциональные, читаются, только
    # если ветка аналитики есть (иначе им взяться неоткуда).
    #
    # N3 (повторное ревью): concept.md сюда НЕ входит, хотя формально он тоже
    # артефакт цепочки FNR. `DECISIONS` выше — тот же файл, объявленный в
    # `shared/task_context.py` и несущий роль «принятые решения и их причины»
    # (M2); отдельная копия под именем `task_context.CONCEPT` дублировала бы
    # его содержимое байт в байт под другой подписью в карте контекста, а не
    # добавляла новый срез. `task_context.CONCEPT` остаётся именем артефакта
    # для чтения с ветки аналитики (см. `_fetch_optional_artifact` выше) — он
    # просто не становится ВТОРЫМ файлом каталога.
    if branch:
        for name, description in _OPTIONAL_ANALYSIS_ARTIFACTS:
            content = _fetch_optional_artifact(issue.repo, name, branch)
            if content:
                (harness / name).write_text(content, encoding="utf-8")
                entries[name] = description

    (harness / task_context.CONTEXT_MAP).write_text(
        task_context.render_map(entries), encoding="utf-8")

    # Обязательный набор — ОТДЕЛЬНО от `entries`: перечень выше называет
    # только то, что реально записалось, и на молчаливом провале записи
    # (сеть недоступна, токен истёк) был бы просто короче — а `missing()` на
    # НЁМ ЖЕ ответила бы «всё доставлено». Проверяем против объявленного вовне
    # обязательного набора, который от факта записи не зависит.
    #
    # `branch` есть, а требования дописать не удалось — сообщение называет
    # ИМЕННО ЭТО (L6, ревью задачи 7): ветка аналитики нередко существует
    # раньше, чем в неё попадает `system_requirements.md` — цепочка FNR ещё не
    # дошла до стадии `sysreq`, либо оборвалась раньше (`publish_analysis_partial`
    # пушит частичный результат). Ручной `/develop` в этом окне — не редкость,
    # и сообщение обязано сказать человеку, что делать, а не только что сломано.
    absent = task_context.missing(harness, task_context.required(has_analysis=bool(branch)))
    if absent:
        raise RuntimeError(
            f"Develop {issue.repo}#{issue.issue_number}: контекст не собран — "
            f"в {task_context.DIR}/ нет обязательных файлов: {', '.join(absent)}. "
            "Отказ стадии вместо слепого прогона исполнителя. Если ветка "
            f"аналитики `{branch}` создана недавно — вероятно, цепочка FNR ещё "
            "не дошла до стадии `sysreq` (или оборвалась раньше неё): дождись "
            "её завершения или перезапусти `/analyze` и повтори `/develop`."
        )

    # H1 (ревью задачи 7), вторая половина чинки: пустая карта контекста при
    # ЖИВОЙ ветке аналитики — самостоятельный повод для отказа, а не только
    # следствие проверки выше. Собранный контекст не может не содержать
    # НИЧЕГО: если ветка аналитики есть, а `entries` пуст (ни требований, ни
    # сценария, ни решений), это неотличимо от молчаливого провала сборки.
    # Сегодня проверка `required()`/`missing()` выше уже ловит этот случай
    # (REQUIREMENTS обязателен при `has_analysis`) и потому оказывается первой
    # — её сообщение конкретнее (называет отсутствующий файл). Эта проверка —
    # СТРАХОВКА: полагаться ИСКЛЮЧИТЕЛЬНО на `required()` значит терять
    # защиту, если его определение изменится независимо от этой строки;
    # `test_empty_context_fails_even_if_required_set_is_patched_to_demand_nothing`
    # подтверждает мутацией, что она действительно ловит сама, а не только
    # вслед за `required()`.
    #
    # Без ветки (`branch` пуст) `entries` пустым бывает штатно: «аналитики нет
    # — работай от тела Issue» — не отказ (см. `task_context.required()`,
    # `test_no_analysis_branch_does_not_require_a_requirements_file`), и здесь
    # эта строка это уважает — проверка условна на `branch`.
    if branch and not entries:
        raise RuntimeError(
            f"Develop {issue.repo}#{issue.issue_number}: контекст не собран — "
            f"{task_context.DIR}/ пуст, хотя ветка аналитики {branch} есть. "
            "Отказ стадии вместо слепого прогона исполнителя."
        )

    # L2 (ревью задачи 7): сообщение обязано подсказывать выход, а не только
    # называть находку. В штатной работе этот путь недостижим — единственный
    # код, что дописывал маркер (`_apply_size_limit`), задача 7 удалила
    # целиком, — проверка защищает от УНАСЛЕДОВАННОГО маркера, если он всё же
    # попал в исходный текст (например, дословно процитирован в требованиях).
    # Без подсказки такой отказ повторялся бы на каждой разработке по этой
    # задаче: файл на ветке аналитики не правит сам себя.
    corrupted = task_context.truncation_markers(harness)
    if corrupted:
        source = f"ветке аналитики `{branch}`" if branch else "теле Issue"
        raise RuntimeError(
            f"Develop {issue.repo}#{issue.issue_number}: в {task_context.DIR}/ "
            f"найден след усечения (маркер «{task_context.TRUNCATION_MARKER}») "
            f"в файлах: {', '.join(corrupted)}. Если это не сбойное усечение, а "
            "часть настоящего текста (маркер процитирован дословно) — исправь "
            f"исходный текст в {source} (перепиши или убери маркер) и повтори "
            "`/develop`."
        )

    parts.append(
        f"## Контекст\n\n"
        f"Требования и сценарий приёмки, если они собрались, — в `{task_context.DIR}/`"
        f" рядом с кодом; что именно там лежит и в каком порядке читать — в "
        f"`{task_context.DIR}/{task_context.CONTEXT_MAP}`. Это файлы git, а не "
        "пересказ: открывай по мере надобности, потолка на объём нет.\n\n"
        f"Результат проверяется сценарием приёмки, если он есть "
        f"(`{task_context.DIR}/{task_context.HOWTODEMO}`), и тестами репозитория."
        + ("" if branch else "\n\nАналитики по задаче нет — работай от тела Issue.")
    )

    # Правила репозитория и Repowise (как было)
    rules = (clone_dir / ".openhands" / "task-rules.md")
    parts.append(rules.read_text(encoding="utf-8") if rules.exists() else _DEV_FALLBACK_RULES)
    # Дописывается ПОСЛЕ правил репозитория, а не вместо: правила проекта
    # главнее, а обращение к индексу — общий приём контура, который к ним
    # добавляется в обеих ветках (свои правила есть и когда их нет).
    if repowise.enabled():
        parts.append(_DEV_REPOWISE_RULES)

    # Всегда, независимо от того, чьи правила выше: свои у репозитория или
    # запасные. Требование контура к прогону не может зависеть от того, завёл
    # ли репозиторий свой файл правил.
    parts.append(_DEV_REFLECT_NOTE_RULE)

    # Правило фокуса — той же логикой и в том же месте, что и след решения
    # чуть выше: отдельным блоком постановки, а не довеском к запасным
    # правилам, иначе граница приёмки пропадала бы ровно там, где нужнее
    # всего — в репозиториях со своими правилами.
    parts.append(_FOCUS_RULE)

    # Правила и накопленный опыт организации — слой саморефлексии.
    #
    # Отбор идёт ЗДЕСЬ, а не отдельной активностью перед этой. Отдельная
    # активность повезла бы текст правил через полезную нагрузку Temporal, а
    # это против решения, закреплённого `tests/test_develop_child.py`: между
    # шагами едут числа и пути, не содержимое, потолок 4 КБ.
    #
    # Блок дописывается ПОСЛЕДНИМ и НЕ начинается с заголовка: разбор на
    # секции ниже сделал бы его именем секции без содержимого. При выключенном
    # слое текст пуст, и постановка не меняется ни на символ.
    # Контрольная выборка: каждая N-я задача идёт БЕЗ правил. Не порча
    # прогона, а единственный способ ответить на вопрос «слой не мешает?» —
    # сравнивать доли исходов не с чем, если правила подсыпаются всегда.
    if memory.control_arm(issue.issue_number):
        logger.info("Develop %s#%s: контрольная итерация — правила организации "
                    "не подсыпаются", issue.repo, issue.issue_number)
        memory_rules = memory.Rules(text="", ids=[])
    else:
        memory_rules = memory.rules(memory.DEVELOP, repo=issue.repo,
                                    query=f"{issue.title}\n{fresh_body or ''}")
    if memory_rules.text:
        # Заголовок ставит КОНТУР, а не слой: слой не знает, во что его блок
        # вставят, и заголовков не выдаёт. Отдельной секцией, а не довеском к
        # предыдущей — см. докстринг ORG_RULES_HEADING.
        parts.append(f"{ORG_RULES_HEADING}\n{memory_rules.text.strip()}")

    # Постановка короткая по построению: тяжёлый контекст ушёл в `.harness/`
    # выше, здесь остаются заголовок/тело задачи, указатель на контекст и
    # рабочие инструкции контура — потолка на размер больше нет и не нужно.
    task = _join_sections(_split_sections(parts))
    (clone_dir / ".task.md").write_text(task, encoding="utf-8")

    # Перечень подсыпанных правил — файлом в КОРНЕ задачи, а не в клоне.
    # Корень лежит вне рабочего дерева git, поэтому файл физически не может
    # уехать в коммит: `git add -A` его не видит. Через полезную нагрузку
    # Temporal перечень не везём — между шагами едут числа и пути.
    _write_injected_rules(root, memory_rules.ids)

    _handover_to_runner(root)
    return task, memory_rules.ids


INJECTED_RULES_FILE = ".reflect-rules.json"
"""Имя файла с перечнем подсыпанных правил. Лежит в корне задачи, вне клона."""


def _write_injected_rules(root: Path, ids: list[str]) -> None:
    """Сохранить перечень. Отказ записи не срывает подготовку постановки."""
    try:
        (root / INJECTED_RULES_FILE).write_text(
            json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.warning("перечень подсыпанных правил не сохранён: %s", e)


SIGNALS_FILE = ".reflect-signals.json"
"""Сигналы, которые контур измерил по ходу прогона.

Лежит в КОРНЕ задачи, вне рабочего дерева git: `git add -A` его не видит.
Через полезную нагрузку Temporal не везём — между шагами едут числа и пути.

Существует потому, что измерение из первых рук точнее восстановленного
постфактум: результат тестов контур знает в момент прогона, а по артефактам
через неделю его не установить вовсе.
"""


def _write_signal(root: Path, name: str, value) -> None:
    """Добавить измеренный сигнал. Отказ записи не срывает шаг."""
    try:
        path = root / SIGNALS_FILE
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8")) or {}
            except ValueError:
                data = {}
        data[name] = value
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.warning("сигнал %s не сохранён: %s", name, e)


def _read_signals(root: Path) -> dict:
    """Прочитать измеренные сигналы. Нет файла — пусто, это обычный ход дел."""
    try:
        data = json.loads((root / SIGNALS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_injected_rules(root: Path) -> list[str]:
    """Прочитать перечень. Нет файла — пустой список, это обычный ход событий."""
    try:
        raw = json.loads((root / INJECTED_RULES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(x) for x in raw] if isinstance(raw, list) else []


_DEV_REPOWISE_RULES = """## Индекс кода (MCP-сервер `repowise`) — обращение обязательно

Постоянный индекс репозиториев организации: граф символов, история git, blame,
поиск, оценка риска правки, мёртвый код.

1. **До начала работы** — ПЕРВЫМ ДЕЙСТВИЕМ, до чтения файлов и до первой
   правки — задай индексу не меньше одного вопроса о компонентах, которые
   собираешься менять, и об их связях: `search_codebase`, `get_context`,
   `get_symbol`, `get_answer`. Это дешевле, чем читать репозиторий целиком, и
   точнее, чем догадываться по именам файлов.

   «Задача выглядит простой», «требования и так подробные», «репозиторий
   маленький» — НЕ основания пропустить шаг. Индекс знает то, чего нет ни в
   требованиях, ни в файлах: кто ещё вызывает этот код, чем он был раньше и
   почему устроен так. Пропуск шага — ошибка прогона, даже если правка вышла
   верной.
2. **При затруднении** спроси снова — вместо того чтобы продолжать вслепую.
   Не понял, почему код устроен так — спроси про историю и решение
   (`get_why`, `get_risk`), а не переписывай.
3. **Индекс недоступен** — работай без него. Это штатный режим, а не повод
   останавливаться. Недоступен — значит вызов вернул ошибку; отсутствие
   желания спрашивать недоступностью не считается.

Весь диалог сохраняется автоматически и публикуется артефактом: пересказывать
его в отчёте не нужно.
"""


REFLECT_NOTE_FILE = ".reflect.md"
"""Файл намерений агента. Входит в перечень служебных файлов и не коммитится."""

TASK_BODY_LIMIT = 4000
"""Сколько текста постановки едет в запись об итерации.

Постановка бывает на десятки килобайт, а нужна судье лишь настолько, чтобы
понять, что просили. Полный текст задачи всегда доступен по её номеру.
"""


_DEV_FALLBACK_RULES = f"""## Как работать

Правила репозитория — в `AGENTS.md` и `CLAUDE.md`, они обязательны.

1. **MVP первым.** Кратчайший путь к тому, что просят. Не углубляйся в
   надёжность и редкие ветки, пока основное не работает.
2. **Edge-кейс — не в эту ветку.** Найденное по дороге не чини здесь, а запиши
   в `{develop.FOLLOWUPS_FILE}` в корне рабочего каталога — по одному разделу
   `## <кратко что не учтено>` на находку, в теле: где (файл:строка), чем
   грозит, при каких условиях всплывёт. Issue по ним заведёт контур: `gh` и
   токена у тебя нет намеренно. Ничего не нашёл — файл не создавай.
3. **Тесты.** Прогоняй проверки проекта; красный прогон в PR не отдаём.
4. **Коммитить самому не надо** — коммит, пуш и PR делает контур после тебя.
"""


_DEV_REFLECT_NOTE_RULE = f"""## След решения

В конце запиши `{REFLECT_NOTE_FILE}` в корне рабочего
каталога тремя разделами: `## Намерение` — что ты решил сделать и почему
именно так; `## Допущения` — что принял на веру, не проверив; `## Сомнения` —
где не уверен и что стоит перепроверить человеку. По строке на пункт.

Это не отчёт о работе: дифф и так виден. Это то, чего по диффу НЕ
восстановить — почему сделано так, а не иначе. Восстанавливать это потом по
артефактам бессмысленно: на такой задаче даже сильные модели угадывают редко.

Файл в коммит не попадёт, его снимает контур.
"""
"""Инструкция про файл намерений — ОТДЕЛЬНЫМ блоком, а не внутри запасных правил.

Правила репозитория подменяются его собственным `.openhands/task-rules.md`
целиком. Пока эта инструкция жила внутри запасных правил, до агента она
доходила только в репозиториях БЕЗ своих правил — то есть в самых редких.
Найдено живым прогоном: демо-репозиторий имеет свои правила, и файл намерений
не появился ни разу.

Инструкция контурная, а не репозиторная: слой саморефлексии один на все
репозитории организации, и его требование к прогону не может зависеть от того,
завёл ли конкретный репозиторий свой файл правил.
"""


_FOCUS_RULE = f"""## Фокус

Нашёл по дороге то, без чего сценарий приёмки всё равно пройдёт, — запиши в
`{develop.FOLLOWUPS_FILE}` и иди дальше. Нужно для прохождения сценария — сделай здесь же,
отдельной задачи не заводи.

Граница не на вкус: критерий один — пройдёт ли сценарий без этого.

Ветка, где сделано лишнее, ревьюится дольше и откатывается целиком. Работа,
которой не хватило для сценария, возвращается кругом правок и стоит второго
прогона.
"""
"""Правило фокуса — ОТДЕЛЬНЫМ блоком, тем же приёмом, что и `_DEV_REFLECT_NOTE_RULE`
выше (см. её докстринг для полного разбора ловушки).

Свой `.openhands/task-rules.md` целевого репозитория подменяет запасные
правила контура (`_DEV_FALLBACK_RULES`) ЦЕЛИКОМ. Внутри запасных правил это
правило доходило бы до агента только в репозиториях БЕЗ своих правил — то
есть в самых редких, и границу приёмки нечем было бы держать в самых обычных
прогонах. Ровно так уже были потеряны блок правил и инструкция про файл
находок.

Правило контурное, а не репозиторное: граница фокуса — требование ко всем
прогонам организации одинаково, вне зависимости от того, завёл ли конкретный
репозиторий свой файл правил.
"""


def _handover_to_runner(path: Path) -> None:
    """Передать каталог задачи раннеру целиком: он работает не от root.

    Передаётся ВЕСЬ каталог задачи, а не только клон. Каталог задачи — это
    ещё и `$HOME` раннера (см. `_runner_home`), а OpenHands держит там своё
    состояние: `$HOME/.openhands/conversations`. Оставленный за root'ом, он
    даёт `PermissionError` на первом же шаге, но код возврата остаётся нулевым
    — снаружи прогон выглядит как отработавший, а правок нет ни одной.

    Падаем громко. Молча оставленный каталог root'а — рабочее место, в которое
    агент не может писать: он не сообщает об отказе, а уходит писать в /tmp и
    докладывает об успехе. Прогон отрабатывает целиком и не оставляет ни одной
    правки — отказ, который снаружи выглядит как исправная работа.
    """
    try:
        for current, dirs, files in os.walk(path):
            os.chown(current, develop.RUNNER_UID, develop.RUNNER_GID)
            for name in (*dirs, *files):
                os.chown(os.path.join(current, name),
                         develop.RUNNER_UID, develop.RUNNER_GID)
    except OSError as exc:
        raise RuntimeError(
            f"не передал рабочий каталог раннеру (uid {develop.RUNNER_UID}): {exc}. "
            "Без этого агент не сможет писать в него и молча уйдёт в /tmp."
        ) from exc


def _reap_runner(slug: str) -> None:
    """Снять контейнер прошлой попытки, если он пережил своего запускателя.

    Temporal повторяет активность до трёх раз. Умерший вместе с воркером прогон
    контейнер за собой не убирает (`--rm` срабатывает только на нормальном
    выходе), и вторая попытка либо упирается в занятое имя, либо запускает
    второго агента в тот же рабочий каталог. На стенде остаток жил полчаса и
    доедал память, из-за которой следующая задача еле ползла.
    """
    subprocess.run(develop.reap_command(slug), capture_output=True, text=True,
                   timeout=60, check=False)


def _dev_run_agent(issue: IssueInput) -> str:
    """Прогон одноразового контейнера. Возвращает хвост вывода."""
    shortage = develop.resource_shortage()
    if shortage:
        # Отказ ДО старта, а не сожжённый прогон: контейнер агента поднимается
        # на общем хосте, и нехватка памяти бьёт не по нам, а по соседям через
        # OOM-killer, который выбирает жертву сам.
        raise RuntimeError(f"прогон агента не начат: {shortage}")
    slug = develop.task_slug(issue.repo, issue.issue_number)
    _reap_runner(slug)
    command = develop.runner_command(
        slug,
        image=develop.runner_image(),
        volume=develop.workspace_volume(),
        mount=develop.workspace_mount(),
        network=develop.proxy_network(),
        home=_runner_home(slug),
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
    # Логируем и на успехе. Раньше вывод жил только в тексте исключения, то есть
    # при ненулевом коде, — и прогон, который отработал двадцать минут и не
    # тронул ни одного файла, не оставлял ни строки. Разбираться было не с чем.
    logger.info("Develop %s#%s: вывод агента\n%s",
                issue.repo, issue.issue_number, tail or "(пусто)")
    return tail


DEV_DIALOG_PATH = "docs/research/issue-{n}-repowise-dialog.md"


def _collect_dev_dialog(repo: str, issue_number: int, run_failed: bool) -> str:
    """Транскрипт сессии разработки. Забирает ВОРКЕР, а не раннер.

    Раннер к этому моменту уже мёртв — в этом и смысл: артефакт переживает
    прогон, включая аварийный, а диалог полезен ровно тогда, когда разбирают
    неудачу.

    Пустая сессия даёт артефакт с отметкой, а не отсутствие артефакта:
    «агент не обращался к индексу» — это факт, который надо видеть, а не
    пробел, который надо угадывать.
    """
    session = repowise.session_id(repo, issue_number, repowise.DEVELOP)
    text = repowise.transcript(session)
    if text:
        return text
    failed = " (прогон завершился аварийно)" if run_failed else ""
    return (
        f"---\nissue: {repo}#{issue_number}\nsession: {session}\n"
        f"agent: {repowise.DEVELOP}\noutcome: no-turns\nturns: 0\n---\n\n"
        f"# Итог\n\nЗа время прогона обращений к индексу не было{failed}.\n\n"
        f"Причины бывают три: индекс был недоступен, задача не потребовала "
        f"дополнительного контекста, либо агент не воспользовался им, хотя "
        f"стоило. Первую отличают по артефакту аналитики того же Issue.\n"
    )


def _publish_dev_dialog_sync(issue: IssueInput, branch: str) -> None:
    """Опубликовать диалог разработки. Best-effort: исход прогона не подменяет.

    Сбой публикации артефакта не должен выглядеть как сбой разработки — иначе
    разбор начнут не с того места.
    """
    if not repowise.enabled():
        return
    text = _collect_dev_dialog(issue.repo, issue.issue_number, run_failed=False)
    path = DEV_DIALOG_PATH.format(n=issue.issue_number)
    try:
        if branch:
            github_client.push_artifacts_to_branch(
                issue.repo, branch, {path: text},
                f"docs(repowise): диалог разработки по issue #{issue.issue_number}")
        github_client.post_comment(
            issue.repo, issue.issue_number,
            f"## 🧭 Контекст из Repowise (разработка)\n\n"
            f"Диалог агента разработки с индексом кода — `{path}`"
            f"{f' в ветке `{branch}`' if branch else ''}.\n\n"
            f"<details><summary>Показать</summary>\n\n{text[:20000]}\n\n</details>")
    except Exception as exc:
        logger.warning("диалог разработки не опубликован (%s#%s): %s",
                       issue.repo, issue.issue_number, exc)


def _dev_tests(issue: IssueInput) -> str:
    """Прогон проверок проекта. Пусто в конфиге — шаг пропускается.

    Гоняется ЗДЕСЬ, до пуша: красный код не должен доезжать до PR, а на PR от
    агента CI может и не запуститься (события от токена Actions не порождают
    прогонов).
    """
    root, clone_dir = _dev_paths(issue)
    command = os.environ.get("DEVELOP_TEST_COMMAND", "").strip()
    if not command:
        # Пусто — шаг пропускается, и это НЕ «тесты прошли». Записываем
        # неизвестность явно: иначе слой саморефлексии засчитает пропуск как
        # успех, а свёртка сигналов начнёт хвалить прогоны, которых не было.
        _write_signal(root, "tests_passed", None)
        return "(проверки не заданы — DEVELOP_TEST_COMMAND пуст)"

    result = subprocess.run(command, shell=True, cwd=str(clone_dir),
                            capture_output=True, text=True, timeout=DEV_TESTS_TIMEOUT_SEC)
    out = ((result.stdout or "") + (result.stderr or ""))[-3000:]

    # Исход пишется ДО возможного исключения. Красный прогон — самый интересный
    # для разбора, и терять о нём запись значит собирать статистику только по
    # удачам.
    _write_signal(root, "tests_passed", result.returncode == 0)

    if result.returncode != 0:
        raise RuntimeError(f"проверки не прошли (код {result.returncode}):\n{out[-1500:]}")
    return out


def _dev_publish(issue: IssueInput, branch: str) -> int | None:
    """Коммит, пуш и PR — руками воркера, его токеном.

    Агенту токен не давали намеренно; здесь он уже не нужен агенту, а нужен
    контуру. Возвращает номер PR либо None, если агент ничего не изменил.
    """
    # Корень задачи нужен не только клону: туда перекладывается файл намерений,
    # чтобы пережить снятие из рабочего дерева.
    root, clone_dir = _dev_paths(issue)
    # Постановка — вход контура, а не часть правки. Она лежит в рабочем дереве, и
    # `git add -A` забирает её вместе с кодом: на живом прогоне это дало PR из
    # одного файла на 1721 строку — нашей же постановки. Хуже того, дифф из неё
    # обманывал гвард «изменений нет — открывать нечего», и PR открывался по
    # прогону, в котором агент не тронул ни одного файла.
    # Одна точка снятия на весь контур: перечень служебных файлов живёт в
    # `shared/develop.py`, а не переписывается в каждой функции заново.
    removed = develop.clear_service_files(clone_dir, keep_dir=root)
    if removed:
        logger.info("Develop %s#%s: сняты служебные файлы: %s",
                    issue.repo, issue.issue_number, ", ".join(removed))
    work = develop.work_branch(issue.issue_number)
    return github_client.publish_worktree(
        issue.repo, str(clone_dir), work,
        title=f"feat(#{issue.issue_number}): {issue.title}",
        body=develop.pr_body(issue.issue_number, branch=branch),
        message=f"feat(#{issue.issue_number}): реализация по системным требованиям",
        # `.harness/` — единственный служебный каталог, что НЕ снимается
        # (задача 7: контекст обязан дойти до PR). Он пишется в `_dev_prepare`
        # ДО прогона агента и потому существует независимо от того, тронул ли
        # агент код, — «пустой прогон» больше не значит «дифф пуст», если
        # эту проверку не поправить. Исключаем каталог из решения «есть ли
        # диф», а не из самого коммита: `git add -A` продолжает забирать его.
        ignore_for_empty_check=(f"{task_context.DIR}/**",),
        # M3 (ревью задачи 7): если `.gitignore` ЦЕЛЕВОГО репозитория содержит
        # `.harness/`, голый `git add -A` молча пропускает каталог — PR уйдёт
        # без контекста и без единого предупреждения. `force_include`
        # заставляет каталог попасть в коммит независимо от `.gitignore` и
        # подтверждает это фактом (деревом HEAD), а не только вызовом `add -f`.
        force_include=(task_context.DIR,),
    )


async def _dev_resolve_branch(issue: IssueInput, root_issue: int | None = None,
                              branch: str | None = None) -> str:
    """Выключатель разработки + ветка аналитики — общий вход в стадию.

    Раньше — две дословные копии, в `trigger_openhands_resolver` и в
    `dev_begin`: правка формата ветки или условия выключателя попала бы в
    одну и была бы забыта в другой, и линейный путь молча разошёлся бы с
    путём через дочерний воркфлоу.
    """
    if not develop.enabled():
        raise RuntimeError(
            "DEVELOP_ENABLED выключен — задача остаётся в очереди к разработчику")

    if branch is None:
        source = root_issue if root_issue else issue.issue_number
        branch = f"research/issue-{source}"
    if not await asyncio.to_thread(github_client.branch_exists, issue.repo, branch):
        # Путь бага: аналитики не было, и ветки с артефактами тоже. Штатно —
        # агент работает от тела Issue, но знать об этом должен явно.
        branch = ""
    return branch


async def _dev_dispatch_and_announce(issue: IssueInput, branch: str) -> None:
    """Режим `dispatch`: запуск в GitHub Actions + объявление человеку.

    Раньше — две дословные копии, в `trigger_openhands_resolver` и в
    `dev_dispatch`: правка аргументов `dispatch_inputs` или текста объявления
    попала бы в одну и была бы забыта в другой.
    """
    await asyncio.to_thread(
        github_client.dispatch_workflow,
        issue.repo, develop.workflow_file(), develop.workflow_ref(),
        develop.dispatch_inputs(issue.issue_number, branch=branch),
    )
    await _dev_announce(issue, branch,
                        where="запустил OpenHands Resolver в GitHub Actions")


@activity.defn
async def trigger_openhands_resolver(issue: IssueInput, root_issue: int | None = None, 
                                     branch: str | None = None) -> int | None:
    """Активность Develop: разработка по подготовленному Issue.

    Два режима (`shared/develop.py`). `local` — прогон одноразовым контейнером
    на своём сервере, контур замкнут внутри стенда. `dispatch` — прогон уезжает
    в GitHub Actions, для репозиториев без стенда.

    Возвращает номер PR (режим `local`) либо None (`dispatch`: результат
    придёт событием `pr-open`, прогон идёт на чужой стороне).
    
    ISSUE-113: для подзадачи плана использует ветку родителя, а не свою.
    `root_issue` — номер родительской задачи (если это подзадача плана),
    `branch` — готовая ветка (если вычислена в workflow).
    """
    branch = await _dev_resolve_branch(issue, root_issue=root_issue, branch=branch)

    if develop.mode() == develop.DISPATCH:
        await _dev_dispatch_and_announce(issue, branch)
        return None

    # Порядок не косметический: сначала клон и постановка — они единственные
    # могут не состояться до того, как что-либо сказано человеку.
    task, rule_ids = await _run_with_heartbeat(_dev_prepare, issue, branch,
                                               label="dev:prepare")
    logger.info("Develop %s#%s: постановка (%d симв.), правил подсыпано %d\n%s",
                issue.repo, issue.issue_number, len(task), len(rule_ids), task[:2000])
    await _dev_announce(issue, branch, where="запустил OpenHands на своём сервере")

    try:
        await _run_with_heartbeat(_dev_run_agent, issue, label="dev:agent")
    finally:
        # В finally, а не после: диалог полезнее всего при разборе упавшего
        # прогона, и терять его ровно в этом случае было бы худшим из исходов.
        await asyncio.to_thread(_publish_dev_dialog_sync, issue, branch)
    # Находки собираются ДО тестов и публикации: файл находок обязан исчезнуть
    # из рабочего дерева раньше коммита, иначе он уедет в PR — в ревью как мусор,
    # а на следующем круге правок агент прочитает свои прошлые находки как новые.
    await collect_dev_followups(issue)
    await _run_with_heartbeat(_dev_tests, issue, label="dev:tests")
    number = await _run_with_heartbeat(_dev_publish, issue, branch, label="dev:publish")

    if number is None:
        task, _clone = _dev_paths(issue)
        raise RuntimeError(develop.empty_run_reason(task))
    return number


# --- Разработка дочерним воркфлоу: шаги как отдельные активности ---
#
# Прежде вся разработка была ОДНОЙ активностью, и её ретрай повторял четыре
# внутренних шага целиком. На прогоне #39 падал только `git push` — уже после
# работы агента, — а заново шёл весь прогон, и контур трижды объявил о передаче
# задачи. Лечение снижением до одной попытки отменяло ретраи и там, где они
# уместны. Разрезав стадию на активности, ретраи возвращаются туда, где дёшевы.
#
# Приватные `_dev_*` НЕ трогаем: по ним идёт `trigger_openhands_resolver`, а по
# нему — реплей прогонов, начатых до выкладки, и прежний линейный сценарий.


@activity.defn
async def dev_begin(issue: IssueInput) -> DevelopPlan:
    """Решения входа в стадию: работаем ли вообще, в каком режиме и от чего.

    Собрано в один шаг намеренно. Выключатель и наличие ветки читаются из
    окружения и из GitHub — в воркфлоу так нельзя, там решение обязано быть
    детерминированным при реплее. Один вызов вместо трёх ещё и делает вход в
    стадию одной строкой в истории.
    """
    branch = await _dev_resolve_branch(issue)
    return DevelopPlan(mode=develop.mode(), branch=branch)


@activity.defn
async def dev_dispatch(issue: IssueInput, branch: str) -> None:
    """Режим `dispatch`: прогон уезжает в GitHub Actions.

    Своих шагов на этой стороне нет — отсюда и один вызов вместо цепочки.
    Результат придёт событием `pr-open` от внешнего агента.
    """
    await _dev_dispatch_and_announce(issue, branch)


@activity.defn
async def dev_prepare(issue: IssueInput, branch: str) -> int:
    """Шаг 1: свежий клон и постановка файлом. Возвращает длину постановки.

    Длину, а не текст: постановка уже лежит в `.task.md` в общем томе, и
    дублировать её в payload Temporal незачем. В лог она уходит целиком — там
    её и смотрят, когда разбираются «почему агент сделал не то».
    """
    task, rule_ids = await _run_with_heartbeat(_dev_prepare, issue, branch,
                                               label="dev:prepare")
    logger.info("Develop %s#%s: постановка (%d симв.), правил подсыпано %d\n%s",
                issue.repo, issue.issue_number, len(task), len(rule_ids), task[:2000])
    return len(task)


@activity.defn
async def dev_announce(issue: IssueInput, branch: str) -> None:
    """Шаг 2: метка и комментарий о начале работы — best-effort.

    Отдельным шагом, а не частью прогона: объявление обязано случиться ПОСЛЕ
    успешного клона (иначе контур скажет о работе, которая не началась) и ДО
    прогона агента (иначе человек двадцать минут не знает, что задача в работе).
    """
    await _dev_announce(issue, branch, where="запустил OpenHands на своём сервере")


@activity.defn
async def dev_run_agent(issue: IssueInput) -> None:
    """Шаг 3: прогон одноразового контейнера агента.

    Возврата нет: хвост вывода уходит в лог воркера на любом исходе
    (`_dev_run_agent`), а в историю воркфлоу ему не место — это килобайты
    текста на прогон.
    """
    await _run_with_heartbeat(_dev_run_agent, issue, label="dev:agent")


@activity.defn
async def dev_empty_run_reason(issue: IssueInput) -> str:
    """Почему прогон агента не дал изменений — по следам самого раннера.

    Отдельной активностью, потому что воркфлоу файловой системы не видит, а
    признак лежит именно там: каталог событий разговора OpenHands. Пуст —
    агент не сделал ни одного хода, то есть отказало окружение, а не работа
    агента. Это разные новости и зовут человека в разные места.
    """
    task, _clone = _dev_paths(issue)
    return develop.empty_run_reason(task)


@activity.defn
async def dev_followups(issue: IssueInput) -> list[str]:
    """Шаг 4: находки агента — строками в секцию GROW тела родителя.

    Идёт ДО тестов и публикации: файл находок обязан исчезнуть из рабочего
    дерева раньше коммита, иначе он уедет в PR — в ревью как мусор, а на
    следующем круге правок агент прочитает свои прошлые находки как новые.
    """
    return await collect_dev_followups(issue)


@activity.defn
async def dev_tests(issue: IssueInput) -> None:
    """Шаг 5: проверки проекта — до пуша.

    Красный код не должен доезжать до PR, а на PR от агента CI может и не
    запуститься: события от токена Actions не порождают прогонов.
    """
    await _run_with_heartbeat(_dev_tests, issue, label="dev:tests")


@activity.defn
async def dev_publish(issue: IssueInput, branch: str) -> int | None:
    """Шаг 6: коммит, пуш и PR — руками воркера, его токеном.

    `None` — агент не изменил ни одного файла. Это не сбой шага, а его
    результат; решение, что делать с пустым прогоном, принимает воркфлоу.
    """
    return await _run_with_heartbeat(_dev_publish, issue, branch, label="dev:publish")


@activity.defn
async def capture_episode(issue: IssueInput, branch: str,
                          pr_number: int | None) -> bool:
    """Шаг 7: запись об итерации — слою саморефлексии.

    Горячий такт: фиксируется то, что уже известно коду, БЕЗ обращения к
    модели. Оценивать в этот момент нечего — фактов об исходе ещё нет, их
    соберёт отложенный проход рефлексии, когда пул-реквест доедет до слияния
    или будет закрыт.

    Намерение агента берётся из файла `.reflect.md`, если тот его написал.
    Отсутствие файла НЕ срывает шаг: запись уходит без намерения, а сигналы и
    дифф остаются. Требовать от агента файл под угрозой падения стадии значило
    бы обменять работающую разработку на полноту записи.

    Возврат — успех отправки. Неуспех не роняет прогон: слой опционален.
    """
    if not memory.enabled():
        return False

    root, clone_dir = _dev_paths(issue)
    # Из КОРНЯ: к этому моменту публикация уже сняла файл из рабочего дерева и
    # переложила сюда. Чтение из клона давало пустое намерение при исправном
    # агенте — файл удалялся за секунды до чтения.
    reflect = _read_reflect_note(root) or _read_reflect_note(clone_dir)

    episode = {
        "run_id": activity.info().workflow_id,
        "repo": issue.repo,
        "issue": issue.issue_number,
        # Текст задачи. Без него судья слоя видит только числа — и на живом
        # прогоне #94 поставил 0.93 правке в две строки на задачу «описать
        # поведение функций»: слито, тесты зелёные, круг правок один. Числа
        # хорошие, работа не сделана. Соразмерность правки замыслу проверяется
        # только против постановки.
        #
        # Режется на стороне отправителя: гнать по сети и хранить в памяти
        # десятки килобайт постановки незачем, слой всё равно возьмёт начало.
        "task_title": issue.title,
        "task_body": (issue.body or "")[:TASK_BODY_LIMIT] or None,
        "phase": "develop",
        "agent": memory.DEVELOP,
        "branch": develop.work_branch(issue.issue_number),
        "pr_number": pr_number,
        "model": os.environ.get("DEVELOP_MODEL", "").strip() or "openai/glm-4.6",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "rules_injected": _read_injected_rules(root),
        # Число попыток активности: правило контура «Attempt > 1 у долгой
        # активности — уже беда» до сих пор нигде не читалось кодом.
        #
        # Плюс всё, что контур измерил по ходу прогона: результат тестов и
        # прочее. Измерение из первых рук точнее восстановленного постфактум.
        # `control` ставится ЯВНО, а не выводится из пустого перечня правил:
        # пустым он бывает и когда слой был недоступен в момент подготовки.
        # «Правил не дали нарочно» и «правил не досталось» — разные вещи, и
        # смешивать их значит подмешивать в контрольную выборку брак.
        "artifacts": {"activity_attempt": activity.info().attempt,
                      "control": memory.control_arm(issue.issue_number),
                      **_read_signals(root)},
        **reflect,
    }
    ok = await asyncio.to_thread(memory.put_episode, episode)
    if ok:
        logger.info("Develop %s#%s: запись об итерации отдана слою памяти",
                    issue.repo, issue.issue_number)
    return ok


def _read_reflect_note(clone_dir: Path) -> dict:
    """Разобрать `.reflect.md`, если агент его написал.

    Формат нарочно простой — заголовки второго уровня «Намерение»,
    «Допущения», «Сомнения». Требовать от агента строгий JSON значило бы
    получать пустой файл там, где сейчас получается частичный.
    """
    path = clone_dir / REFLECT_NOTE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    buckets: dict[str, list[str]] = {}
    current = None
    for line in text.split("\n"):
        head = line.strip().lstrip("#").strip().lower()
        if line.startswith("#") and head:
            current = head
            buckets[current] = []
        elif current:
            item = line.strip().lstrip("-").strip()
            if item:
                buckets[current].append(item)

    def pick(*names: str) -> list[str]:
        for n in names:
            for key, items in buckets.items():
                if key.startswith(n):
                    return items
        return []

    intent = pick("намерение", "intent")
    return {
        "intent": " ".join(intent) or None,
        "assumptions": pick("допущения", "assumptions"),
        "uncertainty": pick("сомнения", "uncertainty"),
        "alternatives_rejected": pick("отброшен", "alternatives"),
    }


async def collect_dev_followups(issue: IssueInput) -> list[str]:
    """Находки шага — строками в секцию GROW тела родителя, а не новыми Issue.

    Прежде каждая находка заводила отдельный Issue: он проходил триаж,
    поднимал свой вечный цикл и вставал в общую очередь контура — 221 из 267
    открытых задач организации заведены контуром, и находки составляют
    большую их часть. Теперь находка ждёт гейта приёмки строкой в секции GROW
    тела родителя; Issue из неё заведёт человек, если решит — и только после
    того, как MVP подтверждён (Task 11).

    Агент по-прежнему оставляет находки файлом: `gh` и GITHUB_TOKEN ему не
    дают намеренно, это весь смысл его изоляции — он исполняет чужой код. Файл
    снимается ПОСЛЕ того, как находки долетели до GROW (или сразу, если
    парсить оказалось нечего) — а не заранее. Снятый до сетевой записи файл
    убивал бы повтор активности так же, как сама неудавшаяся запись, только
    тише: следующая попытка не находила бы файл и молча докладывала бы «находок
    нет» вместо честного повтора (ревью, находка 3). Уехать в PR он всё равно
    не может, даже если так и останется лежать до конца прогона: `_dev_publish`
    снимает любой служебный файл через `develop.clear_service_files` перед
    коммитом, независимо от исхода этой функции.

    Накопление прежнего содержимого блока — присоединением целой строки
    записи к целому прежнему содержимому, без построчного разбора. Раньше
    накопление читало прежнее содержимое и оставляло только строки,
    начинающиеся с `- [` — многострочная находка занимает несколько
    физических строк, и её продолжение под это правило не подходило: со
    второго прогона от неё оставался только заголовок (ревью, находка 1). По
    той же причине терялся и любой текст, дописанный в блок человеком. Здесь
    прежнее содержимое — уже готовый текст блока, и трогать в нём нечего:
    новые записи дописываются к нему целиком, каким бы оно ни было.

    Запись в GROW — best-effort, как раньше было создание Issue: прогон
    разработки уже состоялся, и находка не должна ронять шаг целиком.
    `issue_blocks.write` намеренно отказывает `ValueError`, если содержимое
    похоже на маркер блока — а находка приходит от модели и может дословно
    процитировать разметку (например, разбирая баг в самом `issue_blocks.py`)
    — или если тело Issue уже повреждено. Такой отказ, как и любой сетевой
    сбой чтения/записи тела, ловится здесь: находка не засчитывается
    записанной на ЭТОМ прогоне, файл остаётся на диске для следующей попытки,
    а сам отказ уходит и в лог, и в Sentry (`capture_followups_failure`) —
    иначе о молчаливой потере узнают только по stdout контейнера, который
    никого не будит (ревью, находка 4).
    """
    _, clone_dir = _dev_paths(issue)
    path = clone_dir / develop.FOLLOWUPS_FILE
    if not path.exists():
        return []  # «не нашёл» — законный исход, комментировать нечего

    try:
        items = develop.parse_followups(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — разбор находок не ломает разработку
        logger.warning("не разобрал %s по %s#%s: %s",
                       develop.FOLLOWUPS_FILE, issue.repo, issue.issue_number, exc)
        items = []
    if not items:
        path.unlink(missing_ok=True)  # нечего сохранять, нечего и повторять
        return []

    try:
        body = await asyncio.to_thread(github_client.get_issue_body,
                                       issue.repo, issue.issue_number)
        previous = issue_blocks.read(body, issue_blocks.GROW) or ""

        # Извлечём уже существующие заголовки из прежней секции GROW
        existing_titles = set()
        if previous.strip():
            for line in previous.split('\n'):
                # Формат: `- [ ] Заголовок — тело` или `- [ ] Заголовок`
                if line.strip().startswith('- [ ] '):
                    # Вытаскиваем заголовок до первого ` — ` (если есть) или до конца строки
                    rest = line.strip()[6:]  # убираем '- [ ] '
                    title = rest.split(' — ', 1)[0].strip()
                    if title:
                        existing_titles.add(title)

        # Фильтруем items: оставляем только новые (не в existing_titles)
        new_items = [item for item in items if item['title'] not in existing_titles]

        # Формируем строки только для новых записей
        lines = [f"- [ ] {item['title']} — {item.get('body', '').strip()}" for item in new_items]

        if lines:  # Только если есть новые записи
            new_block = "\n".join(lines)
            content = (f"{previous}\n{new_block}" if previous.strip()
                      else f"## GROW — после прохождения HowToDemo\n\n{new_block}")
            await asyncio.to_thread(
                github_client.update_issue_body, issue.repo, issue.issue_number,
                issue_blocks.write(body, issue_blocks.GROW, content))
    except Exception as exc:  # noqa: BLE001 — запись находок не ломает разработку
        logger.warning("не записал находки по %s#%s в секцию %s: %s",
                       issue.repo, issue.issue_number, issue_blocks.GROW, exc)
        sentry_setup.capture_followups_failure(issue, type(exc).__name__, str(exc))
        return []
    path.unlink(missing_ok=True)  # находки доехали — теперь их можно снять
    return [item["title"] for item in new_items]


async def _dev_announce(issue: IssueInput, branch: str, *, where: str) -> None:
    """Метка и комментарий о начале работы — best-effort и ОДИН раз на задачу.

    Прогон к этому моменту начался; падать из-за непоставленной метки значило
    бы отправить в `failed` задачу, которая на самом деле в работе.

    Повторный вход в передачу (перезапуск активности, второе решение человека)
    не должен давать второго объявления: на живом прогоне #39 их набралось три
    штуки подряд, и по треду нельзя было понять, идёт одна работа или три.
    Признак — метка `in-development`: её ставит эта же функция строкой ниже, и
    снимает смена фазы (`set_phase`), то есть она держится ровно столько,
    сколько длится передача.
    """
    try:
        already = await asyncio.to_thread(
            github_client.get_issue, issue.repo, issue.issue_number)
        names = [label["name"] for label in already.get("labels", [])]
        if develop.IN_DEVELOPMENT_LABEL in names:
            logger.info("Develop %s#%s: объявление уже сделано — повторно не пишу",
                        issue.repo, issue.issue_number)
            return
    except Exception as exc:
        # Не прочитали состояние — объявляем. Лишний комментарий хуже молчания
        # ровно настолько, насколько молчание хуже дубля: человек должен знать,
        # что работа идёт.
        logger.warning("Develop %s#%s: не прочитал метки (%s) — объявляю",
                       issue.repo, issue.issue_number, exc)
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


@activity.defn
async def pr_is_merged(repo: str, pr_number: int) -> bool:
    """Влит ли PR. Спрашиваем сам PR, а не полезную нагрузку закрытия Issue.

    У `issues.closed` признака слияния нет: `state_reason` одинаков и когда
    Issue закрыл `Closes #N` во влитом PR, и когда человек закрыл его руками
    «как выполненное». Доставки `issues.closed` и `pull_request.closed` идут
    наперегонки, поэтому ждать второй, чтобы истолковать первую, — гонка.

    PR своё состояние знает точно и в любой момент, а номер у цикла уже есть:
    он запомнил его, когда PR открылся. Один вызов на закрытие — цена
    честной фазы.
    """
    pr = await asyncio.to_thread(github_client.get_pull, repo, pr_number)
    # `merged` булев и появляется только у влитого PR. `state == "closed"` для
    # этого не годится: закрытый без слияния PR тоже `closed`.
    return bool(pr.get("merged"))


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
    _handover_to_runner(root)


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

    # Правила организации для роли РАЗРАБОТКИ, а не ревью. Круг правок — это
    # агент, который пишет код: он читает замечания и меняет файлы. Правила
    # роли `review` описывают, как формулировать замечание, — исполнителю они
    # бесполезны, а нужные ему (как писать код в этой организации) не доезжали
    # вовсе. Блок дописывается к постановке здесь, а не в
    # `pr_closing.build_task`: тот модуль намеренно чистый и в сеть не ходит.
    org_rules = memory.rules(memory.DEVELOP, repo=repo, query=review[:500])
    if org_rules.text:
        task += "\n" + org_rules.text

    await _run_with_heartbeat(_prfix_prepare, repo, pr_number, branch, task,
                              label="prfix:prepare")

    slug = pr_closing.task_slug(repo, pr_number)
    await asyncio.to_thread(_reap_runner, slug)
    command = develop.runner_command(
        slug, image=develop.runner_image(),
        volume=develop.workspace_volume(), mount=develop.workspace_mount(),
        network=develop.proxy_network(), home=_runner_home(slug))
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
    # Ни разбор, ни постановка круга не уезжают в коммит: они живут в
    # комментарии PR, а не в коде.
    #
    # Постановка опаснее разбора. Она меняется на КАЖДОМ круге — номер круга,
    # накопленный текст ревью, — поэтому пуш всегда видел дифф и всегда
    # докладывал «правки внесены». Исход «замечаний нет, PR готов к merge»
    # становился недостижим: цикл сжигал все три круга и отдавал PR человеку, а
    # настоящий вердикт агента терялся.
    develop.clear_service_files(clone_dir)

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
    await asyncio.to_thread(
        github_client.post_comment, repo, pr_number,
        pr_closing.exhausted_comment(pr_closing.max_rounds(), rounds_done=rounds))
    await asyncio.to_thread(github_client.add_label, repo, pr_number,
                            pr_closing.NEEDS_HUMAN_PR)


# --- Приём комментария: реакция раньше любой работы ---

@activity.defn
async def ack_comment_seen(ack: CommentAckInput) -> None:
    """«Система увидела комментарий» — реакция `eyes` до разбора и до пайплайнов.

    Ставится на КАЖДЫЙ человеческий комментарий, а не только на команду: с
    телефона иначе не отличить «не доехало» от «думает». Дальше вход может
    оказаться командой, репликой в цикл уточнений или ничем (живого цикла нет —
    комментарий best-effort и тихо теряется, webhook/main.py); реакция стоит в
    любом из этих исходов.

    Реакция идемпотентна на стороне GitHub: повторная доставка того же
    комментария упирается в тот же workflow id, а совпавший гонкой второй POST
    возвращает 200 на уже поставленную реакцию.
    """
    await asyncio.to_thread(
        github_client.add_reaction, ack.repo, ack.comment_id, "eyes")


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
    exc_type, _, message = reason.partition(": ")
    event_id = await asyncio.to_thread(
        sentry_setup.capture_analysis_failure,
        analyze, exc_type or "unknown", message or reason)
    await asyncio.to_thread(
        github_client.post_comment,
        analyze.repo,
        analyze.issue_number,
        f"⚠️ Автономный анализ не удался: {reason}\n\n"
        "Прогон не повторяется автоматически (он недетерминирован и дорог). "
        "Запустить заново — командой `/analyze`."
        + sentry_setup.debug_reference(event_id),
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

# Текстовые форматы, которые пишет пайплайн БФТ: документ и отчёты (md), таблицы
# требований и персон (csv), диаграммы плана демонстрации (puml). Список — не
# запрет на новое, а граница возможностей транспорта: Contents API принимает
# текст, и всё, что им не является, обязано быть отброшено громко.
BFT_TEXT_SUFFIXES = frozenset({".md", ".csv", ".puml", ".txt", ".json", ".yaml", ".yml"})

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

    # Трекер диалога — до первой стадии: хуки ставятся в клон, а он создаётся
    # заново на каждый прогон.
    _enable_entire(clone_dir)
    if req.session_id:
        _resume_entire_session(req.repo, clone_dir, req.session_id)

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
    if requires:
        # `requires` — список путей через запятую (см. `deep_stages`): каждый
        # проверяется отдельно, иначе весь список читался бы как один
        # несуществующий путь и стадия падала бы даже при готовых артефактах.
        missing = [item for item in requires.split(",")
                  if not (Path(clone_dir) / item).exists()]
        if missing:
            raise RuntimeError(
                f"нет входа {','.join(missing)} (стадия-предшественник не отработала?) — повтори /bft-deep"
            )
    return clone_dir


def _collect_bft_artifacts(clone_dir: str, issue_number: int) -> dict[str, str]:
    """Всё, что пайплайн положил в каталог эпика: документ и служебные артефакты.

    Забираем каталогом, а не списком имён: состав артефактов задаёт скилл, и
    зашитый перечень разъехался бы с ним при первом же его обновлении, молча
    теряя файлы. По той же причине берём не один `*.md`: помимо документа скилл
    пишет csv с требованиями и персонами и выносит диаграммы в `.puml` — забрав
    только markdown, мы опубликовали бы документ со ссылками в никуда.

    Расширение всё же проверяем: публикация идёт через Contents API, который
    принимает ТЕКСТ, и попытка прочитать бинарь (png, docx) упала бы на
    UnicodeDecodeError посреди уже начатой публикации. Такой файл пропускаем
    громко — тихо потерянный артефакт как раз и есть то, от чего этот код
    защищает.
    """
    root = Path(clone_dir) / bft.epic_dir(issue_number)
    files: dict[str, str] = {}
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in BFT_TEXT_SUFFIXES:
            logger.warning("артефакт БФТ %s пропущен: не текстовый формат", path.name)
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("артефакт БФТ %s не прочитан: %s", path.name, exc)
            continue
        files[str(path.relative_to(clone_dir))] = content
    return files


@activity.defn
async def prepare_bft_workspace(req: BftRequest) -> None:
    """Стадия 0 глубокого прогона: клон (с веткой прошлого БФТ, если есть),
    repomix и постановка файлом. Идемпотентна — сносит остаток и строит заново."""
    await _run_with_heartbeat(_build_bft_workspace, req, label="bft-preparing")


# Скиллы и команды bft-writer лежат в ПОЛЬЗОВАТЕЛЬСКОМ ~/.claude образа воркера
# (см. worker/Dockerfile): `claude -p` запускается с cwd внутри клона чужого
# репозитория, и проектный .claude там был бы чужим. Прямому вызову те же файлы
# нужны из процесса — путь один и тот же.
CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", "/root/.claude"))

# Исходники, на которые вешаются якоря ранга R1. Список задан явно: якорь обязан
# указывать на строку файла, который модель ВИДЕЛА, иначе ссылка недоказуема.
BFT_SOURCE_GLOBS = ("src/*", "*.md", "package.json")
BFT_SOURCE_LIMIT_BYTES = 24_000  # крупные файлы в промпт не тащим


def _bft_sources(clone_dir: str) -> dict[str, str]:
    """Файлы репозитория для якорей R1 — путь → содержимое."""
    root = Path(clone_dir)
    out: dict[str, str] = {}
    for pattern in BFT_SOURCE_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path.stat().st_size > BFT_SOURCE_LIMIT_BYTES:
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".bft/"):
                continue  # артефакты пайплайна подаются отдельно, это не исходники
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _numbered(text: str) -> str:
    """С номерами строк: якорь ранга R1 указывает на строку, а не на файл."""
    return "\n".join(f"{i:4d}| {line}" for i, line in enumerate(text.splitlines(), 1))


def _bft_stage_system(stage_name: str, role_tail: str) -> str:
    """Системный промпт стадии — та же инструкция, что читает `claude -p`."""
    parts = [
        "Ты — исполнитель стадии пайплайна bft-writer. Ниже инструкция команды и "
        "ресурсы скилла. Следуй им буквально: порядок разделов, типы требований, "
        "якоря и запреты — проверяемые гейты, а не рекомендации.\n\n" + role_tail,
    ]
    command = CLAUDE_HOME / "commands" / f"bft-{stage_name}.md"
    if command.exists():
        parts.append(f"# Инструкция команды /bft-{stage_name}\n\n"
                     + command.read_text(encoding="utf-8"))
    skill = CLAUDE_HOME / "skills" / "bft-writer"
    for rel in ("SKILL.md", "resources/bft_standards.md", "examples/ideal_bft.md",
                "examples/golden_bft_example.md", "resources/anchor_rules.md",
                "resources/catwoe.md", "resources/writing_style.md",
                "resources/review_feedback.md"):
        path = skill / rel
        if path.exists():
            parts.append(f"# {rel}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def _bft_stage_inputs(clone_dir: str, issue_number: int,
                      sources: dict[str, str]) -> str:
    """Вход стадии: артефакты предшественников плюс исходники с номерами строк.

    Список шире, чем `requires` в `deep_stages`: там записан лишь артефакт, без
    которого стадию нельзя начинать, а работает она по всем. Агент дочитывал
    остальное сам — прямому вызову эту зависимость надо назвать (#78, находка D).
    """
    root = Path(clone_dir)
    parts = []
    for name in ("po-statement.md", "bft-context-pack.md", "problem.md", "concept.md"):
        path = root / bft.artefacts_dir(issue_number) / name
        if path.exists():
            parts.append(f"# Вход: {name}\n\n{path.read_text(encoding='utf-8')}")
    for rel, body in sources.items():
        parts.append(f"# Исходник: {rel} (с номерами строк)\n\n"
                     f"```\n{_numbered(body)}\n```")
    return "\n\n---\n\n".join(parts)


ENTIRE_TIMEOUT_SEC = 120


def _entire(clone_dir: str, *args: str, check: bool = False):
    """Вызов `entire` в каталоге задачи.

    Трекер вспомогательный: его отказ не должен ронять прогон, который в
    остальном идёт нормально. Поэтому по умолчанию `check=False`, а вызывающий
    смотрит на `returncode`, если исход ему важен.
    """
    return subprocess.run(["entire", *args], cwd=clone_dir, capture_output=True,
                          text=True, timeout=ENTIRE_TIMEOUT_SEC, check=check)


def _enable_entire(clone_dir: str) -> None:
    """Включить запись диалога стадий в клоне задачи.

    `--agent claude-code` переводит команду в неинтерактивный режим: TTY в
    контейнере нет, а без флага она ушла бы в диалоговый мастер и повисла до
    таймаута. Хуки ставятся в клон, поэтому включать надо на каждый прогон —
    каталог создаётся заново.

    Флаг `--agent-help-skill` НЕ используем намеренно: он кладёт свой скилл по
    тому же пути `.claude/skills/entire/SKILL.md` — но уже в КЛОН, а проектный
    уровень перекрывает пользовательский. Наш скилл (`.claude/skills/entire/`
    в образе) содержит то же указание читать `entire agent-help` плюс контекст
    контура: когда трекер звать, что он не видит и чем чекпоинты отличаются от
    артефактов. Их тринадцать строк это бы затёрли.

    Молча продолжаем при любом отказе: без трекера прогон соберёт БФТ ровно так
    же, просто без записи диалога. Менять исход из-за вспомогательного слоя
    нельзя.
    """
    try:
        result = _entire(clone_dir, "enable", "--agent", "claude-code")
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("entire не включён (%s) — прогон без записи диалога", exc)
        return
    if result.returncode != 0:
        logger.warning("entire не включён (код %s): %s", result.returncode,
                       (result.stderr or result.stdout or "").strip()[:300])


def _entire_session(clone_dir: str) -> tuple[str, str]:
    """(id сессии, ветка чекпоинтов) — то, чем человек продолжит прогон.

    Пустые строки, если трекера нет или сессия не завелась: комментарий тогда
    просто не обещает продолжения по id.
    """
    try:
        listing = _entire(clone_dir, "session", "list")
        refs = subprocess.run(["git", "for-each-ref", "--format=%(refname)"],
                              cwd=clone_dir, capture_output=True, text=True,
                              timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("сессия entire не прочитана: %s", exc)
        return "", ""
    return (bft.parse_session_id(listing.stdout or ""),
            bft.parse_session_branch(refs.stdout or ""))


def _push_entire_branch(repo: str, clone_dir: str, session_branch: str) -> None:
    """Ветка чекпоинтов уезжает в origin рядом с артефактами.

    Иначе запись диалога живёт только в каталоге, который снимут вместе с
    прогоном, — то есть ровно там, где её и теряли.
    """
    if not session_branch:
        return
    try:
        token = github_client.auth_token(repo)
        env = {
            **os.environ,
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0":
                "!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f",
            "GIT_CONFIG_KEY_1": "safe.directory",
            "GIT_CONFIG_VALUE_1": clone_dir,
            "GH_PUSH_TOKEN": token,
        }
        result = subprocess.run(
            ["git", "-C", clone_dir, "push", "-f", "origin",
             f"{session_branch}:{session_branch}"],
            env=env, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0:
            logger.warning("ветка сессии не отправлена: %s",
                           (result.stderr or "").strip()[:300])
    except Exception as exc:  # noqa: BLE001 — вспомогательный слой
        logger.warning("ветка сессии не отправлена: %s", exc)


def _resume_entire_session(repo: str, clone_dir: str, session_id: str) -> None:
    """Поднять диалог прошлого прогона по id из `/bft-deep <id>`.

    Ветку чекпоинтов забираем из origin, потому что писал её ДРУГОЙ прогон и в
    свежем клоне её нет. Дальше `entire session resume` возвращает контекст той
    сессии — стадии видят, о чём уже говорили, а не начинают знакомство заново.

    Отказ не останавливает прогон: артефакты лежат в ветке БФТ, и без диалога
    он соберётся — просто без памяти о прошлых рассуждениях. Сказать об этом в
    лог обязательно, иначе «продолжение» тихо превратится в новый прогон.
    """
    try:
        fetched = subprocess.run(
            ["git", "-C", clone_dir, "fetch", "-q", "origin",
             "+refs/heads/entire/*:refs/heads/entire/*"],
            capture_output=True, text=True, timeout=120, check=False)
        if fetched.returncode != 0:
            logger.warning("ветки сессий не забраны: %s",
                           (fetched.stderr or "").strip()[:200])
        result = _entire(clone_dir, "session", "resume", session_id)
        if result.returncode != 0:
            logger.warning(
                "сессия %s не поднята (код %s): %s — прогон пойдёт без её контекста",
                session_id, result.returncode,
                (result.stderr or result.stdout or "").strip()[:300])
        else:
            logger.info("БФТ %s: продолжаю сессию %s", repo, session_id)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("сессия %s не поднята: %s", session_id, exc)


def _append_dialog(clone_dir: str, issue_number: int, entry: str) -> None:
    """Дописать строку в журнал прогона — best-effort.

    Журнал вспомогательный: уронить из-за него стадию, которая отработала,
    значит поменять настоящий результат на запись о нём.
    """
    try:
        path = Path(clone_dir) / bft.dialog_log_path(issue_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(bft.DIALOG_LOG_HEADER, encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        logger.warning("журнал прогона не дописан: %s", exc)


def _bft_direct_draft(req: BftRequest, clone_dir: str) -> str:
    """Стадия `draft` двумя вызовами модели вместо агента.

    Первый вызов собирает каскад требований и якоря структурой, второй рендерит
    из них документ. Между ними — программная проверка полноты и якорей: ради
    неё разбиение и сделано, одним ответом проверять нечего.
    """
    model = os.environ.get("BFT_DIRECT_MODEL", "glm-4.6")
    sources = _bft_sources(clone_dir)
    line_counts = {rel: len(body.splitlines()) for rel, body in sources.items()}
    inputs = _bft_stage_inputs(clone_dir, req.issue_number, sources)
    issue = req.issue_number

    system = _bft_stage_system(
        "draft", "СЕЙЧАС ты собираешь ТОЛЬКО каскад требований и таблицу якорей. "
                 "Документ не пишешь — его соберёт следующий шаг.")
    cascade_task = (
        f"{inputs}\n\n---\n\n# Задание\n\n"
        f"Собери каскад требований БФТ для эпика issue-{issue} и таблицу якорей.\n\n"
        "Разворачивай, а не сворачивай: каждый пункт TOBE из problem.md, каждое "
        "уточнение постановки, каждая ветка сценария демонстрации, каждый экран "
        "актора, каждая измеримая характеристика — отдельное требование.\n\n"
        "Якоря: As-Is-факт → `файл:строки` из исходников выше (ранг R1, тип "
        "«Код»); требование постановки → `po-statement.md:N` (R2, «Постановка»); "
        "решение концепта → `concept.md` (R2, «Решение»). To-Be на код НЕ "
        "якорится.\n\n"
        "Нижняя граница: "
        + ", ".join(f"{k} ≥ {v}" for k, v in bft.CASCADE_FLOOR.items())
        + f", якорей ≥ {bft.ANCHOR_FLOOR}.\n\n"
        f"Верни ТОЛЬКО JSON по схеме:\n{bft.CASCADE_SCHEMA}")

    started = time.monotonic()
    cascade = bft.parse_cascade(llm.complete(system, cascade_task, model=model))
    _append_dialog(clone_dir, issue, bft.render_dialog_entry(
        stage="draft", actor=f"прямой вызов ({model})", step="каскад требований",
        outcome="готово", elapsed=time.monotonic() - started,
        detail=f"требований {len(cascade.get('requirements') or [])}, "
               f"якорей {len(cascade.get('anchors') or [])}"))
    for _ in range(BFT_TOP_UP_ATTEMPTS):
        gaps = bft.cascade_gaps(cascade, line_counts)
        if not gaps:
            break
        logger.info("БФТ %s#%s: добор каскада — %s", req.repo, issue, "; ".join(gaps))
        _append_dialog(clone_dir, issue, bft.render_dialog_entry(
            stage="draft", actor=f"прямой вызов ({model})", step="добор каскада",
            outcome="добор", detail="; ".join(gaps)))
        top_up = (f"{inputs}\n\n---\n\n# Уже собрано\n\n```json\n"
                  + json.dumps(cascade, ensure_ascii=False, indent=1) + "\n```\n\n"
                  "# Чего не хватает\n\n- " + "\n- ".join(gaps) + "\n\n"
                  "Верни ПОЛНЫЙ JSON той же схемы: собранное дословно плюс "
                  "недостающее. Ничего не удаляй и не переформулируй.")
        cascade = bft.parse_cascade(llm.complete(system, top_up, model=model))

    left = bft.cascade_gaps(cascade, line_counts)
    if left:
        # Не падаем: неполный каскад — это плохой документ, а не сорванный
        # прогон, и человеку полезнее увидеть его с честной пометкой в логе,
        # чем не увидеть ничего. Полнота проверяется стадией `validate`.
        logger.warning("БФТ %s#%s: каскад неполон после добора — %s",
                       req.repo, issue, "; ".join(left))

    system2 = _bft_stage_system(
        "draft", "СЕЙЧАС ты рендеришь документ из УТВЕРЖДЁННОГО каскада. "
                 "Требования и якоря уже собраны: переносишь их все, ничего не "
                 "теряя и не добавляя новых идентификаторов.")
    render_task = (
        f"{inputs}\n\n---\n\n# Утверждённый каскад\n\n```json\n"
        + json.dumps(cascade, ensure_ascii=False, indent=1) + "\n```\n\n"
        f"# Задание\n\nСобери чистовик БФТ issue-{issue} по корп-шаблону. Все "
        "требования каскада обязаны попасть в свои разделы, все якоря — в раздел "
        "«Якоря истины» таблицей `Факт | Источник | Ранг | Тип`.\n\n"
        "Файловых инструментов нет: ты не записываешь файл, а выводишь его "
        "содержимое целиком.\n\n"
        f"YAML-шапка ровно такая:\n```\n---\nEpic: issue-{issue}\n"
        "Название: <название>\nСтатус: Черновик\nДата: <сегодня>\n"
        "Автор: bft-draft\nВерсия: 1.0\n---\n```\n\n"
        "Заголовки разделов — только `##`. Ответ начинается со строки `---` и "
        "заканчивается последней строкой таблицы якорей, без обрамляющих "
        "```-блоков и без фраз до или после.")

    started = time.monotonic()
    document = llm.complete(system2, render_task, model=model)
    _append_dialog(clone_dir, issue, bft.render_dialog_entry(
        stage="draft", actor=f"прямой вызов ({model})", step="рендер документа",
        outcome="готово", elapsed=time.monotonic() - started,
        detail=f"{len(document)} символов"))
    return document


BFT_TOP_UP_ATTEMPTS = 2


async def _validate_stage_anchors(clone_dir: str, issue_number: int, 
                                  stage_name: str) -> list[str]:
    """Проверка якорей R1 в документе после draft/validate (Issue #78, находка B).
    
    Извлекает каскад из документа и проверяет, что все якоря R1 указывают на
    существующие строки существующих файлов.
    """
    # Для draft проверяем документ, для validate - validation.md
    if stage_name == "draft":
        doc_path = Path(clone_dir) / bft.document_path(issue_number)
    else:  # validate
        doc_path = Path(clone_dir) / bft.artefacts_dir(issue_number) / "validation.md"
    
    if not doc_path.exists():
        return [f"документ {doc_path.name} не найден"]
    
    # Пытаемся извлечь каскад из документа
    content = doc_path.read_text(encoding="utf-8")
    cascade = bft.extract_cascade_from_document(str(doc_path))
    
    if not cascade:
        # Если каскад не найден в документе, это не ошибка для validate
        # (там может быть только текст вердикта), но для draft это проблема
        if stage_name == "draft":
            return ["каскад требований не найден в документе"]
        return []
    
    # Получаем исходники для проверки строк
    sources = _bft_sources(clone_dir)
    line_counts = {rel: len(body.splitlines()) for rel, body in sources.items()}
    
    # Проверяем якори
    return bft.cascade_gaps(cascade, line_counts)


async def _validate_formal_gates(clone_dir: str, issue_number: int) -> list[str]:
    """Проверка формальных гейтов валидации (Issue #78, находка E).
    
    Проверяет документ БФТ на соответствие формальным требованиям:
    - отсутствие запрещённых разделов
    - правильность идентификаторов
    - непустые связи
    - НФТ с числовыми значениями
    - отсутствие битых ссылок
    """
    doc_path = Path(clone_dir) / bft.document_path(issue_number)
    if not doc_path.exists():
        return [f"документ БФТ не найден: {doc_path}"]
    
    content = doc_path.read_text(encoding="utf-8")
    epic_slug = bft.epic_slug(issue_number)
    
    return bft.validate_formal_gates(content, epic_slug)


@activity.defn
async def run_bft_stage(req: BftRequest, stage_name: str) -> dict:
    """Одна стадия канонического пайплайна БФТ — отдельный `claude -p`.

    Разложено по стадиям ровно затем же, зачем разложена цепочка FNR: одной
    активностью весь пайплайн был бы одним баром в Event History на десятки
    минут, и застрявшая стадия не называла бы себя.
    """
    prompt, expected, requires = bft.deep_stage(stage_name, req.issue_number)
    clone_dir = _require_bft_workspace(req, requires)
    if expected:
        done = Path(clone_dir) / expected
        if done.is_file() and done.stat().st_size > 0:
            # Артефакт приехал с веткой прошлого прогона: стадия уже сделана, и
            # повторять её — платить второй раз за тот же документ. Так `/bft-deep`
            # после срыва продолжает с места обрыва, а не начинает заново.
            logger.info("БФТ %s#%s: стадия %s уже сделана — пропускаю",
                        req.repo, req.issue_number, stage_name)
            return {"stage": stage_name, "artifact": expected,
                    "bytes": done.stat().st_size, "skipped": True}
    if stage_name in bft.direct_stages() and expected:
        # Стадия без исследования репозитория: вход готов, выход — один файл.
        # Агент здесь стоит 356 МБ RSS и ничего не добавляет, кроме способности
        # дочитать файл, который мы и так подаём (#77).
        document = await _run_with_heartbeat(
            _bft_direct_draft, req, clone_dir, label=f"bft:{stage_name}")
        path = Path(clone_dir) / expected
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document, encoding="utf-8")
    else:
        # Диалог этой стадии пишет entire: у `claude -p` есть сессия, за которую
        # он цепляется хуками. Дублировать её журналом значит вести две записи
        # одного и того же и обе поддерживать.
        await _run_with_heartbeat(_run_claude, prompt, clone_dir,
                                  label=f"bft:{stage_name}")
    artifact: str | None = None
    size = 0
    if expected:
        path = Path(clone_dir) / expected
        if not path.exists():
            raise RuntimeError(f"стадия {stage_name}: артефакт {expected} не создан")
        artifact = expected
        size = path.stat().st_size
        
        # Issue #78, находка A: проверка минимального размера артефакта
        size_issues = bft.check_artifact_size(expected, size)
        if size_issues:
            raise RuntimeError(
                f"стадия {stage_name}: артефакт не прошёл проверку размера — "
                + "; ".join(size_issues)
            )
        
        # Issue #78, находка B: проверка якорей после draft и validate
        if stage_name in ("draft", "validate"):
            anchor_issues = await _validate_stage_anchors(
                clone_dir, req.issue_number, stage_name
            )
            if anchor_issues:
                raise RuntimeError(
                    f"стадия {stage_name}: якоря не прошли проверку — "
                    + "; ".join(anchor_issues)
                )
        
        # Issue #78, находка E: проверка формальных гейтов после validate
        if stage_name == "validate":
            formal_issues = await _validate_formal_gates(
                clone_dir, req.issue_number
            )
            if formal_issues:
                raise RuntimeError(
                    f"стадия {stage_name}: формальные гейты не пройдены — "
                    + "; ".join(formal_issues)
                )
    
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
    session_id, session_branch = await asyncio.to_thread(_entire_session, clone_dir)
    await asyncio.to_thread(_push_entire_branch, req.repo, clone_dir, session_branch)
    await asyncio.to_thread(
        github_client.post_comment, req.repo, req.issue_number,
        bft.render_deep_summary(req.repo, req.issue_number, list(files))
        + bft.render_session_hint(req.repo, session_id, session_branch),
    )
    return branch


@activity.defn
async def cleanup_bft_workspace(req: BftRequest) -> None:
    """Best-effort снос рабочего каталога прогона."""
    await asyncio.to_thread(
        shutil.rmtree, str(_bft_workspace_dir(req)), ignore_errors=True)


@activity.defn
async def publish_bft_partial(req: BftRequest, reason: str) -> list[str]:
    """Сорванный прогон отдаёт то, что успел собрать.

    Прогон срывается не только от ошибок в коде: провайдер отвечает 524, кончается
    лимит запросов, стенд передеплоивают посреди работы. Раньше это стоило всей
    работы — артефакты жили в каталоге, который `cleanup` стирал на любом исходе,
    и повтор начинался с нуля, заново оплачивая уже пройденные стадии.

    Возвращает список стадий, чьи артефакты уже готовы: воркфлоу называет их
    человеку, а следующий `/bft-deep` по ним же понимает, с чего продолжать.
    Пустой результат — не ошибка: сорваться могло и на первой стадии.
    """
    clone_dir = _bft_clone_dir(req)
    if not Path(clone_dir).is_dir():
        logger.warning("БФТ %s#%s: каталог уже снят — публиковать нечего",
                       req.repo, req.issue_number)
        return []
    files = await asyncio.to_thread(
        _collect_bft_artifacts, clone_dir, req.issue_number)
    done = bft.done_stages(
        req.issue_number,
        lambda rel: (Path(clone_dir) / rel).is_file()
        and (Path(clone_dir) / rel).stat().st_size > 0)
    if not files:
        return done
    branch = bft.branch(req.issue_number)
    await asyncio.to_thread(
        github_client.push_artifacts_to_branch,
        req.repo, branch, files,
        f"docs(bft): частичный прогон по issue #{req.issue_number}",
    )
    session_id, session_branch = await asyncio.to_thread(_entire_session, clone_dir)
    await asyncio.to_thread(_push_entire_branch, req.repo, clone_dir, session_branch)
    await asyncio.to_thread(
        github_client.post_comment, req.repo, req.issue_number,
        bft.render_partial_summary(req.repo, req.issue_number,
                                   list(files), done, reason)
        + bft.render_session_hint(req.repo, session_id, session_branch),
    )
    return done


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
    "docs/research/issue-{n}-repowise-dialog.md",
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
        github_client.add_label(req.repo, req.issue_number, labels.ESTIMATED)


@activity.defn
def post_estimate_error(req: EstimateRequest, stage: str, reason: str = "") -> None:
    exc_type, _, message = reason.partition(": ")
    event_id = sentry_setup.capture_estimate_failure(
        req, stage, exc_type or "unknown", message or reason)
    github_client.post_comment(
        req.repo,
        req.issue_number,
        f"⚠️ Оценка не удалась на стадии «{stage}». Повтори `/estimate` позже — "
        f"подробности прогона видны в Temporal UI."
        + sentry_setup.debug_reference(event_id),
    )
    if req.comment_id is not None:
        github_client.add_reaction(req.repo, req.comment_id, "confused")
