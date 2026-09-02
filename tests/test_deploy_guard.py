"""Сторож выкладки: цифра под ударом, порядок старейших, коды возврата.

Отказ, ради которого написан (#263, стенд 25.08): передеплой воркера при 120
незакрытых прогонах убил шедшее воркфлоу недетерминизмом. Опасность была
невидимой — ни счётчика, ни предупреждения, ни строки в инструкции по выкладке.

Сеть не трогаем: клиент Temporal подменяется двойником, чистые функции
проверяются напрямую.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deploy_guard  # noqa: E402

NOW = datetime(2026, 8, 25, 17, 10, tzinfo=timezone.utc)


def _run(workflow_id="issue-po-helper-org/app-1", days=1.0, wtype="IssueLifecycle"):
    return deploy_guard.Run(workflow_id, f"run-{workflow_id}", wtype,
                            NOW - timedelta(days=days))


# --- Быстрый отчёт ---

def test_no_running_workflows_is_safe():
    lines, ok = deploy_guard.report_lines(0, [], NOW)
    assert ok is True
    assert "никого не заденет" in "\n".join(lines)


def test_running_workflows_warn_and_are_not_safe():
    lines, ok = deploy_guard.report_lines(120, [_run()], NOW)
    text = "\n".join(lines)
    assert ok is False
    assert "120" in text
    assert "workflow.patched" in text          # куда смотреть, а не только «плохо»


def test_count_comes_from_query_not_sample():
    """Цифра — из `count_workflows`, выборка ограничена `--limit`. Печатать
    длину выборки значило бы занижать риск ровно там, где он максимален."""
    lines, _ = deploy_guard.report_lines(120, [_run(), _run("issue-x-2")], NOW)
    assert "Running: 120" in "\n".join(lines)


def test_oldest_first():
    """Старейшие прогоны — те, что переживут больше выкладок, и именно они
    первыми расходятся с новым кодом."""
    runs = [_run("issue-new", days=1), _run("issue-old", days=6), _run("issue-mid", days=3)]
    lines, _ = deploy_guard.report_lines(3, runs, NOW)
    body = "\n".join(lines)
    assert body.index("issue-old") < body.index("issue-mid") < body.index("issue-new")


def test_age_is_shown_in_days():
    lines, _ = deploy_guard.report_lines(1, [_run(days=6.0)], NOW)
    assert "6.0 сут" in "\n".join(lines)


def test_unknown_start_time_sorts_last_and_says_so():
    """`start_time` может не приехать — это не повод ни падать, ни врать
    возрастом."""
    runs = [deploy_guard.Run("issue-no-time", "r", "IssueLifecycle", None),
            _run("issue-old", days=6)]
    lines, _ = deploy_guard.report_lines(2, runs, NOW)
    body = "\n".join(lines)
    assert "возраст неизвестен" in body
    assert body.index("issue-old") < body.index("issue-no-time")


def test_listing_is_capped():
    """Сто двадцать строк вместо цифры — тот же шум, от которого уходили."""
    runs = [_run(f"issue-{i}", days=i + 1) for i in range(40)]
    lines, _ = deploy_guard.report_lines(40, runs, NOW)
    listed = [ln for ln in lines if ln.startswith("  ") and "issue-" in ln]
    assert len(listed) == deploy_guard.OLDEST_SHOWN


# --- Отчёт реплея ---

def test_clean_replay_is_ok():
    lines, ok = deploy_guard.replay_lines({}, 120)
    assert ok is True
    assert "расхождений нет" in "\n".join(lines)


def test_broken_replay_is_not_ok_and_groups_by_reason():
    """Группировка по причине, а не по прогону: одна выкладка ломает все
    прогоны, дошедшие до изменённого места, и сотня строк об одной причине
    спрятала бы вторую причину."""
    failures = {"Activity machine does not handle this event": ["a", "b", "c"],
                "Timer machine does not handle this event": ["d"]}
    lines, ok = deploy_guard.replay_lines(failures, 10)
    text = "\n".join(lines)
    assert ok is False
    assert "сломается 4" in text
    assert text.index("Activity machine") < text.index("Timer machine")  # частое выше


def test_long_failure_group_is_truncated():
    failures = {"Activity machine does not handle this event": [f"w{i}" for i in range(9)]}
    lines, _ = deploy_guard.replay_lines(failures, 9)
    assert "… и ещё 4" in "\n".join(lines)


# --- Сбор данных ---

class _FakeCount:
    def __init__(self, count):
        self.count = count


class _FakeExecution:
    def __init__(self, wid, started):
        self.id = wid
        self.run_id = f"run-{wid}"
        self.workflow_type = "IssueLifecycle"
        self.start_time = started


class _FakeClient:
    def __init__(self, total, executions=None, fail_connect=False):
        self._total = total
        self._executions = executions or []
        self.queries = []

    async def count_workflows(self, query):
        self.queries.append(query)
        return _FakeCount(self._total)

    async def list_workflows(self, query):
        for execution in self._executions:
            yield execution


async def test_collect_counts_and_samples():
    client = _FakeClient(120, [_FakeExecution(f"issue-{i}", NOW) for i in range(5)])
    total, runs = await deploy_guard.collect(client, limit=200)
    assert total == 120
    assert len(runs) == 5
    assert client.queries == [deploy_guard.RUNNING_QUERY]


async def test_collect_respects_limit():
    """Потолок выборки: на большом namespace перечисление всего — лишние
    страницы визибилити ради списка, из которого печатается десяток строк."""
    client = _FakeClient(500, [_FakeExecution(f"issue-{i}", NOW) for i in range(50)])
    total, runs = await deploy_guard.collect(client, limit=10)
    assert (total, len(runs)) == (500, 10)


def test_query_targets_running_only():
    """`ContinuedAsNew` и терминальные статусы историю уже закрыли — новый код
    им не грозит, и в счёт риска они попадать не должны."""
    assert deploy_guard.RUNNING_QUERY == "ExecutionStatus = 'Running'"


# --- Коды возврата ---

async def _main(monkeypatch, client, argv, replay_result=None):
    async def fake_connect():
        if client is None:
            raise ConnectionError("Temporal недоступен")
        return client

    monkeypatch.setattr(deploy_guard, "connect_temporal", fake_connect)
    if replay_result is not None:
        async def fake_replay(_client, runs):
            return replay_result
        monkeypatch.setattr(deploy_guard, "replay", fake_replay)
    return await deploy_guard.main(argv)


async def test_exit_zero_when_nothing_running(monkeypatch):
    assert await _main(monkeypatch, _FakeClient(0), []) == 0


async def test_exit_one_when_runs_are_at_risk(monkeypatch):
    """Ненулевой код — чтобы цель годилась гейтом в CI, а не только для чтения."""
    client = _FakeClient(120, [_FakeExecution("issue-1", NOW)])
    assert await _main(monkeypatch, client, []) == 1


async def test_warn_only_never_blocks(monkeypatch):
    """`make up` печатает цифру, но не запрещает сборку: решение выкладывать —
    за человеком."""
    client = _FakeClient(120, [_FakeExecution("issue-1", NOW)])
    assert await _main(monkeypatch, client, ["--warn-only"]) == 0


async def test_unreachable_temporal_does_not_claim_safety(monkeypatch, capsys):
    """Молчание Temporal — не «прогонов нет». Соврать здесь значит выдать
    невыполненную проверку за пройденную."""
    assert await _main(monkeypatch, None, []) == 1
    out = capsys.readouterr().out
    assert "НЕ значит" in out


async def test_unreachable_temporal_still_lets_build_through_in_warn_only(monkeypatch):
    assert await _main(monkeypatch, None, ["--warn-only"]) == 0


async def test_clean_replay_of_all_runs_clears_the_risk(monkeypatch):
    client = _FakeClient(2, [_FakeExecution("issue-1", NOW), _FakeExecution("issue-2", NOW)])
    assert await _main(monkeypatch, client, ["--replay"], replay_result=({}, 2)) == 0


async def test_broken_replay_keeps_exit_one(monkeypatch):
    client = _FakeClient(2, [_FakeExecution("issue-1", NOW), _FakeExecution("issue-2", NOW)])
    result = ({"Activity machine does not handle this event": ["issue-1"]}, 2)
    assert await _main(monkeypatch, client, ["--replay"], replay_result=result) == 1


async def test_partial_replay_does_not_clear_the_risk(monkeypatch, capsys):
    """«Проверил двести из пятисот, всё чисто» — не безопасность. На непокрытом
    остатке молчание реплея не значит ничего."""
    client = _FakeClient(500, [_FakeExecution(f"issue-{i}", NOW) for i in range(3)])
    code = await _main(monkeypatch, client, ["--replay", "--limit", "3"],
                       replay_result=({}, 3))
    assert code == 1
    assert "Проверено 3 из 500" in capsys.readouterr().out


# --- Реплей живых историй ---
#
# `replay()` тянет истории из Temporal и проигрывает их против текущего кода.
# Двойник клиента отдаёт НАСТОЯЩУЮ записанную историю из фикстур: проверять
# реплей на выдуманной истории значило бы проверять двойник, а не реплей.

class _FakeHandle:
    def __init__(self, history, error=None):
        self._history = history
        self._error = error

    async def fetch_history(self):
        if self._error is not None:
            raise self._error
        return self._history


class _ReplayClient:
    def __init__(self, history=None, error=None):
        self._history = history
        self._error = error

    def get_workflow_handle(self, workflow_id, run_id=None):
        return _FakeHandle(self._history, self._error)


def _fixture_history():
    import gzip

    from temporalio.client import WorkflowHistory

    path = sorted((ROOT / "tests" / "replay" / "histories").glob("*.json.gz"))[0]
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    return WorkflowHistory.from_json(path.name.removesuffix(".json.gz").replace("__", "/"), raw)


async def test_replay_of_live_history_is_clean():
    """Сквозной путь: история живого прогона проигрывается против текущего кода
    и расхождений не даёт. Красный тест здесь означает, что HEAD ломает идущие
    прогоны, — ровно то, ради чего сторож и написан."""
    history = _fixture_history()
    failures, replayed = await deploy_guard.replay(
        _ReplayClient(history), [_run(history.workflow_id)])
    assert (failures, replayed) == ({}, 1)


async def test_unreadable_history_is_reported_not_swallowed():
    """Недоступная история — не повод бросить проверку остальных, но и не повод
    посчитать прогон проверенным."""
    failures, replayed = await deploy_guard.replay(
        _ReplayClient(error=TimeoutError("visibility недоступна")), [_run()])
    assert replayed == 0
    assert list(failures) == ["история не читается: TimeoutError"]


def test_failure_reason_keeps_the_distinguishing_tail():
    """Начало текста у всех расхождений общее, различает их хвост после маркера."""
    exc = RuntimeError(
        "Replay failed: [TMPRL1100] Nondeterminism error: Activity machine "
        "does not handle this event")
    assert deploy_guard.failure_reason(exc, "Nondeterminism error: ") == (
        "Activity machine does not handle this event")


def test_failure_reason_is_bounded():
    """Полный текст несёт идентификаторы прогона: с ними каждая строка
    уникальна, и группировка вырождается в список."""
    exc = RuntimeError("Nondeterminism error: " + "x" * 500)
    assert len(deploy_guard.failure_reason(exc, "Nondeterminism error: ")) == 160


def test_failure_reason_falls_back_to_exception_type():
    """Отказ не про недетерминизм — показывать нечего, группируем по типу."""
    assert deploy_guard.failure_reason(KeyError("IssueLifecycle"),
                                       "Nondeterminism error: ") == "KeyError"


async def test_broken_history_lands_in_failures():
    """Сквозной путь отказа: реплей не прошёл — прогон обязан попасть в отчёт,
    а не потеряться. Это тот самый путь, ради которого сторож и написан."""
    from temporalio.client import WorkflowHistory

    real = _fixture_history()
    # Тип воркфлоу, которого в коде нет: реплей обязан отказаться, и отказ
    # обязан быть посчитан. Подменяем именно тип, а не содержимое истории, —
    # так отказ приходит от самого Replayer, а не от порчи JSON.
    raw = real.to_json_dict()
    raw["events"][0]["workflowExecutionStartedEventAttributes"]["workflowType"]["name"] = \
        "ВоркфлоуКоторогоНет"
    broken = WorkflowHistory.from_json("issue-broken", raw)

    failures, replayed = await deploy_guard.replay(
        _ReplayClient(broken), [_run("issue-broken")])
    assert replayed == 1
    assert sum(len(v) for v in failures.values()) == 1
    assert failures[next(iter(failures))] == ["issue-broken"]
