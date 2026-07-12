# Design: Issue Agent — Слой A (автономный триаж на po-helper)

Дата: 2026-07-12
Статус: одобрен к реализации (Слой A)
Репозиторий: `kibarik/GitHub-issue-agents` (этот)
Целевой репозиторий обработки: `kibarik/po-helper`

## Цель и мерило успеха

Стратегическая цель владельца: делегировать через GitHub Issues первичный
сбор и аналитику по доработке проекта `po-helper`.

Мерило успеха («workflow заработал на po-helper»):

1. Для **каждого** уже открытого Issue в `po-helper` (на момент старта — 39)
   система прошлась и отработала согласно бизнес-процессу.
2. Когда открывается **новый** Issue — система обрабатывает его согласно
   бизнес-процессу автоматически.

Полный бизнес-процесс делится на автономную часть (триаж) и часть по запросу
человека (аналитика). Данная спека покрывает **Слой A — автономный триаж** как
первый проверяемый сквозной результат, дающий пункт 1 критерия целиком.
Слои B (новые Issue авто) и C (аналитика по запросу) описаны как последующие
и вне объёма этой спеки.

## Границы (scope)

**В объёме (Слой A):**
- Прогон существующей дешёвой части пайплайна (`prefilter_bot_and_security` →
  `intake_gate` → `classify_issue` → `duplicate_check` → `score_priority` →
  `post_priority_comment`) на всех открытых Issue `po-helper`.
- Механизм бэкфилла: старт `IssueLifecycle`-workflow для каждого уже открытого
  Issue (webhook такие события не присылает).
- Аутентификация по personal access token вместо регистрации GitHub App
  (снижение фрикшна пилота).
- Наполнение `capabilities.md` реальным функционалом `po-helper`.
- Режим `DRY_RUN` — защита от массового автозакрытия при первом прогоне.
- Локальный запуск через `docker-compose` (postgres, temporal, temporal-ui,
  worker); сервис `webhook` в Слое A не требуется.

**Вне объёма (последующие слои):**
- Слой B: публичный webhook (cloudflared/reverse proxy) + вебхук репозитория
  для автостарта на новых Issue.
- Слой C: `run_research_pipeline` / `run_bug_pipeline` / `trigger_openhands_resolver`
  (сейчас `NotImplementedError`), скиллы po-helper/SA-helper в контейнере,
  deb8flow, MCP Confluence/Jira, генерация `.docx`.
- Регистрация полноценного GitHub App с App-идентичностью комментариев.

## Существующая архитектура (не меняется по сути)

Один долгоживущий Temporal-workflow `IssueLifecycle` на один Issue
(ID = `issue-<repo>-<n>`, даёт идемпотентность). Лейблы/комментарии —
Temporal signals, не отдельные триггеры. Слои: `webhook` (транспорт) →
Temporal → `worker` (`workflows.py` оркестрация, `activities.py` содержание,
`llm.py` доступ к GLM через z.ai, `github_client.py` GitHub REST).

Слой A использует этот каркас как есть. Workflow доходит до
`post_priority_comment`, затем паркуется на `await self._wait_for_signal()`
(точка решения человека №1) — это штатное «отработал согласно бизнес-процессу»
для автономной части. Дальнейшие стадии остаются заглушками (Слой C).

## Разрывы между текущим кодом и мерилом успеха

1. **Бэкфилла нет.** `webhook/main.py` стартует workflow только на
   `issues.opened`. GitHub не присылает webhook по уже существующим Issue.
   Без отдельного бэкфилла пункт 1 критерия недостижим.
2. **Аутентификация только через GitHub App.** `github_client.py` жёстко
   читает `GITHUB_PRIVATE_KEY_PATH` / `GITHUB_APP_ID` / `GITHUB_INSTALLATION_ID`
   и генерирует installation-токен. Для пилота это лишний фрикшн (регистрация
   App, монтирование `.pem`, которого нет в `docker-compose.yml`).
3. **`capabilities.md` пустой/отсутствует.** `classify_issue` читает
   `WORKSPACE_DIR/capabilities.md`; при отсутствии подставляет «(пусто)» —
   тогда классификатор не отличает существующий функционал от новой фичи.
4. **Автозакрытие живых Issue.** `close_as_spam`, ветка дубликата ≥ 0.85 и
   классы `existing-functionality`/`consultation` закрывают Issue. На 39 живых
   discussion/enhancement ошибка модели = автозакрытие ценного обсуждения.

## Проектные решения

### Решение 1. Бэкфилл прямым стартом в Temporal

Скрипт `scripts/backfill.py` (запускается на хосте или во временном
worker-контейнере — важно, что он импортирует те же `shared.workflow_types`):

- `gh issue list --repo <repo> --state open --json number,title,body,author --limit N`
  (используется уже авторизованный `gh` как `kibarik`).
- Для каждого Issue собирает `IssueInput` и вызывает
  `client.start_workflow("IssueLifecycle", ..., id="issue-<repo>-<n>",
  task_queue="issue-lifecycle")`.
- Идемпотентность: id = `issue-<repo>-<n>` уникален на Issue. Припаркованные
  workflow всё ещё *running* (ждут сигнал), поэтому повторный `start_workflow`
  по тому же id бросит `WorkflowAlreadyStartedError` — бэкфилл ловит это
  исключение и пропускает Issue (уже в обработке), не падая. Это делает
  повторный запуск бэкфилла безопасным.
- Флаги: `--issue N` (один Issue для смоук-теста), `--limit K`,
  `--repo owner/name` (по умолчанию из `GITHUB_REPOSITORY`).

Бэкфилл бьёт напрямую в Temporal (адрес `TEMPORAL_ADDRESS`), публичный
webhook и туннель для него не нужны.

### Решение 2. PAT-путь аутентификации

В `github_client.py` добавить ветку: если задан `GH_TOKEN` (или
`GITHUB_TOKEN`), использовать его как Bearer напрямую и **не** ходить в
App-flow. App-путь сохраняется как есть для будущего (Слой B/прод).

```
_auth_headers():
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return {"Authorization": f"Bearer {token}", "Accept": "..."}
    return _installation_token_headers()   # существующий App-flow
```

Все функции (`post_comment`, `add_label`, `close_issue`, `search_candidates`,
`branch_exists`) переключаются на `_auth_headers()`. `search_candidates` уже
пробрасывает токен в `gh` через `GH_TOKEN` — там меняется лишь источник токена.

Токен: fine-grained PAT на `kibarik/po-helper` с правами Issues (read/write),
Contents (read) — либо переиспользовать сессию `gh auth token`.

### Решение 3. Наполнение `capabilities.md`

Создать `workspace/capabilities.md` — перечень известного функционала
`po-helper` (навыки/команды из его README: OKR, Спринт, БФТ, Внешние запросы,
jira-task, инфо-каналы, summary, дейлики, релизы, people-map, confluence-
индексатор и т.д.). Источник — README `po-helper`, раздел «Что внутри».

`docker-compose.yml`: заменить named-том `worker_workspace:/app/workspace` на
бинд `./workspace:/app/workspace`, чтобы засеять файл из репозитория и видеть
артефакты на хосте.

### Решение 4. Режим `DRY_RUN`

Переменная окружения `DRY_RUN=1`. В `github_client.py` мутирующие вызовы
(`post_comment`, `add_label`, `close_issue`) при `DRY_RUN` **логируют**
намерение (`repo`, `issue`, действие, тело) и возвращаются без HTTP-запроса.
Читающие вызовы (`search_candidates`, `branch_exists`) работают как обычно —
чтобы классификация/дубликаты давали настоящий результат.

Процесс первого прогона:
1. `DRY_RUN=1`, бэкфилл всех 39 → смотрим в Temporal UI, что каждый workflow
   дошёл до `post_priority_comment`; в логах worker — какие лейблы/комменты/
   закрытия он бы поставил.
2. Владелец ревьюит вывод (особенно предполагаемые автозакрытия).
3. Снимаем `DRY_RUN`, боевой прогон.

## Поток Слоя A (happy path)

```
scripts/backfill.py
  → start_workflow(IssueLifecycle, IssueInput) для каждого open Issue
      → prefilter_bot_and_security   (бот/security → стоп)
      → intake_gate (GLM-air)        (VAGUE → цикл уточнений; SPAM → закрыть)
      → classify_issue (GLM-5.2)     (EXISTING/CONSULTATION → ответ, стоп)
      → duplicate_check (GLM-air)    (≥0.85 → закрыть дубль; ≥0.5 → пометить)
      → score_priority (GLM + Python) → priority:PN
      → post_priority_comment        → лейбл priority:PN + разбивка
      → await human_decision         (парковка — конец автономной части)
```

## Обработка ошибок

- LLM-стадии уже обёрнуты в `RetryPolicy(maximum_attempts=3)`.
- Полноценную обработку сбоев (лейбл `advisor:error` + комментарий вместо
  тихого падения) относим к Слою A-hardening — минимально: если activity
  падает после исчерпания ретраев, workflow завершается с ошибкой, видимой в
  Temporal UI; на первом прогоне в `DRY_RUN` это безопасно.
- `DRY_RUN` исключает главный риск необратимости (массовое автозакрытие).

## Тестирование и верификация

- **Смоук:** `backfill.py --issue <N>` на одном показательном Issue (например,
  явный feature-request) в `DRY_RUN` → в Temporal UI workflow дошёл до парковки,
  в логах — ожидаемые лейбл+приоритет.
- **Детерминизм приоритета:** один Issue дважды → тот же `priority:PN`
  (формула детерминирована; вариативность только на извлечении атрибутов LLM —
  зафиксировать наблюдение).
- **Дубликаты:** проверить, что заведомо близкие Issue из 39 дают
  `possible-duplicate` (≥0.5), не ложное автозакрытие.
- **Полный прогон:** все 39 в `DRY_RUN`, ручной ревью, затем боевой.
- Верификация «работает» = наблюдаемое поведение в Temporal UI + реальные
  комментарии/лейблы на Issue после снятия `DRY_RUN`, не только зелёные тесты.

## Предпосылки (обеспечивает владелец)

- `ZAI_API_KEY` — есть (подтверждено).
- Docker running — подтверждено.
- `gh` авторизован как `kibarik` — подтверждено; источник `GH_TOKEN`.

## Открытые вопросы (не блокируют Слой A)

- Калибровка порогов `priority-weights.toml` на реальных Issue — Слой A-hardening/Ф6.
- Источник OKR для `okr_alignment` — на старте статично/`unrelated`, реальный
  источник позже.
- Промпты написаны под старый парсинг маркеров `[[...]]` — с Instructor
  избыточно, упрощение косметическое, не блокирует.

## Последующие слои (вне объёма)

- **Слой B:** публичный webhook + вебхук репозитория `po-helper` → автостарт
  на `issues.opened`/`labeled`/`comment`. Даёт пункт 2 критерия.
- **Слой C:** реализация research/bug-пайплайнов — стратегическая аналитика
  (БФТ/Blueprint/дебаты/техспека в git-ветку). Основные блокеры: загрузка
  скиллов po-helper/SA-helper в worker-контейнер, `claude -p` через z.ai с
  tool-calling, deb8flow, MCP Confluence/Jira в headless, генерация `.docx`.
