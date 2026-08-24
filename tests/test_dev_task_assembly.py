"""Сборка постановки разработки: заголовки и усечение по приоритету.

Оба дефекта, которые здесь закрыты, были молчаливыми: постановка собиралась,
файл писался, прогон шёл — и часть содержимого просто отсутствовала.
"""
import activities as a


TITLE = "Починить кнопку"
ISSUE_N = 42
MAIN = f"# Задача: реализовать Issue #{ISSUE_N}"


# ───────────────────── разбор на секции ─────────────────────

def test_heading_is_the_first_line_not_the_whole_block():
    """Раньше весь кусок становился именем секции, и содержимое исчезало."""
    secs = a._split_sections(["## Как работать\nнаходки пиши в .followups.md"])
    assert secs == [("## Как работать", "находки пиши в .followups.md")]


def test_rules_block_reaches_the_agent():
    """Блок правил репозитория терялся целиком вместе с этой инструкцией."""
    parts = [MAIN, f"## {TITLE}", "тело", a._DEV_FALLBACK_RULES]
    task = a._join_sections(a._split_sections(parts))
    assert ".followups.md" in task


def test_joined_task_keeps_section_headings():
    parts = [MAIN, f"## {TITLE}", "тело", "## Системные требования", "требования"]
    task = a._join_sections(a._split_sections(parts))
    assert MAIN in task
    assert "## Системные требования" in task


def test_block_starting_with_newline_survives():
    """Единственный блок, переживавший прежний разбор, обязан пережить и новый."""
    parts = [MAIN, "тело", "\nПравила организации:\n- пункт"]
    assert "- пункт" in a._join_sections(a._split_sections(parts))


def test_empty_sections_do_not_produce_blank_blocks():
    task = a._join_sections([("", ""), ("## Пусто", "")])
    assert task.strip() == "## Пусто"


# ───────────────────── усечение по приоритету ─────────────────────

def _cut(sections, limit):
    return a._apply_size_limit(sections, limit, ISSUE_N, TITLE)


def test_nothing_is_dropped_when_it_fits():
    secs = [(MAIN, "тело"), ("## Обсуждение", "разговор")]
    kept, dropped = _cut(secs, 10_000)
    assert kept == secs and dropped == []


def test_lowest_priority_is_dropped_first():
    """Заявленный порядок: тело > план > артефакты > обсуждение > правила."""
    secs = [(MAIN, "т" * 100), ("## План декомпозиции", "п" * 100),
            ("## Системные требования", "а" * 100), ("## Обсуждение", "о" * 100),
            ("## Как работать", "р" * 100)]
    kept, dropped = _cut(secs, 350)
    names = [n for n, _ in kept]
    assert MAIN in names
    assert dropped[0] == "## Как работать"
    assert "## Обсуждение" in dropped


def test_indices_are_recomputed_after_each_removal():
    """Прежний код брал один и тот же индекс и резал подряд от него."""
    secs = [(MAIN, "т" * 50)] + [(f"## Обсуждение {i}", "о" * 50) for i in range(10)]
    kept, dropped = _cut(secs, 200)
    kept_names = [n for n, _ in kept]
    assert len(set(kept_names)) == len(kept_names)
    assert MAIN in kept_names


def test_task_body_is_never_dropped():
    """Лучше превысить потолок, чем отдать агенту постановку без задачи."""
    secs = [(MAIN, "т" * 100_000)]
    kept, dropped = _cut(secs, 100)
    assert [n for n, _ in kept] == [MAIN]
    assert dropped == []


def test_artifacts_are_protected_above_discussion():
    secs = [(MAIN, "т" * 50), ("### system_requirements.md", "а" * 100),
            ("## Обсуждение", "о" * 100)]
    # Потолок выбран так, чтобы вместились тело и артефакт, но не обсуждение.
    kept, dropped = _cut(secs, 260)
    assert "## Обсуждение" in dropped
    assert "### system_requirements.md" in [n for n, _ in kept]


def test_overflow_is_reachable_with_default_caps():
    """Сумма жёстких потолков артефактов равна общему потолку постановки."""
    assert a.DEV_ARTIFACT_MAX_CHARS * 5 >= a.DEV_TASK_MAX_CHARS
