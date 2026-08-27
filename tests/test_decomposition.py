"""Декомпозиция задачи на подзадачи и раскладка по релизам.

Проверяем то, что нельзя починить после: созданный SubIssue живёт в бэклоге,
его видят люди, на него ссылается родитель. Поэтому битый план обязан отвергаться
целиком ДО первой записи в GitHub.
"""

import pytest

from shared import decomposition as d


def _item(title="сделать", release=d.MVP, depends=None, body="", why=""):
    return {"title": title, "release": release, "depends_on": depends or [],
            "body_markdown": body, "rationale": why}


# --- Проверки плана ---

def test_empty_plan_is_rejected():
    with pytest.raises(d.InvalidPlan, match="пуст"):
        d.validate([])


def test_plan_bigger_than_the_cap_is_rejected():
    """Три десятка подзадач — это не план, а свалка: её никто не разберёт."""
    with pytest.raises(d.InvalidPlan, match="свалка"):
        d.validate([_item(f"задача {i}") for i in range(d.TOTAL_CAP + 1)])


def test_unknown_release_is_rejected():
    with pytest.raises(d.InvalidPlan, match="неизвестный релиз"):
        d.validate([_item(release="asap")])


def test_empty_title_is_rejected():
    with pytest.raises(d.InvalidPlan, match="пустой заголовок"):
        d.validate([_item(title="   ")])


def test_dependency_outside_the_list_is_rejected():
    with pytest.raises(d.InvalidPlan, match="вне списка"):
        d.validate([_item(depends=[5])])


def test_self_dependency_is_rejected():
    with pytest.raises(d.InvalidPlan, match="самой себя"):
        d.validate([_item(depends=[0])])


def test_dependency_cycle_is_rejected():
    """Цикл означает план, который нельзя исполнить: каждая подзадача ждёт
    другую. В GitHub это уже неисправимо."""
    plan = [_item("а", depends=[1]), _item("б", depends=[2]), _item("в", depends=[0])]

    with pytest.raises(d.InvalidPlan, match="цикл"):
        d.validate(plan)


def test_valid_plan_survives_and_is_normalized():
    items = d.validate([{"title": " Считать скидку ", "release": "MVP",
                         "depends_on": [], "body_markdown": "тело", "rationale": "ядро"}])

    assert items[0]["title"] == "Считать скидку"
    assert items[0]["release"] == d.MVP


# --- Раскладка и сводка ---

def test_grouping_keeps_all_three_releases_even_when_empty():
    """Пустой релиз должен быть виден: «SUPPORT пуст» и «SUPPORT забыли» —
    разные сообщения для того, кто читает план."""
    groups = d.group(d.validate([_item()]))

    assert set(groups) == set(d.RELEASES)
    assert groups[d.SUPPORT] == []


def test_summary_shows_dependencies_as_issue_numbers():
    """Порядок исполнения задан зависимостями. «Сначала пункт 1» ничего не
    говорит агенту, если пункт 3 нужен раньше."""
    plan = d.validate([_item("основа"), _item("надстройка", depends=[0])])
    body = d.parent_summary(plan, {0: 11, 1: 12}, summary="итог", branch="research/issue-3")

    assert "#11 — основа" in body
    assert "← после #11" in body
    assert "research/issue-3" in body


def test_summary_marks_an_oversized_mvp():
    """Раздутый MVP — признак, что граница прямого пути проведена не там.
    Молча резать нельзя: решение о границе принимает человек."""
    plan = d.validate([_item(f"шаг {i}") for i in range(d.MVP_SOFT_CAP + 1)])
    body = d.parent_summary(plan, {i: 100 + i for i in range(len(plan))},
                            summary="", branch="")

    assert "граница прямого пути" in body


def test_summary_stays_quiet_on_a_normal_mvp():
    plan = d.validate([_item("шаг")])
    body = d.parent_summary(plan, {0: 5}, summary="", branch="")

    assert "граница прямого пути" not in body


def test_subissue_body_carries_the_chain_key():
    """`root-issue` — то, по чему контур отличает свой выход от входа. Без него
    follow-up уходит в полный триаж и контур начинает кормить себя."""
    plan = d.validate([_item("основа"), _item("надстройка", depends=[0], why="нужна база")])
    body = d.subissue_body(plan[1], parent=3, numbers={0: 11}, index=1)

    assert "root-issue: #3" in body
    assert "Зависит от:** #11" in body
    assert "нужна база" in body


def test_release_label_uses_the_common_prefix():
    assert d.release_label(d.MVP) == "release:mvp"


def test_decomposition_is_on_by_default(monkeypatch):
    monkeypatch.delenv("DECOMPOSE_ENABLED", raising=False)

    assert d.enabled() is True


# --- Правило деления по объявленным зависимостям ---

def test_no_dependencies_means_single_run():
    """Граф без рёбер — не план, а список правок: делить нечего."""
    items = [
        {"title": "Импорт версии", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Лог версии", "release": "mvp", "depends_on": [], "depends_reason": {}},
    ]
    assert d.needs_subissues(items) is False


def test_one_real_dependency_means_split():
    items = [
        {"title": "Загрузить версию", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Отдать версию", "release": "mvp", "depends_on": [0],
         "depends_reason": {"0": "читает version из состояния"}},
    ]
    assert d.needs_subissues(items) is True


def test_single_item_never_splits():
    items = [{"title": "Одна правка", "release": "mvp", "depends_on": [], "depends_reason": {}}]
    assert d.needs_subissues(items) is False


def test_dependency_without_reason_is_reported():
    """Ребро без предмета — выдумка ради вида плана, а не зависимость."""
    items = [
        {"title": "Первый", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Второй", "release": "mvp", "depends_on": [0], "depends_reason": {}},
    ]
    assert d.dependency_reason_missing(items) == ["Второй"]


def test_dependency_with_reason_is_not_reported():
    items = [
        {"title": "Первый", "release": "mvp", "depends_on": [], "depends_reason": {}},
        {"title": "Второй", "release": "mvp", "depends_on": [0],
         "depends_reason": {"0": "использует функцию parse()"}},
    ]
    assert d.dependency_reason_missing(items) == []
