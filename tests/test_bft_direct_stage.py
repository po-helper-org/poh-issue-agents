"""Прямые стадии БФТ: разбор каскада, проверка полноты и якорей, выбор пути.

Замена `claude -p` двумя вызовами модели проверяется здесь без сети: разбор и
проверка — чистые функции, а выбор исполнителя — подменяемые вызовы.
"""

import asyncio
import json

import pytest

import activities
from shared import bft
from shared.workflow_types import BftRequest


# --- Флаг ---

def test_no_direct_stages_by_default(monkeypatch):
    monkeypatch.delenv("BFT_DIRECT_STAGES", raising=False)
    assert bft.direct_stages() == set()


@pytest.mark.parametrize("raw,expected", [
    ("draft", {"draft"}),
    ("draft,validate", {"draft", "validate"}),
    (" draft , validate ", {"draft", "validate"}),
    ("", set()),
    (" , ", set()),
])
def test_direct_stages_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("BFT_DIRECT_STAGES", raw)
    assert bft.direct_stages() == expected


# --- Разбор каскада ---

CASCADE = {"requirements": [{"id": "БТ-1", "type": "БТ"}], "anchors": []}


def test_parse_cascade_accepts_plain_json():
    assert bft.parse_cascade(json.dumps(CASCADE)) == CASCADE


def test_parse_cascade_survives_fenced_block_and_chatter():
    text = ("Собрал каскад, вот он:\n\n```json\n" + json.dumps(CASCADE)
            + "\n```\n\nДальше можно рендерить документ.")
    assert bft.parse_cascade(text) == CASCADE


def test_parse_cascade_reports_missing_json():
    with pytest.raises(ValueError, match="нет JSON"):
        bft.parse_cascade("Каскад собран, файл записан. Дальше /bft-validate")


# --- Полнота и якоря ---

def _full_cascade(**over):
    reqs = []
    for kind, count in bft.CASCADE_FLOOR.items():
        reqs += [{"id": f"{kind}-{i}", "type": kind} for i in range(1, count + 1)]
    cascade = {
        "requirements": reqs,
        "anchors": [{"fact": f"факт {i}", "source": "po-statement.md:7",
                     "rank": "R2", "kind": "Постановка"}
                    for i in range(bft.ANCHOR_FLOOR)],
    }
    cascade.update(over)
    return cascade


LINES = {"src/pricing.mjs": 60, "src/server.mjs": 55}


def test_full_cascade_has_no_gaps():
    assert bft.cascade_gaps(_full_cascade(), LINES) == []


def test_missing_type_is_reported_with_the_number_to_add():
    cascade = _full_cascade()
    cascade["requirements"] = [r for r in cascade["requirements"]
                               if not (r["type"] == "ФТ" and r["id"] == "ФТ-10")]
    gaps = bft.cascade_gaps(cascade, LINES)
    assert any("ФТ" in g and "добавь 1" in g for g in gaps)


def test_thin_anchor_table_is_reported():
    cascade = _full_cascade()
    cascade["anchors"] = cascade["anchors"][:5]
    gaps = bft.cascade_gaps(cascade, LINES)
    assert any("якорей 5" in g for g in gaps)


def test_anchor_pointing_past_end_of_file_is_caught():
    """Выдуманная ссылка выглядит в документе как настоящая — ловит только код."""
    cascade = _full_cascade()
    cascade["anchors"][0] = {"fact": "…", "source": "src/pricing.mjs:900",
                             "rank": "R1", "kind": "Код"}
    gaps = bft.cascade_gaps(cascade, LINES)
    assert any("строки 900 не существует" in g for g in gaps)


def test_anchor_to_unknown_file_is_caught():
    cascade = _full_cascade()
    cascade["anchors"][0] = {"fact": "…", "source": "src/imaginary.mjs:3",
                             "rank": "R1", "kind": "Код"}
    gaps = bft.cascade_gaps(cascade, LINES)
    assert any("такого файла во входе нет" in g for g in gaps)


def test_anchor_without_line_number_is_caught():
    cascade = _full_cascade()
    cascade["anchors"][0] = {"fact": "…", "source": "src/pricing.mjs",
                             "rank": "R1", "kind": "Код"}
    gaps = bft.cascade_gaps(cascade, LINES)
    assert any("без номера строки" in g for g in gaps)


def test_r2_anchors_are_not_checked_against_source_lines():
    """R2 ссылается на постановку и решения — строк кода у них нет."""
    cascade = _full_cascade()
    cascade["anchors"][0] = {"fact": "…", "source": "concept.md",
                             "rank": "R2", "kind": "Решение"}
    assert bft.cascade_gaps(cascade, LINES) == []


# --- Выбор исполнителя стадии ---

def _req():
    return BftRequest(repo="o/r", issue_number=41, title="t", body="b",
                      mode=bft.DEEP, instructions="")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    clone = tmp_path / "repo"
    (clone / "sa_documentation").mkdir(parents=True)
    (clone / "sa_documentation" / "repomix-output.xml").write_text("<x/>")
    artefacts = clone / bft.artefacts_dir(41)
    artefacts.mkdir(parents=True)
    (artefacts / "concept.md").write_text("концепт")
    (artefacts / "problem.md").write_text("проблема")
    (artefacts / "bft-context-pack.md").write_text("пак")
    (artefacts / "po-statement.md").write_text("постановка")
    (clone / "src").mkdir()
    (clone / "src" / "pricing.mjs").write_text("строка\n" * 20)
    monkeypatch.setattr(activities, "_bft_clone_dir", lambda req: str(clone))
    return clone


@pytest.mark.timeout(30)
async def test_flagged_stage_skips_the_agent_and_writes_the_artifact(
        workspace, monkeypatch):
    monkeypatch.setenv("BFT_DIRECT_STAGES", "draft")
    monkeypatch.setattr(activities, "_run_claude", lambda *a, **kw: pytest.fail(
        "при включённом флаге стадия не должна запускать claude -p"))
    monkeypatch.setattr(activities, "_bft_direct_draft",
                        lambda req, clone_dir: "---\nEpic: issue-41\n---\n# БФТ")
    # Якоря (Issue #78, находка B) — отдельная, уже покрытая проверка выше по
    # файлу; этот тест — про маршрутизацию агент/прямой вызов, не про неё.
    monkeypatch.setattr(activities, "_validate_stage_anchors",
                        lambda *a, **kw: asyncio.sleep(0, result=[]))

    result = await activities.run_bft_stage(_req(), "draft")

    document = workspace / bft.document_path(41)
    assert document.exists(), "документ прямой стадии не записан"
    assert document.read_text().startswith("---")
    assert result["stage"] == "draft" and result["bytes"] > 0


@pytest.mark.timeout(30)
async def test_stage_without_the_flag_still_goes_through_the_agent(
        workspace, monkeypatch):
    monkeypatch.setenv("BFT_DIRECT_STAGES", "validate")  # draft НЕ включён
    called = []

    def fake_claude(prompt, cwd, mcp=None):
        called.append(prompt)
        (workspace / bft.document_path(41)).parent.mkdir(parents=True, exist_ok=True)
        (workspace / bft.document_path(41)).write_text("документ агента")

    monkeypatch.setattr(activities, "_run_claude", fake_claude)
    monkeypatch.setattr(activities, "_bft_direct_draft", lambda *a: pytest.fail(
        "стадия без флага ушла в прямой вызов"))
    monkeypatch.setattr(activities, "_validate_stage_anchors",
                        lambda *a, **kw: asyncio.sleep(0, result=[]))

    await activities.run_bft_stage(_req(), "draft")

    assert called and called[0].startswith("/bft-draft")


# --- Добор ---

@pytest.mark.timeout(30)
def test_top_up_is_requested_until_the_cascade_is_complete(workspace, monkeypatch):
    thin = {"requirements": [{"id": "БТ-1", "type": "БТ"}], "anchors": []}
    answers = [json.dumps(thin), json.dumps(_full_cascade()), "# документ"]
    asked = []

    def fake_complete(system, user, *, model, **kw):
        asked.append(user)
        return answers[len(asked) - 1]

    monkeypatch.setattr(activities.llm, "complete", fake_complete)
    monkeypatch.setattr(activities, "_bft_stage_system", lambda *a: "system")

    activities._bft_direct_draft(_req(), str(workspace))

    assert len(asked) == 3, "ожидались каскад, добор и рендер"
    assert "Чего не хватает" in asked[1], "добор не назвал, чего именно не хватает"
    assert "Утверждённый каскад" in asked[2], "рендер получил не утверждённый каскад"


@pytest.mark.timeout(30)
def test_complete_cascade_needs_no_top_up(workspace, monkeypatch):
    answers = [json.dumps(_full_cascade()), "# документ"]
    asked = []

    def fake_complete(system, user, *, model, **kw):
        asked.append(user)
        return answers[len(asked) - 1]

    monkeypatch.setattr(activities.llm, "complete", fake_complete)
    monkeypatch.setattr(activities, "_bft_stage_system", lambda *a: "system")

    activities._bft_direct_draft(_req(), str(workspace))

    assert len(asked) == 2, "полный каскад не должен вызывать добор"
