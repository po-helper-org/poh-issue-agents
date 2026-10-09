#!/usr/bin/env python3
"""Живая приёмка T1 (#329) на стенде харнесса БФТ: Gitea → webhook → Temporal → GLM → комментарий.

Запуск под aleks на сервере:
    ~/Projects/poh-issue-agents/.venv/bin/python scripts/smoke_gitea.py [--timeout 180] [--keep]

Создаёт задачу в bft/requests, ждёт IssueLifecycle этой задачи в Temporal и подписанный
комментарий агента в задаче, проверяет, что `claude` на сервере не запускался.
Задача закрывается по завершении (--keep — оставить открытой). Токен — из файла, не печатается.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from shared.agent_comment import is_agent_comment  # noqa: E402

GITEA = os.environ.get("GITEA_URL", "http://127.0.0.1:8650") + "/api/v1/repos/bft/requests"
# Карточку заводит учётка приёма, а не агент: от агента prefilter отбросил бы её как «bot».
INTAKE = open(os.path.expanduser("~/.config/bft-harness/intake-token")).read().strip()
TOKEN = open(os.path.expanduser("~/.config/bft-harness/gitea-token")).read().strip()
TEMPORAL = os.path.expanduser("~/.local/share/bft-harness/bin/temporal")


def api(method, path, body=None, token=None):
    req = urllib.request.Request(GITEA + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"token {token or TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def workflows(number: int) -> list[str]:
    out = subprocess.run([TEMPORAL, "workflow", "list", "--address", "127.0.0.1:7233", "-o", "json",
                          "--query", "WorkflowType = 'IssueLifecycle'"], capture_output=True, text=True)
    rows = json.loads(out.stdout or "[]") if out.returncode == 0 else []
    want = f"issue-bft/requests-{number}"   # точный id: endswith("1") принял бы и карточку 11
    return [f"{w['execution']['workflowId']} {w.get('status')}" for w in rows if w["execution"]["workflowId"] == want]


def stages(number: int) -> tuple[list[str], list[str]]:
    """(завершённые активности, упавшие активности) процесса задачи по истории Temporal.

    Критерий — история, а не комментарий: при сбое стадии контур тоже пишет комментарий
    («Автоматическая обработка не удалась»), и проверка «есть комментарий агента» его принимала.
    """
    out = subprocess.run([TEMPORAL, "workflow", "show", "-w", f"issue-bft/requests-{number}",
                          "--address", "127.0.0.1:7233", "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        return [], []
    events = json.loads(out.stdout).get("events", [])
    names = {e["eventId"]: e["activityTaskScheduledEventAttributes"]["activityType"]["name"]
             for e in events if "activityTaskScheduledEventAttributes" in e}
    done, failed = [], []
    for e in events:
        for key, bucket in (("activityTaskCompletedEventAttributes", done), ("activityTaskFailedEventAttributes", failed)):
            if key in e:
                bucket.append(names.get(e[key]["scheduledEventId"], "?"))
    return done, failed


def worker_claude() -> list[str]:
    """Процессы `claude` внутри юнита bft-worker (ADR-22). Остальной сервер — не предмет этой приёмки."""
    cg = subprocess.run(["systemctl", "--user", "show", "bft-worker", "-p", "ControlGroup", "--value"],
                        capture_output=True, text=True).stdout.strip()
    try:
        pids = open(f"/sys/fs/cgroup{cg}/cgroup.procs").read().split()
    except OSError:
        return ["(нет cgroup bft-worker — worker не запущен?)"]
    out = []
    for pid in pids:
        try:
            if b"claude" in open(f"/proc/{pid}/cmdline", "rb").read():
                out.append(pid)
        except OSError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=120)  # #329: «за 120 с»
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    issue = api("POST", "/issues", {
        "title": "Smoke T1: выгрузка заказов в CSV для бухгалтерии",
        "body": ("Бухгалтер раз в неделю вручную копирует заказы из админки в Excel — уходит 3 часа и бывают ошибки. "
                 "Нужна кнопка «Экспорт в CSV» за выбранный период: номер заказа, дата, сумма, статус оплаты. "
                 "Демо: выбираем период за неделю, жмём экспорт, файл открывается в Excel без кракозябр.")},
                token=INTAKE)
    n = issue["number"]
    print(f"задача bft/requests#{n} создана")
    t0, wf, comment = time.time(), [], None
    done, failed = [], []
    while time.time() - t0 < args.timeout:
        time.sleep(5)
        wf = wf or workflows(n)
        done, failed = stages(n)
        comment = next((c for c in api("GET", f"/issues/{n}/comments") or [] if is_agent_comment(c.get("body") or "")), None)
        if failed or "post_error_label" in done or (comment and "intake_gate" in done):
            break
    claude = worker_claude()
    print("процесс в Temporal:", wf or "НЕТ")
    print("комментарий агента:", (comment["body"][:300].replace("\n", " ") if comment else "НЕТ"),
          f"({time.time() - t0:.0f} с)")
    print("стадии:", done, "| упали:", failed or "нет")
    print("claude в bft-worker:", "НЕТ" if not claude else f"ЕСТЬ {claude}")
    if not args.keep:
        api("PATCH", f"/issues/{n}", {"state": "closed"})
    # Стадия на GLM (intake_gate) отработала, ни одна активность не упала, ошибку контур не ставил.
    ok = (bool(wf) and "intake_gate" in done and comment is not None
          and not failed and "post_error_label" not in done and not claude)
    print("ИТОГ:", "OK" if ok else "ПРОВАЛ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
