import consolidation_activities as ca
from consolidation_activities import (ClusterExtraction, ClusterOut, MemberOut,
                                      MergeAssignment, MergeExtraction)
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


def test_cluster_mapreduce_merges_across_batches(monkeypatch):
    # >CLUSTER_BATCH_SIZE profiles => batched. Each batch returns a local cluster
    # for the same mechanism; the merge pass must re-unite them into ONE cluster.
    monkeypatch.setattr(ca, "CLUSTER_BATCH_SIZE", 12)
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake prompt")

    batch = {"n": 0}

    def fake_extract(system, user, response_model, model=None):
        if response_model is ClusterExtraction:
            batch["n"] += 1
            n = batch["n"]  # one local cluster per batch, member # = batch index
            return ClusterExtraction(clusters=[ClusterOut(
                mechanism="graph memory core", target="unify",
                members=[MemberOut(issue_number=n, role="primary",
                                   contributed_requirement="x")])], orphans=[])
        if response_model is MergeExtraction:
            # both local clusters (indices 0 and 1) share one canonical key
            return MergeExtraction(assignments=[
                MergeAssignment(cluster_index=0, group_key="graph-core"),
                MergeAssignment(cluster_index=1, group_key="graph-core")])
        raise AssertionError(f"unexpected response_model {response_model}")

    monkeypatch.setattr(ca.llm, "extract", fake_extract)
    profiles = [_p(i, "graph memory core", "unify") for i in range(1, 15)]  # 14 -> 2 batches
    cs = ca.cluster_profiles(profiles)

    assert batch["n"] == 2                       # ran two map batches
    assert len(cs.clusters) == 1                 # merge collapsed them into one
    assert sorted(m.issue_number for m in cs.clusters[0].members) == [1, 2]
