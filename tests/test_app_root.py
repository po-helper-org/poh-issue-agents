"""Корень данных воркера: промпты, конфиг и workspace.

В образе это `/app` (`COPY worker/ .`), а на стенде харнесса БФТ воркер идёт юнитом из
рабочей копии репозитория. Прошитый `/app/prompts` ронял первую же стадию на GLM —
intake_gate на smoke T1 (bft/requests#7): «No such file or directory: '/app/prompts/system_intake_gate.md'».

Модули импортируются в отдельном процессе: перезагрузка `estimation` в общем процессе
подменяла класс `EstimationError`, и `pytest.raises` в соседних тестах переставал его ловить.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def paths(app_root: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "APP_ROOT"}
    if app_root is not None:
        env["APP_ROOT"] = app_root
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "worker"), str(ROOT)])
    code = ("import activities, consolidation_activities, estimation, json; print(json.dumps({"
            "'prompts': str(activities.PROMPTS_DIR), 'config': str(activities.CONFIG_DIR), "
            "'workspace': str(activities.WORKSPACE_DIR), "
            "'consolidation_prompts': str(consolidation_activities.PROMPTS_DIR), "
            "'rules': str(estimation.RULES_PATH)}))")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_по_умолчанию_корень_образа():
    p = paths(None)
    assert p["prompts"] == "/app/prompts"
    assert p["config"] == "/app/config"
    assert p["rules"] == "/app/config/estimation-rules.toml"


def test_корень_задаётся_окружением(tmp_path):
    p = paths(str(tmp_path))
    assert p == {
        "prompts": str(tmp_path / "prompts"),
        "config": str(tmp_path / "config"),
        "workspace": str(tmp_path / "workspace"),
        "consolidation_prompts": str(tmp_path / "prompts"),
        "rules": str(tmp_path / "config" / "estimation-rules.toml"),
    }
