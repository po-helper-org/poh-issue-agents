"""Выбор провайдера по репозиторию."""
import importlib

import pytest


@pytest.fixture
def forge(monkeypatch):
    monkeypatch.delenv("GITLAB_REPOS", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh")
    monkeypatch.setenv("GITLAB_TOKEN", "gl")
    import forge as f
    return importlib.reload(f)


def test_умолчание_github(forge):
    """Пустая переменная означает GitHub, а не «всё подряд»."""
    assert forge.provider_for("po-helper-org/poh-demo-checkout") == "github"


def test_репозиторий_из_списка_уходит_в_gitlab(forge, monkeypatch):
    monkeypatch.setenv("GITLAB_REPOS", "poh-harness/threads-harness")
    import forge as f
    g = importlib.reload(f)
    assert g.provider_for("poh-harness/threads-harness") == "gitlab"
    assert g.provider_for("po-helper-org/poh-demo-checkout") == "github"


def test_маска_группы_работает(forge, monkeypatch):
    monkeypatch.setenv("GITLAB_REPOS", "poh-harness/*")
    import forge as f
    g = importlib.reload(f)
    assert g.provider_for("poh-harness/anything") == "gitlab"
    assert g.provider_for("other/anything") == "github"


def test_вложенная_подгруппа(forge, monkeypatch):
    monkeypatch.setenv("GITLAB_REPOS", "group/sub/*")
    import forge as f
    g = importlib.reload(f)
    assert g.provider_for("group/sub/project") == "gitlab"
    assert g.provider_for("group/other/project") == "github"


def test_вызов_уходит_в_нужный_клиент(forge, monkeypatch):
    monkeypatch.setenv("GITLAB_REPOS", "gl/*")
    import forge as f
    g = importlib.reload(f)
    seen = []
    monkeypatch.setattr(g.github_client, "post_comment",
                        lambda repo, n, body: seen.append(("github", repo)))
    monkeypatch.setattr(g.gitlab_client, "post_comment",
                        lambda repo, n, body: seen.append(("gitlab", repo)))
    g.post_comment("gl/project", 1, "текст")
    g.post_comment("gh/project", 1, "текст")
    assert seen == [("gitlab", "gl/project"), ("github", "gh/project")]


def test_подмена_атрибута_перекрывает_диспетчер(forge, monkeypatch):
    """Тридцать тестовых файлов патчат имена напрямую — это должно работать."""
    called = []
    monkeypatch.setattr(forge, "post_comment", lambda *a, **k: called.append(a), raising=False)
    forge.post_comment("любой/репо", 1, "текст")
    assert called


def test_операции_которой_нет_у_провайдера_называют_провайдера(forge, monkeypatch):
    """Ошибка обязана сказать, у КОГО не нашлось операции."""
    monkeypatch.setenv("GITLAB_REPOS", "gl/*")
    import forge as f
    g = importlib.reload(f)
    with pytest.raises(NotImplementedError, match="gitlab.*совсем_нет_такой"):
        g.совсем_нет_такой("gl/project")


def test_dispatch_workflow_бросает_ошибку_самого_клиента(forge, monkeypatch):
    """Диспетчер не подменяет объяснение: у GitLab это осознанный отказ."""
    monkeypatch.setenv("GITLAB_REPOS", "gl/*")
    import forge as f
    g = importlib.reload(f)
    with pytest.raises(NotImplementedError, match="локальным раннером"):
        g.dispatch_workflow("gl/project", "wf.yml")


def test_list_recent_comments_реализован_у_обоих_провайдеров(forge, monkeypatch):
    """Повторное ревью, находка (Important) у `github_client.list_comments`.
    `ask_question` в `worker/activities.py` зовёт `github_client.list_recent_comments`
    через этот же диспетчер (`github_client = forge` там). Без метода у ОБОИХ
    клиентов GitLab-репозиторий падал бы с `NotImplementedError` ровно там,
    где для GitHub всё работало бы — расхождение поверхности, которого этот
    диспетчер (и `activities.py`, не знающий о провайдере) не должен видеть."""
    monkeypatch.setenv("GITLAB_REPOS", "gl/*")
    import forge as f
    g = importlib.reload(f)
    monkeypatch.setattr(g.github_client, "list_recent_comments",
                        lambda repo, n, limit=100: ["github"])
    monkeypatch.setattr(g.gitlab_client, "list_recent_comments",
                        lambda repo, n, limit=100: ["gitlab"])
    assert g.list_recent_comments("gh/project", 1) == ["github"]
    assert g.list_recent_comments("gl/project", 1) == ["gitlab"]
