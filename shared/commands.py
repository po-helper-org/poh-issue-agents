"""Разбор slash-команд из комментариев Issue и сборка входа аналитики.

Живёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен
воркеру — чтобы исключить сами команды из треда, уходящего в модель. Модуль
намеренно не зависит ни от FastAPI, ни от temporalio: логика юнит-тестируема
без веб-стека (в dev-окружении fastapi отсутствует). Оба Dockerfile копируют
shared/ в образ.
"""

from shared.workflow_types import AnalyzeInput

ESTIMATE = "estimate"
ANALYZE = "analyze"

_COMMANDS = {"/estimate": ESTIMATE, "/analyze": ANALYZE}


def parse_command(comment_body: str) -> str | None:
    """Имя команды, если комментарий — вызов команды, иначе None.

    Командой считается только комментарий, ПЕРВАЯ непустая строка которого
    начинается с самого вызова. Цитата (строка с '>') командой не считается:
    иначе ответ с процитированной командой запускал бы её повторно. Хвост
    после имени команды игнорируется — аргументов в этой версии нет.
    """
    for raw_line in comment_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            return None
        return _COMMANDS.get(line.split()[0].lower())
    return None


def build_analyze_input(payload: dict) -> AnalyzeInput:
    """Собирает вход воркфлоу IssueAnalysis из payload вебхука issue_comment."""
    issue = payload["issue"]
    return AnalyzeInput(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        comment_id=payload["comment"]["id"],
    )
