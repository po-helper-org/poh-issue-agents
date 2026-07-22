from shared.workflow_types import (
    SolutionProfile, ClusterMember, Cluster, ClusterSet,
    UnifyingIssueDraft, ConsolidationInput,
)


def test_types_construct_and_default():
    p = SolutionProfile(issue_number=59, title="FTS search layer",
                        problem_essence="grep is token-heavy",
                        proposed_mechanism="FTS + dependency graph engine",
                        target="cut context-assembly token cost",
                        domain="memory-core", anchors=["grep/echo"],
                        advisor_label="advisor:feature-request")
    m = ClusterMember(issue_number=59, role="primary",
                      contributed_requirement="FTS over docs")
    c = Cluster(cluster_id="memory-core-search", mechanism="FTS engine",
                target="cut token cost", members=[m], cross_links=[])
    cs = ClusterSet(clusters=[c], orphans=[])
    d = UnifyingIssueDraft(cluster_id="memory-core-search", title="Search engine",
                           body_markdown="# ...", source_issue_numbers=[59])
    cfg = ConsolidationInput(repo="kibarik/po-helper")
    assert cfg.exclude_labels == ["advisor:consultation", "advisor:existing-functionality"]
    assert cs.clusters[0].members[0].role == "primary"
    assert d.source_issue_numbers == [59]
