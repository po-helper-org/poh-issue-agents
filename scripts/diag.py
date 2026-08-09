"""Диагностика эффективного конфига сервиса — «почему issue не доехал».

Событие может пропасть молча: репозиторий вне ISSUE_AGENT_REPOS отбрасывается
до старта workflow, а GH_TOKEN незаметно подменяет GitHub App личным аккаунтом.
Ни то, ни другое не видно снаружи — GitHub получает 200, в Temporal пусто.
Скрипт печатает то, что сервис реально видит в своём окружении.

Запускать ВНУТРИ контейнера, иначе прочитаешь окружение хоста, а не сервиса:

    docker compose exec webhook python scripts/diag.py
    docker compose exec webhook python scripts/diag.py --repo owner/name
    docker compose exec webhook python scripts/diag.py --no-temporal

Значения секретов не печатаются ни при каких условиях — только «задан/не задан».
Вывод уходит в stdout и может попасть в тикет или чат, а конфиг сервиса
(список репозиториев, адрес кластера) — уже разведданные для постороннего.

Коды возврата: 0 — конфиг рабочий; 1 — Temporal недостижим либо авторизация в
GitHub не настроена вовсе (ни PAT, ни App).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.repos import allowed_specs, is_allowed, parse_repo_specs

# Печатаем только факт наличия. Список закрыт намеренно: добавляя сюда новую
# переменную, ты явно решаешь, что её значение секретно.
SECRET_VARS = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_PRIVATE_KEY_B64",
    "ZAI_API_KEY",
)


def _is_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _yes_no(flag: bool) -> str:
    return "задан" if flag else "НЕ задан"


def allowlist_lines(specs: list[str]) -> list[str]:
    """Сырое значение ISSUE_AGENT_REPOS и результат его разбора."""
    raw = os.environ.get("ISSUE_AGENT_REPOS", "")
    concrete, masks = parse_repo_specs(specs)
    lines = [f"  ISSUE_AGENT_REPOS = {raw!r}"]
    if not concrete and not masks:
        lines.append("  → пусто: разрешён ЛЮБОЙ репозиторий, где установлен App")
        return lines
    if "*" in masks:
        lines.append("  → '*': разрешён ЛЮБОЙ репозиторий, где установлен App")
    if concrete:
        lines.append(f"  → точные записи: {', '.join(concrete)}")
    owner_masks = [m for m in masks if m != "*"]
    if owner_masks:
        lines.append(f"  → маски owner/*: {', '.join(owner_masks)}")
    return lines


def repo_verdict_lines(repo: str, specs: list[str]) -> list[str]:
    """Прямой ответ на исходный вопрос: доедет событие этого репо или нет."""
    concrete, masks = parse_repo_specs(specs)
    if not is_allowed(repo, specs):
        return [
            f"  {repo}: ОТФИЛЬТРУЕТСЯ — события отбрасываются до старта workflow",
            "  → добавь его в ISSUE_AGENT_REPOS и перезапусти сервис",
        ]
    reason = "allowlist пуст — разрешено всё"
    if "*" in masks:
        reason = "запись '*'"
    elif repo.lower() in {c.lower() for c in concrete}:
        reason = f"точная запись {repo}"
    else:
        owner = repo.lower().split("/", 1)[0]
        match = next((m for m in masks if m.lower() == owner), None)
        if match:
            reason = f"маска {match}/*"
    return [f"  {repo}: ДОЕДЕТ (сработала {reason})"]


def auth_lines() -> tuple[list[str], bool]:
    """Режим авторизации в GitHub. Второй элемент — настроена ли она вообще."""
    pat_var = next((v for v in ("GH_TOKEN", "GITHUB_TOKEN") if _is_set(v)), None)
    app = _is_set("GITHUB_APP_ID")
    key = _is_set("GITHUB_PRIVATE_KEY_B64") or _is_set("GITHUB_PRIVATE_KEY_PATH")

    if pat_var and app:
        # Главный молчаливый отказ: github_client._auth_headers предпочитает PAT,
        # и App-путь выключается без единого следа — комментарии уходят от имени
        # владельца токена, а не от приложения.
        return ([
            f"  режим: PAT ({pat_var}) — ПЕРЕБИВАЕТ настроенный GitHub App",
            "  ⚠ заданы одновременно PAT и GITHUB_APP_ID: App-путь не используется,",
            "    всё постится от имени владельца токена. Убери PAT, если нужен App.",
        ], True)
    if pat_var:
        return ([f"  режим: PAT ({pat_var}) — документированный dev-фолбэк"], True)
    if app:
        lines = ["  режим: GitHub App (installation-токен по репозиторию)"]
        if not key:
            lines.append("  ⚠ GITHUB_APP_ID задан, но приватного ключа нет "
                         "(ни GITHUB_PRIVATE_KEY_B64, ни GITHUB_PRIVATE_KEY_PATH)")
            return (lines, False)
        return (lines, True)
    return (["  режим: НЕ НАСТРОЕН — ни PAT, ни GitHub App"], False)


def temporal_config_lines() -> list[str]:
    return [
        f"  TEMPORAL_ADDRESS   = {os.environ.get('TEMPORAL_ADDRESS', 'localhost:7233')}",
        f"  TEMPORAL_NAMESPACE = {os.environ.get('TEMPORAL_NAMESPACE', 'default')}",
        f"  TEMPORAL_TLS       = {os.environ.get('TEMPORAL_TLS', '') or '(выкл)'}",
    ]


async def temporal_check_lines() -> tuple[list[str], bool]:
    """Реальная проверка связи: без неё конфиг может выглядеть корректным,
    а кластер быть недостижимым."""
    from shared.temporal_client import connect_temporal

    from datetime import timedelta

    try:
        client = await connect_temporal()
        healthy = await client.service_client.check_health(timeout=timedelta(seconds=10))
    except Exception as exc:  # сетевые, TLS, отсутствующий namespace — всё сюда
        return ([f"  связь: НЕТ — {type(exc).__name__}: {exc}"], False)
    if not healthy:
        return (["  связь: кластер отвечает, но health-check отрицательный"], False)
    return (["  связь: есть, кластер отвечает"], True)


def secrets_lines() -> list[str]:
    return [f"  {var}: {_yes_no(_is_set(var))}" for var in SECRET_VARS]


def build_report(repo: str | None) -> tuple[list[str], bool]:
    """Статическая часть отчёта (без сети). Второй элемент — всё ли в порядке."""
    specs = allowed_specs()
    auth, auth_ok = auth_lines()

    lines = ["=== Отслеживаемые репозитории ==="]
    lines += allowlist_lines(specs)
    if repo:
        lines.append("")
        lines.append("=== Вердикт по репозиторию ===")
        lines += repo_verdict_lines(repo, specs)
    lines.append("")
    lines.append("=== Авторизация в GitHub ===")
    lines += auth
    lines.append("")
    lines.append("=== Секреты (только факт наличия) ===")
    lines += secrets_lines()
    lines.append(f"  DRY_RUN: {'включён — мутаций в GitHub не будет' if _is_set('DRY_RUN') else 'выключен (боевой режим)'}")
    lines.append("")
    lines.append("=== Temporal ===")
    lines += temporal_config_lines()
    return lines, auth_ok


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Диагностика конфига issue-agent")
    parser.add_argument("--repo", help="проверить конкретный репозиторий owner/name")
    parser.add_argument("--no-temporal", action="store_true",
                        help="не проверять связь с Temporal (только конфиг)")
    args = parser.parse_args(argv)

    lines, ok = build_report(args.repo)
    if args.no_temporal:
        lines.append("  связь: не проверялась (--no-temporal)")
    else:
        check, temporal_ok = await temporal_check_lines()
        lines += check
        ok = ok and temporal_ok

    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
