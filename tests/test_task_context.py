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


# Находка 1: BOM и невидимые символы
def test_bom_only_file_counts_as_missing(tmp_path):
    """Файл из одного BOM считается отсутствующим."""
    (tmp_path / task_context.PLAN).write_bytes(b'\xef\xbb\xbf')
    assert task_context.missing(tmp_path, {task_context.PLAN: "план"}) == [task_context.PLAN]


def test_zero_width_space_counts_as_missing(tmp_path):
    """Файл из одного zero-width space считается отсутствующим."""
    (tmp_path / task_context.PLAN).write_text("​", encoding="utf-8")
    assert task_context.missing(tmp_path, {task_context.PLAN: "план"}) == [task_context.PLAN]


def test_bom_plus_whitespace_counts_as_missing(tmp_path):
    """Файл с BOM и пробелами считается отсутствующим."""
    (tmp_path / task_context.PLAN).write_bytes(b'\xef\xbb\xbf   \n  ')
    assert task_context.missing(tmp_path, {task_context.PLAN: "план"}) == [task_context.PLAN]


# Находка 2: Нечитаемый файл
def test_unreadable_file_counts_as_missing(tmp_path):
    """Файл с неверной кодировкой не должен рушить проверку целиком."""
    # Пишем тестовый файл с невалидной UTF-8
    bad_file = tmp_path / task_context.REQUIREMENTS
    bad_file.write_bytes(b'\x80\x81\x82')

    good_file = tmp_path / task_context.PLAN
    good_file.write_text("целый текст", encoding="utf-8")

    # Должны получить оба файла в списке: плохо кодированный и отсутствующий
    absent = task_context.missing(tmp_path, {
        task_context.PLAN: "план",
        task_context.REQUIREMENTS: "требования",
        task_context.DECISIONS: "решения",
    })
    # REQUIREMENTS должен быть в списке как нечитаемый
    # DECISIONS отсутствует
    assert task_context.REQUIREMENTS in absent
    assert task_context.DECISIONS in absent
    assert task_context.PLAN not in absent
    assert len(absent) == 2


# Находка 3: Рекурсивный поиск маркеров
def test_truncation_marker_in_nested_file(tmp_path):
    """Маркер обрезки во вложенной папке должен быть найден."""
    nested = tmp_path / "subdir"
    nested.mkdir()
    (nested / "nested.md").write_text("текст …[обрезано]", encoding="utf-8")

    found = task_context.truncation_markers(tmp_path)
    # Должна найтись вложенная папка/файл
    assert any("nested.md" in str(p) for p in found) or "nested.md" in found


def test_truncation_marker_in_non_md_file(tmp_path):
    """Маркер обрезки в файле не-.md должен быть найден."""
    (tmp_path / "artifact.txt").write_text("текст …[обрезано]", encoding="utf-8")
    (tmp_path / "howtodemo.puml").write_text("diagram …[обрезано]", encoding="utf-8")

    found = task_context.truncation_markers(tmp_path)
    # Должны найтись оба файла (не только .md)
    assert len(found) >= 2
