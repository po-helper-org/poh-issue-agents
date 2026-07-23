import consolidation_activities as ca
from consolidation_activities import SynthOut
from shared.workflow_types import Increment, SolutionProfile


def test_synth_builds_draft_with_sources(monkeypatch):
    monkeypatch.setattr(ca.llm, "extract",
                        lambda *a, **k: SynthOut(title="Unify search",
                                                 body_markdown="# Search\n- req from #1"))
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake prompt")
    inc = Increment("jira:MVP", "r", [1, 2])
    profiles = [SolutionProfile(1, "t1", "p", "FTS", "cut cost", "memory-core",
                                ["a"], "advisor:feature-request")]
    d = ca.synthesize_unifying_issue(inc, profiles)
    assert d.cluster_id == "jira:MVP"
    assert d.source_issue_numbers == [1, 2]
    assert d.title == "Unify search"
