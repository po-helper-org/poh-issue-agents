"""Словарь «метка → команда»: у команды ровно один источник правды, а метки
исхода, которые агент ставит себе сам, не запускают ничего."""

from shared.commands import (
    ANALYZE,
    ESTIMATE,
    _COMMANDS,
    done_label,
    failed_label,
    parse_label_command,
    run_label,
    running_labels,
)


def test_run_label_starts_the_command():
    assert parse_label_command("run:analyze") == ANALYZE
    assert parse_label_command("run:estimate") == ESTIMATE


def test_outcome_labels_start_nothing():
    """Защита от петли: агент ставит done:/failed: сам, и они прилетают обратно
    событием issues.labeled. Совпади они с триггером — прогон запускал бы себя."""
    for command in (ANALYZE, ESTIMATE):
        assert parse_label_command(done_label(command)) is None
        assert parse_label_command(failed_label(command)) is None


def test_unknown_and_human_decision_labels_are_not_commands():
    for label in ("wontfix", "research-me", "bug-me", "build-me", "run:", "run:nope"):
        assert parse_label_command(label) is None


def test_label_is_case_insensitive_like_the_slash_command():
    assert parse_label_command("run:ANALYZE") == ANALYZE


def test_every_slash_command_has_a_label_trigger_and_back():
    """Единый источник правды: набор команд один, метки из него выводятся."""
    for command in set(_COMMANDS.values()):
        assert parse_label_command(run_label(command)) == command


def test_running_labels_include_legacy_analyzing():
    """`analyzing` — метка «идёт прогон» прежних версий: её снимает та же
    финализация, иначе на Issue останется analyzing вместе с done:analyze."""
    assert run_label(ANALYZE) in running_labels(ANALYZE)
    assert "analyzing" in running_labels(ANALYZE)
    assert running_labels(ESTIMATE) == ("run:estimate",)


def test_label_names_match_protocol_v1_namespace_scheme():
    assert run_label(ANALYZE) == "run:analyze"
    assert done_label(ANALYZE) == "done:analyze"
    assert failed_label(ESTIMATE) == "failed:estimate"
