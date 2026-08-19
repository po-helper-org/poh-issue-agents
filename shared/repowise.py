"""Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.

Прокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по
workspace, требует токен и идентификатор сессии, журналирует каждый обмен и
рендерит из журнала артефакт диалога.

Почему транскрипт забирается у прокси, а не пишется агентом. Guard стадии
(`worker/activities.py`, проверка ожидаемого артефакта в `run_fnr_stage`) умеет
проверить только существование файла и его размер; отличить полный транскрипт
от правдоподобного пересказа ему не с чем. Журнал на стороне прокси делает
полноту свойством построения, а не добросовестности модели.

Модуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и
`shared/agent_events.py`. Он вызывается и из воркера, и из подготовки каталога
разработки; лишний импорт втащил бы клиент GitHub вместе с токеном туда, где
его быть не должно.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from shared import repos

# --- Виды агентов ---
#
# Попадают в идентификатор сессии: аналитика и разработка по одному Issue —
# два разных диалога, и слить их в один журнал значило бы потерять оба.
ANALYSIS = "analysis"
DEVELOP = "openhands"

# --- Workspace ---
#
# Граница вопроса, а не команды: `contour` отвечает «как устроены сами агенты»,
# `product` — «что агенты пишут» (правила R1–R9 спеки FNR-5).
CONTOUR = "contour"
PRODUCT = "product"

DEFAULT_MAX_TURNS = 12
PROBE_TIMEOUT_SEC = 5.0
TRANSCRIPT_TIMEOUT_SEC = 30.0

# Имя сервера в конфигурации MCP. Фиксировано: на него ссылается промпт стадии.
SERVER_NAME = "repowise"


def proxy_base() -> str:
    return os.environ.get("REPOWISE_PROXY_URL", "").rstrip("/")


def agent_token() -> str:
    return os.environ.get("REPOWISE_AGENT_TOKEN", "")


def enabled() -> bool:
    """Интеграция включена только при заданном адресе прокси.

    Пустой адрес — не отказ, а выключенная интеграция: стадия деградирует
    штатно (см. `unavailable_artifact`), конвейер идёт дальше.
    """
    return bool(proxy_base())


def max_turns() -> int:
    """Потолок ходов диалога.

    Мусор в переменной не снимает потолок вовсе: стадия живёт внутри активности
    с потолком времени, и неограниченный цикл вопросов — это и расход средств,
    и зависший прогон.
    """
    raw = os.environ.get("REPOWISE_MAX_TURNS", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_MAX_TURNS


def workspace_for(repo: str) -> str:
    """`contour` для репозиториев из REPOWISE_CONTOUR_REPOS, иначе `product`.

    Guard на пустой список обязателен: `repos.is_allowed` трактует пустоту как
    «разрешено всё», а здесь это означало бы, что каждый репозиторий попал в
    `contour`, — ровно наоборот.
    """
    specs = [s for s in os.environ.get("REPOWISE_CONTOUR_REPOS", "").split(",") if s.strip()]
    if not specs:
        return PRODUCT
    return CONTOUR if repos.is_allowed(repo, specs) else PRODUCT


def session_id(repo: str, issue_number: int, agent: str) -> str:
    """Детерминированный идентификатор сессии.

    Детерминированный по той же причине, что и идентификаторы прогонов
    (`shared/workflow_ids.py`): повторный запуск по тому же Issue должен
    попадать в ту же сессию, а не плодить осиротевшие журналы.

    Слэш в имени репозитория заменяется на `__` — идентификатор уезжает в
    query-параметр, и кодировать его на каждой стороне незачем. Тот же приём
    применяется для каталога прогона (`worker/activities.py`, `_workspace_dir`).
    """
    return f"rw-{agent}-{repo.replace('/', '__')}-{issue_number}"


def mcp_url(workspace: str, session: str) -> str:
    query = urllib.parse.urlencode({"workspace": workspace, "session": session})
    return f"{proxy_base()}/mcp?{query}"


def _headers() -> dict:
    return {"Authorization": f"Bearer {agent_token()}"}


def claude_mcp_config(repo: str, issue_number: int, agent: str) -> dict:
    """Содержимое `.mcp.json` в рабочем каталоге прогона `claude -p`."""
    session = session_id(repo, issue_number, agent)
    return {
        "mcpServers": {
            SERVER_NAME: {
                "type": "http",
                "url": mcp_url(workspace_for(repo), session),
                "headers": _headers(),
            }
        }
    }


def openhands_mcp_config(repo: str, issue_number: int, agent: str) -> dict:
    """Содержимое `~/.openhands/mcp.json` одноразового контейнера разработки.

    Формат снят со спайка FR-16 (`docs/spikes/2026-08-19-openhands-mcp-config.md`):
    ключи `transport`, `headers`, `enabled` — то, что пишет сам
    `openhands mcp add --transport http --header ...`.
    """
    session = session_id(repo, issue_number, agent)
    return {
        "mcpServers": {
            SERVER_NAME: {
                "url": mcp_url(workspace_for(repo), session),
                "transport": "http",
                "headers": _headers(),
                "enabled": True,
            }
        }
    }


def available(timeout: float = PROBE_TIMEOUT_SEC) -> bool:
    """Отвечает ли прокси. Исключений не поднимает — недоступность не отказ.

    Точка `/health` открыта и токена не требует (спайк FR-1,
    `docs/spikes/2026-08-19-repowise-headless.md`): проверка живости не должна
    падать из-за неверного токена, иначе отличить «прокси лежит» от «токен
    протух» станет нельзя.
    """
    if not enabled():
        return False
    try:
        with urllib.request.urlopen(f"{proxy_base()}/health", timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def transcript(session: str) -> str | None:
    """Отрендеренный транскрипт сессии либо None, если получить не удалось.

    None — не ошибка вызывающего: он подставит артефакт с отметкой о том, что
    обращений не было (см. забор транскрипта разработки в `worker/activities.py`).
    """
    if not enabled():
        return None
    request = urllib.request.Request(
        f"{proxy_base()}/sessions/{urllib.parse.quote(session)}/render",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=TRANSCRIPT_TIMEOUT_SEC) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def unavailable_artifact(repo: str, issue_number: int, agent: str, reason: str) -> str:
    """Артефакт диалога для случая, когда источник недоступен.

    Артефакт создаётся ВСЕГДА (модификация M1 вердикта дебатов). Guard стадии
    `task` остаётся на месте и по-прежнему ловит молчаливый пропуск, но жёсткой
    остановки конвейера недоступность Repowise не создаёт.

    Токен сюда не попадает: файл публикуется комментарием и уезжает в ветку.
    """
    return f"""---
issue: {repo}#{issue_number}
session: {session_id(repo, issue_number, agent)}
workspace: {workspace_for(repo)}
agent: {agent}
outcome: source-unavailable
turns: 0
---

# Итог

Диалог с Repowise не состоялся: источник недоступен.

**Причина:** {reason}

Стадия отработала штатно и не остановила конвейер — так предписывает
модификация M1 вердикта дебатов (`sa_documentation/FNR/FNR_5/concept.md`).
Аналитика ниже по конвейеру идёт без дополнительного контекста из индекса.

# Что осталось неспрошенным

Вопросы к индексу по этому Issue не задавались. Диалог возобновляется
повторным запуском стадии после восстановления сервиса.

# Диалог

Ходов нет.
"""
