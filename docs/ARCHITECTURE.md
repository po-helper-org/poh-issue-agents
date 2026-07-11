# Архитектура: Issue Agent Service

## Обзор

```
┌──────────┐   webhook    ┌──────────────┐   start/signal   ┌──────────────┐
│  GitHub  │ ───────────► │   webhook    │ ───────────────► │   Temporal   │
│  (Issues)│              │  (FastAPI)   │                  │   (Postgres) │
└──────────┘              └──────────────┘                  └──────┬───────┘
     ▲                                                             │
     │ REST (comment/label/close)                          task queue
     │                                                             ▼
     │                                                      ┌──────────────┐
     └──────────────────────────────────────────────────── │    worker    │
       activities: GLM (Instructor) / gh CLI / claude -p    │ (activities) │
                                                            └──────────────┘
                          ┌──────────────┐
        наблюдаемость ──► │ Temporal UI  │  localhost:8080
                          └──────────────┘
```

Пять контейнеров в `docker-compose.yml`: `postgres`, `temporal`,
`temporal-ui`, `webhook`, `worker`.

## Ключевой архитектурный принцип

**Один долгоживущий Temporal-workflow на один Issue.** Workflow ID =
`issue-<repo>-<n>`. Это заменяет то, что в исходной реализации было семью
отдельными GitHub Actions, триггерящимися на лейблы. Следствия:

1. **Лейблы и комментарии = Temporal signals**, не триггеры отдельных
   процессов. Workflow приостанавливается (`await`) и ждёт сигнала:
   - `human_decision(label)` — установка `research-me`/`bug-me`/`build-me`.
   - `user_comment(text)` — ответ пользователя в цикле уточнения.
2. **Нет гонок между стадиями.** duplicate-check и priority-scoring были
   параллельными Actions на один лейбл — теперь последовательные шаги
   одного потока.
3. **Состояние живёт в переменных workflow**, не в HTML-маркерах в
   комментариях (счётчик раундов уточнения и т.п.). Temporal журналирует
   состояние сам.
4. **Идемпотентность бесплатно** — повторный `issues.opened` по тому же
   номеру не стартует второй workflow (тот же ID).

## Слои и ответственность

### webhook (FastAPI) — чистый транспорт
Единственная точка входа для GitHub. Проверяет HMAC-подпись, транслирует:
- `issues.opened` → `start_workflow`
- `issues.labeled` (research-me/bug-me/build-me) → `signal("human_decision")`
- `issue_comment.created` (не от бота) → `signal("user_comment")`

Никакой бизнес-логики. Не знает про GLM, про стадии, про пороги.

### worker → workflows.py — оркестрация
`IssueLifecycle.run()` — последовательность шагов с точками ожидания
сигналов. Только композиция activities и управление потоком, без прямых
вызовов LLM/GitHub (в workflow-коде Temporal это запрещено — только через
activities, ради детерминизма replay).

### worker → activities.py — вся содержательная работа
Каждая стадия из требований = одна activity. Здесь живут вызовы GLM,
gh CLI, claude -p, детерминированный расчёт. Перенесены из исходных
`advisor/*.py`.

### worker → llm.py — доступ к модели
Instructor поверх OpenAI-совместимого эндпоинта z.ai. Структурированное
извлечение (Pydantic-схема) вместо ручного JSON-парсинга.

### worker → github_client.py — GitHub REST
Аутентификация как GitHub App (генерация installation-токена, живёт ~1ч).
Отличие от исходной версии на Actions (там был готовый GITHUB_TOKEN).

## Поток обработки (happy path для FEATURE)

1. `issues.opened` → старт workflow.
2. `prefilter_bot_and_security` — если бот/security, стоп.
3. `intake_gate` (GLM-air) → SUFFICIENT (иначе цикл уточнения/спам).
4. `classify_issue` (GLM-5.2) → `advisor:feature-request`.
5. `duplicate_check` (GLM-air) → не дубликат.
6. `score_priority` (GLM-air извлечение + Python расчёт) → `priority:P1`.
7. `post_priority_comment`.
8. **Ожидание сигнала** `human_decision`.
9. Человек ставит `research-me` → сигнал.
10. `run_research_pipeline` (po-helper → Repowise → Blueprint → deb8flow →
    SA-helper) — до 60 мин, durable.
11. **Ожидание сигнала** `human_decision`.
12. Человек ставит `build-me` → `trigger_openhands_resolver`.

## Модель данных (артефакты в git-ветках)

```
research/issue-<n>/
  docs/bft/issue-<n>.docx                    # БФТ (критерии + контекст)
  docs/bft/issue-<n>-blueprint.md            # Service Blueprint + IDEF0
  docs/bft/issue-<n>-debate.md               # протокол дебатов
  docs/bft/issue-<n>-recommendations.md      # рекомендации дебатов
  docs/research/issue-<n>-sa-spec.md         # техническая спецификация

bug/issue-<n>/
  docs/bugs/issue-<n>-diagnosis.md           # диагноз + DoD

docs/context/issue-<n>-related.json          # кэш кандидатов-дубликатов
docs/capabilities.md                         # известный функционал (ручной)
config/priority-weights.toml                 # веса и пороги приоритизации
```

## Границы отказоустойчивости

- LLM-стадии обёрнуты в Temporal RetryPolicy (3 попытки).
- Дорогие мультиагентные стадии (research/bug) — RetryPolicy(1): не
  ретраятся вслепую, чтобы не жечь ресурсы на повтор длинного прогона.
- Падение воркера в середине research → Temporal продолжает с последнего
  завершённого шага после рестарта.

## Что осознанно вне ядра

- OpenHands resolver (стадия 8) — отдельный сервис, свой sandboxing.
- deb8flow — CLI внутри worker-контейнера, но сам инструмент авторский,
  устанавливается отдельно (TODO в Dockerfile).
- Repowise MCP (Confluence/Jira) — подключение к headless-среде worker'а
  ещё не решено.
