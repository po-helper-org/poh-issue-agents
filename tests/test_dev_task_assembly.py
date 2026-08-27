"""Сборка постановки разработки: заголовки и усечение по приоритету.

Оба дефекта, которые здесь закрыты, были молчаливыми: постановка собиралась,
файл писался, прогон шёл — и часть содержимого просто отсутствовала.
"""
from pathlib import Path

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
    """Порядок вытеснения: правила организации > обсуждение > артефакты >
    инструкции контура > план > тело задачи.

    Инструкции контура стоят ВЫШЕ артефактов намеренно — см. регрессию
    прогона #105 ниже: без них агент коммитит сам, и прогон встаёт.
    """
    secs = [(MAIN, "т" * 100), ("## План декомпозиции", "п" * 100),
            ("## Системные требования", "а" * 100), ("## Обсуждение", "о" * 100),
            ("## Как работать", "р" * 100),
            (a.ORG_RULES_HEADING, "о" * 100)]
    # Потолок подобран так, чтобы уцелели тело, план и инструкции контура —
    # то есть ровно то, без чего прогон не состоится.
    kept, dropped = _cut(secs, 400)
    names = [n for n, _ in kept]
    assert MAIN in names
    assert dropped[0] == a.ORG_RULES_HEADING
    assert "## Обсуждение" in dropped
    assert "## Как работать" in names, "инструкции контура вытесняются последними"


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


# ────────── регрессия прогона #105: правила организации выбили инструкции ──────────

def _contour_parts(org_rules_size=3500, artifacts_size=46000):
    """Постановка в том виде, в каком она собирается на живом прогоне."""
    return [
        MAIN,
        f"## {TITLE}",
        "тело задачи",
        "## Системные требования",
        "### system_requirements.md\n" + "т" * artifacts_size,
        "## Как работать\nКоммитить самому не надо — коммит и PR делает контур.",
        a._DEV_REPOWISE_RULES,
        a._DEV_REFLECT_NOTE_RULE,
        f"{a.ORG_RULES_HEADING}\n" + "- правило организации\n" * (org_rules_size // 22),
    ]


def test_org_rules_are_evicted_before_contour_instructions():
    """Прогон #105: блок правил вытеснил секцию «Как работать», где написано
    «коммитить самому не надо». Агент закоммитил в свою ветку, публикация не
    нашла изменений, прогон встал.

    Цена несимметрична: потеря требований даёт неполную правку, потеря
    инструкций контура ломает прогон целиком.
    """
    kept, dropped = _cut(a._split_sections(_contour_parts()), a.DEV_TASK_MAX_CHARS)
    names = [n for n, _ in kept]

    assert "Коммитить самому не надо" in a._join_sections(kept)
    assert any(n.startswith("## Как работать") for n in names)
    assert any(n.startswith(a.ORG_RULES_HEADING) for n in dropped)


def test_org_rules_never_evict_the_index_or_the_reflect_note():
    kept, dropped = _cut(a._split_sections(_contour_parts()), a.DEV_TASK_MAX_CHARS)
    names = [n for n, _ in kept]
    assert any(n.startswith("## Индекс кода") for n in names)
    assert any(n.startswith("## След решения") for n in names)


def test_contour_instructions_outrank_artifacts():
    """Артефакты стоят пятьдесят килобайт, инструкции — два. Ломает прогон
    потеря вторых, а не первых."""
    assert a._section_rank("## Как работать", ISSUE_N, TITLE) < \
           a._section_rank("### system_requirements.md", ISSUE_N, TITLE)


def test_unknown_section_is_treated_as_contour_instructions():
    """Свои правила репозитория приходят со своим заголовком. Терять их нельзя."""
    assert a._section_rank("## Наши правила", ISSUE_N, TITLE) == a._RANK_CONTOUR


def test_org_rules_block_is_its_own_section():
    """Приклеенный к соседу блок делит его судьбу при усечении."""
    secs = a._split_sections(["## Как работать\nправила",
                              f"{a.ORG_RULES_HEADING}\n- пункт"])
    assert len(secs) == 2
    assert secs[1][0] == a.ORG_RULES_HEADING


def test_everything_fits_when_artifacts_are_modest():
    kept, dropped = _cut(a._split_sections(_contour_parts(artifacts_size=5000)),
                         a.DEV_TASK_MAX_CHARS)
    assert dropped == []


# ────────── правило фокуса переживает свои правила репозитория ──────────

def test_focus_rule_survives_repository_own_rules(monkeypatch, tmp_path):
    """Правило фокуса обязано доехать и в репозиторий со своими правилами.

    Свой `.openhands/task-rules.md` целевого репозитория вытесняет запасные
    правила контура ЦЕЛИКОМ. Это уже стоило потери блока правил и инструкции
    про файл находок: они жили внутри запасных правил и исчезали в самых
    обычных репозиториях — тех, у кого свои правила есть.
    """
    import activities as a

    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None: "## Свои правила репозитория"
                        if path.endswith("task-rules.md") else "")

    def _fake_clone(repo, dest, branch=None):
        # `_dev_prepare` читает `.openhands/task-rules.md` локальным файлом
        # клона (`rules.exists()` / `rules.read_text()`), а не через
        # `github_client.get_file` — двойник обязан положить файл НА ДИСК,
        # иначе `rules.exists()` всегда False и репозиторий со своими
        # правилами неотличим в тесте от репозитория без них.
        rules_dir = Path(dest) / ".openhands"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "task-rules.md").write_text(
            "## Свои правила репозитория", encoding="utf-8")

    monkeypatch.setattr(a, "_clone_repo", _fake_clone)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-1")

    assert "Свои правила репозитория" in task, "правила репозитория потерялись"
    assert "пройдёт ли сценарий без этого" in task, "правило фокуса не доехало"
