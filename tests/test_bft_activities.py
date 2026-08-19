"""Активности БФТ: подтверждение приёма, письмо, рабочий каталог, публикация.

GitHub и модель подменены — проверяется решение активности, а не чужой HTTP.
"""

from pathlib import Path

import pytest

import activities as acts
from shared import bft
from shared.workflow_types import BftRequest, IssueInput


def _req(**overrides) -> BftRequest:
    kwargs = dict(repo="acme/widgets", issue_number=42, title="Валюты",
                  body="Хотим видеть цену в тенге", mode=bft.FAST)
    kwargs.update(overrides)
    return BftRequest(**kwargs)


class FakeGithub:
    def __init__(self, comments=None, branch=True):
        self.comments = comments or []
        self.posted: list[str] = []
        self.labels: list[str] = []
        self.reactions: list[tuple[int, str]] = []
        self.pushed: dict = {}
        self._branch = branch

    def list_comments(self, repo, issue_number, limit=50):
        return self.comments[:limit]

    def post_comment(self, repo, issue_number, body):
        self.posted.append(body)

    def add_label(self, repo, issue_number, label):
        self.labels.append(label)

    def remove_label(self, repo, issue_number, label):
        pass

    def add_reaction(self, repo, comment_id, content="eyes"):
        self.reactions.append((comment_id, content))

    def branch_exists(self, repo, branch):
        return self._branch

    def push_artifacts_to_branch(self, repo, branch, files, message):
        self.pushed = {"branch": branch, "files": files, "message": message}

    def auth_token(self, repo):
        return "t"


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGithub()
    monkeypatch.setattr(acts, "github_client", fake)
    # В образе промпты лежат по /app/prompts; тесты берут их из исходников —
    # промпт должен быть НАСТОЯЩИЙ, иначе тест не заметит, что файла нет вовсе.
    monkeypatch.setattr(acts, "PROMPTS_DIR",
                        Path(__file__).resolve().parent.parent / "prompts")
    return fake


def _comment(login, body, date="2026-08-01"):
    return {"user": {"login": login}, "body": body, "created_at": f"{date}T10:00:00Z"}


# --- Подтверждение приёма ---

async def test_fast_command_is_acknowledged_by_the_eyes_reaction(gh):
    """Требование постановки: команда получает реакцию «глаза». Метку быстрый
    проход себе НЕ вешает — она вернулась бы вебхуком как новая команда уже
    после того, как секундный прогон закончился."""
    await acts.ack_bft_command(_req(comment_id=555))

    assert gh.reactions == [(555, "eyes")]
    assert gh.labels == []
    assert gh.posted == []


async def test_deep_command_also_says_it_will_take_minutes(gh):
    """Прогон идёт минутами: без комментария человек не отличит «работаю» от
    «команда не доехала»."""
    await acts.ack_bft_command(_req(mode=bft.DEEP, comment_id=555))

    assert gh.reactions == [(555, "eyes")]
    assert "run:bft-deep" in gh.labels
    assert len(gh.posted) == 1
    assert bft.branch(42) in gh.posted[0]


async def test_label_triggered_fast_run_answers_with_a_comment(gh):
    """Триггер — метка, реагировать не на что: подтверждением служит комментарий,
    иначе с телефона не видно, что метка вообще доехала."""
    await acts.ack_bft_command(_req(comment_id=None))

    assert gh.reactions == []
    assert len(gh.posted) == 1


async def test_a_deleted_trigger_comment_does_not_break_the_ack(monkeypatch, gh):
    """Реакция — декорация. Её сбой не должен ронять приём команды."""
    def boom(*a, **kw):
        raise RuntimeError("404")

    monkeypatch.setattr(gh, "add_reaction", boom)
    await acts.ack_bft_command(_req(mode=bft.DEEP, comment_id=555))  # не падает

    assert gh.posted, "комментарий-подтверждение обязан уйти несмотря на сбой реакции"


# --- Сбор треда ---

def test_thread_keeps_the_agents_own_comments(gh):
    """Правка «во втором пункте не так» адресована прошлой редакции БФТ. Отсей
    её как «свой комментарий» — и замечание повиснет в воздухе."""
    gh.comments = [
        _comment("agent", f"{acts.BFT_LETTER_HEADING}\n\nЦель: старая"),
        _comment("alice", "/bft поправь цель"),
    ]
    thread, revision = acts._bft_thread(_req())

    assert "Цель: старая" in thread
    assert "/bft поправь цель" in thread
    assert revision == 2, "прошлая редакция обязана считаться"


def test_thread_survives_a_github_failure(monkeypatch, gh):
    """БФТ по заголовку и телу честнее, чем несобравшийся БФТ."""
    def boom(*a, **kw):
        raise RuntimeError("502")

    monkeypatch.setattr(gh, "list_comments", boom)
    assert acts._bft_thread(_req()) == ("", 1)


def test_oldest_comments_are_dropped_first(monkeypatch, gh):
    """Свежие реплики — это и есть правки, ради которых прогон запущен."""
    monkeypatch.setattr(acts, "BFT_THREAD_CHARS", 300)
    gh.comments = [_comment("alice", "старое " * 50), _comment("bob", "свежее")]
    thread, _ = acts._bft_thread(_req())

    assert "свежее" in thread
    assert "старое" not in thread


def test_instructions_outrank_the_thread_in_the_prompt():
    """Замечания человека — последнее слово; модель должна увидеть их до того,
    как прочтёт переписку, где сказано иначе."""
    message = acts._bft_user_message(
        _req(instructions="курс берём у ЦБ"), thread="**@bob:** курс с биржи")

    assert message.index("курс берём у ЦБ") < message.index("курс с биржи")


# --- Быстрый проход ---

class FakeLetter:
    goal = "цель"
    scope = "границы"
    how_to_demo = ["шаг"]
    open_questions = ["вопрос?"]
    documentation = []
    requirements = []
    personas = []


async def test_fast_run_publishes_the_letter(monkeypatch, gh):
    captured = {}

    def fake_extract(system, user, model_cls, model=None):
        captured["system"] = system
        captured["user"] = user
        return FakeLetter()

    monkeypatch.setattr(acts.llm, "extract", fake_extract)
    body = await acts.run_bft_fast(_req())

    assert gh.posted == [body]
    assert "**Цель:** цель" in body
    assert "/bft-deep" in body
    assert "Валюты" in captured["user"], "постановка обязана уехать в модель"


# --- Рабочий каталог глубокого прогона ---

def test_bft_workspace_is_separate_from_the_analysis_one():
    """Команды могут идти одновременно. Общий каталог означал бы, что
    подготовка одной сносит рабочее дерево другой посреди стадии."""
    from shared.workflow_types import AnalyzeInput

    req = _req()
    analyze = AnalyzeInput(repo=req.repo, issue_number=req.issue_number,
                           title=req.title, body=req.body)
    assert acts._bft_workspace_dir(req) != acts._workspace_dir(analyze)


def test_missing_workspace_fails_fast_before_the_expensive_stage(monkeypatch, tmp_path):
    """Пере-клон дал бы свежий репозиторий без артефактов прежних стадий, и
    прогон продолжился бы по пустому месту."""
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="рабочий каталог потерян"):
        acts._require_bft_workspace(_req(), None)


def test_missing_stage_input_names_the_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    req = _req()
    clone = Path(acts._bft_clone_dir(req))
    (clone / "sa_documentation").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")

    with pytest.raises(RuntimeError, match="problem.md"):
        acts._require_bft_workspace(req, f"{bft.artefacts_dir(42)}/problem.md")


def test_prepare_writes_the_statement_and_reuses_the_previous_branch(monkeypatch, tmp_path, gh):
    """Повторный `/bft-deep` — доработка лежащего документа, а не второй рядом."""
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    cloned = {}

    def fake_clone(repo, dest, branch=None):
        cloned["branch"] = branch
        Path(dest).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(acts, "_clone_repo", fake_clone)
    monkeypatch.setattr(acts, "_run_repomix", lambda clone_dir: None)

    req = _req(mode=bft.DEEP, instructions="курс у ЦБ")
    clone_dir = acts._build_bft_workspace(req)

    assert cloned["branch"] == bft.branch(42)
    statement = (Path(clone_dir) / bft.statement_path(42)).read_text(encoding="utf-8")
    assert "курс у ЦБ" in statement
    # Свой конфиг поверх чужого: разъехавшийся docs_path увёл бы артефакты туда,
    # где публикация их не ищет, и полный документов прогон отчитался бы пустым.
    config = (Path(clone_dir) / "bft-config.md").read_text(encoding="utf-8")
    assert bft.DOCS_ROOT in config


def test_prepare_falls_back_to_the_default_branch_on_the_first_run(monkeypatch, tmp_path):
    """Ветки ещё нет — клонировать её нельзя, git упал бы на ней молча для нас
    и непонятно для человека."""
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    fake = FakeGithub(branch=False)
    monkeypatch.setattr(acts, "github_client", fake)
    cloned = {}

    def fake_clone(repo, dest, branch=None):
        cloned["branch"] = branch
        Path(dest).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(acts, "_clone_repo", fake_clone)
    monkeypatch.setattr(acts, "_run_repomix", lambda clone_dir: None)
    acts._build_bft_workspace(_req(mode=bft.DEEP))

    assert cloned["branch"] is None


@pytest.fixture
def deep_env(monkeypatch, tmp_path, gh):
    """Реальный каталог под ANALYSIS_WORKSPACE_ROOT; внешние эффекты — заглушки.

    Каталог настоящий: guard стадии проверяет файлы на диске, и подменять его
    значило бы проверять заглушку вместо самой проверки.
    """
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    state = {"prompts": [], "beats": []}

    monkeypatch.setattr(acts.activity, "heartbeat",
                        lambda *a: state["beats"].append(a[0] if a else None))

    def fake_clone(repo, dest, branch=None):
        Path(dest).mkdir(parents=True, exist_ok=True)

    def fake_repomix(clone_dir):
        out = Path(clone_dir) / "sa_documentation" / "repomix-output.xml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<repo/>", encoding="utf-8")

    def fake_claude(prompt, cwd):
        state["prompts"].append(prompt)
        produced = {
            "/bft-context-gen": f"{bft.artefacts_dir(42)}/bft-context-pack.md",
            "/bft-problem": f"{bft.artefacts_dir(42)}/problem.md",
            "/bft-concept": f"{bft.artefacts_dir(42)}/concept.md",
            "/bft-draft": bft.document_path(42),
            "/bft-validate": f"{bft.artefacts_dir(42)}/validation.md",
        }.get(prompt.split()[0])
        if produced:
            path = Path(cwd) / produced
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("артефакт", encoding="utf-8")

    monkeypatch.setattr(acts, "_clone_repo", fake_clone)
    monkeypatch.setattr(acts, "_run_repomix", fake_repomix)
    monkeypatch.setattr(acts, "_run_claude", fake_claude)
    return state


async def test_the_whole_deep_pipeline_runs_end_to_end(deep_env):
    """Каждая стадия видит вход предыдущей: цепочка проверяется на настоящих
    файлах, а не на согласованности таблицы с самой собой."""
    req = _req(mode=bft.DEEP)
    await acts.prepare_bft_workspace(req)
    for stage in bft.DEEP_STAGE_NAMES:
        await acts.run_bft_stage(req, stage)

    assert [p.split()[0] for p in deep_env["prompts"]] == [
        "/bft-index", "/bft-context-gen", "/bft-problem", "/bft-concept",
        "/bft-debate", "/bft-draft", "/bft-validate",
    ]


async def test_a_stage_that_produced_nothing_is_a_failure(deep_env, monkeypatch):
    """Молчаливо пустая стадия увела бы прогон дальше по пустому месту, и
    провал вскрылся бы только на публикации — через семь стадий и деньги."""
    req = _req(mode=bft.DEEP)
    await acts.prepare_bft_workspace(req)
    await acts.run_bft_stage(req, "index")
    monkeypatch.setattr(acts, "_run_claude", lambda prompt, cwd: None)

    with pytest.raises(RuntimeError, match="не создан"):
        await acts.run_bft_stage(req, "context")


async def test_cleanup_removes_the_workspace(deep_env):
    req = _req(mode=bft.DEEP)
    await acts.prepare_bft_workspace(req)
    assert acts._bft_workspace_dir(req).exists()

    await acts.cleanup_bft_workspace(req)

    assert not acts._bft_workspace_dir(req).exists()


async def test_cleanup_of_a_missing_workspace_is_not_an_error(deep_env):
    """Уборка идёт в `finally` на обоих путях, в том числе когда каталога уже
    нет: её сбой затёр бы реальный исход прогона."""
    await acts.cleanup_bft_workspace(_req(mode=bft.DEEP))  # не падает


# --- Публикация ---

def test_artifacts_are_collected_by_directory_not_by_a_hardcoded_list(tmp_path):
    """Состав артефактов задаёт скилл. Зашитый перечень разъехался бы с ним при
    первом же обновлении, молча теряя файлы — включая csv с требованиями и
    диаграммы, на которые ссылается сам документ."""
    clone = tmp_path / "repo"
    epic = clone / bft.epic_dir(42)
    (epic / "artefacts").mkdir(parents=True)
    (epic / "issue-42.md").write_text("документ")
    (epic / "artefacts" / "problem.md").write_text("диагноз")
    (epic / "artefacts" / "requirements.csv").write_text("ID,ASIS\nБТ-1,нет")
    (epic / "artefacts" / "diagram.puml").write_text("@startuml")

    files = acts._collect_bft_artifacts(str(clone), 42)

    assert bft.document_path(42) in files
    assert f"{bft.artefacts_dir(42)}/problem.md" in files
    assert f"{bft.artefacts_dir(42)}/requirements.csv" in files
    assert f"{bft.artefacts_dir(42)}/diagram.puml" in files


def test_a_binary_artifact_is_skipped_loudly_not_silently(tmp_path, caplog):
    """Contents API принимает текст. Бинарь уронил бы уже начатую публикацию на
    UnicodeDecodeError, а тихо выброшенный артефакт — ровно то, от чего этот
    сбор и защищает."""
    clone = tmp_path / "repo"
    epic = clone / bft.epic_dir(42)
    epic.mkdir(parents=True)
    (epic / "issue-42.md").write_text("документ")
    (epic / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

    with caplog.at_level("WARNING"):
        files = acts._collect_bft_artifacts(str(clone), 42)

    assert bft.document_path(42) in files
    assert not any(p.endswith(".png") for p in files)
    assert "diagram.png" in caplog.text


async def test_publish_refuses_to_report_an_empty_run(monkeypatch, tmp_path, gh):
    """Ветка без артефактов и сводка со ссылками в никуда хуже честного сбоя."""
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    req = _req(mode=bft.DEEP)
    clone = Path(acts._bft_clone_dir(req))
    (clone / "sa_documentation").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")

    with pytest.raises(RuntimeError, match="ни одного артефакта"):
        await acts.publish_bft_deep(req)


async def test_publish_pushes_to_the_bft_branch_and_summarises(monkeypatch, tmp_path, gh):
    monkeypatch.setenv("ANALYSIS_WORKSPACE_ROOT", str(tmp_path))
    req = _req(mode=bft.DEEP)
    clone = Path(acts._bft_clone_dir(req))
    (clone / "sa_documentation").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")
    epic = clone / bft.epic_dir(42)
    epic.mkdir(parents=True)
    (epic / "issue-42.md").write_text("документ")

    assert await acts.publish_bft_deep(req) == bft.branch(42)
    assert gh.pushed["branch"] == bft.branch(42)
    assert bft.document_path(42) in gh.pushed["files"]
    assert bft.branch(42) in gh.posted[0]


async def test_failure_is_never_silent(gh):
    """Молчащий сбой неотличим от «ещё думает»: человек ждёт БФТ, которого уже
    не будет."""
    await acts.publish_bft_error(_req(mode=bft.DEEP), "стадия concept упала")

    assert len(gh.posted) == 1
    assert "стадия concept упала" in gh.posted[0]
    assert "/bft-deep" in gh.posted[0]


# --- Триаж: advisor молчит только про запрос функционала ---

def _classified(monkeypatch, category):
    class Result:
        def __init__(self):
            self.category = category
            self.answer = "ответ advisor"

    monkeypatch.setattr(acts.llm, "extract", lambda *a, **kw: Result())
    return IssueInput(repo="acme/widgets", issue_number=42, title="t", body="b",
                      author_login="alice", author_type="User")


def test_feature_answer_is_suppressed_when_bft_answers_instead(monkeypatch, gh):
    """Два комментария подряд означали бы, что первый неактуален уже в момент
    публикации."""
    issue = _classified(monkeypatch, "FEATURE")
    result = acts.classify_issue(issue, True)

    assert result.label == "advisor:feature-request"
    assert gh.posted == []
    assert "advisor:feature-request" in gh.labels


def test_a_bug_still_gets_its_advisor_answer(monkeypatch, gh):
    """БФТ по багу не собирается: промолчав, оставили бы Issue вообще без
    содержательного комментария."""
    issue = _classified(monkeypatch, "BUG")
    acts.classify_issue(issue, True)

    assert gh.posted == ["ответ advisor"]


def test_without_bft_the_old_behaviour_stands(monkeypatch, gh):
    """Прогоны прежнего поколения зовут активность одним аргументом."""
    issue = _classified(monkeypatch, "FEATURE")
    acts.classify_issue(issue)

    assert gh.posted == ["ответ advisor"]


def test_bft_on_triage_is_on_unless_explicitly_disabled(monkeypatch):
    """Продуктовое умолчание — БФТ включён: это новый формат ответа, а не
    дополнительная стадия. Тумблер существует ради отката."""
    monkeypatch.delenv("BFT_ON_TRIAGE", raising=False)
    assert acts.read_deadlines().bft_on_triage is True

    monkeypatch.setenv("BFT_ON_TRIAGE", "0")
    assert acts.read_deadlines().bft_on_triage is False
