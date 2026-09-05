# Issue #308 — Implementation Plan

> **Для исполнителя:** план исполняется по задачам сверху вниз, шаг за шагом
> (`- [ ]` — отметка выполнения). Навык-помощник: `superpowers:executing-plans`.
> Исполнять план НЕ из этого файла — этот файл результат планирования; исполняет
> контур. Исполнителю: ничего не коммитить (см. Глобальные ограничения, п. 5).

**Цель:** закрытый влитым PR из фазы `pr-open` получает метку `phase:merged`, а
каждый отказ подписи на канале докладов агентов оставляет строку в логе вебхука
с причиной отказа.

**Архитектура:** два независимых точечных изменения. (1) В таблице переходов
`shared/lifecycle.py` появляется ход `pr-open → merged`, а ветка закрытия
`_phase_on_close` в `worker/workflows.py` начинает задавать вопрос GitHub про
слияние и из `pr-open` — под собственным маркером `workflow.patched`, чтобы
прогоны, уже выбравшие ветку `cancelled`, на реплее выбрали её же. (2) В
`webhook/main.py` функция `verify_agent_signature` перед каждым из трёх отказов
пишет предупреждение в лог: причина и отпечаток тела, без тела и без секрета.

**Стек:** Python 3, Temporal Python SDK (`workflow.patched`), FastAPI (вебхук),
pytest + `temporalio.testing.WorkflowEnvironment`. Чистая логика фаз —
`shared/lifecycle.py` (без сети и Temporal).

---

## Глобальные ограничения

1. **Правка решения воркфлоу — под своим `workflow.patched(...)`.** Маркер —
   ВСЕГДА первым операндом связки (`AGENTS.md`, правило 1). Название нового
   маркера: `issue-lifecycle-pr-open-merged-on-close`. Переименование
   существующих маркеров = отказ по недетерминизму.
2. **`worker/` и `webhook/` — не пакеты.** Импортировать модули напрямую:
   `import main`, `from workflows import ...`, `from shared import lifecycle`
   (`AGENTS.md`, правило 7). `from worker.X import ...` не работает нигде.
3. **TDD обязателен** (`AGENTS.md`, «Как проверять»): сначала падающий тест,
   потом код. Проверки проекта: `make setup` (один раз, если нет `.venv`),
   затем `.venv/bin/pytest -q` — красный прогон не отдаём.
4. **Тексты — по-русски.** Комментарий объясняет ПОЧЕМУ так, а не что делает
   код: какой отказ этим закрыт и чем плоха очевидная альтернатива.
5. **Не коммитить.** Коммит, пуш и PR делает контур после исполнителя.
   `.task.md`, `.verdict.md`, `.followups.md`, `.reflect.md` в коммит не
   попадают (`AGENTS.md`, правило 5).
6. **Фазы `testing` и `released` этой задачей не закрываются** — их не
   докладывает никто, это отдельная задача (граница из `.task.md`).

## Приёмочный сценарий (граница MVP)

Из `.harness/howtodemo.md`:

> было — задача, закрытая влитым PR из фазы `pr-open`, получает метку
> `phase:cancelled`, а отвергнутый по подписи доклад агента не оставляет в логе
> вебхука ни строки; стало — такая задача получает `phase:merged`, а каждый
> отказ подписи виден в логе с причиной отказа.

Сценарий распадается ровно на две независимые половины, каждая закрывается
одной задачей:

| Половина сценария | Чем проверяется |
|---|---|
| `pr-open` + влитый PR → `phase:merged` | `tests/test_workflow_closed_by_merge.py` (задача 1) |
| каждый отказ подписи виден в логе с причиной | `tests/test_agent_event_endpoint.py` (задача 2) |

Без задачи 1 первая половина сценария не проходит: `_phase_on_close`
(`worker/workflows.py:981-983`) возвращает `cancelled`, даже не спросив GitHub,
потому что `lifecycle.can('pr-open', 'merged')` — `False`. Единственный ход
`pr-open → pr-review` объявлен как `EXTERNAL` (доклад PR-Agent, который не
приходит — #103), поэтому ветка `pr-review` из правки
`issue-lifecycle-merged-on-close` сюда не достаёт.

Без задачи 2 вторая половина сценария не проходит: все три отказа
`verify_agent_signature` (`webhook/main.py:294-301`) молча поднимают
`HTTPException`.

---

### Задача 1: ход `pr-open → merged` при закрытии влитым PR

**Files:**
- Modify: `shared/lifecycle.py:157-163` (блок `PR_OPEN` таблицы `TRANSITIONS`)
- Modify: `worker/workflows.py:969-992` (`_phase_on_close`)
- Test: `tests/test_workflow_closed_by_merge.py`
- Test: `tests/test_lifecycle_phases.py:101-104`

**Interfaces:**
- Consumes: ничего — задача независима. Опирается на существующие `self._pr_number`,
  `activities.pr_is_merged` и маркер `issue-lifecycle-merged-on-close` в
  `worker/workflows.py:1231`.
- Produces: (а) в `shared.lifecycle` — ход
  `lifecycle.can(lifecycle.PR_OPEN, lifecycle.MERGED) == True` с инициатором
  `lifecycle.EXTERNAL` и триггером `"PR влит"`; (б) в `worker.workflows` —
  `_phase_on_close()` возвращает `("merged", "merged")` для `self._phase ==
  lifecycle.PR_OPEN` при влитом PR; новый маркер `workflow.patched` с именем
  `issue-lifecycle-pr-open-merged-on-close`. Никто из последующих задач это не
  читает (задача 2 независима), поэтому Produces — контракт для ревью и для
  тестов этой же задачи.

- [ ] **Шаг 1: дописать падающий юнит-тест на таблицу переходов**

В `tests/test_lifecycle_phases.py` в существующий тест
`test_pr_phases_are_driven_by_external_agents` (строки 101-104) добавляется
третья строка:

```python
def test_pr_phases_are_driven_by_external_agents():
    """PR ведут PR-Agent и PR-Closer — Issue-Agent их только слушает."""
    assert lc.initiator(lc.IN_DEVELOPMENT, lc.PR_OPEN) == lc.EXTERNAL
    assert lc.initiator(lc.PR_REVIEW, lc.MERGED) == lc.EXTERNAL
    # Ход появился в #308: без него закрытие влитым PR из `pr-open` молча
    # давало `cancelled` — вопрос GitHub даже не задавался.
    assert lc.initiator(lc.PR_OPEN, lc.MERGED) == lc.EXTERNAL
```

- [ ] **Шаг 2: запустить тест, убедиться, что он падает**

Run: `.venv/bin/pytest tests/test_lifecycle_phases.py::test_pr_phases_are_driven_by_external_agents -q`
Expected: FAIL — `shared.lifecycle.InvalidTransition: переход pr-open → merged не предусмотрен`

- [ ] **Шаг 3: добавить ход в таблицу переходов**

В `shared/lifecycle.py` блок `PR_OPEN` (строки 157-163) целиком:

```python
    PR_OPEN: (
        Transition(PR_REVIEW, EXTERNAL, "PR-Agent начал ревью"),
        # PR влит, пока доклада PR-Agent не было (#103): единственный путь в
        # `pr-review` — внешний доклад, и доведённая до `main` задача из
        # `pr-open` иначе записывалась снятой с обработки.
        Transition(MERGED, EXTERNAL, "PR влит"),
        Transition(IN_DEVELOPMENT, EXTERNAL, "PR закрыт без слияния"),
        Transition(FAILED, EXTERNAL, "CI красный"),
        Transition(ESCALATED, EXTERNAL, "нужен человек"),
        Transition(CANCELLED, HUMAN, "снято с обработки"),
    ),
```

- [ ] **Шаг 4: написать падающие тесты поведения воркфлоу**

В `tests/test_workflow_closed_by_merge.py` функции `_drive_to_pr_review` и
`_run` (строки 138-171) заменяются на следующие — прежняя жёстко вела до
`pr-review`, а новая граница ровно в `pr-open`:

```python
async def _drive_to(env, handle, path: tuple[str, ...]) -> None:
    """Довести цикл до заданной фазы фактами внешнего агента.

    Сам цикл из `pr-open` не выходит: единственный ход дальше объявлен как
    EXTERNAL — его приносит доклад PR-Agent, которого в тесте заменяет сигнал.
    """
    await _wait_for_park(env, handle)
    for phase in path:
        await handle.signal(IssueLifecycle.agent_event, _event(phase))
        for _ in range(300):
            if await handle.query(IssueLifecycle.phase) == phase:
                break
            await env.sleep(1)
        assert await handle.query(IssueLifecycle.phase) == phase, \
            f"цикл не дошёл до {phase}"


async def _run(merged: bool,
               path: tuple[str, ...] = ("ready-for-dev", "pr-open", "pr-review"),
               ) -> tuple[str, list[str]]:
    _phases.clear()
    _asked.clear()
    _merged["value"] = merged
    async with await WorkflowEnvironment.start_time_skipping() as env:
        tq = f"tq-{uuid.uuid4()}"
        async with Worker(env.client, task_queue=tq,
                          workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation],
                          activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                IssueLifecycle.run, _issue(), id=f"wf-{uuid.uuid4()}", task_queue=tq)
            await _drive_to(env, handle, path)

            await handle.signal(IssueLifecycle.issue_closed, "github-actions[bot]")

            await handle.result()
            phase = await handle.query(IssueLifecycle.phase)
            desc = await handle.describe()
            assert desc.status == WorkflowExecutionStatus.COMPLETED, \
                "закрытый Issue обязан завершить цикл в любом исходе"
    return phase, list(_phases)
```

Новые тесты — в конец того же модуля, после `test_no_pr_no_question_to_github`:

```python
@pytest.mark.timeout(180)
async def test_pr_open_and_merged_pr_closes_as_merged():
    # Граница #308: в `pr-open` цикл попадает и без доклада PR-Agent (#103).
    # Прежняя ветка закрытия возвращала `cancelled`, не задавая вопроса GitHub,
    # — доведённая до `main` задача числилась снятой с обработки.
    phase, phases = await _run(merged=True, path=("ready-for-dev", "pr-open"))
    assert phase == "merged", "доведённый до main Issue помечен как снятый с обработки"
    assert phases[-1] == "merged", f"метка фазы не доехала: {phases}"
    assert _asked == [("o/r", 81)], "цикл не спросил GitHub про свой PR"


@pytest.mark.timeout(180)
async def test_pr_open_and_unmerged_pr_still_closes_as_cancelled():
    # Спрашивается сам PR, а не тот, кто закрыл Issue: вопрос из `pr-open` не
    # отменяет прежнего правила — закрыли без слияния, значит это снятие с
    # обработки, а не успех.
    phase, phases = await _run(merged=False, path=("ready-for-dev", "pr-open"))
    assert phase == "cancelled"
    assert phases[-1] == "cancelled", f"метка фазы не доехала: {phases}"
```

- [ ] **Шаг 5: запустить тесты, убедиться, что новый тест красный**

Run: `.venv/bin/pytest tests/test_workflow_closed_by_merge.py -q`
Expected: `test_pr_open_and_merged_pr_closes_as_merged` FAIL с
`AssertionError: доведённый до main Issue помечен как снятый с обработки`
(фаза остаётся `cancelled`). Остальные тесты модуля зелёные.

- [ ] **Шаг 6: правка решения воркфлоу — под маркером**

В `worker/workflows.py` функция `_phase_on_close` (строки 969-992) заменяется
целиком:

```python
    async def _phase_on_close(self) -> tuple[str, str]:
        """Чем закончился путь Issue: слиянием или снятием с обработки.

        Спрашиваем сам PR, а не того, кто закрыл Issue: закрыть его по `Closes`
        может и бот, и человек, а `state_reason` у закрытия «как выполненное»
        одинаков в обоих случаях. Номер PR у цикла уже есть — он запомнил его,
        когда PR открылся.

        Вопрос задаём, только если ответ может что-то изменить: PR нет либо из
        текущей фазы в `merged` хода нет — значит, это отмена, и лишний вызов
        GitHub на каждом закрытии не нужен.
        """
        if self._issue is None or not self._pr_number:
            return (lifecycle.CANCELLED, "cancelled")
        # Ход `pr-open → merged` объявлен позже остальных (#308). Прогоны,
        # чья история записана до выкладки, на закрытии из `pr-open` уже выбрали
        # ветку `cancelled` — без вопроса GitHub. Вопрос на реплее появился бы
        # в истории, которой не было, и Temporal уронил бы прогон
        # недетерминизмом (см. #263). Маркер — первым операндом связки
        # (AGENTS.md, правило 1): у таких прогонов `patched` отвечает «нет».
        if (not workflow.patched("issue-lifecycle-pr-open-merged-on-close")
                and self._phase == lifecycle.PR_OPEN):
            return (lifecycle.CANCELLED, "cancelled")
        if not lifecycle.can(self._phase, lifecycle.MERGED):
            return (lifecycle.CANCELLED, "cancelled")
        merged = await workflow.execute_activity(
            activities.pr_is_merged,
            args=[self._issue.repo, self._pr_number],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        if merged:
            return (lifecycle.MERGED, "merged")
        return (lifecycle.CANCELLED, "cancelled")
```

Маркер и правка решения выкладываются одним изменением: маркер «задним числом
не лечит» (`AGENTS.md`, правило 1), отдельного коммита под таблицу быть не
должно.

- [ ] **Шаг 7: прогнать тесты задачи**

Run: `.venv/bin/pytest tests/test_workflow_closed_by_merge.py tests/test_lifecycle_phases.py -q`
Expected: все зелёные, включая прежние `test_merged_pr_closes_the_issue_as_merged`,
`test_unmerged_pr_still_closes_as_cancelled`,
`test_no_pr_no_question_to_github` — поведение из `pr-review` не изменилось.

- [ ] **Шаг 8: проверить реплей историй — маркер не ломает записанное**

Run: `.venv/bin/pytest tests/test_workflow_replay.py -q`
Expected: PASS — фикстуры `tests/replay/histories/` записаны прежним кодом, и
новая ветка обязана оставить их на прежнем пути (маркер в их истории
отсутствует).

Run: `.venv/bin/pytest -q`
Expected: весь прогон зелёный (порог покрытия — `.coveragerc`).

---

### Задача 2: отказ подписи доклада агента виден в логе

**Files:**
- Modify: `webhook/main.py:286-301` (`verify_agent_signature`)
- Test: `tests/test_agent_event_endpoint.py`

**Interfaces:**
- Consumes: ничего — задача независима от задачи 1 (общих сущностей нет: одна
  правит решение воркфлоу, другая — логирование в вебхуке). Использует
  существующие `_log = logging.getLogger("webhook")` (`webhook/main.py:77`) и
  импортированный там же `hashlib`.
- Produces: `verify_agent_signature(body: bytes, signature_header: str | None) -> None`
  — сигнатура и три кода ответа (503/401/401) не меняются; добавляется
  предупреждение в логгер `webhook` перед каждым `raise`. Формат строки:
  `доклад агента отклонён (len=<N> sha256=<12 hex>): <причина>`, где причина —
  `AGENT_EVENT_SECRET не задан`, `подпись не передана` или `подпись не
  совпала`. Эндпоинт `/agent-event` (`webhook/main.py:344`) — единственный
  вызыватель, правок не требует.

- [ ] **Шаг 1: написать падающие тесты**

В `tests/test_agent_event_endpoint.py` в раздел `# --- авторизация ---`
(после `test_endpoint_is_closed_when_the_secret_is_not_configured`, строка 106)
добавляются три теста:

```python
def test_rejection_is_visible_in_the_log(webhook, caplog):
    """Канал доклада, тихо переставший работать, обязан быть виден в логе
    контура. Соседний сервис видит лишь код ответа: между 28 августа и
    4 сентября канал доклада отвалился (#241), и по логам контура этого не
    было видно вовсе."""
    fake, app_client = webhook()

    with caplog.at_level("WARNING", logger="webhook"):
        _post(app_client, _event(), sign=False)
        _post(app_client, _event(), secret="чужой")

    assert "подпись не передана" in caplog.text
    assert "подпись не совпала" in caplog.text
    assert fake.started == []


def test_unconfigured_secret_is_visible_in_the_log(webhook, monkeypatch, caplog):
    """Эндпоинт закрыт целиком — это тоже отказ, а не тишина: иначе outage
    конфигурации выглядит в логах как отсутствие трафика."""
    monkeypatch.delenv("AGENT_EVENT_SECRET", raising=False)
    fake, app_client = webhook()

    with caplog.at_level("WARNING", logger="webhook"):
        _post(app_client, _event())

    assert "AGENT_EVENT_SECRET" in caplog.text
    assert fake.started == []


def test_rejection_log_carries_no_secret_and_no_body(webhook, caplog):
    """В запись идут причина и отпечаток тела. Тело может нести чужое, а
    подпись позволяет повторить ровно этот запрос — обе в лог не попадают."""
    fake, app_client = webhook()
    payload = _event(detail="служебное-содержимое-доклада")

    with caplog.at_level("WARNING", logger="webhook"):
        _post(app_client, payload, secret="чужой")

    assert "служебное-содержимое-доклада" not in caplog.text
    assert SECRET not in caplog.text
    assert "чужой" not in caplog.text
```

- [ ] **Шаг 2: запустить тесты, убедиться, что они падают**

Run: `.venv/bin/pytest tests/test_agent_event_endpoint.py -q`
Expected: FAIL два новых теста про лог (`подпись не передана` not in
`caplog.text` и `AGENT_EVENT_SECRET` not in `caplog.text`); третий
(`test_rejection_log_carries_no_secret_and_no_body`) зелёный уже сейчас — он
держит границу, которую реализация не должна перейти. Существующие тесты
раздела «авторизация» зелёные.

- [ ] **Шаг 3: добавить запись отказа в лог**

В `webhook/main.py` функция `verify_agent_signature` (строки 286-301)
заменяется целиком:

```python
def verify_agent_signature(body: bytes, signature_header: str | None) -> None:
    """Подпись входящего события агента — своим секретом, не гитхабовским.

    Сигнал, двигающий фазу Issue, не может приходить анонимно. Секрет отдельный:
    у соседних сервисов свои права, и утечка одного не должна открывать второй
    канал. Без переменной эндпоинт закрыт (503, а не «пропускаем всех») —
    молчаливо открытый приём фазовых событий хуже, чем выключенный.

    Каждый отказ пишется в лог: соседний сервис видит только код ответа, и его
    предупреждение остаётся на его стороне. Так канал доклада, тихо переставший
    работать (#241), становится виден в логах контура. В запись идут причина и
    отпечаток тела — не тело и не подпись: тело может нести чужое, а подпись
    позволяет повторить ровно этот запрос.
    """
    fingerprint = f"len={len(body)} sha256={hashlib.sha256(body).hexdigest()[:12]}"
    secret = os.environ.get("AGENT_EVENT_SECRET", "")
    if not secret:
        _log.warning("доклад агента отклонён (%s): AGENT_EVENT_SECRET не задан",
                     fingerprint)
        raise HTTPException(status_code=503, detail="AGENT_EVENT_SECRET не задан")
    if not signature_header or not signature_header.startswith("sha256="):
        _log.warning("доклад агента отклонён (%s): подпись не передана", fingerprint)
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        _log.warning("доклад агента отклонён (%s): подпись не совпала", fingerprint)
        raise HTTPException(status_code=401, detail="Invalid signature")
```

- [ ] **Шаг 4: прогнать тесты задачи**

Run: `.venv/bin/pytest tests/test_agent_event_endpoint.py -q`
Expected: все зелёные, включая прежние `test_unsigned_event_is_rejected`,
`test_event_signed_with_a_wrong_secret_is_rejected`,
`test_github_secret_does_not_open_this_channel`,
`test_endpoint_is_closed_when_the_secret_is_not_configured` — коды ответов и
поведение `fake.started == []` не изменились.

Run: `.venv/bin/pytest tests/test_review_events.py tests/test_webhook_subissue_ignored.py tests/test_webhook_imports_nothing_from_worker.py -q`
Expected: PASS — эти модули тоже ходят через `/agent-event` и подпись; ничего
кроме записи в лог не изменилось.

---

### Задача 3: след решения и находки

**Files:**
- Create: `.reflect.md` (корень рабочего каталога)
- Create: `.followups.md` (корень рабочего каталога; только если есть находки)

**Interfaces:**
- Consumes: обе задачи выполнены и оба прогона тестов зелёные — след описывает
  то, что уже стоит в рабочем дереве.
- Produces: ничего в код; файлы контур снимает до коммита (`AGENTS.md`,
  правило 5), в `.gitignore` они не попадают намеренно.

- [ ] **Шаг 1: записать `.reflect.md`** тремя разделами, по строке на пункт:
  `## Намерение` (почему маркер `issue-lifecycle-pr-open-merged-on-close`, а не
  расширение старого `issue-lifecycle-merged-on-close`; почему запись отказа —
  в `verify_agent_signature`, а не в обработчике `/agent-event`), `## Допущения`,
  `## Сомнения`.

- [ ] **Шаг 2: записать `.followups.md`** — по разделу
  `## <кратко что не учтено>` на находку, в теле где (файл:строка), чем грозит,
  при каких условиях всплывёт. Ничего не нашёл — файл не создавать. Заявка
  Issue по находкам — на контуре, `gh` и токена у исполнителя нет.

- [ ] **Шаг 3: финальный прогон**

Run: `.venv/bin/pytest -q`
Expected: зелёный. Файлов `.reflect.md` / `.followups.md` / `.task.md` в
`git status` не стесняться — их снимает контур.

---

## Вне MVP

Не входит в эту ветку — критерий границы: без перечисленного сценарий приёмки
проходит.

1. **Фазы `testing` и `released`.** Их не докладывает никто; в `.task.md`
   обозначены как отдельный вопрос (соседняя задача).
2. **Логирование отказов подписи GitHub-вебхука** — `verify_signature`
   (`webhook/main.py:136-142`). Сценарий говорит про доклад агента
   (`verify_agent_signature`), у GitHub-канала свой отправитель и свои ретраи.
3. **Обновление таблицы маркеров в `AGENTS.md`** (правило 1). Таблица уже не
   полна (в коде маркеров больше, чем в списке), сценарий от неё не зависит;
   заводить правку документации в ветку с двумя строчными изменениями — лишний
   круг ревью.
4. **Полный реплей корпуса со стенда** (`python scripts/replay_histories.py`,
   `make deploy-check ARGS=--replay`). Фикстурный гвард в задаче 1 шаг 8
   выполняется; снятие корпуса требует доступного Temporal и делается на
   выкладке.
