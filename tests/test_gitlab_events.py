"""Нормализация вебхуков GitLab.

Формы payload взяты из документации GitLab, а не выдуманы: у Issue Hook
номер задачи лежит в object_attributes.iid, у Note Hook — во вложенном issue,
а поля «какая метка добавлена» нет вовсе.
"""
import pytest

from shared.gitlab_events import (
    UnsupportedEvent, normalize, internal_event,
    labels_added, labels_removed, project_path, project_id,
)

PROJECT = {"id": 85686131, "name": "threads-harness",
           "path_with_namespace": "poh-harness/threads-harness"}
USER = {"id": 4549553, "name": "Aleks", "username": "cvyatoslavka"}


def issue_hook(action="open", labels=None, changes=None):
    return {
        "object_kind": "issue", "event_type": "issue",
        "user": USER, "project": PROJECT,
        "object_attributes": {
            "id": 999, "iid": 7, "title": "Заголовок",
            "description": "Тело задачи", "state": "opened",
            "action": action, "labels": labels or [],
        },
        **({"changes": changes} if changes else {}),
    }


def note_hook(note="текст", action="create", noteable="Issue"):
    return {
        "object_kind": "note", "event_type": "note",
        "user": USER, "project": PROJECT,
        "object_attributes": {
            "id": 3722933426, "note": note, "noteable_type": noteable,
            "action": action, "discussion_id": "abc",
        },
        "issue": {"id": 999, "iid": 7, "title": "Заголовок",
                  "description": "Тело", "state": "opened",
                  "author": {"username": "someone"},
                  "labels": [{"title": "phase:created"}]},
    }


# --- имя события ---

def test_имена_событий():
    assert internal_event("Issue Hook") == "issues"
    assert internal_event("Note Hook") == "issue_comment"
    assert internal_event("Merge Request Hook") == "pull_request"


def test_чужое_событие_не_молчит():
    with pytest.raises(UnsupportedEvent):
        internal_event("Pipeline Hook")


# --- проект ---

def test_путь_проекта_несёт_неймспейс():
    assert project_path(issue_hook()) == "poh-harness/threads-harness"
    assert project_id(issue_hook()) == 85686131


def test_устаревшее_поле_repository_не_используется():
    """`repository.name` без неймспейса пропустил бы чужой проект в allowlist."""
    payload = issue_hook()
    payload["repository"] = {"name": "threads-harness"}
    assert normalize("Issue Hook", payload)["repository"]["full_name"] \
        == "poh-harness/threads-harness"


# --- дельта меток ---

def test_дельта_меток_считается_сама():
    changes = {"labels": {
        "previous": [{"title": "phase:created"}],
        "current": [{"title": "phase:created"}, {"title": "research-me"}],
    }}
    assert labels_added(issue_hook("update", changes=changes)) == ["research-me"]
    assert labels_removed(issue_hook("update", changes=changes)) == []


def test_снятие_метки_видно():
    changes = {"labels": {
        "previous": [{"title": "run:analyze"}, {"title": "phase:created"}],
        "current": [{"title": "phase:created"}],
    }}
    assert labels_removed(issue_hook("update", changes=changes)) == ["run:analyze"]
    assert labels_added(issue_hook("update", changes=changes)) == []


def test_без_changes_дельта_пуста():
    assert labels_added(issue_hook()) == []


# --- задача ---

def test_номер_задачи_из_iid_а_не_id():
    """Глобальный id в роли номера означал бы чужую задачу."""
    out = normalize("Issue Hook", issue_hook())
    assert out["issue"]["number"] == 7
    assert out["issue"]["number"] != 999


def test_действия_приводятся_к_внутренним():
    for gitlab, internal in [("open", "opened"), ("close", "closed"), ("reopen", "reopened")]:
        assert normalize("Issue Hook", issue_hook(gitlab))["action"] == internal


def test_смена_меток_выглядит_как_labeled():
    """Триггерный путь контура ждёт `labeled` с именем метки."""
    changes = {"labels": {"previous": [], "current": [{"title": "research-me"}]}}
    out = normalize("Issue Hook", issue_hook("update", changes=changes))
    assert out["action"] == "labeled"
    assert out["label"]["name"] == "research-me"


def test_update_без_меток_остаётся_edited():
    assert normalize("Issue Hook", issue_hook("update"))["action"] == "edited"


def test_метки_задачи_переводятся_в_имена():
    out = normalize("Issue Hook", issue_hook(labels=[{"title": "bug"}, {"title": "priority:P1"}]))
    assert [l["name"] for l in out["issue"]["labels"]] == ["bug", "priority:P1"]


# --- комментарий ---

def test_комментарий_несёт_id_тело_и_номер_задачи():
    out = normalize("Note Hook", note_hook("/analyze"))
    assert out["action"] == "created"
    assert out["comment"]["id"] == 3722933426
    assert out["comment"]["body"] == "/analyze"
    assert out["issue"]["number"] == 7


def test_автор_задачи_не_подменяется_автором_комментария():
    out = normalize("Note Hook", note_hook())
    assert out["issue"]["user"]["login"] == "someone"
    assert out["comment"]["user"]["login"] == "cvyatoslavka"


def test_заметка_не_к_задаче_отвергается():
    with pytest.raises(UnsupportedEvent):
        normalize("Note Hook", note_hook(noteable="MergeRequest"))


# --- признак бота ---

def test_без_логина_бота_все_люди():
    """Поля user.type у GitLab нет; без настройки считаем автора человеком."""
    assert normalize("Note Hook", note_hook())["comment"]["user"]["type"] == "User"


def test_логин_сервисного_аккаунта_даёт_бота():
    out = normalize("Note Hook", note_hook(), bot_login="cvyatoslavka")
    assert out["comment"]["user"]["type"] == "Bot"


# --- merge request ---

def test_merge_request_несёт_ветки():
    payload = {
        "object_kind": "merge_request", "user": USER, "project": PROJECT,
        "object_attributes": {"iid": 12, "title": "MR", "description": "",
                              "state": "opened", "action": "open",
                              "source_branch": "research/issue-7", "target_branch": "main"},
    }
    out = normalize("Merge Request Hook", payload)
    assert out["pull_request"]["number"] == 12
    assert out["pull_request"]["head"]["ref"] == "research/issue-7"
    assert out["pull_request"]["base"]["ref"] == "main"


# --- служебный ключ ---

def test_служебный_ключ_несёт_то_чего_нет_у_github():
    out = normalize("Issue Hook", issue_hook())
    assert out["_gitlab"]["project_id"] == 85686131
    assert "labels_added" in out["_gitlab"]
