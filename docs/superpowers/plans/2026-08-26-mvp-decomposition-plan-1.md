# План 1: декомпозиция MVP, гейт GROW и передача контекста

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Одна законченная итерация разработки даёт один Issue в общем списке; под-задачи становятся временным инструментом деления, а контекст доезжает до исполнителя без потерь.

**Architecture:** Отдельный воркфлоу `MvpDelivery` ведёт шаги плана, заводя нативные под-задачи GitHub на время шага. План и весь контекст задачи живут каталогом `.harness/` в ветке задачи, исполнитель читает их файлами из git вместо упакованной постановки. Находки уходят в размеченную секцию тела родителя, а не в новые Issue. GROW открывается вердиктом приёмки и никого не блокирует.

**Tech Stack:** Python 3.12, Temporal (`temporalio==1.9.0`), pytest с `asyncio_mode = auto`, GitHub REST (включая `sub_issues`), Claude Code CLI для стадий документов.

**Спека:** `docs/superpowers/specs/2026-08-26-subissue-mvp-decomposition-design.md`. Требования этого плана: R1, R2, R2a, R3–R10, R12, R13, R18.

## Global Constraints

- Работа через Pull Request; в `main` не пушить.
- Python 3.12 — та же версия, что в `worker/Dockerfile` и `webhook/Dockerfile`.
- Порог покрытия 83% (`.coveragerc`); падение ниже роняет прогон.
- `worker/` и `webhook/` не пакеты: импортировать модули напрямую (`import github_client`), не `from worker.X`.
- Фикстура pytest из чужого тестового модуля не видна; общее место — `tests/conftest.py`.
- Любая правка РЕШЕНИЯ воркфлоу — `workflow.patched(...)` + фикстура истории в `tests/replay/histories/` + прогон корпуса живых прогонов `scripts/replay_histories.py` до выкладки.
- У активности с недетерминированной дорогой работой потолок попыток один.
- Агенту разработки GitHub-токен не дают: коммит, пуш и PR делает воркер.
- Свои правила организации старше импортированных практик (R12).
- Обязательные части процесса — шаги конвейера, а не доверие скиллу (R13).
- Модули `shared/*` намеренно чистые: ни сети, ни Temporal, ни GitHub.

## File Structure

| Файл | Ответственность |
|---|---|
| `shared/issue_blocks.py` (новый) | размеченные блоки тела Issue: прочитать, заменить, собрать |
| `shared/decomposition.py` | правило деления по объявленным зависимостям; раскладка по релизам |
| `shared/task_context.py` (новый) | состав каталога `.harness/`, карта контекста, проверка полноты |
| `worker/github_client.py` | нативные под-задачи: привязать, отвязать, перечислить |
| `worker/activities.py` | подготовка каталога контекста вместо упаковки постановки; находки в секцию |
| `worker/mvp_delivery.py` (новый) | воркфлоу `MvpDelivery`: шаги, под-задачи, чеклист |
| `worker/workflows.py` | одна точка: `ready-for-dev` запускает `MvpDelivery` |
| `shared/lifecycle.py` | переходы `merged → testing → released` |
| `.claude/commands/plan-mvp.md` (новый) | неинтерактивный `writing-plans` |

---

### Task 1: Размеченные блоки тела Issue

**Files:**
- Create: `shared/issue_blocks.py`
- Test: `tests/test_issue_blocks.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `MVP_PLAN = "mvp-plan"`, `GROW = "grow"`; `read(body: str, name: str) -> str | None`; `write(body: str, name: str, content: str) -> str`.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_issue_blocks.py`:

```python
"""Блоки тела Issue: контур правит только своё.

Тело правят и человек, и контур. Без границ они затирают друг друга: дописывание
в конец плодит дубли разделов, а перезапись целиком уносит текст человека.
"""

from shared import issue_blocks


def test_write_into_empty_body_appends_block():
    body = "Описание задачи от человека."
    result = issue_blocks.write(body, issue_blocks.MVP_PLAN, "- [ ] 1. Шаг")
    assert "Описание задачи от человека." in result
    assert issue_blocks.read(result, issue_blocks.MVP_PLAN) == "- [ ] 1. Шаг"


def test_write_replaces_block_and_keeps_human_text():
    body = issue_blocks.write("Текст человека.", issue_blocks.MVP_PLAN, "старое")
    result = issue_blocks.write(body, issue_blocks.MVP_PLAN, "новое")
    assert issue_blocks.read(result, issue_blocks.MVP_PLAN) == "новое"
    assert "старое" not in result
    assert "Текст человека." in result
    assert result.count("harness:mvp-plan:start") == 1


def test_two_blocks_are_independent():
    body = issue_blocks.write("Текст.", issue_blocks.MVP_PLAN, "план")
    body = issue_blocks.write(body, issue_blocks.GROW, "находки")
    assert issue_blocks.read(body, issue_blocks.MVP_PLAN) == "план"
    assert issue_blocks.read(body, issue_blocks.GROW) == "находки"


def test_read_absent_block_is_none():
    assert issue_blocks.read("просто текст", issue_blocks.MVP_PLAN) is None


def test_body_without_markers_survives_untouched():
    """Тело, где маркеров нет вовсе, не должно потерять ни строки."""
    body = "Строка 1\n\nСтрока 2"
    result = issue_blocks.write(body, issue_blocks.GROW, "x")
    assert result.startswith(body)
```

- [ ] **Step 2: Прогнать тест и убедиться, что падает**

Запуск: `pytest tests/test_issue_blocks.py -q --no-cov`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'shared.issue_blocks'`

- [ ] **Step 3: Написать минимальную реализацию**

Файл `shared/issue_blocks.py`:

```python
"""Размеченные блоки тела Issue — граница между текстом человека и контура.

Контур правит ТОЛЬКО то, что лежит между своими маркерами. Всё остальное тело
принадлежит человеку и не трогается: дописывание в конец плодило бы дубли
разделов при каждом обновлении плана, а перезапись целиком уносила бы
постановку.

Модуль намеренно чистый: ни сети, ни GitHub — как `lifecycle.py`.
"""

import re

MVP_PLAN = "mvp-plan"
GROW = "grow"


def _markers(name: str) -> tuple[str, str]:
    return f"<!-- harness:{name}:start -->", f"<!-- harness:{name}:end -->"


def read(body: str, name: str) -> str | None:
    """Содержимое блока либо None, если блока нет."""
    start, end = _markers(name)
    pattern = re.compile(re.escape(start) + r"\n(.*?)\n" + re.escape(end), re.S)
    found = pattern.search(body or "")
    return found.group(1) if found else None


def write(body: str, name: str, content: str) -> str:
    """Тело с заменённым (или добавленным) блоком."""
    start, end = _markers(name)
    block = f"{start}\n{content}\n{end}"
    pattern = re.compile(re.escape(start) + r"\n.*?\n" + re.escape(end), re.S)
    if pattern.search(body or ""):
        return pattern.sub(lambda _: block, body, count=1)
    tail = "" if (body or "").endswith("\n") else "\n"
    return f"{body or ''}{tail}\n{block}\n"
```

- [ ] **Step 4: Прогнать тест и убедиться, что проходит**

Запуск: `pytest tests/test_issue_blocks.py -q --no-cov`
Ожидается: `5 passed`

- [ ] **Step 5: Коммит**

```bash
git add shared/issue_blocks.py tests/test_issue_blocks.py
git commit -m "feat(issue): размеченные блоки тела — граница между человеком и контуром

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Правило деления по объявленным зависимостям

**Files:**
- Modify: `shared/decomposition.py`
- Test: `tests/test_decomposition.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `needs_subissues(items: list[dict]) -> bool`; `dependency_reason_missing(items: list[dict]) -> list[str]`.

Пункт плана — словарь с ключами `title`, `release`, `depends_on: list[int]`, `depends_reason: dict[str, str]` (ключ — индекс предшественника строкой).

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_decomposition.py`:

```python
def test_no_dependencies_means_single_run():
    """Граф без рёбер — не план, а список правок: делить нечего."""
    items = [
        {"title": "Импорт версии", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Лог версии", "release": "mvp", "depends_on": [], "depends_reason": {}},
    ]
    assert decomposition.needs_subissues(items) is False


def test_one_real_dependency_means_split():
    items = [
        {"title": "Загрузить версию", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Отдать версию", "release": "mvp", "depends_on": [0],
         "depends_reason": {"0": "читает version из состояния"}},
    ]
    assert decomposition.needs_subissues(items) is True


def test_single_item_never_splits():
    items = [{"title": "Одна правка", "release": "mvp", "depends_on": [], "depends_reason": {}}]
    assert decomposition.needs_subissues(items) is False


def test_dependency_without_reason_is_reported():
    """Ребро без предмета — выдумка ради вида плана, а не зависимость."""
    items = [
        {"title": "Первый", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Второй", "release": "mvp", "depends_on": [0], "depends_reason": {}},
    ]
    assert decomposition.dependency_reason_missing(items) == ["Второй"]


def test_dependency_with_reason_is_not_reported():
    items = [
        {"title": "Первый", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Второй", "release": "mvp", "depends_on": [0],
         "depends_reason": {"0": "использует функцию parse()"}},
    ]
    assert decomposition.dependency_reason_missing(items) == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_decomposition.py -q --no-cov -k "dependencies or dependency or single_run or never_splits"`
Ожидается: FAIL с `AttributeError: module 'shared.decomposition' has no attribute 'needs_subissues'`

- [ ] **Step 3: Написать реализацию**

Дописать в `shared/decomposition.py`:

```python
def needs_subissues(items: list[dict]) -> bool:
    """Разворачивать ли план в под-задачи.

    Шаг существует, только если от него зависит другой шаг. Граф без рёбер —
    это не план, а список правок, который исполнитель сделает за один прогон;
    заводить под каждую строку задачу в трекере значит платить вниманием за
    видимость, которой никто не пользуется.

    Определение взято из инструмента, а не выдумано: задачи планов superpowers
    несут блок Interfaces с Consumes/Produces, и непустой Consumes — это и есть
    объявленное ребро.
    """
    return any(item.get("depends_on") for item in items)


def dependency_reason_missing(items: list[dict]) -> list[str]:
    """Заголовки шагов, где зависимость объявлена без предмета.

    Ребро обязано называть, ЧТО даёт предшественник: «читает version из
    состояния». Без предмета зависимость невозможно ни проверить, ни
    опровергнуть, а модели дешевле выдумать её, чем признать, что плана нет.
    """
    bad = []
    for item in items:
        for index in item.get("depends_on") or []:
            if not (item.get("depends_reason") or {}).get(str(index), "").strip():
                bad.append(item["title"])
                break
    return bad
```

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_decomposition.py -q --no-cov`
Ожидается: все проходят, включая прежние.

- [ ] **Step 5: Коммит**

```bash
git add shared/decomposition.py tests/test_decomposition.py
git commit -m "feat(decomposition): делим только при объявленной зависимости

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Каталог контекста задачи

**Files:**
- Create: `shared/task_context.py`
- Test: `tests/test_task_context.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `DIR = ".harness"`; `PLAN`, `REQUIREMENTS`, `HOWTODEMO`, `DECISIONS`, `CONTEXT_MAP` — имена файлов; `render_map(entries: dict[str, str]) -> str`; `missing(root, entries: dict[str, str]) -> list[str]`; `truncation_markers(root) -> list[str]`.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_task_context.py`:

```python
"""Каталог контекста задачи: исполнитель читает файлы, а не пересказ.

До этого постановка упаковывалась в один файл с потолками 50000 знаков на всё
и 10000 на артефакт, лишние секции вытеснялись целиком. Докстринг того кода
признавал: «Переполнение достижимо штатно». Потеря контекста была не риском, а
заложенным поведением.
"""

from shared import task_context


def test_map_lists_every_entry():
    text = task_context.render_map({
        task_context.PLAN: "план работ",
        task_context.REQUIREMENTS: "системные требования",
    })
    assert task_context.PLAN in text
    assert "план работ" in text
    assert task_context.REQUIREMENTS in text


def test_missing_names_absent_files(tmp_path):
    (tmp_path / task_context.PLAN).write_text("текст", encoding="utf-8")
    absent = task_context.missing(tmp_path, {
        task_context.PLAN: "план",
        task_context.REQUIREMENTS: "требования",
    })
    assert absent == [task_context.REQUIREMENTS]


def test_empty_file_counts_as_missing(tmp_path):
    """Пустой файл хуже отсутствующего: он выглядит доставленным."""
    (tmp_path / task_context.PLAN).write_text("   \n", encoding="utf-8")
    assert task_context.missing(tmp_path, {task_context.PLAN: "план"}) == [task_context.PLAN]


def test_truncation_marker_is_found(tmp_path):
    (tmp_path / task_context.PLAN).write_text("начало …[обрезано]", encoding="utf-8")
    assert task_context.truncation_markers(tmp_path) == [task_context.PLAN]


def test_clean_directory_has_no_markers(tmp_path):
    (tmp_path / task_context.PLAN).write_text("целый текст", encoding="utf-8")
    assert task_context.truncation_markers(tmp_path) == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_task_context.py -q --no-cov`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'shared.task_context'`

- [ ] **Step 3: Написать реализацию**

Файл `shared/task_context.py`:

```python
"""Состав каталога `.harness/` — контекст задачи, который читает исполнитель.

Смысл каталога в том, что контекст НЕ пересказывается. Исполнитель открывает
файлы из git по мере надобности, поэтому потолков на объём нет и усечения нет.

Каталог коммитится в ветку задачи: он виден в PR и читается через полгода —
в отличие от прежней постановки, которая снималась перед коммитом, и
восстановить, что именно видел исполнитель, было нечем.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub.
"""

from pathlib import Path

DIR = ".harness"

PLAN = "plan.md"
REQUIREMENTS = "requirements.md"
HOWTODEMO = "howtodemo.md"
DECISIONS = "decisions.md"
CONTEXT_MAP = "context.md"

TRUNCATION_MARKER = "…[обрезано]"


def render_map(entries: dict[str, str]) -> str:
    """Карта контекста: что где лежит и в каком порядке читать."""
    lines = ["# Контекст задачи", "",
             "Читать в этом порядке. Все файлы лежат рядом с этим.", ""]
    lines += [f"- `{name}` — {what}" for name, what in entries.items()]
    return "\n".join(lines) + "\n"


def missing(root, entries: dict[str, str]) -> list[str]:
    """Имена объявленных файлов, которых нет либо которые пусты.

    Пустой файл считается отсутствующим намеренно: он выглядит доставленным и
    потому опаснее — стадия отчитается успехом, а исполнитель не получит
    ничего.
    """
    base = Path(root)
    absent = []
    for name in entries:
        path = base / name
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            absent.append(name)
    return absent


def truncation_markers(root) -> list[str]:
    """Файлы каталога, где остался след обрезки."""
    base = Path(root)
    found = []
    for path in sorted(base.glob("*.md")):
        if TRUNCATION_MARKER in path.read_text(encoding="utf-8"):
            found.append(path.name)
    return found
```

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_task_context.py -q --no-cov`
Ожидается: `5 passed`

- [ ] **Step 5: Коммит**

```bash
git add shared/task_context.py tests/test_task_context.py
git commit -m "feat(context): каталог .harness — контекст задачи файлами, без потолков

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Нативные под-задачи GitHub

**Files:**
- Modify: `worker/github_client.py`
- Test: `tests/test_github_subissues.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `link_sub_issue(repo: str, parent: int, child_id: int) -> None`; `list_sub_issues(repo: str, parent: int) -> list[dict]`; `issue_node_id(repo: str, issue_number: int) -> int`.

Привязка идёт по внутреннему `id` задачи, а не по её номеру — это требование API `sub_issues`.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_github_subissues.py`:

```python
"""Нативные под-задачи GitHub: связь без строки в теле.

`root-issue: #N` в теле давало связь, которую GitHub не понимает: подзадача
оставалась обычным Issue в общем списке. Нативная связь убирает её оттуда и
даёт счётчик готовности у родителя.
"""

import github_client


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


def test_link_posts_child_id_not_number(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        return _FakeResponse({}, 201)

    monkeypatch.setattr(github_client.requests, "post", fake_post)
    monkeypatch.setattr(github_client, "_headers", lambda repo: {})

    github_client.link_sub_issue("o/r", 151, 987654)

    assert seen["url"].endswith("/repos/o/r/issues/151/sub_issues")
    assert seen["json"] == {"sub_issue_id": 987654}


def test_list_returns_children(monkeypatch):
    monkeypatch.setattr(github_client.requests, "get",
                        lambda url, headers=None, timeout=None:
                            _FakeResponse([{"number": 152}, {"number": 153}]))
    monkeypatch.setattr(github_client, "_headers", lambda repo: {})

    assert [i["number"] for i in github_client.list_sub_issues("o/r", 151)] == [152, 153]


def test_node_id_comes_from_issue(monkeypatch):
    monkeypatch.setattr(github_client, "get_issue",
                        lambda repo, number: {"number": number, "id": 424242})
    assert github_client.issue_node_id("o/r", 152) == 424242
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_github_subissues.py -q --no-cov`
Ожидается: FAIL с `AttributeError: module 'github_client' has no attribute 'link_sub_issue'`

- [ ] **Step 3: Написать реализацию**

Дописать в `worker/github_client.py`:

```python
def issue_node_id(repo: str, issue_number: int) -> int:
    """Внутренний id задачи. Привязка под-задач идёт по нему, а не по номеру."""
    return int(get_issue(repo, issue_number)["id"])


def link_sub_issue(repo: str, parent: int, child_id: int) -> None:
    """Привязать задачу к родителю нативной связью GitHub.

    `child_id` — внутренний id (см. `issue_node_id`), НЕ номер. Передача номера
    даёт 422 с невнятным телом, и отличить её от прочих отказов трудно.
    """
    response = requests.post(
        f"{API}/repos/{repo}/issues/{parent}/sub_issues",
        headers=_headers(repo),
        json={"sub_issue_id": child_id},
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def list_sub_issues(repo: str, parent: int) -> list[dict]:
    """Под-задачи родителя."""
    response = requests.get(
        f"{API}/repos/{repo}/issues/{parent}/sub_issues",
        headers=_headers(repo),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()
```

Если имена `API`, `TIMEOUT` или `_headers` в файле отличаются — использовать существующие: посмотреть на соседнюю функцию `create_issue` и повторить её приём получения заголовков и адреса.

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_github_subissues.py -q --no-cov`
Ожидается: `3 passed`

- [ ] **Step 5: Проверить живым вызовом, что связь работает и прячет задачу из списка**

Это единственная проверка, которую нельзя сделать подделкой: до сих пор ни одной нативной под-задачи в репозиториях организации не существовало, и фильтр `-is:sub-issue` проверить было не на чем.

```bash
gh issue create --repo po-helper-org/poh-demo-checkout --title "проба под-задачи" --body "временная" 
gh api repos/po-helper-org/poh-demo-checkout/issues/<номер родителя>/sub_issues \
  -X POST -F sub_issue_id=$(gh api repos/po-helper-org/poh-demo-checkout/issues/<номер пробы> --jq .id)
gh issue list --repo po-helper-org/poh-demo-checkout --search "is:open -is:sub-issue" --json number --jq 'length'
gh issue list --repo po-helper-org/poh-demo-checkout --search "is:open" --json number --jq 'length'
```

Ожидается: второе число на единицу больше первого. Пробную задачу закрыть.
Если фильтр не работает — записать это в отчёт: тогда требование R1 держится не выборкой GitHub, а тем, что под-задача закрывается вместе с шагом, и в спеку нужна поправка.

- [ ] **Step 6: Коммит**

```bash
git add worker/github_client.py tests/test_github_subissues.py
git commit -m "feat(github): нативные под-задачи — привязать, перечислить

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Правило фокуса как базовое знание

**Files:**
- Modify: `worker/activities.py` (рядом с `_DEV_FALLBACK_RULES`, около строки 2006 на `main`)
- Test: `tests/test_dev_task_assembly.py`
- Create: `harness-memory-base/rules/develop/D-011.md` (в репозитории слоя, отдельным PR)
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: ничего.
- Produces: `_FOCUS_RULE` — строка блока правила фокуса, дописываемая к постановке отдельным блоком.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_dev_task_assembly.py`:

```python
def test_focus_rule_survives_repository_own_rules(monkeypatch, tmp_path):
    """Правило фокуса обязано доехать и в репозиторий со своими правилами.

    Свой `.openhands/task-rules.md` целевого репозитория вытесняет запасные
    правила контура ЦЕЛИКОМ. Это уже стоило потери блока правил и инструкции
    про файл находок: они жили внутри запасных правил и исчезали в самых
    обычных репозиториях — тех, у кого свои правила есть.
    """
    import activities as a

    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None: "## Свои правила репозитория"
                        if path.endswith("task-rules.md") else "")
    monkeypatch.setattr(a, "_clone_repo", lambda repo, dest, branch=None: None)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-1")

    assert "Свои правила репозитория" in task, "правила репозитория потерялись"
    assert "пройдёт ли сценарий без этого" in task, "правило фокуса не доехало"
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_dev_task_assembly.py -q --no-cov -k focus_rule`
Ожидается: FAIL с `AssertionError: правило фокуса не доехало`

- [ ] **Step 3: Написать реализацию**

Дописать в `worker/activities.py` рядом с `_DEV_REFLECT_NOTE_RULE`:

```python
_FOCUS_RULE = """## Фокус

Нашёл по дороге то, без чего сценарий приёмки всё равно пройдёт, — запиши в
`.followups.md` и иди дальше. Нужно для прохождения сценария — сделай здесь же,
отдельной задачи не заводи.

Граница не на вкус: критерий один — пройдёт ли сценарий без этого.

Ветка, где сделано лишнее, ревьюится дольше и откатывается целиком. Работа,
которой не хватило для сценария, возвращается кругом правок и стоит второго
прогона.
"""
```

И дописать её к постановке ОТДЕЛЬНЫМ блоком — там же, где дописывается
`_DEV_REFLECT_NOTE_RULE`, а не внутри `_DEV_FALLBACK_RULES`.

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_dev_task_assembly.py -q --no-cov`
Ожидается: все проходят.

- [ ] **Step 5: Записать старшинство источников в `AGENTS.md`**

Добавить разделом после правила 8:

```markdown
### 9. Свои правила старше импортированных практик

В постановку агента приезжают два источника: практики superpowers
(`.claude/skills/`, импортированы, обновляются извне) и правила организации
(`harness-memory-base/rules/`, курируются человеком, меняются только PR).

Практики отвечают на вопрос КАК делать. Правила организации — что считать
сделанным и чего не делать. Противоречие разрешается в пользу своих правил.

Без объявленного старшинства выбирает исполнитель, и выбор будет разным от
прогона к прогону.
```

- [ ] **Step 6: Завести правило организации**

В репозитории `harness-memory-base`, отдельной веткой и отдельным PR, файл
`rules/develop/D-011.md` — текст взять из спеки, раздел «Правило организации».

- [ ] **Step 7: Коммит**

```bash
git add worker/activities.py tests/test_dev_task_assembly.py AGENTS.md
git commit -m "feat(develop): правило фокуса отдельным блоком, старшинство источников

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Находки уходят в секцию, а не в Issue

**Files:**
- Modify: `worker/activities.py` — `collect_dev_followups` (около строки 2569 на `main`)
- Test: `tests/test_develop_followups.py`

**Interfaces:**
- Consumes: `shared.issue_blocks.write`, `issue_blocks.GROW` (Task 1).
- Produces: `collect_dev_followups(issue) -> list[str]` — теперь возвращает заголовки записанных находок, а не номера созданных Issue.

Возвращаемый тип меняется намеренно: номеров больше нет, и оставить `list[int]` значило бы врать сигнатурой.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_develop_followups.py`:

```python
def test_followups_go_to_grow_section_not_issues(monkeypatch, tmp_path):
    """Находка становится строкой в теле родителя, а не новой задачей.

    221 из 267 открытых задач организации завёл контур; большая часть — именно
    находки. Каждая поднимала свой вечный цикл и проходила триаж.
    """
    import asyncio
    import activities as a
    from shared import issue_blocks

    created = []
    body = {"text": "Постановка от человека."}

    monkeypatch.setattr(a.github_client, "create_issue",
                        lambda *args, **kwargs: created.append(args) or 999)
    monkeypatch.setattr(a.github_client, "get_issue_body", lambda repo, n: body["text"])
    monkeypatch.setattr(a.github_client, "update_issue_body",
                        lambda repo, n, new: body.__setitem__("text", new))
    monkeypatch.setattr(a.github_client, "post_comment", lambda *a_, **k_: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    root, clone = a._dev_paths(issue_stub := a.IssueInput(
        repo="o/r", issue_number=42, title="t", body="b",
        author_login="u", author_type="User"))
    clone.mkdir(parents=True, exist_ok=True)
    (clone / a.develop.FOLLOWUPS_FILE).write_text(
        "## Отрицательная цена проходит в расчёт\n\n"
        "`subtotal` проверяет price < 0 после умножения (src/pricing.mjs:26).\n",
        encoding="utf-8")

    result = asyncio.run(a.collect_dev_followups(issue_stub))

    assert created == [], "находка всё ещё заводит Issue"
    assert result == ["Отрицательная цена проходит в расчёт"]
    section = issue_blocks.read(body["text"], issue_blocks.GROW)
    assert section is not None and "Отрицательная цена" in section
    assert "Постановка от человека." in body["text"]
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_develop_followups.py -q --no-cov -k grow_section`
Ожидается: FAIL с `AssertionError: находка всё ещё заводит Issue`

- [ ] **Step 3: Переписать `collect_dev_followups`**

Заменить тело функции: разбор `.followups.md` остаётся прежним (`develop.parse_followups`), создание задач уходит.

```python
@activity.defn
async def collect_dev_followups(issue: IssueInput) -> list[str]:
    """Находки шага — строками в секцию GROW тела родителя.

    Прежде каждая находка становилась Issue: он проходил триаж, поднимал свой
    вечный цикл и вставал в общую очередь. На 267 открытых задач организации
    221 заведена контуром, и находки — их основная часть.

    Теперь находка ждёт гейта приёмки строкой в теле родителя. Issue из неё
    заведёт человек, если решит, — и только после того, как MVP подтверждён.
    """
    root, clone_dir = _dev_paths(issue)
    path = Path(clone_dir) / develop.FOLLOWUPS_FILE
    if not path.exists():
        return []
    try:
        items = develop.parse_followups(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — разбор находок не ломает разработку
        logger.warning("не разобрал %s по %s#%s: %s",
                       develop.FOLLOWUPS_FILE, issue.repo, issue.issue_number, exc)
        items = []
    path.unlink(missing_ok=True)
    if not items:
        return []

    lines = [f"- [ ] {item['title']} — {item.get('detail', '').strip()}" for item in items]
    previous = issue_blocks.read(
        await asyncio.to_thread(github_client.get_issue_body, issue.repo, issue.issue_number),
        issue_blocks.GROW) or ""
    content = "## GROW — после прохождения HowToDemo\n\n" + "\n".join(
        [line for line in previous.splitlines() if line.startswith("- [")] + lines)

    body = await asyncio.to_thread(github_client.get_issue_body, issue.repo, issue.issue_number)
    await asyncio.to_thread(github_client.update_issue_body, issue.repo, issue.issue_number,
                            issue_blocks.write(body, issue_blocks.GROW, content))
    return [item["title"] for item in items]
```

Добавить импорт `from shared import issue_blocks` рядом с прочими импортами `shared`.

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_develop_followups.py -q --no-cov`
Ожидается: все проходят. Тесты, ожидавшие создания Issue, обновить — они закрепляли прежнее поведение.

- [ ] **Step 5: Коммит**

```bash
git add worker/activities.py tests/test_develop_followups.py
git commit -m "feat(followups): находки в секцию GROW вместо новых Issue

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Подготовка контекста файлами вместо упаковки

**Files:**
- Modify: `worker/activities.py` — `_dev_prepare` (около строки 1774 на `main`)
- Modify: `shared/develop.py` — `SERVICE_FILES`
- Test: `tests/test_dev_task_assembly.py`

**Interfaces:**
- Consumes: `shared.task_context` (Task 3).
- Produces: `_dev_prepare(issue, branch) -> tuple[str, list[str]]` — постановка теперь короткая и указывает на `.harness/`; второй элемент прежний (идентификаторы применённых правил).

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_dev_task_assembly.py`:

```python
def test_context_goes_to_files_without_truncation(monkeypatch, tmp_path):
    """Контекст доезжает файлами, а не упаковкой с потолком.

    Прежде постановка паковалась в один файл: 50000 знаков на всё, 10000 на
    артефакт, лишние секции вытеснялись целиком. Докстринг того кода признавал:
    «Переполнение достижимо штатно».
    """
    import activities as a
    from shared import task_context

    long_requirements = "требование\n" * 5000   # заведомо больше прежнего потолка

    monkeypatch.setattr(a.github_client, "get_file",
                        lambda repo, path, ref=None:
                            long_requirements if path.endswith("system_requirements.md") else "")
    monkeypatch.setattr(a, "_clone_repo", lambda repo, dest, branch=None: None)
    monkeypatch.setattr(a, "_handover_to_runner", lambda root: None)
    monkeypatch.setattr(a.develop, "workspace_mount", lambda: str(tmp_path))

    issue = a.IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                         author_login="u", author_type="User")
    task, _ = a._dev_prepare(issue, "research/issue-7")

    root, clone = a._dev_paths(issue)
    harness = Path(clone) / task_context.DIR

    assert (harness / task_context.CONTEXT_MAP).exists(), "карты контекста нет"
    assert task_context.missing(harness, {task_context.REQUIREMENTS: "требования"}) == []
    assert task_context.truncation_markers(harness) == [], "контекст обрезан"
    assert (harness / task_context.REQUIREMENTS).read_text(encoding="utf-8").count("требование") == 5000
    assert task_context.DIR in task, "постановка не указывает на каталог контекста"
    assert len(task) < 5000, "постановка снова пересказывает контекст вместо ссылки"
```

Добавить `from pathlib import Path` в начало файла, если его там нет.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_dev_task_assembly.py -q --no-cov -k context_goes_to_files`
Ожидается: FAIL — каталога `.harness/` нет.

- [ ] **Step 3: Переписать подготовку**

В `_dev_prepare`:

1. Создать каталог `Path(clone_dir) / task_context.DIR`.
2. Сложить туда файлы: требования из ветки аналитики, сценарий приёмки из тела Issue, решения (файл намерений прошлых шагов, если есть), план (кладёт Task 8; пока может отсутствовать).
3. Записать `context.md` через `task_context.render_map`.
4. Постановку собрать короткой: что сделать, где контекст, чем проверяется.
5. Удалить `DEV_TASK_MAX_CHARS`, `DEV_ARTIFACT_MAX_CHARS`, `_apply_size_limit` и их вызовы — вместе с тестами, которые закрепляли усечение.

```python
    harness = Path(clone_dir) / task_context.DIR
    harness.mkdir(parents=True, exist_ok=True)

    entries: dict[str, str] = {}
    requirements = github_client.get_file(
        issue.repo, f"{FNR_DIR}/system_requirements.md", branch) or ""
    if requirements:
        (harness / task_context.REQUIREMENTS).write_text(requirements, encoding="utf-8")
        entries[task_context.REQUIREMENTS] = "системные требования (ветка аналитики)"

    scenario = _howtodemo_block(issue.body or "")
    if scenario:
        (harness / task_context.HOWTODEMO).write_text(scenario, encoding="utf-8")
        entries[task_context.HOWTODEMO] = "сценарий приёмки: им проверяется результат"

    (harness / task_context.CONTEXT_MAP).write_text(
        task_context.render_map(entries), encoding="utf-8")
```

Функция `_howtodemo_block(body)` — вырезка блока HowToDemo из тела Issue; если
в теле блока нет, возвращает пустую строку. Её отсутствие не отказ: сценарий
может лежать в письме БФТ, и приёмщик умеет брать его оттуда.

- [ ] **Step 4: Снять `.harness` со списка удаляемых**

В `shared/develop.py`, `SERVICE_FILES` — убедиться, что `.harness` там НЕТ, и
дописать комментарий рядом:

```python
# `.harness/` в этот перечень НЕ входит намеренно: это контекст задачи, он
# коммитится вместе с кодом. Снятая постановка не давала восстановить, что
# именно видел исполнитель.
```

- [ ] **Step 5: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_dev_task_assembly.py -q --no-cov`
Ожидается: все проходят.

- [ ] **Step 6: Полный прогон**

Запуск: `pytest -q`
Ожидается: все зелёные, `Required test coverage of 83.0% reached`.

- [ ] **Step 7: Коммит**

```bash
git add worker/activities.py shared/develop.py tests/test_dev_task_assembly.py
git commit -m "feat(context): исполнитель читает .harness из git, потолки постановки сняты

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Команда построения плана

**Files:**
- Create: `.claude/commands/plan-mvp.md`
- Modify: `worker/activities.py` — новая активность `build_mvp_plan`
- Test: `tests/test_plan_mvp.py`

**Interfaces:**
- Consumes: `shared.task_context` (Task 3), `_run_claude` (существует).
- Produces: активность `build_mvp_plan(issue: IssueInput, branch: str) -> bool` — истина, если `.harness/plan.md` создан и непуст.

- [ ] **Step 1: Написать команду**

Файл `.claude/commands/plan-mvp.md`:

```markdown
---
description: План работ по системным требованиям, неинтерактивно
---

Прочитай `.harness/requirements.md` и `.harness/howtodemo.md` в текущем каталоге.

Используй навык writing-plans, чтобы составить план работ, и запиши его в
`.harness/plan.md`.

Три отступления от навыка, обязательных здесь:

1. **Ничего не спрашивай.** Прогон неинтерактивный, отвечать некому. Место, где
   навык предлагает выбрать способ исполнения, пропусти.
2. **Ничего не исполняй.** Твой результат — файл плана, и только он.
3. **У каждой задачи заполни блок Interfaces.** `Consumes` — что задача берёт
   у предыдущих, назвав предмет: не «зависит от 1», а «читает version из
   состояния». Пустой `Consumes` означает, что задача независима, и это
   законный ответ.

Границей MVP считай сценарий приёмки: задача входит в план, только если без неё
сценарий не пройдёт. Остальное перечисли в конце файла разделом «Вне MVP».
```

- [ ] **Step 2: Написать падающий тест**

Файл `tests/test_plan_mvp.py`:

```python
"""Стадия построения плана: артефакт проверяется существованием, не словом модели.

Стадия `validate` цепочки FNR объявлена с ожидаемым артефактом None — проверять
нечего, и вердикт пишет сама модель. Здесь так нельзя: план — вход исполнителя.
"""

import asyncio
from pathlib import Path

import activities as a
from shared import task_context


def test_plan_stage_fails_when_file_not_created(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "_run_claude", lambda prompt, cwd, mcp=None: None)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))
    (tmp_path / "repo" / task_context.DIR).mkdir(parents=True)

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is False


def test_plan_stage_succeeds_when_file_written(monkeypatch, tmp_path):
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)

    def fake_claude(prompt, cwd, mcp=None):
        (harness / task_context.PLAN).write_text("# План\n\n### Task 1\n", encoding="utf-8")

    monkeypatch.setattr(a, "_run_claude", fake_claude)
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is True


def test_empty_plan_file_counts_as_failure(monkeypatch, tmp_path):
    """Пустой файл выглядит доставленным — самый дорогой вид отказа."""
    harness = tmp_path / "repo" / task_context.DIR
    harness.mkdir(parents=True)
    monkeypatch.setattr(a, "_run_claude",
                        lambda prompt, cwd, mcp=None:
                            (harness / task_context.PLAN).write_text("  \n", encoding="utf-8"))
    monkeypatch.setattr(a, "_dev_paths", lambda issue: (tmp_path, tmp_path / "repo"))

    issue = a.IssueInput(repo="o/r", issue_number=3, title="t", body="b",
                         author_login="u", author_type="User")
    assert asyncio.run(a.build_mvp_plan(issue, "research/issue-3")) is False
```

- [ ] **Step 3: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_plan_mvp.py -q --no-cov`
Ожидается: FAIL с `AttributeError: module 'activities' has no attribute 'build_mvp_plan'`

- [ ] **Step 4: Написать активность**

```python
@activity.defn
async def build_mvp_plan(issue: IssueInput, branch: str) -> bool:
    """План работ по требованиям — навыком writing-plans, файлом в `.harness/`.

    Исход считается по АРТЕФАКТУ, а не по коду возврата и не по словам модели:
    `claude -p` выходит нулём и без файла — так уже падали стадии FNR на
    ограничении частоты у провайдера.
    """
    _, clone_dir = _dev_paths(issue)
    plan_path = Path(clone_dir) / task_context.DIR / task_context.PLAN
    await asyncio.to_thread(_run_claude, "/plan-mvp", str(clone_dir))
    return plan_path.exists() and bool(plan_path.read_text(encoding="utf-8").strip())
```

- [ ] **Step 5: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_plan_mvp.py -q --no-cov`
Ожидается: `3 passed`

- [ ] **Step 6: Коммит**

```bash
git add .claude/commands/plan-mvp.md worker/activities.py tests/test_plan_mvp.py
git commit -m "feat(plan): стадия построения плана навыком writing-plans

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Воркфлоу MvpDelivery

**Files:**
- Create: `worker/mvp_delivery.py`
- Modify: `worker/worker.py` — регистрация воркфлоу
- Test: `tests/test_mvp_delivery.py`

**Interfaces:**
- Consumes: `decomposition.needs_subissues` (Task 2), `github_client.link_sub_issue` / `issue_node_id` (Task 4), `issue_blocks` (Task 1), `build_mvp_plan` (Task 8).
- Produces: воркфлоу `MvpDelivery` с методом `run(issue: IssueInput) -> int | None` (возвращает номер PR либо None); активности `mvp_read_plan`, `mvp_open_substep`, `mvp_close_substep`.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_mvp_delivery.py`:

```python
"""MvpDelivery: шаги плана, под-задачи на время шага.

Проверяется ПОРЯДОК внешних действий, а не арифметика: релиз и доставка
ошибаются в последовательности. Тот же приём, что у тестов Delivery-Agent.
"""

import asyncio

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import mvp_delivery
from shared.workflow_types import IssueInput


@pytest.mark.timeout(60)
async def test_plan_without_dependencies_runs_once_without_subissues():
    """Граф без рёбер — под-задач ноль, один прогон разработки."""
    calls = []

    async def fake_read_plan(issue):
        return [{"title": "Одна правка", "depends_on": [], "depends_reason": {}}]

    async def fake_open(issue, index, title):
        calls.append(("open", index))
        return 0

    async def fake_develop(issue, step_index):
        calls.append(("develop", step_index))
        return 101

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[mvp_delivery.MvpDelivery],
                          activities=[fake_read_plan, fake_open, fake_develop]):
            pr = await env.client.execute_workflow(
                mvp_delivery.MvpDelivery.run,
                IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                           author_login="u", author_type="User"),
                id="mvp-1", task_queue="tq")

    assert pr == 101
    assert ("open", 0) not in calls, "под-задача заведена там, где делить нечего"
    assert calls.count(("develop", 0)) == 1
```

Имена активностей в тесте подставляются подделками через тот же приём, что в
`tests/test_agents_as_children.py`: активность объявляется строкой имени, а
подделка регистрируется под тем же именем. Смотреть, как это сделано там, и
повторить — иначе конвертер Temporal отдаст `dict` вместо dataclass.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_mvp_delivery.py -q --no-cov`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'mvp_delivery'`

- [ ] **Step 3: Написать воркфлоу**

Файл `worker/mvp_delivery.py`:

```python
"""MvpDelivery — доведение одного MVP от плана до готовности к приёмке.

Почему отдельный воркфлоу, а не фаза `IssueLifecycle`: своя история для
разбора, свой `workflow list`, шаги переживают рестарт воркера, а ошибка в
логике шагов правится без риска для живых прогонов цикла Issue. Тот же приём,
что у `IssueDevelopment`, `IssuePrFix` и `DeliveryRelease`.

Чего не делает: не ревьюит, не мержит, не выкатывает, не заводит GROW-Issue.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared import decomposition
    from shared.workflow_types import IssueInput

_ONE_ATTEMPT = RetryPolicy(maximum_attempts=1)


@workflow.defn(name="MvpDelivery")
class MvpDelivery:
    @workflow.run
    async def run(self, issue: IssueInput) -> int | None:
        items = await workflow.execute_activity(
            "mvp_read_plan", issue, result_type=list,
            start_to_close_timeout=timedelta(minutes=5), retry_policy=_ONE_ATTEMPT)
        if not items:
            return None

        if not decomposition.needs_subissues(items):
            # Делить нечего: план без объявленных зависимостей — список правок,
            # который исполнитель сделает за один прогон.
            return await workflow.execute_activity(
                "mvp_develop_step", args=[issue, 0], result_type=int,
                start_to_close_timeout=timedelta(seconds=3600),
                heartbeat_timeout=timedelta(seconds=300), retry_policy=_ONE_ATTEMPT)

        pr_number: int | None = None
        for index, item in enumerate(items):
            number = await workflow.execute_activity(
                "mvp_open_substep", args=[issue, index, item["title"]], result_type=int,
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_ONE_ATTEMPT)
            pr_number = await workflow.execute_activity(
                "mvp_develop_step", args=[issue, index], result_type=int,
                start_to_close_timeout=timedelta(seconds=3600),
                heartbeat_timeout=timedelta(seconds=300), retry_policy=_ONE_ATTEMPT)
            await workflow.execute_activity(
                "mvp_close_substep", args=[issue, number, index],
                start_to_close_timeout=timedelta(minutes=5), retry_policy=_ONE_ATTEMPT)
        return pr_number
```

Активности `mvp_read_plan`, `mvp_open_substep`, `mvp_develop_step`,
`mvp_close_substep` объявляются в `worker/activities.py`. Разбор плана — чистой
функцией `plan_parse.parse` из **Task 12**, её и вызывает `mvp_read_plan`.
`mvp_open_substep` заводит задачу и привязывает нативно: `create_issue` →
`issue_node_id` → `link_sub_issue` (Task 4), с метками `ORIGIN_AGENT` и `STEP`
(Task 13). `mvp_close_substep` закрывает задачу (`github_client.close_issue`) и
отмечает пункт чеклиста в теле родителя через `issue_blocks.write` (Task 1).
`mvp_develop_step` — существующий прогон разработки, вызванный на один шаг.

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_mvp_delivery.py -q --no-cov`
Ожидается: `1 passed`

- [ ] **Step 5: Дописать тест на путь с делением**

```python
@pytest.mark.timeout(60)
async def test_plan_with_dependency_opens_and_closes_subissue_per_step():
    calls = []

    async def fake_read_plan(issue):
        return [
            {"title": "Первый", "depends_on": [], "depends_reason": {}},
            {"title": "Второй", "depends_on": [0], "depends_reason": {"0": "берёт parse()"}},
        ]

    async def fake_open(issue, index, title):
        calls.append(("open", index))
        return 200 + index

    async def fake_develop(issue, step_index):
        calls.append(("develop", step_index))
        return 300 + step_index

    async def fake_close(issue, number, index):
        calls.append(("close", number))

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue="tq",
                          workflows=[mvp_delivery.MvpDelivery],
                          activities=[fake_read_plan, fake_open, fake_develop, fake_close]):
            await env.client.execute_workflow(
                mvp_delivery.MvpDelivery.run,
                IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                           author_login="u", author_type="User"),
                id="mvp-2", task_queue="tq")

    assert calls == [("open", 0), ("develop", 0), ("close", 200),
                     ("open", 1), ("develop", 1), ("close", 201)]
```

- [ ] **Step 6: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_mvp_delivery.py -q --no-cov`
Ожидается: `2 passed`

- [ ] **Step 7: Зарегистрировать воркфлоу**

В `worker/worker.py` добавить `MvpDelivery` в перечень воркфлоу очереди
`issue-lifecycle` рядом с `IssueDevelopment` и `IssuePrFix`, а новые активности —
в перечень активностей.

- [ ] **Step 8: Коммит**

```bash
git add worker/mvp_delivery.py worker/worker.py worker/activities.py tests/test_mvp_delivery.py
git commit -m "feat(mvp): воркфлоу MvpDelivery — шаги плана и под-задачи на время шага

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Врезка в цикл Issue

**Files:**
- Modify: `worker/workflows.py` — `_start_development`
- Create: `tests/replay/histories/<фикстура>.json.gz`
- Test: `tests/test_workflow_replay.py` (существует)

**Interfaces:**
- Consumes: `MvpDelivery` (Task 9).
- Produces: маркер `issue-lifecycle-mvp-delivery`.

**Это правка РЕШЕНИЯ воркфлоу.** Без маркера она остановит идущие прогоны: их истории записали запуск `IssueDevelopment`, а новый код запустит другой воркфлоу. Так уже встали 29 прогонов из 149.

- [ ] **Step 1: Снять свежий корпус историй со стенда**

```bash
ssh poh-stand "T=compose-connect-redundant-system-mzso3q-temporal-1
A=--address=compose-connect-redundant-system-mzso3q-temporal-1:7233
rm -rf /tmp/hist && mkdir -p /tmp/hist
for w in \$(docker exec \$T temporal workflow list \$A --limit 300 2>/dev/null \
             | awk '\$3==\"IssueLifecycle\"{print \$2}'); do
  docker exec \$T temporal workflow show \$A -w \"\$w\" -o json \
    > /tmp/hist/\$(echo \"\$w\" | tr '/' '_').json 2>/dev/null
done
tar -czf /tmp/hist.tgz -C /tmp hist"
scp poh-stand:/tmp/hist.tgz /tmp/ && mkdir -p /tmp/corpus && tar -xzf /tmp/hist.tgz -C /tmp/corpus --strip-components=1
```

- [ ] **Step 2: Прогнать корпус до правки — зафиксировать базовую линию**

Запуск: `python scripts/replay_histories.py /tmp/corpus`
Записать числа в отчёт. Всё, что падало ДО правки, падает по другим причинам и этой задачей не лечится.

- [ ] **Step 3: Внести правку под маркером**

В `worker/workflows.py`, метод `_start_development`, заменить выбор дочернего воркфлоу:

```python
            if workflow.patched("issue-lifecycle-mvp-delivery"):
                # MVP ведёт отдельный воркфлоу: он разворачивает план в шаги и
                # заводит под-задачу на время каждого. Прежние прогоны записали
                # запуск IssueDevelopment — маркер разводит эти пути.
                pr_number = await workflow.execute_child_workflow(
                    MvpDelivery.run, issue,
                    id=mvp_delivery_workflow_id(issue.repo, issue.issue_number),
                    parent_close_policy=ParentClosePolicy.ABANDON,
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            elif workflow.patched("issue-lifecycle-develop-child"):
                # Прежняя ветка сохраняется ДОСЛОВНО: по ней идёт реплей
                # прогонов, начатых до этой правки. Ни строки не менять.
```

В `shared/workflow_ids.py` добавить:

```python
def mvp_delivery_workflow_id(repo_full_name: str, issue_number: int) -> str:
    """MVP по задаче — ровно один за раз."""
    return f"mvp-{repo_full_name}-{issue_number}"
```

- [ ] **Step 4: Прогнать корпус после правки**

Запуск: `python scripts/replay_histories.py /tmp/corpus`
Ожидается: **числа совпадают с базовой линией шага 2**. Любое новое падение означает, что маркер не разводит путь, и правку выкладывать нельзя.

- [ ] **Step 5: Положить фикстуру**

Взять из корпуса историю, проходящую через `_start_development`, проверить на секреты декодирующей проверкой из `tests/replay/README.md`, положить сжатой в `tests/replay/histories/` под именем-идентификатором с `__` вместо `/`.

- [ ] **Step 6: Полный прогон**

Запуск: `pytest -q`
Ожидается: все зелёные, порог покрытия достигнут.

- [ ] **Step 7: Коммит**

```bash
git add worker/workflows.py shared/workflow_ids.py tests/replay/histories/
git commit -m "feat(lifecycle): ready-for-dev запускает MvpDelivery под маркером

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Гейт GROW и фазы приёмки

**Files:**
- Modify: `shared/lifecycle.py`
- Modify: `worker/workflows.py` — обработчик фазы `testing`
- Test: `tests/test_lifecycle.py`, `tests/test_grow_gate.py`

**Interfaces:**
- Consumes: `issue_blocks.GROW` (Task 1), вердикт HowToDemo (существующий агент).
- Produces: переходы `merged → testing` и `testing → released`; активность `publish_grow_candidates(issue, candidates: list[str]) -> None`.

- [ ] **Step 1: Написать падающий тест на непрерывность пути**

Файл `tests/test_grow_gate.py`:

```python
"""Гейт GROW: кандидаты предлагаются, но никого не держат.

Публикация кандидатов — предложение, а не гейт на пути работы. Родительский
Issue закрывается и PR мержится независимо от того, притронулся человек к
списку или нет.
"""

from shared import lifecycle


def test_merged_leads_to_testing():
    assert lifecycle.can(lifecycle.MERGED, lifecycle.TESTING)


def test_testing_leads_to_released():
    assert lifecycle.can(lifecycle.TESTING, lifecycle.RELEASED)


def test_released_is_reachable_from_start():
    assert lifecycle.RELEASED in lifecycle.reachable_from(lifecycle.CREATED)
```

Последний тест — главный: сегодня `released` объявлена и недостижима, то есть
успешного конца пути у контура нет вовсе.

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_grow_gate.py -q --no-cov`
Ожидается: FAIL на `test_released_is_reachable_from_start` — переходы объявлены, но в код не входят.

- [ ] **Step 3: Врезать фазы в цикл**

В `worker/workflows.py`, в `_run_phase_loop`, добавить обработчик фазы `testing`
под маркером `issue-lifecycle-acceptance` (правка решения — маркер обязателен):
запуск приёмки, ожидание вердикта, переход `released` при сходстве и
`in-development` при несовпадении сценария.

- [ ] **Step 4: Написать активность публикации кандидатов**

```python
@activity.defn
async def publish_grow_candidates(issue: IssueInput) -> None:
    """Кандидаты GROW — комментарием после вердикта приёмки.

    Ничего не блокирует: это предложение человеку, а не условие продолжения.
    Issue заводит человек отметкой, и только те, что отметил.
    """
    body = await asyncio.to_thread(github_client.get_issue_body,
                                   issue.repo, issue.issue_number)
    section = issue_blocks.read(body, issue_blocks.GROW)
    if not section:
        return
    await asyncio.to_thread(
        github_client.post_comment, issue.repo, issue.issue_number,
        "MVP принят приёмкой. Накопленное за время работы — ниже.\n\n"
        f"{section}\n\n"
        "Отметьте то, что стоит взять в работу: по отмеченному контур заведёт "
        "задачи. Неотмеченное останется здесь и ничего не задерживает.")
```

- [ ] **Step 5: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_grow_gate.py tests/test_lifecycle.py -q --no-cov`
Ожидается: все проходят.

- [ ] **Step 6: Прогнать корпус историй**

Запуск: `python scripts/replay_histories.py /tmp/corpus`
Ожидается: числа совпадают с базовой линией Task 10, шаг 2.

- [ ] **Step 7: Полный прогон и коммит**

```bash
pytest -q
git add shared/lifecycle.py worker/workflows.py worker/activities.py tests/
git commit -m "feat(gate): фазы приёмки живые, кандидаты GROW ничего не блокируют

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Разбор плана в шаги

**Files:**
- Create: `shared/plan_parse.py`
- Test: `tests/test_plan_parse.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `parse(text: str) -> list[dict]` — список шагов с ключами `title`, `depends_on: list[int]`, `depends_reason: dict[str, str]`. Форма совпадает с той, что принимает `decomposition.needs_subissues` (Task 2).

**Порядок:** делать ДО Task 9 — там эта функция вызывается.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_plan_parse.py`:

```python
"""Разбор плана superpowers в шаги.

Зависимость берётся из блока Interfaces: непустой Consumes — объявленное ребро.
Отдельный вызов модели на декомпозицию не нужен.
"""

from shared import plan_parse

PLAN = """# План

### Task 1: Загрузить версию

**Interfaces:**
- Consumes: ничего.
- Produces: `version` в состоянии сервиса.

### Task 2: Отдать версию

**Interfaces:**
- Consumes: Task 1 — читает `version` из состояния.
- Produces: маршрут GET /version.
"""


def test_titles_are_taken_from_task_headers():
    steps = plan_parse.parse(PLAN)
    assert [s["title"] for s in steps] == ["Загрузить версию", "Отдать версию"]


def test_consumes_nothing_gives_no_edges():
    assert plan_parse.parse(PLAN)[0]["depends_on"] == []


def test_consumes_task_gives_edge_with_reason():
    second = plan_parse.parse(PLAN)[1]
    assert second["depends_on"] == [0]
    assert "version" in second["depends_reason"]["0"]


def test_plan_without_tasks_is_empty():
    assert plan_parse.parse("# План, без задач") == []
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_plan_parse.py -q --no-cov`
Ожидается: FAIL с `ModuleNotFoundError: No module named 'shared.plan_parse'`

- [ ] **Step 3: Написать реализацию**

Файл `shared/plan_parse.py` — докстринг модуля: «Разбор плана superpowers в шаги исполнения. Определение шага взято из инструмента, а не выдумано: задача плана несёт блок Interfaces, и непустой Consumes — объявленная зависимость. Модуль намеренно чистый: ни сети, ни файлов.»

```python
import re

_TASK = re.compile(r"^###\s+Task\s+(\d+)\s*:\s*(.+?)\s*$", re.M)
_CONSUMES = re.compile(r"^-\s*Consumes:\s*(.+?)\s*$", re.M)
_REF = re.compile(r"Task\s+(\d+)", re.I)

_NOTHING = ("ничего", "nothing", "—", "-")


def parse(text: str) -> list[dict]:
    """Шаги плана с объявленными зависимостями."""
    bounds = [(m.start(), m.group(2)) for m in _TASK.finditer(text or "")]
    steps: list[dict] = []
    for position, (start, title) in enumerate(bounds):
        end = bounds[position + 1][0] if position + 1 < len(bounds) else len(text)
        chunk = text[start:end]
        depends_on: list[int] = []
        reason: dict[str, str] = {}
        found = _CONSUMES.search(chunk)
        if found:
            line = found.group(1).strip()
            if line.rstrip(".").lower() not in _NOTHING:
                for ref in _REF.finditer(line):
                    index = int(ref.group(1)) - 1
                    if 0 <= index < len(bounds) and index != position:
                        depends_on.append(index)
                        reason[str(index)] = line
        steps.append({"title": title, "depends_on": depends_on,
                      "depends_reason": reason})
    return steps
```

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_plan_parse.py -q --no-cov`
Ожидается: `4 passed`

- [ ] **Step 5: Коммит**

```bash
git add shared/plan_parse.py tests/test_plan_parse.py
git commit -m "feat(plan): разбор плана superpowers в шаги по Consumes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: Под-задача не поднимает свой цикл

**Files:**
- Modify: `webhook/main.py` — обработчик `issues.opened`
- Modify: `shared/labels.py`
- Test: `tests/test_webhook_subissue_ignored.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `labels.STEP = "harness:step"`; вебхук не поднимает цикл при наличии этой метки.

**Почему это обязательная задача, а не деталь.** Под-задача заводится через `create_issue`, а это порождает событие `issues.opened`, на которое вебхук поднимает полноценный `IssueLifecycle` с триажом. Без этой задачи под-задачи продолжают плодить вечные воркфлоу и вызовы модели — то есть R5 не выполнен, и остальная работа теряет смысл.

**Порядок:** делать ДО того, как Task 9 попадёт на стенд.

- [ ] **Step 1: Написать падающий тест**

Файл `tests/test_webhook_subissue_ignored.py`:

```python
"""Под-задача шага не поднимает свой жизненный цикл.

Она живёт часы, закрывается вместе со своим шагом, и триаж ей не нужен: задачу
уже разобрал план родителя. Каждый лишний цикл — вечный воркфлоу и вызов модели
на приоритет.
"""

import hashlib
import hmac
import json

SECRET = "s3cret"


def _payload(label_names):
    return {
        "action": "opened",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 152, "title": "Шаг 2", "body": "тело",
                  "user": {"login": "bot", "type": "Bot"},
                  "labels": [{"name": name} for name in label_names]},
    }


def _post(client, payload):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body,
                       headers={"X-GitHub-Event": "issues",
                                "X-Hub-Signature-256": sig,
                                "Content-Type": "application/json"})


def test_step_subissue_starts_nothing(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "*")

    import main
    from fastapi.testclient import TestClient

    started = []

    class FakeClient:
        async def start_workflow(self, workflow, arg, **kwargs):
            started.append(workflow)

        def get_workflow_handle(self, wf_id):
            raise AssertionError("под-задача не должна ничего сигналить")

    async def _get_client():
        return FakeClient()

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    client = TestClient(main.app)

    assert _post(client, _payload(["harness:step"])).status_code == 200
    assert started == [], "под-задача подняла цикл"

    assert _post(client, _payload([])).status_code == 200
    assert started, "обычный Issue перестал подниматься"
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Запуск: `pytest tests/test_webhook_subissue_ignored.py -q --no-cov`
Ожидается: FAIL с `AssertionError: под-задача подняла цикл`

- [ ] **Step 3: Написать реализацию**

В `shared/labels.py`:

```python
STEP = "harness:step"
"""Метка под-задачи шага. Такой Issue не поднимает свой жизненный цикл: он
живёт время шага и закрывается вместе с ним."""
```

В `webhook/main.py`, в ветке `issues.opened`, ДО любого обращения к Temporal:

```python
        if labels.has(names, labels.STEP):
            _log.info("под-задача шага %s#%s — цикл не поднимаем", repo, issue_number)
            return {"ok": True}
```

В `worker/activities.py`, в активности `mvp_open_substep`, заводить задачу с этой меткой: `labels=[labels.ORIGIN_AGENT, labels.STEP]`.

- [ ] **Step 4: Прогнать и убедиться, что проходит**

Запуск: `pytest tests/test_webhook_subissue_ignored.py -q --no-cov`
Ожидается: `1 passed`

- [ ] **Step 5: Полный прогон и коммит**

```bash
pytest -q
git add shared/labels.py webhook/main.py worker/activities.py tests/test_webhook_subissue_ignored.py
git commit -m "feat(webhook): под-задача шага не поднимает жизненный цикл

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Метрики (R10)

Снять до внедрения и после первого живого прогона на демо-репозитории:

```bash
gh issue list --repo po-helper-org/poh-demo-checkout --state open --limit 300 --json number --jq 'length'
gh issue list --repo po-helper-org/poh-demo-checkout --state open --limit 300 --search "is:open -is:sub-issue" --json number --jq 'length'
ssh poh-stand "docker exec compose-connect-redundant-system-mzso3q-temporal-1 \
  temporal workflow list --address=compose-connect-redundant-system-mzso3q-temporal-1:7233 --limit 300 \
  | grep -c IssueLifecycle"
```

| Показатель | До | После |
|---|---|---|
| Открытых Issue в демо-репозитории | 87 | |
| Из них заведено контуром | 71 | |
| Живых `IssueLifecycle` | 124 | |
| Issue на одну фичу (случай #151) | 10 | |

## Что этот план НЕ делает

- **Не выбирает исполнителя.** OpenHands остаётся; сравнение с Claude Code и удаление проигравшей ветки — План 2.
- **Не трогает 267 открытых Issue.** Решение принято: оставить как есть.
- **Не обосновывает потолок 6.** Для этого нужен признак размера в эпизоде и накопленные данные.
- **Не заводит гейт принятия плана человеком.** Открытый вопрос спеки, решается тиром автономии.
