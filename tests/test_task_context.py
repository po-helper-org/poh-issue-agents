"""Каталог контекста задачи: исполнитель читает файлы, а не пересказ.

До этого постановка упаковывалась в один файл с потолками 50000 знаков на всё
и 10000 на артефакт, лишние секции вытеснялись целиком. Докстринг того кода
признавал: «Переполнение достижимо штатно». Потеря контекста была не риском, а
заложенным поведением.
"""

from shared import task_context


def test_map_lists_every_entry():
    text = task_context.render_map({
        task_context.PLAN: "план работ",
        task_context.REQUIREMENTS: "системные требования",
    })
    assert task_context.PLAN in text
    assert "план работ" in text
    assert task_context.REQUIREMENTS in text


def test_missing_names_absent_files(tmp_path):
    (tmp_path / task_context.PLAN).write_text("текст", encoding="utf-8")
    absent = task_context.missing(tmp_path, {
        task_context.PLAN: "план",
        task_context.REQUIREMENTS: "требования",
    })
    assert absent == [task_context.REQUIREMENTS]


def test_empty_file_counts_as_missing(tmp_path):
    """Пустой файл хуже отсутствующего: он выглядит доставленным."""
    (tmp_path / task_context.PLAN).write_text("   \n", encoding="utf-8")
    assert task_context.missing(tmp_path, {task_context.PLAN: "план"}) == [task_context.PLAN]


def test_truncation_marker_is_found(tmp_path):
    (tmp_path / task_context.PLAN).write_text("начало …[обрезано]", encoding="utf-8")
    assert task_context.truncation_markers(tmp_path) == [task_context.PLAN]


def test_clean_directory_has_no_markers(tmp_path):
    (tmp_path / task_context.PLAN).write_text("целый текст", encoding="utf-8")
    assert task_context.truncation_markers(tmp_path) == []
