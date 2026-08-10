"""Живой E2E: проверка контура на настоящем репозитории, Temporal и модели.

Внутрипроцессный E2E (`tests/test_e2e_issue_lifecycle.py`) замыкает сеть на
заглушки и потому не может ответить на вопросы, которые ломались в проде:
доезжает ли вебхук, входит ли репозиторий в ISSUE_AGENT_REPOS, отвечает ли
кластер, работает ли ключ модели. Этот скрипт отвечает — ценой реального
прогона и реальных токенов.

Запускать ТАМ, ГДЕ ЖИВЁТ СЕРВИС (у скрипта должны быть те же креды и та же сеть):

    docker compose exec worker python scripts/e2e_live.py triage
    docker compose exec worker python scripts/e2e_live.py label-command
    docker compose exec worker python scripts/e2e_live.py triage --repo owner/name --keep

Репозиторий берётся из --repo, иначе из E2E_REPO, иначе из GITHUB_REPOSITORY.
Ни один из сценариев не трогает существующие Issue: скрипт заводит свой,
наблюдает за ним и закрывает (кроме --keep).

Коды возврата: 0 — контур отработал, 1 — ожидания не выполнены за отведённое
время, 2 — ошибка конфигурации (репозиторий не задан, нет доступа).
"""

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import github_client  # noqa: E402
from shared.commands import ESTIMATE, done_label, failed_label, run_label  # noqa: E402
from shared.temporal_client import connect_temporal  # noqa: E402
from shared.workflow_ids import estimate_workflow_id, issue_workflow_id  # noqa: E402
from shared.workflow_types import IssueInput  # noqa: E402

TASK_QUEUE = "issue-lifecycle"
MARKER = "e2e-live-probe"


@dataclass
class Expectation:
    """Что должно появиться на Issue, чтобы прогон считался состоявшимся."""
    what: str
    label_prefix: str | None = None
    label: str | None = None
    forbidden_label: str | None = None

    def met(self, labels: list[str]) -> bool:
        lowered = {name.lower() for name in labels}
        if self.forbidden_label:
            return self.forbidden_label.lower() not in lowered
        if self.label:
            return self.label.lower() in lowered
        return any(name.startswith(self.label_prefix) for name in lowered)


@dataclass
class Scenario:
    name: str
    title: str
    body: str
    expectations: list[Expectation] = field(default_factory=list)


def triage_scenario() -> Scenario:
    """Полный триаж: классификация и приоритет — видимый результат Layer A."""
    return Scenario(
        name="triage",
        title=f"[{MARKER}] проверка контура: добавить экспорт отчёта в CSV",
        body=(
            "Служебная задача автоматической проверки контура.\n\n"
            "Пользователь смотрит отчёт в интерфейсе и хочет выгрузить его в CSV, "
            "чтобы продолжить работу в таблице. Сейчас выгрузки нет — данные "
            "переносят копированием.\n\n"
            f"Заведено скриптом `scripts/e2e_live.py` ({MARKER}), закроется само."
        ),
        expectations=[
            Expectation("классификация проставлена", label_prefix="advisor:"),
            Expectation("приоритет посчитан", label_prefix="priority:"),
        ],
    )


def label_command_scenario() -> Scenario:
    """Запуск командой из метки и обратный ход меток — путь #33."""
    return Scenario(
        name="label-command",
        title=f"[{MARKER}] проверка запуска по метке run:estimate",
        body=(
            "Служебная задача автоматической проверки контура.\n\n"
            "Нужно оценить трудоёмкость добавления выгрузки отчёта в CSV: одна "
            "кнопка в интерфейсе и серверный эндпоинт, отдающий файл.\n\n"
            f"Заведено скриптом `scripts/e2e_live.py` ({MARKER}), закроется само."
        ),
        expectations=[
            Expectation("оценка завершена", label=done_label(ESTIMATE)),
            Expectation("метка запуска снята", forbidden_label=run_label(ESTIMATE)),
        ],
    )


SCENARIOS = {"triage": triage_scenario, "label-command": label_command_scenario}


def resolve_repo(explicit: str | None) -> str:
    repo = explicit or os.environ.get("E2E_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    return repo.strip()


def unmet(scenario: Scenario, labels: list[str]) -> list[Expectation]:
    return [e for e in scenario.expectations if not e.met(labels)]


def failure_detected(scenario: Scenario, labels: list[str]) -> str | None:
    """Метки, означающие, что прогон дошёл до конца и провалился.

    Ждать до истечения таймаута в этом случае бессмысленно — ответ уже получен,
    просто отрицательный.
    """
    lowered = {name.lower() for name in labels}
    if failed_label(ESTIMATE) in lowered:
        return f"прогон завершился неуспехом: метка {failed_label(ESTIMATE)}"
    if "advisor:error" in lowered:
        return "триаж упал: метка advisor:error"
    return None


async def check_temporal() -> str:
    """Связь с кластером — первое, что стоит проверить: без него не стартует
    ни один прогон, а симптом на стороне GitHub будет просто тишиной."""
    from datetime import timedelta

    client = await connect_temporal()
    healthy = await client.service_client.check_health(timeout=timedelta(seconds=10))
    if not healthy:
        raise RuntimeError("Temporal отвечает, но health-check отрицательный")
    return f"{os.environ.get('TEMPORAL_ADDRESS', 'localhost:7233')}" \
           f"/{os.environ.get('TEMPORAL_NAMESPACE', 'default')}"


async def start_triage(repo: str, number: int, title: str, body: str) -> str:
    """Старт напрямую в Temporal — как это делает backfill.

    Проверяет воркер, активности, модель и GitHub. Доставку вебхука НЕ
    проверяет: она зависит от установки App и публичного URL, и её отсутствие
    даёт ровно ту тишину, ради диагностики которой написан scripts/diag.py.
    """
    client = await connect_temporal()
    wf_id = issue_workflow_id(repo, number)
    await client.start_workflow(
        "IssueLifecycle",
        IssueInput(repo=repo, issue_number=number, title=title, body=body,
                   author_login="e2e", author_type="User", interactive=False),
        id=wf_id, task_queue=TASK_QUEUE,
    )
    return wf_id


def wait_for(repo: str, number: int, scenario: Scenario, timeout_sec: int,
             poll_sec: int, log) -> tuple[bool, list[str]]:
    """Опрашивает Issue, пока ожидания не выполнятся либо не истечёт время."""
    deadline = time.monotonic() + timeout_sec
    labels: list[str] = []
    while time.monotonic() < deadline:
        issue = github_client.get_issue(repo, number)
        labels = [label["name"] for label in issue.get("labels", [])]
        problem = failure_detected(scenario, labels)
        if problem:
            log(f"  ✗ {problem}")
            return False, labels
        missing = unmet(scenario, labels)
        if not missing:
            return True, labels
        log(f"  … ждём: {', '.join(e.what for e in missing)} (метки: {labels or '—'})")
        time.sleep(poll_sec)
    return False, labels


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Живой E2E контура Issue-Agent")
    parser.add_argument("scenario", choices=sorted(SCENARIOS), help="что проверяем")
    parser.add_argument("--repo", help="owner/name; иначе E2E_REPO или GITHUB_REPOSITORY")
    parser.add_argument("--timeout", type=int, default=600, help="секунд на прогон")
    parser.add_argument("--poll", type=int, default=15, help="секунд между опросами")
    parser.add_argument("--keep", action="store_true", help="не закрывать служебный Issue")
    args = parser.parse_args(argv)

    log = print
    repo = resolve_repo(args.repo)
    if not repo:
        log("✗ репозиторий не задан: --repo, E2E_REPO или GITHUB_REPOSITORY")
        return 2
    if os.environ.get("DRY_RUN"):
        log("✗ DRY_RUN включён — живой прогон невозможен, мутации подавлены")
        return 2

    scenario = SCENARIOS[args.scenario]()
    log(f"E2E «{scenario.name}» на {repo}")

    try:
        where = await check_temporal()
        log(f"  ✓ Temporal доступен: {where}")
    except Exception as exc:
        log(f"✗ Temporal недоступен: {type(exc).__name__}: {exc}")
        return 2

    try:
        number = github_client.create_issue(repo, scenario.title, scenario.body)
    except Exception as exc:
        log(f"✗ не удалось завести Issue: {type(exc).__name__}: {exc}")
        return 2
    log(f"  ✓ Issue #{number} заведён")

    try:
        if scenario.name == "triage":
            wf_id = await start_triage(repo, number, scenario.title, scenario.body)
            log(f"  ✓ воркфлоу запущен: {wf_id}")
        else:
            # Путь через метку: событие issues.labeled обязано доехать до
            # вебхука и запустить воркфлоу. Именно этот участок и проверяем.
            github_client.add_label(repo, number, run_label(ESTIMATE))
            log(f"  ✓ метка {run_label(ESTIMATE)} поставлена; ожидаемый воркфлоу — "
                f"{estimate_workflow_id(repo, number)}")

        ok, labels = wait_for(repo, number, scenario, args.timeout, args.poll, log)
    finally:
        if not args.keep:
            try:
                github_client.close_issue(repo, number)
                log(f"  ✓ служебный Issue #{number} закрыт")
            except Exception as exc:
                log(f"  ⚠ не удалось закрыть #{number}: {exc}")

    if ok:
        log(f"✓ контур отработал: {labels}")
        return 0
    log(f"✗ ожидания не выполнены за {args.timeout} с. Итоговые метки: {labels or '—'}")
    log("  Что смотреть: scripts/diag.py --repo <repo> (allowlist и авторизация), "
        "логи вебхука за момент события, Temporal UI по id воркфлоу.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
