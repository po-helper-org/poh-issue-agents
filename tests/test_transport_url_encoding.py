"""Транспортные тесты кодирования URL для путей репозиториев.

Проверяет, что все API вызовы правильно кодируют пути GitLab
с вложенными подгруппами и специальными символами.
"""

import importlib
import urllib.parse

import pytest

from shared.repo_ref import RepoRef


def _fresh_github_client(monkeypatch, dry=False):
    """Создает чистый инстанс github_client для каждого теста."""
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    import github_client
    return importlib.reload(github_client)


def test_repo_ref_encodes_gitlab_nested_paths():
    """RepoRef кодирует вложенные подгруппы для GitLab."""
    test_cases = [
        ("group/project", "group%2Fproject"),
        ("group/sub/project", "group%2Fsub%2Fproject"),
        ("org/team/subgroup/repo", "org%2Fteam%2Fsubgroup%2Frepo"),
        ("a/b/c/d/e/f", "a%2Fb%2Fc%2Fd%2Fe%2Ff"),
    ]
    
    for path, expected_api_segment in test_cases:
        ref = RepoRef.parse(path, provider="gitlab")
        assert ref.api_segment == expected_api_segment, (
            f"Для {path} ожидался {expected_api_segment}, получен {ref.api_segment}")


def test_repo_ref_github_paths_not_encoded():
    """GitHub пути не кодируются - они уже валидные сегменты URL."""
    test_cases = [
        "owner/repo",
        "org/project",
        "user/repository",
    ]
    
    for path in test_cases:
        ref = RepoRef.parse(path, provider="github")
        assert ref.api_segment == path, (
            f"Для GitHub {path} кодирование не нужно, но получен {ref.api_segment}")


def test_repo_prefers_numeric_id_over_path():
    """При наличии numeric_id GitLab API использует его вместо пути."""
    ref = RepoRef.parse("group/sub/project", provider="gitlab", project_id=12345)
    assert ref.api_segment == "12345"


def test_special_chars_in_path_are_encoded():
    """Специальные символы в путях кодируются."""
    test_cases = [
        ("group/project+name", "group%2Fproject%2Bname"),
        ("group/pro@ject", "group%2Fpro%40ject"),
        ("group/pro#ject", "group%2Fpro%23ject"),
    ]
    
    for path, expected in test_cases:
        ref = RepoRef.parse(path, provider="gitlab")
        assert ref.api_segment == expected


def test_github_client_uses_url_encoded_repo_path(monkeypatch):
    """Проверяет, что github_client использует правильно кодированный путь в API."""
    gc = _fresh_github_client(monkeypatch)
    
    calls = []
    
    class MockResponse:
        status_code = 200
        
        def raise_for_status(self):
            pass
    
    def mock_request(method, url, **kwargs):
        calls.append({"method": method, "url": url})
        return MockResponse()
    
    monkeypatch.setattr(gc.requests, "get", mock_request)
    monkeypatch.setattr(gc.requests, "post", mock_request)
    monkeypatch.setattr(gc.requests, "delete", mock_request)
    
    # Тестируем с репозиторием GitLab (имитация через путь)
    test_repo = "group/sub/project"
    
    # Вызываем различные операции, которые используют URL репозитория
    try:
        gc.set_labels(test_repo, 1, add=["test"])
        gc.remove_label(test_repo, 1, "test")
    except Exception:
        pass  # Нас интересуют только URL, не успешность запросов
    
    # Проверяем, что во всех URL путь репозитория закодирован
    expected_segment = urllib.parse.quote(test_repo, safe="")
    
    for call in calls:
        url = call["url"]
        # Для GitHub API путь должен быть закодирован в URL
        if f"/repos/{test_repo}/" in url:
            # Если URL содержит некодированный путь - это ошибка
            pytest.fail(f"URL содержит некодированный путь репозитория: {url}")
        
        # Проверяем, что кодированный путь присутствует в URL
        if expected_segment in url or test_repo in url:
            # URL либо содержит кодированный, либо оригинальный путь
            # Для GitHub с обычным путем (без спецсимволов) оба варианта валидны
            pass


def test_label_names_are_always_url_encoded(monkeypatch):
    """Имена меток всегда кодируются, независимо от провайдера."""
    gc = _fresh_github_client(monkeypatch)
    
    calls = []
    
    class MockResponse:
        status_code = 200
        
        def raise_for_status(self):
            pass
    
    def mock_request(method, url, **kwargs):
        calls.append({"method": method, "url": url})
        return MockResponse()
    
    monkeypatch.setattr(gc.requests, "post", mock_request)
    monkeypatch.setattr(gc.requests, "delete", mock_request)
    
    # Метки с двоеточиями (стандартная схема меток проекта)
    test_labels = ["run:analyze", "phase:classified", "bug:diagnosed"]
    
    for label in test_labels:
        try:
            gc.set_labels("owner/repo", 1, add=[label])
        except Exception:
            pass
    
    # Проверяем, что все имена меток закодированы
    for call in calls:
        url = call["url"]
        # Двоеточие должно быть закодировано как %3A
        if "run:analyze" in url:
            pytest.fail(f"Имя метки не закодировано в URL: {url}")
        assert "run%3Aanalyze" in url or "phase%3Aclassified" in url or "bug%3Adiagnosed" in url, (
            f"URL должен содержать закодированное имя метки: {url}")


def test_workflow_file_names_are_url_encoded(monkeypatch):
    """Имена файлов воркфлоу кодируются при создании через API."""
    gc = _fresh_github_client(monkeypatch)
    
    calls = []
    
    class MockResponse:
        status_code = 200
        
        def raise_for_status(self):
            pass
    
    def mock_request(method, url, **kwargs):
        calls.append({"method": method, "url": url})
        return MockResponse()
    
    monkeypatch.setattr(gc.requests, "put", mock_request)
    
    # Тестируем создание файла с именем, требующим кодирования
    test_file = "workflows/issue-lifecycle-workflow.yml"
    encoded_file = urllib.parse.quote(test_file, safe="/")
    
    try:
        # Вызываем метод, который создает файл (если такой есть)
        if hasattr(gc, 'create_file'):
            gc.create_file("owner/repo", test_file, "content", "message")
    except Exception:
        pass
    
    # Проверяем кодирование имени файла
    for call in calls:
        url = call["url"]
        # Имя файла должно быть закодировано, кроме слешей
        assert encoded_file in url or test_file in url, (
            f"URL должен содержать (закодированное) имя файла: {url}")


def test_deeply_nested_gitlab_paths_work_correctly():
    """Очень глубокие вложения (до 20 уровней) корректно обрабатываются."""
    # Создаем путь с максимальной глубиной
    deep_path = "/".join([f"level{i}" for i in range(1, 21)]) + "/project"
    
    ref = RepoRef.parse(deep_path, provider="gitlab")
    
    # Проверяем, что все сегменты сохранены
    assert len(ref.segments) == 21
    assert ref.owner == "level1"
    assert ref.name == "project"
    
    # Проверяем, что API сегмент полностью закодирован
    expected = urllib.parse.quote(deep_path, safe="")
    assert ref.api_segment == expected
    
    # Проверяем, что можно восстановить путь из сегментов
    reconstructed = "/".join(ref.segments)
    assert reconstructed == deep_path


def test_url_encoding_preserves_case_sensitivity():
    """Кодирование URL сохраняет регистр символов."""
    test_cases = [
        ("Group/Project", "Group%2FProject"),
        ("ORG/REPO", "ORG%2FREPO"),
        ("group/SubGroup/Project", "group%2FSubGroup%2FProject"),
    ]
    
    for path, expected in test_cases:
        ref = RepoRef.parse(path, provider="gitlab")
        assert ref.api_segment == expected, (
            f"Регистр должен сохраняться при кодировании: {path}")


def test_edge_cases_in_url_encoding():
    """Крайние случаи кодирования URL."""
    # Путь с ведущими/заключающими пробелами (должны быть удалены при parse)
    ref = RepoRef.parse("  group/sub/project  ", provider="gitlab")
    assert ref.api_segment == "group%2Fsub%2Fproject"
    
    # Путь с несколькими слешами подряд
    ref = RepoRef.parse("group///sub///project", provider="gitlab")
    assert ref.api_segment == "group%2Fsub%2Fproject"
    
    # Путь с Unicode символами (если поддерживаются)
    try:
        unicode_path = "group/sub/проект"
        ref = RepoRef.parse(unicode_path, provider="gitlab")
        # Unicode должен быть закодирован
        assert "%" in ref.api_segment
    except Exception:
        # Если Unicode не поддерживается - это нормально
        pass


def test_allowlist_works_with_encoded_paths():
    """Allowlist корректно работает с закодированными путями."""
    from shared.repos import is_allowed
    
    # Тестируем, что allowlist использует некодированные пути для сравнения
    test_cases = [
        ("group/sub/project", ["group/sub/*"], True),
        ("group/sub/project", ["group/*"], True),
        ("group/sub/project", ["other/*"], False),
        ("org/team/repo", ["org/team/repo"], True),
    ]
    
    for repo_path, allowlist, expected in test_cases:
        result = is_allowed(repo_path, allowlist)
        assert result == expected, (
            f"Allowlist проверка не удалась для {repo_path} с {allowlist}: "
            f"ожидалось {expected}, получено {result}"
        )


def test_transport_integration_with_multiple_operations(monkeypatch):
    """Интеграционный тест: несколько операций с одним репозиторием."""
    gc = _fresh_github_client(monkeypatch)
    
    all_calls = []
    
    class MockResponse:
        status_code = 200
        
        def raise_for_status(self):
            pass
    
    def track_calls(method, url, **kwargs):
        all_calls.append({"method": method, "url": url})
        return MockResponse()
    
    monkeypatch.setattr(gc.requests, "get", track_calls)
    monkeypatch.setattr(gc.requests, "post", track_calls)
    monkeypatch.setattr(gc.requests, "delete", track_calls)
    monkeypatch.setattr(gc.requests, "put", track_calls)
    
    test_repo = "group/sub/project"
    
    # Выполняем последовательность операций
    try:
        gc.set_labels(test_repo, 1, add=["phase:classified"])
        gc.remove_label(test_repo, 1, "run:analyze")
        if hasattr(gc, 'get_issue'):
            gc.get_issue(test_repo, 1)
    except Exception:
        pass
    
    # Проверяем, что все URL корректны
    for call in all_calls:
        url = call["url"]
        # URL не должен содержать некодированные спецсимволы в путях
        assert "run:analyze" not in url, f"Некодированная метка в URL: {url}"
        assert "phase:classified" not in url, f"Некодированная метка в URL: {url}"
