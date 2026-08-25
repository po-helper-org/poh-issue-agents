"""Вебхук не может импортировать модули воркера — ни строкой, ни отложенно.

Раскладка образов несимметрична, и это свойство сборки, а не упущение:
`worker/Dockerfile` кладёт содержимое `worker/` плоско в `/app`, а
`webhook/Dockerfile` — содержимое `webhook/`. Каталога `worker/` в образе
вебхука нет вовсе, `shared/` есть у обоих.

В тестах имя `worker` тоже не пакет: `conftest.py` кладёт в `sys.path` сам
каталог `worker/`, и имя перехватывает модуль `worker/worker.py`.

Проверка нужна потому, что отказ этого класса молчаливый. На `main` жил
`from worker import github_client` внутри `except Exception` (пришёл мержем
`aa3551d`): реакция на комментарий не ставилась никогда, а в логе стояло
«не смог поставить реакцию» — исправная с виду работа без результата.

Отложенный импорт внутри функции проверяется наравне с верхним уровнем:
именно так дефект и выглядел.
"""

import ast
from pathlib import Path

WEBHOOK = Path(__file__).resolve().parent.parent / "webhook" / "main.py"


def _worker_imports(source: str) -> list[str]:
    """Все импорты из `worker`, на любой глубине вложенности."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names
                      if a.name == "worker" or a.name.startswith("worker.")]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "worker" or module.startswith("worker."):
                found += [f"from {module} import {a.name}" for a in node.names]
    return found


def test_webhook_does_not_import_worker():
    found = _worker_imports(WEBHOOK.read_text(encoding="utf-8"))
    assert not found, (
        "вебхук импортирует модули воркера, в его образе их нет: "
        + ", ".join(found))
