"""Состав каталога `.harness/` — контекст задачи, который читает исполнитель.

Смысл каталога в том, что контекст НЕ пересказывается. Исполнитель открывает
файлы из git по мере надобности, поэтому потолков на объём нет и усечения нет.

Каталог коммитится в ветку задачи: он виден в PR и читается через полгода —
в отличие от прежней постановки, которая снималась перед коммитом, и
восстановить, что именно видел исполнитель, было нечем.

Модуль намеренно чистый: ни сети, ни Temporal, ни GitHub.
"""

from pathlib import Path

DIR = ".harness"

PLAN = "plan.md"
REQUIREMENTS = "requirements.md"
HOWTODEMO = "howtodemo.md"
DECISIONS = "decisions.md"
CONTEXT_MAP = "context.md"

TRUNCATION_MARKER = "…[обрезано]"


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
    """
    base = Path(root)
    absent = []
    for name in entries:
        path = base / name
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            absent.append(name)
    return absent


def truncation_markers(root) -> list[str]:
    """Файлы каталога, где остался след обрезки."""
    base = Path(root)
    found = []
    for path in sorted(base.glob("*.md")):
        if TRUNCATION_MARKER in path.read_text(encoding="utf-8"):
            found.append(path.name)
    return found
