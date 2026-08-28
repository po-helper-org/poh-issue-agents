# Устаревшие артефакты для удаления

## Системные требования (аналитика Issue-Agent)

## Что удалить после успешного тестирования внешнего модуля

После того как интеграция `poh-sysreq-agent` будет проверена и подтверждена рабочей, следующие локальные файлы должны быть удалены, чтобы избежать дублирования и путаницы:

### Директория скиллов

```bash
rm -rf .claude/skills/system-analyst-sysreq/
```

### Файл команды

```bash
rm -f .claude/commands/fnr-system-requirements.md
```

## Порядок удаления

1. **Подтверждение работы внешнего модуля**
   - Убедитесь, что `docker-compose build worker` успешно собирает образ
   - Проверьте, что sysreq-стадия работает корректно в тестовом прогоне FNR
   - Убедитесь, что в логах нет ошибок при загрузке скиллов/команд

2. **Создание бэкапа** (опционально, но рекомендуется)

```bash
# Создайте ветку для бэкапа
git checkout -b backup/sysreq-artifacts

# Зафиксируйте текущее состояние
git add .claude/skills/system-analyst-sysreq/ .claude/commands/fnr-system-requirements.md
git commit -m "Backup: local sysreq artifacts before removal"
git push origin backup/sysreq-artifacts
```

3. **Удаление артефактов**

```bash
# Вернитесь в основную ветку
git checkout main

# Удалите локальные копии
rm -rf .claude/skills/system-analyst-sysreq/
rm -f .claude/commands/fnr-system-requirements.md
```

4. **Проверка целостности**

```bash
# Убедитесь, что структура репозитория корректна
git status

# Проверьте, что не осталось других ссылок на удалённые файлы
grep -r "system-analyst-sysreq" --include="*.md" --include="*.py" --include="*.yml" . | grep -v "docs/SYSREQ_AGENT_INTEGRATION.md" | grep -v "CLEANUP_PROCEDURE.md"
```

5. **Коммит изменений**

```bash
git add -A
git commit -m "chore: remove duplicate sysreq artifacts after external module integration

Local copies of sysreq skill and command are no longer needed since
they are now fetched from poh-sysreq-agent external module during
Docker image build.

This removes duplication and ensures single source of truth for
sysreq stage implementation.

See docs/SYSREQ_AGENT_INTEGRATION.md for details."
```

## Что НЕ удалять

- **Документация**: `docs/SYSREQ_AGENT_INTEGRATION.md` — это руководство по интеграции
- **Конфигурация**: `.env.example` — переменные `SYSREQ_AGENT_*` нужны для работы
- **Dockerfile**: `worker/Dockerfile` — код интеграции в образ
- **Compose-файлы**: `docker-compose*.yml` — параметры сборки с внешним модулем

## Проверка после удаления

После удаления убедитесь, что:

1. **Сборка образа работает**

```bash
docker-compose build worker
# Не должно быть ошибок об отсутствующих файлах
```

2. **Версия определяется из внешнего репозитория**

```bash
# В логах сборки должно быть видно:
# Cloning into '/tmp/poh-sysreq-agent'...
# cp -r /tmp/poh-sysreq-agent/.claude/skills/system-analyst-sysreq /root/.claude/skills/
```

3. **Функциональность сохраняется**

Запустите тестовый прогон FNR-пайплайна и убедитесь, что стадия sysreq работает корректно.

## Восстановление при проблемах

Если после удаления возникнут проблемы:

```bash
# Откатитесь к бэкапу
git checkout backup/sysreq-artifacts
git checkout main -- .claude/skills/system-analyst-sysreq/ .claude/commands/fnr-system-requirements.md

# Или восстановите из git history
git checkout HEAD~1 -- .claude/skills/system-analyst-sysreq/ .claude/commands/fnr-system-requirements.md
```

## Связанные задачи

- Issue #70 — исходная задача по выносу sysreq-стадии
- docs/SYSREQ_AGENT_INTEGRATION.md — полное руководство по интеграции
- worker/Dockerfile — точка подключения внешнего модуля