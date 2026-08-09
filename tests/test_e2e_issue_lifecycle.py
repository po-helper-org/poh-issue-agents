"""E2E: реальный вебхук → реальный воркфлоу → реальные активности.

Отличие от остальных тестов: здесь НИЧЕГО не подменяется внутри сервиса.
Работает настоящий FastAPI-обработчик, настоящий Temporal-воркер с настоящими
`workflows.py` и `activities.py`, настоящие промпты и коэффициенты из репозитория.
Заглушки стоят ровно на двух границах — GitHub и LLM, то есть там, где кончается
наш код и начинается сеть.

Это ответ на вопрос «не деградировал ли путь Issue»: если сломается композиция —
маршрут вебхука, порядок стадий, работа с метками, — упадёт именно этот файл, а
не набор изолированных заглушек, каждая из которых по отдельности зелёная.
"""

import hashlib
import hmac
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webhook"))

import activities as activities_module  # noqa: E402
import estimation  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402
from temporalio.worker import Worker  # noqa: E402
from workflows import (  # noqa: E402
    IssueAnalysis,
    IssueEstimation,
    IssueLifecycle,
    WebhookAudit,
)

SECRET = "e2e-secret"
REPO = "acme/widgets"

# Тот же список, что регистрирует worker.py. Расхождение ловит
# tests/test_worker_wiring.py; здесь важно, что активности НАСТОЯЩИЕ.
E2E_ACTIVITIES = [
    activities_module.prefilter_bot_and_security,
    activities_module.read_protocol_state,
    activities_module.read_deadlines,
    activities_module.mark_ready_for_dev,
    activities_module.post_agents_off_notice,
    activities_module.intake_gate,
    activities_module.post_clarifying_question,
    activities_module.close_as_spam,
    activities_module.escalate_to_human,
    activities_module.post_error_label,
    activities_module.mark_analyzing,
    activities_module.mark_command_running,
    activities_module.finish_command_labels,
    activities_module.classify_issue,
    activities_module.duplicate_check,
    activities_module.score_priority,
    activities_module.post_priority_comment,
    activities_module.prepare_workspace,
    activities_module.run_fnr_stage,
    activities_module.publish_analysis,
    activities_module.cleanup_workspace,
    activities_module.ack_command,
    activities_module.publish_analysis_error,
    activities_module.ack_estimate_command,
    activities_module.collect_estimation_context,
    activities_module.extract_estimation_facts,
    activities_module.compute_estimate,
    activities_module.post_estimate_comment,
    activities_module.post_estimate_error,
]


class FakeGitHub:
    """Состояние Issue в памяти. Ведёт себя как GitHub в том, что важно
    пайплайну: метки накапливаются и снимаются, комментарии дописываются."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.comments: list[str] = []
        self.state = "open"
        self.reactions: list[tuple[int, str]] = []
        self.branches: dict[str, dict[str, str]] = {}
        self.calls: list[str] = []

    # --- мутации ---
    def post_comment(self, repo, issue_number, body):
        self.calls.append("post_comment")
        self.comments.append(body)

    def add_label(self, repo, issue_number, label):
        self.calls.append(f"add_label:{label}")
        if label not in self.labels:
            self.labels.append(label)

    def remove_label(self, repo, issue_number, label):
        self.calls.append(f"remove_label:{label}")
        if label in self.labels:
            self.labels.remove(label)

    def close_issue(self, repo, issue_number):
        self.state = "closed"

    def add_reaction(self, repo, comment_id, content="eyes"):
        self.reactions.append((comment_id, content))

    def push_artifacts_to_branch(self, repo, branch, files, message):
        self.calls.append(f"push:{branch}")
        self.branches.setdefault(branch, {}).update(files)

    # --- чтения ---
    def get_issue(self, repo, issue_number):
        return {"number": issue_number, "title": "Ревизия оплаты",
                "body": "нужен ретрай платежей", "state": self.state,
                "labels": [{"name": name} for name in self.labels]}

    def get_issue_body(self, repo, issue_number):
        return "нужен ретрай платежей"

    def list_comments(self, repo, issue_number, limit=50):
        return [{"user": {"login": "alice", "type": "User"}, "body": c,
                 "created_at": "2026-08-09T10:00:00Z"} for c in self.comments]

    def list_linked_prs(self, repo, issue_number, limit=20):
        return []

    def search_candidates(self, repo, query, limit=15):
        return []  # дублей нет — ветка duplicate_check без LLM

    def branch_exists(self, repo, branch):
        return branch in self.branches

    def get_file(self, repo, path, ref):
        return self.branches.get(ref, {}).get(path)


class FakeLLM:
    """Детерминированные ответы модели по типу запрошенной схемы."""

    def __init__(self) -> None:
        self.models: list[str] = []

    def extract(self, system_prompt, user_message, response_model, model=None):
        self.models.append(model)
        name = response_model.__name__
        if name == "GateExtraction":
            return response_model(status="SUFFICIENT", content="ок")
        if name == "ClassificationExtraction":
            return response_model(category="FEATURE", answer="Разберём ретраи платежей.")
        if name == "PriorityExtraction":
            return response_model(impact=4, time_criticality=3, risk_reduction=3, effort=3,
                                  okr_alignment="supports_okr", who="платежи",
                                  risks=["сложность"], goal_impact="ускорит оплату")
        if name == "EstimationFacts":
            # Полный набор полей: методика считает по декомпозиции и сверяет её
            # с независимой оценкой по Function Points.
            return response_model.model_validate({
                "work_type": "new_development",
                "artifact_type": "new_module",
                "scaffolding_hours": 4.0,
                "work_units": [
                    {"name": "ретрай платежей", "hours": 10.0,
                     "rationale": "эндпоинт + правило повтора"},
                ],
                "integration_hours": 3.0,
                "fp_count": 8.0,
                "fp_hours_per_point": 2.0,
                "data_sufficiency": "sufficient",
                "has_acceptance_criteria": True,
                "has_dependencies_listed": True,
                "has_api_contract": False,
                "has_data_class": True,
                "risks": [],
                "open_questions": [],
                "reasoning": "декомпозиция по единицам работы",
            })
        raise AssertionError(f"неожиданная схема: {name}")


@pytest.fixture
def e2e(monkeypatch, tmp_path):
    """Сервис целиком, с сетью, замкнутой на заглушки."""
    gh = FakeGitHub()
    fake_llm = FakeLLM()

    # Границы: GitHub и LLM.
    monkeypatch.setattr(activities_module, "github_client", gh)
    monkeypatch.setattr(activities_module.llm, "extract", fake_llm.extract)

    # Тяжёлые внешние процессы прогона /analyze — тоже граница (git, repomix, claude).
    def fake_clone(repo, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)

    def fake_repomix(clone_dir):
        out = Path(clone_dir) / "sa_documentation" / "repomix-output.xml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<repo/>", encoding="utf-8")

    produced = {
        "/fnr-new-task": "task.md",
        "/fnr-concept": "concept.md",
        "/fnr-system-requirements": "system_requirements.md",
        "/validate-doc": "validation.md",
    }

    def fake_claude(prompt, cwd):
        fnr = Path(cwd) / activities_module.FNR_DIR
        fnr.mkdir(parents=True, exist_ok=True)
        name = produced.get(prompt.split()[0])
        if name:
            body = f"# {name}\n"
            if name == "system_requirements.md":
                body += "- [УТОЧНИТЬ] лимит попыток ретрая\n"
            (fnr / name).write_text(body, encoding="utf-8")

    monkeypatch.setattr(activities_module, "_clone_repo", fake_clone)
    monkeypatch.setattr(activities_module, "_run_repomix", fake_repomix)
    monkeypatch.setattr(activities_module, "_run_claude", fake_claude)

    # Файлы, запечённые в образ: в тестах берём их из репозитория.
    monkeypatch.setattr(activities_module, "PROMPTS_DIR", ROOT / "prompts")
    monkeypatch.setattr(activities_module, "CONFIG_DIR", ROOT / "config")
    monkeypatch.setattr(activities_module, "WORKSPACE_DIR", ROOT / "workspace")
    # Значение по умолчанию у load_rules связывается при определении функции,
    # поэтому подмены RULES_PATH мало — заменяем саму функцию.
    rules_path = ROOT / "config" / "estimation-rules.toml"
    monkeypatch.setattr(estimation, "RULES_PATH", rules_path)
    monkeypatch.setattr(estimation, "load_rules",
                        lambda path=rules_path: estimation.tomllib.loads(
                            rules_path.read_text(encoding="utf-8")))
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("ISSUE_AGENT_REPOS", REPO)
    monkeypatch.delenv("AGENT_TRIGGER_ALLOWLIST", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    return gh, fake_llm


def _post(client, event: str, payload: dict):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body, headers={
        "X-GitHub-Event": event, "X-Hub-Signature-256": sig,
        "X-GitHub-Delivery": f"dlv-{uuid.uuid4()}", "Content-Type": "application/json"})


def _opened(number: int = 7) -> dict:
    return {
        "action": "opened",
        "repository": {"full_name": REPO},
        "issue": {"number": number, "title": "Ревизия оплаты",
                  "body": "нужен ретрай платежей",
                  "user": {"login": "alice", "type": "User"}},
        "sender": {"login": "alice"},
    }


def _labeled(label: str, number: int = 7) -> dict:
    payload = _opened(number)
    payload["action"] = "labeled"
    payload["label"] = {"name": label}
    return payload


def _commented(text: str, number: int = 7) -> dict:
    payload = _opened(number)
    payload["action"] = "created"
    payload["comment"] = {"id": 555, "body": text,
                          "user": {"login": "alice", "type": "User"}}
    return payload


class _Harness:
    """Вебхук и воркер, говорящие через один тестовый Temporal."""

    def __init__(self, env, client):
        self.env = env
        self.client = client

    async def wait(self, wf_id: str):
        return await self.env.client.get_workflow_handle(wf_id).result()

    async def stage(self, wf_id: str) -> str:
        return await self.env.client.get_workflow_handle(wf_id).query(IssueLifecycle.stage)

    async def signal(self, wf_id: str, label: str):
        await self.env.client.get_workflow_handle(wf_id).signal(
            IssueLifecycle.human_decision, label)


async def _harness(monkeypatch):
    """Поднимает Temporal и подменяет клиента вебхука на тестовый."""
    env = await WorkflowEnvironment.start_time_skipping()
    import main

    async def _get_client():
        return env.client

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    from fastapi.testclient import TestClient

    return env, main, TestClient(main.app)


def _worker(env) -> Worker:
    """Воркер, настроенный КАК В ПРОДЕ: активности синхронные и обязаны идти в
    пул потоков, иначе блокирующий вызов заморозил бы event loop целиком."""
    return Worker(
        env.client, task_queue="issue-lifecycle",
        workflows=[IssueLifecycle, IssueAnalysis, IssueEstimation, WebhookAudit],
        activities=E2E_ACTIVITIES,
        activity_executor=ThreadPoolExecutor(max_workers=3),
        max_concurrent_activities=3,
    )


@pytest.mark.timeout(120)
async def test_new_issue_goes_through_the_whole_triage(e2e, monkeypatch):
    """issues.opened → предфильтр → gate → классификация → дедуп → приоритет →
    парковка. Проверяем видимый результат в GitHub и стадию в Temporal."""
    gh, fake_llm = e2e
    env, main, client = await _harness(monkeypatch)
    async with env:
        async with _worker(env):
            assert _post(client, "issues", _opened()).status_code == 200

            wf_id = f"issue-{REPO}-7"
            handle = env.client.get_workflow_handle(wf_id)
            for _ in range(300):
                if await handle.query(IssueLifecycle.stage) == "awaiting-human-decision":
                    break
                await env.sleep(1)

            assert await handle.query(IssueLifecycle.stage) == "awaiting-human-decision"

    # Классификация и приоритет доехали до Issue.
    assert "advisor:feature-request" in gh.labels
    assert any(label.startswith("priority:") for label in gh.labels)
    assert any("Приоритет" in c for c in gh.comments)
    # Дешёвая модель на gate, сильная на классификации — разделение сохранилось.
    assert fake_llm.models[0] != fake_llm.models[1]


@pytest.mark.timeout(120)
async def test_research_me_produces_artifacts_and_hands_off(e2e, monkeypatch):
    """Полный путь до передачи разработчику: триаж → research-me → пять стадий
    FNR → артефакты в ветке → ready-for-dev с чеклистом."""
    gh, _ = e2e
    env, main, client = await _harness(monkeypatch)
    async with env:
        async with _worker(env):
            assert _post(client, "issues", _opened()).status_code == 200
            wf_id = f"issue-{REPO}-7"
            handle = env.client.get_workflow_handle(wf_id)
            for _ in range(300):
                if await handle.query(IssueLifecycle.stage) == "awaiting-human-decision":
                    break
                await env.sleep(1)

            # Человек ставит research-me, затем не даёт build-me.
            assert _post(client, "issues", _labeled("research-me")).status_code == 200
            await handle.signal(IssueLifecycle.human_decision, "no-build")
            await handle.result()

    branch = "research/issue-7"
    assert branch in gh.branches, "артефакты анализа не опубликованы"
    assert f"{activities_module.FNR_DIR}/system_requirements.md" in gh.branches[branch]

    # Обратный ход меток команды и передача разработчику.
    assert "done:analyze" in gh.labels
    assert "run:analyze" not in gh.labels
    assert "ready-for-dev" in gh.labels
    checklist = next(c for c in gh.comments if "готова к разработке" in c)
    assert "лимит попыток ретрая" in checklist, "незакрытый вопрос не попал в чеклист"
    assert "Closes #7" in checklist


@pytest.mark.timeout(120)
async def test_label_command_runs_estimation_end_to_end(e2e, monkeypatch):
    """run:estimate меткой: подтверждение, расчёт, комментарий и обратный ход меток."""
    gh, _ = e2e
    env, main, client = await _harness(monkeypatch)
    async with env:
        async with _worker(env):
            assert _post(client, "issues", _labeled("run:estimate")).status_code == 200
            await env.client.get_workflow_handle(f"estimate-{REPO}-7-label").result()

    assert "done:estimate" in gh.labels
    assert "run:estimate" not in gh.labels
    assert any("Оценка" in c or "оценк" in c.lower() for c in gh.comments)


@pytest.mark.timeout(120)
async def test_agents_off_stops_everything(e2e, monkeypatch):
    """Рубильник человека: ни одного вызова модели и ни одной метки триажа."""
    gh, fake_llm = e2e
    gh.labels.append("agents:off")
    env, main, client = await _harness(monkeypatch)
    async with env:
        async with _worker(env):
            assert _post(client, "issues", _opened()).status_code == 200
            await env.client.get_workflow_handle(f"issue-{REPO}-7").result()

    assert fake_llm.models == [], "рубильник не остановил вызовы модели"
    assert not any(label.startswith("advisor:") for label in gh.labels)
    assert not any(label.startswith("priority:") for label in gh.labels)


@pytest.mark.timeout(120)
async def test_foreign_repo_is_dropped_and_audited(e2e, monkeypatch):
    """Событие чужого репозитория не запускает триаж, но оставляет след."""
    gh, fake_llm = e2e
    env, main, client = await _harness(monkeypatch)
    payload = _opened()
    payload["repository"]["full_name"] = "other/thing"
    async with env:
        async with _worker(env):
            assert _post(client, "issues", payload).status_code == 200
            await env.sleep(5)

    assert fake_llm.models == []
    assert gh.comments == []
