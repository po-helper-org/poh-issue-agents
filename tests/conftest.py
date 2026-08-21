import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# worker/ holds workflows.py, activities.py, github_client.py, llm.py
sys.path.insert(0, str(ROOT / "worker"))
# repo root holds shared/
sys.path.insert(0, str(ROOT))

import pytest

RULES_PATH = ROOT / "config" / "estimation-rules.toml"


@pytest.fixture
def rules():
    """Правила расчёта из репозитория. В контейнере тот же файл лежит по
    /app/config — тесты берут его из исходников."""
    import estimation

    return estimation.load_rules(RULES_PATH)


_FORGE_ENV = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY_B64",
    "GITHUB_PRIVATE_KEY_PATH", "GITHUB_INSTALLATION_ID", "GITHUB_REPOSITORY",
    "GITHUB_WEBHOOK_SECRET", "GH_PUSH_TOKEN", "GH_CLONE_TOKEN",
    "ISSUE_AGENT_REPOS", "DRY_RUN",
)


@pytest.fixture(autouse=True)
def forge_env(monkeypatch):
    """Переменные трекера не протекают между тестами.

    Раньше их ставили по месту в 17 файлах и почти нигде не убирали: тест,
    прошедший в одиночку, мог упасть в общем прогоне из-за порядка запуска.
    Фикстура снимает весь набор до теста; тест ставит только то, что ему нужно.
    """
    for name in _FORGE_ENV:
        monkeypatch.delenv(name, raising=False)
