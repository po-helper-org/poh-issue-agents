"""Ссылка на репозиторий, не привязанная к форме `owner/repo`.

GitHub адресует репозиторий ровно двумя сегментами. GitLab — путём из двух и
более (подгруппы вкладываются до 20 уровней) либо числовым id проекта, причём
путь в URL API обязан быть закодирован целиком: `group%2Fsub%2Fproject`.

Кодирование живёт здесь, а не в вызывающем коде. Иначе повторяется то, что
уже случилось в `worker/github_client.py`: имя метки там кодируется, имя файла
воркфлоу кодируется, а путь репозитория — ни в одном из 26 URL.

Чистый модуль: ни сети, ни Temporal, ни обращений к трекеру.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

GITHUB = "github"
GITLAB = "gitlab"


@dataclass(frozen=True)
class RepoRef:
    """Репозиторий у конкретного провайдера.

    `path` — человекочитаемая форма (`owner/repo`, `group/sub/project`), она же
    ключ allowlist и то, что видно в логах. `project_id` — числовой
    идентификатор GitLab; если он известен, обращаться по нему дешевле и
    надёжнее, чем по пути, который может смениться при переносе проекта.
    """

    provider: str
    path: str
    project_id: int | None = None

    @classmethod
    def parse(cls, raw: str, provider: str = GITHUB,
              project_id: int | None = None) -> "RepoRef":
        path = (raw or "").strip().strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) < 2:
            raise ValueError(
                f"ссылка на репозиторий требует как минимум два сегмента: {raw!r}")
        return cls(provider=provider, path="/".join(segments), project_id=project_id)

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.path.split("/"))

    @property
    def owner(self) -> str:
        """Верхнеуровневый владелец: организация GitHub или корневая группа."""
        return self.segments[0]

    @property
    def name(self) -> str:
        return self.segments[-1]

    @property
    def api_segment(self) -> str:
        """Готовая подстановка в путь REST API."""
        if self.provider == GITLAB:
            if self.project_id is not None:
                return str(self.project_id)
            return urllib.parse.quote(self.path, safe="")
        return self.path

    def __str__(self) -> str:
        return self.path
