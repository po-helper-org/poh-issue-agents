"""Числа живут в двух местах: config/estimation-rules.toml (источник правды
для расчёта) и таблицы docs/methodology/task-estimation.md (для чтения
человеком). Этот тест не даёт копиям разъехаться.

Соглашение по формату: в таблице методологии ячейка с точечным путём ключа
TOML, а следом за ней — ячейка с числом. Строки без такой пары тест
пропускает, поэтому пояснительные таблицы ничего не ломают.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "methodology" / "task-estimation.md"
RULES = ROOT / "config" / "estimation-rules.toml"

KEY_PATH = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _lookup(rules: dict, dotted: str):
    node = rules
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _pairs_from_doc() -> list[tuple[str, float]]:
    pairs = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        for left, right in zip(cells, cells[1:]):
            if not KEY_PATH.match(left):
                continue
            try:
                pairs.append((left, float(right.replace(",", "."))))
            except ValueError:
                continue
    return pairs


def test_doc_declares_at_least_the_core_keys():
    keys = {key for key, _ in _pairs_from_doc()}
    assert "work_type.new_development" in keys
    assert "pert.buffer_k" in keys
    assert len(keys) >= 20


def test_every_number_in_doc_matches_config():
    with open(RULES, "rb") as f:
        rules = tomllib.load(f)
    mismatched = []
    for key, value in _pairs_from_doc():
        actual = _lookup(rules, key)
        if actual is None or float(actual) != value:
            mismatched.append((key, value, actual))
    assert not mismatched, f"расходятся с TOML: {mismatched}"
