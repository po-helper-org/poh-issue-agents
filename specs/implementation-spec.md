# Implementation Spec: Issue Agent Service

> Формат: spec-driven (совместим с OpenSpec/Superpower обработкой).
> Назначение: вход для агентного исполнения. Каждая capability имеет
> WHY / WHAT / ACCEPTANCE / TASKS. Задачи атомарны и проверяемы.
> Порядок capability соответствует фазам ROADMAP.md.

## Context

Платформа автономной обработки GitHub Issues на self-hosted стеке
(docker-compose + Temporal + GLM через z.ai). Заготовка кода существует
(webhook/worker/activities/workflows). Задача исполнения — довести заглушки
до рабочего состояния по фазам и закрыть инфраструктурные блокеры.

Стек зафиксирован (см. docs/DECISIONS.md): менять оркестратор/модель/деплой
не в объёме. Исполнять в рамках принятых ADR.

Инварианты, которые НЕЛЬЗЯ нарушать при исполнении:
- INV-1. Priority Scoring: LLM только извлекает атрибуты, расчёт — чистый
  детерминированный Python по формуле из config/priority-weights.toml.
- INV-2. Дорогие стадии (research/bug) стартуют только по сигналу человека
  (лейбл), никогда автоматически.
- INV-3. Workflow-код (workflows.py) не делает прямых I/O — только через
  activities (требование Temporal replay-детерминизма).
- INV-4. Один workflow на Issue, ID = issue-<repo>-<n> (идемпотентность).
- INV-5. Сбой не оставляет Issue без обратной связи в комментариях.

---

## Capability 1: Инфраструктура и приём событий

**WHY:** без поднятого сервиса и доступного webhook ничего не тестируется.

**WHAT:** docker-compose поднимает 5 сервисов; GitHub App настроен;
webhook публично доступен; issues.opened стартует workflow.

**ACCEPTANCE:**
- `docker-compose up --build` стартует postgres/temporal/temporal-ui/
  webhook/worker без ошибок; healthcheck postgres зелёный.
- GitHub App зарегистрирован с permissions Issues(rw)/Contents(rw),
  events Issues + Issue comments.
- Приватный ключ App смонтирован в worker/webhook как secret volume.
- Webhook публично доступен (tunnel для dev / reverse proxy для prod),
  HMAC-подпись проверяется, невалидная подпись → 401.
- Создание тестового Issue → workflow-инстанс виден в Temporal UI
  (localhost:8080) с ID issue-<repo>-<n>.

**TASKS:**
- [ ] T1.1. Добавить в docker-compose.yml volume/secret с приватным ключом
      GitHub App (сейчас не смонтирован).
- [ ] T1.2. Настроить публичный доступ к webhook-сервису (cloudflared/ngrok
      dev; ingress prod).
- [ ] T1.3. Зарегистрировать GitHub App, установить на тестовый репозиторий,
      заполнить .env (App ID, Installation ID, webhook secret, repo).
- [ ] T1.4. Проверить HMAC-верификацию (валидная/невалидная подпись).
- [ ] T1.5. E2E-проверка: Issue opened → workflow в Temporal UI.

---

## Capability 2: Дешёвый сквозной путь (intake → priority)

**WHY:** любой Issue должен автономно доходить до приоритета — это уже
самостоятельно полезный продукт, до всякой разработки кода.

**WHAT:** предфильтры → intake gate (+ цикл уточнения) → классификация →
duplicate check → priority scoring, с лейблами и комментариями.

**ACCEPTANCE:**
- Issue от type=Bot / из денайлиста → лейбл bot-authored, стоп, БЕЗ вызова
  LLM (проверить по отсутствию запроса к z.ai).
- Issue с security-keyword/CVE → лейбл security-sensitive + комментарий,
  стоп.
- intake_gate возвращает валидный GateExtraction (Instructor) на реальном
  GLM-вызове; SPAM/VAGUE/SUFFICIENT ветвятся корректно.
- VAGUE: комментарий с вопросами → лейбл needs-clarification → ответ
  пользователя (signal user_comment) → повторный gate; после 2 раундов →
  needs-human-triage.
- classify_issue: все 4 категории дают корректный лейбл + комментарий.
- duplicate_check: заведомый дубликат ловится с prob>=0.85 → автозакрытие
  + ссылка; 0.5-0.85 → possible-duplicate; <0.5 → кэш кандидатов.
- score_priority: ДЕТЕРМИНИЗМ — один и тот же Issue дважды даёт одинаковый
  priority:PN (INV-1). Критичный баг → P0 override.
- capabilities.md заполнен реальным функционалом.

**TASKS:**
- [ ] T2.1. Проверить z.ai/GLM + Instructor: валидные Pydantic-объекты на
      intake_gate и classify (первый тест schema-совместимости).
- [ ] T2.2. Прогнать предфильтры на тест-кейсах (бот, security).
- [ ] T2.3. Прогнать gate: спам / vague / sufficient + цикл уточнения до
      потолка раундов.
- [ ] T2.4. Прогнать классификацию на 4 типах Issue.
- [ ] T2.5. Прогнать duplicate_check на заведомом дубликате, проверить оба
      порога.
- [ ] T2.6. Прогнать score_priority дважды на одном Issue → проверить
      детерминизм; проверить override критичного бага.
- [ ] T2.7. Заполнить docs/capabilities.md реальным функционалом.
- [ ] T2.8. Упростить промпты: убрать инструкции маркеров [[...]] (Instructor
      задаёт схему сам) — опционально, не блокирует.
- [ ] T2.9. Калибровка: прогнать 10-15 реальных прошлых Issue, сверить
      приоритеты, подправить config/priority-weights.toml.

---

## Capability 3: Отказоустойчивость

**WHY:** INV-5 — Issue не должен пропадать в тишине при сбое.

**WHAT:** обработка сбоев LLM/API с понятным комментарием; guard
possible-duplicate; обработка edited; override классификации.

**ACCEPTANCE:**
- Сбой z.ai (таймаут/500) → RetryPolicy отрабатывает; после исчерпания →
  лейбл advisor:error + комментарий "автообработка не удалась", НЕ тихое
  падение.
- possible-duplicate блокирует research/bug старт, пока нет
  confirmed-not-duplicate.
- issues.edited: принято решение (переклассифицировать / игнорировать) и
  реализовано.
- Ручная смена классификационного лейбла человеком пересчитывает зависимые
  стадии.

**TASKS:**
- [ ] T3.1. Обернуть LLM-вызовы в activities в обработку исключений →
      advisor:error + комментарий.
- [ ] T3.2. Проверить поведение при недоступности z.ai.
- [ ] T3.3. Добавить guard possible-duplicate в research/bug workflow-ветки.
- [ ] T3.4. Обработать issues.edited в webhook (signal или переклассификация).
- [ ] T3.5. Реализовать override классификации по ручному лейблу.

---

## Capability 4: Bug Pipeline

**WHY:** BUG доходит до диагноза; начинаем с багов (проще — нет po-helper,
нет дебатов, ADR-6).

**WHAT:** run_bug_pipeline: поиск дублей/регрессии + SA-helper диагноз →
артефакт в ветку bug/issue-<n>.

**ACCEPTANCE:**
- Скилл SA-helper загружается в worker-контейнер (механизм решён).
- claude -p через Anthropic-совм. эндпоинт z.ai: GLM корректно вызывает
  Read/Write инструменты.
- run_bug_pipeline создаёт docs/bugs/issue-<n>-diagnosis.md (гипотеза
  первопричины, шаги воспроизведения, DoD фикса, оценка риска).
- Артефакт коммитится в ветку bug/issue-<n>, лейбл bug:diagnosed,
  комментарий со ссылкой.
- Guard: не стартует без advisor:bug.

**TASKS:**
- [ ] T4.1. Решить и реализовать загрузку скиллов Claude Code в контейнер
      (.claude/skills/ в образе или plugin install). БЛОКЕР Cap 4 и 5.
- [ ] T4.2. Проверить claude -p + z.ai Anthropic-эндпоинт + tool-calling.
- [ ] T4.3. Реализовать run_bug_pipeline (заменить NotImplementedError).
- [ ] T4.4. Реализовать коммит артефакта в ветку + лейбл + комментарий.
- [ ] T4.5. Guard advisor:bug.

---

## Capability 5: Research Pipeline

**WHY:** FEATURE доходит до техспеки с полной аналитикой — центральная
ценность платформы.

**WHAT:** run_research_pipeline: po-helper (критерии приёмки) → gh-поиск →
Repowise (контекст) → Blueprint → deb8flow → SA-helper → ветка
research/issue-<n>.

**ACCEPTANCE:**
- po-helper: БФТ .docx с плейсхолдерами, роль ТОЛЬКО критерии приёмки
  (ADR-7): DoD, входит/не входит, UJM, интерфейсы, НФТ; без реализации.
- Repowise дозаполняет секции стратегия/связанные/история/рынок.
- Blueprint: Service Blueprint + IDEF0 + обязательный раздел
  "Несогласованности и открытые вопросы" (ADR-8).
- deb8flow: дебаты по обогащённому .docx → debate.md + recommendations.md.
- SA-helper: техспека, каждый пункт "Несогласованностей" явно закрыт или
  перенесён как риск.
- Все артефакты в ветку research/issue-<n>, лейбл research:done, комментарий.
- Durable: убийство worker в середине → продолжение после рестарта (INV-4).
- Guard: не стартует без advisor:feature-request.

**TASKS:**
- [ ] T5.1. Установить deb8flow в worker/Dockerfile (способ + флаги CLI).
- [ ] T5.2. Решить MCP Confluence/Jira для Repowise в headless-среде.
- [ ] T5.3. Подтвердить/задать плейсхолдеры в шаблоне po-helper.
- [ ] T5.4. Реализовать шаг po-helper (проверить запись .docx через claude -p).
- [ ] T5.5. Реализовать шаг gh-поиска связанных Issue.
- [ ] T5.6. Реализовать шаг Repowise (контекст-дозаполнение).
- [ ] T5.7. Реализовать шаг Blueprint.
- [ ] T5.8. Реализовать шаг deb8flow.
- [ ] T5.9. Реализовать шаг SA-helper.
- [ ] T5.10. Коммит всех артефактов в ветку + лейбл + комментарий.
- [ ] T5.11. Тест durable execution (kill worker mid-run).
- [ ] T5.12. Guard advisor:feature-request.
- [ ] T5.13. Решить источник OKR (заглушка docs/okr/current-quarter.md или
      реальное подключение).

---

## Capability 6: Передача в разработку (вне ядра)

**WHY:** замкнуть цикл на автономное написание кода (ADR-12).

**WHAT:** trigger_openhands_resolver передаёт пакет артефактов в OpenHands
(отдельный сервис); pr-agent ревьюит PR; после merge — capabilities.md.

**ACCEPTANCE:**
- OpenHands развёрнут ОТДЕЛЬНО (свой sandboxing, docker.sock, изолир. хост
  — НЕ в этом docker-compose).
- trigger_openhands_resolver передаёт БФТ+blueprint+техспеку как контекст.
- pr-agent даёт независимый review на PR от OpenHands.
- После merge — capabilities.md обновляется (замыкание: advisor узнаёт про
  фичу).

**TASKS:**
- [ ] T6.1. Развернуть OpenHands как отдельный сервис.
- [ ] T6.2. Реализовать trigger_openhands_resolver.
- [ ] T6.3. Подключить pr-agent на PR.
- [ ] T6.4. Реализовать обновление capabilities.md после merge.

---

## Out of scope (текущая итерация)
- Метрики калибровки / сбор рассогласований (после пилота).
- @advisor живой Q&A в тредике.
- Авто-синхронизация capabilities.md с кодовой базой.
- Реальное подключение OKR (на старте — заглушка).

## Definition of Done для проекта
Все Capability 1-5 приняты; FEATURE-Issue проходит путь от открытия до
пакета аналитики в git-ветке полностью на self-hosted стеке; ни один сбой
не оставляет Issue без обратной связи; приоритизация детерминирована.
Capability 6 — отдельная веха, зависит от готовности OpenHands.
