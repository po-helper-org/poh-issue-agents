"""Проигрывание реальных историй против текущего кода воркфлоу.

Класс, который этот тест закрывает, стоил контуру 28 мёртвых прогонов из 124.
Правка РЕШЕНИЯ воркфлоу без `workflow.patched(...)` не роняет ни один обычный
тест: они гоняют код с нуля, а расхождение возникает только на реплее уже
записанной истории. Прогон при этом не падает заметно — он перестаёт выполнять
задачи воркфлоу, сигналы приходят и умирают, а снаружи Issue выглядит живым.

Найдено 2026-08-25: коммит `ac625e7` добавил ветку автостарта в
`_phase_handoff` без маркера, и все прогоны, стоявшие в парковке
`awaiting-build-decision`, встали намертво с
`[TMPRL1100] Nondeterminism error: Activity type of scheduled event 'set_phase'
does not match activity type of activity command 'trigger_openhands_resolver'`.
"""

import gzip
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

import workflows as wf

HISTORIES = sorted((Path(__file__).parent / "replay" / "histories").glob("*.json.gz"))


def _workflow_classes() -> list[type]:
    """Все классы воркфлоу модуля: реплей обязан знать каждый тип из истории."""
    found = []
    for name in dir(wf):
        if not name[0].isupper():
            continue
        obj = getattr(wf, name)
        if hasattr(obj, "__temporal_workflow_definition"):
            found.append(obj)
    return found


def test_fixtures_exist():
    """Пустой каталог фикстур означал бы зелёный гвард, который ничего не держит."""
    assert HISTORIES, "нет ни одной истории в tests/replay/histories"


@pytest.mark.parametrize("path", HISTORIES, ids=lambda p: p.name)
async def test_history_replays(path):
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    workflow_id = path.name.removesuffix(".json.gz").replace("__", "/")
    history = WorkflowHistory.from_json(workflow_id, raw)
    await Replayer(workflows=_workflow_classes()).replay_workflow(history)
