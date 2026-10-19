"""Выбор провайдера по репозиторию.

Модуль подставляет нужный клиент по первому аргументу вызова — им у всех
операций является репозиторий. Благодаря этому 118 мест в `activities.py`
остаются без изменений: меняется одна строка импорта.

Почему диспетчер, а не правка каждого вызова. Правка 118 мест ради выбора
провайдера — это 118 возможностей ошибиться в механической работе, причём в
файле, который правят параллельно. Диспетчер держит решение в одном месте, и
его видно целиком.

Принадлежность репозитория задаётся переменными `GITLAB_REPOS` и `GITEA_REPOS`
в том же формате, что и `ISSUE_AGENT_REPOS`. Молчание переменных означает GitHub:
контур работал с ним всегда, и умолчание не должно менять поведение. Gitea —
self-hosted хранилище карточек харнесса БФТ (ADR-21): корпоративные требования
не уходят на github.com.
"""
from __future__ import annotations

import logging
import os

import gitea_client
import github_client
import gitlab_client

from shared.repos import is_allowed

_log = logging.getLogger("forge")

GITHUB = "github"
GITLAB = "gitlab"
GITEA = "gitea"

_CLIENTS = {GITHUB: github_client, GITLAB: gitlab_client, GITEA: gitea_client}


def gitlab_specs() -> list[str]:
    return os.environ.get("GITLAB_REPOS", "").split(",")


def gitea_specs() -> list[str]:
    return os.environ.get("GITEA_REPOS", "").split(",")


def provider_for(repo: str) -> str:
    """Какому провайдеру принадлежит репозиторий.

    Пустой `GITLAB_REPOS` намеренно означает «GitHub», а не «всё подряд»:
    `is_allowed` на пустом списке разрешает всё, и без этой проверки включение
    переменной было бы не нужно — весь трафик уехал бы в GitLab молча.
    """
    for provider, specs in ((GITEA, gitea_specs()), (GITLAB, gitlab_specs())):
        specs = [s for s in specs if s.strip()]
        if specs and is_allowed(str(repo), specs):
            return provider
    return GITHUB


def client_for(repo: str):
    return _CLIENTS[provider_for(repo)]


def __getattr__(name: str):
    """Операция, выбирающая клиент по репозиторию.

    `__getattr__` модуля срабатывает только для имён, которых в модуле нет.
    Поэтому подмена атрибута тестом (`monkeypatch.setattr(forge, "post_comment",
    ...)`) продолжает работать: заданный атрибут находится раньше и диспетчер
    не вызывается.
    """
    if name.startswith("_"):
        raise AttributeError(name)

    def call(repo, *args, **kwargs):
        client = client_for(repo)
        fn = getattr(client, name, None)
        if fn is None:
            raise NotImplementedError(
                f"{provider_for(repo)}-клиент не умеет «{name}» для {repo}")
        return fn(repo, *args, **kwargs)

    call.__name__ = name
    return call
