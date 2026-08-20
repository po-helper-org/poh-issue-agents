"""Контракт активности Develop — разработка по подготовленному Issue.

Research доводит Issue до системных требований и метки `ready-for-dev` (точка
передачи H1 протокола). Develop берёт его оттуда и доводит до открытого PR.

Код пишет OpenHands. Где именно он это делает — вопрос не удобства, а радиуса
поражения, и отсюда два режима:

`local` (умолчание) — прогон идёт **одноразовым контейнером на своём же
сервере**. Контур получается замкнутым: репозиторий обслуживается целиком
внутри стенда, без чужих раннеров и без минут GitHub.

`dispatch` — прогон уезжает в GitHub Actions (`workflow_dispatch`). Остаётся
для репозиториев, где стенда нет.

Почему отдельный контейнер, а не воркер. Аналитика (`claude -p`) пишет
документы, и её соседство с токенами безобидно. Агент разработки делает другое:
он ИСПОЛНЯЕТ код репозитория — ставит зависимости, гоняет тесты. Внутри воркера
это означало бы выполнение произвольного кода чужого проекта рядом с
GitHub-токеном и ключом модели. Поэтому прогон живёт минуты в отдельном
контейнере, видит только каталог своей задачи и умирает вместе с ней; коммит,
пуш и PR делает воркер уже после — своими руками и своим токеном.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub — как
`shared/lifecycle.py` и `shared/agent_events.py`.
"""

import os
import shlex

# --- Режимы ---

LOCAL = "local"
DISPATCH = "dispatch"

# Файл workflow в репозитории-цели для режима `dispatch`. Диспатчится по имени
# файла, а не по имени workflow: имя внутри файла человек меняет свободно,
# путь — контракт.
DEFAULT_WORKFLOW_FILE = "openhands-resolver.yml"
DEFAULT_REF = "main"

# Метка-индикатор для человека: видно в списке Issue, что задача уехала в
# разработку, не открывая ни Actions, ни Temporal.
IN_DEVELOPMENT_LABEL = "in-development"

AGENT_NAME = "openhands"

# Образ агента разработки и том, который воркер делит с ним. Том именно общий:
# воркер готовит каталог задачи и читает результат, раннер пишет в него. Через
# bind-mount это не сделать — путь внутри воркера не существует на хосте.
DEFAULT_RUNNER_IMAGE = "poh-openhands-runner:local"
DEFAULT_WORKSPACE_VOLUME = "poh-dev-workspace"
DEFAULT_WORKSPACE_MOUNT = "/workspaces"

# Пользователь, от которого работает раннер (см. `openhands/Dockerfile`).
#
# Объявлен здесь, потому что каталог задачи готовит ВОРКЕР — от root, — а писать
# в него будет раннер. Разъехались числа — каталог остаётся недоступным на
# запись, и это самый дорогой из возможных отказов: агент не падает, а молча
# уходит писать в /tmp и докладывает об успехе. На живом прогоне так потерялись
# двадцать минут работы, а PR открылся пустым.
RUNNER_UID = 10001
RUNNER_GID = 10001

# Конфигурация MCP агента разработки. Пути сняты со спайка FR-16
# (`docs/spikes/2026-08-19-openhands-mcp-config.md`): агент читает её из
# `$HOME/.openhands/mcp.json`. Воркер кладёт файл в каталог задачи на общем
# томе и переставляет раннеру HOME туда же — образ при этом не трогается.
MCP_CONFIG_DIR = ".openhands"
MCP_CONFIG_NAME = "mcp.json"

# Потолок прогона. Больше часа — это не «агент думает», это агент застрял, и
# держать задачу в неопределённости дороже, чем оборвать и сказать об этом.
DEFAULT_RUN_TIMEOUT_SEC = 2700

# Находки агента разработки — ФАЙЛОМ в рабочем каталоге, а не через `gh`.
#
# Правило работы «edge-кейс не в эту ветку, а отдельным SubIssue» в режиме
# `dispatch` агент исполнял сам: в Actions есть и `gh`, и GITHUB_TOKEN. У
# одноразового контейнера нет ни того, ни другого — и это не упущение, а весь
# смысл его изоляции: он исполняет чужой код, токена ему не дают. Поэтому агент
# оставляет находки файлом, а Issue по ним заводит воркер своими руками. Файл
# снимается до коммита: он постановка для контура, а не часть правки.
FOLLOWUPS_FILE = ".followups.md"

# Потолок находок за прогон. Тридцать «надо бы потом учесть» — это не бэклог, а
# способ не делать основную работу; и каждый такой Issue контур обработает
# рекурсивно, то есть за них ещё и заплатит.
MAX_FOLLOWUPS = 8


def mode() -> str:
    """`local` по умолчанию: стенд самодостаточен, пока явно не сказано иначе."""
    raw = os.environ.get("DEVELOP_MODE", "").strip().lower()
    return DISPATCH if raw == DISPATCH else LOCAL


def enabled() -> bool:
    """Выключатель контура разработки.

    Пусто — включено: демо-контур замкнут по умолчанию, иначе забытая
    переменная тихо обрывает путь на самом дорогом шаге. Явное `0` оставляет
    Issue в `ready-for-dev`, то есть в очереди к живому разработчику.
    """
    raw = os.environ.get("DEVELOP_ENABLED", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def workflow_file() -> str:
    return os.environ.get("DEVELOP_WORKFLOW_FILE", "").strip() or DEFAULT_WORKFLOW_FILE


def workflow_ref() -> str:
    return os.environ.get("DEVELOP_REF", "").strip() or DEFAULT_REF


def runner_image() -> str:
    return os.environ.get("DEVELOP_RUNNER_IMAGE", "").strip() or DEFAULT_RUNNER_IMAGE


def workspace_volume() -> str:
    return os.environ.get("DEVELOP_WORKSPACE_VOLUME", "").strip() or DEFAULT_WORKSPACE_VOLUME


def workspace_mount() -> str:
    return os.environ.get("DEVELOP_WORKSPACE_MOUNT", "").strip() or DEFAULT_WORKSPACE_MOUNT


def run_timeout() -> int:
    raw = os.environ.get("DEVELOP_TIMEOUT_SEC", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_RUN_TIMEOUT_SEC
    except ValueError:
        return DEFAULT_RUN_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_RUN_TIMEOUT_SEC


def task_slug(repo: str, issue_number: int) -> str:
    """Имя каталога задачи в общем томе. Слэш репозитория заменён: это имя
    каталога, а не путь."""
    return f"dev-{repo.replace('/', '__')}-{issue_number}"


def work_branch(issue_number: int) -> str:
    return f"feature/{issue_number}-openhands"


def runner_command(slug: str, *, image: str, volume: str, mount: str,
                   network: str = "", home: str = "") -> list[str]:
    """Команда запуска одноразового контейнера.

    `--rm` обязателен: контейнер существует ради одного прогона, и оставлять
    его — значит копить мусор с ключом модели в переменных окружения.

    Сеть агенту нужна: он ставит зависимости проекта. Секреты внутрь идут
    ровно два — ключ и адрес модели; GitHub-токена там нет, потому что пушит
    и открывает PR воркер, а не агент.

    `network` — сеть, в которой раннеру виден MCP-прокси Repowise. Пусто —
    раннер работает без индекса; это штатный режим, а не отказ.

    `home` — куда переставить домашний каталог. Нужен ровно затем, чтобы агент
    нашёл конфигурацию MCP: он читает её из `$HOME/.openhands/mcp.json`
    (спайк FR-16), а общий том смонтирован в другом месте. Переставить одну
    переменную дешевле, чем оборачивать ENTRYPOINT образа или монтировать
    отдельный файл, путь которого на хосте воркеру неизвестен.

    Пусто — HOME остаётся тем, что задан образом, и поведение раннера не
    меняется вовсе.
    """
    command = [
        # Имя, а не случайное: воркер запускает контейнер и ждёт, но если воркер
        # умер (выкладка, рестарт, terminate воркфлоу), клиент исчезает, а
        # контейнер остаётся работать — с ключом модели, минутами CPU и памятью.
        # `--rm` тут не спасает: он убирает контейнер только после нормального
        # выхода. По имени прогон находится и снимается перед новой попыткой.
        "docker", "run", "--rm", "--name", slug,
        "-v", f"{volume}:{mount}",
        "-w", f"{mount}/{slug}/repo",
        "-e", "LLM_API_KEY",
        "-e", "LLM_BASE_URL",
        "-e", "LLM_MODEL",
    ]
    if network:
        command += ["--network", network]
    if home:
        command += ["-e", f"HOME={home}"]
    command.append(image)
    return command


def proxy_network() -> str:
    """Сеть docker, в которой раннеру виден MCP-прокси Repowise.

    Пусто — раннер работает без индекса. Это штатный режим: интеграция может
    быть не поднята вовсе, и разработка от этого останавливаться не должна.
    """
    return os.environ.get("REPOWISE_NETWORK", "").strip()


def reap_command(slug: str) -> list[str]:
    """Снять остаток прошлой попытки. Нет такого контейнера — команда просто
    вернёт ненулевой код, и это штатно."""
    return ["docker", "rm", "-f", slug]


def runner_env(api_key: str, base_url: str, model: str) -> dict[str, str]:
    return {"LLM_API_KEY": api_key, "LLM_BASE_URL": base_url, "LLM_MODEL": model}


def dispatch_inputs(issue_number: int, *, branch: str, priority: str = "") -> dict[str, str]:
    """Входы прогона для режима `dispatch`. Только строки: `workflow_dispatch`
    других не принимает."""
    return {
        "issue_number": str(issue_number),
        "research_branch": branch or "",
        "priority": priority or "",
    }


def handoff_comment(issue_number: int, *, repo: str, branch: str, where: str) -> str:
    """Комментарий в Issue о старте разработки."""
    artifacts = (f"- контекст для агента: ветка `{branch}`\n"
                 if branch else
                 "- аналитики по задаче не было — агент работает от тела Issue\n")
    return (
        f"🛠 Передал задачу в разработку — {where}.\n\n"
        f"{artifacts}"
        "- найденные по дороге edge-кейсы агент заводит отдельными SubIssue, "
        "а не чинит в этой же ветке\n\n"
        f"Ветка работы — `{work_branch(issue_number)}`, "
        f"по завершении откроется PR с `Closes #{issue_number}`."
    )


def pr_body(issue_number: int, *, branch: str) -> str:
    return (
        f"Closes #{issue_number}\n\n"
        f"Разработку вёл OpenHands по системным требованиям из `{branch or '—'}`.\n"
        "Найденные по дороге edge-кейсы вынесены отдельными SubIssue и в этой "
        "ветке не чинились.\n\n"
        f"<sub>origin: agent · root-issue: #{issue_number}</sub>\n"
    )


def parse_followups(text: str) -> list[dict]:
    """Находки из файла агента: заголовок `## …` — название, остальное — тело.

    Проза без заголовков находкой не считается. Без заголовка не понять, где
    кончается одна находка и начинается следующая, а Issue с телом вместо
    названия хуже, чем ненайденный edge-кейс: он живёт в бэклоге и его читают.
    """
    items: list[dict] = []
    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        if title:
            items.append({"title": title, "body": "\n".join(body).strip()})

    for raw in (text or "").splitlines():
        if raw.startswith("## "):
            flush()
            if len(items) >= MAX_FOLLOWUPS:
                return items[:MAX_FOLLOWUPS]
            title = raw[3:].strip()
            body = []
            continue
        if title is not None:
            body.append(raw)
    flush()
    return items[:MAX_FOLLOWUPS]


def followup_body(item: dict, *, parent: int) -> str:
    """Тело SubIssue по находке. Ключ цепочки первой строкой — по нему контур
    отличает свой выход от входа и считает глубину (правила R6, R7)."""
    return "\n".join([
        f"root-issue: #{parent}",
        "",
        f"Найдено агентом разработки по задаче #{parent} и намеренно не "
        "исправлено в её ветке: MVP это не блокирует.",
        "",
        item.get("body") or "(без описания)",
    ])


def quote(command: list[str]) -> str:
    """Команда одной строкой — для лога и сообщений об ошибке."""
    return " ".join(shlex.quote(part) for part in command)
