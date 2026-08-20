"""БФТ в контуре Issue: режимы, ветка артефактов, стадии, сборка комментария.

Модуль намеренно чистый — ни сети, ни Temporal, ни GitHub, как `lifecycle.py` и
`estimation.py`. Формат комментария и перечень стадий проверяются напрямую, без
прогона воркфлоу и без обращения к модели.

Почему БФТ, а не прежний advisor-ответ
--------------------------------------
Классификация отвечала свободным текстом «Ситуация / Ограничение / Варианты
решения / Оценка сложности». В нём нет сценария приёмки, нет границ и нет
списка открытых вопросов с владельцами, зато есть «варианты решения» — то есть
проектирование вместо постановки. Формат `/bft-fast` (`po-helper-org/poh-bft-writer`)
даёт ровно недостающее: `Цель` (WHY вперёд) → `How to demo` → `Открытые вопросы`
→ `Границы` → `Документация` плюс таблицу требований на цитатах.

Два режима, две цены
--------------------
`fast` — один вызов модели по тексту Issue и треду: секунды, комментарий в Issue.
`deep` — канонический пайплайн `bft-writer` внутри клона репозитория: минуты,
артефакты в ветке. Первый идёт сам на триаже, второй — только по явной команде:
дорогую стадию запускает человек, а не догадка агента.
"""

import json
import os
import re

FAST = "fast"
DEEP = "deep"
MODES = (FAST, DEEP)

# Ветка артефактов глубокого прогона. Отдельная от `research/issue-N` (цепочка
# FNR): у документов разные авторы и разная судьба, и складывать их в одну ветку
# значило бы, что повторный прогон одного затирает историю другого.
BRANCH_PREFIX = "bft-research"

# Корень документации bft-writer внутри воркспейса — дефолт `docs_path` из
# `bft-config.md`. Задан здесь явно, чтобы публикация знала, что забирать, не
# угадывая по маске.
DOCS_ROOT = ".bft/documentation"


def epic_slug(issue_number: int) -> str:
    """Имя эпика для пайплайна — от НОМЕРА Issue, а не от заголовка.

    Заголовок редактируют, и slug из него менял бы каталог артефактов между
    прогонами: второй `/bft-deep` писал бы рядом с первым, а не поверх, и
    «документ с дополнительными требованиями» превращался бы во второй документ.
    """
    return f"issue-{issue_number}"


def branch(issue_number: int) -> str:
    return f"{BRANCH_PREFIX}/{epic_slug(issue_number)}"


def epic_dir(issue_number: int) -> str:
    return f"{DOCS_ROOT}/{epic_slug(issue_number)}"


def artefacts_dir(issue_number: int) -> str:
    return f"{epic_dir(issue_number)}/artefacts"


def statement_path(issue_number: int) -> str:
    """Постановка от заказчика — файл, который пайплайн читает вместо JIRA.

    В контуре Issue трекера нет: `/bft-context-gen` штатно тянет эпик из JIRA, а
    здесь его роль играет сам Issue вместе с тредом и уточнениями из команды.
    Путь фиксирован, потому что на него ссылается адаптированная команда
    (`.claude/commands/bft-context-gen.md`, раздел «Постановка без JIRA»).
    """
    return f"{artefacts_dir(issue_number)}/po-statement.md"


def document_path(issue_number: int) -> str:
    """Главный документ БФТ — то, что открывает человек."""
    return f"{epic_dir(issue_number)}/{epic_slug(issue_number)}.md"


# --- Стадии глубокого прогона ---
#
# Канонический пайплайн bft-writer, разложенный по стадиям: каждая — свой
# `claude -p` и свой шаг Event History со своим таймингом. Одной активностью на
# весь пайплайн он был бы чёрным ящиком на десятки минут — ровно тем, от чего
# ушла цепочка FNR (#26).
DEEP_STAGE_NAMES: tuple[str, ...] = (
    "index", "context", "problem", "concept", "debate", "draft", "validate",
)


def deep_stages(issue_number: int) -> list[tuple[str, str, str | None, str | None]]:
    """(имя, промпт, ожидаемый артефакт, требуемый вход) для каждой стадии.

    Промпт — `/<команда> <аргументы>` и ничего больше: `claude -p` разворачивает
    команду только тогда, когда она стоит первой, а произвольный текст после
    аргументов команда прочитает как ещё один аргумент.

    `index` и `debate` ожидаемого файла не имеют: первый строит каталог
    `.bft/index/`, второй дописывает вердикт в конец `concept.md`.
    """
    slug = epic_slug(issue_number)
    pack = f"{artefacts_dir(issue_number)}/bft-context-pack.md"
    problem = f"{artefacts_dir(issue_number)}/problem.md"
    concept = f"{artefacts_dir(issue_number)}/concept.md"
    document = document_path(issue_number)
    validation = f"{artefacts_dir(issue_number)}/validation.md"
    return [
        ("index", "/bft-index", None, None),
        # Второй аргумент `/bft-context-gen` — ключ эпика в трекере. Трекера нет,
        # и подставлять туда выдуманный ключ хуже, чем назвать вещи своими
        # именами: команда увидит тот же slug и не станет искать несуществующий
        # проект.
        ("context", f"/bft-context-gen {slug} {slug}", pack, None),
        ("problem", f"/bft-problem {slug}", problem, pack),
        ("concept", f"/bft-concept {slug}", concept, problem),
        ("debate", f"/bft-debate {slug}", None, concept),
        ("draft", f"/bft-draft {slug}", document, concept),
        ("validate", f"/bft-validate {slug}", validation, document),
    ]


def deep_stage(name: str, issue_number: int) -> tuple[str, str | None, str | None]:
    """(промпт, ожидаемый артефакт, требуемый вход) стадии по имени."""
    for stage_name, prompt, expected, requires in deep_stages(issue_number):
        if stage_name == name:
            return prompt, expected, requires
    raise ValueError(f"неизвестная стадия БФТ: {name}")


# --- Сборка комментария fast-режима ---

# Приписка под письмом. Дословно из постановки задачи: человек должен видеть,
# каким одним действием запускается глубокая проработка и на что ответить.
DEEP_HINT = (
    "Если задача касается больших изменений — запустите команду `/bft-deep` "
    "и ответьте на ряд этих уточняющих вопросов:"
)

DEEP_HINT_NO_QUESTIONS = (
    "Если задача касается больших изменений — запустите команду `/bft-deep` "
    "(можно с уточнениями в том же комментарии): она соберёт полный БФТ по "
    "канону и приложит артефакты веткой."
)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"* {item.strip()}" for item in items if item and item.strip())


def _numbered(items: list[str]) -> str:
    kept = [item.strip() for item in items if item and item.strip()]
    return "\n".join(f"{i}. {item}" for i, item in enumerate(kept, 1))


def _table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """Markdown-таблица из строк-словарей. Пустой список строк → пустая строка.

    В `/bft-fast` требования уезжают вложением csv. В Issue вложений нет, и
    таблица — единственная форма, в которой они и читаются глазами, и остаются
    машиночитаемыми (GitHub рендерит markdown-таблицы).
    """
    if not rows:
        return ""
    head = "| " + " | ".join(title for _, title in columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = []
    for row in rows:
        cells = [str(row.get(key, "") or "").replace("|", "\\|").replace("\n", " ")
                 for key, _ in columns]
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *body])


def render_letter(
    *,
    goal: str,
    how_to_demo: list[str],
    open_questions: list[str],
    scope: str,
    documentation: list[str],
    requirements: list[dict],
    personas: list[dict],
    revision: int = 1,
) -> str:
    """Комментарий fast-режима: письмо `/bft-fast` плюс приписка про `/bft-deep`.

    Порядок блоков письма зафиксирован скиллом (`letter_format.md`) и здесь не
    меняется: `Цель` → `How to demo` → `Открытые вопросы` → `Границы` →
    `Документация`. Таблицы требований и персон идут после письма — в оригинале
    это csv-вложение, которого в Issue быть не может.

    Пустой блок не выводится вовсе: пустой заголовок читается как «мы про это
    подумали и там ничего нет», а на деле означает «данных не было».
    """
    parts: list[str] = ["## 📋 БФТ (быстрый проход)"]
    if revision > 1:
        parts.append(f"_Редакция {revision} — с учётом замечаний из обсуждения._")

    parts.append(f"**Цель:** {goal.strip()}")

    demo = _numbered(how_to_demo)
    if demo:
        parts.append(f"**How to demo:**\n{demo}")

    questions = [q.strip() for q in open_questions if q and q.strip()]
    if questions:
        parts.append(f"**Открытые вопросы:**\n{_bullets(questions)}")

    if scope and scope.strip():
        parts.append(f"**Границы:** {scope.strip()}")

    docs = _bullets(documentation)
    if docs:
        parts.append(f"**Документация:**\n{docs}")

    table = _table(requirements, [
        ("id", "ID"),
        ("as_is", "Сейчас (AS IS)"),
        ("to_be", "После (TO BE)"),
        ("related", "Связанные"),
        ("source", "Источник"),
    ])
    if table:
        parts.append(f"**Ключевые требования:**\n\n{table}")

    people = _table(personas, [("name", "Кто"), ("role", "Роль"), ("unit", "Департамент")])
    if people:
        parts.append(f"**Стейкхолдеры:**\n\n{people}")

    parts.append("---")
    if questions:
        parts.append(f"{DEEP_HINT}\n\n{_numbered(questions)}")
    else:
        parts.append(DEEP_HINT_NO_QUESTIONS)
    parts.append(
        "Не согласны с формулировкой — вызовите `/bft` с замечаниями в том же "
        "комментарии, и БФТ пересоберётся с их учётом."
    )
    return "\n\n".join(parts)


def render_statement(
    *,
    title: str,
    body: str,
    thread: str,
    instructions: str,
    issue_number: int,
    repo: str,
) -> str:
    """Постановка для глубокого прогона — единственный вход задачи в пайплайн.

    Собирается ЗДЕСЬ и кладётся в воркспейс файлом, а не растворяется в промпте:
    то, что уехало в работу, должно быть видно дословно и лежать в ветке рядом с
    результатом. Иначе на разборе «почему БФТ вышел не про то» предъявить нечего.
    """
    parts = [
        f"# Постановка: {repo}#{issue_number} — {title}",
        "",
        "> Источник задачи — Issue на GitHub. Трекер (JIRA) в этом контуре не "
        "подключён: этот файл заменяет эпик трекера и является основным входом "
        "пайплайна БФТ.",
        "",
        "## Запрос",
        "",
        body.strip() or "(тело Issue пустое)",
    ]
    if instructions.strip():
        parts += [
            "",
            "## Уточнения заказчика к этому прогону",
            "",
            "> Пришли вместе с командой `/bft-deep`. Имеют приоритет над более "
            "ранними формулировками: это последнее слово заказчика.",
            "",
            instructions.strip(),
        ]
    if thread.strip():
        parts += ["", "## Обсуждение Issue", "", thread.strip()]
    return "\n".join(parts)


def render_config() -> str:
    """`bft-config.md` для клона — конфигурация пайплайна на этот прогон.

    Пишется всегда, поверх того, что может лежать в целевом репозитории. Иначе
    чужой `docs_path` увёл бы артефакты туда, где публикация их не ищет, и
    прогон завершился бы «пайплайн не произвёл ни одного артефакта» при полной
    папке документов.

    Трекер и Confluence пусты намеренно: в контуре Issue их нет, а гейт
    «сухой прогон → явное ок PO» в автономном прогоне пройти некому.
    """
    return (
        "# bft-config (сгенерирован Issue-агентом на этот прогон)\n\n"
        "## tracker_projects\n\n"
        "(пусто — трекера в контуре Issue нет; постановка приходит файлом "
        "`artefacts/po-statement.md`)\n\n"
        "## wiki_space\n\n"
        "(пусто — публикация в Confluence выключена: подтвердить сухой прогон "
        "в автономном прогоне некому. Артефакты уезжают веткой в GitHub.)\n\n"
        "## docs_path\n\n"
        f"{DOCS_ROOT}\n"
    )


def render_deep_summary(repo: str, issue_number: int, files: list[str]) -> str:
    """Сводка глубокого прогона: где лежит документ и что ещё появилось."""
    br = branch(issue_number)
    base = f"https://github.com/{repo}/blob/{br}"
    document = document_path(issue_number)
    links = "\n".join(
        f"- [`{path.rsplit('/', 1)[-1]}`]({base}/{path})" for path in sorted(files)
    )
    head = (
        "## 📚 БФТ: глубокая проработка\n\n"
        f"Прогнал канонический пайплайн bft-writer. Артефакты — в ветке `{br}`:\n\n"
        f"{links}\n\n"
    )
    if document in files:
        head += (
            f"Начни с [`{epic_slug(issue_number)}.md`]({base}/{document}) — это сам "
            "БФТ: бизнес-требования, продуктовые и функциональные требования с "
            "якорями на код и открытые вопросы там, где данных не хватило.\n\n"
        )
    return head + (
        "Не хватает требований или изменилась постановка — вызови `/bft-deep` с "
        "уточнением: документ дополнится, уже принятые требования не "
        "перенумеруются."
    )


# --- Прямые стадии: два вызова модели вместо агента ---
#
# `claude -p` стоит 356 МБ RSS на стадию — дороже, чем весь контейнер воркера, и
# на тесном стенде это уже мешает. Но агентность нужна не всем стадиям: `index`
# и `context` исследуют репозиторий, а `draft` получает готовый вход и пишет
# один файл. Такую стадию можно выполнить прямыми вызовами модели из процесса
# воркера — без второго процесса вовсе.
#
# Разбор на ДВА вызова не косметика. Одним ответом модель сворачивала каскад
# (5 функциональных требований вместо 10) и недобирала якоря: собрать структуру
# и оформить документ — разные задачи, и вторая вытесняет первую. Между вызовами
# появляется место для программной проверки, ради которого всё и затевалось.
#
# Ориентиры полноты выведены из эталонного прогона `claude -p` по демо-задаче.
# Это НИЖНЯЯ граница здравого смысла, а не догма: настраивается переменными,
# и по-настоящему полноту задаёт покрытие источников (см. #78).
CASCADE_FLOOR: dict[str, int] = {"БТ": 4, "ПТ": 5, "ИТ": 6, "ФТ": 10, "НФТ": 4}
ANCHOR_FLOOR = 24

CASCADE_SCHEMA = """{
  "requirements": [
    {"id": "БТ-1", "type": "БТ", "title": "…", "body": "…",
     "related": ["ПТ-1", "ФТ-2"], "anchor": "po-statement.md:7"}
  ],
  "anchors": [
    {"fact": "…", "source": "src/pricing.mjs:5-9", "rank": "R1", "kind": "Код"}
  ]
}"""


def direct_stages() -> set[str]:
    """Стадии, которые идут прямыми вызовами вместо `claude -p`.

    Пусто (умолчание) — прежнее поведение целиком: ни одна стадия не меняет
    исполнителя. Флаг перечисляет стадии поимённо, чтобы переключать их по одной
    и сравнивать результат с агентом на той же задаче.
    """
    raw = os.environ.get("BFT_DIRECT_STAGES", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def parse_cascade(text: str) -> dict:
    """JSON каскада из ответа модели.

    Модель охотно добавляет ```-обрамление и пояснения до и после — берём срез
    от первой скобки до последней, а не доверяем формату ответа.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"в ответе нет JSON каскада: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def cascade_gaps(cascade: dict, line_counts: dict[str, int]) -> list[str]:
    """Чего каскаду не хватает — претензиями на языке добора.

    `line_counts` — сколько строк в каждом файле исходников. Якорь ранга R1
    обязан указывать на СУЩЕСТВУЮЩУЮ строку существующего файла: выдуманная
    ссылка выглядит в документе ровно так же убедительно, как настоящая, и
    проверить её может только код (#78).

    Функция чистая: файловую систему читает вызывающий, сюда приходят уже
    посчитанные длины.
    """
    gaps: list[str] = []

    have: dict[str, int] = {}
    for req in cascade.get("requirements") or []:
        kind = req.get("type")
        have[kind] = have.get(kind, 0) + 1
    for kind, floor in CASCADE_FLOOR.items():
        if have.get(kind, 0) < floor:
            gaps.append(f"{kind}: {have.get(kind, 0)} из {floor} — "
                        f"добавь {floor - have.get(kind, 0)} шт.")

    anchors = cascade.get("anchors") or []
    if len(anchors) < ANCHOR_FLOOR:
        gaps.append(f"якорей {len(anchors)} из {ANCHOR_FLOOR} — "
                    f"добавь {ANCHOR_FLOOR - len(anchors)} шт.")

    for anchor in anchors:
        if anchor.get("rank") != "R1":
            continue  # R2/R3 ссылаются на постановку и решения, не на строки кода
        source = str(anchor.get("source", ""))
        match = re.match(r"([\w./-]+):(\d+)", source)
        if not match:
            gaps.append(f"якорь R1 «{source}» без номера строки — укажи файл:строки")
            continue
        path, line = match.group(1), int(match.group(2))
        if path not in line_counts:
            gaps.append(f"якорь R1 ссылается на {path} — такого файла во входе нет")
        elif line > line_counts[path]:
            gaps.append(f"якорь R1 «{source}»: в файле {line_counts[path]} строк, "
                        f"строки {line} не существует")
    return gaps


# --- Частичный прогон: что успели и что осталось ---
#
# Прогон срывается не только от ошибок в коде: провайдер отдаёт 524, кончается
# лимит запросов, стенд передеплоивают посреди работы. Раньше это стоило всего
# прогона целиком — артефакты жили в эфемерном каталоге, а `cleanup` в `finally`
# стирал его на любом исходе. Двадцать минут работы модели уходили в никуда, и
# повтор начинался с нуля.
#
# Теперь сделанное публикуется в ту же ветку `bft-research/issue-N`, из которой
# следующий `/bft-deep` поднимает прошлый прогон: стадия с уже готовым
# артефактом пропускается, работа продолжается с места обрыва.


def stage_artifacts(issue_number: int) -> dict[str, str]:
    """Стадия → путь её артефакта. Только стадии, у которых он есть.

    `index` строит каталог `.bft/index/`, `debate` дописывает вердикт в конец
    `concept.md` — по файлу их «сделанность» не определить, поэтому в карте их
    нет и пропускать их нельзя.
    """
    return {name: expected
            for name, _prompt, expected, _requires in deep_stages(issue_number)
            if expected}


def done_stages(issue_number: int, exists) -> list[str]:
    """Стадии, чей артефакт уже лежит в рабочем каталоге.

    `exists(path) -> bool` — проверка наличия, файловую систему трогает
    вызывающий. Пустой файл за сделанную стадию не считаем: артефакт нулевого
    размера означает оборванную запись, а не готовую работу.
    """
    return [name for name, path in stage_artifacts(issue_number).items() if exists(path)]


def remaining_stages(issue_number: int, done: list[str]) -> list[str]:
    """Стадии, которые осталось прогнать — в каноническом порядке."""
    return [name for name in DEEP_STAGE_NAMES if name not in done]


def render_partial_summary(repo: str, issue_number: int, files: list[str],
                           done: list[str], reason: str) -> str:
    """Комментарий о прогоне, оборванном на середине.

    Человеку нужны три вещи: что сорвалось, что уцелело и что сделать дальше.
    Без последнего пункта частичный результат выглядит как окончательный.
    """
    br = branch(issue_number)
    base = f"https://github.com/{repo}/blob/{br}"
    links = "\n".join(f"- [`{path.rsplit('/', 1)[-1]}`]({base}/{path})"
                      for path in sorted(files))
    left = remaining_stages(issue_number, done)
    head = (
        "## ⏸ БФТ собран частично\n\n"
        f"Прогон оборвался: {reason}\n\n"
    )
    if links:
        head += (f"Что успели — в ветке `{br}`:\n\n{links}\n\n")
    else:
        head += "Ни одна стадия не успела дать артефакт.\n\n"
    if left:
        head += ("Осталось прогнать: "
                 + ", ".join(f"`{name}`" for name in left) + ".\n\n")
    return head + (
        "Работа не потеряна: повторный `/bft-deep` поднимет эту ветку и "
        "продолжит с места обрыва — готовые стадии заново не считаются."
    )


# --- Журнал прямых вызовов: слепая зона трекера ---
#
# Диалог стадий пишет entire — но только там, где есть АГЕНТ: он цепляется
# хуками за сессию Claude Code. Стадия, переведённая на прямые вызовы модели
# (`BFT_DIRECT_STAGES`), сессии не имеет, и для трекера её работы не существует.
#
# Журнал закрывает ровно эту дыру: что делал прямой вызов, сколько заходов
# понадобилось и чем кончилось. Стадии агента сюда не пишут — дублировать
# чекпоинты значит вести две записи одного и того же и обе поддерживать.
#
# Промпты целиком не кладутся: у стадии системная часть под сто килобайт, и в
# ветке она стала бы мусором, который никто не читает.

DIALOG_LOG = "dialog-log.md"


def dialog_log_path(issue_number: int) -> str:
    return f"{artefacts_dir(issue_number)}/{DIALOG_LOG}"


def render_dialog_entry(*, stage: str, actor: str, step: str, outcome: str,
                        detail: str = "", tokens: str = "",
                        elapsed: float | None = None) -> str:
    """Одна запись журнала — строка таблицы.

    `outcome` — «готово» / «добор» / «сбой»: по нему видно, где прогон буксовал,
    без чтения самих артефактов.
    """
    cells = [stage, actor, step, outcome,
             f"{elapsed:.0f} с" if elapsed is not None else "",
             tokens,
             (detail or "").replace("|", "\\|").replace("\n", " ")[:300]]
    return "| " + " | ".join(cells) + " |"


DIALOG_LOG_HEADER = (
    "# Журнал прогона БФТ\n\n"
    "Что делал пайплайн и чем это кончилось. Пишется по ходу, поэтому уцелевает\n"
    "и у оборванного прогона — по нему видно, на чём именно остановились.\n\n"
    "| Стадия | Исполнитель | Шаг | Исход | Время | Токены | Подробности |\n"
    "|---|---|---|---|---|---|---|\n"
)


# --- Сессия entire: диалог стадий как ветка репозитория ---
#
# Артефакты показывают результат, но не путь к нему. entire вешает хуки на
# `claude -p` и складывает диалог стадий чекпоинтами в git-рефы: получается
# ветка `entire/<hash>`, которая уезжает в origin рядом с артефактами. По id
# сессии оборванный прогон поднимается там, где встал, — без внешнего хранилища
# и без аккаунта, всё внутри репозитория задачи.
#
# ⚠️ Границы: entire перехватывает АГЕНТА. Стадия, переведённая на прямые вызовы
# модели (`BFT_DIRECT_STAGES`), для него невидима — у неё нет сессии Claude Code,
# которую можно зацепить хуком. Такие стадии видны только по артефактам.

ENTIRE_BRANCH_PREFIX = "entire/"


def parse_session_id(text: str) -> str:
    """Id сессии entire из вывода `entire session list`.

    Формат строки: `Claude Code · <repo> · session <uuid>`. Разбираем по
    ключевому слову, а не по позиции: CLI меняет оформление между версиями, а
    слово `session` перед идентификатором держится.
    """
    match = re.search(
        r"session\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        text, re.IGNORECASE)
    return match.group(1) if match else ""


def parse_session_branch(text: str) -> str:
    """Ветка чекпоинтов из вывода `git branch` или `git for-each-ref`."""
    for line in text.splitlines():
        name = line.strip().lstrip("* ").removeprefix("refs/heads/").strip()
        if name.startswith(ENTIRE_BRANCH_PREFIX):
            return name
    return ""


def render_session_hint(repo: str, session_id: str, session_branch: str) -> str:
    """Блок про сессию для комментария: где диалог и чем продолжить.

    Без id команда продолжения бессмысленна, поэтому пустой id — пустой блок:
    обещать «продолжите по ссылке», которой нет, хуже, чем не обещать.
    """
    if not session_id:
        return ""
    lines = ["", "**Диалог прогона сохранён.**"]
    if session_branch:
        lines.append(
            f"Чекпоинты — в ветке [`{session_branch}`]"
            f"(https://github.com/{repo}/tree/{session_branch}).")
    lines.append(
        f"Продолжить с этого места: `/bft-deep {session_id}` — прогон поднимет "
        "сессию и не станет пересчитывать сделанное.")
    return "\n".join(lines)


def split_session_arg(instructions: str) -> tuple[str, str]:
    """(id сессии, остальные инструкции) из хвоста `/bft-deep`.

    Человек пишет либо `/bft-deep <uuid>` для продолжения, либо `/bft-deep` с
    уточнениями текстом, либо и то и другое. Id ищем только в начале хвоста:
    uuid посреди текста — это цитата из прошлого комментария, а не команда.
    """
    text = (instructions or "").strip()
    match = re.match(
        r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b(.*)$",
        text, re.IGNORECASE | re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2).strip()
