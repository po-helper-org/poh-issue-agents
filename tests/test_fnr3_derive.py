import consolidation_activities as ca
from consolidation_activities import TaxonomyExtraction, ZoneOut
from shared.workflow_types import SolutionProfile


def _p(n, mech):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target="tg", domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


def test_derive_taxonomy_maps_zones(monkeypatch):
    ext = TaxonomyExtraction(zones=[
        ZoneOut(name="jira-engine", boundary="одна итерация JIRA", surface="JIRA-Connector")])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: ext)
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    tax = ca.derive_taxonomy([_p(57, "jira idx"), _p(60, "jira meta")], None)
    assert [z.name for z in tax.zones] == ["jira-engine"]


def test_derive_taxonomy_includes_prior(monkeypatch):
    captured = {}
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda system, user, model_class, **k: captured.update(user=user) or
                        TaxonomyExtraction(zones=[ZoneOut(name="x", boundary="b", surface="s")]))
    from shared.workflow_types import Taxonomy, DeliveryZone
    ca.derive_taxonomy([_p(1, "m")], Taxonomy(zones=[DeliveryZone("prev-zone", "b", "s")]))
    assert "prev-zone" in captured["user"]  # prior zones fed into the prompt
