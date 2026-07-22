from shared.commands import ESTIMATE, parse_command


def test_plain_command():
    assert parse_command("/estimate") == ESTIMATE


def test_case_insensitive():
    assert parse_command("/Estimate") == ESTIMATE


def test_leading_and_trailing_whitespace():
    assert parse_command("   /estimate  \n") == ESTIMATE


def test_leading_blank_lines_are_skipped():
    assert parse_command("\n\n/estimate") == ESTIMATE


def test_trailing_argument_is_ignored_in_v1():
    assert parse_command("/estimate заново") == ESTIMATE


def test_command_in_the_middle_of_text_is_not_a_command():
    assert parse_command("посмотри и потом /estimate") is None


def test_command_on_second_line_is_not_a_command():
    assert parse_command("контекст добавлен\n/estimate") is None


def test_quoted_command_is_not_a_command():
    assert parse_command("> /estimate\n\nуже запускал") is None


def test_similar_word_is_not_a_command():
    assert parse_command("/estimated") is None


def test_empty_body():
    assert parse_command("") is None


def test_unknown_command():
    assert parse_command("/deploy") is None
