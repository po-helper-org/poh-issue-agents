# Roadmap: слои после Layer A

Каркас последующих слоёв. Детали заполняются позже — сейчас фиксируем объём и
блокеры, чтобы не переоткрывать. Layer A (автономный триаж) описан отдельно в
[специи](superpowers/specs/2026-07-12-issue-agent-layer-a-triage-design.md).

Связь с исходным фазовым планом — [ROADMAP.md](ROADMAP.md) (Ф0–Ф6).

---

## Слой B — новые Issue обрабатываются автоматически

Даёт пункт 2 мерила успеха: открыл новый Issue → система обработала сама.

Объём:
- Публичный webhook: `cloudflared tunnel` / `ngrok` для разработки, reverse
  proxy на домене для прода.
- Вебхук репозитория `po-helper` (events: Issues, Issue comments) на URL
  сервиса `webhook`.
- Поднять сервис `webhook` в `docker-compose` (в Layer A не запускался).
- Проверка подписи HMAC (`GITHUB_WEBHOOK_SECRET`).

Открытые вопросы:
- Repo-webhook + PAT против полноценного GitHub App с App-идентичностью
  комментариев — решить по модели секретов.

_TODO: заполнить детали._

---

## Слой C — аналитика по запросу (стратегическая цель)

Делегирование первичного сбора + аналитики доработок po-helper. Тяжёлый слой,
все блокеры известны заранее.

Объём:
- `run_bug_pipeline` (сейчас `NotImplementedError`): поиск дублей/регрессии +
  SA-helper диагноз → `docs/bugs/issue-<n>-diagnosis.md` в ветку `bug/issue-<n>`.
- `run_research_pipeline` (сейчас `NotImplementedError`): po-helper (БФТ) →
  gh-поиск связанных → Repowise (контекст) → Blueprint → deb8flow (дебаты) →
  SA-helper (техспека) → артефакты в ветку `research/issue-<n>`.
- `trigger_openhands_resolver` — передача пакета артефактов в OpenAI resolver
  (отдельный сервис со своим sandboxing).

Блокеры (из ROADMAP.md, сводка):
- Загрузка скиллов po-helper/SA-helper в worker-контейнер.
- `claude -p` через Anthropic-совместимый эндпоинт z.ai + корректный
  tool-calling (Write/Read).
- Установка deb8flow в `worker/Dockerfile` + точный синтаксис CLI.
- MCP Confluence/Jira для Repowise в headless-среде worker'а.
- Генерация `.docx` через `claude -p` (шаблон БФТ с плейсхолдерами).
- Источник OKR для `okr_alignment`.

_TODO: заполнить детали по каждой стадии._

---

## Layer A-hardening / калибровка (Ф2, Ф6)

- Обработка сбоев: лейбл `advisor:error` + комментарий вместо тихого падения
  workflow при исчерпании ретраев.
- Guard `possible-duplicate`: тяжёлые стадии не стартуют без
  `confirmed-not-duplicate`.
- Обработка `issues.edited` (переклассификация или игнор).
- Override классификации/приоритета человеком → пересчёт зависимых стадий.
- Калибровка порогов `priority-weights.toml` на 10–15 реальных Issue.
- Упрощение промптов (убрать инструкции маркеров `[[...]]` — с Instructor
  избыточны).

_TODO: заполнить детали._
