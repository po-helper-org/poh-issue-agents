import consolidation_activities as ca
from consolidation_activities import SynthOut
from shared.workflow_types import Cluster, ClusterMember, SolutionProfile


def test_synth_builds_draft_with_sources(monkeypatch):
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: SynthOut(title="Unify search",
                                                 body_markdown="# Search\n- req from #1"))
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake prompt")
    cluster = Cluster(cluster_id="cluster-1-2", mechanism="FTS", target="cut cost",
                      members=[ClusterMember(1, "primary", "FTS over docs"),
                               ClusterMember(2, "secondary", "index JIRA")],
                      cross_links=[])
    profiles = [SolutionProfile(1, "t1", "p", "FTS", "cut cost", "memory-core",
                                ["a"], "advisor:feature-request")]
    d = ca.synthesize_unifying_issue(cluster, profiles)
    assert d.cluster_id == "cluster-1-2"
    assert d.source_issue_numbers == [1, 2]
    assert d.title == "Unify search"
