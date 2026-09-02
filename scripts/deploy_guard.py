"""Сторож выкладки: сколько незакрытых прогонов попадёт под пересборку.

Зачем. `IssueLifecycle` — долгоживущий воркфлоу: один на задачу, живёт неделями,
подолгу стоит на ожидании сигнала. Любая выкладка, меняющая ПОСЛЕДОВАТЕЛЬНОСТЬ
активностей, попадает в незакрытые прогоны: они переигрываются против нового
кода, порядок расходится с записанной историей, и Temporal отказывается
продолжать. Само это не лечится — ни ретраем, ни правкой вперёд (#263, живой
случай 25.08: 120 прогонов в Running, старейшие с 19 августа).

Опасность до сих пор была невидимой: в `docs/DEPLOY-DOKPLOY.md` о ней не
сказано, предупреждения при выкладке нет, проверки перед пересборкой нет. Про
неё знали только те, кто уже обжёгся. Одна цифра перед пересборкой превращает
невидимый риск в осознанное решение — этим скрипт и занят.

Два режима:

    python scripts/deploy_guard.py              # быстрый: счёт и старейшие
    python scripts/deploy_guard.py --replay     # плюс реплей их историй

Быстрый режим — одна цифра и список старейших прогонов, доли секунды, из
зависимостей только клиент Temporal. Он отвечает на вопрос «сколько под ударом».

`--replay` отвечает на вопрос «кто именно сломается»: тянет истории живых
прогонов прямо из Temporal и проигрывает их против текущего кода воркфлоу.
Это тот же реплей, что и в `scripts/replay_histories.py` (классы воркфлоу
берутся оттуда же), но без снятия корпуса на стенде через ssh + tar — истории
приезжают по тому же соединению, по которому считались прогоны. Режим тяжелее:
импортирует код воркера и делает запрос на каждый прогон.

Коды возврата: 0 — выкладка безопасна (незакрытых прогонов нет либо реплей
чист); 1 — под ударом есть прогоны. `--warn-only` всегда возвращает 0: им
пользуются цели `make up`/`up-full`, где предупредить надо, а запрещать —
не дело сборки.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.temporal_client import connect_temporal  # noqa: E402

# Незакрытые прогоны. Именно `Running`: `ContinuedAsNew` и прочие терминальные
# статусы историю уже закрыли, и новый код им не грозит.
RUNNING_QUERY = "ExecutionStatus = 'Running'"

# Сколько старейших показать. Список нужен, чтобы цифра была предметной («вот
# эти, с 19 августа»), а не абстрактной; печатать все сто двадцать смысла нет.
OLDEST_SHOWN = 10


class Run(NamedTuple):
    """Незакрытый прогон — ровно то, что нужно для отчёта и реплея."""
    workflow_id: str
    run_id: str
    workflow_type: str
    started: Optional[datetime]

    def age_days(self, now: datetime) -> Optional[float]:
        if self.started is None:
            return None
        return (now - self.started).total_seconds() / 86400


def _age(run: Run, now: datetime) -> str:
    days = run.age_days(now)
    return "возраст неизвестен" if days is None else f"{days:.1f} сут"


def report_lines(count: int, runs: list[Run], now: datetime) -> tuple[list[str], bool]:
    """Отчёт быстрого режима. Второй элемент — безопасна ли выкладка.

    Чистая функция: ни сети, ни времени изнутри — `now` приходит аргументом,
    иначе тест на возраст прогонов зависел бы от даты запуска.
    """
    if count == 0:
        return (["Незакрытых прогонов нет — выкладка никого не заденет."], True)

    lines = [
        f"⚠ Незакрытых прогонов в Running: {count}",
        "",
        "Выкладка, меняющая ПОСЛЕДОВАТЕЛЬНОСТЬ активностей, вид ожидания или",
        "длительность таймера, разойдётся с их историями, и Temporal откажется",
        "их продолжать. Само это не лечится: ни ретраем, ни правкой вперёд.",
        "",
        "Изменил решение воркфлоу — заведи `workflow.patched(...)` ДО выкладки",
        "(AGENTS.md, правило 1). Правка тела активности, её ретраев и меток",
        "безопасна: их в истории нет.",
    ]
    if runs:
        shown = sorted(runs, key=lambda r: (r.started is None,
                                            r.started or datetime.max.replace(tzinfo=timezone.utc)))
        lines += ["", f"Старейшие из выборки ({min(len(shown), OLDEST_SHOWN)} из {len(shown)}):"]
        for run in shown[:OLDEST_SHOWN]:
            lines.append(f"  {_age(run, now):>18}  {run.workflow_type:<20} {run.workflow_id}")
    lines += ["", "Проверить, кто именно сломается: --replay"]
    return (lines, False)


def failure_reason(exc: BaseException, marker: str) -> str:
    """Во что группировать отказ реплея.

    У расхождения берём хвост после маркера: в начале текста стоит общая для
    всех обёртка, а различает причины именно хвост («Activity machine does not
    handle this event» против «Timer machine…»). Обрезаем: полный текст несёт
    идентификаторы прогона, и с ними каждая строка станет уникальной — то есть
    группировка выродится в список.

    Отказ не про недетерминизм (история не той версии, класс воркфлоу не
    зарегистрирован) группируем по типу исключения: текста, который стоило бы
    показывать, у него обычно нет.
    """
    text = str(exc)
    return text.split(marker)[-1][:160] if marker in text else type(exc).__name__


def replay_lines(failures: dict[str, list[str]], replayed: int) -> tuple[list[str], bool]:
    """Отчёт реплея. Второй элемент — чист ли он.

    Группировка по тексту расхождения, а не по прогону: одна выкладка ломает
    все прогоны, дошедшие до изменённого места, и сотня строк об одной причине
    прячет вторую причину, если та есть.
    """
    broken = sum(len(v) for v in failures.values())
    if broken == 0:
        return ([f"Реплей: {replayed} историй, расхождений нет — эти прогоны выкладку переживут."],
                True)

    lines = [f"⛔ Реплей: {replayed} историй, сломается {broken}.", ""]
    for reason, ids in sorted(failures.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {len(ids):3d}  {reason}")
        for workflow_id in ids[:5]:
            lines.append(f"         {workflow_id}")
        if len(ids) > 5:
            lines.append(f"         … и ещё {len(ids) - 5}")
    lines += ["", "Выкладывать в таком виде — гарантированно остановить эти задачи."]
    return (lines, False)


async def collect(client, limit: int) -> tuple[int, list[Run]]:
    """Счёт незакрытых прогонов и выборка из них не больше `limit`.

    Счёт отдельным запросом, а не длиной выборки: `count_workflows` отвечает
    одним вызовом по всему namespace, а перечисление ограничено `limit` и на
    ста двадцати прогонах давало бы заниженную цифру там, где важна именно она.
    """
    total = (await client.count_workflows(RUNNING_QUERY)).count
    runs: list[Run] = []
    async for execution in client.list_workflows(RUNNING_QUERY):
        runs.append(Run(execution.id, execution.run_id,
                        execution.workflow_type, execution.start_time))
        if len(runs) >= limit:
            break
    return total, runs


async def replay(client, runs: list[Run]) -> tuple[dict[str, list[str]], int]:
    """Проиграть истории живых прогонов против текущего кода воркфлоу.

    Импорт кода воркера — внутри функции, а не в шапке модуля: быстрый режим
    обязан работать там, где зависимостей воркера нет (например, с машины
    оператора), и тянуть `instructor`/`openai` ради счёта прогонов незачем.
    """
    for path in (ROOT / "worker", ROOT / "scripts"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from temporalio.worker import Replayer  # noqa: PLC0415

    from replay_histories import MARKER, workflow_classes  # noqa: PLC0415

    classes = workflow_classes()
    failures: dict[str, list[str]] = {}
    replayed = 0
    for run in runs:
        handle = client.get_workflow_handle(run.workflow_id, run_id=run.run_id)
        try:
            history = await handle.fetch_history()
        except Exception as exc:  # noqa: BLE001 — недоступная история не повод падать целиком
            failures.setdefault(f"история не читается: {type(exc).__name__}", []).append(run.workflow_id)
            continue
        replayed += 1
        try:
            # Новый `Replayer` на историю — как в `scripts/replay_histories.py`:
            # переиспользование одного между историями в контракте SDK не
            # обещано, а цена создания рядом с сетевым запросом за историю не
            # видна.
            await Replayer(workflows=classes).replay_workflow(history)
        except Exception as exc:  # noqa: BLE001 — интересен любой отказ реплея
            failures.setdefault(failure_reason(exc, MARKER), []).append(run.workflow_id)
    return failures, replayed


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Сколько незакрытых прогонов попадёт под пересборку воркера")
    parser.add_argument("--replay", action="store_true",
                        help="проиграть истории живых прогонов против текущего кода")
    parser.add_argument("--limit", type=int, default=200,
                        help="потолок выборки прогонов (по умолчанию 200)")
    parser.add_argument("--warn-only", action="store_true",
                        help="всегда возвращать 0 — предупредить, но не блокировать")
    args = parser.parse_args(argv)

    try:
        client = await connect_temporal()
    except Exception as exc:  # noqa: BLE001 — недоступный Temporal не должен ронять сборку
        print(f"Temporal недоступен ({type(exc).__name__}: {exc}) — проверка не выполнена.")
        print("Это НЕ значит, что незакрытых прогонов нет: их просто не у кого спросить.")
        return 0 if args.warn_only else 1

    total, runs = await collect(client, args.limit)
    lines, ok = report_lines(total, runs, datetime.now(timezone.utc))

    if args.replay and runs:
        failures, replayed = await replay(client, runs)
        extra, clean = replay_lines(failures, replayed)
        lines += ["", *extra]
        # Чистый реплей снимает риск только когда проверены ВСЕ прогоны. Выборка
        # ограничена `--limit`, и на непокрытом остатке молчание реплея ничего не
        # значит: «проверил двести из пятисот, всё чисто» безопасностью не является.
        if len(runs) < total:
            lines.append(f"⚠ Проверено {len(runs)} из {total} — остальные не смотрели "
                         f"(потолок --limit). Риск не снят.")
        elif clean:
            ok = True

    print("\n".join(lines))
    return 0 if (ok or args.warn_only) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
