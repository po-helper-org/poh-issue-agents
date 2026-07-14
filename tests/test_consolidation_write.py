import consolidation_activities as ca
from shared.workflow_types import ClusterSet, Cluster, ClusterMember, UnifyingIssueDraft


def test_write_pr_composes_overview_and_files(monkeypatch):
    captured = {}
    monkeypatch.setattr(ca.github_client, "create_pr_with_files",
                        lambda repo, branch, base, files, title, body: captured.update(
                            files=files, title=title) or "http://pr/1")
    cs = ClusterSet(clusters=[Cluster("cluster-1", "FTS", "cut cost",
                                      [ClusterMember(1, "primary", "x")], [])],
                    orphans=[9])
    drafts = [UnifyingIssueDraft("cluster-1", "Unify", "# body", [1])]
    url = ca.write_consolidation_pr(cs, drafts, repo="o/r")
    assert url == "http://pr/1"
    assert "docs/consolidation/overview.md" in captured["files"]
    assert "docs/consolidation/unifying/cluster-1.md" in captured["files"]
