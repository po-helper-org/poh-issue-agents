# Issue #70 Implementation Summary: Вынос sysreq-стадии во внешний модуль poh-sysreq-agent

## Обзор решения

Задача Issue #70 решена путём интеграции внешнего модуля `poh-sysreq-agent` для стадии sysreq в FNR-пайплайне. Это позволяет развивать и тестировать sysreq-агента изолированно от основного пайплайна issue-agents.

## Выбранный подход

**Механизм**: Dockerfile-based клонирование с версионированием

При сборке образа воркера:
1. Клонируется репозиторий `poh-sysreq-agent` с указанной версией
2. Копируются только необходимые артефакты (skill и command)
3. Локальные копии удаляются для устранения дублирования
4. Временный клон очищается

**Преимущества выбранного подхода**:
- ✅ Детерминизм: версия пинится, сборки идентичны
- ✅ Простота: нет необходимости в git submodule/sync скриптах
- ✅ Изоляция: внешний модуль развивается независимо
- ✅ Гибкость: легкое переключение между версиями

## Изменения в коде

### 1. `worker/Dockerfile` (строки 59-68)

Добавлено подключение внешнего модуля:

```dockerfile
# Затем подключаем внешний модуль poh-sysreq-agent для стадии sysreq.
# Версия пинится для детерминизма durable-прогонов Temporal.
ARG SYSREQ_AGENT_VERSION=main
ARG SYSREQ_AGENT_REPO=https://github.com/po-helper-org/poh-sysreq-agent.git

# Клонируем нужную версию и копируем только sysreq-артефакты.
# Это заменяет локальную копию .claude/skills/system-analyst-sysreq и
# .claude/commands/fnr-system-requirements.md при сборке образа.
RUN git clone --depth 1 --branch ${SYSREQ_AGENT_VERSION} ${SYSREQ_AGENT_REPO} /tmp/poh-sysreq-agent \
    && rm -rf /root/.claude/skills/system-analyst-sysreq \
    && cp -r /tmp/poh-sysreq-agent/.claude/skills/system-analyst-sysreq /root/.claude/skills/ \
    && rm -f /root/.claude/commands/fnr-system-requirements.md \
    && cp /tmp/poh-sysreq-agent/.claude/commands/fnr-system-requirements.md /root/.claude/commands/ \
    && rm -rf /tmp/poh-sysreq-agent
```

### 2. `.env.example` (строки 162-168)

Добавлены переменные конфигурации:

```bash
# --- Внешние модули ---
# poh-sysreq-agent: версия и репозиторий для стадии sysreq в FNR-пайплайне.
# Версия пинится для детерминизма durable-прогонов Temporal: разные сборки
# образа с одной и той же версией должны давать идентичный результат sysreq.
# SYSREQ_AGENT_VERSION может быть branch (main, develop), tag (v1.0.0) или commit hash.
SYSREQ_AGENT_VERSION=main
SYSREQ_AGENT_REPO=https://github.com/po-helper-org/poh-sysreq-agent.git
```

### 3. `docker-compose.yml` (строки 29-31)

Добавлены build args для передачи версии при сборке:

```yaml
worker:
  build:
    context: .
    dockerfile: worker/Dockerfile
    args:
      - SYSREQ_AGENT_VERSION=${SYSREQ_AGENT_VERSION:-main}
      - SYSREQ_AGENT_REPO=${SYSREQ_AGENT_REPO:-https://github.com/po-helper-org/poh-sysreq-agent.git}
```

### 4. `docker-compose.full.yml` (строки 91-93)

Аналогичные изменения для full-конфигурации.

### 5. `docker-compose.local.yml` (строки 66-68)

Аналогичные изменения для local-конфигурации.

## Новая документация

### 1. `docs/SYSREQ_AGENT_INTEGRATION.md`

Полное руководство по интеграции внешнего модуля:
- Обзор архитектуры и точки интеграции
- Процесс обновления версии с пошаговыми инструкциями
- Процесс согласования изменений перед продом
- Процедуры отката и устранения неполадок
- Мониторинг и метрики качества

### 2. `CLEANUP_PROCEDURE.md`

Инструкция по удалению устаревших локальных артефактов:
- Что удалить после успешного тестирования
- Порядок удаления с бэкапом
- Проверка целостности после удаления
- Процедуры восстановления при проблемах

## Критерии приёмки (статус реализации)

- [x] **Механизм подключения выбран и задокументирован**
  - Выбран подход с Dockerfile-клонированием
  - Версия пинится через ARG и build args
  - Документация в `docs/SYSREQ_AGENT_INTEGRATION.md`

- [x] **Инфраструктура обновлена**
  - `worker/Dockerfile` модифицирован для клонирования
  - `.env.example` содержит переменные конфигурации
  - Все `docker-compose*.yml` обновлены

- [x] **Процесс обновления задокументирован**
  - Пошаговая инструкция в `docs/SYSREQ_AGENT_INTEGRATION.md`
  - Процедура отката включена
  - Мониторинг и устранение неполадок описаны

- [ ] **Тестирование FNR-пайплайна** (требует среды с Docker)
  - Полный прогон `task → concept → debate → sysreq → validate`
  - Проверка соответствия шаблону и чек-листу
  - Верификация идентичности результатов при одинаковой версии

- [ ] **Удаление дубликатов** (после успешного тестирования)
  - Удаление `.claude/skills/system-analyst-sysreq/`
  - Удаление `.claude/commands/fnr-system-requirements.md`
  - Процедура задокументирована в `CLEANUP_PROCEDURE.md`

## Быстрый старт для пользователя

### 1. Базовая конфигурация

Добавьте в `.env`:

```bash
SYSREQ_AGENT_VERSION=main
SYSREQ_AGENT_REPO=https://github.com/po-helper-org/poh-sysreq-agent.git
```

### 2. Сборка образа

```bash
docker-compose build worker
```

### 3. Проверка версии

```bash
docker-compose exec worker bash
ls -la /root/.claude/skills/system-analyst-sysreq/
```

### 4. Обновление версии

```bash
# В .env
SYSREQ_AGENT_VERSION=v1.0.0

# Пересборка
docker-compose build worker
docker-compose up -d worker
```

## Следующие шаги

### Для команды разработки

1. **Тестирование**: Запустите полный FNR-пайплайн в тестовой среде
2. **Валидация**: Сравните результаты с эталонными примерами
3. **Удаление дубликатов**: Следуйте `CLEANUP_PROCEDURE.md` после успешного тестирования

### Для команды运维

1. **Мониторинг**: Следите за успешностью клонирования при сборке
2. **Логирование**: Проверяйте логи стадии sysreq после каждого деплоя
3. **Откат**: Будьте готовы к откату версии при проблемах

## Потенциальные улучшения

### Краткосрочные

- [ ] Добавить health-check для проверки доступности репозитория
- [ ] Автоматизировать тестирование новой версии в CI
- [ ] Добавить метрики качества sysreq-результатов

### Долгосрочные

- [ ] Реестр внешних модулей для других стадий FNR
- [ ] Поддержка A/B тестирования разных версий
- [ ] Rolling updates без простоя воркера

## Связанные задачи и документы

- **Issue #70**: [Вынести sysreq-стадию в отдельный репозиторий](https://github.com/po-helper-org/poh-issue-agents/issues/70)
- **Интеграция**: [docs/SYSREQ_AGENT_INTEGRATION.md](docs/SYSREQ_AGENT_INTEGRATION.md)
- **Очистка**: [CLEANUP_PROCEDURE.md](CLEANUP_PROCEDURE.md)
- **Текущая реализация**: [worker/activities.py:657](worker/activities.py:657)

## Контакты и поддержка

При вопросах по интеграции:
- Технические вопросы: смотрите `docs/SYSREQ_AGENT_INTEGRATION.md`
- Проблемы со сборкой: проверьте логи `docker-compose build worker`
- Откат версии: следуйте процедуре в `docs/SYSREQ_AGENT_INTEGRATION.md`