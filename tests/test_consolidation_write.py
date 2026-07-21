import consolidation_activities as ca
from shared.workflow_types import DeliveryZone, Increment, Taxonomy, UnifyingIssueDraft


def test_write_pr_composes_overview_and_files(monkeypatch):
    captured = {}
    monkeypatch.setattr(ca.github_client, "create_pr_with_files",
                        lambda repo, branch, base, files, title, body: captured.update(
                            files=files, title=title) or "http://pr/1")
    tax = Taxonomy([DeliveryZone("jira", "b", "s")])
    incs = [Increment("jira:MVP", "r", [1])]
    drafts = [UnifyingIssueDraft("jira:MVP", "Unify", "# body", [1])]
    url = ca.write_consolidation_pr(tax, incs, drafts, repo="o/r")
    assert url == "http://pr/1"
    assert "docs/consolidation/overview.md" in captured["files"]
    assert "docs/consolidation/unifying/jira-MVP.md" in captured["files"]
