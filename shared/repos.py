"""Список отслеживаемых репозиториев (ISSUE_AGENT_REPOS).

Аналог RELIABILITY_REPOS в poh-pr-agents. Чистые функции: разбор спецификаций
и проверка допуска репозитория. Сетевых вызовов нет — проверка строковая.

Форматы записи (comma-separated в ISSUE_AGENT_REPOS):
  owner/repo        — конкретный репозиторий
  group/sub/project — конкретный проект во вложенной подгруппе
  owner/*           — всё, что принадлежит owner, включая подгруппы
  group/sub/*       — всё внутри этой подгруппы
  owner             — голый owner: то же, что owner/*
  *                 — любой репозиторий (все установки App)
  (пусто)           — то же, что * — любой установленный
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
    """True, если репозиторий входит в allowlist.

    Пустой список или `*` → разрешено всё. Иначе — точное совпадение пути
    (регистронезависимо) либо маска-префикс.

    Маска сопоставляется **по границе сегмента**: `group/sub` покрывает
    `group/sub/project`, но не `group/subterfuge/project`. Маска верхнего
    уровня (`owner/*` или голый `owner`) достаёт и до вложенных подгрупп —
    так у одной записи остаётся один смысл «всё, что принадлежит владельцу»
    на обоих провайдерах.

    До этой правки сравнивался только первый сегмент пути, поэтому проект
    GitLab в подгруппе не проходил ни точной записью, ни маской своей
    подгруппы: событие молча отбрасывалось до Temporal.
    """
    concrete, mask_owners = parse_repo_specs(specs)
    if not concrete and not mask_owners:
        return True  # пусто → любой установленный
    if "*" in mask_owners:
        return True
    repo_l = repo.strip().strip("/").lower()
    if repo_l in {c.strip().strip("/").lower() for c in concrete}:
        return True
    for mask in mask_owners:
        mask_l = mask.strip().strip("/").lower()
        if not mask_l:
            continue
        if repo_l == mask_l or repo_l.startswith(mask_l + "/"):
            return True
    return False


def allowed_specs() -> list[str]:
    """Записи ISSUE_AGENT_REPOS из окружения (comma-separated, пустые допустимы)."""
    return os.environ.get("ISSUE_AGENT_REPOS", "").split(",")
