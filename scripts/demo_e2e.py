#!/usr/bin/env python3
"""Автономный прогон контура по сценарию демо.

Заводит Issue на простую доработку и ведёт его по стадиям, проверяя каждую.
Существует потому, что модульные тесты не ловят то, что ломает контур: занятый
порт на сервере, кэш сборки с чужим коммитом, отставший main, эхо собственной
метки, 500 на повторной доставке вебхука. Все они живут на стыках — между
кодом, конфигом, GitHub и Docker — и видны только в живом прогоне.

Проверяются три поверхности, они дополняют друг друга:
  GitHub   — метки и комментарии: что увидит человек;
  Temporal — какой воркфлоу выполняется (косвенно, через метки фаз);
  Sentry   — что упало молча (если задан SENTRY_TOKEN).

Использование:
    python scripts/demo_e2e.py --repo owner/name
    python scripts/demo_e2e.py --repo owner/name --issue 42   # вести существующий
    python scripts/demo_e2e.py --repo owner/name --keep       # не закрывать по итогу
"""

import argparse
import json
import os
import subprocess
import sys
import time

# Стадии сценария: (имя, что ждём, потолок ожидания в секундах).
#
# Потолки разные не случайно: триаж — это несколько вызовов модели, аналитика —
# цепочка FNR через `claude -p`, разработка — прогон агента с установкой
# зависимостей и тестами. Один общий потолок либо врал бы про триаж, либо не
# дожидался разработки.
STAGES = [
    ("триаж: классификация",
     lambda st: any(l.startswith("advisor:") for l in st["labels"]), 600),
    ("триаж: приоритет",
     lambda st: any(l.startswith("priority:") for l in st["labels"]), 600),
    ("аналитика запущена",
     lambda st: "phase:business-analysis" in st["labels"] or st["analysis_started"], 900),
    ("ветка требований",
     lambda st: st["research_branch"], 3600),
    ("передача разработчику",
     lambda st: "ready-for-dev" in st["labels"], 600),
    ("декомпозиция",
     lambda st: st["subissues"] > 0 or st["decomposition_comment"], 900),
    ("разработка началась",
     lambda st: "in-development" in st["labels"] or st["pr"] is not None, 900),
    ("PR открыт",
     lambda st: st["pr"] is not None, 3600),
    ("ревью прошло",
     lambda st: "phase:pr-review" in st["labels"], 1800),
]

# Метки, при которых контур сам сказал «дальше не пойду». Ждать после них до
# потолка — врать себе: задача уже передана человеку.
STOP_LABELS = ("phase:failed", "failed:analyze", "needs-human:triage",
               "phase:escalated", "needs-human:pr")


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {result.stderr.strip()[:300]}")
    return result.stdout


def issue_state(repo: str, number: int) -> dict:
    data = json.loads(gh("issue", "view", str(number), "--repo", repo,
                         "--json", "labels,comments,title"))
    labels = [l["name"] for l in data["labels"]]
    bodies = [c["body"] for c in data["comments"]]

    subs = json.loads(gh("issue", "list", "--repo", repo, "--state", "all",
                         "--search", f'"root-issue: #{number}" in:body',
                         "--json", "number") or "[]")

    branches = subprocess.run(
        ["git", "ls-remote", "--heads", f"https://github.com/{repo}.git",
         f"research/issue-{number}"],
        capture_output=True, text=True).stdout.strip()

    prs = json.loads(gh("pr", "list", "--repo", repo, "--state", "all",
                        "--json", "number,body") or "[]")
    pr = next((p["number"] for p in prs if f"Closes #{number}" in (p["body"] or "")), None)

    return {
        "labels": labels,
        "comments": len(bodies),
        "analysis_started": any("автономный анализ" in b.lower() for b in bodies),
        "decomposition_comment": any("Декомпозиция" in b for b in bodies),
        "research_branch": bool(branches),
        "subissues": len(subs),
        "pr": pr,
    }


def wait_for(repo: str, number: int, check, timeout: int) -> tuple[bool, dict]:
    deadline = time.time() + timeout
    state: dict = issue_state(repo, number)
    while True:
        if check(state):
            return True, state
        stuck = [l for l in state["labels"] if l in STOP_LABELS]
        if stuck:
            print(f"   ✗ контур остановился сам: {', '.join(stuck)}")
            return False, state
        if time.time() >= deadline:
            return False, state
        time.sleep(20)
        state = issue_state(repo, number)


def sentry_errors(period: str = "1h") -> list[str]:
    """Ошибки стенда за период.

    Пусто и при отсутствии токена, и при отсутствии ошибок — поэтому вызывающий
    сравнивает списки «до» и «после», а не доверяет пустоте как признаку
    здоровья.
    """
    token = os.environ.get("SENTRY_TOKEN", "").strip()
    org = os.environ.get("SENTRY_ORG", "poh-orgranization").strip()
    if not token:
        return []
    import urllib.request
    url = (f"https://us.sentry.io/api/0/organizations/{org}/issues/"
           f"?query=is:unresolved environment:harness&statsPeriod={period}")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return [i.get("title", "") for i in json.load(resp)]
    except Exception as exc:  # доступность Sentry не должна ронять прогон
        return [f"(Sentry недоступен: {exc})"]


DEFAULT_BODY = """## Проблема

Ответ `POST /quote` не содержит валюты. Клиент вынужден догадываться, что суммы
в рублях, и на витрине это уже приводило к разночтениям.

## Что нужно

Добавить в ответ поле `currency` со значением `RUB`.

## HowToDemo

```bash
curl -sX POST localhost:8080/quote -H 'content-type: application/json' \\
  -d '{"items":[{"sku":"a","price":100,"qty":1}]}'
```

Ожидаемо: в ответе есть `"currency":"RUB"`, остальные поля не изменились.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue", type=int, help="вести существующий Issue")
    parser.add_argument("--title", default="Добавить валюту в ответ /quote")
    parser.add_argument("--keep", action="store_true", help="не закрывать Issue по итогу")
    args = parser.parse_args()

    number = args.issue
    if number is None:
        url = gh("issue", "create", "--repo", args.repo,
                 "--title", args.title, "--body", DEFAULT_BODY).strip()
        number = int(url.rstrip("/").split("/")[-1])
        print(f"Заведён Issue #{number}: {url}\n")
    else:
        print(f"Веду существующий Issue #{number}\n")

    before = set(sentry_errors())
    passed: list[str] = []
    failed: list[str] = []

    for name, check, timeout in STAGES:
        print(f"→ {name} (потолок {timeout // 60} мин)")
        ok, state = wait_for(args.repo, number, check, timeout)
        if ok:
            passed.append(name)
            print(f"   ✓ метки: {', '.join(state['labels']) or '—'}")
            continue
        failed.append(name)
        print(f"   ✗ не дождался; метки: {', '.join(state.get('labels', [])) or '—'}")
        # Дальше идти бессмысленно: следующие стадии опираются на эту.
        break

    print("\n" + "=" * 60)
    print(f"Пройдено: {len(passed)} из {len(STAGES)}")
    for name in passed:
        print(f"  ✓ {name}")
    for name in failed:
        print(f"  ✗ {name}")

    new_errors = [e for e in sentry_errors() if e not in before]
    if new_errors:
        print("\nНовые ошибки в Sentry за прогон:")
        for err in new_errors:
            print(f"  ⚠ {err}")

    if not args.keep and not failed:
        gh("issue", "close", str(number), "--repo", args.repo,
           "--comment", "Прогон контура завершён, задача служебная.")

    return 0 if not failed and not new_errors else 1


if __name__ == "__main__":
    sys.exit(main())
