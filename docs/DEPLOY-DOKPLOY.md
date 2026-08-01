# Развёртывание на Dokploy

Инструкция поднимает сервис как постоянно работающий self-hosted: GitHub шлёт
вебхуки на публичный адрес с TLS, команда `/estimate` в комментарии Issue
работает без туннелей на ноутбуке.

Compose-файл — `docker-compose.full.yml` (конфигурация **full**): поднимает
полный стек со **встроенным** Temporal (`postgres` + `temporal` + `temporal-ui` +
`webhook` + `worker`). Сервис самодостаточен и не зависит от внешнего Temporal —
это и есть смысл прод-варианта. Наружу выставлен только `webhook` (через Traefik
самого Dokploy, с TLS), инфраструктурные порты не публикуются.

> **Альтернатива — конфигурация main** (`docker-compose.yml`): то же приложение,
> но против ВНЕШНЕГО централизованного Temporal (`TEMPORAL_ADDRESS` /
> `TEMPORAL_NAMESPACE` в Environment), без встроенного `postgres`/`temporal`.
> Выбирай её, если в инфраструктуре уже есть централизованный Temporal-кластер.
> Тогда Compose Path — `docker-compose.yml`, а из переменных ниже вместо
> `POSTGRES_PASSWORD` задай `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`.

## Что понадобится

- Сервер с установленным Dokploy и доменом, направленным на его адрес.
  Сборка образа воркера — самый тяжёлый момент развёртывания: в нём ставятся
  Node.js, GitHub CLI и Claude Code. На инстансе с 1 ГБ памяти сборка,
  скорее всего, не пройдёт; закладывай запас или собирай образ отдельно.
- Поддомен под вебхук, например `issue-agent.example.com`.
- Personal access token GitHub со scope `repo`. Проще, чем GitHub App:
  `github_client` предпочитает токен, если он задан, и приватный ключ App
  тогда не нужен вовсе.
- Ключ к модели (`ZAI_API_KEY`).

## Шаг 1. Создать Compose-приложение

В Dokploy: **Create Service → Compose**.

- **Provider** — Git, репозиторий `po-helper-org/poh-issue-agents`, нужная
  ветка.
- **Compose Path** — `docker-compose.full.yml` (или `docker-compose.yml` для
  варианта main с внешним Temporal).
- **Compose Type** — `docker-compose`, не `stack`. Режим Docker Stack не
  поддерживает директиву `build`, а оба образа собираются из исходников.

## Шаг 2. Переменные окружения

Вкладка **Environment**. Dokploy сохраняет их в `.env` рядом с compose-файлом;
оба сервиса подхватывают его через `env_file: .env`.

**Мультирепо через GitHub App (рекомендуется).** Как в `poh-pr-agents`: установи
App на нужные репозитории, укажи вебхук в самом App, задай 4 переменные —
`GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY_B64` (`base64 -w0 ключ.pem`),
`GITHUB_WEBHOOK_SECRET`, `ISSUE_AGENT_REPOS` (`owner/repo,owner2/*` или `*`/пусто).
Installation определяется по репозиторию — `GITHUB_INSTALLATION_ID` не нужен.
Ниже — dev-вариант на PAT + один репозиторий.

```env
DRY_RUN=1
GITHUB_REPOSITORY=your-org/your-repo
GH_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=<openssl rand -hex 32>
ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
ZAI_API_KEY=...
MODEL_GATE=glm-4.5-air
MODEL_CLASSIFY=glm-4.6
POSTGRES_PASSWORD=<openssl rand -hex 24>
```

`POSTGRES_PASSWORD` — пароль к встроенному Postgres, где Temporal хранит историю
событий workflow. Именно она даёт durable execution — падение воркера продолжается
с последнего завершённого шага, а issue месяцами ждёт сигнала как штатное
состояние. В `docker-compose.full.yml` деплой намеренно падает, если переменная
пуста.

> Для варианта **main** (внешний Temporal) `POSTGRES_PASSWORD` не нужен — вместо
> него задай `TEMPORAL_ADDRESS=<host>:7233` и `TEMPORAL_NAMESPACE=<namespace>`
> (namespace должен уже существовать на кластере). По умолчанию plain gRPC; если
> кластер поддерживает TLS — добавь `TEMPORAL_TLS=1`.

Один провайдер, одна модель GLM. `ZAI_*` — OpenAI-совместимый эндпоинт z.ai,
через него идут все стадии, включая оценку. Второй пары `ANTHROPIC_*` из
`.env.example` здесь нет намеренно: она нужна только пайплайнам research/bug
(запускают CLI `claude -p`, который говорит по протоколу Anthropic), а те пока
`NotImplementedError`. Для `/estimate` она не используется — не задавай.

`DRY_RUN=1` на первом развёртывании обязателен. В этом режиме комментарии,
лейблы и реакции только пишутся в лог — сервис ничего не меняет в репозитории,
пока ты не убедишься, что он работает.

`GITHUB_WEBHOOK_SECRET` должен совпасть с секретом, который ты укажешь в
настройках вебхука на шаге 5. Без совпадения все доставки получат 401.

## Шаг 3. Домен для вебхука

Вкладка **Domains → Add Domain**:

| Поле | Значение |
|------|----------|
| Service Name | `webhook` |
| Container Port | `3000` |
| Host | `issue-agent.example.com` |
| HTTPS | включить, Certificate Provider — Let's Encrypt |

Домен получает только `webhook`. Ни `temporal`, ни `temporal-ui`, ни `postgres`
наружу не выставляются (у них `expose`, а не `ports`) — как дойти до UI, описано
ниже. В варианте main этих сервисов нет вовсе, Temporal внешний.

## Шаг 4. Развернуть

Нажать **Deploy**. Проверить логи:

```
worker:  Worker started, listening on task queue 'issue-lifecycle'
webhook: Uvicorn running on http://0.0.0.0:3000
```

Воркер при первом запуске может один раз упасть с `Namespace default is not
found` — контейнер `temporal` создаёт namespace через несколько секунд после
старта, а `depends_on` ждёт только запуска контейнера, не готовности. Политика
`restart: unless-stopped` перезапустит воркер, и вторая попытка пройдёт. Если
падение повторяется больше двух-трёх раз — проблема не в гонке, смотри логи
`temporal`. (В варианте main namespace должен уже существовать на внешнем
кластере — тогда сообщение будет с его именем, а не `default`.)

Проверить, что endpoint жив снаружи (подпись не сойдётся, поэтому ожидаемый
ответ — 401, и это как раз признак работающей проверки HMAC):

```bash
curl -i -X POST https://issue-agent.example.com/webhook \
  -H 'X-GitHub-Event: ping' -H 'Content-Type: application/json' -d '{}'
```

## Шаг 5. Вебхук в репозитории GitHub

GitHub App не нужен — достаточно вебхука уровня репозитория.

**Settings → Webhooks → Add webhook**:

| Поле | Значение |
|------|----------|
| Payload URL | `https://issue-agent.example.com/webhook` |
| Content type | `application/json` |
| Secret | то же значение, что в `GITHUB_WEBHOOK_SECRET` |
| Events | **Let me select individual events → Issue comments** |

То же самое из терминала:

```bash
gh api /repos/OWNER/REPO/hooks --method POST --input - <<'JSON'
{"name":"web","active":true,
 "events":["issue_comment"],
 "config":{"url":"https://issue-agent.example.com/webhook",
           "content_type":"json","secret":"ТОТ_ЖЕ_СЕКРЕТ"}}
JSON
```

> **Подписывайся только на `issue_comment`.** Если добавить событие `issues`,
> каждый новый Issue запустит полный автономный триаж `IssueLifecycle`, а он
> умеет закрывать Issue как спам и как дубликат. Для команды `/estimate`
> событие `issues` не требуется. Добавляй его отдельно и осознанно, когда
> захочешь включить триаж.

## Шаг 6. Проверка и выход в боевой режим

При всё ещё выставленном `DRY_RUN=1` напиши в любом Issue комментарий
`/estimate`. В логах воркера должно появиться:

```
[DRY_RUN] reaction eyes on OWNER/REPO comment 2145678901
[DRY_RUN] comment OWNER/REPO#42: ## Оценка задачи
[DRY_RUN] label OWNER/REPO#42 += estimated
```

Три строки означают, что путь целиком рабочий: вебхук принял команду, workflow
стартовал, модель ответила, расчёт прошёл, комментарий отрендерился. В самом
Issue при этом не появилось ничего.

Только после этого убери `DRY_RUN` — очисти значение переменной в Environment
(не удаляй строку, оставь `DRY_RUN=`) и нажми **Redeploy**. Теперь `/estimate`
ставит 👀 и публикует оценку по-настоящему.

## Temporal UI

Веб-интерфейс Temporal показывает каждый workflow на его текущей стадии — без
него диагностика сводится к чтению логов. В варианте **full** он входит в стек
(`temporal-ui`), но хост-порт не публикует: на Dokploy-хосте порт 8080 обычно
занят, а входа по паролю у интерфейса нет, тела Issue в нём видны — торчать
наружу как есть он не должен.

Доступ — через Dokploy-домен, закрытый basic-auth:

1. **Domains → Add Domain**, **Service Name** `temporal-ui`, **Container Port**
   `8080`, домен — свой или **Generate Domain**.
2. Traefik-middleware с basic-auth (**Advanced → Middlewares** или ярлык
   `traefik.http.middlewares.*.basicauth`). Без этого шага интерфейс окажется
   открыт всему интернету — не выкладывай домен, пока basic-auth не включён.

Альтернатива без домена — SSH-туннель в контейнер:

```bash
ssh -N -L 8080:<container-name>:8080 user@server   # <container-name> из docker ps
```

(В варианте **main** `temporal-ui` не поднимается — смотри UI централизованного
кластера в инфраструктуре.)

## Обновления

**Auto Deploy** в Dokploy вешает вебхук на репозиторий сервиса и передеплоивает
при пуше в отслеживаемую ветку. Удобно, но помни: передеплой пересобирает
образы, а сборка воркера тяжёлая.

Промпты (`prompts/`), коэффициенты расчёта (`config/estimation-rules.toml`) и
справочник функционала (`workspace/capabilities.md`) в продакшне **запечены в
образ**, а не примонтированы. Поменять коэффициент — значит закоммитить и
передеплоить. Это осознанный размен: Dokploy очищает каталог репозитория при
автодеплое, поэтому монтирование оттуда оставило бы воркер без файлов.
Локальная разработка не меняется — `docker-compose.local.yml` монтирует эти
каталоги поверх, и правка промпта видна без пересборки.

Данные Temporal живут в именованном томе `pgdata` и передеплой переживают.

## Если что-то не работает

**Доставки вебхука возвращают 401.** Секрет в настройках вебхука GitHub не
совпадает с `GITHUB_WEBHOOK_SECRET`. Смотри Recent Deliveries на странице
вебхука — там видны и запрос, и ответ.

**Доставки успешны, но реакции нет.** Команду не распознали. Команда — это
комментарий, у которого `/estimate` стоит **первой непустой строкой**.
`/estimate` в середине текста и процитированный `> /estimate` намеренно не
срабатывают. Комментарии от ботов отбрасываются раньше разбора.

**Реакция появилась, оценки нет.** Смотри логи воркера и Temporal UI. Workflow
перехватывает исключение и публикует комментарий с названием стадии, на которой
сломалось: `подтверждение команды`, `сбор контекста`, `извлечение фактов`,
`расчёт`, `публикация`.

**«Оценка задачи: расчёт остановлен».** Не сбой, а штатное поведение:
декомпозиция и Function Points разошлись больше чем вдвое. По методологии в
этом случае ищется ошибка, а не выводится среднее. Уточни описание задачи и
вызови `/estimate` заново.

**Воркер циклически перезапускается.** Если это не разовая гонка с namespace
(см. шаг 4), проверь `ZAI_API_KEY` и `ZAI_BASE_URL`: без них `llm.get_client()`
падает на `KeyError` при первом же обращении к модели.

**Оценка приходит бессмысленная.** Стадия извлечения фактов идёт на
`MODEL_CLASSIFY`, а не на дешёвой `MODEL_GATE`: модели послабее хватает на
классификацию, но не на декомпозицию задачи. Проверь, что переменная задана
именно той моделью, на которой ты калибровал коэффициенты. Пустое значение
`MODEL_CLASSIFY=` — хуже отсутствия строки: `os.environ.get` вернёт пустую
строку, а не дефолт из `llm.py`, и запрос уйдёт с пустым именем модели.
