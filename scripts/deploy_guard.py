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
чист и охватил всех); 1 — под ударом есть прогоны. `--warn-only` всегда
возвращает 0: им зовут сторож цели сборки (`make up`, `make up-local`), где
предупредить надо, а запрещать — не дело сборки.

Где Temporal наружу не опубликован (конфигурация full: `expose`, а не `ports`),
скрипт запускают ВНУТРИ контейнера — `make deploy-check-stack`. Тот же приём,
что у `scripts/diag.py`.
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

from shared.replay_report import failure_reason, format_failures  # noqa: E402
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


def replay_lines(failures: dict[str, list[str]], replayed: int,
                 skipped: dict[str, int] | None = None) -> tuple[list[str], bool]:
    """Отчёт реплея. Второй элемент — чист ли он.

    `skipped` — прогоны, чей тип воркфлоу этому инструменту недоступен. Они
    НЕ отказы: считать их поломкой значит объявлять аварийной безопасную
    выкладку, а оператор, один раз поверивший ложной тревоге, следующую
    настоящую уже не прочтёт.
    """
    skipped = skipped or {}
    tail = []
    if skipped:
        total_skipped = sum(skipped.values())
        listing = ", ".join(f"{name} ({count})" for name, count in sorted(skipped.items()))
        tail = ["", f"Не проверено: {total_skipped} — класс воркфлоу этому инструменту "
                    f"недоступен: {listing}.",
                "Это не поломка: такие прогоны реплеем не охвачены, и о них ничего не известно."]

    broken = sum(len(v) for v in failures.values())
    if broken == 0:
        return ([f"Реплей: {replayed} историй, расхождений нет — "
                 f"эти прогоны выкладку переживут.", *tail], True)

    lines = [f"⛔ Реплей: {replayed} историй, сломается {broken}.", ""]
    lines += format_failures(failures)
    lines += ["", "Выкладывать в таком виде — гарантированно остановить эти задачи.", *tail]
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
        # Потолок проверяется ДО добавления: иначе `--limit 0` — естественный
        # способ попросить счёт без выборки — всё равно тянул бы один прогон и
        # с `--replay` проигрывал бы его историю.
        if len(runs) >= limit:
            break
        runs.append(Run(execution.id, execution.run_id,
                        execution.workflow_type, execution.start_time))
    return total, runs


def replayable_classes() -> tuple[list[type], set[str]]:
    """Классы воркфлоу, которые этот инструмент умеет проигрывать, и их имена.

    `workflow_classes()` из `replay_histories` сканирует только `workflows.py`,
    а воркер регистрирует в ТОЙ ЖЕ очереди ещё и `ConsolidationWorkflow`
    (`worker/worker.py`), плюс воркфлоу соседних модулей в своих очередях того
    же namespace. Реплей без их классов объявил бы живой прогон консолидации
    сломанным — ложная тревога на безопасной выкладке.

    Соседние модули необязательны поштучно, как и в самом воркере: не собрался
    сосед — его тип просто не попадает в проверяемые, и прогоны на нём честно
    уедут в «не проверено», а не в «сломается».
    """
    from replay_histories import workflow_classes  # noqa: PLC0415

    classes = list(workflow_classes())
    try:
        from consolidation_workflow import ConsolidationWorkflow  # noqa: PLC0415
        classes.append(ConsolidationWorkflow)
    except ImportError:  # pragma: no cover — модуль лежит рядом в worker/
        pass
    for module in ("poh_delivery.integration", "poh_howtodemo.integration"):
        try:
            neighbour = __import__(module, fromlist=["WORKFLOWS"])
            classes.extend(getattr(neighbour, "WORKFLOWS", []))
        except Exception:  # noqa: BLE001 — несобравшийся сосед не отменяет проверку
            pass

    names = set()
    for cls in classes:
        defn = getattr(cls, "__temporal_workflow_definition", None)
        names.add(getattr(defn, "name", None) or cls.__name__)
    return classes, names


async def replay(client, runs: list[Run]
                 ) -> tuple[dict[str, list[str]], int, dict[str, int]]:
    """Проиграть истории живых прогонов против текущего кода воркфлоу.

    Третьим возвращает непроверенные прогоны по типам: их история не читалась
    и о них ничего не известно — это НЕ отказ (см. `replayable_classes`).

    Импорт кода воркера — внутри функции, а не в шапке модуля: быстрый режим
    обязан работать там, где зависимостей воркера нет (например, с машины
    оператора), и тянуть `instructor`/`openai` ради счёта прогонов незачем.
    """
    for path in (ROOT / "worker", ROOT / "scripts"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from temporalio.worker import Replayer  # noqa: PLC0415

    classes, known = replayable_classes()
    failures: dict[str, list[str]] = {}
    skipped: dict[str, int] = {}
    replayed = 0
    for run in runs:
        if run.workflow_type not in known:
            skipped[run.workflow_type] = skipped.get(run.workflow_type, 0) + 1
            continue
        handle = client.get_workflow_handle(run.workflow_id, run_id=run.run_id)
        try:
            history = await handle.fetch_history()
        except Exception as exc:  # noqa: BLE001 — недоступная история не повод падать целиком
            failures.setdefault(f"история не читается: {type(exc).__name__}",
                                []).append(run.workflow_id)
            continue
        replayed += 1
        try:
            # Новый `Replayer` на историю — как в `scripts/replay_histories.py`:
            # переиспользование одного между историями в контракте SDK не
            # обещано, а цена создания рядом с сетевым запросом за историю не
            # видна.
            await Replayer(workflows=classes).replay_workflow(history)
        except Exception as exc:  # noqa: BLE001 — интересен любой отказ реплея
            failures.setdefault(failure_reason(exc), []).append(run.workflow_id)
    return failures, replayed, skipped


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

    # Перехват вокруг работы с Temporal. Шире, чем одно подключение:
    # `Client.connect` спрашивает лишь системную информацию и проходит там, где
    # визибилити уже не отвечает (namespace без advanced visibility возвращает
    # Unimplemented на `count_workflows`), и без этого оператор получал бы голый
    # traceback вместо честного «проверка не выполнена».
    #
    # Но НЕ шире работы с Temporal: `replay()` первым делом импортирует код
    # воркера, и его отказ — не про кластер. Раньше он попадал сюда же, и
    # отсутствующий `instructor` докладывался как «Temporal недоступен
    # (ModuleNotFoundError)» — оператор шёл проверять связь с кластером вместо
    # своего окружения. У реплея свой перехват ниже.
    try:
        client = await connect_temporal()
        total, runs = await collect(client, args.limit)
    except Exception as exc:  # noqa: BLE001 — недоступный Temporal не должен ронять сборку
        print(f"Temporal недоступен ({type(exc).__name__}: {exc}) — проверка не выполнена.")
        print("Это НЕ значит, что незакрытых прогонов нет: их просто не у кого спросить.")
        return 0 if args.warn_only else 1

    replayed_result = None
    replay_failure = None
    if args.replay and runs:
        try:
            replayed_result = await replay(client, runs)
        except ImportError as exc:
            # Отдельно от прочего: быстрый режим намеренно работает без
            # зависимостей воркера (см. докстринг модуля), поэтому `--replay`
            # с машины оператора — ожидаемый способ на это наткнуться, и
            # назвать причину надо прямо.
            replay_failure = (f"нет зависимостей воркера ({type(exc).__name__}: {exc}). "
                              f"Реплей требует того же окружения, что и воркер; "
                              f"счёт прогонов выше от него не зависит и выполнен")
        except Exception as exc:  # noqa: BLE001 — отказ реплея не отменяет уже полученный счёт
            replay_failure = f"{type(exc).__name__}: {exc}"

    lines, ok = report_lines(total, runs, datetime.now(timezone.utc))

    if replay_failure is not None:
        lines += ["", f"⚠ Реплей не выполнен: {replay_failure}.",
                  "Кто именно сломается — неизвестно. Риск не снят."]
    elif replayed_result is not None:
        failures, replayed, skipped = replayed_result
        extra, clean = replay_lines(failures, replayed, skipped)
        lines += ["", *extra]
        # Чистый реплей снимает риск, только когда проверены ВСЕ прогоны: на
        # непокрытом остатке молчание реплея не значит ничего — «проверил
        # двести из пятисот, всё чисто» безопасностью не является.
        missing = total - len(runs)
        if missing > 0:
            # Причин у разрыва две, и обвинять одну — посылать оператора
            # поднимать потолок, который, возможно, ни при чём: выборка могла
            # упереться в `--limit`, а могла разойтись со счётом, если прогон
            # закрылся между двумя запросами.
            because = (f"потолок --limit {args.limit}" if len(runs) >= args.limit
                       else "прогоны закрылись между счётом и выборкой")
            lines.append(f"⚠ Проверено {len(runs)} из {total} — остальные не смотрели "
                         f"({because}). Риск не снят.")
        elif skipped:
            lines.append("⚠ Часть прогонов реплеем не охвачена (см. выше). Риск не снят.")
        elif clean:
            ok = True

    print("\n".join(lines))
    return 0 if (ok or args.warn_only) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
