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
| **`/analyze` — автономный анализ Issue** (Слой C): клон репозитория → repomix → цепочка FNR через `claude -p` (`task → concept → debate → sysreq → validate`) → артефакты в ветку `research/issue-<n>` + итоговый комментарий | ✅ Работает | комментарий `/analyze` в Issue либо лейбл `research-me` |
| **Запуск команд метками** (`run:analyze` / `run:estimate` → прогон → `done:*` либо `failed:*`) — управление с телефона в два тапа и индикатор состояния в списке Issue | ✅ Работает | метка `run:<команда>` на Issue |
| **Layer B — webhook-автостарт** на новых Issue (GitHub App) | ⚙️ Код есть (`webhook/`), требует регистрации App + публичного URL | см. «Установка Layer B» |
| **Доставка скиллов po-helper/SA-helper в воркер** (`.claude/skills` + `.claude/commands` → `/root/.claude/`, `claude-code` и `repomix` в образе) | ✅ Решено в `worker/Dockerfile` | — |
| **Установка `deb8flow`** в образ воркера | ❌ Не решено (`worker/Dockerfile:15` — TODO) | — |
| **Тяжёлая стадия по багам** `run_bug_pipeline` (перенос `bug-pipeline.yml`) | ❌ `NotImplementedError` — не реализовано | — |
| **OpenHands resolver** | ❌ `NotImplementedError`, намеренно вне этого compose | — |

Тесты: **383 теста**, покрытие **88%**. Локально — `make test` (после `make setup`
цель зовёт `.venv/bin/pytest`), на каждый push и PR — GitHub Actions
(`.github/workflows/tests.yml`). Порог покрытия — `.coveragerc`, `fail_under = 83`:
он держит текущий уровень, чтобы тот не проседал незаметно, а не задаёт цель.

---

## Быстрый старт (Layer A — триаж)

Прогнать триаж по всем открытым Issue репозитория, без GitHub App и публичного
webhook:

```bash
make setup     # preflight (docker/uv/gh) + venv + генерация .env (интерактивно)
make up        # поднять worker (Temporal — централизованный, TEMPORAL_ADDRESS в .env)
make dry-run   # прогнать ВСЕ открытые Issue в DRY_RUN — ничего не мутируется
```

Три конфигурации compose (выбирается одна):

| Файл | Что | Temporal | Команда |
|------|-----|----------|---------|
| `docker-compose.yml` (**main**) | только приложение (`webhook`+`worker`) | внешний, `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE` в `.env` | `make up` |
| `docker-compose.local.yml` (**local**) | полный стек, порты 7233/8080 наружу, промпты монтируются | встроенный (`temporal:7233`, namespace `default`) | `make up-local` |
| `docker-compose.full.yml` (**full**) | полный стек, прод-hardened (Traefik, без публичных портов, `POSTGRES_PASSWORD`) | встроенный | `make up-full` / Dokploy |

`make up` (main) не поднимает ни одного лишнего контейнера — Temporal внешний.
В `local`/`full` Temporal встроенный, `.env` для него править не нужно.

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
- Дальше workflow **паркуется** и ждёт лейбл `research-me` / `bug-me`.
  `research-me` запускает ту же аналитику Слоя C, что и команда `/analyze`;
  `bug-me` пока `NotImplementedError` — см. таблицу выше.

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
- **LLM-стадии — синхронные `def`** (исполняются в ThreadPoolExecutor). Делать их
  `async def` нельзя, не вынеся блокирующий вызов: LLM-вызов прямо на event-loop
  замораживает воркер. Activity долгого анализа (`prepare_workspace`,
  `run_fnr_stage`, `publish_analysis`, …) — наоборот
  `async def`: им нужен heartbeat, а каждый блокирующий git/repomix/`claude -p`/REST
  внутри обёрнут в `asyncio.to_thread`, иначе heartbeat не уходит на сервер.

---

## Архитектура

```
GitHub → webhook (FastAPI) → Temporal → worker (activities: GLM / gh / claude -p)
                          (централизованный, TEMPORAL_ADDRESS/TEMPORAL_NAMESPACE)
```

Четыре workflow-типа на одной очереди `issue-lifecycle`
(`worker/worker.py`):

- **`IssueLifecycle`** — один на Issue (id `issue-<repo>-<n>`). Лейблы
  `research-me`/`bug-me` и ответы-уточнения — это Temporal **signals**: workflow
  спит и ждёт сигнал сколько угодно долго.
- **`IssueAnalysis`** — один на команду `/analyze` (id `analysis-<repo>-<n>`).
- **`IssueEstimation`** — один на команду `/estimate` (id включает `comment_id`).
- **`ConsolidationWorkflow`** — один на прогон консолидации, fan-out по бэклогу.

Агенты работают **в двух режимах** (#37): дочерним прогоном `IssueLifecycle`,
когда цикл жив, и самостоятельным — при автономном запуске (скрипты,
`make backfill-one`, прогон прежнего поколения). Код один и тот же, отличается
только родитель; id остаётся каноническим (`shared/workflow_ids.py`), поэтому
повторная команда упирается в `WorkflowAlreadyStarted` в обоих режимах.

### Путь Issue: от `issues.opened` до парковки

```mermaid
flowchart TD
    A["GitHub: issues.opened"] --> B{"HMAC подпись<br/>X-Hub-Signature-256"}
    B -->|invalid| B1["401"]
    B -->|ok| C{"repo в ISSUE_AGENT_REPOS?"}
    C -->|нет| C1["ok: true, игнор"]
    C -->|да| D["start_workflow IssueLifecycle<br/>id = issue-repo-N"]

    D --> E["1. prefilter_bot_and_security<br/>без LLM"]
    E -->|Bot / dependabot / renovate| E1["метка bot-authored"] --> STOP1(["СТОП"])
    E -->|"CVE / RCE / уязвимост"| E2["комментарий + security-sensitive"] --> STOP1

    E -->|ok| F["2. intake_gate<br/>MODEL_GATE"]
    F -->|SPAM| F1["метка spam + close_issue"] --> STOP1
    F -->|"VAGUE, interactive=false"| F2["escalate_to_human<br/>needs-human-triage"] --> STOP1
    F -->|VAGUE| G["post_clarifying_question<br/>метка needs-clarification"]

    G --> H(["ПАРКОВКА<br/>await signal_queue.get"])
    H -.->|"issue_comment.created<br/>signal user_comment"| I{"round_count > 2?"}
    I -->|да| F2
    I -->|нет| F

    F -->|SUFFICIENT| J["3. classify_issue<br/>MODEL_CLASSIFY + capabilities.md<br/>постит ответ комментарием"]
    J -->|"advisor:existing-functionality"| STOP2(["СТОП: закрыт ответом"])
    J -->|"advisor:consultation"| STOP2
    J -->|"advisor:bug / advisor:feature-request"| K["4. duplicate_check<br/>search_candidates + LLM"]

    K -->|"p >= 0.85"| K1["метка duplicate + комментарий<br/>issue НЕ закрывается"] --> STOP3(["СТОП: решает человек"])
    K -->|"0.5 <= p < 0.85"| L["метка possible-duplicate"]
    K -->|"p < 0.5"| L2[" "]
    L --> M
    L2 --> M

    M["5. score_priority<br/>LLM извлекает атрибуты"] --> N["формула из priority-weights.toml<br/>score = CoD × okr_mult / effort"]
    N --> O["post_priority_comment<br/>метка priority:P0..P3"]

    O --> P(["ПАРКОВКА №1<br/>ждём лейбл, без таймаута"])
    P -.->|"issues.labeled<br/>signal-with-start"| Q{"лейбл vs тип"}
    Q -->|"research-me + feature-request"| R["пер-стадийный прогон FNR<br/>тот же, что у /analyze"]
    Q -->|"bug-me + advisor:bug"| R2["run_bug_pipeline<br/>NotImplementedError"]
    Q -->|не совпал| STOP4(["СТОП"])

    R --> S(["ПАРКОВКА №2"])
    R2 --> S
    S -.->|build-me| T["trigger_openhands_resolver<br/>NotImplementedError"]

    E -.->|"любое исключение"| ERR["post_error_label<br/>метка advisor:error + Sentry"]
    F -.-> ERR
    J -.-> ERR
    K -.-> ERR
    M -.-> ERR
```

Ключевое: `issues.labeled` доставляется через **signal-with-start**, а не голый
signal — Issue мог быть заведён до установки App, воркфлоу триажа не существует,
и голый signal дал бы 500, после чего GitHub бросил бы доставку.

### Команды в комментариях — отдельные workflow

Триаж завершается после приоритизации (а на спаме и дубликате — раньше), поэтому
`/analyze` и `/estimate` — не сигналы в `IssueLifecycle`, а самостоятельные
воркфлоу со своими id.

```mermaid
flowchart TD
    A["issue_comment.created"] --> B{"user.type == Bot?"}
    B -->|да| B1["игнор: не сигналим сами себе"]
    B -->|нет| C{"parse_command"}

    C -->|"/estimate"| D["signal estimate_requested<br/>цикл поднимает child<br/>id включает comment_id"]
    D --> D1["ack_estimate_command"] --> D2["collect_estimation_context"] --> D3["extract_estimation_facts<br/>LLM"] --> D4["compute_estimate<br/>детерминированный, attempts=1"] --> D5["post_estimate_comment"]
    D1 -.->|fail| DE["post_estimate_error<br/>с именем стадии"]
    D2 -.-> DE
    D3 -.-> DE
    D4 -.-> DE
    D5 -.-> DE

    C -->|"/analyze"| E["signal analyze_requested<br/>в IssueLifecycle"]
    E --> F["child IssueAnalysis<br/>id = analysis-repo-N<br/>фаза → business-analysis"]
    F --> F1["ack_command"] --> F2["prepare_workspace<br/>clone + repomix"] --> F3["цикл run_fnr_stage<br/>по FNR_STAGE_NAMES<br/>attempts=1 на стадию"] --> F4["publish_analysis"]
    F2 -.->|fail| FE["publish_analysis_error"]
    F3 -.-> FE
    F4 --> FIN["finally: cleanup_workspace<br/>best-effort"]
    FE --> FIN

    C -->|обычный текст| G["signal user_comment<br/>в IssueLifecycle"] --> G1["кормит цикл уточнений intake gate"]
```

### Запуск командой из метки — `run:*` → `done:*` / `failed:*`

У каждой команды два равноправных триггера: комментарий (`/analyze`) и метка
(`run:analyze`). Метка ставится в два тапа из мобильного GitHub и не требует
ввода текста, поэтому это основной способ управления с телефона.

| Поставить | Что запускает | Чем закончится |
|---|---|---|
| `run:analyze` | `IssueAnalysis` — то же, что `/analyze` (дочерним прогоном цикла) | `done:analyze` либо `failed:analyze` |
| `run:estimate` | `IssueEstimation` — то же, что `/estimate` (дочерним прогоном цикла) | `done:estimate` либо `failed:estimate` |

Метка `run:*` снимается по завершении прогона, исход вешается своей меткой.
Неуспех получает `failed:*`, а не просто снятый `run:*`: молча снятая метка
неотличима от «никто не запускал». Заодно снимается легаси-метка `analyzing`.

Это и индикатор состояния прямо в списке Issue, без открытия каждого:

```
label:run:*    — что сейчас в работе у агента
label:done:*   — что проработано
label:failed:* — где прогон сорвался
```

Метку ставит и сам прогон, запущенный командой в комментарии, — иначе выборка
`label:run:*` врала бы. Ветка `research-me` помечается так же (`run:analyze`).

Схема имён — namespace через двоеточие, как в протоколе агентов v1
(`needs-human:*`, `origin:agent`). Метки исхода агент ставит себе сам, они
возвращаются событием `issues.labeled` и **не** совпадают ни с одним триггером —
на этом и держится защита от петли: запускает только `run:<команда>`.

Повторная постановка `run:*` на идущем прогоне упирается в
`WorkflowAlreadyStarted` и второго дорогого прогона не создаёт; после
завершённого — запускает честно новый. Прежние `research-me` / `bug-me` /
`build-me` работают как раньше.

**Авторизации пока нет:** метку может поставить любой с правами на репозиторий,
а прогон стоит токенов — allowlist по `sender.login` отслеживается в
[#7](https://github.com/po-helper-org/poh-issue-agents/issues/7).

## Живая проверка контура

Тесты замыкают сеть на заглушки и потому не отвечают на вопросы, которые ломаются
в проде: доезжает ли вебхук, входит ли репозиторий в `ISSUE_AGENT_REPOS`, отвечает
ли кластер, работает ли ключ модели. На это отвечает живой прогон — ценой реальных
токенов.

```bash
docker compose exec worker python scripts/e2e_live.py triage
docker compose exec worker python scripts/e2e_live.py label-command
```

Запускать **внутри контейнера**: скрипту нужны те же креды и та же сеть, что и
сервису. Репозиторий — `--repo`, иначе `E2E_REPO`, иначе `GITHUB_REPOSITORY`.

| Сценарий | Что проверяет | Признак успеха |
|---|---|---|
| `triage` | Воркер, активности, модель, запись в GitHub. Стартует воркфлоу напрямую в Temporal, как `backfill` | появились `advisor:*` и `priority:*` |
| `label-command` | **Доставку вебхука** целиком: метка → событие → воркфлоу → обратный ход меток | появилась `done:estimate`, снята `run:estimate` |

Скрипт заводит свой служебный Issue, наблюдает за ним и закрывает (`--keep`
оставляет открытым). Существующие задачи не трогаются. Прогон прекращается
досрочно, если появилась метка неуспеха (`failed:*`, `advisor:error`) — ответ уже
получен. Коды возврата: `0` — контур отработал, `1` — ожидания не выполнены за
таймаут, `2` — ошибка конфигурации (нет репозитория, включён `DRY_RUN`, не
отвечает Temporal).

## Диагностика: почему issue не доехал

Событие может пропасть молча — репозиторий вне `ISSUE_AGENT_REPOS` отбрасывается
до старта workflow, а `GH_TOKEN` незаметно подменяет GitHub App личным
аккаунтом. Снаружи оба случая выглядят одинаково: GitHub получает 200, в
Temporal пусто.

```bash
docker compose exec webhook python scripts/diag.py                   # весь конфиг
docker compose exec webhook python scripts/diag.py --repo owner/name # доедет или нет
```

Скрипт печатает действующий allowlist и результат его разбора, режим авторизации
(с явным предупреждением, когда PAT перебивает настроенный App), адрес и
namespace Temporal с реальной проверкой связи. **Значения секретов не печатаются
никогда** — только «задан / не задан». Код возврата: `0` — конфиг рабочий, `1` —
Temporal недостижим либо авторизация не настроена вовсе.

Запускать нужно ВНУТРИ контейнера: снаружи прочитается окружение хоста, а не
сервиса. Тот же конфиг вебхук логирует одной строкой на старте.

Что ещё видно без захода в контейнер:

- **Отброшенная доставка** оставляет след в Temporal — воркфлоу
  `webhook-drop-<delivery-id>` с причиной и действовавшим allowlist. Это
  единственный молчаливый отказ, о котором иначе неоткуда узнать.
- **Стадия триажа** доступна query `stage` на `IssueLifecycle` (вкладка Queries):
  `intake` → `classify` → `duplicate-check` → `priority` →
  `awaiting-human-decision` → `analysis`/`bug` → `awaiting-build-decision` →
  `done`; ранние выходы — `skipped`, `spam`, `escalated`, `answered`,
  `duplicate`, `failed`, `agents-off`. Припаркованный прогон теперь отличим от
  зависшего.

## Фазы жизненного цикла Issue

`shared/lifecycle.py` — единственный источник правды о состоянии Issue: перечень
фаз, таблица переходов и инициатор каждого перехода. Из него выводятся значения
query, метки `phase:*`, search attribute и строки таймлайна. Модуль чистый — ни
сети, ни Temporal, как `estimation.py`.

Основной путь: `created` → `classified` → `business-analysis` →
`system-requirements` → `groomed` → `ready-for-dev` → `in-development` →
`pr-open` → `pr-review` → `merged` → `testing` → `released`. Путь бага короче —
из `classified` сразу в `ready-for-dev`, мимо аналитики.

Боковые состояния — `spam`, `duplicate`, `answered`, `skipped`, `escalated`,
`failed` — **не тупики**: человек возвращает Issue в работу явным переходом.
Терминальны только `released` и `cancelled`.

У каждого перехода записан инициатор: `agent`, `human` или `external` (PR-Agent,
PR-Closer, CI). «Ждём агента» и «ждём человека» — разные состояния для того, кто
смотрит на очередь. Недопустимый переход — `InvalidTransition` с перечнем того,
что было возможно, а не молчаливая перезапись.

Инвариант: одна фаза — ровно одна метка `phase:*`; при переходе предыдущая
снимается (`set_phase`). Две метки фазы означали бы противоречие, и
`phase_from_labels` отказывается угадывать.

### Цикл как владелец состояния

`IssueLifecycle` — не линейный сценарий, а цикл поверх таблицы переходов: пока
фаза не терминальна, прогон жив. Это меняет два свойства контура.

**Боковой исход перестал быть концом.** Раньше `spam`, `duplicate`, `answered`,
`skipped` и сбой стадии завершали воркфлоу — вернуть Issue в работу было не
у кого просить: сигналить некому. Теперь это фазы, из которых сигнал `reopen`
(лейбл человека) ведёт обратно в основной путь первым допустимым переходом.
Ожидание тоже ограничено сроком (`PARK_SIDE_STATE_HOURS`) — «не тупик» не
означает «вечная сессия».

**История обрывается по порогу.** На активном Issue цикл живёт неделями, и
Event History упёрлась бы в тот же потолок, который уже словила консолидация
(~990 событий на ~75 Issue — реплей не укладывается в workflow-task timeout).
Достигнув `HISTORY_EVENT_THRESHOLD` событий, цикл делает `continue_as_new` в
точке смены фазы — там, где состояние согласовано и незавершённой работы нет.
Переносится компактный снимок (`LifecycleState`: фаза, стадия, приоритет,
классификация), а не тред и не история. Сколько раз цикл перезапускался, видно
в query `generation`: без него по одной истории нельзя отличить новый Issue от
продолжения старого.

**Поколения разведены `workflow.patched("issue-lifecycle-phase-loop")`.**
Прогоны, запущенные до этого изменения, припаркованы в проде; их история не
знает маркера, поэтому они доигрывают по прежнему линейному коду
(`_run_linear`). Реплей старой истории новым кодом означал бы отказ по
недетерминизму. Линейный путь удаляется только когда прогоны того поколения
закончатся — через `workflow.deprecate_patch`.

Query `phase` отдаёт фазу цикла напрямую; для прогонов прежнего поколения она
по-прежнему выводится из стадии через `STAGE_TO_PHASE`.

### Агенты как дочерние прогоны

`shared/agent_launcher.py` — единственное место, где решается, как запускать
агента. Решение не «описать воркфлоу и посмотреть статус» (лишний round-trip и
гонка между проверкой и стартом), а **всегда signal-with-start в цикл**: он
либо получает команду, либо поднимается тем же вызовом, а дальше сам решает,
поднимать ли дочерний прогон.

Остаётся один случай, который цикл обслужить не может: прогоны прежнего
поколения. Их история не знает ни фазового цикла, ни сигнала на запуск агента —
команда была бы принята и потеряна. Их отличает query `handles_agents`; для них
лаунчер стартует самостоятельный прогон, как раньше. Ветка исчезнет сама, когда
прогоны того поколения завершатся.

Дорогие прогоны запускаются с `ParentClosePolicy.ABANDON`: цепочка FNR идёт до
4500 с, и ни `continue-as-new` родителя, ни его завершение не должны обрывать её
по причине, к ней не относящейся.

Аналитика двигает фазу (`business-analysis` → `system-requirements`), если из
текущей фазы такой ход есть по таблице переходов. Если нет — задача уже у
разработчика или Issue в боковом состоянии, — команда всё равно выполняется, но
фаза не трогается: соврать про состояние хуже, чем не отразить в нём разовый
прогон. Оценка фазу не двигает никогда: это боковая команда, а не стадия пути.

Очередь у всех прогонов по-прежнему одна (`issue-lifecycle`,
`max_concurrent_activities=3`): дочерний прогон наследует очередь родителя, и по
сравнению с прежним поведением — когда цикл гонял те же стадии сам —
конкуренция не изменилась. Выделенная очередь под тяжёлые прогоны остаётся
отдельной задачей.

**Сигнал поднимает цикл.** Все командные входы идут через signal-with-start:
метки решения (`research-me`/`bug-me`/`build-me`) и `/analyze`. Команда по
Issue, у которого цикла не было — заведён до установки App, триаж прогнали мимо
Temporal, — больше не теряется молча. Обычный комментарий остаётся исключением
и работает best-effort: он не проходит гейт на дорогую стадию, и поднимать им
триаж означало бы веер LLM-прогонов на любой реплике в старом Issue.

## Протокол агентов v1

Issue-Agent — узловой сервис контура (Issue-Agent → PR-Agent → PR-Closer), и
часть словаря меток общая на всю организацию. Источник:
[AGENT-PROTOCOL.md](https://github.com/po-helper-org/.github/blob/main/AGENT-PROTOCOL.md).
Правило протокола — **одна метка, один писатель**: чужую метку агент только читает.

| Метка | Пишет | Что делает Issue-Agent |
|---|---|---|
| `agents:off` | человек | Останавливается **до первого вызова LLM**: триаж, `/analyze` и `/estimate` не стартуют (R4) |
| `origin:agent` | любой агент | Сокращённый триаж: пропускает intake gate и advisor-ответ, оставляет дедуп и приоритет (R6) |
| `needs-human:triage` | Issue-Agent | Очередь к человеку. Было `needs-human-triage` — приведено к общему префиксу |
| `ready-for-dev` | Issue-Agent | Точка передачи разработчику (H1): выборка `label:ready-for-dev` — его рабочая очередь |

**Потолок глубины (R7).** Follow-up несёт в теле строку `root-issue: #N`. Если у
родителя тоже стоит `origin:agent`, цепочка пошла на второй круг — Issue уходит
человеку без единой дорогой стадии. Иначе контур начинает кормить себя сам:
каждый PR рождает Issue, каждый Issue — PR. Родитель читается только у Issue от
агента; для обычной задачи это был бы лишний вызов GitHub на каждом прогоне.

**Дедлайн на каждой парковке (R3).** Ожидание `research-me`/`bug-me`, ответа на
уточняющий вопрос и `build-me` ограничено по времени (`PARK_*_HOURS` в `.env`).
По истечении Issue получает `needs-human:triage` с объяснением, сколько ждали и
как запустить прогон заново, и уходит в фазу `escalated`. Оттуда его возвращает
`reopen`, а если и этого не случилось за `PARK_SIDE_STATE_HOURS` — сессия
закрывается: иначе забытый Issue держал бы воркфлоу вечно, и список открытых
прогонов рос бы монотонно.

**Передача разработчику (H1).** После успешной аналитики по `research-me` сервис
ставит `ready-for-dev` и публикует чеклист готовности: что известно (приоритет,
дубли, ветка с артефактами), с чего начать и **что осталось неопределённым** —
строки с маркером `[УТОЧНИТЬ]` вычитываются из самих артефактов. Незакрытые
вопросы видны до того, как задачу взяли, а не в середине реализации. На
сорвавшемся анализе метка не ставится: передавать нечего.

Всё состояние читается **одним вызовом на старте** (R2) — сервис не полагается
на порядок вебхуков и не хранит предположений о том, чего не проверил сам.

Провенанс на своих артефактах (R6): PR консолидации помечается `origin:agent`.
Issue этот сервис не создаёт, поэтому больше помечать нечего — follow-up Issue
заводит PR-Closer (точка передачи H5), он же ставит `root-issue`.

## Кто вправе запускать дорогие стадии

`AGENT_TRIGGER_ALLOWLIST` — comma-separated GitHub-логины. Пусто = разрешено
всем (поведение по умолчанию). Проверяется автор события (`sender.login`), а не
факт наличия метки: `run:analyze` может поставить любой с правами на
репозиторий, а прогон стоит токенов. Гейт закрывает метки `run:*`,
`research-me`/`bug-me`/`build-me` и команды `/analyze`, `/estimate`; **триаж
новых Issue открыт для всех** — иначе Issue от постороннего просто не
обработается. Кто запустил дорогую стадию, видно в логе вебхука.

## Модель — GLM через z.ai

- Python-стадии (gate/classify/duplicate/priority/консолидация) — Instructor поверх
  OpenAI-совместимого эндпоинта z.ai (`worker/llm.py`). Дешёвая модель `MODEL_GATE`
  (по умолчанию `glm-4.5-air`), сильная `MODEL_CLASSIFY` (по умолчанию `glm-5.2`,
  переопределяется через `.env`).
- `claude -p` для скиллов po-helper/SA-helper — Anthropic-совместимый эндпоинт z.ai
  (`ANTHROPIC_BASE_URL`). Используется стадиями FNR в `/analyze` — по одному
  вызову `claude -p` на стадию.

## Наблюдаемость — Sentry

`shared/sentry_setup.py`, включается переменной `SENTRY_DSN` (пусто — полный
no-op, это же и процедура отката). Плюс `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`,
`SENTRY_TRACES_SAMPLE_RATE` — см. `.env.example`.

Ловит не падение процесса, а главный класс сбоя этого стека — **пойманный** сбой,
который иначе виден только комментарием в Issue: триаж упал и повесил
`advisor:error`, `/estimate` упал на стадии. События приходят с тегами
service/repo/issue/stage.

Два ограничения, которые нельзя нарушать при правках:
- модуль зовётся только из entrypoint'ов (`worker.py`, `webhook/main.py`) и из
  activity — **никогда** из workflow-кода: сетевой вызов там недетерминирован и
  ломает replay;
- скраббер `_scrub_event` вырезает значения локальных переменных по денилисту имён
  до отправки — через этот код ходят `ZAI_API_KEY`, GitHub-токен и
  `GITHUB_PRIVATE_KEY_B64`.

## Развёртывание как постоянного сервиса

`docs/DEPLOY-DOKPLOY.md` — self-hosted развёртывание на Dokploy: публичный
адрес с TLS для вебхука, туннели с ноутбука не нужны. Продакшн-compose —
`docker-compose.full.yml` (**full**, встроенный Temporal) либо
`docker-compose.yml` (**main**, внешний централизованный Temporal).

Для команды `/estimate` регистрация GitHub App не нужна: хватает вебхука
уровня репозитория и personal access token.

---

## Установка Layer B (webhook + GitHub App, мультирепо)

> Для Layer A и консолидации это НЕ нужно. App и публичный webhook требуются только
> чтобы **новые** Issue, лейблы-решения (`research-me`/`bug-me`/`build-me`) и
> команды `/analyze` и `/estimate` обрабатывались автоматически.

Модель мультирепо — как в `poh-pr-agents`: устанавливаешь App на репозитории,
задаёшь 4 переменные, указываешь **вебхук самого App** (не пер-репо hooks).
Сервис отслеживает репозитории из `ISSUE_AGENT_REPOS` (installation находится
по репозиторию автоматически, `GITHUB_INSTALLATION_ID` не нужен).

1. **Зарегистрировать GitHub App** — `github.com/settings/apps/new` (личный
   App) либо `github.com/organizations/<org>/settings/apps/new` (org-level,
   если App должен ставиться на репозитории конкретной организации).
   - Permissions: **Issues** (read/write), **Pull requests** (read/write),
     **Contents** (read/write).
   - Webhook events: **Issues**, **Issue comments**.
   - Webhook URL — публичный адрес сервиса `webhook` (локально —
     туннель `cloudflared`/`ngrok`).
   - Webhook secret — сгенерировать: `openssl rand -hex 32`. Это же значение
     пойдёт в `GITHUB_WEBHOOK_SECRET`.
2. **Установить App** на нужные репозитории (Install App → выбрать owner →
   выбрать репозитории или "All repositories").
3. **Скачать приватный ключ** App (.pem, кнопка "Generate a private key" в
   настройках App) и закодировать в base64 одной строкой:
   ```bash
   # Linux (GNU coreutils)
   base64 -w0 github-app-private-key.pem
   # macOS (BSD base64 — флага -w нет)
   base64 -i github-app-private-key.pem | tr -d '\n'
   ```
4. **`.env`** — задать 4 переменные:
   ```env
   GITHUB_APP_ID=<App ID из настроек App>
   GITHUB_PRIVATE_KEY_B64=<вывод base64 из шага 3>
   GITHUB_WEBHOOK_SECRET=<секрет из шага 1>
   ISSUE_AGENT_REPOS=owner/repo,owner2/*
   ```
   Форматы `ISSUE_AGENT_REPOS` (comma-separated): `owner/repo` — конкретный
   репозиторий; `owner/*` или голый `owner` — все репозитории owner'а; `*`
   или пусто — любой установленный. Плюс `ZAI_API_KEY`, если ещё не задан.

   > **Важно:** `github_client` предпочитает PAT (`GH_TOKEN`), если он
   > задан, — тогда блок GitHub App игнорируется целиком. Если раньше был
   > настроен Layer A (`GH_TOKEN`/`GITHUB_REPOSITORY`), очисти `GH_TOKEN=`
   > в `.env`, иначе App-путь не заработает.
5. `docker compose up --build` (или Redeploy, если сервис уже развёрнут на
   Dokploy — см. `docs/DEPLOY-DOKPLOY.md`).

> Dev-фолбэк на один репозиторий без App: `GH_TOKEN` (PAT со scope `repo`) +
> вебхук уровня репозитория. См. `docs/DEPLOY-DOKPLOY.md`.

---

## Автономный анализ — команда `/analyze` (Слой C)

Комментарий `/analyze` в Issue (или лейбл `research-me` на Issue с типом
`advisor:feature-request`) запускает воркфлоу `IssueAnalysis`. Что происходит:

1. `ack_command` — 👀 на комментарий с командой; в идущий воркфлоу триажа уходит
   сигнал, который вешает метку `analyzing`.
2. `prepare_workspace` — клон целевого репозитория во временный каталог и упаковка
   его в один файл через `repomix`.
3. Цепочка FNR через `claude -p`, каждая стадия — **отдельная activity** со своим
   таймаутом и своим шагом Event History:
   `task → concept → debate → sysreq → validate`
   (артефакты в `sa_documentation/FNR/FNR_1/`). Стадия не ретраится
   (`maximum_attempts=1`): прогон дорогой и недетерминированный, повтор инициирует
   человек.
4. `publish_analysis` — артефакты пушатся в ветку `research/issue-<n>`, в Issue
   уходит итоговый комментарий со списком файлов.
5. `cleanup_workspace` в `finally` — рабочий каталог сносится на обоих путях.

Падение любой стадии → `publish_analysis_error`: комментарий с названием стадии и
причиной, а не молчаливый обвал. Повторный `/analyze` по тому же Issue упирается в
`WorkflowAlreadyStarted` (id `analysis-<repo>-<n>`) — второго прогона не будет.

Требования: в образе воркера должны быть `claude-code`, `repomix` и `gh` — они
ставятся в `worker/Dockerfile`, скиллы SA-helper копируются в `/root/.claude/`.

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

Прогнать оценку **без Layer B** (вебхука и GitHub App): `scripts/estimate.py`
стартует тот же воркфлоу напрямую в Temporal — нужен только поднятый `worker`.

```bash
python scripts/estimate.py --issue 83                        # DRY_RUN, реакция только в лог
python scripts/estimate.py --issue 83 --comment-id 2145678901  # реальный прогон
```

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
