"""
Идентификаторы Temporal-workflow — в одном месте.

ID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный
`issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делает
идемпотентной повторную доставку вебхука с командой. Формат собирают и вебхук,
и скрипты прямого запуска; разъехавшись, они молча потеряли бы именно эту
идемпотентность — поэтому строка живёт здесь одна.
"""


def issue_workflow_id(repo_full_name: str, issue_number: int, suffix: str = "") -> str:
    # suffix — осознанный перепрогон backfill: другой id, чтобы не упереться в
    # REJECT_DUPLICATE уже обработанного Issue (scripts/backfill.py --suffix).
    base = f"issue-{repo_full_name}-{issue_number}"
    return f"{base}-{suffix}" if suffix else base


def estimate_workflow_id(repo_full_name: str, issue_number: int, comment_id: int) -> str:
    return f"estimate-{repo_full_name}-{issue_number}-{comment_id}"


def analysis_workflow_id(repo_full_name: str, issue_number: int) -> str:
    # Фиксированный id (без comment_id): повторный /analyze при идущем прогоне
    # упирается в WorkflowAlreadyStarted вместо второго дорогого прогона.
    return f"analysis-{repo_full_name}-{issue_number}"
