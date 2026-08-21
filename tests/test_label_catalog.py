"""Каталог меток собирается из кода, а не переписывается руками."""

from shared import commands, develop, lifecycle, pr_closing
from shared import labels as L
from shared.label_catalog import catalog


def test_every_phase_is_present():
    names = catalog()
    for phase in lifecycle.PHASES:
        assert lifecycle.phase_label(phase) in names


def test_command_labels_cover_all_three_outcomes():
    names = catalog()
    for command in commands._COMMANDS.values():
        assert f"{commands.RUN_PREFIX}{command}" in names
        assert f"{commands.DONE_PREFIX}{command}" in names
        assert f"{commands.FAILED_PREFIX}{command}" in names


def test_control_labels_are_present():
    names = catalog()
    for label in (L.NEEDS_HUMAN_TRIAGE, L.ORIGIN_AGENT, L.AGENTS_OFF,
                  L.READY_FOR_DEV, pr_closing.NEEDS_HUMAN_PR,
                  develop.IN_DEVELOPMENT_LABEL):
        assert label in names


def test_trigger_labels_are_present():
    names = catalog()
    assert {"research-me", "bug-me", "build-me"} <= set(names)


def test_every_entry_has_colour_and_description():
    for name, spec in catalog().items():
        assert spec.color.startswith("#"), name
        assert spec.description.strip(), name


def test_catalog_grows_with_lifecycle():
    """Новая фаза попадает в каталог сама — иначе он разъедется с контуром."""
    assert len([n for n in catalog() if n.startswith(lifecycle.PHASE_PREFIX)]) \
        == len(lifecycle.PHASES)
