"""Разбор команд из комментариев Issue и идентификаторы воркфлоу аналитики.

Модуль намеренно не зависит ни от FastAPI, ни от temporalio: webhook — чистый
транспортный слой, а эта логика должна оставаться юнит-тестируемой без
установленного веб-стека (в dev-окружении fastapi отсутствует).
"""

from shared.workflow_types import AnalyzeInput

ANALYZE_COMMAND = "/analyze"


def is_analyze_command(body: str | None) -> bool:
    """True, если комментарий — команда `/analyze`.

    Команда распознаётся только в начале комментария: упоминание `/analyze`
    в середине текста (цитата, обсуждение) не должно запускать тяжёлый прогон.
    """
    if not body:
        return False
    tokens = body.strip().split()
    return bool(tokens) and tokens[0].lower() == ANALYZE_COMMAND


def analysis_workflow_id_for(repo_full_name: str, issue_number: int) -> str:
    """Фиксированный id воркфлоу аналитики — источник идемпотентности.

    Повторный `/analyze` при идущем прогоне упрётся в WorkflowAlreadyStarted
    вместо запуска второго дорогого прогона. Namespace отличается от
    `issue-<repo>-<n>`, чтобы не конфликтовать с воркфлоу триажа.
    """
    return f"analysis-{repo_full_name}-{issue_number}"


def build_analyze_input(payload: dict) -> AnalyzeInput:
    """Собирает вход воркфлоу из payload вебхука issue_comment."""
    issue = payload["issue"]
    return AnalyzeInput(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        comment_id=payload["comment"]["id"],
    )
