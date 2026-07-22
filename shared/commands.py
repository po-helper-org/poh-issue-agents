"""
Разбор slash-команд из комментариев Issue.

Живёт в shared/, потому что распознаёт команду вебхук, а тот же разбор нужен
воркеру — чтобы исключить сами команды из треда, который уходит в модель.
Оба Dockerfile копируют shared/ в образ.
"""

ESTIMATE = "estimate"

_COMMANDS = {"/estimate": ESTIMATE}


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
