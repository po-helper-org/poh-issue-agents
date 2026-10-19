"""Контракт коробки БФТ: схема протокола и эталоны (#363).

По этим же эталонам гоняет контрактные тесты тестовый двойник исполнителя
(po-helper-org/poh-widget-harness#43): если эталон перестал проходить схему здесь,
двойник и коробка уже разъехались.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

DIR = Path(__file__).resolve().parent.parent / "docs" / "bft-box" / "contract"
SCHEMA = json.loads((DIR / "protocol.schema.json").read_text())
CASES = json.loads((DIR / "cases" / "cases.json").read_text())


def validator(defn: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{defn}", "$defs": SCHEMA["$defs"]})


def load(name: str) -> dict:
    return json.loads((DIR / "cases" / name).read_text())


def test_схема_сама_корректна():
    Draft202012Validator.check_schema(SCHEMA)


def test_каждый_файл_эталонов_описан_в_cases():
    files = {p.name for p in (DIR / "cases").glob("*.json")} - {"cases.json"}
    assert files == {c["file"] for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
def test_эталон_проходит_схему(case):
    errors = sorted(validator(case["def"]).iter_errors(load(case["file"])), key=str)
    assert not errors, [e.message for e in errors]


def iterations():
    return [load(c["file"]) for c in CASES if c["def"] == "Iteration"]


def test_внешние_ссылки_возвращаются_как_есть_в_каждой_итерации():
    refs = load("01-start-request.json")["external_refs"]
    assert all(it["external_refs"] == refs for it in iterations())


def test_номера_итераций_идут_подряд():
    numbers = sorted({it["number"] for it in iterations()})
    assert numbers == list(range(1, max(numbers) + 1))


def test_id_указания_стабилен_между_итерациями():
    seen = {}
    for it in iterations():
        for d in it.get("directives", []):
            if d["id"] in seen:
                assert d["text"].split("?")[0] == seen[d["id"]].split("?")[0], d["id"]
            seen[d["id"]] = d["text"]


def test_без_команды_первое_указание_уточнить_команду():
    first = load("04-iteration-1-brief.json")
    assert first["team"] is None and first["directives"][0]["kind"] == "clarify_team"


def test_адресат_вне_плана_сначала_утверждается_po():
    it = load("10-iteration-4-plan-change.json")
    approve = [d for d in it["directives"] if d["kind"] == "approve_plan_change"]
    assert approve and approve[0]["to"]["role"] == "po"
    assert not any("главн" in (d["to"].get("person") or "").lower() for d in it["directives"])


def test_доработка_после_приёмки_поднимает_версию_пакета():
    before, after = load("14-iteration-8-acceptance.json"), load("20-iteration-9-rework.json")
    assert after["initiative_id"] == before["initiative_id"]
    assert after["package"]["version"] == before["package"]["version"] + 1


def test_md_вид_собирает_вопросы_одному_адресату_вместе():
    spec = importlib.util.spec_from_file_location("render_md", DIR / "render_md.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    md = mod.render(load("08-iteration-3-working.json"))
    assert "Руководитель группы расчётов** — одним обращением" in md
    assert md.count("dir-005") == 1 and "dir-006" in md


# Отрицательные случаи: схема должна ловить то, о чём договорились.

def broken(name: str, mutate) -> list:
    body = copy.deepcopy(load(name))
    mutate(body)
    defn = next(c["def"] for c in CASES if c["file"] == name)
    return list(validator(defn).iter_errors(body))


def test_на_приёмке_нельзя_с_красной_проверкой():
    assert broken("14-iteration-8-acceptance.json", lambda b: b["checks"][0].update(status="red"))


def test_пока_готовится_указаний_нет():
    assert broken("03-iteration-1-preparing.json", lambda b: b.update(directives=[]))


def test_готовая_итерация_без_указаний_не_проходит():
    assert broken("08-iteration-3-working.json", lambda b: b.pop("directives"))


def test_ответ_без_содержания_не_проходит():
    assert broken("09-submit-mixed-outcomes.json", lambda b: b["outcomes"][0].pop("content"))


def test_другая_мажорная_версия_не_проходит():
    assert broken("01-start-request.json", lambda b: b.update(schema_version="2.0.0"))


def test_старт_без_ключа_идемпотентности_не_проходит():
    assert broken("01-start-request.json", lambda b: b.pop("idempotency_key"))
