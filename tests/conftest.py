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
