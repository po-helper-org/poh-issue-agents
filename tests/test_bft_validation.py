"""Тесты проверок БФТ из Issue #78.

Проверки, которые ловят то, что пайплайн раньше доверял модели:
- минимальный размер артефактов (находка A)
- валидность якорей R1 (находка B)
- формальные гейты валидации (находка E)
"""

import json
import tempfile
from pathlib import Path

import pytest

from shared import bft


# --- Тесты проверки размера артефактов (находка A) ---

def test_normal_artifact_size_passes():
    """Артефакт нормального размера проходит проверку."""
    issues = bft.check_artifact_size("problem.md", 1000)
    assert issues == []


def test_too_small_artifact_fails():
    """Слишком маленький артефакт не проходит проверку."""
    issues = bft.check_artifact_size("problem.md", 100)
    assert len(issues) == 1
    assert "слишком мал" in issues[0]
    assert "problem.md" in issues[0]


def test_artifact_without_size_requirement_passes():
    """Артефакт без требования к размеру проходит проверку."""
    issues = bft.check_artifact_size("unknown.md", 10)
    assert issues == []


def test_exactly_minimum_size_passes():
    """Артефакт ровно минимального размера проходит."""
    issues = bft.check_artifact_size("problem.md", 500)
    assert issues == []


# --- Тесты извлечения каскада из документа (находка B) ---

def test_extract_cascade_from_json_block():
    """Каскад извлекается из JSON-блока в документе."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, 
                                     encoding='utf-8') as f:
        cascade = {"requirements": [{"id": "БТ-1", "type": "БТ"}], "anchors": []}
        f.write("# Документ\n\n```json\n")
        f.write(json.dumps(cascade, ensure_ascii=False))
        f.write("\n```\n")
        f.flush()
        temp_path = f.name
    
    try:
        result = bft.extract_cascade_from_document(temp_path)
        assert result is not None
        assert result["requirements"][0]["id"] == "БТ-1"
    finally:
        Path(temp_path).unlink()


def test_extract_cascade_from_plain_json():
    """Каскад извлекается из plain JSON в документе."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                     encoding='utf-8') as f:
        cascade = {"requirements": [{"id": "ПТ-1", "type": "ПТ"}], "anchors": []}
        f.write("# Документ\n\n")
        f.write(json.dumps(cascade, ensure_ascii=False))
        f.write("\n\nКонец документа\n")
        f.flush()
        temp_path = f.name
    
    try:
        result = bft.extract_cascade_from_document(temp_path)
        assert result is not None
        assert result["requirements"][0]["id"] == "ПТ-1"
    finally:
        Path(temp_path).unlink()


def test_nonexistent_document_returns_none():
    """Несуществующий документ возвращает None."""
    result = bft.extract_cascade_from_document("/nonexistent/file.md")
    assert result is None


def test_document_without_cascade_returns_none():
    """Документ без каскада возвращает None."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                     encoding='utf-8') as f:
        f.write("# Просто документ\n\nТекст без JSON\n")
        f.flush()
        temp_path = f.name
    
    try:
        result = bft.extract_cascade_from_document(temp_path)
        assert result is None
    finally:
        Path(temp_path).unlink()


# --- Тесты проверки формальных гейтов (находка E) ---

def test_clean_document_passes_formal_gates():
    """Чистый документ проходит все формальные гейты."""
    doc = """
# БФТ

## Функциональные требования

### БТ-1
Требование бизнес-типа.

### ПТ-1
Требование продук-типа.

## Нефункциональные требования

### НФТ-1
Время ответа < 100 мс.
"""
    issues = bft.validate_formal_gates(doc, "issue-42")
    assert issues == []


def test_forbidden_section_is_detected():
    """Запрещённый раздел детектируется."""
    doc = """
# БФТ

## Ключевые решения

Какие-то решения.
"""
    issues = bft.validate_formal_gates(doc, "issue-42")
    assert any("запрещённый раздел" in issue and "Ключевые решения" in issue 
               for issue in issues)


def test_nft_without_numeric_value_is_detected():
    """НФТ без числового значения детектируется."""
    doc = """
# БФТ

## Нефункциональные требования

### НФТ-1
Быстро и качественно.
"""
    issues = bft.validate_formal_gates(doc, "issue-42")
    assert any("НФТ-1" in issue and "без числового значения" in issue 
               for issue in issues)


def test_unknown_requirement_type_is_detected():
    """Неизвестный тип требования детектируется."""
    doc = """
# БФТ

## Требования

### XYZ-1
Требование неизвестного типа.
"""
    issues = bft.validate_formal_gates(doc, "issue-42")
    assert any("неизвестный тип требования" in issue and "XYZ" in issue 
               for issue in issues)


# --- Тесты проверки якорей (находка B) ---

def test_valid_anchors_pass():
    """Валидные якоря проходят проверку."""
    cascade = {
        "requirements": (
            [{"id": f"БТ-{i}", "type": "БТ"} for i in range(1, 5)] +  # 4 БТ
            [{"id": f"ПТ-{i}", "type": "ПТ"} for i in range(1, 6)] +  # 5 ПТ
            [{"id": f"ИТ-{i}", "type": "ИТ"} for i in range(1, 7)] +  # 6 ИТ
            [{"id": f"ФТ-{i}", "type": "ФТ"} for i in range(1, 11)] + # 10 ФТ
            [{"id": f"НФТ-{i}", "type": "НФТ"} for i in range(1, 5)] # 4 НФТ
        ),
        "anchors": [
            {"fact": "факт", "source": "src/file.js:10", "rank": "R1", "kind": "Код"}
            for _ in range(24)
        ]
    }
    line_counts = {"src/file.js": 50}
    
    gaps = bft.cascade_gaps(cascade, line_counts)
    assert gaps == []


def test_anchor_past_file_end_is_detected():
    """Якорь за концом файла детектируется."""
    cascade = {
        "requirements": [{"id": "БТ-1", "type": "БТ"} for _ in range(4)] +
                     [{"id": "ПТ-1", "type": "ПТ"} for _ in range(5)] +
                     [{"id": "ИТ-1", "type": "ИТ"} for _ in range(6)] +
                     [{"id": "ФТ-1", "type": "ФТ"} for _ in range(10)] +
                     [{"id": "НФТ-1", "type": "НФТ"} for _ in range(4)],
        "anchors": [
            {"fact": "факт", "source": "src/file.js:999", "rank": "R1", "kind": "Код"}
            for _ in range(24)
        ]
    }
    line_counts = {"src/file.js": 50}
    
    gaps = bft.cascade_gaps(cascade, line_counts)
    assert any("строки 999 не существует" in gap for gap in gaps)


def test_anchor_to_nonexistent_file_is_detected():
    """Якорь к несуществующему файлу детектируется."""
    cascade = {
        "requirements": [{"id": "БТ-1", "type": "БТ"} for _ in range(4)] +
                     [{"id": "ПТ-1", "type": "ПТ"} for _ in range(5)] +
                     [{"id": "ИТ-1", "type": "ИТ"} for _ in range(6)] +
                     [{"id": "ФТ-1", "type": "ФТ"} for _ in range(10)] +
                     [{"id": "НФТ-1", "type": "НФТ"} for _ in range(4)],
        "anchors": [
            {"fact": "факт", "source": "nonexistent/file.js:10", "rank": "R1", "kind": "Код"}
            for _ in range(24)
        ]
    }
    line_counts = {"src/file.js": 50}
    
    gaps = bft.cascade_gaps(cascade, line_counts)
    assert any("такого файла во входе нет" in gap for gap in gaps)


def test_too_few_requirements_is_detected():
    """Недостаточное количество требований детектируется."""
    cascade = {
        "requirements": [{"id": "БТ-1", "type": "БТ"}],  # Только 1, нужно 4
        "anchors": [{"fact": "факт", "source": "src/file.js:10", "rank": "R1", "kind": "Код"}
                   for _ in range(24)]
    }
    line_counts = {"src/file.js": 50}
    
    gaps = bft.cascade_gaps(cascade, line_counts)
    assert any("БТ" in gap and "добавь" in gap for gap in gaps)


def test_too_few_anchors_is_detected():
    """Недостаточное количество якорей детектируется."""
    cascade = {
        "requirements": [{"id": "БТ-1", "type": "БТ"} for _ in range(4)] +
                     [{"id": "ПТ-1", "type": "ПТ"} for _ in range(5)] +
                     [{"id": "ИТ-1", "type": "ИТ"} for _ in range(6)] +
                     [{"id": "ФТ-1", "type": "ФТ"} for _ in range(10)] +
                     [{"id": "НФТ-1", "type": "НФТ"} for _ in range(4)],
        "anchors": [{"fact": "факт", "source": "src/file.js:10", "rank": "R1", "kind": "Код"}
                   for _ in range(5)]  # Только 5, нужно 24
    }
    line_counts = {"src/file.js": 50}
    
    gaps = bft.cascade_gaps(cascade, line_counts)
    assert any("якорей 5" in gap for gap in gaps)


# --- Тесты обновлённых зависимостей стадий (находка D) ---

def test_draft_stage_has_complete_dependencies():
    """Стадия draft имеет полные зависимости."""
    stages = bft.deep_stages(42)
    draft_stage = next((s for s in stages if s[0] == "draft"), None)
    assert draft_stage is not None
    
    # draft должен зависеть от concept, problem, pack, statement и src
    requires = draft_stage[3]  # (name, prompt, expected, requires)
    assert requires is not None
    assert "concept.md" in requires
    assert "problem.md" in requires
    assert "po-statement.md" in requires
    assert "bft-context-pack.md" in requires
    assert "src" in requires


def test_problem_stage_has_statement_dependency():
    """Стадия problem зависит от statement."""
    stages = bft.deep_stages(42)
    problem_stage = next((s for s in stages if s[0] == "problem"), None)
    assert problem_stage is not None
    
    requires = problem_stage[3]
    assert requires is not None
    assert "po-statement.md" in requires


def test_concept_stage_has_complete_dependencies():
    """Стадия concept имеет полные зависимости."""
    stages = bft.deep_stages(42)
    concept_stage = next((s for s in stages if s[0] == "concept"), None)
    assert concept_stage is not None
    
    requires = concept_stage[3]
    assert requires is not None
    assert "problem.md" in requires
    assert "po-statement.md" in requires
    assert "bft-context-pack.md" in requires
