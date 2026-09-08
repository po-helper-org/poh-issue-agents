"""Замер моделей z.ai: какая из них ещё справляется с работой контура.

Зачем скрипт, а не таблица цен провайдера: цена решает, какую модель хочется,
а годность — какую можно. Стадии контура не «болтают с моделью», они требуют
**структурированный ответ по схеме** через Instructor в режиме JSON (tool-calling
GLM отвергает, `worker/llm.py:28-30`). Модель, которая дешевле, но не держит
схему, не экономит ничего: Instructor ретраит, стадия падает, задача уходит
человеку — и токены потрачены дважды.

Поэтому здесь проверяется ровно то, что делает контур, теми же промптами и
теми же схемами:

* `intake_gate` — SPAM / VAGUE / SUFFICIENT на трёх заведомо разных задачах;
* `classify_issue` — категория и ответ;
* свободный ответ (`complete`) — путь стадий БФТ.

Порядок кандидатов задаёте вы, от дешёвой к дорогой: цена зависит от тарифа и
отсюда не видна. Скрипт говорит, какая из них РАБОТАЕТ и сколько токенов
съедает, а «самая дешёвая» — первая прошедшая в вашем порядке.

    python scripts/model_probe.py                       # список по умолчанию
    python scripts/model_probe.py glm-4.5-air glm-4.6   # свой порядок
    python scripts/model_probe.py --list                # что вообще даёт аккаунт
    python scripts/model_probe.py --claude glm-4.6      # ещё и путь `claude -p`

Нужны `ZAI_BASE_URL` и `ZAI_API_KEY` в окружении — те же, что у воркера.
Запускать удобнее всего изнутри контейнера воркера: там уже есть и промпты,
и `claude`.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "worker"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import llm  # noqa: E402
from activities import ClassificationExtraction, GateExtraction  # noqa: E402

# Порядок по умолчанию — от дешёвой к дорогой по прейскуранту z.ai на момент
# написания. Свой порядок передаётся аргументами: тариф у каждого свой.
DEFAULT_CANDIDATES = ["glm-4.5-air", "glm-4.6", "glm-5", "glm-5.2"]

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _prompt(name: str) -> str:
    """Промпт контура. Из `/app/prompts` в контейнере, из репозитория снаружи —
    иначе замер шёл бы не на том, чем работает стадия."""
    for path in (pathlib.Path("/app/prompts") / name, REPO_ROOT / "prompts" / name):
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise SystemExit(f"промпт {name} не найден ни в /app/prompts, ни в {REPO_ROOT}/prompts")


# Три задачи с известным ответом. Не «примерно похожие», а именно те исходы,
# по которым контур ветвится: закрыть, спросить, пропустить дальше. Модель,
# путающая их, дешевле не работает — она работает неправильно.
GATE_CASES = [
    ("спам",
     "Заголовок: CHEAP WATCHES BUY NOW\n\nОписание:\nvisit http://spam.example для скидок 90%",
     "SPAM"),
    ("расплывчато",
     "Заголовок: не работает\n\nОписание:\nпочините пожалуйста",
     "VAGUE"),
    ("достаточно",
     "Заголовок: Корзина теряет промокод при смене количества\n\n"
     "Описание:\nШаги: 1) добавить товар, 2) применить промокод SALE10, "
     "3) изменить количество на 2. Ожидается: скидка сохраняется. "
     "Фактически: промокод снимается, итог считается без скидки. "
     "Воспроизводится в Chrome 141 и Firefox 133, на демо-стенде.",
     "SUFFICIENT"),
]

# Форма сообщения — как у `classify_issue`, вместе с блоком известного
# функционала: без него замер шёл бы на входе, которого стадия не видит.
CLASSIFY_CASE = (
    "Заголовок: Добавить экспорт отчёта в CSV\n\n"
    "Описание:\nНужна выгрузка таблицы заказов в CSV с фильтрами, "
    "которые применены на экране.\n\n"
    "Известный функционал:\n(пусто)"
)


def _usage(obj) -> tuple[int, int]:
    """Токены запроса и ответа. Instructor прячет сырой ответ в
    `_raw_response`; у прямого вызова usage лежит на самом объекте."""
    raw = getattr(obj, "_raw_response", obj)
    usage = getattr(raw, "usage", None)
    if usage is None:
        return 0, 0
    return (getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0)


def probe(model: str) -> dict:
    """Один кандидат: три ворот, классификация, свободный ответ."""
    out = {"model": model, "gate": [], "classify": None, "complete": None,
           "tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "error": ""}
    started = time.monotonic()
    gate_prompt = _prompt("system_intake_gate.md")

    try:
        for name, message, expected in GATE_CASES:
            got = llm.extract(gate_prompt, message, GateExtraction, model=model)
            tin, tout = _usage(got)
            out["tokens_in"] += tin
            out["tokens_out"] += tout
            out["gate"].append((name, got.status, got.status == expected))

        got = llm.extract(_prompt("system_advisor.md"), CLASSIFY_CASE,
                          ClassificationExtraction, model=model)
        tin, tout = _usage(got)
        out["tokens_in"] += tin
        out["tokens_out"] += tout
        out["classify"] = got.category

        text = llm.complete("Отвечай одной короткой строкой по-русски.",
                            "Назови три признака хорошего баг-репорта.",
                            model=model, max_tokens=200)
        out["complete"] = (text or "").strip()[:60]
    except Exception as exc:                                  # noqa: BLE001
        # Любой отказ — исход замера, а не сбой скрипта: недоступная на тарифе
        # модель, отвергнутая схема и таймаут одинаково означают «не годится».
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]

    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def probe_claude(model: str, timeout: int = 120) -> str:
    """Путь `claude -p` — Anthropic-совместимый эндпоинт того же z.ai.

    Отдельным замером, потому что это другой протокол и другая переменная:
    модель здесь задаёт `ANTHROPIC_MODEL`, и сегодня её никто не задаёт —
    выбирает сам провайдер.
    """
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ZAI_API_KEY", "")
    if not base:
        zai = os.environ.get("ZAI_BASE_URL", "")
        if zai:
            from urllib.parse import urlsplit
            p = urlsplit(zai)
            base = f"{p.scheme}://{p.netloc}/api/anthropic"
    if not base or not token:
        return "нет кредов"
    try:
        res = subprocess.run(
            ["claude", "-p", "Ответь одним словом: готов", "--permission-mode", "acceptEdits"],
            capture_output=True, text=True, timeout=timeout, check=False,
            env={**os.environ, "ANTHROPIC_BASE_URL": base,
                 "ANTHROPIC_AUTH_TOKEN": token, "ANTHROPIC_MODEL": model},
        )
    except FileNotFoundError:
        return "claude не установлен"
    except subprocess.TimeoutExpired:
        return f"таймаут {timeout}с"
    if res.returncode != 0:
        return f"exit {res.returncode}: {(res.stderr or res.stdout).strip()[:80]}"
    return (res.stdout or "").strip()[:40] or "(пустой ответ)"


def list_models() -> None:
    """Что аккаунт действительно отдаёт. Список моделей провайдера и список,
    доступный тарифу, — разные вещи, и второй виден только отсюда."""
    base = os.environ["ZAI_BASE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/models",
        headers={"Authorization": f"Bearer {os.environ['ZAI_API_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"эндпоинт /models ответил {exc.code}: {exc.read()[:200].decode(errors='replace')}")
        return
    except Exception as exc:                                  # noqa: BLE001
        print(f"эндпоинт /models недоступен: {type(exc).__name__}: {exc}")
        return
    for item in data.get("data", data if isinstance(data, list) else []):
        print("   ", item.get("id", item))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", nargs="*", default=DEFAULT_CANDIDATES,
                    help="модели от дешёвой к дорогой (порядок ваш — цена зависит от тарифа)")
    ap.add_argument("--list", action="store_true", help="показать модели аккаунта и выйти")
    ap.add_argument("--claude", action="store_true", help="ещё и путь `claude -p`")
    args = ap.parse_args()

    for var in ("ZAI_BASE_URL", "ZAI_API_KEY"):
        if not os.environ.get(var):
            print(f"нет {var} — замер невозможен: это те же переменные, что у воркера")
            return 2

    if args.list:
        print("Модели, доступные аккаунту:")
        list_models()
        return 0

    rows = []
    for model in args.candidates:
        print(f"замеряю {model} …", flush=True)
        row = probe(model)
        if args.claude:
            row["claude"] = probe_claude(model)
        rows.append(row)

    print()
    header = f"{'модель':<14} {'ворота':<22} {'классиф.':<12} {'ответ':<7} {'токены':<14} {'сек':>5}"
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["error"]:
            print(f"{r['model']:<14} ОТКАЗ: {r['error'][:70]}")
            continue
        gates = " ".join(("✓" if ok else f"✗{got}") for _, got, ok in r["gate"])
        ok_all = all(ok for _, _, ok in r["gate"]) and bool(r["complete"])
        print(f"{r['model']:<14} {gates:<22} {str(r['classify']):<12} "
              f"{'есть' if r['complete'] else 'нет':<7} "
              f"{r['tokens_in']}/{r['tokens_out']:<8} {r['seconds']:>5}"
              f"{'' if ok_all else '   ← не держит схему или ветвление'}")
        if "claude" in r:
            print(f"{'':<14} claude -p: {r['claude']}")

    passed = [r for r in rows
              if not r["error"] and all(ok for _, _, ok in r["gate"]) and r["complete"]]
    print()
    if passed:
        best = passed[0]
        print(f"Самая дешёвая из прошедших (в заданном порядке): {best['model']} — "
              f"{best['tokens_in'] + best['tokens_out']} токенов на замер, {best['seconds']} с")
    else:
        print("Ни один кандидат не прошёл: контур на них работать не будет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
