"""Модель фаз: перечень, переходы, инициаторы и инвариант «фаза ↔ метка».

Проверяется не список констант, а свойства модели: достижимость, отсутствие
тупиков, полнота таблицы и то, что недопустимый переход падает, а не молча
перезаписывает состояние.
"""

import pytest

from shared import lifecycle as lc


# --- полнота и связность ---

def test_every_phase_has_a_transition_table():
    """Фаза без записи в таблице — состояние, из которого модель не знает выхода."""
    targets = {t.to for transitions in lc.TRANSITIONS.values() for t in transitions}
    unknown = targets - set(lc.TRANSITIONS)
    assert not unknown, f"переходы ведут в фазы без таблицы: {sorted(unknown)}"


def test_every_phase_is_reachable_from_created():
    """Недостижимая фаза — мёртвая запись в словаре."""
    unreachable = set(lc.PHASES) - lc.reachable_from(lc.CREATED)
    assert not unreachable, f"недостижимо из created: {sorted(unreachable)}"


def test_only_declared_phases_are_dead_ends():
    """Тупик, не объявленный терминальным, — почти наверняка забытый переход."""
    dead_ends = {phase for phase in lc.PHASES if not lc.TRANSITIONS[phase]}
    assert dead_ends == set(lc.TERMINAL)


def test_full_path_to_production_exists():
    """Главный путь эпика: от создания до прода, без разрывов."""
    path = [lc.CREATED, lc.CLASSIFIED, lc.BUSINESS_ANALYSIS, lc.SYSTEM_REQUIREMENTS,
            lc.GROOMED, lc.READY_FOR_DEV, lc.IN_DEVELOPMENT, lc.PR_OPEN,
            lc.PR_REVIEW, lc.MERGED, lc.TESTING, lc.RELEASED]
    for source, target in zip(path, path[1:]):
        assert lc.can(source, target), f"разрыв пути: {source} → {target}"


def test_bug_path_skips_analysis():
    """Решение по открытому вопросу: один перечень с пропусками, а не два
    подмножества. Путь бага короче — из классификации сразу к разработке."""
    assert lc.can(lc.CLASSIFIED, lc.READY_FOR_DEV)
    assert lc.initiator(lc.CLASSIFIED, lc.READY_FOR_DEV) == lc.HUMAN


# --- недопустимые переходы ---

def test_invalid_transition_raises_instead_of_overwriting():
    with pytest.raises(lc.InvalidTransition):
        lc.transition(lc.CREATED, lc.RELEASED)


def test_error_message_lists_what_was_possible():
    """Сообщение должно само говорить, что было допустимо вместо этого."""
    with pytest.raises(lc.InvalidTransition, match=lc.CLASSIFIED):
        lc.transition(lc.CREATED, lc.MERGED)


def test_unknown_phase_is_an_error():
    with pytest.raises(lc.InvalidTransition):
        lc.allowed("выдуманная-фаза")


def test_terminal_phases_have_no_way_out():
    for phase in lc.TERMINAL:
        assert lc.allowed(phase) == ()
        assert lc.is_terminal(phase)


# --- инициаторы ---

def test_initiator_is_recorded_for_every_transition():
    """«Ждём агента» и «ждём человека» — разные состояния для того, кто смотрит
    на очередь; без инициатора модель этого не различает."""
    known = {lc.AGENT, lc.HUMAN, lc.EXTERNAL}
    for phase, transitions in lc.TRANSITIONS.items():
        for t in transitions:
            assert t.initiator in known, f"{phase} → {t.to}: неизвестный инициатор"
            assert t.trigger, f"{phase} → {t.to}: не указано, чем инициируется"


def test_heavy_stage_is_started_by_a_human():
    """Дорогой прогон не начинается сам: то же решение, что в #7."""
    assert lc.initiator(lc.CLASSIFIED, lc.BUSINESS_ANALYSIS) == lc.HUMAN


def test_pr_phases_are_driven_by_external_agents():
    """PR ведут PR-Agent и PR-Closer — Issue-Agent их только слушает."""
    assert lc.initiator(lc.IN_DEVELOPMENT, lc.PR_OPEN) == lc.EXTERNAL
    assert lc.initiator(lc.PR_REVIEW, lc.MERGED) == lc.EXTERNAL


# --- боковые состояния возвращаемы ---

@pytest.mark.parametrize("phase", [lc.SPAM, lc.DUPLICATE, lc.ANSWERED,
                                   lc.SKIPPED, lc.ESCALATED, lc.FAILED])
def test_side_states_can_be_returned_to_work(phase):
    """Сегодня вернуть Issue в работу невозможно: воркфлоу уже завершён. Модель
    заранее описывает выход, который починит #36."""
    assert lc.allowed(phase), f"{phase} — тупик, человек не может вернуть Issue"
    assert any(t.initiator == lc.HUMAN for t in lc.allowed(phase))


def test_cancelled_is_terminal_but_spam_is_not():
    """Спам — подозрение агента, отмена — решение человека. Первое обратимо."""
    assert lc.is_terminal(lc.CANCELLED)
    assert not lc.is_terminal(lc.SPAM)


# --- инвариант «фаза ↔ метка» ---

def test_phase_label_uses_the_agreed_namespace():
    """Схема согласована с needs-human:* и run:* — иначе словарь разъедется."""
    assert lc.phase_label(lc.READY_FOR_DEV) == "phase:ready-for-dev"


def test_phase_restored_from_labels():
    labels = ["priority:P1", "phase:groomed", "origin:agent"]
    assert lc.phase_from_labels(labels) == lc.GROOMED


def test_two_phase_labels_are_a_contradiction():
    """Две метки фазы — противоречие, а не история. Угадывать нельзя."""
    assert lc.phase_from_labels(["phase:groomed", "phase:merged"]) is None


def test_no_phase_label_returns_none():
    assert lc.phase_from_labels(["priority:P1"]) is None


def test_unknown_phase_label_is_ignored():
    """Метка `phase:` с чужим значением не должна выдаваться за фазу."""
    assert lc.phase_from_labels(["phase:придумано"]) is None


def test_label_roundtrip_for_every_phase():
    for phase in lc.PHASES:
        assert lc.phase_from_labels([lc.phase_label(phase)]) == phase


# --- мост от текущих стадий ---

def test_every_current_stage_maps_to_a_phase():
    """Пока IssueLifecycle линейный, стадия — единственное, что воркфлоу знает о
    себе. Мост нужен, чтобы #36 не начинала с пустого места."""
    for stage, phase in lc.STAGE_TO_PHASE.items():
        assert phase in lc.TRANSITIONS, f"стадия {stage} ведёт в неизвестную фазу {phase}"


def test_bridge_covers_all_stage_values_used_by_the_workflow():
    """Значения берутся из самого воркфлоу: разъехавшись, мост потеряет стадию."""
    source = (__import__("pathlib").Path(__file__).resolve().parent.parent
              / "worker" / "workflows.py").read_text(encoding="utf-8")
    used = {line.split('self._stage = "')[1].split('"')[0]
            for line in source.splitlines() if 'self._stage = "' in line}
    missing = used - set(lc.STAGE_TO_PHASE)
    assert not missing, f"стадии воркфлоу без фазы: {sorted(missing)}"


# --- запись фазы в GitHub ---

def test_set_phase_removes_the_previous_one():
    """Инвариант «одна фаза — одна метка»: предыдущая снимается, а не остаётся
    рядом. Две метки фазы означали бы противоречие."""
    import activities

    removed: list[str] = []
    added: list[str] = []

    class _GH:
        @staticmethod
        def remove_label(repo, n, label):
            removed.append(label)

        @staticmethod
        def add_label(repo, n, label):
            added.append(label)

    original = activities.github_client
    activities.github_client = _GH
    try:
        activities.set_phase("o/r", 7, lc.GROOMED)
    finally:
        activities.github_client = original

    assert added == [lc.phase_label(lc.GROOMED)]
    assert lc.phase_label(lc.CLASSIFIED) in removed
    assert lc.phase_label(lc.GROOMED) not in removed, "новая метка не должна сниматься"


def test_workflow_phase_query_derives_from_stage():
    """Фаза выводится из стадии, а не хранится вторым источником правды."""
    from workflows import IssueLifecycle

    wf = IssueLifecycle()
    assert wf.phase() == lc.CREATED

    wf._stage = "awaiting-human-decision"
    assert wf.phase() == lc.CLASSIFIED

    wf._stage = "analysis"
    assert wf.phase() == lc.BUSINESS_ANALYSIS
