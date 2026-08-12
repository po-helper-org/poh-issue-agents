import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# app.py и pipeline.storage создают DATA_DIR при импорте — направляем его
# во временную папку теста, а не в реальный /data (там прав на запись нет,
# да и незачем мусорить настоящее состояние прогонов тестовыми файлами).
os.environ.setdefault("DATA_DIR", "/tmp/vrm_pytest_data")
os.environ.setdefault("BASIC_AUTH_USER", "test")
os.environ.setdefault("BASIC_AUTH_PASS", "test")
os.environ.setdefault("RUN_TOKEN", "test-token")

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
