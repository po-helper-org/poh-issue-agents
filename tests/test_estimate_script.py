import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backfill
import estimate

from shared.workflow_ids import estimate_workflow_id, issue_workflow_id


def test_estimate_id_format_is_pinned():
    """Формат несёт идемпотентность: comment_id в ID — то, что не даёт
    повторной доставке вебхука запустить вторую оценку."""
    assert estimate_workflow_id("o/r", 7, 555) == "estimate-o/r-7-555"


def test_issue_id_format_is_pinned():
    assert issue_workflow_id("o/r", 7) == "issue-o/r-7"


def test_script_and_shared_builder_agree():
    """Смок-скрипт обязан целиться в тот же ID, что соберёт вебхук, — иначе
    он проверял бы не тот путь, что живёт в проде."""
    assert estimate.workflow_id_for("o/r", 7, 555) == estimate_workflow_id("o/r", 7, 555)


def test_backfill_and_shared_builder_agree():
    assert backfill.workflow_id_for("o/r", 7) == issue_workflow_id("o/r", 7)


def test_zero_comment_id_still_produces_a_valid_id():
    assert estimate.workflow_id_for("o/r", 7, 0) == "estimate-o/r-7-0"
