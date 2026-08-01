from shared.commands import ANALYZE, ESTIMATE, build_analyze_input, parse_command
from shared.workflow_ids import analysis_workflow_id


def test_recognises_bare_command():
    assert parse_command("/analyze") == ANALYZE


def test_recognises_command_with_trailing_text():
    assert parse_command("/analyze  спроектируй решение") == ANALYZE


def test_recognises_command_case_insensitively():
    assert parse_command("/ANALYZE") == ANALYZE


def test_recognises_estimate_from_same_registry():
    assert parse_command("/estimate") == ESTIMATE


def test_ignores_command_not_at_start():
    assert parse_command("см. выше /analyze") is None


def test_ignores_quoted_command():
    # Цитата (строка с '>') командой не считается: ответ с процитированной
    # командой не должен запускать её повторно.
    assert parse_command("> /analyze") is None


def test_ignores_plain_comment():
    assert parse_command("это обычный ответ на уточнение") is None


def test_ignores_empty_and_whitespace():
    assert parse_command("") is None
    assert parse_command("   ") is None


def test_analysis_workflow_id_is_distinct_from_lifecycle_id():
    wf_id = analysis_workflow_id("o/r", 5)
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
