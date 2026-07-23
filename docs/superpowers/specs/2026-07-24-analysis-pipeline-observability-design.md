# Прозрачность пайплайна /analyze — пер-стадийная видимость в Temporal

- **Дата:** 2026-07-24
- **Статус:** согласован (направление), ожидает ревью спеки
- **Ветка:** `claude/issue-agents-solution-generation-b6c73c`
- **Затрагивает:** `worker/activities.py`, `worker/workflows.py`, `tests/test_analysis_pipeline.py`, `tests/test_workflow_analysis.py`

## Проблема

`/analyze` выполняется одной Temporal-activity `run_analysis_pipeline` (worker/activities.py:459).
Внутри неё последовательно: clone → repomix → 5 стадий FNR (`task`, `concept`,
`debate`, `sysreq`, `validate`) → сбор артефактов → push ветки → один итоговый
комментарий. В Event History это **один бар** длиной до 4500с (75 мин). Единственный
сигнал прогресса — `activity.heartbeat(label)`, метки которого видны лишь в деталях
pending-activity, не в таймлайне.

Наблюдаемый эффект: активность «висит» несколько минут, и невозможно понять, на какой
стадии процесс, движется ли он вообще и что произвела каждая стадия. Пять вызовов
`claude -p` по z.ai/GLM, каждый до `CLAUDE_STAGE_TIMEOUT_SEC` (900с), — это медленно и
слепо. При сбое `RetryPolicy(maximum_attempts=1)` роняет весь прогон без указания
виноватой стадии.

## Цели

- Каждая стадия FNR — **отдельный шаг в Temporal Event History** с собственным таймингом.
- По шагу видно: имя стадии, успех/падение, длительность, имя и размер созданного артефакта.
- Застрявшая стадия падает по **своему** таймауту (а не прячется под общим 4500с) и
  называет себя в ошибке.

## Не-цели (осознанно вне охвата)

- Live-комментарий в GitHub-issue с чек-листом прогресса. (Рассматривалось, отклонено.)
- Стриминг рассуждений `claude -p` в реальном времени (`--output-format stream-json`).
- Превью содержимого артефактов в результате шага Temporal. Только имя + размер.
- Выживание прогона при рестарте контейнера воркера посреди стадий (см. «Риски» —
  это отдельный шаг «смонтировать том», не входит в v1).

## Решения (зафиксированы с пользователем)

1. **Поверхность прозрачности — Temporal UI, пер-стадийно.** Не GitHub-коммент, не стрим.
2. **Глубина вывода на стадию — статус + тайминг + артефакт** (имя + размер). Без превью
   и без полного содержимого в истории.

## Выбранный подход: A — стабильный рабочий каталог + fail-fast guard

Воркфлоу `IssueAnalysis` перестаёт звать один монолит и оркестрирует последовательность
activity. Все они работают с **детерминированным** путём рабочего каталога, выведенным из
`repo` + `issue_number`, вместо случайного `tempfile.mkdtemp`. На одном воркере
(`max_concurrent_activities=3`, одна реплика) все activity одного прогона попадают в один
контейнер, поэтому каталог, созданный `prepare_workspace`, виден последующим стадиям в
пределах жизни контейнера. repomix пакуется **один раз** — оптимизация сохраняется.

### Почему не B и не C

- **B (re-clone + repomix в каждой стадии, stateless):** даёт пер-стадийные шаги и
  масштабируемость, но платит 5× clone и **5× repomix** (repomix до `REPOMIX_TIMEOUT_SEC`
  = 600с). Прямо убивает «пакуем один раз». Держим как аварийный fallback, не как v1.
- **C (одна activity + прогресс через query/signal):** Event History остаётся одним баром —
  не даёт выбранной поверхности. Отклонено.

### Уточнение self-heal (отличие от первичного питча)

Первично предлагался self-heal через «пере-клон при пропаже каталога». Это ложное
спокойствие: без постоянного тома артефакты (`task.md`, `concept.md`, …) живут только в
эфемерном каталоге; при потере каталога re-clone даёт **свежий репозиторий без прежних
артефактов**, и стадия `concept` всё равно упадёт (нет `task.md`). Поэтому в v1 guard =
**fail-fast с внятным сообщением**, а не тихий пере-клон:

- Настоящее выживание рестарта даёт постоянный том (см. «Риски → Хардненинг»).
- Blast radius v1 при рестарте посреди прогона = ровно как сегодня (монолит с
  `maximum_attempts=1` тоже теряет всё и падает). Хуже не становится.

## Архитектура

### Константы и хелперы (worker/activities.py)

- `FNR_STAGE_NAMES = ("task", "concept", "debate", "sysreq", "validate")` — публичная
  константа, по которой итерирует воркфлоу (детерминированно; безопасно в sandbox).
- `_workspace_dir(analyze) -> Path` — детерминированный путь. База из
  `os.environ.get("ANALYSIS_WORKSPACE_ROOT")` или системного temp; подкаталог
  `analysis-<repo с '/'→'__'>-<issue>`. `clone_dir = <workspace>/repo`.
- `_fnr_stage(name, description) -> tuple[str, str | None]` — по имени возвращает
  `(prompt, expected_artifact)`. Извлекается из текущего `_fnr_stages` (список остаётся
  источником правды; добавляется поиск по имени).
- `_build_workspace(analyze) -> str` — снести прошлый остаток каталога, создать, clone,
  repomix. Возвращает `clone_dir`. Использует существующие `_clone_repo` (токен через
  `credential.helper`, не в argv) и `_run_repomix`.
- `_require_workspace(analyze, need_artifact=None) -> str` — guard стадии: каталог и
  repomix-выход на месте? нужный предшествующий артефакт на месте? иначе
  `RuntimeError("рабочий каталог потерян (рестарт воркера?) — повтори /analyze")`.
  Никакого тихого пере-клона.

### Activity (все — `async def`, heartbeat внутри долгих вызовов через `_run_with_heartbeat`)

| Activity | Делает | start_to_close | heartbeat | retry |
|---|---|---|---|---|
| `prepare_workspace(analyze)` | `_build_workspace` (clone + repomix) | 1000с | 300с | 2 |
| `run_fnr_stage(analyze, stage_name)` | guard → один `claude -p` → проверка ожидаемого артефакта → вернуть отчёт | 1200с | 300с | 1 |
| `publish_analysis(analyze)` | guard → собрать артефакты → push ветки `research/issue-N` → итоговый коммент | 120с | — | 3 |
| `cleanup_workspace(analyze)` | best-effort `rmtree` каталога | 60с | — | 1 |

- `run_fnr_stage` **возвращает** `{"stage": name, "artifact": <rel path|None>, "bytes": <int>}`.
  Статус (ok/fail) и длительность Temporal фиксирует сам в ActivityTask событиях. Для стадий
  без ожидаемого артефакта (`debate`, `validate`) — `artifact=None, bytes=0`.
- `retry=1` у стадий: `claude -p` мутирует файлы, не идемпотентно. `prepare` идемпотентна
  (сносит и строит заново) → `retry=2` на сетевые сбои клона.
- DRY_RUN не трогаем: `push_artifacts_to_branch` / `post_comment` уже гейтятся в
  `github_client`.

### Workflow (worker/workflows.py, `IssueAnalysis.run`)

```
ack_command                       (как сейчас: 60с, retry 3)
try:
    prepare_workspace
    for name in FNR_STAGE_NAMES:  # детерминированный цикл
        run_fnr_stage(analyze, name)
    publish_analysis              # возвращает ветку
except:                           # ActivityError → разворачиваем .cause (как сейчас)
    publish_analysis_error(analyze, reason[:500])   (60с, retry 3)
finally:                          # Temporal поддерживает try/except/finally в воркфлоу
    cleanup_workspace             # best-effort на обоих путях; провал не роняет исход
```

Итоговый Event History:

```
ack_command
prepare_workspace          clone + repomix
fnr_stage · task           → sa_documentation/FNR/FNR_1/task.md (N байт)
fnr_stage · concept        → concept.md
fnr_stage · debate         (дописано в concept.md)
fnr_stage · sysreq         → system_requirements.md
fnr_stage · validate       (отчёт)
publish_analysis           → research/issue-N + коммент
cleanup_workspace
```

`_build_summary`, `_collect_fnr_artifacts`, `_run_claude`, `_claude_anthropic_creds`,
`_run_with_heartbeat`, `_clone_repo`, `_run_repomix` — переиспользуются как есть.
Монолит `run_analysis_pipeline` удаляется (его роль берёт воркфлоу + новые activity).

## Обработка ошибок

- Падение любой стадии → `except` в воркфлоу → `publish_analysis_error` с развёрнутой
  `.cause` (текущее поведение сохранено). Теперь причина указывает конкретную стадию:
  `run_fnr_stage · concept` в Event History + текст `стадия concept: артефакт ... не создан`.
- Застревание → срабатывает `start_to_close` именно этой стадии (1200с), а не общий 4500с.
- `cleanup_workspace` best-effort: воркфлоу игнорирует её падение, чтобы не затирать
  реальный исход.

## План тестирования (TDD)

Паттерн воркфлоу-теста уже есть: `WorkflowEnvironment.start_time_skipping()` + `Worker` со
stub-activity (tests/test_workflow_analysis.py).

- **tests/test_analysis_pipeline.py** (переписать под новую структуру):
  - `prepare_workspace` строит каталог по детерминированному пути, чистит прежний остаток
    (mock `_clone_repo`/`_run_repomix`).
  - `run_fnr_stage("concept")` зовёт `_run_claude` с промптом `/fnr-concept …`, проверяет
    ожидаемый артефакт, возвращает `{stage, artifact, bytes}`.
  - guard `_require_workspace`: при отсутствии предшественника → `RuntimeError` с внятным
    сообщением (не пере-клон).
  - `publish_analysis`: собирает артефакты, push в `research/issue-5`, постит summary.
  - heartbeat идёт ВНУТРИ долгой стадии (сохранить текущий тест на `_run_with_heartbeat`).
  - блокирующие вызовы уходят с event-loop (сохранить тест на `to_thread`).
- **Регрессия токена сохраняется без изменений**: `_clone_repo` переиспользуется —
  `test_clone_failure_never_leaks_token_*` остаются валидны.
- **tests/test_workflow_analysis.py** (расширить):
  - happy-path: порядок вызовов `ack → prepare → task → concept → debate → sysreq →
    validate → publish → cleanup`.
  - падение стадии `sysreq` → `publish_analysis_error` вызван, стадии после неё не
    вызваны, `cleanup_workspace` вызван, `maximum_attempts=1` (одна попытка).
- Команда прогона (память проекта): `.venv/bin/python -m pytest` из корня b6c73c-воркта.

## Риски и компромиссы

- **Рестарт контейнера посреди прогона** теряет эфемерный каталог → прогон падает с
  внятным сообщением, человек повторяет `/analyze`. Blast radius = как сегодня.
- **Хардненинг (отдельный шаг, вне v1):** смонтировать постоянный `workspace`-том воркеру
  в `docker-compose.yml` (боевой compose сейчас тома НЕ монтирует). Тогда каталог и
  артефакты переживают рестарт, стадии дочитывают тёплый каталог, guard почти не
  срабатывает. Тянет за собой замену fail-fast на настоящий self-heal.
- **Горизонтальное масштабирование воркеров** (>1 реплики) сломает предположение «все
  activity в одном контейнере» — тогда обязателен сетевой том или подход B. Сейчас реплика
  одна; зафиксировать это допущение.
- **Больше событий в истории** (≈9 вместо ≈3) — незначительно, payload'ы крошечные
  (имена+размеры, не содержимое).

## Открытых вопросов нет.
