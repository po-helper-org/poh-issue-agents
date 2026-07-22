# Issue Agent Service — self-hosted, docker-compose, GLM

Обработка GitHub Issue как долгоживущие Temporal-workflow вместо набора GitHub
Actions. Два независимых сценария: **триаж каждого Issue** (Layer A) и
**консолидация бэклога в зоны поставки** (consolidation).

---

## Что умеет сейчас

| Возможность | Статус | Точка входа |
|-------------|--------|-------------|
| **Layer A — автономный триаж Issue**: предфильтры → intake-gate (с циклом уточнений) → 4-way классификация + advisor-ответ → duplicate-check (только метка) → приоритет по формуле | ✅ Работает, прогнан вживую по реальному бэклогу (64/67 Issue размечено, 0 ошибочных закрытий) | `make dry-run` / `make backfill-one issue=N` |
| **Consolidation — группировка бэклога в зоны поставки** (taxonomy-first): профиль на Issue → вывод 8–12 зон → классификация Issue в зону → нарезка зоны на инкременты (MVP/MVP+1) → объединяющий Issue на инкремент → **PR** | ✅ Работает, прогнан вживую (8 зон, 19 инкрементов, PR с 20 файлами). ⚠️ см. «Ограничения» | `make consolidate` |
| **`/estimate` — оценка трудоёмкости Issue** по методологии (тип работы → декомпозиция → FP cross-check → PERT → риски/надбавки → sanity bounds → грейды → Story Points), обоснование комментарием | ✅ Работает, прогнано вживую через webhook | комментарий `/estimate` в Issue |
| **Layer B — webhook-автостарт** на новых Issue (GitHub App) | ⚙️ Код есть (`webhook/`), требует регистрации App + публичного URL | см. «Установка Layer B» |
| **Тяжёлые стадии** `run_research_pipeline` / `run_bug_pipeline` (БФТ/Blueprint/SA-helper через `claude -p`) | ❌ `NotImplementedError` — не реализовано | — |
| **Доставка скиллов po-helper/SA-helper в воркер**, установка `deb8flow` | ❌ Не решено (`worker/Dockerfile` — TODO) | — |
| **OpenHands resolver** | ❌ `NotImplementedError`, намеренно вне этого compose | — |

Тесты: `make test` — **32 теста**.

---

## Быстрый старт (Layer A — триаж)

Прогнать триаж по всем открытым Issue репозитория, без GitHub App и публичного
webhook:

```bash
make setup     # preflight (docker/uv/gh) + venv + генерация .env (интерактивно)
make up        # поднять worker (Temporal — централизованный, TEMPORAL_ADDRESS в .env)
make dry-run   # прогнать ВСЕ открытые Issue в DRY_RUN — ничего не мутируется
```

Temporal — **внешний**: `docker-compose.yml` поднимает только `webhook`+`worker`,
никаких `postgres`/`temporal`/`temporal-ui`. Адрес и namespace задаются через
`TEMPORAL_ADDRESS` и `TEMPORAL_NAMESPACE` в `.env`. Нужен локальный Temporal для
офлайн-разработки — `make up-local` наложит override `docker-compose.local.yml`
(поднимет локальный стек, UI на http://localhost:8080, и сам переключит приложение
на него; `.env` для этого править не нужно).

`make setup` спросит целевой репозиторий, возьмёт GitHub-токен из авторизованного
`gh`, запросит `ZAI_API_KEY`, запишет `.env` с `DRY_RUN=1`. Смотри `[DRY_RUN]`-строки
в `make logs`, затем:

```bash
make go-live   # выключить DRY_RUN, перезапустить worker, прогнать по-настоящему
```

Точечно: `make backfill-one issue=<N>`. Повторный прогон идемпотентен
(`REJECT_DUPLICATE` по workflow-id); осознанный перепрогон — `scripts/backfill.py --suffix <tag>`.

Требования: Docker, [`uv`](https://astral.sh/uv), [`gh`](https://cli.github.com) (`gh auth login`).

### Что триаж делает с Issue

- Бот/security-подозрение → метка, дальше не идёт.
- Расплывчатый запрос → уточняющий вопрос (интерактивно) либо эскалация (batch).
- Классификация: `advisor:feature-request` / `advisor:bug` / `advisor:consultation` /
  `advisor:existing-functionality` + содержательный ответ комментарием.
- Дубликат: **только метка** `duplicate` / `possible-duplicate` + комментарий.
  **Issue НЕ закрывается автоматически** — решает человек (функциональный дубль ≠
  целевой, см. #111).
- Приоритет: LLM извлекает атрибуты → детерминированная формула из
  `config/priority-weights.toml` → метка `priority:*` + комментарий с разбором.
- Дальше workflow **паркуется** и ждёт сигнал `research-me` / `bug-me` (эти стадии
  пока не реализованы — см. таблицу выше).

---

## Consolidation — бэклог в зоны поставки

```bash
make consolidate   # или: scripts/consolidate.py --repo <owner>/<repo>
```

Группирует открытые Issue по **оси поставки** — «что реализуется и релизится
вместе одной технической итерацией», а не по похожести темы. Пайплайн:

1. `fetch_open_issues` — список Issue **без тел** (тело тянет профиль — держит историю лёгкой).
2. `extract_solution_profile` (fan-out) — на каждый Issue: суть проблемы, механизм, цель, домен, якоря-цитаты.
3. `derive_taxonomy` — один вызов на весь бэклог → **8–12 зон поставки** (имя, граница «что закрывает одна итерация», имплементационная поверхность).
4. `assign_zone` (fan-out, пер-Issue) — классификация в primary-зону (+ secondary для сквозных, `other` если не подходит ни одна).
5. `slice_zone` — крупную зону режет на **инкременты** (MVP/MVP+1/…) по зависимостям и потолку размера (~3–6 Issue). Внутри зоны разводит по разным инкрементам одинаковый функционал с разной целью (#111).
6. `synthesize_unifying_issue` — на инкремент: объединяющий Issue (синтез проблемы + механизм + агрегат требований, каждое подписано `— from #N`).
7. `write_consolidation_pr` — ветка `consolidation/<дата>` + **PR**: `docs/consolidation/overview.md` (карта зон и инкрементов) + файл на каждый объединяющий Issue.

**Consolidation НИКОГДА не трогает Issue** — не комментирует, не метит, не закрывает.
Единственная запись — ветка+PR, и та под `DRY_RUN`. Предлагает — решает человек.

Реальный прогон дал 8 зон (`memory-core`, `jira-connector`, `process-engine`,
`llm-routing`, `router`, `po-helper`, `ui-shell`, `ops-core`) и 19 инкрементов по
3–6 Issue.

---

## Ограничения (важно)

- **Большой бэклог не дорабатывает до PR в самом workflow.** На ~75 Issue история
  превышает ~990 событий, и реплей не укладывается в workflow-task timeout на
  стадии synth. Нужен `continue-as-new` после `derive_taxonomy` (не реализовано).
  Пока обход: снять посчитанные зоны/инкременты из истории Temporal и выполнить
  synth+PR отдельно.
- **Rate-limit z.ai** — главный потолок скорости. Воркер намеренно ограничен:
  `max_concurrent_activities=3` + `ThreadPoolExecutor(3)`. Полный прогон по ~75
  Issue занимает десятки минут.
- **Таксономия не версионируется**: `derive_taxonomy` вызывается с `prior=None`,
  temperature не фиксирована → зоны могут «плыть» между прогонами.
- **Activity — синхронные `def`** (исполняются в ThreadPoolExecutor). Делать их
  `async def` нельзя: блокирующий LLM-вызов на event-loop замораживает воркер.

---

## Архитектура

```
GitHub → webhook (FastAPI) → Temporal → worker (activities: GLM / gh / claude -p)
                          (централизованный, TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE)
```

Два workflow-типа на одной очереди `issue-lifecycle`:

- **`IssueLifecycle`** — один на Issue (id `issue-<repo>-<n>`). Лейблы
  `research-me`/`bug-me` и ответы-уточнения — это Temporal **signals**: workflow
  спит и ждёт сигнал сколько угодно долго.
- **`ConsolidationWorkflow`** — один на прогон консолидации, fan-out по бэклогу.

## Модель — GLM через z.ai

- Python-стадии (gate/classify/duplicate/priority/консолидация) — Instructor поверх
  OpenAI-совместимого эндпоинта z.ai (`worker/llm.py`). Дешёвая модель `MODEL_GATE`
  (по умолчанию `glm-4.5-air`), сильная `MODEL_CLASSIFY` (по умолчанию `glm-5.2`,
  переопределяется через `.env`).
- `claude -p` для скиллов po-helper/SA-helper — Anthropic-совместимый эндпоинт z.ai
  (`ANTHROPIC_BASE_URL`). Используется только тяжёлыми стадиями, которые пока не
  реализованы.

## Развёртывание как постоянного сервиса

`docs/DEPLOY-DOKPLOY.md` — self-hosted развёртывание на Dokploy: публичный
адрес с TLS для вебхука, Temporal переживает перезагрузку сервера, туннели с
ноутбука не нужны. Продакшн-compose — `docker-compose.dokploy.yml`; локальный
`docker-compose.yml` для этого не годится, он публикует наружу gRPC-API
Temporal и веб-интерфейс без аутентификации.

Для команды `/estimate` регистрация GitHub App не нужна: хватает вебхука
уровня репозитория и personal access token.

---

## Установка Layer B (webhook + GitHub App)

> Для Layer A и консолидации это НЕ нужно. App и публичный webhook требуются только
> чтобы **новые** Issue обрабатывались автоматически при создании.

1. Зарегистрировать GitHub App: permissions Issues (read/write), Contents
   (read/write); events Issues + Issue comments; webhook URL — публичный адрес
   сервиса `webhook` (локально — `cloudflared`/`ngrok`).
2. Установить App на репозиторий; сохранить App ID, Installation ID, `.pem`.
3. `.env.example` → `.env`, заполнить GitHub App + `ZAI_API_KEY`.
4. Положить `.pem` по пути `GITHUB_PRIVATE_KEY_PATH` (том/secret в
   `docker-compose.yml` явно не прописан — добавить под свою модель секретов).
5. `docker compose up --build`.

> Для команды `/estimate` App не обязателен: хватает вебхука уровня
> репозитория (событие `issue_comment`) и personal access token в `GH_TOKEN`.
> См. `docs/DEPLOY-DOKPLOY.md`.

---

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

---

## Почему Temporal

Durable execution: воркер упал посреди долгого прогона — Temporal продолжит с
последнего завершённого шага, а не начнёт заново. Тот же механизм даёт «ждать
сигнал сколько угодно»: Issue может неделями висеть с приоритетом в ожидании
`research-me` — это штатное состояние workflow, не хак.

## Документация

- `sa_documentation/FNR/` — постановки задач, концепты, дебаты и системные
  требования (FNR-1 тяжёлые стадии, FNR-3 кластеризация под поставку).
- `docs/consolidation-clustering-study.md` — почему группировка по «механизму»
  вырождается в одиночки и какие практики группировки применимы (с экспериментом).
- `docs/superpowers/specs/` и `docs/superpowers/plans/` — дизайн-спеки и планы
  реализации.
- `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`,
  `docs/diagrams/` — архитектура, журнал решений, план, диаграммы.
- `docs/demo-plan.md` — сценарий демонстрации с критериями приёмки.
