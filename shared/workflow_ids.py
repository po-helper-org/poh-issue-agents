"""
Идентификаторы Temporal-workflow — в одном месте.

ID несут смысл, а не только уникальность: `issue-<repo>-<n>` делает повторный
`issues.opened` идемпотентным, `estimate-<repo>-<n>-<comment_id>` делает
идемпотентной повторную доставку вебхука с командой. Формат собирают и вебхук,
и скрипты прямого запуска; разъехавшись, они молча потеряли бы именно эту
идемпотентность — поэтому строка живёт здесь одна.
"""


def issue_workflow_id(repo_full_name: str, issue_number: int, suffix: str = "") -> str:
    # suffix — осознанный перепрогон backfill: другой id, чтобы не упереться в
    # REJECT_DUPLICATE уже обработанного Issue (scripts/backfill.py --suffix).
    base = f"issue-{repo_full_name}-{issue_number}"
    return f"{base}-{suffix}" if suffix else base


def estimate_workflow_id(repo_full_name: str, issue_number: int,
                         comment_id: int | None = None) -> str:
    # comment_id=None — запуск меткой `run:estimate`: комментария-триггера нет,
    # различителем служит "label". Повторная доставка того же события упирается
    # в WorkflowAlreadyStarted, а метка, поставленная заново после завершённого
    # прогона, — честно новый прогон (прошлый закрыт, id свободен).
    marker = "label" if comment_id is None else comment_id
    return f"estimate-{repo_full_name}-{issue_number}-{marker}"


def bft_workflow_id(repo_full_name: str, issue_number: int, mode: str) -> str:
    # Режим входит в id, а лишних различителей нет. Два режима — разные прогоны,
    # и глубокий не должен упираться в идущий быстрый. Внутри режима id
    # фиксирован: повторная команда при идущем прогоне упирается в
    # WorkflowAlreadyStarted вместо второго прогона, а после завершения id
    # свободен — и следующая команда с новыми уточнениями честно новый прогон.
    return f"bft-{mode}-{repo_full_name}-{issue_number}"


def comment_ack_workflow_id(repo_full_name: str, comment_id: int) -> str:
    # Ключ — id комментария: повторная доставка того же события упирается в
    # WorkflowAlreadyStarted, и второй реакции GitHub не просят. Номер issue в
    # ключе не нужен — id комментария уникален в пределах репозитория.
    return f"comment-ack-{repo_full_name}-{comment_id}"


def analysis_workflow_id(repo_full_name: str, issue_number: int) -> str:
    # Фиксированный id (без comment_id): повторный /analyze при идущем прогоне
    # упирается в WorkflowAlreadyStarted вместо второго дорогого прогона.
    return f"analysis-{repo_full_name}-{issue_number}"


def development_workflow_id(repo_full_name: str, issue_number: int) -> str:
    # Номера попытки в ключе НЕТ намеренно: разработка по одному Issue идёт в
    # один момент времени в одном экземпляре, и повторный запуск при идущем
    # прогоне обязан упереться в WorkflowAlreadyStarted. Иначе на репозитории
    # окажется два агента в одном рабочем каталоге — имя контейнера раннера
    # тоже выводится из номера Issue (`shared/develop.py:131`).
    return f"develop-{repo_full_name}-{issue_number}"


def pr_fix_workflow_id(repo_full_name: str, pr_number: int, round_number: int) -> str:
    # Номер круга в ключе, в отличие от разработки: круги разделены ожиданием
    # доклада ревью, и второй круг — честно новый прогон со своей историей.
    # Без номера он упирался бы в id первого, и доводка PR вставала бы после
    # первого же круга.
    return f"prfix-{repo_full_name}-{pr_number}-{round_number}"


def research_workflow_id(repo_full_name: str, issue_number: int, comment_id: int | None = None) -> str:
    # comment_id=None — запуск меткой `run:research`: комментария-триггера нет,
    # различителем служит "label". Повторная доставка того же события упирается
    # в WorkflowAlreadyStarted, а метка, поставленная заново после завершённого
    # прогона, — честно новый прогон (прошлый закрыт, id свободен).
    marker = "label" if comment_id is None else comment_id
    return f"research-{repo_full_name}-{issue_number}-{marker}"


def delivery_workflow_id(repo_full_name: str) -> str:
    """Релиз в репозитории — ровно один за раз.

    Ключ по репозиторию, без номера Issue и без комментария: два одновременных
    релиза мержили бы в одну ветку по двум разным планам, и ни один из них не
    смог бы честно сказать, что он выкатил. Повторная команда при идущем
    релизе упирается в WorkflowAlreadyStarted — это и есть нужный ответ
    «релиз уже идёт», а не второй прогон.
    """
    return f"delivery-{repo_full_name}"


def howtodemo_workflow_id(repo_full_name: str, issue_number: int) -> str:
    """Приёмка Issue — ровно одна за раз.

    Ключ по Issue, а не по репозиторию: приёмок в репозитории может идти
    несколько (по разным задачам), но по одной задаче два прогона одновременно
    гоняли бы один и тот же сценарий по одному и тому же стенду, и второй снёс
    бы контейнер первого. Повторная команда при идущей приёмке упирается в
    WorkflowAlreadyStarted — это и есть нужный ответ «приёмка уже идёт».

    Без номера комментария: осознанный перепрогон делается после того, как
    предыдущий завершился, а не поверх него.
    """
    return f"howtodemo-{repo_full_name}-{issue_number}"
