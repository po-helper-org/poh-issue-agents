"""
Идентификаторы Temporal-workflow — в одном месте.

ID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный
`issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делает
идемпотентной повторную доставку вебхука с командой. Формат собирают и вебхук,
и скрипты прямого запуска; разъехавшись, они молча потеряли бы именно эту
идемпотентность — поэтому строка живёт здесь одна.
"""


def issue_workflow_id(repo_full_name: str, issue_number: int) -> str:
    return f"issue-{repo_full_name}-{issue_number}"


def estimate_workflow_id(repo_full_name: str, issue_number: int, comment_id: int) -> str:
    return f"estimate-{repo_full_name}-{issue_number}-{comment_id}"
