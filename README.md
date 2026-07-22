# Issue Agent Service — self-hosted, docker-compose, GLM

Полный цикл обработки Issue как один долгоживущий Temporal-workflow вместо
семи отдельных GitHub Actions. Один `docker-compose up` — и сервис слушает
вебхуки GitHub напрямую.

## 🚀 Быстрый старт (Layer A — автономный триаж)

Прогнать бизнес-процесс по **всем открытым Issue** репозитория (триаж:
предфильтры → gate → классификация → дубликаты → приоритет → лейбл+коммент),
не регистрируя GitHub App и без публичного webhook. Три команды:

```bash
make setup     # preflight (docker/uv/gh) + venv + генерация .env (интерактивно)
make up        # поднять temporal + worker
make dry-run   # прогнать ВСЕ открытые Issue в DRY_RUN — ничего не мутируется
```

`make setup` спросит целевой репозиторий (по умолчанию `kibarik/po-helper`),
возьмёт GitHub-токен из уже авторизованного `gh`, запросит `ZAI_API_KEY` и
запишет `.env` с `DRY_RUN=1`. Проверь `[DRY_RUN]`-строки в `make logs`
(Temporal UI — http://localhost:8080), затем:

```bash
make go-live   # выключить DRY_RUN, перезапустить worker, прогнать по-настоящему
```

`make backfill-one issue=<N>` — прогнать один Issue (смоук-тест). Требования:
Docker, [`uv`](https://astral.sh/uv), [`gh`](https://cli.github.com) (`gh auth login`).
Детали и слои B/C — `docs/superpowers/`.

## Документация (начни отсюда)

- **`docs/REQUIREMENTS.md`** — зафиксированный набор требований (FR/NFR),
  технологические решения, границы. Источник правды.
- **`docs/ARCHITECTURE.md`** — как устроена система, потоки, слои,
  модель данных артефактов.
- **`docs/ROADMAP.md`** — фазированный план реализации (Ф0-Ф6) с
  чекпоинтами, открытыми вопросами и сводкой блокеров. **С этого начинать
  разработку.**
- **`docs/DECISIONS.md`** — журнал архитектурных решений (почему Temporal,
  почему GLM, почему не KAgent/gh-aw) — чтобы не переоткрывать обсуждённое.
- **`docs/diagrams/`** — Mermaid-диаграммы полного процесса (2 части).

## С чего начать завтра

1. Прочитать `docs/ROADMAP.md`, раздел "Фаза 0".
2. Поднять инфраструктуру, зарегистрировать GitHub App, настроить публичный
   webhook.
3. Проверить, что тестовый Issue создаёт workflow в Temporal UI.
4. Двигаться по фазам: сначала дешёвый сквозной путь (Ф1), потом
   отказоустойчивость (Ф2), потом bug/research-пайплайны (Ф3-Ф4).

## Архитектура

```
GitHub → webhook (FastAPI) → Temporal → worker (activities: GLM/gh/claude -p)
                                  ↑
                          Temporal UI (localhost:8080) — видно каждый issue
                          на его текущей стадии
```

Один workflow `IssueLifecycle` на issue (ID = `issue-<repo>-<n>`). Лейблы
`research-me`/`bug-me`/`build-me` и ответы-уточнения — не отдельные
GitHub Actions триггеры, а Temporal **signals**: workflow буквально спит
и ждёт, пока не придёт сигнал. Это убирает гонку между duplicate-check и
priority-scoring (были параллельными Actions — теперь последовательные шаги
одного потока) и ручной парсинг HTML-маркеров для счётчика раундов
уточнения (состояние просто живёт в переменных workflow).

## Модель — GLM через z.ai

- Python-стадии (gate/classify/duplicate/priority) — Instructor поверх
  OpenAI-совместимого эндпоинта z.ai (`worker/llm.py`). Дешёвая модель —
  `glm-4.5-air`, для классификации — `glm-5.2`.
- `claude -p` для po-helper/SA-helper skills (research/bug-pipeline) —
  Anthropic-совместимый эндпоинт z.ai через `ANTHROPIC_BASE_URL`. Сами
  скиллы не меняются, меняется только backend-модель.

## Установка (Layer B — webhook + GitHub App, для автостарта на новых Issue)

> Для Layer A это НЕ нужно — см. [Быстрый старт](#-быстрый-старт-layer-a--автономный-триаж)
> выше. Регистрация App и публичный webhook требуются только чтобы новые Issue
> обрабатывались автоматически при создании (Layer B).

1. Зарегистрировать GitHub App (Settings → Developer settings → GitHub Apps):
   permissions Issues (read/write), Contents (read/write); webhook events
   Issues + Issue comments; webhook URL — публичный адрес твоего `webhook`
   сервиса (для локальной разработки — `cloudflared tunnel` или `ngrok`,
   для прода — за твоим reverse proxy на реальном домене).
2. Установить App на репозиторий, сохранить App ID, Installation ID,
   приватный ключ (`.pem`).
3. Скопировать `.env.example` → `.env`, заполнить GitHub App данные и
   `ZAI_API_KEY`.
4. Положить приватный ключ App по пути из `GITHUB_PRIVATE_KEY_PATH`
   (по умолчанию монтируется как volume — добавь маунт в
   `docker-compose.yml`, сейчас в шаблоне не прописан секрет-том явно).
5. `docker-compose up --build`.
6. Открой `localhost:8080` (Temporal UI) — там видно все workflow-инстансы
   и на какой стадии застрял каждый issue.

## Оценка трудоёмкости — команда `/estimate`

Комментарий `/estimate` в любом Issue запускает оценку. Агент ставит 👀 на
комментарий, собирает контекст (описание, обсуждение, артефакты ветки
`research/issue-<n>` или `bug/issue-<n>`, если она есть) и публикует оценку
с обоснованием: декомпозиция по единицам работы, Function Points как
cross-check, PERT, разбивка по грейдам, каждый применённый риск и каждая
надбавка отдельной строкой.

Повторный `/estimate` — новая оценка с учётом контекста, появившегося с
прошлого раза. Прошлые прогоны остаются в Temporal UI.

Методология — `docs/methodology/task-estimation.md`. Все коэффициенты
вынесены в `config/estimation-rules.toml`: меняя их, не трогаешь ни промпт,
ни код расчёта. Модель извлекает только факты, все числа считает Python.

Требует Layer B (вебхук + GitHub App): команда приходит событием
`issue_comment.created`.

## Что перенесено 1:1, что требует доработки

**Перенесено без изменений по смыслу:**
- Zero-cost предфильтры (боты/security) — `activities.prefilter_bot_and_security`
- Intake Gate с циклом уточнений — `intake_gate` + signal `user_comment`
- 4-way классификация — `classify_issue`
- Duplicate Check (один LLM-вызов на всех кандидатов, порог 85%/50%) —
  `duplicate_check`
- Priority Scoring (LLM извлекает атрибуты → детерминированная формула из
  `config/priority-weights.toml`) — `score_priority`. Формула не изменилась.

**Требует доработки (те же TODO, что были на Actions, не появились заново):**
- `run_research_pipeline` / `run_bug_pipeline` — сейчас `NotImplementedError`.
  Нужно перенести содержимое старых `research-pipeline.yml`/`bug-pipeline.yml`
  как subprocess-вызовы `claude -p`/`deb8flow`/`gh` внутри activity. Логика
  та же (po-helper → Repowise контекст → Blueprint → deb8flow → SA-helper),
  меняется только то, что это Python-функция, а не шаги YAML.
- Механизм загрузки скиллов po-helper/SA-helper в контейнер воркера — не
  решён (тот же открытый вопрос, что и раньше).
- `deb8flow` — установка внутри `worker/Dockerfile` помечена TODO.
- `trigger_openhands_resolver` — OpenHands намеренно остаётся ОТДЕЛЬНЫМ
  сервисом со своим sandboxing (`docker.sock` = root-эквивалент на хосте),
  не частью этого docker-compose. Activity здесь — просто вызов его API/CLI.
- Промпты в `prompts/` были написаны под ручной парсинг маркеров
  (`[[EXISTING]]`/`[[SPAM]]` и т.п.) для версии без Instructor. Сейчас
  структура ответа задаётся Pydantic-схемой в `activities.py`, а не
  парсингом текста — промпты работают (Instructor всё равно направит
  LLM в нужную схему), но инструкцию "начни ответ с маркера" в них можно
  убрать как избыточную, она больше ничего не делает.
- `docker-compose.yml` не монтирует секрет с приватным ключом GitHub App —
  добавь volume/secret под свою модель хранения секретов в MTS.

## Почему Temporal, а не просто Python-скрипт с очередью

Durable execution — если worker упадёт посреди research-pipeline (60 минут
исполнения), Temporal переживёт рестарт и продолжит с последнего
завершённого шага, а не начнёт weit заново. Тот же механизм даёт "подожди
сигнал сколько угодно долго" — issue может неделями висеть в бэклоге с
приоритетом, ожидая `research-me`, это штатное состояние workflow, не хак.
