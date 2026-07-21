import consolidation_activities as ca
from consolidation_activities import ProfileExtraction
from shared.workflow_types import IssueInput


def test_fetch_returns_bodyless(monkeypatch):
    monkeypatch.setattr(ca.github_client, "list_open_issues",
                        lambda repo, limit: [{"number": 5, "title": "t", "body": "BIG BODY",
                                              "labels": []}])
    from shared.workflow_types import ConsolidationInput
    refs = ca.fetch_open_issues(ConsolidationInput(repo="o/r"))
    assert refs[0].issue_number == 5
    assert refs[0].body == ""  # body stripped from history payload


def test_extract_self_fetches_body(monkeypatch):
    seen = {}
    monkeypatch.setattr(ca.github_client, "get_issue_body",
                        lambda repo, n: "FETCHED BODY")
    monkeypatch.setattr(ca, "_load_prompt", lambda name: "fake")
    monkeypatch.setattr(ca.llm, "extract",
                        lambda system, user, response_model, **k: seen.update(user=user) or
                        ProfileExtraction(problem_essence="e", proposed_mechanism="m",
                                          target="t", domain="d", anchors=["a"]))
    issue = IssueInput(repo="o/r", issue_number=5, title="t", body="",
                       author_login="", author_type="User")
    ca.extract_solution_profile(issue)
    assert "FETCHED BODY" in seen["user"]  # body pulled inside the activity
