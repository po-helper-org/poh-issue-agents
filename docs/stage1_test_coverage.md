# Тесты транспортного уровня для GitLab поддержки

Этот файл описывает тестовые покрытия для адаптации системы под GitLab.

## Созданные тесты

### 1. Transport URL Encoding Tests (`tests/test_transport_url_encoding.py`)

**Цель:** Проверить, что все URL правильно кодируются для GitLab с вложенными подгруппами.

**Ключевые проверки:**
- ✅ `test_repo_ref_encodes_gitlab_nested_paths` - Кодирование вложенных подгрупп (`group/sub/project` → `group%2Fsub%2Fproject`)
- ✅ `test_repo_ref_github_paths_not_encoded` - GitHub пути не кодируются
- ✅ `test_repo_prefers_numeric_id_over_path` - Использование numeric_id когда доступно
- ✅ `test_special_chars_in_path_are_encoded` - Кодирование специальных символов
- ✅ `test_github_client_uses_url_encoded_repo_path` - Клиент использует закодированные пути
- ✅ `test_label_names_are_always_url_encoded` - Метки всегда кодируются (`run:analyze` → `run%3Aanalyze`)
- ✅ `test_workflow_file_names_are_url_encoded` - Имена файлов воркфлоу кодируются
- ✅ `test_deeply_nested_gitlab_paths_work_correctly` - Очень глубокие вложения (до 20 уровней)
- ✅ `test_url_encoding_preserves_case_sensitivity` - Сохранение регистра при кодировании
- ✅ `test_edge_cases_in_url_encoding` - Крайние случаи (пробелы, множественные слеши)
- ✅ `test_allowlist_works_with_encoded_paths` - Allowlist работает с закодированными путями
- ✅ `test_transport_integration_with_multiple_operations` - Интеграция нескольких операций

**Результат:** 12/12 passed ✅

### 2. GitLab Webhook Resilience Tests (`tests/test_gitlab_webhook_resilience.py`)

**Цель:** Проверить, что вебхук никогда не возвращает 5xx, что критично для GitLab (нет ретраев, 4 провала → отключение).

**Ключевые проверки:**
- ✅ `test_gitlab_issue_opened_without_user_type_accepted` - События без `user.type` (GitLab не всегда включает)
- ✅ `test_gitlab_comment_created_without_user_type_accepted` - Комментарии без `user.type`
- ✅ `test_gitlab_label_change_payload_accepted` - Payload в формате `changes.labels.previous/current`
- ✅ `test_gitlab_merge_request_payload_accepted` - События MR от GitLab
- ✅ `test_gitlab_nested_group_path_accepted` - Проекты во вложенных группах
- ✅ `test_gitlab_missing_project_field_accepted` - Отсутствие поля `project`
- ✅ `test_gitlab_missing_object_attributes_accepted` - Отсутствие `object_attributes`
- ✅ `test_gitlab_malformed_json_accepted` - Некорректный JSON
- ✅ `test_gitlab_empty_payload_accepted` - Пустой payload
- ✅ `test_gitlab_bad_signature_returns_401` - Неверная подпись (не 5xx!)
- ✅ `test_gitlab_no_signature_returns_401` - Отсутствие подписи (не 5xx!)
- ✅ `test_gitlab_very_long_payload_accepted` - Очень длинный payload (10KB+)
- ✅ `test_gitlab_unicode_in_fields_accepted` - Unicode символы
- ✅ `test_gitlab_system_note_accepted` - Системные заметки (`system: true`)
- ✅ `test_multiple_webhook_events_in_sequence` - Последовательная обработка событий
- ✅ `test_gitlab_webhook_with_custom_fields_accepted` - Неожиданные поля не ломают обработку

**Результат:** 16/16 passed ✅

### 3. Существующие RepoRef Tests (`tests/test_repo_ref.py`)

**Цель:** Базовая функциональность `RepoRef` для GitHub и GitLab.

**Ключевые проверки:**
- ✅ GitHub двухсегментные пути
- ✅ GitHub API сегменты не кодируются
- ✅ GitLab вложенные подгруппы сохраняются
- ✅ GitLab API сегменты кодируются
- ✅ GitLab numeric_id имеет приоритет
- ✅ Обработка пробелов и слешей
- ✅ Отклонение некорректных путей
- ✅ Хешируемость и сравнение

**Результат:** 9/9 passed ✅

## Текущее покрытие

**Всего тестов:** 37/37 passed ✅

**Покрытие для этапа 1 (Закалка под второго провайдера):**
- ✅ URL-кодирование путей репозиториев
- ✅ Поддержка вложенных групп GitLab  
- ✅ Allowlist для многосегментных путей
- ✅ Вебхук не возвращает 5xx
- ✅ Обработка GitLab-специфичных payload форматов

## Запуск тестов

```bash
# Все новые тесты
pytest tests/test_transport_url_encoding.py tests/test_gitlab_webhook_resilience.py tests/test_repo_ref.py -v

# Только транспортные тесты
pytest tests/test_transport_url_encoding.py -v

# Только тесты устойчивости вебхука
pytest tests/test_gitlab_webhook_resilience.py -v

# С покрытием
pytest tests/test_transport_url_encoding.py tests/test_gitlab_webhook_resilience.py --cov=shared/repo_ref --cov=webhook/main --cov-report=term-missing
```

## Следующие шаги (Stage 2)

После успешного завершения Stage 1, следующие тесты понадобятся для:

1. **GitLab API Client Tests:**
   - Тесты для GitLab-specific API calls
   - Методы работы с Merge Requests вместо Pull Requests
   - Обработка системных заметок вместо Timeline API

2. **Integration Tests:**
   - End-to-end тесты с реальным GitLab instance
   - Проверка полного потока обработки issue
   - Тесты для команд в комментариях

3. **Migration Tests:**
   - Проверка backward compatibility с GitHub
   - Тесты для одновременной работы с GitHub и GitLab
   - Валидация миграции данных

## Примечания по тестированию

- Все тесты используют моки (no real HTTP calls)
- Тесты изолированы и не требуют внешних зависимостей
- Покрытие включает крайние случаи и ошибки
- Тесты следуют паттерну существующих тестов проекта
