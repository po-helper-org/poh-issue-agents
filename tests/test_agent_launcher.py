"""#37: одна точка решения «агент как child или как самостоятельный прогон».

Проверяется без Temporal — лаунчер это чистая маршрутизация поверх клиента.
Важны три свойства: живой цикл получает команду и ведёт агента сам; прогон
прежнего поколения не теряет команду; идентификаторы остаются каноническими,
иначе повторный запуск перестанет быть идемпотентным.
"""

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError

from shared.agent_launcher import (
    CHILD,
    ROOT,
    request_analysis,
    request_bft,
    request_estimate,
)
from shared.workflow_ids import (
    bft_workflow_id,
    analysis_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
)
from shared.workflow_types import (
    AnalyzeInput,
    BftRequest,
    EstimateRequest,
    IssueInput,
)

REPO = "acme/widgets"


class _Handle:
    def __init__(self, answer) -> None:
        self._answer = answer

    async def query(self, name, *args):
        assert name == "handles_agents", name
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


class FakeClient:
    def __init__(self, answer=True, already: set[str] | None = None) -> None:
        self.started: list[dict] = []
        self._answer = answer
        self._already = already or set()

    async def start_workflow(self, workflow, arg, **kwargs):
        if workflow in self._already:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), workflow)
        self.started.append({"workflow": workflow, "arg": arg, **kwargs})
        return _Handle(self._answer)


def _issue() -> IssueInput:
    return IssueInput(repo=REPO, issue_number=7, title="t", body="b",
                      author_login="alice", author_type="User")


def _analyze(comment_id: int | None = 555) -> AnalyzeInput:
    return AnalyzeInput(repo=REPO, issue_number=7, title="t", body="b",
                        comment_id=comment_id)


def _estimate(comment_id: int | None = 555) -> EstimateRequest:
    return EstimateRequest(repo=REPO, issue_number=7, comment_id=comment_id)


# --- живой цикл ведёт агента сам ---

async def test_live_cycle_gets_the_command_and_nothing_else_starts():
    client = FakeClient(answer=True)

    mode = await request_analysis(client, _issue(), _analyze())

    assert mode == CHILD
    assert [c["workflow"] for c in client.started] == ["IssueLifecycle"]
    assert client.started[0]["start_signal"] == "analyze_requested"
    assert client.started[0]["start_signal_args"] == [555]


async def test_estimate_reaches_the_cycle_with_its_trigger_comment():
    client = FakeClient(answer=True)

    mode = await request_estimate(client, _issue(), _estimate())

    assert mode == CHILD
    assert client.started[0]["start_signal"] == "estimate_requested"
    assert client.started[0]["start_signal_args"] == [555]


# --- прежнее поколение: команда не теряется ---

async def test_old_cycle_gets_a_root_run_instead():
    client = FakeClient(answer=False)

    mode = await request_analysis(client, _issue(), _analyze())

    assert mode == ROOT
    assert [c["workflow"] for c in client.started] == ["IssueLifecycle", "IssueAnalysis"]


async def test_old_cycle_root_estimate_keeps_the_comment_id():
    client = FakeClient(answer=False)

    await request_estimate(client, _issue(), _estimate())

    call = next(c for c in client.started if c["workflow"] == "IssueEstimation")
    assert call["arg"].comment_id == 555


@pytest.mark.parametrize("comment_id, expected", [(555, "555"), (None, "label")])
async def test_estimate_id_distinguishes_label_from_comment(comment_id, expected):
    """Метку можно поставить заново после завершённого прогона — это честно
    новый прогон; повторная доставка того же комментария — нет."""
    client = FakeClient(answer=False)

    await request_estimate(client, _issue(), _estimate(comment_id))

    call = next(c for c in client.started if c["workflow"] == "IssueEstimation")
    assert call["id"] == f"estimate-{REPO}-7-{expected}"


# --- идемпотентность и отказоустойчивость ---

async def test_ids_come_from_the_single_source():
    """Разъехавшись с `shared/workflow_ids.py`, лаунчер молча потерял бы
    идемпотентность повторного запуска."""
    client = FakeClient(answer=False)

    await request_analysis(client, _issue(), _analyze())

    started = {c["workflow"]: c["id"] for c in client.started}
    assert started["IssueLifecycle"] == issue_workflow_id(REPO, 7)
    assert started["IssueAnalysis"] == analysis_workflow_id(REPO, 7)


async def test_running_root_analysis_is_not_started_twice():
    client = FakeClient(answer=False, already={"IssueAnalysis"})

    mode = await request_analysis(client, _issue(), _analyze())

    assert mode == ROOT  # 200 вебхуку, а не 500: повтор — не ошибка
    assert not any(c["workflow"] == "IssueAnalysis" for c in client.started)


async def test_running_root_estimate_is_not_started_twice():
    client = FakeClient(answer=False, already={"IssueEstimation"})

    await request_estimate(client, _issue(), _estimate())

    assert not any(c["workflow"] == "IssueEstimation" for c in client.started)
    assert estimate_workflow_id(REPO, 7, 555)  # id остаётся каноническим


async def test_unavailable_query_prefers_the_cycle():
    """Сигнал уже доставлен — цикл жив. Поднимать на недоступном query второй
    дорогой прогон хуже, чем один раз не отработать по старому пути."""
    client = FakeClient(answer=RuntimeError("query timeout"))

    mode = await request_analysis(client, _issue(), _analyze())

    assert mode == CHILD
    assert [c["workflow"] for c in client.started] == ["IssueLifecycle"]


# --- БФТ ---

def _bft(mode: str = "fast") -> BftRequest:
    return BftRequest(repo=REPO, issue_number=7, title="t", body="b",
                      mode=mode, comment_id=555)


async def test_bft_goes_to_the_live_cycle_as_a_child():
    """Живой цикл ведёт прогон сам — второй, самостоятельный, был бы платой за
    ту же работу дважды."""
    client = FakeClient(answer=True)

    assert await request_bft(client, _issue(), _bft()) == CHILD

    assert len(client.started) == 1
    call = client.started[0]
    assert call["workflow"] == "IssueLifecycle"
    assert call["id"] == issue_workflow_id(REPO, 7)
    assert call["start_signal"] == "bft_requested"
    assert call["start_signal_args"][0].mode == "fast"


async def test_bft_falls_back_to_a_root_run_for_an_old_cycle():
    """Прогон прежнего поколения сигнала не понимает: команда была бы принята и
    потеряна, поэтому лаунчер поднимает прогон сам."""
    client = FakeClient(answer=False)

    assert await request_bft(client, _issue(), _bft("deep")) == ROOT

    assert [c["workflow"] for c in client.started] == ["IssueLifecycle", "IssueBft"]
    assert client.started[1]["id"] == bft_workflow_id(REPO, 7, "deep")


async def test_a_running_bft_is_not_started_twice():
    """Повторная доставка того же вебхука не должна платить второй раз."""
    client = FakeClient(answer=False, already={"IssueBft"})

    assert await request_bft(client, _issue(), _bft()) == ROOT  # без исключения


async def test_the_two_bft_modes_get_different_ids():
    """Иначе заказ полного документа упирался бы в идущую переформулировку."""
    fast, deep = FakeClient(answer=False), FakeClient(answer=False)
    await request_bft(fast, _issue(), _bft("fast"))
    await request_bft(deep, _issue(), _bft("deep"))

    assert fast.started[1]["id"] != deep.started[1]["id"]
