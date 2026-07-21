import consolidation_activities as ca
from consolidation_activities import AssignExtraction
from shared.workflow_types import SolutionProfile, Taxonomy, DeliveryZone


def _p(n, mech):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target="tg", domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


TAX = Taxonomy(zones=[DeliveryZone("jira-engine", "b", "s"),
                      DeliveryZone("memory-core", "b", "s")])


def test_assign_maps_primary(monkeypatch):
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: AssignExtraction(primary_zone="jira-engine",
                                                         secondary_zones=["memory-core"]))
    a = ca.assign_zone(_p(57, "jira idx"), TAX)
    assert a.issue_number == 57
    assert a.primary_zone == "jira-engine"
    assert a.secondary_zones == ["memory-core"]


def test_assign_other_when_unknown_zone(monkeypatch):
    # model returns a zone not in the taxonomy -> coerce to "other"
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: AssignExtraction(primary_zone="hallucinated", secondary_zones=[]))
    a = ca.assign_zone(_p(99, "weird"), TAX)
    assert a.primary_zone == "other"
