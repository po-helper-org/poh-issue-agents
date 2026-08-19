# Диалоговые сессии с Repowise — план реализации

> **Для агентных исполнителей:** ОБЯЗАТЕЛЬНЫЙ СУБ-СКИЛЛ — `superpowers:executing-plans`, задача за задачей. Шаги помечены чекбоксами `- [ ]`.

**Цель:** аналитика и разработка получают контекст из постоянного индекса кода через MCP-прокси, а весь диалог становится артефактом `repowise-dialog.md`.

**Архитектура:** новый чистый модуль `shared/repowise.py` строит идентификатор сессии, конфигурацию MCP и ходит к прокси по HTTP. Конвейер аналитики получает новую первую стадию `repowise`, чей артефакт становится входным условием стадии `task`. Агент разработки получает конфигурацию MCP монтированием, а транскрипт его сессии забирает воркер. Недоступность прокси деградирует стадию, а не останавливает конвейер.

**Стек:** Python 3.12, Temporal, pytest + monkeypatch, `urllib.request` (сторонних HTTP-клиентов в `shared/` нет).

## Границы плана

Покрывает FR-11 — FR-15, FR-17 — FR-21 из `sa_documentation/FNR/FNR_5/system_requirements.md` — часть работы, живущая в `poh-issue-agents`.

**Не покрывает:** FR-2 — FR-10 (сервис Repowise, репозиторий `poh-infra`, отдельный план). FR-1 и FR-16 выполнены, отчёты в `docs/spikes/`.

**FR-20 (тесты)** отдельной задачей не выделено: каждая задача ниже начинается с падающего теста, и покрытие пунктов FR-20 распределено по задачам 1, 3, 4, 6, 7.

## Глобальные ограничения

Значения скопированы из спеки и результатов спайков. Требования каждой задачи неявно включают этот раздел.

- Модуль `shared/repowise.py` **не импортирует** `temporalio` и клиент GitHub — как `shared/develop.py` и `shared/agent_events.py`. Проверяется тестом.
- Потолок времени стадии — **900 секунд** (`CLAUDE_STAGE_TIMEOUT_SEC`, `worker/activities.py:636`). Стадия обязана в него укладываться.
- Потолок ходов диалога — **12** по умолчанию, задаётся `REPOWISE_MAX_TURNS`.
- Проверка доступности прокси — **не более 5 секунд**, исключений не поднимает.
- Токен `REPOWISE_AGENT_TOKEN` **не попадает** ни в текст постановки, ни в опубликованные артефакты, ни в диагностические сообщения.
- Каталог артефактов аналитики — `sa_documentation/FNR/FNR_1`, значение константы `FNR_DIR` (`worker/activities.py:634`), не вычисляется.
- Одноразовый контейнер разработки **не получает** ключ GitHub и ключ модели (`shared/develop.py`, докстрока модуля). План эту границу не меняет.
- Тесты **не ходят в сеть**. Прокси подменяется через `monkeypatch`.
- Конфигурация MCP агента разработки лежит в `/home/agent/.openhands/mcp.json` (спайк FR-16), пользователь `agent`, uid **10001**.

## Переменные окружения

| Переменная | Значение по умолчанию | Смысл |
|-----------|----------------------|-------|
| `REPOWISE_PROXY_URL` | пусто | Базовый адрес прокси, например `http://repowise-proxy:7400`. Пусто — интеграция выключена целиком |
| `REPOWISE_AGENT_TOKEN` | пусто | Токен предъявителя для прокси |
| `REPOWISE_CONTOUR_REPOS` | пусто | Репозитории workspace `contour`, формат `shared/repos.py` (маски `owner/*`, `*`). Пусто — все репозитории относятся к `product` |
| `REPOWISE_MAX_TURNS` | `12` | Потолок ходов диалога |

## Структура файлов

| Файл | Ответственность |
|------|----------------|
| `shared/repowise.py` (создать) | Контракт обращения к прокси: идентификатор сессии, выбор workspace, конфигурации MCP, проверка доступности, получение транскрипта, рендер артефакта недоступности. Чистый, без Temporal и GitHub |
| `worker/activities.py` (править) | Состав стадий, размещение конфигурации, ветвь деградации, подготовка каталога разработки, забор транскрипта |
| `prompts/system_repowise_dialog.md` (создать) | Правила ведения автономного диалога |
| `tests/test_repowise_client.py` (создать) | Контракт модуля |
| `tests/test_repowise_stage.py` (создать) | Стадия в конвейере и деградация |
| `tests/test_repowise_develop.py` (создать) | Интеграция с агентом разработки |
| `.env.example` (править) | Четыре новые переменные |

---

### Task 1: Контракт клиента прокси (FR-11, FR-14 в части рендера)

**Файлы:**
- Создать: `shared/repowise.py`
- Создать: `tests/test_repowise_client.py`
- Править: `.env.example`

**Интерфейсы:**
- Потребляет: `shared.repos.is_allowed` — сопоставление репозитория со списком масок.
- Производит (на это опираются задачи 3, 4, 6, 7, 8):
  - `ANALYSIS: str = "analysis"`, `DEVELOP: str = "openhands"`
  - `CONTOUR: str = "contour"`, `PRODUCT: str = "product"`
  - `enabled() -> bool`
  - `workspace_for(repo: str) -> str`
  - `session_id(repo: str, issue_number: int, agent: str) -> str`
  - `mcp_url(workspace: str, session: str) -> str`
  - `claude_mcp_config(repo: str, issue_number: int, agent: str) -> dict`
  - `openhands_mcp_config(repo: str, issue_number: int, agent: str) -> dict`
  - `max_turns() -> int`
  - `available(timeout: float = 5.0) -> bool`
  - `transcript(session: str) -> str | None`
  - `unavailable_artifact(repo: str, issue_number: int, agent: str, reason: str) -> str`

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_repowise_client.py`:

```python
"""Контракт клиента MCP-прокси Repowise.

Проверяем ровно те свойства, на которых стоит остальная интеграция:
идентификатор сессии воспроизводим и различает агентов, конфигурация MCP несёт
токен, а сам модуль остаётся чистым — без Temporal и GitHub. Последнее не
придирка к стилю: модуль вызывается и из воркера, и из подготовки каталога
разработки, и лишний импорт втащил бы туда клиент GitHub вместе с токеном.
"""

import json
import pathlib

import pytest

from shared import repowise


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch):
    monkeypatch.setenv("REPOWISE_PROXY_URL", "http://proxy:7400")
    monkeypatch.setenv("REPOWISE_AGENT_TOKEN", "tok-test")
    monkeypatch.setenv("REPOWISE_CONTOUR_REPOS", "po-helper-org/poh-issue-agents")


def test_session_id_is_reproducible():
    a = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    b = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    assert a == b


def test_session_id_distinguishes_agents():
    analysis = repowise.session_id("o/r", 42, repowise.ANALYSIS)
    develop = repowise.session_id("o/r", 42, repowise.DEVELOP)
    assert analysis != develop


def test_session_id_has_no_slash():
    # Идентификатор уезжает в query-параметр прокси; слэш из полного имени
    # репозитория там пришлось бы кодировать на каждой стороне.
    assert "/" not in repowise.session_id("o/r", 42, repowise.ANALYSIS)


def test_workspace_contour_by_mask():
    assert repowise.workspace_for("po-helper-org/poh-issue-agents") == repowise.CONTOUR


def test_workspace_product_is_default():
    assert repowise.workspace_for("po-helper-org/poh-demo-checkout") == repowise.PRODUCT


def test_empty_contour_list_means_everything_is_product(monkeypatch):
    # Пустой список у shared.repos.is_allowed означает «разрешено всё»; для
    # выбора workspace это ровно противоположный смысл, и guard обязателен.
    monkeypatch.setenv("REPOWISE_CONTOUR_REPOS", "")
    assert repowise.workspace_for("po-helper-org/poh-issue-agents") == repowise.PRODUCT


def test_claude_config_carries_token_and_session():
    cfg = repowise.claude_mcp_config("o/r", 42, repowise.ANALYSIS)
    server = cfg["mcpServers"]["repowise"]
    assert server["headers"]["Authorization"] == "Bearer tok-test"
    assert repowise.session_id("o/r", 42, repowise.ANALYSIS) in server["url"]


def test_openhands_config_matches_runner_format():
    # Формат снят со спайка FR-16: docs/spikes/2026-08-19-openhands-mcp-config.md
    cfg = repowise.openhands_mcp_config("o/r", 42, repowise.DEVELOP)
    server = cfg["mcpServers"]["repowise"]
    assert server["transport"] == "http"
    assert server["enabled"] is True
    assert server["headers"]["Authorization"] == "Bearer tok-test"


def test_disabled_without_proxy_url(monkeypatch):
    monkeypatch.delenv("REPOWISE_PROXY_URL")
    assert repowise.enabled() is False


def test_available_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("сеть недоступна")
    monkeypatch.setattr(repowise.urllib.request, "urlopen", boom)
    assert repowise.available() is False


def test_transcript_returns_none_on_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("сеть недоступна")
    monkeypatch.setattr(repowise.urllib.request, "urlopen", boom)
    assert repowise.transcript("rw-analysis-o__r-42") is None


def test_unavailable_artifact_is_not_empty_and_names_reason():
    text = repowise.unavailable_artifact("o/r", 42, repowise.ANALYSIS, "нет соединения")
    assert "нет соединения" in text
    assert "o/r#42" in text
    assert len(text) > 200


def test_module_stays_pure():
    source = pathlib.Path(repowise.__file__).read_text(encoding="utf-8")
    assert "temporalio" not in source
    assert "github_client" not in source


def test_token_absent_from_artifact():
    text = repowise.unavailable_artifact("o/r", 42, repowise.ANALYSIS, "нет соединения")
    assert "tok-test" not in text
```

- [ ] **Шаг 2: Прогнать тест и убедиться, что он падает**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_client.py -q --no-cov
```
Ожидается: `ModuleNotFoundError: No module named 'shared.repowise'`.

- [ ] **Шаг 3: Написать модуль**

Создать `shared/repowise.py`:

```python
"""Клиент MCP-прокси Repowise — обращение агентов к постоянному индексу кода.

Прокси стоит между агентами и MCP-эндпоинтами Repowise: маршрутизирует по
workspace, требует токен и идентификатор сессии, журналирует каждый обмен и
рендерит из журнала артефакт диалога.

Почему транскрипт забирается у прокси, а не пишется агентом. Guard стадии
(`worker/activities.py:994-1002`) умеет проверить только существование файла и
его размер; отличить полный транскрипт от правдоподобного пересказа ему не с
чем. Журнал на стороне прокси делает полноту свойством построения, а не
добросовестности модели.

Модуль намеренно чистый: ни Temporal, ни GitHub — как `shared/develop.py` и
`shared/agent_events.py`. Он вызывается и из воркера, и из подготовки каталога
разработки; лишний импорт втащил бы клиент GitHub вместе с токеном туда, где
его быть не должно.
"""

from __future__ import annotations

import json
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
CONTOUR = "contour"
PRODUCT = "product"

DEFAULT_MAX_TURNS = 12
PROBE_TIMEOUT_SEC = 5.0

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
    применяется для каталога прогона (`worker/activities.py:_workspace_dir`).
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

    Точка `/health` открыта и токена не требует (спайк FR-1): проверка живости
    не должна падать из-за неверного токена, иначе отличить «прокси лежит» от
    «токен протух» станет нельзя.
    """
    if not enabled():
        return False
    try:
        with urllib.request.urlopen(f"{proxy_base()}/health", timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def transcript(session: str) -> str | None:
    """Отрендеренный транскрипт сессии либо None, если получить не удалось."""
    if not enabled():
        return None
    request = urllib.request.Request(
        f"{proxy_base()}/sessions/{urllib.parse.quote(session)}/render",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def unavailable_artifact(repo: str, issue_number: int, agent: str, reason: str) -> str:
    """Артефакт диалога для случая, когда источник недоступен (FR-14).

    Артефакт создаётся ВСЕГДА. Guard стадии `task` остаётся на месте и
    по-прежнему ловит молчаливый пропуск, но жёсткой остановки конвейера
    недоступность Repowise не создаёт.

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
```

- [ ] **Шаг 4: Прогнать тест и убедиться, что он проходит**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_client.py -q --no-cov
```
Ожидается: `15 passed`.

- [ ] **Шаг 5: Дописать переменные в `.env.example`**

Добавить в конец файла:

```bash
# --- Repowise: постоянный индекс кода (FNR-5) ---
# Базовый адрес MCP-прокси. Пусто — интеграция выключена целиком, стадия
# repowise деградирует штатно и конвейер идёт дальше.
REPOWISE_PROXY_URL=
# Токен предъявителя для прокси. В артефакты и в постановку не попадает.
REPOWISE_AGENT_TOKEN=
# Репозитории workspace `contour` (как устроены сами агенты). Формат тот же,
# что у ISSUE_AGENT_REPOS: owner/repo, owner/*, *. Пусто — всё в `product`.
REPOWISE_CONTOUR_REPOS=
# Потолок ходов диалога. Стадия живёт внутри активности с потолком 900 с.
REPOWISE_MAX_TURNS=12
```

- [ ] **Шаг 6: Коммит**

```bash
git add shared/repowise.py tests/test_repowise_client.py .env.example
git commit -m "feat(repowise): контракт клиента MCP-прокси"
```

---

### Task 2: Правила автономного диалога (FR-13)

**Файлы:**
- Создать: `prompts/system_repowise_dialog.md`

**Интерфейсы:**
- Потребляет: `repowise.SERVER_NAME`, `repowise.max_turns()` — имя сервера MCP и потолок ходов упоминаются в тексте правил.
- Производит: файл промпта, который задача 3 загружает через существующий `_load_prompt`.

- [ ] **Шаг 1: Написать промпт**

Создать `prompts/system_repowise_dialog.md`:

```markdown
# Сбор контекста из Repowise

Ты ведёшь автономный диалог с Repowise — постоянным индексом кода
организации, подключённым как MCP-сервер `repowise`. Цель — собрать
известный контекст по задаче до того, как её начнут ставить.

## Порядок

1. Первый ход — `get_overview` целевого репозитория. Дешёвый вызов, задаёт
   рамку и экономит серию точечных вопросов вслепую.
2. Выведи из тела Issue от 3 до 7 исходных вопросов. Задавай **по одному**:
   каждый следующий вопрос опирается на полученный ответ, а не на список.
3. Ответ «сведений нет» либо встречный вопрос — переформулируй **один** раз.
   Не помогло — отступи и зафиксируй вопрос как открытый.
4. Вопрос к репозиторию, отличному от целевого, задавай отдельным ходом и с
   явным указанием его alias.

## Остановка

- Потолок ходов задан и превышать его нельзя.
- Останавливайся раньше, если два хода подряд не дали нового факта.

## Что записать в конце

Транскрипт диалога ведёт прокси — переписывать ходы не нужно и не следует.
Твой вывод: короткий итог и перечень открытых вопросов.

## Запрещено

- Задавать вопросы, ответ на которые уже есть в теле Issue.
- Продолжать диалог после двух пустых ходов подряд.
- Выдумывать ответ, которого Repowise не дал.
```

- [ ] **Шаг 2: Проверить, что промпт читается существующим загрузчиком**

`PROMPTS_DIR` — константа `Path("/app/prompts")` (`worker/activities.py:54`) без переопределения из окружения: локально её подменяют, как это делают тесты.

Команда:
```bash
.venv/bin/python -c "import sys, pathlib; sys.path.insert(0,'worker'); import activities; activities.PROMPTS_DIR = pathlib.Path('prompts'); print(len(activities._load_prompt('system_repowise_dialog.md')))"
```
Ожидается: число больше 500.

- [ ] **Шаг 3: Коммит**

```bash
git add prompts/system_repowise_dialog.md
git commit -m "feat(repowise): правила автономного диалога стадии"
```

---

### Task 3: Стадия `repowise` в конвейере аналитики (FR-12)

**Файлы:**
- Править: `worker/activities.py:634-676` (константы и состав стадий)
- Править: `worker/activities.py:977-1002` (размещение конфигурации)
- Править: `worker/activities.py:1634-1640` (`ARTIFACT_PATHS`)
- Создать: `tests/test_repowise_stage.py`

**Интерфейсы:**
- Потребляет: `repowise.claude_mcp_config`, `repowise.ANALYSIS` (задача 1); `prompts/system_repowise_dialog.md` (задача 2).
- Производит: имя стадии `"repowise"` в `FNR_STAGE_NAMES` и артефакт `sa_documentation/FNR/FNR_1/repowise-dialog.md`, на которые опираются задачи 4 и 6.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_repowise_stage.py`:

```python
"""Стадия repowise в конвейере аналитики.

Состав стадий задан в четырёх местах сразу — набор артефактов, цепочка,
перечень имён и входные условия. Рассогласование этих мест проявляется не
ошибкой при запуске, а отказом живого прогона, поэтому тест состава дешевле
любого другого способа его поймать.
"""

import activities


def test_repowise_is_first_stage():
    assert activities.FNR_STAGE_NAMES[0] == "repowise"


def test_task_stage_requires_dialog_artifact():
    assert activities._FNR_STAGE_REQUIRES["task"] == \
        f"{activities.FNR_DIR}/repowise-dialog.md"


def test_repowise_stage_has_no_input_requirement():
    # Первая стадия конвейера: требовать от неё чего-либо на входе не с чего.
    assert activities._FNR_STAGE_REQUIRES["repowise"] is None


def test_dialog_artifact_is_collected():
    assert "repowise-dialog.md" in activities.ARTIFACT_FILES


def test_dialog_artifact_is_visible_to_estimation():
    assert any("repowise-dialog" in p for p in activities.ARTIFACT_PATHS)


def test_every_stage_name_resolves():
    # _fnr_stage поднимает ValueError на неизвестном имени; перечень и цепочка
    # обязаны совпадать поимённо.
    for name in activities.FNR_STAGE_NAMES:
        prompt, expected, requires = activities._fnr_stage(name, "описание")
        assert prompt
```

- [ ] **Шаг 2: Прогнать тест и убедиться, что он падает**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_stage.py -q --no-cov
```
Ожидается: `AssertionError` на `test_repowise_is_first_stage` — первой стадией остаётся `task`.

- [ ] **Шаг 3: Добавить стадию в состав**

В `worker/activities.py` заменить строку 635:

```python
ARTIFACT_FILES = ("task.md", "concept.md", "system_requirements.md", "validation.md")
```

на:

```python
ARTIFACT_FILES = ("repowise-dialog.md", "task.md", "concept.md",
                  "system_requirements.md", "validation.md")
```

В `_fnr_stages` (строка 648) первым элементом возвращаемого списка добавить:

```python
        ("repowise", f"/repowise-context {description}",
         f"{FNR_DIR}/repowise-dialog.md"),
```

Заменить строку 664:

```python
FNR_STAGE_NAMES = ("task", "concept", "debate", "sysreq", "validate")
```

на:

```python
FNR_STAGE_NAMES = ("repowise", "task", "concept", "debate", "sysreq", "validate")
```

В словаре `_FNR_STAGE_REQUIRES` (строка 668) добавить первым ключом и изменить `task`:

```python
    "repowise": None,
    "task": f"{FNR_DIR}/repowise-dialog.md",
```

В кортеже `ARTIFACT_PATHS` (строка 1634) добавить строкой:

```python
    "docs/research/issue-{n}-repowise-dialog.md",
```

- [ ] **Шаг 4: Разместить конфигурацию MCP перед запуском стадии**

В `run_fnr_stage` (`worker/activities.py:977`) после строки

```python
    clone_dir = _require_workspace(analyze, requires)
```

вставить:

```python
    # Конфигурация MCP кладётся в каталог прогона, а не в образ: адрес прокси и
    # идентификатор сессии зависят от Issue, и вшить их в образ нельзя. Файл
    # пишется на каждой стадии, потому что каталог прогона переживает activity,
    # а вот пересоздание каталога стадией 0 — нет.
    if repowise.enabled():
        (Path(clone_dir) / ".mcp.json").write_text(
            json.dumps(repowise.claude_mcp_config(
                analyze.repo, analyze.issue_number, repowise.ANALYSIS),
                ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

Добавить импорт в шапку модуля рядом с прочими импортами `shared`:

```python
from shared import repowise
```

- [ ] **Шаг 5: Прогнать тест и убедиться, что он проходит**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_stage.py -q --no-cov
```
Ожидается: `6 passed`.

- [ ] **Шаг 6: Прогнать весь набор — состав стадий зашит и в других тестах**

Команда:
```bash
.venv/bin/python -m pytest -q
```
Ожидается: все тесты проходят. Падения в `tests/test_analysis_pipeline.py` и `tests/test_workflow_analysis.py` означают, что там зафиксирован прежний состав стадий, — обновить ожидаемые значения, не трогая логику.

- [ ] **Шаг 7: Коммит**

```bash
git add worker/activities.py tests/test_repowise_stage.py
git commit -m "feat(repowise): стадия сбора контекста первой в конвейере аналитики"
```

---

### Task 4: Деградация при недоступности источника (FR-14)

**Файлы:**
- Править: `worker/activities.py:977-1002` (ветвь деградации в `run_fnr_stage`)
- Править: `tests/test_repowise_stage.py`

**Интерфейсы:**
- Потребляет: `repowise.available`, `repowise.unavailable_artifact` (задача 1); стадию `repowise` (задача 3).
- Производит: ключ `"outcome"` в отчёте стадии со значениями `"ok"` и `"degraded"` — на него опирается задача 9 (наблюдаемость) и требование FR-9 в плане `poh-infra`.

- [ ] **Шаг 1: Дописать падающие тесты**

Добавить в `tests/test_repowise_stage.py`:

```python
import asyncio

import pytest

from shared import repowise as repowise_module
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=42, title="Заголовок",
                        body="тело", comment_id=1)


def test_degrades_when_proxy_unavailable(monkeypatch, tmp_path):
    """Прокси лежит — стадия отрабатывает, артефакт есть, конвейер идёт дальше.

    Модификация M1 вердикта дебатов. Без неё прокси становится обязательной
    зависимостью на пути, который сегодня остановить нечему.
    """
    clone = tmp_path / "repo"
    (clone / activities.FNR_DIR).mkdir(parents=True)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.setattr(repowise_module, "enabled", lambda: True)
    monkeypatch.setattr(repowise_module, "available", lambda timeout=5.0: False)

    ran = []
    monkeypatch.setattr(activities, "_run_claude",
                        lambda prompt, cwd: ran.append(prompt))

    report = asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))

    assert ran == []                      # процесс диалога не запускался
    assert report["outcome"] == "degraded"
    artifact = clone / activities.FNR_DIR / "repowise-dialog.md"
    assert artifact.exists()
    assert "source-unavailable" in artifact.read_text(encoding="utf-8")


def test_ok_outcome_when_proxy_available(monkeypatch, tmp_path):
    clone = tmp_path / "repo"
    (clone / activities.FNR_DIR).mkdir(parents=True)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.setattr(repowise_module, "enabled", lambda: True)
    monkeypatch.setattr(repowise_module, "available", lambda timeout=5.0: True)

    def fake_claude(prompt, cwd):
        (clone / activities.FNR_DIR / "repowise-dialog.md").write_text(
            "# Диалог\n\nход 1\n", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)

    report = asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))
    assert report["outcome"] == "ok"


def test_other_stages_report_ok(monkeypatch, tmp_path):
    # Ключ outcome должен быть у КАЖДОЙ стадии, иначе потребителю отчёта
    # пришлось бы знать, у каких стадий он есть, а у каких нет.
    clone = tmp_path / "repo"
    (clone / activities.FNR_DIR).mkdir(parents=True)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))

    def fake_claude(prompt, cwd):
        (clone / activities.FNR_DIR / "task.md").write_text("x", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    report = asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    assert report["outcome"] == "ok"
```

- [ ] **Шаг 2: Прогнать тесты и убедиться, что они падают**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_stage.py -q --no-cov
```
Ожидается: `KeyError: 'outcome'`.

- [ ] **Шаг 3: Реализовать ветвь деградации**

В `run_fnr_stage` (`worker/activities.py:977`) после размещения конфигурации из задачи 3 вставить:

```python
    # Деградация вместо остановки (M1). Артефакт создаётся ВСЕГДА: guard стадии
    # `task` остаётся на месте и по-прежнему ловит молчаливый пропуск, но
    # недоступность Repowise конвейер не роняет.
    if stage_name == "repowise" and not (
            repowise.enabled() and await asyncio.to_thread(repowise.available)):
        reason = ("REPOWISE_PROXY_URL не задан" if not repowise.enabled()
                  else "прокси не отвечает на проверку живости")
        path = Path(clone_dir) / expected
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            repowise.unavailable_artifact(
                analyze.repo, analyze.issue_number, repowise.ANALYSIS, reason),
            encoding="utf-8",
        )
        _log.warning("стадия repowise деградировала: %s", reason)
        return {"stage": stage_name, "artifact": expected,
                "bytes": path.stat().st_size, "outcome": "degraded"}
```

В конце той же функции добавить ключ `outcome` в возвращаемый отчёт: найти строку возврата и заменить

```python
    return {"stage": stage_name, "artifact": artifact, "bytes": size}
```

на

```python
    return {"stage": stage_name, "artifact": artifact, "bytes": size,
            "outcome": "ok"}
```

- [ ] **Шаг 4: Прогнать тесты и убедиться, что они проходят**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_stage.py -q --no-cov
```
Ожидается: `9 passed`.

- [ ] **Шаг 5: Коммит**

```bash
git add worker/activities.py tests/test_repowise_stage.py
git commit -m "feat(repowise): недоступность источника деградирует стадию, а не конвейер"
```

---

### Task 5: Публикация артефакта диалога (FR-15)

**Файлы:**
- Править: `shared/agent_comment.py`
- Править: `tests/test_agent_comment.py`

**Интерфейсы:**
- Потребляет: артефакт `repowise-dialog.md` из `ARTIFACT_FILES` (задача 3).
- Производит: артефакт в комментарии и в ветке; далее ничего не потребляет.

- [ ] **Шаг 1: Прочитать текущий сборщик комментария**

Команда:
```bash
grep -n "ARTIFACT_FILES\|def " shared/agent_comment.py
```
Цель шага — найти функцию, собирающую сводку по артефактам, чтобы дописать в неё диалог, а не завести второй путь публикации.

- [ ] **Шаг 2: Написать падающий тест**

Добавить в `tests/test_agent_comment.py`:

```python
def test_dialog_artifact_appears_in_summary():
    """Диалог публикуется вместе со сводкой, а не отдельным сообщением.

    Отдельное сообщение означало бы второй путь публикации: он разъедется с
    первым ровно тогда, когда его перестанут трогать.
    """
    body = agent_comment.analysis_summary(
        repo="o/r", issue_number=42, branch="research/issue-42",
        artifacts={"sa_documentation/FNR/FNR_1/repowise-dialog.md": "# Диалог\n"},
    )
    assert "repowise-dialog.md" in body
```

- [ ] **Шаг 3: Прогнать тест и убедиться, что он падает**

Команда:
```bash
.venv/bin/python -m pytest tests/test_agent_comment.py -q --no-cov
```
Ожидается: падение — либо `AttributeError`, если имя функции иное, либо `AssertionError`. Имя функции взять из результата шага 1 и поправить тест под него.

- [ ] **Шаг 4: Дописать артефакт в сводку**

Добавить `repowise-dialog.md` в перечень артефактов, попадающих в комментарий, тем же способом, каким туда попадают `task.md` и остальные. Артефакт объёмом более лимита комментария публиковать ссылкой на файл в ветке, а не обрезать.

- [ ] **Шаг 5: Прогнать тест и убедиться, что он проходит**

Команда:
```bash
.venv/bin/python -m pytest tests/test_agent_comment.py -q --no-cov
```
Ожидается: все тесты файла проходят.

- [ ] **Шаг 6: Коммит**

```bash
git add shared/agent_comment.py tests/test_agent_comment.py
git commit -m "feat(repowise): артефакт диалога публикуется вместе со сводкой аналитики"
```

---

### Task 6: Доступ агента разработки к прокси (FR-17)

**Файлы:**
- Править: `shared/develop.py`
- Править: `worker/activities.py:1056-1090` (`_dev_prepare`)
- Создать: `tests/test_repowise_develop.py`

**Интерфейсы:**
- Потребляет: `repowise.openhands_mcp_config`, `repowise.DEVELOP`, `repowise.enabled` (задача 1).
- Производит: `develop.MCP_CONFIG_NAME = "mcp.json"` и `develop.RUNNER_MCP_MOUNT = "/home/agent/.openhands/mcp.json"` — на них опирается задача 7.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_repowise_develop.py`:

```python
"""Доступ одноразового контейнера разработки к индексу.

Проверяем ровно ту границу, которую нельзя ослабить: контейнер получает адрес
прокси и токен на чтение индекса — и ничего сверх того. Токен при этом не
должен попасть в постановку: она собирается дословно и публикуется артефактом.
"""

import json

import pytest

from shared import develop, repowise


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch):
    monkeypatch.setenv("REPOWISE_PROXY_URL", "http://proxy:7400")
    monkeypatch.setenv("REPOWISE_AGENT_TOKEN", "tok-secret")


def test_runner_joins_proxy_network(monkeypatch):
    monkeypatch.setenv("REPOWISE_NETWORK", "poh-harness-net")
    command = develop.run_command(slug="o__r-42", workdir="/workspaces/o__r-42")
    assert "--network" in command
    assert "poh-harness-net" in command


def test_no_network_flag_without_setting(monkeypatch):
    monkeypatch.delenv("REPOWISE_NETWORK", raising=False)
    command = develop.run_command(slug="o__r-42", workdir="/workspaces/o__r-42")
    assert "--network" not in command


def test_config_mounted_into_runner_home():
    assert develop.RUNNER_MCP_MOUNT == "/home/agent/.openhands/mcp.json"


def test_token_absent_from_task_statement(tmp_path, monkeypatch):
    # Постановка собирается воркером и публикуется дословно
    # (worker/activities.py:1056-1064) — токену там не место.
    config = repowise.openhands_mcp_config("o/r", 42, repowise.DEVELOP)
    statement = "# Задача: реализовать Issue #42\n\nтело\n"
    assert "tok-secret" in json.dumps(config)   # в конфигурации токен есть
    assert "tok-secret" not in statement        # в постановке — нет
```

- [ ] **Шаг 2: Прогнать тест и убедиться, что он падает**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_develop.py -q --no-cov
```
Ожидается: `AttributeError: module 'shared.develop' has no attribute 'RUNNER_MCP_MOUNT'`.

- [ ] **Шаг 3: Добавить константы и сеть в контракт запуска**

В `shared/develop.py` рядом с прочими константами раннера добавить:

```python
# Конфигурация MCP уезжает в ДОМАШНИЙ каталог раннера, а не в каталог задачи:
# так её ищет сам агент (спайк FR-16, docs/spikes/2026-08-19-openhands-mcp-config.md),
# а общий том туда не достаёт. Отсюда монтирование отдельным файлом.
MCP_CONFIG_NAME = "mcp.json"
RUNNER_MCP_MOUNT = "/home/agent/.openhands/mcp.json"

# Сеть, в которой раннеру виден прокси. Пусто — раннер работает без индекса:
# это штатный режим, а не отказ.
def proxy_network() -> str:
    return os.environ.get("REPOWISE_NETWORK", "").strip()
```

В функции, собирающей команду `docker run`, добавить перед именем образа:

```python
    network = proxy_network()
    if network:
        command += ["--network", network]
        command += ["-v", f"{host_config_path}:{RUNNER_MCP_MOUNT}:ro"]
```

- [ ] **Шаг 4: Писать конфигурацию в каталоге задачи**

В `_dev_prepare` (`worker/activities.py:1056`) после создания каталога задачи добавить:

```python
    # Файл лежит в каталоге задачи, а монтируется в домашний каталог раннера:
    # каталог задачи — общий том, доступный обоим контейнерам.
    if repowise.enabled():
        (root / develop.MCP_CONFIG_NAME).write_text(
            json.dumps(repowise.openhands_mcp_config(
                issue.repo, issue.issue_number, repowise.DEVELOP),
                ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Шаг 5: Прогнать тест и убедиться, что он проходит**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_develop.py -q --no-cov
```
Ожидается: `4 passed`. Имена аргументов `develop.run_command` привести к тем, что реально объявлены в модуле, — тест править под код, а не наоборот.

- [ ] **Шаг 6: Коммит**

```bash
git add shared/develop.py worker/activities.py tests/test_repowise_develop.py
git commit -m "feat(repowise): агент разработки получает индекс через прокси"
```

---

### Task 7: Забор артефакта воркером (FR-18)

**Файлы:**
- Править: `worker/activities.py` (завершение прогона разработки)
- Править: `tests/test_repowise_develop.py`

**Интерфейсы:**
- Потребляет: `repowise.transcript`, `repowise.session_id`, `repowise.DEVELOP` (задача 1); публикацию из задачи 5.
- Производит: артефакт `docs/research/issue-{n}-repowise-dialog.md`.

- [ ] **Шаг 1: Дописать падающие тесты**

Добавить в `tests/test_repowise_develop.py`:

```python
def test_transcript_fetched_after_failed_run(monkeypatch):
    """Раннер упал — артефакт всё равно опубликован.

    Забор возложен на воркер именно поэтому: файл, записанный раннером, при
    аварийном завершении был бы потерян — а диалог полезен ровно тогда, когда
    разбирают неудачный прогон.
    """
    fetched = []
    monkeypatch.setattr(repowise, "transcript",
                        lambda session: fetched.append(session) or "# Диалог\n")
    activities._collect_dev_dialog("o/r", 42, run_failed=True)
    assert fetched == [repowise.session_id("o/r", 42, repowise.DEVELOP)]


def test_empty_session_yields_marked_artifact(monkeypatch):
    monkeypatch.setattr(repowise, "transcript", lambda session: None)
    text = activities._collect_dev_dialog("o/r", 42, run_failed=False)
    assert "обращений к индексу не было" in text
```

- [ ] **Шаг 2: Прогнать тесты и убедиться, что они падают**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_develop.py -q --no-cov
```
Ожидается: `AttributeError: module 'activities' has no attribute '_collect_dev_dialog'`.

- [ ] **Шаг 3: Реализовать забор**

В `worker/activities.py` рядом с прочими помощниками разработки добавить:

```python
def _collect_dev_dialog(repo: str, issue_number: int, run_failed: bool) -> str:
    """Транскрипт сессии разработки. Забирает ВОРКЕР, а не раннер.

    Раннер к этому моменту уже мёртв — в этом и смысл: артефакт переживает
    прогон, включая аварийный.
    """
    session = repowise.session_id(repo, issue_number, repowise.DEVELOP)
    text = repowise.transcript(session)
    if text:
        return text
    return (f"---\nissue: {repo}#{issue_number}\nsession: {session}\n"
            f"agent: {repowise.DEVELOP}\nturns: 0\n---\n\n"
            f"# Итог\n\nЗа время прогона обращений к индексу не было"
            f"{' (прогон завершился аварийно)' if run_failed else ''}.\n")
```

Вызвать эту функцию в месте завершения прогона разработки — после того, как исход прогона определён, и **независимо** от исхода, — и передать результат в публикацию из задачи 5.

- [ ] **Шаг 4: Прогнать тесты и убедиться, что они проходят**

Команда:
```bash
.venv/bin/python -m pytest tests/test_repowise_develop.py -q --no-cov
```
Ожидается: `6 passed`.

- [ ] **Шаг 5: Коммит**

```bash
git add worker/activities.py tests/test_repowise_develop.py
git commit -m "feat(repowise): транскрипт разработки забирает воркер, а не раннер"
```

---

### Task 8: Правила обращения к индексу в постановке разработки (FR-19)

**Файлы:**
- Править: `worker/activities.py:1083` (файл правил задачи)

**Интерфейсы:**
- Потребляет: `repowise.enabled`, `repowise.SERVER_NAME` (задача 1).
- Производит: ничего.

- [ ] **Шаг 1: Дописать правила**

В `_dev_prepare`, там где формируется содержимое `.openhands/task-rules.md` (`worker/activities.py:1083`), добавить блок при включённой интеграции:

```python
    if repowise.enabled():
        rules_text += (
            "\n## Индекс кода (MCP-сервер `repowise`)\n\n"
            "Обратись к индексу ДО начала работы: спроси про компоненты, "
            "которые собираешься менять, и про их связи. Это дешевле, чем "
            "читать репозиторий целиком.\n\n"
            "Обратись к нему СНОВА при затруднении — вместо того чтобы "
            "продолжать вслепую.\n\n"
            "Индекс недоступен — работай без него, это штатный режим, "
            "а не повод останавливаться.\n"
        )
```

- [ ] **Шаг 2: Проверить, что правила доезжают**

Команда:
```bash
.venv/bin/python -m pytest tests/test_develop.py -q --no-cov
```
Ожидается: все тесты файла проходят.

- [ ] **Шаг 3: Коммит**

```bash
git add worker/activities.py
git commit -m "feat(repowise): постановка разработки предписывает обращение к индексу"
```

---

### Task 9: Приведение проектной документации в соответствие коду (FR-21)

**Файлы:**
- Править: `specs/implementation-spec.md:184,188`
- Править: `docs/ROADMAP.md:139,157,200`
- Править: `docs/ARCHITECTURE.md:84,140`
- Править: `docs/diagrams/issue-workflow-part1-intake.mermaid:45`
- Править: `docs/diagrams/issue-workflow-part2-pipelines.mermaid:19-20`
- Править: `sa_documentation/naming_conventions.md`

**Интерфейсы:** ничего не потребляет и не производит — завершающая задача.

- [ ] **Шаг 1: Закрыть задачи плана работ**

В `specs/implementation-spec.md` пометить `T5.2` выполненной с переформулировкой: блокирующее условие было поставлено к системе управления знаниями, тогда как Repowise в организации работает по кодовой базе. Пометить `T5.6` выполненной.

- [ ] **Шаг 2: Обновить дорожную карту**

В `docs/ROADMAP.md` снять пометку «Требует решения» со строки 139, привести строки 157 и 200 в соответствие принятому решению.

- [ ] **Шаг 3: Отразить стадию в архитектуре**

В `docs/ARCHITECTURE.md` описать стадию `repowise` первой в конвейере аналитики и заменить формулировку строки 140 на фактическую.

- [ ] **Шаг 4: Поправить диаграммы**

В `issue-workflow-part1-intake.mermaid:45` кандидаты проверки дублей теперь имеют потребителя — отразить. В `issue-workflow-part2-pipelines.mermaid:19-20` показать стадию первой.

- [ ] **Шаг 5: Исправить словарь терминов**

В `sa_documentation/naming_conventions.md` заменить запись про `run_research_pipeline` (`worker/activities.py:265`) — такой функции в коде нет. Конвейер реализован как `prepare_workspace` (`worker/activities.py:970`) и постадийная `run_fnr_stage` (`worker/activities.py:977`). Добавить термины: индекс кода, workspace, alias, MCP-прокси, сессия диалога, артефакт диалога, деградация стадии.

- [ ] **Шаг 6: Проверить, что тест синхронизации документации проходит**

Команда:
```bash
.venv/bin/python -m pytest -q
```
Ожидается: все тесты проходят, включая покрытие не ниже 83%.

- [ ] **Шаг 7: Коммит**

```bash
git add specs docs sa_documentation
git commit -m "docs(repowise): документация догнала код, T5.2 и T5.6 закрыты"
```

---

## Самопроверка плана

**Покрытие спеки.**

| Требование | Задача |
|-----------|--------|
| FR-11 клиент прокси | 1 |
| FR-12 стадия в конвейере | 3 |
| FR-13 правила диалога | 2 |
| FR-14 деградация | 1 (рендер) + 4 (ветвь) |
| FR-15 публикация | 5 |
| FR-17 доступ раннера | 6 |
| FR-18 забор артефакта | 7 |
| FR-19 правила постановки | 8 |
| FR-20 тесты | распределено: 1, 3, 4, 5, 6, 7 |
| FR-21 документация | 9 |

FR-16 выполнено до плана (`docs/spikes/2026-08-19-openhands-mcp-config.md`). FR-1 — там же по соседству. FR-2 — FR-10 вне границ плана.

**Согласованность имён.** `session_id`, `workspace_for`, `claude_mcp_config`, `openhands_mcp_config`, `available`, `transcript`, `unavailable_artifact`, `enabled`, `max_turns`, `SERVER_NAME`, `ANALYSIS`, `DEVELOP`, `CONTOUR`, `PRODUCT` объявлены в задаче 1 и используются далее ровно в этих написаниях. `MCP_CONFIG_NAME` и `RUNNER_MCP_MOUNT` объявлены в задаче 6, используются в ней же. Ключ отчёта `outcome` объявлен в задаче 4.

**Слабое место, известное заранее.** Задачи 5, 6 и 7 правят функции, точные сигнатуры которых в плане не воспроизведены: сборщик комментария в `shared/agent_comment.py`, сборщик команды запуска в `shared/develop.py` и место завершения прогона в `worker/activities.py`. Первый шаг каждой из этих задач — прочитать текущий код и привести тест под фактические имена. Это осознанный компромисс: воспроизводить в плане три функции целиком дороже, чем прочитать их при исполнении.
