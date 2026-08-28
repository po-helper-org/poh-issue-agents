# Интеграция poh-sysreq-agent

## Обзор

Стадия `sysreq` (генерация системных требований) в FNR-пайплайне использует внешний модуль `poh-sysreq-agent`. Это позволяет:

- Развивать и тестировать качество sysreq-агента изолированно
- Обновлять sysreq-логику без пересборки всего issue-agents пайплайна
- Версионировать изменения промптов/шаблонов отдельно от основного сервиса

## Архитектура

### Точка интеграции

- **Dockerfile**: `worker/Dockerfile` (строки 59-68)
- **Конфигурация**: `.env.example` (строки 162-168) и `docker-compose.yml` (строки 29-31)
- **Исполнение**: `worker/activities.py:_fnr_stages()` (строка 854)

### Механизм подключения

При сборке образа воркера:

1. Клонируется репозиторий `poh-sysreq-agent` с указанной версией
2. Копируются только нужные артефакты:
   - `.claude/skills/system-analyst-sysreq/` → `/root/.claude/skills/`
   - `.claude/commands/fnr-system-requirements.md` → `/root/.claude/commands/`
3. Локальные копии удаляются (если есть)
4. Временный клон очищается

Это обеспечивает детерминизм: одна и та же версия `poh-sysreq-agent` всегда даёт одинаковый результат при сборке.

## Обновление версии

### Шаг 1: Выберите новую версию

Определите нужную версию `poh-sysreq-agent`:

```bash
# Для стабильных релизов — используйте теги
SYSREQ_AGENT_VERSION=v1.2.3

# Для тестирования новых фич — используйте ветки
SYSREQ_AGENT_VERSION=develop

# Для максимальной стабильности — используйте commit hash
SYSREQ_AGENT_VERSION=abc123def456...
```

### Шаг 2: Обновите `.env`

Добавьте или измените переменные в `.env`:

```bash
SYSREQ_AGENT_VERSION=v1.2.3
SYSREQ_AGENT_REPO=https://github.com/po-helper-org/poh-sysreq-agent.git
```

### Шаг 3: Пересоберите образ

```bash
docker-compose build worker
```

При сборке будет выведен URL клонирования и версия:

```
#15 [10/15] RUN git clone --depth 1 --branch v1.2.3 https://github.com/po-helper-org/poh-sysreq-agent.git /tmp/poh-sysreq-agent
#15 DONE 2.3s
```

### Шаг 4: Перезапустите воркер

```bash
docker-compose up -d worker
```

### Шаг 5: Проверьте версию

В контейнере воркера:

```bash
docker-compose exec worker bash
ls -la /root/.claude/skills/system-analyst-sysreq/
cat /root/.claude/commands/fnr-system-requirements.md | head -5
```

## Процесс согласования

Перед обновлением версии в проде:

1. **Тестирование**: Протестируйте новую версию на staging-окружении с реальными Issue
2. **Ревью промптов**: Проверьте изменения в `SKILL.md`, шаблонах и чек-листах
3. **Регрессионное тестирование**: Убедитесь, что sysreq-стадия даёт ожидаемый результат
4. **Документирование**: Обновите CHANGELOG.md с описанием изменений
5. **Планируемое обновление**: Выберите окно обслуживания с минимальной нагрузкой

## Откат

Если новая версия вызывает проблемы:

### Быстрый откат (с сохранением текущего образа)

```bash
# 1. Откатите версию в .env
SYSREQ_AGENT_VERSION=v1.2.2  # предыдущая стабильная версия

# 2. Пересоберите и перезапустите
docker-compose build worker
docker-compose up -d worker
```

### Полный откат (если пересборка невозможна)

```bash
# 1. Остановите воркер
docker-compose stop worker

# 2. Удалите текущий образ
docker rmi poh-issue-agents-worker

# 3. Восстановите предыдущую версию из git
git checkout HEAD~1 worker/Dockerfile

# 4. Пересоберите с предыдущей конфигурацией
docker-compose build worker --no-cache
docker-compose up -d worker
```

## Мониторинг

### Логи сборки

Следите за ошибками клонирования при сборке:

```bash
docker-compose build worker 2>&1 | grep -E "git clone|ERROR|fatal"
```

### Логи выполнения

Проверяйте успешность стадии sysreq в логах воркера:

```bash
docker-compose logs worker | grep -A 10 "sysreq"
```

### Метрики качества

После обновления:

1. Сравните результаты `system_requirements.md` с эталонными примерами
2. Проверьте соответствие шаблону `ideal_system_requirements.md`
3. Пройдитесь по чек-листу `sysreq_validation_checklist.md`

## Устранение неполадок

### Проблема: Клонирование не работает

```
ERROR: Repository 'https://github.com/po-helper-org/poh-sysreq-agent.git' not found
```

**Решение**: Проверьте URL репозитория и доступность сети. Попробуйте указать другую организацию или fork.

### Проблема: Ветка не существует

```
ERROR: Remote branch v1.2.3 not found
```

**Решение**: Проверьте доступные ветки и теги:

```bash
git ls-remote --tags https://github.com/po-helper-org/poh-sysreq-agent.git
```

### Проблема: Артефакты не копируются

```
cp: cannot stat '/tmp/poh-sysreq-agent/.claude/skills/system-analyst-sysreq': No such file or directory
```

**Решение**: Структура репозитория `poh-sysreq-agent` изменилась. Проверьте актуальную структуру и при необходимости обновите `worker/Dockerfile`.

## Будущая работа

### Планируемые улучшения

1. **Автоматическое тестирование**: CI-пайплайн для проверки новой версии перед деплоем
2. **Semantic Versioning**: Чёткое следование SemVer для прогнозируемости изменений
3. **Health Check**: Эндпоинт для проверки доступности и версии sysreq-агента
4. **Rolling Updates**: Обновление без простоя воркера

### Потенциальные изменения архитектуры

- Вынос других стадий FNR (`task`, `concept`, `debate`, `validate`) в отдельные модули
- Реестр внешних модулей для упрощения подключения
- Поддержка нескольких версий sysreq-агента для A/B тестирования

## Связанные документы

- [Issue #70](https://github.com/po-helper-org/poh-issue-agents/issues/70) — исходная задача
- [worker/Dockerfile](../worker/Dockerfile) — точка интеграции
- [worker/activities.py](../worker/activities.py) — использование sysreq-стадии
- [.env.example](../.env.example) — конфигурация версии
- [docker-compose.yml](../docker-compose.yml) — сборка с параметрами версии
