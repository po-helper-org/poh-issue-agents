# AGENTS.md

Постоянный контекст для агентов, работающих в этом репозитории. Полный свод —
[`README.md`](README.md); здесь то, что обязано быть в голове ДО первой правки.

## Что это

`poh-issue-agents` — Issue-Agent контура производства: он ведёт Issue от заявки
до открытого PR. Не набор скриптов, а **долгоживущий воркфлоу Temporal**, который
владеет состоянием задачи неделями.

Три процесса в одном образе:

- `webhook/main.py` — приём событий GitHub и докладов соседних агентов, запуск и
  сигналы воркфлоу. Ничего не решает сам;
- `worker/workflows.py` — `IssueLifecycle` (цикл поверх таблицы фаз), командные
  воркфлоу (`IssueAnalysis`, `IssueEstimation`, консолидация) и служебные
  (`CommentAck` — реакция на комментарий, `WebhookAudit` — след отброшенной
  доставки);
- `worker/activities.py` — всё, что трогает внешний мир: GitHub, LLM, git,
  контейнеры.

`shared/` — чистые модули без сети и Temporal: `lifecycle` (фазы и переходы),
`awaiting` (вид ожидания), `decomposition` (MVP/GROW/SUPPORT), `develop`
(контракт агента разработки), `pr_closing` (круг правок), `agent_events`
(контракт докладов), `labels`, `commands`. Логика проверяется на них напрямую, а
не прогоном воркфлоу.

## Правила, которые дороже всего нарушить

### 1. Изменил РЕШЕНИЕ воркфлоу — заведи `workflow.patched(...)`

Ветку, которую прогон уже выбрал, он держит в Event History. Новый код на реплее
выбирает другую, и Temporal валит прогон:

```
Nondeterminism error: Activity machine does not handle this event
Nondeterminism error: Timer machine does not handle this event
```

После этого Issue перестаёт отвечать на сигналы **вовсе** — снаружи неотличимо от
мёртвого. Решением считается и вид ожидания, и длительность таймера, и порядок
активностей. Правка тела активности, её ретраев и меток безопасна: их в истории
нет.

Переименование любого маркера = отказ по недетерминизму на живых прогонах.
Ниже — те, чью историю важно помнить; **полный** список, проверяемый тестом,
лежит в реестре следом за ними:

| Маркер | Что разводит |
|---|---|
| `issue-lifecycle-phase-loop` | фазовый цикл против прежнего линейного `_run_linear` |
| `issue-lifecycle-awaiting` | публикацию метки очереди к людям |
| `issue-lifecycle-absolute-park-deadline` | срок парковки от входа в фазу, а не от последнего сигнала |
| `issue-lifecycle-clear-queue-on-work` | снятие метки очереди на входе в рабочую фазу |
| `issue-lifecycle-analyze-recovers-failed` | ход `failed → business-analysis` по `/analyze` |
| `issue-lifecycle-plan-member-skips-analysis` | подзадача плана идёт мимо своей аналитики |
| `issue-lifecycle-plan-member-waits-for-parent` | подзадача ждёт контур, а не человека |
| `issue-lifecycle-clarify-after-analysis` | круг уточнений после аналитики |
| `issue-lifecycle-merged-from-pr-open` | закрытие влитым PR из `pr-open` — успех, а не отмена |

**`workflow.patched(...)` зовётся ТАМ, где ветвление, и никуда не переносится.**
Правка 5 сентября (#311, PR #313): прежняя формулировка требовала обратного —
«первым операндом связки, всегда» — и, исполненная буквально, приводила ровно к
тому отказу, от которого правило защищает. Проверено разбором SDK и живым
воспроизведением, а не рассуждением.

Что делает `workflow.patched` (`temporalio/worker/_workflow_instance.py:1067`):

```python
use_patch = self._patches_memoized.get(id)
if use_patch is not None:
    return use_patch                       # решение первого вызова — на весь прогон
use_patch = not self._is_replaying or id in self._patches_notified
self._patches_memoized[id] = use_patch
if use_patch:
    command = self._add_command()          # маркер уходит в историю ЗДЕСЬ
```

Отсюда два следствия, и оба ломают живые прогоны.

**Перенос вызова через `await` убивает прогон.** `_patches_notified` наполняется
на КАЖДУЮ задачу воркфлоу отдельно. Вызов, поднятый выше `await`, попадает в
более раннюю задачу: там маркера ещё не объявляли, `patched` возвращает False,
запоминает это на весь прогон и команду не выдаёт — а в истории маркер лежит
дальше, в своей задаче. Реплей падает:

    [TMPRL1100] Nondeterminism error: Non-deprecated patch marker encountered
    for change p, but there is no corresponding change command!

Воспроизведено на игрушечном воркфлоу против установленного SDK: v1 пишет
маркер во второй задаче, v2 поднимает вызов в первую, реплей истории v1 против
v2 падает этим текстом; контроль v1 против v1 проходит.

**Вызов раньше прежнего замораживает старые прогоны на старой ветке.** Решение
первого вызова запоминается на весь прогон. Прогон, припаркованный до выкладки,
маркера в истории не имеет: вызов, случившийся на реплее, вернёт False, запишет
False — и до конца жизни прогона новая ветка ему недоступна, хотя прежний код
дошёл бы до вызова живьём и получил True.

**Что делать.** Оставлять вызов на месте ветвления: `if some_flag and
workflow.patched(...)` — нормальная форма. При ОДНОМ читателе маркера она
реплеится верно: история с маркером находит его в своей задаче, история без
маркера просто не звала вызов, а на живом краю получает True.

Опасность не в порядке операндов, а во ВТОРОМ читателе того же идентификатора.
Решение первого вызова запоминается на весь прогон (`_patches_memoized` выше), и
второй читатель получает уже принятое — даже если сам добрался бы до живого края
и получил True. Практически это значит: ранний читатель, срабатывающий на
реплее старой истории, ЗАКРЫВАЕТ ветку позднему до конца жизни прогона.

`issue-lifecycle-merged-from-pr-open` заведён именно так — одна строка таблицы
переходов, два читателя (`IssueLifecycle._phase_on_close` и `_agent_event`), — и
цена у этого следующая: прогон, начатый до выкладки и успевший обработать доклад
внешнего агента, к моменту закрытия задачи получит уже запомненное False и
запишет `cancelled`, хотя правка #308 делалась ровно против этого. Прогонов,
припаркованных в `pr-open` БЕЗ единого доклада, это не касается: `pr-open` цикл
проставляет себе сам (`Transition(PR_OPEN, AGENT, ...)`), и `_agent_event` у них
на реплее не зовётся.

Отсюда правило для нового кода: второму читателю — свой идентификатор, если не
доказано, что ранний вызов не случается раньше позднего.

### Реестр: все маркеры и где они живут

Таблица выше — те, чью историю важно помнить. Реестр ниже — **все**, и он
проверяется тестом `tests/test_patch_markers.py`: маркер, добавленный в код и не
внесённый сюда, роняет прогон тестов; строка про несуществующий маркер и
неверное место — тоже.

Прозы здесь нет намеренно. Место в коде проверяемо, а пересказ намерения для
сорока маркеров разъезжается молча — так и разъехалась таблица выше, знавшая
девять из сорока (#311).

<!-- markers:start -->

| Маркер | Где вызывается |
|---|---|
| `issue-development-partial-publish` | `IssueDevelopment.run` |
| `issue-development-repair-loop` | `IssueDevelopment.run` |
| `issue-lifecycle-absolute-park-deadline` | `IssueLifecycle._park_timeout` |
| `issue-lifecycle-acceptance-gate` | `IssueLifecycle._start_development` |
| `issue-lifecycle-acceptance-gate-stall-notice` | `IssueLifecycle._start_development` |
| `issue-lifecycle-acceptance-gate-stall-notice-safe` | `IssueLifecycle._start_development` |
| `issue-lifecycle-analyze-recovers-failed` | `IssueLifecycle._analysis_requested` |
| `issue-lifecycle-answer-command-without-open-question` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-answer-question-failure-notice` | `IssueLifecycle._answer_open_question` |
| `issue-lifecycle-ask-question-failure-message` | `IssueLifecycle._start_development` |
| `issue-lifecycle-ask-question-failure-safe` | `IssueLifecycle._start_development` |
| `issue-lifecycle-autostart-waits-for-answer` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-awaiting` | `IssueLifecycle._publish_awaiting` |
| `issue-lifecycle-bft` | `IssueLifecycle._phase_triage` |
| `issue-lifecycle-capture-episode-always` | `IssueDevelopment.run` |
| `issue-lifecycle-clarify-after-analysis` | `IssueLifecycle._clarify_open_questions` |
| `issue-lifecycle-clear-queue-on-work` | `IssueLifecycle._enter` |
| `issue-lifecycle-close-confirmed-duplicate` | `IssueLifecycle._phase_park` |
| `issue-lifecycle-comment-intent-reply-activity` | `IssueLifecycle._handle_comment_intent` |
| `issue-lifecycle-criterion-filled-by-hand-closes-question` | `IssueLifecycle._start_development` |
| `issue-lifecycle-criterion-recheck-stall-notice` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-criterion-recheck-while-parked` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-develop-child` | `IssueLifecycle._begin_development` |
| `issue-lifecycle-develop-plan-stage` | `IssueDevelopment.run` |
| `issue-lifecycle-duplicate-exit-checks-existing-labels` | `IssueLifecycle._phase_park` |
| `issue-lifecycle-empty-run-diagnosis` | `IssueDevelopment.run` |
| `issue-lifecycle-followup-answer` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-howtodemo-on-pr-open` | `IssueLifecycle._phase_park` |
| `issue-lifecycle-merged-from-pr-open` | `IssueLifecycle._agent_event`, `IssueLifecycle._phase_on_close` |
| `issue-lifecycle-merged-on-close` | `IssueLifecycle._run_phase_loop` |
| `issue-lifecycle-phase-loop` | `IssueLifecycle.agent_event`, `IssueLifecycle.analyze_requested`, `IssueLifecycle.bft_requested`, `IssueLifecycle.estimate_requested`, `IssueLifecycle.run` |
| `issue-lifecycle-plan-member-skips-analysis` | `IssueLifecycle._phase_await_decision`, `IssueLifecycle._phase_park` |
| `issue-lifecycle-plan-member-waits-for-parent` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-prfix-child` | `IssueLifecycle._phase_pr_review` |
| `issue-lifecycle-question-answer` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-question-close-failure-notice` | `IssueLifecycle._start_development` |
| `issue-lifecycle-question-repoint-failure-notice` | `IssueLifecycle._answer_open_question`, `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-reasked-question-repoints-pointer` | `IssueLifecycle._answer_open_question` |
| `issue-lifecycle-repoint-open-question-on-answer` | `IssueLifecycle._phase_await_build` |
| `issue-lifecycle-step-subissue-barrier` | `IssueLifecycle._run_phase_loop` |

<!-- markers:end -->

**Маркер ставится ДО выкладки, задним числом он не лечит.** `workflow.patched`
на реплее смотрит не на то, что произошло, а на наличие своего маркера в
истории. Прогон, успевший пройти новую ветку живьём до появления маркера, его
в истории не имеет — и добавленный позже маркер уводит такой прогон в старую
ветку. Расхождение получается зеркальным, и бьёт оно по работающим прогонам, а
не по сломанным.

Проверено числами 2026-08-26 на корпусе из 149 историй — это истории всех
прогонов, числящихся запущенными, а не только живых (29 из них к тому моменту
уже мертвы): маркер, заведённый через четыре дня после правки, чинил 29
прогонов и ломал 45.

**Мёртвый прогон лечится сбросом, а не правкой кода.** Его история записана
прежним кодом и расходится с любым новым по определению.

**Вставший прогон теперь виден.** Расхождение не роняет воркфлоу — Temporal
валит workflow task и повторяет его бесконечно, прогон остаётся в `Running`, и
снаружи это неотличимо от «задача стоит и ждёт человека». Наблюдатель
(`shared/nondeterminism.py`, ставится в `worker/worker.py`) поднимает такой
отказ до строки `НЕДЕТЕРМИНИЗМ:` в логе и события Sentry с fingerprint
`nondeterminism` — одного на все пострадавшие прогоны, потому что причина у них
одна. Сколько прогонов под ударом ДО выкладки — `make deploy-check`.

**Почему не `workflow_failure_exception_types=[NondeterminismError]`.** У
воркера есть настройка, превращающая расхождение в падение воркфлоу вместо
зависания, и «видимый след» она даёт сама собой. Она не включена намеренно:
зависший прогон восстанавливается откатом воркера на прежний образ, а упавший —
уже никогда. Это размен восстановимой остановки на невосстановимую потерю, и
делать его ради заметности нельзя (в SDK настройка к тому же помечена
экспериментальной).

**Перед правкой решения — проиграть истории живых прогонов.** Тест
`tests/test_workflow_replay.py` держит представительные фикстуры и гоняется на
каждом PR — это сигнал по узкой выборке, не гарантия: фикстур единицы, а форм
пути десятки, и правка может ломать именно ту форму, которая в выборку не
попала. Полную проверку даёт только прогон ВСЕГО корпуса со стенда скриптом:

    python scripts/replay_histories.py <каталог со снятыми историями>

Ненулевой код возврата означает, что правка ломает идущее. Команда снятия
корпуса — в докстринге скрипта; снимать его руками нужно не всегда — когда
Temporal доступен, истории живых прогонов тянет прямо оттуда `make deploy-check
ARGS=--replay`. Именно прогон всего корпуса поймал бы
`ac625e7` до мержа: PR-тест держит представительную, но не исчерпывающую
выборку, и в момент инцидента она не покрывала форму пути, которую правка
ломала, — эксперимент на фикстурах того времени остался зелёным и на самой
поломке, и на попытке её откатить.

**У реплея есть слепая зона: длительность таймеров.** И тест, и скрипт
проверяют только уже записанную часть истории — что прогон выдаёт ту же
последовательность команд того же типа, а не с какими аргументами. Выше
длительность таймера отнесена к решению воркфлоу, но гвард её не ловит:
подмена срока парковки на 7 секунд не изменила исход прогона ни на одной
истории корпуса. Маркер на такую правку всё равно обязателен — просто не
рассчитывай, что тест или скрипт эту правку поймают.

### 2. Состояние, которое читают фазы после перезапуска, обязано быть в снимке

Цикл делает `continue_as_new` по порогу истории. Поле, добавленное в
`IssueLifecycle` и забытое в `LifecycleState`, теряется молча. Так терялся номер
PR: фаза доведения не знала, что доводить, и вместо круга правок уходила в
парковку. Полнота снимка проверяется механически —
`test_snapshot_carries_everything_the_later_phases_read`.

### 3. Одна фаза — ровно одна метка `phase:*`

Две метки означали бы противоречие, и `phase_from_labels` отказывается угадывать.
Исход команды тоже один: `done:<cmd>` и `failed:<cmd>` не висят вместе.

### 4. `label:needs-human:*` — ПОЛНАЯ очередь к людям

Метка стоит, пока ход за человеком, и только тогда. Задача, которую ведёт агент,
в этой выборке — шум, из-за которого на саму выборку перестают смотреть. Ожидание
машины (стенд, соседний сервис, прогон разработки по родителю) метку не ставит.

### 5. Мусор контура не уезжает в коммит

`.task.md` (постановка), `.verdict.md` (разбор замечаний), `.followups.md`
(находки) живут в рабочем дереве и попадают под `git add -A`. Каждый снимается до
коммита. `.task.md` однажды уехал в PR один-файлом-на-1721-строку и заодно обманул
гвард «изменений нет — открывать нечего»; в круге правок он менялся каждый круг,
из-за чего исход «замечаний нет» был недостижим в принципе.

### 6. Агенту разработки не дают GitHub-токен

Он исполняет код чужого репозитория. Коммит, пуш и PR делает воркер после него.
Поэтому же находки агент оставляет **файлом**, а не через `gh`.

### 7. `worker` и `webhook` — не пакеты; импортировать модули напрямую

Раскладка несимметрична, и это свойство сборки, а не упущение:

| Каталог | `__init__.py` | В образе | Как импортировать |
|---|---|---|---|
| `shared/` | есть | `/app/shared/` у обоих сервисов | `from shared.workflow_types import ...` |
| `worker/` | нет | содержимое плоско в `/app` (`COPY worker/ .`) | `import llm`, `import github_client` |
| `webhook/` | нет | содержимое плоско в `/app` (`COPY webhook/ .`) | `import main` |

`from worker.X import ...` не работает **нигде**: в образе воркера каталога
`worker/` не существует (файлы лежат в корне `/app`), в образе вебхука его нет
вовсе, а в тестах имя `worker` перехватывает модуль `worker/worker.py` — отсюда
`ModuleNotFoundError: ... 'worker' is not a package`.

Ошибка предсказуема: в тестах 58 импортов вида `from shared.X`, и по этому
образцу пишется `from worker.Y`. Три раза подряд так и вышло (#179, #199, #233).

Добавить `__init__.py` — не исправление: тесты позеленеют, а в образе вебхука
каталога `worker/` всё равно нет. Проверяет это `tests/test_webhook_imports_nothing_from_worker.py`.

### 8. Фикстура pytest из чужого тестового модуля не видна

Общее место ровно одно — `tests/conftest.py`. Фикстура, объявленная в
`tests/test_foo.py`, для `tests/test_bar.py` не существует: `fixture 'X' not
found` на сборке, а не на прогоне.

Переносить чужую фикстуру в `conftest.py` ради своего теста нельзя. Имя может
быть занято дважды с РАЗНЫМ поведением: `make_client` объявлен и в
`test_webhook_label_trigger.py`, и в `test_webhook_audit.py` — разные подделки
и разные аргументы `_build`. Перенос одной из них молча подменил бы фикстуру
второму модулю.

Нужна общая — заводи свою в своём модуле либо выноси в `conftest.py` под новым
именем, не трогая существующие.

### 9. Свои правила старше импортированных практик

В постановку агента приезжают два источника: практики superpowers
(`.claude/skills/`, импортированы, обновляются извне) и правила организации
(`harness-memory-base/rules/`, курируются человеком, меняются только PR).

Практики отвечают на вопрос КАК делать. Правила организации — что считать
сделанным и чего не делать. Противоречие разрешается в пользу своих правил.

Без объявленного старшинства выбирает исполнитель, и выбор будет разным от
прогона к прогону.

## Отказы, которые выглядят как исправная работа

Самый дорогой класс: шаг отработал, успех доложен, результата нет. Проверять
результатом, а не статусом.

| Признак | Причина |
|---|---|
| PR открыт, диффа по существу нет | каталог задачи не передан раннеру: воркер root, раннер uid 10001 (`develop.RUNNER_UID`). Агент не падает — уходит писать в `/tmp` и докладывает об успехе |
| в PR заглушка «Preparing review...» | `pr-agent` вышел нулём на rate-limit модели; исход надо определять по выводу, а не по коду возврата |
| стадия FNR: «артефакт не создан» | `claude -p` тоже выходит нулём без артефакта; частая причина — rate-limit z.ai |
| круг правок «внёс правки», а в диффе только служебный файл | см. правило 5 |
| второй круг не начинается | ключ идемпотентности доклада не различал круги; сейчас в него входит `revision` (коммит) |
| проверки красные на зелёном коде | Node воркера разошёлся с CI целевого репозитория. Тест сверяет мажорные версии образов воркера и раннера |
| в логе «не смог поставить реакцию», реакции нет | `from worker import ...` в вебхуке: модуля нет в его образе. `except Exception` съедал и это, и `NameError` от неимпортированного `asyncio` (жило на `main` с `aa3551d`) |

## Как проверять

```bash
make setup          # venv + зависимости
make test           # 653 теста, порог покрытия в .coveragerc
```

TDD обязателен: сначала падающий тест, потом код. Каждая правка контура,
найденная живым прогоном, оформляется тестом на СТЫК, а не на happy path — иначе
она вернётся.

Живой прогон — не замена тестам, а другой инструмент: он один отвечает на
вопросы «доехал ли вебхук», «отвечает ли модель», «пишет ли агент в свой
каталог». Скрипты — `scripts/e2e_live.py`, `scripts/demo_e2e.py`,
`scripts/diag.py` (последний печатает конфиг без значений секретов).

## Выкладка

Стенд и порядок выкладки — в `po-helper-org/poh-infra`, `harness/STATUS.md`.
Коротко: контекст сборки пинится на **полный SHA**, иначе BuildKit молча собирает
прежний код; выкладывать между прогонами, а не посреди (см. правило 1 и убитые
heartbeat-ом активности).

## Стиль

Комментарий объясняет ПОЧЕМУ так, а не что делает код: какой отказ этим закрыт и
чем плоха очевидная альтернатива. Ссылка на живой инцидент ценнее общего
рассуждения. Тексты — по-русски, как весь репозиторий.
