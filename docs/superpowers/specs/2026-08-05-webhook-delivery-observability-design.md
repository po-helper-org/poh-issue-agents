# Наблюдаемость доставки вебхуков — почему issue не доехал до Temporal

- **Дата:** 2026-08-05
- **Статус:** согласован, ожидает ревью спеки
- **Ветка:** `claude/fix-labeled-signal-with-start`
- **Затрагивает:** `webhook/main.py`, `worker/workflows.py`, `worker/worker.py`,
  `worker/github_client.py`, `shared/workflow_types.py`, `scripts/diag.py` (новый),
  `tests/` (три новых файла)

## Проблема

Issue [momento-box-org/mbox-checkout-service#2](https://github.com/momento-box-org/mbox-checkout-service/issues/2)
обработан не был: в Temporal UI по нему нет ни одного workflow, хотя по другим
репозиториям прогоны видны. Комментарии в issue оставлены от личного аккаунта
`kibarik`, а не от GitHub App.

Разведка показала, что переводить на Temporal нечего — код уже Temporal-native.
Все точки входа стартуют workflow: `webhook/main.py` (`issues.opened`,
`issues.labeled`, `/analyze`, `/estimate`), `scripts/backfill.py`,
`scripts/consolidate.py`, `scripts/estimate.py`. `IssueLifecycle` уже разбит на
отдельные activity (`prefilter_bot_and_security` → `intake_gate` →
`classify_issue` → `duplicate_check` → `score_priority` →
`post_priority_comment`) — структурно ровно то же, что даёт пер-стадийность
`/analyze` (см. `2026-07-24-analysis-pipeline-observability-design.md`).

Сломана **доставка**, и её отказ не оставляет следов. Три молчаливых пути:

| Что | Где | Симптом |
|---|---|---|
| Репозиторий вне `ISSUE_AGENT_REPOS` | `webhook/main.py:82-84` | лог уровня `info`, ответ `{"ok": true}` — GitHub видит успех, workflow не создаётся |
| `GH_TOKEN` перебивает GitHub App | `worker/github_client.py:92-99` | всё постится от владельца PAT, никакого сигнала о подмене |
| Конфиг задеплоенного сервиса | — | посмотреть неоткуда, только заходить в контейнер и читать окружение |

Отдельно: `IssueLifecycle` после приоритизации паркуется на
`_wait_for_signal()` без таймаута (`worker/workflows.py:233`). В UI такой прогон
висит `Running` бессрочно, и припаркованный в ожидании лейбла процесс
неотличим от зависшего.

Смежный баг того же класса уже исправлен в этой ветке (коммит `d28787e`):
`issues.labeled` слал голый `signal()` в возможно несуществующий workflow, что
роняло вебхук в 500 и убивало доставку лейбла. Переведён на signal-with-start.

## Цели

- Ответ на вопрос «почему этот issue не доехал» получается **одной командой**,
  без чтения окружения контейнера вручную.
- Событие, отброшенное из-за конфига, оставляет **след в Temporal UI** — там же,
  где пользователь смотрит всё остальное.
- Припаркованный workflow **отличим** от зависшего.

## Не-цели (осознанно вне охвата)

- Аудит комментариев ботов, необработанных `action`/`event` и сигналов в уже
  завершённый workflow. Это штатный высокочастотный шум; аудит утопил бы в нём
  настоящие прогоны — ровно та проблема, от которой уходили в `/analyze`.
- HTTP-эндпоинт диагностики. Вебхук публично доступен, а конфиг (список
  репозиториев, адрес кластера) — разведданные для постороннего. Решено: только
  CLI внутри контейнера.
- Починка конкретного задеплоенного окружения. Спека даёт инструмент диагноза;
  правка `.env` на сервере — отдельное действие оператора.
- Пер-стадийное дробление уже существующих activity `IssueLifecycle`. Они и так
  отдельные шаги Event History.

## Решения (зафиксированы с пользователем)

1. **Поверхность диагностики — CLI, не HTTP.** Ничего не торчит наружу.
2. **Аудит — только `repo_not_allowed`.** Единственный случай, когда событие
   пропадает из-за неверного конфига и узнать об этом неоткуда.
3. **Стадия — через query**, а не через дробление activity.

## Дизайн

### 1. `scripts/diag.py` — диагностика конфига

CLI, запускается внутри контейнера (`docker compose exec webhook python
scripts/diag.py`). Печатает эффективное состояние сервиса:

- `ISSUE_AGENT_REPOS`: сырое значение и результат разбора через
  `shared.repos.parse_repo_specs` — какие записи точные (`owner/repo`), какие
  маски (`owner/*`), пусто ли (= разрешено всё).
- Режим авторизации: `PAT` или `App`. Явное предупреждение, когда `GH_TOKEN`
  (или `GITHUB_TOKEN`) задан **одновременно** с `GITHUB_APP_ID` — это молча
  отключает App-путь. Одиночный `GH_TOKEN` — документированный dev-фолбэк, не
  ошибка, предупреждения не даёт.
- Temporal: `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_TLS` и реальная
  проверка связи (`connect_temporal` + `describe_namespace`).
- Заданы ли `GITHUB_WEBHOOK_SECRET` и `DRY_RUN`.

**Значения секретов не печатаются ни при каких условиях** — только «задан / не
задан». Это относится к `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`,
`GITHUB_PRIVATE_KEY_B64`, `ZAI_API_KEY`.

Флаг `--repo owner/name` отвечает на исходный вопрос напрямую: доедет это
репозиторий или отфильтруется, и по какой записи allowlist.

Exit code: `0` — конфиг рабочий; `1` — Temporal недостижим либо авторизация не
настроена вовсе (ни PAT, ни App).

### 2. Громкие логи вместо тишины

- `webhook/main.py`: отброшенный по allowlist репозиторий переезжает с `info` на
  `warning` и печатает вместе с собой текущий allowlist — строка лога должна
  сама говорить, что чинить.
- `webhook/main.py`: на старте один раз логируется эффективный конфиг
  (allowlist, режим авторизации, Temporal address/namespace). Секреты — не
  логируются.
- `worker/github_client.py`: предупреждение при реальном конфликте PAT + App
  (оба заданы). Один раз на процесс, не на каждый вызов.

### 3. `WebhookAudit` — след для молчаливых отбрасываний

Новый workflow. Стартует **только** на `repo_not_allowed`.

- **ID:** `webhook-drop-<delivery_id>`, где `delivery_id` — заголовок
  `X-GitHub-Delivery` (уникален на доставку). Ретрай GitHub упирается в
  `WorkflowAlreadyStartedError` и дублей не плодит.
- **Вход** (`WebhookAuditInput` в `shared/workflow_types.py`): `delivery_id`,
  `event`, `action`, `repo`, `reason`, `allowlist`.
- **Тело:** workflow не исполняет ни одной activity — завершается сразу. Его
  ценность в том, что вход виден в Temporal UI: это и есть запись «пришло,
  отклонено, вот причина и вот действовавший allowlist».
- Заголовок `X-GitHub-Delivery` отсутствует (ручной курл, тест) → аудит
  пропускается, обработка не падает.

Регистрируется в `worker/worker.py` рядом с остальными workflow.

### 4. Query «стадия» на `IssueLifecycle`

`@workflow.query def stage(self) -> str` возвращает текущую стадию. Значения — в
порядке прохождения `run()`:

`intake` (предфильтр и intake gate, включая цикл уточнений) → `classify` →
`duplicate-check` → `priority` → `awaiting-human-decision` → далее по решению
человека `analysis` либо `bug` → `awaiting-build-decision` → `done`.

Терминальные значения на ранних выходах: `spam`, `escalated`, `duplicate`,
`skipped` (предфильтр отсёк бота или security-sensitive issue), `answered`
(классификация закрыла issue содержательным ответом).

Поле `self._stage` обновляется перед соответствующим шагом `run()`. Query —
детерминированное чтение атрибута, побочных эффектов не имеет.

Закрывает пункт «внутри видны стадии прогресса» и снимает главную
двусмысленность: `awaiting-human-decision` явно говорит, что триаж закончен и
процесс ждёт человека, а не завис.

## Тестирование

- `tests/test_webhook_audit.py` — репозиторий вне allowlist порождает
  `WebhookAudit` с верной причиной и **не** порождает `IssueLifecycle`;
  разрешённый репозиторий порождает `IssueLifecycle` и **не** порождает аудит;
  отсутствие `X-GitHub-Delivery` не роняет обработку.
- `tests/test_diag.py` — разбор allowlist, вердикт `--repo`, обнаружение
  конфликта PAT + App, отсутствие значений секретов в выводе, коды возврата.
- `tests/test_workflow_lifecycle_stage.py` — query возвращает ожидаемую стадию
  на каждом шаге, включая `awaiting-human-decision` на парковке и терминальные
  значения ранних выходов (`spam`, `escalated`, `duplicate`, `skipped`,
  `answered`).

Существующий набор (214 тестов) обязан остаться зелёным.

## Риски

- **Шум аудита при чужом трафике.** Если на вебхук указывает App, установленный
  на много посторонних репозиториев, `repo_not_allowed` будет срабатывать часто.
  Смягчение: это и есть сигнал о неверной установке App, ровно то, что аудит
  должен показывать. Ретеншн Temporal подчистит записи сам.
- **Query добавляет состояние в workflow.** `self._stage` меняет только
  локальный атрибут и не влияет на детерминизм воспроизведения: значение
  выводится из той же последовательности шагов, что и раньше.

## Якоря

| Факт | Источник |
|---|---|
| Отбрасывание репо молчаливое | `webhook/main.py:82-84` |
| PAT перебивает App | `worker/github_client.py:92-99` |
| Парковка без таймаута | `worker/workflows.py:233` |
| Пер-стадийность `/analyze` как референс | `docs/superpowers/specs/2026-07-24-analysis-pipeline-observability-design.md` |
| Форматы allowlist | `shared/repos.py` |
| Переменные Temporal | `shared/temporal_client.py:4-9` |
| Лейбл-баг того же класса | коммит `d28787e` |
