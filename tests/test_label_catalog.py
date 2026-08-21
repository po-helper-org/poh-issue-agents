"""Каталог меток: проверка синхронизации с каноническими константами.

Каталог собирается из тех же констант, что и рабочий код. Если константа
добавлена в код, но не отражена в каталоге, тесты должны ронять набор — иначе
каталог тихо разъедется с контуром, как триггерные метки в первой версии.

Тесты проверяют:
1. Каждое семейство меток полностью соответствует канонической константе
2. Каталог не содержит лишних меток, которых нет в константах
3. Новая метка в коде, не добавленная в каталог, роняет тесты
"""

import pytest

from shared import label_catalog, labels, lifecycle, commands


# --- advisor:* метки ---

def test_advisor_labels_match_constant():
    """advisor:* метки берутся из одной константы — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    assert catalog_families["advisors"] == labels.ADVISOR_LABELS
    assert all(label.startswith("advisor:") for label in labels.ADVISOR_LABELS)


def test_catalog_includes_all_advisor_labels():
    """Новая advisor метка в коде должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    for label in labels.ADVISOR_LABELS:
        assert label in catalog, f"advisor метка {label} отсутствует в каталоге"


def test_catalog_has_no_extra_advisor_labels():
    """Каталог не должен содержать advisor меток, которых нет в константе."""
    catalog_families = label_catalog.label_families()
    advisor_in_catalog = {label for label in catalog_families["advisors"] if label.startswith("advisor:")}
    assert advisor_in_catalog == labels.ADVISOR_LABELS


# --- priority:* метки ---

def test_priority_labels_match_constant():
    """priority:* метки берутся из одной константы — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    assert catalog_families["priorities"] == labels.PRIORITY_LABELS
    assert all(label.startswith("priority:") for label in labels.PRIORITY_LABELS)


def test_catalog_includes_all_priority_labels():
    """Новая priority метка в коде должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    for label in labels.PRIORITY_LABELS:
        assert label in catalog, f"priority метка {label} отсутствует в каталоге"


def test_catalog_has_no_extra_priority_labels():
    """Каталог не должен содержать priority меток, которых нет в константе."""
    catalog_families = label_catalog.label_families()
    priority_in_catalog = {label for label in catalog_families["priorities"] if label.startswith("priority:")}
    assert priority_in_catalog == labels.PRIORITY_LABELS


def test_priority_labels_match_toml_config():
    """priority:* метки должны соответствовать записям в config/priority-weights.toml."""
    import tomli
    import pathlib
    
    config_path = pathlib.Path(__file__).parent.parent / "config" / "priority-weights.toml"
    if not config_path.exists():
        pytest.skip("config/priority-weights.toml не найден")
    
    with open(config_path, "rb") as f:
        config = tomli.load(f)
    
    # Config имеет thresholds (p0_min, p1_min, p2_min) и bug_severity_override
    thresholds = set(config.get("thresholds", {}).keys())
    # Извлекаем уровни приоритетов из названий порогов (p0_min -> P0, и т.д.)
    config_priorities = {t.split("_")[0].upper() for t in thresholds}
    
    # Добавляем P3 как уровень по умолчанию (ниже p2_min)
    config_priorities.add("P3")

    catalog_priorities = {label.split(":")[1] for label in labels.PRIORITY_LABELS if label.startswith("priority:")}
    
    assert config_priorities == catalog_priorities, (
        f"priority метки ({catalog_priorities}) не соответствуют записям в "
        f"config/priority-weights.toml ({config_priorities})"
    )


# --- плоские метки ---

def test_flat_labels_match_constant():
    """Плоские метки берутся из одной константы — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    assert catalog_families["flat"] == labels.FLAT_LABELS


def test_catalog_includes_all_flat_labels():
    """Новая плоская метка в коде должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    for label in labels.FLAT_LABELS:
        assert label in catalog, f"плоская метка {label} отсутствует в каталоге"


def test_catalog_has_no_extra_flat_labels():
    """Каталог не должен содержать плоских меток, которых нет в константе."""
    catalog_families = label_catalog.label_families()
    assert catalog_families["flat"] == labels.FLAT_LABELS


def test_flat_labels_do_not_use_colons():
    """Плоские метки не используют двоеточие — это зарезервировано за пространствами имён."""
    for label in labels.FLAT_LABELS:
        assert ":" not in label, f"плоская метка {label} использует двоеточие"


# --- phase:* метки ---

def test_phase_labels_match_lifecycle_constant():
    """phase:* метки выводятся из lifecycle.PHASES — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    expected_phases = frozenset(f"phase:{phase}" for phase in lifecycle.PHASES)
    assert catalog_families["phases"] == expected_phases


def test_catalog_includes_all_phase_labels():
    """Новая фаза в lifecycle.PHASES должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    for phase in lifecycle.PHASES:
        label = f"phase:{phase}"
        assert label in catalog, f"фазовая метка {label} отсутствует в каталоге"


def test_catalog_has_no_extra_phase_labels():
    """Каталог не должен содержать phase меток, которых нет в lifecycle.PHASES."""
    catalog_families = label_catalog.label_families()
    phase_in_catalog = {label for label in catalog_families["phases"] if label.startswith("phase:")}
    expected_phases = {f"phase:{phase}" for phase in lifecycle.PHASES}
    assert phase_in_catalog == expected_phases


# --- command метки (run:*, done:*, failed:*) ---

def test_command_labels_match_commands_constant():
    """Метки команд выводятся из commands._COMMANDS — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    expected_commands = _build_expected_command_labels()
    assert catalog_families["commands"] == expected_commands


def test_catalog_includes_all_command_labels():
    """Новая команда в commands._COMMANDS должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    for cmd in commands._COMMANDS:
        assert commands.run_label(cmd) in catalog, f"run:{cmd} отсутствует в каталоге"
        assert commands.done_label(cmd) in catalog, f"done:{cmd} отсутствует в каталоге"
        assert commands.failed_label(cmd) in catalog, f"failed:{cmd} отсутствует в каталоге"


def test_catalog_has_no_extra_command_labels():
    """Каталог не должен содержать командных меток, которых нет в константах."""
    catalog_families = label_catalog.label_families()
    command_in_catalog = catalog_families["commands"]
    expected_commands = _build_expected_command_labels()
    assert command_in_catalog == expected_commands


def _build_expected_command_labels():
    """Вспомогательная функция: собрать все командные метки из констант."""
    result = set()
    for cmd in commands._COMMANDS:
        result.add(commands.run_label(cmd))
        result.add(commands.done_label(cmd))
        result.add(commands.failed_label(cmd))
    # Legacy labels
    result.update(commands._LEGACY_RUNNING_LABELS.get(commands.ANALYZE, ()))
    return frozenset(result)


# --- протокольные метки ---

def test_protocol_labels_match_constant():
    """Протокольные метки берутся из shared.labels — расхождение невозможно."""
    catalog_families = label_catalog.label_families()
    expected_protocol = frozenset({
        labels.NEEDS_HUMAN_TRIAGE,
        labels.LEGACY_NEEDS_HUMAN_TRIAGE,
        labels.READY_FOR_DEV,
        labels.AGENTS_OFF,
        labels.ORIGIN_AGENT,
    })
    assert catalog_families["protocol"] == expected_protocol


def test_catalog_includes_all_protocol_labels():
    """Новая протокольная метка должна быть и в каталоге."""
    catalog = label_catalog.all_labels()
    protocol_labels = {
        labels.NEEDS_HUMAN_TRIAGE,
        labels.LEGACY_NEEDS_HUMAN_TRIAGE,
        labels.READY_FOR_DEV,
        labels.AGENTS_OFF,
        labels.ORIGIN_AGENT,
    }
    for label in protocol_labels:
        assert label in catalog, f"протокольная метка {label} отсутствует в каталоге"


# --- целостность каталога ---

def test_catalog_is_frozen_set():
    """Каталог возвращает frozenset — защита от случайных модификаций."""
    catalog = label_catalog.all_labels()
    assert isinstance(catalog, frozenset)


def test_label_families_are_frozen_sets():
    """Каждое семейство возвращает frozenset — защита от модификаций."""
    families = label_catalog.label_families()
    for name, family in families.items():
        assert isinstance(family, frozenset), f"семейство {name} не frozenset"


def test_all_families_union_equals_catalog():
    """Объединение всех семейств должно давать полный каталог."""
    families = label_catalog.label_families()
    union = set()
    for family in families.values():
        union.update(family)
    
    catalog = label_catalog.all_labels()
    assert union == catalog, "объединение семейств не равно каталогу"


def test_catalog_has_no_duplicates():
    """Каталог не должен содержать дубликатов."""
    catalog = label_catalog.all_labels()
    assert len(catalog) == len(set(catalog)), "каталог содержит дубликаты"


def test_all_labels_are_strings():
    """Все метки в каталоге должны быть строками."""
    catalog = label_catalog.all_labels()
    for label in catalog:
        assert isinstance(label, str), f"метка {label} не является строкой"
        assert label.strip(), f"метка {label} пустая или состоит из пробелов"


# --- регрессионные тесты ---

def test_catalog_grows_with_lifecycle():
    """Регрессия: новая фаза, не попавшая в каталог, роняет набор.
    
    Историческая проблема: триггерные метки в первой версии каталога были
    списком из трёх имён, и каталог не знал `not-duplicate` и
    `confirm-duplicate`, хотя `HUMAN_DECISION_LABELS` объявляет пять.
    
    Этот тест гарантирует, что добавление новой фазы в lifecycle.PHASES
    автоматически роняет тесты, если не обновить каталог.
    """
    # Проверяем, что каждая фаза из lifecycle.PHASES есть в каталоге
    catalog = label_catalog.all_labels()
    for phase in lifecycle.PHASES:
        label = f"phase:{phase}"
        assert label in catalog, (
            f"фаза {phase} из lifecycle.PHASES отсутствует в каталоге. "
            f"Добавь её в lifecycle.PHASES или обнови каталог."
        )


def test_catalog_grows_with_commands():
    """Регрессия: новая команда, не попавшая в каталог, роняет набор.
    
    Аналогично test_catalog_grows_with_lifecycle, но для команд.
    """
    catalog = label_catalog.all_labels()
    for cmd in commands._COMMANDS:
        assert commands.run_label(cmd) in catalog, (
            f"команда {cmd} из commands._COMMANDS отсутствует в каталоге. "
            f"Добавь её в commands._COMMANDS или обнови каталог."
        )
        assert commands.done_label(cmd) in catalog, (
            f"метка done:{cmd} отсутствует в каталоге"
        )
        assert commands.failed_label(cmd) in catalog, (
            f"метка failed:{cmd} отсутствует в каталоге"
        )


def test_catalog_grows_with_advisor_labels():
    """Регрессия: новая advisor метка, не попавшая в каталог, роняет набор."""
    catalog = label_catalog.all_labels()
    for label in labels.ADVISOR_LABELS:
        assert label in catalog, (
            f"advisor метка {label} отсутствует в каталоге. "
            f"Добавь её в labels.ADVISOR_LABELS или обнови каталог."
        )


def test_catalog_grows_with_priority_labels():
    """Регрессия: новая priority метка, не попавшая в каталог, роняет набор."""
    catalog = label_catalog.all_labels()
    for label in labels.PRIORITY_LABELS:
        assert label in catalog, (
            f"priority метка {label} отсутствует в каталоге. "
            f"Добавь её в labels.PRIORITY_LABELS или обнови каталог."
        )


def test_catalog_grows_with_flat_labels():
    """Регрессия: новая плоская метка, не попавшая в каталог, роняет набор."""
    catalog = label_catalog.all_labels()
    for label in labels.FLAT_LABELS:
        assert label in catalog, (
            f"плоская метка {label} отсутствует в каталоге. "
            f"Добавь её в labels.FLAT_LABELS или обнови каталог."
        )
