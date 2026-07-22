import consolidation_activities as ca
from consolidation_activities import SliceExtraction, IncrementOut
from shared.workflow_types import DeliveryZone, SolutionProfile


def _p(n):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism="m", target="tg", domain="d",
                           anchors=["a"], advisor_label="x")


ZONE = DeliveryZone("jira-engine", "b", "s")


def test_slice_big_zone(monkeypatch):
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: SliceExtraction(increments=[
        IncrementOut(name="MVP", rationale="фундамент", issue_numbers=[1, 2, 3]),
        IncrementOut(name="MVP+1", rationale="надстройка", issue_numbers=[4, 5, 6, 7])]))
    members = list(range(1, 8))
    incs = ca.slice_zone(ZONE, members, [_p(n) for n in members])
    assert [i.name for i in incs] == ["jira-engine:MVP", "jira-engine:MVP+1"]
    assert sorted(n for i in incs for n in i.issue_numbers) == members


def test_slice_small_zone_single_increment(monkeypatch):
    # <= SLICE_MIN members -> one increment, no LLM call
    called = {"n": 0}
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: called.__setitem__("n", 1))
    incs = ca.slice_zone(ZONE, [1, 2], [_p(1), _p(2)])
    assert len(incs) == 1
    assert incs[0].issue_numbers == [1, 2]
    assert called["n"] == 0  # no LLM for a small zone
