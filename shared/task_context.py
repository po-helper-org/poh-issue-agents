"""Состав каталога `.harness/` — контекст задачи, который читает исполнитель.

Смысл каталога в том, что контекст НЕ пересказывается. Исполнитель открывает
файлы из git по мере надобности, поэтому потолков на объём нет и усечения нет.

Каталог коммитится в ветку задачи: он виден в PR и читается через полгода —
в отличие от прежней постановки, которая снималась перед коммитом, и
восстановить, что именно видел исполнитель, было нечем.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DIR = ".harness"

PLAN = "plan.md"
REQUIREMENTS = "requirements.md"
HOWTODEMO = "howtodemo.md"
DECISIONS = "decisions.md"
CONTEXT_MAP = "context.md"

TRUNCATION_MARKER = "…[обрезано]"


def _strip_invisible(text: str) -> str:
    """Удаляет пробельные символы и невидимые символы (BOM, zero-width space)."""
    # Сначала удаляем обычные пробелы
    text = text.strip()
    # Удаляем BOM (U+FEFF) и zero-width space (U+200B) и другие невидимые
    invisible_chars = {'﻿', '​', '‌', '‍'}
    while text and text[0] in invisible_chars:
        text = text[1:]
    while text and text[-1] in invisible_chars:
        text = text[:-1]
    return text


def render_map(entries: dict[str, str]) -> str:
    """Карта контекста: что где лежит и в каком порядке читать."""
    lines = ["# Контекст задачи", "",
             "Читать в этом порядке. Все файлы лежат рядом с этим.", ""]
    lines += [f"- `{name}` — {what}" for name, what in entries.items()]
    return "\n".join(lines) + "\n"


def missing(root, entries: dict[str, str]) -> list[str]:
    """Имена объявленных файлов, которых нет либо которые пусты.

    Пустой файл считается отсутствующим намеренно: он выглядит доставленным и
    потому опаснее — стадия отчитается успехом, а исполнитель не получит
    ничего.

    Нечитаемый файл (с неверной кодировкой) также считается отсутствующим:
    такой файл не может быть использован исполнителем.
    """
    base = Path(root)
    absent = []
    for name in entries:
        path = base / name
        if not path.exists():
            absent.append(name)
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("файл %s не прочитан: %s", path.name, exc)
            absent.append(name)
            continue

        # Проверяем, что после удаления пробелов и невидимых символов что-то остаётся
        if not _strip_invisible(content):
            absent.append(name)

    return absent


def truncation_markers(root) -> list[str]:
    """Файлы каталога, где остался след обрезки.

    Проходит рекурсивно по всему каталогу, проверяя все файлы, не только .md.
    Нечитаемые файлы пропускаются с предупреждением — проверка остальных продолжается.
    """
    base = Path(root)
    found = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("файл %s не проверен на обрезку: %s", path.name, exc)
            continue

        if TRUNCATION_MARKER in content:
            found.append(path.name)

    return found
