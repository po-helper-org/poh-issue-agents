import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# worker/ holds workflows.py, activities.py, github_client.py, llm.py
sys.path.insert(0, str(ROOT / "worker"))
# repo root holds shared/
sys.path.insert(0, str(ROOT))
