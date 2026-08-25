# GitLab: подключение и работа

Операционный документ. Проектное обоснование — `docs/superpowers/specs/2026-08-21-gitlab-support-design.md`, постановка — [#109](https://github.com/po-helper-org/poh-issue-agents/issues/109).

---

## Статус: что работает сегодня, а что нет

Читать первым. Ниже описан и работающий путь, и тот, которого пока нет, — они помечены явно.

| Возможность | Состояние |
|---|---|
| Разбор ссылки на проект, включая вложенные подгруппы | **работает** — `shared/repo_ref.py` |
| Allowlist на многосегментных путях | **работает** — `shared/repos.py` |
| Каталог меток и их заведение | **работает** — `shared/label_catalog.py`, `scripts/bootstrap_labels.py` |
| Смена набора меток одной операцией | **работает** — `github_client.set_labels` |
| Вебхук не отдаёт 5xx на неразобранной доставке | **работает** — `webhook/main.py` |
| Эндпоинт `/gitlab/webhook` | **нет** |
| Проверка подписи вебхука GitLab | **нет** |
| Клиент GitLab API | **нет** |
| Драйвер провайдера (`poh-forge`) | **нет** |

Проверить самому:

```bash
git grep -n '@app.post' -- webhook/main.py
```

Два эндпоинта — `/webhook` и `/agent-event`. Третьего нет.

**Практическое следствие.** Контур пока не может вести проект GitLab. Подготовительные шаги 1–4 ниже выполняются уже сейчас и не пропадут; шаг 5 (вебхук) ставится последним, когда драйвер появится.

---

## Подключение проекта

Шаги 1–4 выполнены дважды на живых проектах: `poh-harness/harness-demo-service` и `poh-harness/threads-harness`.

### Шаг 1. Токен

GitLab → Preferences → Access tokens:

- scope **`api`** — нужен и на чтение, и на запись;
- срок **≤365 дней**. Бессрочные токены запрещены с версии 16.0, а с 17.3 инстанс может требовать явную дату;
- роль в проекте — **Maintainer**. Ниже неё вебхук не заведётся.

Положить в файл с правами `600`. Значение токена в переписку, Issue и коммиты не помещать:

```bash
mkdir -p ~/.config/poh
printf '%s' 'ТОКЕН' > ~/.config/poh/gitlab-token
chmod 600 ~/.config/poh/gitlab-token
```

**Выбор типа токена — не формальность.**

| Тип | Когда годится |
|---|---|
| Personal Access Token | единственный рабочий вариант на бесплатном `gitlab.com` |
| Project / Group Access Token | правильный выбор для корпоративного инстанса. **На `gitlab.com` требует Premium/Ultimate**, несмотря на бейдж Free |
| Service account + токен | корпоративный инстанс, если не хочется привязки к человеку |
| CI job token | **не годится** — не умеет писать комментарии |
| Deploy token | **не годится** — нет `write_repository`, не работает с REST API |

Ротация (`POST /personal_access_tokens/self/rotate`) **отзывает старый токен немедленно**. Это не параллельная выдача, как installation token у GitHub: между отзывом и записью нового значения контур слеп.

Проверка, что токен живой и ведёт куда надо:

```bash
T=$(cat ~/.config/poh/gitlab-token)
curl -s -H "PRIVATE-TOKEN: $T" https://gitlab.com/api/v4/user | python3 -m json.tool | head -5
```

### Шаг 2. Числовой id проекта

Пригодится везде: обращаться по id дешевле и надёжнее, чем по пути, который меняется при переносе проекта между группами.

```bash
T=$(cat ~/.config/poh/gitlab-token)
curl -s -H "PRIVATE-TOKEN: $T" \
  "https://gitlab.com/api/v4/projects/GROUP%2FPROJECT" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['id'], d['path_with_namespace'], d['default_branch'])"
```

**Путь обязателен к URL-кодированию целиком**, включая все слэши: `group/sub/project` → `group%2Fsub%2Fproject`. Это относится и к вложенным подгруппам, которых у GitLab бывает до 20 уровней. Кодирование берёт на себя `RepoRef.api_segment` — руками его дублировать не нужно.

### Шаг 3. Метки

Контур хранит состояние Issue в метках и **сам их не создаёт**.

GitLab заводит недостающую метку автоматически при первом применении — **проверено экспериментом 2026-08-24**: `PUT /issues/:iid` с `add_labels=<несуществующее имя>` отдаёт 200, метка появляется и на Issue, и в списке проекта. Поведение то же, что у GitHub.

Значит bootstrap — не условие работоспособности, а защита от другого: опечатка в имени молча создаёт мусорную метку вместо ошибки, и метка приезжает серой, без описания.

Каталог собирается из кода, а не переписывается руками — иначе разъедется с контуром на первой новой фазе:

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from shared.label_catalog import catalog
print(len(catalog()), 'меток')
"
```

Скрипт `scripts/bootstrap_labels.py` заводит их **через GitHub API**. Для GitLab до появления драйвера — прямой вызов:

```bash
T=$(cat ~/.config/poh/gitlab-token); PID=<id проекта>
python3 - "$T" "$PID" <<'PY'
import json, sys, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, ".")
from shared.label_catalog import catalog
token, pid = sys.argv[1], sys.argv[2]
created = existed = 0
for name, spec in catalog().items():
    body = urllib.parse.urlencode({
        "name": name, "color": spec.color, "description": spec.description}).encode()
    req = urllib.request.Request(
        f"https://gitlab.com/api/v4/projects/{pid}/labels",
        data=body, headers={"PRIVATE-TOKEN": token})
    try:
        urllib.request.urlopen(req, timeout=30); created += 1
    except urllib.error.HTTPError as e:
        if e.code == 409 or "already exists" in e.read().decode()[:200]: existed += 1
        else: raise
print(f"создано {created}, уже было {existed}")
PY
```

**`GET /projects/:id/labels` требует токен даже на публичном проекте** — отдаёт 401 анонимно. Прочитать состояние меток без авторизации нельзя.

**Каталог растёт.** На 24.08 в нём 64 метки, и число меняется: `/release` добавила семейство `run:`/`done:`/`failed:release`, а legacy-метка `needs-human-triage` вошла в каталог коммитом `feat(#118)`, хотя система её не ставит — она нужна для поиска по старым Issue.

Поэтому в проверке ниже сверяется **не число**, а совпадение с текущим каталогом. Захардкоженное число разъедется молча, и разъезд будет незаметен: недостающая метка всё равно заведётся при первом применении, просто серой.

### Шаг 4. Allowlist контура

В `.env` на стенде:

```
WATCHED_REPOS=group/project
```

`docker-compose.yml` пробрасывает эту переменную в контейнер под именем `ISSUE_AGENT_REPOS` — расхождение имён историческое, при grep по коду искать второе.

Форматы записи (`shared/repos.py`):

| Запись | Что покрывает |
|---|---|
| `group/project` | конкретный проект |
| `group/sub/project` | проект во вложенной подгруппе |
| `group/*` | всё, что принадлежит группе, включая подгруппы |
| `group/sub/*` | всё внутри этой подгруппы |
| `group` | то же, что `group/*` |
| `*` или пусто | всё |

Совпадение маски идёт **по границе сегмента**: `group/sub` покрывает `group/sub/project`, но не `group/subterfuge/project`.

**Гейта два, и они независимы:** allowlist контура и права токена. Событие проходит, только если прошло оба. Не прошедшее роняется до Temporal с записью в лог — искать в `docker logs …-issue-webhook-1` строку `ignored repo`.

### Шаг 5. Вебхук — **ставится последним**

**Не выполнять, пока в `webhook/main.py` нет эндпоинта `/gitlab/webhook`.**

Причина конкретная: у GitLab **нет автоматических ретраев**. Упавшая доставка теряется навсегда, только ручной Resend. Сверх того, **четыре подряд провала отключают вебхук** с backoff, растущим до суток; сорок подряд — насовсем. Настроить вебхук на несуществующий эндпоинт значит получить 404 на каждой доставке и отключённый вебхук в первый же час.

Когда драйвер появится: Project → Settings → Webhooks.

- **URL:** `http://<хост стенда>/gitlab/webhook`
- **Secret token** — он же проверяется контуром
- **Triggers:** Issues events, Comments, Merge request events
- SSL verification — по обстоятельствам: у стенда сертификата нет, вебхук идёт по http

---

## Чем GitLab отличается от GitHub

Разобрано по документации Meta… то есть GitLab: `docs.gitlab.com`. Каждая строка — то, что придётся учесть драйверу.

### Подпись вебхука зависит от версии

| Версия | Что доступно |
|---|---|
| ниже 19.0 | только plain `X-Gitlab-Token` — секрет сравнивается как есть |
| **19.0 / GA 19.1** | HMAC: заголовок `webhook-signature`, подписывается строка `{webhook-id}.{webhook-timestamp}.{body}`, ключ — base64 после снятия префикса `whsec_` |

`gitlab.com` держит свежую версию, поэтому HMAC там есть. Корпоративный инстанс может оказаться младше — деградация до сравнения секрета должна быть **явным решением с записью в лог**, а не тихим фолбэком.

### Идемпотентность доставки

| GitHub | GitLab |
|---|---|
| `X-GitHub-Delivery` | `Idempotency-Key` (с 17.4), иначе `X-Gitlab-Event-UUID` (с 14.8) |

### Метка «какая добавлена» не приходит

GitHub присылает `label.name`. GitLab присылает только `changes.labels.previous[]` и `current[]` — **дельту нужно считать самому**. На этом висит весь триггерный путь: `run:*`, `research-me`, `bug-me`, `build-me`.

### Поля `user.type` не существует

GitHub помечает ботов через `user.type == "Bot"`. У GitLab такого поля нет вовсе.

Опознание своих комментариев переживает переезд: маркер `<!-- issue-agent -->` ставится в единственной точке отправки и от API не зависит. Но код, читающий `type` **индексацией**, на GitLab даст `KeyError` — а это 500, потерянная доставка и шаг к отключению вебхука. Читать только через `.get()`.

Отдельно: в `github_client.review_text` фильтр по `type` работает **наоборот** — он отбирает комментарии ботов, потому что ревью пишет именно контур. На GitLab условие станет истинным всегда, и функция молча вернёт пустоту. Ошибки не будет.

### Аналога GitHub App не существует

Ни один документированный механизм GitLab не чеканит короткоживущий токен на установку. Минимальный документированный срок жизни не-CI токена — 2 часа у OAuth; у остальных до 365 дней.

### Аналога Timeline `cross-referenced` нет

Связь Issue↔MR пересобирается из трёх источников: `related_merge_requests`, `closed_by` и системных нот (`system: true`).

### Паритет операций

| Операция | GitHub | GitLab |
|---|---|---|
| Комментарий | `POST /repos/{r}/issues/{n}/comments` | `POST /projects/:id/issues/:iid/notes` |
| Метки | `POST`/`DELETE .../labels` | `PUT /projects/:id/issues/:iid` с `add_labels`/`remove_labels` |
| Закрыть Issue | `PATCH` `{"state":"closed"}` | `PUT` с `state_event=close` |
| Ветка есть? | `GET .../branches/{b}` | `GET /projects/:id/repository/branches/:branch` |
| Записать файл | `PUT /contents` с blob `sha` | **`POST`** создать / **`PUT`** обновить, с `last_commit_id` (**commit** SHA) |
| Открыть CR | `POST .../pulls` | `POST /projects/:id/merge_requests` |
| Найти CR по ветке | `?head={owner}:{branch}` | `?source_branch=&state=opened` |
| Реакция | `.../comments/{id}/reactions` | `.../issues/:iid/notes/:note_id/award_emoji` |
| Поиск Issue | `gh issue list` | `GET /projects/:id/issues?search=&in=title,description` |
| CLI | `gh` | `glab` |

Метки одним `PUT` — не только другая форма, но и улучшение: `add_labels`/`remove_labels` инкрементальны и безопасны для гонок. На GitHub `set_labels` разворачивается в POST плюс серию DELETE.

---

## Ловушки, установленные фактом

Каждая проверена, а не выведена из документации.

**Запись файла разная по семантике.** GitHub `PUT /contents` и создаёт, и обновляет. GitLab разделяет: `POST` создать, `PUT` обновить — вызывающему нужно знать, существует ли файл. И `last_commit_id` это **commit** SHA последнего изменения файла, а не blob SHA; у `POST` аналога нет вовсе.

**Реакция требует `issue_iid` в пути.** GitHub адресует реакцию только по `comment_id`. Значит при обработке `Note Hook` надо тащить `issue.iid` из payload и нести его в ссылке на комментарий.

**Имена emoji расходятся.** `eyes` и `confused`, которые использует контур, в GitLab есть. Но `+1`, `-1` и `hooray` отсутствуют — маппинг на `thumbsup`, `thumbsdown`, `tada`.

**Дубликат MR не документирован.** Ни код 409, ни текст ошибки при попытке создать существующий MR в документации не описаны. Закладывать pre-check по `?source_branch=&state=opened`, а не «создай и поймай».

**Поиск на Free работает только по Issue.** `?search=&in=title,description` — basic search, доступен. Advanced Search (по коду и комментариям) требует Premium/Ultimate. Duplicate-check жив, сценарии с поиском по содержимому репозитория — нет.

**Лимит нот на `gitlab.com` — 60/мин.** Контур на одном Issue пишет много: реакция, комментарий приоритета, уточнения, публикация анализа. Заголовки `RateLimit-*` приходят на всех ответах — драйвер обязан их читать и отдавать `RateLimited`, а не падать.

---

## Self-hosted и корпоративный контур

### Минимальные версии

| Возможность | Версия |
|---|---|
| `X-Gitlab-Event-UUID` | 14.8 |
| Auto-disable вебхуков | 15.10, порог 40 — 17.11 |
| `Idempotency-Key` | **17.4** |
| Service accounts на Free | 18.11 |
| **HMAC-подпись вебхука** | **19.0, GA 19.1** |

### CE против EE

| Фича | Tier |
|---|---|
| Project webhooks | Free+ |
| **Group webhooks** | Premium/Ultimate |
| **Advanced Search** | Premium/Ultimate |
| **Scoped labels** (`key::value`) | Premium/Ultimate |
| Project/Group Access Tokens **на `gitlab.com`** | Premium/Ultimate |

На Free вебхук заводится **на каждый проект отдельно**.

Про scoped labels: схема имён контура — одинарное двоеточие (`phase:`, `run:`, `advisor:`). У GitLab scoped labels используют двойное и дают взаимоисключаемость на стороне трекера. Соблазн перейти есть, но это Premium, и имена меток разошлись бы между провайдерами. Инвариант «одна фаза — одна метка» остаётся на коде.

### Корпоративный CA

| Клиент | Что делать |
|---|---|
| GitLab (Omnibus) | PEM с расширением `.crt` в `/etc/gitlab/trusted-certs`, затем `gitlab-ctl reconfigure`. Цепочку раскладывать по отдельным файлам — известная проблема `openssl rehash` |
| git | `git config --global http.sslCAInfo <path>` |
| Python `requests` | `REQUESTS_CA_BUNDLE`. **В документации GitLab для Python-клиентов не описано** — это перенос практики, а не официальная рекомендация |
| `glab` | Ключи `ca_cert`/`client_cert`/`client_key` в `~/.config/glab-cli/config.yml`. **На `docs.gitlab.com` не задокументировано** — для self-managed блокирующий вопрос, снимать на инстансе |

Типовая ошибка при непрописанном CA — `unable to get local issuer certificate`.

### Исходящие вебхуки заблокированы по умолчанию

Admin → Settings → Network → Outbound requests: чекбокс «Allow requests to the local network from webhooks and integrations» **выключен**. Блокируются адрес инстанса, `127.0.0.1`, `::1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.

Приёмник во внутренней сети требует действия администратора: включить чекбокс либо добавить адрес в allowlist. Allowlist — до 1000 записей по ≤255 символов, **wildcards не поддерживаются**.

### GitLab под VPN

Кодом не решается, решается размещением.

| Вариант | Требует | Не решает |
|---|---|---|
| Контур внутри периметра | согласования на размещение, исходящего доступа к LLM | — |
| Poller вместо вебхука | курсора, дедупликации, VPN-клиента; реакция задерживается на интервал | — |
| Релей внутри периметра | третьего компонента и ещё одного согласования | git-операции всё равно требуют связности контура к GitLab |

Рекомендация: первый вариант, если периметр допускает исходящий доступ к LLM; иначе второй. У poller есть побочная выгода — он не подвержен отключению вебхука после четырёх провалов.

---

## Проверка подключения

```bash
T=$(cat ~/.config/poh/gitlab-token); PID=<id>
B="https://gitlab.com/api/v4/projects/$PID"

curl -s -H "PRIVATE-TOKEN: $T" "$B" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('проект:', d['path_with_namespace'])"

curl -s -H "PRIVATE-TOKEN: $T" "$B/labels?per_page=100" \
  | python3 -c "import json,sys;print('меток:', len(json.load(sys.stdin)))"

curl -s -H "PRIVATE-TOKEN: $T" "$B/issues?per_page=1" \
  | python3 -c "import json,sys;print('доступ к Issue: ок')"
```

Число меток должно совпасть с размером каталога.

---

## Когда сломалось

| Симптом | Причина | Что делать |
|---|---|---|
| Вебхук отключился сам | четыре подряд провала доставки | **не долбить Test повторами** — сначала лог `issue-webhook`, потом одна тестовая доставка. Пять операций Test/Resend в минуту, дальше `Webhook rate limit exceeded` |
| Событие не дошло, в логе `ignored repo` | не прошёл allowlist | проверить `WATCHED_REPOS`, помня, что в контейнере переменная зовётся `ISSUE_AGENT_REPOS` |
| `401 Unauthorized` на чтении меток | нет токена | метки требуют авторизации даже на публичном проекте |
| Метка появилась серой и без описания | заведена автоматически при применении | опечатка в имени: сверить с `label_catalog.catalog()` |
| Комментарии ревью пусты | фильтр по `user.type` на GitLab всегда истинен | известный дефект, см. раздел про `user.type` |
| `unable to get local issuer certificate` | корпоративный CA не прописан | см. раздел про CA |
| Пост-атрибуция сломалась после переноса проекта | обращались по пути, а не по числовому id | использовать `project_id` |

---

## Что почитать дальше

- `docs/superpowers/specs/2026-08-21-gitlab-support-design.md` — почему выбран пакет-драйвер, а не транслятор, и почему стадия разработки идёт локальным раннером
- [#109](https://github.com/po-helper-org/poh-issue-agents/issues/109) — постановка и полная фактура по API
- [#241](https://github.com/po-helper-org/poh-issue-agents/issues/241) — план работ и протокол приёмки, 12 критериев
