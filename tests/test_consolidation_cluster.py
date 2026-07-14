import consolidation_activities as ca
from consolidation_activities import ClusterExtraction, ClusterOut, MemberOut
from shared.workflow_types import SolutionProfile


def _p(n, mech, target):
    return SolutionProfile(issue_number=n, title=f"t{n}", problem_essence="p",
                           proposed_mechanism=mech, target=target, domain="d",
                           anchors=["a"], advisor_label="advisor:feature-request")


def test_cluster_splits_same_mechanism_divergent_target(monkeypatch):
    # Model returns two clusters: same mechanism, different target (the #111 case)
    ext = ClusterExtraction(
        clusters=[
            ClusterOut(mechanism="graph memory core", target="launch new store",
                       members=[MemberOut(issue_number=1, role="primary",
                                          contributed_requirement="store nodes")],
                       cross_links=[]),
            ClusterOut(mechanism="graph memory core", target="migrate legacy store",
                       members=[MemberOut(issue_number=2, role="primary",
                                          contributed_requirement="migrate data")],
                       cross_links=[]),
        ], orphans=[])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: ext)
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake prompt")
    profiles = [_p(1, "graph memory core", "launch new store"),
                _p(2, "graph memory core", "migrate legacy store")]
    cs = ca.cluster_profiles(profiles)
    assert len(cs.clusters) == 2  # NOT merged despite identical mechanism
    ids = {c.cluster_id for c in cs.clusters}
    assert len(ids) == 2  # deterministic distinct slugs


def test_cluster_slug_is_deterministic():
    assert ca._slug([3, 1, 2]) == ca._slug([1, 2, 3])
