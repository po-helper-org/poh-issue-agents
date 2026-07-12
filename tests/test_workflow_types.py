from shared.workflow_types import IssueInput


def test_interactive_defaults_true():
    issue = IssueInput(
        repo="o/r", issue_number=1, title="t", body="b",
        author_login="u", author_type="User",
    )
    assert issue.interactive is True


def test_interactive_can_be_false():
    issue = IssueInput(
        repo="o/r", issue_number=1, title="t", body="b",
        author_login="u", author_type="User", interactive=False,
    )
    assert issue.interactive is False
