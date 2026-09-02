#!/usr/bin/env python3
"""Проиграть истории прогонов Temporal против текущего кода воркфлоу.

Зачем отдельный скрипт, а не только тест: перед правкой РЕШЕНИЯ воркфлоу
проверять надо не фикстуры из репозитория, а истории ВСЕХ живых прогонов на
стенде — их там сотни, и в репозиторий они не поместятся. Тест держит
представительную выборку, скрипт — весь корпус.

Как снять корпус со стенда:

    ssh poh-stand "T=compose-connect-redundant-system-mzso3q-temporal-1
    A=--address=compose-connect-redundant-system-mzso3q-temporal-1:7233
    rm -rf /tmp/hist && mkdir -p /tmp/hist
    for w in \\$(docker exec \\$T temporal workflow list \\$A --limit 300 2>/dev/null \
                 | awk '\\$3==\"IssueLifecycle\"{print \\$2}'); do
      docker exec \\$T temporal workflow show \\$A -w \"\\$w\" -o json \
        > /tmp/hist/\\$(echo \"\\$w\" | tr '/' '_').json 2>/dev/null
    done
    tar -czf /tmp/hist.tgz -C /tmp hist"

Имена в корпусе — с ОДНИМ подчёркиванием (`tr '/' '_'` в цикле выше). Фикстуры
в tests/replay/histories/ — с ДВУМЯ (см. tests/replay/README.md). Перенос
истории из снятого корпуса в фикстуры репозитория — это переименование, а не
просто `cp` + `gzip`:

    mv /tmp/hist/issue-po-helper-org_poh-example-1.json \
       /tmp/hist/issue-po-helper-org__poh-example-1.json
    gzip -c /tmp/hist/issue-po-helper-org__poh-example-1.json \
      > tests/replay/histories/issue-po-helper-org__poh-example-1.json.gz

Копия «как есть», без переименования, даст файл с одним подчёркиванием, и
`workflow_id = path.name...replace("__", "/")` в тесте восстановит по нему
неверный идентификатор прогона.

Запуск:

    python scripts/replay_histories.py <каталог с *.json или *.json.gz>

Читает и распакованные истории корпуса (*.json), и сжатые фикстуры репозитория
(*.json.gz) — один инструмент годится для обоих каталогов.

Код возврата 1, если хоть одна история не проигралась.
"""
import asyncio
import glob
import gzip
import sys
from collections import defaultdict

sys.path.insert(0, "worker")
sys.path.insert(0, ".")

from temporalio.client import WorkflowHistory          # noqa: E402
from temporalio.worker import Replayer                 # noqa: E402

import workflows as wf                                 # noqa: E402

from shared.replay_report import (                     # noqa: E402
    MARKER, failure_reason, format_failures)


def workflow_classes() -> list[type]:
    """Все классы воркфлоу модуля: реплей обязан знать каждый тип из истории."""
    found = []
    for name in dir(wf):
        if not name[0].isupper():
            continue
        obj = getattr(wf, name)
        if hasattr(obj, "__temporal_workflow_definition"):
            found.append(obj)
    return found


def _read_history(path: str) -> str:
    """*.json — как есть, *.json.gz — распаковать. Один каталог может смешивать оба вида."""
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8").read()
    return open(path, encoding="utf-8").read()


async def run(directory: str) -> int:
    paths = sorted(glob.glob(f"{directory}/*.json") + glob.glob(f"{directory}/*.json.gz"))
    if not paths:
        print(f"в {directory} нет ни одной истории")
        return 1

    classes = workflow_classes()
    failures: dict[str, list[str]] = defaultdict(list)
    ok = 0
    for path in paths:
        raw = _read_history(path)
        name = path.rsplit("/", 1)[-1]
        try:
            await Replayer(workflows=classes).replay_workflow(
                WorkflowHistory.from_json(name, raw))
            ok += 1
        except Exception as exc:            # noqa: BLE001 — интересен любой отказ
            failures[failure_reason(exc)].append(name)

    total = sum(len(v) for v in failures.values())
    print(f"проиграно: {ok} | падений: {total}")
    # Группировка и форма отчёта общие со сторожем выкладки
    # (`scripts/deploy_guard.py --replay`): одна и та же поломка обязана
    # выглядеть одинаково, каким бы из двух инструментов её ни нашли.
    for line in format_failures(failures):
        print(line)
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("использование: python scripts/replay_histories.py <каталог>")
    sys.exit(asyncio.run(run(sys.argv[1])))
