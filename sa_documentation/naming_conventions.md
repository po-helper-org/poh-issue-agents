# Naming Conventions — Issue Agent Service

Словарь соответствия «код ↔ бизнес» для документов SA-helper. Источник —
живой код репозитория (repomix-output.xml не генерировался: проект мал,
анализ вёлся по исходникам напрямую).

| Понятие (в документах) | Технический термин (в коде) | Описание |
|---|---|---|
| Обработчик Issue | `IssueLifecycle` (`worker/workflows.py:31`) | Один Temporal-workflow на один issue, ID = `issue-<repo>-<n>` |
| Приёмный шлюз | `intake_gate` (`worker/activities.py:105`) | Дешёвый фильтр SPAM/VAGUE/SUFFICIENT |
| Классификатор | `classify_issue` (`worker/activities.py:158`) | 4-way: EXISTING/CONSULTATION/BUG/FEATURE |
| Проверка дублей | `duplicate_check` (`worker/activities.py:184`) | Один LLM-вызов на всех кандидатов, порог 85%/50% |
| Приоритизация | `score_priority` (`worker/activities.py:230`) | Извлечение атрибутов LLM + детерминированная формула |
| Конвейер аналитики | `prepare_workspace` + `run_fnr_stage` (`worker/activities.py`) | Реализован постадийно. Функции `run_research_pipeline` в коде НЕТ — запись о ней была устаревшей и снята при FNR-5 |
| Стадия FNR | одна из `FNR_STAGE_NAMES`: `repowise`, `task`, `concept`, `debate`, `sysreq`, `validate` | Отдельный процесс `claude -p` с чистым контекстом; знание переходит между стадиями только файлами |
| Индекс кода | Repowise, отдельный сервис (`po-helper-org/poh-infra`) | Граф символов, история git, blame, поиск, риск правки, мёртвый код. Живёт дольше прогона |
| Workspace | `contour` / `product` (`shared/repowise.py`) | Граница вопроса, не команды: «как устроены агенты» против «что агенты пишут» |
| MCP-прокси | `REPOWISE_PROXY_URL` (`shared/repowise.py`) | Единственный вход к индексу из контура: маршрут по workspace, токен, журнал обмена |
| Сессия диалога | `repowise.session_id(repo, n, agent)` | Детерминированный ключ журнала; аналитика и разработка по одному Issue — две разные сессии |
| Артефакт диалога | `repowise-dialog.md` | Транскрипт, отрендеренный прокси из журнала. Модель его не пишет — полнота получается построением |
| Деградация стадии | `outcome: degraded` в отчёте `run_fnr_stage` | Индекс недоступен: артефакт создан, конвейер идёт дальше. Штатный режим, не отказ |
| Bug-пайплайн | `run_bug_pipeline` (`worker/activities.py`) | **Не реализовано** (`NotImplementedError`). Диагностика бага (SA-helper) |
| Агент разработки | одноразовый контейнер OpenHands (`shared/develop.py`) | Реализован режимом `local`; `trigger_openhands_resolver` в коде нет |
| Скилл (навык) | po-helper / SA-helper Claude Code skill | Набор инструкций для `claude -p`; вызывается тяжёлыми стадиями |
| Сигнал решения человека | `human_decision` signal (`worker/workflows.py:34`) | Лейблы `research-me`/`bug-me`/`build-me` как Temporal-сигналы |
| Бэкенд-модель (skills) | z.ai Anthropic-эндпоинт | `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` (`.env.example:20-21`) |
| Бэкенд-модель (Python-стадии) | z.ai OpenAI-эндпоинт (GLM) | `ZAI_BASE_URL`/`ZAI_API_KEY` (`.env.example:15-16`) |
| Директория промптов | `PROMPTS_DIR = /app/prompts` (`worker/activities.py:26`) | Монтируется как volume (`docker-compose.yml:64`) |
| Рабочая директория | `WORKSPACE_DIR = /app/workspace` (`worker/activities.py:28`) | Volume `worker_workspace` (`docker-compose.yml:68,74`) |

## Запрещённые синонимы

- «Индекс» ≠ «выгрузка repomix». Выгрузка — плоский XML, собираемый заново
  каждым прогоном; индекс — постоянный объект со своим жизненным циклом.
  Они сосуществуют: индекс выгрузку дополняет, а не заменяет.

- «Скилл» ≠ «промпт». Промпты (`prompts/*.md`) — системные подсказки для
  дешёвых Python-стадий (Instructor). Скиллы (po-helper/SA-helper) — это
  Claude Code `.claude/skills`, запускаемые через `claude -p`.
- «Activity» ≠ «GitHub Action». В этом сервисе стадии — Temporal-activities
  (Python), а не YAML-шаги Actions (это было в предыдущей версии).
