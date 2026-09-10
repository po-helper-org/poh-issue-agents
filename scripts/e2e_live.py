"""Живой E2E: проверка контура на настоящем репозитории, Temporal и модели.

Внутрипроцессный E2E (`tests/test_e2e_issue_lifecycle.py`) замыкает сеть на
заглушки и потому не может ответить на вопросы, которые ломались в проде:
доезжает ли вебхук, входит ли репозиторий в ISSUE_AGENT_REPOS, отвечает ли
кластер, работает ли ключ модели. Этот скрипт отвечает — ценой реального
прогона и реальных токенов.

Запускать ТАМ, ГДЕ ЖИВЁТ СЕРВИС (у скрипта должны быть те же креды и та же сеть):

    docker compose exec worker python scripts/e2e_live.py triage
    docker compose exec worker python scripts/e2e_live.py label-command
    docker compose exec worker python scripts/e2e_live.py develop --fix-round
    docker compose exec worker python scripts/e2e_live.py triage --repo owner/name --keep

Репозиторий берётся из --repo, иначе из E2E_REPO, иначе из GITHUB_REPOSITORY.
Ни один из сценариев не трогает существующие Issue: скрипт заводит свой,
наблюдает за ним и закрывает (кроме --keep).

`triage` и `label-command` смотрят на метки: их исход виден снаружи. `develop`
смотрит на ПУЛ-РЕКВЕСТ, потому что у стадии разработки метка «готово» и
состоявшаяся правка — разные вещи. Прогон #19 открыл PR, доложил об успехе и не
изменил ни одного файла кода: воркер работает от root, раннер от uid 10001, и
агент ушёл писать в `/tmp`. Метки в тот прогон выглядели исправными.

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
from poh_developer import develop  # noqa: E402
from poh_developer.integration import TASK_QUEUE as DEVELOPER_QUEUE  # noqa: E402
from shared.commands import ESTIMATE, done_label, failed_label, run_label  # noqa: E402
from shared.temporal_client import connect_temporal  # noqa: E402
from shared.workflow_ids import (  # noqa: E402
    development_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
    pr_fix_workflow_id,
)
from shared.workflow_types import IssueInput  # noqa: E402

TASK_QUEUE = "issue-lifecycle"
MARKER = "e2e-live-probe"

# Каталог контекста задачи коммитится вместе с кодом намеренно (см.
# `poh_developer/develop.py`), поэтому правкой он не считается: PR, в котором
# нет ничего, кроме него, — это ровно прогон #19.
CONTEXT_DIR = ".harness/"


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


def develop_scenario() -> Scenario:
    """Стадия разработки целиком: клон, агент, тесты, пуш, пул-реквест.

    Без ожиданий по меткам — исход этой стадии читается из PR, а не из разметки
    Issue (`develop_problems`). Задача выбрана мелкой и однозначной: она обязана
    затронуть и `src/`, и `tests/`, иначе проверять «правка настоящая» не на чем.

    Допущение: PR прогона не вливается. Скрипт закрывает его сам, но если
    оставленный `--keep` пул-реквест кто-то влил, база уже несёт эту правку —
    и следующий прогон честно доложит о пустом диффе.
    """
    return Scenario(
        name="develop",
        title=f"[{MARKER}] проверка стадии разработки: эндпоинт /version",
        body=(
            "Служебная задача автоматической проверки контура.\n\n"
            "Нужен эндпоинт `GET /version`, отдающий JSON вида "
            '`{"version": "<версия из package.json>"}` со статусом 200. '
            "Версию читать из `package.json`, не дублировать её строкой в коде.\n\n"
            "Обязателен тест в `tests/`, проверяющий статус и тело ответа.\n\n"
            f"Заведено скриптом `scripts/e2e_live.py` ({MARKER}), закроется само."
        ),
    )


SCENARIOS = {
    "triage": triage_scenario,
    "label-command": label_command_scenario,
    "develop": develop_scenario,
}

# Стадия разработки идёт десятками минут (один `dev_run_agent` — до часа), и
# общее умолчание в 600 секунд для неё означало бы гарантированный ложный
# отказ по таймауту.
DEFAULT_TIMEOUT = {"develop": 3600}
FALLBACK_TIMEOUT = 600


def develop_problems(filenames: list[str]) -> list[str]:
    """Отказы стадии, которые выглядят как успех. Пусто — правка настоящая.

    Оба пункта оплачены живыми прогонами и оба молчали:

    #19 — постановка уехала в PR одним файлом на 1721 строку и заодно скрыла
          главное: агент не изменил ни одного файла кода;
    #35 — круг правок закоммитил свою же постановку.

    Служебные файлы перечислены в `poh_developer.develop.SERVICE_FILES` — здесь
    берётся оттуда, а не переписывается: перечень пополняется, и вторая копия
    рассохлась бы молча.
    """
    service = [name for name in filenames if name in develop.SERVICE_FILES]
    changed = [name for name in filenames
               if name not in develop.SERVICE_FILES
               and not name.startswith(CONTEXT_DIR)]
    problems = []
    if service:
        problems.append(f"служебные файлы уехали в PR: {', '.join(sorted(service))}")
    if not changed:
        problems.append("в PR нет ни одного файла правки — агент не изменил кода")
    return problems


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


async def start_development(repo: str, number: int, scenario: Scenario):
    """Запуск стадии напрямую на её очереди — минуя триаж и аналитику.

    Прогонять ради проверки разработки весь цикл значило бы платить за триаж и
    аналитику и получать красный результат от любого их отказа. Стадия работает
    и без аналитики: `dev_begin` вернёт пустую ветку артефактов.
    """
    client = await connect_temporal()
    handle = await client.start_workflow(
        "IssueDevelopment",
        IssueInput(repo=repo, issue_number=number, title=scenario.title,
                   body=scenario.body, author_login="e2e", author_type="User",
                   interactive=False),
        id=development_workflow_id(repo, number), task_queue=DEVELOPER_QUEUE,
    )
    return handle


async def run_fix_round(repo: str, pr: int) -> str:
    """Круг правок по тому же PR. Возвращает строку исхода для отчёта."""
    client = await connect_temporal()
    outcome = await client.execute_workflow(
        "IssuePrFix", args=[repo, pr, 1],
        id=pr_fix_workflow_id(repo, pr, 1), task_queue=DEVELOPER_QUEUE,
    )
    if outcome is True:
        return "правки внесены, перепроверка запрошена"
    # Строка вместо True означает «править было нечего»: круг прошёл клон,
    # агента и разбор, но сам путь внесения правок не тронул. Зелёным это
    # считать можно, полной проверкой круга — нет.
    return f"правок не потребовалось ({outcome}); путь внесения правок не проверен"


async def run_develop_scenario(repo: str, args, log) -> int:
    """Стадия разработки на живом репозитории: от задачи до проверенного PR."""
    scenario = develop_scenario()

    if not develop.enabled():
        log("✗ DEVELOP_ENABLED выключен — стадия откажется работать")
        return 2
    if develop.mode() != "local":
        log(f"✗ DEVELOP_MODE={develop.mode()}: PR откроет чужая сторона, "
            "и проверить его этим сценарием нечем. Нужен local")
        return 2

    try:
        number = github_client.create_issue(repo, scenario.title, scenario.body)
    except Exception as exc:
        log(f"✗ не удалось завести Issue: {type(exc).__name__}: {exc}")
        return 2
    log(f"  ✓ Issue #{number} заведён")

    pr: int | None = None
    code = 1
    try:
        handle = await start_development(repo, number, scenario)
        log(f"  ✓ стадия запущена на очереди «{DEVELOPER_QUEUE}»: {handle.id}")
        log(f"  … ждём PR (до {args.timeout} с; прогон агента идёт десятками минут)")
        try:
            pr = await asyncio.wait_for(handle.result(), timeout=args.timeout)
        except asyncio.TimeoutError:
            log(f"✗ стадия не завершилась за {args.timeout} с. Прогон ЖИВ: "
                f"смотреть {handle.id} в Temporal UI, там же видно, на каком шаге")
            return 1

        if pr is None:
            log("✗ стадия вернула None — это режим dispatch, а не local")
            return 2
        log(f"  ✓ пул-реквест #{pr} открыт")

        files = github_client.list_pull_files(repo, pr)
        problems = develop_problems(files)
        for problem in problems:
            log(f"  ✗ {problem}")
        if problems:
            log(f"  файлы PR: {files or '—'}")
            return 1
        log(f"  ✓ правка настоящая: {len(files)} файл(ов), среди них код")

        code = 0
        if args.fix_round:
            log("  … круг правок")
            try:
                log(f"  ✓ круг правок: {await run_fix_round(repo, pr)}")
            except Exception as exc:
                log(f"  ✗ круг правок сорвался: {type(exc).__name__}: {exc}")
                code = 1
    finally:
        if not args.keep:
            # PR закрывается тем же вызовом, что и Issue: у GitHub пул-реквест
            # доступен по /issues/<номер>, и отдельной функции для этого в
            # клиенте нет намеренно.
            for target, what in ((pr, "PR"), (number, "Issue")):
                if target is None:
                    continue
                try:
                    github_client.close_issue(repo, target)
                    log(f"  ✓ служебный {what} #{target} закрыт")
                except Exception as exc:
                    log(f"  ⚠ не удалось закрыть {what} #{target}: {exc}")

    if code == 0:
        log(f"✓ стадия разработки отработала: {repo}#{number} → PR #{pr}")
    return code


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Живой E2E контура Issue-Agent")
    parser.add_argument("scenario", choices=sorted(SCENARIOS), help="что проверяем")
    parser.add_argument("--repo", help="owner/name; иначе E2E_REPO или GITHUB_REPOSITORY")
    parser.add_argument("--timeout", type=int, default=None,
                        help="секунд на прогон; умолчание зависит от сценария")
    parser.add_argument("--poll", type=int, default=15, help="секунд между опросами")
    parser.add_argument("--keep", action="store_true", help="не закрывать служебный Issue")
    parser.add_argument("--fix-round", action="store_true",
                        help="develop: прогнать по открытому PR ещё и круг правок")
    args = parser.parse_args(argv)
    if args.timeout is None:
        args.timeout = DEFAULT_TIMEOUT.get(args.scenario, FALLBACK_TIMEOUT)

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

    # Исход разработки читается из PR, а не из меток, поэтому у сценария свой
    # ход целиком — от старта на очереди стадии до разбора файлов пул-реквеста.
    if scenario.name == "develop":
        return await run_develop_scenario(repo, args, log)

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
