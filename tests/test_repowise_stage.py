"""Стадия repowise в конвейере аналитики.

Состав стадий задан в четырёх местах сразу — набор артефактов, цепочка,
перечень имён и входные условия. Рассогласование этих мест проявляется не
ошибкой при запуске, а отказом живого прогона, поэтому тест состава дешевле
любого другого способа его поймать.
"""

import activities


def test_repowise_is_first_stage():
    assert activities.FNR_STAGE_NAMES[0] == "repowise"


def test_task_stage_requires_dialog_artifact():
    assert activities._FNR_STAGE_REQUIRES["task"] == \
        f"{activities.FNR_DIR}/repowise-dialog.md"


def test_repowise_stage_has_no_input_requirement():
    # Первая стадия конвейера: требовать от неё чего-либо на входе не с чего.
    assert activities._FNR_STAGE_REQUIRES["repowise"] is None


def test_dialog_artifact_is_collected():
    assert "repowise-dialog.md" in activities.ARTIFACT_FILES


def test_dialog_artifact_is_visible_to_estimation():
    assert any("repowise-dialog" in p for p in activities.ARTIFACT_PATHS)


def test_every_stage_name_resolves():
    # _fnr_stage поднимает ValueError на неизвестном имени; перечень и цепочка
    # обязаны совпадать поимённо.
    for name in activities.FNR_STAGE_NAMES:
        prompt, expected, requires = activities._fnr_stage(name, "описание")
        assert prompt
