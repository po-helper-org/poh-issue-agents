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

Запуск:

    python scripts/replay_histories.py <каталог с *.json>

Код возврата 1, если хоть одна история не проигралась.
"""
import asyncio
import glob
import sys
from collections import defaultdict

sys.path.insert(0, "worker")
sys.path.insert(0, ".")

from temporalio.client import WorkflowHistory          # noqa: E402
from temporalio.worker import Replayer                 # noqa: E402

import workflows as wf                                 # noqa: E402

MARKER = "Nondeterminism error: "


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


async def run(directory: str) -> int:
    paths = sorted(glob.glob(f"{directory}/*.json"))
    if not paths:
        print(f"в {directory} нет ни одной истории")
        return 1

    classes = workflow_classes()
    failures: dict[str, list[str]] = defaultdict(list)
    ok = 0
    for path in paths:
        raw = open(path, encoding="utf-8").read()
        name = path.rsplit("/", 1)[-1]
        try:
            await Replayer(workflows=classes).replay_workflow(
                WorkflowHistory.from_json(name, raw))
            ok += 1
        except Exception as exc:            # noqa: BLE001 — интересен любой отказ
            text = str(exc)
            key = text.split(MARKER)[-1][:80] if MARKER in text else type(exc).__name__
            failures[key].append(name)

    total = sum(len(v) for v in failures.values())
    print(f"проиграно: {ok} | падений: {total}")
    for key, names in sorted(failures.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(names):3d}  {key}")
        for name in names[:5]:
            print(f"         {name}")
        if len(names) > 5:
            print(f"         … и ещё {len(names) - 5}")
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("использование: python scripts/replay_histories.py <каталог>")
    sys.exit(asyncio.run(run(sys.argv[1])))
