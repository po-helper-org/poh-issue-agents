# FNR-1: Тяжёлые стадии пайплайна не реализованы, механизм загрузки скиллов в воркер отсутствует

> **Тип:** Архитектурное изменение / Новая фича
> **Дата:** 2026-07-12
> **Статус:** Открыта

---

## 1. Постановка проблемы

Workflow `IssueLifecycle` доводит issue до точки решения человека и по сигналу
`research-me`/`bug-me` вызывает activities `run_research_pipeline` /
`run_bug_pipeline`, но обе они немедленно бросают `NotImplementedError`. Тяжёлая
часть сервиса (ради которой он и строился) не работает end-to-end: нет ни
реализации самих пайплайнов, ни механизма доставки скиллов po-helper/SA-helper
в контейнер воркера, который эти пайплайны должны запускать.

## 2. Контекст

Сервис — перенос семи GitHub Actions в единый Temporal-workflow. Intake-часть
(предфильтры → gate → классификация → дубликаты → приоритет) перенесена «1:1» и
рабочая. Тяжёлые стадии перенесены как заглушки-`activity` с сохранёнными TODO
из версии на Actions: «перенести содержимое `research-pipeline.yml` /
`bug-pipeline.yml` как subprocess-вызовы `claude -p`». Проявляется при первом
же прохождении issue типа FEATURE/BUG до сигнала `research-me`/`bug-me`.
Подтверждение из README: раздел «Требует доработки» прямо перечисляет
`run_research_pipeline`/`run_bug_pipeline` (`NotImplementedError`) и «механизм
загрузки скиллов po-helper/SA-helper в контейнер воркера — не решён».

## 3. Текущее поведение (As-Is)

Workflow исправно доходит до тяжёлой стадии и вызывает соответствующую activity
с большим таймаутом и без ретраев, но сама activity — заглушка. Контейнер
воркера при этом собирает CLI `claude` и `gh`, монтирует `prompts/` и `config/`
и рабочий том `workspace`, но **не** содержит и не монтирует ни `.claude/skills`
(скиллы po-helper/SA-helper), ни бинарь `deb8flow`.

**Цепочка событий (от симптома к корню):**

| Шаг | Компонент | Что происходит | Доказательство |
|-----|-----------|---------------|----------------|
| 1 | `IssueLifecycle.run` | По сигналу `research-me` для FEATURE вызывает `run_research_pipeline` с `start_to_close_timeout=60 мин`, `maximum_attempts=1` | `worker/workflows.py:156-162` |
| 2 | `IssueLifecycle.run` | По сигналу `bug-me` для BUG вызывает `run_bug_pipeline` с таймаутом 30 мин | `worker/workflows.py:163-168` |
| 3 | `run_research_pipeline` | Тело — только docstring + `raise NotImplementedError(...)` | `worker/activities.py:265-272` |
| 4 | `run_bug_pipeline` | То же — `raise NotImplementedError(...)` | `worker/activities.py:276-278` |
| 5 | Temporal worker | Обе activity зарегистрированы и вызываемы, т.е. падение происходит в рантайме, а не на старте | `worker/worker.py:27-28` |
| 6 | `worker/Dockerfile` | Устанавливается `@anthropic-ai/claude-code`, но скиллы никуда не копируются; `deb8flow` — только TODO-комментарий | `worker/Dockerfile:12,15` |
| 7 | `docker-compose.yml` | Воркеру монтируются только `prompts`, `config`, `workspace` — тома со скиллами нет | `docker-compose.yml:63-68` |

**Ключевые компоненты:**

| Компонент | Роль | Файл:строка |
|-----------|------|-------------|
| `run_research_pipeline` | Точка, где должен исполняться forward-пайплайн (po-helper→Repowise→Blueprint→deb8flow→SA-helper) | `worker/activities.py:265` |
| `run_bug_pipeline` | Точка, где должен исполняться bug-диагностический пайплайн (SA-helper) | `worker/activities.py:276` |
| `run` (workflow) | Оркестратор, уже вызывающий эти activity | `worker/workflows.py:156-168` |
| `worker/Dockerfile` | Сборка окружения воркера (claude CLI есть, скиллов/deb8flow нет) | `worker/Dockerfile:1-27` |
| `docker-compose.yml` (worker) | Монтирование ресурсов в воркер | `docker-compose.yml:56-68` |
| `_load_prompt` / `PROMPTS_DIR` | Существующий паттерн доставки ресурсов через `/app/*` volume | `worker/activities.py:26,32` |

## 4. Корень проблемы

Причина не одна, а две связанные: (а) сами activity не имеют реализации —
исполнение forward/bug-цепочек как subprocess-вызовов `claude -p`/`deb8flow`/`gh`
не написано (`worker/activities.py:265-278`); (б) даже будь оно написано, ему
нечего запускать: в образе/томах воркера физически отсутствуют скиллы
po-helper/SA-helper и бинарь `deb8flow`, т.е. `claude -p` не найдёт `.claude/skills`,
а `deb8flow` не найдётся в `PATH`.

**Доказательство:** `worker/Dockerfile:12` — ставится только `@anthropic-ai/claude-code`;
`worker/Dockerfile:15` — `# TODO: установка deb8flow`; `docker-compose.yml:64-68` —
монтируются лишь `prompts`/`config`/`workspace`, тома со скиллами нет.

## 5. Ожидаемое поведение

По сигналу `research-me` (FEATURE) workflow исполняет полную forward-цепочку и
сохраняет артефакты (БФТ/Blueprint/техспека) в рабочую директорию/ветку; по
`bug-me` (BUG) — исполняет диагностику и ставит лейбл `bug:diagnosed`. Скиллы
po-helper/SA-helper и `deb8flow` доступны процессу `claude -p` внутри воркера.
Падение посреди 60-минутного прогона переживается благодаря durable execution
Temporal (as-is гарантия сохраняется). Конкретное целевое состояние — предмет
концепта (`/fnr-concept`), здесь фиксируется только разрыв.

## 6. Зона воздействия

**Прямое воздействие:**

| Компонент | Тип | Файл |
|-----------|-----|------|
| `run_research_pipeline` | activity (Python) | `worker/activities.py` |
| `run_bug_pipeline` | activity (Python) | `worker/activities.py` |
| Образ воркера | Dockerfile | `worker/Dockerfile` |
| Композиция воркера | docker-compose (volumes) | `docker-compose.yml` |
| Окружение | `.env.example` (ANTHROPIC_*, DEB8FLOW_BIN) | `.env.example:20-21,29` |

**Косвенное воздействие (зависимые компоненты):**

| Компонент | Зависимость | Риск |
|-----------|------------|------|
| `IssueLifecycle.run` | Вызывает обе activity; полагается на их таймауты/ретраи | Изменение сигнатур/времени исполнения может потребовать правки оркестратора (`worker/workflows.py:156-168`) |
| `github_client` | Пайплайны будут коммитить артефакты/ветки через gh/REST | Нагрузка на installation-token, ветки `research/issue-N` (`worker/github_client.py:78`) |
| `trigger_openhands_resolver` | Следующая стадия после research/bug | Тоже `NotImplementedError` — вне scope, но зависит от результата (`worker/activities.py:282`) |
| Рабочий том `worker_workspace` | Пайплайны пишут артефакты сюда | Конкурентная запись веток разных issue (`docker-compose.yml:68`) |

**Защищённые компоненты (не должны быть затронуты):**

- Intake-часть (`prefilter_bot_and_security`…`post_priority_comment`, `worker/activities.py:74-260`) — перенесена «1:1», менять её поведение нельзя.
- Формула приоритизации и `config/priority-weights.toml` — по README «формула не изменилась».
- Контракт вебхука и сигналов (`webhook/main.py`, signals `human_decision`/`user_comment`) — точки интеграции, ломать обратную совместимость нельзя.

## 7. Ограничения

- Скиллы po-helper/SA-helper по README «сами не меняются, меняется только backend-модель» — механизм загрузки не должен требовать правки самих скиллов.
- OpenHands намеренно остаётся ОТДЕЛЬНЫМ сервисом со своим sandboxing (`docker.sock` = root на хосте) — не втягивать его в этот docker-compose.
- Секрет приватного ключа GitHub App пока не смонтирован (`docker-compose.yml` не содержит secret-тома) — смежное ограничение среды.
- Durable-гарантия Temporal должна сохраниться: тяжёлый прогон переживает рестарт воркера.

## 8. Ссылки

| Артефакт | Путь |
|----------|------|
| README (раздел «Что перенесено 1:1, что требует доработки») | `README.md` |
| Диаграмма пайплайнов (часть 2) | `docs/diagrams/issue-workflow-part2-pipelines.mermaid` |
| Спецификация реализации | `specs/implementation-spec.md` |
| Словарь терминов | `sa_documentation/naming_conventions.md` |

---

> Задача FNR-1 описана. Следующий шаг: `/fnr-concept sa_documentation/FNR/FNR_1/task.md`
