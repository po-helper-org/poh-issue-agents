from shared.commands import (
    analysis_workflow_id_for,
    build_analyze_input,
    is_analyze_command,
)


def test_recognises_bare_command():
    assert is_analyze_command("/analyze") is True


def test_recognises_command_with_trailing_text():
    assert is_analyze_command("/analyze  спроектируй решение") is True


def test_recognises_command_case_insensitively():
    assert is_analyze_command("/ANALYZE") is True


def test_ignores_command_not_at_start():
    assert is_analyze_command("см. выше /analyze") is False


def test_ignores_plain_comment():
    assert is_analyze_command("это обычный ответ на уточнение") is False


def test_ignores_empty_and_none():
    assert is_analyze_command("") is False
    assert is_analyze_command(None) is False
    assert is_analyze_command("   ") is False


def test_analysis_workflow_id_is_distinct_from_lifecycle_id():
    wf_id = analysis_workflow_id_for("o/r", 5)
    assert wf_id == "analysis-o/r-5"
    assert wf_id != "issue-o/r-5"


def test_build_analyze_input_extracts_payload_fields():
    payload = {
        "repository": {"full_name": "o/r"},
        "issue": {"number": 5, "title": "Ревизия reliability", "body": "текст"},
        "comment": {"id": 999},
    }
    analyze = build_analyze_input(payload)
    assert analyze.repo == "o/r"
    assert analyze.issue_number == 5
    assert analyze.title == "Ревизия reliability"
    assert analyze.body == "текст"
    assert analyze.comment_id == 999


def test_build_analyze_input_tolerates_null_body():
    payload = {
        "repository": {"full_name": "o/r"},
        "issue": {"number": 5, "title": "t", "body": None},
        "comment": {"id": 1},
    }
    assert build_analyze_input(payload).body == ""
