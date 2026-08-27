import subprocess

import pytest

import github_client


def test_create_pr_dry_run_makes_no_calls(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    called = {"n": 0}
    monkeypatch.setattr(github_client.requests, "post",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "put",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    monkeypatch.setattr(github_client.requests, "get",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    url = github_client.create_pr_with_files(
        "o/r", "consolidation/2026-07-14", "main",
        {"docs/consolidation/overview.md": "# x"}, "Consolidation", "body")
    assert url is None
    assert called["n"] == 0


def test_review_text_skips_the_harness_own_comments(monkeypatch):
    """Круг правок отвечает РЕВЬЮЕРУ, а не сам себе.

    Комментарии контура приходят от GitHub App, то есть с `type == "Bot"`, и
    попадали в текст ревью вместе с настоящими замечаниями. На втором круге
    агент читал собственную просьбу «внёс правки, прошу перепроверить» как часть
    замечаний — и правил по ней.
    """
    import github_client as gc
    from shared.agent_comment import MARKER

    class _Resp:
        ok = True

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("/reviews"):
            return _Resp([{"state": "COMMENTED", "body": "PR Reviewer Guide 🔍"}])
        if url.endswith("/pulls/9/comments"):
            return _Resp([])
        return _Resp([
            {"user": {"type": "Bot"}, "body": f"/review\n\nвнёс правки\n\n{MARKER}"},
            {"user": {"type": "Bot"}, "body": "Suggestion: вынести порог в константу"},
            {"user": {"type": "User"}, "body": "а мне и так нравится"},
        ])

    monkeypatch.setattr(gc.requests, "get", fake_get)
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})

    text = gc.review_text("o/r", 9)

    assert "PR Reviewer Guide" in text
    assert "вынести порог в константу" in text
    assert "внёс правки" not in text, "агент кормится своей же просьбой"
    assert "и так нравится" not in text, "реплика человека — не замечание ревью"


def test_git_trusts_the_worktree_the_runner_owned(monkeypatch, tmp_path):
    """Коммит идёт от root в каталоге, которым владеет раннер.

    Каталог задачи передаётся раннеру (uid 10001), а коммит и пуш делает воркер
    от root. Git на такое отвечает `fatal: detected dubious ownership in
    repository` и отказывается работать — то есть готовая работа агента не
    доезжает до PR. `safe.directory` объявляет каталог доверенным для этой
    команды, не трогая глобальный конфиг.
    """
    import github_client as gc

    class _Done:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    captured: dict = {}

    def fake_run(cmd, **kw):
        captured.setdefault("env", kw.get("env"))
        # `show-ref` — «ветка ещё не существует», иначе пустой диф читался бы
        # как ретрай, а не как «агент ничего не менял», и код пошёл бы дальше
        # к пушу, до которого этому тесту дела нет — ему нужен только env.
        if "show-ref" in cmd:
            return _Done(1)
        return _Done(0)  # «диффа нет» — до пуша не доходим, нам нужен только env

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc.subprocess, "run", fake_run)

    gc.publish_worktree("o/r", str(tmp_path), "feature/1-x",
                        title="t", body="b", message="m")

    env = captured["env"]
    keys = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
            for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert keys.get("safe.directory") == str(tmp_path)


def test_a_retry_after_a_failed_push_finishes_publishing_instead_of_declaring_no_changes(
        monkeypatch, tmp_path):
    """Находка 1: единственный реалистичный сбой публикации — падение пуша ПОСЛЕ
    успешного коммита. `dev_publish` идёт с `maximum_attempts=3`, и вторая
    попытка видит то же рабочее дерево: изменения агента уже в коммите,
    `git add -A` ставить нечего, `diff --cached --quiet` возвращает 0.

    Раньше это читалось буквально как «агент не изменил ни одного файла», и
    функция возвращала `None` до пуша — воркфлоу ронял стадию с заведомо
    ложной причиной, а обещание ветки «срыв публикации повторяет публикацию»
    не выполнялось. Настоящий git нужен здесь, а не мок: сама находка — в
    точной семантике `checkout -B` на уже созданной ветке (no-op, коммит не
    теряется), подделать её мокой — рискуя подтвердить не то, что происходит
    на самом деле.
    """
    import github_client as gc

    origin = tmp_path / "origin.git"
    clone_dir = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(origin)],
                   check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(clone_dir)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.name", "t"], check=True)
    # Базовый коммит БЕЗ правки агента — иначе `checkout -B` не от чего будет
    # отталкиваться, а `a.txt` ниже создаёт ИМЕННО некоммиченное изменение:
    # реальный агент оставляет файлы на диске, коммит делает уже сама
    # `publish_worktree`.
    (clone_dir / "README.md").write_text("baseline")
    subprocess.run(["git", "-C", str(clone_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "seed"],
                   check=True, capture_output=True)
    (clone_dir / "a.txt").write_text("тронуто агентом")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _FakeResp:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 101}

    posts: list = []
    monkeypatch.setattr(gc.requests, "post",
                        lambda *a, **k: posts.append((a, k)) or _FakeResp())

    # Реальный `subprocess.run` для всего, кроме первого пуша: имитируем ровно
    # тот сбой, который описывает находка, — не трогая семантику остальных
    # git-команд подменой.
    real_run = subprocess.run
    push_attempts = {"n": 0}

    def flaky_push(cmd, **kw):
        if len(cmd) > 3 and cmd[3] == "push":
            push_attempts["n"] += 1
            if push_attempts["n"] == 1:
                class _FailedPush:
                    returncode = 1
                    stdout = ""
                    stderr = "имитация сетевого сбоя на пуше"
                return _FailedPush()
        return real_run(cmd, **kw)

    monkeypatch.setattr(gc.subprocess, "run", flaky_push)

    with pytest.raises(gc.GitCommandError):
        gc.publish_worktree("o/r", str(clone_dir), "agent/issue-1",
                            title="t", body="b", message="m")

    # Ретрай: то же рабочее дерево — коммит уже есть, добавлять нечего.
    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-1",
                                 title="t", body="b", message="m")

    assert number == 101, "ретрай не довёл публикацию и не вернул номер PR"
    assert push_attempts["n"] == 2, "второй пуш не состоялся"
    assert len(posts) == 1, "PR должен открыться ровно один раз — на удавшемся пуше"

    log = subprocess.run(["git", "-C", str(clone_dir), "log", "--oneline", "agent/issue-1"],
                         check=True, capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 2, (
        "повторная попытка не должна была создать второй коммит поверх первого:\n" + log)


def test_a_retry_with_nothing_new_to_add_but_a_fresh_branch_is_still_no_changes(
        monkeypatch, tmp_path):
    """Различаем находку 1 от её противоположности: если ветка свежая (агент
    первый раз тут), пустой индекс — по-прежнему честное «агент ничего не
    менял», а не повод пытаться пушить нулевой коммит."""
    import github_client as gc

    class _Done:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    calls: list = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "show-ref" in cmd:
            return _Done(1)  # ветки ещё нет — это первая попытка
        return _Done(0)      # «диффа нет» на первой попытке — агент не менял файлов

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc.subprocess, "run", fake_run)

    number = gc.publish_worktree("o/r", str(tmp_path), "agent/issue-2",
                                 title="t", body="b", message="m")

    assert number is None
    assert not any(len(c) > 3 and c[3] == "push" for c in calls), (
        "пуша быть не должно — открывать нечего")


# ────────── задача 7: `.harness/` коммитится всегда, пустой прогон не должен потеряться ──────────
#
# `.harness/` пишет `_dev_prepare` ДО прогона агента (контекст задачи, не
# часть правки — см. `shared/develop.py`, SERVICE_FILES) и НЕ снимает перед
# коммитом: он обязан дойти до PR. Значит каталог существует в рабочем дереве
# независимо от того, тронул ли агент код, и голая проверка `git diff --cached
# --quiet` перестала бы отличать «агент ничего не сделал» от «агент отработал».
# `ignore_for_empty_check` — тот же трюк, что раньше решался снятием файла
# (`.task.md` и соседи): каталог остаётся в коммите, но не в проверке пустоты.
# Настоящий git, не подделка: находка — в точной семантике pathspec-исключения,
# а мок рискует подтвердить не то, что происходит на самом деле (см. другие
# тесты этого файла).

def _seed_repo(tmp_path):
    origin = tmp_path / "origin.git"
    clone_dir = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(clone_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "config", "user.name", "t"], check=True)
    (clone_dir / "README.md").write_text("baseline")
    subprocess.run(["git", "-C", str(clone_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "seed"],
                   check=True, capture_output=True)
    return clone_dir


def test_publish_ignores_the_harness_directory_when_deciding_if_anything_changed(
        monkeypatch, tmp_path):
    """`.harness/` коммитится всегда — его наличие само по себе не должно
    читаться как «агент что-то сделал». Иначе ЛЮБОЙ прогон, даже тот, где
    агент не тронул ни одного файла, открывал бы PR с одним каталогом
    контекста внутри: то самое «шаг отработал, доложил успех, результата
    нет», ради которого и существует эта проверка."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    # Только каталог контекста — как будто агент код не менял вовсе.
    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    posts: list = []
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: posts.append((a, k)))

    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-3",
                                 title="t", body="b", message="m",
                                 ignore_for_empty_check=(".harness/**",))

    assert number is None, "только контекст без правок — это пустой прогон"
    assert posts == [], "PR не должен открываться без настоящей правки"
    log = subprocess.run(["git", "-C", str(clone_dir), "log", "--oneline"],
                         check=True, capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 1, "коммит одного контекста без кода делать не должны"


def test_publish_still_commits_real_changes_alongside_the_harness_directory(
        monkeypatch, tmp_path):
    """Исключение из проверки пустоты не должно исключать каталог из самого
    коммита: `.harness/` обязан доехать до PR вместе с настоящей правкой."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")
    (clone_dir / "a.txt").write_text("тронуто агентом")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _FakeResp:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 55}

    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _FakeResp())

    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-4",
                                 title="t", body="b", message="m",
                                 ignore_for_empty_check=(".harness/**",))

    assert number == 55
    show = subprocess.run(["git", "-C", str(clone_dir), "show", "--stat", "HEAD"],
                          check=True, capture_output=True, text=True).stdout
    assert "a.txt" in show and ".harness/context.md" in show, (
        "исключение из проверки пустоты не должно исключать файлы из самого коммита")


def test_ignore_for_empty_check_defaults_to_excluding_nothing(monkeypatch, tmp_path):
    """Без аргумента поведение прежнее: голый каталог контекста без кода
    по-прежнему считается изменением — исключение из проверки пустоты
    работает, только когда вызывающий явно об этом попросил.

    L3 (ревью задачи 7): раньше тест создавал посторонний файл
    (`untracked.txt`), никак не связанный с `.harness/`, и проходил бы при
    ЛЮБОМ значении по умолчанию — обычный файл считается правкой независимо
    от того, исключается ли `.harness/`. Докстринг обещал проверку «голый
    каталог контекста читается как пустой прогон», а тест её не делал. Теперь
    сценарий — тот же голый каталог контекста, что и в
    `test_publish_ignores_the_harness_directory_when_deciding_if_anything_changed`,
    но БЕЗ `ignore_for_empty_check`: по умолчанию каталог не исключается и
    обязан читаться как настоящее изменение — PR открывается."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _FakeResp:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 66}

    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _FakeResp())

    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-5",
                                 title="t", body="b", message="m")

    assert number == 66, "без исключений даже .harness/ по-прежнему считается правкой"


# ────────── M3 (ревью задачи 7): .gitignore целевого репозитория не съедает каталог ──────────
#
# `git add -A` молча пропускает пути, которые `.gitignore` целевого
# репозитория игнорирует. Если в нём есть `.harness/`, `.harness/` не
# попадает в индекс — проверка пустоты (уже исключающая `.harness/**` из
# рассмотрения) видит только код агента, коммит и PR проходят, а каталог
# контекста молча теряется без единого предупреждения.

def test_force_include_on_a_brand_new_branch_does_not_undo_the_empty_run_guard(
        monkeypatch, tmp_path):
    """Регрессия на связку M1+M3: `force_include` сам по себе не должен
    заставлять коммитить пустой прогон. На СОВЕРШЕННО НОВОЙ ветке
    `.harness/` «новый» ВСЕГДА (его только что собрал `_dev_prepare`) — если
    бы это само по себе считалось изменением, ЛЮБОЙ прогон, где агент не
    тронул ни файла, открывал бы PR с одним каталогом контекста внутри,
    ровно тот регресс, ради которого существует `ignore_for_empty_check`."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")
    # Агент НИЧЕГО не менял — единственное отличие от seed-коммита это .harness/.

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    posts: list = []
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: posts.append((a, k)))

    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-10",
                                 title="t", body="b", message="m",
                                 ignore_for_empty_check=(".harness/**",),
                                 force_include=(".harness",))

    assert number is None, "пустой прогон с force_include всё равно обязан читаться пустым"
    assert posts == [], "PR не должен открываться без настоящей правки"
    log = subprocess.run(["git", "-C", str(clone_dir), "log", "--oneline"],
                         check=True, capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 1, "коммит одного контекста без кода делать не должны"


def test_publish_force_includes_the_harness_directory_despite_gitignore(monkeypatch, tmp_path):
    """Основной случай: `.gitignore` целевого репозитория игнорирует
    `.harness/`, но `force_include` заставляет его попасть в коммит вместе с
    настоящей правкой кода."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    (clone_dir / ".gitignore").write_text(".harness/\n")
    subprocess.run(["git", "-C", str(clone_dir), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "add gitignore"],
                   check=True, capture_output=True)

    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")
    (clone_dir / "a.txt").write_text("тронуто агентом")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    class _FakeResp:
        status_code = 201
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"number": 88}

    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _FakeResp())

    number = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-6",
                                 title="t", body="b", message="m",
                                 ignore_for_empty_check=(".harness/**",),
                                 force_include=(".harness",))

    assert number == 88
    show = subprocess.run(["git", "-C", str(clone_dir), "show", "--stat", "HEAD"],
                          check=True, capture_output=True, text=True).stdout
    assert ".harness/context.md" in show, \
        ".harness проигнорирован .gitignore, несмотря на force_include"


def test_publish_commits_a_forced_path_even_when_the_visible_diff_is_otherwise_empty(
        monkeypatch, tmp_path):
    """Ретрай без нового кода: первый коммит на ветке сделан БЕЗ
    force_include (например, старой версией кода) и не содержит `.harness/`
    из-за `.gitignore`. Второй вызов — с force_include, но без каких-либо
    других изменений в рабочем дереве: «видимый» дифф (без
    `ignore_for_empty_check`) пуст, но `.harness/` обязан всё равно доехать
    до коммита — иначе force_include ничего не гарантирует именно там, где
    он нужнее всего."""
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    (clone_dir / ".gitignore").write_text(".harness/\n")
    subprocess.run(["git", "-C", str(clone_dir), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "add gitignore"],
                   check=True, capture_output=True)

    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("# Контекст задачи\n")
    (clone_dir / "a.txt").write_text("тронуто агентом")

    monkeypatch.setattr(gc, "_dry_run", lambda: False)
    monkeypatch.setattr(gc, "auth_token", lambda repo: "t")
    monkeypatch.setattr(gc, "_auth_headers", lambda repo: {})
    monkeypatch.setattr(gc, "_default_branch", lambda repo: "main")

    # Первый вызов — БЕЗ force_include, как «старая версия»: коммит уходит,
    # но .harness/ в него не попадает (gitignore).
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _FakeResp(77))
    number1 = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-9",
                                  title="t", body="b", message="m",
                                  ignore_for_empty_check=(".harness/**",))
    assert number1 == 77
    show1 = subprocess.run(["git", "-C", str(clone_dir), "show", "--stat", "HEAD"],
                           check=True, capture_output=True, text=True).stdout
    assert ".harness" not in show1, "тест не воспроизвёл предпосылку — .harness уже в коммите"

    # Второй вызов — с force_include, рабочее дерево НЕ менялось: видимый
    # дифф (a.txt) пуст, потому что a.txt уже в первом коммите.
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _FakeResp(77))
    number2 = gc.publish_worktree("o/r", str(clone_dir), "agent/issue-9",
                                  title="t", body="b", message="m",
                                  ignore_for_empty_check=(".harness/**",),
                                  force_include=(".harness",))

    assert number2 == 77, "PR должен подтвердиться, а не пропасть на ретрае"
    show2 = subprocess.run(["git", "-C", str(clone_dir), "show", "--stat", "HEAD"],
                           check=True, capture_output=True, text=True).stdout
    assert ".harness/context.md" in show2, \
        "force_include не довёл каталог до коммита, когда видимый дифф пуст"
    log = subprocess.run(["git", "-C", str(clone_dir), "log", "--oneline", "agent/issue-9"],
                         check=True, capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 4, (
        "ожидался НОВЫЙ коммит поверх первого (seed + gitignore + первый + второй):\n" + log)


class _FakeResp:
    def __init__(self, number, status_code=201):
        self.number = number
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {"number": self.number}


# ────────── M3: подтверждение фактом, а не замыслом ──────────

def test_missing_from_tree_reports_a_path_absent_from_head(tmp_path):
    """Юнит на саму проверку «фактом»: путь либо есть в дереве HEAD, либо
    нет — независимо от того, что о нём думал `git add -f`."""
    import os
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    git = gc._git_runner(str(clone_dir), {**os.environ})

    assert gc._missing_from_tree(git, (".harness",)) == [".harness"]

    harness = clone_dir / ".harness"
    harness.mkdir()
    (harness / "context.md").write_text("x")
    subprocess.run(["git", "-C", str(clone_dir), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(clone_dir), "commit", "-m", "add harness"],
                   check=True, capture_output=True)

    assert gc._missing_from_tree(git, (".harness",)) == []


def test_missing_from_tree_is_a_noop_without_force_include(tmp_path):
    """Без аргументов проверка не должна стоить лишнего вызова git — путь
    вызывающего кода без `force_include` её не платит вовсе."""
    import os
    import github_client as gc

    clone_dir = _seed_repo(tmp_path)
    git = gc._git_runner(str(clone_dir), {**os.environ})
    assert gc._missing_from_tree(git, ()) == []
