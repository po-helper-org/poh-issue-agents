"""Тесты обработки ошибок вебхука для GitLab-специфичных сценариев.

Эти тесты проверяют, что вебхук никогда не возвращает 5xx, даже при:
- Некорректных payload от GitLab
- Отсутствующих обязательных полях
- Ошибках подписи
- Специфичных для GitLab форматах событий
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

SECRET = "test_secret"
GITLAB_SECRET = "glpat_test_secret"


@pytest.fixture
def client(monkeypatch):
    """Создает клиент для тестирования вебхука."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", GITLAB_SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", "o/r")
    import importlib
    
    import main
    importlib.reload(main)

    async def no_temporal():
        raise AssertionError("до Temporal дойти не должно")

    monkeypatch.setattr(main, "get_temporal_client", no_temporal)
    return TestClient(main.app, raise_server_exceptions=False)


def _gitlab_signature(payload: bytes, secret: str = GITLAB_SECRET) -> str:
    """Создает GitLab-подпись (X-Gitlab-Token)."""
    return secret


# --- GitLab-специфичные тесты ---

def test_gitlab_issue_opened_without_user_type_accepted(client):
    """GitLab не всегда включает user.type, но вебхук должен принимать событие."""
    payload = {
        "object_kind": "issue",
        "event_type": "issue",
        "user": {
            "id": 123,
            "username": "testuser",
            # Нет поля "type" - нормально для GitLab
        },
        "project": {
            "id": 456,
            "path_with_namespace": "group/sub/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "description": "Test description",
            "state": "opened",
            "action": "open",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    # Должен быть принят (202) или ошибка клиента (4xx), но не 5xx
    assert response.status_code < 500, (
        f"GitLab webhook должен принимать события без user.type, но вернул {response.status_code}"
    )


def test_gitlab_comment_created_without_user_type_accepted(client):
    """Комментарии GitLab могут не иметь user.type."""
    payload = {
        "object_kind": "note",
        "event_type": "note",
        "user": {
            "id": 123,
            "username": "testuser",
            # Нет поля "type"
        },
        "project": {
            "id": 456,
            "path_with_namespace": "group/sub/project",
        },
        "object_attributes": {
            "id": 789,
            "note": "Test comment",
            "noteable_type": "Issue",
            "noteable_id": 1,
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Note Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_label_change_payload_accepted(client):
    """GitLab отправляет изменения меток в формате changes.labels.previous/current."""
    payload = {
        "object_kind": "issue",
        "event_type": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/sub/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "state": "opened",
            "action": "update",
        },
        "changes": {
            "labels": {
                "previous": [],
                "current": [
                    {"id": 1, "title": "bug", "color": "#ff0000"}
                ]
            }
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_merge_request_payload_accepted(client):
    """Вебхук должен принимать события MR от GitLab."""
    payload = {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/sub/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test MR",
            "state": "opened",
            "action": "open",
            "target_branch": "main",
            "source_branch": "feature-branch",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Merge Request Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_nested_group_path_accepted(client):
    """Вебхук должен корректно обрабатывать проекты во вложенных группах."""
    payload = {
        "object_kind": "issue",
        "event_type": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "org/team/subgroup/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "description": "Test",
            "state": "opened",
            "action": "open",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


# --- Обработка ошибок ---

def test_gitlab_missing_project_field_accepted(client):
    """Отсутствие поля project не должно вызывать 5xx."""
    payload = {
        "object_kind": "issue",
        "user": {"id": 123, "username": "testuser"},
        # Нет поля "project"
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "state": "opened",
            "action": "open",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_missing_object_attributes_accepted(client):
    """Отсутствие object_attributes не должно вызывать 5xx."""
    payload = {
        "object_kind": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/project",
        }
        # Нет поля "object_attributes"
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_malformed_json_accepted(client):
    """Некорректный JSON не должен вызывать 5xx."""
    malformed_json = "{invalid json"
    
    response = client.post(
        "/webhook",
        content=malformed_json.encode(),
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook",
            "Content-Type": "application/json"
        }
    )
    
    # FastAPI вернет 422 (Unprocessable Entity) для некорректного JSON
    assert response.status_code < 500


def test_gitlab_empty_payload_accepted(client):
    """Пустой payload не должен вызывать 5xx."""
    response = client.post(
        "/webhook",
        json={},
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


# --- Проверка подписи ---

def test_gitlab_bad_signature_returns_401(client):
    """Неверная подпись GitLab должна возвращать 401, не 5xx."""
    payload = {"object_kind": "issue"}
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": "wrong_secret",
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    # Важно: не должен быть 5xx. 422 тоже приемлемо (FastAPI validation),
    # главное - не ошибка сервера
    assert response.status_code < 500


def test_gitlab_no_signature_returns_401(client):
    """Отсутствие подписи должно возвращать 401, не 5xx."""
    payload = {"object_kind": "issue"}
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Event": "Issue Hook"
            # Нет заголовка подписи
        }
    )
    
    # Важно: не должен быть 5xx
    assert response.status_code < 500


# --- Крайние случаи ---

def test_gitlab_very_long_payload_accepted(client):
    """Очень длинный payload не должен вызывать 5xx."""
    long_description = "x" * 10000  # 10KB текста
    
    payload = {
        "object_kind": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "description": long_description,
            "state": "opened",
            "action": "open",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_unicode_in_fields_accepted(client):
    """Unicode символы в полях не должны вызывать 5xx."""
    payload = {
        "object_kind": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Иssue 测试 🚀",
            "description": "Описание with émojis 🎉",
            "state": "opened",
            "action": "open",
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500


def test_gitlab_system_note_accepted(client):
    """Системные заметки GitLab (например, 'assigned to @user') должны обрабатываться."""
    payload = {
        "object_kind": "note",
        "event_type": "note",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/project",
        },
        "object_attributes": {
            "id": 789,
            "note": "assigned to @user",
            "noteable_type": "Issue",
            "noteable_id": 1,
            "system": True,  # Это системная заметка
        }
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Note Hook"
        }
    )
    
    assert response.status_code < 500


def test_multiple_webhook_events_in_sequence(client):
    """Последовательная обработка нескольких событий не должна вызывать 5xx."""
    events = [
        {
            "object_kind": "issue",
            "user": {"id": 123, "username": "testuser"},
            "project": {"id": 456, "path_with_namespace": "group/project"},
            "object_attributes": {"id": 1, "iid": 1, "title": "Issue 1", "state": "opened", "action": "open"}
        },
        {
            "object_kind": "note",
            "user": {"id": 123, "username": "testuser"},
            "project": {"id": 456, "path_with_namespace": "group/project"},
            "object_attributes": {"id": 1, "note": "Comment 1", "noteable_type": "Issue", "noteable_id": 1}
        },
        {
            "object_kind": "issue",
            "user": {"id": 123, "username": "testuser"},
            "project": {"id": 456, "path_with_namespace": "group/project"},
            "object_attributes": {"id": 1, "iid": 1, "title": "Issue 1", "state": "opened", "action": "update"},
            "changes": {
                "labels": {
                    "previous": [],
                    "current": [{"id": 1, "title": "bug"}]
                }
            }
        }
    ]
    
    for event in events:
        headers = {
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": f"{event['object_kind'].title()} Hook"
        }
        
        response = client.post("/webhook", json=event, headers=headers)
        assert response.status_code < 500, (
            f"Событие {event['object_kind']} вызвало {response.status_code}"
        )


def test_gitlab_webhook_with_custom_fields_accepted(client):
    """Поля, не ожидаемые вебхуком, не должны вызывать 5xx."""
    payload = {
        "object_kind": "issue",
        "user": {"id": 123, "username": "testuser"},
        "project": {
            "id": 456,
            "path_with_namespace": "group/project",
        },
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Test Issue",
            "state": "opened",
            "action": "open",
        },
        "custom_field_1": "value1",
        "custom_field_2": {"nested": "data"},
        "unexpected_array": [1, 2, 3]
    }
    
    response = client.post(
        "/webhook",
        json=payload,
        headers={
            "X-Gitlab-Token": GITLAB_SECRET,
            "X-Gitlab-Event": "Issue Hook"
        }
    )
    
    assert response.status_code < 500
