"""Стадия repowise в конвейере аналитики.

Состав стадий задан в четырёх местах сразу — набор артефактов, цепочка,
перечень имён и входные условия. Рассогласование этих мест проявляется не
ошибкой при запуске, а отказом живого прогона, поэтому тест состава дешевле
любого другого способа его поймать.
"""

import activities


def test_repowise_is_first_stage():
    assert activities.FNR_STAGE_NAMES[0] == "repowise"


def test_task_stage_requires_dialog_artifact():
    assert activities._FNR_STAGE_REQUIRES["task"] == \
        f"{activities.FNR_DIR}/repowise-dialog.md"


def test_repowise_stage_has_no_input_requirement():
    # Первая стадия конвейера: требовать от неё чего-либо на входе не с чего.
    assert activities._FNR_STAGE_REQUIRES["repowise"] is None


def test_dialog_artifact_is_collected():
    assert "repowise-dialog.md" in activities.ARTIFACT_FILES


def test_dialog_artifact_is_visible_to_estimation():
    assert any("repowise-dialog" in p for p in activities.ARTIFACT_PATHS)


def test_every_stage_name_resolves():
    # _fnr_stage поднимает ValueError на неизвестном имени; перечень и цепочка
    # обязаны совпадать поимённо.
    for name in activities.FNR_STAGE_NAMES:
        prompt, expected, requires = activities._fnr_stage(name, "описание")
        assert prompt


# --- Деградация вместо остановки (модификация M1 вердикта дебатов) ---
#
# Без неё прокси становится обязательной зависимостью на пути, который сегодня
# остановить нечему: _build_workspace зависит только от git и repomix внутри
# того же контейнера. Артефакт создаётся всегда, поэтому guard стадии `task`
# сохраняется без изменений и по-прежнему ловит молчаливый пропуск.

import asyncio

from shared import repowise as repowise_module
from shared.workflow_types import AnalyzeInput


def _analyze():
    return AnalyzeInput(repo="o/r", issue_number=42, title="Заголовок",
                        body="тело", comment_id=1)


def _clone(tmp_path):
    clone = tmp_path / "repo"
    (clone / activities.FNR_DIR).mkdir(parents=True)
    return clone


def test_degrades_when_proxy_unavailable(monkeypatch, tmp_path):
    clone = _clone(tmp_path)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.setattr(repowise_module, "enabled", lambda: True)
    monkeypatch.setattr(repowise_module, "available", lambda timeout=5.0: False)

    ran = []
    monkeypatch.setattr(activities, "_run_claude",
                        lambda prompt, cwd: ran.append(prompt))

    report = asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))

    assert ran == []                      # дорогой процесс диалога не запускался
    assert report["outcome"] == "degraded"
    artifact = clone / activities.FNR_DIR / "repowise-dialog.md"
    assert artifact.exists()
    assert "source-unavailable" in artifact.read_text(encoding="utf-8")


def test_degrades_when_integration_disabled(monkeypatch, tmp_path):
    # Пустой REPOWISE_PROXY_URL — не отказ, а выключенная интеграция.
    clone = _clone(tmp_path)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.delenv("REPOWISE_PROXY_URL", raising=False)
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)

    report = asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))
    assert report["outcome"] == "degraded"


def test_ok_outcome_when_proxy_available(monkeypatch, tmp_path):
    clone = _clone(tmp_path)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.setattr(repowise_module, "enabled", lambda: True)
    monkeypatch.setattr(repowise_module, "available", lambda timeout=5.0: True)

    def fake_claude(prompt, cwd):
        (clone / activities.FNR_DIR / "repowise-dialog.md").write_text(
            "# Диалог\n\nход 1\n", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)

    report = asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))
    assert report["outcome"] == "ok"


def test_other_stages_report_outcome(monkeypatch, tmp_path):
    # Ключ outcome должен быть у КАЖДОЙ стадии, иначе потребителю отчёта
    # пришлось бы знать, у каких стадий он есть, а у каких нет.
    clone = _clone(tmp_path)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))

    def fake_claude(prompt, cwd):
        (clone / activities.FNR_DIR / "task.md").write_text("x", encoding="utf-8")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    report = asyncio.run(activities.run_fnr_stage(_analyze(), "task"))
    assert report["outcome"] == "ok"


def test_degradation_does_not_burn_stage_timeout(monkeypatch, tmp_path):
    # Проверка доступности обязана быть быстрой: деградация не должна съедать
    # потолок времени стадии, иначе выигрыш от неё теряется.
    clone = _clone(tmp_path)
    monkeypatch.setattr(activities, "_require_workspace", lambda a, r: str(clone))
    monkeypatch.setattr(repowise_module, "enabled", lambda: True)
    seen = {}

    def probe(timeout=5.0):
        seen["timeout"] = timeout
        return False

    monkeypatch.setattr(repowise_module, "available", probe)
    monkeypatch.setattr(activities, "_run_claude", lambda prompt, cwd: None)
    asyncio.run(activities.run_fnr_stage(_analyze(), "repowise"))
    assert seen["timeout"] <= repowise_module.PROBE_TIMEOUT_SEC


# --- Публикация артефакта диалога (FR-15) ---
#
# Диалог публикуется тем же путём, что и остальные артефакты FNR: комментарием
# со ссылками и пушем в ветку. Второй путь публикации был бы дешевле в моменте
# и дороже потом — он разъедется с первым ровно тогда, когда его перестанут
# трогать.

def test_dialog_reaches_branch_and_summary(tmp_path):
    clone = _clone(tmp_path)
    fnr = clone / activities.FNR_DIR
    (fnr / "repowise-dialog.md").write_text("# Диалог\n\nход 1\n", encoding="utf-8")
    (fnr / "system_requirements.md").write_text("# СТ\n", encoding="utf-8")

    files = activities._collect_fnr_artifacts(str(clone))
    assert f"{activities.FNR_DIR}/repowise-dialog.md" in files

    summary = activities._build_summary(_analyze(), "research/issue-42", files)
    assert "repowise-dialog.md" in summary


def test_summary_names_the_dialog_as_context_source():
    # Человеку, открывшему Issue, из сводки должно быть понятно, откуда взялся
    # дополнительный контекст, — иначе артефакт выглядит служебным мусором.
    files = {f"{activities.FNR_DIR}/repowise-dialog.md": "# Диалог\n"}
    summary = activities._build_summary(_analyze(), "research/issue-42", files)
    assert "Repowise" in summary


# --- Слэш-команды стадий существуют ---
#
# Стадия зовёт `claude -p "/<команда> …"`, а команды берутся из
# `.claude/commands` образа воркера. Нет файла — команда уезжает в модель
# обычным текстом, артефакт не создаётся, и стадия падает на guard'е «артефакт
# не создан». Ровно этот промах нашёлся при подготовке демонстрации: промпт
# стадии был написан, а команда — нет.

def test_every_stage_has_its_command():
    import pathlib
    root = pathlib.Path(activities.__file__).resolve().parents[1]
    missing = []
    for name in activities.FNR_STAGE_NAMES:
        prompt, _, _ = activities._fnr_stage(name, "описание")
        command = prompt.split()[0].lstrip("/")
        if not (root / ".claude" / "commands" / f"{command}.md").exists():
            missing.append(f"{name} → /{command}")
    assert not missing, f"стадии без файла команды: {missing}"


def test_repowise_command_names_the_same_artifact():
    # Имя артефакта в команде и в конвейере обязано совпадать: разъехались —
    # стадия отработает, файл появится не там, и guard уронит прогон.
    import pathlib
    root = pathlib.Path(activities.__file__).resolve().parents[1]
    text = (root / ".claude" / "commands" / "repowise-context.md").read_text(encoding="utf-8")
    assert "repowise-dialog.md" in text
    assert "get_overview" in text
