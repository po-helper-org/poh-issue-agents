# Закалка контура под второго провайдера — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить `poh-issue-agents` к появлению второго трекера, не меняя наблюдаемого поведения на GitHub.

**Architecture:** Этап 1 из [дизайна](../specs/2026-08-21-gitlab-support-design.md) ([#109](https://github.com/po-helper-org/poh-issue-agents/issues/109)). Ничего не выносится в пакет и не пишется под GitLab — работа целиком внутри репозитория. Сначала транспорт закрывается характеризующими тестами, затем правится то, что на втором провайдере ломается молча: разбор ссылки на репозиторий, allowlist, операции с метками, устойчивость вебхука к собственным ошибкам разбора.

**Tech Stack:** Python 3.11, FastAPI, Temporal SDK, `requests`, pytest (`asyncio_mode=auto`, покрытие считается каждым прогоном).

## Global Constraints

- **Поведение на GitHub не меняется.** Любая правка, меняющая наблюдаемый результат на GitHub, — ошибка, а не улучшение. Исключение оговорено явно в Задаче 5.
- **Тесты запускаются `.venv/bin/pytest -q`** (цель `make test`). Покрытие считается на каждом прогоне, порог — в `.coveragerc`.
- **Импорты в тестах плоские**: `tests/conftest.py` кладёт `worker/` и корень в `sys.path`, поэтому `import github_client`, а не `from worker import github_client`.
- **Модуль `github_client` перезагружается в тестах** через `importlib.reload` после установки переменных окружения — константы уровня модуля (`DRY_RUN`) читаются при импорте.
- **Ветка одна на весь план**, PR в `main`. Прямой пуш в `main` запрещён.
- **`shared/*` остаются чистыми**: ни сети, ни Temporal, ни обращений к трекеру. Это зафиксировано в docstring каждого модуля и проверяется тестом `tests/test_repowise_client.py:102`.
- **Провайдер в этом этапе один — GitHub.** Строки `"gitlab"` появляются только там, где это прямо предписано задачей.

---

### Задача 1: Характеризующие тесты на транспорт

Страховка для всех последующих задач. Сейчас строка `api.github.com` встречается во всём наборе из 814 тестов **три раза** — то есть URL-контракт не зафиксирован, и любой рефакторинг клиента пройдёт зелёным даже при поехавших путях.

**Files:**
- Create: `tests/test_github_client_contract.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: ничего.
- Produces: фикстура `forge_env` (autouse, изолирует переменные окружения трекера) и хелпер `capture` из `tests/test_github_client_contract.py` — задачи 4, 5, 6 дописывают в этот же файл.

- [ ] **Step 1: Написать autouse-фикстуру изоляции окружения**

Сейчас `GITHUB_WEBHOOK_SECRET` настраивается в 12 файлах, `ISSUE_AGENT_REPOS` — в 17, а чистка есть только в двух. Тест, забывший подчистить за собой, влияет на соседей через порядок запуска.

Дописать в конец `tests/conftest.py`:

```python
_FORGE_ENV = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY_B64",
    "GITHUB_PRIVATE_KEY_PATH", "GITHUB_INSTALLATION_ID", "GITHUB_REPOSITORY",
    "GITHUB_WEBHOOK_SECRET", "GH_PUSH_TOKEN", "GH_CLONE_TOKEN",
    "ISSUE_AGENT_REPOS", "DRY_RUN",
)


@pytest.fixture(autouse=True)
def forge_env(monkeypatch):
    """Переменные трекера не протекают между тестами.

    Раньше их ставили по месту в 17 файлах и почти нигде не убирали: тест,
    прошедший в одиночку, мог упасть в общем прогоне из-за порядка запуска.
    Фикстура снимает весь набор до теста; тест ставит только то, что ему нужно.
    """
    for name in _FORGE_ENV:
        monkeypatch.delenv(name, raising=False)
```

- [ ] **Step 2: Запустить весь набор — убедиться, что фикстура ничего не сломала**

Run: `.venv/bin/pytest -q`
Expected: PASS. Если что-то упало — тест полагался на протёкшую переменную; поставить её явно внутри самого теста, а фикстуру не ослаблять.

- [ ] **Step 3: Написать характеризующие тесты**

Создать `tests/test_github_client_contract.py`:

```python
"""Контракт транспорта: метод, путь и тело каждого вызова к трекеру.

Эти тесты не проверяют логику — они фиксируют форму HTTP-запроса. Смысл
появляется при втором провайдере: без них рефакторинг клиента проходит
зелёным даже когда пути поехали, потому что 31 тест из 33 подменяют модуль
целиком, а не HTTP.

Проверяется ровно то, что нельзя изменить, не сломав интеграцию: метод,
полный URL и полезная нагрузка.
"""

import importlib

import pytest


def _fresh(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "tok")
    import github_client
    return importlib.reload(github_client)


class _Resp:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    @property
    def ok(self):
        return True


@pytest.fixture
def capture(monkeypatch):
    """Перехватывает вызовы requests и возвращает список (метод, url, kwargs)."""
    gc = _fresh(monkeypatch)
    calls = []

    def record(method, payload=None):
        def fake(url, **kwargs):
            calls.append((method, url, kwargs))
            return _Resp(payload)
        return fake

    monkeypatch.setattr(gc.requests, "post", record("POST", {"number": 42}))
    monkeypatch.setattr(gc.requests, "get", record("GET", {"default_branch": "main"}))
    monkeypatch.setattr(gc.requests, "patch", record("PATCH"))
    monkeypatch.setattr(gc.requests, "delete", record("DELETE"))
    monkeypatch.setattr(gc.requests, "put", record("PUT"))
    return gc, calls


B = "https://api.github.com"


def test_post_comment_contract(capture):
    gc, calls = capture
    gc.post_comment("o/r", 7, "текст")
    method, url, kwargs = calls[0]
    assert (method, url) == ("POST", f"{B}/repos/o/r/issues/7/comments")
    assert kwargs["json"]["body"].startswith("текст")
    assert "<!-- issue-agent -->" in kwargs["json"]["body"]


def test_add_label_contract(capture):
    gc, calls = capture
    gc.add_label("o/r", 7, "phase:classified")
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues/7/labels")
    assert calls[0][2]["json"] == {"labels": ["phase:classified"]}


def test_remove_label_contract(capture):
    gc, calls = capture
    gc.remove_label("o/r", 7, "run:analyze")
    assert calls[0][:2] == ("DELETE", f"{B}/repos/o/r/issues/7/labels/run%3Aanalyze")


def test_create_issue_contract(capture):
    gc, calls = capture
    number = gc.create_issue("o/r", "заголовок", "тело", ["origin:agent"])
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues")
    assert calls[0][2]["json"] == {
        "title": "заголовок", "body": "тело", "labels": ["origin:agent"]}
    assert number == 42


def test_close_issue_contract(capture):
    gc, calls = capture
    gc.close_issue("o/r", 7)
    assert calls[0][:2] == ("PATCH", f"{B}/repos/o/r/issues/7")
    assert calls[0][2]["json"] == {"state": "closed"}


def test_branch_exists_contract(capture):
    gc, calls = capture
    gc.branch_exists("o/r", "research/issue-7")
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/branches/research/issue-7")


def test_get_issue_contract(capture):
    gc, calls = capture
    gc.get_issue("o/r", 7)
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/issues/7")


def test_list_comments_contract(capture):
    gc, calls = capture
    gc.list_comments("o/r", 7)
    assert calls[0][:2] == ("GET", f"{B}/repos/o/r/issues/7/comments")
    assert calls[0][2]["params"]["per_page"]


def test_add_reaction_contract(capture):
    gc, calls = capture
    gc.add_reaction("o/r", 99)
    assert calls[0][:2] == ("POST", f"{B}/repos/o/r/issues/comments/99/reactions")
    assert calls[0][2]["json"] == {"content": "eyes"}


def test_pat_beats_app_in_auth_header(capture):
    gc, _ = capture
    headers = gc._auth_headers("o/r")
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Accept"] == "application/vnd.github+json"
```

- [ ] **Step 4: Запустить — тесты должны пройти на текущем коде**

Run: `.venv/bin/pytest tests/test_github_client_contract.py -q`
Expected: PASS, 11 тестов.

Это характеризующие тесты: они описывают то, что уже есть. Красный тест здесь означает, что я неверно прочитал код, а не что код плох — сверить с `worker/github_client.py` и поправить **тест**, не клиент.

- [ ] **Step 5: Коммит**

```bash
git add tests/conftest.py tests/test_github_client_contract.py
git commit -m "test: контракт транспорта закрыт характеризующими тестами (#109)"
```

---

### Задача 2: `RepoRef` — доменная ссылка на репозиторий

**Files:**
- Create: `shared/repo_ref.py`
- Test: `tests/test_repo_ref.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `RepoRef` с полями `provider: str`, `path: str`, `project_id: int | None`; classmethod `parse(raw: str, provider: str = "github", project_id: int | None = None) -> RepoRef`; свойства `api_segment: str`, `owner: str`, `name: str`, `segments: tuple[str, ...]`; `__str__` возвращает `path`. Задача 3 использует `segments`.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_repo_ref.py`:

```python
"""Разбор ссылки на репозиторий, переживающий вложенные подгруппы."""

import pytest

from shared.repo_ref import RepoRef


def test_github_two_segments():
    ref = RepoRef.parse("po-helper-org/poh-demo-checkout")
    assert ref.provider == "github"
    assert ref.owner == "po-helper-org"
    assert ref.name == "poh-demo-checkout"
    assert str(ref) == "po-helper-org/poh-demo-checkout"


def test_github_api_segment_is_path_as_is():
    """У GitHub путь — валидный сегмент URL, кодировать нечего."""
    ref = RepoRef.parse("po-helper-org/poh-demo-checkout")
    assert ref.api_segment == "po-helper-org/poh-demo-checkout"


def test_gitlab_nested_subgroups_are_kept():
    ref = RepoRef.parse("group/sub1/sub2/project", provider="gitlab")
    assert ref.owner == "group"
    assert ref.name == "project"
    assert ref.segments == ("group", "sub1", "sub2", "project")


def test_gitlab_api_segment_is_url_encoded():
    """GitLab адресует проект либо числовым id, либо путём с %2F."""
    ref = RepoRef.parse("group/sub/project", provider="gitlab")
    assert ref.api_segment == "group%2Fsub%2Fproject"


def test_gitlab_numeric_id_wins_over_path():
    ref = RepoRef.parse("group/sub/project", provider="gitlab", project_id=85622870)
    assert ref.api_segment == "85622870"


def test_surrounding_slashes_and_spaces_are_stripped():
    assert RepoRef.parse("  /owner/repo/  ").path == "owner/repo"


def test_single_segment_is_rejected():
    with pytest.raises(ValueError, match="как минимум два сегмента"):
        RepoRef.parse("owner")


def test_empty_is_rejected():
    with pytest.raises(ValueError):
        RepoRef.parse("   ")


def test_is_hashable_and_comparable():
    """Ссылка ходит ключом словаря в кэше токенов."""
    a = RepoRef.parse("o/r")
    b = RepoRef.parse("o/r")
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_repo_ref.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.repo_ref'`

- [ ] **Step 3: Написать реализацию**

Создать `shared/repo_ref.py`:

```python
"""Ссылка на репозиторий, не привязанная к форме `owner/repo`.

GitHub адресует репозиторий ровно двумя сегментами. GitLab — путём из двух и
более (подгруппы вкладываются до 20 уровней) либо числовым id проекта, причём
путь в URL API обязан быть закодирован целиком: `group%2Fsub%2Fproject`.

Кодирование живёт здесь, а не в вызывающем коде. Иначе повторяется то, что
уже случилось в `worker/github_client.py`: имя метки там кодируется, имя файла
воркфлоу кодируется, а путь репозитория — ни в одном из 26 URL.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

GITHUB = "github"
GITLAB = "gitlab"


@dataclass(frozen=True)
class RepoRef:
    """Репозиторий у конкретного провайдера.

    `path` — человекочитаемая форма (`owner/repo`, `group/sub/project`), она же
    ключ allowlist и то, что видно в логах. `project_id` — числовой
    идентификатор GitLab; если он известен, обращаться по нему дешевле и
    надёжнее, чем по пути, который может смениться при переносе проекта.
    """

    provider: str
    path: str
    project_id: int | None = None

    @classmethod
    def parse(cls, raw: str, provider: str = GITHUB,
              project_id: int | None = None) -> "RepoRef":
        path = (raw or "").strip().strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) < 2:
            raise ValueError(
                f"ссылка на репозиторий требует как минимум два сегмента: {raw!r}")
        return cls(provider=provider, path="/".join(segments), project_id=project_id)

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.path.split("/"))

    @property
    def owner(self) -> str:
        """Верхнеуровневый владелец: организация GitHub или корневая группа."""
        return self.segments[0]

    @property
    def name(self) -> str:
        return self.segments[-1]

    @property
    def api_segment(self) -> str:
        """Готовая подстановка в путь REST API."""
        if self.provider == GITLAB:
            if self.project_id is not None:
                return str(self.project_id)
            return urllib.parse.quote(self.path, safe="")
        return self.path

    def __str__(self) -> str:
        return self.path
```

- [ ] **Step 4: Запустить — тесты проходят**

Run: `.venv/bin/pytest tests/test_repo_ref.py -q`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Коммит**

```bash
git add shared/repo_ref.py tests/test_repo_ref.py
git commit -m "feat(shared): RepoRef переживает вложенные подгруппы (#109)"
```

---

### Задача 3: Allowlist на многосегментных путях

`shared/repos.py:55` берёт `repo.split("/", 1)[0]` и сравнивает с маской. Проверено прогоном: `group/subgroup/*` даёт `False`, точное `group/subgroup/project` тоже даёт `False` — событие молча отбрасывается до Temporal, а в логе это неотличимо от осознанного отказа.

**Files:**
- Modify: `shared/repos.py:18-56`
- Test: `tests/test_repos_allowlist.py` (создать)

**Interfaces:**
- Consumes: ничего (модуль остаётся строковым, `RepoRef` сюда не тянем — allowlist читает сырую строку из payload).
- Produces: `is_allowed(repo: str, specs: list[str]) -> bool` с прежней сигнатурой и расширенной семантикой масок.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_repos_allowlist.py`:

```python
"""Допуск репозитория, включая пути глубже двух сегментов."""

from shared.repos import is_allowed, parse_repo_specs


def test_exact_two_segment_match():
    assert is_allowed("po-helper-org/poh-demo-checkout",
                      ["po-helper-org/poh-demo-checkout"])


def test_exact_match_is_case_insensitive():
    assert is_allowed("PO-Helper-Org/Poh-Demo", ["po-helper-org/poh-demo"])


def test_owner_mask_matches_direct_child():
    assert is_allowed("po-helper-org/anything", ["po-helper-org/*"])


def test_bare_owner_is_the_same_as_mask():
    assert is_allowed("po-helper-org/anything", ["po-helper-org"])


def test_star_allows_everything():
    assert is_allowed("whoever/whatever", ["*"])


def test_empty_specs_allow_everything():
    assert is_allowed("whoever/whatever", [])
    assert is_allowed("whoever/whatever", [""])


def test_foreign_repo_is_rejected():
    assert not is_allowed("someone-else/repo", ["po-helper-org/*"])


# --- то, что ломалось до правки ---

def test_exact_three_segment_match():
    """Проект GitLab в подгруппе, записанный точно."""
    assert is_allowed("group/sub/project", ["group/sub/project"])


def test_subgroup_mask_matches_project_inside_it():
    assert is_allowed("group/sub/project", ["group/sub/*"])


def test_owner_mask_reaches_into_subgroups():
    """`group/*` покрывает и вложенные подгруппы — это осознанно."""
    assert is_allowed("group/sub/project", ["group/*"])


def test_subgroup_mask_does_not_match_sibling_subgroup():
    assert not is_allowed("group/other/project", ["group/sub/*"])


def test_mask_matches_on_segment_boundary_only():
    """`group/sub` не должна цеплять `group/subterfuge`."""
    assert not is_allowed("group/subterfuge/project", ["group/sub/*"])


def test_parse_splits_multi_segment_masks():
    concrete, masks = parse_repo_specs(["group/sub/*", "group/sub/project", "owner"])
    assert concrete == ["group/sub/project"]
    assert masks == ["group/sub", "owner"]
```

- [ ] **Step 2: Запустить — убедиться, что падают ровно четыре**

Run: `.venv/bin/pytest tests/test_repos_allowlist.py -q`
Expected: FAIL — `test_exact_three_segment_match`, `test_subgroup_mask_matches_project_inside_it`, `test_owner_mask_reaches_into_subgroups`, `test_mask_matches_on_segment_boundary_only`. Остальные проходят: это защита от регресса.

Если `test_exact_three_segment_match` неожиданно прошёл — перечитать `parse_repo_specs`, ветка `else` кладёт спеку в `concrete` независимо от числа сегментов, и тогда падений будет три.

- [ ] **Step 3: Переписать `is_allowed`**

Заменить `shared/repos.py:41-56` на:

```python
def is_allowed(repo: str, specs: list[str]) -> bool:
    """True, если репозиторий входит в allowlist.

    Пустой список или `*` → разрешено всё. Иначе — точное совпадение пути
    (регистронезависимо) либо маска-префикс.

    Маска сопоставляется **по границе сегмента**: `group/sub` покрывает
    `group/sub/project`, но не `group/subterfuge/project`. Маска верхнего
    уровня (`owner/*` или голый `owner`) достаёт и до вложенных подгрупп —
    так у одной записи остаётся один смысл «всё, что принадлежит владельцу»
    на обоих провайдерах.

    До этой правки сравнивался только первый сегмент пути, поэтому проект
    GitLab в подгруппе не проходил ни точной записью, ни маской своей
    подгруппы: событие молча отбрасывалось до Temporal.
    """
    concrete, mask_owners = parse_repo_specs(specs)
    if not concrete and not mask_owners:
        return True  # пусто → любой установленный
    if "*" in mask_owners:
        return True
    repo_l = repo.strip().strip("/").lower()
    if repo_l in {c.strip().strip("/").lower() for c in concrete}:
        return True
    for mask in mask_owners:
        mask_l = mask.strip().strip("/").lower()
        if not mask_l:
            continue
        if repo_l == mask_l or repo_l.startswith(mask_l + "/"):
            return True
    return False
```

- [ ] **Step 4: Обновить docstring модуля**

Заменить блок форматов в `shared/repos.py:6-11` на:

```
Форматы записи (comma-separated в ISSUE_AGENT_REPOS):
  owner/repo        — конкретный репозиторий
  group/sub/project — конкретный проект во вложенной подгруппе
  owner/*           — всё, что принадлежит owner, включая подгруппы
  group/sub/*       — всё внутри этой подгруппы
  owner             — голый owner: то же, что owner/*
  *                 — любой репозиторий (все установки App)
  (пусто)           — то же, что * — любой установленный
```

- [ ] **Step 5: Запустить — все проходят**

Run: `.venv/bin/pytest tests/test_repos_allowlist.py -q`
Expected: PASS, 13 тестов.

- [ ] **Step 6: Прогнать весь набор — allowlist трогают 17 файлов**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add shared/repos.py tests/test_repos_allowlist.py
git commit -m "fix(repos): allowlist перестал молча ронять пути глубже двух сегментов (#109)"
```

---

### Задача 4: `set_labels` — метки одной операцией

**Files:**
- Modify: `worker/github_client.py` (добавить `set_labels` после `remove_label`)
- Modify: `worker/activities.py:199-223` (`set_phase`), `:226-246` (`mark_awaiting`), `:497-511` (`finish_command_labels`)
- Test: `tests/test_github_client_contract.py` (дописать), `tests/test_set_labels.py` (создать)

**Interfaces:**
- Consumes: ничего.
- Produces: `github_client.set_labels(repo: str, issue_number: int, *, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None`. Задачи 5 и 6 её не трогают.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_set_labels.py`:

```python
"""Метки одной операцией: порядок вызовов, терпимость к 404, DRY_RUN."""

import importlib


def _fresh(monkeypatch, dry=False):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    import github_client
    return importlib.reload(github_client)


class _Resp:
    def __init__(self, code=200):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


def test_add_goes_before_remove(monkeypatch):
    """Целевая метка ставится раньше снятия соседних.

    Иначе есть окно, в котором меток `phase:*` нет вовсе, и
    `lifecycle.phase_from_labels` возвращает None — Issue выглядит как никогда
    не входивший в жизненный цикл. Две метки в том же окне хотя бы видны.
    """
    gc = _fresh(monkeypatch)
    order = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda url, **kw: order.append("add") or _Resp())
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: order.append("remove") or _Resp())

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])
    assert order == ["add", "remove"]


def test_add_is_a_single_request(monkeypatch):
    """Несколько меток уезжают одним POST, а не по одной."""
    gc = _fresh(monkeypatch)
    posts = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda url, **kw: posts.append(kw["json"]) or _Resp())
    monkeypatch.setattr(gc.requests, "delete", lambda url, **kw: _Resp())

    gc.set_labels("o/r", 7, add=["a", "b", "c"])
    assert posts == [{"labels": ["a", "b", "c"]}]


def test_failed_removal_is_logged_not_raised(monkeypatch):
    """Снятие метки — best-effort, как было в set_phase."""
    gc = _fresh(monkeypatch)
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp())
    monkeypatch.setattr(gc.requests, "delete", lambda url, **kw: _Resp(500))

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:classified"])


def test_failed_add_still_raises(monkeypatch):
    """Непоставленная метка — потерянное состояние, это ошибка."""
    gc = _fresh(monkeypatch)
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp(500))
    monkeypatch.setattr(gc.requests, "delete", lambda url, **kw: _Resp())

    try:
        gc.set_labels("o/r", 7, add=["phase:groomed"])
    except RuntimeError:
        return
    raise AssertionError("ошибка постановки метки должна подниматься")


def test_label_being_added_is_never_removed(monkeypatch):
    """Защита от вызова, где имя есть и в add, и в remove."""
    gc = _fresh(monkeypatch)
    removed = []
    monkeypatch.setattr(gc.requests, "post", lambda url, **kw: _Resp())
    monkeypatch.setattr(gc.requests, "delete",
                        lambda url, **kw: removed.append(url) or _Resp())

    gc.set_labels("o/r", 7, add=["phase:groomed"], remove=["phase:groomed", "x"])
    assert len(removed) == 1 and removed[0].endswith("/labels/x")


def test_nothing_to_do_makes_no_requests(monkeypatch):
    gc = _fresh(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("HTTP на пустом наборе меток")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "delete", boom)
    gc.set_labels("o/r", 7)


def test_dry_run_makes_no_requests(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP под DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "delete", boom)
    gc.set_labels("o/r", 7, add=["a"], remove=["b"])
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_set_labels.py -q`
Expected: FAIL с `AttributeError: module 'github_client' has no attribute 'set_labels'`

- [ ] **Step 3: Реализовать `set_labels`**

Добавить в `worker/github_client.py` сразу после `remove_label`:

```python
def set_labels(repo: str, issue_number: int, *,
               add: "Sequence[str]" = (), remove: "Sequence[str]" = ()) -> None:
    """Приводит набор меток к нужному виду одной операцией.

    Порядок намеренный: сначала ставим целевые, потом снимаем лишние. При
    обратном порядке между двумя запросами есть окно, в котором меток `phase:*`
    нет вовсе — `lifecycle.phase_from_labels` вернёт None, и Issue будет
    выглядеть как не входивший в жизненный цикл. Две метки в том же окне
    противоречивы, но видны и восстановимы.

    Постановка и снятие различаются по строгости, и это не случайность.
    Непоставленная метка — потерянное состояние, поэтому ошибка поднимается.
    Неснятая — мусор в выборке, из-за которого не стоит ронять прогон; она
    уходит в лог, как это делал `set_phase`.

    У второго провайдера операция схлопывается в один запрос: GitLab
    обновляет метки одним `PUT` с `add_labels` / `remove_labels`. Здесь она
    описана одним местом ровно для того, чтобы драйверу было что реализовать.
    """
    add = [label for label in add if label]
    keep = set(add)
    remove = [label for label in remove if label and label not in keep]
    if not add and not remove:
        return
    if _dry_run():
        _log.info("[DRY_RUN] labels %s#%s += %s -= %s", repo, issue_number, add, remove)
        return
    if add:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
        resp = requests.post(url, headers=_auth_headers(repo),
                             json={"labels": add}, timeout=30)
        resp.raise_for_status()
    for label in remove:
        try:
            remove_label(repo, issue_number, label)
        except Exception as exc:
            _log.warning("не снял метку %s с %s#%s: %s", label, repo, issue_number, exc)
```

Добавить импорт в шапку `worker/github_client.py`, если его там нет:

```python
from collections.abc import Sequence
```

- [ ] **Step 4: Запустить — тесты проходят**

Run: `.venv/bin/pytest tests/test_set_labels.py -q`
Expected: PASS, 7 тестов.

- [ ] **Step 5: Переписать `set_phase` на `set_labels`**

Заменить тело цикла в `worker/activities.py:216-223` (всё от `for stale in stale_labels:` до конца функции) на:

```python
    github_client.set_labels(repo, issue_number, add=[target], remove=stale_labels)
```

Докстринг `set_phase` дополнить абзацем перед закрывающими кавычками:

```
    Целевая метка ставится раньше снятия прежних: окно, в котором меток
    `phase:*` нет вовсе, хуже окна, в котором их две. Атомарно это делается
    только на провайдере, умеющем менять набор одним запросом.
```

- [ ] **Step 6: Переписать `finish_command_labels`**

`finish_command_labels` — **корутина**, и она best-effort по **обеим** операциям, а не только по снятию: она зовётся из терминальных веток воркфлоу, где провал косметики не должен превращать состоявшийся прогон в проваленный. `set_labels` поднимает ошибку постановки, поэтому терпимость остаётся на месте вызова.

Заменить в `worker/activities.py` блок от `for stale in (*running_labels(command), previous):` до конца функции на:

```python
    try:
        await asyncio.to_thread(
            github_client.set_labels, repo, issue_number,
            add=[outcome], remove=[*running_labels(command), previous])
    except Exception as exc:
        logger.warning("не привёл метки команды на %s#%s к виду %s: %s",
                       repo, issue_number, outcome, exc)
```

Имена `outcome`, `previous` и вызов `running_labels(command)` уже есть в функции выше — не переименовывать.

- [ ] **Step 7: Переписать `mark_awaiting`**

Это обычная функция, не корутина. Заменить в `worker/activities.py` блок от `if waiting is not None and waiting.blocks_on_human:` до конца функции на:

```python
    if waiting is not None and waiting.blocks_on_human:
        github_client.set_labels(repo, issue_number, add=[labels.NEEDS_HUMAN_TRIAGE])
        return
    github_client.set_labels(repo, issue_number, remove=[labels.NEEDS_HUMAN_TRIAGE])
```

Нормализацию `waiting` из словаря двумя строками выше **не трогать** — она приезжает из Temporal сериализованной.

Прежний `try/except` вокруг снятия убрать: терпимость к сбою снятия теперь внутри `set_labels`.

- [ ] **Step 8: Прогнать тесты жизненного цикла**

Run: `.venv/bin/pytest tests/test_lifecycle_phases.py tests/test_command_label_activities.py tests/test_ready_for_dev.py -q`
Expected: PASS.

Тесты подменяют `github_client` целиком (`tests/test_lifecycle_phases.py:191` — класс `_GH`), поэтому у фейка появится необъявленный метод. Дописать `set_labels` в фейк, сохранив прежние проверки: он должен складывать `add` и `remove` в те же структуры, которые тест уже читает.

- [ ] **Step 9: Прогнать весь набор**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 10: Коммит**

```bash
git add worker/github_client.py worker/activities.py tests/test_set_labels.py tests/test_lifecycle_phases.py
git commit -m "refactor(labels): смена набора меток стала одной операцией (#109)"
```

---

### Задача 5: Каталог меток и `ensure_labels_exist`

Bootstrap меток в репозитории отсутствует: grep по `label create` и `POST .../labels` даёт ноль. Система полагается на то, что трекер заведёт метку сам. Проверено на GitLab 2026-08-21 — заводит, как и GitHub. Значит проблема не в отказе, а в тишине: опечатка в имени оседает мусорной меткой вместо ошибки, и метка приезжает без цвета.

**Это единственная задача плана, меняющая наблюдаемое поведение на GitHub:** у меток появляются цвета и описания. Изменение косметическое и намеренное.

**Files:**
- Create: `shared/label_catalog.py`, `scripts/bootstrap_labels.py`
- Modify: `worker/github_client.py` (добавить `ensure_labels_exist`)
- Test: `tests/test_label_catalog.py`

**Interfaces:**
- Consumes: `lifecycle.PHASES`, `lifecycle.phase_label`, `shared/labels.py`, `commands._COMMANDS`, `commands.RUN_PREFIX/DONE_PREFIX/FAILED_PREFIX`, `pr_closing.NEEDS_HUMAN_PR`, `develop.IN_DEVELOPMENT_LABEL`.
- Produces: `label_catalog.catalog() -> dict[str, LabelSpec]`, где `LabelSpec` — `dataclass(name: str, color: str, description: str)`; `github_client.ensure_labels_exist(repo: str, specs: Iterable[LabelSpec]) -> int` (возвращает число созданных).

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_label_catalog.py`:

```python
"""Каталог меток собирается из кода, а не переписывается руками."""

from shared import commands, develop, lifecycle, pr_closing
from shared import labels as L
from shared.label_catalog import catalog


def test_every_phase_is_present():
    names = catalog()
    for phase in lifecycle.PHASES:
        assert lifecycle.phase_label(phase) in names


def test_command_labels_cover_all_three_outcomes():
    names = catalog()
    for command in commands._COMMANDS.values():
        assert f"{commands.RUN_PREFIX}{command}" in names
        assert f"{commands.DONE_PREFIX}{command}" in names
        assert f"{commands.FAILED_PREFIX}{command}" in names


def test_control_labels_are_present():
    names = catalog()
    for label in (L.NEEDS_HUMAN_TRIAGE, L.ORIGIN_AGENT, L.AGENTS_OFF,
                  L.READY_FOR_DEV, pr_closing.NEEDS_HUMAN_PR,
                  develop.IN_DEVELOPMENT_LABEL):
        assert label in names


def test_trigger_labels_are_present():
    names = catalog()
    assert {"research-me", "bug-me", "build-me"} <= set(names)


def test_every_entry_has_colour_and_description():
    for name, spec in catalog().items():
        assert spec.color.startswith("#"), name
        assert spec.description.strip(), name


def test_catalog_grows_with_lifecycle():
    """Новая фаза попадает в каталог сама — иначе он разъедется с контуром."""
    assert len([n for n in catalog() if n.startswith(lifecycle.PHASE_PREFIX)]) \
        == len(lifecycle.PHASES)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_label_catalog.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'shared.label_catalog'`

- [ ] **Step 3: Написать каталог**

Создать `shared/label_catalog.py`:

```python
"""Каталог меток контура: имя, цвет, описание.

Собирается из тех же констант, что и рабочий код. Переписанный руками список
разъезжается с контуром на первой же новой фазе — и разъезд этот тихий: метка
всё равно заведётся при первом применении, просто серой и без описания.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import commands, develop, lifecycle, pr_closing
from . import labels as L

PHASE_COLOR = "#1F75CB"
ADVISOR_COLOR = "#6E49CB"
PRIORITY_COLOR = "#ED9121"
RUNNING_COLOR = "#FC9403"
DONE_COLOR = "#108548"
FAILED_COLOR = "#DD2B0E"
HUMAN_COLOR = "#E24329"
TRIGGER_COLOR = "#2DA160"
NEUTRAL_COLOR = "#666666"

ADVISOR_KINDS = ("answered", "bug", "consultation", "error",
                 "existing-functionality", "feature-request")
PRIORITY_LEVELS = ("P0", "P1", "P2", "P3")
TRIGGERS = {"research-me": "аналитика", "bug-me": "багфикс",
            "build-me": "разработка"}
FLAT = {
    "bot-authored": "Issue заведён ботом",
    "security-sensitive": "Затрагивает безопасность",
    "needs-clarification": "Нужны уточнения от автора",
    "spam": "Отброшен как спам",
    "duplicate": "Дубликат",
    "possible-duplicate": "Возможный дубликат",
    "estimated": "Оценка трудоёмкости опубликована",
}


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str


def catalog() -> dict[str, LabelSpec]:
    """Все метки, которыми оперирует контур."""
    out: dict[str, LabelSpec] = {}

    def add(name: str, color: str, description: str) -> None:
        out[name] = LabelSpec(name=name, color=color, description=description)

    for phase in lifecycle.PHASES:
        add(lifecycle.phase_label(phase), PHASE_COLOR, "Фаза жизненного цикла Issue")
    for kind in ADVISOR_KINDS:
        add(f"advisor:{kind}", ADVISOR_COLOR, "Классификация обращения")
    for level in PRIORITY_LEVELS:
        add(f"priority:{level}", PRIORITY_COLOR, "Расчётный приоритет")
    for command in commands._COMMANDS.values():
        add(f"{commands.RUN_PREFIX}{command}", RUNNING_COLOR,
            f"Команда /{command} выполняется")
        add(f"{commands.DONE_PREFIX}{command}", DONE_COLOR,
            f"Команда /{command} завершена")
        add(f"{commands.FAILED_PREFIX}{command}", FAILED_COLOR,
            f"Команда /{command} сорвалась")
    for legacy in commands._LEGACY_RUNNING_LABELS.get("analyze", ()):
        add(legacy, RUNNING_COLOR, "Legacy-метка выполнения /analyze")

    add(L.NEEDS_HUMAN_TRIAGE, HUMAN_COLOR, "Ход за человеком")
    add(pr_closing.NEEDS_HUMAN_PR, HUMAN_COLOR, "Круг правок PR требует человека")
    add(L.ORIGIN_AGENT, NEUTRAL_COLOR, "Issue или PR заведён агентом")
    add(L.AGENTS_OFF, "#333333", "Контур не трогает этот Issue")
    add(L.READY_FOR_DEV, DONE_COLOR, "Готово к разработке")
    add(develop.IN_DEVELOPMENT_LABEL, RUNNING_COLOR, "У агента разработки")

    for trigger, what in TRIGGERS.items():
        add(trigger, TRIGGER_COLOR, f"Триггер человека: запустить {what}")
    for flat, description in FLAT.items():
        add(flat, NEUTRAL_COLOR, description)
    return out
```

- [ ] **Step 4: Запустить — тесты проходят**

Run: `.venv/bin/pytest tests/test_label_catalog.py -q`
Expected: PASS, 6 тестов.

Если `test_control_labels_are_present` упал — сверить имена констант в `shared/labels.py`: там есть legacy-имя `needs-human-triage` рядом с рабочим `needs-human:triage`, перепутать их легко.

- [ ] **Step 5: Реализовать `ensure_labels_exist`**

Добавить в `worker/github_client.py` после `set_labels`:

```python
def ensure_labels_exist(repo: str, specs) -> int:
    """Заводит недостающие метки. Возвращает число созданных.

    Трекеры создают метку сами при первом применении — и GitHub, и GitLab
    (проверено 2026-08-21). Проблема не в отказе, а в тишине: опечатка в имени
    оседает новой меткой вместо ошибки, и выборка тихо перестаёт находить то,
    что искала. Явное заведение делает набор конечным и заодно даёт цвета.

    Идемпотентна: существующая метка не трогается, цвет ей не переписывается —
    человек мог поправить его руками, и спорить с ним незачем.
    """
    if _dry_run():
        _log.info("[DRY_RUN] ensure labels %s: %s", repo, [s.name for s in specs])
        return 0
    url = f"https://api.github.com/repos/{repo}/labels"
    existing: set[str] = set()
    page = 1
    while True:
        resp = requests.get(url, headers=_auth_headers(repo),
                            params={"per_page": 100, "page": page}, timeout=30)
        resp.raise_for_status()
        chunk = resp.json()
        existing.update(item["name"] for item in chunk)
        if len(chunk) < 100:
            break
        page += 1

    created = 0
    for spec in specs:
        if spec.name in existing:
            continue
        resp = requests.post(url, headers=_auth_headers(repo), timeout=30, json={
            "name": spec.name,
            "color": spec.color.lstrip("#"),
            "description": spec.description,
        })
        if resp.status_code == 422:
            continue  # завелась параллельно — не наша забота
        resp.raise_for_status()
        created += 1
    return created
```

- [ ] **Step 6: Написать скрипт bootstrap**

Создать `scripts/bootstrap_labels.py`:

```python
"""Заводит метки контура в репозитории.

Гоняется один раз при подключении нового репозитория — это шаг runbook'а из
дизайна поддержки GitLab. Идемпотентен: повторный запуск ничего не портит.

    python scripts/bootstrap_labels.py --repo owner/name
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import github_client  # noqa: E402
from shared.label_catalog import catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                        help="owner/name; по умолчанию GITHUB_REPOSITORY")
    args = parser.parse_args()
    if not args.repo:
        parser.error("нужен --repo или GITHUB_REPOSITORY")

    specs = list(catalog().values())
    created = github_client.ensure_labels_exist(args.repo, specs)
    print(f"{args.repo}: в каталоге {len(specs)}, создано {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Проверить скрипт вхолостую**

Run: `DRY_RUN=1 GH_TOKEN=x .venv/bin/python scripts/bootstrap_labels.py --repo o/r`
Expected: строка вида `o/r: в каталоге 59, создано 0`, ни одного HTTP-запроса.

- [ ] **Step 8: Прогнать весь набор**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 9: Коммит**

```bash
git add shared/label_catalog.py scripts/bootstrap_labels.py worker/github_client.py tests/test_label_catalog.py
git commit -m "feat(labels): каталог меток собирается из кода и заводится явно (#109)"
```

---

### Задача 6: Вебхук перестаёт отдавать 5xx

На GitHub упавшая доставка повторяется, поэтому 500 из обработчика незаметен. У GitLab **автоматических ретраев нет** — событие теряется навсегда, а **четыре подряд провала отключают вебхук** с backoff до 24 часов. Обработчик обязан принимать всё и разбираться внутри.

**Files:**
- Modify: `webhook/main.py:157-174` (`_issue_input`), `:383-392` (тело `github_webhook`), `:524-538` (гейт бота)
- Test: `tests/test_webhook_never_5xx.py` (создать)

**Interfaces:**
- Consumes: `_audit_dropped_delivery` (существует, `webhook/main.py:202`).
- Produces: ничего для последующих задач.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_webhook_never_5xx.py`:

```python
"""Обработчик принимает доставку даже когда разобрать её не может.

У GitLab ретраев нет, а четыре подряд провала отключают вебхук на срок до
суток. 500 из обработчика — это потерянное событие плюс шаг к отключению.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

SECRET = "s3cret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "o/r")
    import importlib

    import main
    importlib.reload(main)

    async def no_temporal():
        raise AssertionError("до Temporal дойти не должно")

    monkeypatch.setattr(main, "get_temporal_client", no_temporal)
    return TestClient(main.app)


def _post(client, event, payload):
    body = json.dumps(payload).encode()
    return client.post("/webhook", content=body, headers={
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": _sign(body),
        "X-GitHub-Delivery": "d-1",
        "Content-Type": "application/json",
    })


def test_comment_without_user_type_is_accepted(client):
    """Поля user.type у второго провайдера нет вовсе."""
    payload = {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 1},
        "comment": {"id": 5, "body": "текст", "user": {"login": "human"}},
    }
    assert _post(client, "issue_comment", payload).status_code == 200


def test_issue_without_user_type_is_accepted(client):
    payload = {
        "action": "opened",
        "repository": {"full_name": "o/r"},
        "issue": {"number": 1, "title": "t", "body": "b", "user": {"login": "human"}},
    }
    assert _post(client, "issues", payload).status_code < 500


def test_malformed_payload_is_accepted_not_500(client):
    """Мусор в теле — не повод терять доставку."""
    payload = {"action": "created", "repository": {"full_name": "o/r"}}
    assert _post(client, "issue_comment", payload).status_code == 200


def test_bad_signature_still_401(client):
    """Отказ авторизации остаётся отказом: 401 не считается сбоем доставки."""
    body = json.dumps({"repository": {"full_name": "o/r"}}).encode()
    resp = client.post("/webhook", content=body, headers={
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": "sha256=deadbeef",
        "Content-Type": "application/json",
    })
    assert resp.status_code == 401
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_webhook_never_5xx.py -q`
Expected: FAIL — `test_comment_without_user_type_is_accepted` и `test_malformed_payload_is_accepted_not_500` дают 500 (`KeyError`).

- [ ] **Step 3: Убрать индексацию в гейте бота**

В `webhook/main.py:530` заменить:

```python
        if payload["comment"]["user"]["type"] == "Bot":
```

на:

```python
        if (payload["comment"].get("user") or {}).get("type") == "Bot":
```

Дописать в комментарий выше строку:

```
        # `.get`, а не индексация: поле есть только у GitHub. Основную работу
        # всё равно делает подпись ниже — она различает происхождение, а не
        # автора, и работает у любого провайдера.
```

- [ ] **Step 4: Убрать индексацию в `_issue_input`**

В `webhook/main.py:172` заменить `author_type=issue["user"]["type"]` на:

```python
        author_type=(issue.get("user") or {}).get("type") or "User",
```

Дефолт `"User"` осознан: неизвестный автор — человек, а не бот. Ошибка в эту сторону приводит к лишней обработке, в обратную — к молча пропущенному Issue.

- [ ] **Step 5: Обернуть обработчик**

В `webhook/main.py` заменить строки `383-392` (от декоратора до `payload = await request.json()`) на:

```python
@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
):
    """Приём доставки. Отказать может только подпись.

    Всё остальное — включая payload, который мы не сумели разобрать, — уезжает
    в аудит и подтверждается 200. Причина: у GitLab автоматических ретраев нет,
    доставка теряется навсегда, а четыре подряд провала отключают вебхук на
    срок до суток. 500 отсюда стоит дороже, чем необработанное событие.
    """
    body = await request.body()
    verify_signature(body, x_hub_signature_256)
    payload = await request.json()
    try:
        return await _handle_delivery(payload, x_github_event, x_github_delivery)
    except HTTPException:
        raise
    except Exception:
        _log.exception(
            "не разобрал доставку %s (%s) — принимаю и ухожу в аудит",
            x_github_delivery or "без id", x_github_event)
        await _audit_dropped_delivery(
            payload, x_github_event, x_github_delivery,
            (payload.get("repository") or {}).get("full_name"),
            ["(ошибка разбора)"])
        return {"ok": True}


async def _handle_delivery(payload: dict, x_github_event: str,
                           x_github_delivery: str | None):
```

Дальше идёт прежнее тело обработчика начиная со строки с комментарием про allowlist — сдвинуть его в новую функцию без изменений. Проверить, что `return {"ok": True}` во всех ветках остались на месте.

- [ ] **Step 6: Обновить комментарий про ретраи**

В `webhook/main.py:73-74` заменить фразу про ретраи GitHub на:

```
    Доставка не потеряна: GitHub повторит её сам. У GitLab ретраев нет — там
    оборванная доставка теряется, поэтому обработчик ниже принимает всё, что
    прошло подпись, и разбирается внутри.
```

- [ ] **Step 7: Запустить — тесты проходят**

Run: `.venv/bin/pytest tests/test_webhook_never_5xx.py -q`
Expected: PASS, 4 теста.

- [ ] **Step 8: Прогнать весь вебхучный слой**

Run: `.venv/bin/pytest tests/test_webhook_audit.py tests/test_webhook_comment_commands.py tests/test_webhook_label_trigger.py tests/test_webhook_labeled.py tests/test_webhook_issue_closed.py tests/test_trigger_authz.py tests/test_bft_webhook.py -q`
Expected: PASS.

- [ ] **Step 9: Прогнать весь набор**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 10: Коммит**

```bash
git add webhook/main.py tests/test_webhook_never_5xx.py
git commit -m "fix(webhook): доставка принимается даже когда её не удалось разобрать (#109)"
```

---

### Задача 7: Свести итог этапа

**Files:**
- Modify: `docs/superpowers/specs/2026-08-21-gitlab-support-design.md` (раздел 15, строка статуса)
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: всё сделанное выше.
- Produces: ничего.

- [ ] **Step 1: Отметить этап 1 в дизайне**

В шапке дизайна заменить `**Статус:** дизайн согласован, реализация не начата` на `**Статус:** этап 1 (закалка) выполнен, этап 2 (извлечение `poh-forge`) не начат`.

В таблице этапов (раздел 15) в строке этапа 1 дописать в конец ячейки содержания: `— **сделано**`.

- [ ] **Step 2: Добавить абзац в ARCHITECTURE.md**

После раздела `### worker → github_client.py — GitHub REST` дописать:

```markdown
Операции с метками идут через `set_labels(add, remove)`, а не парой
`add_label`/`remove_label`. Так у смены набора одно место, и у провайдера,
умеющего менять метки одним запросом, есть что реализовать. Каталог меток
контура — `shared/label_catalog.py`, он собирается из тех же констант, что и
рабочий код; заводится скриптом `scripts/bootstrap_labels.py`.

Ссылка на репозиторий разбирается `shared/repo_ref.py`. Она переживает пути
глубже двух сегментов и берёт на себя кодирование для URL — заботиться об
этом на каждом вызове не нужно.
```

- [ ] **Step 3: Прогнать весь набор последний раз**

Run: `.venv/bin/pytest -q`
Expected: PASS. Записать итоговую строку с числом тестов — она идёт в описание PR.

- [ ] **Step 4: Коммит и PR**

```bash
git add docs/
git commit -m "docs: этап 1 закалки отмечен выполненным (#109)"
git push -u origin HEAD
gh pr create --base main --title "feat: закалка контура под второго провайдера (#109)" --body "Этап 1 из плана docs/superpowers/plans/2026-08-21-forge-hardening.md. Поведение на GitHub не меняется, кроме цветов и описаний у меток."
```

---

## Что этот план намеренно не делает

- **Не создаёт `poh-forge`.** Извлечение — этап 2, у него своя цена и свой PR.
- **Не пишет ни строчки под GitLab.** Драйвер — этап 3.
- **Не трогает `worker/github_client.py:611`** — фильтр «только боты» в `review_text`. Там `type` не защитный гейт, а **селектор**: он выбирает комментарии, которые и есть ревью. Заменить его нечем, пока нет второго провайдера с его понятием «комментарий сервиса»; вопрос решается в этапе 3, а падений на GitHub он не даёт.
- **Не заменяет `gh` CLI.** `search_candidates` и `list_open_issues` остаются на нём до этапа 3.
- **Не вводит `RepoRef` в 118 call-site.** Тип появляется и покрывается тестами, но подстановка в клиент — работа этапа 2, где она делается один раз вместе с переездом.
