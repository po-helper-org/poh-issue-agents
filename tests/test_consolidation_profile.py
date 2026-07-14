import consolidation_activities as ca
from consolidation_activities import ProfileExtraction
from shared.workflow_types import IssueInput


def test_extract_profile_maps_fields(monkeypatch):
    fake = ProfileExtraction(problem_essence="grep costs tokens",
                             proposed_mechanism="FTS engine", target="cut cost",
                             domain="memory-core", anchors=["grep/echo"])
    monkeypatch.setattr(ca.llm, "extract", lambda *a, **k: fake)
    issue = IssueInput(repo="o/r", issue_number=59, title="Search layer",
                       body="replace grep with FTS", author_login="u",
                       author_type="User")
    p = ca.extract_solution_profile(issue)
    assert p.issue_number == 59
    assert p.proposed_mechanism == "FTS engine"
    assert p.target == "cut cost"
    assert p.anchors == ["grep/echo"]
