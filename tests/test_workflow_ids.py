"""Идентификаторы дорогих стадий — ключ к восстановлению истории Issue.

Дерево дочерних прогонов в Temporal UI привязано к RunId родителя, а родитель
делает continue-as-new при 800 событиях истории (`worker/workflows.py:74`).
Поэтому полнота восстановления держится на ИДЕНТИФИКАТОРЕ, а не на дереве —
и формат id проверяется тестом, а не соглашением.
"""

from shared.workflow_ids import (
    analysis_workflow_id,
    development_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
    pr_fix_workflow_id,
)


def test_development_id_is_derived_from_the_issue():
    """Идентификатор выводится из номера Issue и не содержит номера попытки:
    повторный запуск при идущем прогоне обязан упереться в занятый id, а не
    поднять второй контейнер раннера."""
    assert development_workflow_id("o/r", 39) == "develop-o/r-39"


def test_development_id_is_stable_across_calls():
    """Ключ идемпотентности: два вызова дают одну строку, иначе
    WorkflowAlreadyStartedError никогда не сработает."""
    assert development_workflow_id("o/r", 39) == development_workflow_id("o/r", 39)


def test_pr_fix_id_includes_the_round():
    """Круги правок — честно разные прогоны со своей историей: второй круг не
    должен упираться в занятый идентификатор первого."""
    assert pr_fix_workflow_id("o/r", 41, 2) == "prfix-o/r-41-2"


def test_pr_fix_rounds_do_not_collide():
    assert pr_fix_workflow_id("o/r", 41, 1) != pr_fix_workflow_id("o/r", 41, 2)


def test_stage_prefixes_are_distinct():
    """Восстановление истории идёт фильтром по префиксу: `issue-` даёт только
    родителей, `develop-` — только разработки. Совпади префиксы — фильтр
    перестал бы разделять стадии."""
    ids = [
        issue_workflow_id("o/r", 7),
        analysis_workflow_id("o/r", 7),
        estimate_workflow_id("o/r", 7, 555),
        development_workflow_id("o/r", 7),
        pr_fix_workflow_id("o/r", 7, 1),
    ]
    prefixes = [i.split("-", 1)[0] for i in ids]
    assert len(set(prefixes)) == len(prefixes), f"префиксы пересеклись: {prefixes}"
