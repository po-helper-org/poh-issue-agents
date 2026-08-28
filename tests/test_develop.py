"""Активность Develop: передача подготовленного Issue агенту разработки.

Второй ключевой шаг контура после Research. Проверяем ровно ту границу, на
которой цикл перестаёт отвечать за работу: запуск либо состоялся и Issue уехал
в `in-development`, либо не состоялся и это видно. Промежуточного состояния
«метка стоит, прогона нет» быть не должно — именно оно превращает потерянную
задачу в незаметную.
"""

import asyncio
import pathlib
import re

import pytest

import activities as activities_module
from shared import develop
from shared.workflow_types import IssueInput
from tests.conftest import make_fake_set_labels


def _issue(number: int = 7) -> IssueInput:
    return IssueInput(repo="o/r", issue_number=number, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


@pytest.fixture
def gh(monkeypatch):
    """Подменяет GitHub целиком: активность не должна ходить в сеть в тестах."""
    monkeypatch.setenv("DEVELOP_MODE", "dispatch")
    calls: dict = {"dispatch": [], "labels": [], "comments": []}
    monkeypatch.setattr(activities_module.github_client, "dispatch_workflow",
                        lambda repo, wf, ref, inputs:
                            calls["dispatch"].append((repo, wf, ref, inputs)))
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: calls["labels"].append(label))
    monkeypatch.setattr(activities_module.github_client, "post_comment",
                        lambda repo, n, body: calls["comments"].append(body))
    monkeypatch.setattr(activities_module.github_client, "branch_exists",
                        lambda repo, branch: calls.get("branch_exists", True))
    return calls


# --- чистый контракт границы ---

def test_inputs_are_all_strings():
    """`workflow_dispatch` принимает только строки — число молча уронит прогон
    на стороне GitHub, где мы его уже не увидим."""
    inputs = develop.dispatch_inputs(12, branch="research/issue-12", priority="P1")

    assert all(isinstance(v, str) for v in inputs.values())
    assert inputs["issue_number"] == "12"


def test_missing_branch_is_an_explicit_empty_string():
    """Пустая строка — это «аналитики не было», и агент обязан отличать её от
    несуществующей ветки. Отсутствие ключа означало бы «не передали»."""
    inputs = develop.dispatch_inputs(12, branch="")

    assert inputs["research_branch"] == ""


def test_comment_says_where_the_run_happens():
    body = develop.handoff_comment(12, repo="o/r", branch="research/issue-12",
                                   where="запустил OpenHands на своём сервере")

    assert "research/issue-12" in body
    assert "на своём сервере" in body    # где именно идёт работа
    assert "Closes #12" in body          # чем прогон должен закончиться
    assert "GROW" in body                # и что он делает с edge-кейсами


def test_comment_without_analysis_says_so_instead_of_naming_a_branch():
    body = develop.handoff_comment(12, repo="o/r", branch="", where="запустил агента")

    assert "аналитики по задаче не было" in body
    assert "research/issue-12" not in body


def test_develop_is_on_by_default(monkeypatch):
    """Забытая переменная не должна тихо обрывать контур на самом дорогом шаге."""
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    assert develop.enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "off", "NO"])
def test_develop_switches_off_only_explicitly(monkeypatch, raw):
    monkeypatch.setenv("DEVELOP_ENABLED", raw)

    assert develop.enabled() is False


# --- сама активность ---

def test_dispatch_carries_the_research_branch(gh, monkeypatch):
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    asyncio.run(activities_module.trigger_openhands_resolver(_issue(7)))

    repo, workflow_file, ref, inputs = gh["dispatch"][0]
    assert repo == "o/r"
    assert workflow_file == develop.DEFAULT_WORKFLOW_FILE
    assert ref == develop.DEFAULT_REF
    assert inputs["research_branch"] == "research/issue-7"


def test_no_analysis_branch_still_dispatches(gh, monkeypatch):
    """Путь бага: ветки с артефактами нет, и это не повод не начинать работу."""
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)
    monkeypatch.setattr(activities_module.github_client, "branch_exists",
                        lambda repo, branch: False)

    asyncio.run(activities_module.trigger_openhands_resolver(_issue(7)))

    _, _, _, inputs = gh["dispatch"][0]
    assert inputs["research_branch"] == ""


def test_failed_dispatch_leaves_no_trace_of_a_started_run(gh, monkeypatch):
    """Соврать про запуск хуже, чем не запустить: без прогона не должно быть ни
    метки, ни комментария о начале работы."""
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("workflow_dispatch не принят (404)")

    monkeypatch.setattr(activities_module.github_client, "dispatch_workflow", boom)

    with pytest.raises(RuntimeError, match="404"):
        asyncio.run(activities_module.trigger_openhands_resolver(_issue(7)))

    assert gh["labels"] == []
    assert gh["comments"] == []


def test_label_failure_does_not_fail_a_started_run(gh, monkeypatch):
    """Прогон уже идёт. Уронить активность из-за не поставленной метки значит
    отправить в `failed` задачу, которая на самом деле в работе."""
    monkeypatch.delenv("DEVELOP_ENABLED", raising=False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("rate limit")

    monkeypatch.setattr(activities_module.github_client, "add_label", boom)

    asyncio.run(activities_module.trigger_openhands_resolver(_issue(7)))

    assert gh["dispatch"], "прогон должен был стартовать"
    assert gh["comments"], "комментарий не должен зависеть от метки"


def test_switched_off_fails_visibly_instead_of_pretending(gh, monkeypatch):
    monkeypatch.setenv("DEVELOP_ENABLED", "0")

    with pytest.raises(RuntimeError, match="DEVELOP_ENABLED"):
        asyncio.run(activities_module.trigger_openhands_resolver(_issue(7)))

    assert gh["dispatch"] == []


# --- Провенанс сильнее фильтра ботов ---

def test_agent_follow_up_is_not_filtered_as_a_bot(monkeypatch):
    """Follow-up контура заводит агент, и по автору он бот. Но `origin:agent`
    означает ровно обратное тому, ради чего фильтр заведён: это собственный
    выход контура, которому протокол предписывает сокращённый триаж, а не
    пропуск."""
    labels_set: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: labels_set.append(label))

    issue = IssueInput(repo="o/r", issue_number=9, title="edge-кейс", body="тело",
                       author_login="github-actions[bot]", author_type="Bot",
                       interactive=False)

    assert activities_module.prefilter_bot_and_security(issue, origin_agent=True) is None
    assert labels_set == []


def test_bot_without_provenance_is_still_filtered(monkeypatch):
    labels_set: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "add_label",
                        lambda repo, n, label: labels_set.append(label))

    issue = IssueInput(repo="o/r", issue_number=9, title="bump deps", body="",
                       author_login="dependabot[bot]", author_type="Bot",
                       interactive=False)

    assert activities_module.prefilter_bot_and_security(issue) == "bot"
    assert "bot-authored" in labels_set


def test_security_check_survives_the_provenance_exception(monkeypatch):
    """Проверка на безопасность — о содержимом, а не об авторе: репорт об
    уязвимости не становится безопаснее оттого, что его завёл агент."""
    monkeypatch.setattr(activities_module.github_client, "add_label", lambda *a: None)
    monkeypatch.setattr(activities_module.github_client, "post_comment", lambda *a: None)

    issue = IssueInput(repo="o/r", issue_number=9,
                       title="Найдена уязвимость в расчёте", body="",
                       author_login="openhands", author_type="Bot", interactive=False)

    assert activities_module.prefilter_bot_and_security(issue, origin_agent=True) == "security"


# --- Индикатор разработки не переживает смену фазы ---

def test_in_development_label_is_dropped_when_the_phase_moves_on(monkeypatch):
    """Метка сообщает «задача у агента разработки». После открытия PR это уже
    неправда, а снять её в самой активности Develop нельзя — она к тому моменту
    давно завершилась."""
    removed: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "remove_label",
                        lambda repo, n, label: removed.append(label))
    monkeypatch.setattr(activities_module.github_client, "add_label", lambda *a: None)
    monkeypatch.setattr(activities_module.github_client, "set_labels",
                        make_fake_set_labels(activities_module.github_client.add_label,
                                             activities_module.github_client.remove_label))

    activities_module.set_phase("o/r", 7, "pr-open")

    assert develop.IN_DEVELOPMENT_LABEL in removed


def test_in_development_label_survives_its_own_phase(monkeypatch):
    removed: list[str] = []
    monkeypatch.setattr(activities_module.github_client, "remove_label",
                        lambda repo, n, label: removed.append(label))
    monkeypatch.setattr(activities_module.github_client, "add_label", lambda *a: None)
    monkeypatch.setattr(activities_module.github_client, "set_labels",
                        make_fake_set_labels(activities_module.github_client.add_label,
                                             activities_module.github_client.remove_label))

    activities_module.set_phase("o/r", 7, "in-development")

    assert develop.IN_DEVELOPMENT_LABEL not in removed


# --- Сокращённый триаж: приоритет без классификации ---

def test_priority_is_scored_for_an_agent_issue_without_classification(monkeypatch):
    """Сокращённый триаж классификацию пропускает — её уже сделал тот агент,
    который завёл задачу. Приоритет ей всё равно нужен: по нему follow-up встаёт
    в очередь наравне с остальными."""
    seen: dict = {}

    class _Extracted:
        impact = time_criticality = risk_reduction = 3
        effort = 4
        okr_alignment = "unrelated"
        okr_key_result = None
        bug_severity = "none"
        affected_domains: list[str] = []
        who = ""
        risks: list[str] = []
        goal_impact = ""

    monkeypatch.setattr(activities_module, "_load_prompt", lambda name: "prompt")
    monkeypatch.setattr(activities_module, "CONFIG_DIR",
                        pathlib.Path(__file__).resolve().parent.parent / "config")
    def _fake_extract(prompt, msg, schema, model=None):
        seen["msg"] = msg
        return _Extracted()

    monkeypatch.setattr(activities_module.llm, "extract", _fake_extract)

    result = activities_module.score_priority(
        _issue(7), None,
        activities_module.DuplicateResult(decision="none", best_match_number=None,
                                          probability=0.0, reason="", context_branch=None))

    assert result.tier.startswith("P")
    assert "Issue заведён агентом" in seen["msg"]


# --- Локальный режим: прогон на своём сервере ---

def test_local_is_the_default(monkeypatch):
    """Стенд самодостаточен, пока явно не сказано иначе: репозиторий
    обслуживается целиком внутри контура, без чужих раннеров."""
    monkeypatch.delenv("DEVELOP_MODE", raising=False)

    assert develop.mode() == develop.LOCAL


def test_runner_gets_no_github_token():
    """Агент исполняет код чужого репозитория. Токен ему не нужен: пушит и
    открывает PR воркер — своим токеном и после прогона."""
    command = develop.runner_command("dev-o__r-7", image="img",
                                     volume="vol", mount="/workspaces")

    passed = {command[i + 1] for i, part in enumerate(command) if part == "-e"}
    assert passed == {"LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"}
    assert not any("GH" in part or "TOKEN" in part for part in command)


def test_runner_is_disposable_and_sees_only_its_task():
    command = develop.runner_command("dev-o__r-7", image="img",
                                     volume="vol", mount="/workspaces")

    assert "--rm" in command                                  # не копим мусор с ключом
    assert "vol:/workspaces" in command                       # общий том с воркером
    assert command[command.index("-w") + 1] == "/workspaces/dev-o__r-7/repo"


def test_task_slug_is_a_directory_name_not_a_path():
    """Слэш репозитория в имени каталога создал бы вложенность вместо задачи."""
    assert "/" not in develop.task_slug("po-helper-org/poh-demo-checkout", 7)


def test_run_timeout_falls_back_on_garbage(monkeypatch):
    """Битое значение не должно означать «без потолка»: зависший агент держал
    бы задачу в неопределённости молча."""
    monkeypatch.setenv("DEVELOP_TIMEOUT_SEC", "скоро")

    assert develop.run_timeout() == develop.DEFAULT_RUN_TIMEOUT_SEC


def test_worker_image_carries_the_binary_the_runner_is_launched_with():
    """Одноразовый контейнер поднимает сам воркер — значит клиент Docker обязан
    лежать в его образе.

    Сокет демона воркеру уже смонтирован, и по конфигу всё выглядит рабочим:
    том на месте, образ раннера собран, `DEVELOP_MODE=local`. Но команда
    запуска — `docker run ...`, а бинаря `docker` в образе воркера не было, и
    прогон падал на FileNotFoundError ещё до первой строки кода агента. Снаружи
    это `phase:failed` на самом дорогом шаге, причём одинаковый и для «агент не
    справился», и для «агента не запускали вовсе».
    """
    binary = develop.runner_command("slug", image="i", volume="v", mount="/m")[0]
    dockerfile = (pathlib.Path(__file__).resolve().parents[1]
                  / "worker" / "Dockerfile").read_text(encoding="utf-8")

    assert binary == "docker"
    assert "docker-ce-cli" in dockerfile, (
        "воркер запускает раннер через docker, но клиента в его образе нет")


def test_worker_and_runner_agree_on_the_node_version():
    """Проверки проекта гоняет воркер, код проекта исполняет раннер — Node у них
    обязан быть один.

    Воркер прогоняет `DEVELOP_TEST_COMMAND` до пуша, ту же строку, что и CI. На
    живом прогоне #13 это дало `Could not find 'tests/*.test.mjs'`: команда
    репозитория — `node --test "tests/*.test.mjs"`, glob раскрывает сам Node
    (с 22), а в образе воркера стоял 20. Красный шаг разработки на зелёном коде.
    """
    root = pathlib.Path(__file__).resolve().parents[1]

    def node_major(dockerfile: str) -> str:
        text = (root / dockerfile).read_text(encoding="utf-8")
        found = re.search(r"deb\.nodesource\.com/setup_(\d+)\.x", text)
        assert found, f"{dockerfile}: не нашёл установку Node"
        return found.group(1)

    assert node_major("worker/Dockerfile") == node_major("openhands/Dockerfile")


def test_runner_container_has_a_deterministic_name():
    """У прогона должно быть имя, по которому его можно найти и снять.

    Контейнер живёт своей жизнью: воркер запускает его и ждёт, но если воркер
    умер (выкладка, рестарт, terminate воркфлоу), клиент исчезает, а контейнер
    остаётся работать — с ключом модели, минутами CPU и памятью. На стенде так
    и вышло: прогон сняли, а раннер жил ещё полчаса и доедал память, из-за
    которой следующая задача еле ползла. Без имени найти его нечем: `--rm`
    убирает контейнер только после нормального выхода.
    """
    slug = develop.task_slug("o/r", 7)
    command = develop.runner_command(slug, image="i", volume="v", mount="/m")

    assert "--name" in command
    assert command[command.index("--name") + 1] == slug


def test_leftover_run_is_reaped_before_a_new_attempt(monkeypatch):
    """Новая попытка начинается с чистого места.

    Temporal повторяет активность разработки до трёх раз. Если предыдущая
    попытка умерла вместе с воркером, её контейнер остался работать — и вторая
    попытка либо упирается в занятое имя, либо запускает второго агента в тот же
    рабочий каталог. Оба исхода хуже, чем снять остаток.
    """
    commands: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(activities_module.subprocess, "run",
                        lambda cmd, **kw: commands.append(cmd) or _Done())

    activities_module._dev_run_agent(_issue(7))

    slug = develop.task_slug("o/r", 7)
    assert commands[0] == ["docker", "rm", "-f", slug], (
        f"перед прогоном не сняли остаток: {commands[0]}")
    assert commands[1][:2] == ["docker", "run"]


def test_runner_uid_matches_the_image():
    """Uid раннера объявлен в одном месте и совпадает с образом.

    Воркер готовит каталог задачи от root, а раннер работает непривилегированным
    пользователем. Разъехались числа — каталог остаётся недоступным на запись, и
    это САМЫЙ дорогой из возможных отказов: агент не падает, а молча уходит
    писать в /tmp и докладывает об успехе. На живом прогоне #19 так потерялись
    21 минута работы, а PR открылся пустым.
    """
    dockerfile = (pathlib.Path(__file__).resolve().parents[1]
                  / "openhands" / "Dockerfile").read_text(encoding="utf-8")

    found = re.search(r"useradd\s+-m\s+-u\s+(\d+)", dockerfile)
    assert found, "не нашёл создание пользователя в образе раннера"
    assert int(found.group(1)) == develop.RUNNER_UID


def test_workspace_is_handed_over_to_the_runner(tmp_path, monkeypatch):
    """Каталог задачи передаётся раннеру пригодным для записи."""
    chowned: list[tuple[str, int]] = []
    monkeypatch.setattr(activities_module.os, "chown",
                        lambda path, uid, gid: chowned.append((str(path), uid)))

    activities_module._handover_to_runner(tmp_path)

    assert (str(tmp_path), develop.RUNNER_UID) in chowned


def test_failed_handover_is_loud(tmp_path, monkeypatch):
    """Не смогли передать — падаем здесь.

    Молча оставить каталог root'а значит отдать агенту рабочее место, в которое
    он не может писать, — и получить успешный прогон без единой правки.
    """
    def boom(path, uid, gid):
        raise PermissionError("not root")

    monkeypatch.setattr(activities_module.os, "chown", boom)

    with pytest.raises(RuntimeError, match="раннер"):
        activities_module._handover_to_runner(tmp_path)
