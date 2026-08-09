"""Словарь меток протокола агентов v1 и разбор сквозного ключа цепочки."""

from shared import labels


def test_human_queue_uses_one_prefix_across_the_org():
    """Смысл переименования: одна выборка `label:needs-human:*` показывает всю
    очередь к людям — и триаж Issue, и остановки PR-Closer."""
    assert labels.NEEDS_HUMAN_TRIAGE == "needs-human:triage"
    assert labels.NEEDS_HUMAN_TRIAGE.startswith(labels.NEEDS_HUMAN_PREFIX)


def test_legacy_name_is_kept_for_searching_old_issues():
    assert labels.LEGACY_NEEDS_HUMAN_TRIAGE == "needs-human-triage"
    assert labels.LEGACY_NEEDS_HUMAN_TRIAGE != labels.NEEDS_HUMAN_TRIAGE


def test_protocol_label_names():
    assert labels.AGENTS_OFF == "agents:off"
    assert labels.ORIGIN_AGENT == "origin:agent"


def test_root_issue_parsed_from_body():
    body = "Follow-up по замечаниям ревью.\n\nroot-issue: #42\nPR: #77"
    assert labels.parse_root_issue(body) == 42


def test_root_issue_is_case_insensitive_and_tolerates_spaces():
    assert labels.parse_root_issue("Root-Issue:   #7") == 7


def test_root_issue_absent_is_not_an_error():
    """PR мог не ссылаться на Issue — тогда follow-up вешается на PR, и ключа
    просто нет. Это допустимо протоколом, а не сбой."""
    assert labels.parse_root_issue("обычное описание задачи") is None
    assert labels.parse_root_issue(None) is None
    assert labels.parse_root_issue("") is None


def test_root_issue_ignores_mentions_inside_text():
    """Ключ — отдельная строка, а не любое упоминание: иначе «см. root-issue:
    #5 в комментарии» в середине абзаца увело бы цепочку не туда."""
    assert labels.parse_root_issue("текст root-issue: #5 внутри строки") is None


def test_label_lookup_is_case_insensitive():
    """GitHub хранит регистр, но считает Agents:Off и agents:off одной меткой."""
    assert labels.has(["Agents:Off"], labels.AGENTS_OFF) is True
    assert labels.has(["origin:agent", "priority:P1"], labels.ORIGIN_AGENT) is True
    assert labels.has(["priority:P1"], labels.ORIGIN_AGENT) is False
    assert labels.has([], labels.AGENTS_OFF) is False
