"""Список отслеживаемых репозиториев (ISSUE_AGENT_REPOS).

Аналог RELIABILITY_REPOS в poh-pr-agents. Чистые функции: разбор спецификаций
и проверка допуска репозитория. Сетевых вызовов нет — проверка строковая.

Форматы записи (comma-separated в ISSUE_AGENT_REPOS):
  owner/repo — конкретный репозиторий
  owner/*    — любой репозиторий этого owner
  owner      — голый owner: то же, что owner/*
  *          — любой репозиторий (все установки App)
  (пусто)    — то же, что * — любой установленный
"""
from __future__ import annotations

import os


def parse_repo_specs(specs: list[str]) -> tuple[list[str], list[str]]:
    """Делит записи на точные `owner/repo` и маски-owner'ы.

    Возвращает (concrete, mask_owners); для `*` в mask_owners кладётся "*".
    Пустые записи игнорируются. Порт `parse_repo_specs` из pr-agents.
    """
    concrete: list[str] = []
    mask_owners: list[str] = []
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        if spec == "*":
            mask_owners.append("*")
        elif spec.endswith("/*"):
            mask_owners.append(spec[: -len("/*")])
        elif "/" not in spec:
            mask_owners.append(spec)  # голый owner → маска owner/*
        else:
            concrete.append(spec)
    return concrete, mask_owners


def is_allowed(repo: str, specs: list[str]) -> bool:
    """True, если репозиторий `owner/name` входит в allowlist.

    Пустой список или `*` → разрешено всё. Иначе — точное совпадение full_name
    (регистронезависимо) либо owner под маской.
    """
    concrete, mask_owners = parse_repo_specs(specs)
    if not concrete and not mask_owners:
        return True  # пусто → любой установленный
    if "*" in mask_owners:
        return True
    repo_l = repo.lower()
    if repo_l in {c.lower() for c in concrete}:
        return True
    owner = repo_l.split("/", 1)[0]
    return owner in {m.lower() for m in mask_owners}


def allowed_specs() -> list[str]:
    """Записи ISSUE_AGENT_REPOS из окружения (comma-separated, пустые допустимы)."""
    return os.environ.get("ISSUE_AGENT_REPOS", "").split(",")
