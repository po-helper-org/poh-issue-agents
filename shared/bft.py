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
