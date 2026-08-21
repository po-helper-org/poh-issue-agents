# Дизайн: поддержка GitLab рядом с GitHub

**Дата:** 2026-08-21
**Issue:** [#109](https://github.com/po-helper-org/poh-issue-agents/issues/109)
**Статус:** дизайн согласован, реализация не начата

---

## 1. Задача и рамки

Контур умеет один трекер — GitHub. Заказчик с GitLab не может им воспользоваться. Нужно научить контур работать с GitLab **рядом** с GitHub, не ломая работающий путь.

**HowToDemo.** Человек читает документацию, выполняет настройки, открывает репозиторий, оставляет Issue — система отрабатывает процесс и выдаёт MR с кодом.

**Цель демо:** `gitlab.com/poh-harness/harness-demo-service` — публичный проект, группа `poh-harness`, тариф Free. Демо-задача: сервис планирования спринтов, который пишет контур по Issue.

**Решения по рамкам, принятые до проектирования:**

| Вопрос | Решение | Почему |
|---|---|---|
| Какой GitLab для демо | `gitlab.com` (SaaS) | Вебхук доходит до стенда напрямую, репозиторий заводится за минуты |
| VPN-сценарии | Глава документа, не код | Реализуем вебхук; варианты для периметра описываем с ценой и ограничениями |
| Стадия разработки | Только локальный docker-раннер | Не нужен runner у заказчика, LLM-ключ в его CI-переменных, отдельное согласование безопасности |
| Форма абстракции | Отдельный пакет `poh-forge` | Клиент уже дублируется в трёх репозиториях |

---

## 2. Обоснование выбора формы

Рассматривались три варианта.

**A. Протокол внутри монолита.** Абстракция живёт в `poh-issue-agents`, драйверы рядом. Дёшево, но не решает дублирование в соседних репозиториях.

**B. Транслятор-прокси.** Отдельный сервис переводит GitLab-вебхук в GitHub-совместимый payload, исходящие вызовы проксирует. Ноль правок в 118 call-site — но протечёт на первом расхождении моделей: метки в GitLab обновляются целиком через `PUT`, `iid` против `id`, вложенные подгруппы не влезают в `owner/repo`, связь Issue↔MR устроена иначе. Плюс третий компонент на стенде, где память в обрез, и отладка через два хопа.

**C. Отдельный пакет `poh-forge`. ← выбран**

Основание — измеренное дублирование:

| Репозиторий | Клиент | Что дублируется |
|---|---|---|
| `poh-issue-agents` | `worker/github_client.py` — 666 строк | JWT App → installation token, кэш 55 мин, git-транспорт, REST |
| `poh-pr-agents` | `self-hosted/reliability/github_client.py` 185 + `token.py` | **Своя** `InstallationTokenProvider`: `_app_jwt`, `_exchange`, парсинг expiry |
| `poh-pr-closer` | `shared/github_client.py` 203 | — |

Самая нетривиальная часть — аутентификация GitHub App — написана дважды с нуля. Это и есть аргумент за библиотеку, а не за протокол внутри одного репозитория.

---

## 3. Границы пакета

**Репозиторий** `po-helper-org/poh-forge`, пакет `poh_forge`.

### Внутрь

- **Протокол `Forge`** — операции в терминах предметной области, не REST.
- **Типы** `RepoRef`, `IssueRef`, `ChangeRequest`, `Comment`, `ForgeEvent`.
- **`TokenProvider`** — две реализации за одним интерфейсом.
- **Нормализация вебхуков** — проверка подписи и перевод payload в `ForgeEvent`.
- **git-транспорт** — credential helper без токена в URL, фильтрация токена из stderr.
- **Ошибки** `ForgeError`, `NotFound`, `RateLimited`, `Conflict`.

### Снаружи

Жизненный цикл Issue (`shared/lifecycle.py`), фазовые метки, Temporal, LLM, промпты, OpenHands, политика allowlist.

Принцип границы: метка `phase:ready-for-dev` — понятие контура, а не форжа. Forge умеет ставить произвольные метки и **не знает, что они значат**. Иначе библиотека начнёт знать про `ISSUE_AGENT_REPOS` и перестанет быть библиотекой.

### Подключение

```
pip install git+https://github.com/po-helper-org/poh-forge@<полный SHA>
```

Пин **на полный SHA**, не на тег и не на ветку. BuildKit кэширует git-клон по URL: после нового коммита в ту же ссылку он молча собирает прежний код, а короткий SHA не находит вовсе (`repository does not contain ref`). Та же практика уже действует для `ISSUE_AGENT_CONTEXT` на стенде.

---

## 4. Протокол `Forge`

Именование намеренно не GitHub-ное. `open_change_request`, а не `create_pr`: иначе GitLab придётся натягивать на чужую форму, и абстракция станет тонкой обёрткой одного провайдера.

```python
class Forge(Protocol):
    # Issue
    def get_issue(self, ref: IssueRef) -> Issue: ...
    def create_issue(self, repo: RepoRef, title: str, body: str,
                     labels: Sequence[str] = ()) -> IssueRef: ...
    def close_issue(self, ref: IssueRef) -> None: ...
    def update_issue_body(self, ref: IssueRef, body: str) -> None: ...
    def search_issues(self, repo: RepoRef, query: str, *,
                      state: str = "opened") -> list[Issue]: ...

    # Комментарии
    def post_comment(self, ref: IssueRef, body: str) -> CommentRef: ...
    def list_comments(self, ref: IssueRef) -> list[Comment]: ...
    def add_reaction(self, ref: CommentRef, name: str) -> None: ...

    # Метки — одной операцией, а не парой
    def set_labels(self, ref: IssueRef, *,
                   add: Sequence[str] = (), remove: Sequence[str] = ()) -> None: ...
    def ensure_labels_exist(self, repo: RepoRef, labels: Sequence[str]) -> None: ...

    # Ветки и файлы
    def default_branch(self, repo: RepoRef) -> str: ...
    def branch_exists(self, repo: RepoRef, branch: str) -> bool: ...
    def ensure_branch(self, repo: RepoRef, branch: str, base: str | None = None) -> None: ...
    def read_file(self, repo: RepoRef, path: str, ref: str) -> str | None: ...
    def put_file(self, repo: RepoRef, path: str, content: str, *,
                 branch: str, message: str) -> None: ...

    # Change request (PR / MR)
    def open_change_request(self, repo: RepoRef, *, source: str, target: str,
                            title: str, body: str) -> ChangeRequest: ...
    def get_change_request(self, repo: RepoRef, number: int) -> ChangeRequest: ...
    def find_change_request(self, repo: RepoRef, source: str) -> ChangeRequest | None: ...
    def linked_change_requests(self, ref: IssueRef) -> list[ChangeRequest]: ...
    def review_text(self, repo: RepoRef, number: int, limit: int = 12000) -> str: ...

    # git
    def push_worktree(self, repo: RepoRef, workdir: Path, *,
                      branch: str, message: str) -> None: ...
    def clone_url(self, repo: RepoRef) -> str: ...
    def git_credentials(self, repo: RepoRef) -> GitCredentials: ...
```

### Три решения, зашитые в форму протокола

**`set_labels(add, remove)` вместо пары `add_label` / `remove_label`.** GitHub-драйвер разворачивает в POST/DELETE. GitLab-драйвер — в один `PUT /issues/:iid` с `add_labels` / `remove_labels`, которые инкрементальны и безопасны для гонок.

Это чинит существующий недостаток: `activities.py:199` `set_phase` делает **до 20 DELETE + 1 POST** на каждую смену фазы, и в окне между ними меток `phase:*` нет вовсе — `phase_from_labels` вернёт `None`. Через `set_labels` на GitLab это один вызов, на GitHub — прежняя последовательность, но описанная в одном месте.

**`ensure_labels_exist` как явная операция.** Сегодня bootstrap меток отсутствует: grep по `label create` / `POST .../labels` даёт ноль. Система полагается на то, что GitHub заводит отсутствующую метку сам при добавлении на Issue — в коде это нигде не записано и не проверяется. Поведение GitLab в документации не описано; кроме того, `GET /projects/:id/labels` отдаёт **401 даже на публичном проекте** (проверено на цели демо). Значит метки надо заводить явно и заранее.

**`linked_change_requests` возвращает список, а не сырой ответ.** У GitHub это Timeline API с `Accept: application/vnd.github.mockingbird-preview+json` и событием `cross-referenced`. Аналога в GitLab нет — граф пересобирается из `related_merge_requests`, `closed_by` и системных нот (`system: true`). Наружу разница не течёт.

---

## 5. Идентичность репозитория

```python
@dataclass(frozen=True)
class RepoRef:
    provider: str          # "github" | "gitlab"
    path: str              # "owner/repo" | "group/subgroup/project"
    project_id: int | None = None   # GitLab: числовой id, GitHub: None

    @property
    def api_segment(self) -> str:
        """Готовый сегмент пути API. GitLab: id или URL-encoded path."""
```

### Что это чинит

**26 URL в `github_client.py` подставляют `{repo}` в путь без URL-кодирования.** Для GitHub `owner/repo` — корректный сегмент. GitLab требует `group%2Fsub%2Fproj`. Показательно, что в том же файле метка кодируется (`:166`), `workflow_file` кодируется (`:450`) — а repo нигде. Кодирование уезжает в `api_segment` и перестаёт быть заботой вызывающего.

**`shared/repos.py:47` `is_allowed` на многосегментных путях.** Проверено прогоном: `group/subgroup/*` даёт `False`, точное совпадение `group/subgroup` даёт `False` — событие молча отбрасывается до Temporal. При этом `group/*` даёт `True`, но матчит рекурсивно все подгруппы: тише и шире, чем задумано.

Для цели демо это **не блокер**: `poh-harness/harness-demo-service` — ровно два сегмента, та же форма, что `owner/repo`. Проблема касается только корпоративного `group/subgroup/project`. Подгруппы GitLab вкладываются до 20 уровней.

### Что не ломается

Проверено отдельно и подтверждено отрицательным результатом:

- **Имена веток репозиторий не содержат** — `research/issue-N`, `bug/issue-N`, `feature/N-openhands`, `bft-research/issue-N`, `entire/*` строятся только от номера Issue.
- **Slug'и экранируют слэши** — `dev-{repo.replace('/','__')}-{n}` даёт валидное имя каталога и docker-контейнера при любом числе сегментов.
- **Search attribute `Repo`** объявлен Keyword — не токенизируется, трёхсегментный путь ложится целиком.
- **`comment.id` в двух workflow ID** (`comment-ack-*`, `estimate-*`): в GitLab id заметки уникален глобально по инстансу — для ключа безопаснее, чем на GitHub.
- **`_BRANCH_RE`** (`shared/agent_events.py:143`) корректно матчит `bft-research/issue-N`: `\b` срабатывает после дефиса. Не покрыт только `feature/N-openhands`, и это третий по счёту fallback в `correlate` после `root_issue` и `Closes #N`.

---

## 6. Приём событий и надёжность

### Ключевое расхождение

**У GitLab нет автоматических ретраев вебхуков.** Провал доставки — событие потеряно навсегда, только ручной Resend Request. Сверх того, **4 подряд провала отключают вебхук** с backoff, растущим до 24 часов; 40 подряд — отключают совсем. Таймаут доставки 10 с.

Текущий код построен на противоположной ставке: комментарий на `webhook/main.py:67-78` прямо говорит «расчёт на ретраи GitHub».

### Следствие для архитектуры

Обработчик обязан **не отдавать 5xx никогда**. Схема: принял → записал сырое событие → вернул 200 → разбирает дальше, ошибки разбора живут в аудит-workflow, а не в HTTP-ответе.

Это переклассифицирует известную ловушку. `webhook/main.py:530` и `:172` читают `payload[...]["user"]["type"]` **индексацией**. На GitHub поле всегда есть. На GitLab его нет вовсе: `KeyError` → 500 → событие потеряно **и** сделан шаг к отключению вебхука. На GitHub тот же 500 был бы незаметен, потому что доставку повторят.

### Нормализация

```python
@dataclass(frozen=True)
class ForgeEvent:
    kind: str                # "issue_opened" | "issue_closed" | "labeled" | "comment"
    repo: RepoRef
    delivery_id: str         # идемпотентность
    issue: IssueRef | None
    labels_added: list[str]  # вычисленная дельта
    comment: Comment | None
    sender: Actor
```

| Аспект | GitHub | GitLab |
|---|---|---|
| Событие | `X-GitHub-Event` | `X-Gitlab-Event`: `Issue Hook`, `Note Hook`, `Merge Request Hook` |
| Идемпотентность | `X-GitHub-Delivery` | `Idempotency-Key` (≥17.4), иначе `X-Gitlab-Event-UUID` (≥14.8) |
| Подпись | `X-Hub-Signature-256`, HMAC от сырого тела | `webhook-signature` (≥19.0/GA 19.1): HMAC от `{webhook-id}.{webhook-timestamp}.{body}`, ключ — base64 после снятия `whsec_`. Ниже 19.0 — plain `X-Gitlab-Token` |
| Идентификация репозитория | `repository.full_name` | `project.id` + `project.path_with_namespace` |
| Действие | `action` | `object_attributes.action`: `open`/`close`/`reopen`/`update` |
| Автор — бот? | `user.type == "Bot"` | **Поля нет.** Опознание по логину сервисного аккаунта и по маркеру `<!-- issue-agent -->` |

### Метки: дельта вместо готового поля

GitLab **не присылает** «какая метка добавлена» — только `changes.labels.previous[]` и `current[]`. На `webhook/main.py:453` (`payload["label"]["name"]`) висит весь триггерный путь: `run:*`, `research-me`, `bug-me`, `build-me`. Дельта считается в нормализаторе и кладётся в `ForgeEvent.labels_added` — дальше по коду разницы нет.

### Опознание своих комментариев

`worker/github_client.py:611` фильтрует `if user.type != "Bot": continue` — оставляет **только** ботов. Это намеренно: docstring на `:582` объясняет, что контур ходит как App, то есть сам Bot, и его реплики и есть ревью.

Без поля `type` условие истинно всегда — **все комментарии молча отбрасываются**, `review_text` тихо пустеет, ошибки не будет. Это худший вид отказа: шаг отработал, успех доложен, результата нет.

Решение: опознание переезжает на два признака, не зависящих от провайдера — логин сервисного аккаунта из конфигурации и маркер `<!-- issue-agent -->`, который уже ставится в единственной точке отправки (`github_client.py:137`) и переносится как есть.

---

## 7. Аутентификация

### Аналога GitHub App не существует

Ни один документированный механизм GitLab не чеканит короткоживущий токен «на установку». OAuth-flow в документации — Authorization Code, PKCE, Device Authorization Grant; Client Credentials отсутствует.

| Вариант | Срок | Ограничение |
|---|---|---|
| Personal Access Token | ≤365 дн., `expires_at` обязателен с 16.0 | Привязан к пользователю |
| Project / Group Access Token | ≤365 дн. | **На `gitlab.com` требует Premium/Ultimate**, несмотря на бейдж Free |
| Service account + PAT | ≤365 дн. | Free+, до 100 аккаунтов на группу; seat не занимает |
| OAuth application | 2 ч, refresh | Инстанс-вайд регистрация — только self-managed |
| CI job token | Жизнь job | **Не умеет писать комментарии**, не умеет GraphQL — непригоден |
| Deploy token | Опционально | Нет `write_repository`, не работает с REST API — непригоден |

**Для демо на бесплатном `gitlab.com`:** PAT бот-пользователя со scope `api`.
**Для корпоративного инстанса:** service account + Group Access Token.

Ротация (`POST .../access_tokens/self/rotate`) **отзывает старый токен немедленно** — это не параллельная выдача, как installation token. Значит смена токена — операция с окном недоступности, её нельзя делать «на живую» без предупреждения.

### Интерфейс

```python
class TokenProvider(Protocol):
    def token_for(self, repo: RepoRef) -> str: ...
```

GitHub-реализация переносится как есть: JWT RS256 (TTL 540 с) → `POST /app/installations/{id}/access_tokens` → кэш 55 мин с double-checked locking. GitLab-реализация — статический токен из конфигурации.

На старте контейнера — предупреждение в лог о сроке жизни токена GitLab, по образцу существующего `_log_effective_config` (`webhook/main.py:84`). Токен, который тихо протух, ничем не отличается от сломанного контура.

### git по HTTPS

Username в credential helper: `x-access-token` для GitHub, **`oauth2`** для GitLab (совместим с PAT, PrAT, GAT, OAuth). Единственный обязательный литерал в GitLab — `gitlab-ci-token`, и он нам не нужен. Токен по-прежнему **не попадает в URL** — только через `GIT_CONFIG_*` и `credential.helper`, как сделано сейчас.

---

## 8. Таблица паритета операций

| Операция | GitHub | GitLab |
|---|---|---|
| Комментарий | `POST /repos/{r}/issues/{n}/comments` | `POST /projects/:id/issues/:iid/notes` |
| Список комментариев | `GET .../comments` | `GET .../notes` |
| Метки | `POST` / `DELETE .../labels[/{l}]` | `PUT /projects/:id/issues/:iid` c `add_labels` / `remove_labels` |
| Создать метку | — (auto-create) | `POST /projects/:id/labels` |
| Создать Issue | `POST /repos/{r}/issues` | `POST /projects/:id/issues` |
| Закрыть Issue | `PATCH` `{"state":"closed"}` | `PUT` c `state_event=close` |
| Default branch | `GET /repos/{r}` → `default_branch` | `GET /projects/:id` → `default_branch` |
| Ветка есть? | `GET .../branches/{b}` | `GET /projects/:id/repository/branches/:branch` |
| Создать ветку | `POST .../git/refs` | `POST /projects/:id/repository/branches` |
| Прочитать файл | Contents API, `Accept: raw` | `GET .../repository/files/:path/raw?ref=` |
| Записать файл | `PUT /contents` c `sha` (blob SHA) | `POST` (create) / `PUT` (update) c `last_commit_id` (**commit** SHA) |
| Открыть CR | `POST /repos/{r}/pulls` | `POST /projects/:id/merge_requests` |
| Найти CR по ветке | `?head={owner}:{branch}` | `?source_branch=&state=opened` |
| Связанные CR | Timeline API `cross-referenced` | `related_merge_requests` + `closed_by` + системные ноты |
| Реакция | `POST .../issues/comments/{id}/reactions` | `POST .../issues/:iid/notes/:note_id/award_emoji` |
| Поиск Issue | `gh issue list` / Search API | `GET /projects/:id/issues?search=&in=title,description` |
| CLI | `gh` | `glab` |

### Ловушки, требующие внимания при реализации

**Запись файла — разная семантика.** GitHub `PUT /contents` создаёт **и** обновляет. GitLab разделяет `POST` (create) и `PUT` (update): вызывающему нужно знать, существует ли файл. Сверх того, GitHub `sha` — blob SHA, GitLab `last_commit_id` — **commit SHA последнего коммита, изменившего файл**; поле `blob_id` в GitLab есть, но параметром записи не является. У `POST` аналога `last_commit_id` нет вообще.

**Реакции требуют `issue_iid` в пути.** GitHub адресует реакцию только по `comment_id`. Значит при обработке `Note Hook` надо тащить `issue.iid` из payload и нести его в `CommentRef`.

**Имена emoji расходятся.** `eyes` и `confused` — используемые контуром — в GitLab есть. Но `+1` / `-1` / `hooray` отсутствуют: маппинг на `thumbsup` / `thumbsdown` / `tada`. Список допустимых имён в документации отсутствует.

**Поиск на Free работает для Issue.** `?search=&in=title,description` — basic search, доступен. Но Advanced Search (поиск по коду и по комментариям) требует Premium/Ultimate: duplicate-check жив, а сценарии, опирающиеся на поиск по содержимому репозитория, — нет.

---

## 9. Стадия разработки

`dispatch` в GitLab CI **не реализуется**. Для GitLab работает только локальный docker-раннер на стенде.

Обоснование: не нужен runner у заказчика, не нужен LLM-ключ в его CI-переменных, не нужно отдельное согласование безопасности. Цена — нагрузка на стенд, где памяти в обрез (~8 ГБ, из них 2.4 ГБ ест соседний `temporal-postgresql`), и параллельные прогоны её выбирают.

Если решение пересмотрят, эквивалент известен: `POST /projects/:id/pipeline` с `variables`, либо `POST /projects/:id/trigger/pipeline` с trigger-токеном. Ловушка на будущее: `CI_PIPELINE_SOURCE` у этих двух путей **разный** — `api` и `trigger`. Типовой `workflow:rules` с `$CI_PIPELINE_SOURCE == "push"` отфильтрует оба, и пайплайн молча не создастся.

---

## 10. Конфигурация

```
FORGE_PROVIDER=gitlab               # github | gitlab
GITLAB_URL=https://gitlab.com       # для self-hosted — свой хост
GITLAB_TOKEN=<PAT scope api>
GITLAB_WEBHOOK_SECRET=<secret или signing token>
GITLAB_BOT_LOGIN=<логин сервисного аккаунта>
ISSUE_AGENT_REPOS=poh-harness/harness-demo-service
```

`ISSUE_AGENT_REPOS` остаётся общим для обоих провайдеров: allowlist — политика контура, а не форжа. В `docker-compose.yml:41` он пробрасывается из `WATCHED_REPOS` — расхождение имён сохраняется как есть, менять его в этой работе не нужно.

Существующие переменные GitHub не трогаются: `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY_B64`, `GITHUB_WEBHOOK_SECRET`, `GH_TOKEN`.

---

## 11. Self-hosted корпоративный GitLab

### Минимальные версии

| Возможность | Версия |
|---|---|
| `X-Gitlab-Event-UUID` | 14.8 |
| Auto-disable вебхуков | 15.10, порог 40 — 17.11 |
| **`Idempotency-Key`, resend event** | **17.4** |
| Scope `self_rotate` | 17.9 |
| Service accounts GA на Free | 18.11 |
| **HMAC-подпись вебхука** | **19.0, GA 19.1** |

**Главное версионное ограничение:** инстанс младше 19.0 не умеет HMAC вообще. Проверка подписи деградирует до сравнения секрета из `X-Gitlab-Token` — это должно быть явным решением с записью в лог, а не тихим фолбэком.

### CE (Free) против EE

| Фича | Tier |
|---|---|
| Project webhooks | Free+ |
| **Group webhooks** | Premium/Ultimate |
| **Advanced Search** (по коду, по комментариям) | Premium/Ultimate |
| **Scoped labels** (`key::value`) | Premium/Ultimate |
| Project / Group Access Tokens **на `gitlab.com`** | Premium/Ultimate |
| Multiple assignees, `assignee_ids` при создании | Premium/Ultimate |
| MR approvals (базовые) | Free+ |
| `approval_rules` | Premium/Ultimate |

Практический вывод для Free-инстанса: вебхук заводится **на каждый проект отдельно** (group webhooks недоступны), поиска по коду нет, scoped labels нет.

Последнее заслуживает отдельной оговорки. Схема имён контура — одинарное двоеточие (`phase:`, `run:`, `advisor:`, `needs-human:`). В GitLab scoped labels используют **двойное** (`phase::classified`) и дают взаимоисключаемость на стороне трекера. Соблазн перейти на `::` есть, но: во-первых, это Premium; во-вторых, разошлись бы имена меток между провайдерами. Инвариант «одна фаза — одна метка» остаётся на коде, как сейчас.

### Корпоративный CA

| Клиент | Что делать |
|---|---|
| GitLab (Omnibus) | PEM с расширением `.crt` в `/etc/gitlab/trusted-certs`, затем `gitlab-ctl reconfigure`. Цепочку раскладывать по отдельным файлам — известная проблема `openssl rehash` |
| git | `git config --global http.sslCAInfo <path>` |
| Python `requests` | `REQUESTS_CA_BUNDLE`. **В документации GitLab для Python-клиентов API это не описано** — перенос практики, а не официальная рекомендация |
| `glab` | Ключи `ca_cert` / `client_cert` / `client_key` в `~/.config/glab-cli/config.yml`, переменная `ADDITIONAL_CA_CERT_BUNDLE`. **На `docs.gitlab.com` не задокументировано** — подтверждается только по MR в трекере GitLab. Для self-managed это блокирующий вопрос, снимать на инстансе |

Типовая ошибка при непрописанном CA — `unable to get local issuer certificate`.

### Исходящие вебхуки заблокированы по умолчанию

Admin → Settings → Network → Outbound requests: чекбокс «Allow requests to the local network from webhooks and integrations» **выключен**. Блокируются адрес самого инстанса, `127.0.0.1`, `::1`, `0.0.0.0`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.

Значит приёмник вебхука во внутренней сети требует действия администратора: либо включения чекбокса, либо добавления адреса в allowlist. Allowlist — до 1000 записей по ≤255 символов, **wildcards не поддерживаются**.

### Лимиты

`gitlab.com`: создание нот — **60/мин**, создание Issue — 200/мин, Search API — 10/мин, auth API — 2000/мин.

Контур на одном Issue пишет много: реакция, комментарий приоритета, уточнения, публикация анализа. В демо вряд ли упрётся; в проде с несколькими параллельными Issue — предсказуемо. Заголовки `RateLimit-*` есть на всех ответах, `Retry-After` — при троттлинге. Драйвер обязан их читать и отдавать `RateLimited`, а не падать.

Self-managed: user/IP лимиты по умолчанию **выключены**, лимит создания нот — 300/мин, включён.

---

## 12. GitLab под корпоративным VPN

Кодом не решается — решается размещением. Три варианта с ценой.

### Вариант 1: контур внутри периметра

Контур разворачивается рядом с GitLab. Вебхук работает штатно.

- **Требует:** согласования на размещение в периметре, исходящего доступа к LLM API.
- **Не требует:** ни строчки нового кода.
- **Риск:** политика может запрещать исходящий трафик к внешним LLM. Тогда нужен LLM внутри периметра — это отдельная задача, выходящая за рамки адаптации трекера.

### Вариант 2: poller вместо вебхука

Контур снаружи, ходит в GitLab через VPN-клиент и опрашивает API по `updated_after`.

- **Требует:** курсора, дедупликации событий, VPN-клиента в контейнере. Реакция задерживается на интервал опроса.
- **Плюс:** нужна только **исходящая** связность контур → GitLab. Ни один входящий порт наружу не открывается.
- **Побочная выгода:** poller не подвержен отключению вебхука после 4 провалов — а на GitLab это реальный режим отказа.

### Вариант 3: релей внутри периметра

Маленький сервис внутри VPN принимает вебхуки и держит исходящий туннель к контуру снаружи.

- **Требует:** третьего разворачиваемого компонента и ещё одного согласования безопасности.
- **Не решает** главного: git-операции и вызовы API всё равно требуют связности контура к GitLab.
- **Вывод:** вариант хуже второго почти во всём. Оставлен для полноты.

**Рекомендация:** вариант 1, если периметр допускает исходящий доступ к LLM; иначе вариант 2.

---

## 13. Runbook подключения

Это шаги 1–2 HowToDemo — документация, по которой человек подключает GitLab.

### Шаг 1. Токен

GitLab → Preferences → Access tokens → новый токен:
- scope **`api`**;
- срок ≤365 дней (бессрочные запрещены с версии 16.0);
- роль в проекте — **Maintainer** (иначе не заведётся вебхук).

Для корпоративного инстанса — вместо личного токена завести service account и Group Access Token на него.

Значение токена в переписку не отправлять. Положить в файл с правами 600 либо в переменную окружения стенда.

### Шаг 2. Метки

Контур хранит состояние Issue в метках и **сам их не создаёт**. Завести заранее (или дождаться `ensure_labels_exist` из шага 1 этапов):

`phase:*` (19 значений), `advisor:*`, `priority:*`, `run:*` / `done:*` / `failed:*`, `needs-human:triage`, `needs-human:pr`, `origin:agent`, `agents:off`, `ready-for-dev`, `in-development`, `research-me`, `bug-me`, `build-me`, `duplicate`, `possible-duplicate`, `spam`, `bot-authored`, `security-sensitive`, `needs-clarification`, `estimated`.

### Шаг 3. Вебхук

Project → Settings → Webhooks:
- **URL:** `http://<хост стенда>/gitlab/webhook`;
- **Secret token** — он же проверяется на стороне контура;
- **Triggers:** Issues events, Comments, Merge request events;
- SSL verification — по обстоятельствам (у стенда сейчас нет сертификата, вебхук идёт по http).

### Шаг 4. Allowlist контура

В `.env` на стенде: `WATCHED_REPOS=poh-harness/harness-demo-service`, затем рестарт `issue-webhook`.

Гейт двойной: allowlist контура **и** доступ токена. Событие в репозитории, не прошедшем оба, не будит контур — вебхук роняет его до Temporal с записью в лог.

### Шаг 5. Проверка

Project → Settings → Webhooks → Test → Issues events. Ожидается 200. Смотреть `docker logs …-issue-webhook-1`.

**Важно:** если тестовая доставка провалилась 4 раза подряд, GitLab отключит вебхук с backoff до 24 часов. Не долбить повторами вслепую — сначала читать лог.

---

## 14. Тестирование

### Исходное состояние

814 тестов в 89 файлах. 33 файла касаются `github_client`, но **31 подменяет сам модуль**, а не HTTP. Строка `api.github.com` встречается во всём наборе **три раза**. Библиотек HTTP-моков нет вовсе (`respx`, `responses`, `requests_mock` — 0 совпадений); транспорт мокается вручную через `monkeypatch.setattr(gc.requests, ...)`. Фикстур payload нет ни одной — inline-словари, продублированные по 12 файлам.

Вывод, определяющий порядок работ: **извлечение в пакет пройдёт зелёным даже если URL поедут.** «Поведение не меняется, тесты те же» — ложное успокоение.

### Что делается

1. **Характеризующие тесты на транспорт — до извлечения.** Фиксируют метод, путь и тело для всех операций GitHub-драйвера. Это страховка шага 2 этапов, без неё рефакторинг слепой.
2. **Общие фикстуры payload** — по одной на событие и провайдера, вместо inline-словарей в 12 файлах.
3. **Контрактный набор, параметризованный по провайдеру.** Один сценарий гоняется на обоих драйверах: расхождение возможностей становится падающим тестом, а не сюрпризом в проде.
4. **`tests/conftest.py`** получает autouse-фикстуру изоляции окружения. Сейчас её нет: `GITHUB_WEBHOOK_SECRET` настраивается в 12 местах, `ISSUE_AGENT_REPOS` — в 17, целенаправленная очистка есть только в двух файлах.

---

## 15. Этапы

| # | Этап | Содержание |
|---|---|---|
| 1 | **Закалка** | `RepoRef` и URL-кодирование; allowlist на многосегментных путях; вебхук перестаёт отдавать 5xx; `set_labels(add, remove)`; `ensure_labels_exist`; опознание своих комментариев без `user.type`; характеризующие тесты на транспорт |
| 2 | **Извлечение `poh-forge`** | Единственный драйвер GitHub. Поведение не меняется — но уже под страховкой тестов шага 1 |
| 3 | **Драйвер GitLab** | Notes API, `PUT` для меток, MR, дельта меток из `changes`, граф Issue↔MR из трёх источников, award emoji с `issue_iid` |
| 4 | **Демо** | `gitlab.com/poh-harness/harness-demo-service`: Issue про сервис планирования спринтов → MR с кодом |
| 5 | **Соседи** | `poh-pr-agents` и `poh-pr-closer` переезжают на пакет. Демо не блокируют |

Шаг 1 целиком осмыслен и в одиночку: он убирает 20 лишних DELETE на смену фазы, закрывает транспорт тестами и делает вебхук устойчивым к собственным ошибкам разбора.

---

## 16. Открытые вопросы

Ответы снимаются на стенде, не из документации.

- **Заводит ли GitLab метку автоматически** при применении к Issue — в документации не описано. От этого зависит, обязателен ли `ensure_labels_exist` или он только страховка.
- **Код и текст ошибки при создании MR, который уже существует** — не задокументированы ни в API MR, ни в траблшутинге. Полагаться на «создай и поймай 409» как на контракт нельзя: закладывается pre-check по `?source_branch=&state=opened`.
- **Поведение при рассинхроне `last_commit_id`** в Repository Files API — 400 или 409, не задокументировано.
- **Дефолт `gitlab_rails['webhook_timeout']`** для self-managed: на `gitlab.com` 10 с, в примере кода документации фигурирует 60.
- **`glab` с корпоративным CA** — на `docs.gitlab.com` не описан. Для self-managed блокирующий.
- **Какие из заголовков `RateLimit-*`** реально отдаёт `gitlab.com` — отдельно не описано.

---

## Приложение: текст демо-Issue

Кладётся в `gitlab.com/poh-harness/harness-demo-service` на шаге 4 этапов — после того, как драйвер GitLab заработает. Это payload демо: код пишет контур, не человек.

> **Заголовок:** Сервис планирования спринтов
>
> **Проблема.** Планирование спринта команда ведёт в таблице: задачи, оценки, вместимость. Таблица не знает про скорость команды, не подсказывает, влезает ли набор в спринт, и не хранит историю — сравнить план с фактом через три спринта уже нельзя.
>
> **Что нужно.** Сервис, который принимает список задач с оценками и вместимость команды, отвечает, что влезает в спринт, и хранит историю спринтов, чтобы считать фактическую скорость.
>
> **Сценарии.**
> 1. Завести спринт: даты, состав команды, вместимость в story points.
> 2. Добавить задачу в бэклог спринта: заголовок, оценка, приоритет.
> 3. Спросить, влезает ли текущий набор: ответ — влезает или на сколько превышена вместимость.
> 4. Закрыть спринт: зафиксировать, что сделано, посчитать фактическую скорость.
> 5. Посмотреть скорость за последние N спринтов — чтобы вместимость следующего опиралась на факт, а не на ощущение.
>
> **Границы.** Без UI — только API. Без интеграций с трекерами. Без авторизации: сервис работает внутри доверенного контура.
>
> **Как проверить.** Завожу спринт вместимостью 20, кладу три задачи по 8 — сервис отвечает, что превышение на 4. Убираю одну — отвечает, что влезает. Закрываю спринт с двумя сделанными — скорость 16.
