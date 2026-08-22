"""Разбор slash-команд из комментариев Issue и сборка входа аналитики.

Живёт в shared/, потому что команду распознаёт вебхук, а тот же разбор нужен
воркеру — чтобы исключить сами команды из треда, уходящего в модель. Модуль
намеренно не зависит ни от FastAPI, ни от temporalio: логика юнит-тестируема
без веб-стека (в dev-окружении fastapi отсутствует). Оба Dockerfile копируют
shared/ в образ.

У команды два равноправных триггера — комментарий (`/analyze`) и метка
(`run:analyze`). Оба ведут в один и тот же воркфлоу, поэтому набор команд
объявлен здесь ОДИН раз, а имена меток из него выводятся: разъехавшись, они
дали бы метку, которая ничего не запускает, и запуск, который ничего не
помечает.
"""

from shared import bft
from shared.workflow_types import AnalyzeInput, BftRequest

ESTIMATE = "estimate"
ANALYZE = "analyze"
RESEARCH = "research"
# БФТ двумя командами, а не одной с флагом: цена у них разная на два порядка
# (один вызов модели против пайплайна в клоне репозитория), и человек обязан
# видеть, что именно он запускает, ещё до запуска.
BFT = "bft"
BFT_DEEP = "bft-deep"

_COMMANDS = {"/estimate": ESTIMATE, "/analyze": ANALYZE, "/research": RESEARCH,
             "/bft": BFT, "/bft-deep": BFT_DEEP}

# Схема имён — namespace через двоеточие, как в протоколе агентов v1
# (needs-human:*, origin:agent). `run:*` — идёт прогон, `done:*` — проработано,
# `failed:*` — прогон был и сорвался. Последнее отдельной меткой, а не молча
# снятым `run:*`: иначе неуспех неотличим от «никто не запускал».
RUN_PREFIX = "run:"
DONE_PREFIX = "done:"
FAILED_PREFIX = "failed:"

# Метки прежних версий, означавшие «идёт прогон». Снимаются вместе с `run:*`,
# чтобы на завершённом Issue не осталось противоречия `analyzing` + `done:analyze`.
_LEGACY_RUNNING_LABELS = {ANALYZE: ("analyzing",)}


def run_label(command: str) -> str:
    return f"{RUN_PREFIX}{command}"


def done_label(command: str) -> str:
    return f"{DONE_PREFIX}{command}"


def failed_label(command: str) -> str:
    return f"{FAILED_PREFIX}{command}"


def running_labels(command: str) -> tuple[str, ...]:
    """Все метки «прогон идёт» для команды — их снимает финализация."""
    return (run_label(command),) + _LEGACY_RUNNING_LABELS.get(command, ())


def parse_label_command(label: str) -> str | None:
    """Команда, которую запускает метка, иначе None.

    Запускает ТОЛЬКО `run:<команда>`. Это же и защита от петли: метки исхода
    (`done:*`, `failed:*`) агент ставит себе сам, они прилетают обратно
    событием issues.labeled — и не совпадают ни с одним триггером.
    """
    if not label.startswith(RUN_PREFIX):
        return None
    command = label[len(RUN_PREFIX):].strip().lower()
    return command if command in set(_COMMANDS.values()) else None


def bft_mode(command: str) -> str:
    """Режим прогона БФТ по имени команды.

    Имена команд и имена режимов разведены намеренно: команда — то, что набирает
    человек (`/bft-deep`), режим — то, чем оперирует пайплайн (`deep`). Свести их
    в одну строку значило бы, что переименование команды молча меняет имя
    стадии в Temporal и путь артефактов.
    """
    return bft.DEEP if command == BFT_DEEP else bft.FAST


def parse_command(comment_body: str) -> str | None:
    """Имя команды, если комментарий — вызов команды, иначе None.

    Командой считается только комментарий, ПЕРВАЯ непустая строка которого
    начинается с самого вызова. Цитата (строка с '>') командой не считается:
    иначе ответ с процитированной командой запускал бы её повторно. Хвост
    после имени команды здесь игнорируется — его достаёт `parse_command_args`.
    """
    for raw_line in comment_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            return None
        return _COMMANDS.get(line.split()[0].lower())
    return None


def parse_command_args(comment_body: str) -> str:
    """Всё, что человек написал после имени команды, включая следующие строки.

    У `/analyze` и `/estimate` аргументов нет, у БФТ есть: `/bft` несёт
    замечания к формулировке, `/bft-deep` — ответы на открытые вопросы. Хвост
    забирается целиком и многострочно, потому что ответы на пять вопросов в одну
    строку не пишут.

    Не команда — пустая строка: вызывающий уже знает про это из `parse_command`,
    и второй способ сказать «это не команда» тут ни к чему.
    """
    lines = comment_body.splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">") or _COMMANDS.get(line.split()[0].lower()) is None:
            return ""
        head = line.split(" ", 1)[1] if " " in line else ""
        tail = "\n".join(lines[index + 1:])
        return f"{head}\n{tail}".strip()
    return ""


def build_analyze_input(payload: dict) -> AnalyzeInput:
    """Собирает вход воркфлоу IssueAnalysis из payload вебхука.

    Один сборщик на оба триггера: у события issue_comment есть комментарий, у
    issues.labeled его нет — тогда comment_id остаётся None, и активности,
    которым нужен комментарий (реакция на него), просто его не ставят.
    """
    issue = payload["issue"]
    comment = payload.get("comment") or {}
    return AnalyzeInput(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        comment_id=comment.get("id"),
    )


def build_bft_request(payload: dict, mode: str) -> BftRequest:
    """Вход воркфлоу БФТ из payload вебхука — один сборщик на оба триггера.

    Аргументы есть только у команды в комментарии: запуск меткой ничего, кроме
    самого факта запуска, не несёт, и `instructions` там пуст. Это не потеря —
    метка и означает «пересобери по тому, что уже написано в Issue».
    """
    issue = payload["issue"]
    comment = payload.get("comment") or {}
    body = comment.get("body") or ""
    # `/bft-deep <id>` — продолжение оборванного прогона. Id отделяем от
    # уточнений здесь, чтобы воркфлоу получал их порознь: иначе идентификатор
    # уехал бы в постановку задачи как «ещё одно требование заказчика».
    session_id, instructions = bft.split_session_arg(
        parse_command_args(body) if comment else "")
    return BftRequest(
        repo=payload["repository"]["full_name"],
        issue_number=issue["number"],
        title=issue["title"],
        body=issue.get("body") or "",
        mode=mode,
        instructions=instructions,
        comment_id=comment.get("id"),
        session_id=session_id,
    )
