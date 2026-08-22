"""Единая точка запуска агента: child при живом цикле, root — иначе.

Требование эпика #34: агенты существуют **и по отдельности, и в рамках Issue**.
До этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`
стартовали из вебхука как самостоятельные воркфлоу, а `IssueLifecycle` о них
не знал и вешал косметическую метку.

Режим выбирает ОДНА функция, а не каждый вызывающий. Иначе решение
«child или root» разъедется по трём местам ровно так же, как когда-то разъехались
форматы workflow id (см. `shared/workflow_ids.py`).

Как принимается решение
-----------------------
Не «описать воркфлоу и посмотреть статус» — это лишний round-trip и гонка между
проверкой и стартом. Вместо этого **всегда signal-with-start** в цикл: он либо
получает сигнал, либо поднимается тем же вызовом. Дальше цикл сам решает,
поднимать ли дочерний прогон.

Остаётся один случай, который цикл обслужить не может: прогоны ПРЕЖНЕГО
поколения (линейный путь до #36). Их история не знает ни фазового цикла, ни
сигнала на запуск агента — команда была бы принята и потеряна. Их отличает
query `handles_agents`; для них лаунчер стартует root-прогон, как раньше.

Двойного прогона это не создаёт при любом исходе гонки: id агента фиксирован
(`shared/workflow_ids.py`), поэтому второй старт упирается в
`WorkflowAlreadyStarted`, а не тратит деньги второй раз.
"""

import logging

from shared.workflow_ids import (
    analysis_workflow_id,
    bft_workflow_id,
    estimate_workflow_id,
    issue_workflow_id,
    research_workflow_id,
)

_log = logging.getLogger(__name__)

TASK_QUEUE = "issue-lifecycle"

ANALYSIS_WORKFLOW = "IssueAnalysis"
ESTIMATION_WORKFLOW = "IssueEstimation"
BFT_WORKFLOW = "IssueBft"
RESEARCH_WORKFLOW = "IssueResearch"

# Режимы — возвращаются вызывающему для лога и тестов.
CHILD = "child"    # работу ведёт цикл дочерним прогоном
ROOT = "root"      # цикл прежнего поколения либо автономный запуск


async def _cycle_handles_agents(handle, repo: str, issue_number: int) -> bool:
    """Умеет ли этот цикл вести агентов дочерними прогонами.

    Ошибку query не считаем за «не умеет»: signal-with-start уже прошёл, значит
    цикл жив, а новых прогонов со временем становится только больше. Поднимать
    на недоступном query второй дорогой прогон — худший из двух исходов.
    """
    try:
        return bool(await handle.query("handles_agents"))
    except Exception as exc:
        _log.warning("не удалось спросить цикл %s#%s о режиме агентов (%s) — "
                     "считаю, что он ведёт их сам", repo, issue_number, exc)
        return True


async def request_analysis(client, issue_input, analyze, *,
                           search_attributes=None) -> str:
    """`/analyze` или метка `run:analyze` — запустить аналитику по Issue."""
    from temporalio.exceptions import WorkflowAlreadyStartedError

    repo, issue_number = analyze.repo, analyze.issue_number
    handle = await client.start_workflow(
        "IssueLifecycle",
        issue_input,
        id=issue_workflow_id(repo, issue_number),
        task_queue=TASK_QUEUE,
        search_attributes=search_attributes,
        start_signal="analyze_requested",
        start_signal_args=[analyze.comment_id],
    )
    if await _cycle_handles_agents(handle, repo, issue_number):
        return CHILD

    try:
        await client.start_workflow(
            ANALYSIS_WORKFLOW, analyze,
            id=analysis_workflow_id(repo, issue_number),
            task_queue=TASK_QUEUE,
            search_attributes=search_attributes,
        )
    except WorkflowAlreadyStartedError:
        # Прогон по этому Issue уже идёт: пользователь видел ack первого
        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.
        _log.info("analysis already running for %s#%s", repo, issue_number)
    return ROOT


async def request_bft(client, issue_input, req, *, search_attributes=None) -> str:
    """`/bft`, `/bft-deep` или метка `run:bft*` — собрать БФТ по Issue.

    БФТ фазу не двигает: быстрый проход формулирует запрос, глубокий кладёт
    артефакты в свою ветку. Цикл поднимает прогон дочерним и продолжает ждать
    своё — ровно как с оценкой.
    """
    from temporalio.exceptions import WorkflowAlreadyStartedError

    repo, issue_number = req.repo, req.issue_number
    handle = await client.start_workflow(
        "IssueLifecycle",
        issue_input,
        id=issue_workflow_id(repo, issue_number),
        task_queue=TASK_QUEUE,
        search_attributes=search_attributes,
        start_signal="bft_requested",
        start_signal_args=[req],
    )
    if await _cycle_handles_agents(handle, repo, issue_number):
        return CHILD

    try:
        await client.start_workflow(
            BFT_WORKFLOW, req,
            id=bft_workflow_id(repo, issue_number, req.mode),
            task_queue=TASK_QUEUE,
            search_attributes=search_attributes,
        )
    except WorkflowAlreadyStartedError:
        # Прогон в этом режиме уже идёт: пользователь видел подтверждение
        # первого запуска, второе было бы шумом. Вебхук — чистый транспорт.
        _log.info("bft %s already running for %s#%s", req.mode, repo, issue_number)
    return ROOT


async def request_estimate(client, issue_input, estimate, *,
                           search_attributes=None) -> str:
    """`/estimate` или метка `run:estimate` — оценить трудоёмкость.

    Оценка фазу не двигает: это боковая команда, а не стадия пути Issue.
    Цикл поднимает её дочерним прогоном и продолжает ждать своё.
    """
    from temporalio.exceptions import WorkflowAlreadyStartedError

    repo, issue_number = estimate.repo, estimate.issue_number
    handle = await client.start_workflow(
        "IssueLifecycle",
        issue_input,
        id=issue_workflow_id(repo, issue_number),
        task_queue=TASK_QUEUE,
        search_attributes=search_attributes,
        start_signal="estimate_requested",
        start_signal_args=[estimate.comment_id],
    )
    if await _cycle_handles_agents(handle, repo, issue_number):
        return CHILD

    try:
        await client.start_workflow(
            ESTIMATION_WORKFLOW, estimate,
            id=estimate_workflow_id(repo, issue_number, estimate.comment_id),
            task_queue=TASK_QUEUE,
            search_attributes=search_attributes,
        )
    except WorkflowAlreadyStartedError:
        # Тот же вебхук доставлен повторно — оценка уже идёт.
        _log.info("estimate already running for %s#%s", repo, issue_number)
    return ROOT


async def request_research(client, issue_input, analyze, *,
                          search_attributes=None) -> str:
    """`/research` или метка `run:research` — продуктовое исследование по Issue.

    Продуктовое исследование фазу двигает: это отдельная стадия `product-research`,
    предшествующая бизнес-анализу. Цикл поднимает её дочерним прогоном.
    """
    from temporalio.exceptions import WorkflowAlreadyStartedError

    repo, issue_number = analyze.repo, analyze.issue_number
    handle = await client.start_workflow(
        "IssueLifecycle",
        issue_input,
        id=issue_workflow_id(repo, issue_number),
        task_queue=TASK_QUEUE,
        search_attributes=search_attributes,
        start_signal="research_requested",
        start_signal_args=[analyze.comment_id],
    )
    if await _cycle_handles_agents(handle, repo, issue_number):
        return CHILD

    try:
        await client.start_workflow(
            RESEARCH_WORKFLOW, analyze,
            id=research_workflow_id(repo, issue_number, analyze.comment_id or 0),
            task_queue=TASK_QUEUE,
            search_attributes=search_attributes,
        )
    except WorkflowAlreadyStartedError:
        # Прогон по этому Issue уже идёт: пользователь видел ack первого
        # запуска, второй ack был бы шумом. Webhook — чистый транспорт.
        _log.info("research already running for %s#%s", repo, issue_number)
    return ROOT
